"""The notes: free-form notes that the language parses and gives no meaning (docs/language.md, §2.11).
A note has any key, a value, notes under it and records; the compiler checks no key, no study reads
a note, and the records of the notes are cited as any record is. The catalogue's pages check the
notes that they read, so a misspelt name fails there. The scope of the outputs is on the scenario line
and on each output, not in the notes.

They build MODELTEST (tests/model/modeltest.py), whose notes give one premise and whose scenario line
gives the scope of its outputs.
"""

from __future__ import annotations

import pytest

from napkin.engine import evaluate_study
from napkin.model import ModelError
from tests.build import drop, member, replace
from tests.model.modeltest import build
from tools.publish.pages import pages

# The premises of the fixture's notes.
PREMISES = '    premises:\n        START: "The attacker holds access at the start."  @ident\n'


def notes_of(*notes):
    """An edit step: these notes at the end of the fixture's notes."""
    return member('notes:', *notes)


def whole(model):
    """{start-state options: the plain data of the whole structure} of a model."""
    return {starts: structure.plain() for starts, structure in model.whole.items()}


def test_a_note_that_no_page_reads_builds_and_runs(tmp_path):
    """The language gives the notes no meaning: a note that nothing reads changes no part of the
    model, and its study is admitted. The pages read the notes, and a name that they do not read is a
    mistake there, at the line of the note."""
    plain = whole(build(tmp_path))
    model = build(tmp_path, notes_of('notes: "An annotation that nothing reads."'))
    assert whole(model) == plain
    assert evaluate_study(model).admissible
    with pytest.raises(ModelError, match="'notes'") as caught:
        pages(model)
    (found,) = caught.value.diagnostics
    assert (found['path'], found.get('line')) == ('notes:/notes:', model.lines[('notes:', 'notes:')])


@pytest.mark.parametrize(
    'note',
    [
        pytest.param('anything: "A text."', id='text'),
        pytest.param('anything: ["A text.", "Another text."]', id='list'),
        pytest.param('anything:\n    status: checked\n    by: "A reviewer"', id='record'),
        pytest.param('anything:\n    A:\n        B:\n            C: 3', id='nested'),
        pytest.param('anything: []', id='empty list'),
        # Names that the build read before, and the pages' own names, are notes like any other.
        pytest.param('scope: "Synthetic users."', id='scope'),
        pytest.param('scopes:\n    users: "Synthetic users."', id='scopes'),
        pytest.param('limitations:\n    L1: "The users are synthetic."', id='limitations'),
    ],
)
def test_the_compiler_checks_no_key_of_a_note(tmp_path, note):
    """A note of any key and any shape builds, and the model is the same as without it."""
    assert whole(build(tmp_path, notes_of(note))) == whole(build(tmp_path))


def test_the_records_of_a_note_are_cited_at_any_depth(tmp_path):
    """A record under a note, however deep, and a named record at the end of a note's line, are records
    of the file: their claims are the model's, and a name that no record has is an error at its line.
    No record of a note is a use of a part of the model."""
    plain = build(tmp_path)
    assert 'T_DATUM' not in plain.evidence['claims']
    deep = '@identity "A reviewer\'s source."\n    claims:\n        T_DATUM'
    model = build(
        tmp_path,
        notes_of(
            'checks:\n    first:\n        by: "A reviewer"\n        ' + deep.replace('\n', '\n        ')
        ),
    )
    assert 'T_DATUM' in model.evidence['claims']
    assert [use for use in model.index['uses'] if use['part'].startswith('notes:')] == []
    cited = build(tmp_path, notes_of('checks: "Checked."  @ident'))
    assert ('notes:', 'checks:') in cited.evidence['sites']
    with pytest.raises(ModelError, match='missing'):
        build(tmp_path, notes_of('checks: "Checked."  @missing'))


def test_no_study_reads_a_note(tmp_path):
    """The notes give no warning and change no study: the limitations of a model are its authors' and
    the reviewers' texts, which the pages show (D-10)."""
    limitations = (
        'limitations:\n    L1: "The users are synthetic."  @ident\n    L2: "A limit with no record."'
    )
    plain = evaluate_study(build(tmp_path, drop('notes:')))
    noted = evaluate_study(build(tmp_path, notes_of(limitations)))
    assert noted.admissible
    assert not [d for d in noted.diagnostics if d['code'].startswith('model_limitation')]
    assert noted.diagnostics == plain.diagnostics


def test_the_scope_of_an_output_is_its_own_or_the_scenarios(tmp_path):
    """An output's scope is its own `scope "…"`, else the scope on the scenario line; with neither, an
    output has none, and the model still builds."""
    model = build(tmp_path)
    scopes = {name: outcome.scope for name, outcome in model.whole[()].outcomes.items()}
    assert set(scopes.values()) == {'Synthetic users.'}
    own = build(tmp_path, member('service/served/output:', 'scope "The users that it serves."'))
    found = {name: outcome.scope for name, outcome in own.whole[()].outcomes.items()}
    assert found[own.outputs['service.served']] == 'The users that it serves.'
    assert {k: v for k, v in found.items() if k != own.outputs['service.served']} == {
        k: v for k, v in scopes.items() if k != own.outputs['service.served']
    }
    bare = build(tmp_path, replace('    scope "Synthetic users."\n', ''))
    assert all(outcome.scope is None for outcome in bare.whole[()].outcomes.values())


@pytest.mark.parametrize(
    ('steps', 'place'),
    [
        # A misspelt name of a note, and a misspelt key of an entry.
        pytest.param(
            (notes_of('limitation:\n    L1: "The users are synthetic."'),),
            'notes:/limitation:',
            id='a misspelt note',
        ),
        pytest.param(
            (notes_of('limitations:\n    L1:\n        statment: "The users are synthetic."'),),
            'notes:/limitations:/L1:/statment:',
            id='a misspelt key of an entry',
        ),
        # An entry without what the pages show.
        pytest.param(
            (notes_of('limitations:\n    L1:'),),
            'notes:/limitations:/L1:',
            id='an entry without its statement',
        ),
        # A note in another shape than the one that the pages read.
        pytest.param(
            (notes_of('exposure: ["The users.", "Their area."]'),),
            'notes:/exposure:',
            id='a note of another shape',
        ),
        pytest.param(
            (replace(PREMISES, '    premises: "The users wait."\n'),),
            'notes:/premises:',
            id='premises that are a text',
        ),
        # The library holds the verification status of a claim, so a copy of it goes stale.
        pytest.param(
            (notes_of('verification:\n    verification_status: verified'),),
            'notes:/verification:/verification_status:',
            id='a copy of a verification status',
        ),
        # The scope of the outputs is on the scenario line, not in the notes.
        pytest.param((notes_of('scope: "Synthetic users."'),), 'notes:/scope:', id='a scope in the notes'),
    ],
)
def test_the_pages_check_the_notes_that_they_read(tmp_path, steps, place):
    """Each of these builds, and the pages reject it at the line of the note that they read."""
    model = build(tmp_path, *steps)
    with pytest.raises(ModelError) as caught:
        pages(model)
    (found,) = caught.value.diagnostics
    assert found['path'] == place
    key = tuple(place.split('/'))
    while key not in model.lines:
        key = key[:-1]
    assert found.get('line') == model.lines[key]
