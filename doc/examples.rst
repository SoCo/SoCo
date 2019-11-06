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

Getting a device by player name can be done with the
:func:`soco.discovery.by_name` function::

  >>> from soco.discovery import by_name
  >>> device = by_name("Living Room")
  >>> device
  SoCo("192.168.1.18")


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

Seeing and manipulating the queue
---------------------------------

Getting the queue
^^^^^^^^^^^^^^^^^

Getting the queue is done with the :meth:`~soco.core.SoCo.get_queue` method::

  >>> queue = device.get_queue()
  >>> queue
  Queue(items=[<DidlMusicTrack 'b'Blackened'' at 0x7f2237006dd8>, ..., <DidlMusicTrack 'b'Dyers Eve'' at 0x7f2237006828>])

The returned :class:`~soco.data_structures.Queue` object is a sequence
of items from the queue, meaning that it can be iterated over and its
length aquired with :func:`len`::

  >>> len(queue)
  9
  >>> for item in queue:
  ...     print(item.title)
  ...
  Blackened
  ...and Justice for All
  Eye of the Beholder
  One
  The Shortest Straw
  Harvester of Sorrow
  The Frayed Ends of Sanity
  To Live Is to Die
  Dyers Eve
  
The queue object also has :attr:`~.ListOfMusicInfoItems.total_matches`
and :attr:`~.ListOfMusicInfoItems.number_returned` attributes, which
are used to figure out whether paging is required in order to get all
elements of the queue. See the :class:`~.ListOfMusicInfoItems`
docstring for details.

Clearing the queue
^^^^^^^^^^^^^^^^^^

Clearing the queue is done with the
:meth:`~soco.core.SoCo.clear_queue` method as follows::

  >>> queue = device.get_queue()
  >>> len(queue)
  9
  >>> device.clear_queue()
  >>> queue = device.get_queue()
  >>> len(queue)
  0

Listing and deleting music library shares
-----------------------------------------

Music library shares are the local network drive shares connected to
Sonos, which host the audio content in the Sonos Music Library.

To list the shares connected to Sonos, use the
:meth:`~soco.music_library.MusicLibrary.list_library_shares` method as follows::

  >>> device.music_library.list_library_shares()
  ['//share_host_01/music', '//share_host_02/music']

The result is a list of network share locations.

To delete a network share, use the
:meth:`~soco.music_library.MusicLibrary.delete_library_share` method as follows::

  >>> device.music_library.delete_library_share('//share_host_01/music')

You may want to check that the deletion has succeeded, by waiting a few seconds,
then confirming that the share has disappeared from the list of shares.
