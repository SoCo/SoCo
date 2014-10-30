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

        print (MusicService.get_all_music_services())

        # The TuneIn services doesn't require a login, so we don't need to use
        # any credentials
        tunein = MusicService('TuneIn')
        print (tunein.get_metadata(item_id=root))

        # Now let's play with Spotify. Spotify is authenticated by the Sonos
        # system itself, so we only need a username
        spotify = MusicService('Spotify', username='12345678') # <-your userID

        print (spotify.get_metadata(item_id='root'))

        # Now we can get some metadata about a track
        response =  spotify.get_media_metadata(
            item_id='spotify:track:6NmXV4o6bmp704aPGyTVVG')
        print (response)

        # or even a playlist
        response =  spotify.get_metadata(
            item_id='spotify:user:spotify:playlist:0FQk6BADgIIYd3yTLCThjg')
        print (response)

        # or a URI
        response =  spotify.get_media_URI(
            item_id='spotify:track:6NmXV4o6bmp704aPGyTVVG')
        pprint (response)

        # and a search
        print (spotify.available_search_categories)
        print (spotify.search(category='artists', term='miles'))


    """

    _music_services_data = None

    def __init__(self, service_name, username='', password=''):
        """Constructor

        Arg:
            service_name (str): The name of the music service, as returned by
                `get_all_music_services()`
            username (str): The username for accessing this service. Not
                needed if device authorisation is used
            password (str): The password for accessing the service. Not needed
                if device authorisation is used

        """

        self.service_name = service_name
        self.username = username
        data = self._get_music_services_data().get(service_name)
        if not data:
            raise Exception("Unknown music service: '%s'" % service_name)
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
            # Spotify uses gzip. Others may also. Unzipping is handled by
            # the Requests library
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
        # elif self.auth_type == 'UserId':
        #     credentials_header.marshall('username', username)
        #     credentials_header.marshall('password', password)

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
            dict: A dict containing relevant data, keyed by service name

        """
        # Check if cached, and return the cached value
        if cls._music_services_data is not None:
            return cls._music_services_data
        # Get a soco instance to query. It doesn't matter which.
        device = SoCo.any_soco()
        available_services = device.musicServices.ListAvailableServices()
        descriptor_list_xml = available_services[
            'AvailableServiceDescriptorList']
        # AvailableServiceTypeList is a comma separated string, so we split it
        # Each entry corresponds with an entry in
        # AvailableServicesDescriptorList
        type_list = available_services['AvailableServiceTypeList'].split(',')

        root = XML.fromstring(descriptor_list_xml.encode('utf-8'))
        result = {}
        for service, service_type in zip(root, type_list):
            auth_element = (service.find('Policy'))
            auth = auth_element.attrib
            result_value = service.attrib.copy()
            result_value.update(auth)
            presentation_element = (service.find('.//PresentationMap'))
            if presentation_element is not None:
                result_value['PresentationMapUri'] = presentation_element.get(
                    'Uri')
            result_value['ServiceType'] = service_type
            result[service.get('Name')] = result_value
        cls._music_services_data = result
        return result

    @classmethod
    def get_all_music_services(cls):
        """ Return a list of available music services.

        These services have not necessarily been subscribed to"""
        return cls._get_music_services_data().keys()

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
        response = self.soap_client.getMediaMetadata(
            id=item_id, headers=self.headers)
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
        response = self.soap_client.getMediaURI(
            id=item_id, headers=self.headers)
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

        response = self.soap_client.getMetadata(
            id=item_id, index=index, count=count, recursive=recursive,
            headers=self.headers)
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
        response = self.soap_client.search(
            id=search_category, term=term, index=index, count=count,
            headers=self.headers)
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
