#!/bin/bash

set -euxo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ACCESS_TOKEN=${ACCESS_TOKEN:-testing123}
INGEST_HOST=${INGEST_HOST:-https://ingest.us0.signalfx.com}

# create login session
splunk list user -auth admin:testing123

splunk install app ${SCRIPT_DIR}/signalfx-forwarder-*.tar.gz

# create app config
mkdir -p /opt/splunk/etc/apps/signalfx-forwarder-app/local
echo -e "[setupentity]\nsignalfx_realm = \ningest_url = ${INGEST_HOST}" > /opt/splunk/etc/apps/signalfx-forwarder-app/local/sfx.conf
echo -e "[install]\nis_configured = 1" > /opt/splunk/etc/apps/signalfx-forwarder-app/local/app.conf

splunk restart
