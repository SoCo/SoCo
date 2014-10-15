.. _data_structure_mod:

The ``data_structures`` sub module
**********************************

Introduction
============

The majority of the data structures in this module are used to represent the
metadata for music items, such as music tracks, genres and playlists. The data
structure classes are documented in the sections below and the rest of this
section contains a more thorough introduction.

Many music related items have a lot of metadata in common. For example, a music
track and an album may both have artist and title metadata. It is possible
therefore to derive a hierarchy of items, and to implement them as a class
structure. The hierarchy which Sonos has adopted is represented by the `DIDL
Lite xml schema <http://www.upnp.org/schemas/av/didl-lite-v2.xsd>`_ (DIDL stands for 'Digital Item Description Language'. For more details, see the
`UPnP specifications
(PDF) <http://www.upnp.org/specs/av/UPnP-av-ContentDirectory-v1-Service.pdf>`_.

In the ``data_structures`` module, each class represents a particular DIDL-Lite
object and is illustrated in :ref:`the figure below <figure-inheritance>`. The
black lines are the lines of inheritance, going from the top down.

.. _figure-inheritance:
.. inheritance-diagram:: soco.data_structures

All data structures are subclasses of the abstract :py:class:`music library item <soco.data_structures.MusicLibraryItem>` class. You should never need to instantiate this directly. The subclasses are divided into :py:class:`ML Containers <soco.data_structures.MLContainer>` and :py:class:`ML Items <soco.data_structures.MLItem>`. In general, :py:class:`ML Containers <soco.data_structures.MLContainer>` are things, like playlists, which are intended to contain other items.

At the bottom of the class hierarchy are 10 types of :py:class:`music library items <.MusicLibraryItem>`. On each of these classes, relevant metadata items
are are available as attributes (though they may be implemented as properties).
Each has a :py:attr:`title <.MusicLibraryItem.title>`, a :py:attr:`URI <.MusicLibraryItem.uri>`, an :py:attr:`item id <.MusicLibraryItem.item_id>` and
a :py:attr:`UPnP class <.MusicLibraryItem.item_class>`. Some have other
attributes. For example, :py:class:`.MLTrack` and :py:class:`.MLMusicAlbum` have
some extra fields such as :py:attr:`album <.MLTrack.album>`,
:py:attr:`album_art_uri <.MLTrack.album_art_uri>` and :py:attr:`creator <.MLTrack.creator>`.

One of the more important attributes which each class has is
:py:attr:`didl_metadata <.MusicLibraryItem.didl_metadata>`. It is used to
produce the metadata that is sent to the Sonos® units in the form of xml. This
metadata is created in an almost identical way for each class, which is why it
is implemented in :py:class:`.MusicLibraryItem`. It uses the URI, the UPnP
class and the title that the items are instantiated with, along with the two
class variables ``parent_id`` and ``_translation``.

Functions
=========

.. autofunction:: soco.data_structures.ns_tag
.. autofunction:: soco.data_structures.get_ml_item


MusicLibraryItem
================

.. autoclass:: soco.data_structures.MusicLibraryItem
   :members:
   :special-members:
   :show-inheritance:
   
   .. automethod:: soco.data_structures.MusicLibraryItem.__init__
   .. automethod:: soco.data_structures.MusicLibraryItem.__eq__
   .. automethod:: soco.data_structures.MusicLibraryItem.__repr__
   .. automethod:: soco.data_structures.MusicLibraryItem.__str__


MLContainer
===========

.. autoclass:: soco.data_structures.MLContainer
   :members:
   :special-members:
   :show-inheritance:
   
MLItem
=======

.. autoclass:: soco.data_structures.MLItem
   :members:
   :special-members:
   :show-inheritance:


MLTrack
=======

.. autoclass:: soco.data_structures.MLTrack
   :members:
   :special-members:
   :show-inheritance:

MLMusicAlbum
============

.. autoclass:: soco.data_structures.MLMusicAlbum
   :members:
   :special-members:
   :show-inheritance:

MLArtist
========

.. autoclass:: soco.data_structures.MLArtist
   :members:
   :special-members:
   :show-inheritance:

MLMusicGenre
============

.. autoclass:: soco.data_structures.MLMusicGenre
   :members:
   :special-members:
   :show-inheritance:

MLAlbumList
===========

.. autoclass:: soco.data_structures.MLAlbumList
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


MLAudioBroadcast
================

.. autoclass:: soco.data_structures.MLAudioBroadcast
   :members:
   :special-members:
   :show-inheritance:


MLShare
=======

.. autoclass:: soco.data_structures.MLShare
   :members:
   :special-members:
   :show-inheritance:

