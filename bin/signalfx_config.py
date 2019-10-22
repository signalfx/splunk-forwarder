"""
Description:  This skeleton python script handles the parameters in the configuration page.

  handleList method: lists configurable parameters in the configuration page
  corresponds to handleractions = list in restmap.conf

  handleEdit method: controls the parameters and saves the values 
  corresponds to handleractions = edit in restmap.conf

"""
import splunk.entity as en
import splunk.admin as admin


class ConfigApp(admin.MConfigHandler):
    """
    Set up supported arguments
    """

    def setup(self):
        if self.requestedAction == admin.ACTION_EDIT:
            for arg in ["access_token", "realm", "ingest_url"]:
                self.supportedArgs.addOptArg(arg)

    def handleList(self, confInfo):
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
        confDict = self.readConf("sfx.conf")
        if confDict is not None:
            for stanza, settings in confDict.items():
                for key, val in settings.items():
                    if key in ["access_token"] and not val:
                        val = ""
                    if key in ["ingest_url"] and not val:
                        val = ""
                    if key in ["realm"] and not val:
                        val = ""

                    confInfo[stanza].append(key, val)

    def handleEdit(self, confInfo):
        """
        After user clicks Save on setup page, take updated parameters,
        normalize them, and save them somewhere
        """
        ingest_url = self.callerArgs.data["ingest_url"][0]
        ## if ingest url is not set, check realm
        if not ingest_url:
            realm = self.callerArgs.data["realm"][0]
            ## if realm is not set, default to us0
            if not realm:
                realm = "us0"
            self.callerArgs.data["ingest_url"][0] = (
                "https://ingest.%s.signalfx.com" % realm.lower()
            )

        # Since we are using a conf file to store parameters,
        # write them to the [SignalFxConfig] stanza
        # in splunk-forwarder/local/sfx.conf
        self.writeConf("sfx", "SignalFxConfig", self.callerArgs.data)


# initialize the handler
admin.init(ConfigApp, admin.CONTEXT_NONE)