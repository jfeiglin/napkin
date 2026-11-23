"""The records of a status display (spec, "Evidence at the point of use"; docs/design/decisions.md, change
16). A case of a status display cites the records behind its text on its own line, and a case
with none of its own rests on the records of its entity or template. A case that rests on no record is
no error: the compiler warns of it with the code `no_record` at the case's line
(`napkin/model/support.py`), and the model still compiles and runs. The old rule that a fixed value
has no range went: a range belongs to any value.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from tests.program.examples import UNITS

BREAKER = """\
scenario "Breaker"
    horizon 4 h

breaker:{thing}
    "A breaker that an attacker opens."
    position: enum[ON, OFF] = ON  @ident
        "Position"
    status failed when this.position == OFF{failed}
        "Off"
    status ok{ok}
        "On"
    turn = event():  @attack
        after 1 h:
            this.position = OFF

breaker.turn.start()

record ident: identity "The breaker of the fixture."
record attack: assumption "The attacker opens the breaker after an hour."
"""


def compiled(thing='', failed='', ok=''):
    return compile_text(BREAKER.format(thing=thing, failed=failed, ok=ok), UNITS)


def unsupported_cases(model):
    """The (line, path) of each warning of a case of the breaker's display that rests on no record."""
    return [
        (item.line, item.message.split(':')[0])
        for item in model.reports
        if item.code == 'no_record' and item.message.startswith('breaker.status')
    ]


def line_of(words):
    text = BREAKER.format(thing='', failed='', ok='')
    return next(number for number, row in enumerate(text.split('\n'), 1) if row.strip().startswith(words))


def test_a_status_case_cites_the_record_behind_its_text():
    model = compiled(failed='  @attack', ok='  @ident')
    cases = [model.declared.part(f'breaker.status.case[{k}]') for k in (0, 1)]
    assert [[item.name for item in case.evidence] for case in cases] == [['attack'], ['ident']]
    assert unsupported_cases(model) == []


@pytest.mark.parametrize('records', ['  @ident', '  @ident @attack'], ids=['one', 'two'])
def test_a_case_with_no_record_of_its_own_rests_on_those_of_its_entity(records):
    model = compiled(thing=records)
    assert [item.name for item in model.declared.part('breaker').evidence] == [
        name.lstrip('@') for name in records.split()
    ]
    assert unsupported_cases(model) == []


def test_a_case_that_rests_on_no_record_is_a_warning_at_its_line_and_the_model_runs():
    model = compiled(failed='  @attack')
    assert unsupported_cases(model) == [(line_of('status ok'), 'breaker.status.case[1]')]
    # The display follows the run: on until the attacker opens the breaker at 1 h.
    record = run(model.program, model.configuration)
    (status,) = read(record, model.program, ['breaker.status'], [0, 1, 4])
    assert status.values == ('case[1]', 'case[0]', 'case[0]')
    both = compiled()
    assert unsupported_cases(both) == [
        (line_of('status failed'), 'breaker.status.case[0]'),
        (line_of('status ok'), 'breaker.status.case[1]'),
    ]
