# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance

"""Functionality to support saving and restoring the current Sonos state.

This is useful for scenarios such as when you want to switch to radio
or an announcement and then back again to what was playing previously.

Warning:
    Sonos has introduced control via Amazon Alexa. A new cloud queue is
    created and at present there appears no way to restart this
    queue from snapshot. Currently if a cloud queue was playing it will
    not restart.

Warning:
    This class is designed to be created used and destroyed. It is not
    designed to be reused or long lived. The init sets up defaults for
    one use.
"""


class Snapshot:
    """A snapshot of the current state.

    Note:
        This does not change anything to do with the configuration
        such as which group the speaker is in, just settings that impact
        what is playing, or how it is played.

        List of sources that may be playing using root of media_uri:

        | ``x-rincon-queue``: playing from Queue
        | ``x-sonosapi-stream``: playing a stream (eg radio)
        | ``x-file-cifs``: playing file
        | ``x-rincon``: slave zone (only change volume etc. rest from
          coordinator)
    """

    def __init__(self, device, snapshot_queue=False):
        """
        Args:
            device (SoCo): The device to snapshot
            snapshot_queue (bool): Whether the queue should be snapshotted.
                Defaults to `False`.

        Warning:
            It is strongly advised that you do not snapshot the queue unless
            you really need to as it takes a very long time to restore large
            queues as it is done one track at a time.
        """
        # The device that will be snapshotted
        self.device = device

        # The values that will be stored
        # For all zones:
        self.media_uri = None
        self.is_coordinator = False
        self.is_playing_queue = False
        self.is_playing_cloud_queue = False

        self.volume = None
        self.mute = None
        self.bass = None
        self.treble = None
        self.loudness = None

        # For coordinator zone playing from Queue:
        self.play_mode = None
        self.cross_fade = None
        self.playlist_position = 0
        self.track_position = None

        # For coordinator zone playing a Stream:
        self.media_metadata = None

        # For all coordinator zones
        self.transport_state = None

        self.queue = None
        # Only set the queue as a list if we are going to save it
        if snapshot_queue:
            self.queue = []

    def snapshot(self):
        """Record and store the current state of a device.

        Returns:
            bool: `True` if the device is a coordinator, `False` otherwise.
            Useful for determining whether playing an alert on a device
            will ungroup it.
        """
        # get if device coordinator (or slave) True (or False)
        self.is_coordinator = self.device.is_coordinator

        # Get information about the currently playing media
        media_info = self.device.avTransport.GetMediaInfo([("InstanceID", 0)])
        self.media_uri = media_info["CurrentURI"]
        # Extract source from media uri - below some media URI value examples:
        #  'x-rincon-queue:RINCON_000E5859E49601400#0'
        #       - playing a local queue always #0 for local queue)
        #
        #  'x-rincon-queue:RINCON_000E5859E49601400#6'
        #       - playing a cloud queue where #x changes with each queue)
        #
        #  -'x-rincon:RINCON_000E5859E49601400'
        #       - a slave player pointing to coordinator player

        if self.media_uri.split(":")[0] == "x-rincon-queue":
            # The pylint error below is a false positive, see about removing it
            # in the future
            # pylint: disable=simplifiable-if-statement
            if self.media_uri.split("#")[1] == "0":
                # playing local queue
                self.is_playing_queue = True
            else:
                # playing cloud queue - started from Alexa
                self.is_playing_cloud_queue = True

        # Save the volume, mute and other sound settings
        self.volume = self.device.volume
        self.mute = self.device.mute
        self.bass = self.device.bass
        self.treble = self.device.treble
        self.loudness = self.device.loudness

        # get details required for what's playing:
        if self.is_playing_queue:
            # playing from queue - save repeat, random, cross fade, track, etc.
            self.play_mode = self.device.play_mode
            self.cross_fade = self.device.cross_fade

            # Get information about the currently playing track
            track_info = self.device.get_current_track_info()
            if track_info is not None:
                position = track_info["playlist_position"]
                if position != "":
                    # save as integer
                    self.playlist_position = int(position)
                self.track_position = track_info["position"]
        else:
            # playing from a stream - save media metadata
            self.media_metadata = media_info["CurrentURIMetaData"]

        # Work out what the playing state is - if a coordinator
        if self.is_coordinator:
            transport_info = self.device.get_current_transport_info()
            if transport_info is not None:
                self.transport_state = transport_info["current_transport_state"]

        # Save of the current queue if we need to
        self._save_queue()

        # return if device is a coordinator (helps usage)
        return self.is_coordinator

    def restore(self, fade=False):
        """Restore the state of a device to that which was previously saved.

        For coordinator devices restore everything. For slave devices
        only restore volume etc., not transport info (transport info
        comes from the slave's coordinator).

        Args:
            fade (bool): Whether volume should be faded up on restore.
        """
        try:
            if self.is_coordinator:
                self._restore_coordinator()
        finally:
            self._restore_volume(fade)

        # Now everything is set, see if we need to be playing, stopped
        # or paused ( only for coordinators)
        if self.is_coordinator:
            if self.transport_state == "PLAYING":
                self.device.play()
            elif self.transport_state == "STOPPED":
                self.device.stop()

    def _restore_coordinator(self):
        """Do the coordinator-only part of the restore."""
        # Start by ensuring that the speaker is paused as we don't want
        # things all rolling back when we are changing them, as this could
        # include things like audio
        transport_info = self.device.get_current_transport_info()
        if transport_info is not None:
            if transport_info["current_transport_state"] == "PLAYING":
                self.device.pause()

        # Check if the queue should be restored
        self._restore_queue()

        # Reinstate what was playing

        if self.is_playing_queue and self.playlist_position > 0:
            # was playing from playlist

            if self.playlist_position is not None:
                # The position in the playlist returned by
                # get_current_track_info starts at 1, but when
                # playing from playlist, the index starts at 0
                # if position > 0:
                self.playlist_position -= 1
                self.device.play_from_queue(self.playlist_position, False)

            if self.track_position is not None:
                if self.track_position != "":
                    self.device.seek(self.track_position)

            # reinstate track, position, play mode, cross fade
            # Need to make sure there is a proper track selected first
            self.device.play_mode = self.play_mode
            self.device.cross_fade = self.cross_fade

        elif self.is_playing_cloud_queue:
            # was playing a cloud queue started by Alexa
            # No way yet to re-start this so prevent it throwing an error!
            pass

        else:
            # was playing a stream (radio station, file, or nothing)
            # reinstate uri and meta data
            if self.media_uri != "":
                self.device.play_uri(self.media_uri, self.media_metadata, start=False)

    def _restore_volume(self, fade):
        """Reinstate volume.

        Args:
            fade (bool): Whether volume should be faded up on restore.
        """
        self.device.mute = self.mute

        # Can only change volume on device with fixed volume set to False
        # otherwise get uPnP error, so check first. Before issuing a network
        # command to check, fixed volume always has volume set to 100.
        # So only checked fixed volume if volume is 100.
        if self.volume == 100:
            fixed_vol = self.device.fixed_volume
        else:
            fixed_vol = False

        # now set volume if not fixed
        if not fixed_vol:
            self.device.bass = self.bass
            self.device.treble = self.treble
            self.device.loudness = self.loudness

            if fade:
                # if fade requested in restore
                # set volume to 0 then fade up to saved volume (non blocking)
                self.device.volume = 0
                self.device.ramp_to_volume(self.volume)
            else:
                # set volume
                self.device.volume = self.volume

    def _save_queue(self):
        """Save the current state of the queue."""
        if self.queue is not None:
            # Maximum batch is 486, anything larger will still only
            # return 486
            batch_size = 400
            total = 0
            num_return = batch_size

            # Need to get all the tracks in batches, but Only get the next
            # batch if all the items requested were in the last batch
            while num_return == batch_size:
                queue_items = self.device.get_queue(total, batch_size)
                # Check how many entries were returned
                num_return = len(queue_items)
                # Make sure the queue is not empty
                if num_return > 0:
                    self.queue.append(queue_items)
                # Update the total that have been processed
                total = total + num_return

    def _restore_queue(self):
        """Restore the previous state of the queue.

        Note:
            The restore currently adds the items back into the queue
            using the URI, for items the Sonos system already knows about
            this is OK, but for other items, they may be missing some of
            their metadata as it will not be automatically picked up.
        """
        if self.queue is not None:
            # Clear the queue so that it can be reset
            self.device.clear_queue()
            # Now loop around all the queue entries adding them
            for queue_group in self.queue:
                for queue_item in queue_group:
                    self.device.add_uri_to_queue(queue_item.uri)

    def __enter__(self):
        self.snapshot()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.restore()
