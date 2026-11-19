"""The closed form of local sharing is a short path of the selection order (`network.Instant._groups`).

Where a store rests at its lower bound and its inflows carry no more than they ask, its outflows
share what flows in by their allocation, and groups in supply order give that in closed form
(water-filling, R-A3-09). Everywhere else, and wherever the form does not hold, the selection order
gives the rates (`selection.select`). The closed form must give what the selection order gives: the
runs are compared with it and without it, and with what the model says in closed form.

The model is a tank with one inflow and two outflows that share it, on the sparse integrator: the
rates rise with time, so the solver asks for the rates many times. The inflow is 1.1 times the first
outflow, or 1.05 times; the outflows together are 1.1 times the first outflow. The inflow carries no
more than it asks (a capacity at its request), else a claim of the outflows would raise it (D15).

- Full (it starts at its upper bound of 100) with the inflow of 1.1: the tank stays full, and each
  outflow gets what it asks; the selection order gives that, since a full store with inflows has no
  closed form.
- Empty (it starts at 0) with the inflow of 1.05: the outflows get what comes in, by the policy of
  the tank's outflow.
- Full with the inflow of 1.05: the tank drains, empties, and shares from then on.
"""

import pytest

from napkin.engine import read, run
from napkin.engine.timeline.network import Instant
from napkin.program.build import (
    SOURCE,
    Builder,
    endpoint,
    flow,
    formula,
    input_,
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
HORIZON = 40
# The integral of 1 + 0.01 t over the run: what the first outflow moves for a demand of 1.
MOVED = HORIZON + 0.005 * HORIZON**2
DEMANDS = (10304732.104954248, 1e7 / 3)
ORDERS = ('proportional', ('deliver', 'leak'), ('leak', 'deliver'))


def tank(demand, start, order, fill):
    rate = this.demand * (1 + q(0.01, '1/h') * t)
    allocation = (
        proportional() if order == 'proportional' else priority(*(getattr(this, name) for name in order))
    )
    b = Builder(UNITS)
    b.entity(
        's',
        input_('demand', 'people/h', demand, lower=0, upper=1e9),
        value(
            'tank',
            'people',
            start,
            lower=0,
            upper=100,
            outflow=endpoint(capacity=q(1e12, 'people/h'), allocation=allocation),
        ),
        value('used', 'people', 0, lower=0),
        value('lost', 'people', 0, lower=0),
        flow('fill', SOURCE, this.tank, request=formula(rate * fill), capacity=formula(rate * fill)),
        flow('deliver', this.tank, this.used, request=formula(rate)),
        flow('leak', this.tank, this.lost, request=formula(rate / 10)),
    )
    return b.finish()


def moved(order, fill):
    """(what the first outflow moves, what the second moves) for a demand of 1, from an empty tank:
    all that comes in goes out, by the policy of the tank's outflow."""
    if fill >= 1.1:
        return MOVED, MOVED / 10
    if order == 'proportional':
        return MOVED * fill / 1.1, MOVED / 10 * fill / 1.1
    if order[0] == 'deliver':
        return MOVED, MOVED * (fill - 1)
    return MOVED * (fill - 0.1), MOVED / 10


CASES = [
    (demand, start, order, fill)
    for demand in DEMANDS
    for start, fill in ((100, 1.1), (0, 1.05), (100, 1.05))
    for order in ORDERS
]


def ends(program):
    record = run(program, Configuration(Request(HORIZON)))
    assert record.failure is None, record.failure.detail('message')
    keys = [Key('s', (name,)) for name in ('used', 'lost', 'tank')]
    return [reading.values[0] for reading in read(record, program, keys, [float(HORIZON)])]


@pytest.mark.parametrize(('demand', 'start', 'order', 'fill'), CASES)
def test_a_run_is_the_same_with_the_closed_form_and_without(demand, start, order, fill, monkeypatch):
    """The run with the closed form is the run of the selection order alone, within the tolerance of
    the solver. From a full tank that stays full, and from an empty one, the two outflows moved what
    the model says in closed form."""
    program = tank(demand, start, order, fill)
    short = ends(program)
    monkeypatch.setattr(Instant, '_groups', lambda self, part: None)
    whole = ends(program)
    assert short == pytest.approx(whole, rel=1e-9, abs=1e-6)
    if (start, fill) != (100, 1.05):
        used, lost = moved(order, fill)
        assert short[0] == pytest.approx(used * demand, rel=1e-7)
        assert short[1] == pytest.approx(lost * demand, rel=1e-7)
        assert short[2] == pytest.approx(start, abs=1e-6)
