# -*- coding: utf-8 -*-

"""Classes to handle Sonos UPnP Events and Subscriptions."""

from __future__ import unicode_literals

import atexit
import logging
import socket
import threading
import time
import weakref

import requests

from . import config
from .compat import (
    Queue, BaseHTTPRequestHandler, URLError, socketserver, urlopen
)
from .data_structures import from_didl_string
from .exceptions import SoCoException
from .utils import camel_to_underscore
from .xml import XML

log = logging.getLogger(__name__)  # pylint: disable=C0103


def parse_event_xml(xml_event):
    """Parse the body of a UPnP event.

    Args:
        xml_event (bytes): bytes containing the body of the event encoded
            with utf-8.

    Returns:
        dict: A dict with keys representing the evented variables. The
            relevant value will usually be a string representation of the
            variable's value, but may on occasion be:

            * a dict (eg when the volume changes, the value will itself be a
              dict containing the volume for each channel:
              :code:`{'Volume': {'LF': '100', 'RF': '100', 'Master': '36'}}`)
            * an instance of a `DidlObject` subclass (eg if it represents
              track metadata).

    Example:

        Run this code, and change your volume, tracks etc::

            from __future__ import print_function
            try:
                from queue import Empty
            except:  # Py2.7
                from Queue import Empty

            import soco
            from pprint import pprint
            from soco.events import event_listener
            # pick a device at random
            device = soco.discover().pop()
            print (device.player_name)
            sub = device.renderingControl.subscribe()
            sub2 = device.avTransport.subscribe()

            while True:
                try:
                    event = sub.events.get(timeout=0.5)
                    pprint (event.variables)
                except Empty:
                    pass
                try:
                    event = sub2.events.get(timeout=0.5)
                    pprint (event.variables)
                except Empty:
                    pass

                except KeyboardInterrupt:
                    sub.unsubscribe()
                    sub2.unsubscribe()
                    event_listener.stop()
                    break
    """

    result = {}
    tree = XML.fromstring(xml_event)
    # property values are just under the propertyset, which
    # uses this namespace
    properties = tree.findall(
        '{urn:schemas-upnp-org:event-1-0}property')
    for prop in properties:
        for variable in prop:
            # Special handling for a LastChange event specially. For details on
            # LastChange events, see
            # http://upnp.org/specs/av/UPnP-av-RenderingControl-v1-Service.pdf
            # and http://upnp.org/specs/av/UPnP-av-AVTransport-v1-Service.pdf
            if variable.tag == "LastChange":
                last_change_tree = XML.fromstring(
                    variable.text.encode('utf-8'))
                # We assume there is only one InstanceID tag. This is true for
                # Sonos, as far as we know.
                # InstanceID can be in one of two namespaces, depending on
                # whether we are looking at an avTransport event or a
                # renderingControl event, so we need to look for both
                instance = last_change_tree.find(
                    "{urn:schemas-upnp-org:metadata-1-0/AVT/}InstanceID")
                if instance is None:
                    instance = last_change_tree.find(
                        "{urn:schemas-upnp-org:metadata-1-0/RCS/}InstanceID")
                # Look at each variable within the LastChange event
                for last_change_var in instance:
                    tag = last_change_var.tag
                    # Remove any namespaces from the tags
                    if tag.startswith('{'):
                        tag = tag.split('}', 1)[1]
                    # Un-camel case it
                    tag = camel_to_underscore(tag)
                    # Now extract the relevant value for the variable.
                    # The UPnP specs suggest that the value of any variable
                    # evented via a LastChange Event will be in the 'val'
                    # attribute, but audio related variables may also have a
                    # 'channel' attribute. In addition, it seems that Sonos
                    # sometimes uses a text value instead: see
                    # http://forums.sonos.com/showthread.php?t=34663
                    value = last_change_var.get('val')
                    if value is None:
                        value = last_change_var.text
                    # If DIDL metadata is returned, convert it to a music
                    # library data structure
                    if value.startswith('<DIDL-Lite'):
                        value = from_didl_string(value)[0]
                    channel = last_change_var.get('channel')
                    if channel is not None:
                        if result.get(tag) is None:
                            result[tag] = {}
                        result[tag][channel] = value
                    else:
                        result[tag] = value
            else:
                result[camel_to_underscore(variable.tag)] = variable.text
    return result


class Event(object):
    """A read-only object representing a received event.

    The values of the evented variables can be accessed via the ``variables``
    dict, or as attributes on the instance itself. You should treat all
    attributes as read-only.

    Args:
        sid (str): the subscription id.
        seq (str): the event sequence number for that subscription.
        timestamp (str): the time that the event was received (from Python's
            `time.time` function).
        service (str): the service which is subscribed to the event.
        variables (dict, optional): contains the ``{names: values}`` of the
            evented variables. Defaults to `None`.

    Raises:
        AttributeError:  Not all attributes are returned with each event. An
            `AttributeError` will be raised if you attempt to access as an
            attribute a variable which was not returned in the event.

    Example:

        >>> print event.variables['transport_state']
        'STOPPED'
        >>> print event.transport_state
        'STOPPED'

    """
    # pylint: disable=too-few-public-methods, too-many-arguments

    def __init__(self, sid, seq, service, timestamp, variables=None):
        # Initialisation has to be done like this, because __setattr__ is
        # overridden, and will not allow direct setting of attributes
        self.__dict__['sid'] = sid
        self.__dict__['seq'] = seq
        self.__dict__['timestamp'] = timestamp
        self.__dict__['service'] = service
        self.__dict__['variables'] = variables if variables is not None else {}

    def __getattr__(self, name):
        if name in self.variables:
            return self.variables[name]
        else:
            raise AttributeError('No such attribute: %s' % name)

    def __setattr__(self, name, value):
        """Disable (most) attempts to set attributes.

        This is not completely foolproof. It just acts as a warning! See
        `object.__setattr__`.
        """
        raise TypeError('Event object does not support attribute assignment')


class EventServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """A TCP server which handles each new request in a new thread."""
    allow_reuse_address = True


class EventNotifyHandler(BaseHTTPRequestHandler):
    """Handles HTTP ``NOTIFY`` Verbs sent to the listener server."""

    def do_NOTIFY(self):  # pylint: disable=invalid-name
        """Serve a ``NOTIFY`` request.

        A ``NOTIFY`` request will be sent by a Sonos device when a state
        variable changes. See the `UPnP Spec §4.3 [pdf]
        <http://upnp.org/specs/arch/UPnP-arch
        -DeviceArchitecture-v1.1.pdf>`_  for details.
        """
        timestamp = time.time()
        headers = requests.structures.CaseInsensitiveDict(self.headers)
        seq = headers['seq']  # Event sequence number
        sid = headers['sid']  # Event Subscription Identifier
        content_length = int(headers['content-length'])
        content = self.rfile.read(content_length)
        # find the relevant service from the sid
        with _sid_to_service_lock:
            service = _sid_to_service.get(sid)
        log.info(
            "Event %s received for %s service on thread %s at %s", seq,
            service.service_id, threading.current_thread(), timestamp)
        log.debug("Event content: %s", content)
        variables = parse_event_xml(content)
        # Build the Event object
        event = Event(sid, seq, service, timestamp, variables)
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
    """The thread in which the event listener server will run."""

    def __init__(self, address):
        """
        Args:
            address (tuple): The (ip, port) address on which the server
                should listen.
        """
        super(EventServerThread, self).__init__()
        #: `threading.Event`: Used to signal that the server should stop.
        self.stop_flag = threading.Event()
        #: `tuple`: The (ip, port) address on which the server is
        #: configured to listen.
        self.address = address

    def run(self):
        """Start the server on the local IP at port 1400 (default).

        Handling of requests is delegated to an instance of the
        `EventNotifyHandler` class.
        """
        listener = EventServer(self.address, EventNotifyHandler)
        log.info("Event listener running on %s", listener.server_address)
        # Listen for events until told to stop
        while not self.stop_flag.is_set():
            listener.handle_request()


class EventListener(object):
    """The Event Listener.

    Runs an http server in a thread which is an endpoint for ``NOTIFY``
    requests from Sonos devices.

    """

    def __init__(self):
        super(EventListener, self).__init__()
        #: `bool`: Indicates whether the server is currently running
        self.is_running = False
        self._listener_thread = None
        #: `tuple`: The address (ip, port) on which the server is
        #: configured to listen.
        # Empty for the moment. (It is set in `start`)
        self.address = ()

    def start(self, any_zone):
        """Start the event listener listening on the local machine at port 1400
        (default)

        Make sure that your firewall allows connections to this port

        Args:
            any_zone (SoCo): Any Sonos device on the network. It does not
                matter which device. It is used only to find a local IP address
                reachable by the Sonos net.

        Note:
            The port on which the event listener listens is configurable.
            See `config.EVENT_LISTENER_PORT`
        """

        # Find our local network IP address which is accessible to the
        # Sonos net, see http://stackoverflow.com/q/166506

        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_sock.connect((any_zone.ip_address, config.EVENT_LISTENER_PORT))
        ip_address = temp_sock.getsockname()[0]
        temp_sock.close()
        # Start the event listener server in a separate thread.
        self.address = (ip_address, config.EVENT_LISTENER_PORT)
        self._listener_thread = EventServerThread(self.address)
        self._listener_thread.daemon = True
        self._listener_thread.start()
        self.is_running = True
        log.info("Event listener started")

    def stop(self):
        """Stop the event listener."""
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
    """A class representing the subscription to a UPnP event."""
    # pylint: disable=too-many-instance-attributes

    def __init__(self, service, event_queue=None):
        """
        Args:
            service (Service): The SoCo `Service` to which the subscription
                 should be made.
            event_queue (:class:`~queue.Queue`): A queue on which received
                events will be put. If not specified, a queue will be
                created and used.

        """
        super(Subscription, self).__init__()
        self.service = service
        #: `str`: A unique ID for this subscription
        self.sid = None
        #: `int`: The amount of time in seconds until the subscription expires.
        self.timeout = None
        #: `bool`: An indication of whether the subscription is subscribed.
        self.is_subscribed = False
        #: :class:`~queue.Queue`: The queue on which events are placed.
        self.events = Queue() if event_queue is None else event_queue
        #: `int`: The period (seconds) for which the subscription is requested
        self.requested_timeout = None
        # A flag to make sure that an unsubscribed instance is not
        # resubscribed
        self._has_been_unsubscribed = False
        # The time when the subscription was made
        self._timestamp = None
        # Used to keep track of the auto_renew thread
        self._auto_renew_thread = None
        self._auto_renew_thread_flag = threading.Event()

    def subscribe(self, requested_timeout=None, auto_renew=False):
        """Subscribe to the service.

        If requested_timeout is provided, a subscription valid for that number
        of seconds will be requested, but not guaranteed. Check
        `timeout` on return to find out what period of validity is
        actually allocated.

        Note:
            SoCo will try to unsubscribe any subscriptions which are still
            subscribed on program termination, but it is good practice for
            you to clean up by making sure that you call :meth:`unsubscribe`
            yourself.

        Args:
            requested_timeout(int, optional): The timeout to be requested.
            auto_renew (bool, optional): If `True`, renew the subscription
                automatically shortly before timeout. Default `False`.
        """

        class AutoRenewThread(threading.Thread):
            """Used by the auto_renew code to renew a subscription from within
            a thread.

            """

            def __init__(self, interval, stop_flag, sub, *args, **kwargs):
                super(AutoRenewThread, self).__init__(*args, **kwargs)
                self.interval = interval
                self.sub = sub
                self.stop_flag = stop_flag
                self.daemon = True

            def run(self):
                sub = self.sub
                stop_flag = self.stop_flag
                interval = self.interval
                while not stop_flag.wait(interval):
                    log.info("Autorenewing subscription %s", sub.sid)
                    sub.renew()

        # TIMEOUT is provided for in the UPnP spec, but it is not clear if
        # Sonos pays any attention to it. A timeout of 86400 secs always seems
        # to be allocated
        self.requested_timeout = requested_timeout
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
        if requested_timeout is not None:
            headers["TIMEOUT"] = "Second-{0}".format(requested_timeout)
        response = requests.request(
            'SUBSCRIBE', service.base_url + service.event_subscription_url,
            headers=headers)
        response.raise_for_status()
        self.sid = response.headers['sid']
        timeout = response.headers['timeout']
        # According to the spec, timeout can be "infinite" or "second-123"
        # where 123 is a number of seconds.  Sonos uses "Second-123" (with a
        # capital letter)
        if timeout.lower() == 'infinite':
            self.timeout = None
        else:
            self.timeout = int(timeout.lstrip('Second-'))
        self._timestamp = time.time()
        self.is_subscribed = True
        log.info(
            "Subscribed to %s, sid: %s",
            service.base_url + service.event_subscription_url, self.sid)
        # Add the queue to the master dict of queues so it can be looked up
        # by sid
        with _sid_to_event_queue_lock:
            _sid_to_event_queue[self.sid] = self.events
        # And do the same for the sid to service mapping
        with _sid_to_service_lock:
            _sid_to_service[self.sid] = self.service
        # Register this subscription to be unsubscribed at exit if still alive
        # This will not happen if exit is abnormal (eg in response to a
        # signal or fatal interpreter error - see the docs for `atexit`).
        atexit.register(self.unsubscribe)

        # Set up auto_renew
        if not auto_renew:
            return
        # Autorenew just before expiry, say at 85% of self.timeout seconds
        interval = self.timeout * 85 / 100
        auto_renew_thread = AutoRenewThread(
            interval, self._auto_renew_thread_flag, self)
        auto_renew_thread.start()

    def renew(self, requested_timeout=None):
        """Renew the event subscription.

        You should not try to renew a subscription which has been
        unsubscribed, or once it has expired.

        Args:
            requested_timeout (int, optional): The period for which a renewal
                request should be made. If None (the default), use the timeout
                requested on subscription.
        """
        # NB This code is sometimes called from a separate thread (when
        # subscriptions are auto-renewed. Be careful to ensure thread-safety

        if self._has_been_unsubscribed:
            raise SoCoException(
                'Cannot renew subscription once unsubscribed')
        if not self.is_subscribed:
            raise SoCoException(
                'Cannot renew subscription before subscribing')
        if self.time_left == 0:
            raise SoCoException(
                'Cannot renew subscription after expiry')

        # SUBSCRIBE publisher path HTTP/1.1
        # HOST: publisher host:publisher port
        # SID: uuid:subscription UUID
        # TIMEOUT: Second-requested subscription duration (optional)
        headers = {
            'SID': self.sid
        }
        if requested_timeout is None:
            requested_timeout = self.requested_timeout
        if requested_timeout is not None:
            headers["TIMEOUT"] = "Second-{0}".format(requested_timeout)
        response = requests.request(
            'SUBSCRIBE',
            self.service.base_url + self.service.event_subscription_url,
            headers=headers)
        response.raise_for_status()
        timeout = response.headers['timeout']
        # According to the spec, timeout can be "infinite" or "second-123"
        # where 123 is a number of seconds.  Sonos uses "Second-123" (with a
        # a capital letter)
        if timeout.lower() == 'infinite':
            self.timeout = None
        else:
            self.timeout = int(timeout.lstrip('Second-'))
        self._timestamp = time.time()
        self.is_subscribed = True
        log.info(
            "Renewed subscription to %s, sid: %s",
            self.service.base_url + self.service.event_subscription_url,
            self.sid)

    def unsubscribe(self):
        """Unsubscribe from the service's events.

        Once unsubscribed, a Subscription instance should not be reused
        """
        # Trying to unsubscribe if already unsubscribed, or not yet
        # subscribed, fails silently
        if self._has_been_unsubscribed or not self.is_subscribed:
            return

        # Cancel any auto renew
        self._auto_renew_thread_flag.set()
        # Send an unsubscribe request like this:
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
        self._timestamp = None
        log.info(
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

    @property
    def time_left(self):
        """
        `int`: The amount of time left until the subscription expires (seconds)

        If the subscription is unsubscribed (or not yet subscribed),
        `time_left` is 0.
        """
        if self._timestamp is None:
            return 0
        else:
            time_left = self.timeout - (time.time() - self._timestamp)
            return time_left if time_left > 0 else 0

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
