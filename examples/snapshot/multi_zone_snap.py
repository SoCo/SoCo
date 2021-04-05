"""Sample script to demonstrate use of SoCo snapshot on multiple zones

To use this script just run it - no configuration required.
It shows it's capabilities better if you have something playing.

This is useful for scenarios such as when you want to switch to radio,
an announcement or doorbell sound and then back to what was playing previously.

This script has a play_alert function that will:
 - take a snapshot of the current status of all sonos players (whats playing,
   volume etc.)
 - play an alert_uri file on each group coordinator
 - re-instate the sonos players to it's previous state

This script does not group or un-group any Sonos players. Group management is
a separate subject. For alerts grouping causes delays, so is avoided here.

Note: The Snapshot class is designed for single use. If a second snapshot is
required create another instance of the class e.g. `snap2 = Snapshot(device)`.
"""

import time
import soco
from soco.snapshot import Snapshot


def play_alert(zones, alert_uri, alert_volume=20, alert_duration=0, fade_back=False):
    """
    Demo function using soco.snapshot across multiple Sonos players.

    Args:
        zones (set): a set of SoCo objects
        alert_uri (str): uri that Sonos can play as an alert
        alert_volume (int): volume level for playing alert (0 tp 100)
        alert_duration (int): length of alert (if zero then length of track)
        fade_back (bool): on reinstating the zones fade up the sound?
    """

    # Use soco.snapshot to capture current state of each zone to allow restore
    for zone in zones:
        zone.snap = Snapshot(zone)
        zone.snap.snapshot()
        print("snapshot of zone: {}".format(zone.player_name))

    # prepare all zones for playing the alert
    for zone in zones:
        # Each Sonos group has one coordinator only these can play, pause, etc.
        if zone.is_coordinator:
            if not zone.is_playing_tv:  # can't pause TV - so don't try!
                # pause music for each coordinators if playing
                trans_state = zone.get_current_transport_info()
                if trans_state["current_transport_state"] == "PLAYING":
                    zone.pause()

        # For every Sonos player set volume and mute for every zone
        zone.volume = alert_volume
        zone.mute = False

    # play the sound (uri) on each sonos coordinator
    print("will play: {} on all coordinators".format(alert_uri))
    for zone in zones:
        if zone.is_coordinator:
            zone.play_uri(uri=alert_uri, title="Sonos Alert")

    # wait for alert_duration
    time.sleep(alert_duration)

    # restore each zone to previous state
    for zone in zones:
        print("restoring {}".format(zone.player_name))
        zone.snap.restore(fade=fade_back)


if __name__ == "__main__":

    all_zones = soco.discover()

    # alert uri to send to sonos - this uri must be available to Sonos
    alert_sound = (
        "https://ia800503.us.archive.org/8/items/futuresoundfx-98/futuresoundfx-96.mp3"
    )

    play_alert(
        all_zones, alert_sound, alert_volume=30, alert_duration=3, fade_back=False
    )
