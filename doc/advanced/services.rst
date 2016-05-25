.. _upnp_services:

UPnP Services
=============

Sonos devices offer several UPnP services which are accessible from classes in
the :mod:`soco.services` module.

* :class:`soco.services.AlarmClock`
* :class:`soco.services.MusicServices`
* :class:`soco.services.DeviceProperties`
* :class:`soco.services.SystemProperties`
* :class:`soco.services.ZoneGroupTopology`
* :class:`soco.services.GroupManagement`
* :class:`soco.services.QPlay`
* :class:`soco.services.ContentDirectory`
* :class:`soco.services.MS_ConnectionManager`
* :class:`soco.services.RenderingControl`
* :class:`soco.services.MR_ConnectionManager`
* :class:`soco.services.AVTransport`
* :class:`soco.services.Queue`
* :class:`soco.services.GroupRenderingControl`

All services take a :class:`soco.SoCo` instance as their first parameter.

Inspecting
----------

To get a list of supported actions you can call the service's
:meth:`soco.services.Service.iter_actions`. It yields the service's actions
with their in_arguments (ie parameters to pass to the action) and out_arguments
(ie returned values).

Each action is an :class:`soco.services.Action` namedtuple, consisting
of ``action_name`` (a string), ``in_args`` (a list of
:class:`soco.services.Argument` namedtuples consisting of ``name`` and
``argtype``), and out_args (ditto), eg:

Events
------

You can subscribe to the events of a service using the
:meth:`soco.services.Service.subscribe` method. See :ref:`events` for details.
