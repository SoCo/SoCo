# pylint: disable=R0201,E0711

# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance

"""This is the __init__ module for the plugins.

It contains the base class for all plugins
"""

import logging
import importlib


_LOG = logging.getLogger(__name__)


class SoCoPlugin:

    """The base class for SoCo plugins."""

    def __init__(self, soco):
        cls = self.__class__.__name__
        _LOG.info("Initializing SoCo plugin %s", cls)
        self.soco = soco

    @property
    def name(self):
        """Human-readable name of the plugin"""
        raise NotImplementedError("Plugins should overwrite the name property")

    @classmethod
    def from_name(cls, fullname, soco, *args, **kwargs):
        """Instantiate a plugin by its full name."""

        _LOG.info("Loading plugin %s", fullname)

        parts = fullname.split(".")
        modname = ".".join(parts[:-1])
        clsname = parts[-1]

        mod = importlib.import_module(modname)
        class_ = getattr(mod, clsname)

        _LOG.info("Loaded class %s", class_)

        return class_(soco, *args, **kwargs)
