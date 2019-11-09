#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This illustrates how to use SoCo plugins
# an example plugin is provided in soco.plugins.example.ExamplePlugin

from __future__ import print_function
import time

from soco import SoCo
from soco.plugins import SoCoPlugin


def main():
    speakers = [speaker.ip_address for speaker in SoCo.discover()]

    if not speakers:
        print("no speakers found, exiting.")
        return

    soco = SoCo(speakers[0])

    # get a plugin by name (eg from a config file)
    myplugin = SoCoPlugin.from_name(
        "soco.plugins.example.ExamplePlugin", soco, "some user"
    )

    # do something with your plugin
    print("Testing", myplugin.name)
    myplugin.music_plugin_play()

    time.sleep(5)

    # create a plugin by normal instantiation
    from soco.plugins.example import ExamplePlugin

    # create a new plugin, pass the soco instance to it
    myplugin = ExamplePlugin(soco, "a user")

    print("Testing", myplugin.name)

    # do something with your plugin
    myplugin.music_plugin_stop()


if __name__ == "__main__":
    main()
