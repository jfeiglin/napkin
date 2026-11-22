"""Publication uses saved edits for their model revision and run records for their executing engine."""

import json

import pytest

from napkin import store
from napkin.engine import edits_for, read
from napkin.engine.study import study
from napkin.model import LanguageError, load_scenario
from tests.evidence.support import QUEUE, SERVICE, evidence_library, fixture_claim, write_package
from tools.publish import Context, dossier


def test_saved_edits_survive_a_new_engine_digest_and_reject_a_different_model(tmp_path, monkeypatch):
    path = write_package(tmp_path, {'model.scn': QUEUE})
    model = load_scenario(path)
    edits = edits_for(model, {'set': {'queue.arrivals': 2}})
    config = model.configure(edits=edits)
    key = store.key(model.program, config)
    monkeypatch.setattr(store, 'ENGINE_DIGEST', '0' * 64)
    assert store.key(model.program, config) != key
    record = study(model, edits=edits)[None]
    assert read(record, model.program, ['queue.waiting'], [4])[0].values == (8,)

    path.write_text(QUEUE.replace('horizon 4 h', 'horizon 8 h'))
    revised = load_scenario(path)
    assert revised.model_hash != model.model_hash
    with pytest.raises(LanguageError, match='revision'):
        study(revised, edits=edits)


def test_dossier_reachability_includes_review_lists_and_related_claims(tmp_path):
    library = evidence_library()
    library['sources'][0]['custom']['verification']['url'] = 'https://example.test/source'
    library['claims'].extend(
        [
            fixture_claim('C-REVIEW', related=[{'claim': 'C-RELATED', 'relation': 'context_limitations'}]),
            fixture_claim('C-RELATED'),
        ]
    )
    note = """
notes:
    benchmark:
        source: "The benchmark."
            @source_transfer "Benchmark evidence."
                claims:
                    C-REVIEW
"""
    write_package(tmp_path, {'model.scn': SERVICE + note}, library)
    path = 'scenarios/SC99/results/source-dossier.json'
    result = json.loads(dossier.artifacts(Context(tmp_path))[path])
    reached = {
        record['id']: record['reachable_from_scenarios']
        for source in result['sources']
        for record in source['claims']
    }
    assert reached['C-REVIEW'] == reached['C-RELATED'] == ['SC99']


def test_a_worker_that_loads_a_different_model_revision_is_refused(tmp_path):
    first = write_package(tmp_path, {'model.scn': QUEUE}, owner='SC97')
    write_package(tmp_path, {'model.scn': QUEUE}, owner='SC98')
    ctx = Context(tmp_path, jobs=2)
    assert set(ctx.models) == {'SC97', 'SC98'}
    # The parent has both compiled models. A worker now opens the changed file.
    first.write_text(QUEUE.replace('horizon 4 h', 'horizon 5 h'))
    with pytest.raises(ValueError, match='SC97: a worker built another model revision'):
        _ = ctx.studies
