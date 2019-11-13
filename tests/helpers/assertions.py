"""
Assertions about requests/data received on the fake backend
"""
import socket
import urllib.request
from base64 import b64encode
from http.client import HTTPException


def has_all_dims(dp, dims):
    """
    Tests if `dims`'s are all in a certain datapoint or event
    """
    return dims <= dp.dimensions


def has_no_datapoint(fake_services, metric=None, dimensions=None, value=None, metric_type=None):
    """
    Returns True is there are no datapoints matching the given parameters
    """
    return not has_datapoint(fake_services, metric, dimensions, value, metric_type, count=1)


def has_datapoint(
    fake_services, metric=None, dimensions=None, value=None, metric_type=None, count=1, has_timestamp=True
):
    """
    Returns True if there is a datapoint seen in the fake_services backend that
    has the given attributes.  If a property is not specified it will not be
    considered.  Dimensions, if provided, will be tested as a subset of total
    set of dimensions on the datapoint and not the complete set.
    """
    found = 0
    for dp in fake_services.datapoints:
        if metric and dp.get("metric") != metric:
            continue
        if dimensions and not has_all_dims(dp, dimensions):
            continue
        if metric_type and dp.get("type") != metric_type:
            continue
        if value is not None:
            if float(dp.value) != float(value):
                continue
        if has_timestamp and not dp.get("timestamp"):
            continue
        if not has_timestamp and dp.get("timestamp"):
            continue
        found += 1
        if found >= count:
            return True
    return False


def container_cmd_exit_0(container, command, **kwargs):
    """
    Tests if a command run against a container returns with an exit code of 0
    """
    code, output = container.exec_run(command, **kwargs)
    print(output.decode("utf-8"))
    return code == 0


def http_status(url=None, status=None, username=None, password=None, timeout=1, **kwargs):
    """
    Wrapper around urllib.request.urlopen() that returns True if
    the request returns the any of the specified HTTP status codes.  Accepts
    username and password keyword arguments for basic authorization.
    """
    if status is None:
        status = []

    try:
        # urllib expects url argument to either be a string url or a request object
        req = url if isinstance(url, urllib.request.Request) else urllib.request.Request(url)

        if username and password:
            # create basic authorization header
            auth = b64encode("{0}:{1}".format(username, password).encode("ascii")).decode("utf-8")
            req.add_header("Authorization", "Basic {0}".format(auth))

        return urllib.request.urlopen(req, timeout=timeout, **kwargs).getcode() in status
    except urllib.error.HTTPError as err:
        # urllib raises exceptions for some http error statuses
        return err.code in status
    except (urllib.error.URLError, socket.timeout, HTTPException, ConnectionResetError, ConnectionError):
        return False
