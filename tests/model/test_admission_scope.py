"""Named numerical admission keeps global language checks and cannot masquerade as full admission."""

from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from napkin.engine.study import evaluate_study
from napkin.model import ModelError, load_scenario
from napkin.model.language import front
from napkin.model.model import choice_errors, choice_key
from tests import build as f


def source(*, invalid_named=False, unused=True):
    text = f.scenario().replace('input end: h = 12 h in 1 h to 24 h', 'input end: h = 12 h in 1 h to 48 h')
    if unused:
        option = f.options(
            'Stop', f.option('Late', 'Outside the blocking check.', 'service.end = 30 h  @fixture')
        )
        text = text.replace('\nruns:\n', '\n' + option + '\n\nruns:\n')
    if invalid_named:
        text = text.replace('b = "Default" + "Half rate"', 'b = "Default" + "Late"')
    return text


def scoped(text, runs=('a',)):
    return front.compile_file(
        front.read(text, 'fixture.scn'), 'fixture.scn', f.library(), admission_runs=runs
    )


@pytest.mark.parametrize('invalid_named', [False, True])
def test_selected_run_can_pass_when_unused_numerical_admission_fails(tmp_path, invalid_named):
    text = source(invalid_named=invalid_named)
    path = tmp_path / 'fixture.scn'
    path.write_text(text)
    model = load_scenario(path, f.library(), admission_runs=['a'])
    assert model.admission_runs == ('a',)
    assert set(model.defaults) == {'a'}
    assert model.proven == {choice_key(model.runs['a']['starts'], model.run_values('a'))}
    assert model.resolve('a').run == 'a'
    assert evaluate_study(model, runs=['a']).admissible
    with pytest.raises(FrozenInstanceError):
        model.admission_runs = None
    with pytest.raises(ModelError):
        load_scenario(path, f.library())
    if invalid_named:
        with pytest.raises(ModelError):
            scoped(text, ('b',))


def test_full_default_is_unchanged_and_scoped_identity_is_authored_identity():
    text = source(unused=False)
    full = front.compile_file(front.read(text, 'fixture.scn'), 'fixture.scn', f.library())
    partial = scoped(text)
    assert full.admission_runs is None
    assert set(full.defaults) == {'a', 'b'}
    assert full.model_hash == partial.model_hash
    assert full.library_hash == partial.library_hash
    assert full.resolve('a') == partial.resolve('a')
    assert evaluate_study(full).admissible


def test_scope_is_validated_before_structures_are_built():
    with (
        patch('napkin.model.model.Builder', side_effect=AssertionError('built too early')),
        pytest.raises(ModelError, match='Unknown admission runs'),
    ):
        scoped(source(), ('absent',))


@pytest.mark.parametrize('selection', [[], 'a', [1]])
def test_empty_or_malformed_scope_rejected(selection):
    with pytest.raises(ModelError, match='nonempty collection'):
        scoped(source(), selection)


def test_resolve_and_study_cannot_escape_or_implicitly_expand_scope():
    model = scoped(source(unused=False))
    with pytest.raises(ModelError, match='outside'):
        model.resolve('b')
    for selection in (None, ['b'], ['a', 'b']):
        result = evaluate_study(model, runs=selection)
        assert not result.admissible and not result.runs
        assert {d['code'] for d in result.diagnostics} == {'admission_scope'}


@pytest.mark.parametrize(
    'broken',
    [
        lambda text: text.replace('rate if state is "on"', 'unknown if state is "on"'),
        lambda text: text.replace('service.end = 30 h', 'service.end = 30 people'),
        lambda text: text.replace('service.end = 30 h  @fixture', 'service.end = 30 h  @missing'),
    ],
)
def test_unselected_content_retains_structure_unit_and_evidence_checks(broken):
    with pytest.raises(ModelError):
        scoped(broken(source()))


def test_failed_resolution_never_enters_proven_keys():
    model = scoped(source())
    values = {**model.run_values('a'), 'service.end': 30}
    checked = set()
    errors = choice_errors(model, {('Late',): values}, checked)
    assert errors and not checked


def test_selected_whole_structure_uses_its_admitted_run():
    option = f.options('Start', f.option('Off', 'Starts off.', 'service.state = "off"  @fixture'))
    text = source(unused=False).replace('\nruns:\n', '\n' + option + '\n\nruns:\n')
    text = text.replace('b = "Default" + "Half rate"', 'b = "Default" + "Off"')
    model = scoped(text, ('b',))
    assert set(model.defaults) == {'b'}
    assert any(model.left_out[model.runs['b']['starts']].values())
    assert model.resolve('b').run == 'b'


def test_unused_start_profile_still_receives_structural_checks():
    option = f.options('Start', f.option('Off', 'Starts off.', 'service.state = "off"  @fixture'))
    text = source(unused=False).replace('\nruns:\n', '\n' + option + '\n\nruns:\n')
    from napkin.model.analysis import structure as checks

    checked = []
    original = checks.structure_facts

    def record(structure, library, units):
        checked.append(structure.modes['service.state'].initial)
        return original(structure, library, units)

    with patch.object(checks, 'structure_facts', side_effect=record):
        scoped(text)
    assert 'off' in checked


@pytest.mark.parametrize('invalid_named', [False, True])
def test_source_table_errors_remain_global_for_consistent_selected_studies(invalid_named):
    text = source(invalid_named=invalid_named).replace('service.end = 30 h', 'service.end = 60 h')
    with pytest.raises(ModelError, match='outside'):
        scoped(text)
