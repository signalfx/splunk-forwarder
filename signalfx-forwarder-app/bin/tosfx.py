import configparser
import json
import logging
import os
import sys
import zlib
from collections import OrderedDict

import requests

import splunk.Intersplunk as inter  # pylint:disable=import-error

logger = logging.getLogger("SignalFxForwarder")
logger.setLevel(logging.DEBUG)


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


def main():
    token = ""
    dry_run = False
    debug = False
    ingest_url = "https://ingest.us0.signalfx.com"
    dp_endpoint = "/v2/datapoint"
    configs = configparser.ConfigParser(allow_no_value=True)
    local_config = os.path.abspath(os.path.join(os.getcwd(), "..", "local", "sfx.conf"))
    default_config = os.path.abspath(os.path.join(os.getcwd(), "..", "default", "sfx.conf"))

    # Read the default section then local so local will take precedence
    configs.read(default_config)
    configs.read(local_config)

    if configs.get("setupentity", "ingest_url"):
        ingest_url = configs.get("setupentity", "ingest_url")

    if configs.get("setupentity", "access_token"):
        token = configs.get("setupentity", "access_token")

    for arg in sys.argv[:]:
        if arg.startswith("dryrun="):
            dry_run = arg[-1] in ["T", "t"]
        elif arg.startswith("debug="):
            debug = arg[-1] in ["T", "t"]

    results, _, _ = inter.getOrganizedResults()
    logger.debug("signalfx-forwarder-app found %d results in search", len(results))
    outbuffer = []

    payload = OrderedDict()
    for result in results:
        add_result_to_payload(result=result, payload=payload)

        if debug:
            result["token"] = token
            result["endpoint"] = ingest_url + dp_endpoint

        outbuffer.append(result)

    if not dry_run:
        resp = send_payload(payload=payload, ingest_url=ingest_url, dp_endpoint=dp_endpoint, token=token)
        for result in outbuffer:
            result["status"] = resp.status_code

    inter.outputResults(outbuffer)


def add_result_to_payload(result, payload):
    gauges = []
    counters = []
    cumulative_counters = []
    dimensions = dict()
    timestamp = None
    for key, value in result.iteritems():
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


def send_payload(payload, ingest_url, dp_endpoint, token):
    target = ingest_url + dp_endpoint
    body = zlib.compress(json.dumps(payload))
    resp = requests.post(
        target, headers={"X-SF-TOKEN": token, "Content-Encoding": "gzip", "Content-Type": "application/json"}, data=body
    )
    return resp


try:
    main()
except Exception as e:  # pylint:disable=broad-except
    logger.exception("Unhanded top-level exception")
    inter.generateErrorResults("Exception! %s (See python.log)" % (e,))
