"""Tests for the SoCoSingletonBase and _ArgsSingleton classes in core."""

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
