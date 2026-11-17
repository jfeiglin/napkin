"""Authored sensitivity domains and the admission of binary controls."""

import pytest

from napkin.engine import edits_for, resolve_edits
from napkin.model import ModelError
from napkin.model import structure as typed
from tests.helpers import SCENARIO_IDS, catalogue_model


def declared_parameters(model):
    """(name, definition) of every input and fixed value in every structure of a model."""
    for structure in model.structures.values():
        yield from structure.parameters.items()


def notes_of(parameter):
    """The free notes of an input as plain data, empty for an input that has none."""
    return typed.thawed(parameter.metadata) or {}


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_every_structured_rationale_boundary_matches_its_executable_domain(scenario_id):
    for name, parameter in declared_parameters(catalogue_model(scenario_id)):
        rationale = notes_of(parameter).get('range_rationale', {})
        limits = {'min': parameter.adjust.minimum, 'max': parameter.adjust.maximum}
        for edge in ('min', 'max'):
            if isinstance(rationale.get(edge), dict) and 'value' in rationale[edge]:
                assert rationale[edge]['value'] == limits[edge], (name, edge)


@pytest.mark.deep
@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
def test_binary_controls_have_binary_range_and_compiler_admission(scenario_id):
    model = catalogue_model(scenario_id)
    blocking = {
        cid
        for s in model.structures.values()
        for cid, check in s.input_checks.items()
        if check.severity == 'block'
    }
    for name, parameter in dict(declared_parameters(model)).items():
        if notes_of(parameter).get('control') != 'binary':
            continue
        info = model.inputs[name]
        assert info['type'] == 'bool', name
        # An edit names a copy's input as the file does (`set.k.field`).
        written = f'{model.entities.get(info["entity"], info["entity"])}.{info["field"]}'

        def admission(value):
            # The edit reaches every run: one transaction over every run, which simulates nothing.
            # Its diagnostics, empty when it is admitted.
            try:
                resolve_edits(model, edits_for(model, {'set': {written: value}}))
            except ModelError as exc:
                return exc.diagnostics
            return []

        if info['fixed']:
            # A fixed bool is locked at 0 or 1, and an edit of either value is refused.
            assert parameter.adjust.mode == 'locked' and parameter.value in (0, 1), name
            for value in (False, True):
                diagnostics = admission(value)
                assert any(
                    d['code'] == 'locked' and d['path'].endswith('/' + written) for d in diagnostics
                ), (name, value, diagnostics)
            continue
        assert parameter.adjust.minimum == 0 and parameter.adjust.maximum == 1
        # A fraction is rejected before any run: a bool input takes true or false.
        diagnostics = admission(0.5)
        assert any(d['code'] == 'bool' and d['path'].endswith('/' + written) for d in diagnostics), (
            name,
            diagnostics,
        )
        # Either value is admitted. It can still break a scenario's blocking check,
        # which is reported under that check's identity.
        for value in (False, True):
            for d in admission(value):
                assert d['code'].removeprefix('check:') in blocking, (name, value, d)
