import gzip
import json
import os
import sys
from collections import OrderedDict
from io import BytesIO

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from splunklib.searchcommands import Configuration, EventingCommand, Option, dispatch, validators  # isort:skip

from sfx_utils import get_access_token  # isort:skip

try:
    import configparser
except ImportError:
    import ConfigParser as configparser


@Configuration()
class ToSFXCommand(EventingCommand):
    """
    ## Syntax

    <command> | tosfx

    ## Description

    One or more datapoints are generated for each input event's field(s) of the
    form `gauge_*`, `counter_*` or `cumulative_counter_*`.  The metric name in
    SignalFx will be the `*` part of the field name.  Any additional fields on
    the event will be attached as dimensions to the generated datapoints.

    """

    access_token = Option()
    debug = Option(validate=validators.Boolean(), default=False)
    dry_run = Option(validate=validators.Boolean(), default=False)
    signalfx_realm = Option()
    ingest_url = Option()
    dp_endpoint = Option(default="/v2/datapoint")

    def ensure_default_config(self):
        configs = configparser.ConfigParser(allow_no_value=True)
        local_config = os.path.abspath(os.path.join(os.getcwd(), "..", "local", "sfx.conf"))

        configs.read(local_config)

        def read_conf_value(field):
            try:
                return configs.get("setupentity", field)
            except configparser.NoOptionError:
                return None

        if not self.signalfx_realm:
            self.signalfx_realm = read_conf_value("signalfx_realm")
        if not self.ingest_url:
            self.ingest_url = read_conf_value("ingest_url")

        self.logger.error("getting access token")
        if not self.access_token:
            self.access_token = get_access_token(self.service)

    def transform(self, records):
        self.ensure_default_config()

        out = []
        payload = OrderedDict()
        for event in records:
            add_event_to_payload(event=event, payload=payload)

            if self.debug:
                event["endpoint"] = self.ingest_url + self.dp_endpoint

            out.append(event)

        if not self.dry_run:
            resp = send_payload(
                payload=payload,
                target_url=compose_ingest_url(self.signalfx_realm, self.ingest_url, self.dp_endpoint),
                token=self.access_token,
            )
            for event in out:
                event["status"] = resp.status_code
                if resp.status_code != 200:
                    event["response_error"] = resp.content

        for event in out:
            yield event


def compose_ingest_url(realm, ingest_base_url, dp_endpoint):
    if realm:
        ingest_base_url = "https://ingest.%s.signalfx.com" % (realm,)

    return ingest_base_url.rstrip("/") + dp_endpoint


def populate_payload(metric_type, metric_list, payload, timestamp, dims):
    expanded = []
    for metric, value in metric_list:
        expanded.append(dict([("metric", metric), ("value", value)]))
        if timestamp:
            expanded[-1]["timestamp"] = timestamp
        expanded[-1]["dimensions"] = dims
    if metric_type in payload:
        # Append in reverse order because SignalFx expects data points oldest to latest
        payload[metric_type] = expanded + payload[metric_type]
    else:
        payload[metric_type] = expanded


def add_event_to_payload(event, payload):
    gauges = []
    counters = []
    cumulative_counters = []
    dimensions = dict()
    timestamp = None
    for key, value in event.iteritems():
        if value != "":
            if key.startswith("gauge_"):
                try:
                    value = int(value)
                except ValueError:
                    value = float(value)
                gauges.append((key[len("gauge_") :], value))
            elif key.startswith("counter_"):
                counters.append((key[len("counter_") :], int(value)))
            elif key.startswith("cumulative_counter_"):
                cumulative_counters.append((key[len("cumulative_counter_") :], int(value)))
            elif key == "_time":
                timestamp = int(float(value) * 1000)
            elif not key.startswith("_") and key != "punct" and not key.startswith("date_"):
                if value[0] != "_" and len(value) < 256:
                    dimensions[key.replace(".", "_")] = value

    if gauges:
        populate_payload("gauge", gauges, payload, timestamp, dimensions)
    if counters:
        populate_payload("counter", counters, payload, timestamp, dimensions)
    if cumulative_counters:
        populate_payload("cumulative_counter", cumulative_counters, payload, timestamp, dimensions)


def send_payload(payload, target_url, token):
    body = BytesIO()
    with gzip.GzipFile(fileobj=body, mode="w") as fd:
        fd.write(json.dumps(payload))
    body.seek(0)

    resp = requests.post(
        target_url,
        headers={"X-SF-TOKEN": token, "Content-Encoding": "gzip", "Content-Type": "application/json"},
        data=body.read(),
    )
    return resp


dispatch(ToSFXCommand, sys.argv, sys.stdin, sys.stdout, __name__)
