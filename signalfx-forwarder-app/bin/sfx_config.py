"""
Description:  This skeleton python script handles the parameters in the configuration page.

  handleList method: lists configurable parameters in the configuration page
  corresponds to handleractions = list in restmap.conf

  handleEdit method: controls the parameters and saves the values
  corresponds to handleractions = edit in restmap.conf

"""
import os
import sys

import splunk.admin as admin  # pylint:disable=import-error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from sfx_utils import STORAGE_PASSWORD_NAME, get_access_token  # isort:skip
from splunklib.client import Service  # isort:skip


APP_NAME = "signalfx-forwarder-app"


class ConfigApp(admin.MConfigHandler):
    """
    Set up supported arguments
    """

    def __init__(self, *args, **kwargs):
        super(ConfigApp, self).__init__(*args, **kwargs)

        self.service = Service(scheme="https", host="localhost", port=8089, app=APP_NAME, token=self.getSessionKey())

    def setup(self):
        if self.requestedAction == admin.ACTION_EDIT:
            for arg in ["access_token", "signalfx_realm", "ingest_url"]:
                self.supportedArgs.addOptArg(arg)

    def handleList(self, conf_info):  # pylint:disable=invalid-name
        """
        Read the initial values of the parameters from the custom file
        sfx.conf, and write them to the setup page.

        If the app has never been set up,
        uses .../signalfx-forwarder/default/sfx.conf.

        If app has been set up, looks at
        .../local/sfx.conf first, then looks at
        .../default/sfx.conf only if there is no value for a field in
        .../local/sfx.conf

        For boolean fields, may need to switch the true/false setting.
        For text fields, if the conf file says None or empty string,
        set to the empty string.
        """
        conf_dict = self.readConf("sfx")
        if conf_dict is not None:
            for stanza, settings in conf_dict.items():
                for key, val in settings.items():
                    conf_info[stanza].append(key, val or "")

        access_token = get_access_token(self.service)
        conf_info["setupentity"].append("access_token", access_token)

    def handleEdit(self, _):  # pylint:disable=invalid-name
        """
        After user clicks Save on setup page, take updated parameters,
        normalize them, and save them somewhere
        """
        data = {k: [s or "" for s in v] for k, v in self.callerArgs.data.items()}

        server_info = self.service.info()
        if server_info.get("instance_type") == "cloud":
            ingest_url = data.get("ingest_url")
            if ingest_url and ingest_url[0] and not ingest_url[0].startswith("https"):
                raise admin.ArgValidationException("ingest_url must be https in Splunk Cloud")

        access_token_list = data.pop("access_token")
        if not access_token_list:
            raise admin.ArgValidationException("required access token is missing")
        self.save_access_token(access_token_list[0])

        # Since we are using a conf file to store parameters,
        # write them to the [SignalFxConfig] stanza
        # in splunk-forwarder/local/sfx.conf
        self.writeConf("sfx", "setupentity", data)

    def save_access_token(self, access_token):
        try:
            self.service.storage_passwords.delete(STORAGE_PASSWORD_NAME)
        except KeyError:  # This is thrown when the password didn't already exist
            pass
        self.service.storage_passwords.create(access_token, STORAGE_PASSWORD_NAME)


# initialize the handler
admin.init(ConfigApp, admin.CONTEXT_NONE)
