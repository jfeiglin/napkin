"""Study entrypoints cannot silently expand a compiler's admission scope."""

import pytest

from napkin.engine.study import evaluate_study, resolve_edits
from napkin.model.ir import ModelError
from tests.build import compiled, scenario


class Scoped:
    """Only admission metadata differs; normal resolution still uses the real model."""

    def __init__(self, model):
        self.model = model
        self.admission_runs = ('a',)

    def __getattr__(self, name):
        return getattr(self.model, name)


@pytest.fixture
def model():
    return compiled(scenario())


@pytest.mark.parametrize('selection', [None, ['b'], ['a', 'b']])
def test_scoped_study_requires_an_explicit_admitted_selection(model, selection):
    scoped = Scoped(model)
    with pytest.raises(ModelError) as rejected:
        resolve_edits(scoped, runs=selection)
    assert {item['code'] for item in rejected.value.diagnostics} == {'admission_scope'}
    study = evaluate_study(scoped, runs=selection)
    assert not study.admissible and not study.runs
    assert {item['code'] for item in study.diagnostics} == {'admission_scope'}


def test_scoped_study_still_reports_unknown_names_before_scope_checks(model):
    with pytest.raises(ModelError) as rejected:
        resolve_edits(Scoped(model), runs=['missing'])
    assert {item['code'] for item in rejected.value.diagnostics} == {'run'}


def test_explicit_admitted_selection_and_ordinary_full_resolution_still_work(model):
    assert set(resolve_edits(Scoped(model), runs=['a'])) == {'a'}
    assert set(resolve_edits(model)) == {'a', 'b'}
