"""Records that a status can cite, and the range that a fixed value has not.

They build MODELTEST (tests/model/modeltest.py): an attacker switches a service off at t = 0; after the
repair it jams the switch unless the responders remove it first. Each test reads the records that a
part of the built structure cites, and the evidence index of the file.
"""

from __future__ import annotations

import pytest

from napkin.model import ModelError
from napkin.model.ir import basis_records
from tests.build import member, replace, status
from tests.model.modeltest import build


def names(basis):
    return [record['name'] for record in basis_records(basis)]


def cited(model, part):
    """The records that the evidence index lists for one part of the file."""
    return [u['name'] for u in model.index['uses'] if u['part'] == part]


# ---- the records of a status --------------------------------------------------------------------

# The switch with no records of its own.
BARE_SWITCH = replace('switch:  @ident @access', 'switch:')
# The first status line of the service.
FAILED = '    status failed when status is "down"'


def test_a_status_case_can_cite_the_record_behind_its_text(tmp_path):
    plain = build(tmp_path)
    model = build(tmp_path, replace(FAILED, f'{FAILED}  @attack'))
    # A status rests on its entity's records, or on its own: they sit on its lines.
    assert names(plain.structure_of('slow').labels['service.health'].basis) == ['ident']
    assert names(model.structure_of('slow').labels['service.health'].basis) == ['attack']
    assert cited(model, 'service/status:') == ['attack']


def test_a_status_can_rest_on_the_records_of_its_cases(tmp_path):
    cases = status(('failed', 'position is "off"', 'Off'), ('ok', None, 'On'), records='@attack @ident')
    model = build(tmp_path, BARE_SWITCH, member('switch', cases))
    assert names(model.structure_of('slow').labels['switch.health'].basis) == ['attack', 'ident']


def test_a_status_rests_on_some_record(tmp_path):
    with pytest.raises(ModelError, match='status rests on'):
        build(tmp_path, BARE_SWITCH, member('switch', status(('ok', None, 'On'))))


# ---- the range of a fixed value -----------------------------------------------------------------


def test_a_fixed_value_has_no_range(tmp_path):
    users = '    let users = 1000 people'
    with pytest.raises(ModelError, match='a fixed value has no bounds'):
        build(tmp_path, replace(f'{users}  @ident', f'{users} in 1 people to 5000 people  @ident'))
