""" Sample script to demonstrate use of SoCo snapshot

This is useful for scenarios such as when you want to switch to radio,
an announcement or doorbell sound and then back to what was playing previously.

To use it just change the IP address to one of your Sonos players.

This script will:
 - start playing a radio station
 - take a snapshot of the status of the sonos player (what playing, volume etc.)
 - play an alert mp3 for a few seconds (a poem!)
 - re-instate the sonos player to it's previous state (the radio station)

Note: The Snapshot class is designed for single use. If a second snapshot is
required create another instance of the class e.g. `snap2 = Snapshot(device)`.
"""

import time
import soco
from soco.snapshot import Snapshot

# something to play on a Sonos player to start (a radio station)
start_uri = "x-sonosapi-stream:s2846?sid=254&amp;flags=32"

# alert sound to interrupt the above (a poem) - use amy file Sonos can play
alert_uri = "https://ia800504.us.archive.org/21/items/PoemsInEnglish/tygerblake.mp3"

# choose device
device = soco.SoCo("192.168.1.68")  # <--change IP to one of your Sonos devices

# start playing something on this device(a radio station)
print("playing a radio station")
device.play_uri(start_uri, title="test radio station")
time.sleep(10)  # pause to ensure radio station playing

# take snapshot of current state
snap = Snapshot(device)  # 1) create a Snapshot class for this device
snap.snapshot()  # 2) take a snapshot of this device's status

# Do something that changes what's playing on this device
print("playing alert")
device.volume += 10  # increase volume
device.play_uri(alert_uri, title="my alert")  # play an alert sound
time.sleep(10)  # wait for a bit !

# Restore previous state of Sonos (with slow fade up)
print("reinstating how it was before....")
snap.restore(fade=True)
