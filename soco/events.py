# -*- coding: utf-8 -*-
# pylint: disable=not-context-manager

# NOTE: The pylint not-content-manager warning is disabled pending the fix of
# a bug in pylint: https://github.com/PyCQA/pylint/issues/782

"""Classes to handle Sonos UPnP Events and Subscriptions.

.. _example1:

    Example 1:

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

.. _example2:

    Example 2 (with a twisted reactor):

        Run this code, and change your volume, tracks etc::

            from twisted.internet import reactor

            import logging
            logging.basicConfig()
            import soco
            from pprint import pprint
            from soco.events import event_listener

            def print_event(event):
                try:
                    pprint (event.variables)
                except Exception as e:
                    print 'There was an error in print_event:', e

            def main():
                # pick a device at random and use it to get
                # the group coordinator
                device = soco.discover().pop()
                device = device.group.coordinator
                print (device.player_name)

                sub = device.renderingControl.subscribe()
                sub2 = device.avTransport.subscribe()
                sub.callback = print_event
                sub2.callback = print_event

                def before_shutdown():
                    sub.unsubscribe()
                    sub2.unsubscribe()
                    event_listener.stop()

                reactor.addSystemEventTrigger(
                    'before', 'shutdown', before_shutdown)

            if __name__=='__main__':
                reactor.callWhenRunning(main)
                reactor.run()
"""

from __future__ import unicode_literals

import logging
import socket
import time
import sys

from . import config
from .compat import Queue
from .data_structures_entry import from_didl_string
from .exceptions import SoCoException
from .utils import camel_to_underscore
from .xml import XML

# Import base modules from events_base, unless a twisted.internet.reactor
# is detected in the application, in which case import base modules from
# events_base_twisted.
if 'twisted.internet.reactor' in sys.modules.keys():
    from .events_base_twisted import (
        NotifyHandler, Listener, SubscriptionBase, Subscriptions
    )
else:
    from .events_base import (
        NotifyHandler, Listener, SubscriptionBase, Subscriptions
    )

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
    """

    result = {}
    tree = XML.fromstring(xml_event)
    # property values are just under the propertyset, which
    # uses this namespace
    properties = tree.findall(
        '{urn:schemas-upnp-org:event-1-0}property')
    for prop in properties:  # pylint: disable=too-many-nested-blocks
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
                # whether we are looking at an avTransport event, a
                # renderingControl event, or a Queue event
                # (there, it is named QueueID)
                instance = last_change_tree.find(
                    "{urn:schemas-upnp-org:metadata-1-0/AVT/}InstanceID")
                if instance is None:
                    instance = last_change_tree.find(
                        "{urn:schemas-upnp-org:metadata-1-0/RCS/}InstanceID")
                if instance is None:
                    instance = last_change_tree.find(
                        "{urn:schemas-sonos-com:metadata-1-0/Queue/}QueueID")
                # Fix for issue described at
                # https://github.com/SoCo/SoCo/issues/378
                if instance is None:
                    instance = last_change_tree.find(
                        "{urn:schemas-sonos-com:metadata-1-0/Queue/}QueueID")
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


class EventNotifyHandler(NotifyHandler):
    """Handles HTTP ``NOTIFY`` Verbs sent to the Event Listener server.

    A ``NOTIFY`` request will be sent by a Sonos device when a state
    variable changes. See the `UPnP Spec §4.3 [pdf]
    <http://upnp.org/specs/arch/UPnP-arch
    -DeviceArchitecture-v1.1.pdf>`_  for details.

    Inherits from `soco.events_base.NotifyHandler`, unless a twisted reactor
    is detected, in which case it inherits from
    `soco.events_base_twisted.NotifyHandler`.
    """
    # pylint: disable=too-many-public-methods

    def handle_notification(self, headers, content):
        """
        Builds an `Event` object and sends it to the relevant
        `Subscription` object.

        Args:
            headers (dict): A dict of received headers.
            content (str): A string of received content.

        Note:
            The :py:mod:`soco.events` module has a **subscriptions**
            object which keeps a record of `Subscription` objects. The
            *get_service* method of the **subscriptions** object is used
            to look up the service to which the event relates and the
            *send_to_service* method of the **subscriptions** object is
            used to send an event to the relevant `Subscription`. When
            the Event Listener runs in a thread(the default), a lock is
            used by both these methods for thread safety. The `Event`
            object will be sent to the event queue of the relevant
            `Subscription` object (see :ref:`Example 1 <example1>` above),
            unless the application is using twisted, in which case the
            *send_to_service* method of the **subscriptions** object will
            first check to see whether the *callback* variable of the relevant
            `Subscription` has been set. If it has been and is callable,
            then the *callback* will be called with the `Event` object
            (see :ref:`Example 2 <example2>` above). Otherwise, the `Event`
            object will be sent to the event queue of the relevant
            `Subscription` object. The **subscriptions** object is a
            `events_base.Subscriptions` object from `soco.events_base`,
            unless a twisted reactor is detected, in which case it is a
            `soco.events_base_twisted.Subscriptions` object from
            `soco.events_base_twisted`.
         """

        timestamp = time.time()
        seq = headers['seq']  # Event sequence number
        sid = headers['sid']  # Event Subscription Identifier
        # find the relevant service from the sid
        service = subscriptions.get_service(sid)
        # It might have been removed by another thread
        if service:
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
            subscriptions.send_to_service(sid, event)
        else:
            log.info("No service registered for %s", sid)


class EventListener(Listener):
    """The Event Listener server.

    Runs an http server which is an endpoint for ``NOTIFY``
    requests from Sonos devices. The server will run in a thread,
    unless the application is using twisted.

    The Event Listener will listen on the local machine at port 1400
    (default). Make sure that your firewall allows connections to this port.

    Inherits from `soco.events_base.Listener`, unless a twisted reactor
    is detected, in which case it inherits from
    `soco.events_base_twisted.Listener`.

    Note:
        The port on which the Event Listener attempts to listen is
        configurable. See `config.EVENT_LISTENER_PORT`. If the application
        is using twisted (see :ref:`Example 2 <example2>` above) and this
        port is unavailable, the Event Listener will attempt to listen on
        the next available port, within a range of 100 from
        `config.EVENT_LISTENER_PORT`.

    """

    def __init__(self):
        super(EventListener, self).__init__(EventNotifyHandler,
                                            config.EVENT_LISTENER_PORT)
        #: `bool`: Indicates whether the server is currently running
        self.is_running = False
        #: `tuple`: The address (ip, port) on which the server is
        #: configured to listen.
        # Empty for the moment. (It is set in `start`)
        self.address = ()

    def start(self, any_zone):
        """ Starts the Event Listener.

        Args:
            any_zone (SoCo): Any Sonos device on the network. It does not
                matter which device. It is used only to find a local IP address
                reachable by the Sonos net.
        """

        # Find our local network IP address which is accessible to the
        # Sonos net, see http://stackoverflow.com/q/166506
        if not self.is_running:
            # Use configured IP address if there is one, else detect
            # automatically.
            if config.EVENT_LISTENER_IP:
                ip_address = config.EVENT_LISTENER_IP
            else:
                temp_sock = socket.socket(socket.AF_INET,
                                          socket.SOCK_DGRAM)
                try:
                    # doesn't have to be reachable
                    temp_sock.connect((any_zone.ip_address, 0))
                    ip_address = temp_sock.getsockname()[0]
                except socket.error:
                    log.exception(
                        'Could not start Event Listener: check network.')
                    ip_address = None
                finally:
                    temp_sock.close()
            if ip_address:  # Otherwise, no point trying to start server
                # Check what port we actually got (twisted only)
                port = super(EventListener, self).start(ip_address)
                if port:
                    self.address = (ip_address, port)
                    self.is_running = True
                    log.info("Event Listener started")

    def stop(self):
        """Stop the Event Listener."""
        if not self.is_running:
            return
        self.is_running = False
        super(EventListener, self).stop(self.address)
        log.info("Event Listener stopped")


class Subscription(SubscriptionBase):

    """A class representing the subscription to a UPnP event.

    Inherits from `soco.events_base.SubscriptionBase`, unless a
    twisted reactor is detected, in which case it inherits from
    `soco.events_base_twisted.SubscriptionBase`.

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

    def subscribe(self, requested_timeout=None, auto_renew=False):
        """subscribe(requested_timeout=None, auto_renew=False)
        Subscribe to the service.

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
        if self._has_been_unsubscribed:
            raise SoCoException(
                'Cannot resubscribe instance once unsubscribed')
        service = self.service
        # The Event Listener must be running, so start it if not
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
            'Callback': '<http://{}:{}>'.format(ip_address, port),
            'NT': 'upnp:event'
        }
        if requested_timeout is not None:
            headers["TIMEOUT"] = "Second-{}".format(requested_timeout)

        # pylint: disable=missing-docstring
        def success(headers):
            self.sid = headers['sid']
            timeout = headers['timeout']
            # According to the spec, timeout can be "infinite" or "second-123"
            # where 123 is a number of seconds.  Sonos uses "Second-123"
            # (with a capital letter)
            if timeout.lower() == 'infinite':
                self.timeout = None
            else:
                self.timeout = int(timeout.lstrip('Second-'))
            self._timestamp = time.time()
            self.is_subscribed = True
            log.info(
                "Subscribed to %s, sid: %s",
                service.base_url + service.event_subscription_url, self.sid)
            # Register the subscription so it can be looked up by sid
            # and unsubscribed at exit
            subscriptions.register(self)

            # Set up auto_renew
            if not auto_renew:
                return
            # Autorenew just before expiry, say at 85% of self.timeout seconds
            interval = self.timeout * 85 / 100
            self.auto_renew_start(interval)

        # pylint: disable=missing-docstring
        def failure():
            # Should an exception be raised?
            log.warning(
                "Could not subscribe to %s",
                service.base_url + service.event_subscription_url)

        # Lock out EventNotifyHandler during registration.
        # If events_base_twisted is used, this lock should always be
        # available, since threading is not being used.
        with subscriptions.subscriptions_lock:
            self.request(
                'SUBSCRIBE', service.base_url + service.event_subscription_url,
                headers, success, failure)

    def renew(self, requested_timeout=None):
        """renew(requested_timeout=None)
        Renew the event subscription.

        You should not try to renew a subscription which has been
        unsubscribed, or once it has expired.

        Args:
            requested_timeout (int, optional): The period for which a renewal
                request should be made. If None (the default), use the timeout
                requested on subscription.
        """
        # NB This code may be called from a separate thread when
        # subscriptions are auto-renewed. Be careful to ensure thread-safety

        log.info("Autorenewing subscription %s", self.sid)
        # log.warning is used below, as raising
        # Exceptions from within a thread seems pointless
        if self._has_been_unsubscribed:
            log.warning(
                'Cannot renew subscription once unsubscribed')
            return
        if not self.is_subscribed:
            log.warning(
                'Cannot renew subscription before subscribing')
            return
        if self.time_left == 0:
            log.warning(
                'Cannot renew subscription after expiry')
            # If the subscription has timed out, it seems appropriate
            # to cancel it.
            self._cancel_subscription()

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
            headers["TIMEOUT"] = "Second-{}".format(requested_timeout)

        # pylint: disable=missing-docstring
        def success(headers):
            timeout = headers['timeout']
            # According to the spec, timeout can be "infinite" or "second-123"
            # where 123 is a number of seconds.  Sonos uses "Second-123"
            # (with a capital letter)
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

        # pylint: disable=missing-docstring
        def failure():
            log.warning(
                "Could not renew subscription to %s, sid: %s",
                self.service.base_url + self.service.event_subscription_url,
                self.sid)
            # If the renewal has failed, it seems appropriate
            # to cancel the subscription.
            self._cancel_subscription()

        self.request(
            'SUBSCRIBE',
            self.service.base_url + self.service.event_subscription_url,
            headers, success, failure)

    def unsubscribe(self):
        """unsubscribe()
        Unsubscribe from the service's events.

        Once unsubscribed, a Subscription instance should not be reused
        """
        # Trying to unsubscribe if already unsubscribed, or not yet
        # subscribed, fails silently
        if self._has_been_unsubscribed or not self.is_subscribed:
            return
        self._cancel_subscription()

        # Send an unsubscribe request like this:
        # UNSUBSCRIBE publisher path HTTP/1.1
        # HOST: publisher host:publisher port
        # SID: uuid:subscription UUID
        headers = {
            'SID': self.sid
        }

        # pylint: disable=missing-docstring, unused-argument
        def success(*arg):
            log.info(
                "Unsubscribed from %s, sid: %s",
                self.service.base_url + self.service.event_subscription_url,
                self.sid)

        # pylint: disable=missing-docstring
        def failure():
            log.warning(
                "Error attempting to unsubscribe from %s, sid: %s",
                self.service.base_url + self.service.event_subscription_url,
                self.sid)

        self.request(
            'UNSUBSCRIBE',
            self.service.base_url + self.service.event_subscription_url,
            headers, success, failure)

    # pylint: disable=missing-docstring
    def _cancel_subscription(self):
        self.is_subscribed = False
        # Set the self._has_been_unsubscribed flag now
        # to prevent reuse of the subscription, even if
        # an attempt to unsubscribe fails
        self._has_been_unsubscribed = True
        self._timestamp = None
        # unregister subscription
        subscriptions.unregister(self)
        # Cancel any auto renew
        self.auto_renew_cancel()

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

subscriptions = Subscriptions()  # pylint: disable=C0103
event_listener = EventListener()  # pylint: disable=C0103
