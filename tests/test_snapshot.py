"""Tests for the snapshot module."""

from unittest.mock import MagicMock, call

from soco.data_structures import DidlMusicTrack, DidlResource
from soco.snapshot import Snapshot


def make_track(uri, protocol_info="http-get:*:audio/mpeg:*"):
    """Create a DidlMusicTrack with a resource URI, as returned by get_queue."""
    resource = DidlResource(uri=uri, protocol_info=protocol_info)
    return DidlMusicTrack(
        title="Test Track",
        parent_id="Q:0",
        item_id="Q:0/1",
        resources=[resource],
    )


def test_restore_queue_calls_add_uri_to_queue(moco):
    """_restore_queue adds each queue item's URI via add_uri_to_queue."""
    track1 = make_track("x-file-cifs://nas/music/a.mp3")
    track2 = make_track("http://192.168.1.50/music/b.mp3")

    snap = Snapshot(moco, snapshot_queue=True)
    snap.queue = [[track1, track2]]

    moco.add_uri_to_queue = MagicMock()
    snap._restore_queue()

    moco.add_uri_to_queue.assert_has_calls(
        [
            call("x-file-cifs://nas/music/a.mp3"),
            call("http://192.168.1.50/music/b.mp3"),
        ]
    )


def test_restore_queue_http_uri(moco):
    """Tracks added via HTTP (e.g. WebDAV) are correctly restored (issue #983).

    DidlMusicTrack has no direct .uri attribute; the URI lives in resources[0].
    get_uri() must be used instead.
    """
    http_track = make_track("http://192.168.1.50/share/song.mp3")
    assert not hasattr(http_track, "uri"), "DidlMusicTrack should not have .uri"
    assert http_track.get_uri() == "http://192.168.1.50/share/song.mp3"

    snap = Snapshot(moco, snapshot_queue=True)
    snap.queue = [[http_track]]

    moco.add_uri_to_queue = MagicMock()
    snap._restore_queue()

    moco.add_uri_to_queue.assert_called_once_with("http://192.168.1.50/share/song.mp3")


def test_restore_queue_skipped_when_none(moco):
    """_restore_queue does nothing when queue was not snapshotted."""
    snap = Snapshot(moco, snapshot_queue=False)
    moco.add_uri_to_queue = MagicMock()
    snap._restore_queue()
    moco.add_uri_to_queue.assert_not_called()
