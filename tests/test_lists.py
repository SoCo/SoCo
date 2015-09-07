# -*- coding: utf-8 -*-
"""
Tests for the special lists in data_structures
"""

from __future__ import unicode_literals

import pytest

from soco.data_structures import ListOfMusicInfoItems


def test_lomi():
    lomi = ListOfMusicInfoItems(items=['one', 'two', 3, 4], number_returned=5,
                                total_matches=5, update_id=12)
    assert lomi.number_returned == 5
    assert lomi.total_matches == 5
    assert lomi.update_id == 12
    assert len(lomi) == 4

    # Slicing
    assert lomi[0] == 'one'
    assert lomi[-1] == 4
    assert lomi[1:3] == ['two', 3]
    assert lomi[3:1] == []
    assert lomi[3:1:-1] == [4, 3]
    assert lomi[:] == ['one', 'two', 3, 4]

    # Multiple slices

    assert lomi[0, 1:4, 3] == ['one', 'two', 3, 4, 4]
    assert lomi[0, 0, 1, 1] == ['one', 'one', 'two', 'two']

    # Read only.  Setting is not allowed
    with pytest.raises(TypeError):
        lomi[2] = 3
