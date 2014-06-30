# pylint: disable=too-many-lines,R0903,W0142,R0913,C0302
# -*- coding: utf-8 -*-


""" This module contains all the event structures for the events that
can be returned

"""
import logging
from .xml import XML

log = logging.getLogger(__name__)  # pylint: disable=C0103


class LastChangeEvent():
    """
    Class to handle the Last Change event XML
    """

    def __init__(self, contents):
        """ Initialize the class with the contents of the event

        :param contents: Dictionary of the data
        """
        self.content = contents

    @classmethod
    def from_xml(cls, xmlStr):
        """Return an instance of this class, created from xml.

        :param xmlStr: The xml in string form to create the class from
        """
        try:
            # Read in the XML
            lastChangeXml = XML.fromstring(xmlStr)
        except Exception as exc:
            # Not valid XML
            log.exception(xmlStr)
            log.exception(str(exc))
            return None

        # All the namespaces used in the event XML
        ns = '{urn:schemas-upnp-org:metadata-1-0/AVT/}'
        didlns = '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}'
        rns = '{urn:schemas-rinconnetworks-com:metadata-1-0/}'
        upnpns = '{urn:schemas-upnp-org:metadata-1-0/upnp/}'
        nsdc = '{http://purl.org/dc/elements/1.1/}'

        instanceId = lastChangeXml.find('{0}InstanceID'.format(ns))
        if instanceId is None:
            return None
        
        result = {}
        result['transportState'] = LastChangeEvent.getValData(
                                    ns, instanceId, 'TransportState')
        result['currentPlayMode'] = LastChangeEvent.getValData(
                                    ns, instanceId, 'CurrentPlayMode')
        result['currentCrossfadeMode'] = LastChangeEvent.getValData(
                                    ns, instanceId, 'CurrentCrossfadeMode')
        result['numberOfTracks'] = LastChangeEvent.getValData(
                                    ns, instanceId, 'NumberOfTracks')
        result['currentTrack'] = LastChangeEvent.getValData(
                                    ns, instanceId, 'CurrentTrack')
        result['currentSection'] = LastChangeEvent.getValData(
                                    ns, instanceId, 'CurrentSection')
        result['currentTrackURI'] = LastChangeEvent.getValData(
                                    ns, instanceId, 'CurrentTrackURI')
        result['currentTrackDuration'] = LastChangeEvent.getValData(
                                    ns, instanceId, 'CurrentTrackDuration')

        # The current track meta data is embedded XML
        currentTrackMetaData = LastChangeEvent.getValData(
                                    ns, instanceId, 'CurrentTrackMetaData')
        if currentTrackMetaData is not None:
            try:
                currentTrackMetaDataXml = XML.fromstring(currentTrackMetaData)
            except Exception as exc:
                # Not valid XML
                log.exception(currentTrackMetaData)
                log.exception(str(exc))
                return None

            item = currentTrackMetaDataXml.find('{0}item'.format(didlns))
            
            if item is not None:
                result['title'] = LastChangeEvent.getElementData(
                                            nsdc, item, 'title')
                result['creator'] = LastChangeEvent.getElementData(
                                            nsdc, item, 'creator')
                result['album'] = LastChangeEvent.getElementData(
                                            upnpns, item, 'album')
                result['originalTrackNumber'] =\
                                LastChangeEvent.getElementData(
                                    upnpns, item, 'originalTrackNumber')
                result['albumArtist'] = LastChangeEvent.getElementData(
                                            rns, item, 'albumArtist')
                result['albumArtURI'] = LastChangeEvent.getElementData(
                                            upnpns, item, 'albumArtURI')
                result['radioShowMd'] = LastChangeEvent.getElementData(
                                            rns, item, 'radioShowMd')
        
        result['nextTrackURI'] = LastChangeEvent.getValData(
                                            rns, instanceId, 'NextTrackURI')
        
        # The next track meta data is embedded XML
        nextTrackMetaData = LastChangeEvent.getValData(
                                        rns, instanceId, 'NextTrackMetaData')
        if nextTrackMetaData is not None:
            try:
                nextTrackMetaDataXml = XML.fromstring(nextTrackMetaData)
            except Exception as exc:
                # Not valid XML
                log.exception(nextTrackMetaData)
                log.exception(str(exc))
                return None

            item = nextTrackMetaDataXml.find('{0}item'.format(didlns))
            
            if item is not None:
                result['nextTitle'] = LastChangeEvent.getElementData(
                                                nsdc, item, 'title')
                result['nextCreator'] = LastChangeEvent.getElementData(
                                                nsdc, item, 'creator')
                result['nextAlbum'] = LastChangeEvent.getElementData(
                                                upnpns, item, 'album')
                result['nextOriginalTrackNumber'] =\
                    LastChangeEvent.getElementData(
                            upnpns, item, 'originalTrackNumber')
                result['nextAlbumArtist'] = LastChangeEvent.getElementData(
                                                rns, item, 'albumArtist')
                result['nextAlbumArtURI'] = LastChangeEvent.getElementData(
                                                upnpns, item, 'albumArtURI')
            
        # The transport meta data is embedded XML
        transportMetaData = LastChangeEvent.getValData(
                            rns, instanceId, 'EnqueuedTransportURIMetaData')
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
                result['transportTitle'] = LastChangeEvent.getElementData(
                                                nsdc, item, 'title')

        return cls(result)

    @staticmethod
    def getValData(ns, container, elemName):
        """Returns the string from the val attribute

        :param ns: Namespace the element is in
        :param container: Parent object the element is in
        :param elemName: Name of the to get the attribute of   
        """
        value = None
        if container is not None:
            element = container.find('{0}{1}'.format(ns,elemName))
            if element is not None:
                value = element.get('val')
        return value
    
    @staticmethod
    def getElementData(ns, container, elemName):
        """Returns the string from the element

        :param ns: Namespace the element is in
        :param container: Parent object the element is in
        :param elemName: Name of the to get the value of   
        """
        value = None
        if container is not None:
            element = container.find('{0}{1}'.format(ns,elemName))
            if element is not None:
                value = element.text
        return value

    def getContent(self, keyVal):
        """Gets the content value if it is set"""
        if keyVal not in self.content:
            print "no key " + keyVal
            return None
        return self.content[keyVal]

    def getIntegerContent(self, key):
        """Gets the content value as an integer"""
        intVal = self.getContent(key)
        if intVal is not None:
            try:
                # Try and convert to an integer
                intVal = int(intVal)
            except:
                pass
        return intVal

    @property
    def transportState(self):
        """Get the transport state"""
        return self.getContent('transportState')

    @property
    def currentPlayMode(self):
        """Get the current play mode"""
        return self.getContent('currentPlayMode')

    @property
    def currentCrossfadeMode(self):
        """Get the current cross fade mode"""
        return self.getContent('currentCrossfadeMode')

    @property
    def numberOfTracks(self):
        """Get the number of tracks"""
        return self.getIntegerContent('numberOfTracks')

    @property
    def currentTrack(self):
        """Get the current track number"""
        return self.getIntegerContent('currentTrack')

    @property
    def currentTrackURI(self):
        """Get the track URI"""
        return self.getContent('currentTrackURI')

    @property
    def currentTrackDuration(self):
        """Get the current track duration"""
        return self.getContent('currentTrackDuration')

    @property
    def title(self):
        """Get the title"""
        return self.getContent('title')

    @property
    def creator(self):
        """Get the creator"""
        return self.getContent('creator')

    @property
    def album(self):
        """Get the album"""
        return self.getContent('album')

    @property
    def originalTrackNumber(self):
        """Get the original track number"""
        return self.getIntegerContent('originalTrackNumber')

    @property
    def albumArtist(self):
        """Get the album artist"""
        return self.getContent('albumArtist')

    @property
    def albumArtURI(self):
        """Get the albumArtURI"""
        return self.getContent('albumArtURI')

    @property
    def radioShowMd(self):
        """Get the radio show name"""
        return self.getContent('radioShowMd')

    @property
    def nextTrackURI(self):
        """Get the next track URI"""
        return self.getContent('nextTrackURI')

    @property
    def nextTitle(self):
        """Get the next title"""
        return self.getContent('nextTitle')

    @property
    def nextCreator(self):
        """Get the next creator"""
        return self.getContent('nextCreator')

    @property
    def nextAlbum(self):
        """Get the next album name"""
        return self.getContent('nextAlbum')

    @property
    def nextOriginalTrackNumber(self):
        """Get the next original track number"""
        return self.getIntegerContent('nextOriginalTrackNumber')

    @property
    def nextAlbumArtist(self):
        """Get the next album artist"""
        return self.getContent('nextAlbumArtist')

    @property
    def nextAlbumArtURI(self):
        """Get the next albumArtURI"""
        return self.getContent('nextAlbumArtURI')

    @property
    def transportTitle(self):
        """Get the transport title"""
        return self.getContent('transportTitle')

