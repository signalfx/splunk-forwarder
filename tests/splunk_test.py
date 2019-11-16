import os
import time
from functools import partial as p

import pytest
from tests.helpers import fake_backend
from tests.helpers.assertions import container_cmd_exit_0, has_datapoint, http_status
from tests.helpers.util import container_ip, ensure_always, get_host_ip, run_splunk, wait_for

SPLUNK_VERSIONS = os.environ.get("SPLUNK_VERSIONS", "6.5.0,7.0.0,8.0.0").split(",")


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


@pytest.mark.parametrize("splunk_version", SPLUNK_VERSIONS)
def test_signalfx_forwarder_app(splunk_version):
    with fake_backend.start(ip_addr=get_host_ip()) as backend:
        with run_splunk(splunk_version) as cont:
            splunk_host = container_ip(cont)
            assert wait_for(p(http_status, url=f"http://{splunk_host}:8000", status=[200]), 120), "service didn't start"

            time.sleep(5)
            assert container_cmd_exit_0(
                cont, "/test/install-app.sh", environment={"INGEST_HOST": backend.ingest_url}, user="splunk"
            ), "failed to install app"
            assert wait_for(p(http_status, url=f"http://{splunk_host}:8000", status=[200]), 120), "service didn't start"

            assert wait_for(
                p(has_series_data, cont), timeout_seconds=60, interval_seconds=2
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

                # test streamtosfx
                backend.reset_datapoints()
                cmd = (
                    "rtsearch 'index=_internal series=* | table _time kb ev max_age | `gauge(kb)` "
                    "| `counter(ev)` | `cumulative_counter(max_age)` | streamtosfx' -detach true"
                )
                code, output = run_splunk_cmd(cont, cmd)
                assert code == 0, output.decode("utf-8")
                assert wait_for(lambda: backend.datapoints, timeout_seconds=60)
                assert wait_for(p(has_datapoint, backend, metric="kb", metric_type="gauge", has_timestamp=True))
                assert wait_for(p(has_datapoint, backend, metric="ev", metric_type="counter", has_timestamp=True))
                assert wait_for(
                    p(has_datapoint, backend, metric="max_age", metric_type="cumulative_counter", has_timestamp=True)
                )

                # check that datapoints are streaming
                num_datapoints = len(backend.datapoints)
                assert wait_for(lambda: len(backend.datapoints) > num_datapoints, timeout_seconds=60)

            finally:
                print_datapoints(backend)
                code, output = cont.exec_run("cat /opt/splunk/var/log/splunk/python.log")
                if code == 0 and output:
                    print("/opt/splunk/var/log/splunk/python.log:")
                    print(output.decode("utf-8"))
