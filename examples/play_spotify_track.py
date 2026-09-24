"""Play a Spotify track on a Sonos speaker.

Requires a Spotify account already linked to the Sonos system. By default the
track keeps playing at the speaker's current volume after the script exits;
use --volume to cap it and --duration to stop and restore the previous state
automatically. Restoration covers the targeted speaker's own snapshot only;
it is refused when the speaker is not its group's coordinator or when the
current state cannot be reconstructed, such as provider-controlled
(x-sonos-vli:) sessions or cloud queues. For safety, playback is limited to
standalone speakers: a grouped speaker would play on every group member at
each member's own volume.
"""

import argparse
import time

import soco
from soco.music_services import ConfiguredMusicServiceAccount, MusicServiceBrowser
from soco.music_services.browser.models import MusicServiceBrowseItem
from soco.snapshot import Snapshot

SPOTIFY_SERVICE_ID = 12  # Spotify
TRACK_ID = "spotify:track:4cOdK2wGLETKBW3PvgPWqT"  # Never Gonna Give You Up


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("room", help="name of the Sonos room to play on")
    parser.add_argument(
        "--volume",
        type=int,
        metavar="0-100",
        help=(
            "maximum playback volume; never raises the speaker above its "
            "current volume"
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        metavar="SECONDS",
        help="stop after SECONDS and restore the previous playback state",
    )
    args = parser.parse_args()
    if args.volume is not None and not 0 <= args.volume <= 100:
        parser.error("--volume must be between 0 and 100")
    if args.duration is not None and args.duration < 0:
        parser.error("--duration must be >= 0")

    player = soco.discovery.by_name(args.room)
    if player is None:
        raise SystemExit("No speaker named %r found" % args.room)
    if len(player.group.members) > 1:
        raise SystemExit(
            "%s is grouped with other speakers; playback would run on every "
            "member at its own volume, which this example does not manage. "
            "Choose a standalone speaker" % player.player_name
        )

    # Pick a configured Spotify account from the selected Sonos system.
    account = next(
        (
            a
            for a in ConfiguredMusicServiceAccount.get_accounts(player)
            if a.service_id == SPOTIFY_SERVICE_ID
        ),
        None,
    )
    if account is None:
        raise SystemExit(
            "No Spotify account is configured on %s; "
            "link one in the Sonos app first" % player.player_name
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

    snapshot = None
    if args.duration is not None:
        snapshot = Snapshot(player)
        snapshot.snapshot()
        # Refuse rather than promise a false restore: a non-coordinator
        # snapshot only restores volume, and Snapshot cannot reliably
        # reconstruct provider-controlled or cloud-queue sessions.
        if not snapshot.is_coordinator:
            raise SystemExit(
                "Cannot use --duration: %s is not the coordinator of its "
                "group, so its playback state cannot be restored" % player.player_name
            )
        media_uri = snapshot.media_uri or ""
        if snapshot.is_playing_cloud_queue or media_uri.startswith("x-sonos-vli:"):
            raise SystemExit(
                "Cannot use --duration: the current playback state on %s "
                "cannot be restored safely" % player.player_name
            )

    try:
        if args.volume is not None:
            player.volume = min(player.volume, args.volume)
        print("Playing on %s ..." % player.player_name)
        browser.play(track, device=player)
        if snapshot is None:
            print("The track will keep playing; stop it from the Sonos app.")
            return
        time.sleep(args.duration)
    finally:
        if snapshot is not None:
            print("Restoring previous playback state ...")
            snapshot.restore()


if __name__ == "__main__":
    main()
