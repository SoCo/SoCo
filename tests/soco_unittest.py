# pylint: disable-msg=R0904

"""This file contains the classes used to perform unit tests on the methods in
the SoCo class.

PLEASE TAKE NOTE: All of these unit tests are designed to run on a sonos
system without interfering with normal service. This means that they will not
raise the volume or leave the player in another state than it started in. They
have been made this way, since sonos is developed by volunteers, that in all
likelihood does not have a dedicated test system, so the tests must be able to
run on an ordinary system without annoying the neighboors and it should return
to its original state because those same developers will likely want to listen
to music while coding, without having it interrupted at every unit test.
PLEASE RESPECT THIS.
"""

import time
import unittest

import pytest

import soco

SOCO = None
pytestmark = pytest.mark.integration


class SoCoUnitTestInitError(Exception):
    """Exception for incomplete unit test initialization."""

    def __init__(self, message):
        Exception.__init__(self, message)


def init(**kwargs):
    """Initialize variables for the unittests that are only known at run
    time."""
    global SOCO  # pylint: disable-msg=W0603
    SOCO = soco.SoCo(kwargs["ip"])

    if len(SOCO.get_queue()) == 0:
        raise SoCoUnitTestInitError(
            "Unit tests on the SoCo class must be run "
            "with at least 1 item in the playlist"
        )

    transport_info = SOCO.get_current_transport_info()
    if transport_info["current_transport_state"] != "PLAYING":
        raise SoCoUnitTestInitError(
            "Unit tests on the SoCo class must be run " "with the sonos unit playing"
        )


def get_state():
    """Utility function to get the entire playing state before the unit tests
    starts to change it."""
    state = {
        "queue": SOCO.get_queue(0, 1000),
        "current_track_info": SOCO.get_current_track_info(),
    }
    return state


def set_state(state):
    """Utility function to set the entire state.

    Used to reset the unit after the unit tests have changed it
    """
    SOCO.stop()
    SOCO.clear_queue()
    for track in state["queue"]:
        SOCO.add_to_queue(track["uri"])
    SOCO.play_from_queue(int(state["current_track_info"]["playlist_position"]) - 1)
    SOCO.seek(state["current_track_info"]["position"])
    SOCO.play()


def wait(interval=0.1):
    """Convinience function to adjust sleep interval for all tests."""
    time.sleep(interval)


# Test return strings that are used a lot
NOT_TRUE = "The method did not return True"
NOT_EXP = "The method did not return the expected value"
NOT_TYPE = "The return value of the method did not have the expected type: {}"
NOT_IN_RANGE = "The returned value is not in the expected range"


# functions for running via pytest
def setup_module(module):
    ip = pytest.config.option.IP
    if ip is None:
        pytest.fail("No ip address specified. Use the --ip option.")
    init(ip=ip)
    state = get_state()
    module.state = state


def teardown_module(module):
    state = module.state
    set_state(state)


class Volume(unittest.TestCase):
    """Unit tests for the volume method."""

    def setUp(self):  # pylint: disable-msg=C0103
        self.valid_values = range(101)

    def test_get_and_set(self):
        """Tests if the set functionlity works when given valid arguments."""
        old = SOCO.volume
        self.assertIn(old, self.valid_values, NOT_IN_RANGE)
        if old == self.valid_values[0]:
            new = old + 1
        else:
            new = old - 1
        SOCO.volume = new
        wait()
        self.assertEqual(SOCO.volume, new, NOT_EXP)
        SOCO.volume = old
        wait()

    def test_invalid_arguments(self):
        """Tests if the set functionality coerces into range when given
        integers outside of allowed range."""
        old = SOCO.volume
        # NOTE We don't test coerce from too large values, since that would
        # put the unit at full volume
        SOCO.volume = self.valid_values[0] - 1
        wait()
        self.assertEqual(SOCO.volume, 0, NOT_EXP)
        SOCO.volume = old
        wait()

    def test_set_0(self):
        """Tests whether the volume can be set to 0. Regression test for:
        https://github.com/rahims/SoCo/issues/29
        """
        old = SOCO.volume
        SOCO.volume = 0
        wait()
        self.assertEqual(SOCO.volume, 0, NOT_EXP)
        SOCO.volume = old
        wait()


class Bass(unittest.TestCase):
    """Unit tests for the bass method.

    This class implements a full boundary value test.
    """

    def setUp(self):  # pylint: disable-msg=C0103
        self.valid_values = range(-10, 11)

    def test_get_and_set(self):
        """Tests if the set functionlity works when given valid arguments."""
        old = SOCO.bass
        self.assertIn(old, self.valid_values, NOT_IN_RANGE)
        # Values on the boundaries of the valid equivalence partition
        for value in [self.valid_values[0], self.valid_values[-1]]:
            SOCO.bass = value
            wait()
            self.assertEqual(SOCO.bass, value, NOT_EXP)
        SOCO.bass = old
        wait()

    def test_invalid_arguments(self):
        """Tests if the set functionality produces the expected "coerce in
        range" functionality when given a value outside of its range."""
        old = SOCO.bass
        # Values on the boundaries of the two invalid equivalence partitions
        SOCO.bass = self.valid_values[0] - 1
        wait()
        self.assertEqual(SOCO.bass, self.valid_values[0], NOT_EXP)
        SOCO.bass = self.valid_values[-1] + 1
        wait()
        self.assertEqual(SOCO.bass, self.valid_values[-1], NOT_EXP)
        SOCO.bass = old
        wait()


class Treble(unittest.TestCase):
    """Unit tests for the treble method This class implements a full boundary
    value test."""

    def setUp(self):  # pylint: disable-msg=C0103
        self.valid_values = range(-10, 11)

    def test_get_and_set(self):
        """Tests if the set functionlity works when given valid arguments."""
        old = SOCO.treble
        self.assertIn(old, self.valid_values, NOT_IN_RANGE)
        # Values on the boundaries of the valid equivalence partition
        for value in [self.valid_values[0], self.valid_values[-1]]:
            SOCO.treble = value
            wait()
            self.assertEqual(SOCO.treble, value, NOT_EXP)
        SOCO.treble = old
        wait()

    def test_invalid_arguments(self):
        """Tests if the set functionality produces the expected "coerce in
        range" functionality when given a value outside its range."""
        old = SOCO.treble
        # Values on the boundaries of the two invalid equivalence partitions
        SOCO.treble = self.valid_values[0] - 1
        wait()
        self.assertEqual(SOCO.treble, self.valid_values[0], NOT_EXP)
        SOCO.treble = self.valid_values[-1] + 1
        wait()
        self.assertEqual(SOCO.treble, self.valid_values[-1], NOT_EXP)
        SOCO.treble = old
        wait()


class GetCurrentTrackInfo(unittest.TestCase):
    """Unit test for the get_current_track_info method."""

    def setUp(self):  # pylint: disable-msg=C0103
        # The value in this list must be kept up to date with the values in
        # the test_get doc string
        self.info_keys = sorted(
            [
                "album",
                "artist",
                "title",
                "uri",
                "playlist_position",
                "duration",
                "album_art",
                "position",
            ]
        )

    def test_get(self):
        """Test is the return value is a dictinary and contains the following
        keys: album, artist, title, uri, playlist_position, duration,
        album_art and position
        """
        info = SOCO.get_current_track_info()
        self.assertIsInstance(info, dict, "Returned info is not a dict")
        self.assertEqual(
            sorted(info.keys()), self.info_keys, "Info does not contain the proper keys"
        )


class AddToQueue(unittest.TestCase):
    """Unit test for the add_to_queue method."""

    def test(self):
        """Gets the current queue, adds the last item of the current queue and
        then compares the length of the old queue with the new and checks that
        the last two elements are identical."""
        state = get_state()
        SOCO.pause()
        old_queue = SOCO.get_queue(0, 1000)
        # Add new element and check
        self.assertEqual(
            SOCO.add_to_queue(old_queue[-1]["uri"]), len(old_queue) + 1, ""
        )
        wait()
        new_queue = SOCO.get_queue()
        self.assertEqual(len(new_queue) - 1, len(old_queue))
        self.assertEqual(new_queue[-1], new_queue[-2])
        # Clean up
        set_state(state)
        wait()


class GetQueue(unittest.TestCase):
    """Unit test for the get_queue method."""

    def setUp(self):  # pylint: disable-msg=C0103
        # The values in this list must be kept up to date with the values in
        # the test_get doc string
        self.qeueu_element_keys = sorted(
            ["album", "artist", "uri", "album_art", "title"]
        )

    def test_get(self):
        """Tests is return value is a list of dictionaries and if each of
        the dictionaries contain the keys: album, artist, uri, album_art and
        title
        """
        queue = SOCO.get_queue()
        self.assertIsInstance(queue, list, NOT_TYPE.format("list"))
        for item in queue:
            self.assertIsInstance(item, dict, "Item in queue is not a dictionary")
            self.assertEqual(
                sorted(item.keys()),
                self.qeueu_element_keys,
                "The keys in the queue element dict are not the "
                "expected ones: {}".format(self.qeueu_element_keys),
            )


class GetCurrentTransportInfo(unittest.TestCase):
    """Unit test for the get_current_transport_info method."""

    def setUp(self):  # pylint: disable-msg=C0103
        # The values in this list must be kept up to date with the values in
        # the test doc string
        self.transport_info_keys = sorted(
            [
                "current_transport_status",
                "current_transport_state",
                "current_transport_speed",
            ]
        )

    def test(self):
        """Tests if the return value is a dictionary that contains the keys:
        current_transport_status, current_transport_state,
        current_transport_speed
        and that values have been found for all keys, i.e. they are not None
        """
        transport_info = SOCO.get_current_transport_info()
        self.assertIsInstance(transport_info, dict, NOT_TYPE.format("dict"))
        self.assertEqual(
            self.transport_info_keys,
            sorted(transport_info.keys()),
            "The keys in the speaker info dict are not the "
            "expected ones: {}".format(self.transport_info_keys),
        )
        for key, value in transport_info.items():
            self.assertIsNotNone(
                value,
                'The value for the key "{}" is None '
                "which indicate that no value was found for "
                "it".format(key),
            )


class GetSpeakerInfo(unittest.TestCase):
    """Unit test for the get_speaker_info method."""

    def setUp(self):  # pylint: disable-msg=C0103
        # The values in this list must be kept up to date with the values in
        # the test doc string
        self.info_keys = sorted(
            [
                "zone_name",
                "player_icon",
                "uid",
                "serial_number",
                "software_version",
                "hardware_version",
                "mac_address",
                "model_name",
                "model_number",
                "display_version",
            ]
        )

    def test(self):
        """Tests if the return value is a dictionary that contains the keys:
        zone_name, player_icon, uid, serial_number, software_version,
        hardware_version, mac_address, model_name, model_number, display_version
        and that values have been found for all keys, i.e. they are not None
        """
        speaker_info = SOCO.get_speaker_info()
        self.assertIsInstance(speaker_info, dict, NOT_TYPE.format("dict"))
        self.assertEqual(
            self.info_keys,
            sorted(speaker_info.keys()),
            "The "
            "keys in speaker info are not the expected ones: {}"
            "".format(self.info_keys),
        )
        for key, value in speaker_info.items():
            self.assertIsNotNone(
                value,
                'The value for the key "{}" is None '
                "which indicate that no value was found for "
                "it".format(key),
            )


# class GetSpeakersIp(unittest.TestCase):
# """ Unit tests for the get_speakers_ip method """

# TODO: Awaits https://github.com/rahims/SoCo/issues/26

# def test(self):
# print SOCO.get_speakers_ip()


class Pause(unittest.TestCase):
    """Unittest for the pause method."""

    def test(self):
        """Tests if the pause method works."""
        SOCO.pause()
        wait(1)
        new = SOCO.get_current_transport_info()["current_transport_state"]
        self.assertEqual(
            new, "PAUSED_PLAYBACK", "State after pause is not " '"PAUSED_PLAYBACK"'
        )
        SOCO.play()
        wait(1)


class Stop(unittest.TestCase):
    """Unittest for the stop method."""

    def test(self):
        """Tests if the stop method works."""
        state = get_state()
        SOCO.stop()
        wait(1)
        new = SOCO.get_current_transport_info()["current_transport_state"]
        self.assertEqual(new, "STOPPED", 'State after stop is not "STOPPED"')
        set_state(state)  # Reset unit the way it was before the test
        wait(1)


class Play(unittest.TestCase):
    """Unit test for the play method."""

    def test(self):
        """Tests if the play method works."""
        SOCO.pause()
        wait(1)
        on_pause = SOCO.get_current_transport_info()["current_transport_state"]
        self.assertEqual(
            on_pause, "PAUSED_PLAYBACK", "State after pause is " 'not "PAUSED_PLAYBACK"'
        )
        SOCO.play()
        wait(1)
        on_play = SOCO.get_current_transport_info()["current_transport_state"]
        self.assertEqual(
            on_play, "PLAYING", "State after play is not " '"PAUSED_PLAYBACK"'
        )


class Mute(unittest.TestCase):
    """Unit test for the mute method."""

    def test(self):
        """Tests of the mute method works."""
        old = SOCO.mute
        self.assertEqual(
            old, 0, "The unit should not be muted when running " "the unit tests"
        )
        SOCO.mute = True
        wait()
        new = SOCO.mute
        self.assertEqual(new, 1, "The unit did not successfully mute")
        SOCO.mute = False
        wait()


class RemoveFromQueue(unittest.TestCase):
    """Unit test for the remove_from_queue method."""

    def test(self):
        """Tests if the remove_from_queue method works."""
        old_queue = SOCO.get_queue()
        track_to_remove = old_queue[-1]
        SOCO.remove_from_queue(len(old_queue))
        wait()
        new_queue = SOCO.get_queue()
        self.assertNotEqual(
            old_queue,
            new_queue,
            "No difference between " "queues before and after removing the last item",
        )
        self.assertEqual(
            len(new_queue),
            len(old_queue) - 1,
            "The length of " "queue after removing a track is not length before - " "1",
        )
        # Clean up
        SOCO.add_to_queue(track_to_remove["uri"])
        wait()
        self.assertEqual(old_queue, SOCO.get_queue(), "Clean up unsuccessful")


class Seek(unittest.TestCase):
    """Unit test for the seek method."""

    def test_valid(self):
        """Tests if the seek method works with valid input."""
        original_position = SOCO.get_current_track_info()["position"]
        # Format 1
        SOCO.seek("0:00:00")
        wait()
        position = SOCO.get_current_track_info()["position"]
        self.assertIn(position, ["0:00:00", "0:00:01"])
        # Reset and format 2
        SOCO.seek(original_position)
        SOCO.seek("00:00:00")
        wait()
        position = SOCO.get_current_track_info()["position"]
        self.assertIn(position, ["0:00:00", "0:00:01"])
        # Clean up
        SOCO.seek(original_position)
        wait()

    def test_invald(self):
        """Tests if the seek method properly fails with invalid input."""
        for string in ["invalid_time_string", "5:12", "6", "aa:aa:aa"]:
            with self.assertRaises(ValueError):
                SOCO.seek(string)
