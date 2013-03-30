import logging
import importlib

logger = logging.getLogger(__name__)


class SoCoPlugin(object):
    """ The base class for SoCo plugins """

    def __init__(self, soco):
        logger.info('Initializing SoCo plugin {cls}'.format(
            cls=self.__class__.__name__)
        )
        self.soco = soco


    @property
    def name(self):
        """ human-readable name of the plugin """
        raise NotImplemented('Plugins should overwrite the name property')


    @classmethod
    def from_name(cls, fullname, soco, *args, **kwargs):
        """ Instantiate a plugin by its full name """

        logger.info('Loading plugin {fullname}'.format(fullname=fullname))

        parts = fullname.split('.')
        modname = '.'.join(parts[:-1])
        clsname = parts[-1]

        mod = importlib.import_module(modname)
        cls = getattr(mod, clsname)

        logger.info('Loaded class {cls}'.format(cls=cls))

        return cls(soco, *args, **kwargs)
