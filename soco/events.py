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
    allow_reuse_address = True


class EventNotifyHandler(SimpleHTTPRequestHandler):
    """ Handles HTTP NOTIFY Verbs sent to the listener server """

    def do_NOTIFY(self):
        """ Handle a NOTIFY request.  See the UPnP Spec for details."""
        headers = dict(self.headers)
        seq = headers['seq']  # Event sequence number
        sid = headers['sid']  # Event Subscription Identifier
        content_length = int(headers['content-length'])
        content = self.rfile.read(content_length)
        # Build an event structure to put on the queue, containing the useful
        # information extracted from the request
        event = {
            'seq': seq,
            'sid': sid,
            'content': content
            }
        # put it on the queue for later consumption
        self.server.event_queue.put(event)
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # We override this to stop the printing of requests and errors
        pass


class EventServerThread(threading.Thread):
    """The thread in which the event listener server will run"""
    def __init__(self, ip, event_queue):
        super(EventServerThread, self).__init__()
        #: used to signal that the server should stop
        self.stop_flag = threading.Event()
        #: The ip address on which the server should listen
        self.ip = ip
        #: The queue onto which events will be placed
        self.event_queue = event_queue

    def run(self):
        # Start the server on the local IP at port 1400. Any free port could
        # be used but this seems appropriate for Sonos, and avoids the need
        # to find a free port. Handling of requests is delegated to instances
        # of the EventNotifyHandler class
        listener = EventServer((self.ip, 1400), EventNotifyHandler)
        listener.event_queue = self.event_queue
        log.debug("Event listener running on %s", listener.server_address)
        # Listen for events untill told to stop
        while not self.stop_flag.is_set():
            listener.handle_request()


class EventListener(object):
    """The Event Listener.

    Runs an http server in a thread which is an endpoint for NOTIFY messages
    from sonos devices"""
    def __init__(self):
        super(EventListener, self).__init__()
        #: Indicates whether the server is currently running
        self.is_running = False
        #: The queue to which events are posted
        self.event_queue = Queue()
        self._listener_thread = None
        #: The address (ip, port) on which the server is listening
        self.address = ()

    def start(self, any_zone):
        """Start the event listener

        any_zone is any Sonos device on the network. It does not matter which
        device. It is used only to find a local IP address reachable by the
        Sonos net.

        """

        # Find our local network IP address which is accessible to the Sonos net
        # See http://stackoverflow.com/q/166506

        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_sock.connect((any_zone.ip_address, 1400))
        ip = temp_sock.getsockname()[0]
        temp_sock.close()
        # Start the event listener server in a separate thread
        self.address = (ip, 1400)
        self._listener_thread = EventServerThread(ip, self.event_queue)
        self._listener_thread.daemon = True
        self._listener_thread.start()
        self.is_running = True
        log.info("Event listener started")

    def stop(self):
        """Stop the event listener"""
        # Signal the thread to stop before handling the next request
        self._listener_thread.stop_flag.set()
        # Send a dummy request in case the http server is currently listening
        try:
            urlopen(
                'http://%s:%s/' % (self.address[0], self.address[1]))
        except URLError:
            # If the server is already shut down, we receive a socket error,
            # which we ignore.
            pass
        # wait for the thread to finish
        self._listener_thread.join()
        self.is_running = False
        log.info("Event listener stopped")

event_listener = EventListener()
event_queue = event_listener.event_queue
