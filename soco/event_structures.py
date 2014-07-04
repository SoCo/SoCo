# -*- coding: utf-8 -*-

""" This module contains all the event structures for the events that
can be returned

"""
from __future__ import unicode_literals

import logging
from .xml import XML

log = logging.getLogger(__name__)  # pylint: disable=C0103


# pylint: disable=too-many-public-methods,too-many-statements
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
        result['transportState'] = LastChangeEvent._get_val_data(
            avtns, instanceid, 'TransportState')
        result['currentPlayMode'] = LastChangeEvent._get_val_data(
            avtns, instanceid, 'CurrentPlayMode')
        result['currentCrossfadeMode'] = LastChangeEvent._get_val_data(
            avtns, instanceid, 'CurrentCrossfadeMode')
        result['numberOfTracks'] = LastChangeEvent._get_val_data(
            avtns, instanceid, 'NumberOfTracks')
        result['currentTrack'] = LastChangeEvent._get_val_data(
            avtns, instanceid, 'CurrentTrack')
        result['currentSection'] = LastChangeEvent._get_val_data(
            avtns, instanceid, 'CurrentSection')
        result['currentTrackURI'] = LastChangeEvent._get_val_data(
            avtns, instanceid, 'CurrentTrackURI')
        result['currentTrackDuration'] = LastChangeEvent._get_val_data(
            avtns, instanceid, 'CurrentTrackDuration')

        # The current track meta data is embedded XML
        current_track_metadata = LastChangeEvent._get_val_data(
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
                result['title'] = LastChangeEvent._get_element_data(
                    nsdc, item, 'title')
                result['creator'] = LastChangeEvent._get_element_data(
                    nsdc, item, 'creator')
                result['album'] = LastChangeEvent._get_element_data(
                    upnpns, item, 'album')
                result['originalTrackNumber'] =\
                    LastChangeEvent._get_element_data(
                        upnpns, item, 'originalTrackNumber')
                result['albumArtist'] = LastChangeEvent._get_element_data(
                    rns, item, 'albumArtist')
                result['albumArtURI'] = LastChangeEvent._get_element_data(
                    upnpns, item, 'albumArtURI')
                result['radioShowMd'] = LastChangeEvent._get_element_data(
                    rns, item, 'radioShowMd')

        result['nextTrackURI'] = LastChangeEvent._get_val_data(
            rns, instanceid, 'NextTrackURI')

        # The next track meta data is embedded XML
        next_track_metadata = LastChangeEvent._get_val_data(
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
                result['nextTitle'] = LastChangeEvent._get_element_data(
                    nsdc, item, 'title')
                result['nextCreator'] = LastChangeEvent._get_element_data(
                    nsdc, item, 'creator')
                result['nextAlbum'] = LastChangeEvent._get_element_data(
                    upnpns, item, 'album')
                result['nextOriginalTrackNumber'] =\
                    LastChangeEvent._get_element_data(
                        upnpns, item, 'originalTrackNumber')
                result['nextAlbumArtist'] = LastChangeEvent._get_element_data(
                    rns, item, 'albumArtist')
                result['nextAlbumArtURI'] = LastChangeEvent._get_element_data(
                    upnpns, item, 'albumArtURI')

        # The transport meta data is embedded XML
        transportmetadata = LastChangeEvent._get_val_data(
            rns, instanceid, 'EnqueuedTransportURIMetaData')
        if transportmetadata is not None:
            try:
                transport_xml = XML.fromstring(transportmetadata)
            except Exception as exc:
                # Not valid XML
                log.exception(transportmetadata)
                log.exception(str(exc))
                return None

            item = transport_xml.find('{0}item'.format(didlns))

            if item is not None:
                result['transportTitle'] = LastChangeEvent._get_element_data(
                    nsdc, item, 'title')

        return cls(result)

    @staticmethod
    def _get_val_data(namesp, container, elem_name):
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
    def _get_element_data(namesp, container, elem_name):
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

    def _get_integer_content(self, keyval):
        """Gets the content value as an integer"""
        int_val = self.content.get(keyval, None)
        if int_val is not None:
            try:
                # Try and convert to an integer
                int_val = int(int_val)
            except ValueError:
                pass
        return int_val

    @property
    def transport_state(self):
        """Get the transport state"""
        return self.content.get('transportState', None)

    @property
    def current_play_mode(self):
        """Get the current play mode"""
        return self.content.get('currentPlayMode', None)

    @property
    def current_crossfade_mode(self):
        """Get the current cross fade mode"""
        return self.content.get('currentCrossfadeMode', None)

    @property
    def number_of_tracks(self):
        """Get the number of tracks"""
        return self._get_integer_content('numberOfTracks')

    @property
    def current_track(self):
        """Get the current track number"""
        return self._get_integer_content('currentTrack')

    @property
    def current_track_uri(self):
        """Get the track URI"""
        return self.content.get('currentTrackURI', None)

    @property
    def current_track_duration(self):
        """Get the current track duration"""
        return self.content.get('currentTrackDuration', None)

    @property
    def title(self):
        """Get the title"""
        return self.content.get('title', None)

    @property
    def creator(self):
        """Get the creator"""
        return self.content.get('creator', None)

    @property
    def album(self):
        """Get the album"""
        return self.content.get('album', None)

    @property
    def original_track_number(self):
        """Get the original track number"""
        return self._get_integer_content('originalTrackNumber')

    @property
    def album_artist(self):
        """Get the album artist"""
        return self.content.get('albumArtist', None)

    @property
    def album_art_uri(self):
        """Get the albumArtURI"""
        return self.content.get('albumArtURI', None)

    @property
    def radio_show_md(self):
        """Get the radio show name"""
        return self.content.get('radioShowMd', None)

    @property
    def next_track_uri(self):
        """Get the next track URI"""
        return self.content.get('nextTrackURI', None)

    @property
    def next_title(self):
        """Get the next title"""
        return self.content.get('nextTitle', None)

    @property
    def next_creator(self):
        """Get the next creator"""
        return self.content.get('nextCreator', None)

    @property
    def next_album(self):
        """Get the next album name"""
        return self.content.get('nextAlbum', None)

    @property
    def next_original_track_number(self):
        """Get the next original track number"""
        return self._get_integer_content('nextOriginalTrackNumber')

    @property
    def next_album_artist(self):
        """Get the next album artist"""
        return self.content.get('nextAlbumArtist', None)

    @property
    def next_album_art_uri(self):
        """Get the next albumArtURI"""
        return self.content.get('nextAlbumArtURI', None)

    @property
    def transport_title(self):
        """Get the transport title"""
        return self.content.get('transportTitle', None)
