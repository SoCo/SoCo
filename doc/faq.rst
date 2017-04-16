.. _faq:

Frequently Asked Questions
==========================

This page contains answers to a few commonly asked questions.

.. _faq_no_play_uri_from_music_service:

Why can't I play a URI from music service X with the :meth:`~soco.core.SoCo.play_uri` method?
---------------------------------------------------------------------------------------------

The :meth:`~soco.core.SoCo.play_uri` method is only for playing URI's
with un-restricted access such as podcasts, certain radion stations or
sound clips on webpages. In short, the
:meth:`~soco.core.SoCo.play_uri` method is for anything that will play
as a sound file in your browser without authentication.

To play music from a music service, you will need to go via the
:mod:`~soco.music_services.music_service` module. Here you can search
or browse to obtain music service items, which can be added to the
queue and played.

Why can't I add a URI from music service X to the queue with the :meth:`~soco.core.SoCo.add_uri_to_queue` method?
-----------------------------------------------------------------------------------------------------------------

See :ref:`faq_no_play_uri_from_music_service`.

Can I make my Sonos® speaker play music from my local hard drive with SoCo?
---------------------------------------------------------------------------

At the face of it, *no*. Sonos® devices can only play music that is
available on the network i.e. can be reached via a URI. So you have
two options:

1. You can share your local music folder onto the network and add it
   to the Sonos® library as a part of your music collection, which can
   then be searched, browsed and played with SoCo.
2. You can cheat and make Python serve the files on the fly and play
   them as URIs. The `play local files
   <https://github.com/SoCo/SoCo/blob/master/examples/play_local_files/play_local_files.py>`_ example shows one way in which this can be accomplished.

 .. warning:: Note that this example is meant as a convenient way get
       started, but that no security precautions has been taken to
       e.g. prevent serving other files out into the local
       network. Take appropriate actions if this is a concern.

How can I save, then restore the previous playing Sonos state ?
---------------------------------------------------------------

This is useful for scenarios such as when you want to switch to radio,
an announcement or doorbell sound and then back to what was playing previously.
Documentation of the Snapshot :mod:`~soco.snapshot` module.

SoCo provides a snapshot module that captures the current state of a player and
then when requested re-instates that state. Examples of it's use are:

 * `basic snap example  <https://github.com/SoCo/SoCo/blob/master/examples/snapshot/basic_snap.py>`_
 * `multi zone example  <https://github.com/SoCo/SoCo/blob/master/examples/snapshot/multi_zone_snap.py>`_
