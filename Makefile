.DEFAULT_GOAL := all

.PHONY: lint
lint:
	pylint signalfx-forwarder-app --ignore lib

.PHONY: package
package:
	slim package signalfx-forwarder-app

.PHONY: appinspect
appinspect: package
	splunk-appinspect inspect signalfx-forwarder-*.tar.gz --mode=precert

.PHONY: all
all: package appinspect lint
