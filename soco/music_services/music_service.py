# pylint: disable=fixme

"""Sonos Music Services interface.

This module provides the MusicService class and related functionality.
"""


import logging

from urllib.parse import quote as quote_url
from urllib.parse import urlparse, parse_qs

import requests

from xmltodict import parse

from .. import discovery
from ..exceptions import MusicServiceException
from ..music_services.accounts import Account
from .data_structures import parse_response, MusicServiceItem
from ..soap import SoapFault, SoapMessage
from ..xml import XML

log = logging.getLogger(__name__)  # pylint: disable=C0103


# pylint: disable=too-many-instance-attributes, protected-access
class MusicServiceSoapClient:

    """A SOAP client for accessing Music Services.

    This class handles all the necessary authentication for accessing
    third party music services. You are unlikely to need to use it
    yourself.
    """

    def __init__(self, endpoint, timeout, music_service):
        """
        Args:
             endpoint (str): The SOAP endpoint. A url.
             timeout (int): Timeout the connection after this number of
                 seconds.
             music_service (MusicService): The MusicService object to which
                 this client belongs.
        """

        self.endpoint = endpoint
        self.timeout = timeout
        self.music_service = music_service
        self.namespace = "http://www.sonos.com/Services/1.1"

        self._cached_soap_header = None

        # Spotify uses gzip. Others may do so as well. Unzipping is handled
        # for us by the requests library. Google Play seems to be very fussy
        #  about the user-agent string. The firmware release number (after
        # 'Sonos/') has to be '26' for some reason to get Google Play to
        # work. Although we have access to a real SONOS user agent
        # string (one is returned, eg, in the SERVER header of discovery
        # packets and looks like this: Linux UPnP/1.0 Sonos/29.5-91030 (
        # ZPS3)) it is a bit too much trouble here to access it, and Google
        # Play does not like it anyway.

        self.http_headers = {
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "Linux UPnP/1.0 Sonos/26.99-12345",
        }
        self._device = discovery.any_soco()
        self._device_id = self._device.systemProperties.GetString(
            [("VariableName", "R_TrialZPSerial")]
        )["StringValue"]

    def get_soap_header(self):
        """Generate the SOAP authentication header for the related service.

        This header contains all the necessary authentication details.

        Returns:
            str: A string representation of the XML content of the SOAP
                header.
        """

        # According to the SONOS SMAPI, this header must be sent with all
        # SOAP requests. Building this is an expensive operation (though
        # occasionally necessary), so f we have a cached value, return it
        if self._cached_soap_header is not None:
            return self._cached_soap_header
        music_service = self.music_service
        credentials_header = XML.Element(
            "credentials", {"xmlns": "http://www.sonos.com/Services/1.1"}
        )
        device_id = XML.SubElement(credentials_header, "deviceId")
        device_id.text = self._device_id
        device_provider = XML.SubElement(credentials_header, "deviceProvider")
        device_provider.text = "Sonos"
        if music_service.account.oa_device_id:
            # OAuth account credentials are present. We must use them to
            # authenticate.
            login_token = XML.Element("loginToken")
            token = XML.SubElement(login_token, "token")
            token.text = music_service.account.oa_device_id
            key = XML.SubElement(login_token, "key")
            key.text = music_service.account.key
            household_id = XML.SubElement(login_token, "householdId")
            household_id.text = self._device.household_id
            credentials_header.append(login_token)

        # otherwise, perhaps use DeviceLink or UserId auth
        elif music_service.auth_type in ["DeviceLink", "UserId"]:
            # We need a session ID from Sonos
            session_id = self._device.musicServices.GetSessionId(
                [
                    ("ServiceId", music_service.service_id),
                    ("Username", music_service.account.username),
                ]
            )["SessionId"]
            session_elt = XML.Element("sessionId")
            session_elt.text = session_id
            credentials_header.append(session_elt)

        # Anonymous auth. No need for anything further.
        self._cached_soap_header = XML.tostring(
            credentials_header, encoding="utf-8"
        ).decode(encoding="utf-8")
        return self._cached_soap_header

    def call(self, method, args=None):
        """Call a method on the server.

        Args:
            method (str): The name of the method to call.
            args (List[Tuple[str, str]] or None): A list of (parameter,
                value) pairs representing the parameters of the method.
                Defaults to `None`.

        Returns:
            ~collections.OrderedDict: An OrderedDict representing the response.

        Raises:
            `MusicServiceException`: containing details of the error
                returned by the music service.
        """
        message = SoapMessage(
            endpoint=self.endpoint,
            method=method,
            parameters=[] if args is None else args,
            http_headers=self.http_headers,
            soap_action="http://www.sonos.com/Services/1" ".1#{}".format(method),
            soap_header=self.get_soap_header(),
            namespace=self.namespace,
            timeout=self.timeout,
        )

        try:
            result_elt = message.call()
        except SoapFault as exc:
            if "Client.TokenRefreshRequired" in exc.faultcode:
                log.debug("Token refresh required. Trying again")
                # Remove any cached value for the SOAP header
                self._cached_soap_header = None

                # <detail>
                #   <refreshAuthTokenResult>
                #       <authToken>xxxxxxx</authToken>
                #       <privateKey>zzzzzz</privateKey>
                #   </refreshAuthTokenResult>
                # </detail>
                auth_token = exc.detail.findtext(".//authToken")
                private_key = exc.detail.findtext(".//privateKey")
                # We have new details - update the account
                self.music_service.account.oa_device_id = auth_token
                self.music_service.account.key = private_key
                message = SoapMessage(
                    endpoint=self.endpoint,
                    method=method,
                    parameters=args,
                    http_headers=self.http_headers,
                    soap_action="http://www.sonos.com/Services/1"
                    ".1#{}".format(method),
                    soap_header=self.get_soap_header(),
                    namespace=self.namespace,
                    timeout=self.timeout,
                )
                result_elt = message.call()

            else:
                raise MusicServiceException(exc.faultstring, exc.faultcode) from exc

        # The top key in the OrderedDict will be the methodResult. Its
        # value may be None if no results were returned.
        result = list(
            parse(
                XML.tostring(result_elt),
                process_namespaces=True,
                namespaces={"http://www.sonos.com/Services/1.1": None},
            ).values()
        )[0]

        return result if result is not None else {}


# pylint: disable=too-many-instance-attributes
class MusicService:

    """The MusicService class provides access to third party music services.

    Example:

        List all the services Sonos knows about:

        >>> from soco.music_services import MusicService
        >>> print(MusicService.get_all_music_services_names())
        ['Spotify', 'The Hype Machine', 'Saavn', 'Bandcamp',
         'Stitcher SmartRadio', 'Concert Vault',
         ...
         ]

        Or just those to which you are subscribed:

        >>> print(MusicService.get_subscribed_services_names())
        ['Spotify', 'radioPup', 'Spreaker']

        Interact with TuneIn:

        >>> tunein = MusicService('TuneIn')
        >>> print (tunein)
        <MusicService 'TuneIn' at 0x10ad84e10>

        Browse an item. By default, the root item is used. An
        :class:`~collections.OrderedDict` is returned:

        >>> from json import dumps # Used for pretty printing ordereddicts
        >>> print(dumps(tunein.get_metadata(), indent=4))
        {
            "index": "0",
            "count": "7",
            "total": "7",
            "mediaCollection": [
                {
                    "id": "featured:c100000150",
                    "title": "Blue Note on SONOS",
                    "itemType": "container",
                    "authRequired": "false",
                    "canPlay": "false",
                    "canEnumerate": "true",
                    "canCache": "true",
                    "homogeneous": "false",
                    "canAddToFavorite": "false",
                    "canScroll": "false",
                    "albumArtURI":
                    "http://cdn-albums.tunein.com/sonos/channel_legacy.png"
                },
                {
                    "id": "y1",
                    "title": "Music",
                    "itemType": "container",
                    "authRequired": "false",
                    "canPlay": "false",
                    "canEnumerate": "true",
                    "canCache": "true",
                    "homogeneous": "false",
                    "canAddToFavorite": "false",
                    "canScroll": "false",
                    "albumArtURI": "http://cdn-albums.tunein.com/sonos...
                    .png"
                },
         ...
            ]
        }


        Interact with Spotify (assuming you are subscribed):

        >>> spotify = MusicService('Spotify')

        Get some metadata about a specific track:

        >>> response =  spotify.get_media_metadata(
        ... item_id='spotify:track:6NmXV4o6bmp704aPGyTVVG')
        >>> print(dumps(response, indent=4))
        {
            "mediaMetadata": {
                "id": "spotify:track:6NmXV4o6bmp704aPGyTVVG",
                "itemType": "track",
                "title": "B\u00f8n Fra Helvete (Live)",
                "mimeType": "audio/x-spotify",
                "trackMetadata": {
                    "artistId": "spotify:artist:1s1DnVoBDfp3jxjjew8cBR",
                    "artist": "Kaizers Orchestra",
                    "albumId": "spotify:album:6K8NUknbPh5TGaKeZdDwSg",
                    "album": "Mann Mot Mann (Ep)",
                    "duration": "317",
                    "albumArtURI":
                    "http://o.scdn.co/image/7b76a5074416e83fa3f3cd...9",
                    "canPlay": "true",
                    "canSkip": "true",
                    "canAddToFavorites": "true"
                }
            }
        }
        or even a playlist:

        >>> response =  spotify.get_metadata(
        ...    item_id='spotify:user:spotify:playlist:0FQk6BADgIIYd3yTLCThjg')

        Find the available search categories, and use them:

        >>> print(spotify.available_search_categories)
        ['albums', 'tracks', 'artists']
        >>> result =  spotify.search(category='artists', term='miles')


    Note:
        Some of this code is still unstable, and in particular the data
        structures returned by methods such as `get_metadata` may change in
        future.
    """

    _music_services_data = None

    def __init__(self, service_name, account=None):
        """
        Args:
            service_name (str): The name of the music service, as returned by
                `get_all_music_services_names()`, eg 'Spotify', or 'TuneIn'
            account (Account): The account to use to access this service.
                If none is specified, one will be chosen automatically if
                possible. Defaults to `None`.

        Raises:
            `MusicServiceException`
        """

        self.service_name = service_name
        # Look up the data for this service
        data = self.get_data_for_name(service_name)
        self.uri = data["Uri"]
        self.secure_uri = data["SecureUri"]
        self.capabilities = data["Capabilities"]
        self.version = data["Version"]
        self.container_type = data["ContainerType"]
        self.service_id = data["Id"]
        # Auth_type can be 'Anonymous', 'UserId, 'DeviceLink'
        self.auth_type = data["Auth"]
        self.presentation_map_uri = data.get("PresentationMapUri", None)
        self._search_prefix_map = None
        self.service_type = data["ServiceType"]
        if account is not None:
            self.account = account
        else:
            # try to find an account for this service
            for acct in Account.get_accounts().values():
                if acct.service_type == self.service_type:
                    self.account = acct
                    break
            else:
                raise MusicServiceException(
                    "No account found for service: '%s'" % service_name
                )

        self.soap_client = MusicServiceSoapClient(
            endpoint=self.secure_uri, timeout=9, music_service=self  # The default is 60
        )

    def __repr__(self):
        return "<{} '{}' at {}>".format(
            self.__class__.__name__, self.service_name, hex(id(self))
        )

    def __str__(self):
        return self.__repr__()

    @staticmethod
    def _get_music_services_data_xml(soco=None):
        """Fetch the music services data xml from a Sonos device.

        Args:
            soco (SoCo): a SoCo instance to query. If none is specified, a
            random device will be used. Defaults to `None`.

        Returns:
            str: a string containing the music services data xml
        """
        device = soco or discovery.any_soco()
        log.debug("Fetching music services data from %s", device)
        available_services = device.musicServices.ListAvailableServices()
        descriptor_list_xml = available_services["AvailableServiceDescriptorList"]
        log.debug("Services descriptor list: %s", descriptor_list_xml)
        return descriptor_list_xml

    @classmethod
    def _get_music_services_data(cls):
        """Parse raw account data xml into a useful python datastructure.

        Returns:
            dict: Each key is a service_type, and each value is a
            `dict` containing relevant data.
        """
        # Return from cache if we have it.
        if cls._music_services_data is not None:
            return cls._music_services_data

        result = {}
        root = XML.fromstring(cls._get_music_services_data_xml().encode("utf-8"))
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

        # Ideally, the search path should be './/Service' to find Service
        # elements at any level, but Python 2.6 breaks with this if Service
        # is a child of the current element. Since 'Service' works here, we use
        # that instead
        services = root.findall("Service")
        for service in services:
            result_value = service.attrib.copy()
            name = service.get("Name")
            result_value["Name"] = name
            auth_element = service.find("Policy")
            auth = auth_element.attrib
            result_value.update(auth)
            presentation_element = service.find(".//PresentationMap")
            if presentation_element is not None:
                result_value["PresentationMapUri"] = presentation_element.get("Uri")
            result_value["ServiceID"] = service.get("Id")
            # ServiceType is used elsewhere in Sonos, eg to form tokens,
            # and get_subscribed_music_services() below. It is also the
            # 'Type' used in account_xml (see above). Its value always
            # seems to be (ID*256) + 7. Some serviceTypes are also
            # listed in available_services['AvailableServiceTypeList']
            # but this does not seem to be comprehensive
            service_type = str(int(service.get("Id")) * 256 + 7)
            result_value["ServiceType"] = service_type
            result[service_type] = result_value
        # Cache this so we don't need to do it again.
        cls._music_services_data = result
        return result

    @classmethod
    def get_all_music_services_names(cls):
        """Get a list of the names of all available music services.

        These services have not necessarily been subscribed to.

        Returns:
            list: A list of strings.
        """
        return [service["Name"] for service in cls._get_music_services_data().values()]

    @classmethod
    def get_subscribed_services_names(cls):
        """Get a list of the names of all subscribed music services.

        Returns:
            list: A list of strings.
        """
        # This is very inefficient - loops within loops within loops, and
        # many network requests
        # Optimise it?
        accounts_for_service = Account.get_accounts_for_service
        service_data = cls._get_music_services_data().values()
        return [
            service["Name"]
            for service in service_data
            if len(accounts_for_service(service["ServiceType"])) > 0
        ]

    @classmethod
    def get_data_for_name(cls, service_name):
        """Get the data relating to a named music service.

        Args:
            service_name (str): The name of the music service for which data
                is required.

        Returns:
            dict: Data relating to the music service.

        Raises:
            `MusicServiceException`: if the music service cannot be found.
        """
        for service in cls._get_music_services_data().values():
            if service_name == service["Name"]:
                return service
        raise MusicServiceException("Unknown music service: '%s'" % service_name)

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
                "stations": "search:station",
                "shows": "search:show",
                "hosts": "search:host",
            }
            return self._search_prefix_map
        if self.presentation_map_uri is None:
            # Assume not searchable?
            return self._search_prefix_map
        log.info("Fetching presentation map from %s", self.presentation_map_uri)
        pmap = requests.get(self.presentation_map_uri, timeout=9)
        pmap_root = XML.fromstring(pmap.content)
        # Search translations can appear in Category or CustomCategory elements
        categories = pmap_root.findall(".//SearchCategories/Category")
        if categories is None:
            return self._search_prefix_map
        for cat in categories:
            self._search_prefix_map[cat.get("id")] = cat.get("mappedId")
        custom_categories = pmap_root.findall(".//SearchCategories/CustomCategory")
        for cat in custom_categories:
            self._search_prefix_map[cat.get("stringId")] = cat.get("mappedId")
        return self._search_prefix_map

    @property
    def available_search_categories(self):
        """list:  The list of search categories (each a string) supported.

        May include ``'artists'``, ``'albums'``, ``'tracks'``, ``'playlists'``,
        ``'genres'``, ``'stations'``, ``'tags'``, or others depending on the
        service. Some services, such as Spotify, support ``'all'``, but do not
        advertise it.

        Any of the categories in this list may be used as a value for
        ``category`` in :meth:`search`.

        Example:

            >>> print(spotify.available_search_categories)
            ['albums', 'tracks', 'artists']
            >>> result =  spotify.search(category='artists', term='miles')


        """
        return self._get_search_prefix_map().keys()

    def sonos_uri_from_id(self, item_id):
        """Get a uri which can be sent for playing.

        Args:
            item_id (str): The unique id of a playable item for this music
                service, such as that returned in the metadata from
                `get_metadata`, eg ``spotify:track:2qs5ZcLByNTctJKbhAZ9JE``

        Returns:
            str: A URI of the form: ``soco://spotify%3Atrack
            %3A2qs5ZcLByNTctJKbhAZ9JE?sid=2311&sn=1`` which encodes the
            ``item_id``, and relevant data from the account for the music
            service. This URI can be sent to a Sonos device for playing,
            and the device itself will retrieve all the necessary metadata
            such as title, album etc.
        """
        # Real Sonos URIs look like this:
        # x-sonos-http:tr%3a92352286.mp3?sid=2&flags=8224&sn=4 The
        # extension (.mp3) presumably comes from the mime-type returned in a
        # MusicService.get_metadata() result (though for Spotify the mime-type
        # is audio/x-spotify, and there is no extension. See
        # http://musicpartners.sonos.com/node/464 for supported mime-types and
        # related extensions). The scheme (x-sonos-http) presumably
        # indicates how the player is to obtain the stream for playing. It
        # is not clear what the flags param is used for (perhaps bitrate,
        # or certain metadata such as canSkip?). Fortunately, none of these
        # seems to be necessary. We can leave them out, (or in the case of
        # the scheme, use 'soco' as dummy text, and the players still seem
        # to do the right thing.

        # quote_url will break if given unicode on Py2.6, and early 2.7. So
        # we need to encode.
        item_id = quote_url(item_id.encode("utf-8"))
        # Add the account info to the end as query params
        account = self.account
        result = "soco://{}?sid={}&sn={}".format(
            item_id, self.service_id, account.serial_number
        )
        return result

    @property
    def desc(self):
        """str: The Sonos descriptor to use for this service.

        The Sonos descriptor is used as the content of the <desc> tag in
        DIDL metadata, to indicate the relevant music service id and username.
        """
        desc = "SA_RINCON{}_{}".format(self.account.service_type, self.account.username)
        return desc

    ########################################################################
    #                                                                      #
    #                           SOAP METHODS.                              #
    #                                                                      #
    ########################################################################

    #  Looking at various services, we see that the following SOAP methods
    #  are implemented, but not all in each service. Probably, the
    #  Capabilities property indicates which features are implemented, but
    #  it is not clear precisely how. Some of the more common/useful
    #  features have been wrapped into instance methods, below.
    #  See generally: http://musicpartners.sonos.com/node/81

    #    createItem(xs:string favorite)
    #    createTrialAccount(xs:string deviceId)
    #    deleteItem(xs:string favorite)
    #    getAccount()
    #    getExtendedMetadata(xs:string id)
    #    getExtendedMetadataText(xs:string id, xs:string Type)
    #    getLastUpdate()
    #    getMediaMetadata(xs:string id)
    #    getMediaURI(xs:string id)
    #    getMetadata(xs:string id, xs:int index, xs:int count,xs:boolean
    #                recursive)
    #    getScrollIndices(xs:string id)
    #    getSessionId(xs:string username, xs:string password)
    #    mergeTrialccount(xs:string deviceId)
    #    rateItem(id id, xs:integer rating)
    #    search(xs:string id, xs:string term, xs:string index, xs:int count)
    #    setPlayedSeconds(id id, xs:int seconds)

    def get_metadata(self, item="root", index=0, count=100, recursive=False):
        """Get metadata for a container or item.

        Args:
            item (str or MusicServiceItem): The container or item to browse
                given either as a MusicServiceItem instance or as a str.
                Defaults to the root item.
            index (int): The starting index. Default 0.
            count (int): The maximum number of items to return. Default 100.
            recursive (bool): Whether the browse should recurse into sub-items
                (Does not always work). Defaults to `False`.

        Returns:
            ~collections.OrderedDict: The item or container's metadata,
            or `None`.

        See also:
            The Sonos `getMetadata API
            <http://musicpartners.sonos.com/node/83>`_.

        """
        if isinstance(item, MusicServiceItem):
            item_id = item.id  # pylint: disable=no-member
        else:
            item_id = item
        response = self.soap_client.call(
            "getMetadata",
            [
                ("id", item_id),
                ("index", index),
                ("count", count),
                ("recursive", 1 if recursive else 0),
            ],
        )
        return parse_response(self, response, "browse")

    def search(self, category, term="", index=0, count=100):
        """Search for an item in a category.

        Args:
            category (str): The search category to use. Standard Sonos search
                categories are 'artists', 'albums', 'tracks', 'playlists',
                'genres', 'stations', 'tags'. Not all are available for each
                music service. Call available_search_categories for a list for
                this service.
            term (str): The term to search for.
            index (int): The starting index. Default 0.
            count (int): The maximum number of items to return. Default 100.

        Returns:
            ~collections.OrderedDict: The search results, or `None`.

        See also:
            The Sonos `search API <http://musicpartners.sonos.com/node/86>`_
        """
        search_category = self._get_search_prefix_map().get(category, None)
        if search_category is None:
            raise MusicServiceException(
                "%s does not support the '%s' search category"
                % (self.service_name, category)
            )

        response = self.soap_client.call(
            "search",
            [
                ("id", search_category),
                ("term", term),
                ("index", index),
                ("count", count),
            ],
        )

        return parse_response(self, response, category)

    def get_media_metadata(self, item_id):
        """Get metadata for a media item.

        Args:
            item_id (str): The item for which metadata is required.

        Returns:
            ~collections.OrderedDict: The item's metadata, or `None`

        See also:
            The Sonos `getMediaMetadata API
            <http://musicpartners.sonos.com/node/83>`_
        """
        response = self.soap_client.call("getMediaMetadata", [("id", item_id)])
        return response.get("getMediaMetadataResult", None)

    def get_media_uri(self, item_id):
        """Get a streaming URI for an item.

        Note:
           You should not need to use this directly. It is used by the Sonos
           players (not the controllers) to obtain the uri of the media
           stream. If you want to have a player play a media item,
           you should add add it to the queue using its id and let the
           player work out where to get the stream from (see `On Demand
           Playback <http://musicpartners.sonos.com/node/421>`_ and
           `Programmed Radio <http://musicpartners.sonos.com/node/422>`_)

        Args:
            item_id (str): The item for which the URI is required

        Returns:
            str: The item's streaming URI.
        """
        response = self.soap_client.call("getMediaURI", [("id", item_id)])
        return response.get("getMediaURIResult", None)

    def get_last_update(self):
        """Get last_update details for this music service.

        Returns:
            ~collections.OrderedDict: A dict with keys 'catalog',
            and 'favorites'. The value of each is a string which changes
            each time the catalog or favorites change. You can use this to
            detect when any caches need to be updated.
        """
        # TODO: Maybe create a favorites/catalog cache which is invalidated
        # TODO: when these values change?
        response = self.soap_client.call("getLastUpdate")
        return response.get("getLastUpdateResult", None)

    def get_extended_metadata(self, item_id):
        """Get extended metadata for a media item, such as related items.

        Args:
            item_id (str): The item for which metadata is required.

        Returns:
            ~collections.OrderedDict: The item's extended metadata or None.

        See also:
            The Sonos `getExtendedMetadata API
            <http://musicpartners.sonos.com/node/128>`_
        """
        response = self.soap_client.call("getExtendedMetadata", [("id", item_id)])
        return response.get("getExtendedMetadataResult", None)

    def get_extended_metadata_text(self, item_id, metadata_type):
        """Get extended metadata text for a media item.

        Args:
            item_id (str): The item for which metadata is required
            metadata_type (str): The type of text to return, eg
            ``'ARTIST_BIO'``, or ``'ALBUM_NOTES'``. Calling
            `get_extended_metadata` for the item will show which extended
            metadata_types are available (under relatedBrowse and relatedText).

        Returns:
            str: The item's extended metadata text or None

        See also:
            The Sonos `getExtendedMetadataText API
            <http://musicpartners.sonos.com/node/127>`_
        """
        response = self.soap_client.call(
            "getExtendedMetadataText", [("id", item_id), ("type", metadata_type)]
        )
        return response.get("getExtendedMetadataTextResult", None)


def desc_from_uri(uri):
    """Create the content of DIDL desc element from a uri.

    Args:
        uri (str): A uri, eg:
            ``'x-sonos-http:track%3a3402413.mp3?sid=2&amp;flags=32&amp;sn=4'``

    Returns:
        str: The content of a desc element for that uri, eg
            ``'SA_RINCON519_email@example.com'``
    """
    #
    # If there is an sn parameter (which is the serial number of an account),
    # we can obtain all the information we need from that, because we can find
    # the relevant service_id in the account database (it is the same as the
    # service_type). Consequently, the sid parameter is unneeded. But if sn is
    # missing, we need the sid (service_type) parameter to find a relevant
    # account

    # urlparse does not work consistently with custom URI schemes such as
    # those used by Sonos. This is especially broken in Python 2.6 and
    # early versions of 2.7: http://bugs.python.org/issue9374
    # As a workaround, we split off the scheme manually, and then parse
    # the uri as if it were http
    if ":" in uri:
        _, uri = uri.split(":", 1)
    # Remove 'amp;' from uri, leaving '&' as the separator
    # See: https://github.com/SoCo/SoCo/issues/810
    uri = uri.replace("amp;", "")
    query_string = parse_qs(urlparse(uri, "http").query)
    # Is there an account serial number?
    if query_string.get("sn"):
        account_serial_number = query_string["sn"][0]
        try:
            account = Account.get_accounts()[account_serial_number]
            desc = "SA_RINCON{}_{}".format(account.service_type, account.username)
            return desc
        except KeyError:
            # There is no account matching this serial number. Fall back to
            # using the service id to find an account
            pass
    if query_string.get("sid"):
        service_id = query_string["sid"][0]
        for service in MusicService._get_music_services_data().values():
            if service_id == service["ServiceID"]:
                service_type = service["ServiceType"]
                account = Account.get_accounts_for_service(service_type)
                if not account:
                    break
                # Use the first account we find
                account = account[0]
                desc = "SA_RINCON{}_{}".format(account.service_type, account.username)
                return desc
    # Nothing found. Default to the standard desc value. Is this the right
    # thing to do?
    desc = "RINCON_AssociatedZPUDN"
    return desc
