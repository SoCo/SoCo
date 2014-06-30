# -*- coding: utf-8 -*-

""" This module contains all the event structures for the events that
can be returned

"""
import logging
from .xml import XML

log = logging.getLogger(__name__)  # pylint: disable=C0103


# pylint: disable=too-many-public-methods,too-many-statements,invalid-name
class LastChangeEvent(object):
    """
    Class to handle the Last Change event XML
    """

    def __init__(self, contents):
        """ Initialize the class with the contents of the event

        :param contents: Dictionary of the data
        """
        self.content = contents

    # pylint: disable=bare-except,broad-except,too-many-locals
    @classmethod
    def from_xml(cls, xmlstr):
        """Return an instance of this class, created from xml.

        :param xmlStr: The xml in string form to create the class from
        """
        try:
            # Read in the XML
            last_change_xml = XML.fromstring(xmlstr)
        except Exception as exc:
            # Not valid XML
            log.exception(xmlstr)
            log.exception(str(exc))
            return None

        # All the namespaces used in the event XML
        avtns = '{urn:schemas-upnp-org:metadata-1-0/AVT/}'
        didlns = '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}'
        rns = '{urn:schemas-rinconnetworks-com:metadata-1-0/}'
        upnpns = '{urn:schemas-upnp-org:metadata-1-0/upnp/}'
        nsdc = '{http://purl.org/dc/elements/1.1/}'

        instanceid = last_change_xml.find('{0}InstanceID'.format(avtns))
        if instanceid is None:
            return None

        result = {}
        result['transportState'] = LastChangeEvent._getValData(
            avtns, instanceid, 'TransportState')
        result['currentPlayMode'] = LastChangeEvent._getValData(
            avtns, instanceid, 'CurrentPlayMode')
        result['currentCrossfadeMode'] = LastChangeEvent._getValData(
            avtns, instanceid, 'CurrentCrossfadeMode')
        result['numberOfTracks'] = LastChangeEvent._getValData(
            avtns, instanceid, 'NumberOfTracks')
        result['currentTrack'] = LastChangeEvent._getValData(
            avtns, instanceid, 'CurrentTrack')
        result['currentSection'] = LastChangeEvent._getValData(
            avtns, instanceid, 'CurrentSection')
        result['currentTrackURI'] = LastChangeEvent._getValData(
            avtns, instanceid, 'CurrentTrackURI')
        result['currentTrackDuration'] = LastChangeEvent._getValData(
            avtns, instanceid, 'CurrentTrackDuration')

        # The current track meta data is embedded XML
        current_track_metadata = LastChangeEvent._getValData(
            avtns, instanceid, 'CurrentTrackMetaData')
        if current_track_metadata is not None:
            try:
                ctrack_metadata_xml = XML.fromstring(current_track_metadata)
            except Exception as exc:
                # Not valid XML
                log.exception(current_track_metadata)
                log.exception(str(exc))
                return None

            item = ctrack_metadata_xml.find('{0}item'.format(didlns))

            if item is not None:
                result['title'] = LastChangeEvent._getElementData(
                    nsdc, item, 'title')
                result['creator'] = LastChangeEvent._getElementData(
                    nsdc, item, 'creator')
                result['album'] = LastChangeEvent._getElementData(
                    upnpns, item, 'album')
                result['originalTrackNumber'] =\
                    LastChangeEvent._getElementData(
                        upnpns, item, 'originalTrackNumber')
                result['albumArtist'] = LastChangeEvent._getElementData(
                    rns, item, 'albumArtist')
                result['albumArtURI'] = LastChangeEvent._getElementData(
                    upnpns, item, 'albumArtURI')
                result['radioShowMd'] = LastChangeEvent._getElementData(
                    rns, item, 'radioShowMd')

        result['nextTrackURI'] = LastChangeEvent._getValData(
            rns, instanceid, 'NextTrackURI')

        # The next track meta data is embedded XML
        next_track_metadata = LastChangeEvent._getValData(
            rns, instanceid, 'NextTrackMetaData')
        if next_track_metadata is not None:
            try:
                next_track_metadata_xml = XML.fromstring(next_track_metadata)
            except Exception as exc:
                # Not valid XML
                log.exception(next_track_metadata)
                log.exception(str(exc))
                return None

            item = next_track_metadata_xml.find('{0}item'.format(didlns))

            if item is not None:
                result['nextTitle'] = LastChangeEvent._getElementData(
                    nsdc, item, 'title')
                result['nextCreator'] = LastChangeEvent._getElementData(
                    nsdc, item, 'creator')
                result['nextAlbum'] = LastChangeEvent._getElementData(
                    upnpns, item, 'album')
                result['nextOriginalTrackNumber'] =\
                    LastChangeEvent._getElementData(
                        upnpns, item, 'originalTrackNumber')
                result['nextAlbumArtist'] = LastChangeEvent._getElementData(
                    rns, item, 'albumArtist')
                result['nextAlbumArtURI'] = LastChangeEvent._getElementData(
                    upnpns, item, 'albumArtURI')

        # The transport meta data is embedded XML
        transportMetaData = LastChangeEvent._getValData(
            rns, instanceid, 'EnqueuedTransportURIMetaData')
        if transportMetaData is not None:
            try:
                transportMetaDataXml = XML.fromstring(transportMetaData)
            except Exception as exc:
                # Not valid XML
                log.exception(transportMetaData)
                log.exception(str(exc))
                return None

            item = transportMetaDataXml.find('{0}item'.format(didlns))

            if item is not None:
                result['transportTitle'] = LastChangeEvent._getElementData(
                    nsdc, item, 'title')

        return cls(result)

    @staticmethod
    def _getValData(namesp, container, elem_name):
        """Returns the string from the val attribute

        :param ns: Namespace the element is in
        :param container: Parent object the element is in
        :param elem_name: Name of the to get the attribute of
        """
        value = None
        if container is not None:
            element = container.find('{0}{1}'.format(namesp, elem_name))
            if element is not None:
                value = element.get('val')
        return value

    @staticmethod
    def _getElementData(namesp, container, elem_name):
        """Returns the string from the element

        :param ns: Namespace the element is in
        :param container: Parent object the element is in
        :param elem_name: Name of the to get the value of
        """
        value = None
        if container is not None:
            element = container.find('{0}{1}'.format(namesp, elem_name))
            if element is not None:
                value = element.text
        return value

    def _getContent(self, keyval):
        """Gets the content value if it is set"""
        if keyval not in self.content:
            return None
        return self.content[keyval]

    def _getIntegerContent(self, keyval):
        """Gets the content value as an integer"""
        int_val = self._getContent(keyval)
        if int_val is not None:
            try:
                # Try and convert to an integer
                int_val = int(int_val)
            except:
                pass
        return int_val

    @property
    def transportState(self):
        """Get the transport state"""
        return self._getContent('transportState')

    @property
    def currentPlayMode(self):
        """Get the current play mode"""
        return self._getContent('currentPlayMode')

    @property
    def currentCrossfadeMode(self):
        """Get the current cross fade mode"""
        return self._getContent('currentCrossfadeMode')

    @property
    def numberOfTracks(self):
        """Get the number of tracks"""
        return self._getIntegerContent('numberOfTracks')

    @property
    def currentTrack(self):
        """Get the current track number"""
        return self._getIntegerContent('currentTrack')

    @property
    def currentTrackURI(self):
        """Get the track URI"""
        return self._getContent('currentTrackURI')

    @property
    def currentTrackDuration(self):
        """Get the current track duration"""
        return self._getContent('currentTrackDuration')

    @property
    def title(self):
        """Get the title"""
        return self._getContent('title')

    @property
    def creator(self):
        """Get the creator"""
        return self._getContent('creator')

    @property
    def album(self):
        """Get the album"""
        return self._getContent('album')

    @property
    def originalTrackNumber(self):
        """Get the original track number"""
        return self._getIntegerContent('originalTrackNumber')

    @property
    def albumArtist(self):
        """Get the album artist"""
        return self._getContent('albumArtist')

    @property
    def albumArtURI(self):
        """Get the albumArtURI"""
        return self._getContent('albumArtURI')

    @property
    def radioShowMd(self):
        """Get the radio show name"""
        return self._getContent('radioShowMd')

    @property
    def nextTrackURI(self):
        """Get the next track URI"""
        return self._getContent('nextTrackURI')

    @property
    def nextTitle(self):
        """Get the next title"""
        return self._getContent('nextTitle')

    @property
    def nextCreator(self):
        """Get the next creator"""
        return self._getContent('nextCreator')

    @property
    def nextAlbum(self):
        """Get the next album name"""
        return self._getContent('nextAlbum')

    @property
    def nextOriginalTrackNumber(self):
        """Get the next original track number"""
        return self._getIntegerContent('nextOriginalTrackNumber')

    @property
    def nextAlbumArtist(self):
        """Get the next album artist"""
        return self._getContent('nextAlbumArtist')

    @property
    def nextAlbumArtURI(self):
        """Get the next albumArtURI"""
        return self._getContent('nextAlbumArtURI')

    @property
    def transportTitle(self):
        """Get the transport title"""
        return self._getContent('transportTitle')
