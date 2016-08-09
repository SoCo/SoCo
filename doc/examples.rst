.. _examples:

Examples
========

This page contains collection of small examples to show of the features of
*SoCo* and hopefully get you well started with the library.

All examples are shown as if entered in the Python interpreter (as apposed to
executed from a file) because that makes it easy to incorporate output in the
code listings.

All the examples from :ref:`examples_playback_control` and forward
assume that you have followed one of the examples in
:ref:`examples_getting_your_devices` and therefore already have a
variable named ``device`` that points to a :class:`soco.SoCo`
instance.

.. _examples_getting_your_devices:

Getting your devices
--------------------

Getting all your devices
^^^^^^^^^^^^^^^^^^^^^^^^

To get all your devices use the :func:`soco.discover` function::

  >>> import soco
  >>> devices = soco.discover()
  >>> devices
  set([SoCo("192.168.0.10"), SoCo("192.168.0.30"), SoCo("192.168.0.17")])
  >>> device = devices.pop()
  >>> device
  SoCo("192.168.0.16")

Getting any device
^^^^^^^^^^^^^^^^^^

To get any device use the :func:`soco.discovery.any_soco` function. This can be
useful for cases where you really do not care which one you get, you just need
one e.g. to query for music library information::

  >>> import soco
  >>> device = soco.discovery.any_soco()
  >>> device
  SoCo("192.168.0.16")

Getting a named device
^^^^^^^^^^^^^^^^^^^^^^

Getting a device by name is done by searching through the devices
returned by :func:`soco.discover`::

  >>> import soco
  >>> for device in soco.discover():
  ...     if device.player_name == 'Office':
  ...         break
  ... else:
  ...     device = None
  ... 
  >>> device
  SoCo("192.168.1.8")

.. _examples_playback_control:

Playback control
----------------

Play, pause and stop
^^^^^^^^^^^^^^^^^^^^

The normal play, pause and stop functionality is provided with
similarly named methods (:meth:`~soco.core.SoCo.play`,
:meth:`~soco.core.SoCo.pause` and :meth:`~soco.core.SoCo.stop`) on the
:class:`~soco.core.SoCo` instance and the current state is included in the
output of :meth:`~soco.core.SoCo.get_current_transport_info`::

  >>> device.get_current_transport_info()['current_transport_state']
  'STOPPED'
  >>> device.play()
  >>> device.get_current_transport_info()['current_transport_state']
  'PLAYING'
  >>> device.pause()
  >>> device.get_current_transport_info()['current_transport_state']
  'PAUSED_PLAYBACK'

More playback control with next, previous and seek
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Navigating to the next or previous track is similarly done with
methods of the same name (:meth:`~soco.core.SoCo.next` and
:meth:`~soco.core.SoCo.previous`) and information about the current
position in the queue is contained in the output from
:meth:`~soco.core.SoCo.get_current_track_info`::

  >>> device.get_current_track_info()['playlist_position']
  '29'
  >>> device.next()
  >>> device.get_current_track_info()['playlist_position']
  '30'
  >>> device.previous()
  >>> device.get_current_track_info()['playlist_position']
  '29'

Seeking is done with the :meth:`~soco.core.SoCo.seek` method. Note
that the input for that method is a string on the form "HH:MM:SS" or
"H:MM:SS". The current position is also contained in
:meth:`~soco.core.SoCo.get_current_track_info`::

  >>> device.get_current_track_info()['position']
  '0:02:59'
  >>> device.seek("0:00:30")
  >>> device.get_current_track_info()['position']
  '0:00:31'
