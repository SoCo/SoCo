.. _speaker_topologies:

Speaker Topologies
------------------

Sonos speakers can be grouped together, and existing groups can be inspected.

Topology is available from each :class:`soco.SoCo` instance.

.. code-block:: python

    >>> my_player.group
    ZoneGroup(
        uid='RINCON_000E5879136C01400:58',
        coordinator=SoCo("192.168.1.101"),
        members={SoCo("192.168.1.101"), SoCo("192.168.1.102")}
    )

A group of speakers is represented by a :class:`soco.groups.ZoneGroup`.

Zone Group
==========

Each ``ZoneGroup`` contains its coordinator

.. code-block:: python

    >>> my_player.group.coordinator
    SoCo("192.168.1.101")

which is again a :class:`soco.SoCo` instance

.. code-block:: python

    >>> my_player.group.coordinator.player_name
    Kitchen


A ``ZoneGroup`` also contains a set of members.

.. code-block:: python

    >>> my_player.group.members
    {SoCo("192.168.1.101"), SoCo("192.168.1.102")}

For convenience, ``ZoneGroup`` is also a container:

.. code-block:: python

    >>> for player in my_player.group:
    ...   print(player.player_name)
    Living Room
    Kitchen

If you need it, you can get an iterator over all groups on the network:

.. code-block:: python

    >>> my_player.all_groups
    <generator object all_groups at 0x108cf0c30>
