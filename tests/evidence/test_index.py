"""E12: evidence lineage. A value that a run reports traces to the parts of its evidence trail, their
records, and the claims and assumptions of the library behind them, each with its status
(`tools/evidence/trail.py` over `napkin/engine/report.py`); the front end resolves each reference of a
record, reads only the lines that a record has, and checks that a datum names data of its claim.

The model is the synthetic service of `tests/evidence/support.py`: 20 people wait, the service serves
2 people/h (1 people/h under the option "Half rate") until its stop at 8 h, so 16 are served (8 under
the run `half`) by the horizon of 10 h.
"""

from __future__ import annotations

import copy
import re
import textwrap
from dataclasses import replace

import pytest

from napkin.engine.report import report
from napkin.engine.timeline import run
from napkin.expressions import UnitSystem
from napkin.model import ModelError
from napkin.model.compile import compile_text, library_units, load_scenario
from napkin.model.evidence import datum_matches
from napkin.model.language.evidence import document
from napkin.model.language.parse import parse
from napkin.model.language.problems import LanguageError
from napkin.program.config import InputValue, Quantity
from tests.evidence.support import SERVICE, evidence_library, fixture_claim, write_package
from tools.evidence.trail import disclosures, evidence

# The end of the service may lie after the horizon, so that its stop does not start.
LATE = SERVICE.replace('input end: h = 8 h in [1 h, 10 h]', 'input end: h = 8 h in [1 h, 20 h]')


def served(root, text=SERVICE, library=None, name=None, **inputs):
    """(the report of `service.served` at 10 h, its evidence, the compiled model) of a run of the package
    written below `root`: the named run `name`, or the default run, with the service's `inputs`."""
    library = evidence_library() if library is None else library
    compiled = load_scenario(write_package(root, {'model.scn': text}, library), run=name)
    given = tuple(InputValue('service', key, Quantity(*value)) for key, value in inputs.items())
    configuration = replace(compiled.configuration, inputs=compiled.configuration.inputs + given)
    record = run(compiled.program, configuration)
    found = report(record, compiled.program, configuration, ['service.served'], [10], model=compiled.declared)
    options = compiled.declared.run(name).options if name else ()
    (traced,) = evidence(found, compiled.declared, library, options)
    return found, traced, compiled


def parts(traced):
    """{(kind, origin): (exercised, [(record name, option) of each use])} of a value's evidence."""
    return {
        (used.kind, used.origin): (used.exercised, [(use.name, use.option) for use in uses])
        for used, uses in traced.parts
    }


def test_a_reported_value_traces_to_its_parts_records_claims_and_assumptions(tmp_path):
    found, traced, _ = served(tmp_path, name='half')
    assert found.values[0].label == 'People served' and found.values[0].values == pytest.approx((8,))
    trail = parts(traced)
    # The rate rests on its own record and on the option of the run that halves it.
    assert trail['value', 'service.rate'] == (True, [('access', None), ('halved', 'Half rate')])
    assert trail['event', 'service.stop'] == (True, [(None, None)])
    assert trail['flow', 'service.serve'] == (True, [('fixture', None)])
    assert trail['trigger', 'service.stop.when[0]'][0] and trail['stage', 'service.stop.step[0]'][0]
    # C-ACTION supports RT-FIXTURE, on which the stop and the option rest.
    assert traced.reached.claims == {'C-ACCESS': 'unverified', 'C-ACTION': 'unverified'}
    assert traced.reached.assumptions == {'RT-FIXTURE': 'unreviewed'}
    assert traced.reached.sources == ('src',) and traced.possible.claims == {}
    assert disclosures(traced) == [
        'the claim C-ACCESS is unverified',
        'the claim C-ACTION is unverified',
        'the assumption RT-FIXTURE is unreviewed',
    ]


def test_the_default_run_rests_on_no_option(tmp_path):
    found, traced, _ = served(tmp_path)
    assert found.values[0].values == pytest.approx((16,))
    assert parts(traced)['value', 'service.rate'] == (True, [('access', None)])


def test_an_event_that_did_not_start_is_what_a_value_could_rest_on(tmp_path):
    # With the end at 12 h the stop never starts: the 20 people are served at 2 people/h by 10 h. Its
    # assumption, and the claim that supports it, are what the value could rest on, not what it does.
    found, traced, _ = served(tmp_path, LATE, end=(12, 'h'))
    assert found.values[0].values == pytest.approx((20,))
    assert parts(traced)['event', 'service.stop'] == (False, [(None, None)])
    assert traced.reached.claims == {'C-ACCESS': 'unverified'} and traced.reached.assumptions == {}
    assert traced.possible.assumptions == {'RT-FIXTURE': 'unreviewed'}
    assert traced.possible.claims == {'C-ACTION': 'unverified'}
    assert disclosures(traced) == ['the claim C-ACCESS is unverified']


def test_an_input_that_keeps_a_flow_still_is_exercised(tmp_path):
    # At no rate the flow moves nothing, yet its rate was read: the rate's claim is what the value
    # rests on.
    found, traced, _ = served(tmp_path, rate=(0, 'people/h'))
    assert found.values[0].values == pytest.approx((0,))
    trail = parts(traced)
    assert not trail['flow', 'service.serve'][0] and trail['value', 'service.rate'][0]
    assert 'C-ACCESS' in traced.reached.claims


def test_a_record_revision_changes_the_evidence_and_neither_the_hash_nor_the_trail(tmp_path):
    revised = evidence_library()
    revised['assumptions'][0]['statement'] += ' Revised.'
    # A machine red-team record is never confirmed: a review replaces it.
    revised['assumptions'][0]['review'] = {'status': 'replaced', 'by': 'a reviewer', 'date': '2026-10-01'}
    before, first, one = served(tmp_path / 'before')
    after, second, other = served(tmp_path / 'after', library=revised)
    assert one.model_hash == other.model_hash
    assert before.values == after.values and before.records == after.records
    assert (first.reached.assumptions, second.reached.assumptions) == (
        {'RT-FIXTURE': 'unreviewed'},
        {'RT-FIXTURE': 'replaced'},
    )
    assert disclosures(second)[-1] == 'the assumption RT-FIXTURE is replaced'


def compiled(text):
    return compile_text(textwrap.dedent(text), library_units(evidence_library()))


def line_of(text, words):
    (number,) = [number for number, row in enumerate(text.split('\n'), 1) if words in row]
    return number


def test_a_record_has_no_review_of_its_applicability():
    """A record is its kind, its explanation, the records that it rests on and its claims: a line
    `applicability:` under it is not a line of the language."""
    text = SERVICE + 'record other: identity "Another."\n    applicability:\n        fingerprint: x\n'
    with pytest.raises(LanguageError) as raised:
        compiled(text)
    assert [(item.code, item.line) for item in raised.value.problems] == [
        ('syntax', line_of(text, 'applicability:'))
    ]


@pytest.mark.parametrize(
    'record, path, message',
    [
        (
            '@source "Cites a missing claim."\n            claims:\n                T_MISSING',
            'service.rate/0/links/0',
            'Unknown claim T_MISSING',
        ),
        (
            '@assumption "Rests on a missing one."\n            assumption T_MISSING',
            'service.rate/0/rests_on/0',
            'Unknown assumption T_MISSING',
        ),
    ],
    ids=['claim', 'assumption'],
)
def test_a_missing_record_is_refused_at_its_part(tmp_path, record, path, message):
    text = SERVICE.replace(
        '    input rate: people/h = 2 people/h in [0 people/h, 10 people/h]  @access\n',
        f'    input rate: people/h = 2 people/h in [0 people/h, 10 people/h]\n        {record}\n',
    )
    entry = write_package(tmp_path, {'model.scn': text}, evidence_library())
    with pytest.raises(ModelError) as caught:
        load_scenario(entry)
    found = [(d['code'], d['path'], d['message']) for d in caught.value.diagnostics]
    assert found == [('provenance', path, message)]


def test_a_name_that_a_file_chooses_never_holds_a_record():
    """Only the lines of the language hold records: values named as the words of a record (`claims`,
    `datum`, `assumption`, `source`, `convention`) are ordinary names, so each record stays where it was
    and no name becomes one."""
    names = {'n': 'claims', 'rate': 'datum', 'end': 'assumption', 'waiting': 'source', 'served': 'convention'}
    text = SERVICE
    for old, new in names.items():
        text = text.replace(f'input {old}:', f'input {new}:').replace(f'    {old}:', f'    {new}:')
        text = text.replace(f'this.{old}', f'this.{new}').replace(f'service.{old} =', f'service.{new} =')
    compiled(text)

    def back(path):
        for old, new in names.items():
            path = re.sub(rf'\bservice\.{new}\b', f'service.{old}', path)
        return path

    assert {back(path): records for path, records in document(parse(text)).items()} == document(
        parse(SERVICE)
    )


def test_a_datum_names_data_of_its_claim_and_matches_after_unit_conversion_only(tmp_path):
    units = UnitSystem(
        {'L': {'dimensions': {'volume': 1}, 'scale': 1}, 'm3': {'dimensions': {'volume': 1}, 'scale': 1000}}
    )
    datum = {'value': 100, 'unit': 'L'}
    assert datum_matches(0.1, 'm3', datum, units) and datum_matches(100, 'L', datum, units)
    assert not datum_matches(80, 'L', datum, units)
    # The record of the people waiting names the datum `count` of C-ACCESS, which has no data.
    text = SERVICE.replace(
        '    claims:\n        C-ACCESS\n', '    claims:\n        C-ACCESS\n            datum: count\n'
    )
    library = evidence_library()
    with pytest.raises(ModelError) as caught:
        load_scenario(write_package(tmp_path / 'none', {'model.scn': text}, library))
    assert [d['message'] for d in caught.value.diagnostics] == ['Unknown datum count']
    data = copy.deepcopy(library)
    data['claims'][0] = fixture_claim('C-ACCESS', data={'count': {'value': 2, 'unit': 'people/h'}})
    load_scenario(write_package(tmp_path / 'data', {'model.scn': text}, data))
