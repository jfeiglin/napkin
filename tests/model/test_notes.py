"""The notes: free-form notes that the language parses and gives no meaning. A note is `key: value` under
`notes:`, with a text, a number, a word or a list, its records and the notes under it
(`language/parse.py`); the compiler checks no key, so a note of any key and shape leaves the program
and the hash of the model as they are without it (`napkin/model/identity.py`), and no run reads a
note. A note's records are the model's at any depth, so a name that names no record is refused at its
line, as on any other line. A number of a note has no unit.

The pages that read the notes and check the names that they read are the publisher's, which stage M
ports (PLAN, change 13); the scope of an output went with the outputs (D10). The records of a note
that cite the library are resolved in `tests/evidence/test_library_integrity.py`.
"""

from __future__ import annotations

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.canonical import program_bytes
from tests.program.examples import UNITS

TANK = """\
scenario "Notes"
    horizon 4 h

tank:
    "A tank that drains."
    water: L = 8 L in [0 L,]  @fixture
        "Water held"
    flow drain: this.water -> SINK  @fixture
        request = 1 L/h

record fixture: identity "Analytic contract fixture."
"""


def with_notes(*notes):
    """The tank with a block of these notes at its end."""
    rows = [f'    {row}' for note in notes for row in note.split('\n')]
    return TANK + '\nnotes:\n' + '\n'.join(rows) + '\n'


def compiled(text):
    return compile_text(text, UNITS)


def line_of(text, words):
    return next(number for number, row in enumerate(text.split('\n'), 1) if words in row)


@pytest.mark.parametrize(
    'note',
    [
        pytest.param('anything: "A text."', id='text'),
        pytest.param('anything: ["A text.", "Another text."]', id='list'),
        pytest.param('anything:\n    status: checked\n    by: "A reviewer"', id='record'),
        pytest.param('anything:\n    A:\n        B:\n            C: 3', id='nested'),
        pytest.param('anything: []', id='empty list'),
        pytest.param('anything: [2, 3.5, word]', id='numbers and a word'),
        # Names that the pages read are notes like any other.
        pytest.param('scope: "Synthetic users."', id='scope'),
        pytest.param('limitations:\n    L1: "The users are synthetic."  @fixture', id='limitations'),
    ],
)
def test_a_note_of_any_key_and_shape_changes_neither_the_program_nor_the_hash(note):
    plain, noted = compiled(TANK), compiled(with_notes(note))
    assert program_bytes(noted.program) == program_bytes(plain.program)
    assert noted.model_hash == plain.model_hash
    assert [item.key for item in noted.declared.notes] == [note.split(':')[0]]


def test_the_records_of_a_note_at_any_depth_are_records_of_the_model():
    deep = (
        'checks:\n    first:\n        by: "A reviewer"  @fixture\n        @identity "A reviewer\'s source."'
    )
    (checks,) = compiled(with_notes(deep)).declared.notes
    (first,) = checks.notes
    (by,) = first.notes
    assert [item.name for item in by.cites] == ['fixture']
    assert [(item.kind, item.text) for item in first.evidence] == [('identity', "A reviewer's source.")]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason='bug: a note that cites no record of the model is accepted (napkin/model/semantic.py checks '
    'the citations of declarations only, and napkin/model/evidence.basis_errors no named record)',
)
@pytest.mark.parametrize(
    'note', ['checks: "Checked."  @missing', 'checks:\n    first: "By a reviewer."  @missing']
)
def test_a_note_that_cites_no_record_is_refused_at_its_line(note):
    text = with_notes(note)
    try:
        compiled(text)
    except LanguageError as error:
        assert [(item.code, item.line) for item in error.problems] == [
            ('unknown_record', line_of(text, '@missing'))
        ]
    else:
        raise AssertionError('the model was accepted')


def test_a_number_of_a_note_has_no_unit():
    text = with_notes('limit: 3 L')
    with pytest.raises(LanguageError) as raised:
        compiled(text)
    (problem,) = raised.value.problems
    assert (problem.code, problem.line) == ('syntax', line_of(text, 'limit: 3 L'))
    assert 'a number of a note has no unit' in problem.message
