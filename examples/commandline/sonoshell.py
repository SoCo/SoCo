#!/usr/bin/env python

import sys

from soco import SoCo

if __name__ == '__main__':
    if (len(sys.argv) != 3):
        print "Usage: sonoshell.py [speaker's IP] [cmd]"
        print ""
        print "Valid commands: play, pause, stop, next, previous, current, and partymode"
        sys.exit()

    speaker_ip = sys.argv[1]
    cmd = sys.argv[2].lower()

    sonos = SoCo(speaker_ip)

    if (cmd == 'partymode'):
        print sonos.partymode()
    elif (cmd == 'play'):
        print sonos.play()
    elif (cmd == 'pause'):
        print sonos.pause()
    elif (cmd == 'stop'):
        print sonos.stop()
    elif (cmd == 'next'):
        print sonos.next()
    elif (cmd == 'previous'):
        print sonos.previous()
    elif (cmd == 'current'):
        track = sonos.get_current_track_info()

        print 'Current track: ' + track['artist'] + ' - ' + track['title'] + '. From album ' + track['album'] + '. This is track number ' + track['playlist_position'] + ' in the playlist. It is ' + track['duration'] + ' minutes long.'
    else:
        print "Valid commands: play, pause, stop, next, previous, current, and partymode"
