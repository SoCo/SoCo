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

Note: the snap function is designed to be used once, Having taken a snap to 
take another re-instantiate the class.
"""

import time
import soco
from soco.snapshot import Snapshot


def play_alert(alert_uri, alert_volume=20, alert_duration=0, fade_back=False):
    """
    Demo function using soco.snapshot accrss multiple Sonos players.
    
    :param alert_uri: file that Sonos can play as an alert
    :param alert_volume: volume to play alert at 
    :param alert_duration: length of alert (if zero then length of track)
    :param fade_back: on reinstating the zones fade up the sound?
    :return: 
    """

    # Use soco.snapshot to capture current state of each zone to allow restore
    for zone in zones:
        zone.snap = Snapshot(zone)
        zone.snap.snapshot()
        print('snapshot of zone: {}'.format(zone.player_name))

    # prepare all zones for playing the alert
    for zone in zones:
        # Each Sonos group has one coordinator only these can play, pause, etc.
        if zone.is_coordinator:
            if not zone.is_playing_tv:  # can't pause TV - so don't try!
                # pause music for each coordinators if playing
                trans_state = zone.get_current_transport_info()
                if trans_state['current_transport_state'] == 'PLAYING':
                    zone.pause()

        # For every Sonos player set volume and mute for every zone
        zone.volume = alert_volume
        zone.mute = False

    # play the sound (uri) on each sonos coordinator
    print('will play: {} on all coordinators'.format(alert_uri))
    for zone in zones:
        if zone.is_coordinator:
            zone.play_uri(uri=alert_uri, title='Sonos Alert')
            a_coordinator = zone  # remember last coordinator for use next

    # wait for alert_duration
    time.sleep(alert_duration)

    # restore each zone to previous state
    for zone in zones:
        print('restoring {}'.format(zone.player_name))
        zone.snap.restore(fade=fade_back)

if __name__ == '__main__':

    zones = soco.discover()

    # alert uri to send to sonos - this uri must be available to Sonos
    alert_sound = 'https://ia800503.us.archive.org/8/items/futuresoundfx-98/futuresoundfx-96.mp3'

    play_alert(alert_sound, alert_volume=30, alert_duration=3, fade_back=False)


