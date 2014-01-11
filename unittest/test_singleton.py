# -*- coding: utf-8 -*-
""" Tests for the SoCoSingletonBase and _ArgsSingleton classes in core"""

from __future__ import unicode_literals

import pytest
from soco.core import _SocoSingletonBase as Base

class ASingleton(Base):
    def __init__(self, arg):
        pass

class AnotherSingleton(ASingleton):
    pass


def test_singleton():
    """ Check basic functionality. For a given arg, there is only one instance"""
    assert ASingleton('aa') == ASingleton('aa')
    assert ASingleton('aa') != ASingleton('bb')
    
def test_singleton_inherit():
    """ Check that subclasses behave properly"""
    assert ASingleton('aa') != AnotherSingleton('aa')
    assert AnotherSingleton('aa') == AnotherSingleton('aa')
