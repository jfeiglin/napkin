"""A key belongs to the member on which .by was applied (spec, Collections, keys and projections)."""

import pytest

from napkin.program import build as b
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at


def linked_stations(reverse_links, rekey):
    builder = b.Builder({'h': {'time': 1}})
    stations = builder.template('Station', b.input_('rank', '', 1), b.input_('weight', '', 3))
    left = builder.member(stations, 'left')
    right = builder.member(stations, 'right', weight=8)
    owners = builder.template('Owner', b.link('station', 'Station'), b.input_('priority', '', 1))
    first, last = (right, left) if reverse_links else (left, right)
    builder.member(owners, 'first', station=first)
    builder.member(owners, 'last', station=last)
    if rekey:
        picked = owners.instances.station.by('rank').at(1)
    else:
        picked = owners.instances.by('priority').station.at(1)
    builder.root(b.value('picked', '', b.formula(picked.weight)))
    return builder.finish()


@pytest.mark.parametrize(
    'reverse_links,rekey,expected',
    [
        pytest.param(False, True, 8, id='new-station-key'),
        pytest.param(True, True, 8, id='new-station-key-reversed-links'),
        pytest.param(False, False, 8, id='inherited-owner-key'),
        pytest.param(True, False, 3, id='inherited-owner-key-reversed-links'),
    ],
)
def test_equal_keys_select_the_later_member_of_the_keyed_collection(reverse_links, rekey, expected):
    program = linked_stations(reverse_links, rekey)
    result, failure = run_of(program, Configuration(Request(1)))
    assert failure is None, failure
    assert value_at(result, program, Key('', ('picked',)), 0) == expected
