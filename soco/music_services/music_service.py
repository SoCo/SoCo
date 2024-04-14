# pylint: disable=fixme

"""Sonos Music Services interface.

This module provides the MusicService class and related functionality.

Known problems:

1. Not all music services follow the pattern layout for the
   authentication information completely. This means that it might be
   necessary to tweak the code for individual services. This is an
   unfortunate result of Sonos not enforcing data hygiene of its
   services. The implication for SoCo is that getting all services
   to work will require more effort and the kind of broader testing we
   will only get by putting the code out there. Hence, if you are an
   early adopter of the music service code (added in version 0.26)
   consider yourselves guinea pigs.
2. There currently is no way to reset an authentication, at least when
   authentication has been performed for TIDAL (which uses device link
   authentication), after it has been done once for a particular
   household ID, it fails on subsequent attempts. What this might mean
   is that if you lose the authentication tokens for such a service,
   it may not be possible to generate new ones. Obviously, some method
   must exist to reset this, but it is not presently implemented.

"""


import logging
from urllib.parse import quote as quote_url
import json
import requests
from xmltodict import parse

from .. import discovery
from ..exceptions import MusicServiceException, MusicServiceAuthException
from .data_structures import parse_response, MusicServiceItem
from .token_store import JsonFileTokenStore
from ..soap import SoapFault, SoapMessage
from ..xml import XML

log = logging.getLogger(__name__)  # pylint: disable=C0103


# pylint: disable=protected-access
class MusicServiceSoapClient:
    """A SOAP client for accessing Music Services.

    This class handles all the necessary authentication for accessing
    third party music services. You are unlikely to need to use it
    yourself.
    """

    def __init__(self, endpoint, timeout, music_service, token_store, device=None):
        """
        Args:
            endpoint (str): The SOAP endpoint. A url.
            timeout (int): Timeout the connection after this number of
                seconds
            music_service (`MusicService`): The MusicService object to which
                this client belongs.
            token_store (`TokenStoreBase`): A token store instance. The token store is
                an instance of a subclass of `TokenStoreBase`
            device (SoCo): (Optional) If provided this device will be used for the
                communication; if not, the device returned by `discovery.any_soco` will
                be used
        """

        self.endpoint = endpoint
        self.timeout = timeout
        self.music_service = music_service
        self.token_store = token_store
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
            "User-Agent": (
                "Linux UPnP/1.0 Sonos/29.3-87071 (ICRU_iPhone7,1); "
                "iOS/Version 8.2 (Build 12D508)"
            ),
        }
        self._device = device or discovery.any_soco()
        self._device_id = self._device.systemProperties.GetString(
            [("VariableName", "R_TrialZPSerial")]
        )["StringValue"]
        self._household_id = self._device.deviceProperties.GetHouseholdID()[
            "CurrentHouseholdID"
        ]

    def get_soap_header(self):
        """Generate the SOAP authentication header for the related service.

        This header contains all the necessary authentication details.

        Returns:
            str: A string representation of the XML content of the SOAP
                header.
        """

        # According to the SONOS SMAPI, this header must be sent with all
        # SOAP requests. Building this is an expensive operation (though
        # occasionally necessary), so if we have a cached value, return it.
        if self._cached_soap_header is not None:
            return self._cached_soap_header
        music_service = self.music_service
        credentials_header = XML.Element("credentials", {"xmlns": self.namespace})
        device_id = XML.SubElement(credentials_header, "deviceId")
        device_id.text = self._device_id
        device_provider = XML.SubElement(credentials_header, "deviceProvider")
        device_provider.text = "Sonos"

        if music_service.auth_type in ("DeviceLink", "AppLink"):
            # Add context
            context = XML.Element("context")
            credentials_header.append(context)

            # If no existing authentication is known, we do not add 'token' and 'key'
            # elements and the only operation the service can perform is to authenticate
            if self.token_store.has_token(
                self.music_service.service_id, self._device.household_id
            ):
                login_token = XML.Element("loginToken")

                # Fill in from saved tokens
                token_pair = self.token_store.load_token_pair(
                    self.music_service.service_id, self._device.household_id
                )
                token = XML.SubElement(login_token, "token")
                key = XML.SubElement(login_token, "key")
                token.text = token_pair[0]
                key.text = token_pair[1]

                household_id = XML.SubElement(login_token, "householdId")
                household_id.text = self._household_id
                credentials_header.append(login_token)

        # TODO Implement UserID with user provided account, since we can't get the
        # accounts from the device anymore

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
            soap_action="http://www.sonos.com/Services/1.1#{0}".format(method),
            soap_header=self.get_soap_header(),
            namespace=self.namespace,
            timeout=self.timeout,
        )

        try:
            result_elt = message.call()
        except SoapFault as exc:
            if "Client.AuthTokenExpired" in exc.faultcode:
                raise MusicServiceAuthException(
                    "Authorization for {} expired, is invalid or has not yet been "
                    "completed: [{} / {} / {}]".format(
                        self.music_service.service_name,
                        exc.faultcode,
                        exc.faultstring,
                        exc.detail,
                    )
                ) from exc

            if "Client.TokenRefreshRequired" in exc.faultcode:
                log.debug(
                    "Auth token for %s expired, attempting to refresh",
                    self.music_service.service_name,
                )
                if self.music_service.auth_type not in ("DeviceLink", "AppLink"):
                    raise MusicServiceAuthException(
                        "Token-refresh not supported for music service auth type: "
                        + self.music_service.auth_type
                    ) from exc

                # Remove any cached value for the SOAP header
                self._cached_soap_header = None

                # Extract new token and key from the error message
                # <detail xmlns:ms="http://www.sonos.com/Services/1.1">
                #   <ms:RefreshAuthTokenResult>
                #     <ms:authToken>xxxxxxx</ms:authToken>
                #     <ms:privateKey>yyyyyy</ms:privateKey>
                #   </ms:RefreshAuthTokenResult>
                # </detail>
                auth_token = exc.detail.find(
                    ".//xmlns:authToken", {"xmlns": self.namespace}
                )
                if auth_token is not None:
                    auth_token = auth_token.text
                private_key = exc.detail.find(
                    ".//xmlns:privateKey", {"xmlns": self.namespace}
                )
                if private_key is not None:
                    private_key = private_key.text

                if auth_token is None or private_key is None:
                    auth_token = exc.detail.findtext(".//authToken")
                    private_key = exc.detail.findtext(".//privateKey")

                    if auth_token is None or private_key is None:
                        # If we didn't find the tokens, raise
                        raise MusicServiceAuthException(
                            "Got a TokenRefreshRequired but no new token was"
                            " found in the reply: {}".format(exc.detail)
                        ) from exc

                # Create new token pair and save it
                token_pair = (auth_token, private_key)
                self.token_store.save_token_pair(
                    self.music_service.service_id,
                    self._device.household_id,
                    token_pair,
                )

                # With the new token pair in hand, attempt a new call
                message = SoapMessage(
                    endpoint=self.endpoint,
                    method=method,
                    parameters=[] if args is None else args,
                    http_headers=self.http_headers,
                    soap_action="http://www.sonos.com/Services/1.1#{0}".format(method),
                    soap_header=self.get_soap_header(),
                    namespace=self.namespace,
                    timeout=self.timeout,
                )
                result_elt = message.call()
            else:
                log.exception(
                    "Unhandled SOAP Fault. Code: %s. Detail: %s. String: %s",
                    exc.faultcode,
                    exc.detail,
                    exc.faultstring,
                )
                raise MusicServiceException(exc.faultstring, exc.faultcode) from exc
        except XML.ParseError as parse_exc:
            raise MusicServiceAuthException(
                "Got empty response to request, likely because the service is not "
                "authenticated"
            ) from parse_exc

        # The top key in the OrderedDict will be the methodResult. Its
        # value may be None if no results were returned.
        result = list(
            parse(
                XML.tostring(result_elt),
                process_namespaces=True,
                namespaces={self.namespace: None},
            ).values()
        )[0]

        return result if result is not None else {}

    def begin_authentication(self):
        """Perform the first part of a Device or App Link authentication session

        See `begin_authentication` for details

        """
        link_device_id = None

        if self.music_service.auth_type == "DeviceLink":
            log.debug("Beginning DeviceLink authentication")
            result = self.call(
                "getDeviceLinkCode", [("householdId", self._household_id)]
            )["getDeviceLinkCodeResult"]
            if "linkDeviceId" in result:
                link_device_id = result["linkDeviceId"]
            return result["regUrl"], result["linkCode"], link_device_id
        elif self.music_service.auth_type == "AppLink":
            log.debug("Beginning AppLink authentication")
            result = self.call("getAppLink", [("householdId", self._household_id)])[
                "getAppLinkResult"
            ]
            auth_parts = result["authorizeAccount"]["deviceLink"]
            if "linkDeviceId" in auth_parts:
                link_device_id = auth_parts["linkDeviceId"]
            return auth_parts["regUrl"], auth_parts["linkCode"], link_device_id
        raise MusicServiceAuthException(
            "begin_authentication() is not implemented "
            "for auth type {}".format(self.music_service.auth_type)
        )

    def complete_authentication(self, link_code, link_device_id=None):
        """Completes a previously initiated authentication session

        See `complete_authentication` for details

        """
        log.debug("Attempting to complete DeviceLink or AppLink authentication")
        result = self.call(
            "getDeviceAuthToken",
            [
                ("householdId", self._household_id),
                ("linkCode", link_code),
                ("linkDeviceId", link_device_id or self._device_id),
            ],
        )["getDeviceAuthTokenResult"]
        token_pair = (result["authToken"], result["privateKey"])
        self.token_store.save_token_pair(
            self.music_service.service_id, self._device.household_id, token_pair
        )
        # Delete the soap header, which will force it to rebuild
        self._cached_soap_header = None


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

        Interact with TuneIn:

        >>> tunein = MusicService('TuneIn')
        >>> print (tunein)
        <MusicService 'TuneIn' at 0x10ad84e10>

        Browse an item. By default, the root item is used. An
        :class:`~soco.data_structures.SearchResult` is returned (the output of print is
        here indented for easier reading):

        >>> print(tunein.get_metadata())
        SearchResult(
          items=[
            <soco.music_services.data_structures.MSContainer object at 0x7f58b038ac10>,
            <soco.music_services.data_structures.MSContainer object at 0x7f58b038a340>,
            <soco.music_services.data_structures.MSContainer object at 0x7f58b038a6d0>,
            <soco.music_services.data_structures.MSContainer object at 0x7f58b038a310>,
            <soco.music_services.data_structures.MSContainer object at 0x7f58b038a100>,
            <soco.music_services.data_structures.MSContainer object at 0x7f58b038a910>
          ],
          search_type='browse'
        )


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

    def __init__(self, service_name, token_store=None, device=None):
        """
        Args:
            service_name (str): The name of the music service, as returned by
                `get_all_music_services_names()`, eg 'Spotify', or 'TuneIn'
            token_store (`TokenStoreBase`): A token store instance. If none is given,
                it will default to an instance of the `JsonFileTokenStore` using the
                'default' token collection. The token store must be an instance of a
                subclass of `TokenStoreBase`.
            device (SoCo): (Optional) If provided this device will be used for the
                communication, if not the device returned by `discovery.any_soco` will
                be used

        Raises:
            `MusicServiceException`
        """

        self.service_name = service_name
        if token_store:
            self.token_store = token_store
        else:
            self.token_store = JsonFileTokenStore.from_config_file()
        # Look up the data for this service
        data = self.get_data_for_name(service_name)
        self.uri = data["Uri"]
        self.secure_uri = data["SecureUri"]
        self.capabilities = data["Capabilities"]
        self.version = data["Version"]
        self.container_type = data["ContainerType"]
        self.service_id = data["Id"]
        # Auth_type can be 'Anonymous', 'UserId, 'DeviceLink' and 'AppLink'
        self.auth_type = data["Auth"]
        self.presentation_map_uri = data.get("PresentationMapUri")
        # Certain music services doesn't have a PresentationMapUri element, but
        # deliver it instead through a manifest. Get the URI for it to prepare
        # for parsing.
        self.manifest_uri = data.get("ManifestUri")
        self.manifest_data = None
        self._search_prefix_map = None
        self.service_type = data["ServiceType"]

        # Cached values used between begin_authentication and complete_authentication
        self.link_code = None
        self.link_device_id = None

        self.soap_client = MusicServiceSoapClient(
            endpoint=self.secure_uri,
            timeout=9,
            music_service=self,  # The default is 60
            token_store=self.token_store,
            device=device,
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
        # Return from cache if we have it
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

            # Get presentation map
            presentation_element = service.find(".//PresentationMap")
            if presentation_element is not None:
                result_value["PresentationMapUri"] = presentation_element.get("Uri")
                # FIXME these strings seems to have definitions of
                # custom search categories, check whether it is
                # implemented
                # FIXME is this right, or are we getting the same element twice?
                result_value["StringsUri"] = presentation_element.get("Uri")

            # Get manifest information if available
            manifest_element = service.find("Manifest")
            if manifest_element is not None:
                result_value["ManifestUri"] = manifest_element.get("Uri")

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

        # Cache this so we don't need to do it again
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

        # Certain music services delivers the presentation map not in an
        # information field of its own, but in a JSON 'manifest'. Get it
        # and extract the needed values.
        if (
            self.presentation_map_uri is None
            and self.manifest_uri is not None
            and self.manifest_data is None
        ):
            manifest = requests.get(self.manifest_uri, timeout=9)
            self.manifest_data = json.loads(manifest.content)
            pmap_element = self.manifest_data.get("presentationMap")
            if pmap_element:
                self.presentation_map_uri = pmap_element.get("uri")
        if self.presentation_map_uri is None:
            # Assume not searchable?
            return self._search_prefix_map
        log.debug("Fetching presentation map from %s", self.presentation_map_uri)
        pmap = requests.get(self.presentation_map_uri, timeout=9)
        pmap_root = XML.fromstring(pmap.content)
        # Search translations can appear in Category or CustomCategory elements
        categories = pmap_root.findall(".//SearchCategories/Category")
        if categories is None:
            return self._search_prefix_map
        for category in categories:
            # The latter part `or cat.get("id")` is added as a workaround for a
            # Navidrome + bonob setup, where the category ids are delivered on this key
            # instead of `mappedId` like for most other services. Reference:
            # https://github.com/SoCo/SoCo/pull/869#issuecomment-991353397
            self._search_prefix_map[category.get("id")] = category.get(
                "mappedId"
            ) or category.get("id")
        custom_categories = pmap_root.findall(".//SearchCategories/CustomCategory")
        for category in custom_categories:
            self._search_prefix_map[category.get("stringId")] = category.get("mappedId")
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
        return list(self._get_search_prefix_map().keys())

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

        # FIXME we no longer have accounts, so for now the serial
        # numbers is assumed to be 0. Originally it was read from
        # account.serial_numbers
        # account = self.account

        result = "soco://{}?sid={}&sn={}".format(item_id, self.service_id, 0)
        return result

    @property
    def desc(self):
        """str: The Sonos descriptor to use for this service.

        The Sonos descriptor is used as the content of the <desc> tag in
        DIDL metadata, to indicate the relevant music service id.
        """
        if self.auth_type == "DeviceLink":
            # It used to be that the second part (after the second _ was the username
            desc = "SA_RINCON{service_type}_X_#Svc{service_type}-0-Token".format(
                service_type=self.service_type
            )
        else:
            # This seems to at least be the case for TuneIn
            desc = "SA_RINCON{service_type}_".format(service_type=self.service_type)
        return desc

    def begin_authentication(self):
        """Perform the first part of a Device or App Link authentication session

        This result of this is an authentication URL, which a user needs visit and
        complete the necessary authentication on and then proceed to
        `complete_authentication`

        .. note::
           The `begin_authentication` and `complete_authentication` methods must be
           completed **on the same `MusicService` instance** unless the `link_code`
           and `link_device_id` values are passed to `complete_authentication`. These
           two values can be found as attributes on the `MusicService` instance after
           `begin_authentication` has been executed.

        Returns:
            str: Registration URL used for service linking.

        """
        log.debug(
            "Begin authentication on music service '%s' with id %i", self, id(self)
        )
        (
            reg_url,
            self.link_code,
            self.link_device_id,
        ) = self.soap_client.begin_authentication()
        return reg_url

    def complete_authentication(self, link_code=None, link_device_id=None):
        """Completes a previously initiated device or app link authentication session

        This method is the second part of a two-step authentication process, see
        `begin_authentication` for details on the first part.

        Args:
            link_code (str, optional): A link code generated from begin_authentication.
                If not provided, cached code will be used.
            link_device_id (str, optional): A link device ID generated from
                begin_authentication. If not provided, cached device ID will be used.

        """
        log.debug(
            "Complete authentication on music service '%s' with id %i", self, id(self)
        )
        _link_code = link_code or self.link_code
        if not _link_code:
            raise MusicServiceAuthException("link_code not provided or cached")
        _link_device_id = link_device_id or self.link_device_id
        self.soap_client.complete_authentication(_link_code, _link_device_id)
        self.link_code = self.link_device_id = None

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
           you should add it to the queue using its id and let the
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
