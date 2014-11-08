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

All data structures are subclasses of the abstract :py:class:`Didl Object item <soco.data_structures.DidlObject>` class. You should never need to instantiate this directly. The subclasses are divided into :py:class:`Containers <soco.data_structures.DidlContainer>` and :py:class:`Items <soco.data_structures.DidlItem>`. In general, :py:class:`Containers <soco.data_structures.DidlContainer>` are things, like playlists, which are intended to contain other items.

At the bottom of the class hierarchy are 10 types of :py:class:`DIDL items <.DidlObject>`. On each of these classes, relevant metadata items
are available as attributes (though they may be implemented as properties).
Each has a :py:attr:`title <.DidlObject.title>`, a :py:attr:`URI <.DidlObject.uri>`, an :py:attr:`item id <.DidlObject.item_id>` and
a :py:attr:`UPnP class <.DidlObject.item_class>`. Some have other
attributes. For example, :py:class:`.DidlMusicTrack` and :py:class:`.DidlMusicAlbum` have
some extra fields such as :py:attr:`album <.DidlMusicTrack.album>`,
:py:attr:`album_art_uri <.DidlMusicTrack.album_art_uri>` and :py:attr:`creator <.DidlMusicTrack.creator>`.

One of the more important attributes which each class has is
:py:attr:`didl_metadata <.DidlObject.didl_metadata>`. It is used to
produce the metadata that is sent to the Sonos® units in the form of XML. This
metadata is created in an almost identical way for each class, which is why it
is implemented in :py:class:`.DidlObject`. It uses the URI, the UPnP
class and the title that the items are instantiated with, along with the two
class variables ``parent_id`` and ``_translation``.

Functions
=========

.. autofunction:: soco.data_structures.ns_tag
.. autofunction:: soco.data_structures.get_ml_item


DidlObject
================

.. autoclass:: soco.data_structures.DidlObject
   :members:
   :special-members:
   :show-inheritance:

   .. automethod:: soco.data_structures.DidlObject.__init__
   .. automethod:: soco.data_structures.DidlObject.__eq__
   .. automethod:: soco.data_structures.DidlObject.__repr__
   .. automethod:: soco.data_structures.DidlObject.__str__


DidlContainer
===========

.. autoclass:: soco.data_structures.DidlContainer
   :members:
   :special-members:
   :show-inheritance:

DidlItem
=======

.. autoclass:: soco.data_structures.DidlItem
   :members:
   :special-members:
   :show-inheritance:


DidlMusicTrack
=======

.. autoclass:: soco.data_structures.DidlMusicTrack
   :members:
   :special-members:
   :show-inheritance:

DidlMusicAlbum
============

.. autoclass:: soco.data_structures.DidlMusicAlbum
   :members:
   :special-members:
   :show-inheritance:

DidlMusicArtist
========

.. autoclass:: soco.data_structures.DidlMusicArtist
   :members:
   :special-members:
   :show-inheritance:

DidlMusicGenre
============

.. autoclass:: soco.data_structures.DidlMusicGenre
   :members:
   :special-members:
   :show-inheritance:

DidlAlbumList
===========

.. autoclass:: soco.data_structures.DidlAlbumList
   :members:
   :special-members:
   :show-inheritance:


DidlComposer
==========

.. autoclass:: soco.data_structures.DidlComposer
   :members:
   :special-members:
   :show-inheritance:

DidlPlaylistContainer
==========

.. autoclass:: soco.data_structures.DidlPlaylistContainer
   :members:
   :special-members:
   :show-inheritance:


DidlAudioBroadcast
================

.. autoclass:: soco.data_structures.DidlAudioBroadcast
   :members:
   :special-members:
   :show-inheritance:


DidlContainer
=======

.. autoclass:: soco.data_structures.DidlContainer
   :members:
   :special-members:
   :show-inheritance:

