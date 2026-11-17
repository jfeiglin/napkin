"""Adoption copies the dependency closure without linking independent records."""

import copy

import pytest

from napkin.model.evidence import claim_digest
from tests.build import evidence_library, library
from tools.evidence.adopt import adopt
from tools.evidence.integrate import IntegrationError


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
    import json

    from tests.model.test_modules import family
    from tools.evidence.adopt import main

    paths = family(tmp_path)
    source = linked()
    for kind in ('sources', 'claims', 'assumptions'):
        (paths['SC98/model.scn'].parent / 'evidence' / f'{kind}.json').write_text(json.dumps(source[kind]))
    args = ['--root', str(tmp_path), '--from', 'SC98', '--to', 'SC97', '--id', 'RT-FIXTURE']
    assert main(args) == 0
    assert json.loads((tmp_path / 'scenarios/SC97/evidence/assumptions.json').read_text()) == []
    assert main([*args, '--write']) == 0
    written = json.loads((tmp_path / 'scenarios/SC97/evidence/assumptions.json').read_text())
    assert [record['id'] for record in written] == ['RT-FIXTURE']
    held = json.loads((tmp_path / 'scenarios/SC98/evidence/assumptions.json').read_text())
    assert held == source['assumptions']
    assert main([*args[:-1], 'NOT-THERE']) == 1


def test_integrate_adds_an_assumption_that_the_model_already_cites(tmp_path):
    # The module cites A-LATER before any folder holds it: the pack that adds it writes, and a model
    # that still cites a missing record is refused, in a dry run too.
    import json

    from tests.model.test_modules import module, scenario, variant
    from tests.owned import write_family
    from tools.evidence.integrate import main

    later = module().replace(
        '    input start_water: people = {water} in 1 people to 100 people  @fixture'.format(
            water='30 people'
        ),
        '    input start_water: people = 30 people in 1 people to 100 people  @later',
    )
    assert '@later' in later
    text = later + '\nrecord later: assumption A-LATER "A later assumption."\n'
    write_family(
        tmp_path,
        {
            'SC97/common.scn': text,
            'SC97/model.scn': scenario(body=''),
            'SC97/variants/a/model.scn': variant('A'),
        },
    )
    assumption = {
        'id': 'A-LATER',
        'title': 'Later',
        'statement': 'The starting water is an assumption.',
        'rationale': 'A fixture.',
        'status': 'selected',
        'origin': 'author',
        'review': {'status': 'unreviewed'},
        'supports': [],
        'evidence_needed': 'None: a fixture.',
        'decided': {'by': 'fixture', 'date': '2026-10-28'},
    }
    packs = tmp_path / 'packs'
    packs.mkdir()
    pack = {
        'pack_version': '1',
        'kind': 'assumptions',
        'scenario': 'SC97',
        'upsert': [assumption],
        'retire': [],
    }
    (packs / 'later.json').write_text(json.dumps(pack))
    args = ['--root', str(tmp_path), '--packs', str(packs), '--report', str(tmp_path / 'report.json')]
    assert main(args) == 0
    assert main([*args, '--write']) == 0
    written = json.loads((tmp_path / 'scenarios/SC97/evidence/assumptions.json').read_text())
    assert [record['id'] for record in written] == ['A-LATER']
    # A pack that adds something else leaves the citation unresolved.
    (tmp_path / 'scenarios/SC97/evidence/assumptions.json').write_text('[]')
    pack['upsert'] = [{**assumption, 'id': 'A-OTHER'}]
    (packs / 'later.json').write_text(json.dumps(pack))
    assert main(args) == 1


def test_integrate_prunes_the_records_that_no_reader_reaches(tmp_path):
    import json

    from tests.model.test_modules import module, scenario, variant
    from tests.owned import write_family
    from tools.evidence.integrate import main

    write_family(
        tmp_path,
        {
            'SC97/common.scn': module(),
            'SC97/model.scn': scenario(body=''),
            'SC97/variants/a/model.scn': variant('A'),
        },
    )
    folder = tmp_path / 'scenarios/SC97/evidence'
    unused = {
        'id': 'A-UNUSED',
        'title': 'Unused',
        'statement': 'Nothing cites this assumption.',
        'rationale': 'A fixture.',
        'status': 'selected',
        'origin': 'author',
        'review': {'status': 'unreviewed'},
        'supports': [],
        'evidence_needed': 'None: a fixture.',
        'decided': {'by': 'fixture', 'date': '2026-10-29'},
    }
    kept = json.loads((folder / 'assumptions.json').read_text())
    (folder / 'assumptions.json').write_text(json.dumps([*kept, unused]))
    packs = tmp_path / 'packs'
    packs.mkdir()
    empty = {'pack_version': '1', 'kind': 'assumptions', 'scenario': 'SC97', 'upsert': [], 'retire': []}
    (packs / 'empty.json').write_text(json.dumps(empty))
    args = [
        '--root',
        str(tmp_path),
        '--packs',
        str(packs),
        '--report',
        str(tmp_path / 'report.json'),
        '--write',
    ]
    assert main(args) == 0
    assert 'A-UNUSED' in {r['id'] for r in json.loads((folder / 'assumptions.json').read_text())}
    assert main([*args, '--prune']) == 0
    remaining = {r['id'] for r in json.loads((folder / 'assumptions.json').read_text())}
    assert 'A-UNUSED' not in remaining
    assert remaining == {r['id'] for r in kept}
