# -*- coding: utf-8 -*-
# pylint: disable=R0903,W0142

""" This module contains all the data structures for the information objects
such as music tracks or genres

"""

from __future__ import unicode_literals
from soco.utils import really_unicode
from soco.exceptions import CannotCreateDIDLMetadata
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


def ns_tag(ns_id, tag):
    """ Returns a namespace/tag item """
    return '{{{0}}}{1}'.format(NS[ns_id], tag)


def get_ml_item(xml):
    """Returns the music library item that corresponds to xml. The class is
    identified by getting the parentID and making a lookup in the
    PARENT_ID_TO_CLASS dictionary.

    """
    cls = PARENT_ID_TO_CLASS[xml.get('parentID')]
    return cls(xml=xml)


class PlayableItem(object):
    """Abstract class for all playable items."""

    def __init__(self):
        """Initialize the content as an empty dict."""
        self._content = {}

    def __eq__(self, playable_item):
        """Returns the equals comparison result to another ``playable_item``.

        """
        return self._content == playable_item.content

    def __hash__(self):
        """Returns the hash value of the item.

        Calculated as the hash of the :py:attr:`.content` dictionary and the
        ``__class__``.

        """
        hashitems = self._content.items() + [('__class__', self.__class__)]
        return hash(frozenset(hashitems))

    def __repr__(self):
        """Returns the repr value for the item.

        The repr is on the form::

         <class_name 'middle_part[0:40]' at id_in_hex>

        where middle_part is either the title item in content, if it is set, or
        ``str(content)``. The output is also cleared of non-ascii characters.

        """
        # 40 originates from terminal width (78) - (15) for address part and
        # (19) for the longest class name and a little left for buffer
        if self._content.get('title') is not None:
            middle = self._content['title'].encode('ascii', 'replace')[0:40]
        else:
            middle = str(self._content).encode('ascii', 'replace')[0:40]
        return '<{0} \'{1}\' at {2}>'.format(self.__class__.__name__,
                                             middle,
                                             hex(id(self)))

    def __str__(self):
        """Returns the str value for the item::

         <class_name 'middle_part[0:40]' at id_in_hex>

        where middle_part is either the title item in content, if it is set, or
        ``str(content)``. The output is also cleared of non-ascii characters.

        """
        return self.__repr__()

    @property
    def content(self):
        """Get and set method for the content dict.

        If set, the dict must contain values for the keys mentioned in the
        docstring for the __init__ method.

        """
        return self._content

    @content.setter
    def content(self, content):  # pylint: disable=C0111
        self._content = content


class QueueableItem(PlayableItem):
    """Abstract class for a playable item that can be queued."""

    def __init__(self):
        """Run __init__ from :py:class:`.PlayableItem`."""
        PlayableItem.__init__(self)


class MusicLibraryItem(QueueableItem):
    """Abstract class for a queueable item from the music library."""

    def __init__(self, translation=None, xml=None, content=None):
        """Call the ``__init__`` method from :py:class:`.QueueableItem` and
        initialize the internal variables for translation and content.

        MusicLibraryItem must be instantiated with EITHER an xml or content
        argument.

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (com.NS['']). Inside the
            item element are the (namespace, tag_name) elements described in
            translation.
        :param content: A dictionary describing the track. This dictionary can
            only contain values for the keys in translation.
        :param translation: A
            dictionary-key-to-xml-tag-and-namespace-translation. Defaults to:

            .. code-block:: python

                # key: (ns, tag)
                translation = {
                    'title': ('dc', 'title'),
                    'uri': ('', 'res'),
                    'class': ('upnp', 'class')
                }

        """
        QueueableItem.__init__(self)
        self._parent_id = None

        if translation is not None:
            self._translation = translation
        else:
            self._translation = {'title': ('dc', 'title'),
                                 'uri': ('', 'res'),
                                 'class': ('upnp', 'class')}

        # Should be called with EITHER a xml or content argument
        if not ((xml is None) ^ (content is None)):
            raise ValueError('MusicLibraryItem  and subclasses must be '
                             'instantiated with either an xml or a content '
                             'argument')

        # Instantiate from content
        if content is not None:
            for key in content.keys():
                # Do not accept value for keys that are not in translation
                if key not in self._translation.keys():
                    raise ValueError(
                        'The key \'{0}\' is not allowed in the content dict. '
                        'Only these keys are allowed: {1}'.
                        format(key, str(self._translation.keys())))
            self._content = content
        # Instantiate from xml
        else:
            for key, value in self._translation.items():
                result = xml.find(ns_tag(*value))
                if result is None:
                    self._content[key] = None
                else:
                    # The xml objects should contain utf-8 internally
                    self._content[key] = really_unicode(result.text)

    @property
    def item_id(self):  # pylint: disable=C0103
        """Returns the id.

        The id is extracted as the part of the URI after the first # character.
        For the few data types where that is not correct, this method should
        be overwritten.

        """
        out = self._content.get('uri')
        if out is not None:
            out = out[out.index('#') + 1:]
        return out

    @property
    def didl_metadata(self):
        """Produce the DIDL metadata XML.

        This method depends, as a minimum, on the
        :py:attr:`~.MusicLibraryItem.item_id` attribute (and via that the
        :py:attr:`~.MusicLibraryItem.uri` attribute. The values for ``class``
        and ``title`` will also be used if present, but may not be necessary.
        The metadata will be on the form:

        .. code :: xml

         <DIDL-Lite ..NS_INFO..>
           <item id="...self.item_id..."
             parentID="...self._parent_id..." restricted="true">
             <dc:title>...self.title...</dc:title>
             <upnp:class>...self.class_info...</upnp:class>
             <desc id="cdudn"
               nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">
               RINCON_AssociatedZPUDN
             </desc>
           </item>
         </DIDL-Lite>

        """
        # Check the id_info method and via that, the self.content['uri'] value
        if self.item_id is None:
            raise CannotCreateDIDLMetadata(
                'DIDL Metadata cannot be created when if_info returns None '
                '(most likely because uri is not set)')

        # Main element
        xml = XML.Element('DIDL-Lite')
        # Item sub element
        item_attrib = \
            {'parentID': self._parent_id, 'restricted': 'true',
             'id': self.item_id}
        item = XML.SubElement(xml, 'item', item_attrib)
        # Add content from self._content to item
        for key in ['title', 'class']:
            element = XML.SubElement(
                item, ns_tag(self._translation[key][0], key))
            element.text = self._content[key]
        # Add the desc element
        desc_attrib = {'id': 'cdudn', 'nameSpace':
                       'urn:schemas-rinconnetworks-com:metadata-1-0/'}
        desc = XML.SubElement(item, 'desc', desc_attrib)
        desc.text = 'RINCON_AssociatedZPUDN'
        return xml

    @property
    def title(self):
        """Get and set the title as an unicode object."""
        return self._content['title']

    @title.setter
    def title(self, title):  # pylint: disable=C0111
        self._content['title'] = title

    @property
    def uri(self):
        """Get and set the URI as an unicode object."""
        return self._content['uri']

    @uri.setter
    def uri(self, uri):  # pylint: disable=C0111
        self._content['uri'] = uri

    @property
    def upnp_class(self):
        """Get and set the UPnP object class as an unicode object."""
        return self._content['class']

    @upnp_class.setter
    def upnp_class(self, upnp_class):  # pylint: disable=C0111
        self._content['class'] = upnp_class


class MLTrack(MusicLibraryItem):
    """Class that represents a music library track."""

    def __init__(self, xml=None, content=None):
        """Initialize translation dict and call the ``__init__`` method from
        :py:class:`.MusicLibraryItem`.

        MLTrack must be instantiated with EITHER an xml or a content argument.

        MLTrack uses the following content-key-to-xml-tag-and-namespace-
        translation:

        .. code-block:: python

            # key: (ns, tag)
            translation = {
                'title': ('dc', 'title'),
                'creator': ('dc', 'creator'),
                'album': ('upnp', 'album'),
                'album_art_uri': ('upnp', 'albumArtURI'),
                'uri': ('', 'res'),
                'original_track_number': ('upnp', 'originalTrackNumber'),
                'class': ('upnp', 'class')
            }

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (com.NS['']) element.
            Inside the item element are the (namespace, tag_name) elements
            described above in translation.
        :param content: A dictionary describing the track. This dictionary can
            only contain values for the keys described above in translation.
            The standard value for class is 'object.item.audioItem.musicTrack'

        """
        # name: (ns, tag)
        translation = {
            'title': ('dc', 'title'),
            'creator': ('dc', 'creator'),
            'album': ('upnp', 'album'),
            'album_art_uri': ('upnp', 'albumArtURI'),
            'uri': ('', 'res'),
            'original_track_number': ('upnp', 'originalTrackNumber'),
            'class': ('upnp', 'class')
        }
        MusicLibraryItem.__init__(self, translation, xml, content)
        self._parent_id = 'A:TRACKS'

    @property
    def item_id(self):  # pylint: disable=C0103
        """Returns the id."""
        out = self._content.get('uri')
        if out is not None:
            out = out.replace('x-file-cifs', 'S')
        return out

    @property
    def creator(self):
        """Get and set the creator as an unicode object."""
        return self._content['creator']

    @creator.setter
    def creator(self, creator):  # pylint: disable=C0111
        self._content['creator'] = creator

    @property
    def album(self):
        """Get and set the method as an unicode object."""
        return self._content['album']

    @album.setter
    def album(self, album):  # pylint: disable=C0111
        self._content['album'] = album

    @property
    def album_art_uri(self):
        """Get and set the album art URI as an unicode object."""
        return self._content['album_art_uri']

    @album_art_uri.setter
    def album_art_uri(self, album_art_uri):  # pylint: disable=C0111
        self._content['album_art_uri'] = album_art_uri

    @property
    def original_track_number(self):
        """Get and set the original track number as an integer."""
        if self._content.get('original_track_number') is not None:
            return int(self._content['original_track_number'])
        else:
            return None

    @original_track_number.setter
    # pylint: disable=C0111
    def original_track_number(self, original_track_number):
        self._content['original_track_number'] = original_track_number


class MLAlbum(MusicLibraryItem):
    """Class that represents a music library album."""

    def __init__(self, xml=None, content=None):
        """Initialize translation dict and call the ``__init__`` method from
        :py:class:`.MusicLibraryItem`.

        MLAlbum must be instantiated with EITHER an xml or a content argument.

        MLAlbum uses the following content-key-to-xml-tag-and-namespace-
        translation:

        .. code-block :: python

            # key: (ns, tag)
            translation = {
                'title': ('dc', 'title'),
                'creator': ('dc', 'creator'),
                'album_art_uri': ('upnp', 'albumArtURI'),
                'uri': ('', 'res'),
                'class': ('upnp', 'class')
            }

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (com.NS['']). Inside the
            item element are the (namespace, tag_name) elements described above
            in translation.
        :param content: A dictionary describing the track. This dictionary can
            only contain values for the keys described above in translation.
            The standard value for class is 'object.container.album.musicAlbum'

        """
        # name: (ns, tag)
        self._translation = {
            'title': ('dc', 'title'),
            'creator': ('dc', 'creator'),
            'album_art_uri': ('upnp', 'albumArtURI'),
            'uri': ('', 'res'),
            'class': ('upnp', 'class')
        }
        MusicLibraryItem.__init__(self, self._translation, xml, content)
        self._parent_id = 'A:ALBUM'

    @property
    def creator(self):
        """Get and set the creator as an unicode object."""
        return self._content['creator']

    @creator.setter
    def creator(self, creator):  # pylint: disable=C0111
        self._content['creator'] = creator

    @property
    def album_art_uri(self):
        """Get and set the album art URI as an unicode object."""
        return self._content['album_art_uri']

    @album_art_uri.setter
    def album_art_uri(self, album_art_uri):  # pylint: disable=C0111
        self._content['album_art_uri'] = album_art_uri


class MLArtist(MusicLibraryItem):
    """Class that represents a music library artist."""

    def __init__(self, xml=None, content=None):
        """Call the ``__init__`` method from :py:class:`.MusicLibraryItem`.

        MLArtist must be instantiated with EITHER an xml or a content argument.

        MLArtist uses the default content-key-to-xml-tag-and-namespace-
        translation:

        .. code-block :: python

            # key: (ns, tag)
            translation = {
                'title': ('dc', 'title'),
                'uri': ('', 'res'),
                'class': ('upnp', 'class')
            }

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (com.NS['']). Inside the
            item element are the (namespace, tag_name) elements described above
            in translation.
        :param content: A dictionary describing the track. This dictionary can
            only contain values for the keys described above in translation.
            The standard value for class is
            'object.container.person.musicArtist'

        """
        MusicLibraryItem.__init__(self, xml=xml, content=content)
        self._parent_id = 'A:ARTIST'


class MLAlbumArtist(MusicLibraryItem):
    """Class that represents a music library album artist."""

    def __init__(self, xml=None, content=None):
        """Call the ``__init__`` method from :py:class:`.MusicLibraryItem`.

        MLAlbumArtist must be instantiated with EITHER an xml or a content
        argument.

        MLAlbumArtist uses the default content-key-to-xml-tag-and-namespace-
        translation:

        .. code-block :: python

            # key: (ns, tag)
            translation = {
                'title': ('dc', 'title'),
                'uri': ('', 'res'),
                'class': ('upnp', 'class')
            }

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (com.NS['']). Inside the
            item element are the (namespace, tag_name) elements described above
            in translation.
        :param content: A dictionary describing the track. This dictionary can
            only contain values for the keys described above in translation.
            The standard value for class is
            'object.container.person.musicArtist'

        """
        MusicLibraryItem.__init__(self, xml=xml, content=content)
        self._parent_id = 'A:ALBUMARTIST'


class MLGenre(MusicLibraryItem):
    """Class that represents a music library genre."""

    def __init__(self, xml=None, content=None):
        """Call the ``__init__`` method from :py:class:`.MusicLibraryItem`.

        MLGenre must be instantiated with EITHER an xml or a content argument.

        MLGenre uses the default content-key-to-xml-tag-and-namespace-
        translation:

        .. code-block :: python

            # key: (ns, tag)
            translation = {
                'title': ('dc', 'title'),
                'uri': ('', 'res'),
                'class': ('upnp', 'class')
            }

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (com.NS['']). Inside the
            item element are the (namespace, tag_name) elements described above
            in translation.
        :param content: A dictionary describing the track. This dictionary can
            only contain values for the keys described above in translation.
            The standard value for class is 'object.container.genre.musicGenre'

        """
        MusicLibraryItem.__init__(self, xml=xml, content=content)
        self._parent_id = 'A:GENRE'


class MLComposer(MusicLibraryItem):
    """Class that represents a music library composer."""

    def __init__(self, xml=None, content=None):
        """Call the ``__init__`` method from :py:class:`.MusicLibraryItem`.

        MLComposer must be instantiated with EITHER an xml or a content
        argument.

        MLComposer uses the default content-key-to-xml-tag-and-namespace-
        translation:

        .. code-block :: python

            # key: (ns, tag)
            translation = {
                'title': ('dc', 'title'),
                'uri': ('', 'res'),
                'class': ('upnp', 'class')
            }

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (com.NS['']). Inside the
            item element are the (namespace, tag_name) elements described above
            in translation.
        :param content: A dictionary describing the track. This dictionary can
            only contain values for the keys described above in translation.
            The standard value for class is 'object.container.person.composer'

        """
        MusicLibraryItem.__init__(self, xml=xml, content=content)
        self._parent_id = 'A:COMPOSER'


class MLPlaylist(MusicLibraryItem):
    """Class that represents a music library play list"""

    def __init__(self, xml=None, content=None):
        """Call the ``__init__`` method from :py:class:`.MusicLibraryItem`.

        MLPlaylist must be instantiated with EITHER an xml or a content
        argument.

        MLPlaylist uses default following content-key-to-xml-tag-and-namespace-
        translation:

        .. code-block :: python

            # key: (ns, tag)
            translation = {
                'title': ('dc', 'title'),
                'uri': ('', 'res'),
                'class': ('upnp', 'class')
            }

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (com.NS['']). Inside the
            item element are the (namespace, tag_name) elements described above
            in translation.
        :param content: A dictionary describing the track. This dictionary can
            only contain values for the keys described above in translation.
            The standard value for class is
            'object.container.playlistContainer'

        """
        MusicLibraryItem.__init__(self, xml=xml, content=content)
        self._parent_id = 'A:PLAYLISTS'

    @property
    def item_id(self):  # pylint: disable=C0103
        """ Getter method for the id """
        out = self._content.get('uri')
        if out is not None:
            out = out.replace('x-file-cifs', 'S')
        return out


class MLShare(MusicLibraryItem):
    """Class that represents a music library share."""

    def __init__(self, xml=None, content=None):
        """Call the ``__init__`` method from :py:class:`.MusicLibraryItem`.

        MLShare must be instantiated with EITHER an xml or a content argument.

        MLShare uses the default content-key-to-xml-tag-and-namespace-
        translation:

        .. code-block :: python

            # key: (ns, tag)
            translation = {
                'title': ('dc', 'title'),
                'uri': ('', 'res'),
                'class': ('upnp', 'class')
            }

        :param xml: An :py:class:`xml.etree.ElementTree.Element` object. The
            top element usually is a DIDL-LITE item (com.NS['']). Inside the
            item element are the (namespace, tag_name) elements described above
            in translation.
        :param content: A dictionary describing the track. This dictionary can
            only contain values for the keys described above in translation.
            The standard value for class is 'object.container'

        """
        MusicLibraryItem.__init__(self, xml=xml, content=content)
        self._parent_id = 'S:'


PARENT_ID_TO_CLASS = {'A:TRACKS': MLTrack, 'A:ALBUM': MLAlbum,
                      'A:ARTIST': MLArtist, 'A:ALBUMARTIST': MLAlbumArtist,
                      'A:GENRE': MLGenre, 'A:COMPOSER': MLComposer,
                      'A:PLAYLISTS': MLPlaylist, 'S:': MLShare}
