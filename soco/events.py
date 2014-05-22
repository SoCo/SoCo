# -*- coding: utf-8 -*-
# pylint: disable=too-many-public-methods

"""

Classes to handle Sonos UPnP Events and Subscriptions

"""

from __future__ import unicode_literals


import threading
import socket
import logging
import weakref
from collections import namedtuple

import requests

from .compat import (SimpleHTTPRequestHandler, urlopen, URLError, socketserver,
                     Queue,)
from .xml import XML
from .exceptions import SoCoException


log = logging.getLogger(__name__)  # pylint: disable=C0103


def parse_event_xml(xml_event):
    """ Parse a unicode xml_event and return a dict with keys representing the
    event properties"""

    result = {}
    tree = XML.fromstring(xml_event.encode('utf-8'))
    properties = tree.iterfind(
        './/{urn:schemas-upnp-org:event-1-0}property')
    for prop in properties:
        for variable in prop:
            result[variable.tag] = variable.text
    return result


Event = namedtuple('Event', ['sid', 'seq', 'service', 'variables'])
# pylint: disable=pointless-string-statement
""" A namedtuple representing a received event.

sid is the subscription id
seq is the event sequence number for that subscription
service is the service which is subscribed to the event
variables is a dict containing the {names: values} of the evented variables
"""


class EventServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """ A TCP server which handles each new request in a new thread """
    allow_reuse_address = True


class EventNotifyHandler(SimpleHTTPRequestHandler):
    """ Handles HTTP NOTIFY Verbs sent to the listener server """

    def do_NOTIFY(self):  # pylint: disable=invalid-name
        """ Handle a NOTIFY request.  See the UPnP Spec for details."""
        headers = requests.structures.CaseInsensitiveDict(self.headers)
        seq = headers['seq']  # Event sequence number
        sid = headers['sid']  # Event Subscription Identifier
        content_length = int(headers['content-length'])
        content = self.rfile.read(content_length)
        log.debug("Event %s received for sid: %s", seq, sid)
        log.debug("Current thread is %s", threading.current_thread())
        # find the relevant service from the sid
        with _sid_to_service_lock:
            service = _sid_to_service.get(sid)
        variables = parse_event_xml(content)
        # Build the Event tuple
        event = Event(sid, seq, service, variables)
        # pass the event details on to the service so it can update its cache.
        if service is not None:  # It might have been removed by another thread
            # pylint: disable=protected-access
            service._update_cache_on_event(event)
        # Find the right queue, and put the event on it
        with _sid_to_event_queue_lock:
            try:
                _sid_to_event_queue[sid].put(event)
            except KeyError:  # The key have been deleted in another thread
                pass
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        # Divert standard webserver logging to the debug log
        log.debug(fmt, *args)


class EventServerThread(threading.Thread):
    """The thread in which the event listener server will run"""

    def __init__(self, address):
        super(EventServerThread, self).__init__()
        #: used to signal that the server should stop
        self.stop_flag = threading.Event()
        #: The (ip, port) address on which the server should listen
        self.address = address

    def run(self):
        # Start the server on the local IP at port 1400.  Handling of requests
        # is delegated to instances of the EventNotifyHandler class
        listener = EventServer(self.address, EventNotifyHandler)
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
        self._listener_thread = None
        #: The address (ip, port) on which the server will listen. Empty for
        #  the moment. (It is set in `meth`:start)
        self.address = ()

    def start(self, any_zone):
        """Start the event listener listening on the local machine at port 1400

        Make sure that your firewall allows connections to this port

        any_zone is any Sonos device on the network. It does not matter which
        device. It is used only to find a local IP address reachable by the
        Sonos net.

        """

        # Find our local network IP address which is accessible to the
        # Sonos net, see http://stackoverflow.com/q/166506

        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_sock.connect((any_zone.ip_address, 1400))
        ip_address = temp_sock.getsockname()[0]
        temp_sock.close()
        # Start the event listener server in a separate thread.
        # Hardcoded to listen on port 1400. Any free port could
        # be used but this seems appropriate for Sonos, and avoids the need
        # to find a free port.
        self.address = (ip_address, 1400)
        self._listener_thread = EventServerThread(self.address)
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


class Subscription(object):
    """ A class representing the subscription to a UPnP event

    """

    def __init__(self, service, event_queue=None):
        """ Pass a SoCo Service instance as a parameter. If event_queue is
        specified, use it for the queue """
        super(Subscription, self).__init__()
        self.service = service
        #: A unique ID for this subscription
        self.sid = None
        #: The amount of time until the subscription expires
        self.timeout = None
        #: An indication of whether the subscription is subscribed
        self.is_subscribed = False
        #: A queue of events received
        self.events = Queue() if event_queue is None else event_queue
        # A flag to make sure that an unsubscribed instance is not
        # resubscribed
        self._has_been_unsubscribed = False

    def subscribe(self):
        """ Subscribe to the service """
        if self._has_been_unsubscribed:
            raise SoCoException(
                'Cannot resubscribe instance once unsubscribed')
        service = self.service
        # The event listener must be running, so start it if not
        if not event_listener.is_running:
            event_listener.start(service.soco)
        # an event subscription looks like this:
        # SUBSCRIBE publisher path HTTP/1.1
        # HOST: publisher host:publisher port
        # CALLBACK: <delivery URL>
        # NT: upnp:event
        # TIMEOUT: Second-requested subscription duration (optional)

        # pylint: disable=unbalanced-tuple-unpacking
        ip_address, port = event_listener.address
        headers = {
            'Callback': '<http://{0}:{1}>'.format(ip_address, port),
            'NT': 'upnp:event'
        }
        response = requests.request(
            'SUBSCRIBE', service.base_url + service.event_subscription_url,
            headers=headers)
        response.raise_for_status()
        self.sid = response.headers['sid']
        timeout = response.headers['timeout']
        # According to the spec, timeout can be "infinite" or "second-123"
        # where 123 is a number of seconds.  Sonos uses "Seconds-123" (with an
        # 's') and a capital letter
        if timeout.lower() == 'infinite':
            self.timeout = None
        else:
            self.timeout = int(timeout.lstrip('Seconds-'))
        self.is_subscribed = True
        log.debug(
            "Subscribed to %s, sid: %s",
            service.base_url + service.event_subscription_url, self.sid)
        # Add the queue to the master dict of queues so it can be looked up
        # by sid
        with _sid_to_event_queue_lock:
            _sid_to_event_queue[self.sid] = self.events
        # And do the same for the sid to service mapping
        with _sid_to_service_lock:
            _sid_to_service[self.sid] = self.service

    def renew(self):
        """Renew the event subscription.

        You should not try to renew a subscription which has been
        unsubscribed

        """
        if self._has_been_unsubscribed:
            raise SoCoException(
                'Cannot renew instance once unsubscribed')

        # SUBSCRIBE publisher path HTTP/1.1
        # HOST: publisher host:publisher port
        # SID: uuid:subscription UUID
        # TIMEOUT: Second-requested subscription duration (optional)

        headers = {
            'SID': self.sid
        }
        response = requests.request(
            'SUBSCRIBE',
            self.service.base_url + self.service.event_subscription_url,
            headers=headers)
        response.raise_for_status()
        log.debug(
            "Renewed subscription to %s, sid: %s",
            self.service.base_url + self.service.event_subscription_url,
            self.sid)

    def unsubscribe(self):
        """Unsubscribe from the service's events

        Once unsubscribed, a Subscription instance should not be reused

        """
        # UNSUBSCRIBE publisher path HTTP/1.1
        # HOST: publisher host:publisher port
        # SID: uuid:subscription UUID
        headers = {
            'SID': self.sid
        }
        response = requests.request(
            'UNSUBSCRIBE',
            self.service.base_url + self.service.event_subscription_url,
            headers=headers)
        response.raise_for_status()
        self.is_subscribed = False
        log.debug(
            "Unsubscribed from %s, sid: %s",
            self.service.base_url + self.service.event_subscription_url,
            self.sid)
        # remove queue from event queues and sid to service mappings
        with _sid_to_event_queue_lock:
            try:
                del _sid_to_event_queue[self.sid]
            except KeyError:
                pass
        with _sid_to_service_lock:
            try:
                del _sid_to_service[self.sid]
            except KeyError:
                pass
        self._has_been_unsubscribed = True

# pylint: disable=C0103
event_listener = EventListener()

# Thread safe mappings.
# Used to store a mapping of sids to event queues
_sid_to_event_queue = weakref.WeakValueDictionary()
# Used to store a mapping of sids to service instances
_sid_to_service = weakref.WeakValueDictionary()

# The locks to go with them
# You must only ever access the mapping in the context of this lock, eg:
#   with _sid_to_event_queue_lock:
#       queue = _sid_to_event_queue[sid]
_sid_to_event_queue_lock = threading.Lock()
_sid_to_service_lock = threading.Lock()
