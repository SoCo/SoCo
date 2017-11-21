# -*- coding: utf-8 -*-
# pylint: disable=not-context-manager

# NOTE: The pylint not-content-manager warning is disabled pending the fix of
# a bug in pylint: https://github.com/PyCQA/pylint/issues/782

"""Base classes used by :py:mod:`soco.events`.

The base classes will be imported by :py:mod:`soco.events` from this module
unless a twisted reactor is detected, in which case they will be
imported from `soco.events_base_twisted`

"""

from __future__ import unicode_literals

import atexit
import logging
import threading
import weakref

import requests

from .compat import (
    BaseHTTPRequestHandler, URLError, socketserver, urlopen
)

log = logging.getLogger(__name__)  # pylint: disable=C0103

class EventServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """A TCP server which handles each new request in a new thread."""
    allow_reuse_address = True

class EventServerThread(threading.Thread):
    """The thread in which the event listener server will run."""

    def __init__(self, address, notify_handler):
        """
        Args:
            address (tuple): The (ip, port) address on which the server
                should listen.

            notify_handler (soco.events.EventNotifyHandler): The
                `EventNotifyHandler` which should be used to
                handle requests.
        """
        super(EventServerThread, self).__init__()
        #: `threading.Event`: Used to signal that the server should stop.
        self.stop_flag = threading.Event()
        #: `tuple`: The (ip, port) address on which the server is
        #: configured to listen.
        self.address = address
        #: `soco.events.EventNotifyHandler`: Used to handle requests
        self.notify_handler = notify_handler

    def run(self):
        """Start the server on `address`.

        Handling of requests is delegated to `notify_handler`.
        """
        listener = EventServer(self.address, self.notify_handler)
        log.info("Event listener running on %s", listener.server_address)
        # Listen for events until told to stop
        while not self.stop_flag.is_set():
            listener.handle_request()

class NotifyHandler(BaseHTTPRequestHandler):
    """Base class for `soco.events.EventNotifyHandler`
    """
    def do_NOTIFY(self):  # pylint: disable=invalid-name
        """Handles HTTP ``NOTIFY`` Verbs sent to the Event Listener server by
        calling `handle_notification` with the headers and content.
        """
        headers = requests.structures.CaseInsensitiveDict(self.headers)
        content_length = int(headers['content-length'])
        content = self.rfile.read(content_length)
        self.handle_notification(headers, content)
        self.send_response(200)
        self.end_headers()

    def handle_notification(self, headers, content):
        """This function is overriden in `soco.events.EventNotifyHandler`
        to handle notifications

        Args:
            headers (dict): A dict of received headers.
            content (str): A string of received content.

        """
        pass

    # pylint: disable=no-self-use, missing-docstring
    def log_event(self, seq, service_id, timestamp):
        log.info(
            "Event %s received for %s service on thread %s at %s", seq,
            service_id, threading.current_thread(), timestamp)

    # Do we need a twisted equivalent?
    def log_message(self, fmt, *args):  # pylint: disable=arguments-differ
        # Divert standard webserver logging to the debug log
        log.debug(fmt, *args)

class Listener(object):
    """Base class for `soco.events.EventListener`
    """

    def __init__(self, notify_handler, requested_port_number):
        """
        Args:
            notify_handler (soco.events.EventNotifyHandler): The
                `EventNotifyHandler` which should be used to
                handle requests.
            requested_port_number(int): The port on which to listen.
        """
        super(Listener, self).__init__()
        #: `soco.events.EventNotifyHandler`: Used to handle requests.
        self.notify_handler = notify_handler
        #: `int`: Port on which to listen.
        self.requested_port_number = requested_port_number
        #: `EventServerThread`: thread on which to run.
        self._listener_thread = None

    def start(self, ip_address):
        """ Start the listener listening on the local machine at
        `requested_port_number`.

        Args:
            ip_address (str): The local network interface on which the server
                should start listening.

        Returns:
            int: `requested_port_number`. Included for compatibility with
            `soco.events_base_twisted.Listener.start`
        """
        self._listener_thread = EventServerThread((ip_address,
            self.requested_port_number), self.notify_handler)
        self._listener_thread.daemon = True
        self._listener_thread.start()
        return self.requested_port_number

    def stop(self, address):
        """Stop the listener."""
        # Signal the thread to stop before handling the next request
        self._listener_thread.stop_flag.set()
        # Send a dummy request in case the http server is currently listening
        try:
            urlopen(
                'http://%s:%s/' % (address[0], address[1]))
        except URLError:
            # If the server is already shut down, we receive a socket error,
            # which we ignore.
            pass
        # wait for the thread to finish, with a timeout of one second
        # to ensure the main thread does not hang
        self._listener_thread.join(1)
        # check if join timed out and issue a warning if it did
        if self._listener_thread.isAlive():
            log.warning('Event Listener did not shutdown gracefully.')

class SubscriptionBase(object):
    """Base class for `soco.events.Subscription`
    """
    def __init__(self):
        super(SubscriptionBase, self).__init__()
        # Used to keep track of the auto_renew thread
        self._auto_renew_thread = None
        self._auto_renew_thread_flag = threading.Event()

    def auto_renew_start(self, interval):
        """Starts the auto_renew thread."""

        class AutoRenewThread(threading.Thread):
            """Used by the auto_renew code to renew a subscription from within
            a thread.

            """

            def __init__(self, interval, stop_flag, sub, *args, **kwargs):
                super(AutoRenewThread, self).__init__(*args, **kwargs)
                self.interval = interval
                self.subscription = sub
                self.stop_flag = stop_flag
                self.daemon = True

            def run(self):
                subscription = self.subscription
                stop_flag = self.stop_flag
                interval = self.interval
                while not stop_flag.wait(interval):
                    subscription.renew()

        auto_renew_thread = AutoRenewThread(
            interval, self._auto_renew_thread_flag, self)
        auto_renew_thread.start()

    def auto_renew_cancel(self):
        """Cancels the auto_renew thread"""
        self._auto_renew_thread_flag.set()

    def renew(self, requested_timeout=None):
        """This function is overridden to handle renewal of subscription

        Args:
            requested_timeout (int, optional): The period for which a renewal
                request should be made.
        """
        pass

    # pylint: disable=no-self-use, too-many-arguments
    def request(self, method, url, headers, success=None, failure=None):
        """Sends an HTTP request.

        Args:
            method (str): 'SUBSCRIBE' or 'UNSUBSCRIBE'.
            url (str): The full endpoint to which the request is being sent.
            headers (dict): A dict of headers, each key and each value being
                of type `str`.
            success (function, optional): A function to be called if the
                request succeeds. The function will be called with a dict
                of response headers as its only parameter.
            failure (function, optional): A function to call if the request
                fails. The function will be called without any parameter.
        """
        try:
            response = requests.request(method, url, headers=headers)
            response.raise_for_status()
        except: # pylint: disable=bare-except
            log.exception('Problem sending request')
        else:
            if success:
                success(response.headers)
            return

        if failure:
            failure()

class Subscriptions(object):
    """Maintains mappings of sids to event queues and sids to service
    instances and the thread safe locks to go with them. Registers each
    `Subscription` to be unsubscribed at exit.

    """
    def __init__(self):
        super(Subscriptions, self).__init__()
        #: `weakref.WeakValueDictionary`: Thread safe mapping.
        #: Used to store a mapping of sids to event queues
        self.sid_to_event_queue = weakref.WeakValueDictionary()
        #: `weakref.WeakValueDictionary`: Thread safe mapping.
        #: Used to store a mapping of sids to service instances
        self.sid_to_service = weakref.WeakValueDictionary()
        # The locks to go with them
        # You must only ever access the mapping in the context of this lock, eg:
        #   with self.sid_to_event_queue_lock:
        #       queue = self.sid_to_event_queue[sid]
        #: `threading.Lock`: for use with `sid_to_event_queue`
        self.sid_to_event_queue_lock = threading.Lock()
        #: `threading.Lock`: for use with `sid_to_service`
        self.sid_to_service_lock = threading.Lock()

    def register(self, subscription):
        """Register a Subscription by updating local mapping of sids to
        event queues and sids to service instances and registering it
        to be unsubscribed at exit.

        Args:
            subscription(`soco.events.Subscription`): the Subscription
                to be registered.

        """
        # Add the queue to the master dict of queues so it can be looked up
        # by sid
        with self.sid_to_event_queue_lock:
            self.sid_to_event_queue[subscription.sid] = subscription.events
        # And do the same for the sid to service mapping
        with self.sid_to_service_lock:
            self.sid_to_service[subscription.sid] = subscription.service
        # Register subscription to be unsubscribed at exit if still alive
        # This will not happen if exit is abnormal (eg in response to a
        # signal or fatal interpreter error - see the docs for `atexit`).
        atexit.register(subscription.unsubscribe)

    def unregister(self, subscription):
        """Unregister a Subscription by updating local mapping of sids to
        event queues and sids to service instances.

        Args:
            subscription(`soco.events.Subscription`): the Subscription
                to be unregistered.

        """
        with self.sid_to_event_queue_lock:
            try:
                del self.sid_to_event_queue[subscription.sid]
            except KeyError:
                pass
        with self.sid_to_service_lock:
            try:
                del self.sid_to_service[subscription.sid]
            except KeyError:
                pass

    def get_service(self, sid):
        """Look up a service from a sid.

            Args:

                sid(str): The sid from which to look up the service.

            Returns:
                Service: The service relating to that sid.
        """
        with self.sid_to_service_lock:
            service = self.sid_to_service.get(sid)
        return service

    def send_to_service(self, sid, event):
        """Send an `Event` to the relevant event_queue.

            Args:

                sid(str): The sid from which to look up the event_queue.
                event(Event): The `Event` to send to the event_queue.
        """
        with self.sid_to_event_queue_lock:
            try:
                self.sid_to_event_queue[sid].put(event)
            except KeyError:  # The key may have been deleted in another thread
                pass

