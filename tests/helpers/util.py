import asyncio
import io
import os
import random
import re
import socket
import subprocess
import tarfile
import threading
import time
from contextlib import contextmanager
from functools import partial as p
from io import BytesIO
from typing import Dict, List

import docker
import netifaces as ni
from tests.helpers.assertions import regex_search_matches_output
from tests.paths import TEST_SERVICES_DIR

DEFAULT_TIMEOUT = int(os.environ.get("DEFAULT_TIMEOUT", 30))
DOCKER_API_VERSION = "1.34"
STATSD_RE = re.compile(r"SignalFx StatsD monitor: Listening on host & port udp:\[::\]:([0-9]*)")


def get_docker_client():
    return docker.from_env(version=DOCKER_API_VERSION)


def has_docker_image(client, name):
    return name in [t for image in client.images.list() for t in image.tags]


def assert_wait_for(test, timeout_seconds=DEFAULT_TIMEOUT, interval_seconds=0.2, on_fail=None):
    """
    Runs `wait_for` but raises an assertion if it fails, optionally calling
    `on_fail` before raising an AssertionError
    """
    if not wait_for(test, timeout_seconds, interval_seconds):
        if on_fail:
            on_fail()

        raise AssertionError("test '%s' still failng after %d seconds" % (test, timeout_seconds))


def wait_for(test, timeout_seconds=DEFAULT_TIMEOUT, interval_seconds=0.2):
    """
    Repeatedly calls the test function for timeout_seconds until either test
    returns a truthy value, at which point the function returns True -- or the
    timeout is exceeded, at which point it will return False.
    """
    start = time.time()
    while True:
        if test():
            return True
        if time.time() - start > timeout_seconds:
            return False
        time.sleep(interval_seconds)


def wait_for_value(func, timeout_seconds=DEFAULT_TIMEOUT, interval_seconds=0.2):
    """
    Waits for func to return a non-None value and returns that value.  If the
    func is still returning None after the timeout, returns None to the caller.
    """
    start = time.time()
    while True:
        val = func()
        if val is not None:
            return val
        if time.time() - start > timeout_seconds:
            return None
        time.sleep(interval_seconds)


def wait_for_assertion(test, timeout_seconds=DEFAULT_TIMEOUT, interval_seconds=0.2):
    """
    Waits for the given `test` function passed in to not raise an
    AssertionError.  It is is still raising such an error after the
    timeout_seconds, that exception will be raised by this function itself.
    """
    e = None

    def wrap():
        nonlocal e
        try:
            test()
        except AssertionError as err:
            e = err
            return False
        return True

    if not wait_for(wrap, timeout_seconds, interval_seconds):
        raise e  # pylint: disable=raising-bad-type


def ensure_always(test, timeout_seconds=DEFAULT_TIMEOUT, interval_seconds=0.2):
    """
    Repeatedly calls the given test.  If it ever returns false before the timeout
    given is completed, returns False, otherwise True.
    """
    start = time.time()
    while True:
        if not test():
            return False
        if time.time() - start > timeout_seconds:
            return True
        time.sleep(interval_seconds)


def ensure_never(test, timeout_seconds=DEFAULT_TIMEOUT):
    """
    Repeatedly calls the given test.  If it ever returns true before the timeout
    given is completed, returns False, otherwise True.
    """
    start = time.time()
    while True:
        if test():
            return False
        if time.time() - start > timeout_seconds:
            return True
        time.sleep(0.2)


def print_lines(msg):
    """
    Print each line separately to make it easier to read in pytest output
    """
    for line in msg.splitlines():
        print(line)


def container_ip(container):
    container.reload()
    return container.attrs["NetworkSettings"]["IPAddress"]


def container_hostname(container):
    container.reload()
    return container.attrs["Config"]["Hostname"]


# Ensure a unique internal status server host address.  This supports up to
# 255 concurrent agents on the same pytest worker process, and up to 255
# pytest workers, which should be plenty
def get_unique_localhost():
    worker = int(re.sub(r"\D", "", os.environ.get("PYTEST_XDIST_WORKER", "0")))
    get_unique_localhost.counter += 1
    return "127.%d.%d.0" % (worker, get_unique_localhost.counter % 255)


get_unique_localhost.counter = 0


@contextmanager
def run_subprocess(command: List[str], env: Dict[any, any] = None):
    # subprocess on Windows has a bug where it doesn't like Path.
    proc = subprocess.Popen([str(c) for c in command], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    get_output = pull_from_reader_in_background(proc.stdout)

    try:
        yield [get_output, proc.pid]
    finally:
        proc.terminate()
        proc.wait(15)


@contextmanager
def run_container(image_name, wait_for_ip=True, print_logs=True, **kwargs):
    files = kwargs.pop("files", [])
    client = get_docker_client()

    if not image_name.startswith("sha256"):
        container = client.images.pull(image_name)
    container = retry(lambda: client.containers.create(image_name, **kwargs), docker.errors.DockerException)

    for src, dst in files:
        copy_file_into_container(src, container, dst)

    try:
        container.start()

        def has_ip_addr():
            container.reload()
            return container.attrs["NetworkSettings"]["IPAddress"]

        if wait_for_ip:
            wait_for(has_ip_addr, timeout_seconds=5)
            yield container
    finally:
        try:
            if print_logs:
                print_lines(
                    "Container %s/%s logs:\n%s" % (image_name, container.name, container.logs().decode("utf-8"))
                )
            container.remove(force=True, v=True)
        except docker.errors.NotFound:
            pass


@contextmanager
def run_service(service_name, buildargs=None, print_logs=True, path=None, dockerfile="./Dockerfile", **kwargs):
    if buildargs is None:
        buildargs = {}
    if path is None:
        path = os.path.join(TEST_SERVICES_DIR, service_name)

    client = get_docker_client()
    image, _ = retry(
        lambda: client.images.build(path=str(path), dockerfile=dockerfile, rm=True, forcerm=True, buildargs=buildargs),
        docker.errors.BuildError,
    )
    with run_container(image.id, print_logs=print_logs, **kwargs) as cont:
        yield cont


def get_host_ip():
    gws = ni.gateways()
    interface = gws["default"][ni.AF_INET][1]
    return ni.ifaddresses(interface)[ni.AF_INET][0]["addr"]


def send_udp_message(host, port, msg):
    """
    Send a datagram to the given host/port
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # Internet  # UDP
    sock.sendto(msg.encode("utf-8"), (host, port))


def retry(function, exception, max_attempts=5, interval_seconds=5):
    """
    Retry function up to max_attempts if exception is caught
    """
    for attempt in range(max_attempts):
        try:
            return function()
        except exception as e:
            assert attempt < (max_attempts - 1), "%s failed after %d attempts!\n%s" % (function, max_attempts, str(e))
        time.sleep(interval_seconds)


def get_statsd_port(agent):
    """
    Discover an open port of running StatsD monitor
    """
    assert wait_for(p(regex_search_matches_output, agent.get_output, STATSD_RE.search))
    regex_results = STATSD_RE.search(agent.output)
    return int(regex_results.groups()[0])


def pull_from_reader_in_background(reader):
    output = io.BytesIO()

    def pull_output():
        while True:
            # If any output is waiting, grab it.
            try:
                byt = reader.read(1)
            except OSError:
                return
            if not byt:
                return
            if isinstance(byt, str):
                byt = byt.encode("utf-8")
            output.write(byt)

    threading.Thread(target=pull_output).start()

    def get_output():
        return output.getvalue().decode("utf-8")

    return get_output


def random_hex(bits=64):
    """Return random hex number as a string with the given number of bits (default 64)"""
    return hex(random.getrandbits(bits))[2:]


def copy_file_content_into_container(content, container, target_path):
    copy_file_object_into_container(
        BytesIO(content.encode("utf-8")), container, target_path, size=len(content.encode("utf-8"))
    )


# This is more convoluted that it should be but seems to be the simplest way in
# the face of docker-in-docker environments where volume bind mounting is hard.
def copy_file_object_into_container(fd, container, target_path, size=None):
    tario = BytesIO()
    tar = tarfile.TarFile(fileobj=tario, mode="w")

    info = tarfile.TarInfo(name=target_path)
    if size is None:
        size = os.fstat(fd.fileno()).st_size
    info.size = size

    tar.addfile(info, fd)

    tar.close()

    container.put_archive("/", tario.getvalue())
    # Apparently when the above `put_archive` call returns, the file isn't
    # necessarily fully written in the container, so wait a bit to ensure it
    # is.
    time.sleep(2)


def copy_file_into_container(path, container, target_path):
    with open(path, "rb") as fd:
        copy_file_object_into_container(fd, container, target_path)


def path_exists_in_container(container, path):
    code, _ = container.exec_run("test -e %s" % path)
    return code == 0


def get_container_file_content(container, path):
    assert path_exists_in_container(container, path), "File %s does not exist!" % path
    return container.exec_run("cat %s" % path)[1].decode("utf-8")


def get_stripped_container_id(container_id):
    return container_id.replace("docker://", "").replace("cri-o://", "")


@contextmanager
def run_simple_sanic_app(app):
    app_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    app_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    app_sock.bind(("127.0.0.1", 0))

    port = app_sock.getsockname()[1]

    loop = asyncio.new_event_loop()

    async def start_server():
        server = app.create_server(sock=app_sock, access_log=False)
        loop.create_task(server)

    loop.create_task(start_server())
    threading.Thread(target=loop.run_forever).start()

    try:
        yield port
    finally:
        app_sock.close()
        loop.stop()