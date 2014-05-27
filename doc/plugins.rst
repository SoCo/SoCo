.. _plugins:

Plugins
=======

Plugins can extend the functionality of SoCo.

Currently the following plugins are inluded in SoCo.

* An Example plugin to show how to write plugins.
* :class:`soco.plugins.spotify.Spotify` for `Spotify <http://spotify.com/>`_
* :class:`soco.plugins.wimp.Wimp` for `WIMP <http://wimpmusic.com/>`_



Creating a Plugin
-----------------

To write a plugin, simply extend the class :class:`soco.plugins.SoCoPlugin`.
The ``__init__`` method of the plugin should accept an :class:`soco.SoCo`
instance as the first positional argument, which it should pass to its
``super`` constructor.

The class :class:`soco.plugins.example.ExamplePlugin` contains an example
plugin implementation.


Using a Plugin
--------------

To use a plugin, it can be loaded and instantiated directly.

.. code-block:: python

    # create a plugin by normal instantiation
    from soco.plugins.example import ExamplePlugin

    # create a new plugin, pass the soco instance to it
    myplugin = ExamplePlugin(soco, 'a user')

    # do something with your plugin
    print 'Testing', myplugin.name
    myplugin.music_plugin_stop()


Alternatively a plugin can also be loaded by its name using
:meth:`soco.plugins.SoCoPlugin.from_name`.

.. code-block:: python

    # get a plugin by name (eg from a config file)
    myplugin = SoCoPlugin.from_name('soco.plugins.example.ExamplePlugin',
                                    soco, 'some user')

    # do something with your plugin
    print 'Testing', myplugin.name
    myplugin.music_plugin_play()
