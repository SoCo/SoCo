"""Classes to handle Sonos UPnP Events and Subscriptions using asyncio.

The `Subscription` class from this module will be used in
:py:mod:`soco.services` if `config.EVENTS_MODULE` is set
to point to this module.

Example:

    Run this code, and change your volume, tracks etc::

        import logging

        logging.basicConfig()
        import soco
        import asyncio
        from pprint import pprint

        from soco import events_asyncio

        soco.config.EVENTS_MODULE = events_asyncio


        def print_event(event):
            try:
                pprint(event.variables)
            except Exception as e:
                print("There was an error in print_event:", e)


        def _get_device():
            device = soco.discover().pop().group.coordinator
            print(device.player_name)
            return device


        async def main():
            # pick a device at random and use it to get
            # the group coordinator
            loop = asyncio.get_event_loop()
            device = await loop.run_in_executor(None, _get_device)
            sub = await device.renderingControl.subscribe()
            sub2 = await device.avTransport.subscribe()
            sub.callback = print_event
            sub2.callback = print_event

            async def before_shutdown():
                await sub.unsubscribe()
                await sub2.unsubscribe()
                await events_asyncio.event_listener.async_stop()

            await asyncio.sleep(1)
            print("Renewing subscription..")
            await sub.renew()

            await asyncio.sleep(100)
            await before_shutdown()


        if __name__ == "__main__":
            asyncio.run(main())

"""

import logging
import socket
import sys
import time
import asyncio

try:
    from aiohttp import ClientSession, ClientTimeout, web
except ImportError as error:
    print("""ImportError: {}:
    Use of the SoCo events_asyncio module requires the 'aiohttp'
    package and its dependencies to be installed. aiohttp is not
    installed with SoCo by default due to potential issues installing
    the dependencies 'multidict' and 'yarl' on some platforms.
    See: https://github.com/SoCo/SoCo/issues/819""".format(error))
    sys.exit(1)

# Event is imported for compatibility with events.py
# pylint: disable=unused-import
from .events_base import Event  # noqa: F401

from .events_base import (  # noqa: E402
    get_listen_ip,
    parse_event_xml,
    EventNotifyHandlerBase,
    EventListenerBase,
    SubscriptionBase,
    SubscriptionsMap,
)

from .exceptions import SoCoException  # noqa: E402

log = logging.getLogger(__name__)  # pylint: disable=C0103


class EventNotifyHandler(EventNotifyHandlerBase):
    """Handles HTTP ``NOTIFY`` Verbs sent to the listener server.
    Inherits from `soco.events_base.EventNotifyHandlerBase`.
    """

    def __init__(self):
        super().__init__()
        # The SubscriptionsMapAio instance created when this module is
        # imported. This is referenced by
        # soco.events_base.EventNotifyHandlerBase.
        self.subscriptions_map = subscriptions_map

    async def notify(self, request):
        """Serve a ``NOTIFY`` request by calling `handle_notification`
        with the headers and content.
        """
        content = await request.text()
        seq = request.headers["seq"]  # Event sequence number
        sid = request.headers["sid"]  # Event Subscription Identifier
        # find the relevant service from the sid
        # pylint: disable=no-member
        subscription = self.subscriptions_map.get_subscription(sid)
        # It might have been removed by another thread
        if subscription:
            timestamp = time.time()
            service = subscription.service
            self.log_event(seq, service.service_id, timestamp)
            log.debug("Event content: %s", content)
            if "x-sonos-http" in content:
                # parse_event_xml will generate I/O if
                # x-sonos-http is in the content
                variables = await asyncio.get_event_loop().run_in_executor(
                    None, parse_event_xml, content
                )
            else:
                variables = parse_event_xml(content)

            if "zone_group_state" in variables:
                # Pass ZGS payload to associated SoCo instance to update
                # attributes. Keeps cache warm and avoids network calls.
                service.soco.zone_group_state.process_payload(
                    payload=variables["zone_group_state"],
                    source="event",
                    source_ip=service.soco.ip_address,
                )

            # Build the Event object
            event = Event(sid, seq, service, timestamp, variables)
            # pass the event details on to the service so it can update
            # its cache.
            # pylint: disable=protected-access
            service._update_cache_on_event(event)
            # Pass the event on for handling
            subscription.send_event(event)
        else:
            log.debug("No service registered for %s", sid)

        return web.Response(text="OK", status=200)

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
        self.sock = None
        self.ip_address = None
        self.port = None
        self.runner = None
        self.site = None
        self.session = None
        self.start_lock = None
        # async_stop is serialized via stop_lock so overlapping callers
        # don't double-close the same resources.
        self.stop_lock = None
        # stop_listening() schedules a deferred teardown via this task.
        # A resubscribe within the grace window cancels the task and
        # reuses the existing HTTP server, eliminating the
        # teardown/rebuild churn (and FD races) on every renew cycle.
        self._stop_grace_task = None
        # Grace window (seconds) between stop_listening() being called
        # and the deferred async_stop() actually running. Intentionally
        # an instance attribute so consumers and tests can tune it
        # (e.g. shorten for fast unit tests, lengthen for noisy
        # resubscribe patterns). 5 s is the default; values < 0 are
        # treated as "stop immediately on next event-loop tick".
        self._stop_grace_seconds = 5.0

    def start(self, any_zone):
        """A stub since the first subscribe calls async_start."""
        return

    def listen(self, ip_address):
        """A stub since async_listen is used."""
        return

    async def async_start(self, any_zone):
        """Start the event listener listening on the local machine under the lock.

        Args:
            any_zone (SoCo): Any Sonos device on the network. It does not
                matter which device. It is used only to find a local IP
                address reachable by the Sonos net.

        """
        if not self.start_lock:
            self.start_lock = asyncio.Lock()
        async with self.start_lock:
            # If a deferred stop is pending from a recent stop_listening(),
            # cancel it — the caller wants the listener up. If the runtime
            # resources are still alive (the grace window has not yet
            # expired), the listener can simply resume.
            if self._stop_grace_task is not None and not self._stop_grace_task.done():
                self._stop_grace_task.cancel()
                self._stop_grace_task = None
                if (
                    self.site is not None
                    and self.sock is not None
                    and self.runner is not None
                    and self.session is not None
                ):
                    self.is_running = True
                    log.debug("Event Listener resumed (deferred stop cancelled)")
                    return
            if self.is_running:
                return
            # Use configured IP address if there is one, else detect
            # automatically.
            ip_address = get_listen_ip(any_zone.ip_address)
            if not ip_address:
                log.exception("Could not start Event Listener: check network.")
                # Otherwise, no point trying to start server
                return
            port = await self.async_listen(ip_address)
            if not port:
                return
            self.address = (ip_address, port)
            client_timeout = ClientTimeout(total=10)
            self.session = ClientSession(raise_for_status=True, timeout=client_timeout)
            self.is_running = True
            log.debug("Event Listener started")

    async def async_listen(self, ip_address):
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
        for port_number in range(
            self.requested_port_number, self.requested_port_number + 100
        ):
            try:
                if port_number > self.requested_port_number:
                    log.debug("Trying next port (%d)", port_number)
                # pylint: disable=no-member
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind((ip_address, port_number))
                sock.listen(200)
                self.sock = sock
                self.port = port_number
                break
            # pylint: disable=invalid-name
            except OSError as e:
                log.warning("Could not bind to %s:%s: %s", ip_address, port_number, e)
                continue

        if not self.port:
            return None

        self.ip_address = ip_address
        await self._async_start()
        return self.port

    async def _async_start(self):
        """Start the site."""
        handler = EventNotifyHandler()
        app = web.Application()
        app.add_routes([web.route("notify", "", handler.notify)])
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.SockSite(self.runner, self.sock)
        await self.site.start()
        log.debug("Event listener running on %s", (self.ip_address, self.port))

    async def async_stop(self):
        """Stop the listener immediately. Idempotent and concurrency-safe.

        This is the prompt-shutdown path: resources are closed before the
        coroutine returns. Callers that want a deterministic teardown at
        process exit should ``await event_listener.async_stop()``
        directly; ``stop_listening()`` defers teardown by
        ``_stop_grace_seconds`` (default 5 s) to support
        unsubscribe→resubscribe reuse.

        Snapshots the runtime resources locally and clears the instance
        attributes inside ``stop_lock``, then closes the snapshots
        outside the lock. This way a concurrent ``async_start`` never
        observes a half-torn-down listener, and a second overlapping
        ``async_stop`` call sees the cleared attrs and returns early.
        """
        if not self.stop_lock:
            self.stop_lock = asyncio.Lock()
        async with self.stop_lock:
            if (
                not self.is_running
                and self.site is None
                and self.runner is None
                and self.session is None
                and self.sock is None
            ):
                # Already stopped (or never started) — nothing to do.
                return
            self.is_running = False
            site, self.site = self.site, None
            runner, self.runner = self.runner, None
            session, self.session = self.session, None
            sock, self.sock = self.sock, None
            self.port = None
            self.ip_address = None

        # Tear down outside the lock; tolerate already-closed state.
        if site is not None:
            try:
                await site.stop()
            except (ValueError, OSError) as exc:
                # aiohttp's SockSite.stop() ultimately calls
                # loop._stop_serving(sock), which raises ValueError on a
                # closed fd. Tolerate and continue cleanup.
                log.debug("site.stop() during async_stop: %r", exc)
        if runner is not None:
            try:
                await runner.cleanup()
            except Exception as exc:  # pylint: disable=broad-except
                log.debug("runner.cleanup() during async_stop: %r", exc)
        if session is not None:
            try:
                await session.close()
            except Exception as exc:  # pylint: disable=broad-except
                log.debug("session.close() during async_stop: %r", exc)
        if sock is not None:
            try:
                sock.close()
            except OSError as exc:
                log.debug("sock.close() during async_stop: %r", exc)

    async def _deferred_stop(self):
        """Sleep the grace window; stop only if no resubscribe arrived."""
        await asyncio.sleep(self._stop_grace_seconds)
        if subscriptions_map.count == 0:
            await self.async_stop()
        else:
            log.debug(
                "deferred stop aborted: %d subscription(s) appeared during grace",
                subscriptions_map.count,
            )

    # pylint: disable=unused-argument
    def stop_listening(self, address):
        """Stop the listener after a short grace window.

        Called by ``EventListenerBase.stop()`` when the last subscription
        is removed. Schedules teardown via ``_deferred_stop`` rather than
        tearing down immediately: a resubscribe inside the grace window
        (``_stop_grace_seconds``, default 5 s) cancels the pending stop,
        so the underlying HTTP server stays up across the
        unsubscribe→resubscribe cycle. Eliminates teardown/rebuild churn
        (and the FD races that follow) on every renew.

        Behaviour notes for callers:

        * Resources are **not** released by the time this method returns
          — the deferred task runs ``_stop_grace_seconds`` later.
        * Consumers that subscribe once and exit (no resubscribe) will
          see resources released ~``_stop_grace_seconds`` after the last
          ``unsubscribe()``. For deterministic prompt shutdown at process
          exit, call ``await event_listener.async_stop()`` directly.
        * Each call replaces any prior pending stop with a fresh timer,
          so rapid consecutive ``stop_listening()`` calls coalesce into
          a single deferred teardown.
        """
        if self._stop_grace_task is not None and not self._stop_grace_task.done():
            # Replace any prior pending stop with a fresh timer.
            self._stop_grace_task.cancel()
        self._stop_grace_task = asyncio.ensure_future(self._deferred_stop())

        def _swallow_exception(t):
            if t.cancelled():
                return
            try:
                t.result()
            except Exception as exc:  # pylint: disable=broad-except
                log.debug("async_stop scheduled by stop_listening raised: %r", exc)

        self._stop_grace_task.add_done_callback(_swallow_exception)


class Subscription(SubscriptionBase):
    """A class representing the subscription to a UPnP event.
    Inherits from `soco.events_base.SubscriptionBase`.
    """

    def __init__(self, service, callback=None):
        """
        Args:
            service (Service): The SoCo `Service` to which the subscription
                 should be made.
            event_queue (:class:`~queue.Queue`): A queue on which received
                events will be put. If not specified, a queue will be
                created and used.

        """
        super().__init__(service, None)
        #: :py:obj:`function`: callback function to be called whenever an
        #: `Event` is received. If it is set and is callable, the callback
        #: function will be called with the `Event` as the only parameter and
        #: the Subscription's event queue won't be used.
        self.callback = callback
        # The SubscriptionsMapAio instance created when this module is
        # imported. This is referenced by soco.events_base.SubscriptionBase.
        self.subscriptions_map = subscriptions_map
        # The EventListener instance created when this module is imported.
        # This is referenced by soco.events_base.SubscriptionBase.
        self.event_listener = event_listener
        # Used to keep track of the auto_renew loop
        self._auto_renew_task = None

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
        self.subscriptions_map.subscribing()
        future = asyncio.Future()
        subscribe = super().subscribe

        async def _async_wrap_subscribe():
            try:
                if not self.event_listener.is_running:
                    await self.event_listener.async_start(self.service.soco)
                await subscribe(requested_timeout, auto_renew)
                future.set_result(self)
            except SoCoException as ex:
                future.set_exception(ex)
            except Exception as exc:  # pylint: disable=broad-except
                self._cancel_subscription(exc)
                if strict:
                    future.set_exception(exc)
                else:
                    self._log_exception(exc)
                    future.set_result(self)
            finally:
                self.subscriptions_map.finished_subscribing()

        asyncio.ensure_future(_async_wrap_subscribe())
        return future

    def _log_exception(self, exc):
        """Log an exception during subscription."""
        msg = (
            f"An Exception occurred: {exc}."
            + " Subscription to {},".format(
                self.service.base_url + self.service.event_subscription_url
            )
            + f" sid: {self.sid} has been cancelled"
        )
        log.exception(msg)

    async def renew(
        self, requested_timeout=None, is_autorenew=False, strict=True
    ):  # pylint: disable=invalid-overridden-method
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
                execution, the Exception will be raised or, if False, the
                Exception will be logged and the Subscription instance will be
                returned. Default `True`.

        Returns:
            `Subscription`: The Subscription instance.

        """
        try:
            return await super().renew(requested_timeout, is_autorenew)
        except Exception as exc:  # pylint: disable=broad-except
            self._cancel_subscription(exc)
            if self.auto_renew_fail is not None and hasattr(
                self.auto_renew_fail, "__call__"
            ):
                # pylint: disable=not-callable
                self.auto_renew_fail(exc)
            else:
                self._log_exception(exc)
            if strict:
                raise
            return self

    async def unsubscribe(
        self, strict=True
    ):  # pylint: disable=invalid-overridden-method
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
        try:
            unsub = super().unsubscribe()
            if unsub is None:
                return
            await unsub
        except Exception as exc:  # pylint: disable=broad-except
            self._cancel_subscription(exc)
            if strict:
                raise
            self._log_exception(exc)
            return self

    def _auto_renew_start(self, interval):
        """Starts the auto_renew loop."""
        self._auto_renew_task = asyncio.get_event_loop().call_later(
            interval, self._auto_renew_run, interval
        )

    def _auto_renew_run(self, interval):
        asyncio.ensure_future(self.renew(is_autorenew=True, strict=False))
        self._auto_renew_start(interval)

    def _auto_renew_cancel(self):
        """Cancels the auto_renew loop"""
        if self._auto_renew_task:
            self._auto_renew_task.cancel()
            self._auto_renew_task = None

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

        async def _async_make_request():
            response = await self.event_listener.session.request(
                method, url, headers=headers
            )
            if response.ok:
                success(response.headers)
            if unconditional:
                unconditional()

        return _async_make_request()


class nullcontext:  # pylint: disable=invalid-name
    """Context manager that does no additional processing.

    Backport from python 3.7+ for older pythons.
    """

    def __init__(self, enter_result=None):
        self.enter_result = enter_result

    def __enter__(self):
        return self.enter_result

    def __exit__(self, *excinfo):
        pass


class SubscriptionsMapAio(SubscriptionsMap):
    """Maintains a mapping of sids to `soco.events_asyncio.Subscription`
    instances. Registers each subscription to be unsubscribed at exit.

    Inherits from `soco.events_base.SubscriptionsMap`.
    """

    def __init__(self):
        super().__init__()
        # A counter of calls to Subscription.subscribe
        # that have started but not completed. This is
        # to prevent the event listener from being stopped prematurely
        self._pending = 0
        self.subscriptions_lock = nullcontext()

    def register(self, subscription):
        """Register a subscription by updating local mapping of sid to
        subscription and registering it to be unsubscribed at exit.

        Args:
            subscription(`soco.events_asyncio.Subscription`): the subscription
                to be registered.

        """

        # Add the subscription to the local dict of subscriptions so it
        # can be looked up by sid
        self.subscriptions[subscription.sid] = subscription

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


subscriptions_map = SubscriptionsMapAio()  # pylint: disable=C0103
event_listener = EventListener()  # pylint: disable=C0103
