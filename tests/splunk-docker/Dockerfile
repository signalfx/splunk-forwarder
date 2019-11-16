ARG SPLUNK_VERSION

FROM splunk/splunk:${SPLUNK_VERSION}

ENV SPLUNK_START_ARGS=--accept-license
ENV SPLUNK_PASSWORD=testing123
ENV PATH=$PATH:/opt/splunk/bin

COPY ./signalfx-forwarder-app*.tar.gz /test/
COPY ./tests/splunk-docker/install-app.sh /test/
COPY ./tests/splunk-docker/user-seed.conf /var/opt/splunk/etc/system/local/user-seed.conf

WORKDIR /test
