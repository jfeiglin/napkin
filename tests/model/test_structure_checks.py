"""The rules that the checks of the old structure enforced, as the front end enforces them now
(`napkin/model/semantic.py`): each place that takes a yes/no, a time or one dimension refuses another,
by its code and at its line, and formulas on a circle have no order (`cycle`).

The program's checker refuses each invariant of the engine with a code of its own
(`tests/program/test_check.py`), the classes of a trigger's condition are in
`tests/engine/test_trigger_classes.py`, a status case that is no yes/no in
`tests/language/test_status.py`, and the statements of a stage in `tests/language/test_events.py`.
The old checks of groups, windows and outputs went with those parts of the language.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

TANK = """\
scenario "Checks"
    horizon 4 h

tank:
    water: L = 8 L in [0 L, 20 L]
    mass: g = 0 g in [0 g,]
    spill: L = 0 L in [0 L,]
    open: bool = true
    drain = event():
        when this.water <= 2 L:
            this.drain.start()
            reset when false
        until this.open
        after 1 h:
            move 1 L from this.water to this.spill
    assert this.water >= 0 L

tank.drain.start()
"""

CASES = [
    # A condition is a yes/no: of a trigger, of a gate and of an assertion.
    ('        when this.water <= 2 L:', '        when this.water:', 'type'),
    ('        until this.open', '        until this.water', 'type'),
    ('    assert this.water >= 0 L', '    assert this.water', 'type'),
    # A delay is a time.
    ('        after 1 h:', '        after 1 L:', 'unit'),
    # A move joins two stores of one dimension.
    (
        '            move 1 L from this.water to this.spill',
        '            move 1 L from this.water to this.mass',
        'unit',
    ),
    # A range is in the unit of its value.
    ('    water: L = 8 L in [0 L, 20 L]', '    water: L = 8 L in [0 h, 20 L]', 'unit'),
]


@pytest.mark.parametrize(('old', 'new', 'code'), CASES, ids=[case[2] + ':' + case[1].strip() for case in CASES])
def test_each_place_refuses_a_value_of_another_kind_at_its_line(old, new, code):
    text = TANK.replace(old, new)
    with pytest.raises(LanguageError) as raised:
        compile_text(text, UNITS)
    line = text.split('\n').index(new) + 1
    assert [(item.code, item.line) for item in raised.value.problems] == [(code, line)]


def test_the_fixture_runs_as_written():
    """The tank holds 8 L; the drain moves 1 L into the spill at 1 h."""
    model = compile_text(TANK, UNITS)
    record = run(model.program, model.configuration)
    assert record.failure is None
    water, spill = read(record, model.program, ['tank.water', 'tank.spill'], [0, 1, 4])
    assert (water.values, spill.values) == ((8, 7, 7), (0, 1, 1))


@pytest.mark.parametrize(
    'formulas',
    [
        ['a = formula(this.b + 1)', 'b = formula(this.a + 1)'],
        ['a = formula(this.b + 1)', 'b = formula(this.c)', 'c = formula(this.a * 2)'],
        ['a = formula(this.a + 1)'],
    ],
    ids=['two', 'three', 'itself'],
)
def test_formulas_on_a_circle_are_refused_at_a_formula_on_it(formulas):
    text = 's:\n    x = 1\n' + ''.join(f'    {row}\n' for row in formulas) + '    apart = formula(this.x + 1)\n'
    with pytest.raises(LanguageError) as raised:
        compile_text(text, UNITS)
    (problem,) = raised.value.problems
    assert problem.code == 'cycle' and problem.line in range(3, 3 + len(formulas))
