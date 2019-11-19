# signalfx-forwarder
A custom search command to metricize Splunk logs and send to SignalFx


See [./signalfx-forwarder-app/README.md] for usage information.

### Releasing

#### Requirements
You'll need to install the [Splunk Packacking Toolkit](https://dev.splunk.com/enterprise/docs/releaseapps/packagingtoolkit/installpkgtoolkit).
Run `slim package signalfx-forwarder-app` to generate the .tar.gz and upload to the Github release.
