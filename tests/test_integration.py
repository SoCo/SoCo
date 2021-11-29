# pylint: disable-msg=too-few-public-methods, redefined-outer-name, no-self-use

"""This file contains the classes used to perform integration tests on the
methods in the SoCo class. They access a real Sonos system.

PLEASE TAKE NOTE: All of these tests are designed to run on a Sonos system
without interfering with normal service. This means that they must not raise
the volume or must leave the player in the same state as they found it in. They
have been made this way since SoCo is developed by volunteers who in all
likelihood do not have a dedicated test system. Accordingly the tests must not
annoy the neighbors, and should return the system to its original state so that
the developers can listen to their music while coding, without having it
interrupted at every unit test!

PLEASE RESPECT THIS.
"""


import time

import pytest

import soco as soco_module
from soco.data_structures import (
    DidlMusicTrack,
    DidlPlaylistContainer,
    SearchResult,
)
from soco.music_library import MusicLibrary
from soco.exceptions import SoCoUPnPException

# Mark all tests in this module with the pytest custom "integration" marker so
# they can be selected or deselected as a whole, eg:
# py.test -m "integration"
# or
# py.test -m "no integration"
pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def soco(request):
    """Set up and tear down the soco fixture used by all tests."""
    # Get the ip address from the command line, and create the soco object
    # Only one is used per test session, hence the decorator
    ip = request.config.option.IP
    if ip is None:
        pytest.fail("No ip address specified. Use the --ip option.")
    soco_instance = soco_module.SoCo(ip)
    # Check the device is playing and has items in the queue
    if len(soco_instance.get_queue()) == 0:
        pytest.fail(
            "Integration tests on the SoCo class must be run "
            "with at least 1 item in the playlist."
        )

    transport_info = soco_instance.get_current_transport_info()
    if transport_info["current_transport_state"] != "PLAYING":
        pytest.fail(
            "Integration tests on the SoCo class must be run "
            "with the Sonos unit playing."
        )
    # Save the device's state
    state = {
        "queue": soco_instance.get_queue(0, 1000),
        "current_track_info": soco_instance.get_current_track_info(),
    }

    # Yield the device to the test function
    yield soco_instance

    # Tear down. Restore state
    soco_instance.stop()
    soco_instance.clear_queue()
    for track in state["queue"]:
        soco_instance.add_to_queue(track)
    soco_instance.play_from_queue(
        int(state["current_track_info"]["playlist_position"]) - 1
    )
    soco_instance.seek(state["current_track_info"]["position"])
    soco_instance.play()


def wait(interval=0.1):
    """Convenience function to adjust sleep interval for all tests."""
    time.sleep(interval)


class TestVolume:
    """Integration tests for the volume property."""

    valid_values = range(101)

    @pytest.fixture(autouse=True)
    def restore_volume(self, soco):
        """A fixture which restores volume after each test in the class is
        run."""
        old = soco.volume
        yield
        soco.volume = old
        wait()

    def test_get_and_set(self, soco):
        """Test if the set functionlity works when given valid arguments."""
        old = soco.volume
        assert old in self.valid_values
        if old == self.valid_values[0]:
            new = old + 1
        else:
            new = old - 1
        soco.volume = new
        wait()
        assert soco.volume == new

    def test_invalid_arguments(self, soco):
        """Test if the set functionality coerces into range when given integers
        outside of allowed range."""

        # NOTE We don't test coerce from too large values, since that would
        # put the unit at full volume
        soco.volume = self.valid_values[0] - 1
        wait()
        assert soco.volume == 0

    def test_set_0(self):
        """Test whether the volume can be set to 0. Regression test for:
        https://github.com/rahims/soco/issues/29
        """

        soco.volume = 0
        wait()
        assert soco.volume == 0


class TestBass:
    """Integration tests for the bass property.

    This class implements a full boundary value test.
    """

    valid_values = range(-10, 11)

    @pytest.fixture(autouse=True)
    def restore_bass(self, soco):
        """A fixture which restores bass EQ after each test in the class is
        run."""
        old = soco.bass
        yield
        soco.bass = old
        wait()

    def test_get_and_set(self, soco):
        """Test if the set functionlity works when given valid arguments."""
        assert soco.bass in self.valid_values
        # Values on the boundaries of the valid equivalence partition
        for value in [self.valid_values[0], self.valid_values[-1]]:
            soco.bass = value
            wait()
            assert soco.bass == value

    def test_invalid_arguments(self, soco):
        """Test if the set functionality produces the expected "coerce in
        range" functionality when given a value outside of its range."""
        # Values on the boundaries of the two invalid equivalence partitions
        soco.bass = self.valid_values[0] - 1
        wait()
        assert soco.bass == self.valid_values[0]
        soco.bass = self.valid_values[-1] + 1
        wait()
        assert soco.bass == self.valid_values[-1]


class TestTreble:
    """Integration tests for the treble property.

    This class implements a full boundary value test.
    """

    valid_values = range(-10, 11)

    @pytest.fixture(autouse=True)
    def restore_treble(self, soco):
        """A fixture which restores treble EQ after each test in the class is
        run."""
        old = soco.treble
        yield
        soco.treble = old
        wait()

    def test_get_and_set(self, soco):
        """Test if the set functionlity works when given valid arguments."""
        assert soco.treble in self.valid_values
        # Values on the boundaries of the valid equivalence partition
        for value in [self.valid_values[0], self.valid_values[-1]]:
            soco.treble = value
            wait()
            assert soco.treble == value

    def test_invalid_arguments(self, soco):
        """Test if the set functionality produces the expected "coerce in
        range" functionality when given a value outside its range."""
        # Values on the boundaries of the two invalid equivalence partitions
        soco.treble = self.valid_values[0] - 1
        wait()
        assert soco.treble == self.valid_values[0]
        soco.treble = self.valid_values[-1] + 1
        wait()
        assert soco.treble == self.valid_values[-1]


class TestMute:
    """Integration test for the mute method."""

    def test(self, soco):
        """Test if the mute method works."""
        old = soco.mute
        assert old is False, (
            "The unit should not be muted when running " "the unit tests."
        )
        soco.mute = True
        wait()
        new = soco.mute
        assert new is True
        soco.mute = False
        wait()
        assert soco.mute is False


class TestGetCurrentTransportInfo:
    """Integration test for the get_current_transport_info method."""

    # The values in this list must be kept up to date with the values in
    # the test doc string
    transport_info_keys = sorted(
        [
            "current_transport_status",
            "current_transport_state",
            "current_transport_speed",
        ]
    )

    def test(self, soco):
        """Test if the return value is a dictionary that contains the keys:
        current_transport_status, current_transport_state,
        current_transport_speed and that values have been found for all keys,
        i.e. they are not None.
        """
        transport_info = soco.get_current_transport_info()
        assert isinstance(transport_info, dict)
        assert self.transport_info_keys == sorted(transport_info.keys())
        for _, value in transport_info.items():
            assert value is not None


class TestTransport:
    """Integration tests for transport methods (play, pause etc)."""

    def test_pause_and_play(self, soco):
        """Test if the pause and play methods work."""
        soco.pause()
        wait(1)
        on_pause = soco.get_current_transport_info()["current_transport_state"]
        assert on_pause == "PAUSED_PLAYBACK"
        soco.play()
        wait(1)
        on_play = soco.get_current_transport_info()["current_transport_state"]
        assert on_play == "PLAYING"

    def test_stop(self, soco):
        """Test if the stop method works."""
        soco.stop()
        wait(1)
        new = soco.get_current_transport_info()["current_transport_state"]
        assert new == "STOPPED"
        soco.play()
        wait(1)
        on_play = soco.get_current_transport_info()["current_transport_state"]
        assert on_play == "PLAYING"

    def test_seek_valid(self, soco):
        """Test if the seek method works with valid input."""
        original_position = soco.get_current_track_info()["position"]
        # Format 1
        soco.seek("0:00:00")
        wait()
        position = soco.get_current_track_info()["position"]
        assert position in ["0:00:00", "0:00:01"]
        # Reset and format 2
        soco.seek(original_position)
        soco.seek("00:00:00")
        wait()
        position = soco.get_current_track_info()["position"]
        assert position in ["0:00:00", "0:00:01"]
        # Clean up
        soco.seek(original_position)
        wait()

    def test_seek_invald(self, soco):
        """Test if the seek method properly fails with invalid input."""
        for string in ["invalid_time_string", "5:12", "6", "aa:aa:aa"]:
            with pytest.raises(ValueError):
                soco.seek(string)


class TestGetCurrentTrackInfo:
    """Integration test for the get_current_track_info method."""

    info_keys = sorted(
        [
            "album",
            "artist",
            "title",
            "uri",
            "metadata",
            "playlist_position",
            "duration",
            "album_art",
            "position",
        ]
    )

    def test_get(self, soco):
        """Test that the return value is a dictionary and contains the following
        keys: album, artist, title, uri, playlist_position, duration,
        album_art and position.
        """
        info = soco.get_current_track_info()
        assert isinstance(info, dict)
        assert sorted(info.keys()) == self.info_keys


class TestGetCurrentMediaInfo:
    """Integration test for the get_current_media_info method."""

    info_keys = sorted(
        [
            "uri",
            "channel",
        ]
    )

    def test_get(self, soco):
        """Test that the return value is a dictionary and contains the expected
        keys.
        """
        info = soco.get_current_media_info()
        assert isinstance(info, dict)
        assert sorted(info.keys()) == self.info_keys


class TestGetSpeakerInfo:
    """Integration test for the get_speaker_info method."""

    # The values in this list must be kept up to date with the values in
    # the test doc string
    info_keys = sorted(
        [
            "zone_name",
            "zone_icon",
            "uid",
            "serial_number",
            "software_version",
            "hardware_version",
            "mac_address",
        ]
    )

    def test(self, soco):
        """Test if the return value is a dictionary that contains the keys:
        zone_name, zone_icon, uid, serial_number, software_version,
        hardware_version, mac_address
        and that values have been found for all keys, i.e. they are not None.
        """
        speaker_info = soco.get_speaker_info()
        assert isinstance(speaker_info, dict)
        for _, value in speaker_info.items():
            assert value is not None


# TODO: test GetSpeakersIp


class TestGetQueue:
    """Integration test for the get_queue method."""

    # The values in this list must be kept up to date with the values in
    # the test doc string
    queue_element_keys = sorted(
        ["album", "creator", "resources", "album_art_uri", "title"]
    )

    def test_get(self, soco):
        """Test is return value is a list of DidlMusicTracks and if each of
        the objects contain the attributes: album, creator, resources,
        album_art_uri and title.
        """
        queue = soco.get_queue(0, 100)
        assert isinstance(queue, list)
        for item in queue:
            assert isinstance(item, DidlMusicTrack)
            for key in self.queue_element_keys:
                assert getattr(item, key)


class TestAddToQueue:
    """Integration test for the add_to_queue method."""

    def test_add_to_queue(self, soco):
        """Get the current queue, add the last item of the current queue and
        then compare the length of the old queue with the new and check that
        the last two elements are identical."""

        old_queue = soco.get_queue(0, 1000)
        # Add new element and check
        assert (soco.add_to_queue(old_queue[-1])) == len(old_queue) + 1
        wait()
        new_queue = soco.get_queue()
        assert (len(new_queue) - 1) == len(old_queue)
        assert (new_queue[-1].title) == (new_queue[-2].title)


class TestRemoveFromQueue:
    """Integration test for the remove_from_queue method."""

    def test(self, soco):
        """Test if the remove_from_queue method works."""
        old_queue = soco.get_queue()
        soco.remove_from_queue(len(old_queue) - 1)  # queue index is 0 based
        wait()
        new_queue = soco.get_queue()
        assert old_queue != new_queue, (
            "No difference between " "queues before and after removing the last item"
        )
        assert len(new_queue) == len(old_queue) - 1


class TestSonosPlaylist:
    """Integration tests for Sonos Playlist Management."""

    existing_playlists = None
    playlist_name = "zSocoTestPlayList42"

    @pytest.fixture(autouse=True)
    def restore_sonos_playlists(self, soco):
        """A fixture which cleans up after each sonos playlist test."""
        if self.existing_playlists is None:
            self.existing_playlists = soco.get_sonos_playlists()
            if self.playlist_name in [x.title for x in self.existing_playlists]:
                msg = "%s is an existing playlist." % self.playlist_name
                pytest.fail(msg)

        yield
        for sonos_playlist in soco.get_sonos_playlists():
            if sonos_playlist.title == self.playlist_name:
                soco.remove_sonos_playlist(sonos_playlist=sonos_playlist)

    def test_create(self, soco):
        """Test creating a new empty Sonos playlist."""
        existing_playlists = {x.item_id for x in soco.get_sonos_playlists()}
        new_playlist = soco.create_sonos_playlist(title=self.playlist_name)
        assert type(new_playlist) is DidlPlaylistContainer

        new_pl = {x.item_id for x in soco.get_sonos_playlists()}
        assert new_pl != existing_playlists
        assert new_pl - existing_playlists == {new_playlist.item_id}

    def test_create_from_queue(self, soco):
        """Test creating a Sonos playlist from the current queue."""
        playlist = soco.create_sonos_playlist_from_queue(self.playlist_name)
        assert type(playlist) is DidlPlaylistContainer

        prslt = soco.music_library.browse(ml_item=playlist)
        qrslt = soco.get_queue()
        assert len(prslt) == len(qrslt)
        assert prslt.total_matches == qrslt.total_matches
        assert prslt.number_returned == qrslt.number_returned
        # compare uri because item_id is different, SQ:xx/n for playlist
        for p_item, q_item in zip(prslt, qrslt):
            assert p_item.resources[0].uri == q_item.resources[0].uri

    def test_remove_playlist(self, soco):
        """Test removing a Sonos playlist."""
        # a place holder, remove_sonos_playlist is exercised in the
        # 'restore_sonos_playlists'
        pass

    def test_remove_playlist_itemid(self, soco):
        """Test removing a Sonos playlist by item_id."""
        new_playlist = soco.create_sonos_playlist(title=self.playlist_name)
        assert type(new_playlist) is DidlPlaylistContainer
        assert soco.remove_sonos_playlist(new_playlist.item_id)
        found = False
        for sonos_playlist in soco.get_sonos_playlists():
            if sonos_playlist.title == self.playlist_name:
                found = True
                break
        assert found is False, "new_playlist was not removed by item_id"

    def test_remove_playlist_bad_id(self, soco):
        """Test attempting to remove a Sonos playlist using a bad id."""
        # junky bad
        with pytest.raises(SoCoUPnPException):
            soco.remove_sonos_playlist("SQ:-7")
        # realistic non-existing
        playlists = soco.get_sonos_playlists()
        # Accommodate the case of no existing playlists
        if len(playlists) == 0:
            hpl_i = 0
        else:
            hpl_i = max([int(x.item_id.split(":")[1]) for x in playlists])
        with pytest.raises(SoCoUPnPException):
            soco.remove_sonos_playlist("SQ:{}".format(hpl_i + 1))


class TestTimer:
    """Integration tests for timers on Sonos"""

    existing_timer = None

    @pytest.fixture(autouse=True)
    def restore_timer(self, soco):
        """A fixture which cleans up after each timer test."""
        existing_timer = soco.get_sleep_timer()

        yield
        soco.set_sleep_timer(existing_timer)

    def test_get_set_timer(self, soco):
        """Test setting the timer"""
        assert soco.set_sleep_timer(7200) is None
        result = soco.get_sleep_timer()
        if not any(result == s for s in [7200, 7199, 7198]):
            pytest.fail(
                "Set timer to 7200, but sonos reports back time as %s"
                % result["RemainingSleepTimerDuration"]
            )


class TestReorderSonosPlaylist:
    """Integration tests for Sonos Playlist Management."""

    existing_playlists = None
    playlist_name = "zSocoTestPlayList42"
    test_playlist = None
    queue_length = None

    @pytest.fixture(autouse=True, scope="class")
    def restore_sonos_playlists(self, soco):
        """A fixture which cleans up after each sonos playlist test."""
        if self.existing_playlists is None:
            self.existing_playlists = soco.get_sonos_playlists()
        if self.playlist_name in [x.title for x in self.existing_playlists]:
            msg = "%s is an existing playlist." % self.playlist_name
            pytest.fail(msg)

        queue_list = soco.get_queue()
        if len(queue_list) < 2:
            msg = "You must have 3 or more items in your queue for testing."
            pytest.fail(msg)
        playlist = soco.create_sonos_playlist_from_queue(self.playlist_name)
        self.__class__.queue_length = soco.queue_size
        self.__class__.test_playlist = playlist
        yield

        soco.contentDirectory.DestroyObject([("ObjectID", self.test_playlist.item_id)])

    def _reset_spl_contents(self, soco):
        """Ensure test playlist matches queue for each test."""
        soco.contentDirectory.DestroyObject([("ObjectID", self.test_playlist.item_id)])
        playlist = soco.create_sonos_playlist_from_queue(self.playlist_name)
        self.__class__.test_playlist = playlist
        return playlist, self.__class__.queue_length

    def test_reverse_track_order(self, soco):
        """Test reversing the tracks in the Sonos playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        tracks = ",".join([str(x) for x in reversed(range(num_tracks))])
        new_pos = ",".join([str(x) for x in range(num_tracks)])
        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == 0
        assert response["length"] == num_tracks
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        for s_item, q_item in zip(spl, reversed(soco.get_queue())):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_swap_first_two_items(self, soco):
        """Test a use case in doc string. Swapping the positions of the first
        two tracks in the Sonos playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        tracks = [
            0,
        ]
        new_pos = [
            1,
        ]

        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == 0
        assert response["length"] == num_tracks
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        que = soco.get_queue()
        assert spl[0].resources[0].uri == que[1].resources[0].uri
        assert spl[1].resources[0].uri == que[0].resources[0].uri
        # FIXME remove the list on spl and que before slicing, when
        # the deprecated __getitem__ on ListOfMusicInfoItems is
        # removed
        for s_item, q_item in zip(list(spl)[2:], list(que)[2:]):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_remove_first_track(self, soco):
        """Test removing first track from Sonos Playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        tracks = [
            0,
        ]
        new_pos = [
            None,
        ]

        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == -1
        assert response["length"] == num_tracks - 1
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        # FIXME remove the list on queue() call, when the deprecated
        # __getitem__ on ListOfMusicInfoItems is removed
        que = list(soco.get_queue())[1:]
        for s_item, q_item in zip(spl, que):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_remove_first_track_full(self, soco):
        """Test removing first track from Sonos Playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        tracks = [0] + list(range(num_tracks - 1))  # [0, 0, 1, ..., n-1]
        new_pos = [None,] + list(
            range(num_tracks - 1)
        )  # [None, 0, ..., n-1]
        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == -1
        assert response["length"] == num_tracks - 1
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        # FIXME remove the list on queue() call, when the deprecated
        # __getitem__ on ListOfMusicInfoItems is removed
        que = list(soco.get_queue())[1:]
        for s_item, q_item in zip(spl, que):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_remove_last_track(self, soco):
        """Test removing last track from Sonos Playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        tracks = range(num_tracks)
        new_pos = list(range(num_tracks - 1)) + [
            None,
        ]
        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == -1
        assert response["length"] == num_tracks - 1
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        # FIXME remove the list on queue() call, when the deprecated
        # __getitem__ on ListOfMusicInfoItems is removed
        que = list(soco.get_queue())[:-1]
        for s_item, q_item in zip(spl, que):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_remove_between_track(self, soco):
        """Test removing a middle track from Sonos Playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        ndx = int(num_tracks / 2)
        tracks = [ndx]
        new_pos = [None]
        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == -1
        assert response["length"] == num_tracks - 1
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        que = soco.get_queue()
        del que[ndx]
        for s_item, q_item in zip(spl, que):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_remove_some_tracks(self, soco):  # pylint: disable=R0914
        """Test removing some tracks from Sonos Playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        # get rid of the even numbered tracks
        tracks = sorted([x for x in range(num_tracks) if not x & 1], reverse=True)
        new_pos = [None for _ in tracks]
        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == -1 * len(new_pos)
        assert response["length"] == num_tracks + response["change"]
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        que = soco.get_queue()
        for ndx in tracks:
            del que[ndx]
        for s_item, q_item in zip(spl, que):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_remove_all_tracks(self, soco):
        """Test removing all tracks from Sonos Playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        # get rid of the even numbered tracks
        tracks = sorted(range(num_tracks), reverse=True)
        new_pos = [None for _ in tracks]
        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == -1 * num_tracks
        assert response["length"] == num_tracks + response["change"]
        assert response["length"] == 0
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        assert len(spl) == 0

    def test_reorder_and_remove_track(self, soco):
        """Test reorder and removing a track from Sonos Playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        tracks = [1, 2]
        new_pos = [0, None]
        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == -1
        assert response["length"] == num_tracks + response["change"]
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        que = soco.get_queue()
        assert spl[0].resources[0].uri == que[1].resources[0].uri

    def test_object_id_is_object(self, soco):
        """Test removing all tracks from Sonos Playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        tracks = sorted(range(num_tracks), reverse=True)
        new_pos = [None for _ in tracks]
        args = {"sonos_playlist": test_playlist, "tracks": tracks, "new_pos": new_pos}
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == -1 * num_tracks
        assert response["length"] == num_tracks + response["change"]
        assert response["length"] == 0
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        assert len(spl) == 0

    def test_remove_all_string(self, soco):
        """Remove all in one op by using strings."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        # we know what we are doing
        tracks = ",".join([str(x) for x in range(num_tracks)])
        new_pos = ""
        args = {"sonos_playlist": test_playlist, "tracks": tracks, "new_pos": new_pos}
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == -1 * num_tracks
        assert response["length"] == num_tracks + response["change"]
        assert response["length"] == 0
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        assert len(spl) == 0

    def test_remove_and_reorder_string(self, soco):
        """test remove then reorder using string arguments."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        tracks = "0,2"  # trackA, trackB, trackC, ...
        new_pos = ",0"  # trackC, trackB, ...
        args = {"sonos_playlist": test_playlist, "tracks": tracks, "new_pos": new_pos}
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == -1
        assert response["length"] == num_tracks + response["change"]
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        que = soco.get_queue()
        assert spl[0].resources[0].uri == que[2].resources[0].uri
        assert spl[1].resources[0].uri == que[1].resources[0].uri

    def test_move_track_string(self, soco):
        """Test a simple move with strings."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        tracks = "0"
        new_pos = "1"
        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == 0
        assert response["length"] == num_tracks
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        que = soco.get_queue()
        assert spl[0].resources[0].uri == que[1].resources[0].uri
        assert spl[1].resources[0].uri == que[0].resources[0].uri
        # FIXME remove the list on spl and que before slicing, when
        # the deprecated __getitem__ on ListOfMusicInfoItems is
        # removed
        for s_item, q_item in zip(list(spl)[2:], list(que)[2:]):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_move_track_int(self, soco):
        """Test a simple move with ints."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        tracks = 1
        new_pos = 0
        args = {
            "sonos_playlist": test_playlist.item_id,
            "tracks": tracks,
            "new_pos": new_pos,
        }
        response = soco.reorder_sonos_playlist(**args)
        assert response["change"] == 0
        assert response["length"] == num_tracks
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        que = soco.get_queue()
        assert spl[0].resources[0].uri == que[1].resources[0].uri
        assert spl[1].resources[0].uri == que[0].resources[0].uri
        # FIXME remove the list on spl and que before slicing, when
        # the deprecated __getitem__ on ListOfMusicInfoItems is
        # removed
        for s_item, q_item in zip(list(spl)[2:], list(que)[2:]):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_clear_sonos_playlist(self, soco):
        """Test the clear_sonos_playlist helper function."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        response = soco.clear_sonos_playlist(test_playlist)
        assert response["change"] == -1 * num_tracks
        assert response["length"] == num_tracks + response["change"]
        assert response["length"] == 0
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        assert len(spl) == 0

    def test_clear_empty_sonos_playlist(self, soco):
        """Test clearing an already empty Sonos playlist."""
        test_playlist, _ = self._reset_spl_contents(soco)
        response = soco.clear_sonos_playlist(test_playlist)
        assert response["length"] == 0
        update_id = response["update_id"]
        new_response = soco.clear_sonos_playlist(test_playlist, update_id=update_id)
        assert new_response["change"] == 0
        assert new_response["length"] == 0
        assert new_response["update_id"] == update_id

    def test_move_in_sonos_playlist(self, soco):
        """Test method move_in_sonos_playlist."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        args = {"sonos_playlist": test_playlist.item_id, "track": 0, "new_pos": 1}
        response = soco.move_in_sonos_playlist(**args)
        assert response["change"] == 0
        assert response["length"] == num_tracks
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        que = soco.get_queue()
        assert spl[0].resources[0].uri == que[1].resources[0].uri
        assert spl[1].resources[0].uri == que[0].resources[0].uri
        # FIXME remove the list on spl and que before slicing, when
        # the deprecated __getitem__ on ListOfMusicInfoItems is
        # removed
        for s_item, q_item in zip(list(spl)[2:], list(que)[2:]):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_remove_from_sonos_playlist(self, soco):
        """Test remove_from_sonos_playlist method."""
        test_playlist, num_tracks = self._reset_spl_contents(soco)
        args = {"sonos_playlist": test_playlist.item_id, "track": 0}
        response = soco.remove_from_sonos_playlist(**args)
        assert response["change"] == -1
        assert response["length"] == num_tracks - 1
        assert response["update_id"] != 0
        spl = soco.music_library.browse(ml_item=test_playlist)
        # FIXME remove the list on queue() call, when the deprecated
        # __getitem__ on ListOfMusicInfoItems is removed
        que = list(soco.get_queue())[1:]
        for s_item, q_item in zip(spl, que):
            assert s_item.resources[0].uri == q_item.resources[0].uri

    def test_get_sonos_playlist_by_attr(self, soco):
        """Test test_get_sonos_playlist_by_attr."""
        test_playlist, _ = self._reset_spl_contents(soco)
        by_name = soco.get_sonos_playlist_by_attr("title", self.playlist_name)
        assert test_playlist.item_id == by_name.item_id
        by_id = soco.get_sonos_playlist_by_attr("item_id", test_playlist.item_id)
        assert test_playlist.item_id == by_id.item_id
        with pytest.raises(AttributeError):
            soco.get_sonos_playlist_by_attr("fred", "wilma")

        with pytest.raises(ValueError):
            soco.get_sonos_playlist_by_attr("item_id", "wilma")


class TestMusicLibrary:
    """The the music library methods"""

    search_types = list(MusicLibrary.SEARCH_TRANSLATION.keys())
    specific_search_methods = (
        "artists",
        "album_artists",
        "albums",
        "genres",
        "composers",
        "tracks",
        "playlists",
        "sonos_favorites",
        "favorite_radio_stations",
        "favorite_radio_shows",
    )

    @pytest.mark.parametrize("search_type", specific_search_methods)
    def test_from_specific_search_methods(self, soco, search_type):
        """Test getting favorites from the music library"""
        search_method = getattr(soco.music_library, "get_" + search_type)
        search_result = search_method()
        assert isinstance(search_result, SearchResult)

    @pytest.mark.parametrize("search_type", search_types)
    def test_music_library_information(self, soco, search_type):
        """Test getting favorites from the music library"""
        search_result = soco.music_library.get_music_library_information(search_type)
        assert isinstance(search_result, SearchResult)
