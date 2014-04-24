# -*- coding: utf-8 -*-
# pylint: disable=W0511
""" The events module contains the Events class for the implementation of
the listening feature. A user-provided handler can be called upon callbacks
from the Sonos Zones
"""
import socket
import requests
from gevent import pywsgi


class Events(object):
    """A class for creation and subscription to Sonos notifications

    Public functions:
    subscribe -- assign a callback function to the listener
    start -- start the listening (i.e. send the SUBSCRIBE verb to zoneplayer)
    stop -- shutdown the server
    """

    AVTRANSPORT_ENDPOINT = 'http://{0}:1400/MediaRenderer/AVTransport/Event'

    def __init__(self, speaker_ip):
        self.listeners = set()
        self.server = None
        self.speaker_ip = speaker_ip

    def subscribe(self, callback):
        """ Adds the function handle callback to the set of listeners """
        self.listeners.add(callback)

    def start(self, host='', port=8080):
        """ start the server and listen to messages from zoneplayers 

        TODO: check if port available and switch to other port if needed
        """
        self.server = pywsgi.WSGIServer((host, port), self.__event_server)
        self.server.start()

        ip = __get_local_ip() # pylint: disable=C0103

        headers = {
            'Callback': '<http://{0}:{1}>'.format(ip, port),
            'NT': 'upnp:event'
        }

        endpoint = self.AVTRANSPORT_ENDPOINT.format(self.speaker_ip)

        # `SUBSCRIBE` is a custom HTTP/1.1 verb used by Sonos devices.
        # pylint: disable=C0103
        r = requests.request('SUBSCRIBE', endpoint, headers=headers)

        # Raise an exception if we get back a non-200 from the speaker.
        r.raise_for_status()

    def stop(self):
        """ Stop the server listening for Zoneplayer messages

        TODO: Investigate if there is an `UNSUBSCRIBE` verb.
        """
        self.server.stop()

    def __event_server(self, environ, start_response):
        """ call ALL callbacks previously hooked up through subscribe() """
        status = '405 Method Not Allowed'

        # `NOTIFY` is a custom HTTP/1.1 verb used by Sonos devices
        headers = [
            ('Allow', 'NOTIFY'),
            ('Content-Type', 'text/plain')
        ]

        response = "Sorry, I only support the HTTP/1.1 NOTIFY verb.\n"

        if environ['REQUEST_METHOD'].lower() == 'notify':
            body = environ['wsgi.input'].readline()

            for callback in self.listeners:
                # TODO: Parse the raw XML into something sensible.
                # Right now, subscribed listeners will just get the raw XML
                # sent from the Sonos device.
                callback(body)

            status = '200 OK'
            headers = []
            response = ''

        start_response(status, headers)
        return [response]

def __get_local_ip():
    """ Determine local IP in a platform independent way """
    # Not a fan of this, but there isn't a good cross-platform way of
    # determining the local IP.
    # From http://stackoverflow.com/a/7335145
    # pylint: disable=C0103
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        s.connect(('8.8.8.8', 9))
        ip = s.getsockname()[0] # pylint: disable=C0103
    except socket.error:
        raise
    finally:
        del s

    return ip
