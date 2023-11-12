# pylint: disable=not-context-manager,import-error,wrong-import-position

# NOTE: The pylint not-content-manager warning is disabled pending the fix of
# a bug in pylint. See https://github.com/PyCQA/pylint/issues/782

# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance


"""Classes to handle Sonos UPnP Events and Subscriptions.

The `Subscription` class from this module will be used in
:py:mod:`soco.services` if `config.EVENTS_MODULE` is set
to point to this module.

Example:

    Run this code, and change your volume, tracks etc::

        from __future__ import print_function
        import logging
        logging.basicConfig()
        import soco
        from pprint import pprint

        from soco import events_twisted
        soco.config.EVENTS_MODULE = events_twisted
        from twisted.internet import reactor

        def print_event(event):
            try:
                pprint (event.variables)
            except Exception as e:
                pprint ('There was an error in print_event:', e)

        def main():
            # pick a device at random and use it to get
            # the group coordinator
            device = soco.discover().pop().group.coordinator
            print (device.player_name)
            sub = device.renderingControl.subscribe().subscription
            sub2 = device.avTransport.subscribe().subscription
            sub.callback = print_event
            sub2.callback = print_event

            def before_shutdown():
                sub.unsubscribe()
                sub2.unsubscribe()
                events_twisted.event_listener.stop()

            reactor.addSystemEventTrigger(
                'before', 'shutdown', before_shutdown)

        if __name__=='__main__':
            reactor.callWhenRunning(main)
            reactor.run()

.. _Deferred: https://twistedmatrix.com/documents/current/api/\
twisted.internet.defer.Deferred.html
.. _Failure: https://twistedmatrix.com/documents/current/api/\
twisted.python.failure.Failure.html

"""


import sys
import logging

# Hack to make docs build without twisted installed
if "sphinx" in sys.modules:

    class Resource:  # pylint: disable=no-init
        """Fake Resource class to use when building docs"""

else:
    from twisted.internet import reactor
    from twisted.web.server import Site
    from twisted.web.resource import Resource
    import twisted.internet.error
    from twisted.internet import task, defer
    from twisted.python.failure import Failure
    from twisted.web.client import Agent, BrowserLikeRedirectAgent
    from twisted.web.http_headers import Headers

# Event is imported for compatibility with events.py
# pylint: disable=unused-import
from .events_base import Event  # noqa: F401

from .events_base import (  # noqa: E402
    EventNotifyHandlerBase,
    EventListenerBase,
    SubscriptionBase,
    SubscriptionsMap,
)

from .exceptions import SoCoException  # noqa: E402

log = logging.getLogger(__name__)  # pylint: disable=C0103


class EventNotifyHandler(Resource, EventNotifyHandlerBase):
    """Handles HTTP ``NOTIFY`` Verbs sent to the listener server.
    Inherits from `soco.events_base.EventNotifyHandlerBase`.
    """

    isLeaf = True

    def __init__(self):
        super().__init__()
        # The SubscriptionsMapTwisted instance created when this module is
        # imported. This is referenced by
        # soco.events_base.EventNotifyHandlerBase.
        self.subscriptions_map = subscriptions_map

    def render_NOTIFY(self, request):  # pylint: disable=invalid-name
        """Serve a ``NOTIFY`` request by calling `handle_notification`
        with the headers and content.
        """
        headers = {}
        for header in request.requestHeaders.getAllRawHeaders():
            decoded_key = header[0].decode("utf8").lower()
            decoded_header = header[1][0].decode("utf8")
            headers[decoded_key] = decoded_header
        content = request.content.read()
        self.handle_notification(headers, content)
        return b"OK"

    # pylint: disable=no-self-use, missing-docstring
    def log_event(self, seq, service_id, timestamp):
        log.debug("Event %s received for %s service at %s", seq, service_id, timestamp)


class EventListener(EventListenerBase):
    """The Event Listener.

    Runs an http server which is an endpoint for ``NOTIFY``
    requests from Sonos devices. Inherits from
    `soco.events_base.EventListenerBase`.
    """

    def __init__(self):
        super().__init__()
        #:  :py:class:`twisted.internet.tcp.Port`: set at `listen`
        self.port = None

    def listen(self, ip_address):
        """Start the event listener listening on the local machine at
        port 1400 (default). If this port is unavailable, the
        listener will attempt to listen on the next available port,
        within a range of 100.

        Make sure that your firewall allows connections to this port.

        This method is called by `soco.events_base.EventListenerBase.start`

        Handling of requests is delegated to an instance of the
        `EventNotifyHandler` class.

        Args:
            ip_address (str): The local network interface on which the server
                should start listening.
        Returns:
            int: The port on which the server is listening.

        Note:
            The port on which the event listener listens is configurable.
            See `config.EVENT_LISTENER_PORT`
        """
        factory = Site(EventNotifyHandler())
        for port_number in range(
            self.requested_port_number, self.requested_port_number + 100
        ):
            try:
                if port_number > self.requested_port_number:
                    log.debug("Trying next port (%d)", port_number)
                # pylint: disable=no-member
                self.port = reactor.listenTCP(
                    port_number, factory, interface=ip_address
                )
                break
            # pylint: disable=invalid-name,used-before-assignment
            except twisted.internet.error.CannotListenError as e:
                log.warning(e)
                continue

        if self.port:
            log.debug("Event listener running on %s", (ip_address, self.port.port))
            return self.port.port
        else:
            return None

    # pylint: disable=unused-argument
    def stop_listening(self, address):
        """Stop the listener."""
        port, self.port = self.port, None
        port.stopListening()


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
        super().__init__(service, event_queue)
        #: :py:obj:`function`: callback function to be called whenever an
        #: `Event` is received. If it is set and is callable, the callback
        #: function will be called with the `Event` as the only parameter and
        #: the Subscription's event queue won't be used.
        self.callback = None
        # The SubscriptionsMapTwisted instance created when this module is
        # imported. This is referenced by soco.events_base.SubscriptionBase.
        self.subscriptions_map = subscriptions_map
        # The EventListener instance created when this module is imported.
        # This is referenced by soco.events_base.SubscriptionBase.
        self.event_listener = event_listener
        # Used to keep track of the auto_renew loop
        self._auto_renew_loop = None
        # Used to serialise calls to subscribe, renew and unsubscribe
        self._queue = []

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
                execution, the returned Deferred_ will fail with a Failure_
                which will be passed to the applicable errback (if any has
                been set by the calling code) or, if False, the Failure will
                be logged and the Subscription instance will be passed to
                the applicable callback (if any has
                been set by the calling code). Default `True`.

        Returns:
            Deferred_: A Deferred_ the result of which will be the
            Subscription instance and the subscription property of which
            will point to the Subscription instance.

        """
        subscribe = super().subscribe
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
                Default `False`.
            strict (bool, optional): If True and an Exception occurs during
                execution, the returned Deferred_ will fail with a Failure_
                which will be passed to the applicable errback (if any has
                been set by the calling code) or, if False, the Failure will
                be logged and the Subscription instance will be passed to
                the applicable callback (if any has
                been set by the calling code). Default `True`.

        Returns:
            Deferred_: A Deferred_ the result of which will be the
            Subscription instance and the subscription property of which
            will point to the Subscription instance.

        """
        renew = super().renew
        return self._wrap(renew, strict, requested_timeout, is_autorenew)

    def unsubscribe(self, strict=True):
        """unsubscribe()
        Unsubscribe from the service's events.
        Once unsubscribed, a Subscription instance should not be reused

        This method calls `events_base.SubscriptionBase.unsubscribe`.

        Args:
            strict (bool, optional): If True and an Exception occurs during
                execution, the returned Deferred_ will fail with a Failure_
                which will be passed to the applicable errback (if any has
                been set by the calling code) or, if False, the Failure will
                be logged and the Subscription instance will be passed to
                the applicable callback (if any has
                been set by the calling code). Default `True`.

        Returns:
            Deferred_: A Deferred_ the result of which will be the
            Subscription instance and the subscription property of which
            will point to the Subscription instance.
        """
        unsubscribe = super().unsubscribe
        return self._wrap(unsubscribe, strict)

    def _auto_renew_start(self, interval):
        """Starts the auto_renew loop."""
        self._auto_renew_loop = task.LoopingCall(
            self.renew, is_autorenew=True, strict=False
        )
        # False means wait for the interval to elapse, rather than fire at once
        self._auto_renew_loop.start(interval, False)

    def _auto_renew_cancel(self):
        """Cancels the auto_renew loop"""
        if self._auto_renew_loop:
            self._auto_renew_loop.stop()
            self._auto_renew_loop = None

    # pylint: disable=no-self-use
    def _request(self, method, url, headers, success, unconditional=None):
        """Sends an HTTP request.

        Args:
            method (str): 'SUBSCRIBE' or 'UNSUBSCRIBE'.
            url (str): The full endpoint to which the request is being sent.
            headers (dict): A dict of headers, each key and each value being
                of type `str`.
            success (function): A function to be called if the
                request succeeds. The function will be called with a dict
                of response headers as its only parameter.
            unconditional (function): An optional function to be called after
                the request is complete, regardless of its success. Takes
                no parameters.

        """
        agent = BrowserLikeRedirectAgent(Agent(reactor))

        if headers:
            for k in list(headers.keys()):
                header = headers[k]
                del headers[k]
                if isinstance(header, (list,)):
                    header = header[0]
                if not isinstance(header, (bytes, bytearray)):
                    header = header.encode("latin-1")
                    k = k.encode("latin-1")
                headers[k] = [header]

        args = (method.encode("latin-1"), url.encode("latin-1"), Headers(headers))
        d = agent.request(*args)  # pylint: disable=invalid-name

        def on_success(response):  # pylint: disable=missing-docstring
            response_headers = {}
            for header in response.headers.getAllRawHeaders():
                decoded_key = header[0].decode("utf8").lower()
                decoded_header = header[1][0].decode("utf8")
                response_headers[decoded_key] = decoded_header
            success(response_headers)
            return self

        d.addCallback(on_success)
        if unconditional:
            d.addBoth(unconditional)
        return d

    def _wrap(self, method, strict, *args, **kwargs):
        """This is a wrapper for `Subscription.subscribe`, `Subscription.renew`
        and `Subscription.unsubscribe` which:

            * Returns a deferred, the result of which will be the`Subscription`
              instance.
            * Sets deferred.subscription to point to the `Subscription`
              instance so a calling function can access the Subscription
              instance immediately without registering a Callback and waiting
              for it to fire.
            * Converts an Exception into a twisted.python.failure.Failure.
            * If a Failure (including an Exception converted into a Failure)
              has occurred:

                * Cancels the Subscription (unless the Failure was caused by a
                  SoCoException upon subscribe).
                * On an autorenew, if the strict flag was set to False, calls
                  the optional self.auto_renew_fail method with the
                  Failure.
                * If the strict flag was set to True (the default), passes the
                  Failure to the next Errback for handling or, if the strict
                  flag was set to False, logs the Failure instead.

            * Calls the `subscribing` and `finished_subscribing` methods of
              self.subscriptions_map, so that `count` property of
              self.subscriptions_map includes pending subscriptions.
            * Serialises calls to the wrapped methods, so that, for example, a
              call to unsubscribe will not commence until a call to subscribe
              has completed.

        """
        action = method.__name__

        # pylint: disable=unused-argument
        def execute(result, method, *args, **kwargs):
            """Execute method"""
            # Increment the counter of pending calls to Subscription.subscribe
            # if method is subscribe
            if method.__name__ == "subscribe":
                self.subscriptions_map.subscribing()

            # Execute method
            return method(*args, **kwargs)

        def callnext():
            """Call the next deferred in the queue."""
            # If there is another deferred in the queue,
            # call it
            if self._queue:
                d = self._queue[0]  # pylint: disable=invalid-name
                d.callback(None)

        def handle_outcome(outcome):
            """A callback / errback to handle the outcome ofmethod,
            after it has been executed
            """
            # We start by assuming no Failure occurred
            failure = None

            if isinstance(outcome, Failure):
                failure = outcome
                # If a Failure or Exception occurred during execution of
                # subscribe, renew or unsubscribe, cancel it unless the
                # Failure or Exception was a SoCoException upon subscribe
                if failure.type != SoCoException or action == "renew":
                    msg = (
                        "An Exception occurred. Subscription to"
                        + " {}, sid: {} has been cancelled".format(
                            self.service.base_url + self.service.event_subscription_url,
                            self.sid,
                        )
                    )
                    self._cancel_subscription(msg)
                # If we're not being strict, log the Failure
                if not strict:
                    msg = (
                        "Failure received in Subscription"
                        + ".{} for Subscription to:\n{}, sid: {}: {}".format(
                            action,
                            self.service.base_url + self.service.event_subscription_url,
                            self.sid,
                            str(failure),
                        )
                    )
                    log.exception(msg)
                    # If we're not being strict upon a renewal
                    # (e.g. an autorenewal) call the optional
                    # self.auto_renew_fail method, if it has been set
                    if action == "renew":
                        if self.auto_renew_fail:
                            if hasattr(self.auto_renew_fail, "__call__"):
                                # pylint: disable=not-callable
                                self.auto_renew_fail(failure)

            # Decrement the counter of pending calls to Subscription.subscribe
            # if completed action was subscribe
            if action == "subscribe":
                self.subscriptions_map.finished_subscribing()

            # Remove the previous deferred from the queue
            self._queue.pop(0)

            # And call the next deferred in the queue
            callnext()

            # If a Failure occurred and we're in strict mode, reraise it
            if failure and strict:
                failure.trap()

        # Create a deferred
        d = defer.Deferred()  # pylint: disable=invalid-name
        # Set its subscription property to refer to this Subscription
        d.subscription = self
        # Set the deferred to execute method, when the
        # deferred is called
        d.addCallback(execute, method, *args, **kwargs)
        # Add handle_outcome as both a callback and errback
        d.addBoth(handle_outcome)
        # Add the deferred to the queue
        self._queue.append(d)
        # If this is the only deferred in the queue,
        # call it
        if len(self._queue) == 1:
            callnext()
        # Return the deferred
        return d


class SubscriptionsMapTwisted(SubscriptionsMap):
    """Maintains a mapping of sids to `soco.events_twisted.Subscription`
    instances. Registers each subscription to be unsubscribed at exit.

    Inherits from `soco.events_base.SubscriptionsMap`.
    """

    def __init__(self):
        super().__init__()
        # A counter of calls to Subscription.subscribe
        # that have started but not completed. This is
        # to prevent the event listener from being stopped prematurely
        self._pending = 0

    def register(self, subscription):
        """Register a subscription by updating local mapping of sid to
        subscription and registering it to be unsubscribed at exit.

        Args:
            subscription(`soco.events_twisted.Subscription`): the subscription
                to be registered.

        """

        # Add the subscription to the local dict of subscriptions so it
        # can be looked up by sid
        self.subscriptions[subscription.sid] = subscription
        # Register subscription to be unsubscribed at exit if still alive
        # pylint: disable=no-member
        reactor.addSystemEventTrigger("before", "shutdown", subscription.unsubscribe)

    def subscribing(self):
        """Called when the `Subscription.subscribe` method
        commences execution.
        """
        # Increment the counter
        self._pending += 1

    def finished_subscribing(self):
        """Called when the `Subscription.subscribe` method
        completes execution.
        """
        # Decrement the counter
        self._pending -= 1

    @property
    def count(self):
        """
        `int`: The number of active or pending subscriptions.
        """
        return len(self.subscriptions) + self._pending


subscriptions_map = SubscriptionsMapTwisted()  # pylint: disable=C0103
event_listener = EventListener()  # pylint: disable=C0103
