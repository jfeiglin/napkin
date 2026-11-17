"""Publication preserves independent record ownership: each scenario's dossier and inventory list the
records of its own folder, and no output covers the catalogue as a whole."""

import copy
import json

from tests.build import evidence_library, fixture_claim, sc99, scenario
from tests.owned import write_scenario
from tools import catalogue
from tools.publish import Context, assumptions, build, dossier


def write_pair(root):
    library = evidence_library()
    library['sources'][0]['custom']['verification']['url'] = 'https://example.test/owned'
    shared = copy.deepcopy(library['sources'][0])
    shared.update(id='shared-source', title='Shared convention provenance')
    library['sources'].append(shared)
    library['claims'].append(fixture_claim('C-SHARED', source='shared-source'))
    supports = [{'claim': 'C-SHARED', 'relation': 'adopts'}]
    library['conventions'] = [{'id': 'SCALE', 'statement': 'A shared rule.', 'supports': supports}]
    for sid in ('SC97', 'SC98'):
        write_scenario(root, sc99(), library, owner=sid)
    return library


def test_same_id_records_of_two_folders_stay_in_their_own_outputs(tmp_path):
    original = write_pair(tmp_path)
    source_path = tmp_path / 'scenarios/SC98/evidence/sources.json'
    sources = json.loads(source_path.read_text())
    sources[0]['title'] = 'Independent local revision'
    source_path.write_text(json.dumps(sources))
    assumption_path = tmp_path / 'scenarios/SC98/evidence/assumptions.json'
    owned = json.loads(assumption_path.read_text())
    owned[0]['rationale'] = 'Independent local assumption rationale.'
    assumption_path.write_text(json.dumps(owned))
    ctx = Context(tmp_path)
    output = dossier.artifacts(ctx)
    inventories = assumptions.artifacts(ctx)
    # One dossier and one inventory for each scenario, in its results folder; none for the catalogue.
    for sid in ('SC97', 'SC98'):
        assert catalogue.result(sid, 'source-verification.json') in output
        assert catalogue.result(sid, 'assumption-review.json') in inventories
    assert len(output) == len(inventories) == 2
    titles = {'SC97': original['sources'][0]['title'], 'SC98': 'Independent local revision'}
    for sid, title in titles.items():
        local = json.loads(output[catalogue.result(sid, 'source-verification.json')])
        # The folder's own source under its own title; the shared vocabulary's provenance is no folder's.
        assert [source['source_id'] for source in local['sources']] == ['src']
        assert local['sources'][0]['title'] == title
        assert all(record['scenario'] == sid for record in local['sources'][0]['claims'])
        inventory = json.loads(inventories[catalogue.result(sid, 'assumption-review.json')])
        assert [(row['scenario'], row['id']) for row in inventory['assumptions']] == [(sid, 'RT-FIXTURE')]
        assert 'fresh_machine_review' not in inventory['assumptions'][0]


def test_selected_publication_emits_only_that_folders_evidence_outputs(tmp_path):
    write_pair(tmp_path)
    ctx = Context(tmp_path, scenario_ids=['SC98'])
    output = build(ctx, only=['dossier', 'assumptions'])
    assert set(output) == {
        'scenarios/SC98/results/source-verification.json',
        'scenarios/SC98/results/assumption-review.json',
    }


def test_a_scenario_without_evidence_has_empty_local_inventories(tmp_path):
    write_scenario(tmp_path, scenario())
    ctx = Context(tmp_path)
    local = json.loads(dossier.artifacts(ctx)['scenarios/SC99/results/source-verification.json'])
    assert local['sources'] == []
    assert local['summary']['claims'] == 0
    inventory = json.loads(assumptions.artifacts(ctx)['scenarios/SC99/results/assumption-review.json'])
    assert inventory['assumptions'] == []
