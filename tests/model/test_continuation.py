"""Long expressions (spec, "Units, comparisons and layout"): an expression goes on to the next row only
inside `(` or `[` (`napkin/model/language/lex.py`). A line that ends with an operator or a word that
joins two values, or a row that starts with one, says so with the code `continue`. A sign after `=`, an
arrow inside a line and a stage's `if` and `else:` are no continuations."""

from __future__ import annotations

import pytest

from napkin.model.language.lex import lines
from napkin.model.language.problems import SyntaxProblem

HEAD = 'tank:\n    "A tank."\n'


@pytest.mark.parametrize(
    ('text', 'where', 'row'),
    [
        (HEAD + '    x = 0.5 *\n        0.2\n', r'ends with \*', 3),
        (HEAD + '    ok = true and\n        false\n', 'ends with and', 3),
        (HEAD + '    flow drain: this.water ->\n        SINK\n', 'ends with ->', 3),
        (HEAD + '    x = 0.5\n        * 0.2\n', r'starts with \*', 4),
        (HEAD + '    x = 0.5\n    - 0.2\n', 'starts with -', 4),
        (HEAD + '    x = 1 if true\n    else 2\n', 'starts with else', 4),
    ],
    ids=['trailing operator', 'trailing word', 'trailing arrow', 'leading operator', 'leading sign', 'else'],
)
def test_a_line_that_goes_on_outside_brackets_says_how_to_write_it(text, where, row):
    with pytest.raises(SyntaxProblem, match=f'{where}.*only inside brackets') as raised:
        lines(text)
    assert (raised.value.code, raised.value.problem.line) == ('continue', row)


@pytest.mark.parametrize('value', ['(0.5\n        * 0.2)', '3 in [0,\n        10]'], ids=['(', '['])
def test_inside_brackets_an_expression_goes_on(value):
    found = lines(HEAD + f'    x = {value}\n        "X"\n')
    # The value starts on row 3 and takes rows 3 and 4: its text is on row 5.
    assert [line.number for line in found if line.kind == 'line'] == [1, 2, 3, 5]


def test_a_sign_an_arrow_and_a_branch_are_no_continuations():
    lines(HEAD + '    flow fill: SOURCE -> this.water\n')
    lines(HEAD + '    x = -0.5\n')
    branch = '    go = event():\n        after 1 h:\n            if this.x > 0:\n                this.x = 1\n'
    lines(HEAD + branch + '            else:\n                this.x = 2\n')
