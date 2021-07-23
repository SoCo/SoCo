.. _events:

Events
======

.. toctree::
   :maxdepth: 1

   events_twisted
   events_asyncio

You can receive events about changes on the Sonos network.

The :meth:`soco.services.Service.subscribe` method of a service now returns a
:class:`soco.events.Subscription` object. To unsubscribe, call the
:meth:`soco.events.Subscription.unsubscribe` method on the returned
object.

Each subscription has its own queue. Events relevant to that subscription are
put onto that queue, which can be accessed from ``subscription.events.get()``.

Some XML parsing is done for you when you retrieve an event from the event
queue. The ``get`` and ``get_nowait`` methods will return a dict with keys
which are the evented variables and values which are the values sent by the
event.

See :ref:`the events_twisted module <events_twisted>` page for more
information about :mod:`soco.events_twisted`.

See :ref:`the events_asyncio module <events_asyncio>` page for more
information about :mod:`soco.events_asyncio`.

Example: setting up
-------------------

:mod:`soco.events`
^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from queue import Empty

    import soco
    from soco.events import event_listener
    import logging
    logging.basicConfig(level=logging.DEBUG)
    # pick a device
    device = soco.discover().pop()
    # Subscribe to ZGT events
    sub = device.zoneGroupTopology.subscribe()

    # print out the events as they arise
    while True:
        try:
            event = sub.events.get(timeout=0.5)
            print(event)
            print(event.sid)
            print(event.seq)

        except Empty:
            pass
        except KeyboardInterrupt:
            sub.unsubscribe()
            event_listener.stop()
            break

:mod:`soco.events_twisted`
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import soco
    from soco import events_twisted
    soco.config.EVENTS_MODULE = events_twisted
    from twisted.internet import reactor
    import logging
    logging.basicConfig(level=logging.DEBUG)

    def print_event(event):
        print (event)
        print(event.sid)
        print(event.seq)

    def main():
        # pick a device
        device = soco.discover().pop()
        # Subscribe to ZGT events
        sub = device.zoneGroupTopology.subscribe().subscription
        # print out the events as they arise
        sub.callback = print_event

        def before_shutdown():
            sub.unsubscribe()
            events_twisted.event_listener.stop()

        reactor.addSystemEventTrigger(
            'before', 'shutdown', before_shutdown)

    if __name__=='__main__':
        reactor.callWhenRunning(main)
        reactor.run()

:mod:`soco.events_asyncio`
^^^^^^^^^^^^^^^^^^^^^^^^^^

See :mod:`soco.events_asyncio` for a setup example.

Examples: specific features
---------------------------

Autorenewal
^^^^^^^^^^^

A Subscription may be granted by the Sonos system for a finite time. Unless
it is renewed before it times out, the subscription will become defunct once
it times out. To avoid this, the autorenewal feature can be used. If the
auto-renew flag is set to True, the subscription will automatically renew
when 85% of its time has expired.

:mod:`soco.events`::

    sub = device.renderingControl.subscribe(auto_renew=True)

:mod:`soco.events_twisted`::

    sub = device.renderingControl.subscribe(auto_renew=True).subscription

Timeout
^^^^^^^

When subscribing for events, a timeout of a specific duration can be
requested. 

:mod:`soco.events`::

    sub = device.renderingControl.subscribe(requested_timeout=60) # 60 seconds

:mod:`soco.events_twisted`::

    sub = device.renderingControl.subscribe(requested_timeout=60).subscription

Renewal
^^^^^^^

To renew without relying on autorenewal, the renew method can be used::

    sub.renew(requested_timeout=10)

Autorenew failure
^^^^^^^^^^^^^^^^^

If you want your application to respond to an autorenew failure (for example
if the Sonos system dropped off the network), you can set an optional callback
that will be called with the exception that occurred on the attempted
autorenew::

    import logging
    logging.basicConfig()
    log = logging.getLogger(__name__)

    def errback(exception): # events_twisted: failure
        msg = 'Error received on autorenew: {}'.format(str(exception))
        # Redundant, as the exception will be logged by the events module
        log.exception(msg)

    sub.auto_renew_fail=errback

Note: In :mod:`soco.events` the auto_renew_fail function will be called from a
thread, so it must be threadsafe.

Lenient error handling
^^^^^^^^^^^^^^^^^^^^^^

By default, if an exception occurs when subscribing, renewing or unsubscribing
a subscription, the exception will be raised. This can be changed so the
exception is logged instead, by setting the strict flag to be false::

    sub.unsubscribe(strict=False)

Events_twisted: adding callbacks and errbacks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If the events_twisted module is used, subscribe, renew and unsubscribe return
a Deferred_, the result of which will be the
:class:`~soco.events_twisted.Subscription` instance. Callbacks
and errbacks can be added in the usual way::

    device.renderingControl.subscribe().addCallback(myCallback).addErrback(
        myErrback)

.. _Deferred: https://twistedmatrix.com/documents/current/api/twisted.internet.defer.Deferred.html

