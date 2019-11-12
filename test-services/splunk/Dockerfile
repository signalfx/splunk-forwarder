ARG SPLUNK_VERSION=latest

FROM splunk/splunk:${SPLUNK_VERSION}

ENV SPLUNK_START_ARGS=--accept-license
ENV SPLUNK_PASSWORD=testing123

COPY ./ /code/splunk-forwarder

WORKDIR /code/splunk-forwarder

RUN sudo mkdir -p /var/opt/splunk/etc/system/local && \
    sudo cp /code/splunk-forwarder/test-services/splunk/user-seed.conf /var/opt/splunk/etc/system/local/user-seed.conf
