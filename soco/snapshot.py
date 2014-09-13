# -*- coding: utf-8 -*-
"""
Class to support snap-shotting the current Sonos State, and then
restoring it later

This is useful for scenarios such as when you want to switch to radio
and then back again to what was playing previously
"""


class Snapshot(object):
    """
    Class to support snap-shotting the current Sonos State, and then
    restoring it later

    Note: This does not change anything to do with the configuration
    such as which group the speaker is in, just settings that impact
    what is playing, or how it is played.
    """

    def __init__(self, device, snapshot_queue=False):
        """ Construct the Snapshot object

        :params device: Device to snapshot
        :params snapshot_queue: If the queue is to be snapshotted

        Note: It is strongly advised that you do not snapshot the
        queue unless you really need to as it takes a very long
        time to restore large queues as it is done one track at
        a time
        """
        # The device that will be snapshotted
        self.device = device

        # The values that will be stored
        self.volume = None
        self.mute = None
        self.bass = None
        self.treble = None
        self.loudness = None
        self.play_mode = None
        self.cross_fade = None
        self.playlist_position = None
        self.track_position = None
        self.stream_uri = None
        self.metadata = None
        self.transport_state = None

        self.queue = None
        # Only set the queue as a list if we are going to save it
        if snapshot_queue:
            self.queue = []

    def snapshot(self):
        """ Record and store the current state of a device

        """
        # Save the volume, mute and other sound settings
        self.volume = self.device.volume
        self.mute = self.device.mute
        self.bass = self.device.bass
        self.treble = self.device.treble
        self.loudness = self.device.loudness
        # Save things like repeat, random, crossfade
        self.play_mode = self.device.play_mode
        self.cross_fade = self.device.cross_fade

        # Get information about the currently playing track
        track_info = self.device.get_current_track_info()
        if track_info is not None:
            self.playlist_position = track_info['playlist_position']
            self.track_position = track_info['position']

            # Check if this is a radio stream
            if track_info['duration'] == '0:00:00':
                self.stream_uri = track_info['uri']
                self.metadata = track_info['metadata']

        # Work out what the playing state is
        transport_info = self.device.get_current_transport_info()
        if transport_info is not None:
            self.transport_state = transport_info['current_transport_state']

        # Save of the current queue if we need to
        self._saveQueue()

    def restore(self):
        """ Restores the state of a device that was previously saved

        """
        # Start by ensuring that the speaker is paused as we don't want
        # things all rolling back when we are changing them, as this could
        # include things like audio
        transport_info = self.device.get_current_transport_info()
        if transport_info is not None:
            if transport_info['current_transport_state'] == 'PLAYING':
                self.device.pause()

        self._restoreQueue()

        # If a radio stream, then play that
        if self.stream_uri is not None:
            if self.stream_uri != "":
                self.device.play_uri(self.stream_uri, self.metadata, False)
        else:
            # Not radio stream, so must be playing from playlist
            if self.playlist_position is not None:
                if self.playlist_position != "":
                    position = int(self.playlist_position)
                    # The position in the playlist returned by
                    # get_current_track_info starts at 1, but when
                    # playing from playlist, the index starts at 0
                    if position > 0:
                        position = position - 1
                        self.device.play_from_queue(position, False)

            if self.track_position is not None:
                if self.track_position != "":
                    self.device.seek(self.track_position)

        # Reset all the properties that are pretty easy to do
        self.device.volume = self.volume
        self.device.mute = self.mute
        self.device.bass = self.bass
        self.device.treble = self.treble
        self.device.loudness = self.loudness
        self.device.play_mode = self.play_mode
        self.device.cross_fade = self.cross_fade

        # Now everything is set, see if we need to be playing, stopped
        # or paused
        if self.transport_state == 'PLAYING':
            self.device.play()
        elif self.transport_state == 'STOPPED':
            self.device.stop()

    def _saveQueue(self):
        """ Saves the current state of the queue

        """
        if self.queue is not None:
            # Maximum batch is 486, anything larger will still only
            # return 486
            batch_size = 400
            total = 0
            num_return = batch_size

            # Need to get all the tracks in batches, but Only get the next
            # batch if all the items requested were in the last batch
            while num_return == batch_size:
                list = self.device.get_queue(total, batch_size)
                # Check how many entries were returned
                num_return = len(list)
                # Make sure the queue is not empty
                if num_return > 0:
                    self.queue.append(list)
                # Update the total that have been processed
                total = total + num_return

    def _restoreQueue(self):
        """ Restores the previous state of the queue

        """
        if self.queue is not None:
            # Clear the queue so that it can be reset
            self.device.clear_queue()
            # Now loop around all the queue entries adding them
            for queue_group in self.queue:
                for queue_item in queue_group:
                    self.device.add_uri_to_queue(queue_item.uri)
