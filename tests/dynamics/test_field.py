"""The field of a run outside a simulation (napkin/dynamics/field.py).

The rates are the engine's own; the expected values come from the closed forms of the models in
`tests/dynamics/models.py`: a linear field has its matrix as its derivative, the mixed model's level
moves at supply + boost / 1 h - k x while its gate is open, and the pond, which the engine runs on the
sparse integrator, at r + k (top - x) - d x."""

from __future__ import annotations

import numpy as np
import pytest

from napkin.dynamics import STABLE, configured, equilibria, started, vector_field
from napkin.program.config import ConfigurationError
from tests.dynamics.models import CENTRE, fold_in_time, linear, mixed, pond, scheduled

A = ((-1.0, -2.0), (2.0, -1.0))
K, SUPPLY = 0.5, 4.0  # the drain rate (1/h) and the supply (people/h) of the mixed model


def test_a_linear_field_has_its_matrix_as_its_derivative():
    field = vector_field(*linear(A))
    assert field.names == ('tank.x', 'tank.w')
    x = np.array([CENTRE + 0.3, CENTRE - 0.7])
    assert field(x) == pytest.approx(np.array(A) @ (x - CENTRE), abs=1e-12)
    assert field.jacobian(x) == pytest.approx(np.array(A), abs=1e-6)


def test_the_field_sorts_stores_into_active_passive_and_held():
    field = vector_field(*mixed())
    assert field.names == ('tank.x',)  # the drain reads it
    assert field.passive == ('tank.drained',)  # a tally that nothing reads
    assert field.held == ('tank.gate', 'tank.boost')  # stored values that no flow meets
    # The rate at x: supply + boost / 1 h - k x, with boost = 2 people.
    for x in (5.0, 12.0, 20.0):
        assert field(np.array([x]))[0] == pytest.approx(SUPPLY + 2 - K * x, abs=1e-12)


def test_the_field_reads_held_values_and_inputs_at_their_start():
    program, configuration = mixed()
    shut = vector_field(started(program, {'tank.gate': 'SHUT'}), configuration)
    # With the gate shut the drain stops: the level only fills.
    assert shut(np.array([12.0]))[0] == pytest.approx(SUPPLY + 2, abs=1e-12)
    raised = vector_field(started(program, {'tank.boost': 6}), configuration)
    assert raised(np.array([12.0]))[0] == pytest.approx(SUPPLY + 6 - K * 12, abs=1e-12)
    faster = vector_field(program, configuration, {'tank.k': 0.25})
    assert faster(np.array([12.0]))[0] == pytest.approx(SUPPLY + 2 - 0.25 * 12, abs=1e-12)


def test_a_path_that_is_no_value_of_its_kind_is_refused():
    program, configuration = mixed()
    with pytest.raises(KeyError):
        started(program, {'tank.nothing': 1.0})
    with pytest.raises(KeyError):
        started(program, {'tank.k': 1.0})  # an input: a configuration sets it
    with pytest.raises(KeyError):
        configured(program, configuration, {'tank.x': 1.0})  # a stored value: no input
    with pytest.raises(ValueError):
        started(program, {'tank.gate': 'AJAR'})  # no member of the enum
    with pytest.raises(ConfigurationError):
        vector_field(program, configuration, {'tank.k': 2.0})  # outside the input's range


def test_the_field_reads_a_driver_of_the_time_where_it_is_read():
    # mu = mu0 + slope t / 1 h: at x = c + 1, x' = mu - 1.
    field = vector_field(*fold_in_time(-2.0, 0.5))
    for at in (0.0, 4.0, 7.5):
        assert field(np.array([CENTRE + 1]), at)[0] == pytest.approx(-2.0 + 0.5 * at - 1.0, abs=1e-12)


def test_a_keyed_read_by_the_time_selects_its_member_where_the_field_is_read():
    # x' = schedule(t) - x / 2, with the readings 2 people/h from 0 h and 6 people/h from 4 h.
    field = vector_field(*scheduled())
    for at, inflow in ((1.0, 2.0), (5.0, 6.0), (3.5, 2.0), (4.0, 6.0)):
        assert field(np.array([4.0]), at)[0] == pytest.approx(inflow - 0.5 * 4.0, abs=1e-12)
    (early,) = equilibria(field, t=1.0, starts=2, seed=0)
    (late,) = equilibria(field, t=6.0, starts=2, seed=0)
    assert (early.value('tank.x'), late.value('tank.x')) == pytest.approx((4.0, 12.0), abs=1e-9)


def test_a_set_on_the_sparse_integrator_gives_its_field():
    # Two inflows meet the pond on one side: the engine runs it on the sparse integrator.
    rain, k, top, d = 2.0, 0.5, 20.0, 0.25
    field = vector_field(*pond())
    assert field.names == ('pond.x',)
    for x in (0.0, 4.0, 12.0, 19.5):
        assert field(np.array([x]))[0] == pytest.approx(rain + k * (top - x) - d * x, abs=1e-12)
    (rest,) = equilibria(field, starts=4, seed=1)
    assert rest.value('pond.x') == pytest.approx((rain + k * top) / (k + d), abs=1e-9)
    assert rest.eigenvalues[0].real == pytest.approx(-(k + d), rel=1e-6)
    assert rest.stability == STABLE
