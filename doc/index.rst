.. soco documentation master file, created by
   sphinx-quickstart on Mon Sep 14 08:03:37 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to SoCo's documentation!
================================

SoCo (Sonos Controller) is a high level Python 3 library to control your
`Sonos <www.sonos.com>`_ ® speakers with::

    # Import soco and get a SoCo instance
    import soco
    device = soco.discovery.any_soco()

    # Get all albums from the music library that contains the word "Black"
    # and add them to the queue
    albums = device.music_library.get_albums(search_term='Black')
    for album in albums:
        print('Added:', album.title)
	device.add_to_queue(album)

    # Dial up the volume (just a bit) and play
    device.volume += 10
    device.play()

To get up and running quickly with *SoCo*, start by reading the
:ref:`getting started <getting_started>` page, with :ref:`installation
instructions <installation>` and a small :ref:`tutorial <tutorial>`
and then wet your appetite with the :ref:`micro examples
<examples>`. Then optionally follow up with any of the advanced topics
that pique your interest: :ref:`speaker_topologies`, :ref:`events` and
:ref:`upnp_services`. Finally dive into the :ref:`the full module
reference documentation <module_reference>`.

If you have a question, start by consulting the :ref:`FAQ <faq>`. If
your question remains unanswered, post a question in the `SoCo/SoCo
Gitter chat room <https://gitter.im/SoCo/SoCo>`_ or in the `SoCo
Google group <https://groups.google.com/forum/#!forum/python-soco>`_.

If you are interested in participating in the development, plase read :ref:`the
development documentation <development_topics>` and `file a bug
<https://github.com/SoCo/SoCo/issues>`_ or `make a pull request
<https://github.com/SoCo/SoCo/pulls>`_ on `Github
<https://github.com/SoCo/SoCo>`_.

Contents
--------

.. toctree::
   :maxdepth: 4
   :caption: User Documentation

   getting_started
   examples
   faq
   plugins
   authors

.. toctree::
   :maxdepth: 2
   :caption: In depth topics

   advanced/index
	     
.. toctree::
   :maxdepth: 3
   :caption: API documentation

   api/soco

.. toctree::
   :maxdepth: 2
   :caption: Release Notes

   releases/index

.. toctree::
   :maxdepth: 3
   :caption: Development Topics

   development/index


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. _freenode: https://freenode.net/
