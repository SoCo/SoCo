# -*- coding: utf-8 -*-

"""Sonos Music Services interface.

This module provides the MusicService class and related functionality.

"""

from __future__ import unicode_literals

from pysimplesoap.client import SoapClient, SoapFault
from pysimplesoap.simplexml import SimpleXMLElement

import requests

import logging
log = logging.getLogger(__name__)  # pylint: disable=C0103

from soco import SoCo
from soco.xml import XML
from soco.exceptions import MusicServiceException
from soco.music_services.soap_types import (MEDIAMETADATA_TYPE, MEDIALIST_TYPE)
# pylint: disable=unused-import
from soco.music_services import soap_transport  # noqa
from soco.compat import urlparse, parse_qs


# pylint: disable=too-many-instance-attributes
class MusicAccount(object):

    """An account for a Music Service.

    Each service may have more than one account: see
    http://www.sonos.com/en-gb/software/release/5-2

    """

    _account_data = None

    def __init__(self):
        """Constructor.

        Args:
            account_type (str): A unique identifier for the music service to
                which this account relates, eg '2311' for Spotify. It is the
                same as the `service_type` of the relevant MusicService object
            serial_number: (str): A unique identifier for this account
            nickname (str): The account's nickname
            deleted (bool): True if this account has been deleted
            username (str): The username used for logging into the music
                service
            metadata (str): Metadata for the account
            oa_device_id (str): OpenAuth id (currently unused?)
            key (str): (unknown)

        """

        self.account_type = ''
        self.serial_number = ''
        self.nickname = ''
        self.deleted = False
        self.username = ''
        self.metadata = ''
        self.oa_device_id = ''
        self.key = ''

    def __repr__(self):
        return "<{0} '{1}:{2}:{3}' at {4}>".format(
            self.__class__.__name__,
            self.serial_number,
            self.account_type,
            self.nickname,
            hex(id(self))
        )

    def __str__(self):
        return self.__repr__()

    @staticmethod
    def _get_account_xml(soco=None):
        """Fetch the account data from a Sonos device.

        Args:
            soco (SoCo): a SoCo instance to query. If none is specified, a
                random device will be used.

        Returns:
            (str): a byte string containing the account data xml

        """
        # It is likely that the same information is available over UPnP as well
        # via a call to
        # systemProperties.GetStringX([('VariableName','R_SvcAccounts')]))
        # This returns an encrypted string, and, so far, we cannot decrypt it
        device = soco or SoCo.any_soco()
        log.debug("Fetching account data from %s", device)
        settings_url = "http://{0}:1400/status/accounts".format(
            device.ip_address)
        result = requests.get(settings_url).content
        log.debug("Account data: %s", result)
        return result

    @classmethod
    def get_account_data(cls):
        """Parse raw account data xml into a useful python datastructure.

        Returns:
            (dict): A dict keyed by account serial number. Each value is a
                MusicAccount object

        """

        # Check if there is a cached value, and return it if there is.
        if cls._account_data is not None:
            return cls._account_data

        result = {}
        root = XML.fromstring(cls._get_account_xml())
        # <ZPSupportInfo type="User">
        #   <Accounts
        #   LastUpdateDevice="RINCON_000XXXXXXXX400"
        #   Version="8" NextSerialNum="5">
        #     <Account Type="2311" SerialNum="1">
        #         <UN>12345678</UN>
        #         <MD>1</MD>
        #         <NN></NN>
        #         <OADevID></OADevID>
        #         <Key></Key>
        #     </Account>
        #     <Account Type="41735" SerialNum="3" Deleted="1">
        #         <UN></UN>
        #         <MD>1</MD>
        #         <NN>Nickname</NN>
        #         <OADevID></OADevID>
        #         <Key></Key>
        #     </Account>
        # ...
        #   <Accounts />
        accounts = root.findall('.//Account')
        for account in accounts:
            acct = MusicAccount()

            acct.account_type = account.get('Type')
            acct.serial_number = account.get('SerialNum')
            acct.deleted = True if account.get('Deleted') == '1' else False
            acct.username = account.findtext('UN')
            # Not sure what 'MD' stands for.  Metadata?
            acct.metadata = account.findtext('MD')
            acct.nickname = account.findtext('NN')
            acct.oa_device_id = account.findtext('OADevID')
            acct.key = account.findtext('Key')

            result[acct.serial_number] = acct

        cls._account_data = result
        return result

    @classmethod
    def get_all_accounts(cls):
        """Get a list of all accounts.

        Deleted accounts are excluded.

        Returns:
            (list): A set of MusicAccount instances

        """
        return [
            a for a in cls.get_account_data().values() if not a.deleted
        ]

    @classmethod
    def get_accounts_for_service(cls, service_type):
        """Get a list of accounts for a given music service.

        Args:
            service_type (str): The service_type to use

        Returns:
            (list): A list of MusicAccount instances

        """
        return [
            a for a in cls.get_all_accounts() if a.account_type == service_type
        ]


# pylint: disable=too-many-instance-attributes
class MusicService(object):

    """The MusicService class provides access to third party music services.

    Example:

        Print all the services Sonos knows about

        >>> from soco.music_services import MusicService
        >>> from pprint import pprint
        >>> print (MusicService.get_all_music_services_names())
        ['Spotify',
         'The Hype Machine',
         'Saavn',
         'Bandcamp',
         'Stitcher SmartRadio',
         'Concert Vault',
         ...
         ]

        Or just those tho which you are subscribed

        >>> pprint (MusicService.get_subscribed_services_names())
        ['Spotify', 'radioPup', 'Spreaker']

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

        Interact with Spotify (assuming you are subscribed)

        >>> spotify = MusicService('Spotify')

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

    def __init__(self, service_name, account=None):
        """Constructor.

        Arg:
            service_name (str): The name of the music service, as returned by
                `get_all_music_services_names()`, eg 'Spotify', or 'TuneIn'
            account (MusicAccount): The account to use to access this service.
                If none is specified, one will be chosen automatically if
                possible.

        """

        self.service_name = service_name
        data = self.get_data_for_name(service_name)
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
        self.service_type = data['ServiceType']
        if account is not None:
            self.account = account
        elif service_name == "TuneIn":
            # TuneIn is always present, but will have no account data, so we
            # need to handle it specially. Create a dummy account
            self.account = MusicAccount()
        else:
            # try to find an account for this service
            for acct in MusicAccount.get_all_accounts():
                if acct.account_type == self.service_type:
                    self.account = acct
                    break
            else:
                raise MusicServiceException(
                    "No account found for service: '%s'" % service_name)

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
        self.headers = self._get_headers()

    def __repr__(self):
        return '<{0} \'{1}\' at {2}>'.format(self.__class__.__name__,
                                             self.service_name,
                                             hex(id(self)))

    def __str__(self):
        return self.__repr__()

    @staticmethod
    def get_music_services_data_xml(soco=None):
        """Fetch the music services data xml from a Sonos device.

        Args:
            soco (SoCo): a SoCo instance to query. If none is specified, a
            random device will be used.

        Returns:
            (str): a string containing the music services data xml

        """
        device = soco or SoCo.any_soco()
        log.debug("Fetching music services data from %s", device)
        available_services = device.musicServices.ListAvailableServices()
        descriptor_list_xml = available_services[
            'AvailableServiceDescriptorList']
        log.debug("Services descriptor list: %s", descriptor_list_xml)
        return descriptor_list_xml

    @classmethod
    def get_music_services_data(cls):
        """Parse raw account data xml into a useful python datastructure.

        Returns:
            (dict): A dict. Each key is a service_type, and each value is a
                dict containing relevant data

        """
        if cls._music_services_data is not None:
            return cls._music_services_data

        result = {}
        root = XML.fromstring(
            cls.get_music_services_data_xml().encode('utf-8')
        )
        # <Services SchemaVersion="1">
        #     <Service Id="163" Name="Spreaker" Version="1.1"
        #         Uri="http://sonos.spreaker.com/sonos/service/v1"
        #         SecureUri="https://sonos.spreaker.com/sonos/service/v1"
        #         ContainerType="MService"
        #         Capabilities="513"
        #         MaxMessagingChars="0">
        #         <Policy Auth="Anonymous" PollInterval="30" />
        #         <Presentation>
        #             <Strings
        #                 Version="1"
        #                 Uri="https:...string_table.xml" />
        #             <PresentationMap Version="2"
        #                 Uri="https://...presentation_map.xml" />
        #         </Presentation>
        #     </Service>
        # ...
        # </ Services>
        services = root.findall('.//Service')
        for service in services:
            result_value = service.attrib.copy()
            name = service.get('Name')
            result_value['Name'] = name
            auth_element = (service.find('Policy'))
            auth = auth_element.attrib
            result_value.update(auth)
            presentation_element = (service.find('.//PresentationMap'))
            if presentation_element is not None:
                result_value['PresentationMapUri'] = \
                    presentation_element.get('Uri')
            result_value['ServiceID'] = service.get('Id')
            # ServiceType is used elsewhere in Sonos, eg to form tokens,
            # and get_subscribed_music_services() below. It is also the
            # 'Type' used in account_xml (see above). Its value always
            # seems to be (ID*256) + 7. Some serviceTypes are also
            # listed in available_services['AvailableServiceTypeList']
            # but this does not seem to be comprehensive
            service_type = str(int(service.get('Id')) * 256 + 7)
            result_value['ServiceType'] = service_type
            result[service_type] = result_value
        cls._music_services_data = result
        return result

    @classmethod
    def get_all_music_services_names(cls):
        """Get a list of the names of all available music services.

        These services have not necessarily been subscribed to.

        Returns:
            (list): A list of strings

        """
        return [
            service['Name'] for service in
            cls.get_music_services_data().values()
        ]

    @classmethod
    def get_subscribed_services_names(cls):
        """Get a list of the names of all subscribed music services.

        The TuneIn service is always subscribed but will not appear in the list

        Returns:
            (list): A list of strings
        """
        accounts_for_service = MusicAccount.get_accounts_for_service
        return [
            service['Name'] for service in
            cls.get_music_services_data().values() if len(
                accounts_for_service(service['ServiceType'])
                ) > 0
        ]

    @classmethod
    def get_data_for_name(cls, service_name):
        """Get the data relating to a named music service."""
        for service in cls.get_music_services_data().values():
            if service_name == service["Name"]:
                return service
        raise MusicServiceException(
            "Unknown music service: '%s'" % service_name)

    def _get_headers(self):
        """Get the authentication header for this service."""
        result = SimpleXMLElement("<Headers/>")
        credentials_header = result.add_child("credentials")
        credentials_header['xmlns'] = "http://www.sonos.com/Services/1.1"

        device = SoCo.any_soco()
        device_id = device.systemProperties.GetString(
            [('VariableName', 'R_TrialZPSerial')])['StringValue']
        credentials_header.marshall('deviceId', device_id)
        credentials_header.marshall('deviceProvider', 'Sonos')
        if self.auth_type in ['DeviceLink', 'UserId']:
            session_id = device.musicServices.GetSessionId([
                ('ServiceId', self.service_id),
                ('Username', self.account.username)
            ])['SessionId']
            credentials_header.marshall('sessionId', session_id)
        return result

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
        """Get metadata for a media item.

        Args:
            item_id (str): The item for which metadata is required
        Returns:
            (dict): The item's metadata

        """

        types = {'getMediaMetadataResult': {
            'mediaMetadata': [MEDIAMETADATA_TYPE]
        }}
        try:
            response = self.soap_client.call(
                'getMediaMetadata',
                ('id', item_id), headers=self.headers)
        except SoapFault as exc:
            raise MusicServiceException(exc.faultstring)
        return response.getMediaMetadataResult.unmarshall(
            types, strict=False)['getMediaMetadataResult']

    def get_media_uri(self, item_id):
        """Get the URI for an item.

        Args:
            item_id (str): The item for which the URI is required
        Returns:
            (str): The item's URI

        """
        try:
            response = self.soap_client.call(
                'getMediaURI',
                ('id', item_id), headers=self.headers)
        except SoapFault as exc:
            raise MusicServiceException(exc.faultstring)
        return response.getMediaURIResult.unmarshall(
            types={'getMediaURIResult': str},
            strict=False)['getMediaURIResult']

    def get_metadata(
            self, item_id='root', index=0, count=100, recursive=False):
        """Get metadata for a container or item.

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
        try:
            response = self.soap_client.call(
                'getMetadata',
                ('id', item_id), ('index', index),
                ('count', count), ('recursive', recursive),
                headers=self.headers
            )
        except SoapFault as exc:
            raise MusicServiceException(exc.faultstring)
        return response.getMetadataResult.unmarshall(
            types, strict=False)['getMetadataResult']

    def search(self, category, term='', index=0, count=100):
        """Search for an item in a category.

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
            raise MusicServiceException(
                "%s does not support the '%s' search category" % (
                    self.service_name, category))
        try:
            response = self.soap_client.call(
                'search',
                ('id', search_category), ('term', term), ('index', index),
                ('count', count), headers=self.headers)
        except SoapFault as exc:
            raise MusicServiceException(exc.faultstring)
        return response.searchResult.unmarshall(
            types, strict=False)['searchResult']

    def _get_search_prefix_map(self):
        """Fetch and parse the service search category mapping.

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
        """The list of search categories supported by this service.

        May include 'artists', 'albums', 'tracks', 'playlists',
        'genres', 'stations', 'tags', or others depending on the service

        """
        # Some services, eg Spotify, support "all", but do not advertise it
        return self._get_search_prefix_map().keys()


def desc_from_uri(uri):
    """Create the content of DIDL desc element from a uri

    Args:
        uri (str): A uri, eg:
            x-sonos-http:track%3a3402413.mp3?sid=2&amp;flags=32&amp;sn=4

    Returns:
        (str): The content of a desc element for that uri, eg
            SA_RINCON519_email@example.com

    """
    #
    # If there is an sn parameter (which is the serial number of an account),
    # we can obtain all the infomration we need from that, because we can find
    # the relevant service_id in the account database (it is the same as the
    # account_type). Consequently, the sid parameter is unneeded. But if sn is
    # missing, we need the sid (service_type) parameter to find a relevant
    # account

    query_string = parse_qs(urlparse(uri).query)
    # Is there an account serial number?
    if query_string.get('sn'):
        account_serial_number = query_string['sn'][0]
        try:
            account = MusicAccount.get_account_data()[account_serial_number]
            desc = "SA_RINCON{0}_{1}".format(
                account.account_type, account.username)
            return desc
        except KeyError:
            # There is no account matching this serial number. Fall back to
            # using the service id to find an account
            pass
    if query_string.get('sid'):
        service_id = query_string['sid'][0]
        for service in MusicService.get_music_services_data().values():
            if service_id == service["ServiceID"]:
                service_type = service["ServiceType"]
                account = MusicAccount.get_accounts_for_service(service_type)
                if len(account) == 0:
                    break
                # Use the first account we find
                account = account[0]
                desc = "SA_RINCON{0}_{1}".format(
                    account.account_type, account.username)
                return desc
    # Nothing found. Default to the standard desc value. Is this the right
    # thing to do?
    desc = 'RINCON_AssociatedZPUDN'
    return desc
