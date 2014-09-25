Release notes
*************


Version 0.10
============

Release notes for the upcoming release.

New Features
------------


Improvements
------------


Backwards Compatability
-----------------------



Version 0.9
===========

New Features
------------

* Alarm configuration (`#171 <https://github.com/SoCo/SoCo/pull/171>`_) ::

    >>> from soco.alarms import Alarm, get_alarms
    >>> # create an alarm with default properties
    >>> # my_device is the SoCo instance on which the alarm will be played
    >>> alarm = Alarm(my_device)
    >>> print alarm.volume
    20
    >>> print get_alarms()
    set([])
    >>> # save the alarm to the Sonos system
    >>> alarm.save()
    >>> print get_alarms()
    set([<Alarm id:88@15:26:15 at 0x107abb090>])
    >>> # update the alarm
    >>> alarm.recurrence = "ONCE"
    >>> # Save it again for the change to take effect
    >>> alarm.save()
    >>> # Remove it
    >>> alarm.remove()
    >>> print get_alarms()
    set([])

* Methods for browsing the Music library (`#192
  <https://github.com/SoCo/SoCo/pull/192>`_,
  `#203 <https://github.com/SoCo/SoCo/pull/203>`_,
  `#208 <https://github.com/SoCo/SoCo/pull/208>`_) ::

    import soco
    soc = soco.SoCo('...ipaddress..')
    some_album = soc.get_albums()['item_list'][0]
    tracks_in_that_album = soc.browse(some_album)

* Support for full Album Art URIs (`#207
  <https://github.com/SoCo/SoCo/pull/207>`_)

* Support for music queues (`#214 <https://github.com/SoCo/SoCo/pull/214>`_) ::

    queue = soco.get_queue()
    for item in queue:
        print item.title

    print queue.number_returned
    print queue.total_matches
    print queue.update_id

* Support for processing of LastChange events (`#194
  <https://github.com/SoCo/SoCo/pull/194>`_)

* Support for write operations on Playlists (`#198
  <https://github.com/SoCo/SoCo/pull/198>`_)


Improvements
------------

* Improved test coverage (`#159 <https://github.com/SoCo/SoCo/pull/159>`_,
  `#184 <https://github.com/SoCo/SoCo/pull/184>`_)

* Fixes for Python 2.6 support (`#175
  <https://github.com/SoCo/SoCo/pull/175>`_)

* Event-subscriptions can be auto-renewed (`#179
  <https://github.com/SoCo/SoCo/pull/179>`_)

* The ``SoCo`` class can replaced by a custom implementation (`#180
  <https://github.com/SoCo/SoCo/pull/180>`_)

* The cache can be globally disabled (`#180
  <https://github.com/SoCo/SoCo/pull/180>`_)

* Music Library data structures are constructed for DIDL XML content (`#191
  <https://github.com/SoCo/SoCo/pull/191>`_).

* Added previously removed support for PyPy (`#205
  <https://github.com/SoCo/SoCo/pull/205>`_)

* All music library methods (``browse``, ``get_tracks`` etc. `#203
  <https://github.com/SoCo/SoCo/pull/203>`_ and ``get_queue`` `#214
  <https://github.com/SoCo/SoCo/pull/214>`_) now returns container objects
  instead of dicts or lists. The metadata is now available from these container
  objects as named attributes, so e.g. on a queue object you can access the
  size with ``queue.total_matches``.


Backwards Compatability
-----------------------

* Music library methods return container objects instead of dicts and lists (see
  above).  The old way of accessing that metadata (by dictionary type
  indexing), has been deprecated and is planned to be removed 3
  releases after 0.9.


Version 0.8
===========


New Features
------------

* Re-added support for Python 2.6 (`#154
  <https://github.com/SoCo/SoCo/pull/154>`_)

* Added :meth:`SoCo.get_sonos_playlists` (`#114
  <https://github.com/SoCo/SoCo/pull/114>`_)

* Added methods for working with speaker topology

 * :attr:`soco.SoCo.group` retrieves the :class:`soco.groups.ZoneGroup` to
   which the speaker belongs (`#132 <https://github.com/SoCo/SoCo/pull/132>`_).
   The group itself has a :attr:`soco.groups.ZoneGroup.member` attribute
   returning all of its members. Iterating directly over the group is possible
   as well.

 * Speakers can be grouped using :meth:`soco.SoCo.join`
   (`#136 <https://github.com/SoCo/SoCo/pull/136>`_)::

      z1 = SoCo('192.168.1.101')
      z2 = SoCo('192.168.1.102')
      z1.join(z2)

 * :attr:`soco.SoCo.all_zones` and :attr:`soco.SoCo.visible_zones` return all
   and all visible zones, respectively.

 * :attr:`soco.SoCo.is_bridge` indicates if the ``SoCo`` instance represents a
   bridge.

 * :attr:`soco.SoCo.is_coordinator` indicates if the ``SoCo`` instance is a
   group coordinator (`#166 <https://github.com/SoCo/SoCo/pull/166>`_)

* A new :class:`soco.plugins.spotify.Spotify` plugin allows querying and
  playing the Spotify music catalogue (`#119
  <https://github.com/SoCo/SoCo/pull/119>`_)::

      from soco.plugins.spotify import Spotify
      from soco.plugins.spotify import SpotifyTrack
      # create a new plugin, pass the soco instance to it
      myplugin = Spotify(device)
      print 'index: ' + str(myplugin.add_track_to_queue(SpotifyTrack('
          spotify:track:20DfkHC5grnKNJCzZQB6KC')))
      print 'index: ' + str(myplugin.add_album_to_queue(SpotifyAlbum('
          spotify:album:6a50SaJpvdWDp13t0wUcPU')))


* A :class:`soco.data_structures.URI` item can be passed to ``add_to_queue``
  which allows playing music from arbitrary URIs (`#147
  <https://github.com/SoCo/SoCo/pull/147>`_) ::

      import soco
      from soco.data_structures import URI

      soc = soco.SoCo('...ip_address...')
      uri = URI('http://www.noiseaddicts.com/samples/17.mp3')
      soc.add_to_queue(uri)


* A new ``include_invisible`` parameter to :meth:`soco.discover` can be used
  to retrieve invisible speakers or bridges (`#146
  <https://github.com/SoCo/SoCo/pull/146>`_)

* A new ``timeout`` parameter to :meth:`soco.discover`. If no zones are found
  within ``timeout`` seconds ``None`` is returned. (`#146
  <https://github.com/SoCo/SoCo/pull/146>`_)

* Network requests can be cached for better performance (`#131
  <https://github.com/SoCo/SoCo/pull/131>`_).

* It is now possible to subscribe to events of a service using its `subscribe`
  method, which returns a `Subscription` object. To unsubscribe, call the
  `unsubscribe` method on the returned object. (`#121
  <https://github.com/SoCo/SoCo/pull/121>`_, `#130
  <https://github.com/SoCo/SoCo/pull/130>`_)

* Support for reading and setting crossfade (`#165
  <https://github.com/SoCo/SoCo/pull/165>`_)


Improvements
------------

* Performance improvements for speaker discovery (`#146
  <https://github.com/SoCo/SoCo/pull/146>`_)

* Various improvements to the Wimp plugin (`#140
  <https://github.com/SoCo/SoCo/pull/140>`_).

* Test coverage tracking using `coveralls.io <http://coveralls.io/>`_ (`#163
  <https://github.com/SoCo/SoCo/pull/163>`_)


Backwards Compatability
-----------------------

* Queue related use 0-based indexing consistently (`#103
  <https://github.com/SoCo/SoCo/pull/103>`_)

* :meth:`soco.SoCo.get_speakers_ip` is deprecated in favour of
  :meth:`soco.discover` (`#124 <https://github.com/SoCo/SoCo/pull/124>`_)


Version 0.7
===========

New Features
------------

* All information about queue and music library items, like e.g. the
  title and album of a track, are now included in data structure classes
  instead of dictionaries (the classes are available in the
  :ref:`data_structure_mod` sub-module ). This advantages of this
  approach are:

  * The type of the item is identifiable by its class name
  * They have useful ``__str__`` representations and an ``__equals__``
    method
  * Information is available as named attributes
  * They have the ability to produce their own UPnP meta-data (which is
    used by the ``add_to_queue`` method).

  See the Backwards Compatibility notice below.

* A webservice analyzer has been added in ``dev_tools/analyse_ws.py``
  (`#46 <https://github.com/SoCo/SoCo/pull/46>`_).

* The commandline interface has been split into a separate project `socos
  <https://github.com/SoCo/socos>`_. It provides an command line interface on
  top of the SoCo library, and allows users to control their Sonos speakers
  from scripts and from an interactive shell.

* Python 3.2 and later is now supported in addition to 2.7.

* A simple version of the first plugin for the Wimp service has been added
  (`#93 <https://github.com/SoCo/SoCo/pull/93>`_).

* The new ``soco.discover()`` method provides an easier interface for
  discovering speakers in your network. ``SonosDiscovery`` has been deprecated
  in favour of it (see Backwards Compatability below).

* SoCo instances are now singletons per IP address. For any given IP address, there is only one SoCo instance.

* The code for generating the XML to be sent to Sonos devices has been
  completely rewritten, and it is now much easier to add new functionality. All
  services exposed by Sonos zones are now available if you need them (`#48
  <https://github.com/SoCo/SoCo/pull/48>`_).


Backwards Compatability
-----------------------

.. warning:: Please read the section below carefully when upgrading to SoCo
             0.7.

Data Structures
^^^^^^^^^^^^^^^

The move to using **data structure classes** for music item information instead
of dictionaries introduces some **backwards incompatible changes** in the
library (see `#83 <https://github.com/SoCo/SoCo/pull/83>`_). The `get_queue`
and `get_library_information` functions (and all methods derived from the
latter) are affected. In the data structure classes, information like
e.g. the title is now available as named attributes.  This means that by the
update to 0.7 it will also be necessary to update your code like e.g:

.. code-block:: python

    # Version < 0.7
    for item in soco.get_queue():
        print item['title']
    # Version >=0.7
    for item in soco.get_queue():
        print item.title

SonosDiscovery
^^^^^^^^^^^^^^

The ``SonosDiscovery`` class has been deprecated (see `#80
<https://github.com/SoCo/SoCo/pull/80>`_ and `#75
<https://github.com/SoCo/SoCo/issues/75>`_).

Instead of the following

.. code-block:: python

    >>> import soco
    >>> d = soco.SonosDiscovery()
    >>> ips = d.get_speaker_ips()
    >>> for i in ips:
    ...        s = soco.SoCo(i)
    ...        print s.player_name


you should now write

.. code-block:: python

    >>> import soco
    >>> for s in soco.discover():
    ...        print s.player_name



Properties
^^^^^^^^^^

A number of methods have been replaced with properties, to simplify use (see `#62 <https://github.com/SoCo/SoCo/pull/62>`_ )

For example, use

.. code-block:: python

    soco.volume = 30
    soco.volume -=3
    soco.status_light = True

instead of

.. code-block:: python

    soco.volume(30)
    soco.volume(soco.volume()-3)
    soco.status_light("On")


Version 0.6
===========

New features
------------

* **Music library information:** Several methods has been added to get
  information about the music library. It is now possible to get
  e.g. lists of tracks, albums and artists.
* **Raise exceptions on errors:** Several *SoCo* specific exceptions
  has been added. These exceptions are now raised e.g. when *SoCo*
  encounters communications errors instead of returning an error
  codes. This introduces a **backwards incompatible** change in *SoCo*
  that all users should be aware of.

For SoCo developers
-------------------

* **Added plugin framework:** A plugin framework has been added to
  *SoCo*. The primary purpose of this framework is to provide a
  natural partition of the code, in which code that is specific to
  the individual music services is separated out into its own class
  as a plugin. Read more about the plugin framework in :ref:`the docs
  <plugins>`.
* **Added unit testing framework:** A unit testing framework has been
  added to *SoCo* and unit tests has been written for 30% of the
  methods in the ``SoCo`` class. Please consider supplementing any new
  functionality with the appropriate unit tests and fell free to write
  unit tests for any of the methods that are still missing.

Coming next
-----------

* **Data structure change:** For the next version of SoCo it is
  planned to change the way SoCo handles data. It is planned to use
  classes for all the data structures, both internally and for in- and
  output. This will introduce a **backwards incompatible** change and
  therefore users of SoCo should be aware that extra work will be
  needed upon upgrading from version 0.6 to 0.7. The data structure
  changes will be described in more detail in the release notes for
  version 0.7.
