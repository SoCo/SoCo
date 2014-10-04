# pylint: disable=R0201,E0711

"""This is the __init__ module for the plugins. It contains the base class for
all plugings
"""

import logging
import importlib


_log = logging.getLogger(__name__)


class SoCoPlugin(object):
    """ The base class for SoCo plugins """

    def __init__(self, soco):
        cls = self.__class__.__name__
        _log.info('Initializing SoCo plugin {cls}'.format(cls=cls))
        self.soco = soco

    @property
    def name(self):
        """ human-readable name of the plugin """
        raise NotImplemented('Plugins should overwrite the name property')

    @classmethod
    def from_name(cls, fullname, soco, *args, **kwargs):
        """ Instantiate a plugin by its full name """

        _log.info('Loading plugin {fullname}'.format(fullname=fullname))

        parts = fullname.split('.')
        modname = '.'.join(parts[:-1])
        clsname = parts[-1]

        mod = importlib.import_module(modname)
        cls = getattr(mod, clsname)

        _log.info('Loaded class {cls}'.format(cls=cls))

        return cls(soco, *args, **kwargs)
