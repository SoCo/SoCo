from __future__ import print_function

import soco

""" Prints the name of each discovered player in the network. """
for zone in soco.discover():
    print(zone.player_name)
