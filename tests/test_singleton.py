"""Tests for the SoCoSingletonBase and _ArgsSingleton classes in core."""


import pytest

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
