"""Tests for the ShareLink plugin."""

from unittest import mock

import pytest

from soco.exceptions import SoCoException
from soco.plugins.sharelink import (
    AppleMusicShare,
    DeezerShare,
    ShareLinkPlugin,
    SpotifyShare,
    TIDALShare,
)


@pytest.mark.parametrize(
    "service, uri, canonical",
    [
        (
            SpotifyShare,
            "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC?si=abc",
            "spotify:track:4uLU6hMCjMI75M1A2tKUQC",
        ),
        (
            SpotifyShare,
            "https://open.spotify.com/intl-de/album/1DFixLWuPkv3KT3TnV35m3",
            "spotify:album:1DFixLWuPkv3KT3TnV35m3",
        ),
        (
            SpotifyShare,
            "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
            "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
        ),
        (
            TIDALShare,
            "https://tidal.com/browse/album/157273956",
            "tidal:album:157273956",
        ),
        (
            TIDALShare,
            "https://tidal.com/track/12345/u",
            "tidal:track:12345",
        ),
        (
            TIDALShare,
            "https://listen.tidal.com/playlist/0f9f8ad4-7d77-4a07-8c4e-6f0a5d2a8a1b",
            "tidal:playlist:0f9f8ad4-7d77-4a07-8c4e-6f0a5d2a8a1b",
        ),
        (
            DeezerShare,
            "https://www.deezer.com/us/track/3135556",
            "deezer:track:3135556",
        ),
        (
            DeezerShare,
            "https://deezer.com/album/302127",
            "deezer:album:302127",
        ),
        (
            AppleMusicShare,
            "https://music.apple.com/dk/album/black-velvet/217502930?i=217503142",
            "song:217503142",
        ),
        (
            AppleMusicShare,
            "https://music.apple.com/us/song/black-velvet/217503142",
            "song:217503142",
        ),
        (
            AppleMusicShare,
            "https://music.apple.com/dk/album/amused-to-death/975952384",
            "album:975952384",
        ),
        (
            AppleMusicShare,
            "https://music.apple.com/de/playlist/unnamed-playlist/pl.u-rR2PCrLdLJk",
            "playlist:pl.u-rR2PCrLdLJk",
        ),
    ],
)
def test_canonical_uri(service, uri, canonical):
    assert service().canonical_uri(uri) == canonical


@pytest.mark.parametrize(
    "service, uri, expected",
    [
        (
            SpotifyShare,
            "spotify:album:6wiUBliPe76YAVpNEdidpY",
            ("album", "spotify%3aalbum%3a6wiUBliPe76YAVpNEdidpY"),
        ),
        (
            TIDALShare,
            "https://listen.tidal.com/track/12345",
            ("track", "track%2f12345"),
        ),
        (
            DeezerShare,
            "https://deezer.com/playlist/908622995",
            ("playlist", "playlist-908622995"),
        ),
        (
            AppleMusicShare,
            "https://music.apple.com/us/song/black-velvet/217503142",
            ("song", "song%3a217503142"),
        ),
    ],
)
def test_extract(service, uri, expected):
    assert service().extract(uri) == expected


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.com/album/123",
        "https://music.apple.com/us/artist/alannah-myles/1234",
        "not a link",
    ],
)
def test_unsupported_uri(uri):
    plugin = ShareLinkPlugin(mock.Mock())
    assert not plugin.is_share_link(uri)
    with pytest.raises(SoCoException, match="Unsupported URI"):
        plugin.add_share_link_to_queue(uri)


def test_add_share_link_to_queue():
    soco = mock.Mock()
    soco.avTransport.AddURIToQueue.return_value = {"FirstTrackNumberEnqueued": "3"}
    plugin = ShareLinkPlugin(soco)

    uri = "https://open.spotify.com/album/6wiUBliPe76YAVpNEdidpY"
    assert plugin.is_share_link(uri)
    assert plugin.add_share_link_to_queue(uri, position=2, dc_title="Title") == 3

    args = dict(soco.avTransport.AddURIToQueue.call_args[0][0])
    assert args["InstanceID"] == 0
    assert args["EnqueuedURI"] == (
        "x-rincon-cpcontainer:1004206cspotify%3aalbum%3a6wiUBliPe76YAVpNEdidpY"
    )
    assert args["DesiredFirstTrackNumberEnqueued"] == 2
    assert args["EnqueueAsNext"] == 0
    metadata = args["EnqueuedURIMetaData"]
    assert '<item id="00040000spotify%3aalbum%3a6wiUBliPe76YAVpNEdidpY"' in metadata
    assert "<dc:title>Title</dc:title>" in metadata
    assert "<upnp:class>object.container.album.musicAlbum</upnp:class>" in metadata
    # Spotify (non-US) service number
    assert "SA_RINCON2311_X_#Svc2311-0-Token" in metadata


def test_add_share_link_to_queue_tries_next_service_on_failure():
    # Spotify links match both SpotifyShare and SpotifyUSShare; if the first
    # one is rejected, the second service number is tried.
    soco = mock.Mock()
    soco.avTransport.AddURIToQueue.side_effect = [
        SoCoException("rejected"),
        {"FirstTrackNumberEnqueued": "1"},
    ]
    plugin = ShareLinkPlugin(soco)

    assert plugin.add_share_link_to_queue("spotify:track:4uLU6hMCjMI75M1A2tKUQC") == 1
    metadata = soco.avTransport.AddURIToQueue.call_args[0][0][2][1]
    assert "SA_RINCON3079_X_#Svc3079-0-Token" in metadata
