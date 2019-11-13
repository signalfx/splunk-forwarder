ARG SPLUNK_VERSION=latest

FROM splunk/splunk:${SPLUNK_VERSION}

ENV SPLUNK_START_ARGS=--accept-license
ENV SPLUNK_PASSWORD=testing123
ENV PATH=$PATH:/opt/splunk/bin

COPY ./signalfx-forwarder-app*.tar.gz /test/
COPY ./tests/test-services/splunk/install-app.sh /test/
COPY ./tests/test-services/splunk/user-seed.conf /var/opt/splunk/etc/system/local/user-seed.conf

WORKDIR /test
