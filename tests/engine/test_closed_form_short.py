"""The short path of the closed form of the bound allocation (`Allocation.served_in_full`).

A stock that rests at a bound with an inflow that equals its outflows but for roundoff sends each
evaluation of the field to the closed form of the bound allocation, which then serves every unit in
full and gives the request back. `served_in_full` finds that with less work. Its claim is checked
call by call against the closed form with all of its work, and the runs are compared bit for bit.

The model is a tank with one inflow and two outflows that share it. The rates rise with time, so no
segment is exact: the solver asks for the field many times. The inflow is 1.1 times the first
outflow, or 1.05 times; the outflows together are 1.1 times the first outflow.

- Full (it starts at its upper bound of 100) with the inflow of 1.1: the tank stays full, and the
  inflow is served in full but for the evaluations where roundoff leaves an excess.
- Empty (it starts at 0) with the inflow of 1.05: the outflows get what comes in, by the policy of
  the share. Every call cuts a unit.
"""

import pytest

from napkin import store
from napkin.engine.allocation import Allocation
from napkin.engine.runtime import simulate
from tests import build as b

HORIZON = 40
# The integral of 1 + 0.01 t over the run: what the first outflow moves for a demand of 1.
MOVED = HORIZON + 0.005 * HORIZON**2
DEMANDS = (10304732.104954248, 1e7 / 3)
ORDERS = ('proportional', ['deliver', 'leak'], ['leak', 'deliver'])


def tank(demand, start, order, fill):
    rate = 'demand * (1 + 0.01 * t / 1 h)'
    text = b.system(
        b.parameter('demand', demand, 'people/h', 0, 1e9),
        b.stock('tank', start, maximum=100),
        b.stock('used', 0, kind='tally', size=None),
        b.stock('lost', 0, kind='tally', size=None),
        b.flow('fill', b.move(None, 'tank'), f'({rate}) * {fill}'),
        b.flow('deliver', b.move('tank', 'used'), rate),
        b.flow('leak', b.move('tank', 'lost'), f'({rate}) / 10'),
        b.share('tank', '1e12 people/h', order),
        horizon=HORIZON,
        outputs=(b.output('used', 's.used', 'people'),),
    )
    model = b.compiled(text)
    return model.resolve(next(iter(model.runs))), model.library


def moved(order, fill):
    """(what the first outflow moves, what the second moves) for a demand of 1, from an empty tank:
    all that comes in goes out, by the policy of the share."""
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


@pytest.fixture
def claims(monkeypatch):
    """The closed form with all of its work for each call, and what the short path said of the same
    call: [(the claim, whether the closed form gave the request back in each bit)]."""
    quick, closed, found, said = Allocation.served_in_full, Allocation.closed_form, [], []

    def recorded(self, *args):
        said.append(quick(self, *args))
        return False

    def full(self, a, bound, requested, adjustable):
        del said[:]
        out = closed(self, a, bound, requested, adjustable)
        if out is not None and said:
            found.append((said[0], out.tobytes() == requested.tobytes()))
        return out

    monkeypatch.setattr(Allocation, 'served_in_full', recorded)
    monkeypatch.setattr(Allocation, 'closed_form', full)
    return found


def test_each_claim_of_a_full_service_is_what_the_closed_form_gives(claims):
    """Whenever the short path says that every unit is served in full, the closed form gives the
    request back in each bit. The cases have many calls of each kind, with a proportional share and
    with the two orders of a priority share."""
    for demand, start, order, fill in CASES:
        simulate(*tank(demand, start, order, fill))
    wrong = [(claim, same) for claim, same in claims if claim and not same]
    assert wrong == []
    in_full = sum(claim for claim, _ in claims)
    cut = sum(not same for _, same in claims)
    # How many calls there are of each kind follows the steps of the solver: each kind has many.
    assert in_full > 100 and cut > 1000
    # The short path misses no full service of these models: each call that it leaves to the closed
    # form cuts a unit.
    assert all(claim or not same for claim, same in claims)


@pytest.mark.parametrize(('demand', 'start', 'order', 'fill'), CASES)
def test_a_run_is_the_same_in_each_bit_with_the_short_path_and_without(
    demand, start, order, fill, monkeypatch
):
    """The trajectory with the short path is the trajectory of the closed form with all of its
    work, bit for bit. From a full tank that stays full, and from an empty one, the two outflows
    moved what the model says in closed form."""
    rs, library = tank(demand, start, order, fill)
    short = simulate(rs, library)
    monkeypatch.setattr(Allocation, 'served_in_full', lambda self, *args: False)
    whole = simulate(rs, library)
    assert store.fingerprint(short) == store.fingerprint(whole)
    end = short.env_at(float(HORIZON))
    if (start, fill) != (100, 1.05):
        used, lost = moved(order, fill)
        assert end['s.used'] == pytest.approx(used * demand, rel=1e-7)
        assert end['s.lost'] == pytest.approx(lost * demand, rel=1e-7)
        assert end['s.tank'] == pytest.approx(start, abs=1e-6)
