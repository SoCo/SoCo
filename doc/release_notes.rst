Release notes
*************

Version ?.?? (draft)
===================

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
