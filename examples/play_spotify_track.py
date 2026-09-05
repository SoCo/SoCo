import sys

import soco
from soco.music_services import ConfiguredMusicServiceAccount, MusicServiceBrowser
from soco.music_services.browser.models import MusicServiceBrowseItem

SPOTIFY_SERVICE_ID = 12  # Spotify
TRACK_ID = "spotify:track:4cOdK2wGLETKBW3PvgPWqT"  # Never Gonna Give You Up


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python examples/play_spotify_track.py ROOM")

    room = sys.argv[1]
    player = soco.discovery.by_name(room)
    if player is None:
        raise SystemExit("No speaker named %r found" % room)

    # Pick a configured Spotify account from the selected Sonos system.
    account = next(
        a for a in ConfiguredMusicServiceAccount.get_accounts(player)
        if a.service_id == SPOTIFY_SERVICE_ID
    )
    browser = MusicServiceBrowser("Spotify", account=account, device=player)

    # Wrap the track id in a browse item so playback can include its metadata.
    track = MusicServiceBrowseItem(
        item_id=TRACK_ID,
        title="Never Gonna Give You Up",
        kind="track",
        item_type="track",
        artist="Rick Astley",
    )

    print("Playing on %s ..." % player.player_name)
    browser.play(track, device=player)


if __name__ == "__main__":
    main()
