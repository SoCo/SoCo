SoCo
====

SoCo (Sonos Controller) is a Python library that allows you to
control `Sonos speakers`_ programmatically. It was originally created at `Music
Hack Day Sydney`_ by `Rahim Sonawalla`_ and is now developed by a `team of
people`_ at its `GitHub repository`_.

For more background on the project, please see Rahim's `blog post
<http://www.hirahim.com/blog/2012/04/29/dissecting-the-sonos-controller/>`_.

Visit the `SoCo documentation`_ for a more detailed overview of the functionality.

.. image:: https://img.shields.io/pypi/v/soco.svg?style=flat
    :target: https://pypi.org/project/soco/
    :alt: Latest PyPI version

WARNING
-------

    **This warning is outdated.** A new music-services implementation on this
    branch reworks the authentication flow described below and restores most of
    the affected services. see the `Music Services`_ section below for how to use it.

Sonos has changed the way music service authentication works, and **a number of streaming services currently have known issues or cannot be used at all**. Known affected services include Apple Music, Amazon Music, Spotify, and Napster.

Support for these services is an ongoing effort. See the project's `GitHub Issues <https://github.com/SoCo/SoCo/issues>`_ for current status.

Music Services
--------------

A major rework of SoCo's music-services support is in progress on the
`music-services branch <https://github.com/BookCatKid/SoCo/tree/music-services>`_
of this fork. It targets the newer Sonos APIs and re-enables services whose
authentication no longer works through the old flow (Apple Music, Amazon Music,
Spotify, …).

It is **not finished yet**, but most of it works. Everything below imports from
``soco.music_services``, and the old ``MusicService`` API is unchanged and still
available.

Three new building blocks
^^^^^^^^^^^^^^^^^^^^^^^^^

- ``MusicServiceBrowser`` — browse and search any music service using the
  credentials Sonos already stores for your household. No manual token setup is
  needed, and services which use the newer manifest/content-home-page transport
  (not just legacy SMAPI) are supported.
- ``MusicServiceAccountManager`` — add new accounts (OAuth ``DeviceLink`` /
  ``AppLink`` or legacy username/password), re-link and rename existing ones, and
  remove them again.
- ``ConfiguredMusicServiceAccount`` — read the accounts currently configured in
  your household (useful for listing them, and for passing a specific account to
  the browser when several exist).

Browse and search
^^^^^^^^^^^^^^^^^

.. code:: python

    from soco.music_services import MusicServiceBrowser

    # Uses the account already linked to this household.
    browser = MusicServiceBrowser("Apple Music")

    root = browser.get_metadata()       # the root container
    for item in root.items:             # MusicServiceBrowseItem objects
        print(item.title, item.item_id)

    child = browser.get_metadata(root.items[0])   # browse into an item
    tracks = browser.search("tracks", "miles davis")
    for track in tracks.items:
        print(track.title, track.artist)

    browser.play(track)                # play a browsed item

Playback
^^^^^^^^

``MusicServiceBrowser.play`` plays the *player-resolved* way for most services:
streams are resolved by the player itself from the item's type and MIME, so no
credentials ever leave the household (``x-sonosapi-stream:``, ``x-sonos-http:``,
``x-sonosapi-hls-static:``, ...).

Spotify tracks are resolved MIME-aware to ``x-sonos-spotify:`` resources with
the Spotify protocol information and selected account UDN in DIDL metadata.
This is the same ordinary resource path whether ``play`` receives a browsed
item or its raw item id, so equivalent calls do not silently choose different
transport mechanisms::

    browser.play(track)
    browser.play(track.item_id)

This helper does **not** implement Spotify Connect/DirectControl virtual-line-in
(``x-sonos-vli:``) playback. DirectControl has its own session lifecycle and
protocol handling beyond ordinary music-service URI playback, so it is kept
separate from this high-level playback path for now.

Playable service containers must still be browsed into until a normal
player-resolvable item is reached. This keeps the high-level playback helper
on one predictable, provider-aware path.

Presentation map and strings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Most services advertise an XML presentation map describing search categories,
display types, artwork sizes, quality badges, ratings and quick-skip rules, and
(Apple-style services) a JSON manifest that also points at a localized
``strings`` document.  Both are parsed and exposed read-only:

.. code:: python

    pmap = browser.get_presentation_map()     # None if not advertised
    print(pmap.search_variants())             # {category: [(variant, id)]}
    print(pmap.artwork_size_map, pmap.display_types)

    strings = browser.get_strings()           # localized string tables
    print(strings.localized("en-US")["StartStation"])
    # "Start Station"

    resolved = pmap.resolve_strings(strings)  # StringIds -> display text
    print(resolved["menu_item_overrides"])

Add and manage accounts
^^^^^^^^^^^^^^^^^^^^^^^

.. code:: python

    from soco.music_services import MusicServiceAccountManager

    manager = MusicServiceAccountManager("Spotify")
    link = manager.begin_link()         # nothing is changed yet
    # Ask the user to open link.registration_url and authorize in their browser
    # (some services also ask for link.link_code to be entered on the page).
    added = manager.commit_link(link)   # installs the account in the household

    manager.set_nickname(added.account_udn, "Living Room")
    manager.remove_account(added.account_udn)

Anonymous and username/password services are added directly:

.. code:: python

    manager = MusicServiceAccountManager("TuneIn")
    manager.add_credentials()           # anonymous services need no credentials

Example app
^^^^^^^^^^^

The `music-service explorer
<https://github.com/BookCatKid/SoCo/tree/music-services/examples/music_service_explorer>`_
demonstrates every read-only feature (browse, search, metadata) plus an Accounts
tab for onboarding:

.. code:: bash

    pip install -r examples/music_service_explorer/requirements.txt
    python examples/music_service_explorer/app.py   # http://127.0.0.1:5050

Notes
^^^^^

- Browsing configured accounts needs either the ``cryptography`` package or an
  ``openssl`` executable on your system (used to decrypt the account payload
  Sonos sends to the players). Install the dependency explicitly with
  ``pip install soco[music-services]``.
- The new API browses, searches and inspects metadata, and can play a browsed
  item with ``MusicServiceBrowser.play``,
  which builds the player-resolved URI and DIDL metadata and hands them to
  ``SoCo.play_uri``.
- Apple Music accounts already linked to your Sonos system work with the new
  API. Linking a *new* Apple Music account still has to be started from the
  Sonos mobile app; it cannot be completed from a third-party controller.
- Testing against real Sonos setups is very welcome, as is feedback on the API
  design — please open an issue or PR on this fork.

Not a drop-in replacement
^^^^^^^^^^^^^^^^^^^^^^^^^

The new API intentionally does not mirror every legacy ``MusicService`` call:

- Browsing returns the new ``MusicServiceBrowseItem`` / result models rather
  than the legacy ``MusicService`` data structures.
- When a service has several configured accounts you must pick one explicitly
  (``MusicServiceBrowser(service, account=...)``); the browser no longer
  guesses which account to use.
- Playback of browsed content goes through ``play()``, which builds the
  player-resolved ``x-sonos-http:``/``x-sonosapi-stream:`` URI and DIDL
  metadata from the item's type and MIME type rather than the legacy stream
  URIs.

The legacy ``MusicService`` API is unchanged and remains available for code
that depends on it.

Real-system verification
^^^^^^^^^^^^^^^^^^^^^^^^

Unit fixtures cannot establish that an advertised service works end to end, so
live results are recorded separately in
``soco/music_services/browser/VERIFIED.md`` — a per-service matrix of browse,
search, metadata and playback status (✅ works, ❌ broken, 🔒 account required,
⏭️ not exercised), covering every service the household advertises.

That matrix is generated by ``examples/verify_music_services.py``, which walks
every advertised service, tests browsing, searching and metadata on the
configured ones and playback on a chosen speaker, and writes both
``music_services.json`` and ``VERIFIED.md`` into ``soco/music_services/browser/``.
Re-run it against a real household
to refresh and update the results:

.. code:: bash

    python examples/verify_music_services.py

Installation
------------

SoCo requires Python 3.8 or newer.

Use pip:

``pip install soco``


SoCo depends on a number of Python packages. If you use pip to install Soco,
the dependencies will be installed automatically for you. If not, you can inspect
the requirements in the `requirements.txt <https://github.com/SoCo/SoCo/blob/master/requirements.txt>`_
file.


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

    >>> from soco import discover
    >>> for zone in discover():
    ...        print(zone.player_name)
    Living Room
    Kitchen


If you prefer a list to a set:

.. code:: python

    >>> zone_list = list(discover())
    >>> zone_list
    [SoCo("192.168.1.101"), SoCo("192.168.1.102")]
    >>> zone_list[0].mute = True

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
            'https://ia801402.us.archive.org/20/items/TenD2005-07-16.flac16/TenD2005-07-16t10Wonderboy.mp3')

        track = sonos.get_current_track_info()

        print(track['title'])

        sonos.pause()

        # Play a stopped or paused track
        sonos.play()

Support
-------

If you need support for SoCo, feel free to open an issue or discussion on the `SoCo GitHub repository <https://github.com/SoCo/SoCo>`_.

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

-  Play, Pause, Stop
-  Next track, Previous track
-  Volume get and set
-  Mute (or unmute)
-  Get current transport information (if speaker is
   playing, paused or stopped)
-  Get information about the currently playing track

   -  Track title
   -  Artist
   -  Album
   -  Album Art (if available)
   -  Track length
   -  Duration played (for example, 30 seconds into a 3 minute song)
   -  Playlist position (for example, item 5 in the playlist)
   -  Track URI

-  Receive events when the player state changes
-  Search for and play music items:

   -  Local music library
   -  Webradio via TuneIn and music services (see the `Music Services`_ section above for current status)
   -  Saved Sonos favorites, favorite radio stations and shows

-  Switch the speaker’s source to line-in or TV input (if the Zone Player
   supports it)
-  Manage the Sonos queue:

   -  Get the items in the queue
   -  Add items to the queue
   -  Clear the queue
   -  Play a specific song from the queue

-  Join or unjoin speakers from a group
-  Put all Sonos speakers in a network into “party mode”.

-  Get or set alarms
-  Get or set sleep timers

-  Enable or disable surround speakers or subwoofer
-  Get information regarding a home theater setup:

   - If surround speakers or a subwoofer are paired
   - Which audio channel a given speaker handles

-  Get or set the speaker’s bass and treble EQ
-  Toggle the speaker’s loudness compensation, night mode and dialog mode
-  Toggle the white status light on the unit
-  Get the speaker’s information

   -  Zone Name
   -  Zone Icon
   -  UID (usually something like RINCON\_XXXXXXXXXXXXXXXXX)
   -  Serial Number
   -  Software version
   -  Hardware version
   -  MAC Address

-  Set the speaker’s Zone Name
-  Start a music library update and determine if one is in progress

SoCo also supports lower level access from Python to all Sonos services
(e.g. ContentDirectory or RenderingControl).


Related Projects
----------------

**Socos** is a command line tool for controlling Sonos devices. It is developed
in conjunction with Soco, but in a `separate repository <https://github.com/SoCo/socos>`_.

**SoCo-CLI** (`soco-cli <https://github.com/avantrec/soco-cli>`_) is a powerful and
fully-featured command line tool suitable for use in scripts, scheduled tasks, etc. It
supports time-based and state-based actions, and repeated commands using loops. Audio
files on the local filesystem can be played back directly on Sonos from the command line.
Multi-household Sonos systems are supported.

Older Projects
^^^^^^^^^^^^^^

More of a Ruby fan? `Sam Soffes`_ built a `Ruby gem`_, though it is no longer maintained.

`Joel Björkman`_ built SoCo-Tk, a Sonos Controller GUI for Linux, though it is no longer maintained:
https://github.com/labero/SoCo-Tk.


License
-------

SoCo is released under the `MIT license`_.


.. _Sonos speakers: http://www.sonos.com/system/
.. _Music Hack Day Sydney: http://sydney.musichackday.org/2012/
.. _blog post: http://www.hirahim.com/blog/2012/04/29/dissecting-the-sonos-controller/
.. _Sam Soffes: https://github.com/soffes
.. _Ruby gem: https://github.com/soffes/sonos
.. _Joel Björkman: https://github.com/labero
.. _MIT license: http://www.opensource.org/licenses/mit-license.php
.. _Rahim Sonawalla: https://github.com/rahims/SoCo
.. _GitHub repository: https://github.com/SoCo/SoCo
.. _team of people: https://github.com/SoCo/SoCo/blob/master/AUTHORS.rst
.. _SoCo documentation: https://soco.readthedocs.io/en/latest/
