# -*- coding: utf-8 -*-
# pylint: disable=star-args, too-many-arguments


""" This module contains all the data structures for the information objects
such as music tracks or genres.

"""

# It tries to follow the class hierarchy provided by the DIDL-Lite schema
# described in the UPnP Spec, especially that for the ContentDirectory Service

# Although Sonos uses ContentDirectory v1, the document for v2 is more helpful:
# http://upnp.org/specs/av/UPnP-av-ContentDirectory-v2-Service.pdf


from __future__ import unicode_literals

import warnings
warnings.simplefilter('always', DeprecationWarning)
import textwrap

from .xml import XML

from .exceptions import CannotCreateDIDLMetadata
from .utils import really_unicode

###############################################################################
# MISC HELPER FUNCTIONS                                                       #
###############################################################################

# Move these to the XML module?


def ns_tag(ns_id, tag):
    """Return a namespace/tag item. The ns_id is translated to a full name
    space via the NS module variable.

    """
    return '{{{0}}}{1}'.format(NS[ns_id], tag)


def get_ml_item(element):
    """Return the music library item that corresponds to an elementtree
    element. The class is identified by getting the UPNP class making a lookup
    in the DIDL_CLASS_TO_CLASS module variable dictionary.

    """
    cls = _DIDL_CLASS_TO_CLASS[xml.find(ns_tag('upnp', 'class')).text]
    return cls.from_xml(xml=xml)


class Resource(object):

    """Represents a resource. Used for generating the DIDL XML messages.
    """
    # Taken from the Python Brisa project - MIT licence.
    def __init__(self, value='', protocol_info='', import_uri='', size=None,
                 duration='', bitrate=None, sample_frequency=None,
                 bits_per_sample=None, nr_audio_channels=None, resolution='',
                 color_depth=None, protection=''):
        """ Constructor for the Resource class.


            value: value of the res tag
            protocol_info (str): information about the protocol in the form
                a:b:c:d
            import_uri (str): uri locator for resource update
            size (int): size in bytes
            duration (str) : duration of the playback of the res at normal speed
                (H*:MM:SS:F* or H*:MM:SS:F0/F1)
            bitrate (int): bitrate in bytes/second
            sample_frequency (int): sample frequency in Hz
            bits_per_sample (int): bits per sample
            nr_audio_channels (int): number of audio channels
            resolution (str): resolution of the resource (X*Y)
            color_depth (int): color depth in bits
            protection (str): statement of protection type

        """
        self.value = value
        self.protocol_info = protocol_info
        self.import_uri = import_uri
        self.size = size
        self.duration = duration
        self.bitrate = bitrate
        self.sample_frequency = sample_frequency
        self.bits_per_sample = bits_per_sample
        self.nr_audio_channels = nr_audio_channels
        self.resolution = resolution
        self.color_depth = color_depth
        self.protection = protection

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        if 'protocolInfo' not in elt.attrib:
            raise Exception('Could not create Resource from Element: '
                            'protocolInfo not found (required).')

        # Required
        self.protocol_info = elt.attrib['protocolInfo']

        # Optional
        self.import_uri = elt.attrib.get('importUri', '')
        self.size = elt.attrib.get('size', None)
        self.duration = elt.attrib.get('duration', '')
        self.bitrate = elt.attrib.get('bitrate', None)
        self.sample_frequency = elt.attrib.get('sampleFrequency', None)
        self.bits_per_sample = elt.attrib.get('bitsPerSample', None)
        self.nr_audio_channels = elt.attrib.get('nrAudioChannels', None)
        self.resolution = elt.attrib.get('resolution', '')
        self.color_depth = elt.attrib.get('colorDepth', None)
        self.protection = elt.attrib.get('protection', '')
        self.value = elt.text

    @classmethod
    def from_string(cls, xml_string):
        """ Returns an instance generated from a xml string.
        """
        instance = cls()
        elt = parse_xml(xml_string)
        instance.from_element(elt)
        return instance

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        if not self.protocol_info:
            raise Exception('Could not create Element for this resource: '
                            'protocolInfo not set (required).')
        root = ElementTree.Element('res')

        # Required
        root.attrib['protocolInfo'] = self.protocol_info

        # Optional
        if self.import_uri:
            root.attrib['importUri'] = self.import_uri
        if self.size:
            root.attrib['size'] = self.size
        if self.duration:
            root.attrib['duration'] = self.duration
        if self.bitrate:
            root.attrib['bitrate'] = self.bitrate
        if self.sample_frequency:
            root.attrib['sampleFrequency'] = self.sample_frequency
        if self.bits_per_sample:
            root.attrib['bitsPerSample'] = self.bits_per_sample
        if self.nr_audio_channels:
            root.attrib['nrAudioChannels'] = self.nr_audio_channels
        if self.resolution:
            root.attrib['resolution'] = self.resolution
        if self.color_depth:
            root.attrib['colorDepth'] = self.color_depth
        if self.protection:
            root.attrib['protection'] = self.protection

        root.text = self.value

        return root


###############################################################################
# BASE OBJECTS                                                                #
###############################################################################

# a mapping which will be used to look up the relevant class from the
# DIDL item class
_DIDL_CLASS_TO_CLASS = {}


class DidlMetaClass(type):

    """Meta class for all Didl objects"""

    def __new__(mcs, name, bases, attrs):
        """
        Args:
            name: Name of the class
            bases: Base classes (tuple)
            attrs: Attributes defined for the class
        """
        new_cls = super(DidlMetaClass, mcs).__new__(mcs, name, bases, attrs)
        # Register all subclasses with the global _DIDL_CLASS_TO_CLASS mapping
        item_class = attrs.get('item_class', None)
        if item_class is not None:
            _DIDL_CLASS_TO_CLASS[item_class] = new_cls
        return new_cls


# Py2/3 compatible way of declaring the metaclass
class DidlObject(DidlMetaClass(str('DidlMetaClass'), (object,), {})):

    """Abstract base class for all content directory objects

    You should not need to instantiate this.

    :ivar item_class: According to the spec, the DIDL Lite class for the base
     item is ``object``. Since it is a abstract class and it should be
     overwritten in the sub classes
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating Didl objects from XML. The
        default value is shown below. This default value applies to most sub
        classes and the rest should overwrite it.

        .. code-block:: python

            # key: (ns, tag)
            _translation = {
                'title': ('dc', 'title'),
                'uri': ('', 'res'),
                'creator': ('dc', 'creator'),
            }

    """

    item_class = 'object'
    element = 'item'
    # key: (ns, tag)
    _translation = {
        'uri': ('', 'res'),
        'creator': ('dc', 'creator'),
    }

    def __init__(self, title, parent_id, item_id, **kwargs):
        r"""Initialize the DidlObject from parameter arguments.

        :param title: The title for the item
        :param parent_id: The parent ID for the item
        :param item_id: The ID for the item
        :param \*\*kwargs: Extra information items to form the Didl
            item from. Valid keys are ``album``, ``album_art_uri``,
            ``creator`` and ``original_track_number``.
            ``original_track_number`` is an int, all other values are
            unicode objects.

        """
        # All didl objects *must* have a title, a parent_id and an item_id
        # so we specify these as required args in the constructor signature
        # to ensure that we get them. Other didl object properties are
        # optional, so can be passed as kwargs.
        # The content of _translation is adapted from the list in table C at
        # http://upnp.org/specs/av/UPnP-av-ContentDirectory-v2-Service.pdf
        # Not all properties referred to there are catered for, since Sonos
        # does not use some of them.

        # pylint: disable=super-on-old-class
        super(DidlObject, self).__init__()
        self.title = title
        self.parent_id = parent_id
        self.item_id = item_id

        for key, value in kwargs.items():
            # For each attribute, check to see if this class allows it
            if key not in self._translation:
                raise ValueError(
                    'The key \'{0}\' is not allowed as an argument. Only '
                    'parent_id, item_id, title, and these keys are allowed:'
                    ' {1}'.format(key, str(self._translation.keys())))
            # It is an allowed attribute. Set it as an attribute on self, so
            # that it can be accessed as Classname.attribute in the normal
            # way.
            setattr(self, key, value)

    @classmethod
    def from_element(cls, element):
        """An alternative constructor to create an instance of this class
        from an elementtree xml element.

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (NS['']) element. Inside
            the item element should be the (namespace, tag_name) elements
            in the dictionary-key-to-xml-tag-and-namespace-translation
            described in the class docstring.

        """
        # Check we have the right sort of element
        if not element.tag.endswith(cls.element):
            raise CannotCreateDIDLMetadata("Wrong element. Expected {0},"
            " got {1}".format(cls.element, element.tag))
        content = {}
        # parent_id and item_id are stored as attibutes on the element
        item_id = element.get('id', None)
        if item_id is None:
            raise CannotCreateDIDLMetadata("Missing id attribute")
        parent_id = element.get('parentID', None)
        if parent_id is None:
            raise CannotCreateDIDLMetadata("Missing parentID attribute")
        # There must be a title, and it must be the first sub-element
        title_elt = element[0]
        if title_elt.tag != (ns_tag('dc', 'title')):
            raise CannotCreateDIDLMetadata("Missing or misplaced title element")
        title = title_elt.text
        # Get values of the elements listed in _translation and add them to
        # the content dict
        for key, value in cls._translation.items():
            result = element.find('{0}'.format(ns_tag(*value)))
            if result is not None and result.text is not None:
                # We store info as unicode internally.
                content[key] = really_unicode(result.text)

        # Convert type for original track number
        if content.get('original_track_number') is not None:
            content['original_track_number'] = \
                int(content['original_track_number'])

        # Now pass the content dict we have just built to the main
        # constructor, as kwargs, to create the object
        return cls(title=title, parent_id=parent_id, item_id=item_id,
            **content)

    @classmethod
    def from_dict(cls, content):
        """An alternative constructor to create instance from a dict with
        parameters. Equivalent to DidlObject(**content).

        :param content: Dict with information for the music library item.
            Required and valid arguments are the same as for the
            ``__init__`` method.

        """
        # Do we really need this constructor? Could use DidlObject(**content)
        # instead.
        return cls(**content)

    def __eq__(self, playable_item):
        """Return the equals comparison result to another ``playable_item``."""
        if not isinstance(playable_item, DidlObject):
            return False
        return self.to_dict == playable_item.to_dict

    def __ne__(self, playable_item):
        """Return the not equals comparison result to another ``playable_item``
        """
        if not isinstance(playable_item, DidlObject):
            return True
        return self.to_dict != playable_item.to_dict

    def __repr__(self):
        """Return the repr value for the item.

        The repr is on the form::

          <class_name 'middle_part[0:40]' at id_in_hex>

        where middle_part is either the title item in content, if it is set,
        or ``str(content)``. The output is also cleared of non-ascii
        characters.

        """
        # 40 originates from terminal width (78) - (15) for address part and
        # (19) for the longest class name and a little left for buffer
        if self.title is not None:
            middle = self.title.encode('ascii', 'replace')[0:40]
        else:
            middle = str(self.to_dict).encode('ascii', 'replace')[0:40]
        return '<{0} \'{1}\' at {2}>'.format(self.__class__.__name__,
                                             middle,
                                             hex(id(self)))

    def __str__(self):
        """Return the str value for the item::

         <class_name 'middle_part[0:40]' at id_in_hex>

        where middle_part is either the title item in content, if it is set, or
        ``str(content)``. The output is also cleared of non-ascii characters.

        """
        return self.__repr__()

    @property
    def to_dict(self):
        """Get the dict representation of the instance."""

        content = {}
        # Get the value of each attribute listed in _translation, and add it
        # to the content dict
        for key in self._translation:
            if hasattr(self, key):
                content[key] = getattr(self, key)
        # also add parent_id, item_id and title because they are not listed in
        # _translation
        content['parent_id'] = self.parent_id
        content['item_id'] = self.item_id
        content['title'] = self.title
        return content

    @property
    def to_element(self):
        """Produce the DIDL metadata XML.

        This method uses the :py:attr:`~.DidlObject.item_id`
        attribute (and via that the :py:attr:`~.DidlObject.uri`
        attribute), the :py:attr:`~.DidlObject.item_class` attribute
        and the :py:attr:`~.DidlObject.title`  attribute. The
        metadata will be of the form:

        .. code :: xml

         <DIDL-Lite ..NS_INFO..>
           <item id="...self.item_id..."
             parentID="...cls.parent_id..." restricted="true">
             <dc:title>...self.title...</dc:title>
             <upnp:class>...self.item_class...</upnp:class>
             <desc id="cdudn"
               nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">
               RINCON_AssociatedZPUDN
             </desc>
           </item>
         </DIDL-Lite>

        """
        # for prefix, uri in NS.items():
        #           XML.register_namespace(prefix, uri)
        # Insert the parent ID and item ID as attributes on the Item element
        elt_attrib = {
            'xmlns':"urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
            'xmlns:dc':"http://purl.org/dc/elements/1.1/",
            'xmlns:upnp':"urn:schemas-upnp-org:metadata-1-0/upnp/",
            'parentID': self.parent_id,
            'restricted': 'true',
            'id': self.item_id
        }
        elt = XML.Element(self.element, elt_attrib)
        # Add the title, which must always come first, according to the spec
        title = self.title
        XML.SubElement(elt, 'dc:title').text = self.title
        # Add in the item class
        XML.SubElement(elt, 'upnp:class').text = self.item_class
        # Add the rest of the metadata attributes (i.e all those listed in
        # _translation) as sub-elements of the item element
        for key, value in self._translation.items():
            if hasattr(self, key):
                tag = "%s:%s"%value if value[0] else "%s"%value[1]
                XML.SubElement(elt, tag).text = ("%s"%getattr(self, key))
        # Add the desc element
        desc_attrib = {'id': 'cdudn', 'nameSpace':
                       'urn:schemas-rinconnetworks-com:metadata-1-0/'}
        desc = XML.SubElement(elt, 'desc', desc_attrib)
        desc.text = 'RINCON_AssociatedZPUDN'
        return elt


###############################################################################
# OBJECT.ITEM HIERARCHY                                                       #
###############################################################################

class DidlItem(DidlObject):

    """A basic content directory item"""

    item_class = 'object.item'
    # _translation = DidlObject._translation.update({ ...})
     # does not work, but doing it in two steps does
    _translation = DidlObject._translation.copy()
    _translation.update(
        {
        'stream_content': ('r', 'streamContent'),
        'radio_show': ('r', 'radioShowMd'),
        'album_art_uri': ('upnp', 'albumArtURI'),
        }
    )


class DidlAudioItem(DidlItem):

    """An audio item"""

    item_class = 'object.item.audioitem'
    _translation = DidlItem._translation.copy()
    _translation.update(
        {
        'genre': ('upnp', 'genre'),
        'description': ('dc', 'description'),
        }
    )


class DidlMusicTrack(DidlAudioItem):

    """Class that represents a music library track.

    :ivar parent_id: The parent ID for the DidlMusicTrack is 'A:TRACKS'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlMusicTrack from XML. The
        value is shown below

        .. code-block:: python

            # key: (ns, tag)
            _translation = {
                'title': ('dc', 'title'),
                'creator': ('dc', 'creator'),
                'album': ('upnp', 'album'),
                'album_art_uri': ('upnp', 'albumArtURI'),
                'uri': ('', 'res'),
                'original_track_number': ('upnp', 'originalTrackNumber')
            }

    """

    item_class = 'object.item.audioItem.musicTrack'
    # name: (ns, tag)
    _translation = DidlAudioItem._translation.copy()
    _translation.update(
        {
            'artist': ('upnp', 'artist'),
            'album': ('upnp', 'album'),
            'original_track_number': ('upnp', 'originalTrackNumber'),
            'contributor': ('dc', 'contributor'),
        }
    )


class DidlAudioBroadcast(DidlAudioItem):

    """Class that represents an audio broadcast."""
    item_class = 'object.item.audioItem.audioBroadcast'


###############################################################################
# OBJECT.CONTAINER HIERARCHY                                                  #
###############################################################################

class DidlContainer(DidlObject):

    """Class that represents a music library container.

    :ivar item_class: The item_class for the DidlContainer is
        'object.container'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlContainer from XML is
        inherited from :py:class:`.DidlObject`.

    """

    item_class = 'object.container'
    element = 'container'


class DidlAlbum(DidlContainer):

    """A content directory album"""

    item_class = 'object.container.album'
    # name: (ns, tag)
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            'description': ('dc', 'description'),
            'publisher': ('dc', 'publisher'),
            'contributor': ('dc', 'contributor'),
        }
    )


class DidlMusicAlbum(DidlAlbum):

    """Class that represents a music library album.

    :ivar item_class: The item_class for DidlMusicTrack is
        'object.container.album.musicAlbum'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlAlbum from XML. The value is
        shown below

        .. code-block :: python

            # key: (ns, tag)
            _translation = {
                'title': ('dc', 'title'),
                'creator': ('dc', 'creator'),
                'album_art_uri': ('upnp', 'albumArtURI'),
                'uri': ('', 'res')
            }

    """

    item_class = 'object.container.album.musicAlbum'
    # name: (ns, tag)
    _translation = DidlAudioItem._translation.copy()
    _translation.update(
        {
            'artist': ('upnp', 'artist'),
            'genre': ('upnp', 'genre'),
            'album_art_uri': ('upnp', 'albumArtURI'),
        }
    )


class DidlPerson(DidlContainer):

    """A content directory class representing a person"""
    item_class = 'object.container.person'


class DidlComposer(DidlPerson):

    """Class that represents a music library composer.

    :ivar item_class: The item_class for DidlComposer is
        'object.container.person.composer'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlComposer from XML is
        inherited from :py:class:`.DidlObject`.

    """

    item_class = 'object.container.person.composer'


class DidlMusicArtist(DidlPerson):

    """Class that represents a music library artist.

    :ivar item_class: The item_class for DidlMusicArtist is
        'object.container.person.musicArtist'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlMusicArtist from XML is
        inherited from :py:class:`.DidlObject`.
    """

    item_class = 'object.container.person.musicArtist'
    # name: (ns, tag)
    _translation = DidlPerson._translation.copy()
    _translation.update(
        {
            'genre': ('upnp', 'genre'),
        }
    )


class DidlAlbumList(DidlContainer):

    """Class that represents a music library album list.

    :ivar item_class: The item_class for DidlAlbumList is
        'object.container.albumlist'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlAlbumList from XML is
        inherited from :py:class:`.DidlObject`.

    """

    item_class = 'object.container.albumlist'


class DidlPlaylistContainer(DidlContainer):

    """Class that represents a music library play list.

    :ivar item_class: The item_class for the DidlPlaylistContainer is
        'object.container.playlistContainer'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlPlaylistContainer from XML is
        inherited from :py:class:`.DidlObject`.

    """

    item_class = 'object.container.playlistContainer'
    # name: (ns, tag)
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            'artist': ('upnp', 'artist'),
            'genre': ('upnp', 'genre'),
            'description': ('dc', 'description'),
            'contributor': ('dc', 'contributor'),
        }
    )


class DidlSameArtist(DidlPlaylistContainer):

    """Class that represents all by the artist.

    This type is returned by browsing an artist or a composer

    :ivar item_class: The item_class for DidlSameArtist is
        'object.container.playlistContainer.sameArtist'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlSameArtist from XML is
        inherited from :py:class:`.DidlObject`.

    """

    item_class = 'object.container.playlistContainer.sameArtist'


class DidlGenre(DidlContainer):

    """A content directory class representing a general genre"""
    item_class = 'object.container.genre'
    # name: (ns, tag)
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            'genre': ('upnp', 'genre'),
            'description': ('dc', 'description'),
        }
    )


class DidlMusicGenre(DidlGenre):

    """Class that represents a music genre.

    :ivar item_class: The item class for the DidlGenre is
        'object.container.genre.musicGenre'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlGenre from XML is inherited
        from :py:class:`.DidlObject`.

    """

    item_class = 'object.container.genre.musicGenre'


class DidlShare(DidlContainer):
    # Is this really needed?

    """Class that represents a music library share.

    :ivar item_class: The item_class for the DidlShare is 'object.container'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlShare from XML is inherited
        from :py:class:`.DidlObject`."""

    pass


###############################################################################
# SPECIAL LISTS                                                               #
###############################################################################

class ListOfMusicInfoItems(list):

    """Abstract container class for a list of music information items"""

    def __init__(self, items, number_returned, total_matches, update_id):
        super(ListOfMusicInfoItems, self).__init__(items)
        self._metadata = {
            'item_list': list(items),
            'number_returned': number_returned,
            'total_matches': total_matches,
            'update_id': update_id,
        }

    def __getitem__(self, key):
        """Legacy get metadata by string key or list item(s) by index

        DEPRECATION: This overriding form of __getitem__ will be removed in
        the 3rd release after 0.8. The metadata can be fetched via the named
        attributes
        """
        if key in self._metadata:
            if key == 'item_list':
                message = """
                Calling [\'item_list\'] on search results to obtain the objects
                is no longer necessary, since the object returned from searches
                now is a list. This deprecated way of getting the items will
                be removed from the third release after 0.8."""
            else:
                message = """
                Getting metadata items by indexing the search result like a
                dictionary [\'{0}\'] is deprecated. Please use the named
                attribute {1}.{0} instead. The deprecated way of retrieving the
                metadata will be removed from the third release after
                0.8""".format(key, self.__class__.__name__)
            message = textwrap.dedent(message).replace('\n', ' ').lstrip()
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return self._metadata[key]
        else:
            return super(ListOfMusicInfoItems, self).__getitem__(key)

    @property
    def number_returned(self):
        """The number of returned matches"""
        return self._metadata['number_returned']

    @property
    def total_matches(self):
        """The number of total matches"""
        return self._metadata['total_matches']

    @property
    def update_id(self):
        """The update ID"""
        return self._metadata['update_id']


class SearchResult(ListOfMusicInfoItems):

    """Container class that represents a search or browse result

    (browse is just a special case of search)
    """

    def __init__(self, items, search_type, number_returned,
                 total_matches, update_id):
        super(SearchResult, self).__init__(
            items, number_returned, total_matches, update_id
        )
        self._metadata['search_type'] = search_type

    def __repr__(self):
        return '{0}(items={1}, search_type=\'{2}\')'.format(
            self.__class__.__name__,
            super(SearchResult, self).__repr__(),
            self.search_type)

    @property
    def search_type(self):
        """The search type"""
        return self._metadata['search_type']


class Queue(ListOfMusicInfoItems):

    """Container class that represents a queue"""

    def __init__(self, items, number_returned, total_matches, update_id):
        super(Queue, self).__init__(
            items, number_returned, total_matches, update_id
        )

    def __repr__(self):
        return '{0}(items={1})'.format(
            self.__class__.__name__,
            super(Queue, self).__repr__(),
        )


###############################################################################
# CONSTANTS                                                                   #
###############################################################################

NS = {
    'dc': 'http://purl.org/dc/elements/1.1/',
    'upnp': 'urn:schemas-upnp-org:metadata-1-0/upnp/',
    '': 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/',
    'ms': 'http://www.sonos.com/Services/1.1',
    'r': 'urn:schemas-rinconnetworks-com:metadata-1-0/'
}

for prefix, uri in NS.items():
    XML.register_namespace(prefix, uri)