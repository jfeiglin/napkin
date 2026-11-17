"""Consumer freshness follows both the authored model and its executing implementation."""

from dataclasses import replace

import pytest

from napkin.engine import edits_for, evaluate_study, sample_result
from napkin.model.ir import thaw
from napkin.model.language import front
from napkin.model.language.resolve import resolve
from tests.build import (
    block,
    compiled,
    edit,
    evidence_library,
    fixture_claim,
    in_place,
    member,
    sc99,
    scenario,
)
from tests.helpers import ROOT
from tools.publish import runs
from tools.publish.dossier import dossier


def test_saved_inputs_survive_an_implementation_revision():
    model = compiled(scenario())
    edits = edits_for(model, {'set': {'service.n': 18}})
    revised = replace(model, implementation_hash='0' * 64)
    result = evaluate_study(revised, edits)
    assert result.admissible
    assert result.model_hash == model.model_hash
    assert result.implementation_hash == revised.implementation_hash
    report = sample_result(result)
    assert report['implementation_hash'] == revised.implementation_hash
    assert result.effective_edits == edits
    assert 'implementation_hash' not in edits


def test_dossier_reachability_includes_review_lists_and_related_claims():
    library = evidence_library()
    library['sources'][0]['custom']['verification']['url'] = 'https://example.test/source'
    library['claims'].extend(fixture_claim(name) for name in ('C-REVIEW', 'C-RELATED'))
    review = next(record for record in library['claims'] if record['id'] == 'C-REVIEW')
    review['related'] = [{'claim': 'C-RELATED', 'relation': 'context_limitations'}]
    source = edit(
        sc99(), member('notes:', block('benchmark:', in_place('source', 'The benchmark.', 'C-REVIEW')))
    )
    # The dossier reads a scenario's citations, which the front end reads before any check.
    scenario_read, _ = resolve(front.read(source, 'SC99.scn'), thaw(library))
    result = dossier(library, {'SC99': scenario_read})
    reached = {
        record['id']: record['reachable_from_scenarios']
        for source in result['sources']
        for record in source['claims']
    }
    assert reached['C-REVIEW'] == reached['C-RELATED'] == ['SC99']


@pytest.mark.parametrize('field', ['model_hash', 'implementation_hash'])
def test_sweep_worker_refuses_either_stale_identity(monkeypatch, field):
    import tools.publish as publish

    model = compiled(scenario())
    monkeypatch.setattr(publish, '_model', lambda *args: model)
    expected = {'model_hash': model.model_hash, 'implementation_hash': model.implementation_hash}
    expected[field] = '0' * 64
    with pytest.raises(ValueError, match='another model or implementation'):
        runs._sweep_row(ROOT, 'SC99', (expected['model_hash'], expected['implementation_hash']))
