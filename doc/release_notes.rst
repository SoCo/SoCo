Release notes
*************

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
