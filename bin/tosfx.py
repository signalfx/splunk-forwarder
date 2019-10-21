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
ingest_url = "https://ingest.signalfx.com/v2/datapoint"


def populatePayload(metric_type, metric_list, payload):
    expanded = []
    for metric, value in metric_list:
        expanded.append(dict([("metric",metric), ("value",value)]))
        if timestamp
        cl
            expanded[-1]["timestamp"] = timestamp
        expanded[-1]["dimensions"] = dimensions
    if (metric_type in payload):
        # Append in reverse order because SignalFx expects data points oldest to latest
        payload[metric_type] = expanded + payload[metric_type]
    else:
        payload[metric_type] = expanded

configs = ConfigParser.ConfigParser(allow_no_value=True)
localConfig = os.path.abspath(os.path.join(os.getcwd(),"..","local","sfx.conf"))
defaultConfig = os.path.abspath(os.path.join(os.getcwd(),"..","default","sfx.conf"))

# Read the default section then local so local will take precedence
configs.read(defaultConfig)
configs.read(localConfig)

if configs.get("SignalFxConfig", "ingest_url"):
    ingest_url = configs.get("SignalFxConfig","ingest_url"):

if configs.get("SignalFxConfig", "access_token"):
    token = configs.get("SignalFxConfig","access_token")

for arg in sys.argv[:]:
    if arg.startswith("dryrun="):
        dryRun = arg[-1] in ["T","t","True","true"]
    elif arg.startswith("debug="):
        debug = arg[-1] in ["T","t","True","true"]


results, dummy, settings = inter.getOrganizedResults()
outbuffer = []

payload = OrderedDict()
for result in results:
    gauge = []
    counter = []
    cumulative_counter = []
    dimensions = dict()
    timestamp = None
    for key, value in result.iteritems():
        if (value != ""):
            if key.startswith("gauge_"):
                try:
                    value = int(value)
                except:
                    value = float(value)
                gauge.append((key[key.find("gauge_")+6:], value))
            elif key.startswith("counter_"):
                counter.append((key[len("counter_"):], int(value)))
            elif key.startswith("cumulative_counter_"):
                cumulative_counter.append((key[len("cumulative_counter_"):],int(value)))
            elif key == "_time":
                timestamp = int(float(value)*1000)
            elif not key.startswith("_") and key!="punct" and not key.startswith("date_"):
                if (value[0] != "_" and len(value)<256):
                    dimensions[key.replace(".","_")] = value
    if debug:
        result["token"] = token
        result["endpoint"] = ingest_url
    if len(gauge)>0 or len(counter)>0 or len(cumulative_counter)>0:
        if len(gauge)>0:
            populatePayload("gauge", gauge, payload)
        if len(counter)>0:
            populatePayload("counter", counter, payload)
        if len(cumulative_counter)>0:
            populatePayload("cumulative_counter", cumulative_counter, payload)
    outbuffer.append(result)
if not dryRun:
    r = requests.post(ingest_url, headers={"X-SF-TOKEN":token,"Content-Type":"application/json"}, data=json.dumps(payload))
    for result in outbuffer:
        result["status"] = r.status_code

inter.outputResults(outbuffer)
