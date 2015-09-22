.. _plugins:

Plugins
=======

Plugins can extend the functionality of SoCo.


Creating a Plugin
-----------------

To write a plugin, simply extend the class ``soco.plugins.SoCoPlugin``.  The
``__init__`` method of the plugin should accept an ``SoCo`` instance as the
first positional argument, which it should pass to its ``super`` constructor.

The class ``soco.plugins.example.ExamplePlugin`` contains an example plugin
implementation.


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
``SoCoPlugin.from_name()``.

.. code-block:: python

    # get a plugin by name (eg from a config file)
    myplugin = SoCoPlugin.from_name('soco.plugins.example.ExamplePlugin',
                                    soco, 'some user')

    # do something with your plugin
    print 'Testing', myplugin.name
    myplugin.music_plugin_play()



The ``SoCoPlugin`` class
------------------------

.. autoclass:: soco.plugins.SoCoPlugin
   :members:
   :noindex:
