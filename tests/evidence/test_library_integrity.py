"""Library and record references: typos, assumption IDs posing as claims and stale copies fail.

Every expected (code, place) follows from the rule being exercised: references resolve wherever they
appear (a line, a note, a status case, a record of the model and the library's own records), the
library's relations come from a closed vocabulary and a record lists its claims by their IDs alone,
red-team judgements carry their elicitation, and a claim names one datum by its key. A line that the
reader rejects is placed at its line; a reference that the library refuses, at its path. The models
are the synthetic service of `tests/evidence/support.py`.
"""

import copy
import json
import textwrap

import pytest

from napkin.model import ModelError
from napkin.model.compile import compile_text, library_units, load_scenario
from napkin.model.evidence import dependencies, library_checks, validate_library
from napkin.model.language.evidence import document
from napkin.model.language.problems import LanguageError
from napkin.schema import FOLDER as SCHEMAS
from tests.evidence.support import SERVICE, evidence_library, fixture_claim, write_package

RELATIONS = {
    'mechanism_support',
    'mechanism_precedent',
    'specifies_component',
    'bounds',
    'reports_value',
    'context_limitations',
    'defines_conditions',
    'consistent_with',
    'contradicts',
    'accounting_rule',
    'adopts',
    'calibrates',
}
# The record of the rate, whose claims the tests change.
ACCESS = 'record access: source_transfer "Applied from another setting."\n    claims:\n        C-ACCESS\n'


def library_problems(lib):
    return {(d['code'], d['path']) for d in validate_library(lib)}


def refused(root, lib, text=SERVICE):
    """The (code, path) of every diagnostic with which the front end refuses the package of `text`
    under the library `lib`."""
    with pytest.raises(ModelError) as raised:
        load_scenario(write_package(root, {'model.scn': text}, lib))
    return {(d['code'], d['path']) for d in raised.value.diagnostics}


def located(text):
    """The (code, line) of every problem with which the reader refuses a text."""
    with pytest.raises(LanguageError) as raised:
        compile_text(textwrap.dedent(text), library_units(evidence_library()))
    return {(item.code, item.line) for item in raised.value.problems}


def line_of(text, words):
    """The number of the one line of `text` that holds `words`."""
    (number,) = [number for number, row in enumerate(text.split('\n'), 1) if words in row]
    return number


def noted(record):
    """The service with the limitation RF, which rests on `record`, written in place under it."""
    block = textwrap.indent(textwrap.dedent(record).strip('\n'), ' ' * 12)
    return SERVICE + f'\nnotes:\n    limitations:\n        RF: "Fixture."\n{block}\n'


@pytest.mark.parametrize('claim', ['C-TYPO', 'RT-FIXTURE'])
def test_assumption_supports_must_name_library_claims(tmp_path, claim):
    lib = evidence_library()
    lib['assumptions'][0]['supports'].append({'claim': claim, 'relation': 'bounds'})
    assert library_problems(lib) == {('provenance', 'library/assumptions/0/supports/1')}
    assert refused(tmp_path, lib) == {('provenance', 'library/assumptions/0/supports/1')}


@pytest.mark.parametrize(
    'claim, expected',
    [
        ('C-TYPO', {('provenance', 'library/claims/0/related/0')}),
        ('RT-FIXTURE', {('provenance', 'library/claims/0/related/0')}),
        ('C-ACTION', set()),
    ],
)
def test_claim_related_must_name_library_claims(claim, expected):
    lib = evidence_library()
    lib['claims'][0] = fixture_claim('C-ACCESS', related=[{'claim': claim, 'relation': 'consistent_with'}])
    assert library_problems(lib) == expected


def test_the_library_relations_are_closed_and_a_record_writes_none(tmp_path):
    schema = json.loads((SCHEMAS / 'library.schema.json').read_text())
    assert set(schema['$defs']['relation']['enum']) == RELATIONS
    lib = evidence_library()
    lib['assumptions'][0]['supports'][0]['relation'] = 'supports'
    assert refused(tmp_path, lib) == {('schema', 'assumptions/0/supports/0/relation')}
    # A record lists each claim by its ID alone, so the line of the claim is rejected as a whole.
    text = SERVICE.replace(ACCESS, ACCESS.replace('C-ACCESS', 'C-ACCESS: mechanism_support'))
    assert located(text) == {('syntax', line_of(text, 'C-ACCESS: mechanism_support'))}


def test_model_redteam_requires_its_elicitation(tmp_path):
    lib = evidence_library()
    del lib['assumptions'][0]['elicitation']
    assert refused(tmp_path / 'redteam', lib) == {('schema', 'assumptions/0')}
    lib['assumptions'][0]['origin'] = 'author'
    load_scenario(write_package(tmp_path / 'author', {'model.scn': SERVICE}, lib))


@pytest.mark.parametrize(
    'record, path, message',
    [
        ('@source "Fixture."\n    claims:\n        C-TYPO', '/0/links/0', 'Unknown claim C-TYPO'),
        ('@source "Fixture."\n    claims:\n        RT-FIXTURE', '/0/links/0', 'Unknown claim RT-FIXTURE'),
        ('@assumption "Fixture."\n    assumption A-TYPO', '/0/rests_on/0', 'Unknown assumption A-TYPO'),
        ('@assumption "Fixture."\n    assumption C-ACTION', '/0/rests_on/0', 'Unknown assumption C-ACTION'),
    ],
)
def test_the_records_of_a_note_are_resolved(tmp_path, record, path, message):
    lib = evidence_library()
    with pytest.raises(ModelError) as raised:
        load_scenario(write_package(tmp_path, {'model.scn': noted(record)}, lib))
    ((code, where, found),) = [(d['code'], d['path'], d['message']) for d in raised.value.diagnostics]
    assert (code, found) == ('provenance', message) and where.endswith(f'.limitations.RF{path}')
    # The records that a note rests on are typed: a transfer and an assumption.
    fine = '@source_transfer "Fixture."\n    claims:\n        C-ACTION\n@assumption "Fixture."\n    assumption RT-FIXTURE'
    load_scenario(write_package(tmp_path / 'fine', {'model.scn': noted(fine)}, lib))


@pytest.mark.parametrize(
    'claim, wrong',
    [
        ('C-ACTION C-ACCESS', 'C-ACTION C-ACCESS'),
        ('C-ACTION\n            assumption A-UNDER', 'assumption A-UNDER'),
    ],
)
def test_a_claim_line_names_one_claim_and_only_its_datum_sits_under_it(claim, wrong):
    text = SERVICE.replace(ACCESS, ACCESS.replace('        C-ACCESS\n', f'        {claim}\n'))
    assert located(text) == {('syntax', line_of(text, wrong))}


def shown(record):
    """The service with a status display whose first case rests on `record`, written in place."""
    block = textwrap.indent(textwrap.dedent(record).strip('\n'), ' ' * 8)
    cases = f'    status failed when not this.open\n        "Stopped"\n{block}\n    status ok\n        "Running"\n'
    return SERVICE.replace('\nArchive:\n', f'{cases}\nArchive:\n')


@pytest.mark.parametrize(
    'record, message',
    [
        ('@source "Fixture."\n    claims:\n        C-TYPO', 'Unknown claim C-TYPO'),
        ('@source "Fixture."\n    claims:\n        C-ACTION\n            datum: d', 'Unknown datum d'),
        ('@assumption "Fixture."\n    assumption A-TYPO', 'Unknown assumption A-TYPO'),
    ],
)
def test_the_records_of_a_status_case_resolve(tmp_path, record, message):
    with pytest.raises(ModelError) as raised:
        load_scenario(write_package(tmp_path, {'model.scn': shown(record)}, evidence_library()))
    assert [(d['code'], d['message']) for d in raised.value.diagnostics] == [('provenance', message)]


@pytest.mark.parametrize('datum', ['datum: ["d"]', 'datum:\n                name: d'], ids=['list', 'record'])
def test_a_datum_that_is_not_a_key_is_refused_at_its_line(datum):
    # A datum names a key of the claim's data: the reader rejects a list or a record at the line of
    # the datum.
    text = SERVICE.replace(ACCESS, ACCESS + f'            {datum}\n')
    assert located(text) == {('syntax', line_of(text, 'datum:'))}


def test_a_datum_that_names_no_key_of_the_data_is_a_provenance_error(tmp_path):
    text = SERVICE.replace(ACCESS, ACCESS + '            datum: 3\n')
    assert refused(tmp_path, evidence_library(), text) == {('provenance', 'record access/links/0')}


def test_a_copied_verification_status_is_no_line_of_a_record():
    # Under a claim of a record only its datum sits, so a copied status there is rejected as a whole.
    text = SERVICE.replace(ACCESS, ACCESS + '            verification_status: verified\n')
    assert located(text) == {('syntax', line_of(text, 'verification_status:'))}


def test_a_run_declares_only_its_options_and_its_text():
    text = SERVICE.replace('    half = "Half rate"\n', '    half = "Half rate"\n        adversary: true\n')
    assert located(text) == {('layout', line_of(text, 'adversary: true'))}


def test_the_supports_of_a_convention_are_resolved_too(tmp_path):
    # A convention of the library rests on a claim, as an assumption does.
    lib = evidence_library()
    lib['conventions'] = [
        {
            'id': 'ROUNDING',
            'statement': 'Rule.',
            'supports': [{'claim': 'C-TYPO', 'relation': 'accounting_rule'}],
        }
    ]
    assert library_problems(lib) == {('provenance', 'library/conventions/0/supports/0')}
    assert refused(tmp_path / 'typo', lib) == {('provenance', 'library/conventions/0/supports/0')}
    lib['conventions'][0]['supports'][0]['claim'] = 'C-ACTION'
    load_scenario(write_package(tmp_path / 'fine', {'model.scn': SERVICE}, lib))


def test_a_convention_record_names_a_convention_of_the_library(tmp_path):
    """`record r: convention "…"` with `convention ID` under it cites the library's convention ID: an
    unknown ID is an error, and the convention, with the claims that support it, is part of what the
    model reaches. The hash of the model covers no record, so a revised convention keeps it."""
    lib = evidence_library()
    lib['conventions'] = [
        {
            'id': 'ROUNDING',
            'statement': 'Rule.',
            'supports': [{'claim': 'C-ACCESS', 'relation': 'accounting_rule'}],
        }
    ]
    cited = SERVICE.replace(
        'record fixture: identity "Analytic contract fixture."\n',
        'record fixture: convention "The rounding rule."\n    convention ROUNDING\n',
    )
    model = load_scenario(write_package(tmp_path / 'one', {'model.scn': cited}, lib))
    reached = dependencies(document(model.declared.tree), lib)
    assert reached['conventions'] == ['ROUNDING'] and 'C-ACCESS' in reached['claims']
    changed = copy.deepcopy(lib)
    changed['conventions'][0]['statement'] = 'Another rule.'
    again = load_scenario(write_package(tmp_path / 'two', {'model.scn': cited}, changed))
    assert again.model_hash == model.model_hash
    assert refused(tmp_path / 'three', lib, cited.replace('ROUNDING', 'ROUNDED')) == {
        ('provenance', 'record fixture/rests_on/0')
    }


def test_a_library_with_a_harm_scale_is_refused_by_its_schema(tmp_path):
    # The harm scale is gone from the library format; a library that still has one is not read.
    lib = evidence_library()
    assert library_checks(lib)[0] == []
    lib['harm_scale'] = {'dimensions': ['deaths'], 'level_names': ['Zero', 'Minor']}
    found = library_checks(lib)[0]
    assert [(d['code'], d['path']) for d in found] == [('schema', '')]
    assert 'harm_scale' in found[0]['message']
