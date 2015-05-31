# -*- coding: utf-8 -*-
# pylint: disable=star-args, too-many-arguments, fixme


""" This module contains classes for handling DIDL-Lite metadata.

This is the XML schema used by Sonos for carrying metadata representing many
items such as tracks, playlists, composers, albums etc.


"""

# It tries to follow the class hierarchy provided by the DIDL-Lite schema
# described in the UPnP Spec, especially that for the ContentDirectory Service

# Although Sonos uses ContentDirectory v1, the document for v2 is more helpful:
# http://upnp.org/specs/av/UPnP-av-ContentDirectory-v2-Service.pdf


from __future__ import unicode_literals

import sys
import warnings
warnings.simplefilter('always', DeprecationWarning)
import textwrap

from .xml import XML, ns_tag

from .exceptions import DIDLMetadataError
from .utils import really_unicode


###############################################################################
# MISC HELPER FUNCTIONS                                                       #
###############################################################################

def to_didl_string(*args):
    """ Convert any number of DIDLObjects to a unicode xml string.

    Args:
        *args (DidlObject): One or more DidlObject (or subclass) instances

    Returns:
        str: A unicode string of the form <DIDL-Lite ...>...</DIDL-Lite>
            representing the instances
    """
    didl = XML.Element(
        'DIDL-Lite',
        {
            'xmlns': "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
            'xmlns:dc': "http://purl.org/dc/elements/1.1/",
            'xmlns:upnp': "urn:schemas-upnp-org:metadata-1-0/upnp/",
        })
    for arg in args:
        didl.append(arg.to_element())
    if sys.version_info[0] == 2:
        return XML.tostring(didl)
    else:
        return XML.tostring(didl, encoding='unicode')


def from_didl_string(string):
    """ Convert a unicode xml string to a list of DIDLObjects.

    Arg:
        string (str): A unicode string containing an xml representation of one
            or more DIDL-Lite items (in the form  <DIDL-Lite ...>
            ...</DIDL-Lite> )

    Returns:
        list: A list of one or more instances of DIDLObject or a subclass
    """
    items = []
    root = XML.fromstring(string.encode('utf-8'))
    for elt in root:
        if elt.tag.endswith('item') or elt.tag.endswith('container'):
            item_class = elt.findtext(ns_tag('upnp', 'class'))
            try:
                cls = _DIDL_CLASS_TO_CLASS[item_class]
            except KeyError:
                raise DIDLMetadataError("Unknown UPnP class: %s" % item_class)
            items.append(cls.from_element(elt))
        else:
            # <desc> elements are allowed as an immediate child of <DIDL-Lite>
            # according to the spec, but I have not seen one there in Sonos, so
            # we treat them as illegal. May need to fix this if this
            # causes problems.
            raise DIDLMetadataError("Illegal child of DIDL element: <%s>"
                                    % elt.tag)
    return items


###############################################################################
# DIDL RESOURCE                                                               #
###############################################################################

class DidlResource(object):

    """ Identifies a resource, typically some type of a binary asset, such as
    a song.

    A 'res' element contains a uri that identifies the resource.
    """

    # Adapted from a class taken from the Python Brisa project - MIT licence.

    # pylint: disable=too-many-instance-attributes
    def __init__(self, uri, protocol_info, import_uri=None, size=None,
                 duration=None, bitrate=None, sample_frequency=None,
                 bits_per_sample=None, nr_audio_channels=None, resolution=None,
                 color_depth=None, protection=None):
        """ Constructor for the Resource class.

        Args:
            uri (str): value of the res tag, typically a URI. It MUST be
                properly escaped URIs as described in RFC 239
            protocol_info (str):  A string in the form a:b:c:d that
                identifies the streaming or transport protocol for
                transmitting the resource. A value is required. For more
                information see section 2.5.2 at
                http://upnp.org/specs/av/UPnP-av-ConnectionManager-v1-Service.pdf
            import_uri (str, optional): uri locator for resource update
            size (int, optional): size in bytes
            duration (str, optional): duration of the playback of the res
                at normal speed (H*:MM:SS:F* or H*:MM:SS:F0/F1)
            bitrate (int, optional): bitrate in bytes/second
            sample_frequency (int, optional): sample frequency in Hz
            bits_per_sample (int, optional): bits per sample
            nr_audio_channels (int, optional): number of audio channels
            resolution (str, optional): resolution of the resource (X*Y)
            color_depth (int, optional): color depth in bits
            protection (str, optional): statement of protection type

        """
        # Of these attributes, only uri, protocol_info and duration have been
        # spotted 'in the wild'
        self.uri = uri
        # Protocol info is in the form a:b:c:d - see
        # sec 2.5.2 at
        # http://upnp.org/specs/av/UPnP-av-ConnectionManager-v1-Service.pdf
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

    @classmethod
    def from_element(cls, element):
        """ Set the resource properties from a <res> element.

        Arg:
            element (Element): An ElementTree Element
        """
        def _int_helper(name):
            """Try to convert the name attribute to an int, or None."""
            result = element.get(name)
            if result is not None:
                try:
                    return int(result)
                except ValueError:
                    raise ValueError(
                        'Could not convert {0} to an integer'.format(name))
            else:
                return None

        content = {}
        # required
        content['protocol_info'] = element.get('protocolInfo')
        if content['protocol_info'] is None:
            raise Exception('Could not create Resource from Element: '
                            'protocolInfo not found (required).')
        # Optional
        content['import_uri'] = element.get('importUri')
        content['size'] = _int_helper('size')
        content['duration'] = element.get('duration')
        content['bitrate'] = _int_helper('bitrate')
        content['sample_frequency'] = _int_helper('sampleFrequency')
        content['bits_per_sample'] = _int_helper('bitsPerSample')
        content['nr_audio_channels'] = _int_helper('nrAudioChannels')
        content['resolution'] = element.get('resolution')
        content['color_depth'] = _int_helper('colorDepth')
        content['protection'] = element.get('protection')
        content['uri'] = element.text
        return cls(**content)

    def __repr__(self):
        return '<{0} \'{1}\' at {2}>'.format(self.__class__.__name__,
                                             self.uri,
                                             hex(id(self)))

    def __str__(self):
        return self.__repr__()

    def to_element(self):
        """ Return an ElementTree Element based on this resource."""
        if not self.protocol_info:
            raise Exception('Could not create Element for this resource: '
                            'protocolInfo not set (required).')
        root = XML.Element('res')

        # Required
        root.attrib['protocolInfo'] = self.protocol_info
        # Optional
        if self.import_uri is not None:
            root.attrib['importUri'] = self.import_uri
        if self.size is not None:
            root.attrib['size'] = str(self.size)
        if self.duration is not None:
            root.attrib['duration'] = self.duration
        if self.bitrate is not None:
            root.attrib['bitrate'] = str(self.bitrate)
        if self.sample_frequency is not None:
            root.attrib['sampleFrequency'] = str(self.sample_frequency)
        if self.bits_per_sample is not None:
            root.attrib['bitsPerSample'] = str(self.bits_per_sample)
        if self.nr_audio_channels is not None:
            root.attrib['nrAudioChannels'] = str(self.nr_audio_channels)
        if self.resolution is not None:
            root.attrib['resolution'] = self.resolution
        if self.color_depth is not None:
            root.attrib['colorDepth'] = str(self.color_depth)
        if self.protection is not None:
            root.attrib['protection'] = self.protection

        root.text = self.uri
        return root


###############################################################################
# BASE OBJECTS                                                                #
###############################################################################

# a mapping which will be used to look up the relevant class from the
# DIDL item class
_DIDL_CLASS_TO_CLASS = {}


class DidlMetaClass(type):

    """Meta class for all Didl objects."""

    def __new__(mcs, name, bases, attrs):
        """Create a new instance.

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

    """Abstract base class for all DIDL-Lite items.

    You should not need to instantiate this.

    Attributes:
        item_class (str): The DIDL Lite class for this object
        tag (str): The XML element tag name used for this instance
        _translation (dict): A dict used to translate between instance
            attribute names and XML tags/namespaces. It also serves to define
            the allowed tags/attributes for this instance. Overridden and
            extended by subclasses.

    """

    item_class = 'object'
    tag = 'item'
    # key: attribute_name: (ns, tag)
    _translation = {
        'creator': ('dc', 'creator'),
        'write_status': ('upnp', 'writeStatus'),
    }

    def __init__(self, title, parent_id, item_id, restricted=True,
                 resources=None, desc='RINCON_AssociatedZPUDN', **kwargs):
        r"""Construct and initialize a DidlObject.

        Args:
            title (str): The title for the item
            parent_id (str): The parent ID for the item
            item_id (str): The ID for the item
            restricted (bool): Whether the item can be modified
            resources (list): A list of resources for this object
            desc (str): A didl descriptor, default RINCON_AssociatedZPUDN. This
                is not the same as "description"! It is used for identifying
                the relevant music service
            **kwargs: Extra metadata. What is allowed depends on the
                _translation class attribute, which in turn depends on the DIDL
                class

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
        # Restricted is a compulsory attribute, but is almost always True for
        # Sonos. (Only seen it 'false' when browsing favorites)
        self.restricted = restricted

        # Resources is multi-valued, and dealt with separately
        self.resources = [] if resources is None else resources

        # According to the spec, there may be one or more desc values. Sonos
        # only seems to use one, so we won't bother with a list
        self.desc = desc

        for key, value in kwargs.items():
            # For each attribute, check to see if this class allows it
            if key not in self._translation:
                raise ValueError(
                    'The key \'{0}\' is not allowed as an argument. Only '
                    'these keys are allowed: parent_id, item_id, title, '
                    'restricted, resources, desc'
                    ' {1}'.format(key, ', '.join(self._translation.keys())))
            # It is an allowed attribute. Set it as an attribute on self, so
            # that it can be accessed as Classname.attribute in the normal
            # way.
            setattr(self, key, value)

    @classmethod
    def from_element(cls, element):
        """Create an instance of this class from an ElementTree xml Element.

        An alternative constructor. The element must be a DIDL-Lite <item> or
        <container> element, and must be properly namespaced.

        Arg:
            xml (Element): An :py:class:`xml.etree.ElementTree.Element` object.

        """
        # Check we have the right sort of element. tag can be an empty string
        # which indicates that any tag is allowed (see eg the musicAlbum DIDL
        # class)
        if not element.tag.endswith(cls.tag):
            raise DIDLMetadataError(
                "Wrong element. Expected '<{0}>',"
                " got '<{1}>'".format(cls.tag, element.tag))
        # and that the upnp matches what we are expecting
        item_class = element.find(ns_tag('upnp', 'class')).text
        if item_class != cls.item_class:
            raise DIDLMetadataError(
                "UPnP class is incorrect. Expected '{0}',"
                " got '{1}'".format(cls.item_class, item_class))

        # parent_id, item_id  and restricted are stored as attibutes on the
        # element
        item_id = really_unicode(element.get('id', None))
        if item_id is None:
            raise DIDLMetadataError("Missing id attribute")
        parent_id = really_unicode(element.get('parentID', None))
        if parent_id is None:
            raise DIDLMetadataError("Missing parentID attribute")
        restricted = element.get('restricted', None)
        if restricted is None:
            raise DIDLMetadataError("Missing restricted attribute")
        restricted = True if restricted in [1, 'true', 'True'] else False

        # There must be a title. According to spec, it should be the first
        # child, but Sonos does not abide by this
        title_elt = element.find(ns_tag('dc', 'title'))
        if title_elt is None:
            raise DIDLMetadataError(
                "Missing title element")
        title = really_unicode(title_elt.text)

        # Deal with any resource elements
        resources = []
        for res_elt in element.findall(ns_tag('', 'res')):
            resources.append(
                DidlResource.from_element(res_elt))

        # and the desc element (There is only one in Sonos)
        desc = element.findtext(ns_tag('', 'desc'))

        # Get values of the elements listed in _translation and add them to
        # the content dict
        content = {}
        for key, value in cls._translation.items():
            result = element.findtext(ns_tag(*value))
            if result is not None:
                # We store info as unicode internally.
                content[key] = really_unicode(result)

        # Convert type for original track number
        if content.get('original_track_number') is not None:
            content['original_track_number'] = \
                int(content['original_track_number'])

        # Now pass the content dict we have just built to the main
        # constructor, as kwargs, to create the object
        return cls(title=title, parent_id=parent_id, item_id=item_id,
                   restricted=restricted, resources=resources, desc=desc,
                   **content)

    @classmethod
    def from_dict(cls, content):
        """Create an instance from a dict.

        An alternative constructor. Equivalent to DidlObject(**content).

        Arg:
            content (dict): Dict containing metadata information.Required and
            valid arguments are the same as for the ``__init__`` method.

        """
        # Do we really need this constructor? Could use DidlObject(**content)
        # instead.
        return cls(**content)

    def __eq__(self, playable_item):
        """Compare with another ``playable_item``.

        Returns:
            (bool): True if items are equal, else False
        """
        if not isinstance(playable_item, DidlObject):
            return False
        return self.to_dict() == playable_item.to_dict()

    def __ne__(self, playable_item):
        """Compare with another ``playable_item``.

        Returns:
            (bool): True if items are unequal, else False
        """
        if not isinstance(playable_item, DidlObject):
            return True
        return self.to_dict() != playable_item.to_dict()

    def __repr__(self):
        """Return the repr value for the item.

        The repr is of the form::

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

    def to_dict(self):
        """Return the dict representation of the instance."""
        content = {}
        # Get the value of each attribute listed in _translation, and add it
        # to the content dict
        for key in self._translation:
            if hasattr(self, key):
                content[key] = getattr(self, key)
        # also add parent_id, item_id, restricted, title and resources because
        # they are not listed in _translation
        content['parent_id'] = self.parent_id
        content['item_id'] = self.item_id
        content['restricted'] = self.restricted
        content['title'] = self.title
        if self.resources != []:
            content['resources'] = self.resources
        content['desc'] = self.desc
        return content

    def to_element(self, include_namespaces=False):
        """Return an ElementTree Element representing this instance.

        Arg:
            include_namespaces (bool, optional): If True, include xml
                namespace attributes on the root element

        Return:
            An ElementTree Element

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
        elt_attrib = {}
        if include_namespaces:
            elt_attrib.update({
                'xmlns': "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
                'xmlns:dc': "http://purl.org/dc/elements/1.1/",
                'xmlns:upnp': "urn:schemas-upnp-org:metadata-1-0/upnp/",
            })
        elt_attrib.update({
            'parentID': self.parent_id,
            'restricted': 'true' if self.restricted else 'false',
            'id': self.item_id
        })
        elt = XML.Element(self.tag, elt_attrib)

        # Add the title, which should always come first, according to the spec
        XML.SubElement(elt, 'dc:title').text = self.title

        # Add in any resources
        for resource in self.resources:
            elt.append(resource.to_element())

        # Add the rest of the metadata attributes (i.e all those listed in
        # _translation) as sub-elements of the item element.
        for key, value in self._translation.items():
            if hasattr(self, key):
                # Some attributes have a namespace of '', which means they
                # are in the default namespace. We need to handle those
                # carefully
                tag = "%s:%s" % value if value[0] else "%s" % value[1]
                XML.SubElement(elt, tag).text = ("%s" % getattr(self, key))
        # Now add in the item class
        XML.SubElement(elt, 'upnp:class').text = self.item_class

        # And the desc element
        desc_attrib = {'id': 'cdudn', 'nameSpace':
                       'urn:schemas-rinconnetworks-com:metadata-1-0/'}
        desc_elt = XML.SubElement(elt, 'desc', desc_attrib)
        desc_elt.text = self.desc

        return elt


###############################################################################
# OBJECT.ITEM HIERARCHY                                                       #
###############################################################################

class DidlItem(DidlObject):

    """A basic content directory item."""

    # The spec allows for an option 'refID' attribute, but we do not handle it

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

    """An audio item."""

    item_class = 'object.item.audioitem'
    _translation = DidlItem._translation.copy()
    _translation.update(
        {
            'genre': ('upnp', 'genre'),
            'description': ('dc', 'description'),
            'long_description': ('upnp', 'longDescription'),
            'publisher': ('dc', 'publisher'),
            'language': ('dc', 'language'),
            'relation': ('dc', 'relation'),
            'rights': ('dc', 'rights'),
        }
    )

# Browsing Sonos Favorites produces some odd looking DIDL-Lite. The object
# class is 'object.itemobject.item.sonos-favorite', which is probably a typo
# in Sonos' code somewhere.

# Here is an example:
# <?xml version="1.0" ?>
# <DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
#     xmlns:dc="http://purl.org/dc/elements/1.1/"
#     xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"
#     xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
#   <item id="FV:2/13" parentID="FV:2" restricted="false">
#     <dc:title>Shake It Off</dc:title>
#     <upnp:class>object.itemobject.item.sonos-favorite</upnp:class>
#     <r:ordinal>4</r:ordinal>
#     <res protocolInfo="sonos.com-spotify:*:audio/x-spotify:*">
#         x-sonos-spotify:spotify%3atrack%3a7n.......?sid=9&amp;flags=32</res>
#     <upnp:albumArtURI>http://o.scd.....</upnp:albumArtURI>
#     <r:type>instantPlay</r:type>
#     <r:description>By Taylor Swift</r:description>
#     <r:resMD>&lt;DIDL-Lite xmlns:dc=&quot;
#       http://purl.org/dc/elements/1.1/&quot;
#       xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot;
#       xmlns:r=&quot;urn:schemas-rinconnetworks-com:metadata-1-0/&quot;
#       xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot;&gt;
#       &lt;item id=&quot;00030020spotify%3atrack%3a7n9Q6b...74uCtajkddPt&quot;
#       parentID=&quot;0006006ctoplist%2ftracks%2fregion%2fGB&quot;
#       restricted=&quot;true&quot;&gt;&lt;dc:title&gt;Shake It Off
#       &lt;/dc:title&gt;&lt;upnp:class&gt;object.item.audioItem.musicTrack
#       &lt;/upnp:class&gt;&lt;desc id=&quot;cdudn&quot;
#       nameSpace=&quot;urn:schemas-rinconnetworks-com:metadata-1-0/&quot;&gt;
#       SA_RINCON2311_XXXXX&lt;/desc&gt;
#       &lt;/item&gt;
#       &lt;/DIDL-Lite&gt;
#     </r:resMD>
#   </item>
# </DIDL-Lite>

# Note the r:ordinal, r:type; r:description, r:resMD elements which are not
# seen (?) anywhere else
# We're ignoring this for the moment!


class DidlMusicTrack(DidlAudioItem):

    """Class that represents a music library track. """

    item_class = 'object.item.audioItem.musicTrack'
    # name: (ns, tag)
    _translation = DidlAudioItem._translation.copy()
    _translation.update(
        {
            'artist': ('upnp', 'artist'),
            'album': ('upnp', 'album'),
            'original_track_number': ('upnp', 'originalTrackNumber'),
            'playlist': ('upnp', 'playlist'),
            'contributor': ('dc', 'contributor'),
            'date': ('dc', 'date'),
        }
    )


class DidlAudioBroadcast(DidlAudioItem):

    """Class that represents an audio broadcast."""

    item_class = 'object.item.audioItem.audioBroadcast'
    _translation = DidlAudioItem._translation.copy()
    _translation.update(
        {
            'region': ('upnp', 'region'),
            'radio_call_sign': ('upnp', 'radioCallSign'),
            'radio_station_id': ('upnp', 'radioStationID'),
            'channel_nr': ('upnp', 'channelNr'),

        }
    )


class DidlAudioBroadcastFavorite(DidlAudioBroadcast):

    """Class that represents an audio broadcast sonos favorite."""

    # Note: The sonos-favorite part of the class spec obviously isn't part of
    # the DIDL spec, so just assume that it has the same definition as the
    # regular object.item.audioItem.audioBroadcast

    item_class = 'object.item.audioItem.audioBroadcast.sonos-favorite'


###############################################################################
# OBJECT.CONTAINER HIERARCHY                                                  #
###############################################################################

class DidlContainer(DidlObject):

    """Class that represents a music library container.  """

    item_class = 'object.container'
    tag = 'container'
    # We do not implement createClass or searchClass. Not used by Sonos??
    # TODO: handle the 'childCount' element.


class DidlAlbum(DidlContainer):

    """A content directory album."""

    item_class = 'object.container.album'
    # name: (ns, tag)
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            'description': ('dc', 'description'),
            'long_description': ('upnp', 'longDescription'),
            'publisher': ('dc', 'publisher'),
            'contributor': ('dc', 'contributor'),
            'date': ('dc', 'date'),
            'relation': ('dc', 'relation'),
            'rights': ('dc', 'rights'),
        }
    )


class DidlMusicAlbum(DidlAlbum):

    """Class that represents a music library album. """

    item_class = 'object.container.album.musicAlbum'
    # According to the spec, all musicAlbums should be represented in
    # XML by a <container> tag. Sonos sometimes uses <container> and
    # sometimes uses <item>. Set the tag type to '' to indicate that
    # either is allowed.
    tag = ''
    # name: (ns, tag)
    # pylint: disable=protected-access
    _translation = DidlAudioItem._translation.copy()
    _translation.update(
        {
            'artist': ('upnp', 'artist'),
            'genre': ('upnp', 'genre'),
            'producer': ('upnp', 'producer'),
            'toc': ('upnp', 'toc'),
            'album_art_uri': ('upnp', 'albumArtURI'),
        }
    )


class DidlMusicAlbumFavorite(DidlAlbum):

    """Class that represents a Sonos favorite music library album.

    This class is not part of the DIDL spec and is Sonos specific.

    """

    item_class = 'object.container.album.musicAlbum.sonos-favorite'
    # Despite the fact that the item derives from object.container, it's
    # XML does not include a <container> tag, but an <item> tag. This seems
    # to be an error by Sonos.
    tag = 'item'


class DidlMusicAlbumCompilation(DidlAlbum):

    """Class that represents a Sonos favorite music library compilation.

    This class is not part of the DIDL spec and is Sonos specific.

    """
    # These classes appear when browsing the library and Sonos has been set
    # to group albums using compilations.
    # See https://github.com/SoCo/SoCo/issues/280
    item_class = 'object.container.album.musicAlbum.compilation'
    tag = 'container'


class DidlPerson(DidlContainer):

    """A content directory class representing a person."""

    item_class = 'object.container.person'
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            'language': ('dc', 'language'),
        }
    )


class DidlComposer(DidlPerson):

    """Class that represents a music library composer."""

    # Not in the DIDL-Lite spec. Sonos specific??

    item_class = 'object.container.person.composer'


class DidlMusicArtist(DidlPerson):

    """Class that represents a music library artist."""

    item_class = 'object.container.person.musicArtist'
    # name: (ns, tag)
    _translation = DidlPerson._translation.copy()
    _translation.update(
        {
            'genre': ('upnp', 'genre'),
            'artist_discography_uri': ('upnp', 'artistDiscographyURI'),
        }
    )


class DidlAlbumList(DidlContainer):

    """Class that represents a music library album list."""

    # This does not appear (that I can find) in the DIDL-Lite specs.
    # Presumably Sonos specific
    item_class = 'object.container.albumlist'


class DidlPlaylistContainer(DidlContainer):

    """Class that represents a music library play list."""

    item_class = 'object.container.playlistContainer'
    # name: (ns, tag)
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            'artist': ('upnp', 'artist'),
            'genre': ('upnp', 'genre'),
            'long_description': ('upnp', 'longDescription'),
            'producer': ('dc', 'producer'),
            'contributor': ('dc', 'contributor'),
            'description': ('dc', 'description'),
            'date': ('dc', 'date'),
            'language': ('dc', 'language'),
            'rights': ('dc', 'rights'),
        }
    )


class DidlSameArtist(DidlPlaylistContainer):

    """Class that represents all tracks by a single artist.

    This type is returned by browsing an artist or a composer

    """

    # Not in the DIDL-Lite spec. Sonos specific?
    item_class = 'object.container.playlistContainer.sameArtist'


class DidlGenre(DidlContainer):

    """A content directory class representing a general genre."""

    item_class = 'object.container.genre'
    # name: (ns, tag)
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            'genre': ('upnp', 'genre'),
            'long_description': ('upnp', 'longDescription'),
            'description': ('dc', 'description'),
        }
    )


class DidlMusicGenre(DidlGenre):

    """Class that represents a music genre."""

    item_class = 'object.container.genre.musicGenre'


###############################################################################
# SPECIAL LISTS                                                               #
###############################################################################

class ListOfMusicInfoItems(list):

    """Abstract container class for a list of music information items."""

    def __init__(self, items, number_returned, total_matches, update_id):
        super(ListOfMusicInfoItems, self).__init__(items)
        self._metadata = {
            'item_list': list(items),
            'number_returned': number_returned,
            'total_matches': total_matches,
            'update_id': update_id,
        }

    def __getitem__(self, key):
        """Legacy get metadata by string key or list item(s) by index.

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
        """The number of returned matches."""
        return self._metadata['number_returned']

    @property
    def total_matches(self):
        """The number of total matches."""
        return self._metadata['total_matches']

    @property
    def update_id(self):
        """The update ID."""
        return self._metadata['update_id']


class SearchResult(ListOfMusicInfoItems):

    """Container class that represents a search or browse result.

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
        """The search type."""
        return self._metadata['search_type']


class Queue(ListOfMusicInfoItems):

    """Container class that represents a queue."""

    def __init__(self, items, number_returned, total_matches, update_id):
        super(Queue, self).__init__(
            items, number_returned, total_matches, update_id
        )

    def __repr__(self):
        return '{0}(items={1})'.format(
            self.__class__.__name__,
            super(Queue, self).__repr__(),
        )
