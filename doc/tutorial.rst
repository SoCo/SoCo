Tutorial
========

*SoCo* allows you to control your Sonos sound system from a Python program. For
a quick start have a look at the `example applications
<https://github.com/rahims/SoCo/tree/master/examples>`_ that come with the
library.


Discovery
---------

For discovering the Sonos devices in your network, use :meth:`soco.discover`.

.. code-block:: python

    >>> import soco
    >>> speakers = soco.discover()

It returns a :class:`set` of :class:`soco.SoCo` instances, each representing a
speaker in your network.


Music
-----

You can use those SoCo instances to inspect and interact with your speakers.

.. code-block:: python

    >>> speaker = speakers.pop()
    >>> speaker.player_name
    'Living Room'
    >>> speaker.ip_address
    u'192.168.0.129'

    >>> speaker.volume
    10
    >>> speaker.volume = 15
    >>> speaker.play()


See for :class:`soco.SoCo` for all methods that are available for a speaker.
