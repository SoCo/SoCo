.. _data_structure_mod:

The ``data_structures`` sub module
**********************************

Introduction
============

The data structures are used to represent playable items like e.g. a
music track or playlist. The data structure classes are documented in
the sections below and the rest of this section contains a more
thorough introduction.

To expand a bit, the ``data_structures`` sub-module consist of a
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
:ref:`the figure below <figure-inheritance>`, where red boxes
represent items that are not yet implemented, green boxes are abstract
items and blue are real items. The black lines are the lines of
inheritance, going from the top down.

.. _figure-inheritance:
.. inheritance-diagram:: soco.data_structures 

;;.. image:: graphics/data_structures.png

All data structures are :py:class:`playable items
<.PlayableItem>`. They are then split up into :py:class:`queueable
items<.QueueableItem>` and single play items. :py:class:`Queueable
items <.QueueableItem>` are all the "real" :py:class:`music library
items <.MusicLibraryItem>` and music service items such as tracks,
albums and playlists.

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

Functions
=========

.. autofunction:: soco.data_structures.ns_tag
.. autofunction:: soco.data_structures.get_ml_item

PlayableItem
============

.. autoclass:: soco.data_structures.PlayableItem
   :members:
   :show-inheritance:

   .. automethod:: soco.data_structures.PlayableItem.__init__
   .. automethod:: soco.data_structures.PlayableItem.__eq__
   .. automethod:: soco.data_structures.PlayableItem.__repr__
   .. automethod:: soco.data_structures.PlayableItem.__str__


QueueableItem
=============

.. autoclass:: soco.data_structures.QueueableItem
   :members:
   :special-members:
   :show-inheritance:

MusicLibraryItem
================

.. autoclass:: soco.data_structures.MusicLibraryItem
   :members:
   :special-members:
   :show-inheritance:

MLTrack
=======

.. autoclass:: soco.data_structures.MLTrack
   :members:
   :special-members:
   :show-inheritance:

MLAlbum
=======

.. autoclass:: soco.data_structures.MLAlbum
   :members:
   :special-members:
   :show-inheritance:

MLArtist
========

.. autoclass:: soco.data_structures.MLArtist
   :members:
   :special-members:
   :show-inheritance:

MLAlbumArtist
=============

.. autoclass:: soco.data_structures.MLAlbumArtist
   :members:
   :special-members:
   :show-inheritance:

MLGenre
=======

.. autoclass:: soco.data_structures.MLGenre
   :members:
   :special-members:
   :show-inheritance:

MLComposer
==========

.. autoclass:: soco.data_structures.MLComposer
   :members:
   :special-members:
   :show-inheritance:

MLPlaylist
==========

.. autoclass:: soco.data_structures.MLPlaylist
   :members:
   :special-members:
   :show-inheritance:

MLShare
=======

.. autoclass:: soco.data_structures.MLShare
   :members:
   :special-members:
   :show-inheritance:

QueueItem
=========

.. autoclass:: soco.data_structures.QueueItem
   :members:
   :special-members:
   :show-inheritance:
