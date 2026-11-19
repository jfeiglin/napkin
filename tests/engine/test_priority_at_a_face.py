"""A priority outflow, at a stock that rests empty.

When the stock is empty, its outflows share what comes in by its allocation: in the order of
`priority(...)`, the first flows get all that they ask, one flow gets what is left, and the flows
after it get nothing. The fill carries no more than it asks (its capacity is its request): a request
is soft (D15), so a fill with no capacity would be raised to serve the outflows. The requests here are
no round numbers, so "what is left" has roundoff. The expectations are the closed form of the tank,
worked from the requests alone.
"""

import math
import random

import pytest

from napkin.engine import read, run
from napkin.program.build import SOURCE, Builder, endpoint, flow, formula, input_, priority, q, this, value
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'person': {'people': 1}}
RATE = 'person/h'


def tank(asks, inflow, start, horizon, rate=None):
    """A stock `w` that `fill` fills and that the flows `use1`, `use2`, … drain, each into a tally of
    its own, with an outflow that serves them in that order and whose limit is above what they ask."""
    users = range(1, len(asks) + 1)
    rate = rate or (lambda k, ask: q(ask, RATE))
    b = Builder(UNITS)
    b.entity(
        's',
        input_('habit', 'person', 80),
        value(
            'w',
            'person',
            start,
            lower=0,
            scale=100,
            outflow=endpoint(
                capacity=q(4 * sum(asks), RATE),
                allocation=priority(*(getattr(this, f'use{k}') for k in users)),
            ),
        ),
        *(value(f'u{k}', 'person', 0, lower=0, scale=1000) for k in users),
        flow('fill', SOURCE, this.w, request=q(inflow, RATE), capacity=q(inflow, RATE)),
        *(
            flow(f'use{k}', this.w, getattr(this, f'u{k}'), request=rate(k, ask))
            for k, ask in zip(users, asks)
        ),
    )
    return b.finish(), Configuration(Request(horizon))


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


def at(record, program, names, t):
    return [reading.values[0] for reading in read(record, program, names, [t])]


@pytest.mark.parametrize('asks, inflow, start', cases())
def test_the_flows_of_a_priority_outflow_take_the_inflow_in_order_when_the_stock_is_empty(
    asks, inflow, start
):
    empty_at = start / (sum(asks) - inflow)
    horizon = math.ceil(2 * empty_at + 1)
    program, configuration = tank(asks, inflow, start, horizon)
    record = run(program, configuration)
    assert record.failure is None
    names = ['s.w', *(f's.u{k}' for k in range(1, len(asks) + 1))]
    end = at(record, program, names, horizon)
    got = served_in_order(asks, inflow)
    assert end[0] == pytest.approx(0, abs=1e-9 * start)
    for k, (ask, rate) in enumerate(zip(asks, got), start=1):
        # All that it asks until the tank is empty, and its part of the inflow from then.
        expected = ask * empty_at + rate * (horizon - empty_at)
        assert end[k] == pytest.approx(expected, rel=1e-9, abs=1e-9)
    # The material is counted once.
    assert sum(end) == pytest.approx(start + inflow * horizon, rel=1e-12)
    # A flow after the cut gets nothing: its tally does not move between two times on the empty face.
    later = at(record, program, names, (empty_at + horizon) / 2 + 0.25)
    for k, rate in enumerate(got, start=1):
        if rate == 0:
            assert end[k] == later[k]


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


def test_a_priority_outflow_with_requests_that_read_the_state_runs_to_its_end():
    """Each flow asks more as its user has taken more: `a (habit + 2 u) / (habit + u)` when the user has
    taken `u`. The first flow is never cut: its largest request, `2 a`, is less than the inflow. So its
    tally has the closed form `u / 2 + habit / 4 × ln(1 + 2 u / habit) = a t`. The rates move, so the
    set runs on the sparse integrator, with the sharing at each evaluation."""
    asks, inflow, start, habit, horizon = (2.0, 4.0, 6.0, 8.0), 5.0, 160.0, 80.0, 48
    assert 2 * asks[0] < inflow < sum(asks)

    def rate(k, ask):
        u = getattr(this, f'u{k}')
        return formula(q(ask, RATE) * (1 + u / (this.habit + u)))

    program, configuration = tank(asks, inflow, start, horizon, rate)
    record = run(program, configuration)
    assert record.failure is None, record.failure
    names = ['s.w', *(f's.u{k}' for k in range(1, len(asks) + 1))]
    end = at(record, program, names, horizon)
    took = end[1:]
    assert end[0] == pytest.approx(0, abs=1e-9 * start)
    assert sum(end) == pytest.approx(start + inflow * horizon, rel=1e-9)
    first = took[0]
    assert first / 2 + habit / 4 * math.log1p(2 * first / habit) == pytest.approx(asks[0] * horizon, rel=1e-6)
    # In order: when the tank is empty the last flow gets nothing, so it takes less than it asks even
    # at its least request.
    assert took[-1] < 0.9 * asks[-1] * horizon
