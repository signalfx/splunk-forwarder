import os
import time
from contextlib import contextmanager
from pathlib import Path

import docker
import netifaces as ni

DEFAULT_TIMEOUT = int(os.environ.get("DEFAULT_TIMEOUT", 30))
DOCKER_API_VERSION = "1.34"
REPO_ROOT_DIR = Path(__file__).parent.parent.parent.resolve()
TEST_DIR = Path(REPO_ROOT_DIR / "tests")
SPLUNK_DOCKER_DIR = Path(TEST_DIR / "splunk-docker")


def get_docker_client():
    return docker.from_env(version=DOCKER_API_VERSION)


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
def run_splunk(version, buildargs=None, print_logs=True, **kwargs):
    if buildargs is None:
        buildargs = {}

    buildargs["SPLUNK_VERSION"] = version

    if kwargs.get("environment") is None:
        kwargs["environment"] = {"SPLUNK_START_ARGS": "--accept-license", "SPLUNK_PASSWORD": "testing123"}

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
    with run_container(image.id, print_logs=print_logs, **kwargs) as cont:
        yield cont


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
