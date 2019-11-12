#!/bin/bash

set -euxo pipefail

ACCESS_TOKEN=${ACCESS_TOKEN:-testing123}
INGEST_HOST=${INGEST_HOST:-https://ingest.us0.signalfx.com}

/opt/splunk/bin/splunk list user -auth admin:testing123
/opt/splunk/bin/splunk add monitor /opt/splunk/var/log/splunk/splunkd.log
/opt/splunk/bin/splunk install app /code/splunk-forwarder/signalfx-forwarder-app-*.tar.gz
mkdir -p /opt/splunk/etc/apps/signalfx-forwarder-app/local
echo -e "[setupentity]\naccess_token = ${ACCESS_TOKEN}\ningest_url = ${INGEST_HOST}" > /opt/splunk/etc/apps/signalfx-forwarder-app/local/sfx.conf
echo -e "[install]\nis_configured = 1" > /opt/splunk/etc/apps/signalfx-forwarder-app/local/app.conf
/opt/splunk/bin/splunk restart
/opt/splunk/bin/splunk list user -auth admin:testing123
#/opt/splunk/bin/splunk  _internal call /services/apps/local/signalfx-forwarder-app/_reload

echo "Waiting for search data ..."
start_time=$(date +%s)
while [[ $(expr `date +%s` - $start_time) -lt 60 ]]; do
    if /opt/splunk/bin/splunk search 'index=_internal group=per_index_thruput series!=_*' | grep 'Metrics'; then
        exit 0
    fi
    sleep 2
done

echo "Timed out waiting for search data!"
exit 1
