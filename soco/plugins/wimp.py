# pylint: disable=star-args,too-many-locals

"""Plugin for the Wimp music service (Service ID 20)"""


import locale
import socket

import requests

from ..exceptions import SoCoUPnPException, UnknownXMLStructure
from ..ms_data_structures import (
    MSAlbum,
    MSAlbumList,
    MSArtist,
    MSArtistTracklist,
    MSCollection,
    MSFavorites,
    MSPlaylist,
    MSTrack,
    get_ms_item,
)
from ..services import MusicServices
from ..utils import really_utf8
from ..xml import XML
from .__init__ import SoCoPlugin

__all__ = ["Wimp"]


def _post(url, headers, body, retries=3, timeout=3.0):
    """Try 3 times to request the content.

    :param headers: The HTTP headers
    :type headers: dict
    :param body: The body of the HTTP post
    :type body: str
    :param retries: The number of times to retry before giving up
    :type retries: int
    :param timeout: The time to wait for the post to complete, before timing
        out
    :type timeout: float
    """
    retry = 0
    out = None
    while out is None:
        try:
            out = requests.post(url, headers=headers, data=body, timeout=timeout)
        # Due to a bug in requests, the post command will sometimes fail to
        # properly wrap a socket.timeout exception in requests own exception.
        # See https://github.com/kennethreitz/requests/issues/2045
        # Until this is fixed, we need to catch both types of exceptions
        except (requests.exceptions.Timeout, socket.timeout) as exception:
            retry += 1
            if retry == retries:
                # pylint: disable=maybe-no-member
                raise requests.exceptions.Timeout(exception.message)
    return out


def _ns_tag(ns_id, tag):
    """Return a namespace/tag item. The ns_id is translated to a full name
    space via the NS module variable.

    :param ns_id: The name space ID. Translated to a namespace via the module
        variable NS
    :type ns_id: str
    :param tag: The tag
    :type str: str
    """
    return "{{{}}}{}".format(NS[ns_id], tag)


def _get_header(soap_action):
    """Return the HTTP for SOAP Action.

    :param soap_action: The soap action to include in the header. Can be either
        'search' or 'get_metadata'
    :type soap_action: str
    """
    # This way of setting accepted language is obviously flawed, in that it
    # depends on the locale settings of the system. However, I'm unsure if
    # they are actually used. The character coding is set elsewhere and I think
    # the available music in each country is bound to the account.
    language, _ = locale.getdefaultlocale()
    if language is None:
        language = ""
    else:
        language = language.replace("_", "-") + ", "

    header = {
        "CONNECTION": "close",
        "ACCEPT-ENCODING": "gzip",
        "ACCEPT-LANGUAGE": "{}en-US;q=0.9".format(language),
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPACTION": SOAP_ACTION[soap_action],
    }
    return header


class Wimp(SoCoPlugin):

    """Class that implements a Wimp plugin.

    Note:
        There is an (apparent) in-consistency in the use of one data
        type from the Wimp service. When searching for playlists, the XML
        returned by the Wimp server indicates, that the type is an 'album
        list', and it thus suggest, that this type is used for a list of
        tracks (as expected for a playlist), and this data type is reported
        to be playable. However, when browsing the music tree, the Wimp
        server will return items of 'album list' type, but in this case it
        is used for a list of albums and it is not playable. This plugin
        maintains this (apparent) in-consistency to stick as close to the
        reported data as possible, so search for playlists returns
        MSAlbumList that are playable and while browsing the content tree
        the MSAlbumList items returned to you are not playable.


    Note:
       Wimp in some cases lists tracks that are not available. In these
       cases, while it will correctly report these tracks as not being
       playable, the containing data structure like e.g. the album they are
       on may report that they are playable. Trying to add one of these to
       the queue will return a SoCoUPnPException with error code '802'.

    """

    def __init__(self, soco, username, retries=3, timeout=3.0):
        """Initialize the plugin.

        :param soco: The soco instance to retrieve the session ID for the music
            service
        :type: :py:class:`soco.SoCo`
        :param username: The username for the music service
        :type username: str
        :param retries: The number of times to retry before giving up
        :type retries: int
        :param timeout: The time to wait for the post to complete, before
            timing out. The Wimp server seems either slow to respond or to
            make the queries internally, so the timeout should probably not be
            shorter than 3 seconds.
        :type timeout: float

        Note:

            If you are using a phone number as the username and are
            experiencing problems connecting, then try to prepend the area
            code (no + or 00). I.e. if your phone number is 12345678 and you
            are from denmark, then use 4512345678. This must be set up the
            same way in the Sonos device.  For details see `here
            <https://wimp.zendesk.com/hc/da/articles/204311810-Hvorfor-kan
            -jeg-ikke-logge-p%C3%A5-WiMP-med-min-Sonos-n%C3%A5r-jeg-har-et
            -gyldigt-abonnement->`_ (In Danish)
        """
        super().__init__(soco)

        # Instantiate variables
        self._url = "http://client.wimpmusic.com/sonos/services/Sonos"
        self._serial_number = soco.get_speaker_info()["serial_number"]
        self._username = username
        self._service_id = 20
        self._http_vars = {"retries": retries, "timeout": timeout}

        # Get a session id for the searches
        self._music_services = MusicServices(soco)
        response = self._music_services.GetSessionId(
            [("ServiceId", 20), ("Username", username)]
        )
        self._session_id = response["SessionId"]

    @property
    def name(self):
        """Return the human read-able name for the plugin"""
        return "Wimp Plugin for {}".format(self._username)

    @property
    def username(self):
        """Return the username."""
        return self._username

    @property
    def service_id(self):
        """Return the service id."""
        return self._service_id

    @property
    def description(self):
        """Return the music service description for the DIDL metadata on the
        form ``'SA_RINCON5127_...self.username...'``"""
        return "SA_RINCON5127_{}".format(self._username)

    def get_tracks(self, search, start=0, max_items=100):
        """Search for tracks.

        See get_music_service_information for details on the arguments
        """
        return self.get_music_service_information("tracks", search, start, max_items)

    def get_albums(self, search, start=0, max_items=100):
        """Search for albums.

        See get_music_service_information for details on the arguments
        """
        return self.get_music_service_information("albums", search, start, max_items)

    def get_artists(self, search, start=0, max_items=100):
        """Search for artists.

        See get_music_service_information for details on the arguments
        """
        return self.get_music_service_information("artists", search, start, max_items)

    def get_playlists(self, search, start=0, max_items=100):
        """Search for playlists.

        See get_music_service_information for details on the arguments.

        Note:

            Un-intuitively this method returns MSAlbumList items. See
            note in class doc string for details.
        """
        return self.get_music_service_information("playlists", search, start, max_items)

    def get_music_service_information(
        self, search_type, search, start=0, max_items=100
    ):
        """Search for music service information items.

        :param search_type: The type of search to perform, possible values are:
            'artists', 'albums', 'tracks' and 'playlists'
        :type search_type: str
        :param search: The search string to use
        :type search: str
        :param start: The starting index of the returned items
        :type start: int
        :param max_items: The maximum number of returned items
        :type max_items: int

        Note:
            Un-intuitively the playlist search returns MSAlbumList
            items. See note in class doc string for details.
        """
        # Check input
        if search_type not in ["artists", "albums", "tracks", "playlists"]:
            message = "The requested search {} is not valid".format(search_type)
            raise ValueError(message)
        # Transform search: tracks -> tracksearch
        search_type = "{}earch".format(search_type)
        parent_id = SEARCH_PREFIX.format(search_type=search_type, search=search)

        # Perform search
        body = self._search_body(search_type, search, start, max_items)
        headers = _get_header("search")
        response = _post(self._url, headers, body, **self._http_vars)
        self._check_for_errors(response)
        result_dom = XML.fromstring(response.text.encode("utf-8"))

        # Parse results
        search_result = result_dom.find(".//" + _ns_tag("", "searchResult"))
        out = {"item_list": []}
        for element in ["index", "count", "total"]:
            out[element] = search_result.findtext(_ns_tag("", element))

        if search_type == "tracksearch":
            item_name = "mediaMetadata"
        else:
            item_name = "mediaCollection"
        for element in search_result.findall(_ns_tag("", item_name)):
            out["item_list"].append(get_ms_item(element, self, parent_id))

        return out

    def browse(self, ms_item=None):
        """Return the sub-elements of item or of the root if item is None

        :param item: Instance of sub-class of
            :py:class:`soco.data_structures.MusicServiceItem`. This object must
            have item_id, service_id and extended_id properties

        Note:
            Browsing a MSTrack item will return itself.

        Note:
            This plugin cannot yet set the parent ID of the results
            correctly when browsing
            :py:class:`soco.data_structures.MSFavorites` and
            :py:class:`soco.data_structures.MSCollection` elements.

        """
        # Check for correct service
        if ms_item is not None and ms_item.service_id != self._service_id:
            message = "This music service item is not for this service"
            raise ValueError(message)

        # Form HTTP body and set parent_id
        if ms_item:
            body = self._browse_body(ms_item.item_id)
            parent_id = ms_item.extended_id
            if parent_id is None:
                parent_id = ""
        else:
            body = self._browse_body("root")
            parent_id = "0"

        # Get HTTP header and post
        headers = _get_header("get_metadata")
        response = _post(self._url, headers, body, **self._http_vars)

        # Check for errors and get XML
        self._check_for_errors(response)
        result_dom = XML.fromstring(really_utf8(response.text))
        # Find the getMetadataResult item ...
        xpath_search = ".//" + _ns_tag("", "getMetadataResult")
        metadata_result = list(result_dom.findall(xpath_search))
        # ... and make sure there is exactly 1
        if len(metadata_result) != 1:
            raise UnknownXMLStructure(
                "The results XML has more than 1 'getMetadataResult'. This "
                "is unexpected and parsing will dis-continue."
            )
        metadata_result = metadata_result[0]

        # Browse the children of metadata result
        out = {"item_list": []}
        for element in ["index", "count", "total"]:
            out[element] = metadata_result.findtext(_ns_tag("", element))
        for result in metadata_result:
            if result.tag in [
                _ns_tag("", "mediaCollection"),
                _ns_tag("", "mediaMetadata"),
            ]:
                out["item_list"].append(get_ms_item(result, self, parent_id))
        return out

    @staticmethod
    def id_to_extended_id(item_id, item_class):
        """Return the extended ID from an ID.

        :param item_id: The ID of the music library item
        :type item_id: str
        :param cls: The class of the music service item
        :type cls: Sub-class of
            :py:class:`soco.data_structures.MusicServiceItem`

        The extended id can be something like 00030020trackid_22757082
        where the id is just trackid_22757082. For classes where the prefix is
        not known returns None.
        """
        out = ID_PREFIX[item_class]
        if out:
            out += item_id
        return out

    @staticmethod
    def form_uri(item_content, item_class):
        """Form the URI for a music service element.

        :param item_content: The content dict of the item
        :type item_content: dict
        :param item_class: The class of the item
        :type item_class: Sub-class of
            :py:class:`soco.data_structures.MusicServiceItem`
        """
        extension = None
        if "mime_type" in item_content:
            extension = MIME_TYPE_TO_EXTENSION[item_content["mime_type"]]
        out = URIS.get(item_class)
        if out:
            out = out.format(extension=extension, **item_content)
        return out

    def _search_body(self, search_type, search_term, start, max_items):
        """Return the search XML body.

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
        XML.SubElement(xml, "s:Body")
        item_attrib = {"xmlns": "http://www.sonos.com/Services/1.1"}
        search = XML.SubElement(xml[1], "search", item_attrib)
        XML.SubElement(search, "id").text = search_type
        XML.SubElement(search, "term").text = search_term
        XML.SubElement(search, "index").text = str(start)
        XML.SubElement(search, "count").text = str(max_items)

        return XML.tostring(xml)

    def _browse_body(self, search_id):
        """Return the browse XML body.

        The XML is formed by adding, to the envelope of the XML returned by
        ``self._base_body``, the following ``Body`` part:

        .. code :: xml

         <s:Body>
           <getMetadata xmlns="http://www.sonos.com/Services/1.1">
             <id>root</id>
             <index>0</index>
             <count>100</count>
           </getMetadata>
         </s:Body>

        .. note:: The XML contains index and count, but the service does not
        seem to respect them, so therefore they have not been included as
        arguments.
        """
        xml = self._base_body()

        # Add the Body part
        XML.SubElement(xml, "s:Body")
        item_attrib = {"xmlns": "http://www.sonos.com/Services/1.1"}
        search = XML.SubElement(xml[1], "getMetadata", item_attrib)
        XML.SubElement(search, "id").text = search_id
        # Investigate this index, count stuff more
        XML.SubElement(search, "index").text = "0"
        XML.SubElement(search, "count").text = "100"

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
        item_attrib = {
            "xmlns:s": "http://schemas.xmlsoap.org/soap/envelope/",
        }
        xml = XML.Element("s:Envelope", item_attrib)

        # Add the Header part
        XML.SubElement(xml, "s:Header")
        item_attrib = {"xmlns": "http://www.sonos.com/Services/1.1"}
        credentials = XML.SubElement(xml[0], "credentials", item_attrib)
        XML.SubElement(credentials, "sessionId").text = self._session_id
        XML.SubElement(credentials, "deviceId").text = self._serial_number
        XML.SubElement(credentials, "deviceProvider").text = "Sonos"

        return xml

    def _check_for_errors(self, response):
        """Check a response for errors.

        :param response: the response from requests.post()
        """
        if response.status_code != 200:
            xml_error = really_utf8(response.text)
            error_dom = XML.fromstring(xml_error)
            fault = error_dom.find(".//" + _ns_tag("s", "Fault"))
            error_description = fault.find("faultstring").text
            error_code = EXCEPTION_STR_TO_CODE[error_description]
            message = "UPnP Error {} received: {} from {}".format(
                error_code, error_description, self._url
            )
            raise SoCoUPnPException(
                message=message,
                error_code=error_code,
                error_description=error_description,
                error_xml=really_utf8(response.text),
            )


SOAP_ACTION = {
    "get_metadata": '"http://www.sonos.com/Services/1.1#getMetadata"',
    "search": '"http://www.sonos.com/Services/1.1#search"',
}
# Note UPnP exception 802 while trying to add a Wimp track indicates that these
# are tracks that not available in Wimp. Do something with that.
EXCEPTION_STR_TO_CODE = {"unknown": 20000, "ItemNotFound": 20001}
SEARCH_PREFIX = "00020064{search_type}:{search}"
ID_PREFIX = {
    MSTrack: "00030020",
    MSAlbum: "0004002c",
    MSArtist: "10050024",
    MSAlbumList: "000d006c",
    MSPlaylist: "0006006c",
    MSArtistTracklist: "100f006c",
    MSFavorites: None,  # This one is unknown
    MSCollection: None,  # This one is unknown
}
MIME_TYPE_TO_EXTENSION = {"audio/aac": "mp4"}
URIS = {
    MSTrack: "x-sonos-http:{item_id}.{extension}?sid={service_id}&flags=32",
    MSAlbum: "x-rincon-cpcontainer:{extended_id}",
    MSAlbumList: "x-rincon-cpcontainer:{extended_id}",
    MSPlaylist: "x-rincon-cpcontainer:{extended_id}",
    MSArtistTracklist: "x-rincon-cpcontainer:{extended_id}",
}
NS = {
    "s": "http://schemas.xmlsoap.org/soap/envelope/",
    "": "http://www.sonos.com/Services/1.1",
}
