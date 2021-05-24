import os
import time
from functools import partial as p

import pytest
from tests.helpers.assertions import container_cmd_exit_0, has_datapoint, http_status, has_event
from tests.helpers.util import container_ip, ensure_always, run_splunk, wait_for

SPLUNK_VERSIONS = os.environ.get("SPLUNK_VERSIONS", "6.5.0,7.0.0,8.0.0,8.1.0-debian").split(",")

def run_splunk_cmd(cont, cmd):
    cmd = f"splunk {cmd} -auth admin:testing123"
    print(f"Executing '{cmd}'")
    return cont.exec_run(cmd, user="splunk")


def has_series_data(cont):
    cmd = "search 'index=_internal series=* | stats count | where count > 0'"
    code, output = run_splunk_cmd(cont, cmd)
    return code == 0 and output


def print_datapoints(backend):
    print("\nDatapoints received:")
    for dp in backend.datapoints:
        print(dp)


def print_events(backend):
    print("\nEvents received:")
    for ev in backend.events:
        print(ev)

@pytest.mark.parametrize("splunk_version", SPLUNK_VERSIONS)
def test_signalfx_forwarder_app(splunk_version):
    with run_splunk(splunk_version) as [cont, backend]:
        splunk_host = container_ip(cont)
        assert wait_for(p(http_status, url=f"http://{splunk_host}:8000", status=[200]), 120), "service didn't start"

        time.sleep(5)

        # add certs for fake backend to splunk python
        cert_path = cont.exec_run("splunk cmd python -m requests.certs", stderr=False).output.decode("utf-8")
        assert cert_path, "failed to get cert path for splunk python"
        assert container_cmd_exit_0(cont, f"sh -c 'cat /*.cert >> {cert_path}'")

        assert container_cmd_exit_0(cont, "/test/install-app.sh", user="splunk"), "failed to install app"
        assert wait_for(p(http_status, url=f"http://{splunk_host}:8000", status=[200]), 120), "service didn't start"

        assert wait_for(
            p(has_series_data, cont), timeout_seconds=120, interval_seconds=2
        ), "timed out waiting for series data"

        try:
            # test tosfx query with time
            cmd = (
                "search 'index=_internal series=* | table _time kb ev max_age | `gauge(kb)` "
                "| `counter(ev)` | `cumulative_counter(max_age)` | tosfx'"
            )
            code, output = run_splunk_cmd(cont, cmd)
            assert code == 0, output.decode("utf-8")
            assert wait_for(p(has_datapoint, backend, metric="kb", metric_type="gauge", has_timestamp=True))
            assert wait_for(p(has_datapoint, backend, metric="ev", metric_type="counter", has_timestamp=True))
            assert wait_for(
                p(has_datapoint, backend, metric="max_age", metric_type="cumulative_counter", has_timestamp=True)
            )

            # check that datapoints are not streaming
            num_datapoints = len(backend.datapoints)
            assert ensure_always(lambda: len(backend.datapoints) == num_datapoints, timeout_seconds=60)

            # test tosfx query without time
            backend.reset_datapoints()
            cmd = (
                "search 'index=_internal series=* | table kb ev max_age | `gauge(kb)` "
                "| `counter(ev)` | `cumulative_counter(max_age)` | tosfx'"
            )
            code, output = run_splunk_cmd(cont, cmd)
            assert code == 0, output.decode("utf-8")
            assert wait_for(p(has_datapoint, backend, metric="kb", metric_type="gauge", has_timestamp=False))
            assert wait_for(p(has_datapoint, backend, metric="ev", metric_type="counter", has_timestamp=False))
            assert wait_for(
                p(has_datapoint, backend, metric="max_age", metric_type="cumulative_counter", has_timestamp=False)
            )

            # test tosfxevents query with time
            cmd = (
                "search '| makeresults | eval event_sfx_event=\"custom\", message=\"This is a test event for emulating a search\", stack=\"stacktest\", value=\"1234\" | tosfxevents'"
            )
            code, output = run_splunk_cmd(cont, cmd)
            assert code == 0, output.decode("utf-8")
            assert wait_for(p(has_event, backend, dimensions={"message":"This is a test event for emulating a search", "stack":"stacktest", "value": "1234"},category="USER_DEFINED", event_type="custom"))


        finally:
            print_datapoints(backend)
            print_events(backend)
            code, output = cont.exec_run("cat /opt/splunk/var/log/splunk/python.log")
            if code == 0 and output:
                print("/opt/splunk/var/log/splunk/python.log:")
                print(output.decode("utf-8"))
            code, output = cont.exec_run("cat /opt/splunk/var/log/splunk/signalfx-forwarder-app.log")
            if code == 0 and output:
                print("/opt/splunk/var/log/splunk/signalfx-forwarder-app.log")
                print(output.decode("utf-8"))
