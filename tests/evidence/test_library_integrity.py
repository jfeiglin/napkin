"""Library and review references: typos, assumption ids posing as claims and stale copies fail.

Every expected (code, place) follows from the rule being exercised: references resolve wherever
they appear, the library's relations come from a closed vocabulary and a record lists its claims by
their IDs alone, red-team judgements carry their elicitation, and verification status is read from
the library, never copied. A problem in a line of the file is reported at that line; a line that the
reader rejects has no place, only its line.
"""

import copy
import json

import pytest

from napkin.model import ModelError
from napkin.model.evidence import library_checks, validate_library
from napkin.schema import FOLDER as SCHEMAS
from tests.build import (
    FIXTURE_RECORD,
    block,
    compiled,
    edit,
    evidence_library,
    fixture_claim,
    in_place,
    member,
    rejected,
    replace,
    sc99,
    scenario,
)
from tests.evidence.support import resting
from tools.publish.pages import pages

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


def library_problems(lib):
    return {(d['code'], d['path']) for d in validate_library(lib)}


def located(text, lib=None):
    """The (code, place, line) of every diagnostic that rejects a text."""
    with pytest.raises(ModelError) as raised:
        compiled(text, lib or evidence_library())
    return {(d['code'], d['path'], d.get('line')) for d in raised.value.diagnostics}


def line_of(text, words):
    """The number of the one line of `text` that holds `words`."""
    (number,) = [number for number, row in enumerate(text.split('\n'), 1) if words in row]
    return number


def source(*claims):
    """A source record, written in place, that cites `claims`."""
    return in_place('source', 'Fixture.', *claims)


def assumed(name):
    """An assumption record, written in place, that names the assumption `name`."""
    return in_place('assumption', 'Fixture.', assumption=name)


@pytest.mark.parametrize('claim', ['C-TYPO', 'RT-FIXTURE'])
def test_assumption_supports_must_name_library_claims(claim):
    lib = evidence_library()
    lib['assumptions'][0]['supports'].append({'claim': claim, 'relation': 'bounds'})
    assert library_problems(lib) == {('provenance', 'library/assumptions/0/supports/1')}
    assert rejected(sc99(), lib) == {('provenance', 'library/assumptions/0/supports/1')}


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


def test_the_library_relations_are_closed_and_a_record_writes_none():
    schema = json.loads((SCHEMAS / 'library.schema.json').read_text())
    assert set(schema['$defs']['relation']['enum']) == RELATIONS
    lib = evidence_library()
    lib['assumptions'][0]['supports'][0]['relation'] = 'supports'
    assert rejected(sc99(), lib) == {('schema', 'assumptions/0/supports/0/relation')}
    related = in_place('source', 'A relation that the library knows.', 'C-ACTION: mechanism_support')
    text = resting(sc99(), 'service/n', related)
    # A record lists each claim by its ID alone, so the line of the claim is rejected as a whole.
    assert located(text) == {('syntax', '', line_of(text, 'C-ACTION: mechanism_support'))}


def test_model_redteam_requires_its_elicitation():
    lib = evidence_library()
    del lib['assumptions'][0]['elicitation']
    assert rejected(sc99(), lib) == {('schema', 'assumptions/0')}
    lib['assumptions'][0]['origin'] = 'author'
    compiled(sc99(), lib)


def limited(*records):
    """sc99 with the limitation RF, which rests on `records`."""
    return edit(sc99(), member('notes:', block('limitations:', block('RF: "Fixture."', *records))))


def test_review_limitation_bases_are_typed_and_resolved():
    place = 'notes:/limitations:/RF:'
    compiled(
        limited(in_place('source_transfer', 'Contract fixture.', 'C-ACTION'), assumed('RT-FIXTURE')),
        evidence_library(),
    )
    for claim in ('C-TYPO', 'RT-FIXTURE'):
        text = limited(source(claim))
        assert located(text) == {('provenance', f'{place}/links/0', line_of(text, 'RF: '))}
    for name in ('A-TYPO', 'C-ACTION'):
        text = limited(assumed(name))
        assert located(text) == {('provenance', place, line_of(text, 'RF: '))}
    # A claim's line names one claim, and only its datum sits under it: a line that names two claims, or
    # an assumption under a claim, is rejected as a whole.
    for claim, wrong in (
        ('C-ACTION C-ACCESS', 'C-ACTION C-ACCESS'),
        (block('C-ACTION', 'assumption: RT-FIXTURE'), 'assumption:'),
    ):
        text = limited(source(claim))
        assert located(text) == {('syntax', '', line_of(text, wrong))}


def shown(record):
    """sc99 with a status that rests on `record`, written in place under its first line."""
    lines = (block('status failed when state is "off"', '"Stopped"', record), block('status ok', '"Running"'))
    return edit(sc99(), member('service', *lines))


def test_status_bases_resolve_before_any_renderer_reads_them():
    place = 'service/status:'
    for record, where in (
        (source('C-TYPO'), f'{place}/links/0'),
        (source(block('C-ACTION', 'datum: d')), f'{place}/links/0'),
        (assumed('A-TYPO'), place),
    ):
        text = shown(record)
        assert located(text) == {('provenance', where, line_of(text, 'status failed'))}


@pytest.mark.parametrize(
    ('datum', 'code'),
    [('datum: ["d"]', 'syntax'), (block('datum:', 'name: d'), 'syntax'), ('datum: 3', 'provenance')],
    ids=['datum0', 'datum1', '3'],
)
def test_review_datum_that_is_not_a_name_is_a_provenance_error(datum, code):
    # A datum names a key of the claim's data. The reader rejects a list or a record at the line of the
    # datum; a number is a word that names no key of the data, a provenance error of the premise.
    text = edit(sc99(), member('notes:/premises:', block('P1: "Fixture."', source(block('C-ACTION', datum)))))
    expected = {
        'syntax': ('syntax', '', line_of(text, 'datum:')),
        'provenance': ('provenance', 'notes:/premises:/P1:/links/0', line_of(text, 'P1: ')),
    }[code]
    assert located(text) == {expected}


def test_copied_verification_status_is_rejected_anywhere():
    # A note holds any keys, and the catalogue's pages reject a copied status there at its own place.
    noted = edit(sc99(), member('notes:/premises:', block('P1: "Fixture."', 'verification_status: partial')))
    with pytest.raises(ModelError) as raised:
        pages(compiled(noted, evidence_library()))
    assert [(d['path'], d['line']) for d in raised.value.diagnostics] == [
        ('notes:/premises:/P1:/verification_status:', line_of(noted, 'verification_status:'))
    ]
    # Under a claim of a record only its datum sits, so a copied status there is rejected as a whole.
    copied = source(block('C-ACTION', 'verification_status: verified'))
    cited = edit(sc99(), member('service/n', copied))
    assert located(cited) == {('syntax', '', line_of(cited, 'verification_status:'))}


def versus(text, run):
    """`text` whose run `b` is compared with `run`."""
    line = 'b = "Default" + "Half rate"'
    return edit(text, replace(line, f'{line}  versus {run}'))


def test_a_run_declares_only_its_options_name_and_comparison():
    compared = versus(sc99(), 'a')
    assert compiled(compared, evidence_library()).runs['b']['comparison_of'] == 'a'
    text = edit(compared, member('runs:/b', 'adversary: true'))
    # Reported at the line of the key itself.
    assert located(text) == {('syntax', '', line_of(text, 'adversary: true'))}
    text = versus(sc99(), 'missing')
    assert located(text) == {('structure', 'runs:/b/versus:', line_of(text, 'versus missing'))}


def test_library_basis_links_are_resolved_too():
    # A convention of the library rests on a claim, as an assumption does.
    lib = evidence_library()
    supports = [{'claim': 'C-TYPO', 'relation': 'accounting_rule'}]
    lib['conventions'] = [{'id': 'ROUNDING', 'statement': 'Rule.', 'supports': supports}]
    assert library_problems(lib) == {('provenance', 'library/conventions/0/supports/0')}
    assert rejected(scenario(), lib) == {('provenance', 'library/conventions/0/supports/0')}
    lib['conventions'][0]['supports'][0]['claim'] = 'C-ACTION'
    compiled(scenario(), lib)


def test_a_convention_record_names_a_convention_of_the_library():
    """`record r: convention ID \"…\"` cites the library's convention ID: an unknown ID is an error, and
    the convention, with the claims that support it, is part of what the model reaches."""
    lib = evidence_library()
    lib['conventions'] = [
        {
            'id': 'ROUNDING',
            'statement': 'Rule.',
            'supports': [{'claim': 'C-ACCESS', 'relation': 'accounting_rule'}],
        }
    ]
    cited = edit(
        scenario(), replace(FIXTURE_RECORD, 'record fixture: convention ROUNDING "The rounding rule."')
    )
    model = compiled(cited, lib)
    assert [record['id'] for record in model.library['conventions']] == ['ROUNDING']
    assert 'C-ACCESS' in {record['id'] for record in model.library['claims']}
    changed = copy.deepcopy(lib)
    changed['conventions'][0]['statement'] = 'Another rule.'
    assert compiled(cited, changed).model_hash != model.model_hash
    assert ('provenance', 'record:/fixture') in rejected(cited.replace('ROUNDING', 'ROUNDED'), lib)


def test_a_library_with_a_harm_scale_is_refused_by_its_schema():
    # The harm scale is gone from the library format; a library that still has one is not read.
    lib = evidence_library()
    assert library_checks(lib)[0] == []
    lib['harm_scale'] = {'dimensions': ['deaths'], 'level_names': ['Zero', 'Minor']}
    found = library_checks(lib)[0]
    assert [(d['code'], d['path']) for d in found] == [('schema', '')]
    assert 'harm_scale' in found[0]['message']
    with pytest.raises(ModelError):
        compiled(scenario(), lib)
