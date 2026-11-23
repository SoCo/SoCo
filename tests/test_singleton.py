"""Tests for the SoCoSingletonBase and _ArgsSingleton classes in core."""

from unittest import mock

from soco import SoCo, soco_reset
from soco.core import _SocoSingletonBase as Base


class ASingleton(Base):
    def __init__(self, arg):
        pass


class AnotherSingleton(ASingleton):
    pass


class ThirdSingleton(Base):
    _class_group = "somegroup"

    def __init__(self, arg):
        pass


class FourthSingleton(ASingleton):
    _class_group = "somegroup"
    pass


def test_singleton():
    """Check basic functionality.

    For a given arg, there is only one instance
    """
    assert ASingleton("aa") is ASingleton("aa")
    assert ASingleton("aa") is not ASingleton("bb")


def test_singleton_inherit():
    """Check that subclasses behave properly."""
    assert ASingleton("aa") is not AnotherSingleton("aa")
    assert AnotherSingleton("aa") is AnotherSingleton("aa")


def test_class_group_singleton():
    """Check _class_group functionality.

    For a given arg, instances of FourthGroup are Instances of
    ThirdGroup because they share a `_class_group` valur
    """
    assert ThirdSingleton("aa") is FourthSingleton("aa")
    assert ThirdSingleton("aa") is not FourthSingleton("bb")
    assert ThirdSingleton("aa") is not ASingleton("aa")


def test_soco_reset_clears_instances():
    """Check that soco_reset() causes fresh singleton instances."""
    instance_before = ASingleton("aa")
    soco_reset()
    instance_after = ASingleton("aa")
    assert instance_before is not instance_after


def _zgs_payload(grouped):
    """Return a ZoneGroupState payload for two players."""
    member_a = (
        '<ZoneGroupMember UUID="RINCON_A" ZoneName="A" '
        'Location="http://192.168.1.110:1400/xml/device_description.xml"/>'
    )
    member_b = (
        '<ZoneGroupMember UUID="RINCON_B" ZoneName="B" '
        'Location="http://192.168.1.111:1400/xml/device_description.xml"/>'
    )
    if grouped:
        groups = (
            '<ZoneGroup Coordinator="RINCON_A" ID="RINCON_A:1">'
            f"{member_a}{member_b}</ZoneGroup>"
        )
    else:
        groups = (
            f'<ZoneGroup Coordinator="RINCON_A" ID="RINCON_A:1">{member_a}'
            f'</ZoneGroup><ZoneGroup Coordinator="RINCON_B" ID="RINCON_B:2">'
            f"{member_b}</ZoneGroup>"
        )
    return f"<ZoneGroupState><ZoneGroups>{groups}</ZoneGroups></ZoneGroupState>"


def _process_payload(zone, grouped):
    """Process a ZoneGroupState payload as if received in an event."""
    zone.zone_group_state.process_payload(
        _zgs_payload(grouped), "event", zone.ip_address
    )


def test_soco_reset_clears_zone_group_states():
    """Players from a ZoneGroupState after soco_reset() match new payloads.

    ZoneGroupState instances are kept per household on the SoCo class. If
    they survive soco_reset(), players read from them are not the singletons
    used when parsing later payloads, so their group cannot be found.
    """
    with mock.patch.object(SoCo, "household_id", "Sonos_household"), mock.patch(
        "soco.zonegroupstate.ZoneGroupState.poll"
    ):
        _process_payload(SoCo("192.168.1.110"), grouped=True)

        soco_reset()

        assert not SoCo.zone_group_states
        discovered = SoCo("192.168.1.110")
        _process_payload(discovered, grouped=True)
        players = {zone.uid: zone for zone in discovered.visible_zones}

        _process_payload(discovered, grouped=False)
        _process_payload(discovered, grouped=True)

        for player in players.values():
            assert player is SoCo(player.ip_address)
            assert player.group is not None
            assert player.group.members == set(players.values())


def test_soco_instances_are_unique_per_port():
    """A multi-zone device can expose multiple players on a single IP."""
    default = SoCo("192.168.1.100")
    alternate = SoCo("192.168.1.100", 1500)

    assert default is SoCo("192.168.1.100")
    assert default is SoCo("192.168.1.100", 1400)
    assert default is SoCo("192.168.1.100", port=1400)
    assert alternate is SoCo("192.168.1.100", 1500)
    assert alternate is SoCo("192.168.1.100", port=1500)
    assert default is not alternate


def test_subclass_with_other_constructor_args():
    """Subclass args that don't fit SoCo._singleton_key fall back to args."""

    class KwargSoCo(SoCo):
        def __init__(self, ip_address, session=None):
            super().__init__(ip_address)

    class PositionalSoCo(SoCo):
        def __init__(self, ip_address, name):
            super().__init__(ip_address)

    assert KwargSoCo("192.168.1.101", session="s") is KwargSoCo(
        "192.168.1.101", session="s"
    )
    assert PositionalSoCo("192.168.1.102", "kitchen") is not PositionalSoCo(
        "192.168.1.102", "lounge"
    )
