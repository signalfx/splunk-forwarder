import sys
import splunk.Intersplunk as inter
import splunk.entity as entity
import csv
import json
import os
import requests
import argparse
import logging
import ConfigParser

from collections import OrderedDict

logger = logging.getLogger("SignalFxForwarder")
logger.setLevel(logging.DEBUG)


def populatePayload(metric_type, metric_list, payload, timestamp, dims):
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
    dryRun = False
    debug = False
    ingest_url = "https://ingest.us0.signalfx.com"
    dp_endpoint = "/v2/datapoint"
    configs = ConfigParser.ConfigParser(allow_no_value=True)
    localConfig = os.path.abspath(os.path.join(os.getcwd(), "..", "local", "sfx.conf"))
    defaultConfig = os.path.abspath(
        os.path.join(os.getcwd(), "..", "default", "sfx.conf")
    )

    # Read the default section then local so local will take precedence
    configs.read(defaultConfig)
    configs.read(localConfig)

    if configs.get("setupentity", "ingest_url"):
        ingest_url = configs.get("setupentity", "ingest_url")

    if configs.get("setupentity", "access_token"):
        token = configs.get("setupentity", "access_token")

    for arg in sys.argv[:]:
        if arg.startswith("dryrun="):
            dryRun = arg[-1] in ["T", "t"]
        elif arg.startswith("debug="):
            debug = arg[-1] in ["T", "t"]

    results, _, _ = inter.getOrganizedResults()
    logger.debug("signalfx-forwarder-app found %d results in search" % len(results))
    outbuffer = []

    payload = OrderedDict()
    for result in results:
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
                    except:
                        value = float(value)
                    gauges.append((key[len("gauge_") :], value))
                elif key.startswith("counter_"):
                    counters.append((key[len("counter_") :], int(value)))
                elif key.startswith("cumulative_counter_"):
                    cumulative_counters.append(
                        (key[len("cumulative_counter_") :], int(value))
                    )
                elif key == "_time":
                    timestamp = int(float(value) * 1000)
                elif (
                    not key.startswith("_")
                    and key != "punct"
                    and not key.startswith("date_")
                ):
                    if value[0] != "_" and len(value) < 256:
                        dimensions[key.replace(".", "_")] = value

        if debug:
            result["token"] = token
            result["endpoint"] = ingest_url + dp_endpoint

        if len(gauges) > 0 or len(counters) > 0 or len(cumulative_counters) > 0:
            if len(gauges) > 0:
                populatePayload("gauge", gauges, payload, timestamp, dimensions)
            if len(counters) > 0:
                populatePayload("counter", counters, payload, timestamp, dimensions)
            if len(cumulative_counters) > 0:
                populatePayload("cumulative_counter", cumulative_counters, payload, timestamp, dimensions)

        outbuffer.append(result)

    if not dryRun:
        target = ingest_url + dp_endpoint
        r = requests.post(
            target,
            headers={"X-SF-TOKEN": token, "Content-Type": "application/json"},
            data=json.dumps(payload),
        )
        for result in outbuffer:
            result["status"] = r.status_code

    inter.outputResults(outbuffer)


try:
    main()
except Exception as e:
    logger.exception("Unhanded top-level exception")
    inter.generateErrorResults("Exception! %s (See python.log)" % (e,))
