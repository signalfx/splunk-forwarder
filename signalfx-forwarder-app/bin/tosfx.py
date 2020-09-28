import gzip
import json
import os
import sys
from collections import OrderedDict
from io import BytesIO

current_path = os.path.dirname(__file__)  # pylint: disable=invalid-name
sys.path.append(os.path.join(current_path, "libs"))
sys.path.append(os.path.join(current_path, "libs", "sfxlib"))

from splunklib.searchcommands import (  # isort:skip pylint: disable=import-error
    Configuration,
    EventingCommand,
    Option,
    dispatch,
    validators,
)

import requests  # isort:skip


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
    ingest_url = Option()
    dp_endpoint = Option(default="/v2/datapoint")

    SPLUNK_PASSWORD_REALM = "realm"
    SPLUNK_PASSWORD_USER_NAME = "username"
    SPLUNK_PASSWORD_CLEAR_PASSWORD = "clear_password"
    SPLUNK_KV_STORE_SFX_CONFIG_COLLECTION_NAME = "sfx_ingest_config"
    SPLUNK_SFX_CONFIG_INGEST_URL_KEY = "ingest_url"
    SPLUNK_PASSWORDS_STORAGE_SFX_ACCESS_TOKEN_REALM = "sfx_ingest_command"
    SPLUNK_PASSWORDS_STORAGE_SFX_ACCESS_TOKEN_USER_NAME = "access_token"

    def ensure_default_config(self):
        if not self.ingest_url:
            self.ingest_url = self.get_sfx_ingest_url()

        self.logger.error("getting access token")
        if not self.access_token:
            self.access_token = self.get_access_token()

    def get_access_token(self):
        try:
            for credential in self.service.storage_passwords:
                if (
                    credential.content.get(self.SPLUNK_PASSWORD_REALM, None)
                    == self.SPLUNK_PASSWORDS_STORAGE_SFX_ACCESS_TOKEN_REALM
                    and credential.content.get(self.SPLUNK_PASSWORD_USER_NAME, None)
                    == self.SPLUNK_PASSWORDS_STORAGE_SFX_ACCESS_TOKEN_USER_NAME
                ):
                    return credential.content.get(self.SPLUNK_PASSWORD_CLEAR_PASSWORD, None)
        except Exception as e:  # pylint:disable=broad-except
            self.logger.error("status=error, action=get_sfx_access_token, error_msg=%s", e, exc_info=True)
        return None

    def get_sfx_ingest_url(self):
        try:
            sfx_api_config_collection = self.service.kvstore.get(self.SPLUNK_KV_STORE_SFX_CONFIG_COLLECTION_NAME, None)
            if sfx_api_config_collection is not None:
                collection = self.service.kvstore[self.SPLUNK_KV_STORE_SFX_CONFIG_COLLECTION_NAME]
                # will return a list of settings, we should only have one.
                # We'll grab the 'last' / most recent one by default
                sfx_ingest_config_records = collection.data.query()
                if sfx_ingest_config_records:
                    sfx_ingest_config_latest = sfx_ingest_config_records[-1]
                    return sfx_ingest_config_latest.get(self.SPLUNK_SFX_CONFIG_INGEST_URL_KEY, None)
        except Exception as e:  # pylint:disable=broad-except
            self.logger.error("status=error, action=get_sfx_ingest_url, error_msg=%s", str(e), exc_info=True)
        return None

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
                target_url=compose_ingest_url(self.ingest_url, self.dp_endpoint),
                token=self.access_token,
            )
            for event in out:
                event["status"] = resp.status_code
                if resp.status_code != 200:
                    event["response_error"] = resp.content

        for event in out:
            yield event


def compose_ingest_url(ingest_base_url, dp_endpoint):
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
    for key, value in event.items():
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
        fd.write(json.dumps(payload).encode("utf-8"))
    body.seek(0)

    resp = requests.post(
        target_url,
        headers={"X-SF-TOKEN": token, "Content-Encoding": "gzip", "Content-Type": "application/json"},
        data=body.read(),
    )
    return resp


dispatch(ToSFXCommand, sys.argv, sys.stdin, sys.stdout, __name__)
