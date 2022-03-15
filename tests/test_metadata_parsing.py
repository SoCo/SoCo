"""Tests for the media metadata parsing."""
from conftest import DataLoader

DATA_LOADER = DataLoader("media_metadata_payloads")
MEDIA_TEST_SOURCES = ("bbc", "cifs", "pandora", "sonos_radio", "tunein", "tunein_2")


def test_metadata_parsing(moco):
    for media_source in MEDIA_TEST_SOURCES:
        metadata_info = DATA_LOADER.load_json("{}.json".format(media_source))
        moco.avTransport.GetPositionInfo.return_value = metadata_info["input"]
        assert moco.get_current_track_info() == metadata_info["result"]
        moco.avTransport.GetPositionInfo.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master")]
        )
        moco.avTransport.reset_mock()
