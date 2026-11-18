"""Case 23: `move`. 3 L from 8 L into an empty store capped at 4 L gives 5 and 3; 5 L fails and leaves 8 and 0."""
import pytest

from ref import Model, N, RunFailed, after, event, move, start, this, value
from ref.evaluate import Ev, Scope
from ref.run import Run


def build(amount):
    m = Model()
    m.entity('a', fields=[value('water', 8, 0, 20, readonly=True)])
    m.entity('b', fields=[value('water', 0, 0, 4)])
    m.entity('op', events=[event('go', steps=[after(1, [move(amount, N.a.water, N.b.water)])])])
    m.setup = [start(N.op.go)]
    return m


def now(r, e):
    return Ev(r, r.view, Scope()).val(e)


def test_move_three():
    r = Run(build(3), horizon=2).run()
    assert (r.read(N.a.water, 2), r.read(N.b.water, 2)) == (5, 3)
    assert ('move', 1, ) == r.ledger[-1][:2] or any(e[0] == 'move' and e[4] == 3 for e in r.ledger)
    assert r.conservation()['balanced']


def test_move_five_fails():
    r = Run(build(5), horizon=2)
    with pytest.raises(RunFailed, match='would hold 5'):
        r.run()
    assert (now(r, N.a.water), now(r, N.b.water)) == (8, 0)
