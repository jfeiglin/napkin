"""Each published dossier identifies only its folder's evidence, including in a selected build."""

import copy
import json

from tests.evidence.support import QUEUE, SERVICE, evidence_library, fixture_claim, write_package
from tools import catalogue
from tools.publish import Context, build, dossier


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
        write_package(root, {'model.scn': SERVICE}, library, owner=sid)
    return library


def test_same_id_records_of_two_folders_stay_in_their_own_outputs(tmp_path):
    original = write_pair(tmp_path)
    source_path = tmp_path / 'scenarios/SC98/evidence/sources.json'
    sources = json.loads(source_path.read_text())
    sources[0]['title'] = 'Independent local revision'
    source_path.write_text(json.dumps(sources))
    ctx = Context(tmp_path)
    output = dossier.artifacts(ctx)
    assert set(output) == {catalogue.result(sid, 'source-dossier.json') for sid in ('SC97', 'SC98')}
    titles = {'SC97': original['sources'][0]['title'], 'SC98': 'Independent local revision'}
    for sid, title in titles.items():
        local = json.loads(output[catalogue.result(sid, 'source-dossier.json')])
        # The folder's own source under its own title; the shared vocabulary's provenance is no folder's.
        assert [source['source_id'] for source in local['sources']] == ['src']
        assert local['sources'][0]['title'] == title
        assert all(record['scenario'] == sid for record in local['sources'][0]['claims'])


def test_selected_publication_emits_only_that_folders_evidence_outputs(tmp_path):
    write_pair(tmp_path)
    ctx = Context(tmp_path, scenario_ids=['SC98'])
    output = build(ctx, only=['dossier'])
    assert set(output) == {
        'scenarios/SC98/results/source-dossier.json',
    }


def test_a_scenario_without_evidence_has_an_empty_dossier(tmp_path):
    write_package(tmp_path, {'model.scn': QUEUE})
    ctx = Context(tmp_path)
    local = json.loads(dossier.artifacts(ctx)['scenarios/SC99/results/source-dossier.json'])
    assert local['sources'] == []
    assert local['summary']['claims'] == 0
