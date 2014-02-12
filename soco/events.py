# -*- coding: utf-8 -*-

import socket
import requests
from gevent import pywsgi

class Events(object):
    AVTRANSPORT_ENDPOINT = 'http://{0}:1400/MediaRenderer/AVTransport/Event'

    def __init__(self, speaker_ip):
        self.listeners = set()
        self.server = None
        self.speaker_ip = speaker_ip

    def subscribe(self, callback):
        self.listeners.add(callback)

    def start(self, host='', port=8080):
        self.server = pywsgi.WSGIServer((host, port), self.__event_server)
        self.server.start()

        ip = self.__get_local_ip()

        headers = {
            'Callback': '<http://{0}:{1}>'.format(ip, port),
            'NT': 'upnp:event'
        }

        endpoint = self.AVTRANSPORT_ENDPOINT.format(self.speaker_ip)

        # `SUBSCRIBE` is a custom HTTP/1.1 verb used by Sonos devices.
        r = requests.request('SUBSCRIBE', endpoint, headers=headers)

        # Raise an exception if we get back a non-200 from the speaker.
        r.raise_for_status()

    def stop(self):
        # TODO: Investigate if there is an `UNSUBSCRIBE` verb.
        self.server.stop()

    def __event_server(self, environ, start_response):
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

    def __get_local_ip(self):
        # Not a fan of this, but there isn't a good cross-platform way of
        # determining the local IP.
        # From http://stackoverflow.com/a/7335145
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            s.connect(('8.8.8.8', 9))
            ip = s.getsockname()[0]
        except socket.error:
            raise
        finally:
            del s

        return ip
