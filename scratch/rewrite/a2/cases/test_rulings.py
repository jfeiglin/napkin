"""One test for each ruling of FINDINGS.md: the example is run under the rule (the default of its switch in
`ref.model.Rules`) and under the alternative, and the two must differ. Each test returns nothing; the numbers
that FINDINGS.md quotes are the asserted values."""
from fractions import Fraction as F

import pytest

from ref import (Diagnostic, Endpoint, Model, N, NotCovered, RunFailed, SINK, SOURCE, add, after, calc, choose, count,
                 delayed, elapsed, event, flow, fmax, inp, leg, legs, link, lit, none, priority, set_, since, solver,
                 start, sub, t, this, trigger, uniform, until, value)
from ref.evaluate import Ev, Scope
from ref.model import Config, Rules
from ref.run import Run, Unavailable


def run(m, horizon=0, **rules):
    return Run(m, Config(horizon=horizon, rules=Rules(**rules))).run()


def fails(m, horizon=0, match=None, **rules):
    with pytest.raises(RunFailed, match=match) as e:
        run(m, horizon, **rules)
    return str(e.value)


def now(r, e):
    return Ev(r, r.view, Scope()).val(e)


# R-A2-01 the order of due stages ---------------------------------------------------------------------
def test_01_stage_order():
    m = Model()
    m.entity('board', fields=[value('last', '-')], events=[
        event('a', steps=[after(1, []), after(1, [set_(this.last, 'A')])]),  # older; its 2nd stage is scheduled at 1 h
        event('b', steps=[after(2, [set_(this.last, 'B')])])])  # younger; scheduled at 0 h
    m.setup = [start(N.board.a), start(N.board.b)]
    assert run(m, 3).read(N.board.last) == 'B'  # age: A commits, then B; the last write wins
    assert run(m, 3, stage_order='scheduled').read(N.board.last) == 'A'


# R-A2-02 the members of a start on a collection -----------------------------------------------------
def test_02_broadcast():
    m = Model()
    m.template('Machine', fields=[inp('rank', 0)], events=[event('repair', steps=[after(0, [set_(N.board.last, this)])])])
    m.instance('m1', 'Machine', rank=2)
    m.instance('m2', 'Machine', rank=1)
    m.entity('board', fields=[value('last', None)])
    m.setup = [start(N.Machine.instances.by(N.rank).repair)]
    assert run(m, 1).read(N.board.last).id == 'm1'  # key order: m2 (rank 1) registers and commits first
    assert run(m, 1, broadcast='creation').read(N.board.last).id == 'm2'


# R-A2-03 conflicting writes from two stages of one round --------------------------------------------
def build_beans():
    m = Model()
    m.entity('grinder', fields=[value('beans', 20)], events=[
        event('use', steps=[after(1, [set_(this.beans, 8)])]), event('top', steps=[after(1, [add(this.beans, 4)])])])
    m.setup = [start(N.grinder.use), start(N.grinder.top)]
    return m


def test_03_round_writes():
    assert run(build_beans(), 2).read(N.grinder.beans) == 12
    fails(build_beans(), 2, match='conflicting writes to grinder.beans', round_writes='isolated')


# R-A2-04 reset cycles ---------------------------------------------------------------------------------
def build_cycle(limit):
    m = Model()
    m.entity('pump', fields=[value('n', 0)], events=[event(
        'bump', triggers=[trigger(this.n < limit, [start(this.bump)], reset=('when', lit(True)))],
        steps=[after(0, [add(this.n, 1)])])])
    return m


def test_04_refire():
    assert run(build_cycle(2), 1).read(N.pump.n) == 2  # two firings at t = 0, in two rounds
    fails(build_cycle(2), 1, match='fires a second time', refire='once')
    text = fails(build_cycle(10**6), 1, match='more than 100 rounds')
    assert 'pump.bump.when[0]' in text


# R-A2-05 setup order ----------------------------------------------------------------------------------
def build_setup():
    m = Model()
    m.entity('grinder', fields=[value('beans', 8), calc('low', this.beans <= 10)], events=[
        event('refill', triggers=[trigger(this.low, [start(this.refill)], reset=('when', lit(False)))]),
        event('prepare', steps=[after(0, [set_(this.beans, 12)])])])
    m.setup = [start(N.grinder.prepare)]
    return m


def test_05_setup():
    assert run(build_setup(), 1).times('fire') == [0]  # round zero reads 8 g
    assert run(build_setup(), 1, setup='starts_first').times('fire') == []  # the start runs first: 12 g


# R-A2-06 none --------------------------------------------------------------------------------------
def build_none():
    m = Model()
    m.entity('gauge', fields=[value('reading', None), calc('shown', this.reading + 1), calc('absent', this.reading == none)])
    return m


def test_06_none():
    r = run(build_none())
    assert r.read(N.gauge.shown) is None and r.read(N.gauge.absent) is True
    assert r.read(N.gauge.reading <= 3) is None
    with pytest.raises(RunFailed, match='none'):
        r.read(lit(5) + N.gauge.reading)  # rule: none
    s = run(build_none(), none='strict')
    with pytest.raises(RunFailed, match='reads a value that is none'):
        s.read(N.gauge.shown)
    assert s.read(N.gauge.absent) is True
