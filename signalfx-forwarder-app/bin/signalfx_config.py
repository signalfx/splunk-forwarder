"""
Description:  This skeleton python script handles the parameters in the configuration page.

  handleList method: lists configurable parameters in the configuration page
  corresponds to handleractions = list in restmap.conf

  handleEdit method: controls the parameters and saves the values
  corresponds to handleractions = edit in restmap.conf

"""
import splunk.admin as admin  # pylint:disable=import-error


class ConfigApp(admin.MConfigHandler):
    """
    Set up supported arguments
    """

    def setup(self):
        if self.requestedAction == admin.ACTION_EDIT:
            for arg in ["access_token", "ingest_url"]:
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
                    if key in ["access_token"] and not val:
                        val = ""
                    if key in ["ingest_url"] and not val:
                        val = "https://ingest.us0.signalfx.com"

                    conf_info[stanza].append(key, val)

    def handleEdit(self, _):  # pylint:disable=invalid-name
        """
        After user clicks Save on setup page, take updated parameters,
        normalize them, and save them somewhere
        """

        # Since we are using a conf file to store parameters,
        # write them to the [SignalFxConfig] stanza
        # in splunk-forwarder/local/sfx.conf
        self.writeConf("sfx", "setupentity", self.callerArgs.data)


# initialize the handler
admin.init(ConfigApp, admin.CONTEXT_NONE)
