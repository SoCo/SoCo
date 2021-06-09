# pylint: disable=not-context-manager

# NOTE: The pylint not-content-manager warning is disabled pending the fix of
# a bug in pylint. See https://github.com/PyCQA/pylint/issues/782


"""Base classes used by :py:mod:`soco.events` and
:py:mod:`soco.events_twisted`."""


import atexit
import logging
import socket
import time
import threading
import weakref
from queue import Queue

from . import config
from .data_structures_entry import from_didl_string
from .exceptions import SoCoException, SoCoFault, EventParseException
from .utils import camel_to_underscore
from .xml import XML

log = logging.getLogger(__name__)  # pylint: disable=C0103


# pylint: disable=too-many-branches
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
        * a `SoCoFault` (if a variable contains illegal metadata)
    """

    result = {}
    tree = XML.fromstring(xml_event)
    # property values are just under the propertyset, which
    # uses this namespace
    properties = tree.findall("{urn:schemas-upnp-org:event-1-0}property")
    for prop in properties:  # pylint: disable=too-many-nested-blocks
        for variable in prop:
            # Special handling for a LastChange event specially. For details on
            # LastChange events, see
            # http://upnp.org/specs/av/UPnP-av-RenderingControl-v1-Service.pdf
            # and http://upnp.org/specs/av/UPnP-av-AVTransport-v1-Service.pdf
            if variable.tag == "LastChange":
                last_change_tree = XML.fromstring(variable.text.encode("utf-8"))
                # We assume there is only one InstanceID tag. This is true for
                # Sonos, as far as we know.
                # InstanceID can be in one of two namespaces, depending on
                # whether we are looking at an avTransport event, a
                # renderingControl event, or a Queue event
                # (there, it is named QueueID)
                instance = last_change_tree.find(
                    "{urn:schemas-upnp-org:metadata-1-0/AVT/}InstanceID"
                )
                if instance is None:
                    instance = last_change_tree.find(
                        "{urn:schemas-upnp-org:metadata-1-0/RCS/}InstanceID"
                    )
                if instance is None:
                    instance = last_change_tree.find(
                        "{urn:schemas-sonos-com:metadata-1-0/Queue/}QueueID"
                    )
                # Look at each variable within the LastChange event
                for last_change_var in instance:
                    tag = last_change_var.tag
                    # Remove any namespaces from the tags
                    if tag.startswith("{"):
                        tag = tag.split("}", 1)[1]
                    # Un-camel case it
                    tag = camel_to_underscore(tag)
                    # Now extract the relevant value for the variable.
                    # The UPnP specs suggest that the value of any variable
                    # evented via a LastChange Event will be in the 'val'
                    # attribute, but audio related variables may also have a
                    # 'channel' attribute. In addition, it seems that Sonos
                    # sometimes uses a text value instead: see
                    # http://forums.sonos.com/showthread.php?t=34663
                    value = last_change_var.get("val")
                    if value is None:
                        value = last_change_var.text
                    # If DIDL metadata is returned, convert it to a music
                    # library data structure
                    if value.startswith("<DIDL-Lite"):
                        # Wrap any parsing exception in a SoCoFault, so the
                        # user can handle it
                        try:
                            value = from_didl_string(value)[0]
                        except SoCoException as original_exception:
                            log.debug(
                                "Event contains illegal metadata"
                                "for '%s'.\n"
                                "Error message: '%s'\n"
                                "The result will be a SoCoFault.",
                                tag,
                                str(original_exception),
                            )
                            event_parse_exception = EventParseException(
                                tag, value, original_exception
                            )
                            value = SoCoFault(event_parse_exception)
                    channel = last_change_var.get("channel")
                    if channel is not None:
                        if result.get(tag) is None:
                            result[tag] = {}
                        result[tag][channel] = value
                    else:
                        result[tag] = value
            else:
                result[camel_to_underscore(variable.tag)] = variable.text
    return result


class Event:
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
            evented variables. Defaults to `None`. The values may be
            `SoCoFault` objects if the metadata could not be parsed.

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
        self.__dict__["sid"] = sid
        self.__dict__["seq"] = seq
        self.__dict__["timestamp"] = timestamp
        self.__dict__["service"] = service
        self.__dict__["variables"] = variables if variables is not None else {}

    def __getattr__(self, name):
        if name in self.variables:
            return self.variables[name]
        else:
            raise AttributeError("No such attribute: %s" % name)

    def __setattr__(self, name, value):
        """Disable (most) attempts to set attributes.

        This is not completely foolproof. It just acts as a warning! See
        `object.__setattr__`.
        """
        raise TypeError("Event object does not support attribute assignment")


class EventNotifyHandlerBase:
    """Base class for `soco.events.EventNotifyHandler` and
    `soco.events_twisted.EventNotifyHandler`.
    """

    # pylint: disable=too-many-public-methods

    def handle_notification(self, headers, content):
        """Handle a ``NOTIFY`` request by building an `Event` object and
        sending it to the relevant Subscription object.

        A ``NOTIFY`` request will be sent by a Sonos device when a state
        variable changes. See the `UPnP Spec §4.3 [pdf]
        <http://upnp.org/specs/arch/UPnP-arch
        -DeviceArchitecture-v1.1.pdf>`_  for details.

        Args:
            headers (dict): A dict of received headers.
            content (str): A string of received content.
        Note:
            Each of the :py:mod:`soco.events` and the
            :py:mod:`soco.events_twisted` modules has a **subscriptions_map**
            object which keeps a record of Subscription objects. The
            *get_subscription* method of the **subscriptions_map** object is
            used to look up the subscription to which the event relates. When
            the Event Listener runs in a thread (the default), a lock is
            used by this method for thread safety. The *send_event*
            method of the relevant Subscription will first check to see
            whether the *callback* variable of the Subscription has been
            set. If it has been and is callable, then the *callback*
            will be called with the `Event` object. Otherwise, the `Event`
            object will be sent to the event queue of the Subscription
            object. The *callback* variable of the Subscription object is
            intended for use only if :py:mod:`soco.events_twisted` is being
            used, as calls to it are not threadsafe.

            This method calls the log_event method, which must be overridden
            in the class that inherits from this class.
        """

        timestamp = time.time()
        seq = headers["seq"]  # Event sequence number
        sid = headers["sid"]  # Event Subscription Identifier
        # find the relevant service from the sid
        # pylint: disable=no-member
        subscription = self.subscriptions_map.get_subscription(sid)
        # It might have been removed by another thread
        if subscription:
            service = subscription.service
            self.log_event(seq, service.service_id, timestamp)
            log.debug("Event content: %s", content)
            variables = parse_event_xml(content)
            # Build the Event object
            event = Event(sid, seq, service, timestamp, variables)
            # pass the event details on to the service so it can update
            # its cache.
            # pylint: disable=protected-access
            service._update_cache_on_event(event)
            # Pass the event on for handling
            subscription.send_event(event)
        else:
            log.info("No service registered for %s", sid)

    # pylint: disable=missing-docstring
    def log_event(self, seq, service_id, timestamp):
        raise NotImplementedError


class EventListenerBase:
    """Base class for `soco.events.EventListener` and
    `soco.events_twisted.EventListener`.
    """

    def __init__(self):
        #: `bool`: Indicates whether the server is currently running
        self.is_running = False
        self._start_lock = threading.Lock()
        #: `tuple`: The address (ip, port) on which the server is
        #: configured to listen.
        # Empty for the moment. (It is set in `start`)
        self.address = ()
        #: `int`: Port on which to listen.
        self.requested_port_number = config.EVENT_LISTENER_PORT

    def start(self, any_zone):
        """Start the event listener listening on the local machine.

        Args:
            any_zone (SoCo): Any Sonos device on the network. It does not
                matter which device. It is used only to find a local IP
                address reachable by the Sonos net.

        """

        # Find our local network IP address which is accessible to the
        # Sonos net, see http://stackoverflow.com/q/166506
        with self._start_lock:
            if self.is_running:
                return
            # Use configured IP address if there is one, else detect
            # automatically.
            ip_address = get_listen_ip(any_zone.ip_address)
            if not ip_address:
                log.exception("Could not start Event Listener: check network.")
                # Otherwise, no point trying to start server
                return
            port = self.listen(ip_address)
            if not port:
                return
            self.address = (ip_address, port)
            self.is_running = True
            log.debug("Event Listener started")

    def stop(self):
        """Stop the Event Listener."""
        if not self.is_running:
            return
        self.is_running = False
        self.stop_listening(self.address)
        log.debug("Event Listener stopped")

    # pylint: disable=missing-docstring
    def listen(self, ip_address):
        """Start the event listener listening on the local machine.
        This method is called by `start`.

        Args:
            ip_address (str): The local network interface on which the server
                should start listening.
        Returns:
            int: The port on which the server is listening.

        Note:
            This method must be overridden in the class that inherits from
            this class.
        """
        raise NotImplementedError

    # pylint: disable=missing-docstring
    def stop_listening(self, address):
        """Stop the listener.

        Note:
            This method must be overridden in the class that inherits from
            this class.
        """
        raise NotImplementedError


class SubscriptionBase:
    """Base class for `soco.events.Subscription` and
    `soco.events_twisted.Subscription`
    """

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
        #: :py:obj:`function`: an optional function to be called if an
        #: exception occurs upon autorenewal. This will be called with the
        #: exception (or failure, when using :py:mod:`soco.events_twisted`)
        #: as its only parameter. This function must be threadsafe (unless
        #: :py:mod:`soco.events_twisted` is being used).
        self.auto_renew_fail = None
        # A flag to make sure that an unsubscribed instance is not
        # resubscribed
        self._has_been_unsubscribed = False
        # The time when the subscription was made
        self._timestamp = None

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

        # TIMEOUT is provided for in the UPnP spec, but it is not clear if
        # Sonos pays any attention to it. A timeout of 86400 secs always seems
        # to be allocated
        self.requested_timeout = requested_timeout
        if self.is_subscribed:
            raise SoCoException(
                "Cannot subscribe Subscription instance more than once. "
                + "Use renew instead"
            )
        if self._has_been_unsubscribed:
            raise SoCoException(
                "Cannot resubscribe Subscription instance once unsubscribed"
            )
        service = self.service
        # The Event Listener must be running, so start it if not
        # pylint: disable=no-member
        if not self.event_listener.is_running:
            self.event_listener.start(service.soco)
        # an event subscription looks like this:
        # SUBSCRIBE publisher path HTTP/1.1
        # HOST: publisher host:publisher port
        # CALLBACK: <delivery URL>
        # NT: upnp:event
        # TIMEOUT: Second-requested subscription duration (optional)

        # pylint: disable=unbalanced-tuple-unpacking
        ip_address, port = self.event_listener.address

        if config.EVENT_ADVERTISE_IP:
            ip_address = config.EVENT_ADVERTISE_IP

        headers = {
            "Callback": "<http://{}:{}>".format(ip_address, port),
            "NT": "upnp:event",
        }
        if requested_timeout is not None:
            headers["TIMEOUT"] = "Second-{}".format(requested_timeout)

        # pylint: disable=missing-docstring
        def success(headers):
            self.sid = headers["sid"]
            timeout = headers["timeout"]
            # According to the spec, timeout can be "infinite" or "second-123"
            # where 123 is a number of seconds.  Sonos uses "Second-123"
            # (with a capital letter)
            if timeout.lower() == "infinite":
                self.timeout = None
            else:
                self.timeout = int(timeout.lstrip("Second-"))
            self._timestamp = time.time()
            self.is_subscribed = True
            log.debug(
                "Subscribed to %s, sid: %s",
                service.base_url + service.event_subscription_url,
                self.sid,
            )
            # Register the subscription so it can be looked up by sid
            # and unsubscribed at exit
            self.subscriptions_map.register(self)

            # Set up auto_renew
            if not auto_renew:
                return
            # Autorenew just before expiry, say at 85% of self.timeout seconds
            interval = self.timeout * 85 / 100
            self._auto_renew_start(interval)

        # Lock out EventNotifyHandler during registration.
        # If events_twisted is used, this lock should always be
        # available, since threading is not being used. This is to prevent
        # the EventNotifyHandler from sending a notification before the
        # subscription has been registered.
        with self.subscriptions_map.subscriptions_lock:
            return self._request(
                "SUBSCRIBE",
                service.base_url + service.event_subscription_url,
                headers,
                success,
            )

    def renew(self, requested_timeout=None, is_autorenew=False):
        """renew(requested_timeout=None)
        Renew the event subscription.
        You should not try to renew a subscription which has been
        unsubscribed, or once it has expired.

        Args:
            requested_timeout (int, optional): The period for which a renewal
                request should be made. If None (the default), use the timeout
                requested on subscription.
            is_autorenew (bool, optional): Whether this is an autorenewal.

        """
        # NB This code may be called from a separate thread when
        # subscriptions are auto-renewed. Be careful to ensure thread-safety

        if is_autorenew:
            log_msg = "Autorenewing subscription %s"
        else:
            log_msg = "Renewing subscription %s"
        log.debug(log_msg, self.sid)

        if self._has_been_unsubscribed:
            raise SoCoException("Cannot renew subscription once unsubscribed")
        if not self.is_subscribed:
            raise SoCoException("Cannot renew subscription before subscribing")
        if self.time_left == 0:
            raise SoCoException("Cannot renew subscription after expiry")

        # SUBSCRIBE publisher path HTTP/1.1
        # HOST: publisher host:publisher port
        # SID: uuid:subscription UUID
        # TIMEOUT: Second-requested subscription duration (optional)
        headers = {"SID": self.sid}
        if requested_timeout is None:
            requested_timeout = self.requested_timeout
        if requested_timeout is not None:
            headers["TIMEOUT"] = "Second-{}".format(requested_timeout)

        # pylint: disable=missing-docstring
        def success(headers):
            timeout = headers["timeout"]
            # According to the spec, timeout can be "infinite" or "second-123"
            # where 123 is a number of seconds.  Sonos uses "Second-123"
            # (with a capital letter)
            if timeout.lower() == "infinite":
                self.timeout = None
            else:
                self.timeout = int(timeout.lstrip("Second-"))
            self._timestamp = time.time()
            self.is_subscribed = True
            log.debug(
                "Renewed subscription to %s, sid: %s",
                self.service.base_url + self.service.event_subscription_url,
                self.sid,
            )

        return self._request(
            "SUBSCRIBE",
            self.service.base_url + self.service.event_subscription_url,
            headers,
            success,
        )

    def unsubscribe(self):
        """unsubscribe()
        Unsubscribe from the service's events.
        Once unsubscribed, a Subscription instance should not be reused
        """
        # Trying to unsubscribe if already unsubscribed, or not yet
        # subscribed, fails silently
        if self._has_been_unsubscribed or not self.is_subscribed:
            return None

        # If the subscription has timed out, an attempt to
        # unsubscribe from it will fail silently.
        if self.time_left == 0:
            return None

        # Send an unsubscribe request like this:
        # UNSUBSCRIBE publisher path HTTP/1.1
        # HOST: publisher host:publisher port
        # SID: uuid:subscription UUID
        headers = {"SID": self.sid}

        # pylint: disable=missing-docstring, unused-argument
        def success(*arg):
            log.debug(
                "Unsubscribed from %s, sid: %s",
                self.service.base_url + self.service.event_subscription_url,
                self.sid,
            )

        return self._request(
            "UNSUBSCRIBE",
            self.service.base_url + self.service.event_subscription_url,
            headers,
            success,
            self._cancel_subscription,
        )

    def send_event(self, event):
        """Send an `Event` to self.callback or self.events.
        If self.callback is set and is callable, it will be called with the
        `Event` as the only parameter. Otherwise the `Event` will be sent to
        self.events. As self.callback is not threadsafe, it should be set
        only if `soco.events_twisted.Subscription` is being used.

        Args:
            event(Event): The `Event` to send to self.callback or
                self.events.

        """
        if hasattr(self, "callback"):
            # pylint: disable=no-member
            callback = self.callback
        else:
            callback = None
        if callback and hasattr(callback, "__call__"):
            callback(event)
        else:
            try:
                self.events.put(event)
            # pylint: disable=broad-except
            except Exception as ex:
                log.warning("Error putting event %s, ex=%s", event, ex)

    # pylint: disable=missing-docstring
    def _auto_renew_start(self, interval):
        """Starts the auto_renew thread.

        Note:
            This method must be overridden in the class that inherits from
            this class.
        """
        raise NotImplementedError

    # pylint: disable=missing-docstring
    def _auto_renew_cancel(self):
        """Cancels the auto_renew thread.

        Note:
            This method must be overridden in the class that inherits from
            this class.
        """
        raise NotImplementedError

    # pylint: disable=missing-docstring, too-many-arguments
    def _request(self, method, url, headers, success, unconditional=None):
        """Send a HTTP request

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

        Note:
            This method must be overridden in the class that inherits from
            this class.
        """
        raise NotImplementedError

    # pylint: disable=missing-docstring
    def _cancel_subscription(self, msg=None):
        # unregister subscription
        # pylint: disable=no-member
        self.subscriptions_map.unregister(self)
        # Stop the event listener, if there are no other subscriptions
        if self.subscriptions_map.count == 0:
            self.event_listener.stop()
        # No need to do any more if this flag has been set to True
        if self._has_been_unsubscribed:
            return
        self.is_subscribed = False
        # Set the self._has_been_unsubscribed flag now
        # to prevent reuse of the subscription, even if
        # an attempt to unsubscribe fails
        self._has_been_unsubscribed = True
        self._timestamp = None
        # Cancel any auto renew
        self._auto_renew_cancel()
        if msg:
            log.info(msg)

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

    def __enter__(self):
        if not self.is_subscribed:
            self.subscribe()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unsubscribe()


class SubscriptionsMap:
    """Maintains a mapping of sids to `soco.events.Subscription` instances
    and the thread safe lock to go with it. Registers each subscription to
    be unsubscribed at exit.

    `SubscriptionsMapTwisted` inherits from this class.

    """

    def __init__(self):
        super().__init__()
        #: `weakref.WeakValueDictionary`: Thread safe mapping.
        #: Used to store a mapping of sid to subscription
        self.subscriptions = weakref.WeakValueDictionary()
        # The lock to go with it
        # You must only ever access the mapping in the context of this lock,
        # eg:
        #   with self.subscriptions_lock:
        #       queue = self.subscriptions[sid].events
        #: `threading.Lock`: for use with `subscriptions`
        self.subscriptions_lock = threading.Lock()

    def register(self, subscription):
        """Register a subscription by updating local mapping of sid to
        subscription and registering it to be unsubscribed at exit.

        Args:
            subscription(`soco.events.Subscription`): the subscription
                to be registered.

        """
        # Add the queue to the master dict of subscriptions so it can be
        # looked up by sid. The subscriptions_lock is not used here as
        # it is used in Subscription.subscribe() in the events_base
        # module, from which the register function is called.
        self.subscriptions[subscription.sid] = subscription
        # Register subscription to be unsubscribed at exit if still alive
        # This will not happen if exit is abnormal (eg in response to a
        # signal or fatal interpreter error - see the docs for `atexit`).
        atexit.register(subscription.unsubscribe)

    def unregister(self, subscription):
        """Unregister a subscription by updating local mapping of sid to
        subscription instances.

        Args:
            subscription(`soco.events.Subscription`): the subscription
                to be unregistered.

        When using :py:mod:`soco.events_twisted`, an instance of
        `soco.events_twisted.Subscription` will be unregistered.

        """
        with self.subscriptions_lock:
            try:
                del self.subscriptions[subscription.sid]
            except KeyError:
                pass

    def get_subscription(self, sid):
        """Look up a subscription from a sid.

            Args:
                sid(str): The sid from which to look up the subscription.

            Returns:
                `soco.events.Subscription`: The subscription relating
                to that sid.

        When using :py:mod:`soco.events_twisted`, an instance of
        `soco.events_twisted.Subscription` will be returned.

        """
        with self.subscriptions_lock:
            return self.subscriptions.get(sid)

    @property
    def count(self):
        """
        `int`: The number of active subscriptions.
        """
        with self.subscriptions_lock:
            return len(self.subscriptions)


def get_listen_ip(ip_address):
    """Find the listen ip address."""
    if config.EVENT_LISTENER_IP:
        return config.EVENT_LISTENER_IP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((ip_address, config.EVENT_LISTENER_PORT))
        return sock.getsockname()[0]
    except socket.error:
        return None
    finally:
        sock.close()
