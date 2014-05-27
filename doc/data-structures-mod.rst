.. _data_structure_mod:

Data Structures
===============

Introduction
------------

The data structures are used to represent playable items like e.g. a
music track or playlist. The data structure classes are documented in
the sections below and the rest of this section contains a more
thorough introduction.

To expand a bit, the :mod:`soco.data_structures` module consist of a
hierarchy of classes that represent different music information
items. This could be a "real" item such as a music library track,
album or genre or an abstract item such as a music library item.

The main advantages of using classes as apposed to e.g. dicts to
contain the information are:

* They are easy to identify
* It is possibly to define and agree on certain abilities such as
  what is the criteria for two tracks being equal
* Certain functionality for these information object, such as
  producing the XML that is needed for the UPnP communication can be
  attached to the elements themselves.

Many of the items have a lot in common and therefore has shared
functionality. This has been implemented by means of inheritance, in
such a way that common functionality is always pulled up the
inheritance hierarchy to the highest point that have this
functionality in common. The hierarchy is illustrated in figure
:ref:`the figure below <figure-inheritance>`. The black lines are the
lines of inheritance, going from the top down.

.. _figure-inheritance:
.. inheritance-diagram:: soco.data_structures

All data structures are :py:class:`music information items
<.MusicInfoItem>`. Three classes inherit from this top level class;
the :py:class:`queue item <.QueueItem>`, the :py:class:`music library
item <.MusicLibraryItem>` and the music service item

There are 8 types of :py:class:`music library items
<.MusicLibraryItem>`, represented by the 8 classes that inherit from
it. From these classes all information items are available as named
properties. All of these items contains a :py:attr:`title
<.MusicLibraryItem.title>`, a :py:attr:`URI <.MusicLibraryItem.uri>`
and a :py:attr:`UPnP class <.MusicLibraryItem.item_class>`, so these
items are defined in the :py:class:`.MusicLibraryItem` class and
inherited by them all. For most items the ``ID`` can be extracted from
the URI in the same way, so therefore it is defined in
:py:attr:`.MusicLibraryItem.item_id` and the few classes
(:py:class:`.MLTrack`, :py:class:`.MLPlaylist`) that extract the ID
differently from the URI then overrides this property. Besides the
information items that they all share, :py:class:`.MLTrack` and
:py:class:`.MLAlbum` define some extra fields such as :py:attr:`album
<.MLTrack.album>`, :py:attr:`album_art_uri <.MLTrack.album_art_uri>`
and :py:attr:`creator <.MLTrack.creator>`.

One of the more important attributes is :py:attr:`didl_metadata
<.MusicLibraryItem.didl_metadata>`. It is used to produce the metadata
that is sent to the Sonos® units. This metadata is created in an
almost identical way, which is the reason that it is implemented in
:py:class:`.MusicLibraryItem`. It uses the URI (through the ID), the
UPnP class and the title that the items are instantiated with and the
two class variables ``parent_id`` and ``_translation``. ``parent_id``
must be over written in each of the sub classes, whereas that is only
necessary for ``_translation`` if the information fields are different
from the default.
