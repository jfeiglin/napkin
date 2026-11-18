"""Case 20: the history table, each expression of it."""
from fractions import Fraction as F

import pytest

from ref import (Model, N, RunFailed, add, after, any_, count, event, set_, since, start, t, this, trigger, value)
from ref.run import Run, Unavailable


def build():
    refill = event('refill', params=['amount'], locals=[value('status', 'WEIGHING')],
                   steps=[after(F(1, 2), [add(this.beans, N.amount), set_(N.status, 'ADDED')])])
    plan = event('plan', steps=[after(1, [start(this.refill, 50)]),
                                after(1, [start(this.refill, 10), start(this.refill, 20)]),  # two at t = 2
                                after(F(1, 4), [])])
    m = Model()
    m.entity('grinder', fields=[value('beans', 8), value('flag', False)], events=[refill, plan])
    m.setup = [start(N.grinder.plan)]
    return m


@pytest.fixture(scope='module')
def run():
    return Run(build(), horizon=4).run()


OCC = N.grinder.refill.occurrences


def test_table(run):
    r = run
    assert r.read(N.grinder.beans, 4) == 88
    assert r.read(count(OCC), F(1, 2)) == 0
    assert r.read(count(OCC), F(5, 4)) == 1
    assert r.read(count(OCC.done), F(5, 4)) == 0 and r.read(count(OCC.done), F(3, 2)) == 1
    assert r.read(any_(OCC.active), F(5, 4)) is True and r.read(any_(OCC.active), F(3, 2)) is False
    assert r.read(OCC.at(t).status, F(5, 4)) == 'WEIGHING' and r.read(OCC.at(t).status, F(3, 2)) == 'ADDED'
    assert r.read(since(N.grinder.refill), F(3, 2)) == F(1, 2)


def test_two_starts_at_one_time(run):
    assert run.read(count(OCC), 2) == 3
    assert run.read(OCC.at(t).amount, 2) == 20  # the later-created one
    assert run.read(OCC.at(t).started, 2) == 2


def test_invalid_reads(run):
    with pytest.raises(RunFailed, match='before the first occurrence'):
        run.read(since(N.grinder.refill), F(1, 2))
    with pytest.raises(RunFailed, match='empty'):
        run.read(OCC.at(t).status, F(1, 2))
    # the guard of the spec short-circuits
    assert run.read((count(OCC) > 0) & (since(N.grinder.refill) >= 3), F(1, 2)) is False
    assert isinstance(run.report(since(N.grinder.refill), [F(1, 2)])[0], Unavailable)
