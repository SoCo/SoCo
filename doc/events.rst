.. _events:

Events
======

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

Example
-------

.. code-block:: python

    try:
        from queue import Empty
    except:  # Py2.7
        from Queue import Empty

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

