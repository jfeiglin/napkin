"""Local sharing (`network.Instant`): a part that asks nothing gets its targets without the selection
order, as the selection order gives them; and a network keeps one plan for each structure of an
instant (`Network.plans`), which is the plan that the instant itself would make."""

import math
import random

import numpy as np
import pytest

from napkin.engine.errors import SimulationError
from napkin.engine.timeline.network import (
    BACKWARD,
    DIRECT,
    DIRECTED,
    FORWARD,
    IN,
    LEG,
    LEGS,
    OUT,
    ROUTE,
    Asked,
    Instant,
    Network,
)

INF = math.inf


def held_part(request):
    """A store at its lower bound that a pipe fills (connection 0), a route to a second store drains
    and fills (1 forward, 2 backward), and a flow with legs drains (3) beside a leg into the second
    store (4): one coupled part of three flows, which the general form solves."""
    network = Network(
        ['pipe', 'link', 'restore'],
        ['tank', 'basin'],
        [-1, 0, 1, 0, -1],
        [0, 1, 0, -1, 1],
        {},
        np.zeros(5),
        np.zeros(2),
        of=[0, 1, 1, 2, 2],
        roles=np.array([DIRECT, FORWARD, BACKWARD, LEG, LEG]),
        kinds=np.array([DIRECTED, ROUTE, LEGS]),
        connections=['pipe', 'link.forward', 'link.backward', 'restore.a', 'restore.b'],
    )
    asked = Asked(
        np.array(request, dtype=float),
        np.array([INF, 2.0, 2.0, INF, 1.0]),
        np.zeros((2, 2)),
        np.full((2, 2), INF),
    )
    return Instant(network, asked, np.array([True, False]), np.array([False, False]))


def test_a_part_that_asks_nothing_gets_its_targets_and_counts_as_solved():
    instant = held_part([-0.0, 0.0, 0.0, 0.0, 0.0])
    assert instant.parts([0]) == [[0, 1, 2]]
    instant.rate_errors = {1: 1e-9, 3: 1e-9, 7: 1.0}
    found = instant.values()
    assert found.tolist() == [0.0, 0.0, 0.0]
    assert np.signbit(found[0]) and not np.signbit(found[1])  # the pipe's request, -0.0, as it is
    assert instant.selected == 1
    assert instant.rate_errors == {7: 1.0}  # the part's connections have no refinement error


def test_a_part_that_asks_something_is_shared_by_the_selection_order():
    instant = held_part([0.0, 0.0, 0.0, 1.0, 0.0])
    pipe, link, served = instant.values().tolist()
    assert instant.selected == 1
    assert served == 1.0  # leg a takes its 1 L/h in full
    # The empty tank passes on what flows in: the pipe and the route's backward part bring 1 L/h.
    assert pipe + max(-link, 0.0) == pytest.approx(1.0) and pipe > 0 and link < 0


def plain(prepared):
    """A plan with its arrays as lists, so that two plans compare by their numbers."""
    if isinstance(prepared, np.ndarray):
        return prepared.tolist()
    if isinstance(prepared, list | tuple):
        return [plain(item) for item in prepared]
    return prepared


def random_network(rng):
    """A network of directed flows between two to four stores and the outside, with a priority at
    some endpoints that two or more flows meet."""
    count = rng.randint(2, 4)
    flows = []
    for _ in range(rng.randint(3, 7)):
        source = rng.choice([-1, *range(count)])
        sink = rng.choice([s for s in [-1, *range(count)] if s != source or s < 0])
        flows.append((source, sink))
    classes = {}
    for side, at in ((OUT, 0), (IN, 1)):
        for s in range(count):
            mine = [k for k, flow in enumerate(flows) if flow[at] == s]
            if len(mine) >= 2 and rng.random() < 0.4:
                rng.shuffle(mine)
                cut = rng.randint(1, len(mine) - 1)
                classes[(side, s)] = (tuple(mine[:cut]), tuple(mine[cut:]))
    network = Network(
        [f'f{k}' for k in range(len(flows))],
        [f's{s}' for s in range(count)],
        [a for a, _ in flows],
        [b for _, b in flows],
        classes,
        np.zeros(len(flows)),
        np.zeros(count),
    )
    return network, len(flows), count


def random_values(rng, size, count):
    """What the connections and endpoints of a network ask, and the stores at their bounds."""
    request = np.array([rng.choice([0.0, 0.0, 5e-324, 0.5, 1.0, 2.0]) for _ in range(size)])
    capacity = np.array([rng.choice([INF, INF, 0.0, 1.0, 2.0, float(r)]) for r in request])
    end_request = np.array([[rng.choice([0.0, 0.0, 0.0, 1.0, 3.0]) for _ in range(count)] for _ in range(2)])
    end_capacity = np.array(
        [[rng.choice([INF, INF, INF, 0.0, 1.0, 2.5]) for _ in range(count)] for _ in range(2)]
    )
    lower = np.array([rng.random() < 0.4 for _ in range(count)])
    upper = np.array([not low and rng.random() < 0.3 for low in lower])
    return request, capacity, end_request, end_capacity, lower, upper


def scaled(rng, numbers):
    """The numbers with each normal positive one times a factor of its own: a zero, a subnormal and
    an infinity stay, so most of the structure stays, but a capacity can pass its request."""
    return np.array(
        [x * rng.choice([0.5, 1.0, 2.0, 3.0]) if 1e-300 < x < INF else x for x in np.ravel(numbers)]
    ).reshape(np.shape(numbers))


def changed(rng, request, capacity, end_request, end_capacity, lower, upper):
    """Copies of the values of an instant with one fact of its structure changed: a store's bound, or
    whether a request, a capacity, an endpoint's request or its capacity is zero, small or none."""
    request, capacity, end_request, end_capacity = (
        np.array(x, dtype=float) for x in (request, capacity, end_request, end_capacity)
    )
    lower, upper = np.array(lower), np.array(upper)
    k, side, s = rng.randrange(len(request)), rng.randrange(2), rng.randrange(len(lower))
    what = rng.randrange(6)
    if what == 0:
        lower[s] = not lower[s]
    elif what == 1:
        upper[s] = not upper[s]
    elif what == 2:
        request[k] = rng.choice([0.0, 5e-324, 1.0])
    elif what == 3:
        capacity[k] = rng.choice([0.0, INF, float(request[k])])
    elif what == 4:
        end_request[side, s] = rng.choice([0.0, 2.0])
    else:
        end_capacity[side, s] = rng.choice([INF, 0.0, 1.5])
    return request, capacity, end_request, end_capacity, lower, upper


@pytest.mark.parametrize('seed', range(60))
def test_the_plan_of_a_structure_is_the_plan_of_each_instant_that_has_it(seed):
    """The structure of an instant (`Instant._structure`) holds all that its plan reads: wherever two
    instants share a structure, the plan that the network keeps for it is the one that the second
    makes for itself, part by part."""
    rng = random.Random(seed)
    network, size, count = random_network(rng)
    shared, instants = 0, []
    for _ in range(8):
        base = random_values(rng, size, count)
        for _ in range(16):
            *numbers, lower, upper = changed(rng, *base) if rng.random() < 0.5 else base
            numbers = [scaled(rng, x) for x in numbers]
            instants.append(Instant(network, Asked(*numbers), lower, upper))
    for instant in instants:
        key = instant._structure()
        kept = network.plans.get(key)
        try:
            instant.values()
        except SimulationError:
            # A plan that fails is not kept (a general part also fails by its numbers alone).
            assert kept is not None or key not in network.plans
            continue
        if kept is None:
            continue
        shared += 1
        fresh = [(part, instant._prepare(part)) for part in instant.parts(instant._seeds())]
        assert plain(kept) == plain(fresh)
    assert shared  # the draws give instants of one structure


def test_a_part_that_fails_fails_again_at_the_next_instant_of_its_structure():
    """Two empty stores that feed each other through pipes that carry what they ask, and a claim that
    drains the first: the order of supply has no first store, and each instant says so."""
    network = Network(
        ['to_b', 'to_a', 'out'], ['a', 'b'], [0, 1, 0], [1, 0, -1], {}, np.zeros(3), np.zeros(2)
    )
    for wanted in (1.0, 2.0):
        asked = Asked(
            np.array([1.0, 1.0, wanted]), np.array([1.0, 1.0, INF]), np.zeros((2, 2)), np.full((2, 2), INF)
        )
        instant = Instant(network, asked, np.array([True, True]), np.array([False, False]))
        with pytest.raises(SimulationError, match='ring of stores at their lower bound'):
            instant.values()
        assert network.plans == {}
