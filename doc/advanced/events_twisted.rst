.. _events_twisted:

The events_twisted module 
=========================

The :mod:`soco.events_twisted` module has been provided for those wanting to
use soco in an application built on the twisted_ framework who want the event
listener also to be implemented using twisted. The :mod:`soco.events_twisted`
page contains an example of how to use the module.

The event listener is an HTTP server that receives event notifications from
sonos devices. In the :mod:`soco.events` module, it is implemented using 
threading and requests. The :mod:`soco.events` module will apply by default,
unless `config.EVENTS_MODULE` is set to point to the
:mod:`soco.events_twisted` module.

Twisted is not a soco dependency. The existence of the events_twisted module
is not a recommendation or endorsement of twisted. The events_twisted module
has been provided because there are some soco users who use twisted.

If you wish to use events_twisted, it is assumed you already use and are
familiar with the twisted_ framework. No guidance is provided here on how to
install or use twisted.

The main differences between :mod:`soco.events_twisted` and :mod:`soco.events`
are:

- :mod:`soco.events_twisted` uses twisted_, rather than requests_, for making
  and receiving HTTP calls. Network calls in events_twisted return at once
  without blocking

- in :mod:`soco.events_twisted`, the event listener runs in the main thread of
  execution. Threading is not used

- :mod:`soco.events_twisted` requires a twisted reactor_ to be running in the
  application into which it is imported. It will not install or start a
  reactor

- :mod:`soco.events_twisted` is not threadsafe and should run in the main
  thread of execution. Therefore, subscribing to events should happen in the
  main thread of execution. In part, this is because a Deferred_ is not
  threadsafe

- in :mod:`soco.events_twisted`, if the requested port is not available, the
  event_listener will automatically try the next port, within a maximum range
  of 100 of the port initially requested

- in :mod:`soco.events_twisted`, subscribe, renew and unsubscribe return a
  Deferred_ the result of which will be the
  :class:`soco.events_twisted.Subscription` instance. The Subscription can be
  accessed by adding a callback to receive it. In addition,
  Deferred.subscription is set to refer to the Subscription. This is a simpler
  and quicker way to get the Subscription

- in :mod:`soco.events_twisted`, Subscription.callback can be set to refer to
  a function that will be called each time a :class:`soco.events_base.Event`
  is received by the Subscription. The callback will be passed the Event as
  the only parameter. This is likely to be the most convenient way to receive
  Events. If Subscription.callback is not set, or is not callable, Events will
  be put on the Subscription's event queue, in the same way as for the events
  module.

Please note that all network calls in soco (other than those in
events_twisted) are made using the requests_ library, which blocks. In an
application based on twisted, it may be desirable to make these network calls
asynchronously, so they do not block. Two solutions to consider are (a) to use
threads when calling other potentially blocking soco methods or (b) to use a
subprocess to handle calls to soco. Twisted provides the deferToThread_ method
for deferring potentially blocking methods to a thread. If a subprocess is to
be used, there will need to be a protocol for communication between the
subprocess and the main application. For a DIY solution, twisted's
NetstringReceiver_ may be a useful starting point.

.. _twisted: https://twistedmatrix.com/trac/
.. _requests: http://docs.python-requests.org/en/master/
.. _reactor: http://twistedmatrix.com/documents/current/core/howto/reactor-basics.html
.. _Deferred: https://twistedmatrix.com/documents/current/api/twisted.internet.defer.Deferred.html
.. _deferToThread: http://twistedmatrix.com/documents/current/api/twisted.internet.threads.deferToThread.html
.. _NetstringReceiver: http://twistedmatrix.com/documents/current/api/twisted.protocols.basic.NetstringReceiver.html
