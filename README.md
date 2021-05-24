# signalfx-forwarder
A custom search command to metricize Splunk logs and send to SignalFx


See [./signalfx-forwarder-app/README.md](./signalfx-forwarder-app/README.md) for usage information.

### Releasing

#### Requirements
You'll need to install the [Splunk Packacking Toolkit](https://dev.splunk.com/enterprise/docs/releaseapps/packagingtoolkit/installpkgtoolkit).
Run `slim package signalfx-forwarder` to generate the .tar.gz and upload to the Github release.

#### CI testing

The repo includes a set of circleci tests that need to pass before your Pull Request can be merged.
Perform the tests here https://app.circleci.com/ pointed at your updated github fork.

However note that there appears to be an issue with circleci meaning that you if you are pushing to a PR on the signalfx repo you will need to "Stop Building" on your forked circleci project to allow the upstream PR repo to perform the circleci tests.

#### Unit Testing
Unit testing should be completed successfully and can be performed locally as follows.
If you are adding new commands you may need to update the test cases defined in [./signalfx-forwarder-app/tests/splunk_test.py](./signalfx-forwarder-app/tests/splunk_test.py) and possibly the fake handling of the commands [./signalfx-forwarder-app/tests/helpers/fake_backend.py](./signalfx-forwarder-app/tests/helpers/fake_backend.py)

This process has been followed on a Mac with Docker installed.

Build the app i.e. a tag.gz with the updated code in it
```
make package
```

Build the docker image which includes the mock signalfx API, a splunk docker image and the pytests:
```
docker build -t splunk-forwarder-test -f tests/Dockerfile .
```

Run the docker image being sure to mount the tmp directory to the image can access the package to install it as part of the testing:
```
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock:ro -v /tmp/scratch:/tmp/scratch splunk-forwarder-test
```

Note that you may need to add /tmp as a file share to your docker engine config. It can be found under the Docker Settings > Preferences > File Sharing.

### Support

To file a bug report or request help please file an issue on our [Github
repository](https://github.com/signalfx/splunk-forwarder/) for this app.
