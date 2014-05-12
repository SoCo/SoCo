# -*- coding: utf-8 -*-
# pylint: disable-msg=too-few-public-methods, redefined-outer-name, no-self-use

""" This file contains the classes used to perform integration tests on the
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

from __future__ import unicode_literals

import time
import pytest

import soco as soco_module

# Mark all tests in this module with the pytest custom "integration" marker so
# they can be selected or deselected as a whole, eg:
# py.test -m "integration"
# or
# py.test -m "no integration"
pytestmark = pytest.mark.integration


@pytest.yield_fixture(scope='session')
def soco():
    """ Set up and tear down the soco fixture used by all tests. """
    # Get the ip address from the command line, and create the soco object
    # Only one is used per test session, hence the decorator
    ip = pytest.config.option.IP
    if ip is None:
        pytest.fail("No ip address specified. Use the --ip option.")
    soco = soco_module.SoCo(ip)
    # Check the device is playing and has items in the queue
    if len(soco.get_queue()) == 0:
        pytest.fail('Integration tests on the SoCo class must be run '
                    'with at least 1 item in the playlist.')

    transport_info = soco.get_current_transport_info()
    if transport_info['current_transport_state'] != 'PLAYING':
        pytest.fail('Integration tests on the SoCo class must be run '
                    'with the Sonos unit playing.')
    # Save the device's state
    state = {'queue': soco.get_queue(0, 1000),
             'current_track_info': soco.get_current_track_info()}

    # Yield the device to the test function
    yield soco

    # Tear down. Restore state
    soco.stop()
    soco.clear_queue()
    for track in state['queue']:
        soco.add_to_queue(track['uri'])
    soco.play_from_queue(
        int(state['current_track_info']['playlist_position']) - 1)
    soco.seek(state['current_track_info']['position'])
    soco.play()


def wait(interval=0.1):
    """ Convenience function to adjust sleep interval for all tests. """
    time.sleep(interval)


class TestVolume(object):
    """ Integration tests for the volume property """

    valid_values = range(101)

    @pytest.yield_fixture(autouse=True)
    def restore_volume(self, soco):
        """ A fixture which restores volume after each test in the class is
        run. """
        old = soco.volume
        yield
        soco.volume = old
        wait()

    def test_get_and_set(self, soco):
        """ Test if the set functionlity works when given valid arguments. """
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
        """ Test if the set functionality coerces into range when given
        integers outside of allowed range.
        """

        # NOTE We don't test coerce from too large values, since that would
        # put the unit at full volume
        soco.volume = self.valid_values[0] - 1
        wait()
        assert soco.volume == 0

    def test_set_0(self):
        """ Test whether the volume can be set to 0. Regression test for:
        https://github.com/rahims/soco/issues/29
        """

        soco.volume = 0
        wait()
        assert soco.volume == 0


class TestBass(object):
    """ Integration tests for the bass property. This class implements a full
    boundary value test.
    """

    valid_values = range(-10, 11)

    @pytest.yield_fixture(autouse=True)
    def restore_bass(self, soco):
        """ A fixture which restores bass EQ after each test in the class is
        run. """
        old = soco.bass
        yield
        soco.bass = old
        wait()

    def test_get_and_set(self, soco):
        """ Test if the set functionlity works when given valid arguments. """
        assert soco.bass in self.valid_values
        # Values on the boundaries of the valid equivalence partition
        for value in [self.valid_values[0], self.valid_values[-1]]:
            soco.bass = value
            wait()
            assert soco.bass == value

    def test_invalid_arguments(self, soco):
        """ Test if the set functionality produces the expected "coerce in
        range" functionality when given a value outside of its range.
        """
        # Values on the boundaries of the two invalid equivalence partitions
        soco.bass = self.valid_values[0] - 1
        wait()
        assert soco.bass == self.valid_values[0]
        soco.bass = self.valid_values[-1] + 1
        wait()
        assert soco.bass == self.valid_values[-1]


class TestTreble(object):
    """ Integration tests for the treble property. This class implements a full
    boundary value test.
    """

    valid_values = range(-10, 11)

    @pytest.yield_fixture(autouse=True)
    def restore_treble(self, soco):
        """ A fixture which restores treble EQ after each test in the class is
        run. """
        old = soco.treble
        yield
        soco.treble = old
        wait()

    def test_get_and_set(self, soco):
        """ Test if the set functionlity works when given valid arguments. """
        assert soco.treble in self.valid_values
        # Values on the boundaries of the valid equivalence partition
        for value in [self.valid_values[0], self.valid_values[-1]]:
            soco.treble = value
            wait()
            assert soco.treble == value

    def test_invalid_arguments(self, soco):
        """ Test if the set functionality produces the expected "coerce in
        range" functionality when given a value outside its range.
        """
         # Values on the boundaries of the two invalid equivalence partitions
        soco.treble = self.valid_values[0] - 1
        wait()
        assert soco.treble == self.valid_values[0]
        soco.treble = self.valid_values[-1] + 1
        wait()
        assert soco.treble == self.valid_values[-1]


class TestMute(object):
    """ Integration test for the mute method. """

    def test(self, soco):
        """ Test if the mute method works """
        old = soco.mute
        assert old is False, ('The unit should not be muted when running '
                              'the unit tests.')
        soco.mute = True
        wait()
        new = soco.mute
        assert new is True
        soco.mute = False
        wait()
        assert soco.mute is False


class TestGetCurrentTransportInfo(object):
    """ Integration test for the get_current_transport_info method. """

    # The values in this list must be kept up to date with the values in
    # the test doc string
    transport_info_keys = sorted(['current_transport_status',
                                  'current_transport_state',
                                  'current_transport_speed'])

    def test(self, soco):
        """ Test if the return value is a dictionary that contains the keys:
        current_transport_status, current_transport_state,
        current_transport_speed and that values have been found for all keys,
        i.e. they are not None.
        """
        transport_info = soco.get_current_transport_info()
        assert isinstance(transport_info, dict)
        assert self.transport_info_keys == sorted(transport_info.keys())
        for _, value in transport_info.items():
            assert value is not None


class TestTransport(object):
    """ Integration tests for transport methods (play, pause etc). """

    def test_pause_and_play(self, soco):
        """ Test if the pause and play methods work """
        soco.pause()
        wait(1)
        on_pause = soco.get_current_transport_info()['current_transport_state']
        assert on_pause == 'PAUSED_PLAYBACK'
        soco.play()
        wait(1)
        on_play = soco.get_current_transport_info()['current_transport_state']
        assert on_play == 'PLAYING'

    def test_stop(self, soco):
        """ Test if the stop method works """
        soco.stop()
        wait(1)
        new = soco.get_current_transport_info()['current_transport_state']
        assert new == 'STOPPED'
        soco.play()
        wait(1)
        on_play = soco.get_current_transport_info()['current_transport_state']
        assert on_play == 'PLAYING'

    def test_seek_valid(self, soco):
        """ Test if the seek method works with valid input """
        original_position = soco.get_current_track_info()['position']
        # Format 1
        soco.seek('0:00:00')
        wait()
        position = soco.get_current_track_info()['position']
        assert position in ['0:00:00', '0:00:01']
        # Reset and format 2
        soco.seek(original_position)
        soco.seek('00:00:00')
        wait()
        position = soco.get_current_track_info()['position']
        assert position in ['0:00:00', '0:00:01']
        # Clean up
        soco.seek(original_position)
        wait()

    def test_seek_invald(self, soco):
        """ Test if the seek method properly fails with invalid input. """
        for string in ['invalid_time_string', '5:12', '6', 'aa:aa:aa']:
            with pytest.raises(ValueError):
                soco.seek(string)


class TestGetCurrentTrackInfo(object):
    """ Integration test for the get_current_track_info method. """

    info_keys = sorted(['album', 'artist', 'title', 'uri',
                        'playlist_position', 'duration', 'album_art',
                        'position'])

    def test_get(self, soco):
        """ Test is the return value is a dictinary and contains the following
        keys: album, artist, title, uri, playlist_position, duration,
        album_art and position.
        """
        info = soco.get_current_track_info()
        assert isinstance(info, dict)
        assert sorted(info.keys()) == self.info_keys


class TestGetSpeakerInfo(object):
    """ Integration test for the get_speaker_info method. """

    # The values in this list must be kept up to date with the values in
    # the test doc string
    info_keys = sorted(['zone_name', 'zone_icon', 'uid',
                        'serial_number', 'software_version',
                        'hardware_version', 'mac_address'])

    def test(self, soco):
        """ Test if the return value is a dictionary that contains the keys:
        zone_name, zone_icon, uid, serial_number, software_version,
        hardware_version, mac_address
        and that values have been found for all keys, i.e. they are not None.
        """
        speaker_info = soco.get_speaker_info()
        assert isinstance(speaker_info, dict)
        for _, value in speaker_info.items():
            assert value is not None

# TODO: test GetSpeakersIp


class TestGetQueue(object):
    """ Integration test for the get_queue method. """

    # The values in this list must be kept up to date with the values in
    # the test doc string
    queue_element_keys = sorted(['album', 'artist', 'uri',
                                'album_art', 'title'])

    def test_get(self, soco):
        """ Test is return value is a list of dictionaries and if each of
        the dictionaries contain the keys: album, artist, uri, album_art and
        title.
        """
        queue = soco.get_queue(0, 100)
        assert isinstance(queue, list)
        for item in queue:
            assert isinstance(item, dict)
            assert sorted(item.keys()) == self.queue_element_keys


class TestAddToQueue(object):
    """ Integration test for the add_to_queue method. """

    def test_add_to_queue(self, soco):
        """ Get the current queue, add the last item of the current queue
        and then compare the length of the old queue with the new and
        check that the last two elements are identical.
        """

        old_queue = soco.get_queue(0, 1000)
        # Add new element and check
        assert (soco.add_to_queue(old_queue[-1]['uri'])) == len(old_queue) + 1
        wait()
        new_queue = soco.get_queue()
        assert (len(new_queue) - 1) == len(old_queue)
        assert (new_queue[-1]) == (new_queue[-2])
        # Restore queue again? Probably no need, since queue is restored on
        # tear down anyway.


class TestRemoveFromQueue(object):
    """ Integration test for the remove_from_queue method. """

    def test(self, soco):
        """ Test if the remove_from_queue method works. """
        old_queue = soco.get_queue()
        track_to_remove = old_queue[-1]
        soco.remove_from_queue(len(old_queue))
        wait()
        new_queue = soco.get_queue()
        assert old_queue != new_queue, (
            'No difference between '
            'queues before and after removing the last item')
        assert len(new_queue) == len(old_queue) - 1
        # Clean up
        soco.add_to_queue(track_to_remove['uri'])
        wait()
        assert old_queue == soco.get_queue()
