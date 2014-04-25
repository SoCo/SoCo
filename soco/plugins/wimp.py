# -*- coding: utf-8 -*-
# pylint: disable=R0913,W0142

""" Plugin for the Wimp music service (Service ID 20) """

from __future__ import unicode_literals
try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML
NS = {
    's': 'http://schemas.xmlsoap.org/soap/envelope/',
    '': 'http://www.sonos.com/Services/1.1'
}


# Register all name spaces within the XML module
for key_, value_ in NS.items():
    XML.register_namespace(key_, value_)

import requests

from ..services import MusicServices
from ..data_structures import get_ms_item
from .__init__ import SoCoPlugin


__all__ = ['Wimp']


def ns_tag(ns_id, tag):
    """Return a namespace/tag item. The ns_id is translated to a full name
    space via the NS module variable.

    """
    return '{{{0}}}{1}'.format(NS[ns_id], tag)


def _get_header(soap_action):
    """Return the HTTP for SOAP Action

    :param soap_action: The soap action to include in the header. Can be either
        'search' or 'get_metadata'
    """
    # TODO fix accepted encoding. Either form list, fetch from locale settings
    # or some combination
    header = {'CONNECTION': 'close',
              'ACCEPT-ENCODING': 'gzip',
              'ACCEPT-LANGUAGE': 'da-DK, en-US;q=0.9',
              'Content-Type': 'text/xml; charset="utf-8"',
              'SOAPACTION': SOAP_ACTION[soap_action]
              }
    return header


class Wimp(SoCoPlugin):
    """Class that implements a Wimp plugin"""

    def __init__(self, soco, username):
        """ Initialize the plugin"""
        super(Wimp, self).__init__(soco)

        # Instantiate variables
        self._url = 'http://client.wimpmusic.com/sonos/services/Sonos'
        self._serial_number = soco.get_speaker_info()['serial_number']
        self._username = username
        self._service_id = 20

        # Get a session id for the searches
        self._music_services = MusicServices(soco)
        response = self._music_services.GetSessionId([
            ('ServiceId', 20),
            ('Username', username)
        ])
        self._session_id = response['SessionId']

    @property
    def name(self):
        return 'Wimp Plugin for {}'.format(self._username)

    @property
    def username(self):
        """Return the username"""
        return self._username

    @property
    def session_id(self):
        """Return the service id"""
        return self._service_id

    @property
    def description(self):
        """Return the music service description for the DIDL metadata on the
        form SA_RINCON5127_...self.username...
        """
        return 'SA_RINCON5127_{}'.format(self._username)

    def get_tracks(self, search, start=0, max_items=100):
        """Search for tracks

        See get_music_service_information for details on the arguments
        """
        return self.get_music_service_information('tracks', search, start,
                                                  max_items)

    def get_albums(self, search, start=0, max_items=100):
        """Search for albums

        See get_music_service_information for details on the arguments
        """
        return self.get_music_service_information('albums', search, start,
                                                  max_items)

    def get_artists(self, search, start=0, max_items=100):
        """Search for artists

        See get_music_service_information for details on the arguments
        """
        return self.get_music_service_information('artists', search, start,
                                                  max_items)

    def get_playlists(self, search, start=0, max_items=100):
        """Search for playlists

        See get_music_service_information for details on the arguments
        """
        return self.get_music_service_information('playlists', search, start,
                                                  max_items)

    def get_music_service_information(self, search_type, search, start=0,
                                      max_items=100):
        """Search for music service information items

        :param search_type: The type of search to perform, possible values are:
            'artists', 'albums', 'tracks' and 'playlists'
        :type search_type: str
        :param search: The search string to use
        :type search: str
        :param start: The starting index of the returned items
        :type start: int
        :param max_items: The maximum number of returned items
        :type max_items: int
        """
        # Check input
        if search_type not in ['artists', 'albums', 'tracks', 'playlists']:
            message = 'The requested search {} is not valid'\
                .format(search_type)
            raise ValueError(message)
        # Transform search: tracks -> tracksearch
        search_type = '{}earch'.format(search_type)
        # Perform search
        body = self._search_body(search_type, search, start, max_items)
        headers = _get_header('search')
        response = requests.post(self._url, headers=headers, data=body)
        self._check_for_errors(response)
        result_dom = XML.fromstring(response.text.encode('utf-8'))

        search_result = result_dom.find('.//' + ns_tag('', 'searchResult'))
        search_numbers = {}
        for element in ['index', 'count', 'total']:
            search_numbers[element] = \
                search_result.findtext(ns_tag('', element))

        out = []
        if search_type == 'tracksearch':
            item_name = 'mediaMetadata'
        else:
            item_name = 'mediaCollection'
        for element in search_result.findall(ns_tag('', item_name)):
            out.append(get_ms_item(element, self))

        return out

    def _search_body(self, search_type, search_term, start, max_items):
        """Return the search XML body

        :param search_type: The search type
        :type search_type: str
        :param search_term: The search term e.g. 'Jon Bon Jovi'
        :type search_term: str
        :param start: The start index of the returned results
        :type start: int
        :param max_items: The maximum number of returned results
        :type max_items: int

        The XML is formed by adding, to the envelope of the XML returned by
        ``self._base_body``, the following ``Body`` part:

        .. code :: xml

         <s:Body>
           <search xmlns="http://www.sonos.com/Services/1.1">
             <id>search_type</id>
             <term>search_term</term>
             <index>start</index>
             <count>max_items</count>
           </search>
         </s:Body>
        """
        xml = self._base_body()

        # Add the Body part
        XML.SubElement(xml, ns_tag('s', 'Body'))
        search = XML.SubElement(xml[1], ns_tag('', 'search'))
        XML.SubElement(search, 'id').text = search_type
        XML.SubElement(search, 'term').text = search_term
        XML.SubElement(search, 'index').text = str(start)
        XML.SubElement(search, 'count').text = str(max_items)

        return XML.tostring(xml)

    def _base_body(self):
        """Return the base XML body, which has the following form:

        .. code :: xml

         <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
           <s:Header>
             <credentials xmlns="http://www.sonos.com/Services/1.1">
               <sessionId>self._session_id</sessionId>
               <deviceId>self._serial_number</deviceId>
               <deviceProvider>Sonos</deviceProvider>
             </credentials>
           </s:Header>
         </s:Envelope>
        """
        xml = XML.Element(ns_tag('s', 'Envelope'))

        # Add the Header part
        XML.SubElement(xml, ns_tag('s', 'Header'))
        credentials = XML.SubElement(xml[0], ns_tag('', 'credentials'))
        XML.SubElement(credentials, 'sessionID').text = self._session_id
        XML.SubElement(credentials, 'deviceID').text = self._serial_number
        XML.SubElement(credentials, 'deviceProvider').text = 'Sonos'

        return xml

    def _check_for_errors(self, response):
        """Check a response for errors"""
        if response.status_code != 200:
            self._music_services.handle_upnp_error(response.text)


SOAP_ACTION = {
    'get_metadata': '"http://www.sonos.com/Services/1.1#getMetadata"',
    'search': '"http://www.sonos.com/Services/1.1#search"'
}
