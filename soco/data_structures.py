# pylint: disable=too-many-lines,R0903,W0142,R0913,C0302
# -*- coding: utf-8 -*-


""" This module contains all the data structures for the information objects
such as music tracks or genres

"""

from __future__ import unicode_literals, print_function

import warnings
warnings.simplefilter('always', DeprecationWarning)
import textwrap

from .xml import XML
from .exceptions import CannotCreateDIDLMetadata
from .utils import really_unicode, camel_to_underscore


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


def get_ms_item(xml, service, parent_id):
    """Return the music service item that corresponds to xml. The class is
    identified by getting the type from the 'itemType' tag
    """
    cls = MS_TYPE_TO_CLASS.get(xml.findtext(ns_tag('ms', 'itemType')))
    out = cls.from_xml(xml, service, parent_id)
    return out


def tags_with_text(xml, tags=None):
    """Return a list of tags that contain text retrieved recursively from an
    XML tree
    """
    if tags is None:
        tags = []
    for element in xml:
        if element.text is not None:
            tags.append(element)
        elif len(element) > 0:
            tags_with_text(element, tags)
        else:
            message = 'Unknown XML structure: {0}'.format(element)
            raise ValueError(message)
    return tags


class MusicInfoItem(object):
    """Abstract class for all data structure classes"""

    def __init__(self):
        """Initialize the content as an empty dict."""
        self.content = {}

    def __eq__(self, playable_item):
        """Return the equals comparison result to another ``playable_item``."""
        if not isinstance(playable_item, MusicInfoItem):
            return False
        return self.content == playable_item.content

    def __ne__(self, playable_item):
        """Return the not equals comparison result to another ``playable_item``
        """
        if not isinstance(playable_item, MusicInfoItem):
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


###############################################################################
# MUSIC LIBRARY                                                               #
###############################################################################
class MusicLibraryItem(MusicInfoItem):
    """Abstract class for a queueable item from the music library.

    :ivar item_class: The DIDL Lite class for the music library item is
        ``None``, since it is a abstract class and it should be overwritten in
        the sub classes
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MusicLibraryItems from XML. The
        default value is shown below. This default value applies to most sub
        classes and the rest should overwrite it.

        .. code-block:: python

            # key: (ns, tag)
            _translation = {
                'title': ('dc', 'title'),
                'uri': ('', 'res')
            }

    """
    item_class = None
    # key: (ns, tag)
    _translation = {
        'title': ('dc', 'title'),
        'uri': ('', 'res')
    }

    def __init__(self, uri, title, parent_id, item_id, **kwargs):
        r"""Initialize the MusicLibraryItem from parameter arguments.

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
        super(MusicLibraryItem, self).__init__()

        # Parse the input arguments
        arguments = {'uri': uri, 'title': title, 'parent_id': parent_id,
                     'item_id': item_id}
        arguments.update(kwargs)
        for key, value in arguments.items():
            if key in self._translation or key == 'parent_id' \
                    or key == 'item_id':
                self.content[key] = value
            else:
                raise ValueError(
                    'The key \'{0}\' is not allowed as an argument. Only '
                    'these keys are allowed: {1}'.
                    format(key, str(self._translation.keys())))

    @classmethod
    def from_xml(cls, xml):
        """Return an instance of this class, created from xml.

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
        """Return an instance of this class, created from a dict with
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
    def didl_metadata(self):
        """Produce the DIDL metadata XML.

        This method uses the :py:attr:`~.MusicLibraryItem.item_id`
        attribute (and via that the :py:attr:`~.MusicLibraryItem.uri`
        attribute), the :py:attr:`~.MusicLibraryItem.item_class` attribute
        and the :py:attr:`~.MusicLibraryItem.title`  attribute. The
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


class MLTrack(MusicLibraryItem):
    """Class that represents a music library track.

    :ivar parent_id: The parent ID for the MLTrack is 'A:TRACKS'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLTrack from XML. The value is
        shown below

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
    def creator(self):
        """Get and set the creator as an unicode object."""
        return self.content.get('creator')

    @creator.setter
    def creator(self, creator):  # pylint: disable=C0111
        self.content['creator'] = creator

    @property
    def album(self):
        """Get and set the album as an unicode object."""
        return self.content.get('album')

    @album.setter
    def album(self, album):  # pylint: disable=C0111
        self.content['album'] = album

    @property
    def album_art_uri(self):
        """Get and set the album art URI as an unicode object."""
        return self.content.get('album_art_uri')

    @album_art_uri.setter
    def album_art_uri(self, album_art_uri):  # pylint: disable=C0111
        self.content['album_art_uri'] = album_art_uri

    @property
    def original_track_number(self):
        """Get and set the original track number as an ``int``."""
        return self.content.get('original_track_number')

    @original_track_number.setter
    # pylint: disable=C0111
    def original_track_number(self, original_track_number):
        self.content['original_track_number'] = original_track_number


class MLAlbum(MusicLibraryItem):
    """Class that represents a music library album.

    :ivar item_class: The item_class for MLTrack is
        'object.container.album.musicAlbum'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLAlbum from XML. The value is
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
    def creator(self):
        """Get and set the creator as an unicode object."""
        return self.content.get('creator')

    @creator.setter
    def creator(self, creator):  # pylint: disable=C0111
        self.content['creator'] = creator

    @property
    def album_art_uri(self):
        """Get and set the album art URI as an unicode object."""
        return self.content.get('album_art_uri')

    @album_art_uri.setter
    def album_art_uri(self, album_art_uri):  # pylint: disable=C0111
        self.content['album_art_uri'] = album_art_uri


class MLArtist(MusicLibraryItem):
    """Class that represents a music library artist.

    :ivar item_class: The item_class for MLArtist is
        'object.container.person.musicArtist'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLArtist from XML is inherited
        from :py:class:`.MusicLibraryItem`.
    """

    item_class = 'object.container.person.musicArtist'


class MLGenre(MusicLibraryItem):
    """Class that represents a music library genre.

    :ivar item_class: The item class for the MLGenre is
        'object.container.genre.musicGenre'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLGenre from XML is inherited
        from :py:class:`.MusicLibraryItem`.

    """

    item_class = 'object.container.genre.musicGenre'


class MLComposer(MusicLibraryItem):
    """Class that represents a music library composer.

    :ivar item_class: The item_class for MLComposer is
        'object.container.person.composer'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLComposer from XML is inherited
        from :py:class:`.MusicLibraryItem`.

    """

    item_class = 'object.container.person.composer'


class MLPlaylist(MusicLibraryItem):
    """Class that represents a music library play list.

    :ivar item_class: The item_class for the MLPlaylist is
        'object.container.playlistContainer'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLPlaylist from XML is inherited
        from :py:class:`.MusicLibraryItem`.

    """

    item_class = 'object.container.playlistContainer'


class MLSonosPlaylist(MusicLibraryItem):
    """ Class that represents a sonos playlist.

    :ivar item_class: The item_class for MLSonosPlaylist is
        'object.container.playlistContainer'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating MLSonosPlaylist from
        XML is inherited from :py:class:`.MusicLibraryItem`.

    """

    item_class = 'object.container.playlistContainer'


class MLShare(MusicLibraryItem):
    """Class that represents a music library share.

    :ivar item_class: The item_class for the MLShare is 'object.container'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLShare from XML is inherited
        from :py:class:`.MusicLibraryItem`.

    """

    item_class = 'object.container'


class MLCategory(MusicLibraryItem):
    """Class that represents a music library category.

    :ivar item_class: The item_class for the MLCategory is 'object.container'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLCategory from XML is inherited
        from :py:class:`.MusicLibraryItem`.

    """

    item_class = 'object.container'


class MLAlbumList(MusicLibraryItem):
    """Class that represents a music library album list.

    :ivar item_class: The item_class for MLAlbumList is
        'object.container.albumlist'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLAlbumList from XML is inherited
        from :py:class:`.MusicLibraryItem`.

    """

    item_class = 'object.container.albumlist'


class MLSameArtist(MusicLibraryItem):
    """Class that represents all by the artist.

    This type is returned by browsing an artist or a composer

    :ivar item_class: The item_class for MLSameArtist is
        'object.container.playlistContainer.sameArtist'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLSameArtist from XML is
        inherited from :py:class:`.MusicLibraryItem`.

    """

    item_class = 'object.container.playlistContainer.sameArtist'


###############################################################################
# MUSIC LIBRARY                                                               #
###############################################################################
class URI(MusicInfoItem):
    """General purpose class that represents a audio file URI"""

    valid_fields = ['uri']
    # Note, keep this list sorted with the args to __init__
    required_fields = ['uri']

    def __init__(self, uri):
        """Init method for the URI object"""
        super(URI, self).__init__()
        self.content.update({'uri': uri})

    @classmethod
    def from_dict(cls, dict_in):
        """Initialize a URI item from a dict"""
        # Copy before we modify
        kwargs = dict_in.copy()
        # Check input
        for key in kwargs.keys():
            if key not in cls.valid_fields:
                message = 'The key \'{}\' is not allowed as an argument. '\
                    'Only these keys are allowed: {}'.format(key,
                                                             cls.valid_fields)
                raise ValueError(message)
        for key in cls.required_fields:
            if key not in kwargs.keys():
                message = 'There must be an \'{}\' item in the input dict'\
                    .format(key)
                raise ValueError(message)
        args = [kwargs.pop(key) for key in cls.required_fields]
        return cls(*args)

    @property
    def uri(self):
        """Return the URI of the object"""
        return self.content['uri']

    @property
    # pylint: disable=no-self-use
    def didl_metadata(self):
        """Return the DIDL metadata for a URI

        It is not yet know how to structure the metadata for URIs, so at the
        moment the metadata consist purely of an empty DIDL-Lite container:

        .. code :: xml

         <DIDL-Lite/>

        """
        xml = XML.Element('DIDL-Lite')
        return xml


###############################################################################
# QUEUE                                                                       #
###############################################################################
class QueueItem(MusicInfoItem):
    """Class that represents a queue item.

    :ivar parent_id: The parent ID for the QueueItem is 'Q:0'
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a QueueItem from XML. The value is
        shown below

        .. code-block:: python

            # key: (ns, tag)
            _translation = {
                'title': ('dc', 'title'),
                'creator': ('dc', 'creator'),
                'album': ('upnp', 'album'),
                'album_art_uri': ('upnp', 'albumArtURI'),
                'uri': ('', 'res'),
                'original_track_number': ('upnp', 'originalTrackNumber'),
                'item_class': ('upnp', 'class')
            }

    """

    parent_id = 'Q:0'
    _translation = {
        'title': ('dc', 'title'),
        'creator': ('dc', 'creator'),
        'album': ('upnp', 'album'),
        'album_art_uri': ('upnp', 'albumArtURI'),
        'uri': ('', 'res'),
        'original_track_number': ('upnp', 'originalTrackNumber'),
        'item_class': ('upnp', 'class')
    }

    def __init__(self, uri, title,
                 item_class="object.item.audioItem.musicTrack", **kwargs):
        r"""Instantiate the QueueItem by passing the arguments to the super
        class :py:meth:`.MusicInfoItem.__init__`.

        :param uri: The URI for the queue item
        :param title: The title of the queue item
        :param item_class: The UPnP class for the queue item. The default value
            is: ``object.item.audioItem.musicTrack``
        :param \*\*kwargs: Optional extra information items, valid keys are:
            ``album``, ``album_art_uri``, ``creator``,
            ``original_track_number``. ``original_track_number`` is an ``int``.
            All other values are unicode objects.
        """
        super(QueueItem, self).__init__()

        # Parse the input arguments
        arguments = {'uri': uri, 'title': title, 'item_class': item_class}
        arguments.update(kwargs)
        for key, value in arguments.items():
            if key in self._translation:
                self.content[key] = value
            else:
                raise ValueError(
                    'The key \'{0}\' is not allowed as an argument. Only '
                    'these keys are allowed: {1}'.
                    format(key, str(self._translation.keys())))

    @classmethod
    def from_xml(cls, xml):
        """Return an instance of this class, created from xml.

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (NS['']) element. Inside
            the item element should be the (namespace, tag_name) elements
            in the dictionary-key-to-xml-tag-and-namespace-translation
            described in the class docstring.

        """
        content = {}
        for key, value in cls._translation.items():
            result = xml.find(ns_tag(*value))
            if result is None:
                content[key] = None
            else:
                # The xml objects should contain utf-8 internally
                content[key] = really_unicode(result.text)

        args = [content.pop(arg) for arg in ['uri', 'title', 'item_class']]

        if content.get('original_track_number') is not None:
            content['original_track_number'] = \
                int(content['original_track_number'])
        return cls(*args, **content)

    @classmethod
    def from_dict(cls, content):
        """Return an instance of this class, created from a dict with
        parameters.

        :param content: Dict with information for the music library item.
            Required and valid arguments are the same as for the
            ``__init__`` method.

        """
        # Make a copy since this method will modify the input dict
        content_in = content.copy()
        args = [content_in.pop(arg) for arg in ['uri', 'title', 'item_class']]
        return cls(*args, **content_in)

    @property
    def to_dict(self):
        """Get the dict representation of the instance."""
        return self.content.copy()

    @property
    # pylint: disable=no-self-use
    def didl_metadata(self):
        """Produce the DIDL metadata XML."""
        message = 'Queueitems are not meant to be re-added to the queue and '\
            'therefore cannot create their own didl_metadata'
        raise CannotCreateDIDLMetadata(message)

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
    def item_class(self):
        """Get and set the UPnP object class as an unicode object."""
        return self.content['item_class']

    @item_class.setter
    def item_class(self, item_class):  # pylint: disable=C0111
        self.content['item_class'] = item_class

    @property
    def creator(self):
        """Get and set the creator as an unicode object."""
        return self.content.get('creator')

    @creator.setter
    def creator(self, creator):  # pylint: disable=C0111
        self.content['creator'] = creator

    @property
    def album(self):
        """Get and set the album as an unicode object."""
        return self.content.get('album')

    @album.setter
    def album(self, album):  # pylint: disable=C0111
        self.content['album'] = album

    @property
    def album_art_uri(self):
        """Get and set the album art URI as an unicode object."""
        return self.content.get('album_art_uri')

    @album_art_uri.setter
    def album_art_uri(self, album_art_uri):  # pylint: disable=C0111
        self.content['album_art_uri'] = album_art_uri

    @property
    def original_track_number(self):
        """Get and set the original track number as an ``int``."""
        return self.content.get('original_track_number')

    @original_track_number.setter
    # pylint: disable=C0111
    def original_track_number(self, original_track_number):
        self.content['original_track_number'] = original_track_number


###############################################################################
# MUSIC SERVICE                                                             #
###############################################################################
class MusicServiceItem(MusicInfoItem):
    """Class that represents a music service item"""

    # These fields must be overwritten in the sub classes
    item_class = None
    valid_fields = None
    required_fields = None

    def __init__(self, **kwargs):
        super(MusicServiceItem, self).__init__()
        self.content = kwargs

    @classmethod
    def from_xml(cls, xml, service, parent_id):
        """Return a Music Service item generated from xml

        :param xml: Object XML. All items containing text are added to the
            content of the item. The class variable ``valid_fields`` of each of
            the classes list the valid fields (after translating the camel
            case to underscore notation). Required fields are listed in the
            class variable by that name (where 'id' has been renamed to
            'item_id').
        :type xml: :py:class:`xml.etree.ElementTree.Element`
        :param service: The music service (plugin) instance that retrieved the
            element. This service must contain ``id_to_extended_id`` and
            ``form_uri`` methods and ``description`` and ``service_id``
            attributes.
        :type service: Instance of sub-class of
            :class:`soco.plugins.SoCoPlugin`
        :param parent_id: The parent ID of the item, will either be the
            extended ID of another MusicServiceItem or of a search
        :type parent_id: str

        For a track the XML can e.g. be on the following form:

        .. code :: xml

         <mediaMetadata xmlns="http://www.sonos.com/Services/1.1">
           <id>trackid_141359</id>
           <itemType>track</itemType>
           <mimeType>audio/aac</mimeType>
           <title>Teacher</title>
           <trackMetadata>
             <artistId>artistid_10597</artistId>
             <artist>Jethro Tull</artist>
             <composerId>artistid_10597</composerId>
             <composer>Jethro Tull</composer>
             <albumId>albumid_141358</albumId>
             <album>MU - The Best Of Jethro Tull</album>
             <albumArtistId>artistid_10597</albumArtistId>
             <albumArtist>Jethro Tull</albumArtist>
             <duration>229</duration>
             <albumArtURI>http://varnish01.music.aspiro.com/sca/
              imscale?h=90&amp;w=90&amp;img=/content/music10/prod/wmg/
              1383757201/094639008452_20131105025504431/resources/094639008452.
              jpg</albumArtURI>
             <canPlay>true</canPlay>
             <canSkip>true</canSkip>
             <canAddToFavorites>true</canAddToFavorites>
           </trackMetadata>
         </mediaMetadata>
        """
        # Add a few extra pieces of information
        content = {'description': service.description,
                   'service_id': service.service_id,
                   'parent_id': parent_id}
        # Extract values from the XML
        all_text_elements = tags_with_text(xml)
        for item in all_text_elements:
            tag = item.tag[len(NS['ms']) + 2:]  # Strip namespace
            tag = camel_to_underscore(tag)  # Convert to nice names
            if tag not in cls.valid_fields:
                message = 'The info tag \'{0}\' is not allowed for this item'.\
                    format(tag)
                raise ValueError(message)
            content[tag] = item.text

        # Convert values for known types
        for key, value in content.items():
            if key == 'duration':
                content[key] = int(value)
            if key in ['can_play', 'can_skip', 'can_add_to_favorites',
                       'can_enumerate']:
                content[key] = True if value == 'true' else False
        # Rename a single item
        content['item_id'] = content.pop('id')
        # And get the extended id
        content['extended_id'] = service.id_to_extended_id(content['item_id'],
                                                           cls)
        # Add URI if there is one for the relevant class
        uri = service.form_uri(content, cls)
        if uri:
            content['uri'] = uri

        # Check for all required values
        for key in cls.required_fields:
            if key not in content:
                message = 'An XML field that correspond to the key \'{0}\' '\
                    'is required. See the docstring for help.'.format(key)

        return cls.from_dict(content)

    @classmethod
    def from_dict(cls, dict_in):
        """Initialize the class from a dict

        :param dict_in: The dictionary that contains the item content. Required
            fields are listed class variable by that name
        :type dict_in: dict
        """
        kwargs = dict_in.copy()
        args = [kwargs.pop(key) for key in cls.required_fields]
        return cls(*args, **kwargs)

    @property
    def to_dict(self):
        """Return a copy of the content dict"""
        return self.content.copy()

    @property
    def didl_metadata(self):
        """Return the DIDL metadata for a Music Service Track

        The metadata is on the form:

        .. code :: xml

         <DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"
              xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
              xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"
              xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
           <item id="...self.extended_id..."
              parentID="...self.parent_id..."
              restricted="true">
             <dc:title>...self.title...</dc:title>
             <upnp:class>...self.item_class...</upnp:class>
             <desc id="cdudn"
                nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">
               self.content['description']
             </desc>
           </item>
         </DIDL-Lite>
        """
        # Check if this item is meant to be played
        if not self.can_play:
            message = 'This item is not meant to be played and therefore '\
                'also not to create its own didl_metadata'
            raise CannotCreateDIDLMetadata(message)
        # Check if we have the attributes to create the didl metadata:
        for key in ['extended_id', 'title', 'item_class']:
            if not hasattr(self, key):
                message = 'The property \'{0}\' is not present on this item. '\
                    'This indicates that this item was not meant to create '\
                    'didl_metadata'.format(key)
                raise CannotCreateDIDLMetadata(message)
        if 'description' not in self.content:
            message = 'The item for \'description\' is not present in '\
                'self.content. This indicates that this item was not meant '\
                'to create didl_metadata'
            raise CannotCreateDIDLMetadata(message)

        # Main element, ugly? yes! but I have given up on using namespaces
        # with xml.etree.ElementTree
        item_attrib = {
            'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
            'xmlns:upnp': 'urn:schemas-upnp-org:metadata-1-0/upnp/',
            'xmlns:r': 'urn:schemas-rinconnetworks-com:metadata-1-0/',
            'xmlns': 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/'
        }
        xml = XML.Element('DIDL-Lite', item_attrib)
        # Item sub element
        item_attrib = {
            'parentID': '',
            'restricted': 'true',
            'id': self.extended_id
        }
        # Only add the parent_id if we have it
        if self.parent_id:
            item_attrib['parentID'] = self.parent_id
        item = XML.SubElement(xml, 'item', item_attrib)

        # Add title and class
        XML.SubElement(item, 'dc:title').text = self.title
        XML.SubElement(item, 'upnp:class').text = self.item_class
        # Add the desc element
        desc_attrib = {
            'id': 'cdudn',
            'nameSpace': 'urn:schemas-rinconnetworks-com:metadata-1-0/'
        }
        desc = XML.SubElement(item, 'desc', desc_attrib)
        desc.text = self.content['description']

        return xml

    @property
    def item_id(self):
        """Return the item id"""
        return self.content['item_id']

    @property
    def extended_id(self):
        """Return the extended id"""
        return self.content['extended_id']

    @property
    def title(self):
        """Return the title"""
        return self.content['title']

    @property
    def service_id(self):
        """Return the service ID"""
        return self.content['service_id']

    @property
    def can_play(self):
        """Return a boolean for whether the item can be played"""
        return bool(self.content.get('can_play'))

    @property
    def parent_id(self):
        """Return the extended parent_id, if set, otherwise return None"""
        return self.content.get('parent_id')

    @property
    def album_art_uri(self):
        """Return the album art URI if set, otherwise return None"""
        return self.content.get('album_art_uri')


class MSTrack(MusicServiceItem):
    """Class that represents a music service track"""

    item_class = 'object.item.audioItem.musicTrack'
    valid_fields = [
        'album', 'can_add_to_favorites', 'artist', 'album_artist_id', 'title',
        'album_id', 'album_art_uri', 'album_artist', 'composer_id',
        'item_type', 'composer', 'duration', 'can_skip', 'artist_id',
        'can_play', 'id', 'mime_type', 'description'
    ]
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ['title', 'item_id', 'extended_id', 'uri', 'description',
                       'service_id']

    def __init__(self, title, item_id, extended_id, uri, description,
                 service_id, **kwargs):
        """Initialize MSTrack item"""
        content = {
            'title': title, 'item_id': item_id, 'extended_id': extended_id,
            'uri': uri, 'description': description, 'service_id': service_id,
        }
        content.update(kwargs)
        super(MSTrack, self).__init__(**content)

    @property
    def album(self):
        """Return the album title if set, otherwise return None"""
        return self.content.get('album')

    @property
    def artist(self):
        """Return the artist if set, otherwise return None"""
        return self.content.get('artist')

    @property
    def duration(self):
        """Return the duration if set, otherwise return None"""
        return self.content.get('duration')

    @property
    def uri(self):
        """Return the URI"""
        # x-sonos-http:trackid_19356232.mp4?sid=20&amp;flags=32
        return self.content['uri']


class MSAlbum(MusicServiceItem):
    """Class that represents a Music Service Album"""

    item_class = 'object.container.album.musicAlbum'
    valid_fields = [
        'username', 'can_add_to_favorites', 'artist', 'title', 'album_art_uri',
        'can_play', 'item_type', 'service_id', 'id', 'description',
        'can_cache', 'artist_id', 'can_skip'
    ]
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ['title', 'item_id', 'extended_id', 'uri', 'description',
                       'service_id']

    def __init__(self, title, item_id, extended_id, uri, description,
                 service_id, **kwargs):
        content = {
            'title': title, 'item_id': item_id, 'extended_id': extended_id,
            'uri': uri, 'description': description, 'service_id': service_id,
        }
        content.update(kwargs)
        super(MSAlbum, self).__init__(**content)

    @property
    def artist(self):
        """Return the artist if set, otherwise return None"""
        return self.content.get('artist')

    @property
    def uri(self):
        """Return the URI"""
        # x-rincon-cpcontainer:0004002calbumid_22757081
        return self.content['uri']


class MSAlbumList(MusicServiceItem):
    """Class that represents a Music Service Album List"""

    item_class = 'object.container.albumlist'
    valid_fields = [
        'id', 'title', 'item_type', 'artist', 'artist_id', 'can_play',
        'can_enumerate', 'can_add_to_favorites', 'album_art_uri', 'can_cache'
    ]
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ['title', 'item_id', 'extended_id', 'uri', 'description',
                       'service_id']

    def __init__(self, title, item_id, extended_id, uri, description,
                 service_id, **kwargs):
        content = {
            'title': title, 'item_id': item_id, 'extended_id': extended_id,
            'uri': uri, 'description': description, 'service_id': service_id,
        }
        content.update(kwargs)
        super(MSAlbumList, self).__init__(**content)

    @property
    def uri(self):
        """Return the URI"""
        # x-rincon-cpcontainer:000d006cplaylistid_26b18dbb-fd35-40bd-8d4f-
        # 8669bfc9f712
        return self.content['uri']


class MSPlaylist(MusicServiceItem):
    """Class that represents a Music Service Play List"""

    item_class = 'object.container.albumlist'
    valid_fields = ['id', 'item_type', 'title', 'can_play', 'can_cache',
                    'album_art_uri', 'artist', 'can_enumerate',
                    'can_add_to_favorites', 'artist_id']
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ['title', 'item_id', 'extended_id', 'uri', 'description',
                       'service_id']

    def __init__(self, title, item_id, extended_id, uri, description,
                 service_id, **kwargs):
        content = {
            'title': title, 'item_id': item_id, 'extended_id': extended_id,
            'uri': uri, 'description': description, 'service_id': service_id,
        }
        content.update(kwargs)
        super(MSPlaylist, self).__init__(**content)

    @property
    def uri(self):
        """Return the URI"""
        # x-rincon-cpcontainer:000d006cplaylistid_c86ddf26-8ec5-483e-b292-
        # abe18848e89e
        return self.content['uri']


class MSArtistTracklist(MusicServiceItem):
    """Class that represents a Music Service Artist Track List"""

    item_class = 'object.container.playlistContainer.sameArtist'
    valid_fields = ['id', 'title', 'item_type', 'can_play', 'album_art_uri']
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ['title', 'item_id', 'extended_id', 'uri', 'description',
                       'service_id']

    def __init__(self, title, item_id, extended_id, uri, description,
                 service_id, **kwargs):
        content = {
            'title': title, 'item_id': item_id, 'extended_id': extended_id,
            'uri': uri, 'description': description, 'service_id': service_id,
        }
        content.update(kwargs)
        super(MSArtistTracklist, self).__init__(**content)

    @property
    def uri(self):
        """Return the URI"""
        # x-rincon-cpcontainer:100f006cartistpopsongsid_1566
        return 'x-rincon-cpcontainer:100f006c{0}'.format(self.item_id)


class MSArtist(MusicServiceItem):
    """Class that represents a Music Service Artist"""

    valid_fields = [
        'username', 'can_add_to_favorites', 'artist', 'title', 'album_art_uri',
        'item_type', 'id', 'service_id', 'description', 'can_cache'
    ]
    # Since MSArtist cannot produce didl_metadata, they are not strictly
    # required, but it makes sense to require them anyway, since they are the
    # fields that that describe the item
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ['title', 'item_id', 'extended_id', 'service_id']

    def __init__(self, title, item_id, extended_id, service_id, **kwargs):
        content = {'title': title, 'item_id': item_id,
                   'extended_id': extended_id, 'service_id': service_id}
        content.update(kwargs)
        super(MSArtist, self).__init__(**content)


class MSFavorites(MusicServiceItem):
    """Class that represents a Music Service Favorite"""

    valid_fields = ['id', 'item_type', 'title', 'can_play', 'can_cache',
                    'album_art_uri']
    # Since MSFavorites cannot produce didl_metadata, they are not strictly
    # required, but it makes sense to require them anyway, since they are the
    # fields that that describe the item
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ['title', 'item_id', 'extended_id', 'service_id']

    def __init__(self, title, item_id, extended_id, service_id, **kwargs):
        content = {'title': title, 'item_id': item_id,
                   'extended_id': extended_id, 'service_id': service_id}
        content.update(kwargs)
        super(MSFavorites, self).__init__(**content)


class MSCollection(MusicServiceItem):
    """Class that represents a Music Service Collection"""

    valid_fields = ['id', 'item_type', 'title', 'can_play', 'can_cache',
                    'album_art_uri']
    # Since MSCollection cannot produce didl_metadata, they are not strictly
    # required, but it makes sense to require them anyway, since they are the
    # fields that that describe the item
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ['title', 'item_id', 'extended_id', 'service_id']

    def __init__(self, title, item_id, extended_id, service_id, **kwargs):
        content = {'title': title, 'item_id': item_id,
                   'extended_id': extended_id, 'service_id': service_id}
        content.update(kwargs)
        super(MSCollection, self).__init__(**content)

###############################################################################
# MUSIC STREAMS                                                             #
###############################################################################


class Stream(MusicInfoItem):
    """Abstract class for a  streams (eg radio stations or one off URIs)

    :ivar item_class: The DIDL Lite class for the music library item is
        ``None``, since it is a abstract class and it should be overwritten in
        the sub classes
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MusicLibraryItems from XML. The
        default value is shown below. This default value applies to most sub
        classes and the rest should overwrite it.

        .. code-block:: python

            # key: (ns, tag)
            _translation = {
                'title': ('dc', 'title'),
                'uri': ('', 'res')
            }

    """
    item_class = None
    # key: (ns, tag)
    _translation = {
        'title': ('dc', 'title'),
        'uri': ('', 'res')
    }

    def __init__(self, uri, title, parent_id, **kwargs):
        r"""Initialize the MusicLibraryItem from parameter arguments.

        :param uri: The URI for the item
        :param title: The title for the item
        :param parent_id: The parent ID for the item
        :param \*\*kwargs: Extra information items to form the music library
            item from. Valid keys are ``album``, ``album_art_uri``,
            ``creator`` and ``original_track_number``.
            ``original_track_number`` is an int, all other values are
            unicode objects.

        """
        super(Stream, self).__init__()

        # Parse the input arguments
        arguments = {'uri': uri, 'title': title, 'parent_id': parent_id}
        arguments.update(kwargs)
        for key, value in arguments.items():
            if key in self._translation or key == 'parent_id':
                self.content[key] = value
            else:
                raise ValueError(
                    'The key \'{0}\' is not allowed as an argument. Only '
                    'these keys are allowed: {1}'.
                    format(key, str(self._translation.keys())))

    @classmethod
    def from_xml(cls, xml):
        """Return an instance of this class, created from xml.

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

        # Extract the parent ID
        content['parent_id'] = xml.get('parentID')

        # Convert type for original track number
        if content.get('original_track_number') is not None:
            content['original_track_number'] = \
                int(content['original_track_number'])
        return cls.from_dict(content)

    @classmethod
    def from_dict(cls, content):
        """Return an instance of this class, created from a dict with
        parameters.

        :param content: Dict with information for the music library item.
            Required and valid arguments are the same as for the
            ``__init__`` method.

        """
        # Make a copy since this method will modify the input dict
        content_in = content.copy()
        args = [content_in.pop(arg) for arg in ['uri', 'title', 'parent_id']]
        return cls(*args, **content_in)

    @property
    def to_dict(self):
        """Get the dict representation of the instance."""
        return self.content.copy()

    @property
    def item_id(self):  # pylint: disable=C0103
        """Return the id.

        The id is extracted as the part of the URI after the first # character.
        For the few music library types where that is not correct, this method
        should be overwritten.
        """
        out = self.content['uri']
        try:
            out = out[out.index('#') + 1:]
        except ValueError:
            out = None
        return out

    @property
    def didl_metadata(self):
        """Produce the DIDL metadata XML.

        This method uses the :py:attr:`~.MusicLibraryItem.item_id`
        attribute (and via that the :py:attr:`~.MusicLibraryItem.uri`
        attribute), the :py:attr:`~.MusicLibraryItem.item_class` attribute
        and the :py:attr:`~.MusicLibraryItem.title`  attribute. The
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


class StreamItem(Stream):
    """Class that represents an audio broadcast.

    :ivar parent_id: The parent ID for the MLItem is object.item
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLItem from XML.
        The value is shown below

        .. code-block:: python

            # key: (ns, tag)
             _translation = {
                'title': ('dc', 'title'),
                'stream_content': ('r', 'streamContent'),
                'radio_show': ('r', 'radioShowMd'),
                'album_art_uri': ('upnp', 'albumArtURI'),
                'uri': ('', 'res')
            }

    """

    item_class = 'object.item'
    # name: (ns, tag)
    _translation = {
        'title': ('dc', 'title'),
        'stream_content': ('r', 'streamContent'),
        'radio_show': ('r', 'radioShowMd'),
        'album_art_uri': ('upnp', 'albumArtURI'),
        'uri': ('', 'res')
    }

    @property
    def stream_content(self):
        """Get and set the creator as an unicode object."""
        return self.content.get('stream_content')

    @stream_content.setter
    def stream_content(self, stream_content):  # pylint: disable=C0111
        self.content['stream_content'] = stream_content

    @property
    def radio_show(self):
        """Get and set the radio_show as an unicode object."""
        return self.content.get('radio_show')

    @radio_show.setter
    def radio_show(self, radio_show):  # pylint: disable=C0111
        self.content['radio_show'] = radio_show

    @property
    def album_art_uri(self):
        """Get and set the album art URI as an unicode object."""
        return self.content.get('album_art_uri')

    @album_art_uri.setter
    def album_art_uri(self, album_art_uri):  # pylint: disable=C0111
        self.content['album_art_uri'] = album_art_uri


class StreamAudiobroadcast(Stream):
    """Class that represents an audio broadcast.

    :ivar parent_id: The parent ID for the MLAudiobroadcast is ????
    :ivar _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLAudiobroadcast from XML.

        Only use radio station title

        The value is shown below
        (note uri in not in this class but needed to make super class work)

        .. code-block:: python

            # key: (ns, tag)
             _translation = {
                'station_title': ('dc', 'title'),
                'desc': ('r', 'desc')
                'uri': ('', 'res')
            }

    """

    item_class = 'object.item.audioItem.audioBroadcast'
    # name: (ns, tag)
    _translation = {
        'title': ('dc', 'title'),
        'desc': ('r', 'desc'),
        'uri': ('', 'res')
    }

    @property
    def desc(self):
        """Get and set the creator as an unicode object."""
        return self.content.get('desc')

    @desc.setter
    def stream_content(self, desc):  # pylint: disable=C0111
        self.content['stream_content'] = desc


###############################################################################
# CONTAINERS                                                                  #
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


DIDL_CLASS_TO_CLASS = {'object.item.audioItem.musicTrack': MLTrack,
                       'object.container.album.musicAlbum': MLAlbum,
                       'object.container.person.musicArtist': MLArtist,
                       'object.container.genre.musicGenre': MLGenre,
                       'object.container.person.composer': MLComposer,
                       'object.container.playlistContainer': MLPlaylist,
                       'object.container': MLCategory,
                       'object.container.albumlist': MLAlbumList,
                       'object.container.playlistContainer.sameArtist':
                           MLSameArtist,
                       'object.item': StreamItem,
                       'object.item.audioItem.audioBroadcast':
                           StreamAudiobroadcast}

MS_TYPE_TO_CLASS = {'artist': MSArtist, 'album': MSAlbum, 'track': MSTrack,
                    'albumList': MSAlbumList, 'favorites': MSFavorites,
                    'collection': MSCollection, 'playlist': MSPlaylist,
                    'artistTrackList': MSArtistTracklist}

NS = {
    'dc': 'http://purl.org/dc/elements/1.1/',
    'upnp': 'urn:schemas-upnp-org:metadata-1-0/upnp/',
    '': 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/',
    'ms': 'http://www.sonos.com/Services/1.1',
    'r': 'urn:schemas-rinconnetworks-com:metadata-1-0/'
}
