# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" DIDL-Lite classes (object, items, containers and etc).
"""

from __future__ import unicode_literals
from __future__ import absolute_import

import logging, sys
from xml.etree.ElementTree import _ElementInterface
from .xml import XML as ElementTree


log = logging.getLogger(__name__)

ns = {'didl': 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/',
      'dc': 'http://purl.org/dc/elements/1.1/',
      'upnp': 'urn:schemas-upnp-org:metadata-1-0/upnp/',
      'dlna': 'urn:schemas-dlna-org:metadata-1-0'}


def find(elt, namespace, key):
    f = elt.find('{%s}%s' % (ns[namespace], key))
    return f


def findall(elt, namespace, key):
    f = elt.findall('{%s}%s' % (ns[namespace], key))
    if f is None:
        return ()
    return f


def parse_xml(data):
    """ Parses XML in a unicode string into an ElementTree.

    @param data: raw XML data as unicode
    @type data: string

    @rtype: ElementTree
    """
    return ElementTree.fromstring(data.encode('utf-8'))


class Resource(object):
    """Represents a resource. Used for generating the DIDL XML messages.
    """

    def __init__(self, value='', protocol_info='', import_uri='', size=None,
                 duration='', bitrate=None, sample_frequency=None,
                 bits_per_sample=None, nr_audio_channels=None, resolution='',
                 color_depth=None, protection=''):
        """ Constructor for the Resource class.

        @param value: value of the res tag
        @param protocol_info: information about the protocol in the form
                              a:b:c:d
        @param import_uri: uri locator for resource update
        @param size: size in bytes
        @param duration: duration of the playback of the res at normal speed
                         (H*:MM:SS:F* or H*:MM:SS:F0/F1)
        @param bitrate: bitrate in bytes/second
        @param sample_frequency: sample frequency in Hz
        @param bits_per_sample: bits per sample
        @param nr_audio_channels: number of audio channels
        @param resolution: resolution of the resource (X*Y)
        @param color_depth: color depth in bits
        @param protection: statement of protection type

        @type protocol_info: string
        @type import_uri: string
        @type size: int
        @type duration: string
        @type bitrate: int
        @type sample_frequency: int
        @type bits_per_sample: int
        @type nr_audio_channels: int
        @type resolution: string
        @type color_depth: int
        @type protection: string
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
            raise Exception('Could not create Resource from Element: '\
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
            raise Exception('Could not create Element for this resource: '\
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


# upnp:writeStatus possible values
WRITE_STATUS_NOT_WRITABLE, WRITE_STATUS_WRITABLE, WRITE_STATUS_PROTECTED, \
WRITE_STATUS_UNKNOWN, WRITE_STATUS_MIXED = ('NOT_WRITABLE', 'WRITABLE',
'PROTECTED', 'UNKNOWN', 'MIXED')


class Object(object):
    """ Root class and most basic class of the content directory class
    hierarchy.
    """

    upnp_class = 'object'
    element_name = 'object'

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE):
        """ Constructor for the Object class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        """
        self.resources = []
        self.object_id = object_id
        self.parent_id = parent_id
        self.title = title
        self.creator = creator
        self.restricted = restricted
        self.write_status = write_status


    def add_resource(self, res):
        """ Adds a resource to the object.
        """
        if res not in self.resources:
            self.resources.append(res)

    def from_element(self, elt):
        """ Sets the object properties from an element.
        """
        req_attr_not_present = 'Could not create Object from Element: %s '\
                               'attribute not present (required).'

        # Check required attributes
        if 'id' not in elt.attrib:
            raise Exception(req_attr_not_present % 'object_id')
        if 'parentID' not in elt.attrib:
            raise Exception(req_attr_not_present % 'parentID')
        if 'restricted' not in elt.attrib:
            raise Exception(req_attr_not_present % 'restricted')

        upnp_class_elt = find(elt, 'upnp', 'class')
        if not upnp_class_elt.text:
            raise Exception(req_attr_not_present % 'upnp:class')
        title_elt = find(elt, 'dc', 'title')
        if not title_elt.text:
            raise Exception(req_attr_not_present % 'dc:title')

        self.element_name = elt.tag
        self.resources = []

        # Required
        self.object_id = elt.attrib['id']
        self.parent_id = elt.attrib['parentID']
        self.restricted = {True: 'true', False: 'false'}\
                           .get(elt.attrib['restricted'], True)
        self.upnp_class = upnp_class_elt.text
        self.title = title_elt.text

        # Optional
        write_status_elt = find(elt, 'upnp', 'writeStatus')
        if write_status_elt:
            self.write_status = write_status_elt.text
        creator_elt = find(elt, 'dc', 'creator')
        if creator_elt is not None:
            self.creator = creator_elt.text

        for res in findall(elt, 'didl', 'res'):
            self.resources.append(\
                Resource.from_string(ElementTree.tostring(res)))

    @classmethod
    def from_string(cls, xml_string):
        """ Returns an instance generated from an xml unicode string.
        """
        instance = cls()
        elt = parse_xml(xml_string)
        instance.from_element(elt)
        return instance

    def to_didl_element(self):
        """ Returns an Element based on this instance.
        """
        root = ElementTree.Element(self.element_name)
        root.attrib['id'] = str(self.object_id)
        root.attrib['parentID'] = str(self.parent_id)
        ElementTree.SubElement(root, 'dc:title').text = self.title
        ElementTree.SubElement(root, 'upnp:class').text = self.upnp_class

        if self.restricted:
            root.attrib['restricted'] = 'true'
        else:
            root.attrib['restricted'] = 'false'

        if self.creator:
            ElementTree.SubElement(root, 'dc:creator').text = self.creator
        if self.write_status:
            ElementTree.SubElement(root, 'upnp:writeStatus').text = \
                self.write_status

        for r in self.resources:
            root.append(r.to_didl_element())

        return root

    def to_string(self):
        """ String representation of this object.
        """
        return ElementTree.tostring(self.to_didl_element())


class SearchClass(object):
    """ Instances of this class may be passed to search_classes parameter of
    Container constructors.
    """

    def __init__(self, class_name, include_derived=False,
                 class_friendly_name=''):
        self.class_name = class_name
        self.class_friendly_name = class_friendly_name
        self.include_derived = include_derived

    def get_element(self):
        if not self.include_derived:
            raise Exception('Could not create Element from SearchClass: '\
                            'includeDerived attribute missing (required).')

        elt = ElementTree.Element('upnp:searchClass')
        elt.attrib['includeDerived'] = {True: 'true', False: 'false'}\
                                       .get(self.include_derived, False)

        if self.class_friendly_name:
            elt.attrib['name'] = self.class_friendly_name

        elt.text = self.class_name
        return elt


class CreateClass(SearchClass):
    """ Instances of this class may be passed to create_classes parameter of
    Container constructors.
    """

    def get_element(self):
        if not self.include_derived:
            raise Exception('Could not create Element from CreateClass: '\
                            'includeDerived attribute missing (required).')

        elt = ElementTree.Element('upnp:createClass')
        elt.attrib['includeDerived'] = {True: 'true', False: 'false'}\
                                       .get(self.include_derived, False)

        if self.class_friendly_name:
            elt.attrib['name'] = self.class_friendly_name

        elt.text = self.class_name
        return elt


class Container(Object):
    """ An object that can contain other objects.
    """

    upnp_class = '%s%s' % (Object.upnp_class, '.container')
    element_name = 'container'
    create_class = None
    _count = 0

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 searchable=True, search_classes=None, create_classes=None):
        """ Constructor for the Container class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param searchable: if True, Search action can be performed upon the
                           container
        @param search_classes: list of SearchClass objects
        @param create_classes: list of CreateClass objects

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        """
        Object.__init__(self, object_id, parent_id, title, restricted, creator,
                        write_status)
        self.searchable = searchable
        self.search_classes = search_classes if search_classes else []
        self.create_classes = create_classes if create_classes else []
        self.containers = []
        self.items = []

    def _get_child_count(self):
        if self.containers or self.items:
            return len(self.containers) + len(self.items)
        return self._count

    def _set_child_count(self, c):
        self._count = c

    child_count = property(_get_child_count, _set_child_count)

    def from_element(self, elt):
        """ Sets Container attributes from an Element.
        """
        Object.from_element(self, elt)
        self.child_count = int(elt.attrib.get('childCount', '0'))
        self.searchable = elt.attrib.get('searchable', '0') in \
                                    ['True', 'true', '1']
        self.search_classes = []

        for s in findall(elt, 'upnp', 'searchClass'):
            self.search_classes.append(SearchClass(s.text,
                                                   s.attrib['includeDerived'],
                                                   s.attrib.get('name', '')))

        for c in findall(elt, 'upnp', 'createClass'):
            self.create_classes.append(CreateClass(c.text,
                                                   c.attrib['includeDerived'],
                                                   c.attrib.get('name', '')))

    def to_didl_element(self):
        """ Creates Element from this Container.
        """
        root = Object.to_didl_element(self)
        root.attrib['childCount'] = str(self.child_count)

        for s in self.search_classes:
            root.append(s.get_element())
        for c in self.create_classes:
            root.append(c.get_element())

        root.attrib['searchable'] = {True: 'true', False: 'false'}\
                                    .get(self.searchable)

        return root

    def add_item(self, item):
        """ Adds a item to the container.
        """
        if item not in self.items:
            self.items.append(item)
            item.parent_id = self.object_id

    def add_container(self, c):
        """ Adds a container to the container.
        """
        if c not in self.containers:
            self.containers.append(c)
            c.parent_id = self.object_id


class Item(Object):
    """ A class used to represent atomic (non-container) content
    objects.
    """
    upnp_class = '%s%s' % (Object.upnp_class, '.item')
    element_name = 'item'

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 ref_id=''):
        """ Constructor for the Item class.

        @param object_id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param ref_id: id property of the item being referred to

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        """
        Object.__init__(self, object_id, parent_id, title, restricted, creator,
                        write_status)
        self.ref_id = ref_id


    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Object.from_element(self, elt)
        self.ref_id = elt.attrib.get('refID', '')

    def to_didl_element(self):
        root = Object.to_didl_element(self)
        root.attrib['refID'] = self.ref_id
        return root

    @property
    def uri(self):
        if len(self.resources) > 0:
            return self.resources[0].value
        else:
            return ''


class AudioItem(Item):
    """ A piece of content that when rendered generates audio.
    """
    upnp_class = '%s%s' % (Item.upnp_class, '.audioItem')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE, ref_id='',
                 genres=None, description=None, long_description='',
                 publishers=None, language=None, relations=None, rights=None):
        """ Constructor for the Item class.

        @param object_id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param ref_id: id property of the item being referred to
        @param genres: genres to which the object belongs
        @param description: description
        @param long_description: long description
        @param publishers: entities responsible for making the resource
                           available
        @param language: language of the resource
        @param relations: related resources
        @param rights: rights held in and over the resource

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        @type genres: list
        @type description: string
        @type long_description: string
        @type publishers: list
        @type language: string
        @type relations: list
        @type rights: list
        """
        Item.__init__(self, object_id, parent_id, title, restricted, creator,
                      write_status, ref_id)
        self.genres = genres
        self.description = description
        self.long_description = long_description
        self.publishers = publishers if publishers else []
        self.language = language if language else []
        self.relations = relations
        self.rights = rights


    def from_element(self, elt):
        """ Sets AudioItem properties from an element.
        """
        Item.from_element(self, elt)
        long_desc_elt = find(elt, 'upnp', 'longDescription')
        desc_elt = find(elt, 'dc', 'description')

        self.genres = [g.text for g in findall(elt, 'upnp', 'genre')]
        self.publishers = [p.text for p in findall(elt, 'dc', 'publisher')]
        self.relations = [r.text for r in findall(elt, 'dc', 'relation')]
        self.rights = [r.text for r in findall(elt, 'dc', 'rights')]

        if long_desc_elt:
            self.long_description = long_desc_elt.text

        if desc_elt:
            self.description = desc_elt.text

    def to_didl_element(self):
        """ Create Element from AudioItem.
        """
        root = Item.to_didl_element(self)

        for g in self.genres:
            ElementTree.SubElement(root, 'upnp:genre').text = g
        for r in self.relations:
            ElementTree.SubElement(root, 'dc:relation').text = r
        for r in self.rights:
            ElementTree.SubElement(root, 'dc:rights').text = r
        for p in self.publishers:
            ElementTree.SubElement(root, 'dc:publisher').text = p

        if self.long_description:
            ElementTree.SubElement(root, 'upnp:longDescription').text =\
                self.long_description
        if self.description:
            ElementTree.SubElement(root, 'dc:description').text =\
                self.description
        if self.language:
            ElementTree.SubElement(root, 'dc:language').text = self.language

        return root


# upnp:storageMedium possible values
(STORAGE_MEDIUM_UNKNOWN, STORAGE_MEDIUM_DV, STORAGE_MEDIUM_MINI_DV,
STORAGE_MEDIUM_VHS, STORAGE_MEDIUM_W_VHS, STORAGE_MEDIUM_S_VHS,
STORAGE_MEDIUM_D_VHS, STORAGE_MEDIUM_VHSC, STORAGE_MEDIUM_VIDE08,
STORAGE_MEDIUM_HI8, STORAGE_MEDIUM_CD_ROM, STORAGE_MEDIUM_CD_DA,
STORAGE_MEDIUM_CD_R, STORAGE_MEDIUM_CD_RW, STORAGE_MEDIUM_VIDEO_CD,
STORAGE_MEDIUM_SACD, STORAGE_MEDIUM_MD_AUDIO, STORAGE_MEDIUM_MD_PICTURE,
STORAGE_MEDIUM_DVD_ROM, STORAGE_MEDIUM_DVD_VIDEO, STORAGE_MEDIUM_DVD_R,
STORAGE_MEDIUM_DVD_PLUS_RW, STORAGE_MEDIUM_DVD_RW, STORAGE_MEDIUM_DVD_RAM,
STORAGE_MEDIUM_DVD_AUDIO, STORAGE_MEDIUM_DAT, STORAGE_MEDIUM_LD,
STORAGE_MEDIUM_HDD) = (
    'UNKNOWN', 'DV', 'MINI-DV', 'VHS',
    'W-VHS', 'S-VHS', 'D-VHS', 'VHSC', 'VIDE08', 'HI8', 'CD-ROM', 'CD-DA',
    'CD-R', 'CD-RW', 'VIDEO-CD', 'SACD', 'MD-AUDIO', 'MD-PICTURE', 'DVD-ROM',
    'DVD-VIDEO', 'DVD-R', 'DVD+RW', 'DVD-RW', 'DVD-RAM', 'DVD-AUDIO', 'DAT',
    'LD', 'HDD')


class MusicTrack(AudioItem):
    """ A discrete piece of audio that should be interpreted as music.
    """
    upnp_class = '%s%s' % (AudioItem.upnp_class, '.musicTrack')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE, ref_id='',
                 genres=[], description='', long_description='', publishers=[],
                 language='', relations=[], rights=[], artists=[], albums=[],
                 original_track_number='', playlists=[], storage_medium='',
                 contributors=[], date=''):
        """ Constructor for the Item class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param ref_id: id property of the item being referred to
        @param genres: genres to which the object belongs
        @param description: description
        @param long_description: long description
        @param publishers: entities responsible for making the resource
                           available
        @param language: language of the resource
        @param relations: related resources
        @param rights: rights held in and over the resource
        @param artists: artists to which the object belongs
        @param albums: albums to which the object belongs
        @param original_track_number: original track number on an Audio CD or
                                      other medium
        @param playlists: names of the playlists to which the item belongs
        @param storage_medium: indicates the type of storage used for the
                               content. Possible values are enumerated on
                               STORAGE_MEDIUM_* variables
        @param contributors: entities responsible for making contributions to
                             the resource
        @param date: ISO 8601, form YYYY-MM-DD

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        @type genres: list
        @type description: string
        @type long_description: string
        @type publishers: list
        @type language: string
        @type relations: list
        @type rights: list
        @type artists: list
        @type albums: list
        @type original_track_number: int
        @type playlists: list
        @type storage_medium: string
        @type contributors: list
        @type date: string
        """
        AudioItem.__init__(
            self, object_id, parent_id, title, restricted, creator,
            write_status, ref_id, genres, description,
            long_description, publishers, language, relations,
            rights)
        self.artists = artists
        self.albums = albums
        self.original_track_number = original_track_number
        self.playlists = playlists
        self.storage_medium = storage_medium
        self.contributors = contributors
        self.date = date

    def from_element(self, elt):
        """ Set MusicTrack attributes from an element.
        """
        AudioItem.from_element(self, elt)
        self.artists = [a.text for a in findall(elt, 'upnp', 'artist')]
        self.albums = [a.text for a in findall(elt, 'upnp', 'album')]
        self.playlists = [p.text for p in findall(elt, 'upnp', 'playlist')]
        self.contributors = [c.text for c in findall(elt, 'dc', 'contributor')]
        trackno_elt = find(elt, 'upnp', 'originalTrackNumber')
        storage_elt = find(elt, 'upnp', 'storageMedium')
        date_elt = find(elt, 'dc', 'date')

        if trackno_elt:
            self.original_track_number = trackno_elt.text
        if storage_elt:
            self.storage_medium = storage_elt.text
        if date_elt:
            self.date = date_elt.text

    def to_didl_element(self):
        """ Create Element from MusicTrack.
        """
        root = AudioItem.to_didl_element(self)

        for a in self.artists:
            element = ElementTree.SubElement(root, 'upnp:artist')
            element.attrib['role'] = 'AlbumArtist'
            element.text = str(a)
        for a in self.albums:
            ElementTree.SubElement(root, 'upnp:album').text = a
        for p in self.playlists:
            ElementTree.SubElement(root, 'upnp:playlist').text = p
        for c in self.contributors:
            ElementTree.SubElement(root, 'dc:contributor').text = c
        if self.original_track_number:
            ElementTree.SubElement(root, 'upnp:originalTrackNumber').text = \
                str(self.original_track_number)
        if self.storage_medium:
            ElementTree.SubElement(root, 'upnp:storageMedium').text = \
                self.storage_medium
        if self.date:
            ElementTree.SubElement(root, 'dc:date').text = self.date

        return root


class AudioBroadcast(AudioItem):
    """ A continuous stream of audio.
    """
    upnp_class = '%s%s' % (AudioItem.upnp_class, '.audioBroadcast')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE, ref_id='',
                 genres=[], description='', long_description='', publishers=[],
                 language='', relations=[], rights=[], region='',
                 radio_call_sign='', radio_station_id='', radio_band='',
                 channel_nr=None):
        """ Constructor for the AudioBroadcast class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param ref_id: id property of the item being referred to
        @param genres: genres to which the object belongs
        @param description: description
        @param long_description: long description
        @param publishers: entities responsible for making the resource
                           available
        @param language: language of the resource
        @param relations: related resources
        @param rights: rights held in and over the resource
        @param region: identification of the region of the object (source)
        @param radio_call_sign: radio station call sign
        @param radio_station_id: identification of the station (e.g. broadcast
                                 frequency)
        @param radio_band: radio station frequency band
        @param channel_nr: identification of tuner channels

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        @type genres: list
        @type description: string
        @type long_description: string
        @type publishers: list
        @type language: string
        @type relations: list
        @type rights: list
        @type region: string
        @type radio_call_sign: string
        @type radio_station_id: string
        @type radio_band: string
        @type channel_nr: int
        """
        AudioItem.__init__(
            self, object_id, parent_id, title, restricted, creator,
            write_status, ref_id, genres, description,
            long_description, publishers, language, relations,
            rights)
        self.region = region
        self.radio_call_sign = radio_call_sign
        self.radio_station_id = radio_station_id
        self.radio_band = radio_band
        self.channel_nr = channel_nr

    def to_didl_element(self):
        """ Create element for this AudioBroadcast.
        """
        root = AudioItem.to_didl_element(self)

        if self.region:
            ElementTree.SubElement(root, 'upnp:region').text = self.region
        if self.radio_call_sign:
            ElementTree.SubElement(root, 'upnp:radioCallSign').text =\
                self.radio_call_sign
        if self.radio_station_id:
            ElementTree.SubElement(root, 'upnp:radioStationId').text =\
                self.radio_station_id
        if self.radio_band:
            ElementTree.SubElement(root, 'upnp:radioBand').text = \
                self.radio_band
        if self.channel_nr:
            ElementTree.SubElement(root, 'upnp:channelNr').text = \
                self.channel_nr

        return root

    def from_element(self, elt):
        """ Sets AudioBroadcast attributes and properties from an element.
        """
        AudioItem.from_element(self, elt)

        region_elt = find(elt, 'upnp', 'region')
        radio_sign_elt = find(elt, 'upnp', 'radioCallSign')
        radio_sid_elt = find(elt, 'upnp', 'radioStationId')
        radio_band_elt = find(elt, 'upnp', 'radioBand')
        channel_elt = find(elt, 'upnp', 'channelNr')

        if region_elt:
            self.region = region_elt.text
        if radio_sign_elt:
            self.radio_call_sign = radio_sign_elt.text
        if radio_sid_elt:
            self.radio_station_id = radio_sid_elt.text
        if radio_band_elt:
            self.radio_band = radio_band_elt.text
        if channel_elt:
            self.channel_nr = int(channel_elt.text)


class AudioBook(AudioItem):
    """ Discrete piece of audio that should be interpreted as a book.
    """
    upnp_class = '%s%s' % (AudioItem.upnp_class, '.audioBook')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE, ref_id='',
                 genres=[], description='', long_description='', publishers=[],
                 language='', relations=[], rights=[], storage_medium='',
                 producers=[], contributors=[], date=''):
        """ Constructor for the AudioBook class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param ref_id: id property of the item being referred to
        @param genres: genres to which the object belongs
        @param description: description
        @param long_description: long description
        @param publishers: entities responsible for making the resource
                           available
        @param language: language of the resource
        @param relations: related resources
        @param rights: rights held in and over the resource
        @param storage_medium: indicates the type of storage used for the
                               content. Possible values are enumerated on
                               STORAGE_MEDIUM_* variables
        @param producers: names of the producers
        @param contributors: entities responsible for making contributions to
                             the resource
        @param date: ISO 8601, form YYYY-MM-DD

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        @type genres: list
        @type description: string
        @type long_description: string
        @type publishers: list
        @type language: string
        @type relations: list
        @type rights: list
        @type storage_medium: string
        @type producers: list
        @type contributors: list
        @type date: string
        """
        AudioItem.__init__(self, object_id, parent_id, title, restricted, creator,
                           write_status, ref_id, genres, description,
                           long_description, publishers, language, relations,
                           rights)
        self.storage_medium = storage_medium
        self.producers = producers
        self.contributors = contributors
        self.date = date

    def from_element(self, elt):
        """ Sets AudioBook properties and attributes from an element.
        """
        AudioItem.from_element(self, elt)
        self.contributors = [c.text for c in findall(elt, 'dc', 'contributor')]
        self.producers = [p.text for p in find(elt, 'upnp', 'producer')]
        date_elt = find(elt, 'dc', 'date')
        storage_elt = find(elt, 'upnp', 'storageMedium')

        if storage_elt:
            self.storage_medium = storage_elt.text
        if date_elt:
            self.date = date_elt.text

    def to_didl_element(self):
        """ Create Element based on this AudioBook.
        """
        root = AudioItem.to_didl_element(self)

        for p in self.producers:
            ElementTree.SubElement(root, 'upnp:producer').text = p
        for c in self.contributors:
            ElementTree.SubElement(root, 'dc:contributor').text = c
        if self.date:
            ElementTree.SubElement(root, 'dc:date').text = self.date
        if self.storage_medium:
            ElementTree.SubElement(root, 'upnp:storageMedium').text =\
                self.storage_medium

        return root


class ImageItem(Item):
    """ An image representation. Content that when rendered generates some
    image.
    """
    upnp_class = '%s%s' % (Item.upnp_class, '.imageItem')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE, ref_id='',
                 long_description='', storage_medium='', rating='',
                 description='', publishers=[], date='', rights=[]):
        """ Constructor for the ImageItem class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param ref_id: id property of the item being referred to
        @param long_description: long description
        @param storage_medium: indicates the type of storage used for the
                               content. Possible values are enumerated on
                               STORAGE_MEDIUM_* variables
        @param rating: rating of the object's resource
        @param description: description
        @param publishers: entities responsible for making the resource
                           available
        @param date: ISO 8601, form YYYY-MM-DD
        @param rights: rights held in and over the resource

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        @type long_description: string
        @type storage_medium: string
        @type rating: string
        @type description: string
        @type publishers: list
        @type date: string
        @type rights: list
        """
        Item.__init__(self, object_id, parent_id, title, restricted, creator,
                      write_status, ref_id)
        self.long_description = long_description
        self.storage_medium = storage_medium
        self.rating = rating
        self.description = description
        self.date = date
        self.rights = rights

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Item.from_element(self, elt)
        long_desc_elt = find(elt, 'upnp', 'longDescription')
        storage_elt = find(elt, 'upnp', 'storageMedium')
        rating_elt = find(elt, 'upnp', 'rating')
        description_elt = find(elt, 'dc', 'description')
        date_elt = find(elt, 'dc', 'date')
        self.rights = [r.text for r in findall(elt, 'dc', 'rights')]

        if long_desc_elt:
            self.long_description = long_desc_elt.text
        if storage_elt:
            self.storage_medium = storage_elt.text
        if rating_elt:
            self.rating = rating_elt.text
        if description_elt:
            self.description = description_elt.text
        if date_elt:
            self.date = date_elt.text

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Item.to_didl_element(self)

        if self.long_description:
            ElementTree.SubElement(root, 'upnp:longDescription').text =\
                self.long_description
        if self.storage_medium:
            ElementTree.SubElement(root, 'upnp:storageMedium').text = \
                self.storage_medium
        if self.rating:
            ElementTree.SubElement(root, 'upnp:rating').text = self.rating
        if self.description:
            ElementTree.SubElement(root, 'dc:description').text =\
                self.description
        if self.date:
            ElementTree.SubElement(root, 'dc:date').text = self.date
        for r in self.rights:
            ElementTree.SubElement(root, 'dc:rights').text = r

        return root


class PlaylistItem(Item):
    """ Represents a playable sequence of resources (audio, video, image). Must
    have a resource element added for playback of the whole sequence.
    """
    upnp_class = '%s%s' % (Item.upnp_class, '.playlistItem')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE, ref_id='',
                 authors=[], protection='', long_description='',
                 storage_medium='', rating='', description='', publishers=[],
                 contributors=[], date='', relations=[], languages=[],
                 rights=[]):
        """ Constructor for the PlaylistItem class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param ref_id: id property of the item being referred to
        @param authors: list of author names
        @param protection: protection
        @param long_description: long description
        @param storage_medium: indicates the type of storage used for the
                               content. Possible values are enumerated on
                               STORAGE_MEDIUM_* variables
        @param rating: rating of the object's resource
        @param description: description
        @param publishers: list of publisher names
        @param contributors: entities responsible for making contributions to
                             the resource
        @param date: ISO 8601, form YYYY-MM-DD
        @param relations: list of relation (related resources names)
        @param languages: list of languages used
        @param rights: list of rights

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        @type authors: list
        @type protection: string
        @type long_description: string
        @type storage_medium: string
        @type rating: string
        @type description: string
        @type publishers: list
        @type contributors: list
        @type date: string
        @type relations: list
        @type languages: list
        @type rights: list
        """
        Item.__init__(self,object_id, parent_id, title, restricted, creator,
                      write_status, ref_id)
        self.authors = authors
        self.protection = protection
        self.long_description = long_description
        self.storage_medium = storage_medium
        self.rating = rating
        self.description = description
        self.publishers = publishers
        self.contributors = contributors
        self.date = date
        self.relations = relations
        self.languages = languages
        self.rights = rights

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Item.from_element(self, elt)
        protection_elt = find(elt, 'upnp', 'protection')
        long_desc_elt = find(elt, 'upnp', 'longDescription')
        storage_elt = find(elt, 'upnp', 'storageMedium')
        rating_elt = find(elt, 'upnp', 'rating')
        description_elt = find(elt, 'dc', 'description')
        date_elt = find(elt, 'dc', 'date')

        self.authors = [a.text for a in find(elt, 'upnp', 'author')]
        self.publishers = [p.text for p in findall(elt, 'dc', 'publisher')]
        self.contributors = [c.text for c in findall(elt, 'dc', 'contributor')]
        self.relations = [r.text for r in findall(elt, 'dc', 'relation')]
        self.languages = [l.text for l in findall(elt, 'dc', 'language')]
        self.rights = [r.text for r in findall(elt, 'dc', 'rights')]

        if protection_elt:
            self.protection = protection_elt.text
        if long_desc_elt:
            self.long_description = long_desc_elt.text
        if storage_elt:
            self.storage_medium = storage_elt.text
        if rating_elt:
            self.rating = rating_elt.text
        if description_elt:
            self.description = description_elt.text
        if date_elt:
            self.date = date_elt.text

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Item.to_didl_element(self)

        if self.protection:
            ElementTree.SubElement(root, 'upnp:protection').text = \
                self.protection
        if self.storage_medium:
            ElementTree.SubElement(root, 'upnp:storageMedium').text = \
                self.storage_medium
        if self.long_description:
            ElementTree.SubElement(root, 'upnp:longDescription').text = \
                self.long_description
        if self.rating:
            ElementTree.SubElement(root, 'upnp:rating').text = self.rating
        if self.description:
            ElementTree.SubElement(root, 'dc:description').text = \
                self.description
        if self.date:
            ElementTree.SubElement(root, 'dc:date').text = self.date

        for a in self.authors:
            ElementTree.SubElement(root, 'upnp:author').text = a
        for p in self.publishers:
            ElementTree.SubElement(root, 'dc:publisher').text = p
        for c in self.contributors:
            ElementTree.SubElement(root, 'dc:contributor').text = c
        for r in self.relations:
            ElementTree.SubElement(root, 'dc:relation').text = r
        for l in self.languages:
            ElementTree.SubElement(root, 'dc:language').text = l
        for r in self.rights:
            ElementTree.SubElement(root, 'dc:rights').text = r

        return root


class Album(Container):
    """ Ordered collection of objects. Rendering the album has the semantics of
    rendering each object in sequence.
    """
    upnp_class = '%s%s' % (Container.upnp_class, '.album')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 searchable=True, search_classes=[], create_classes=[],
                 storage_medium='', long_description='', description='',
                 publishers=[], contributors=[], date='', relations=[],
                 rights=[]):
        """ Constructor for the Album class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param searchable: if True, Search action can be performed upon the
                           container
        @param search_classes: list of SearchClass objects
        @param create_classes: list of CreateClass objects
        @param storage_medium: indicates the type of storage used for the
                               content. Possible values are enumerated on
                               STORAGE_MEDIUM_* variables
        @param long_description: long description
        @param description: description
        @param publishers: list of publishers names
        @param contributors: entities responsible for making contributions to
                             the resource
        @param date: ISO 8601, form YYYY-MM-DD
        @param relations: list of related resource names
        @param rights: rights held in and over the resource

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type storage_medium: string
        @type long_description: string
        @type description: string
        @type publishers: list
        @type contributors: list
        @type date: string
        @type relations: list
        @type rights: list
        """
        Container.__init__(self,object_id, parent_id, title, restricted, creator,
                           write_status, searchable, search_classes,
                           create_classes)
        self.storage_medium = storage_medium
        self.long_description = long_description
        self.description = description
        self.publishers = publishers
        self.contributors = contributors
        self.date = date
        self.relations = relations
        self.rights = rights

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Container.from_element(self, elt)
        storage_elt = find(elt, 'upnp', 'storageMedium')
        long_desc_elt = find(elt, 'upnp', 'longDescription')
        description_elt = find(elt, 'dc', 'description')
        date_elt = find(elt, 'dc', 'date')

        self.publishers = [p.text for p in findall(elt, 'dc', 'publisher')]
        self.contributors = [c.text for c in findall(elt, 'dc', 'contributor')]
        self.relations = [r.text for r in findall(elt, 'dc', 'relation')]
        self.rights = [r.text for r in findall(elt, 'dc', 'rights')]

        if storage_elt:
            self.storage_medium = storage_elt.text
        if long_desc_elt:
            self.long_description = long_desc_elt.text
        if description_elt:
            self.description = description_elt.text
        if date_elt:
            self.date = date_elt.text

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Container.to_didl_element(self)

        if self.storage_medium:
            ElementTree.SubElement(root, 'upnp:storageMedium').text = \
                self.storage_medium
        if self.long_description:
            ElementTree.SubElement(root, 'upnp:longDescription').text = \
                self.long_description
        if self.description:
            ElementTree.SubElement(root, 'dc:description').text = \
                self.description
        if self.date:
            ElementTree.SubElement(root, 'dc:date').text = self.date

        for p in self.publishers:
            ElementTree.SubElement(root, 'dc:publisher').text = p
        for c in self.contributors:
            ElementTree.SubElement(root, 'dc:contributor').text = c
        for r in self.relations:
            ElementTree.SubElement(root, 'dc:relation').text = r
        for r in self.rights:
            ElementTree.SubElement(root, 'dc:rights').text = r

        return root


class MusicAlbum(Album):
    """ A music album representation.
    """
    upnp_class = '%s%s' % (Album.upnp_class, '.musicAlbum')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 searchable=True, search_classes=[], create_classes=[],
                 storage_medium='', long_description='', description='',
                 publishers=[], contributors=[], date='', relations=[],
                 rights=[], artists=[], genres=[], producers=[],
                 album_art_uri=[], toc=''):
        """ Constructor for the MusicAlbum class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param searchable: if True, Search action can be performed upon the
                           container
        @param search_classes: list of SearchClass objects
        @param create_classes: list of CreateClass objects
        @param storage_medium: indicates the type of storage used for the
                               content. Possible values are enumerated on
                               STORAGE_MEDIUM_* variables
        @param long_description: long description
        @param description: description
        @param publishers: list of publishers names
        @param contributors: entities responsible for making contributions to
                             the resource
        @param date: ISO 8601, form YYYY-MM-DD
        @param relations: list of related resource names
        @param rights: rights held in and over the resource
        @param artists: list of artists names
        @param genres: list of genres that apply to this album
        @param producers: list of producers
        @param album_art_uri: reference to the album art
        @param toc: identifier for an audio CD

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type storage_medium: string
        @type long_description: string
        @type description: string
        @type publishers: list
        @type contributors: list
        @type date: string
        @type relations: list
        @type rights: list
        @type artists: list
        @type genres: list
        @type producers: list
        @type album_art_uri: string
        @type toc: string
        """
        Album.__init__(self, object_id, parent_id, title, restricted, creator,
                       write_status, searchable, search_classes,
                       create_classes, storage_medium, long_description,
                       description, publishers, contributors, date, relations,
                       rights)
        self.artists = artists
        self.genres = genres
        self.producers = producers
        self.album_art_uri = album_art_uri
        self.toc = toc

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Album.from_element(self, elt)
        album_art_uri_elt = find(elt, 'upnp', 'albumArtURI')
        toc_elt = find(elt, 'upnp', 'toc')

        self.artists = [a.text for a in find(elt, 'upnp', 'artist')]
        self.genres = [g.text for g in find(elt, 'upnp', 'genre')]
        self.producers = [p.text for p in findall(elt, 'upnp', 'producer')]

        if album_art_uri_elt:
            self.album_art_uri = album_art_uri_elt.text
        if toc_elt:
            self.toc = toc_elt.text

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Album.to_didl_element(self)

        for a in self.artists:
            ElementTree.SubElement(root, 'upnp:artist').text = a
        for g in self.genres:
            ElementTree.SubElement(root, 'upnp:genre').text = g
        for p in self.producers:
            ElementTree.SubElement(root, 'upnp:producer').text = p
        if self.album_art_uri:
            ElementTree.SubElement(root, 'upnp:albumArtURI').text = \
                self.album_art_uri
        if self.toc:
            ElementTree.SubElement(root, 'upnp:toc').text = self.toc

        return root


class Genre(Container):
    """ A container with a name denoting a genre.
    """
    upnp_class = '%s%s' % (Container.upnp_class, '.genre')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 searchable=True, search_classes=[], create_classes=[],
                 long_description='', description=''):
        """ Constructor for the Container class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param searchable: if True, Search action can be performed upon the
                           container
        @param search_classes: list of SearchClass objects
        @param create_classes: list of CreateClass objects

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        """
        Container.__init__(self, object_id, parent_id, title, restricted, creator,
                           write_status, searchable, search_classes,
                           create_classes)
        self.long_description = long_description
        self.description = description

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Container.from_element(self, elt)
        long_desc_elt = find(elt, 'upnp', 'longDescription')
        desc_elt = find(elt, 'dc', 'description')

        if long_desc_elt:
            self.long_description = long_desc_elt.text
        if desc_elt:
            self.description = desc_elt.text

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Container.to_didl_element(self)

        if self.long_description:
            ElementTree.SubElement(root, 'upnp:longDescription').text = \
                self.long_description
        if self.description:
            ElementTree.SubElement(root, 'dc:description').text = \
                self.description

        return root


class MusicGenre(Genre):
    """ Style of music. Can contain objects of class MusicArtist, MusicAlbum,
    AudioItem, MusicGenre.
    """
    upnp_class = '%s%s' % (Genre.upnp_class, '.musicGenre')

    def add_container(self, c):
        if isinstance(c, MusicArtist) or isinstance(c, MusicAlbum) or\
            isinstance(c, self.__class__):
            Genre.add_container(self, c)
            return True
        return False

    def add_item(self, item):
        if isinstance(item, AudioItem):
            Genre.add_item(self, item)
            return True
        return False




class PlaylistContainer(Container):
    """ A collection of objects. May mix audio, video and image items and is
    typically created by users.
    """
    upnp_class = '%s%s' % (Container.upnp_class, '.playlistContainer')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 searchable=True, search_classes=[], create_classes=[],
                 artists=[], genres=[], long_description='', producers=[],
                 storage_medium='', description='', contributors=[], date='',
                 languages=[], rights=[]):
        """ Constructor for the PlaylistContainer class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param searchable: if True, Search action can be performed upon the
                           container
        @param search_classes: list of SearchClass objects
        @param create_classes: list of CreateClass objects
        @param artists: list of artists names
        @param genres: list of genres
        @param long_description: long description
        @param producers: list of producers names
        @param storage_medium: indicates the type of storage used for the
                               content. Possible values are enumerated on
                               STORAGE_MEDIUM_* variables
        @param description: description
        @param contributors: list of contributors
        @param date: ISO 8601, form YYYY-MM-DD
        @param languages: list of languages
        @param rights: rights held in and over the resource

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type artists: list
        @type genres: list
        @type long_description: string
        @type producers: list
        @type storage_medium: string
        @type description: string
        @type contributors: list
        @type date: string
        @type languages: list
        @type rights: list
        """
        Container.__init__(self, object_id, parent_id, title, restricted, creator,
                           write_status, searchable, search_classes,
                           create_classes)
        self.artists = artists
        self.genres = genres
        self.long_description = long_description
        self.producers = producers
        self.storage_medium = storage_medium
        self.description = description
        self.contributors = contributors
        self.date = date
        self.languages = languages
        self.rights = rights

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Container.from_element(self, elt)
        long_desc_elt = find(elt, 'upnp', 'longDescription')
        storage_elt = find(elt, 'upnp', 'storageMedium')
        desc_elt = find(elt, 'dc', 'description')
        date_elt = find(elt, 'dc', 'date')
        languages_elt = findall(elt, 'dc', 'language')
        rights_elt = findall(elt, 'dc', 'rights')

        self.artists = [a.text for a in find(elt, 'upnp', 'artist')]
        self.genres = [g.text for g in find(elt, 'upnp', 'genre')]
        self.producers = [p.text for p in find(elt, 'upnp', 'producer')]
        self.contributors = [c.text for c in findall(elt, 'dc', 'contributor')]
        self.languages = [l.text for l in findall(elt, 'dc', 'language')]
        self.rights = [r.text for r in findall(elt, 'dc', 'rights')]

        if long_desc_elt:
            self.long_description = long_desc_elt.text
        if storage_elt:
            self.storage_medium = storage_elt.text
        if desc_elt:
            self.description = desc_elt.text
        if date_elt:
            self.date = date_elt.text

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Container.to_didl_element(self)
        for a in self.artists:
            ElementTree.SubElement(root, 'upnp:artist').text = a
        for g in self.genres:
            ElementTree.SubElement(root, 'upnp:genre').text = g
        for p in self.producers:
            ElementTree.SubElement(root, 'upnp:producer').text = p
        for c in self.contributors:
            ElementTree.SubElement(root, 'dc:contributor').text = c
        for l in self.languages:
            ElementTree.SubElement(root, 'dc:language').text = l
        for r in self.rights:
            ElementTree.SubElement(root, 'dc:rights').text = r

        if self.long_description:
            ElementTree.SubElement(root, 'upnp:longDescription').text = \
                self.long_description
        if self.storage_medium:
            ElementTree.SubElement(root, 'upnp:storageMedium').text = \
                self.storage_medium
        if self.description:
            ElementTree.SubElement(root, 'dc:description').text = \
                self.description
        if self.date:
            ElementTree.SubElement(root, 'dc:date').text = self.date

        return root


class Person(Container):
    """ Unordered collection of objects that belong to a person.
    """
    upnp_class = '%s%s' % (Container.upnp_class, '.person')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 searchable=True, search_classes=[], create_classes=[],
                 languages=[]):
        """ Constructor for the Person class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param searchable: if True, Search action can be performed upon the
                           container
        @param search_classes: list of SearchClass objects
        @param create_classes: list of CreateClass objects
        @param languages: list of languages

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type languages: list
        """
        Container.__init__(self, object_id, parent_id, title, restricted, creator,
                           write_status, searchable, search_classes,
                           create_classes)
        self.languages = languages

    def add_container(self, c):
        if isinstance(c, Album) or isinstance(c, PlaylistContainer):
            Container.add_container(self, c)
            return True
        return False

    def add_item(self, item):
        if isinstance(item, Item):
            Container.add_item(self, item)
            return True
        return False

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Container.from_element(self, elt)
        self.languages = [l.text for l in findall(elt, 'dc', 'language')]

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Container.to_didl_element(self)

        for l in self.languages:
            ElementTree.SubElement(root, 'dc:language').text = l

        return root


class MusicArtist(Person):
    """ Person which should be interpreted as a music artist.
    """
    upnp_class = '%s%s' % (Person.upnp_class, '.musicArtist')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 searchable=True, search_classes=[], create_classes=[],
                 languages=[], genres=[], artist_discography_uri=''):
        """ Constructor for the MusicArtist class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param searchable: if True, Search action can be performed upon the
                           container
        @param search_classes: list of SearchClass objects
        @param create_classes: list of CreateClass objects
        @param languages: list of languages
        @param genres: list of genres
        @param artist_discography_uri: artist discography uri

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type languages: list
        @type genres: list
        @type artist_discography_uri: string
        """
        Person.__init__(self, object_id, parent_id, title, restricted, creator,
                        write_status, searchable, search_classes,
                        create_classes, languages)
        self.genres = genres
        self.artist_discography_uri = artist_discography_uri

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Person.from_element(self, elt)
        artist_disc_uri = find(elt, 'upnp', 'artistDiscographyURI')

        self.genres = [g.text for g in find(elt, 'upnp', 'genre')]

        if artist_disc_uri:
            self.artist_discography_uri = artist_disc_uri.text

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Person.to_didl_element(self)

        for g in self.genres:
            ElementTree.SubElement(root, 'upnp:genre').text = g

        if self.artist_discography_uri:
            ElementTree.SubElement(root, 'upnp:artistDiscographyURI').text = \
                self.artist_discography_uri

        return root


class StorageSystem(Container):
    """ Heterogeneous collection of storage media. May only be child of the
    root container or another StorageSystem container.
    """
    upnp_class = '%s%s' % (Container.upnp_class, '.storageSystem')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 searchable=True, search_classes=[], create_classes=[],
                 storage_total=0, storage_used=0, storage_free=0,
                 storage_max_partition=0, storage_medium=''):
        """ Constructor for the StorageSystem class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param searchable: if True, Search action can be performed upon the
                           container
        @param search_classes: list of SearchClass objects
        @param create_classes: list of CreateClass objects
        @param storage_total: total capacity, in bytes, of the storage
                              represented by the container. Value -1 is
                              reserved to indicate that the capacity is
                              unknown
        @param storage_used: combined space, in bytes, used by all the objects
                             held in the storage represented by the container.
                             Value -1 is reserved to indicate that the space is
                             unknown
        @param storage_free: total free capacity, in bytes, of the storage
                             represented by the container. Value -1 is reserved
                             to indicate that the capacity is unknown
        @param storage_max_partition: largest amount of space, in bytes,
                                      available for storing a single resource
                                      in the container. Value -1 is reserved
                                      to indicate that the capacity is unknown
        @param storage_medium: indicates the type of storage used for the
                               content. Possible values are enumerated on
                               STORAGE_MEDIUM_* variables

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type storage_total: signed long
        @type storage_used: signed long
        @type storage_free: signed long
        @type storage_max_partition: signed long
        @type storage_medium: string
        """
        Container.__init__(self, object_id, parent_id, title, restricted, creator,
                           write_status, searchable, search_classes,
                           create_classes)
        self.storage_total = storage_total
        self.storage_used = storage_used
        self.storage_free = storage_free
        self.storage_max_partition = storage_max_partition
        self.storage_medium = storage_medium

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Container.from_element(self, elt)
        total = find(elt, 'upnp', 'storageTotal')
        used = find(elt, 'upnp', 'storageUsed')
        free = find(elt, 'upnp', 'storageFree')
        max_part = find(elt, 'upnp', 'storageMaxPartition')
        medium = find(elt, 'upnp', 'storageMedium')

        if not all([total, used, free, max_part, medium]):
            raise Exception('Could not set StorageSystem properties '\
                            'from element: missing required properties.')

        self.storage_total = total.text
        self.storage_used = used.text
        self.storage_free = free.text
        self.storage_max_partition = max_part.text
        self.storage_medium = medium.text

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Container.to_didl_element(self)

        if not all([self.storage_total, self.storage_used, self.storage_free,
                    self.storage_max_partition, self.storage_medium]):
            raise Exception('Could not create DIDL Element: missing required '\
                            'properties.')

        ElementTree.SubElement(root, 'upnp:storageTotal').text = \
            self.storage_total
        ElementTree.SubElement(root, 'upnp:storageUsed').text = \
            self.storage_used
        ElementTree.SubElement(root, 'upnp:storageFree').text = \
            self.storage_free
        ElementTree.SubElement(root, 'upnp:storageMaxPartition').text = \
            self.storage_max_partition
        ElementTree.SubElement(root, 'upnp:storageMedium').text = \
            self.storage_medium

        return root


class StorageVolume(Container):
    """ Some physical storage unit of a single type. May only be a child of the
    root container or a StorageSystem container.
    """
    upnp_class = '%s%s' % (Container.upnp_class, '.storageVolume')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 searchable=True, search_classes=[], create_classes=[],
                 storage_total=0, storage_used=0, storage_free=0,
                 storage_medium=''):
        """ Constructor for the StorageVolume class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param searchable: if True, Search action can be performed upon the
                           container
        @param search_classes: list of SearchClass objects
        @param create_classes: list of CreateClass objects
        @param storage_total: total capacity, in bytes, of the storage
                              represented by the container. Value -1 is
                              reserved to indicate that the capacity is unknown
        @param storage_used: combined space, in bytes, used by all the objects
                             held in the storage represented by the container.
                             Value -1 is reserved to indicate that the space is
                             unknown
        @param storage_free: total free capacity, in bytes, of the storage
                             represented by the container. Value -1 is reserved
                             to indicate that the capacity is unknown
        @param storage_medium: indicates the type of storage used for the
                               content. Possible values are enumerated on
                               STORAGE_MEDIUM_* variables

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type storage_total: signed long
        @type storage_used: signed long
        @type storage_free: signed long
        @type storage_medium: string
        """
        Container.__init__(self, object_id, parent_id, title, restricted, creator,
                           write_status, searchable, search_classes,
                           create_classes)
        self.storage_total = storage_total
        self.storage_used = storage_used
        self.storage_free = storage_free
        self.storage_medium = storage_medium

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Container.from_element(self, elt)
        total = find(elt, 'upnp', 'storageTotal')
        used = find(elt, 'upnp', 'storageUsed')
        free = find(elt, 'upnp', 'storageFree')
        medium = find(elt, 'upnp', 'storageMedium')

        if not all([total, used, free, medium]):
            raise Exception('Could not set StorageVolume properties '\
                            'from element: missing required properties.')

        self.storage_total = total.text
        self.storage_used = used.text
        self.storage_free = free.text
        self.storage_medium = medium.text

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Container.to_didl_element(self)

        if not all([self.storage_total, self.storage_used, self.storage_free,
                    self.storage_medium]):
            raise Exception('Could not create DIDL Element: missing required '\
                            'properties.')

        ElementTree.SubElement(root, 'upnp:storageTotal').text = \
            self.storage_total
        ElementTree.SubElement(root, 'upnp:storageUsed').text = \
            self.storage_used
        ElementTree.SubElement(root, 'upnp:storageFree').text = \
            self.storage_free
        ElementTree.SubElement(root, 'upnp:storageMedium').text = \
            self.storage_medium

        return root


class StorageFolder(Container):
    """ Collection of objects stored on some storage medium. May only be a
    child of the root container or another storage container.
    """
    upnp_class = '%s%s' % (Container.upnp_class, '.storageFolder')

    def __init__(self, object_id='', parent_id='', title='', restricted=False,
                 creator='', write_status=WRITE_STATUS_NOT_WRITABLE,
                 searchable=True, search_classes=[], create_classes=[],
                 storage_used=''):
        """ Constructor for the StorageFolder class.

        @param id: unique identifier for the object
        @param parent_id: id of object's parent
        @param title: name of the object
        @param restricted: True if only CDS can modify the object
        @param creator: content creator or owner
        @param write_status: modifiability of the resources of this object.
                             Integer parameter based on WRITE_STATUS_*
                             constants
        @param searchable: if True, Search action can be performed upon the
                           container
        @param search_classes: list of SearchClass objects
        @param create_classes: list of CreateClass objects
        @param storage_used: combined space, in bytes, used by all the objects
                             held in the storage represented by the container.
                             Value -1 is reserved to indicate that the space is
                             unknown

        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type storage_used: signed long
        """
        Container.__init__(self, object_id, parent_id, title, restricted, creator,
                           write_status, searchable, search_classes,
                           create_classes)
        self.storage_used = storage_used

    def from_element(self, elt):
        """ Sets the resource properties from an element.
        """
        Container.from_element(self, elt)
        used = find(elt, 'upnp', 'storageUsed')

        if not used:
            raise Exception('Could not set StorageFolder properties '\
                            'from element: missing required properties.')

        self.storage_used = used.text

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        root = Container.to_didl_element(self)

        if not self.storage_used:
            raise Exception('Could not create DIDL Element: missing required '\
                            'properties.')

        ElementTree.SubElement(root, 'upnp:storageUsed').text = \
            self.storage_used

        return root


class Element(_ElementInterface):
    """ Wrapper for elements. Can mount a complete tree of DIDL UPnP classes
    from a string and also mount the string from a complete tree.
    """

    def __init__(self):
        _ElementInterface.__init__(self, 'DIDL-Lite', {})
        self.attrib['xmlns'] = 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/'
        self.attrib['xmlns:dc'] = 'http://purl.org/dc/elements/1.1/'
        self.attrib['xmlns:upnp'] = 'urn:schemas-upnp-org:metadata-1-0/upnp/'
        self.attrib['xmlns:dlna'] = 'urn:schemas-dlna-org:metadata-1-0'
        self._items = []

    def add_container(self, object_id, parent_id, title, restricted=False):
        e = Container(object_id, parent_id, title, restricted)
        self.append(e.to_didl_element())

    def add_item(self, item):
        self.append(item.to_didl_element())
        self._items.append(item)

    def num_items(self):
        return len(self)

    def get_items(self):
        return self._items

    def to_string(self):
        return ElementTree.tostring(self)

    @classmethod
    def from_string(cls, aString):
        instance = cls()
        elt = parse_xml(aString)
        add_item = instance.add_item

        for node in elt:
            upnp_class_name = node.find(
                "{urn:schemas-upnp-org:metadata-1-0/upnp/}class").text
            names = upnp_class_name.split('.')
            while names:
                class_name = names[-1]
                class_name = "%s%s" % (class_name[0].upper(), class_name[1:])
                try:
                    # Get a reference to the current module
                    my_module = sys.modules[cls.__module__]
                    # and find a matching class in it
                    upnp_class = getattr(my_module, class_name)
                    # Create an instance and populate it
                    new_node = upnp_class()
                    new_node.from_element(node)
                    add_item(new_node)
                    break
                except Exception as e:
                    names = names[:-1]
                    log.debug('element from string critical bug: %s', e)
                    continue

        return instance
