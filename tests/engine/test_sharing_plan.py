"""Local sharing of a part (`network.Instant`): a part that asks nothing gets its targets without the
selection order, as the selection order gives them."""

import math

import numpy as np
import pytest

from napkin.engine.timeline.network import (
    BACKWARD,
    DIRECT,
    DIRECTED,
    FORWARD,
    LEG,
    LEGS,
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
