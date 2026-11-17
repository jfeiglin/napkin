"""A local queue limit does not ration its sibling's independent material supply."""

import numpy as np
import pytest

from napkin.engine.runtime import simulate
from tests.build import compiled, flow, run, share, stock, system

MODEL = """scenario "Independent queues using a shared resource"
    horizon 10 h
    scope "Synthetic queue and resource accounting."
clock: @fixture
    var available: "up" | "down" = "up" @fixture
    event start when t >= 0 h: @fixture
        "Start."
    event change once when t >= 5 h: @fixture
        available = "down"
resource: @fixture
    var available: people = 24 people size 168 people @fixture
    var used: people = 0 people size 168 people @fixture
    flow replenish: used -> available at 1.5 people/h @fixture
    share available limit 2 people/h @fixture
first: @fixture
    var pending: people = 0 people size 1000 people @fixture
    var done: people = 0 people size 1000 people @fixture
    flow request: -> pending at 1 people/h @fixture
    flow process at 2 people/h: @fixture
        pending -> done
        resource.available -> resource.used
second: @fixture
    input weight: fraction = 0.25 in 0.01 to 1 @fixture
    var pending: people = 0 people size 1000 people @fixture
    var done: people = 0 people size 1000 people @fixture
    flow request: -> pending at 1 people/h if clock.available is "up" else 0.45 people/h @fixture
    flow process at 2 people/h: @fixture
        pending -> done
        resource.available -> resource.used at 2 people/h * weight
options "Choice":
    "Default":
        "Default."
runs:
    a = "Default"
record fixture: identity "Synthetic queue and resource accounting."
"""


@pytest.mark.parametrize('weight', [0.25, 1])
def test_falling_arrivals_to_one_empty_queue_leave_both_queues_empty(weight):
    """Capacity exceeds every incoming request, so both queues continuously pass it through.

    The shared resource can meet both flows throughout. The second queue's smaller inflow
    therefore cannot reduce the first flow. The exact integrals come from the two external
    arrival rates, not from a second evaluation of the allocation implementation.
    """
    model = compiled(MODEL)
    trajectory = simulate(model.resolve('a', {'second.weight': weight}), model.library)
    for time in (0, 4, 5, 5.5, 8, 10):
        state = trajectory.env_at(time)
        first = time
        second = min(time, 5) + 0.45 * max(0, time - 5)
        assert state['first.pending'] == pytest.approx(0, abs=1e-7)
        assert state['second.pending'] == pytest.approx(0, abs=1e-7)
        assert state['first.done'] == pytest.approx(first, abs=1e-7)
        assert state['second.done'] == pytest.approx(second, abs=1e-7)
        # At weight 1/4 replenishment can match consumption from the start. At weight 1,
        # the resource falls at 1/2 per hour until t=5, then refills at 1/20 per hour.
        used = 0 if weight == 0.25 else 0.5 * min(time, 5) - 0.05 * max(0, time - 5)
        assert state['resource.used'] == pytest.approx(used, abs=1e-7)
        assert state['resource.available'] == pytest.approx(24 - used, abs=1e-7)


def test_empty_shared_resource_redistributes_supply_after_one_queue_empties():
    source = MODEL.replace('available: people = 24 people', 'available: people = 0 people').replace(
        'used: people = 0 people', 'used: people = 24 people'
    )
    model = compiled(source)
    trajectory = simulate(model.resolve('a', {'second.weight': 1}), model.library)
    # Both queues initially receive 1/h and share 1.5/h, accumulating .25/h.
    # After t=5 the second drains at .75-.45=.3/h, emptying at 5+1.25/.3.
    # Its .45/h pass-through then leaves 1.05/h for the first queue.
    empty = 5 + 1.25 / 0.3
    for time in (0, 4, 5, 8, empty, 9.5, 10):
        state = trajectory.env_at(time)
        first = 0.75 * min(time, empty) + 1.05 * max(0, time - empty)
        second = 0.75 * min(time, empty) + 0.45 * max(0, time - empty)
        assert state['first.done'] == pytest.approx(first, abs=1e-7)
        assert state['second.done'] == pytest.approx(second, abs=1e-7)
        assert state['first.pending'] == pytest.approx(time - first, abs=1e-7)
        arrivals = min(time, 5) + 0.45 * max(0, time - 5)
        assert state['second.pending'] == pytest.approx(arrivals - second, abs=1e-7)
        assert state['resource.available'] == pytest.approx(0, abs=1e-7)
        assert state['resource.used'] == pytest.approx(24, abs=1e-7)


@pytest.mark.parametrize('policy', ['proportional', ['first', 'second'], ['second', 'first']])
@pytest.mark.parametrize('boundary', ['lower', 'upper'])
def test_local_material_bound_leaves_unused_share_to_its_sibling(policy, boundary):
    # Half a unit of shared supply per hour supports two transactions that each
    # request 2/h. The first transaction can take only .2/h from/to its local
    # stock; the second can take 1/h. Proportional allocation and first priority
    # therefore deliver .2+.3; second priority delivers 0+.5.
    local = (
        [
            stock('a'),
            stock('b'),
            stock('a_done'),
            stock('b_done'),
            flow('a_supply', '-> a', '0.2 people/h'),
            flow('b_supply', '-> b', '1 people/h'),
            flow('first', ['a -> a_done', 'resource -> used'], '2 people/h'),
            flow('second', ['b -> b_done', 'resource -> used'], '2 people/h'),
        ]
        if boundary == 'lower'
        else [
            stock('a', 1, maximum=1),
            stock('b', 1, maximum=1),
            stock('a_stock', 100),
            stock('b_stock', 100),
            flow('a_drain', 'a ->', '0.2 people/h'),
            flow('b_drain', 'b ->', '1 people/h'),
            flow('first', ['a_stock -> a', 'resource -> used'], '2 people/h'),
            flow('second', ['b_stock -> b', 'resource -> used'], '2 people/h'),
        ]
    )
    source = system(
        stock('resource'),
        stock('used'),
        flow('supply', '-> resource', '0.5 people/h'),
        *local,
        share('resource', '2 people/h', policy),
        horizon=1,
    )
    trajectory = run(source)[1]
    first_rate, second_rate = (0, 0.5) if policy == ['second', 'first'] else (0.2, 0.3)
    for time in (0, 0.25, 0.75, 1):
        state = trajectory.env_at(time)
        assert state['s.resource'] == pytest.approx(0, abs=1e-8)
        assert state['s.used'] == pytest.approx(0.5 * time, abs=1e-8)
        if boundary == 'lower':
            assert state['s.a'] == pytest.approx((0.2 - first_rate) * time, abs=1e-8)
            assert state['s.b'] == pytest.approx((1 - second_rate) * time, abs=1e-8)
            assert state['s.a_done'] == pytest.approx(first_rate * time, abs=1e-8)
            assert state['s.b_done'] == pytest.approx(second_rate * time, abs=1e-8)
        else:
            assert state['s.a'] == pytest.approx(1 + (first_rate - 0.2) * time, abs=1e-8)
            assert state['s.b'] == pytest.approx(1 + (second_rate - 1) * time, abs=1e-8)
            assert state['s.a_stock'] == pytest.approx(100 - first_rate * time, abs=1e-8)
            assert state['s.b_stock'] == pytest.approx(100 - second_rate * time, abs=1e-8)


@pytest.mark.parametrize('order', [('x', 'y'), ('y', 'x')])
def test_transaction_spanning_proportional_groups_has_no_declaration_priority(order):
    # x supplies .6 and y supplies 1. The shared transaction b must take the
    # same amount from each. All requests are 1: x saturates at a=b=.3, after
    # which y can serve c=.7. Naming y's group first cannot give b priority.
    source = system(
        *(stock(name) for name in ('x', 'y', 'a', 'b', 'c', 'b_y')),
        flow('sx', '-> x', '0.6 people/h'),
        flow('sy', '-> y', '1 people/h'),
        flow('a_flow', 'x -> a', '1 people/h'),
        flow('b_flow', ['x -> b', 'y -> b_y'], '1 people/h'),
        flow('c_flow', 'y -> c', '1 people/h'),
        *(share(name, '2 people/h') for name in order),
        horizon=1,
    )
    state = run(source)[1].env_at(1)
    for name, expected in [('x', 0), ('y', 0), ('a', 0.3), ('b', 0.3), ('b_y', 0.3), ('c', 0.7)]:
        assert state[f's.{name}'] == pytest.approx(expected, abs=1e-8)


@pytest.mark.parametrize('order', [('x', 'y'), ('y', 'x')])
def test_separate_proportional_groups_serve_upstream_supply_first(order):
    # The upstream group splits 1/h into .5/h for a and .5/h feeding y.
    # y then divides that supply into .25/h each, regardless of declaration
    # order; two downstream recipients do not win extra upstream supply.
    source = system(
        *(stock(name) for name in ('x', 'y', 'a', 'c', 'd', 'used')),
        stock('reserve', 100),
        flow('supply', '-> x', '1 people/h'),
        flow('a_flow', 'x -> a', '1 people/h'),
        flow('feed', ['x -> y', 'reserve -> used'], '1 people/h'),
        flow('c_flow', 'y -> c', '1 people/h'),
        flow('d_flow', 'y -> d', '1 people/h'),
        *(share(name, '2 people/h') for name in order),
        horizon=1,
    )
    state = run(source)[1].env_at(1)
    for name, expected in [('x', 0), ('y', 0), ('a', 0.5), ('c', 0.25), ('d', 0.25), ('used', 0.5)]:
        assert state[f's.{name}'] == pytest.approx(expected, abs=1e-8)


def test_solver_noise_at_the_waterline_does_not_stop_a_proportional_allocation(monkeypatch):
    """A served fraction within the solver's feasibility tolerance of the waterline is saturated.

    HiGHS may return a vertex slightly past a bound it treats as satisfied. That noise must neither
    stop the run ("no limiting member") nor change the allocation beyond the tolerance.
    """
    from napkin.engine.continuous import highs

    original = highs.solve

    def noisy(objective, *args, **kwargs):
        found = original(objective, *args, **kwargs)
        # Only the probes that ask whether one member can still rise: one variable in the objective.
        if found.success and np.count_nonzero(objective) == 1:
            found.x = found.x + 0.1 * highs.FEASIBILITY
        return found

    source = system(
        stock('resource'),
        stock('used'),
        flow('supply', '-> resource', '0.5 people/h'),
        stock('a'),
        stock('b'),
        stock('a_done'),
        stock('b_done'),
        flow('a_supply', '-> a', '0.2 people/h'),
        flow('b_supply', '-> b', '1 people/h'),
        flow('first', ['a -> a_done', 'resource -> used'], '2 people/h'),
        flow('second', ['b -> b_done', 'resource -> used'], '2 people/h'),
        share('resource', '2 people/h', 'proportional'),
        horizon=1,
    )
    monkeypatch.setattr(highs, 'solve', noisy)
    state = run(source)[1].env_at(1)
    # The same independent split as above: .2 for the first, .3 for the second.
    assert state['s.a_done'] == pytest.approx(0.2, abs=1e-6)
    assert state['s.b_done'] == pytest.approx(0.3, abs=1e-6)
