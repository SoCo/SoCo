# -*- coding: utf-8 -*-

""" pysimplesoap classes and utilities"""

from __future__ import unicode_literals

import logging
log = logging.getLogger(__name__)  # pylint: disable=C0103

from pysimplesoap import transport
from pysimplesoap.client import SoapClient as pss_Client, SoapFault
from pysimplesoap.simplexml import SimpleXMLElement
import requests

from soco import SoCo
from soco.exceptions import MusicServiceException
from soco.xml import XML


# pylint: disable=fixme, protected-access
class SoapClient(pss_Client):

    """Add functionality to the pysimplesoap client"""

    def __init__(self, *args, **kwargs):
        """Note:
            Args are the same as for pysimplesoap.client.SoapClient, but an
            additional kwarg, `music_service` is the service to which
            this client is attached.
        """
        self.music_service = kwargs.pop('music_service', None)
        super(SoapClient, self).__init__(*args, **kwargs)
        self._device = SoCo.any_soco()
        self._device_id = self._device.systemProperties.GetString(
            [('VariableName', 'R_TrialZPSerial')])['StringValue']

    def _get_headers(self):
        """Generate the SOAP authentication header for the related service.

        This header must be sent with all SOAP requests.

        """
        music_service = self.music_service
        result = SimpleXMLElement("<Headers/>")
        credentials_header = result.add_child("credentials")
        credentials_header['xmlns'] = "http://www.sonos.com/Services/1.1"
        credentials_header.marshall('deviceId', self._device_id)
        credentials_header.marshall('deviceProvider', 'Sonos')
        if music_service.account.oa_device_id:
            # OAuth account credentials are present. We must use them to
            # authenticate.
            token = credentials_header.add_child('loginToken')
            token.marshall('token', music_service.account.oa_device_id)
            token.marshall('key', music_service.account.key)
            token.marshall('householdId', self._device.household_id)
            return result

        # otherwise, perhaps use DeviceLink or UserId auth
        if music_service.auth_type in ['DeviceLink', 'UserId']:
            # We need a session ID from Sonos
            session_id = self._device.musicServices.GetSessionId([
                ('ServiceId', music_service.service_id),
                ('Username', music_service.account.username)
            ])['SessionId']
            credentials_header.marshall('sessionId', session_id)
        # Anonymous auth. No need for anything further.
        return result

    def call(self, method, *args, **kwargs):
        """Prepare xml request and make SOAP call. Return a SimpleXMLElement.

        Overrides pysimplesoap.client.call to allow for headers to be added
        automatically on each call, and to wrap errors

        """
        headers = self._get_headers()
        try:
            result = super(SoapClient, self).call(
                method, *args, headers=headers, **kwargs
            )
        except SoapFault as exc:
            log.debug('Soap Fault:', exc_info=True)

            if 'Client.TokenRefreshRequired' in exc.faultcode and exc.detail:

                # <detail>
                #   <refreshAuthTokenResult>
                #       <authToken>xxxxxxx</authToken>
                #       <privateKey>zzzzzz</privateKey>
                #   </refreshAuthTokenResult>
                # </detail>
                detail = XML.fromstring(exc.detail)
                auth_token = detail.findtext('.//authToken')
                private_key = detail.findtext('.//privateKey')
                # We have new details - update the account
                self.music_service.account.oa_device_id = auth_token
                self.music_service.account.key = private_key
                log.debug("Token Refresh required. Trying again")
                headers = self._get_headers()
                result = super(SoapClient, self).call(
                    method, *args, headers=headers, **kwargs
                )
                # TODO: Do we need to update the Sonos databases using
                # SystemProperties.RefreshAccountCredentialsX ?
            else:
                raise MusicServiceException(exc.faultstring, exc.faultcode)
        return result


# pysimplesoap cannot handle the gzipped SOAP which eg Spotify returns. But
# requests can. So we need a custom transport for pysimplesoap which uses
# requests rather than urllib2


class _requestsTransport(transport.TransportBase):

    " A transport for pysimplesoap that uses the requests library"

    def __init__(self, timeout, proxy=None, cacert=None, sessions=False):
        self.timeout = timeout
        self.proxy = proxy or {}
        self.cacert = cacert
        self.sessions = sessions
        # Use sessions, so that the connection can be reused.
        self.request_session = requests.Session()

    def request(self, url, method, body, headers):
        """ Execute the desired request"""
        if method == 'POST':
            result = self.request_session.post(
                url, data=body, headers=headers, timeout=self.timeout,
                proxies=self.proxy
            )
        elif method == 'GET':
            result = self.request_session.get(
                url, headers=headers, timeout=self.timeout, proxies=self.proxy
            )
        else:
            raise Exception('Unknown request method')
        return {}, result.text.encode('ascii', 'replace')

# Register the new transport
# pylint: disable=protected-access
transport._http_connectors['requests'] = _requestsTransport
transport.set_http_wrapper('requests')
