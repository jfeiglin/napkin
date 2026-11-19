"""Adoption copies the dependency closure without linking independent records, and pack integration
writes the folder of a package that its variants read. The packages are synthetic, under tmp_path
(`tests/evidence/support.py`)."""

import copy
import json

import pytest

from napkin.model.evidence import claim_digest
from tests.evidence.support import QUEUE, evidence_library, family, write_package
from tests.units import library
from tools.evidence.adopt import adopt, main
from tools.evidence.integrate import IntegrationError
from tools.evidence.integrate import main as integrate


def linked():
    source = evidence_library()
    first, second = source['claims'][:2]
    first['related'] = [{'claim': second['id'], 'relation': 'consistent_with'}]
    second['related'] = [{'claim': first['id'], 'relation': 'consistent_with'}]
    for claim in (first, second):
        claim['verification']['content_sha256'] = claim_digest(claim)
    source['assumptions'][0]['supports'] = [{'claim': first['id'], 'relation': 'mechanism_precedent'}]
    return source


def test_adopt_follows_supports_related_cycles_and_sources_and_copies_independently():
    source, destination = linked(), library()
    before = copy.deepcopy(source)
    result = adopt(source, destination, 'RT-FIXTURE')
    assert [r['id'] for r in result['claims']] == ['C-ACCESS', 'C-ACTION']
    assert [r['id'] for r in result['sources']] == ['src']
    assert result['assumptions'] == source['assumptions']
    result['claims'][0]['shows'] = 'Locally revised'
    assert source == before and destination['claims'] == []


def test_adopt_same_content_is_idempotent_but_a_conflicting_copy_is_rejected():
    source = linked()
    once = adopt(source, library(), 'RT-FIXTURE')
    assert adopt(source, once, 'RT-FIXTURE') == once
    once['claims'][0]['shows'] = 'Independent destination revision'
    with pytest.raises(IntegrationError, match='Conflicting destination claims'):
        adopt(source, once, 'RT-FIXTURE')


def test_adopt_carries_domain_units_and_rejects_a_conflicting_definition():
    source = linked()
    source['units']['jobs'] = {'dimensions': {'jobs': 1}, 'scale': 1}
    source['claims'][0]['data'] = {'count': {'value': 2, 'unit': 'jobs'}}
    source['claims'][0]['verification']['content_sha256'] = claim_digest(source['claims'][0])
    result = adopt(source, library(), 'C-ACCESS')
    assert result['units']['jobs'] == source['units']['jobs']
    destination = library()
    destination['units']['jobs'] = {'dimensions': {'jobs': 1}, 'scale': 2}
    with pytest.raises(IntegrationError, match='Conflicting destination unit'):
        adopt(source, destination, 'C-ACCESS')


def test_a_unit_that_differs_only_in_its_description_is_the_same_unit():
    source = linked()
    source['units']['jobs'] = {'dimensions': {'jobs': 1}, 'scale': 1}
    source['claims'][0]['data'] = {'count': {'value': 2, 'unit': 'jobs'}}
    source['claims'][0]['verification']['content_sha256'] = claim_digest(source['claims'][0])
    destination = library()
    held = {'dimensions': {'jobs': 1}, 'scale': 1, 'description': 'Filled positions.'}
    destination['units']['jobs'] = held
    assert adopt(source, destination, 'C-ACCESS')['units']['jobs'] == held


def test_adopt_writes_a_packages_folder_and_leaves_the_source_alone(tmp_path):
    # The package SC97, whose main file uses its module, takes a record of SC98 into its own folder.
    family(tmp_path)
    source = linked()
    write_package(tmp_path, {'model.scn': QUEUE}, source, owner='SC98')
    args = ['--root', str(tmp_path), '--from', 'SC98', '--to', 'SC97', '--id', 'RT-FIXTURE']
    assert main(args) == 0
    assert json.loads((tmp_path / 'scenarios/SC97/evidence/assumptions.json').read_text()) == []
    assert main([*args, '--write']) == 0
    written = json.loads((tmp_path / 'scenarios/SC97/evidence/assumptions.json').read_text())
    assert [record['id'] for record in written] == ['RT-FIXTURE']
    claims = json.loads((tmp_path / 'scenarios/SC97/evidence/claims.json').read_text())
    assert [record['id'] for record in claims] == ['C-ACCESS', 'C-ACTION']
    held = json.loads((tmp_path / 'scenarios/SC98/evidence/assumptions.json').read_text())
    assert held == source['assumptions']
    assert main([*args[:-1], 'NOT-THERE']) == 1


LATER = {
    'id': 'A-LATER',
    'title': 'Later',
    'statement': 'The arrivals are an assumption.',
    'rationale': 'A fixture.',
    'status': 'selected',
    'origin': 'author',
    'review': {'status': 'unreviewed'},
    'supports': [],
    'evidence_needed': 'None: a fixture.',
    'decided': {'by': 'fixture', 'date': '2026-10-28'},
}


def packed(tmp_path, upsert):
    """The arguments of pack integration with one pack of assumptions for SC97, which upserts these."""
    folder = tmp_path / 'packs'
    folder.mkdir(exist_ok=True)
    found = {'pack_version': '1', 'kind': 'assumptions', 'scenario': 'SC97', 'upsert': upsert, 'retire': []}
    (folder / 'pack.json').write_text(json.dumps(found))
    return ['--root', str(tmp_path), '--packs', str(folder), '--report', str(tmp_path / 'report.json')]


def test_integrate_adds_an_assumption_that_the_model_already_cites(tmp_path):
    # The module cites A-LATER before any folder holds it: the pack that adds it writes, and a model
    # that still cites a missing record is refused, in a dry run too.
    record = '\nrecord later: assumption "A later assumption."\n    assumption A-LATER\n'
    family(tmp_path, records='@later', extra=record)
    args = packed(tmp_path, [LATER])
    assert integrate(args) == 0
    assert integrate([*args, '--write']) == 0
    written = json.loads((tmp_path / 'scenarios/SC97/evidence/assumptions.json').read_text())
    assert [record['id'] for record in written] == ['A-LATER']
    # A pack that adds something else leaves the citation unresolved.
    (tmp_path / 'scenarios/SC97/evidence/assumptions.json').write_text('[]')
    assert integrate(packed(tmp_path, [{**LATER, 'id': 'A-OTHER'}])) == 1


def test_integrate_prunes_the_records_that_no_reader_reaches(tmp_path):
    # The module cites A-KEPT; the package's folder also holds A-UNUSED, which nothing cites.
    record = '\nrecord kept: assumption "A kept assumption."\n    assumption A-KEPT\n'
    lib = library()
    lib['assumptions'] = [{**LATER, 'id': 'A-KEPT'}, {**LATER, 'id': 'A-UNUSED'}]
    family(tmp_path, lib, records='@kept', extra=record)
    folder = tmp_path / 'scenarios/SC97/evidence'
    args = [*packed(tmp_path, []), '--write']
    assert integrate(args) == 0
    assert {r['id'] for r in json.loads((folder / 'assumptions.json').read_text())} == {'A-KEPT', 'A-UNUSED'}
    assert integrate([*args, '--prune']) == 0
    assert {r['id'] for r in json.loads((folder / 'assumptions.json').read_text())} == {'A-KEPT'}
