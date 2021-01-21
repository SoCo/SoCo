"""This module contains configuration variables.

They may be set by your code as follows::

    from soco import config
    ...
    config.VARIABLE = value
"""


SOCO_CLASS = None
"""The class object to use when `SoCo` instances are created.

Specify the actual callable class object here, not a string. If `None`,
the default SoCo class will be used. Must be set before any instances are
created, or it will have unpredictable effects.
"""


CACHE_ENABLED = True
"""Is the cache enabled?

If `True` (the default), some caching of network requests will take place.

See also:
    The :mod:`soco.cache` module.
"""


EVENT_ADVERTISE_IP = None
"""The IP on which to advertise to Sonos.

The default of None means that the relevant IP address will be detected
automatically.

See also:
    The :mod:`soco.events_base` module.
"""

EVENT_LISTENER_IP = None
"""The IP on which the event listener listens.

The default of None means that the relevant IP address will be detected
automatically.

See also:
    The :mod:`soco.events_base` module.
"""


EVENT_LISTENER_PORT = 1400
"""The port on which the event listener listens.

The default is 1400. You must set this before subscribing to any events.

See also:
    The :mod:`soco.events_base` module.
"""

EVENTS_MODULE = None
"""The events module to be used by the :mod:`soco.services` module.

The default of None means the :mod:`soco.events` module will be used.

See also:
    The :mod:`soco.events` and :mod:`soco.events_twisted` modules.
"""
