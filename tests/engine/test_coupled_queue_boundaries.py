"""Flows with two legs that share a resource at empty or full stocks, under local sharing.

Each queue processes what arrives by a flow with legs: one leg moves the queue's work to `done`, the
other takes the shared resource from `available` to `used`, and both legs are served at one
fraction (spec, "Shared resources and competing invocations"). The rates are worked by hand from the
rules of local sharing (`engine/timeline/network.py`): a store at its lower bound passes on what
flows in, its claims are settled after the claims that supply it, and claims of one tier share by
equal served fractions (max-min). The arrivals and the replenishment are pipes that carry no more
than they ask (a capacity at the request): a request is soft, and an uncapped arrival would be
raised to serve the queue (D15). No expected value comes from a run of the engine.
"""

import numpy as np
import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    endpoint,
    flow,
    formula,
    input_,
    legs,
    priority,
    proportional,
    q,
    t,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key

UNITS = {'h': {'time': 1}, 'people': {'people': 1}}


def rate(number):
    return q(number, 'people/h')


def pipe(name, source, sink, number):
    """A flow that asks `number` people/h and carries no more."""
    return flow(name, source, sink, request=rate(number), capacity=rate(number))


def stock(name, start=0, upper=None, **settings):
    return value(name, 'people', start, lower=0, upper=upper, **settings)


def values(program, horizon, names, times):
    """The values of the stores `names` of the entity `s` at the times."""
    record = run(program, Configuration(Request(horizon)))
    assert record.failure is None, record.failure.detail('message')
    keys = [Key('s', (name,)) for name in names]
    return {key.steps[0]: reading.values for key, reading in zip(keys, read(record, program, keys, times))}


def queues(available, used, weight):
    """The model of two queues that process their arrivals with the shared resource: the resource
    gives out at most 2 people/h and is replenished at 1.5 people/h from what was used. The second
    queue's arrivals fall from 1 to 0.45 people/h at 5 h (a table keyed by the hour), and its resource
    leg asks 2 people/h times its weight."""
    b = Builder(UNITS)
    shift = b.template('Shift', input_('hour', 'h', 0), input_('arrivals', 'people/h', 0))
    b.table(
        'shifts',
        shift,
        [{'id': 'day', 'hour': 0, 'arrivals': 1}, {'id': 'night', 'hour': 5, 'arrivals': 0.45}],
    )
    arrivals = formula(shift.instances.by('hour').at(t).arrivals)
    parts = [
        stock('available', available, outflow=endpoint(capacity=rate(2))),
        stock('used', used),
        input_('weight', '', weight, lower=0.01, upper=1),
        pipe('replenish', this.used, this.available, 1.5),
    ]
    for name, arriving, asked in (('first', rate(1), rate(2)), ('second', arrivals, rate(2) * this.weight)):
        parts += [
            stock(f'{name}_pending'),
            stock(f'{name}_done'),
            flow(
                f'{name}_arrival',
                SOURCE,
                getattr(this, f'{name}_pending'),
                request=arriving,
                capacity=arriving,
            ),
            legs(
                f'{name}_process',
                flow(
                    'work', getattr(this, f'{name}_pending'), getattr(this, f'{name}_done'), request=rate(2)
                ),
                flow('take', this.available, this.used, request=asked),
            ),
        ]
    b.entity('s', *parts)
    return b.finish()


@pytest.mark.parametrize('weight', [0.25, 1])
def test_falling_arrivals_to_one_empty_queue_leave_both_queues_empty(weight):
    """The resource can meet both processes throughout, so each passes its arrivals on: its
    fraction is its arrivals over the 2 people/h that its work leg asks, and its queue stays empty.
    The integrals follow from the arrivals alone. At weight 1/4 the resource legs take 1.25 people/h,
    and `used`, empty, passes on just that (its replenishment is held to what flows in). At weight 1
    they take 2 people/h, so `used` rises at 1/2 people/h until 5 h, and then falls at 1/20 people/h
    as the second queue's leg takes 0.45."""
    times = [0, 4, 5, 5.5, 8, 10]
    program = queues(24, 0, weight)
    found = values(
        program,
        10,
        ['first_pending', 'second_pending', 'first_done', 'second_done', 'used', 'available'],
        times,
    )
    for k, time in enumerate(times):
        assert found['first_pending'][k] == pytest.approx(0, abs=1e-9)
        assert found['second_pending'][k] == pytest.approx(0, abs=1e-9)
        assert found['first_done'][k] == pytest.approx(time, abs=1e-9)
        assert found['second_done'][k] == pytest.approx(min(time, 5) + 0.45 * max(0, time - 5), abs=1e-9)
        used = 0 if weight == 0.25 else 0.5 * min(time, 5) - 0.05 * max(0, time - 5)
        assert found['used'][k] == pytest.approx(used, abs=1e-9)
        assert found['available'][k] == pytest.approx(24 - used, abs=1e-9)


def test_an_empty_shared_resource_shares_its_supply_and_gives_the_rest_once_a_queue_empties():
    """The resource is empty and gets 1.5 people/h: the two processes share it at equal fractions,
    3/8 each, so each work leg moves 0.75 and each queue gains 0.25 people/h. From 5 h the second queue
    gets 0.45 and drains at 0.3 people/h: it is empty at 5 + 1.25 / 0.3 h. Then its process passes on
    its 0.45 (a fraction of 0.225), which leaves 1.05 people/h of the resource to the first."""
    empty = 5 + 1.25 / 0.3
    times = [0, 4, 5, 8, empty, 9.5, 10]
    program = queues(0, 24, 1)
    found = values(
        program,
        10,
        ['first_pending', 'second_pending', 'first_done', 'second_done', 'used', 'available'],
        times,
    )
    for k, time in enumerate(times):
        first = 0.75 * min(time, empty) + 1.05 * max(0, time - empty)
        second = 0.75 * min(time, empty) + 0.45 * max(0, time - empty)
        assert found['first_done'][k] == pytest.approx(first, abs=1e-9)
        assert found['second_done'][k] == pytest.approx(second, abs=1e-9)
        assert found['first_pending'][k] == pytest.approx(time - first, abs=1e-9)
        arrivals = min(time, 5) + 0.45 * max(0, time - 5)
        assert found['second_pending'][k] == pytest.approx(arrivals - second, abs=1e-9)
        assert found['available'][k] == pytest.approx(0, abs=1e-9)
        assert found['used'][k] == pytest.approx(24, abs=1e-9)


def sharing(policy, boundary):
    """Half a unit of supply an hour into an empty resource, which two processes share; each asks
    2 people/h on each of its legs. The first can move only 0.2 people/h from or to its own store,
    the second 1 people/h: from empty stores fed at those rates (`lower`), or into full stores that
    drain at them (`upper`). The resource's outflow ranks the processes' resource legs by `policy`."""
    order = {'first': this.first.take, 'second': this.second.take}
    allocation = proportional() if policy == 'proportional' else priority(*(order[name] for name in policy))
    if boundary == 'lower':
        local = [
            stock('a'),
            stock('b'),
            stock('a_done'),
            stock('b_done'),
            pipe('a_supply', SOURCE, this.a, 0.2),
            pipe('b_supply', SOURCE, this.b, 1),
        ]
        ends = {'first': (this.a, this.a_done), 'second': (this.b, this.b_done)}
    else:
        local = [
            stock('a', 1, upper=1),
            stock('b', 1, upper=1),
            stock('a_stock', 100),
            stock('b_stock', 100),
            pipe('a_drain', this.a, SINK, 0.2),
            pipe('b_drain', this.b, SINK, 1),
        ]
        ends = {'first': (this.a_stock, this.a), 'second': (this.b_stock, this.b)}
    b = Builder(UNITS)
    b.entity(
        's',
        stock('resource', outflow=endpoint(capacity=rate(2), allocation=allocation)),
        stock('used'),
        pipe('supply', SOURCE, this.resource, 0.5),
        *local,
        *(
            legs(
                name,
                flow('work', *ends[name], request=rate(2)),
                flow('take', this.resource, this.used, request=rate(2)),
            )
            for name in ('first', 'second')
        ),
    )
    return b.finish()


@pytest.mark.parametrize('policy', ['proportional', ['first', 'second'], ['second', 'first']])
@pytest.mark.parametrize('boundary', ['lower', 'upper'])
def test_a_local_material_bound_leaves_the_unused_share_to_its_sibling(policy, boundary):
    """The first process can run at a fraction of 0.1 at most, the second at 0.5, and the resource
    gives 0.5 people/h, which is a fraction of 1/4 for each at once. In proportion, and with the
    first ranked first, the first takes 0.2 and the second the 0.3 left; with the second first, it
    takes all 0.5 and the first gets nothing."""
    first, second = (0, 0.5) if policy == ['second', 'first'] else (0.2, 0.3)
    times = [0, 0.25, 0.75, 1]
    names = ['resource', 'used', 'a', 'b'] + (
        ['a_done', 'b_done'] if boundary == 'lower' else ['a_stock', 'b_stock']
    )
    found = values(sharing(policy, boundary), 1, names, times)
    for k, time in enumerate(times):
        assert found['resource'][k] == pytest.approx(0, abs=1e-9)
        assert found['used'][k] == pytest.approx(0.5 * time, abs=1e-9)
        if boundary == 'lower':
            assert found['a'][k] == pytest.approx((0.2 - first) * time, abs=1e-9)
            assert found['b'][k] == pytest.approx((1 - second) * time, abs=1e-9)
            assert found['a_done'][k] == pytest.approx(first * time, abs=1e-9)
            assert found['b_done'][k] == pytest.approx(second * time, abs=1e-9)
        else:
            assert found['a'][k] == pytest.approx(1 + (first - 0.2) * time, abs=1e-9)
            assert found['b'][k] == pytest.approx(1 + (second - 1) * time, abs=1e-9)
            assert found['a_stock'][k] == pytest.approx(100 - first * time, abs=1e-9)
            assert found['b_stock'][k] == pytest.approx(100 - second * time, abs=1e-9)


@pytest.mark.parametrize('order', [('x', 'y'), ('y', 'x')])
def test_a_flow_with_legs_across_two_proportional_groups_has_no_priority_of_declaration(order):
    """x gets 0.6 and y 1 people/h; the flow with legs b takes the same amount from each. Every
    request is 1: x binds at a = b = 0.3, after which y serves c = 0.7. The order in which the two
    outflows are written gives b no priority."""
    b = Builder(UNITS)
    capped = {name: stock(name, outflow=endpoint(capacity=rate(2))) for name in ('x', 'y')}
    b.entity(
        's',
        *(capped[name] for name in order),
        *(stock(name) for name in ('a', 'b', 'c', 'b_y')),
        pipe('sx', SOURCE, this.x, 0.6),
        pipe('sy', SOURCE, this.y, 1),
        flow('a_flow', this.x, this.a, request=rate(1)),
        legs(
            'b_flow',
            flow('from_x', this.x, this.b, request=rate(1)),
            flow('from_y', this.y, this.b_y, request=rate(1)),
        ),
        flow('c_flow', this.y, this.c, request=rate(1)),
    )
    found = values(b.finish(), 1, ['x', 'y', 'a', 'b', 'b_y', 'c'], [1])
    for name, expected in [('x', 0), ('y', 0), ('a', 0.3), ('b', 0.3), ('b_y', 0.3), ('c', 0.7)]:
        assert found[name][0] == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize('order', [('x', 'y'), ('y', 'x')])
def test_separate_proportional_groups_serve_the_upstream_supply_first(order):
    """x gets 1 people/h and splits it into 0.5 for a and 0.5 down the flow with legs `feed`, which
    also moves 0.5 from the reserve to `used`. y then divides its 0.5 into 0.25 each for c and d,
    whatever the order of the outflows: its two recipients win no extra supply upstream."""
    b = Builder(UNITS)
    capped = {name: stock(name, outflow=endpoint(capacity=rate(2))) for name in ('x', 'y')}
    b.entity(
        's',
        *(capped[name] for name in order),
        *(stock(name) for name in ('a', 'c', 'd', 'used')),
        stock('reserve', 100),
        pipe('supply', SOURCE, this.x, 1),
        flow('a_flow', this.x, this.a, request=rate(1)),
        legs(
            'feed',
            flow('onward', this.x, this.y, request=rate(1)),
            flow('spend', this.reserve, this.used, request=rate(1)),
        ),
        flow('c_flow', this.y, this.c, request=rate(1)),
        flow('d_flow', this.y, this.d, request=rate(1)),
    )
    found = values(b.finish(), 1, ['x', 'y', 'a', 'c', 'd', 'used'], [1])
    for name, expected in [('x', 0), ('y', 0), ('a', 0.5), ('c', 0.25), ('d', 0.25), ('used', 0.5)]:
        assert found[name][0] == pytest.approx(expected, abs=1e-9)


def test_solver_noise_at_the_waterline_does_not_stop_a_proportional_allocation(monkeypatch):
    """A served fraction within HiGHS's feasibility tolerance of the waterline is that level.

    HiGHS may return a vertex slightly past a bound that it treats as satisfied. That noise must
    neither stop the run nor change the allocation beyond the tolerance: the same split as above,
    0.2 for the first process and 0.3 for the second."""
    from napkin.engine.continuous import highs

    original = highs.solve

    def noisy(objective, *args, **kwargs):
        found = original(objective, *args, **kwargs)
        # Only the programs whose objective is one unknown: a fair level, or a claim that may rise.
        if found.success and np.count_nonzero(objective) == 1:
            found.x = found.x + 0.1 * highs.FEASIBILITY
        return found

    program = sharing('proportional', 'lower')
    monkeypatch.setattr(highs, 'solve', noisy)
    found = values(program, 1, ['a_done', 'b_done'], [1])
    assert found['a_done'][0] == pytest.approx(0.2, abs=1e-6)
    assert found['b_done'][0] == pytest.approx(0.3, abs=1e-6)


def test_the_flows_with_legs_agree_with_the_oracle():
    """The models above, against the oracle's exact local sharing (`tests/reference/`), at the
    quarters of their runs."""
    from tests.reference.from_program import run_of, value_at

    for program, horizon, names in (
        (queues(24, 0, 1), 10, ['first_done', 'second_done', 'used', 'available']),
        (queues(0, 24, 1), 10, ['first_done', 'second_done', 'first_pending', 'second_pending']),
        (sharing(['second', 'first'], 'lower'), 1, ['a_done', 'b_done', 'used']),
        (sharing('proportional', 'upper'), 1, ['a', 'b', 'used']),
    ):
        configuration = Configuration(Request(horizon))
        oracle, failed = run_of(program, configuration)
        assert failed is None
        record = run(program, configuration)
        times = [horizon * k / 4 for k in range(5)]
        for name in names:
            key = Key('s', (name,))
            found = read(record, program, [key], times)[0].values
            expected = [float(value_at(oracle, program, key, time)) for time in times]
            assert found == pytest.approx(expected, rel=1e-9, abs=1e-9), name
