# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

from ..plugins import SoCoPlugin

""" Example implementation of a plugin """


__all__ = ['ExamplePlugin']


class ExamplePlugin(SoCoPlugin):
    """ This file serves as an example of a SoCo plugin """

    def __init__(self, soco, username):
        """ Initialize the plugin

        The plugin can accept any arguments it requires. It should at least
        accept a soco instance which it passes on to the base class when
        calling super's __init__.  """
        super(ExamplePlugin, self).__init__(soco)
        self.username = username

    @property
    def name(self):
        return 'Example Plugin for {name}'.format(name=self.username)

    def music_plugin_play(self):
        """ Play some music

        This is just a reimplementation of the ordinary play function, to show
        how we can use the general upnp methods from soco """

        print('Hi,', self.username)

        response = self.soco.send_command(
            TRANSPORT_ENDPOINT, PLUGIN_PLAY_ACTION, PLUGIN_PLAY_BODY)

        if (response == PLUGIN_PLAY_RESPONSE):
            return True
        else:
            return self.soco.parse_error(response)

    def music_plugin_stop(self):
        """ Stop the music

        This methods shows how, if we need it, we can use the soco
        functionality from inside the plugins """

        print('Bye,', self.username)
        self.soco.stop()


TRANSPORT_ENDPOINT = '/MediaRenderer/AVTransport/Control'
PLUGIN_PLAY_ACTION = '"urn:schemas-upnp-org:service:AVTransport:1#Play"'
PLUGIN_PLAY_BODY = '''
<u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
  <InstanceID>0</InstanceID>
  <Speed>1</Speed>
</u:Play>
'''
PLUGIN_PLAY_RESPONSE = '''
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
 s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:PlayResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
    </u:PlayResponse>
  </s:Body>
</s:Envelope>'''
