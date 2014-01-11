#!/usr/bin/env python

from __future__ import print_function
import sys
try:
    import colorama
except:
    colorama = False

from soco import SoCo
from soco import SonosDiscovery


def adjust_volume(sonos, operator):
    """ Adjust the volume up or down with a factor from 1 to 100 """
    factor = get_volume_adjustment_factor(operator)
    if not factor:
        return False

    volume = sonos.volume

    if (operator[0] == '+'):
        if (volume + factor) > 100:
            factor = 1
        sonos.volume = (volume + factor)
        print(sonos.volume)
    elif (operator[0] == '-'):
        if (volume - factor) < 0:
            factor = 1
        sonos.volume = (volume - factor)
        print(sonos.volume)
    else:
        print("Valid operators for volume are + and -")


def get_volume_adjustment_factor(operator):
    """ get the factor to adjust the volume with """
    factor = 1
    if len(operator) > 1:
        try:
            factor = int(operator[1:])
        except ValueError:
            print("Adjustment factor for volume has to be a int.")
            return False
    return factor


def print_current_track_info():
    track = sonos.get_current_track_info()
    print(
        "Current track: %s - %s. From album %s. This is track number"
        " %s in the playlist. It is %s minutes long." % (
            track['artist'],
            track['title'],
            track['album'],
            track['playlist_position'],
            track['duration']
        )
    )


def print_queue():
    queue = sonos.get_queue()

    ANSI_BOLD = '\033[1m'
    ANSI_RESET = '\033[0m'

    # colorama.init() takes over stdout/stderr to give cross-platform colors
    if colorama:
        colorama.init()

    current = int(sonos.get_current_track_info()['playlist_position'])

    queue_length = len(queue)
    index_padding = len(str(queue_length))

    for idx, track in enumerate(queue, 1):
        if (idx == current):
            color = ANSI_BOLD
        else:
            color = ANSI_RESET

        print(
            "%s%0*d: %s - %s. From album %s." % (
                color,
                index_padding,
                idx,
                track['artist'],
                track['title'],
                track['album']
            )
        )

    # Release stdout/stderr from colorama
    if colorama:
        colorama.deinit()


if __name__ == '__main__':
    if (len(sys.argv) > 4 or len(sys.argv) < 3):
        print("Usage: sonoshell.py [speaker's IP|all] [cmd]")
        print("")
        print("Valid commands (with IP): info, play, pause, stop, next, previous, current, queue, volume and partymode")
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
            print_current_track_info()
        elif (cmd == 'queue'):
            print_queue()
        elif (cmd == 'volume'):
            if (len(sys.argv) > 3):
                operator = sys.argv[3].lower()
                adjust_volume(sonos, operator)
            else:
                print(sonos.volume)
        else:
            print("Valid commands (with IP): info, play, pause, stop, next, previous, current, volume and partymode")
