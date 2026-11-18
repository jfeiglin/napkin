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
    assert r.read(lit(5) + N.gauge.reading) is None
    s = run(build_none(), none='strict')
    with pytest.raises(RunFailed, match='reads a value that is none'):
        s.read(N.gauge.shown)
    assert s.read(N.gauge.absent) is True


# R-A2-07 min and max over nothing --------------------------------------------------------------------
def build_empty():
    m = Model()
    m.template('Pump', fields=[value('rate', 1)])
    m.entity('site')
    return m


def test_07_empty_minmax():
    r = run(build_empty())
    assert r.read(fmax(N.Pump.instances.rate)) is None
    assert r.read(fmax(0, N.Pump.instances.rate)) == 0
    e = run(build_empty(), empty_minmax='error')
    with pytest.raises(RunFailed, match='over nothing'):
        e.read(fmax(N.Pump.instances.rate))
    assert e.read(fmax(0, N.Pump.instances.rate)) == 0


# R-A2-08 elapsed after several writes in one stage ---------------------------------------------------
def build_elapsed():
    m = Model()
    m.entity('valve', fields=[value('state', 'A')], events=[
        event('flip', steps=[after(2, [set_(this.state, 'B'), set_(this.state, 'A')])])])
    m.setup = [start(N.valve.flip)]
    return m


def test_08_elapsed():
    assert run(build_elapsed(), 3).read(elapsed(N.valve.state)) == 3
    assert run(build_elapsed(), 3, elapsed='every_write').read(elapsed(N.valve.state)) == 1


# R-A2-09 a read with zero delay inside a stage -------------------------------------------------------
def build_delayed():
    m = Model()
    m.entity('box', fields=[value('x', 1), value('y', 0)], events=[
        event('go', steps=[after(1, [set_(this.x, 5), set_(this.y, delayed(this.x, 0))])])])
    m.setup = [start(N.box.go)]
    return m


def test_09_delayed_zero():
    assert run(build_delayed(), 2).read(N.box.y) == 1
    assert run(build_delayed(), 2, delayed_zero='own_writes').read(N.box.y) == 5


# R-A2-10 what stays readable on a finished occurrence ------------------------------------------------
def build_finished():
    m = Model()
    m.entity('tank', events=[event('job', params=['amount'], locals=[calc('double', N.amount * 2)], steps=[after(1, [])])])
    m.setup = [start(N.tank.job, 7)]
    return m


def test_10_finished():
    occ = N.tank.job.occurrences.at(t)
    r = run(build_finished(), 2)
    assert (r.read(occ.amount), r.read(occ.double), r.read(occ.done), r.read(occ.active)) == (7, 14, True, False)
    b = run(build_finished(), 2, finished='builtin')
    assert b.read(occ.done) is True
    with pytest.raises(RunFailed, match='after the occurrence has finished'):
        b.read(occ.amount)


# R-A2-11 a saved reference to an occurrence ----------------------------------------------------------
def build_saved():
    m = Model()
    m.entity('unit', fields=[value('saved', None)], events=[
        event('child', steps=[until(lit(False))]),
        event('parent', steps=[after(1, [start(this.child)]), after(0, [set_(this.saved, this.child.occurrences.at(t))]),
                               after(1, [start(this.child)])])])
    m.setup = [start(N.unit.parent)]
    return m


def test_11_saved_occurrence():
    assert run(build_saved(), 3).read(N.unit.saved.started) == 1
    assert run(build_saved(), 3, saved_occurrence='follows').read(N.unit.saved.started) == 2


# R-A2-12 a flow with legs that two endpoints rank differently ----------------------------------------
def build_tiers():
    m = Model()
    m.entity('x', fields=[value('water', 100, 0, 100, outflow=Endpoint(capacity=lit(6), allocation=priority(N.site.a, N.site.r.l1)))])
    m.entity('y', fields=[value('water', 100, 0, 100, outflow=Endpoint(capacity=lit(4), allocation=priority(N.site.r.l2, N.site.b)))])
    m.entity('site', flows=[flow('a', N.x.water, SINK, request=2), flow('b', N.y.water, SINK, request=4),
                            legs('r', leg('l1', N.x.water, SINK, request=4), leg('l2', N.y.water, SINK, request=4))])
    return m


def test_12_tiers():
    def got(r):
        return r.read(N.site.r.served_fraction), r.read(N.site.b.actual_rate), r.read(N.site.a.actual_rate)
    assert got(run(build_tiers())) == (1, 0, 2)  # r waits for a only; b waits for r
    assert got(run(build_tiers(), tiers='latest')) == (F(1, 2), 2, 2)  # r and b share the second tier
    assert got(run(build_tiers(), tiers='earliest')) == (1, 0, 2)  # here like the rule


# R-A2-13 the budget for occurrences that never finish -------------------------------------------------
def build_forever():
    m = Model()
    m.entity('desk', fields=[value('open', False)], events=[
        event('ticket', triggers=[trigger(t >= 0, [start(this.ticket)], reset=('after', 1))], steps=[until(this.open)])])
    return m


def test_13_budget():
    with pytest.raises(RunFailed, match=r'budget: 3 occurrences of desk.ticket run at once at t = 3 h') as e:
        Run(build_forever(), Config(horizon=10, max_active=3)).run()
    assert 'desk.ticket#1' in str(e.value) and 'until' in str(e.value)
    r = Run(build_forever(), Config(horizon=10, max_active=None)).run()
    assert r.read(count(N.desk.ticket.occurrences)) == 11


# R-A2-14 where a human choice pauses -------------------------------------------------------------------
def build_choice():
    m = Model()
    m.entity('crew', fields=[value('x', 0), value('plan', '-')], events=[
        event('child', steps=[after(5, [])]),
        event('shift', steps=[after(1, [start(this.child), set_(this.x, 1), set_(this.plan, choose('plan', 'repair', 'wait'))])])])
    m.setup = [start(N.crew.shift)]
    return m


def test_14_pause():
    def seen(rules):
        r = Run(build_choice(), Config(horizon=3, rules=Rules(**rules))).run()
        assert r.paused['key'] == 'plan@crew.shift#1' and r.paused['time'] == 1
        return now(r, N.crew.x), now(r, count(N.crew.child.occurrences))
    assert seen({}) == (0, 0)
    assert seen({'pause': 'split'}) == (1, 1)
    r = Run(build_choice(), Config(horizon=3, choices={'plan': 'repair'})).run()
    assert r.read(N.crew.plan) == 'repair' and r.read(count(N.crew.child.occurrences)) == 1


# R-A2-15 where an assert on state is checked -----------------------------------------------------------
def build_assert():
    m = Model()
    m.entity('tank', fields=[value('water', 10, 0, 100)], flows=[flow('drain', this.water, SINK, request=1)],
             events=[event('refill', steps=[after(7, [set_(this.water, 10)])])])
    m.setup = [start(N.tank.refill)]
    m.check(N.tank.water >= 5, text='tank.water >= 5 L')
    return m


def test_15_asserts():
    fails(build_assert(), 8, match=r'fails just after t = 5 h')
    assert run(build_assert(), 8, asserts='rounds').read(N.tank.water) == 9  # 3 L at 7 h was never checked


# R-A2-16 an invalid history read that a report asks for ------------------------------------------------
def build_report(rule):
    m = Model()
    m.entity('grinder', events=[event('refill', steps=[after(1, [])])])
    m.setup = []
    return Run(m, Config(horizon=2, report=[('since', since(N.grinder.refill), [0])], rules=Rules(report=rule)))


def test_16_report():
    r = build_report('record').run()
    assert r.view.t == 2 and isinstance(r.report(since(N.grinder.refill), [0])[0], Unavailable)
    with pytest.raises(RunFailed, match='before the first occurrence'):
        build_report('in_run').run()


# R-A2-17 the key of each draw -----------------------------------------------------------------------------
def build_draws(extra):
    m = Model()
    m.entity('pump', fields=[inp('extra', extra), value('speeds', uniform(0, 10)), value('x', 0), value('y', 0)], events=[
        event('early', steps=[after(0, [set_(this.y, this.speeds.draw())], when=this.extra)]),
        event('late', steps=[after(1, [set_(this.x, this.speeds.draw())])])])
    m.setup = [start(N.pump.early), start(N.pump.late)]
    return m


def test_17_draws():
    def x(extra, rule):
        return Run(build_draws(extra), Config(horizon=2, mode='sampled', seed=7, rules=Rules(draws=rule))).run().read(N.pump.x)
    assert x(True, 'keyed') == x(False, 'keyed')  # an extra draw elsewhere does not move this one
    assert x(True, 'stream') != x(False, 'stream')
    assert Run(build_draws(True), Config(horizon=2)).run().read(N.pump.x) == 5  # median mode


# R-A2-18 an opening balance from outside -------------------------------------------------------------------
def build_opening():
    m = Model()
    m.entity('tank', fields=[value('water', 0, 0, 100)], events=[event(
        'receive', params=['amount'], locals=[value('remaining', N.amount, 0, N.amount)],
        flows=[flow('delivery', N.remaining, this.water, request=10)], steps=[until(N.remaining <= 0)])])
    m.setup = [start(N.tank.receive, 20)]
    return m


def test_18_opening():
    c = run(build_opening(), 3).conservation()
    assert c['opening'] == 20 and c['held'] == 20 and c['balanced']
    with pytest.raises(Diagnostic, match='must start empty'):
        run(build_opening(), 3, opening='refuse')


# R-A2-19 move on a readonly stock (open item #1) -----------------------------------------------------------
def build_move():
    m = Model()
    m.entity('a', fields=[value('water', 8, 0, 20, readonly=True)])
    m.entity('b', fields=[value('water', 0, 0, 4, readonly=True)])
    m.entity('op', events=[event('go', steps=[after(1, [__import__('ref').move(3, N.a.water, N.b.water)])])])
    m.setup = [start(N.op.go)]
    return m


def test_19_move_readonly():
    r = run(build_move(), 2)
    assert (r.read(N.a.water), r.read(N.b.water)) == (5, 3)
    with pytest.raises(Diagnostic, match='readonly'):
        run(build_move(), 2, move_readonly='refused')


# R-A2-20 forward references of locals and flows (open item #23) ---------------------------------------------
def build_forward():
    m = Model()
    m.entity('tank', fields=[value('water', 100, 0, 100)], events=[event(
        'job', locals=[calc('pace', N.base * 2), value('base', 3)],
        flows=[flow('out', this.water, SINK, request=formula_of(N.pace))], steps=[after(1, [])])])
    m.setup = [start(N.tank.job)]
    return m


def formula_of(e):
    return __import__('ref').formula(e)


def test_20_local_order():
    assert run(build_forward(), 2).read(N.tank.water) == 94
    with pytest.raises(Diagnostic, match='declared below it'):
        run(build_forward(), 2, local_order='written')


# R-A2-21 the retirement rule (open item #27) ----------------------------------------------------------------
def build_retire():
    m = Model()
    m.entity('plant', fields=[value('out', 0, 0, 100)], events=[event(
        'batch', locals=[value('stock', 20, 0, 100)], flows=[flow('deliver', N.stock, this.out, request=12)],
        steps=[after(1, [])])])
    m.setup = [start(N.plant.batch)]
    return m


def test_21_retirement():
    fails(build_retire(), 2, match='still holds 8')
    c = run(build_retire(), 2, retirement='dispose').conservation()
    assert c['disposed'] == 8 and c['balanced']


# R-A2-22 a result read across stages of one round ----------------------------------------------------------
def build_stale():
    m = Model()
    m.entity('clinic', fields=[value('staff_hours', 100), calc('outreach_minimum', F(3, 10) * this.staff_hours), value('seen', 0)],
             events=[event('cut', steps=[after(1, [set_(this.staff_hours, 80)])]),
                     event('look', steps=[after(1, [set_(this.seen, this.staffing.care)])])],
             solvers=[__import__('test_31_once_in_a_round').staffing()])
    m.setup = [start(N.clinic.cut), start(N.clinic.look)]
    return m


def test_22_stale_result():
    r = run(build_stale(), 2)
    assert r.read(N.clinic.seen) == 70 and r.read(N.clinic.staffing.care) == 56
    fails(build_stale(), 2, match='another stage of this round changed its inputs', stale_result='error')


# R-A2-23 the reference scale of flows of two dimensions ------------------------------------------------------
def build_scale():
    m = Model()
    m.scales = {'L/h': 1, 'W': F(1, 1000)}  # working units L/h and kW: the canonical W is 1/1000 kW
    m.entity('plant', flows=[flow('fill', SOURCE, SINK, dim='L/h'), flow('motor', SOURCE, SINK, dim='W')], solvers=[solver(
        'mix', inputs={'fill': this.fill, 'motor': this.motor}, solve_for=[N.fill.actual_rate, N.motor.actual_rate],
        constraints=[N.fill.actual_rate + N.motor.actual_rate >= 4])])
    return m


def test_23_flow_scale():
    def got(rule):
        r = run(build_scale(), flow_scale=rule)
        return r.read(N.plant.fill.actual_rate), r.read(N.plant.motor.actual_rate)
    assert got('canonical') == (F(4 * 10**6, 10**6 + 1), F(4, 10**6 + 1))
    assert got('working') == (2, 2)
