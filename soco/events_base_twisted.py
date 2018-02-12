# -*- coding: utf-8 -*-
# pylint: disable=not-context-manager

# NOTE: The pylint not-content-manager warning is disabled pending the fix of
# a bug in pylint: https://github.com/PyCQA/pylint/issues/782

"""Base classes used by :py:mod:`soco.events`.

The base classes will be imported by :py:mod:`soco.events` from this module
only if a twisted reactor is detected, otherwise they will be
imported from `soco.events_base`

"""

# Importing unicode_literals results in twisted errors,
# so the import has been commented out.
# from __future__ import unicode_literals

import threading
import weakref
import logging

from twisted.internet import reactor
from twisted.web.server import Site
from twisted.web.resource import Resource
import twisted.internet.error
from twisted.internet import task
from twisted.web.client import Agent, BrowserLikeRedirectAgent
from twisted.web.http_headers import Headers

log = logging.getLogger(__name__)  # pylint: disable=C0103


class NotifyHandler(Resource):
    """Base class for `soco.events.EventNotifyHandler`
    """
    isLeaf = True

    def render_NOTIFY(self, request):  # pylint: disable=invalid-name
        """Handles HTTP ``NOTIFY`` Verbs sent to the Event Listener server by
        calling `handle_notification` with the headers and content.
        """
        headers = {}
        for header in request.requestHeaders.getAllRawHeaders():
            headers[header[0].lower()] = header[1][0]
        content = request.content.read()
        self.handle_notification(headers, content)
        return 'OK'

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
            "Event %s received for %s service at %s", seq,
            service_id, timestamp)


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
        #:  :py:class:`twisted.internet.tcp.Port`: set at `start`
        self.port = None

    def start(self, ip_address):
        """ Start the listener listening on the local machine at
        `requested_port_number`. If this port is unavailable, the
        listener will attempt to listen on the next available port,
        within a range of 100.

        Args:
            ip_address (str): The local network interface on which the server
                should start listening.

        Returns:
            int: The port on which the server is listening.

        """

        factory = Site(self.notify_handler())
        for port_number in range(self.requested_port_number,
                                 self.requested_port_number + 100):
            try:
                if port_number > self.requested_port_number:
                    log.warning("Trying next port (%d)", port_number)
                # pylint: disable=no-member
                self.port = reactor.listenTCP(port_number, factory,
                                              interface=ip_address)
                break
            # pylint: disable=invalid-name
            except twisted.internet.error.CannotListenError as e:
                log.warning(e)
                continue

        if self.port:
            log.info("Event listener running on %s", (ip_address,
                                                      self.port.port))
            return self.port.port

    # pylint: disable=unused-argument
    def stop(self, *args):
        """Stop the listener."""
        port, self.port = self.port, None
        port.stopListening()


class SubscriptionBase(object):
    """Base class for `soco.events.Subscription`
    """
    def __init__(self):
        super(SubscriptionBase, self).__init__()
        #: `function`: callback function to be called whenever an `Event` is
        #: received. If it is set and is callable, the callback function will
        #: be called with the `Event` as the only parameter and the
        #: Subscription's event queue won't be used.
        self.callback = None
        # Used to keep track of the auto_renew loop
        self._auto_renew_loop = None

    def auto_renew_start(self, interval):
        """Starts the auto_renew loop."""
        self._auto_renew_loop = task.LoopingCall(self.renew)
        # False means wait for the interval to elapse, rather than fire at once
        self._auto_renew_loop.start(interval, False)

    def auto_renew_cancel(self):
        """Cancels the auto_renew loop"""
        if self._auto_renew_loop:
            self._auto_renew_loop.stop()
            self._auto_renew_loop = None

    def renew(self, requested_timeout=None):
        """This function is overridden to handle renewal of subscription

        Args:
            requested_timeout (int, optional): The period for which a renewal
                request should be made.
        """
        pass

    # pylint: disable=no-self-use, too-many-branches, too-many-arguments
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

        agent = BrowserLikeRedirectAgent(Agent(reactor))

        if headers:
            for k in headers.keys():
                header = [headers[k].encode('latin-1')]
                del headers[k]
                k = k.encode('latin-1')
                headers[k] = header

        args = (
            method.encode('latin-1'),
            url.encode('latin-1'),
            Headers(headers)
        )
        d = agent.request(*args)  # pylint: disable=invalid-name

        if success:
            def on_success(response):  # pylint: disable=missing-docstring
                response_headers = {}
                for header in response.headers.getAllRawHeaders():
                    response_headers[header[0].lower()] = header[1][0]
                success(response_headers)
            d.addCallback(on_success)

        def on_failure(f):  # pylint: disable=invalid-name, missing-docstring
            if f.check(twisted.internet.error.ConnectError):
                log.warning('Connection error: %s', f.value)
            else:
                log.exception('Problem executing SubscriptionBase.request')
            if failure:
                failure()
        d.addErrback(on_failure)


class Subscriptions(object):
    """Maintains a mapping of sids to `soco.events.Subscription` instances.
    Registers each Subscription to be unsubscribed at exit.
    """
    def __init__(self):
        super(Subscriptions, self).__init__()
        #: `weakref.WeakValueDictionary`: used to store a mapping of
        #: sids to Subsciption instances
        self.sid_to_subscription = weakref.WeakValueDictionary()
        # Included for compatibility with events_base
        #: `threading.Lock`: for use with `subscriptions`
        self.subscriptions_lock = threading.Lock()

    def register(self, subscription):
        """Register a Subscription by updating local mapping of sids to
        Subscription instances and registering it to be unsubscribed at exit.

        Args:
            subscription(`soco.events.Subscription`): the Subscription
                to be registered.

        """

        # Add the subscription to the local dict of subscriptions so it
        # can be looked up by sid
        self.sid_to_subscription[subscription.sid] = subscription
        # Register subscription to be unsubscribed at exit if still alive
        # pylint: disable=no-member
        reactor.addSystemEventTrigger('before', 'shutdown',
                                      subscription.unsubscribe)

    def unregister(self, subscription):
        """Unregister a Subscription by updating local mapping of sids to
        Subscription instances.

        Args:
            subscription(`soco.events.Subscription`): the Subscription
                to be unregistered.

        """
        try:
            del self.sid_to_subscription[subscription.sid]
        except KeyError:
            pass

    def get_service(self, sid):
        """Look up a service from a sid.

            Args:
                sid(str): The sid from which to look up the service.

            Returns:
                Service: The service relating to that sid.
        """
        if sid in self.sid_to_subscription.keys():
            subscription = self.sid_to_subscription[sid]
            return subscription.service

    def send_to_service(self, sid, event):
        """Send an `Event` to the relevant callback or event_queue.
        If the Subscription's callback variable is set and is callable,
        it will be called with the `Event` as the only parameter. Otherwise
        the `Event` will be sent to the Subscription's event queue.

        Args:
            sid(str): The sid from which to look up the Subscription.
            event(Event): The `Event` to send to the Subscription's callback or
                event_queue.
        """
        if sid in self.sid_to_subscription.keys():
            subscription = self.sid_to_subscription[sid]
            callback = subscription.callback
            if callback and hasattr(callback, '__call__'):
                callback(event)
            else:
                subscription.events.put(event)
