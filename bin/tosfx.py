import sys
import splunk.Intersplunk as inter
import splunk.entity as entity

import csv
import json
import os
import requests
import ConfigParser

from collections import OrderedDict

token = ""
dryRun = False
debug = False
ingest = ""


def populatePayload(metric_type, metric_list, payload):
    expanded = []
    for metric, value in metric_list:
        expanded.append(dict([("metric", metric), ("value", value)]))
        if timestamp:
            expanded[-1]["timestamp"] = timestamp
        expanded[-1]["dimensions"] = dimensions
    if metric_type in payload:
        # Append in reverse order because SignalFx expects data points oldest to latest
        payload[metric_type] = expanded + payload[metric_type]
    else:
        payload[metric_type] = expanded


configs = ConfigParser.ConfigParser(allow_no_value=True)
localConfig = os.path.abspath(os.path.join(os.getcwd(), "..", "local", "sfx.conf"))
defaultConfig = os.path.abspath(os.path.join(os.getcwd(), "..", "default", "sfx.conf"))

# Set the default values. ConfigParser bundled with Splunk is not the latest
configs.add_section("output")
configs.set("output", "token", token)
configs.set("output", "ingest_url", ingest)

# Read the default section then local so local will take precedence
configs.read(defaultConfig)
configs.read(localConfig)
token = ""
if "output" in configs.sections():
    ingest = configs.get("output", "ingest_url")

# default to sending to ingest
target = ingest


def getCredentials(session_key):
    entities = entity.getEntities(
        ["admin", "passwords"],
        namespace="sfxforwarder",
        owner="nobody",
        sessionKey=session_key,
    )
    for i, c in entities.items():
        return c["username"], c["clear_password"]


for arg in sys.argv[:]:
    if arg.startswith("dryrun="):
        dryRun = arg[-1] in ["T", "t", "True", "true"]
    elif arg.startswith("debug="):
        debug = arg[-1] in ["T", "t", "True", "true"]


results, dummy, settings = inter.getOrganizedResults()
user, token = getCredentials(settings.get("sessionKey"))
outbuffer = []

payload = OrderedDict()
for result in results:
    gauge = []
    counter = []
    cumulative_counter = []
    dimensions = dict()
    timestamp = None
    for key, value in result.iteritems():
        if value != "":
            if key.startswith("gauge_"):
                try:
                    value = int(value)
                except:
                    value = float(value)
                gauge.append((key[key.find("gauge_") + 6 :], value))
            elif key.startswith("counter_"):
                counter.append((key[len("counter_") :], int(value)))
            elif key.startswith("cumulative_counter_"):
                cumulative_counter.append(
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
        result["endpoint"] = target
    if len(gauge) > 0 or len(counter) > 0 or len(cumulative_counter) > 0:
        if len(gauge) > 0:
            populatePayload("gauge", gauge, payload)
        if len(counter) > 0:
            populatePayload("counter", counter, payload)
        if len(cumulative_counter) > 0:
            populatePayload("cumulative_counter", cumulative_counter, payload)
    outbuffer.append(result)
if not dryRun:
    r = requests.post(
        target,
        headers={"X-SF-TOKEN": token, "Content-Type": "application/json"},
        data=json.dumps(payload),
    )
    for result in outbuffer:
        result["status"] = r.status_code
inter.outputResults(outbuffer)
