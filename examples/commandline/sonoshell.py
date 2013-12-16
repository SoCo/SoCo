#!/usr/bin/env python

from __future__ import print_function
import sys

from soco import SoCo
from soco import SonosDiscovery


def adjust_volume(sonos, operator):
    """ Adjust the volume up or down with a factor from 1 to 100 """
    factor = get_volume_adjustment_factor(operator)
    volume = sonos.volume()

    if (operator.find('+') != -1):
        if (volume + factor) > 100:
            factor = 1
        print(sonos.volume(volume + factor))
        print(sonos.volume())
    elif (operator.find('-') != -1):
        if (volume - factor) < 0:
            factor = 1
        print(sonos.volume(volume - factor))
        print(sonos.volume())
    else:
        print("Valid operators for volume are + and -")


def get_volume_adjustment_factor(operator):
    """ get the factor to adjust the volume with """
    factor = 1
    if len(operator) > 1:
        factor = int(''.join(n for n in operator if n.isdigit()))
    return factor


if __name__ == '__main__':
    if (len(sys.argv) > 4 or len(sys.argv) < 3):
        print("Usage: sonoshell.py [speaker's IP|all] [cmd]")
        print("")
        print("Valid commands (with IP): info, play, pause, stop, next, previous, current, volume and partymode")
        print("Valid commands (with 'all'): list_ips")
        sys.exit()

    speaker_spec = sys.argv[1]
    cmd = sys.argv[2].lower()

    if speaker_spec == "all":
        sonos = SonosDiscovery()
        if (cmd == 'list_ips'):
            print('\n'.join(sonos.get_speaker_ips()))
        else:
            print("Valid commands (with 'all'): list_ips")
    else:
        sonos = SoCo(speaker_spec)
        if (cmd == 'partymode'):
            print(sonos.partymode())
        elif (cmd == 'info'):
            all_info = sonos.get_speaker_info()
            for item in all_info:
                print("%s: %s" % (item, all_info[item]))
        elif (cmd == 'play'):
            print(sonos.play())
        elif (cmd == 'pause'):
            print(sonos.pause())
        elif (cmd == 'stop'):
            print(sonos.stop())
        elif (cmd == 'next'):
            print(sonos.next())
        elif (cmd == 'previous'):
            print(sonos.previous())
        elif (cmd == 'current'):
            track = sonos.get_current_track_info()
            print('Current track: ' + track['artist'] + ' - ' + track['title'] + '. From album ' + track['album'] + '. This is track number ' + track['playlist_position'] + ' in the playlist. It is ' + track['duration'] + ' minutes long.')
        elif (cmd == 'volume'):
            if (len(sys.argv) > 3):
                operator = sys.argv[3].lower()
                adjust_volume(sonos, operator)
            else:
                print(sonos.volume())
        else:
            print("Valid commands (with IP): info, play, pause, stop, next, previous, current, volume and partymode")
