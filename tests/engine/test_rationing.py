"""The rationing of the flows of allocation groups (`engine/allocation.Allocation.ration`).

The definition is checked with exact fractions. A group whose flows ask no more than its capacity
changes nothing. A priority group serves its flows in their order: each takes the least of its rate
and of what is left. A proportional group gives each flow the same fraction of what it asked, but
no flow more than its own rate (a bound can hold a flow below what it asked): that is one fraction
f with the sum of min(rate, asked * f) equal to the capacity. A coupled transaction then moves by
the least fraction of its flows.
"""

import random
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from napkin.engine.allocation import Allocation
from napkin.engine.errors import SimulationError

# The doubles of a rationed rate against the exact value: a few sums and one quotient.
CLOSE = 1e-12


def system(groups, count, coupled=()):
    """What the rationing reads of a system: `groups` is [(policy, the flows in their order)]."""
    named = {
        f'g{k}': SimpleNamespace(policy=policy, order=[f'f{j}' for j in flows])
        for k, (policy, flows) in enumerate(groups)
    }
    return SimpleNamespace(
        groups=named,
        group_indices={f'g{k}': sorted(flows) for k, (_, flows) in enumerate(groups)},
        flow_index={f'f{j}': j for j in range(count)},
        coupling_members=[list(members) for members in coupled],
    )


def exact_proportional(members, rates, asked, capacity):
    """The exact rates of the flows of a proportional group that binds: the fraction f with the sum
    of min(rate, asked * f) equal to the capacity, found by trying each flow as the last one that
    its own rate holds."""
    flows = [j for j in members if asked[j] > 0]
    # A flow is held by its own rate when rate <= asked * f: those with the least rate / asked first.
    ordered = sorted(flows, key=lambda j: rates[j] / asked[j])
    for held in range(len(ordered) + 1):
        kept, free = ordered[:held], ordered[held:]
        if not free:
            break
        f = (capacity - sum(rates[j] for j in kept)) / sum(asked[j] for j in free)
        if all(rates[j] <= asked[j] * f for j in kept) and all(rates[j] > asked[j] * f for j in free):
            return {**{j: rates[j] for j in kept}, **{j: asked[j] * f for j in free}}
    raise AssertionError('no fraction')


@pytest.mark.parametrize('seed', range(8))
def test_a_group_gives_its_capacity_by_its_policy(seed):
    rng = random.Random(20261117 + seed)
    binding = {'proportional': 0, 'priority': 0, 'free': 0, 'held': 0}
    for _ in range(300):
        count = rng.randrange(2, 9)
        flows = list(range(count))
        rng.shuffle(flows)
        cut = rng.randrange(1, count)
        groups = [(rng.choice(('proportional', 'priority')), flows[:cut])]
        if rng.random() < 0.5 and count - cut >= 1:
            groups.append((rng.choice(('proportional', 'priority')), flows[cut:]))
        asked = [Fraction(rng.choice((0, 1, 2, 3, 5, 8)), rng.choice((1, 2, 4))) for _ in range(count)]
        # A bound can hold a flow below what it asked.
        rates = [a * Fraction(rng.choice((4, 4, 4, 1, 2, 0)), 4) for a in asked]
        capacities = []
        for _, members in groups:
            total = sum(rates[j] for j in members)
            capacities.append(total * Fraction(rng.choice((1, 2, 3, 5, 8)), 4))
        got, rationing = Allocation(system(groups, count)).ration(
            np.array([float(x) for x in rates]),
            np.array([float(x) for x in asked]),
            [float(x) for x in capacities],
        )
        want, limited = list(rates), []
        for (policy, members), capacity in zip(groups, capacities):
            if sum(rates[j] for j in members) <= capacity:
                binding['free'] += 1
                continue
            limited += sorted(members)
            binding[policy] += 1
            if policy == 'priority':
                remaining = capacity
                for j in members:
                    want[j] = min(rates[j], remaining)
                    remaining -= want[j]
            else:
                for j, value in exact_proportional(members, rates, asked, capacity).items():
                    binding['held'] += value == rates[j] and rates[j] < asked[j]
                    want[j] = value
        assert rationing == limited
        for j in range(count):
            if j in limited:
                assert got[j] == pytest.approx(float(want[j]), rel=CLOSE, abs=CLOSE), (groups, asked, rates)
            else:
                # A flow of no group that binds keeps its rate, bit for bit.
                assert got[j] == float(rates[j])
    assert min(binding.values()) > 20, binding


def test_a_coupled_transaction_moves_by_the_least_fraction_of_its_flows():
    """Flows 0 and 1 are one transaction. A priority group gives flow 0 half of what it asked, so
    flow 1 moves by half too; flow 2 is outside the transaction and keeps its rate."""
    plan = system([('priority', [0])], 3, coupled=[(0, 1)])
    got, rationing = Allocation(plan).ration(np.array([4.0, 6.0, 5.0]), np.array([4.0, 6.0, 5.0]), [2.0])
    assert got.tolist() == [2.0, 3.0, 5.0] and rationing == [0]
    # A transaction that asks nothing moves nothing, and one that asks for a part of its flows only
    # is an error of the run.
    got, _ = Allocation(plan).ration(np.array([0.0, 0.0, 5.0]), np.array([0.0, 0.0, 5.0]), [2.0])
    assert got.tolist() == [0.0, 0.0, 5.0]
    with pytest.raises(SimulationError, match='every material flow together'):
        Allocation(plan).ration(np.array([4.0, 0.0, 5.0]), np.array([4.0, 0.0, 5.0]), [9.0])


def by_definition(groups, coupled, rates, asked, capacities):
    """The rationing as its definition states it, with the arithmetic of the doubles in the order
    of the flows: each group that binds by its policy, then every coupled transaction that asks,
    each by the least fraction of its flows. Nothing is left out for a transaction whose flows
    kept their rates."""
    rates, asked = list(rates), list(asked)
    for (policy, flows), capacity in zip(groups, capacities):
        total = 0
        for j in sorted(flows):
            total += rates[j]
        if total <= capacity:
            continue
        assert policy == 'priority'
        left = capacity
        for j in flows:
            rates[j] = min(rates[j], left)
            left -= rates[j]
    for members in coupled:
        if any(asked[j] > 0 for j in members):
            fraction = min(rates[j] / asked[j] for j in members)
            for j in members:
                rates[j] = asked[j] * fraction
    return rates


@pytest.mark.parametrize('seed', range(12))
def test_each_coupled_transaction_has_the_rates_of_the_definition_bit_for_bit(seed):
    """Ten flows, two priority groups and three coupled transactions. A transaction can have a flow
    that a group cuts, a flow that a bound holds below what it asked, both, or neither. The result
    is that of the definition, which works every transaction out, in each bit. The cases have
    transactions of each kind: some change their rates, and some keep them."""
    rng = random.Random(seed)
    groups = [('priority', [0, 1, 2]), ('priority', [5, 3])]
    coupled = [(0, 6), (3, 7, 8), (4, 9)]
    plan = Allocation(system(groups, 10, coupled=coupled))
    kinds = set()
    for _ in range(40):
        asked = [rng.choice([0.5, 1.25, 3.0, 7.75]) * rng.random() + 0.1 for _ in range(10)]
        for members in coupled:
            if rng.random() < 0.15:
                for j in members:
                    asked[j] = 0.0  # this transaction asks nothing
        rates = list(asked)
        for j in rng.sample(range(10), rng.choice([0, 0, 1, 2])):
            rates[j] = asked[j] * rng.random()  # a bound holds this flow
        capacities = [rng.choice([0.2, 2.0, 50.0]), rng.choice([0.3, 50.0])]
        got, _ = plan.ration(np.array(rates), np.array(asked), capacities)
        expected = by_definition(groups, coupled, rates, asked, capacities)
        assert got.tolist() == expected
        for members in coupled:
            kinds.add(all(expected[j] == asked[j] for j in members))
    assert kinds == {True, False}


def test_a_transaction_that_asks_for_a_part_of_its_flows_is_an_error_each_time():
    """Whether a transaction asks for every flow together is kept for each pattern of the signs of
    the requests. A pattern that is an error stays one, also after a pattern that is none and with
    other numbers."""
    plan = Allocation(system([('priority', [0])], 3, coupled=[(0, 1)]))
    whole, part = np.array([4.0, 6.0, 5.0]), np.array([4.0, 0.0, 5.0])
    for requests in (whole, part, 2 * whole, 3 * part, part, whole):
        if requests[1] == 0:
            with pytest.raises(SimulationError, match='every material flow together'):
                plan.ration(requests.copy(), requests.copy(), [9.0])
        else:
            got, _ = plan.ration(requests.copy(), requests.copy(), [9.0])
            assert got.tolist() == requests.tolist()
