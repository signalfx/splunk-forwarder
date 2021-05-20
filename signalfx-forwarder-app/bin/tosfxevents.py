#pylint:disable=broad-except
import gzip
import json
import os
import sys
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
class ToSFXEventsCommand(EventingCommand):
    """
    ## Syntax

    <command> | tosfxevents

    ## Description

    One or more events are generated for each input event.  If there is a field
    called event_* the event_type will be set to the value of the field. 
    Fields beginning with property_ are stripped of their property_ and become 
    properties on the event.
    Any additional fields on the event will be attached as dimensions
    to the generated event.

    """

    access_token = None
    debug = Option(validate=validators.Boolean(), default=False)
    dry_run = Option(validate=validators.Boolean(), default=False)
    ingest_url = Option(validate=validators.Match("https://.*", r"^https://.*"))
    ev_endpoint = Option(default="/v2/event")

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
        payload = []
        for event in records:
            add_event_to_payload(self, event=event, payload=payload)

            if self.debug:
                event["endpoint"] = self.ingest_url + self.ev_endpoint

            out.append(event)

        if not self.dry_run:
            resp = send_payload(
                payload=payload,
                target_url=compose_ingest_url(self.ingest_url, self.ev_endpoint),
                token=self.access_token,
            )
            for event in out:
                event["status"] = resp.status_code
                if resp.status_code != 200:
                    event["response_error"] = resp.content

        for event in out:
            yield event

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
    
def compose_ingest_url(ingest_base_url, ev_endpoint):
    return ingest_base_url.rstrip("/") + ev_endpoint

def add_event_to_payload(self, event, payload):

    dimensions = dict()
    properties = dict()
    timestamp = None
    eventType = None


    for key, value in event.items():
        if value != "":
            if key.startswith("event_"):
                eventType = value
            elif key.startswith("property_"):
                if value[0] != "_" and len(value) < 256:
                    newKey = key.replace("property_", "")
                    newKey = newKey.replace(".", "_")
                    self.logger.error("KEY is "+str(newKey))
                    properties[newKey] = value
            elif key == "_time":
                timestamp = int(float(value) * 1000)
            elif not key.startswith("_") and key != "punct" and not key.startswith("date_"):
                if value[0] != "_" and len(value) < 256:
                    dimensions[key.replace(".", "_")] = value
           
    eventDict = {
        'category': 'USER_DEFINED',
        'dimensions': dimensions,
        'properties': properties,
        'timestamp': timestamp,
        'eventType': eventType,
    }

    payload.append(eventDict)

    event_payload = json.dumps(eventDict)
    self.logger.error(event_payload)

dispatch(ToSFXEventsCommand, sys.argv, sys.stdin, sys.stdout, __name__)
