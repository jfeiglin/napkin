"""The entry of the front end (`napkin/model/compile.py`): one refused model text for each stage that
can refuse it, each a `LanguageError` whose problem has its code, the file that the caller names and
the line that it is about. The lexer refuses a row that it cannot cut into tokens, the parser a line
that is not written as the language writes it, the declared model a part that breaks a rule of names,
types, units or ranges, and the program's checker an invariant that the engine relies on, at the line
of the declared part that it names. A text that is refused at one line is accepted with that line
mended, so each case refuses its own line only.

Copies of a template left the language (spec, "What the first version leaves out"): a template's
members are written by hand or are the rows of a table (`tests/language/test_collections.py`).
"""

from __future__ import annotations

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

TANK = """\
scenario "Tank"
    horizon 4 h

tank:
    water: L = 8 L in [0 L, 20 L]
        outflow.allocation = priority(this.drain)
    spare: L = 0 L in [0 L,]
    flow drain: this.water -> SINK
        request = 1 L/h
    flow fill: SOURCE -> this.spare
        request = 1 L/h
    alarm = event():
        when this.water <= 2 L:
            this.alarm.start()
            reset when false
        after 0 h:
            move 1 L from this.spare to this.water
"""

# {case: (the line as the fixture writes it, the line with its fault, the code)}, one for each stage.
CASES = {
    # The lexer: a tab is no indentation.
    'tab': ('    spare: L = 0 L in [0 L,]', '\tspare: L = 0 L in [0 L,]', 'tab'),
    # The parser: a flow names both of its ends.
    'syntax': ('    flow fill: SOURCE -> this.spare', '    flow fill: -> this.spare', 'syntax'),
    # The declared model: a name that names nothing, ...
    'unknown_name': (
        '        request = 1 L/h\n    flow fill',
        '        request = this.rate\n    flow fill',
        'unknown_name',
    ),
    # ... a range whose ends are in the wrong order, ...
    'range': ('    water: L = 8 L in [0 L, 20 L]', '    water: L = 8 L in [20 L, 0 L]', 'range'),
    # ... a condition that is a number, ...
    'type': ('        when this.water <= 2 L:', '        when this.water:', 'type'),
    # ... and a move whose amount is a time.
    'unit': ('            move 1 L from', '            move 1 h from', 'unit'),
    # The program's checker: a priority names flows of its own endpoint.
    'priority_item': (
        '        outflow.allocation = priority(this.drain)',
        '        outflow.allocation = priority(this.fill)',
        'priority_item',
    ),
}


@pytest.mark.parametrize('name', sorted(CASES))
def test_each_stage_refuses_its_fault_with_its_code_file_and_line(name):
    old, new, code = CASES[name]
    assert TANK.count(old) == 1
    text = TANK.replace(old, new)
    with pytest.raises(LanguageError) as raised:
        compile_text(text, UNITS, 'tank.scn')
    (problem,) = raised.value.problems
    line = next(
        number for number, row in enumerate(text.split('\n'), 1) if row.startswith(new.split('\n')[0])
    )
    assert (problem.code, problem.file, problem.line) == (code, 'tank.scn', line)
    assert str(raised.value).startswith(f'tank.scn:{line}:')


def test_the_fixture_itself_is_accepted_and_a_text_with_no_horizon_has_no_run():
    assert compile_text(TANK, UNITS).configuration is not None
    bare = compile_text(TANK.split('\n', 2)[2], UNITS)
    assert bare.configuration is None
    with pytest.raises(LanguageError) as raised:
        bare.configure()
    assert raised.value.codes == ['scenario']
