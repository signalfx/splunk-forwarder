.DEFAULT_GOAL := all

.PHONY: lint
lint:
	pylint signalfx-forwarder

.PHONY: package
package:
	slim package signalfx-forwarder

.PHONY: appinspect
appinspect: package
	splunk-appinspect inspect signalfx-forwarder-*.tar.gz --mode=precert

.PHONY: test
test: package
	docker build -t signalfx-forwarder-test:latest -f tests/Dockerfile .
	docker run -it --rm \
		-v /var/run/docker.sock:/var/run/docker.sock:ro \
		signalfx-forwarder-test

.PHONY: all
all: package appinspect lint test
