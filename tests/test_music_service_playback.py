"""Tests for music-service playback URI and DIDL metadata builders."""

from types import SimpleNamespace

import pytest

from soco.exceptions import MusicServiceException
from soco.music_services.browser import MusicServiceBrowseItem, MusicServiceBrowser
from soco.music_services.browser.playback import (
    build_metadata,
    build_uri,
    escape_id,
    normalize_item_type,
    resolve_item,
)


def make_browser(
    service_id="204", serial=3, udn="SA_RINCON52231_X_#Svc204-00abcdef-Token"
):
    account = SimpleNamespace(serial_number=serial, udn=udn)
    music_service = SimpleNamespace(desc="SA_RINCON52231_")
    return SimpleNamespace(
        service_id=service_id,
        service_name="Example",
        account=account,
        music_service=music_service,
    )


class FakeDevice:
    """The small SoCo surface MusicServiceBrowser needs."""

    household_id = "Sonos_household"
    uid = "RINCON_000000000001400"

    class _Sys:
        def GetString(self, args):  # pylint: disable=invalid-name
            return {"StringValue": "player-device-id"}

    systemProperties = _Sys()


def test_normalize_item_type():
    assert normalize_item_type("track") == "track"
    assert normalize_item_type("trackList.program") == "program"
    assert normalize_item_type("station.broadcast") == "broadcast"
    assert normalize_item_type("") == ""
    assert normalize_item_type(None) == ""


def test_escape_id():
    assert escape_id("song:1844932150") == "song%3a1844932150"
    assert escape_id("a/b?c=d&e#f") == "a%2fb%3fc%3dd%26e%23f"


def test_build_uri_track_apple_music_flags_override():
    browser = make_browser(service_id="204")
    uri = build_uri(browser, "song:1844932150", "track", "audio/aac")

    assert uri == ("x-sonos-http:song%3a1844932150.mp4?sid=204&flags=8224&sn=3")


def test_build_uri_track_generic_mime_extension_and_flags():
    browser = make_browser(service_id="201")
    assert build_uri(browser, "song:1", "track", "audio/aac").endswith(
        ".mp4?sid=201&flags=32&sn=3"
    )
    assert build_uri(browser, "song:1", "track", "audio/mpeg").endswith(
        ".mp3?sid=201&flags=32&sn=3"
    )
    # Unknown MIME falls back to .mp3 with the default flags.
    assert build_uri(browser, "song:1", "track", "audio/weird").endswith(
        ".mp3?sid=201&flags=32&sn=3"
    )


def test_build_uri_track_special_mime_types():
    browser = make_browser(service_id="12")
    # Spotify tracks map to x-sonos-spotify with the player-verified flags
    # (8224), never the x-sonosapi-stream radio scheme (review regression
    # test: Spotify audio/x-spotify maps to a Spotify resource).
    assert build_uri(browser, "spotify:track:1", "track", "audio/x-spotify") == (
        "x-sonos-spotify:spotify%3atrack%3a1?sid=12&flags=8224&sn=3"
    )
    assert build_uri(browser, "track:1", "track", "audio/flac") == (
        "x-sonos-http:track%3a1.flac?sid=12&flags=0&sn=3"
    )


def test_build_uri_stream_variants():
    browser = make_browser(service_id="254")
    assert build_uri(browser, "s49815", "stream", "") == (
        "x-sonosapi-stream:s49815?sid=254&flags=32&sn=3"
    )
    assert build_uri(browser, "s49815", "stream", "audio/aac") == (
        "x-sonosapi-stream:s49815?sid=254&flags=8224&sn=3"
    )
    assert build_uri(browser, "s1", "stream", "application/x-mpegurl") == (
        "x-sonosapi-hls:s1?sid=254&flags=288&sn=3"
    )


def test_build_uri_program_show_audiobook():
    browser = make_browser(service_id="314")
    assert build_uri(browser, "Playlist:mix1", "program") == (
        "x-sonosapi-radio:Playlist%3amix1?sid=314&flags=104&sn=3"
    )
    assert build_uri(browser, "show:1", "show") == (
        "x-sonosapi-hls-static:show%3a1?sid=314&flags=24616&sn=3"
    )
    assert build_uri(browser, "book:1", "audiobook") == (
        "x-rincon-cpcontainer:101340c8book%3a1?sid=314&flags=16584&sn=3"
    )


def test_build_uri_unknown_type_raises():
    browser = make_browser()
    with pytest.raises(MusicServiceException, match="cannot be played"):
        build_uri(browser, "library", "albumList")


def test_build_uri_normalizes_compound_type():
    browser = make_browser(service_id="303")
    uri = build_uri(browser, "sonos:2997", "trackList.program")

    assert uri == "x-sonosapi-radio:sonos%3a2997?sid=303&flags=104&sn=3"


def test_build_metadata_contains_desc_class_and_item_id():
    browser = make_browser()
    metadata = build_metadata(browser, "song:1", "Title", "track")

    assert 'id="10030020song%3a1"' in metadata
    assert "<upnp:class>object.item.audioItem.musicTrack</upnp:class>" in metadata
    assert ">SA_RINCON52231_X_#Svc204-00abcdef-Token</desc>" in metadata
    assert "<res" not in metadata


def test_build_metadata_spotify_has_protocol_info_and_udn():
    # Review regression: the Spotify DIDL must carry the Spotify resource
    # protocol info and the configured account UDN (in <desc>) for the
    # player to dereference the account's credentials.
    browser = make_browser()
    uri = build_uri(browser, "spotify:track:1", "track", "audio/x-spotify")
    metadata = build_metadata(
        browser, "spotify:track:1", "So What", "track", mime="audio/x-spotify", uri=uri
    )

    assert '<res protocolInfo="sonos.com-spotify:*:audio/x-spotify:*">' in metadata
    assert ">SA_RINCON52231_X_#Svc204-00abcdef-Token</desc>" in metadata
    assert "<upnp:class>object.item.audioItem.musicTrack</upnp:class>" in metadata
    assert uri.replace("&", "&amp;") in metadata


def test_build_metadata_stream_uses_broadcast_class():
    browser = make_browser()
    metadata = build_metadata(browser, "s1", "Station", "stream")

    assert 'id="00090000s1"' in metadata
    assert "<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>" in metadata


def test_build_metadata_escapes_title():
    browser = make_browser()
    metadata = build_metadata(browser, "song:1", "A & B < C", "track")

    assert "<dc:title>A &amp; B &lt; C</dc:title>" in metadata


def test_resolve_item_uses_browse_fields_without_media_call():
    calls = []
    browser = SimpleNamespace(get_media_metadata=lambda *_a: calls.append(1) or None)
    item = MusicServiceBrowseItem(
        item_id="song:1",
        title="Title",
        kind="mediaMetadata",
        item_type="track",
        raw={"mimeType": "audio/aac"},
    )

    item_id, item_type, mime, title = resolve_item(browser, item)

    assert (item_id, item_type, mime, title) == (
        "song:1",
        "track",
        "audio/aac",
        "Title",
    )
    assert calls == []


def test_resolve_item_fetches_media_for_compound_type():
    browser = SimpleNamespace(
        get_media_metadata=lambda _id: {
            "itemType": "program",
            "mimeType": "",
            "title": "Hit List",
        }
    )
    item = MusicServiceBrowseItem(
        item_id="sonos:2997",
        title="Hit List",
        kind="mediaMetadata",
        item_type="trackList.program",
        raw={},
    )

    item_id, item_type, mime, title = resolve_item(browser, item)

    assert (item_id, item_type, mime, title) == (
        "sonos:2997",
        "program",
        "",
        "Hit List",
    )


def test_resolve_item_keeps_known_type_when_media_disagrees():
    # SiriusXM's ``trackList.program`` channels report ``itemType=track`` from
    # getMediaMetadata, but the browse type (program) is authoritative and
    # must not be overridden to a track.
    browser = SimpleNamespace(
        get_media_metadata=lambda _id: {
            "itemType": "track",
            "mimeType": "application/x-mpegURL",
            "title": "Queens of Pop",
        }
    )
    item = MusicServiceBrowseItem(
        item_id="channel-xtra:61893114",
        title="Queens of Pop",
        kind="mediaMetadata",
        item_type="trackList.program",
        raw={},
    )

    item_id, item_type, mime, title = resolve_item(browser, item)

    assert (item_id, item_type, mime, title) == (
        "channel-xtra:61893114",
        "program",
        "application/x-mpegurl",
        "Queens of Pop",
    )


def test_resolve_item_string_id_fetches_media():
    browser = SimpleNamespace(
        get_media_metadata=lambda _id: {
            "itemType": "stream",
            "mimeType": "audio/aac",
            "title": "Station",
        }
    )

    assert resolve_item(browser, "s49815") == (
        "s49815",
        "stream",
        "audio/aac",
        "Station",
    )


def test_resolve_item_falls_back_when_media_fails():
    browser = SimpleNamespace(
        get_media_metadata=lambda _id: (_ for _ in ()).throw(
            MusicServiceException("provider down")
        )
    )
    item = MusicServiceBrowseItem(
        item_id="s1",
        title="Station",
        kind="mediaMetadata",
        item_type="stream",
        raw={},
    )

    item_id, item_type, mime, title = resolve_item(browser, item)

    assert (item_id, item_type, mime, title) == ("s1", "stream", "", "Station")


def test_play_sends_built_uri_and_metadata(monkeypatch):
    service = SimpleNamespace(
        service_name="Example",
        service_id="204",
        service_type="52231",
        auth_type="AppLink",
        capabilities="0",
        version="1.0",
        container_type="MusicService",
        uri="http://example.invalid/smapi",
        secure_uri="https://example.invalid/smapi",
        presentation_map_uri=None,
        manifest_uri=None,
        desc="SA_RINCON52231_",
    )
    monkeypatch.setattr(
        "soco.music_services.browser.MusicService", lambda *_a, **_k: service
    )
    from soco.music_services.browser import credentials

    monkeypatch.setattr(
        credentials.ConfiguredMusicServiceAccount,
        "get_accounts",
        lambda *_a, **_k: [],
    )

    captured = {}

    class FakeDevice:
        household_id = "Sonos_household"
        uid = "RINCON_000000000001400"

        class _Sys:
            def GetString(self, args):  # pylint: disable=invalid-name
                return {"StringValue": "player-device-id"}

        systemProperties = _Sys()

        def play_uri(self, uri, meta="", **kwargs):
            captured["uri"] = uri
            captured["meta"] = meta
            captured["kwargs"] = kwargs
            return "played"

    account = SimpleNamespace(
        service_id=204,
        serial_number=35,
        udn="SA_RINCON52231_X_#Svc52231-bf7d4d9f-Token",
        token="t",
        key="k",
        nickname="",
        tier="",
        account_uid=0xBF7D4D9F,
    )
    browser = MusicServiceBrowser(
        "Example",
        account=account,
        device=FakeDevice(),
        session=SimpleNamespace(),
    )
    item = MusicServiceBrowseItem(
        item_id="song:1844932150",
        title="Choosin' Texas",
        kind="mediaMetadata",
        item_type="track",
        raw={"mimeType": "audio/aac"},
    )

    result = browser.play(item)

    assert result == "played"
    assert captured["uri"] == (
        "x-sonos-http:song%3a1844932150.mp4?sid=204&flags=8224&sn=35"
    )
    assert ">SA_RINCON52231_X_#Svc52231-bf7d4d9f-Token</desc>" in captured["meta"]
    assert "object.item.audioItem.musicTrack" in captured["meta"]


def test_play_raises_for_not_added_anonymous_service(monkeypatch):
    service = SimpleNamespace(
        service_name="Example",
        service_id="254",
        service_type="65031",
        auth_type="Anonymous",
        capabilities="0",
        version="1.0",
        container_type="MusicService",
        uri="http://example.invalid/smapi",
        secure_uri="https://example.invalid/smapi",
        presentation_map_uri=None,
        manifest_uri=None,
        desc="SA_RINCON65031_",
    )
    monkeypatch.setattr(
        "soco.music_services.browser.MusicService", lambda *_a, **_k: service
    )

    class FakeDevice:
        household_id = "Sonos_household"
        uid = "RINCON_000000000001400"

        class _Sys:
            def GetString(self, args):  # pylint: disable=invalid-name
                return {"StringValue": "player-device-id"}

        systemProperties = _Sys()

    # An anonymous service that is not added to the household is constructed
    # with a synthetic serial-0, empty-UDN account.
    browser = MusicServiceBrowser(
        "Example",
        account=SimpleNamespace(service_id=254, serial_number=0, udn=""),
        device=FakeDevice(),
        session=SimpleNamespace(),
    )
    item = MusicServiceBrowseItem(
        item_id="s29271",
        title="Station",
        kind="mediaMetadata",
        item_type="stream",
        raw={},
    )

    with pytest.raises(MusicServiceException, match="not added to this household"):
        browser.play(item)


def test_play_spotify_item_and_id_use_same_provider_resource(monkeypatch):
    """A Spotify item and its raw id must use the same normal resource path."""
    service = SimpleNamespace(
        service_name="Spotify",
        service_id="12",
        service_type="3079",
        auth_type="AppLink",
        capabilities="0",
        version="1.0",
        container_type="MusicService",
        uri="http://example.invalid/smapi",
        secure_uri="https://example.invalid/smapi",
        presentation_map_uri=None,
        manifest_uri=None,
        desc="SA_RINCON3079_",
    )
    monkeypatch.setattr(
        "soco.music_services.browser.MusicService", lambda *_a, **_k: service
    )
    from soco.music_services.browser import credentials

    monkeypatch.setattr(
        credentials.ConfiguredMusicServiceAccount,
        "get_accounts",
        lambda *_a, **_k: [],
    )

    calls = []

    class Player(FakeDevice):
        def play_uri(self, uri, meta="", **kwargs):
            calls.append((uri, meta, kwargs))
            return "played"

    account = SimpleNamespace(
        service_id=12,
        serial_number=63,
        udn="SA_RINCON3079_X_#Svc3079-bf7d4d9f-Token",
        token="t",
        key="k",
        nickname="",
        tier="",
        account_uid=0xBF7D4D9F,
    )
    browser = MusicServiceBrowser(
        "Spotify", account=account, device=Player(), session=SimpleNamespace()
    )
    item = MusicServiceBrowseItem(
        item_id="spotify:track:7azylXFRsebfrIoAtwfjaB",
        title="So What",
        kind="mediaMetadata",
        item_type="track",
        raw={"mimeType": "audio/x-spotify"},
    )
    monkeypatch.setattr(
        browser,
        "get_media_metadata",
        lambda item_id: {
            "id": item_id,
            "itemType": "track",
            "mimeType": "audio/x-spotify",
            "title": "So What",
        },
    )

    assert browser.play(item) == "played"
    assert browser.play(item.item_id) == "played"

    assert len(calls) == 2
    assert calls[0][0] == calls[1][0]
    assert calls[0][0].startswith(
        "x-sonos-spotify:spotify%3atrack%3a7azylXFRsebfrIoAtwfjaB?"
    )
    assert "flags=8224" in calls[0][0]
    for _uri, metadata, _kwargs in calls:
        assert '<res protocolInfo="sonos.com-spotify:*:audio/x-spotify:*">' in metadata
        assert ">SA_RINCON3079_X_#Svc3079-bf7d4d9f-Token</desc>" in metadata
