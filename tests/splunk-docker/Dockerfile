ARG SPLUNK_VERSION

FROM splunk/splunk:${SPLUNK_VERSION}

USER root

COPY ./tests/splunk-docker/socat /bin/socat

# Insert our fake certs to the system bundle so they are trusted
COPY ./tests/splunk-docker/certs/*.signalfx.com.* /

RUN command -v curl || (apt update && apt install -y curl)

ENV SPLUNK_START_ARGS=--accept-license
ENV SPLUNK_PASSWORD=testing123
ENV PATH=$PATH:/opt/splunk/bin

COPY ./signalfx-forwarder*.tar.gz /test/
COPY ./tests/splunk-docker/install-app.sh /test/
COPY ./tests/splunk-docker/user-seed.conf /var/opt/splunk/etc/system/local/user-seed.conf

VOLUME /tmp/scratch

WORKDIR /test
