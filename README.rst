SoCo
====

SoCo (Sonos Controller) is a simple Python class that allows you to
programmatically control `Sonos speakers`_. It was originally created at `Music
Hack Day Sydney`_ by `Rahim Sonawalla`_ and is now developed by a `team of
people`_ at its `GitHub repository`_

For more background on the project, please see Rahim's `blog post
<http://www.hirahim.com/blog/2012/04/29/dissecting-the-sonos-controller/>`_.

.. image:: https://travis-ci.org/SoCo/SoCo.svg?branch=master
   :target: https://travis-ci.org/SoCo/SoCo
   :alt: Build Status

.. image:: https://img.shields.io/requires/github/SoCo/SoCo/master.svg?style=flat
   :target: https://requires.io/github/SoCo/SoCo/requirements/?branch=master
   :alt: Requirements Status

.. image:: https://pypip.in/download/soco/badge.svg?style=flat
    :target: https://pypi.python.org/pypi/soco/
    :alt: Latest PyPI version

.. image:: https://pypip.in/version/soco/badge.svg?style=flat
    :target: https://pypi.python.org/pypi/soco/
    :alt: Number of PyPI downloads

Installation
------------

SoCo requires Python 2.7, or 3.2 or newer.

Use pip:

``pip install soco``


SoCo depends on the `Requests`_ HTTP library. If you use pip to install Soco,
Requests will be installed automatically for you. If not, you can use:

``pip install requests``


Basic Usage
-----------

You can interact with a Sonos Zone Player through a SoCo object. If you know
the IP address of a Zone Player, you can create a SoCo object directly:

.. code:: python

    >>> from soco import SoCo
    >>> my_zone = SoCo('192.168.1.101')
    >>> my_zone.player_name
    Kitchen
    >>> my_zone.status_light = True
    >>> my_zone.volume = 6


But perhaps the easiest way is to use the module-level `discover` function.
This will find all the Zone Players on your network, and return a python
set containing them:

.. code:: python

    >>> import soco
    >>> for zone in soco.discover():
    ...        print zone.player_name
    Living Room
    Kitchen


If you prefer a list to a set:

.. code:: python

    >>> zone_list = list(soco.discover())
    >>> zone_list
    [SoCo("192.168.1.101"), SoCo("192.168.1.102")]
    >>> zone_list[0].mute()

Of course, you can also play music!

.. code:: python

    #!/usr/bin/env python
    from soco import SoCo

    if __name__ == '__main__':
        sonos = SoCo('192.168.1.102') # Pass in the IP of your Sonos speaker
        # You could use the discover function instead, if you don't know the IP

        # Pass in a URI to a media file to have it streamed through the Sonos 
        # speaker
        sonos.play_uri(
            'http://archive.org/download/TenD2005-07-16.flac16/TenD2005-07-16t10Wonderboy_64kb.mp3')

        track = sonos.get_current_track_info()

        print track['title']

        sonos.pause()

        # Play a stopped or paused track
        sonos.play()


Example Applications
--------------------

To show off what can be made with SoCo, a simple web application is included in
the ``examples`` folder.

.. figure:: https://github.com/SoCo/SoCo/raw/master/examples/webapp/screenshot.png
   :alt: Screenshot of web app

   Screenshot of web app


Features
--------

SoCo supports the following controls amongst others:

-  Play
-  Pause
-  Stop
-  Next track
-  Previous track
-  Get current transport information(if speaker is
   playing,paused,stopped)
-  Get information about the currently playing track

   -  Track title
   -  Artist
   -  Album
   -  Album Art (if available)
   -  Track length
   -  Duration played (for example, 30 seconds into a 3 minute song)
   -  Playlist position (for example, item 5 in the playlist)
   -  Track URI

-  Mute (or unmute) the speaker
-  Get or set the speaker volume
-  Get or set the speaker’s bass EQ
-  Get or set the speaker’s treble EQ
-  Toggle the speaker’s loudness compensation
-  Turn on (or off) the white status light on the unit
-  Switch the speaker’s source to line-in or TV input (if the Zone Player
   supports it)
-  Get the speaker’s information

   -  Zone Name
   -  Zone Icon
   -  UID (usually something like RINCON\_XXXXXXXXXXXXXXXXX)
   -  Serial Number
   -  Software version
   -  Hardware version
   -  MAC Address

-  Set the speaker’s Zone Name
-  Find all the Sonos speakers in a network.
-  Put all Sonos speakers in a network into “party mode”.
-  “Unjoin” speakers from a group.
-  Manage the Sonos queue (get the items in it, add to it, clear it,
   play a specific song from it)
-  Get the saved favorite radio stations and shows (title and stream
   URI)
-  Search for and play item from your music library
-  Start a music library update and determine if one is in progress

SoCo also supports lower level access from Python to all Sonos services (eg
Alarms)


Related Projects
----------------

Socos is a command line tool for controlling Sonos devices. It is developed
in conjunction with Soco, but in a `separate repository <https://github.com/SoCo/socos>`_.

More of a Ruby fan? Not a problem, `Sam Soffes`_ is building out an
awesome `Ruby gem`_.

Looking for a GUI that’s more than just a sample project? `Joel
Björkman`_ is building a Sonos Controller GUI–great for folks on Linux
where there isn’t an official Sonos Controller application! Find, fork,
and contribute to it here: https://github.com/labero/SoCo-Tk.


Google Group
------------

There is a Soco group over at `Google Groups`_.  Feel free to drop in.


License
-------

SoCo is released under the `MIT license`_.


.. _Sonos speakers: http://www.sonos.com/system/
.. _Music Hack Day Sydney: http://sydney.musichackday.org/2012/
.. _blog post: http://www.hirahim.com/blog/2012/04/29/dissecting-the-sonos-controller/
.. _Requests: http://docs.python-requests.org/
.. _Sam Soffes: https://github.com/soffes
.. _Ruby gem: https://github.com/soffes/sonos
.. _Joel Björkman: https://github.com/labero
.. _MIT license: http://www.opensource.org/licenses/mit-license.php
.. _Rahim Sonawalla: https://github.com/rahims/SoCo
.. _GitHub repository: https://github.com/SoCo/SoCo
.. _team of people: https://github.com/SoCo/SoCo/blob/master/AUTHORS.rst
.. _Google Groups: https://groups.google.com/forum/#!forum/python-soco
