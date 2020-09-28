require.config({
  paths: {
    'app': '../app'
  }
});

require([
  "jquery",
  "splunkjs/mvc",
  "splunkjs/mvc/simplexml/ready!"
], function (
  $,
  mvc
) {
  const realm = 'sfx_ingest_command';
  const username = 'access_token';
  const obfuscatedToken = '************';

  // ui controls selectors
  const submitBtn = '#submit';
  const deleteBtn = '#delete';
  const accessTokenInput = '#access-token-input';
  const ingestUrlInput = '#ingest-url-input';
  const accessTokenError = '#access-token-error';
  const ingestUrlError = '#ingest-url-error';
  const fetchError = '#fetch-error-message';
  const submitSuccess = '#submit-success-message';
  const submitError = '#submit-error-message';

  // Create a service object using the Splunk SDK for JavaScript
  let service = mvc.createService({ owner: "nobody", app: "signalfx-forwarder-app" });

  const serviceParams = {
    output_mode: "JSON"
  };

  // kick off the fetch from kv
  get_ingest_url(ingest_url_fetch_callback);

  function get_ingest_url(cb) {
    const query = '| inputlookup sfx_ingest_config_lookup | table ingest_url, _key';
    let search = service.oneshotSearch(
      query,
      null,
      function (err, results) {

        if (err) {
          // Error in inputlookup, irrecoverable error. disable form and display error
          displayFetchErrorMessage();
          return;
        }

        if (!results || !results.rows || results.rows.length === 0) {
          return cb(undefined, undefined);
        }
        // Add the new Ingest to the kvstore
        let ingest_url = results.rows[0][0];
        let _key = results.rows[0][1];

        cb(undefined, { ingest_url, _key });
      });
  }

  function ingest_url_fetch_callback(ingest_urlerr, result) {
    if (result && result.ingest_url && result.ingest_url.length) {
      setFormInputValue(ingestUrlInput, result.ingest_url);
    }
    else if (ingest_urlerr != undefined) {
      // irrecoverable error, display error, form should remain disabled
      displayFetchErrorMessage();
    }

    //proceed to load access token
    if (ingest_urlerr == undefined) {
      get_access_token(access_token_fetch_callback);
    }
  }

  function access_token_fetch_callback(access_tokenerr, value) {
    //if a token is set, we won't show the value to the user, we will replace it with obfuscatedToken
    if (value && value != obfuscatedToken) {
      setFormInputValue(accessTokenInput, obfuscatedToken);
    }
    else if (access_tokenerr != undefined) {
      displayFetchErrorMessage();
    }
    enableForm();
  }

  function set_ingest_url(ingest_url, cb) {
    get_ingest_url(function (ingest_urlerr, result) {
      if (result && result.ingest_url && result.ingest_url.length) {
        //UPDATE
        _update_ingest_url(ingest_url, result._key, function (update_ingest_url_err, update_results) {
          cb(update_ingest_url_err, update_results)
        })
      }
      else if (ingest_urlerr != undefined) {
        cb(ingest_urlerr, undefined)
      }
      else {
        //CREATE
        _create_ingest_url(ingest_url, function (create_ingest_url_err, create_results) {
          cb(create_ingest_url_err, create_results)
        })
      }
    });
  }

  function _create_ingest_url(ingest_url, cb) {
    // Create _key
    let params = {
      "ingest_url": ingest_url,
      "_key": ""
    };

    //POST to kvstore requires a json header, but service.post does not allow to modify headers
    service.request("storage/collections/data/sfx_ingest_config/", "POST", null, null, JSON.stringify(params), { "Content-Type": "application/json" },
      function (err, results) {
        if (!err) {
          let _key = ""
          cb(undefined, { ingest_url, _key });
        }
        else {
          cb("Error setting Ingest URL in kvstore.", undefined);
        }
      });
  }

  function _update_ingest_url(ingest_url, _key, cb) {
    const updateSearch = '| inputlookup sfx_ingest_config_lookup ' +
      '| search _key=' + _key +
      '| eval ingest_url="' + ingest_url + '" ' +
      '| outputlookup sfx_ingest_config_lookup';

    service.oneshotSearch(
      updateSearch,
      null,
      function (err, results) {
        if (!err) {
          cb(undefined, { ingest_url, _key });
        }
        else {
          cb("Error setting Ingest URL in kvstore.", undefined);
        }
      });
  }

  function get_access_token(cb) {
    // Retrieve access token
    // NOTE: SDK has missing functionality wrt storage passwords filtered to the app, therefore utilizing raw splunkd endpoints
    service.get("/servicesNS/nobody/signalfx-forwarder-app/storage/passwords", serviceParams,
      function (err, response) {
        if (err) {
          cb('Error retrieving access token from kvstore', undefined);
        }
        else {
          let access_token;
          access_tokens = response.data;

          for (let i = 0; i < access_tokens.entry.length; i++) {
            found_username = access_tokens.entry[i].content.username;
            found_realm = access_tokens.entry[i].content.realm;

            if (found_username && found_username.localeCompare(username) == 0 && found_realm && found_realm.localeCompare(realm) == 0) {
              access_token = access_tokens.entry[i].content.clear_password;
              break;
            }
          }

          // access token does not exist
          if (!access_token || access_token.length === 0)
            cb(undefined, undefined);
          else
            cb(undefined, access_token);
        }
      });
  }

  function set_access_token(access_token, cb) {
    get_access_token(function (access_tokenerr, value) {
      if (value) {
        //UPDATE
        _update_access_token(access_token, function (update_access_token_err, results) {
          cb(update_access_token_err, results);
        })
      }
      else if (access_tokenerr != undefined) {
        cb(access_tokenerr, undefined);
      }
      else {
        //CREATE
        _create_access_token(access_token, function (create_access_token_err, results) {
          cb(create_access_token_err, results);
        })
      }
    })
  }

  function _create_access_token(access_token, cb) {
    let params = {
      name: username,
      realm: realm,
      password: access_token,
    };

    service.post("/servicesNS/nobody/signalfx-forwarder-app/storage/passwords", params,
      function (err, results) {
        if (err) {
          cb('Error retrieving access token from kvstore', undefined);
        }
        else {
          let acl = {
            "sharing": "system",
            "perms.read": "*",
            "perms.write": "admin"
          }
          service.post("/servicesNS/nobody/signalfx-forwarder-app/storage/passwords/_acl", acl, function (err, results) {
            if (err) {
              // ignore the error
            }
            else {
              cb(undefined, access_token);
            }
          });
        }
      });
  }

  function _update_access_token(access_token, cb) {
    let params = {
      'password': access_token
    }

    service.post("/servicesNS/nobody/signalfx-forwarder-app/storage/passwords/" + realm + ":" + username + ":", params,
      function (err, results) {
        if (err) {
          cb('Error retrieving access token from kvstore', undefined);
        }
        else
          cb(undefined, access_token);
      });
  }

  // Create / Update access_token and ingest_url config
  function set_config(ingest_url, access_token) {
    //first update the ingest_url
    set_ingest_url(ingest_url, function (set_ingest_urlerr, results) {
      if (set_ingest_urlerr) {
        displaySubmitErrorMessage();
        return;
      }
      else {
        // update the access_token
        if (access_token != obfuscatedToken) {
          set_access_token(access_token, function (set_access_tokenerr, results) {
            if (set_access_tokenerr) {
              displaySubmitErrorMessage();
              return;
            }
            else {
              displaySubmitSuccessMessage();
              return;
            }
          })
        }
        else {
          displaySubmitSuccessMessage();
          return;
        }
      }
    })
  }

  /**
   * Event handlers for form controls
   */
  $(submitBtn).on("click", function (e) {
    $(this).removeClass('validation-error-nudge');
    // hide previous submit status
    hideSubmitErrorMessage();
    hideSubmitSuccessMessage();
    let isValid = true;

    if (!validateAccessToken()) {
      $(accessTokenError).show();
      isValid = false;
    }
    if (!validateIngestUrl()) {
      $(ingestUrlError).show();
      isValid = false;
    }
    if (isValid) {
      let { ingest_url, access_token } = getFormInputs();
      set_config(ingest_url, access_token);
    }
    else {
      $(this).addClass('validation-error-nudge');
    }

  });

  $(deleteBtn).on("click", function (e) {
    hideSubmitErrorMessage();
    hideSubmitSuccessMessage();
    clearFormInputs();
  });

  $(accessTokenInput).on('focusin', function (e) {
    if ($(this).val() === obfuscatedToken) {
      $(this).val('');
    }
    $(accessTokenError).hide();
    hideSubmitErrorMessage();
    hideSubmitSuccessMessage();
  });
  $(accessTokenInput).on('focusout', function () {
    if (!validateAccessToken()) {
      $(accessTokenError).show();
    }
  });

  $(ingestUrlInput).on('focusin', function () {
    $(ingestUrlError).hide();
    hideSubmitErrorMessage();
    hideSubmitSuccessMessage();
  });
  $(ingestUrlInput).on('focusout', function () {
    if (!validateIngestUrl()) {
      $(ingestUrlError).show();
    }
  });

  /**
   * Util methods
   */
  function getFormInputs() {
    let access_token = $(accessTokenInput).val();
    let ingest_url = $(ingestUrlInput).val();

    return {
      ingest_url,
      access_token
    }
  }

  function clearFormInputs() {
    $(accessTokenInput).val('');
    $(ingestUrlInput).val('');
  }

  function enableForm() {
    $(submitBtn).show();
    $(deleteBtn).show();
  }

  function disableForm() {
    $(submitBtn).hide();
    $(deleteBtn).hide();
  }

  function validSfxURL(str) {
    // valid url syntax https://(.*).signalfx.com
    let pattern = new RegExp('^(https?:\/\/)(.*)$', 'i');
    return !!pattern.test(str);
  }

  function validateAccessToken() {
    let { ingest_url, access_token } = getFormInputs();
    // obfuscatedToken in input implies user does not want to change/overwrite the token
    if (!access_token) {
      return false;
    }
    return true;
  }

  function validateIngestUrl() {
    let { ingest_url, access_token } = getFormInputs();
    if (!ingest_url || !validSfxURL(ingest_url)) {
      return false;
    }
    return true;
  }

  function setFormInputValue(formSelector, value) {
    $(formSelector).val(value);
  }

  function displaySubmitSuccessMessage() {
    $(submitSuccess).show();
  }

  function displaySubmitErrorMessage() {
    $(submitError).show();
  }

  function hideSubmitSuccessMessage() {
    $(submitSuccess).hide();
  }

  function hideSubmitErrorMessage() {
    $(submitError).hide();
  }

  function displayFetchErrorMessage() {
    $(fetchError).show();
  }
});
