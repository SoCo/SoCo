# -*- coding: utf-8 -*-

""" Sonos Music Services interface

This module provides the MusicService class and related functionality
"""

from __future__ import unicode_literals

from pysimplesoap.client import SoapClient
from pysimplesoap.simplexml import SimpleXMLElement

import requests

import logging
log = logging.getLogger(__name__)  # pylint: disable=C0103

from soco import SoCo
from soco.xml import XML
from soco.music_services.soap_types import (MEDIAMETADATA_TYPE, MEDIALIST_TYPE)
# pylint: disable=unused-import
from soco.music_services import soap_transport  # noqa


# pylint: disable=too-many-instance-attributes
class MusicService(object):

    """
    The MusicService class provides access to third party music services

    Example:

        Print all the services Sonos knows about

        >>> from soco.music_services import MusicService
        >>> from pprint import pprint
        >>> print (MusicService.get_all_music_services())
        ['Spotify',
         'The Hype Machine',
         'Saavn',
         'Bandcamp',
         'Stitcher SmartRadio',
         'Concert Vault',
         ...
         ]

        Or just those tho which you are subscribed (and the relevant
        usernames)

        >>> pprint (MusicService.get_subscribed_music_services())
        [('Spotify', u'XXXXXX'), ('radioPup', u''), ('Spreaker', u'')]

        Interact with TuneIn

        >>> tunein = MusicService('TuneIn')
        >>> print tunein
        <MusicService 'TuneIn' at 0x10ad84e10>

        Browse an item. By default, the root item is used.

        >>> pprint (tunein.get_metadata())
        {'count': 5,
         'index': 0,
         'mediaCollection': ({'albumArtURI': u'http://spotify-...',
                              'canEnumerate': True,
                              'canPlay': False,
                              'canScroll': False,
                              'id': u'playlists',
                              'itemType': u'favorites',
                              'title': u'Playlists'},
                             {'albumArtURI': u'http://spotify-...',
                              'canEnumerate': True,
                              'canPlay': True,
                              'canScroll': False,
                              'id': u'starred',
                              'itemType': u'favorites',
                              'title': u'Starred'},
                            ...),
         'total': 5}

        Get some metadata about a specific track

        >>> response =  spotify.get_media_metadata(
        ... item_id='spotify:track:6NmXV4o6bmp704aPGyTVVG')
        >>> print (response)
        {'mediaMetadata': [{'id': u'spotify:track:6NmXV4o6bmp704aPGyTVVG'},
                           {'itemType': u'track'},
                           {'title': u'B?n Fra Helvete (Live)'},
                           {'mimeType': u'audio/x-spotify'},
                           {'trackMetadata': {'album': u'Mann Mot Mann (Ep)',
                                              'albumArtURI': u'http://o.s...9',
                                              'albumId': u'spotify:album:...',
                                              'artist': u'Kaizers Orchestra',
                                              'artistId': u'spotify:artist...',
                                              'canAddToFavorites': True,
                                              'canPlay': True,
                                              'canSkip': True,
                                              'duration': 317}}]}

        or even a playlist

        >>> response =  spotify.get_metadata(
        ...    item_id='spotify:user:spotify:playlist:0FQk6BADgIIYd3yTLCThjg')

        or a URI

        >>> response =  spotify.get_media_URI(
        ...    item_id='spotify:track:6NmXV4o6bmp704aPGyTVVG')

        Find the available search categories, and use them

        # and a search
        >>> pprint (spotify.available_search_categories)
        ['albums', 'tracks', 'artists']
        >>> result =  spotify.search(category='artists', term='miles')


    """

    _music_services_data = None

    def __init__(self, service_name, username=None):
        """Constructor

        Arg:
            service_name (str): The name of the music service, as returned by
                `get_all_music_services()`, eg 'Spotify', or 'TuneIn'
            username (str): The relevant username will be obtained
                automatically if the service is subscribed. Pass another
                username here to override it, if necessary

        """

        self.service_name = service_name
        data = self._get_music_services_data().get(service_name)
        if not data:
            raise Exception("Unknown music service: '%s'" % service_name)
        self.is_subscribed = False
        subscribed = self.get_subscribed_music_services()
        for sub in subscribed:
            if sub[0] == service_name:
                self.username = username if username else sub[1]
                self.is_subscribed = True
        self.uri = data['Uri']
        self.secure_uri = data['SecureUri']
        self.capabilities = data['Capabilities']
        self.version = data['Version']
        self.container_type = data['ContainerType']
        self.service_id = data['Id']
        # Auth_type can be 'Anonymous', 'UserId, 'DeviceLink'
        self.auth_type = data['Auth']
        self.presentation_map_uri = data.get('PresentationMapUri', None)
        self._search_prefix_map = None

        self.soap_client = SoapClient(
            location=self.secure_uri,
            action='http://www.sonos.com/Services/1.1#',
            namespace='http://www.sonos.com/Services/1.1',
            soap_ns='soap',
            # Spotify uses gzip. Others may do so as well. Unzipping is handled
            # for us by the requests library
            http_headers={'Accept-Encoding': 'gzip'},
        )

        # Add the credentials header to the SOAP method, and populate it
        # appropriately. This header must be sent with all future requests.
        #
        self.headers = SimpleXMLElement("<Headers/>")
        credentials_header = self.headers.add_child("credentials")
        credentials_header['xmlns'] = "http://www.sonos.com/Services/1.1"
        device = SoCo.any_soco()
        device_id = device.systemProperties.GetString(
            [('VariableName', 'R_TrialZPSerial')])['StringValue']
        credentials_header.marshall('deviceId', device_id)
        credentials_header.marshall('deviceProvider', 'Sonos')
        if self.auth_type in ['DeviceLink', 'UserId']:
            session_id = device.musicServices.GetSessionId([
                ('ServiceId', self.service_id),
                ('Username', self.username)
            ])['SessionId']
            credentials_header.marshall('sessionId', session_id)

    def __repr__(self):
        return '<{0} \'{1}\' at {2}>'.format(self.__class__.__name__,
                                             self.service_name,
                                             hex(id(self)))

    def __str__(self):
        return self.__repr__()

    @classmethod
    def _get_music_services_data(cls):
        """Gather important data for all music services known to the Sonos
         system

        Returns:
            dict: A dict containing relevant data. Each key is a service name,
                and each value is a dict containing relevant data.

        """
        # Check if cached, and return the cached value
        if cls._music_services_data is not None:
            return cls._music_services_data
        # Get a soco instance to query. It doesn't matter which.
        device = SoCo.any_soco()
        available_services = device.musicServices.ListAvailableServices()
        descriptor_list_xml = available_services[
            'AvailableServiceDescriptorList']
        root = XML.fromstring(descriptor_list_xml.encode('utf-8'))
        result = {}
        for service in root:
            auth_element = (service.find('Policy'))
            auth = auth_element.attrib
            result_value = service.attrib.copy()
            result_value.update(auth)
            presentation_element = (service.find('.//PresentationMap'))
            if presentation_element is not None:
                result_value['PresentationMapUri'] = presentation_element.get(
                    'Uri')
            result_value['ServiceID'] = service.get('Id')

            # ServiceType is used elsewhere in Sonos, eg to form tokens, and
            # get_subscribed_music_services() below
            # Its value always seems to be (ID*256) + 7.
            # Some serviceTypes are listed in
            # available_services['AvailableServiceTypeList'] but this does not
            # seem to be comprehensive
            result_value['ServiceType'] = str(int(service.get('Id'))*256 + 7)
            result[service.get('Name')] = result_value
        cls._music_services_data = result
        return result

    @classmethod
    def get_all_music_services(cls):
        """ Return a list of available music services.

        These services have not necessarily been subscribed to"""
        return cls._get_music_services_data().keys()

    @classmethod
    def get_subscribed_music_services(cls):
        """ Return a list of subscribed music services and their usernames.

        TuneIn is always present, and will not appear in the returned list.

        Returns:
            (list): A list of (service_name, username) tuples
        """
        # Data on subscribed services is available at
        # http://{Player_IP}:1400/status/accounts, which returns XML
        # containing something like this:
        # <?xml version="1.0"?> ...
        # <ZPSupportInfo type="User">
        #     <Accounts LastUpdateDevice="RINCON_000XXXXXXXXXXXXXX" Version="8"
        #       NextSerialNum="5">
        #         <Account Type="2311" SerialNum="1">
        #             <UN>123456789</UN>
        #             <MD>1</MD>
        #             <NN/>
        #             <OADevID/>
        #             <Key/>
        #         </Account>
        #         <Account Type="41735" SerialNum="3">
        #             <UN/>
        #             <MD>1</MD>
        #             <NN/>
        #             <OADevID/>
        #             <Key/>
        #         </Account>
        #         <Account Type="519" SerialNum="4">
        #             <UN>user@example.com</UN>
        #             <MD>1</MD>
        #             <NN/>
        #             <OADevID/>
        #             <Key/>
        #         </Account>
        #         <Account Type="41479" SerialNum="2">
        #             <UN/>
        #             <MD>1</MD>
        #             <NN/>
        #             <OADevID/>
        #             <Key/>
        #         </Account>
        #     </Accounts>
        # </ZPSupportInfo>

        #
        # It is likely that the same information is available over UPnP as well
        # via a call to
        # systemProperties.GetStringX([('VariableName','R_SvcAccounts')]))
        # This returns an encrypted string, and, so far, we cannot decrypt it
        device = SoCo.any_soco()
        settings_url = "http://{0}:1400/status/accounts".format(
            device.ip_address)
        response = requests.get(settings_url)
        dom = XML.fromstring(response.content)
        accounts = dom.findall('.//Account')
        service_types = []
        usernames = []
        for account in accounts:
            service_types.append(account.get('Type'))
            usernames.append(account.findtext('UN'))
        # for each service type, look up its name
        # We should make this faster, perhaps with a dict lookup
        data = cls._get_music_services_data().values()
        service_names = []
        for service_type in service_types:
            for service in data:
                if service['ServiceType'] == service_type:
                    service_names.append(service['Name'])
                    break
        services_info = zip(service_names, usernames)
        return services_info

# Looking at various services, we see that the following SOAP methods are
# implemented, but not all in each service. Probably, the Capabilities property
# indicates which features are implemented, but it is not clear precisely how.
# Some of the more common/useful features have been wrapped into instance
# methods, below
#    createItem(xs:string favorite)
#    createTrialAccount(xs:string deviceId)
#    deleteItem(xs:string favorite)
#    getAccount()
#    getExtendedMetadata(xs:string id)
#    getExtendedMetadataText(xs:string id, xs:string Type)
#    getLastUpdate()
#    getMediaMetadata(xs:string id)
#    getMediaURI(xs:string id)
#    getMetadata(xs:string id, xs:int index, xs:int count,xs:boolean recursive)
#    getScrollIndices(xs:string id)
#    getSessionId(xs:string username, xs:string password)
#    mergeTrialccount(xs:string deviceId)
#    rateItem(id id, xs:integer rating)
#    search(xs:string id, xs:string term, xs:string index, xs:int count)
#    setPlayedSeconds(id id, xs:int seconds)

    def get_media_metadata(self, item_id):
        """
        Get metadata for a media item

        Args:
            item_id (str): The item for which metadata is required
        Returns:
            (dict): The item's metadata
        """

        types = {'getMediaMetadataResult': {
            'mediaMetadata': [MEDIAMETADATA_TYPE]
        }}
        response = self.soap_client.call(
            'getMediaMetadata',
            ('id', item_id), headers=self.headers)
        return response.getMediaMetadataResult.unmarshall(
            types, strict=False)['getMediaMetadataResult']

    def get_media_uri(self, item_id):
        """
        Get the URI for an item

        Args:
            item_id (str): The item for which the URI is required
        Returns:
            (str): The item's URI
        """
        response = self.soap_client.call(
            'getMediaURI',
            ('id', item_id), headers=self.headers)
        return response.getMediaURIResult.unmarshall(
            types={'getMediaURIResult': str},
            strict=False)['getMediaURIResult']

    def get_metadata(
            self, item_id='root', index=0, count=100, recursive=False):
        """
        Get metadata for a container or item

        Args:
            item_id (str): The container or item to browse. Defaults to the
                root item
            index (int): The starting index. Default 0
            count (int): The maximum number of items to return. Default 100
            recursive (bool): Whether the browse should recurse into sub-items
                (Does not always work). Defaults to False
        Returns:
            (dict): The item or containers metadata

        """
        types = {'getMetadataResult': MEDIALIST_TYPE}
        response = self.soap_client.call(
            'getMetadata',
            ('id', item_id), ('index', index),
            ('count', count), ('recursive', recursive),
            headers=self.headers
        )
        return response.getMetadataResult.unmarshall(
            types, strict=False)['getMetadataResult']

    def search(self, category, term='', index=0, count=100):
        """
        Search for an item in a category

        Args:
            category (str): The search category to use. Standard Sonos search
                categories are 'artists', 'albums', 'tracks', 'playlists',
                'genres', 'stations', 'tags'. Not all are available for each
                music service. Call available_search_categories for a list for
                this service.
            term (str): The term to search for
            index (int): The starting index. Default 0
            count (int): The maximum number of items to return. Default 100

        Returns:
            (dict): The search results
        """
        types = {'searchResult': MEDIALIST_TYPE}
        search_category = self._get_search_prefix_map().get(category, None)
        if search_category is None:
            raise Exception("%s does not support the '%s' search category" % (
                self.service_name, category))
        response = self.soap_client.call(
            'search',
            ('id', search_category), ('term', term), ('index', index),
            ('count', count), headers=self.headers)
        return response.searchResult.unmarshall(
            types, strict=False)['searchResult']

    def _get_search_prefix_map(self):
        """ Fetch and parse the service search category mapping

        Standard Sonos search categories are 'all', 'artists', 'albums',
        'tracks', 'playlists', 'genres', 'stations', 'tags'. Not all are
        available for each music service

        """
        # TuneIn does not have a pmap. Its search keys are is search:station,
        # search:show, search:host

        # Presentation maps can also define custom categories. See eg
        # http://sonos-pmap.ws.sonos.com/hypemachine_pmap.6.xml
        # <SearchCategories>
        # ...
        #     <CustomCategory mappedId="SBLG" stringId="Blogs"/>
        # </SearchCategories>
        # Is it already cached? If so, return it
        if self._search_prefix_map is not None:
            return self._search_prefix_map
        # Not cached. Fetch and parse presentation map
        self._search_prefix_map = {}
        # Tunein is a special case. It has no pmap, but supports searching
        if self.service_name == "TuneIn":
            self._search_prefix_map = {
                'stations': 'search:station',
                'shows': 'search:show',
                'hosts': 'search:host',
            }
            return self._search_prefix_map
        if self.presentation_map_uri is None:
            # Assume not searchable?
            return self._search_prefix_map
        log.info('Fetching presentation map from %s',
                 self.presentation_map_uri)
        pmap = requests.get(self.presentation_map_uri)
        pmap_root = XML.fromstring(pmap.content)
        # Search translations can appear in Category or CustomCategory elements
        categories = pmap_root.findall(".//SearchCategories/Category")
        if categories is None:
            return self._search_prefix_map
        for cat in categories:
            self._search_prefix_map[cat.get('id')] = cat.get('mappedId')
        custom_categories = pmap_root.findall(
            ".//SearchCategories/CustomCategory")
        for cat in custom_categories:
            self._search_prefix_map[cat.get('stringId')] = cat.get('mappedId')
        return self._search_prefix_map

    @property
    def available_search_categories(self):
        """ The list of search categories supported by this service

        May include 'artists', 'albums', 'tracks', 'playlists',
        'genres', 'stations', 'tags', or others depending on the service

        """
        # Some services, eg Spotify, support "all", but do not advertise it
        return self._get_search_prefix_map().keys()
