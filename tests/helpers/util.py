import io
import os
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import docker
import netifaces as ni

from tests.helpers import fake_backend

DEFAULT_TIMEOUT = int(os.environ.get("DEFAULT_TIMEOUT", 30))
REPO_ROOT_DIR = Path(__file__).parent.parent.parent.resolve()
TEST_DIR = Path(REPO_ROOT_DIR / "tests")
SPLUNK_DOCKER_DIR = Path(TEST_DIR / "splunk-docker")


def get_docker_client():
    return docker.from_env()


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


def print_lines(msg):
    """
    Print each line separately to make it easier to read in pytest output
    """
    for line in msg.splitlines():
        print(line)


def container_ip(container):
    container.reload()
    return container.attrs["NetworkSettings"]["IPAddress"]


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


# Run an HTTPS proxy inside the container with socat so that our fake backend
# doesn't have to worry about HTTPS.  The cert file must be trusted by the
# container running the agent.
# This is pretty hacky but docker makes it hard to communicate from a container
# back to the host machine (and we don't want to use the host network stack in
# the container due to init systems).  The idea is to bind mount a shared
# folder from the test host to the container that two socat instances use to
# communicate using a file to make the bytes flow between the HTTPS proxy and
# the fake backend.
@contextmanager
def socat_https_proxy(container, target_host, target_port, source_host, bind_addr):
    cert = "/%s.cert" % source_host
    key = "/%s.key" % source_host

    socat_bin = SPLUNK_DOCKER_DIR / "socat"
    stopped = False
    socket_path = "/tmp/scratch/%s-%s" % (source_host, container.id[:12])

    # Keep the socat instance in the container running across container
    # restarts
    def keep_running_in_container(cont, sock):
        while not stopped:
            try:
                cont.exec_run(
                    [
                        "socat",
                        "-v",
                        "OPENSSL-LISTEN:443,cert=%s,key=%s,verify=0,bind=%s,fork" % (cert, key, bind_addr),
                        "UNIX-CONNECT:%s" % sock,
                    ],
                    user="root",
                )
            except docker.errors.APIError:
                print("socat died, restarting...")
                time.sleep(0.1)

    threading.Thread(target=keep_running_in_container, args=(container, socket_path)).start()

    proc = subprocess.Popen(
        [socat_bin, "-v", "UNIX-LISTEN:%s,fork" % socket_path, "TCP4:%s:%d" % (target_host, target_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        close_fds=False,
    )

    get_local_out = pull_from_reader_in_background(proc.stdout)

    try:
        yield
    finally:
        stopped = True
        # The socat instance in the container will die with the container
        proc.kill()
        print(get_local_out())


@contextmanager
def run_container(image_name, wait_for_ip=True, print_logs=True, **kwargs):
    client = get_docker_client()

    if not image_name.startswith("sha256"):
        container = client.images.pull(image_name)
    container = retry(lambda: client.containers.create(image_name, **kwargs), docker.errors.DockerException)

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
def run_splunk(version, ingest_host="ingest.us0.signalfx.com", buildargs=None, print_logs=True, **runargs):
    if buildargs is None:
        buildargs = {}

    buildargs["SPLUNK_VERSION"] = version

    if runargs.get("environment") is None:
        runargs["environment"] = {"SPLUNK_START_ARGS": "--accept-license", "SPLUNK_PASSWORD": "testing123"}

    client = get_docker_client()
    image, _ = retry(
        lambda: client.images.build(
            path=str(REPO_ROOT_DIR),
            dockerfile=str(SPLUNK_DOCKER_DIR / "Dockerfile"),
            rm=True,
            forcerm=True,
            buildargs=buildargs,
        ),
        docker.errors.BuildError,
    )

    with fake_backend.start() as backend:
        runargs["volumes"] = {"/tmp/scratch": {"bind": "/tmp/scratch", "mode": "rw"}}
        runargs["extra_hosts"] = {
            # Socat will be running on localhost to forward requests to
            # these hosts to the fake backend
            ingest_host: backend.ingest_host,
        }

        with run_container(image.id, print_logs=print_logs, **runargs) as cont:
            # Workaround for https://bugzilla.redhat.com/show_bug.cgi?id=1769831 which
            # causes yum/dnf to exit with error code 141 when importing GPG keys.
            cont.exec_run("mkdir -p /run/user/0", user="root")

            # Proxy the backend calls through a fake HTTPS endpoint so that we
            # don't have to change the default configuration default by the
            # package.  The base_image used should trust the self-signed certs
            # default in the images dir so that the agent doesn't throw TLS
            # verification errors.
            with socat_https_proxy(
                cont, backend.ingest_host, backend.ingest_port, ingest_host, "127.0.0.1"
            ):
                yield [cont, backend]


def get_host_ip():
    gws = ni.gateways()
    interface = gws["default"][ni.AF_INET][1]
    return ni.ifaddresses(interface)[ni.AF_INET][0]["addr"]


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
