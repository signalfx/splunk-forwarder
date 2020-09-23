#!/bin/bash

set -euxo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ACCESS_TOKEN=${ACCESS_TOKEN:-testing123}
INGEST_HOST=${INGEST_HOST:-https://ingest.us0.signalfx.com}

# create login session
splunk list user -auth admin:testing123

splunk install app ${SCRIPT_DIR}/signalfx-forwarder-*.tar.gz

curl -k  https://admin:testing123@localhost:8089/servicesNS/nobody/signalfx-forwarder-app/storage/collections/data/sfx_ingest_config -XPOST -H'Content-Type: application/json' -d "$(printf '{"ingest_url": "%s"}' "$INGEST_HOST")"

splunk restart
