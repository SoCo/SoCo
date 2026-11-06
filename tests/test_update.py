"""Tests for the update module."""

import io
from unittest import mock

import pytest

from soco import update
from soco.core import SoCo

MANIFEST = b"""<?xml version="1.0"?>
<update_manifest version="1.1"
                 default_version="97.2-81220"
                 base_url="http://update.example.com/97.2/^97.2-81220">
  <update_list>
    <image model="20" fromver_max="34.7-33245" version="34.16-37101">http://update.example.com/34.16/^34.16-37101</image>
    <image model="20" fromver_min="54.2-71230" version="86.10-81100">http://update.example.com/86.10/^86.10-81100</image>
    <image model="10" submodel_min="2" submodel_max="2" version="31.9-27151"/>
    <image model="10" submodel_min="6" submodel_max="6" version="54.2-73060">http://update.example.com/54.2/^54.2-73060</image>
    <image model="10" version="90.0-82050">http://update.example.com/90.0/^90.0-82050</image>
  </update_list>
</update_manifest>
"""

UPDATE_ITEM = (
    '<UpdateItem xmlns="urn:schemas-rinconnetworks-com:update-1-0" '
    'Type="Software" Version="97.2-81220" '
    'UpdateURL="http://update.example.com/97.2/^97.2-81220" DownloadSize="0" '
    'ManifestURL="http://update.example.com/update.upm" Swgen="2" '
    'LatestSwgen="2" ManifestRevision="f0cb0108"/>'
)


@pytest.fixture
def manifest():
    return update.UpdateManifest.from_xml(MANIFEST)


@pytest.mark.parametrize(
    "version, expected",
    [
        ("97.2-81220", (97, 2, 81220)),
        ("86.10-81100", (86, 10, 81100)),
        ("", None),
        (None, None),
        ("97.2", None),
    ],
)
def test_parse_version(version, expected):
    assert update.parse_version(version) == expected


def test_parse_hardware_version():
    assert update.parse_hardware_version("1.33.1.8-1.9") == (33, 1)


def test_parse_update_item():
    item = update.parse_update_item(UPDATE_ITEM)
    assert item == update.UpdateItem(
        "97.2-81220",
        "http://update.example.com/97.2/^97.2-81220",
        "http://update.example.com/update.upm",
        "f0cb0108",
    )


@pytest.mark.parametrize("update_item", ["", None])
def test_parse_update_item_empty(update_item):
    assert update.parse_update_item(update_item) is None


@pytest.mark.parametrize(
    "model, submodel, current, expected",
    [
        # No entry for the model: the default version
        (
            33,
            1,
            "97.1-80312",
            ("97.2-81220", "http://update.example.com/97.2/^97.2-81220"),
        ),
        # fromver ranges
        (
            20,
            1,
            "86.10-81100",
            ("86.10-81100", "http://update.example.com/86.10/^86.10-81100"),
        ),
        (
            20,
            1,
            "34.0-30000",
            ("34.16-37101", "http://update.example.com/34.16/^34.16-37101"),
        ),
        # A submodel match beats the later generic entry
        (
            10,
            6,
            "54.2-73060",
            ("54.2-73060", "http://update.example.com/54.2/^54.2-73060"),
        ),
        # Entries with no URL fall back to the base URL
        (
            10,
            2,
            "31.9-27151",
            ("31.9-27151", "http://update.example.com/97.2/^97.2-81220"),
        ),
        # No submodel match: the generic entry
        (
            10,
            9,
            "60.0-10000",
            ("90.0-82050", "http://update.example.com/90.0/^90.0-82050"),
        ),
    ],
)
def test_manifest_target(manifest, model, submodel, current, expected):
    assert manifest.target(model, submodel, current) == expected


def _sducp_lines(*lines):
    return io.StringIO("".join(line + "\n" for line in lines))


@mock.patch("soco.update.socket.create_connection")
def test_monitor_update(create_connection):
    sock = create_connection.return_value.__enter__.return_value
    sock.makefile.return_value = _sducp_lines(
        "HELLO?version=97.2-81220",
        "STATUS?phase=DOWNLOAD;percent-complete=17",
        "COMPLETE?phase=DOWNLOAD",
        "STATUS?phase=FLASHWRITE;percent-complete=90",
        "STATUS?phase=REBOOT;percent-complete=100",
    )
    progress = list(update.monitor_update("192.168.1.10"))
    create_connection.assert_called_once_with(("192.168.1.10", 4444), timeout=60)
    assert progress == [
        update.UpdateProgress("DOWNLOAD", 17),
        update.UpdateProgress("FLASHWRITE", 90),
        update.UpdateProgress("REBOOT", 100),
    ]


@mock.patch("soco.update.socket.create_connection")
def test_monitor_update_error(create_connection):
    sock = create_connection.return_value.__enter__.return_value
    sock.makefile.return_value = _sducp_lines(
        "STATUS?phase=DOWNLOAD;percent-complete=0",
        "ERROR?phase=DOWNLOAD;error-code=9;internal-data=downgrade blocked",
    )
    with pytest.raises(update.SoftwareUpdateError) as excinfo:
        list(update.monitor_update("192.168.1.10"))
    assert excinfo.value.phase == "DOWNLOAD"
    assert excinfo.value.error_code == "9"
    assert excinfo.value.detail == "downgrade blocked"


@mock.patch("soco.update.requests")
@mock.patch("soco.core.requests")
def test_check_for_update(core_requests, update_requests):
    speaker = SoCo("192.168.1.11")
    speaker.zoneGroupTopology = mock.Mock()
    speaker.zoneGroupTopology.CheckForUpdate.return_value = {"UpdateItem": UPDATE_ITEM}
    with mock.patch.object(
        SoCo,
        "get_speaker_info",
        return_value={
            "hardware_version": "1.33.1.8-1.9",
            "software_version": "97.1-80312",
        },
    ):
        update_requests.get.return_value.content = MANIFEST
        status = speaker.check_for_update()
    speaker.zoneGroupTopology.CheckForUpdate.assert_called_once_with(
        [("UpdateType", "Software"), ("CachedOnly", "0"), ("Version", "")]
    )
    update_requests.get.assert_called_once_with(
        "http://update.example.com/update.upm", timeout=None
    )
    assert status == update.UpdateStatus(
        "97.1-80312", "97.2-81220", "http://update.example.com/97.2/^97.2-81220"
    )


def test_begin_software_update():
    speaker = SoCo("192.168.1.12")
    speaker.zoneGroupTopology = mock.Mock()
    speaker.begin_software_update("http://update.example.com/97.2/^97.2-81220")
    speaker.zoneGroupTopology.BeginSoftwareUpdate.assert_called_once_with(
        [
            ("UpdateURL", "http://update.example.com/97.2/^97.2-81220"),
            ("Flags", 0x40),
            ("ExtraOptions", ""),
        ]
    )


@mock.patch("soco.update.time.sleep")
@mock.patch("soco.update.socket.create_connection")
def test_monitor_update_waits_for_upgrade_app(create_connection, sleep):
    sock = mock.MagicMock()
    sock.__enter__.return_value.makefile.return_value = _sducp_lines(
        "STATUS?phase=DOWNLOAD;percent-complete=12",
    )
    create_connection.side_effect = [
        ConnectionRefusedError,
        ConnectionRefusedError,
        sock,
    ]
    progress = list(update.monitor_update("192.168.1.10"))
    assert progress == [update.UpdateProgress("DOWNLOAD", 12)]
    assert create_connection.call_count == 3


@mock.patch("soco.update.time.monotonic", side_effect=[0, 150, 301])
@mock.patch("soco.update.time.sleep")
@mock.patch("soco.update.socket.create_connection")
def test_monitor_update_connect_timeout(create_connection, sleep, monotonic):
    create_connection.side_effect = ConnectionRefusedError
    with pytest.raises(ConnectionRefusedError):
        list(update.monitor_update("192.168.1.10"))
    assert create_connection.call_count == 2
