# -*- coding: utf-8 -*-
""" Tests for the services module """

from __future__ import unicode_literals
import pytest
import mock
from io import BytesIO
from soco.events import parse_event_xml, Event, activate_event_stream_logging
from soco import events

DUMMY_EVENT = """
<e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">
    <e:property>
        <ZoneGroupState>&lt;ZoneGroups&gt;&lt;
            ZoneGroup Coordinator="RINCON_000XXX01400"
            ID="RINCON_000XXX1400:56"&gt;&lt;
            ZoneGroupMember UUID="RINCON_000XXX400"
            Location="http://XXX" ZoneName="Living Room"
            Icon="x-rincon-roomicon:living" Configuration="1"
            SoftwareVersion="XXXX"
            MinCompatibleVersion="XXXX"
            LegacyCompatibleVersion="XXXX" BootSeq="48"/&gt;&lt;
            /ZoneGroup&gt;&lt;ZoneGroup Coordinator="RINCON_000XXXX01400"
            ID="RINCON_000XXXX1400:0"&gt;&lt;
            ZoneGroupMember UUID="RINCON_000XXXX1400"
            Location="http://192.168.1.100:1400/xml/device_description.xml"
            ZoneName="BRIDGE" Icon="x-rincon-roomicon:zoneextender"
            Configuration="1" Invisible="1" IsZoneBridge="1"
            SoftwareVersion="XXXX" MinCompatibleVersion="XXXX"
            LegacyCompatibleVersion="XXXX" BootSeq="37"/&gt;&lt;
            /ZoneGroup&gt;&lt;ZoneGroup Coordinator="RINCON_000XXXX1400"
            ID="RINCON_000XXXX1400:57"&gt;&lt;
            ZoneGroupMember UUID="RINCON_000XXXX01400"
            Location="http://192.168.1.102:1400/xml/device_description.xml"
            ZoneName="Kitchen" Icon="x-rincon-roomicon:kitchen"
            Configuration="1" SoftwareVersion="XXXX"
            MinCompatibleVersion="XXXX" LegacyCompatibleVersion="XXXX"
            BootSeq="56"/&gt;&lt;/ZoneGroup&gt;&lt;/ZoneGroups&gt;
         </ZoneGroupState>
    </e:property>
    <e:property>
        <ThirdPartyMediaServersX>...s+3N9Lby8yoJD/QOC4W</ThirdPartyMediaServersX>
    </e:property>
    <e:property>
        <AvailableSoftwareUpdate>&lt;UpdateItem
            xmlns="urn:schemas-rinconnetworks-com:update-1-0"
            Type="Software" Version="XXXX"
            UpdateURL="http://update-firmware.sonos.com/XXXX"
            DownloadSize="0"
            ManifestURL="http://update-firmware.sonos.com/XX"/&gt;
         </AvailableSoftwareUpdate>
    </e:property>
    <e:property>
        <AlarmRunSequence>RINCON_000EXXXXXX0:56:0</AlarmRunSequence>
    </e:property>
    <e:property>
        <ZoneGroupName>Kitchen</ZoneGroupName>
    </e:property>
    <e:property>
        <ZoneGroupID>RINCON_000XXXX01400:57</ZoneGroupID>
    </e:property>
    <e:property>
        <ZonePlayerUUIDsInGroup>RINCON_000XXX1400</ZonePlayerUUIDsInGroup>
    </e:property>
</e:propertyset>
"""
DUMMY_EVENT_LENGTH = '{0:0>20}'.format(len(DUMMY_EVENT))


def test_event_object():
    # Basic initialisation
    dummy_event = Event('123', '456', 'dummy', 123456.7, {'zone': 'kitchen'})
    assert dummy_event.sid == '123'
    assert dummy_event.seq == '456'
    assert dummy_event.timestamp == 123456.7
    assert dummy_event.service =='dummy'
    assert dummy_event.variables == {'zone':'kitchen'}
    # attribute access
    assert dummy_event.zone == 'kitchen'
    # Should not access non-existent attributes
    with pytest.raises(AttributeError):
        var = dummy_event.non_existent
    # Should be read only
    with pytest.raises(TypeError):
        dummy_event.new_var = 4
    with pytest.raises(TypeError):
        dummy_event.sid = 4


def test_event_parsing():
    event_dict = parse_event_xml(DUMMY_EVENT)
    assert event_dict['zone_group_state']
    assert event_dict['alarm_run_sequence'] == 'RINCON_000EXXXXXX0:56:0'
    assert event_dict['zone_group_id'] == "RINCON_000XXXX01400:57"


def test_activate_event_stream_logging():
    """Test the activate_event_stream_logging function"""
    # Simply test that the object we pass into acivate, gets set on a module
    # variable
    activate_event_stream_logging(47)
    assert events.event_stream == 47
    events.event_stream = None

def test_save_event_to_stream():
    """Test the save_event_to_stream function"""
    # Mock the event_stream and event_stream_lock module variables
    with mock.patch("soco.events.event_stream") as event_stream:
        with mock.patch("soco.events.event_stream_lock") as event_stream_lock:
            # Save the cummy event
            events.save_event_to_stream(DUMMY_EVENT.encode('ascii'))

            # Test that both the 20 width zero padded with and the dummt event
            # has been written to the mock stream
            calls = [mock.call(DUMMY_EVENT_LENGTH.encode('ascii')),
                     mock.call(DUMMY_EVENT.encode('ascii'))]
            event_stream.write.assert_has_calls(calls)
            event_stream.flush.assert_has_calls([mock.call()])

            # Assert that the lock has been used
            event_stream_lock.__enter__.assert_called_with()
            event_stream_lock.__exit__.assert_called_with(None, None, None)

def test_replay_event_stream(capsys):
    """Test the replay_event_stream function"""
    # Pre-prpogram responses for three calls to read on the mock stream
    stream = mock.Mock()
    stream.read.side_effect = [string.encode('ascii') for string in
                               [DUMMY_EVENT_LENGTH, DUMMY_EVENT, '']]
    events.replay_event_stream(stream)
    # and check that it has been called
    stream.read.assert_has_calls(
        [mock.call(20), mock.call(int(DUMMY_EVENT_LENGTH)), mock.call(20)]
    )

    # Get the output captured by py.test
    out, _ = capsys.readouterr()

    # We can never be sure of the order of the elements in the dict and
    # therefore of the print order, so we test the keys
    assert out.startswith('########## 0 ##########\n')
    event_dict = events.parse_event_xml(DUMMY_EVENT)
    for key, value in event_dict.items():
        if key in ['zone_group_state']:
            continue
        assert out.find(key) > -1
