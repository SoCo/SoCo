# -*- coding: utf-8 -*-
# pylint: disable=not-context-manager

# NOTE: The pylint not-content-manager warning is disabled pending the fix of
# a bug in pylint. See https://github.com/PyCQA/pylint/issues/782

# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance


"""Classes to handle Sonos UPnP Events and Subscriptions.

The `Subscription` class from this module will be used in
:py:mod:`soco.services` unless config.EVENTS_MODULE is set
to point to :py:mod:`soco.events_twisted`, in which case
:py:mod:`soco.events_twisted.Subscription` will be used.
See the Example in :py:mod:`soco.events_twisted`.

Example:

    Run this code, and change your volume, tracks etc::

        from __future__ import print_function
        try:
            from queue import Empty
        except:  # Py2.7
            from Queue import Empty

        import logging
        logging.basicConfig()
        import soco
        from pprint import pprint
        from soco.events import event_listener
        # pick a device at random and use it to get
        # the group coordinator
        device = soco.discover().pop().group.coordinator
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

from __future__ import unicode_literals

import logging
import threading

import requests

from .compat import (
    BaseHTTPRequestHandler, URLError, socketserver, urlopen
)

# Event is imported so that 'from events import Events' still works
# pylint: disable=unused-import
from .events_base import Event  # noqa: F401

from .events_base import (
    EventNotifyHandlerBase, EventListenerBase, SubscriptionBase,
    SubscriptionsMap
)

from .exceptions import SoCoException

log = logging.getLogger(__name__)  # pylint: disable=C0103


class EventServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """A TCP server which handles each new request in a new thread."""
    allow_reuse_address = True


class EventNotifyHandler(BaseHTTPRequestHandler, EventNotifyHandlerBase):
    """Handles HTTP ``NOTIFY`` Verbs sent to the listener server.
    Inherits from `soco.events_base.EventNotifyHandlerBase`.
    """
    def __init__(self, *args, **kwargs):
        # The SubscriptionsMap instance created when this module is imported.
        # This is referenced by soco.events_base.EventNotifyHandlerBase.
        self.subscriptions_map = subscriptions_map
        # super appears at the end of __init__, because
        # BaseHTTPRequestHandler.__init__ does not return.
        super(EventNotifyHandler, self).__init__(*args, **kwargs)

    def do_NOTIFY(self):  # pylint: disable=invalid-name
        """Serve a ``NOTIFY`` request by calling `handle_notification`
        with the headers and content.
        """
        headers = requests.structures.CaseInsensitiveDict(self.headers)
        content_length = int(headers['content-length'])
        content = self.rfile.read(content_length)
        self.handle_notification(headers, content)
        self.send_response(200)
        self.end_headers()

    # pylint: disable=no-self-use, missing-docstring
    def log_event(self, seq, service_id, timestamp):
        log.info(
            "Event %s received for %s service on thread %s at %s", seq,
            service_id, threading.current_thread(), timestamp)

    def log_message(self, fmt, *args):  # pylint: disable=arguments-differ
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
        """Start the server on `address`.
        Handling of requests is delegated to an instance of the
        `EventNotifyHandler` class.
        """
        server = EventServer(self.address, EventNotifyHandler)
        log.info("Event listener running on %s", server.server_address)
        # Listen for events until told to stop
        while not self.stop_flag.is_set():
            server.handle_request()

    def stop(self):
        """Stop the server.
        """
        self.stop_flag.set()


class EventListener(EventListenerBase):
    """The Event Listener.

    Runs an http server in a thread which is an endpoint for ``NOTIFY``
    requests from Sonos devices. Inherits from
    `soco.events_base.EventListenerBase`.
    """

    def __init__(self):
        super(EventListener, self).__init__()
        #: `EventServerThread`: thread on which to run.
        self._listener_thread = None

    def listen(self, ip_address):
        """Start the event listener listening on the local machine at
        port 1400 (default).

        Make sure that your firewall allows connections to this port.

        This method is called by `soco.events_base.EventListenerBase.start`

        Args:
            ip_address (str): The local network interface on which the server
                should start listening.
        Returns:
            int: `requested_port_number`. Included for
                compatibility with `soco.events_twisted.EventListener.listen`

        Note:
            The port on which the event listener listens is configurable.
            See `config.EVENT_LISTENER_PORT`
        """
        address = (ip_address, self.requested_port_number)
        self._listener_thread = EventServerThread(address)
        self._listener_thread.daemon = True
        self._listener_thread.start()
        return self.requested_port_number

    def stop_listening(self, address):
        """Stop the listener."""
        # Signal the thread to stop before handling the next request
        self._listener_thread.stop()
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


class Subscription(SubscriptionBase):
    """A class representing the subscription to a UPnP event.
    Inherits from `soco.events_base.SubscriptionBase`.
    """
    def __init__(self, service, event_queue=None):
        """
        Args:
            service (Service): The SoCo `Service` to which the subscription
                 should be made.
            event_queue (:class:`~queue.Queue`): A queue on which received
                events will be put. If not specified, a queue will be
                created and used.
        """
        super(Subscription, self).__init__(service, event_queue)
        # Used to keep track of the auto_renew thread
        self._auto_renew_thread = None
        self._auto_renew_thread_flag = threading.Event()
        # The SubscriptionsMap instance created when this module is imported.
        # This is referenced by soco.events_base.SubscriptionBase.
        self.subscriptions_map = subscriptions_map
        # The EventListener instance created when this module is imported.
        # This is referenced by soco.events_base.SubscriptionBase.
        self.event_listener = event_listener
        # Used to stop race conditions, as autorenewal may occur from a thread
        self._lock = threading.Lock()

    # pylint: disable=arguments-differ
    def subscribe(self, requested_timeout=None, auto_renew=False, strict=True):
        """Subscribe to the service.

        If requested_timeout is provided, a subscription valid for that number
        of seconds will be requested, but not guaranteed. Check
        `timeout` on return to find out what period of validity is
        actually allocated.

        This method calls `events_base.SubscriptionBase.subscribe`.

        Note:
            SoCo will try to unsubscribe any subscriptions which are still
            subscribed on program termination, but it is good practice for
            you to clean up by making sure that you call :meth:`unsubscribe`
            yourself.

        Args:
            requested_timeout(int, optional): The timeout to be requested.
            auto_renew (bool, optional): If `True`, renew the subscription
                automatically shortly before timeout. Default `False`.
            strict (bool, optional): If True and an Exception occurs during
                execution, the Exception will be raised or, if False, the
                Exception will be logged and the Subscription instance will be
                returned. Default `True`.

        Returns:
            `Subscription`: The Subscription instance.

        """
        subscribe = super(Subscription, self).subscribe
        return self._wrap(subscribe, strict, requested_timeout, auto_renew)

    def renew(self, requested_timeout=None, is_autorenew=False, strict=True):
        """renew(requested_timeout=None)
        Renew the event subscription.
        You should not try to renew a subscription which has been
        unsubscribed, or once it has expired.

        This method calls `events_base.SubscriptionBase.renew`.

        Args:
            requested_timeout (int, optional): The period for which a renewal
                request should be made. If None (the default), use the timeout
                requested on subscription.
            is_autorenew (bool, optional): Whether this is an autorenewal.
                Default 'False'.
            strict (bool, optional): If True and an Exception occurs during
                execution, the Exception will be raised or, if False, the
                Exception will be logged and the Subscription instance will be
                returned. Default `True`.

        Returns:
            `Subscription`: The Subscription instance.

        """
        renew = super(Subscription, self).renew
        return self._wrap(renew, strict, requested_timeout, is_autorenew)

    def unsubscribe(self, strict=True):
        """unsubscribe()
        Unsubscribe from the service's events.
        Once unsubscribed, a Subscription instance should not be reused

        This method calls `events_base.SubscriptionBase.unsubscribe`.

        Args:
            strict (bool, optional): If True and an Exception occurs during
                execution, the Exception will be raised or, if False, the
                Exception will be logged and the Subscription instance will be
                returned. Default `True`.

        Returns:
            `Subscription`: The Subscription instance.

        """
        unsubscribe = super(Subscription, self).unsubscribe
        return self._wrap(unsubscribe, strict)

    def _auto_renew_start(self, interval):
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
                    subscription.renew(is_autorenew=True, strict=False)

        auto_renew_thread = AutoRenewThread(
            interval, self._auto_renew_thread_flag, self)
        auto_renew_thread.start()

    def _auto_renew_cancel(self):
        """Cancels the auto_renew thread"""
        self._auto_renew_thread_flag.set()

    # pylint: disable=no-self-use, too-many-arguments
    def _request(self, method, url, headers, success):
        """Sends an HTTP request.

        Args:
            method (str): 'SUBSCRIBE' or 'UNSUBSCRIBE'.
            url (str): The full endpoint to which the request is being sent.
            headers (dict): A dict of headers, each key and each value being
                of type `str`.
            success (function): A function to be called if the
                request succeeds. The function will be called with a dict
                of response headers as its only parameter.

        """
        response = requests.request(method, url, headers=headers)
        response.raise_for_status()
        if success:
            success(response.headers)

    def _wrap(self, method, strict, *args, **kwargs):

        """This is a wrapper for `Subscription.subscribe`, `Subscription.renew`
        and `Subscription.unsubscribe` which:

            * Returns the`Subscription` instance.
            * If an Exception has occurred:

                * Cancels the Subscription (unless the Exception was caused by
                  a SoCoException upon subscribe).
                * On an autorenew, if the strict flag was set to False, calls
                  the optional self.auto_renew_fail method with the
                  Exception. This method needs to be threadsafe.
                * If the strict flag was set to True (the default), reraises
                  the Exception or, if the strict flag was set to False, logs
                  the Exception instead.

            * Calls the wrapped methods with a threading.Lock, to prevent race
              conditions (e.g. to prevent unsubscribe and autorenew being
              called simultaneously).

        """

        action = method.__name__

        # A lock is used, because autorenewal occurs in
        # a thread
        with self._lock:

            try:
                method(*args, **kwargs)

            except Exception as exc:  # pylint: disable=broad-except
                # If an Exception occurred during execution of subscribe,
                # renew or unsubscribe, set the cancel flag to True unless
                # the Exception was a SoCoException upon subscribe
                cancel = action == 'renew' or not \
                    isinstance(exc, SoCoException)

                if cancel:
                    # If the cancel flag was set to true, cancel the
                    # subscription with an explanation.
                    msg = "An Exception occurred. Subscription to" +\
                        " {}, sid: {} has been cancelled".format(
                            self.service.base_url +
                            self.service.event_subscription_url,
                            self.sid)
                    self._cancel_subscription(msg)
                # If we're not being strict, log the Exception
                if not strict:
                    msg = "Exception received in Subscription." +\
                        "{} for Subscription to:\n{}, sid: {}".format(
                            action,
                            self.service.base_url +
                            self.service.event_subscription_url,
                            self.sid)
                    log.exception(msg)
                    # If we're not being strict upon a renewal
                    # (e.g. an autorenewal) call the optional
                    # self.auto_renew_fail method, if it has been set
                    if action == 'renew' and self.auto_renew_fail is not None:
                        if hasattr(self.auto_renew_fail, '__call__'):
                            # pylint: disable=not-callable
                            self.auto_renew_fail(exc)

                # If we're being strict, reraise the Exception
                else:
                    raise  # pylint: disable=raising-bad-type

            else:
                # Return the Subscription to the function that
                # called subscribe, renew or unsubscribe (unless an
                # Exception occurred and it was reraised above)
                return self  # pylint: disable=lost-exception


subscriptions_map = SubscriptionsMap()  # pylint: disable=C0103
event_listener = EventListener()  # pylint: disable=C0103
