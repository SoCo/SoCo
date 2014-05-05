# -*- coding: utf-8 -*-
from __future__ import unicode_literals

"""

Classes to handle Sonos UPnP Events

"""

try:  # python 3
    from http.server import SimpleHTTPRequestHandler
    from urllib.request import urlopen
    from urllib.error import URLError
    import socketserver
    from queue import Queue
except ImportError:  # python 2.7
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from urllib2 import urlopen, URLError
    import SocketServer as socketserver
    from Queue import Queue

import threading
import socket
import logging

import soco

log = logging.getLogger(__name__)  # pylint: disable=C0103


class EventServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """ A TCP server which handles each new request in a new thread """
    pass


class EventNotifyHandler(SimpleHTTPRequestHandler):
    """ Handles HTTP NOTIFY Verbs sent to the server """

    def do_NOTIFY(self):
        headers = dict(self.headers)
        seq = headers['seq']  # Event sequence number
        sid = headers['sid']  # Event Subscription Identifier
        # UPnP spec says that a TIMEOUT header should be returned, but
        # Sonos does not appear to use one. At the moment, therefore
        # we assume that subscriptions never expire, and so never need to be
        # renewed.
        content_length = int(headers['content-length'])
        content = self.rfile.read(content_length)
        # Build an event structure to put on the queue, containing the useful
        # information extracted from the request
        event = {
            'seq': seq,
            'sid': sid,
            'content': content
            }

        self.server.event_queue.put(event)
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # We override this to stop the printing of requests and errors
        pass


class EventServerThread(threading.Thread):
    """docstring for ClassName"""
    def __init__(self, ip, event_queue):
        super(EventServerThread, self).__init__()
        self.stop_flag = threading.Event()
        self.ip = ip
        self.event_queue = event_queue

    def run(self):
        httpd = EventServer((self.ip, 1400), EventNotifyHandler)
        httpd.event_queue = self.event_queue
        log.debug("Event listener running on %s", httpd.server_address)
        while not self.stop_flag.is_set():
            httpd.handle_request()


class EventListener(object):
    """docstring for EventListener"""
    def __init__(self):
        super(EventListener, self).__init__()
        self.is_running = False
        self.event_queue = Queue()
        self._listener_thread = None
        self.address = ()

    def start(self, any_zone):
        """Start the event listener"""

        # First, find our network IP address which is accessible to the Sonos net
        # See http://stackoverflow.com/q/166506
        helper_ip = any_zone.ip_address
        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_sock.connect((helper_ip, 1400))
        ip = temp_sock.getsockname()[0]
        temp_sock.close()
        # Start the server in a separate thread
        self.address = (ip, 1400)
        self._listener_thread = EventServerThread(ip, self.event_queue)
        self._listener_thread.daemon = True
        self._listener_thread.start()
        self.is_running = True
        log.info("Event listener started")

    def stop(self):
        """docstring for stop"""
        self._listener_thread.stop_flag.set()
        try:
            urlopen(
                'http://%s:%s/' % (self.address[0], self.address[1]))
        except URLError:
            # If the server is already shut down, we receive a socket error,
            # which we ignore.
            pass
        self._listener_thread.join()
        self.is_running = False
        log.info("Event listener stopped")
    pass

event_listener = EventListener()
