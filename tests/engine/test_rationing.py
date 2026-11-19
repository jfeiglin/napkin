"""Sharing at an endpoint under the rules of local sharing (`engine/timeline/network.py`), and the
coupled transactions of the continuous engine (`engine/allocation.Allocation.ration`), where a flow
that asks nothing moves nothing and does not bound the fraction of the others (S3).

An endpoint with a capacity shares it among its flows by its allocation: `proportional()` gives equal
served fractions within the flows' own capacities (water-filling, the exact max-min of one sum row
with bounds), and `priority(...)` serves its classes in order, a class of equal ranks sharing as a
proportional group, the unlisted flows sharing the rest. A flow in two binding groups is shared by
max-min over both, never one group after another (R-A3-09). A store at its lower bound shares what
flows in by its outflow's allocation; a request is soft, so a flow with no capacity is raised to
serve a claim downstream, and an aggregate request of an endpoint is carried by its first class
first. The expected values are worked by hand or with exact fractions.
"""

import math
import random
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from napkin.engine.allocation import Allocation
from napkin.engine.timeline.network import IN, OUT, Asked, Instant, Network, water

INF = math.inf


def exact_water(requests, capacities, available):
    """Water-filling in fractions: the fraction f with the sum of min(request * f, capacity) equal
    to `available`, found by trying each flow as the last one that its capacity holds."""
    if sum(min(r, c) for r, c in zip(requests, capacities)) <= available:
        return [min(r, c) for r, c in zip(requests, capacities)]
    ordered = sorted(range(len(requests)), key=lambda j: capacities[j] / requests[j])
    for held in range(len(ordered)):
        kept, free = ordered[:held], ordered[held:]
        f = (available - sum(capacities[j] for j in kept)) / sum(requests[j] for j in free)
        if all(capacities[j] <= requests[j] * f for j in kept) and all(
            capacities[j] > requests[j] * f for j in free
        ):
            found = {**{j: capacities[j] for j in kept}, **{j: requests[j] * f for j in free}}
            return [found[j] for j in range(len(requests))]
    raise AssertionError('no fraction')


@pytest.mark.parametrize('seed', range(8))
def test_water_filling_gives_equal_fractions_within_the_capacities(seed):
    rng = random.Random(20261119 + seed)
    for _ in range(200):
        count = rng.randint(1, 6)
        requests = [Fraction(rng.randint(1, 40), 4) for _ in range(count)]
        capacities = [
            Fraction(rng.randint(0, 40), 4) if rng.random() < 0.5 else Fraction(10**6) for _ in range(count)
        ]
        available = Fraction(rng.randint(0, 60), 4)
        got = water(np.array(requests, dtype=float), np.array(capacities, dtype=float), float(available))
        expected = exact_water(requests, capacities, available)
        assert got.tolist() == pytest.approx([float(x) for x in expected], rel=1e-12, abs=1e-12)


def shared(flows, stores, asked, ends=None, classes=None, lower=(), upper=()):
    """The rates of a small network: `flows` as (source, sink) store numbers (-1 outside), each
    flow's (request, capacity), the endpoints' {(side, store): (request, capacity)}, the priority
    classes {(side, store): classes}, and the stores at their lower and upper bounds."""
    count = len(stores)
    network = Network(
        [f'f{k}' for k in range(len(flows))],
        stores,
        [a for a, _ in flows],
        [b for _, b in flows],
        classes or {},
        np.zeros(len(flows)),
        np.zeros(count),
    )
    end_request, end_capacity = np.zeros((2, count)), np.full((2, count), INF)
    for (side, store), (request, capacity) in (ends or {}).items():
        end_request[side, store], end_capacity[side, store] = request, capacity
    request = np.array([r for r, _ in asked], dtype=float)
    capacity = np.array([INF if c is None else c for _, c in asked], dtype=float)
    flags = [np.isin(np.arange(count), list(chosen)) for chosen in (lower, upper)]
    return Instant(network, Asked(request, capacity, end_request, end_capacity), *flags).rates().tolist()


def test_a_capacity_is_shared_in_proportion_or_by_priority():
    """Spec, "Local allocation": a reservoir limited to 10 L/h and requests of 8 and 12 L/h give
    4 and 6 by default, 8 and 2 with priority."""
    flows, asked, ends = [(0, -1), (0, -1)], [(8, None), (12, None)], {(OUT, 0): (0, 10)}
    assert shared(flows, ['tank'], asked, ends) == [4, 6]
    assert shared(flows, ['tank'], asked, ends, {(OUT, 0): ((0,), (1,))}) == [8, 2]


def test_equal_ranks_share_and_unlisted_flows_share_the_rest():
    """Requests 4, 6 and 5 from a limit of 7: a class of the first two shares 7 as 2.8 and 4.2, and
    the third gets nothing. With only the first listed, the other two share the 3 left in proportion
    to their requests: 18/11 and 15/11."""
    flows, asked = [(0, -1)] * 3, [(4, None), (6, None), (5, None)]
    ends = {(OUT, 0): (0, 7)}
    assert shared(flows, ['tank'], asked, ends, {(OUT, 0): ((0, 1), (2,))}) == pytest.approx([2.8, 4.2, 0])
    assert shared(flows, ['tank'], asked, ends, {(OUT, 0): ((0,), (1, 2))}) == pytest.approx(
        [4, 18 / 11, 15 / 11]
    )


def test_a_flow_in_two_binding_groups_is_shared_by_max_min_over_both():
    """R-A3-09: two flows ask 2 L/h each from a limit of 3 L/h: 1.5 each. When the first also passes
    an inflow limited to 1 L/h, max-min gives 1 and 2; one group after another would give 1 and 1.5."""
    flows, asked = [(0, -1), (0, -1)], [(2, None), (2, None)]
    assert shared(flows, ['tank'], asked, {(OUT, 0): (0, 3)}) == [1.5, 1.5]
    flows = [(0, 1), (0, -1), (-1, 1)]
    asked = [(2, None), (2, None), (0, None)]
    ends = {(OUT, 0): (0, 3), (IN, 1): (0, 1)}
    assert shared(flows, ['tank', 'basin'], asked, ends) == pytest.approx([1, 2, 0], abs=1e-12)


def test_an_empty_store_shares_what_flows_in_by_its_allocation():
    """3 L/h reach an empty store through a pipe that carries no more than it asks; its two outflows
    ask 2 each: 1.5 each, or 2 and 1 with the second first."""
    flows, asked = [(-1, 0), (0, -1), (0, -1)], [(3, 3), (2, None), (2, None)]
    assert shared(flows, ['tank'], asked, lower=[0]) == [3, 1.5, 1.5]
    classes = {(OUT, 0): ((2,), (1,))}
    assert shared(flows, ['tank'], asked, classes=classes, lower=[0]) == [3, 1, 2]


def test_a_request_is_soft_where_another_claim_needs_more():
    """An empty store fed by a pipe that asks 1 L/h and has no capacity: its outflow asks 3 L/h, so
    the pipe carries 3 (D15). A common sink that asks 6 L/h of `main` (at most 4) and `backup`, with
    `main` first, gets 4 and 2."""
    assert shared([(-1, 0), (0, -1)], ['tank'], [(1, None), (3, None)], lower=[0]) == pytest.approx([3, 3])
    ends = {(IN, 0): (6, INF)}
    found = shared([(-1, 0), (-1, 0)], ['clinic'], [(0, 4), (0, None)], ends, {(IN, 0): ((0,), (1,))})
    assert found == pytest.approx([4, 2])


# ---- coupled transactions (flows with legs, S3) ------------------------------------------------------


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


def test_a_coupled_transaction_moves_by_the_least_fraction_of_its_flows():
    """Flows 0 and 1 are one transaction. A priority group gives flow 0 half of what it asked, so
    flow 1 moves by half too; flow 2 is outside the transaction and keeps its rate."""
    plan = system([('priority', [0])], 3, coupled=[(0, 1)])
    got, rationing = Allocation(plan).ration(np.array([4.0, 6.0, 5.0]), np.array([4.0, 6.0, 5.0]), [2.0])
    assert got.tolist() == [2.0, 3.0, 5.0] and rationing == [0]
    # A transaction that asks nothing moves nothing. A flow of a transaction that asks nothing moves
    # nothing at any fraction (spec, "Shared resources and competing invocations"): the others move
    # by their own least fraction, whole when nothing cuts them.
    got, _ = Allocation(plan).ration(np.array([0.0, 0.0, 5.0]), np.array([0.0, 0.0, 5.0]), [2.0])
    assert got.tolist() == [0.0, 0.0, 5.0]
    got, _ = Allocation(plan).ration(np.array([4.0, 0.0, 5.0]), np.array([4.0, 0.0, 5.0]), [9.0])
    assert got.tolist() == [4.0, 0.0, 5.0]
    plan = system([('priority', [1])], 3, coupled=[(0, 1)])
    got, _ = Allocation(plan).ration(np.array([0.0, 6.0, 5.0]), np.array([0.0, 6.0, 5.0]), [3.0])
    assert got.tolist() == [0.0, 3.0, 5.0]


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
            fraction = min(rates[j] / asked[j] for j in members if asked[j] > 0)
            for j in members:
                if asked[j] > 0:
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


def test_the_flows_of_a_transaction_that_ask_are_kept_for_each_pattern_of_signs():
    """Which flows of a transaction ask anything is kept for each pattern of the signs of the
    requests. A transaction that asks for a part of its flows moves the others by nothing, also
    after a pattern where every flow asks, and with other numbers; a cut of its asking flow cuts
    only what asks."""
    plan = Allocation(system([('priority', [0])], 3, coupled=[(0, 1)]))
    whole, part = np.array([4.0, 6.0, 5.0]), np.array([4.0, 0.0, 5.0])
    for requests, capacity, expected in (
        (whole, 9.0, [4.0, 6.0, 5.0]),
        (part, 9.0, [4.0, 0.0, 5.0]),
        (2 * whole, 4.0, [4.0, 6.0, 10.0]),
        (3 * part, 6.0, [6.0, 0.0, 15.0]),
        (part, 2.0, [2.0, 0.0, 5.0]),
        (whole, 9.0, [4.0, 6.0, 5.0]),
    ):
        got, _ = plan.ration(requests.copy(), requests.copy(), [capacity])
        assert got.tolist() == expected
