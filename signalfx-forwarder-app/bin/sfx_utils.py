from xml.etree.ElementTree import XML

from splunklib.binding import HTTPError

STORAGE_PASSWORD_NAME = "signalfx"


def get_access_token(service):
    try:
        token_password = service.storage_passwords.get(STORAGE_PASSWORD_NAME).get("body")
        return XML(token_password.read()).findtext(".//*[@name='clear_password']")
    except HTTPError:
        return None
