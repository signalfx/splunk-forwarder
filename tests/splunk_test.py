import os
import time
from functools import partial as p

import pytest
from tests.helpers import fake_backend
from tests.helpers.assertions import has_datapoint, http_status
from tests.helpers.util import container_ip, get_host_ip, run_service, wait_for
from tests.paths import REPO_ROOT_DIR

SPLUNK_VERSIONS = os.environ.get("SPLUNK_VERSIONS", "6.5.0,7.0.0,8.0.0").split(",")


@pytest.mark.parametrize("splunk_version", SPLUNK_VERSIONS)
def test_signalfx_forwarder_app(splunk_version):
    with fake_backend.start(ip_addr=get_host_ip()) as backend:
        with run_service(
            "splunk",
            path=REPO_ROOT_DIR,
            dockerfile=REPO_ROOT_DIR / "test-services/splunk/Dockerfile",
            buildargs={"SPLUNK_VERSION": splunk_version},
            environment={"SPLUNK_START_ARGS": "--accept-license", "SPLUNK_PASSWORD": "testing123"},
        ) as cont:
            splunk_host = container_ip(cont)
            assert wait_for(p(http_status, url=f"http://{splunk_host}:8000", status=[200]), 120), "service didn't start"

            time.sleep(5)

            code, output = cont.exec_run(
                "/code/splunk-forwarder/test-services/splunk/install-app.sh",
                environment={"INGEST_HOST": backend.ingest_url},
                user="splunk",
            )

            assert code == 0, f"Failed to install app: {output.decode('utf-8')}"

            assert wait_for(p(http_status, url=f"http://{splunk_host}:8000", status=[200]), 120), "service didn't start"

            try:
                code, output = cont.exec_run(
                    "/code/splunk-forwarder/test-services/splunk/run-search.sh",
                    user="splunk",
                    environment={"SFX_CMD": "tosfx"},
                )
                assert code == 0, f"tosfx query failed: {output.decode('utf-8')}"

                assert wait_for(p(has_datapoint, backend, metric="eventCount"), timeout_seconds=60)
                assert wait_for(p(has_datapoint, backend, metric="kilobytes"), timeout_seconds=60)

                backend.reset_datapoints()

                code, output = cont.exec_run(
                    "/code/splunk-forwarder/test-services/splunk/run-search.sh",
                    user="splunk",
                    environment={"SFX_CMD": "streamtosfx"},
                )
                assert code == 0, f"streamtosfx query failed: {output.decode('utf-8')}"

                assert wait_for(p(has_datapoint, backend, metric="eventCount"), timeout_seconds=60)
                assert wait_for(p(has_datapoint, backend, metric="kilobytes"), timeout_seconds=60)
            finally:
                print("\nDatapoints received:")
                for dp in backend.datapoints:
                    print(dp)
