"""One test for each ruling that prototype A2 proposed (`scratch/rewrite/a2/FINDINGS.md`), on its own
example. Gate G0 settled them all, so each test now asserts the settled rule; where G0 overturned
the proposal (R-A2-06, 07, 13, 14, 20, 22) or changed its numbers (R-A2-04, 23), the test asserts
the decision of G0 and names it."""

from fractions import Fraction as F

import pytest

from tests.reference.errors import Diagnostic, RunFailed
from tests.reference.evaluate import Ev, Scope
from tests.reference.model import (
    SINK,
    SOURCE,
    Config,
    Endpoint,
    Model,
    N,
    add,
    after,
    calc,
    case,
    categorical,
    count,
    delayed,
    elapsed,
    event,
    flow,
    fmax,
    formula,
    inp,
    leg,
    legs,
    lit,
    move,
    priority,
    q,
    set_,
    since,
    solver,
    start,
    switch,
    t,
    this,
    trigger,
    uniform,
    until,
    value,
)
from tests.reference.run import Run, Unavailable
from tests.reference.test_solvers import staffing


def run(m, horizon=0, **config):
    return Run(m, Config(horizon=horizon, **config)).run()


def now(r, e):
    return Ev(r, r.view, Scope()).val(e)


def test_01_stage_order():
    """Stages due together commit by the age of their occurrence: A (older) then B, so the last write
    is B's, although B's stage was scheduled first."""
    m = Model()
    a = event('a', steps=[after(1, []), after(1, [set_(this.last, 'A')])])
    b = event('b', steps=[after(2, [set_(this.last, 'B')])])
    m.entity('board', fields=[value('last', '-')], events=[a, b])
    m.setup = [start(N.board.a), start(N.board.b)]
    assert run(m, 3).read(N.board.last) == 'B'


def test_02_broadcast():
    """Members of a start on a collection start in key order: m2 (rank 1) commits first, m1 last."""
    m = Model()
    m.template(
        'Machine',
        fields=[inp('rank', 0)],
        events=[event('repair', steps=[after(0, [set_(N.board.last, this)])])],
    )
    m.instance('m1', 'Machine', rank=2)
    m.instance('m2', 'Machine', rank=1)
    m.entity('board', fields=[value('last')])
    m.setup = [start(N.Machine.instances.by(N.rank).repair)]
    assert run(m, 1).read(N.board.last).id == 'm1'


def test_03_round_writes():
    """D5: from 20 g, a stage that sets 8 g and a later stage of the same round that adds 4 g: 12 g."""
    m = Model()
    use = event('use', steps=[after(1, [set_(this.beans, 8)])])
    top = event('top', steps=[after(1, [add(this.beans, 4)])])
    m.entity('grinder', fields=[value('beans', 20)], events=[use, top])
    m.setup = [start(N.grinder.use), start(N.grinder.top)]
    assert run(m, 2).read(N.grinder.beans) == 12


def cycle(limit):
    again = trigger(this.n < limit, [start(this.bump)], reset=('when', lit(True)))
    m = Model()
    m.entity(
        'pump',
        fields=[value('n', 0)],
        events=[event('bump', triggers=[again], steps=[after(0, [add(this.n, 1)])])],
    )
    return m


def test_04_refire():
    """A trigger may fire again at the same time after its reset: two firings at 0 h. A cycle stops
    at `max_rounds`, 1,000 rounds at one time by default (D6), and the message names the trigger."""
    assert run(cycle(2), 1).read(N.pump.n) == 2
    with pytest.raises(RunFailed, match='more than 1000 rounds at t = 0 h: the limit max_rounds') as e:
        run(cycle(10**6), 1)
    assert 'pump.bump.when[0]' in str(e.value)


def test_05_setup():
    """Setup is round zero: the first trigger check reads the starting 8 g, before the `after 0 h`
    stage of a setup start sets 12 g."""
    m = Model()
    refill = event('refill', triggers=[trigger(this.low, [start(this.refill)], reset=('when', lit(False)))])
    prepare = event('prepare', steps=[after(0, [set_(this.beans, 12)])])
    m.entity('grinder', fields=[value('beans', 8), calc('low', this.beans <= 10)], events=[refill, prepare])
    m.setup = [start(N.grinder.prepare)]
    assert run(m, 1).times('fire') == [0]


def test_06_no_absent_value():
    """Overturned by D4: there is no `none`. A field declared without a value fails when it is read,
    also through arithmetic in a formula."""
    m = Model()
    m.entity('gauge', fields=[value('reading'), calc('shown', this.reading + 1)])
    r = run(m)
    for expr in (N.gauge.shown, N.gauge.reading <= 3, lit(5) + N.gauge.reading):
        with pytest.raises(RunFailed, match='read before it has a value'):
            r.read(expr)


def test_07_empty_minmax():
    """Overturned by D4: `max` of an empty collection fails; with a scalar beside it, it is that scalar."""
    m = Model()
    m.template('Pump', fields=[value('rate', 1)])
    m.entity('site')
    r = run(m)
    with pytest.raises(RunFailed, match='empty collection'):
        r.read(fmax(N.Pump.instances.rate))
    assert r.read(fmax(0, N.Pump.instances.rate)) == 0


def test_08_elapsed():
    """`elapsed` restarts only on a net change: a stage that writes B and then A leaves it running."""
    m = Model()
    m.entity(
        'valve',
        fields=[value('state', 'A')],
        events=[event('flip', steps=[after(2, [set_(this.state, 'B'), set_(this.state, 'A')])])],
    )
    m.setup = [start(N.valve.flip)]
    assert run(m, 3).read(elapsed(N.valve.state)) == 3


def test_09_delayed_zero():
    """`delayed(x, 0 h)` in a stage reads the committed value, never the stage's own write."""
    m = Model()
    go = event('go', steps=[after(1, [set_(this.x, 5), set_(this.y, delayed(this.x, 0))])])
    m.entity('box', fields=[value('x', 1), value('y', 0)], events=[go])
    m.setup = [start(N.box.go)]
    assert run(m, 2).read(N.box.y) == 1


def test_10_finished():
    """A finished occurrence is a stable record (D7): its arguments, its locals and its formulas, as
    they were at the finish, with done true and active false."""
    m = Model()
    m.entity(
        'tank',
        events=[event('job', params=['amount'], locals=[calc('double', N.amount * 2)], steps=[after(1, [])])],
    )
    m.setup = [start(N.tank.job, 7)]
    r = run(m, 2)
    occ = N.tank.job.occurrences.at(t)
    assert (r.read(occ.amount), r.read(occ.double), r.read(occ.done), r.read(occ.active)) == (
        7,
        14,
        True,
        False,
    )


def test_11_saved_occurrence():
    """A saved reference pins the occurrence: a later start does not change what it names."""
    m = Model()
    parent = event(
        'parent',
        steps=[
            after(1, [start(this.child)]),
            after(0, [set_(this.saved, this.child.occurrences.at(t))]),
            after(1, [start(this.child)]),
        ],
    )
    m.entity('unit', fields=[value('saved')], events=[event('child', steps=[until(lit(False))]), parent])
    m.setup = [start(N.unit.parent)]
    assert run(m, 3).read(N.unit.saved.started) == 1


def test_12_tiers():
    """Under local sharing each endpoint applies its own priority. X serves a (2) before r's leg, Y
    serves r's leg before b; r's legs ask 4 each: r is served in full, b gets 0 and a gets 2."""
    m = Model()
    x_out = Endpoint(capacity=lit(6), allocation=priority(N.site.a, N.site.r.l1))
    y_out = Endpoint(capacity=lit(4), allocation=priority(N.site.r.l2, N.site.b))
    m.entity('x', fields=[value('water', 100, 0, 100, outflow=x_out)])
    m.entity('y', fields=[value('water', 100, 0, 100, outflow=y_out)])
    m.entity(
        'site',
        flows=[
            flow('a', N.x.water, SINK, request=2),
            flow('b', N.y.water, SINK, request=4),
            legs('r', leg('l1', N.x.water, SINK, request=4), leg('l2', N.y.water, SINK, request=4)),
        ],
    )
    r = run(m)
    assert (r.read(N.site.r.served_fraction), r.read(N.site.b.actual_rate), r.read(N.site.a.actual_rate)) == (
        1,
        0,
        2,
    )


def test_13_budget():
    """D6: `max_active` (100,000 by default) is configurable, and its message names the event, the
    oldest waiting occurrence and its gate."""
    m = Model()
    hourly = trigger(t >= 0, [start(this.ticket)], reset=('after', 1))
    m.entity(
        'desk',
        fields=[value('open', False)],
        events=[event('ticket', triggers=[hourly], steps=[until(this.open)])],
    )
    with pytest.raises(
        RunFailed, match=r'3 occurrences of desk.ticket are active at once \(max_active = 3\)'
    ) as e:
        run(m, 10, max_active=3)
    assert 'desk.ticket#1, started at 0 h and waits at `until this.open`' in str(e.value)
    assert run(m, 10).read(count(N.desk.ticket.occurrences)) == 11


def shift(choices=None):
    stage = after(
        1,
        [
            start(this.child),
            set_(this.x, 1),
            switch(
                N.crew.choose(N.crew.forecast),
                case('REPAIR', [set_(this.plan, 'repair')]),
                case('WAIT', [set_(this.plan, 'wait')]),
            ),
        ],
    )
    m = Model()
    m.entity(
        'crew',
        fields=[
            value('forecast', categorical(REPAIR=F(1, 2), WAIT=F(1, 2))),
            value('x', 0),
            value('plan', '-'),
        ],
        events=[event('child', steps=[after(5, [])]), event('shift', steps=[stage])],
    )
    m.setup = [start(N.crew.shift)]
    return run(m, 3, controllers={'crew'}, choices=choices or {})


def test_14_pause():
    """G0: a prompt pauses one atomic stage. Nothing of the stage is visible while the run waits, but
    the queued start is kept; resuming commits the stage once, with one child."""
    r = shift()
    assert r.paused['time'] == 1 and r.paused['queued_starts'] == ['crew.child']
    assert (now(r, N.crew.x), now(r, count(N.crew.child.occurrences))) == (0, 0)
    r.resume('REPAIR')
    assert (r.read(N.crew.plan), r.read(N.crew.x), r.read(count(N.crew.child.occurrences))) == (
        'repair',
        1,
        1,
    )
    assert shift(choices={'crew': 'REPAIR'}).read(count(N.crew.child.occurrences)) == 1


def test_15_asserts():
    """An assertion on state is checked after every round, just after every moment and at each
    contact between moments: 10 L draining at 1 L/h breaks `water >= 5 L` just after 5 h."""
    m = Model()
    m.entity(
        'tank',
        fields=[value('water', 10, 0, 100)],
        flows=[flow('drain', this.water, SINK, request=1)],
        events=[event('refill', steps=[after(7, [set_(this.water, 10)])])],
    )
    m.setup = [start(N.tank.refill)]
    m.check(N.tank.water >= 5, text='tank.water >= 5 L')
    with pytest.raises(RunFailed, match=r'fails just after t = 5 h'):
        run(m, 8)


def test_16_report():
    """A report reads the record after the run: an invalid read shows as unavailable, with the reason,
    and cannot fail the run."""
    m = Model()
    m.entity('grinder', events=[event('refill', steps=[after(1, [])])])
    r = run(m, 2)
    assert r.view.t == 2
    shown = r.report(since(N.grinder.refill), [0])[0]
    assert isinstance(shown, Unavailable) and 'before the first occurrence' in shown.reason


def draws(extra):
    m = Model()
    early = event('early', steps=[after(0, [set_(this.y, this.speeds.draw())], when=this.extra)])
    late = event('late', steps=[after(1, [set_(this.x, this.speeds.draw())])])
    m.entity(
        'pump',
        fields=[inp('extra', extra), value('speeds', uniform(0, 10)), value('x', 0), value('y', 0)],
        events=[early, late],
    )
    m.setup = [start(N.pump.early), start(N.pump.late)]
    return m


def test_17_draws():
    """A draw is keyed by its site and its owner: an extra draw elsewhere does not move it. A median
    run takes the median, 5."""
    sampled = [run(draws(extra), 2, mode='sampled', seed=7).read(N.pump.x) for extra in (True, False)]
    assert sampled[0] == sampled[1]
    assert run(draws(True), 2).read(N.pump.x) == 5


def test_18_opening():
    """What a store holds when it first becomes a store is recorded as an opening balance."""
    m = Model()
    receive = event(
        'receive',
        params=['amount'],
        locals=[
            value('remaining', N.amount, 0, N.amount),
            flow('delivery', N.remaining, this.water, request=10),
        ],
        steps=[until(N.remaining <= 0)],
    )
    m.entity('tank', fields=[value('water', 0, 0, 100)], events=[receive])
    m.setup = [start(N.tank.receive, 20)]
    c = run(m, 3).conservation()
    assert (c['opening'], c['held'], c['balanced']) == (20, 20, True)


def test_19_move_readonly():
    """`move` may debit and credit a `readonly` stock; a direct assignment stays an error."""
    m = Model()
    m.entity('a', fields=[value('water', 8, 0, 20, readonly=True)])
    m.entity('b', fields=[value('water', 0, 0, 4, readonly=True)])
    m.entity(
        'op',
        events=[
            event('go', steps=[after(1, [move(3, N.a.water, N.b.water)])]),
            event('set', steps=[after(1, [set_(N.a.water, 1)])]),
        ],
    )
    m.setup = [start(N.op.go)]
    r = run(m, 2)
    assert (r.read(N.a.water), r.read(N.b.water)) == (5, 3)
    m.setup = [start(N.op.set)]
    with pytest.raises(Diagnostic, match='readonly'):
        run(m, 2)


def test_20_local_order():
    """D14: locals and flows initialize in written order, and a formula may name a later local. The
    formula `pace` names `base`, declared below it; the flow after both drains 6 L in an hour."""
    m = Model()
    job = event(
        'job',
        locals=[
            calc('pace', N.base * 2),
            value('base', 3),
            flow('out', this.water, SINK, request=formula(N.pace)),
        ],
        steps=[after(1, [])],
    )
    m.entity('tank', fields=[value('water', 100, 0, 100)], events=[job])
    m.setup = [start(N.tank.job)]
    assert run(m, 2).read(N.tank.water) == 94


def test_21_retirement():
    """A store of an occurrence must be empty at normal completion: 8 L left fails the run."""
    m = Model()
    batch = event(
        'batch',
        locals=[value('stock', 20, 0, 100), flow('deliver', N.stock, this.out, request=12)],
        steps=[after(1, [])],
    )
    m.entity('plant', fields=[value('out', 0, 0, 100)], events=[batch])
    m.setup = [start(N.plant.batch)]
    with pytest.raises(RunFailed, match='still holds 8'):
        run(m, 2)


def test_22_stale_result():
    """Overturned by D5: a stage that reads the staffing result after another stage of the same round
    changed its inputs fails; it does not get the last settled 70 h with a warning."""
    m = Model()
    m.entity(
        'clinic',
        fields=[
            value('staff_hours', 100),
            calc('outreach_minimum', F(3, 10) * this.staff_hours),
            value('seen', 0),
        ],
        events=[
            event('cut', steps=[after(1, [set_(this.staff_hours, 80)])]),
            event('look', steps=[after(1, [set_(this.seen, this.staffing.care)])]),
        ],
        solvers=[staffing()],
    )
    m.setup = [start(N.clinic.cut), start(N.clinic.look)]
    with pytest.raises(RunFailed, match='read before its solve settles'):
        run(m, 2)


def mixed(unit):
    """Two flows of two dimensions trade off in one distance step: fill * (1 Wh/L) + motor >= 4 W,
    with the motor's rates written in `unit`."""
    m = Model()
    m.entity(
        'plant',
        flows=[
            flow('fill', SOURCE, SINK, request=q(0, 'L/h')),
            flow('motor', SOURCE, SINK, request=q(0, unit)),
        ],
        solvers=[
            solver(
                'mix',
                inputs={'fill': this.fill, 'motor': this.motor},
                solve_for=[N.fill.actual_rate, N.motor.actual_rate],
                constraints=[
                    N.fill.actual_rate * q(1, 'Wh/L') + N.motor.actual_rate
                    >= q(4 if unit == 'W' else F(4, 1000), unit)
                ],
            )
        ],
    )
    r = run(m)
    return r.read(N.plant.fill.actual_rate, unit='L/h'), r.read(N.plant.motor.actual_rate, unit='W')


def test_23_flow_scale():
    """Each rate is divided by one canonical unit of its dimension: (2 L/h, 2 W), whether the model
    writes the motor in W or in kW."""
    assert mixed('W') == mixed('kW') == (2, 2)
