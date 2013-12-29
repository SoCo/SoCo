#!/usr/bin/env python

from __future__ import print_function
import sys
import time

from soco import SoCo
from soco import SonosDiscovery


def fade_volume(sonos, start, target, duration):
    """ fade the volume (up or down) from start to target over duration seconds """
    if (start > 100):
        start = 100
    elif (start < 0):
        start = 0

    if (target > 100):
        target = 100
    elif (target < 0):
        target = 0

    if (start > target):
        adj_range = reversed(xrange(target, start + 1))
    elif (target > start):
        adj_range = xrange(start, target + 1)
    elif (start == target):
        print("start of %d == target of %d, nothing to do" % (start, target))
        return False

    adj_range = list(adj_range)

    step = float(duration) / (float(len(adj_range)) - 1)

    print("fading volume from %d to %d in %d steps over %d seconds (%.4fs per step)" % (start, target, len(adj_range), int(duration), step))
    for adjustment in adj_range:
        start = time.time()
        sonos.volume = adjustment
        sleep = step - (time.time() - start)
        if sleep <= 0:
            print("set volume to %d, timer overrun by %.4f seconds" % (adjustment, sleep * -1))
        else:
            print("set volume to %d, sleeping for %.4fs" % (adjustment, sleep))
            time.sleep(sleep)


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


if __name__ == '__main__':
    if (len(sys.argv) > 6 or len(sys.argv) < 3):
        print("Usage: sonoshell.py [speaker's IP|all] [cmd]")
        print("")
        print("Valid commands (with IP): info, play, pause, stop, next, previous, current, volume, fade and partymode")
        print("Valid commands (with 'all'): list_ips, list")
        sys.exit()

    speaker_spec = sys.argv[1]
    cmd = sys.argv[2].lower()

    if speaker_spec == "all":
        sonos = SonosDiscovery()
        if (cmd == 'list_ips'):
            print('\n'.join(sonos.get_speaker_ips()))
        elif (cmd == 'list'):
            for speaker_spec in sonos.get_speaker_ips():
                speaker = SoCo(speaker_spec)
                info = speaker.get_speaker_info()
                print("%16s %10s %s" % ( speaker_spec, info['model'], info['zone_name']))
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
        elif (cmd == 'volume'):
            if (len(sys.argv) > 3):
                operator = sys.argv[3].lower()
                adjust_volume(sonos, operator)
            else:
                print(sonos.volume)
        elif (cmd == 'fade'):
            if (len(sys.argv) == 5):
                adjustment = sys.argv[3]
                start = sonos.volume
                if adjustment[0] == "+":
                    target = start + int(adjustment[1:])
                elif adjustment[0] == "-":
                    target = start - int(adjustment[1:])
                else:
                    print("usage: fade <start> <target> <duration>")
                    print("usage: fade [+-]<adjustment> <duration>")
                    sys.exit(1)
                fade_volume(sonos = sonos, start = sonos.volume, target = target, duration = sys.argv[4])
            elif (len(sys.argv) == 6):
                fade_volume(sonos = sonos, start = int(sys.argv[3]), target = int(sys.argv[4]), duration = sys.argv[5])
            else:
                print("usage: fade <start> <target> <duration>")
                print("usage: fade [+-]<adjustment> <duration>")

        else:
            print("Valid commands (with IP): info, play, pause, stop, next, previous, current, volume and partymode")
