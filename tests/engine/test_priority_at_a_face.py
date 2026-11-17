"""A share that serves its flows in order, at a stock that rests empty.

When the stock is empty, the flows take what comes in, in the order of the share: the first flows get
all that they ask, one flow gets what is left, and the flows after it get nothing. The requests here are
no round numbers, so the engine's arithmetic of "what is left" has roundoff; before the correction of
D-62, a remainder a few units in the last place below zero gave the next flow a negative rate, and the
run stopped. The expectations are the closed form of the tank, worked from the requests alone.
"""

import math
import random

import pytest

from tests import build as b

UNIT, RATE = 'people', 'people/h'


def tank(asks, inflow, start, horizon, rate=lambda k, ask: b.q(ask, RATE), extra=()):
    """A stock `w` that `fill` fills and that the flows `use1`, `use2`, … drain, each into a tally of
    its own, with a share that serves them in that order and whose limit is above what they ask."""
    users = range(1, len(asks) + 1)
    members = [
        *extra,
        b.stock('w', start, UNIT, size=100),
        *(b.stock(f'u{k}', 0, UNIT, size=1000) for k in users),
        b.flow('fill', b.move(None, 'w'), b.q(inflow, RATE)),
        *(b.flow(f'use{k}', b.move('w', f'u{k}'), rate(k, ask)) for k, ask in zip(users, asks)),
        b.share('w', b.q(4 * sum(asks), RATE), [f'use{k}' for k in users]),
    ]
    return b.system(*members, horizon=horizon)


def served_in_order(asks, inflow):
    """What each flow gets of the inflow, in order: its request, or what the flows before it left."""
    left, got = inflow, []
    for ask in asks:
        got.append(min(ask, left))
        left = max(0.0, left - got[-1])
    return got


def cases():
    """Tanks with requests of three decimals, which are no round numbers in binary: the count of the
    users, where the inflow cuts, and the time at which the tank is empty all vary."""
    found = []
    for seed in range(40):
        choose = random.Random(seed)
        asks = [round(choose.uniform(0.5, 9.5), 3) for _ in range(choose.randint(2, 6))]
        inflow = round(choose.uniform(0.1, 0.9) * sum(asks), 3)
        start = round(choose.uniform(5, 30), 3)
        found.append((asks, inflow, start))
    return found


@pytest.mark.parametrize('asks, inflow, start', cases())
def test_the_flows_of_a_share_in_order_take_the_inflow_in_order_when_the_stock_is_empty(asks, inflow, start):
    empty_at = start / (sum(asks) - inflow)
    horizon = math.ceil(2 * empty_at + 1)
    _, trajectory = b.run(tank(asks, inflow, start, horizon))
    end = trajectory.env_at(horizon)
    got = served_in_order(asks, inflow)
    assert end['s.w'] == pytest.approx(0, abs=1e-9 * start)
    for k, (ask, rate) in enumerate(zip(asks, got), start=1):
        # All that it asks until the tank is empty, and its part of the inflow from then.
        expected = ask * empty_at + rate * (horizon - empty_at)
        assert end[f's.u{k}'] == pytest.approx(expected, rel=1e-9, abs=1e-9)
    # The material is counted once.
    assert end['s.w'] + sum(end[f's.u{k}'] for k in range(1, len(asks) + 1)) == pytest.approx(
        start + inflow * horizon, rel=1e-12
    )
    # A flow after the cut gets nothing: its tally does not move between two times on the empty face.
    later = trajectory.env_at((empty_at + horizon) / 2 + 0.25)
    for k, rate in enumerate(got, start=1):
        if rate == 0:
            assert end[f's.u{k}'] == later[f's.u{k}']


def test_the_cases_cut_at_the_first_flow_at_a_middle_one_and_at_the_last():
    """The cases above are of each kind: the inflow is less than the first request; it ends inside a
    request in the middle, with flows after it that get nothing; it reaches the last flow."""
    kinds = set()
    for asks, inflow, _ in cases():
        got = served_in_order(asks, inflow)
        cut = next(k for k, (ask, rate) in enumerate(zip(asks, got)) if rate < ask)
        kinds.add('first' if cut == 0 else 'last' if cut == len(asks) - 1 else 'middle')
        assert sum(got) == pytest.approx(inflow)
    assert kinds == {'first', 'middle', 'last'}


def test_a_share_in_order_with_requests_that_read_the_state_runs_to_its_end():
    """Each flow asks more as its user has taken more: `a (habit + 2 u) / (habit + u)` when the user has
    taken `u`. The first flow is never cut: its largest request, `2 a`, is less than the inflow. So its
    tally has the closed form `u / 2 + habit / 4 × ln(1 + 2 u / habit) = a t`."""
    asks, inflow, start, habit, horizon = (2.0, 4.0, 6.0, 8.0), 5.0, 160.0, 80.0, 48
    assert 2 * asks[0] < inflow < sum(asks)

    def rate(k, ask):
        return f'{b.q(ask, RATE)} * (1 + u{k} / (habit + u{k}))'

    text = tank(asks, inflow, start, horizon, rate, extra=[b.parameter('habit', habit, UNIT)])
    _, trajectory = b.run(text)
    end = trajectory.env_at(horizon)
    took = [end[f's.u{k}'] for k in range(1, len(asks) + 1)]
    assert end['s.w'] == pytest.approx(0, abs=1e-9 * start)
    assert end['s.w'] + sum(took) == pytest.approx(start + inflow * horizon, rel=1e-9)
    first = took[0]
    assert first / 2 + habit / 4 * math.log1p(2 * first / habit) == pytest.approx(asks[0] * horizon, rel=1e-6)
    # In order: when the tank is empty the last flow gets nothing, so it takes less than it asks even
    # at its least request.
    assert took[-1] < 0.9 * asks[-1] * horizon
