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


def get_ml_item(xml):
    """Return the music library item that corresponds to xml. The class is
    identified by getting the UPNP class making a lookup in the
    DIDL_CLASS_TO_CLASS module variable dictionary.

    """
    cls = DIDL_CLASS_TO_CLASS[xml.find(ns_tag('upnp', 'class')).text]
    return cls.from_xml(xml=xml)


###############################################################################
# BASE OBJECTS                                                                #
###############################################################################

# a mapping which will be used to look up the relevant class from the
# DIDL item class
DIDL_CLASS_TO_CLASS = {}


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
        # Register all subclasses with the global DIDL_CLASS_TO_CLASS mapping
        item_class = attrs.get('item_class', None)
        if item_class is not None:
            DIDL_CLASS_TO_CLASS[item_class] = new_cls
        return new_cls


# Py2/3 compatible way of declaring the metaclass
class DidlObject(DidlMetaClass(str('DidlMetaClass'), (object,), {})):

    """Abstract base class for all content directory objects

    You should not need to instantiate this

    :ivar item_class: According to the spec, the DIDL Lite class for the music
     library item is ``object``, since it is a abstract class and it should be
     overwritten in the sub classes
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MusicLibraryItems from XML. The
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
    # key: (ns, tag)
    _translation = {
        'title': ('dc', 'title'),
        'uri': ('', 'res'),
        'creator': ('dc', 'creator'),
    }

    def __init__(self, uri, title, parent_id, item_id, **kwargs):
        r"""Initialize the DidlObject from parameter arguments.

        :param uri: The URI for the item
        :param title: The title for the item
        :param parent_id: The parent ID for the item
        :param item_id: The ID for the item
        :param \*\*kwargs: Extra information items to form the music library
            item from. Valid keys are ``album``, ``album_art_uri``,
            ``creator`` and ``original_track_number``.
            ``original_track_number`` is an int, all other values are
            unicode objects.

        """
        # pylint: disable=super-on-old-class
        super(DidlObject, self).__init__()
        self.content = {}
        # Parse the input arguments
        arguments = {'uri': uri, 'title': title, 'parent_id': parent_id,
                     'item_id': item_id}
        arguments.update(kwargs)
        for key, value in arguments.items():
            if key in self._translation or key == 'parent_id' \
                    or key == 'item_id':
                if value is not None:
                    self.content[key] = value
            else:
                raise ValueError(
                    'The key \'{0}\' is not allowed as an argument. Only '
                    'these keys are allowed: {1}'.
                    format(key, str(self._translation.keys())))

    @classmethod
    def from_xml(cls, xml):
        """An alternative constructor to create an instance of this class
        from xml.

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (NS['']) element. Inside
            the item element should be the (namespace, tag_name) elements
            in the dictionary-key-to-xml-tag-and-namespace-translation
            described in the class docstring.

        """
        content = {}
        # Get values from _translation
        for key, value in cls._translation.items():
            result = xml.find(ns_tag(*value))
            if result is None:
                content[key] = None
            elif result.text is None:
                content[key] = None
            else:
                # The xml objects should contain utf-8 internally
                content[key] = really_unicode(result.text)

        # Extract the item ID
        content['item_id'] = xml.get('id')

        # Extract the parent ID
        content['parent_id'] = xml.get('parentID')

        # Convert type for original track number
        if content.get('original_track_number') is not None:
            content['original_track_number'] = \
                int(content['original_track_number'])
        return cls.from_dict(content)

    @classmethod
    def from_dict(cls, content):
        """An alternative constructor to create instance from a dict with
        parameters.

        :param content: Dict with information for the music library item.
            Required and valid arguments are the same as for the
            ``__init__`` method.

        """
        # Make a copy since this method will modify the input dict
        content_in = content.copy()
        args = [content_in.pop(arg) for arg in ['uri', 'title',
                                                'parent_id', 'item_id']]
        return cls(*args, **content_in)

    def __eq__(self, playable_item):
        """Return the equals comparison result to another ``playable_item``."""
        if not isinstance(playable_item, DidlObject):
            return False
        return self.content == playable_item.content

    def __ne__(self, playable_item):
        """Return the not equals comparison result to another ``playable_item``
        """
        if not isinstance(playable_item, DidlObject):
            return True
        return self.content != playable_item.content

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
        if self.content.get('title') is not None:
            middle = self.content['title'].encode('ascii', 'replace')[0:40]
        else:
            middle = str(self.content).encode('ascii', 'replace')[0:40]
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
        return self.content.copy()

    @property
    def item_id(self):  # pylint: disable=C0103
        """Return the id.
        """
        return self.content['item_id']

    @item_id.setter
    def item_id(self, item_id):  # pylint: disable=C0111
        self.content['item_id'] = item_id

    @property
    def title(self):
        """Get and set the title as an unicode object."""
        return self.content['title']

    @title.setter
    def title(self, title):  # pylint: disable=C0111
        self.content['title'] = title

    @property
    def uri(self):
        """Get and set the URI as an unicode object."""
        return self.content['uri']

    @uri.setter
    def uri(self, uri):  # pylint: disable=C0111
        self.content['uri'] = uri

    @property
    def parent_id(self):
        """Get and set the parent ID."""
        return self.content['parent_id']

    @parent_id.setter
    def parent_id(self, parent_id):  # pylint: disable=C0111
        self.content['parent_id'] = parent_id

    @property
    def creator(self):
        """Get and set the creator as an unicode object."""
        return self.content.get('creator')

    @creator.setter
    def creator(self, creator):  # pylint: disable=C0111
        self.content['creator'] = creator

    @property
    def didl_metadata(self):
        """Produce the DIDL metadata XML.

        This method uses the :py:attr:`~.DidlObject.item_id`
        attribute (and via that the :py:attr:`~.DidlObject.uri`
        attribute), the :py:attr:`~.DidlObject.item_class` attribute
        and the :py:attr:`~.DidlObject.title`  attribute. The
        metadata will be on the form:

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
        # Check the id_info method and via that, the self.to_dict['uri'] value
        if self.item_id is None:
            raise CannotCreateDIDLMetadata(
                'DIDL Metadata cannot be created when item_id returns None '
                '(most likely because uri is not set)')

        # Main element, ugly yes, but I have given up on using namespaces with
        # xml.etree.ElementTree
        item_attrib = {
            'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
            'xmlns:upnp': 'urn:schemas-upnp-org:metadata-1-0/upnp/',
            'xmlns': 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/'
        }
        xml = XML.Element('DIDL-Lite', item_attrib)
        # Item sub element
        item_attrib = \
            {'parentID': self.parent_id, 'restricted': 'true',
             'id': self.item_id}
        item = XML.SubElement(xml, 'item', item_attrib)
        # Add content from self.content to item
        XML.SubElement(item, 'dc:title').text = self.title
        XML.SubElement(item, 'upnp:class').text = self.item_class
        # Add the desc element
        desc_attrib = {'id': 'cdudn', 'nameSpace':
                       'urn:schemas-rinconnetworks-com:metadata-1-0/'}
        desc = XML.SubElement(item, 'desc', desc_attrib)
        desc.text = 'RINCON_AssociatedZPUDN'
        return xml


###############################################################################
# OBJECT.ITEM HIERARCHY                                                       #
###############################################################################

class DidlItem(DidlObject):

    """A basic content directory item"""

    item_class = 'object.item'
    _translation = {
        'title': ('dc', 'title'),
        'creator': ('dc', 'creator'),
        'stream_content': ('r', 'streamContent'),
        'radio_show': ('r', 'radioShowMd'),
        'album_art_uri': ('upnp', 'albumArtURI'),
        'uri': ('', 'res')
    }

    @property
    def album_art_uri(self):
        """Get and set the album art URI as an unicode object."""
        return self.content.get('album_art_uri')

    @album_art_uri.setter
    def album_art_uri(self, album_art_uri):  # pylint: disable=C0111
        self.content['album_art_uri'] = album_art_uri

# The following are all Sonos specific
    @property
    def stream_content(self):
        """Get and set the stream content URI as an unicode object."""
        return self.content.get('stream_content')

    @stream_content.setter
    def stream_content(self, stream_content):  # pylint: disable=C0111
        self.content['stream_content'] = stream_content

    @property
    def radio_show(self):
        """Get and set the radio show metadata as an unicode object."""
        return self.content.get('radio_show')

    @radio_show.setter
    def radio_show(self, radio_show):  # pylint: disable=C0111
        self.content['radio_show'] = radio_show


class DidlAudioItem(DidlItem):

    """A audio item"""

    item_class = 'object.item.audioitem'


class DidlMusicTrack(DidlAudioItem):

    """Class that represents a music library track.

    :ivar parent_id: The parent ID for the DidlMusicTrack is 'A:TRACKS'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a DidlMusicTrack from XML.
        The value is shown below

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
    _translation = {
        'title': ('dc', 'title'),
        'creator': ('dc', 'creator'),
        'album': ('upnp', 'album'),
        'album_art_uri': ('upnp', 'albumArtURI'),
        'uri': ('', 'res'),
        'original_track_number': ('upnp', 'originalTrackNumber')
    }

    @property
    def album(self):
        """Get and set the album as an unicode object."""
        return self.content.get('album')

    @album.setter
    def album(self, album):  # pylint: disable=C0111
        self.content['album'] = album

    @property
    def original_track_number(self):
        """Get and set the original track number as an ``int``."""
        return self.content.get('original_track_number')

    @original_track_number.setter
    # pylint: disable=C0111
    def original_track_number(self, original_track_number):
        self.content['original_track_number'] = original_track_number


class DidlAudioBroadcast(DidlAudioItem):

    """Class that represents an audio broadcast."""
    item_class = 'object.item.audioItem.audioBroadcast'
    # name: (ns, tag)
    _translation = {
        'title': ('dc', 'title'),
        'creator': ('dc', 'creator'),
        'album': ('upnp', 'album'),
        'album_art_uri': ('upnp', 'albumArtURI'),
        'uri': ('', 'res'),
        'original_track_number': ('upnp', 'originalTrackNumber'),
    }


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


class DidlAlbum(DidlContainer):

    """A content directory album"""

    item_class = 'object.container.album'


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
    _translation = {
        'title': ('dc', 'title'),
        'creator': ('dc', 'creator'),
        'album_art_uri': ('upnp', 'albumArtURI'),
        'uri': ('', 'res')
    }

    @property
    def album_art_uri(self):
        """Get and set the album art URI as an unicode object."""
        return self.content.get('album_art_uri')

    @album_art_uri.setter
    def album_art_uri(self, album_art_uri):  # pylint: disable=C0111
        self.content['album_art_uri'] = album_art_uri


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
