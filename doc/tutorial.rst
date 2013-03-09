Tutorial
========

*SoCo* allows you to control your Sonos sound system from a Python program. For
a quick start have a look at the `example applications
<https://github.com/rahims/SoCo/tree/master/examples>`_ that come with the
library.


Discovery
---------

For discovering the Sonos devices in your network, use the ``SonosDiscovery``
class.

.. code-block:: python

    sd = SonosDiscovery()
    ips = sd.get_speaker_ips()


Music
-----

Once one of the available devices is selected, the ``SoCo`` class can be used
to control it. Have a look at the :ref:`soco-mod` for all available commands.

.. code-block:: python

    sonos = SoCo(ip)
    sonos.partymode()
