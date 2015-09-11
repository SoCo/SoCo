# -*- coding: utf-8 -*-

"""Example implementation of a plugin."""

from __future__ import (
    print_function, unicode_literals
)

from ..plugins import SoCoPlugin

__all__ = ['ExamplePlugin']


class ExamplePlugin(SoCoPlugin):

    """This file serves as an example of a SoCo plugin."""

    def __init__(self, soco, username):
        """Initialize the plugin.

        The plugin can accept any arguments it requires. It should at
        least accept a soco instance which it passes on to the base
        class when calling super's __init__.
        """
        super(ExamplePlugin, self).__init__(soco)
        self.username = username

    @property
    def name(self):
        return 'Example Plugin for {0}'.format(self.username)

    def music_plugin_play(self):
        """Play some music.

        This is just a reimplementation of the ordinary play function,
        to show how we can use the general upnp methods from soco
        """

        print('Hi,', self.username)

        self.soco.avTransport.Play([
            ('InstanceID', 0),
            ('Speed', 1)
        ])

    def music_plugin_stop(self):
        """Stop the music.

        This methods shows how, if we need it, we can use the soco
        functionality from inside the plugins
        """

        print('Bye,', self.username)
        self.soco.stop()
