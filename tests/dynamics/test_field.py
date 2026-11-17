"""The field of a run outside a simulation (napkin/dynamics/field.py).

The rates are the engine's own; the expected derivatives come from the closed forms of the models
in `tests/dynamics/models.py`: a linear field has its matrix as its derivative, and the mixed model's
stock decays to (supply + boost / 1 h) / k."""

from __future__ import annotations

import numpy as np
import pytest

from napkin.dynamics import vector_field
from tests.build import compiled
from tests.dynamics.models import CENTRE, linear, mixed

A = ((-1.0, -2.0), (2.0, -1.0))


def test_a_linear_field_has_its_matrix_as_its_derivative():
    field = vector_field(compiled(linear(A)), 'a')
    assert field.names == ('s.x', 's.w')
    x = np.array([CENTRE + 0.3, CENTRE - 0.7])
    expected = np.array(A) @ (x - CENTRE)
    assert field(x) == pytest.approx(expected, abs=1e-12)
    assert field.jacobian(x) == pytest.approx(np.array(A), abs=1e-6)


def test_the_field_sorts_quantities_into_active_passive_and_frozen():
    field = vector_field(compiled(mixed()), 'a')
    assert field.names == ('s.x',)  # the drain reads it
    assert field.passive == ('s.drained',)  # a tally that nothing reads
    assert field.discrete == ('s.boost',)  # a number state that only rules could set
    inputs = compiled(mixed()).inputs
    k = inputs['s.k']['value']
    supply = inputs['s.supply']['value']
    # Rate at x: supply + boost / 1 h - k x, with boost = 2 people.
    for x in (5.0, 12.0, 20.0):
        assert field(np.array([x]))[0] == pytest.approx(supply + 2 - k * x, abs=1e-12)


def test_the_field_reads_the_frozen_store_and_state():
    model = compiled(mixed())
    shut = vector_field(model, 'a', store={'s.gate': 'shut', 's.gate__entered': 0.0})
    supply = model.inputs['s.supply']['value']
    # With the gate shut the drain stops: the stock only fills.
    assert shut(np.array([12.0]))[0] == pytest.approx(supply + 2, abs=1e-12)
    raised = vector_field(model, 'a', state={'s.boost': 6.0})
    assert raised(np.array([12.0]))[0] == pytest.approx(
        supply + 6 - model.inputs['s.k']['value'] * 12, abs=1e-12
    )


def test_a_state_that_is_not_a_quantity_is_rejected():
    with pytest.raises(KeyError):
        vector_field(compiled(mixed()), 'a', state={'s.nothing': 1.0})
