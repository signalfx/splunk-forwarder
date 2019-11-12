.DEFAULT_GOAL := all

.PHONY: slim
slim:
	docker build -t signalfx-forwarder-slim:latest -f Dockerfile.slim .
	docker run --rm \
		-v $(PWD):/code \
		signalfx-forwarder-slim

.PHONY: appinspect
appinspect: slim
	docker build -t signalfx-forwarder-appinspect:latest -f Dockerfile.appinspect .
	docker run --rm \
		-v $(PWD):/code \
		signalfx-forwarder-appinspect

.PHONY: lint
lint:
	docker build -t signalfx-forwarder-test:latest -f Dockerfile.test .
	docker run --rm \
		-v $(PWD):/code \
		signalfx-forwarder-test \
		pylint signalfx-forwarder-app

.PHONY: test
test: slim
	docker build -t signalfx-forwarder-test:latest -f Dockerfile.test .
	docker run -it --rm \
		-v $(PWD):/code \
		-v /var/run/docker.sock:/var/run/docker.sock:ro \
		signalfx-forwarder-test

.PHONY: all
all: slim appinspect lint test
