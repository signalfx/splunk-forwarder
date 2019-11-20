.DEFAULT_GOAL := all

.PHONY: lint
lint:
	pylint signalfx-forwarder-app

.PHONY: slim
slim:
	slim package signalfx-forwarder-app

.PHONY: appinspect
appinspect: slim
	splunk-appinspect inspect signalfx-forwarder-app-*.tar.gz --mode=precert

.PHONY: test
test: slim
	docker build -t signalfx-forwarder-test:latest -f tests/Dockerfile .
	docker run -it --rm \
		-v /var/run/docker.sock:/var/run/docker.sock:ro \
		signalfx-forwarder-test

.PHONY: all
all: slim appinspect lint test
