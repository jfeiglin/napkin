"""Long expressions (docs/language.md, §2.1): an expression goes on to the next row only inside
brackets. A line that ends with an operator, or a row that starts with one, says so."""

from __future__ import annotations

import pytest

from napkin.model.language.lex import SyntaxProblem, lines

HEAD = 'thing:\n    "A thing."\n'


@pytest.mark.parametrize(
    ('text', 'where'),
    [
        (HEAD + '    let x: fraction = 0.5 *\n        0.2  @r\n        "X"\n', 'ends with *'),
        (HEAD + '    let x: fraction = 0.5 and\n        0.2  @r\n', 'ends with and'),
        (HEAD + '    let x: fraction = 0.5\n        * 0.2  @r\n', 'starts with *'),
    ],
    ids=['trailing operator', 'trailing word', 'leading operator'],
)
def test_a_line_that_goes_on_outside_brackets_says_how_to_write_it(text, where):
    with pytest.raises(SyntaxProblem, match=f'{where}.*only inside brackets'):
        lines(text)


def test_inside_brackets_an_expression_goes_on():
    found = lines(HEAD + '    let x: fraction = (0.5\n        * 0.2)  @r\n        "X"\n')
    # The let starts on row 3 and takes rows 3 and 4: its text is on row 5.
    assert [line.number for line in found if line.kind == 'line'] == [1, 2, 3, 5]


def test_a_sign_and_a_pair_are_not_continuations():
    lines(HEAD + '    flow fill: -> x at 2 per_h  @r\n')
    lines(HEAD + '    let x: fraction = -0.5  @r\n')
