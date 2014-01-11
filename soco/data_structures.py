# -*- coding: utf-8 -*-
# pylint: disable=R0903,W0142

""" This module contains all the data structures for the information objects
such as music tracks or genres

"""

from __future__ import unicode_literals
try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML
NS = {
    'dc': 'http://purl.org/dc/elements/1.1/',
    'upnp': 'urn:schemas-upnp-org:metadata-1-0/upnp/',
    '': 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/',
    'r': 'urn:schemas-rinconnetworks-com:metadata-1-0/',
    's': 'http://schemas.xmlsoap.org/soap/envelope/',
    'u': 'urn:schemas-upnp-org:service:ContentDirectory:1'
}
# Register all name spaces within the XML module
for key_, value_ in NS.items():
    XML.register_namespace(key_, value_)
from soco.utils import really_unicode
from soco.exceptions import CannotCreateDIDLMetadata


def ns_tag(ns_id, tag):
    """Return a namespace/tag item."""
    return '{{{0}}}{1}'.format(NS[ns_id], tag)


def get_ml_item(xml):
    """Return the music library item that corresponds to xml. The class is
    identified by getting the parentID and making a lookup in the
    PARENT_ID_TO_CLASS dictionary.

    """
    cls = PARENT_ID_TO_CLASS[xml.get('parentID')]
    return cls.from_xml(xml=xml)


class PlayableItem(object):
    """Abstract class for all playable items."""

    def __init__(self):
        """Initialize the content as an empty dict."""
        self.content = {}

    def __eq__(self, playable_item):
        """Return the equals comparison result to another ``playable_item``."""
        return self.content == playable_item.content

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


class QueueableItem(PlayableItem):
    """Abstract class for a playable item that can be queued."""

    def __init__(self):
        """Run __init__ from :py:class:`.PlayableItem`."""
        PlayableItem.__init__(self)


class MusicLibraryItem(QueueableItem):
    """Abstract class for a queueable item from the music library.

    :param parent_id: The parent ID for the music library item is None, since
        it is a abstract class and it should be overwritten in the sub
        classes
    :param _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MusicLibraryItems from XML. The
        default value is shown below. This default value applies to most sub
        classes and the rest should overwrite it.

        .. code-block:: python

            # key: (ns, tag)
            _translation = {
                'title': ('dc', 'title'),
                'uri': ('', 'res'),
                'item_class': ('upnp', 'class')
            }

    """
    parent_id = None
    # key: (ns, tag)
    _translation = {
        'title': ('dc', 'title'),
        'uri': ('', 'res'),
        'item_class': ('upnp', 'class')
    }

    def __init__(self, uri, title, item_class, **kwargs):
        """Initialize the MusicLibraryItem from parameter arguments.

        :param uri: The URI for the item
        :param title: The title for the item
        :param item_class: The UPnP class for the item
        :param **kwargs: Extra information items to form the music library
            item from. Valid keys are 'album', 'album_art_uri', 'creator' and
            'original_track_number'. 'original_track_number' is an int, all
            other values are unicode objects.

        """
        QueueableItem.__init__(self)

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
        """Return an instanse of this class, created from xml.

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (NS['']) element. Inside
            the item element should be the (namespace, tag_name) elements
            in the dictionary-key-to-xml-tag-and-namespace-translation
            described in __init__.

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
        return cls(*args, **content)

    @classmethod
    def from_dict(cls, content):
        """Return an instance of this class, created from a dict with
        parameters.

        :param content: Dict with MusicLirabryItem information. Required and
            valid arguments are the same as for the __init__ method

        """
        # Make a copy since this method will modify the input dict
        content_in = content.copy()
        args = [content_in.pop(arg) for arg in ['uri', 'title', 'item_class']]
        return cls(*args, **content_in)

    @property
    def to_dict(self):
        """Get the dict representation of the ``MusicLibraryItem``."""
        return self.content

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

        This method depends, as a minimum, on the
        :py:attr:`~.MusicLibraryItem.item_id` attribute (and via that the
        :py:attr:`~.MusicLibraryItem.uri` attribute. The values for
        ``item_class`` and ``title`` will also be used if present, but may not
        be necessary. The metadata will be on the form:

        .. code :: xml

         <DIDL-Lite ..NS_INFO..>
           <item id="...self.item_id..."
             parentID="...self.parent_id..." restricted="true">
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

        # Main element
        xml = XML.Element('DIDL-Lite')
        # Item sub element
        item_attrib = \
            {'parentID': self.parent_id, 'restricted': 'true',
             'id': self.item_id}
        item = XML.SubElement(xml, 'item', item_attrib)
        # Add content from self.content to item
        for key in ['title', 'item_class']:
            element = XML.SubElement(
                item, ns_tag(*self._translation[key]))
            element.text = self.content[key]
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
    def item_class(self):
        """Get and set the UPnP object class as an unicode object."""
        return self.content['item_class']

    @item_class.setter
    def item_class(self, item_class):  # pylint: disable=C0111
        self.content['item_class'] = item_class


class MLTrack(MusicLibraryItem):
    """Class that represents a music library track.

    :param parent_id: The parent ID for the MLTrack is 'A:TRACKS'
    :param _translation: The dictionary-key-to-xml-tag-and-namespace-
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
                'original_track_number': ('upnp', 'originalTrackNumber'),
                'item_class': ('upnp', 'class')
            }

    """

    parent_id = 'A:TRACKS'
    # name: (ns, tag)
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
                 item_class='object.item.audioItem.musicTrack', **kwargs):
        """Instantiate the MLTrack item by passing the arguments to the
        super class :py:method:`.MusicLibraryItem.__init__`.

        :param uri: The URI for the track
        :param title: The title of the track
        :param item_class: The UPnP class for the track. The default value is:
            'object.item.audioItem.musicTrack'
        :param kwargs: Optional extra information items, valid keys are:
            'album', 'album_art_uri', 'creator', 'original_track_number'. All
            value should be unicode objects.
        """
        MusicLibraryItem.__init__(self, uri, title, item_class, **kwargs)

    @property
    def item_id(self):  # pylint: disable=C0103
        """Return the id."""
        out = self.content['uri']
        if 'x-file-cifs' in out:
            # URI's for MusicTracks starts with x-file-cifs, where cifs most
            # likely refer to Common Internet File System. For unknown reasons
            # that part must be replaces with an S to form the item_id
            out = out.replace('x-file-cifs', 'S')
        else:
            out = None
        return out

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
        """Get and set the original track number as an integer."""
        return self.content.get('original_track_number')

    @original_track_number.setter
    # pylint: disable=C0111
    def original_track_number(self, original_track_number):
        self.content['original_track_number'] = original_track_number


class MLAlbum(MusicLibraryItem):
    """Class that represents a music library album.

    :param parent_id: The parent ID for the MLTrack is 'A:ALBUM'
    :param _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLAlbum from XML. The value is
        shown below

        .. code-block :: python

            # key: (ns, tag)
            _translation = {
                'title': ('dc', 'title'),
                'creator': ('dc', 'creator'),
                'album_art_uri': ('upnp', 'albumArtURI'),
                'uri': ('', 'res'),
                'item_class': ('upnp', 'class')
            }

    """

    parent_id = 'A:ALBUM'
    # name: (ns, tag)
    _translation = {
        'title': ('dc', 'title'),
        'creator': ('dc', 'creator'),
        'album_art_uri': ('upnp', 'albumArtURI'),
        'uri': ('', 'res'),
        'item_class': ('upnp', 'class')
    }

    def __init__(self, uri, title,
                 item_class='object.container.album.musicAlbum', **kwargs):
        """Instantiate the MLAlbum item by passing the arguments to the
        super class :py:method:`.MusicLibraryItem.__init__`.

        :param uri: The URI for the alum
        :param title: The title of the album
        :param item_class: The UPnP class for the album. The default value is:
            'object.container.album.musicAlbum'
        :param kwargs: Optional extra information items, valid keys are:
            'album_art_uri' and 'creator'. All value should be unicode objects.
        """
        MusicLibraryItem.__init__(self, uri, title, item_class, **kwargs)

    @property
    def creator(self):
        """Get and set the creator as an unicode object."""
        return self.content['creator']

    @creator.setter
    def creator(self, creator):  # pylint: disable=C0111
        self.content['creator'] = creator

    @property
    def album_art_uri(self):
        """Get and set the album art URI as an unicode object."""
        return self.content['album_art_uri']

    @album_art_uri.setter
    def album_art_uri(self, album_art_uri):  # pylint: disable=C0111
        self.content['album_art_uri'] = album_art_uri


class MLArtist(MusicLibraryItem):
    """Class that represents a music library artist.

    :param parent_id: The parent ID for the MLArtist is 'A:ARTIST'
    :param _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLArtist from XML is inherited
        from :py:class:`.MusicLibraryItem`.
    """

    parent_id = 'A:ARTIST'

    def __init__(self, uri, title,
                 item_class='object.container.person.musicArtist'):
        """Instantiate the MLArtist item by passing the arguments to the
        super class :py:method:`.MusicLibraryItem.__init__`.

        :param uri: The URI for the artist
        :param title: The title of the artist
        :param item_class: The UPnP class for the artist. The default value is:
            'object.container.person.musicArtist'
        """
        MusicLibraryItem.__init__(self, uri, title, item_class)


class MLAlbumArtist(MusicLibraryItem):
    """Class that represents a music library album artist.

    :param parent_id: The parent ID for the MLAlbumArtist is 'A:ALBUMARTIST'
    :param _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLAlbumArtist from XML is
        inherited from :py:class:`.MusicLibraryItem`.

    """

    parent_id = 'A:ALBUMARTIST'

    def __init__(self, uri, title,
                 item_class='object.container.person.musicArtist'):
        """Instantiate the MLAlbumArtist item by passing the arguments to the
        super class :py:method:`.MusicLibraryItem.__init__`.

        :param uri: The URI for the alum artist
        :param title: The title of the album artist
        :param item_class: The UPnP class for the album artist. The default
            value is: 'object.container.person.musicArtist'

        """
        MusicLibraryItem.__init__(self, uri, title, item_class)


class MLGenre(MusicLibraryItem):
    """Class that represents a music library genre.

    :param parent_id: The parent ID for the MLGenre is 'A:GENRE'
    :param _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLGenre from XML is inherited
        from :py:class:`.MusicLibraryItem`.

    """

    parent_id = 'A:GENRE'

    def __init__(self, uri, title,
                 item_class='object.container.genre.musicGenre'):
        """Instantiate the MLGenre item by passing the arguments to the
        super class :py:method:`.MusicLibraryItem.__init__`.

        :param uri: The URI for the genre
        :param title: The title of the genre
        :param item_class: The UPnP class for the genre. The default value is:
            'object.container.genre.musicGenre'

        """
        MusicLibraryItem.__init__(self, uri, title, item_class)


class MLComposer(MusicLibraryItem):
    """Class that represents a music library composer.

    :param parent_id: The parent ID for the MLComposer is 'A:COMPOSER'
    :param _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLComposer from XML is inherited
        from :py:class:`.MusicLibraryItem`.

    """

    parent_id = 'A:COMPOSER'

    def __init__(self, uri, title,
                 item_class='object.container.person.composer'):
        """Instantiate the MLComposer item by passing the arguments to the
        super class :py:method:`.MusicLibraryItem.__init__`.

        :param uri: The URI for the composer
        :param title: The title of the composer
        :param item_class: The UPnP class for the composer. The default value
            is: 'object.container.person.composer'

        """
        MusicLibraryItem.__init__(self, uri, title, item_class)


class MLPlaylist(MusicLibraryItem):
    """Class that represents a music library play list.

    :param parent_id: The parent ID for the MLPlaylist is 'A:PLAYLIST'
    :param _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLPlaylist from XML is inherited
        from :py:class:`.MusicLibraryItem`.

    """

    parent_id = 'A:PLAYLISTS'

    def __init__(self, uri, title,
                 item_class='object.container.playlistContainer'):
        """Instantiate the MLPlaylist item by passing the arguments to the
        super class :py:method:`.MusicLibraryItem.__init__`.

        :param uri: The URI for the playlist
        :param title: The title of the playlist
        :param item_class: The UPnP class for the playlist. The default value
            is: 'object.container.playlistContainer'

        """
        MusicLibraryItem.__init__(self, uri, title, item_class)

    @property
    def item_id(self):  # pylint: disable=C0103
        """Returns the id."""
        out = self.content['uri']
        if 'x-file-cifs' in out:
            out = out.replace('x-file-cifs', 'S')
        else:
            out = None
        return out


class MLShare(MusicLibraryItem):
    """Class that represents a music library share.

    :param parent_id: The parent ID for the MLShare is 'S:'
    :param _translation: The dictionary-key-to-xml-tag-and-namespace-
        translation used when instantiating a MLShare from XML is inherited
        from :py:class:`.MusicLibraryItem`.

    """

    parent_id = 'S:'

    def __init__(self, uri, title, item_class='object.container'):
        """Instantiate the MLShare item by passing the arguments to the
        super class :py:method:`.MusicLibraryItem.__init__`.

        :param uri: The URI for the share
        :param title: The title of the share
        :param item_class: The UPnP class for the share. The default value is:
            'object.container'

        """
        MusicLibraryItem.__init__(self, uri, title, item_class)


PARENT_ID_TO_CLASS = {'A:TRACKS': MLTrack, 'A:ALBUM': MLAlbum,
                      'A:ARTIST': MLArtist, 'A:ALBUMARTIST': MLAlbumArtist,
                      'A:GENRE': MLGenre, 'A:COMPOSER': MLComposer,
                      'A:PLAYLISTS': MLPlaylist, 'S:': MLShare}
