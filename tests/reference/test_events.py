"""Events, triggers and occurrences: the rows of the acceptance table of `spec.md` on time, waiting,
completion, thresholds, history and instantaneous transfers, with the spec's numbers."""

from fractions import Fraction as F

import pytest

from tests.reference.errors import Diagnostic, RunFailed
from tests.reference.evaluate import Ev, Scope
from tests.reference.model import (
    SINK,
    SOURCE,
    Model,
    N,
    add,
    after,
    any_,
    calc,
    count,
    event,
    flow,
    fmax,
    formula,
    if_,
    link,
    lit,
    move,
    q,
    set_,
    since,
    start,
    t,
    this,
    trigger,
    until,
    value,
)
from tests.reference.run import Run, Unavailable

HALF = F(1, 2)


def now(r, e):
    """A value of the live state where a run stopped."""
    return Ev(r, r.view, Scope()).val(e)


def test_grinder_refill():
    """A grinder at 8 g; refill.start(50 g): 58 g after half an hour, and low_on_beans is false."""
    m = Model()
    refill = event('refill', params=['amount'], steps=[after(HALF, [add(this.beans, N.amount)])])
    m.entity(
        'grinder',
        fields=[value('beans', 8), calc('low_on_beans', this.beans <= 10, readonly=True)],
        events=[refill],
    )
    m.setup = [start(N.grinder.refill, 50)]
    r = Run(m, horizon=1).run()
    assert (r.read(N.grinder.beans, 0), r.read(N.grinder.low_on_beans, 0)) == (8, True)
    assert (r.read(N.grinder.beans, HALF), r.read(N.grinder.low_on_beans, HALF)) == (58, False)
    assert r.times('done') == [HALF]


def inspect(safe_at_five):
    weather = [
        after(4, [set_(this.safe, False)]),  # a temporary loss of safety before the due time
        after(HALF, [set_(this.safe, safe_at_five)]),  # t = 4.5
        after(1, [set_(this.safe, True)]),  # t = 5.5: too late, the guard was read at 5
        after(HALF, [set_(this.clearance_received, True)]),  # t = 6
    ]
    steps = [
        after(N.delay, [set_(N.delay, 2)]),
        after(N.delay, [start(this.inspect_equipment)], when=this.safe),
        until(this.clearance_received),
        after(0, [start(this.record_clearance)]),
    ]
    m = Model()
    m.entity(
        'site',
        fields=[value('safe', True), value('clearance_received', False)],
        events=[
            event('inspect', params=['delay'], steps=steps),
            event('inspect_equipment'),
            event('record_clearance'),
            event('weather', steps=weather),
        ],
    )
    m.setup = [start(N.site.inspect, 3), start(N.site.weather)]
    return Run(m, horizon=8).run()


def test_inspect_stages_at_three_and_five():
    """inspect.start(3 h): its stages run at hours 3 and 5, then the gate releases at 6."""
    r = inspect(True)
    assert [(e[1], e[3]) for e in r.trace if e[0] == 'stage' and e[2] == 'site.inspect#0'] == [
        (3, 0),
        (5, 1),
        (6, 3),
    ]
    assert r.times('start', 'site.inspect_equipment#0') == [5]
    assert r.times('start', 'site.record_clearance#0') == [6]
    assert r.times('done', 'site.inspect#0') == [6]


def test_inspect_guard_is_read_once():
    """The guard is false at 5 h: the body is skipped though safety returns at 5.5 h, and the
    occurrence still completes."""
    r = inspect(False)
    assert r.times('start', 'site.inspect_equipment#0') == []
    assert r.times('done', 'site.inspect#0') == [6]
    assert r.read(N.site.inspect.occurrences.at(t).done, 8) is True


def batch(dispose):
    """20 L enters a batch in the first hour and 12 L leaves in the second."""
    steps = [
        after(1, [set_(N.fill, 0), set_(N.out, 12)]),
        after(1, [set_(N.out, 0), set_(N.dump, 8 if dispose else 0)]),
    ]
    if dispose:
        steps.append(until(N.stock <= 0))
    locals_ = [
        value('stock', 0, 0, 100),
        value('fill', 20),
        value('out', 0),
        value('dump', 0),
        flow('arrive', SOURCE, N.stock, request=formula(N.fill)),
        flow('deliver', N.stock, SINK, request=formula(N.out)),
        flow('waste', N.stock, SINK, request=formula(N.dump)),
    ]
    m = Model()
    m.entity('plant', events=[event('batch', locals=locals_, steps=steps)])
    m.setup = [start(N.plant.batch)]
    return Run(m, horizon=5)


def test_retirement_names_what_is_left():
    """An occurrence with 20 L in its batch and 12 L delivered tries to finish: the run fails and
    names the 8 L."""
    with pytest.raises(RunFailed, match=r'plant\.batch#0\.stock still holds 8') as e:
        batch(dispose=False).run()
    assert 't = 2 h' in str(e.value)


def test_disposal_through_a_declared_flow():
    """Sending the rest to SINK through a declared flow lets the occurrence finish; the account
    records the 8 L as external outflow."""
    r = batch(dispose=True).run()
    assert r.times('done') == [3]
    c = r.conservation()
    assert (c['from_source'], c['to_sink'], c['held']) == (20, 20, 0) and c['balanced']


def ramp(rate, change):
    receive = event(
        'receive',
        params=['amount', 'starting_rate', 'rate_change'],
        locals=[
            value('remaining', N.amount, 0, N.amount),
            value('started_at', t, readonly=True),
            flow(
                'delivery',
                N.remaining,
                this.water,
                request=formula(fmax(0, N.starting_rate + N.rate_change * (t - N.started_at))),
            ),
        ],
        steps=[until(N.remaining <= 0)],
    )
    m = Model()
    m.entity('tank', fields=[value('water', 0, 0, 100)], events=[receive])
    m.setup = [start(N.tank.receive, 20, rate, change)]
    return m


DONE = count(N.tank.receive.occurrences.done)


def test_a_rising_rate_at_one_hour():
    """The 20 L delivery with a rising rate, at an hour-one horizon: 7.5 L delivered, 12.5 L in
    transit, one start and no completion."""
    r = Run(ramp(5, 5), horizon=1).run()
    assert r.view.t == 1
    assert r.read(N.tank.water) == F(15, 2)
    assert r.read(N.tank.receive.occurrences.at(t).remaining) == F(25, 2)
    assert (r.read(count(N.tank.receive.occurrences)), r.read(DONE)) == (1, 0)
    assert r.conservation()['balanced']


def test_a_rising_rate_at_two_hours():
    """At hour two: 20 L and one completion; the batch arrived from outside as an opening balance."""
    r = Run(ramp(5, 5), horizon=2).run()
    assert (r.read(N.tank.water), r.read(DONE), r.times('done')) == (20, 1, [2])
    c = r.conservation()
    assert c['opening'] == 20 and c['balanced']


def test_a_falling_rate_leaves_the_gate_waiting():
    """From 5 L/h falling by 2 L/h each hour: 6.25 L by 2.5 h, and the gate waits."""
    r = Run(ramp(5, -2), horizon=10).run()
    assert r.read(N.tank.water, F(5, 2)) == r.read(N.tank.water, 10) == F(25, 4)
    assert r.read(DONE, 10) == 0 and r.read(N.tank.receive.occurrences.at(t).active, 10) is True


def drained(water, request, events=(), setup=()):
    """A tank of `water` litres in [0,] with a member's flow to SINK that requests `request`."""
    m = Model()
    m.entity(
        'tank',
        fields=[value('water', water, 0)],
        flows=[flow('drain', this.water, SINK, request=request)],
        events=list(events),
    )
    m.setup = list(setup)
    return Run(m, horizon=5).run()


def test_a_rate_that_rises_from_zero_moves_its_store():
    """D3: `request = formula(t * 1 L/h/h)` on a member's flow is zero at 0 h and then rises, and the
    flow follows it: a tank of 100 L holds 100 - t^2/2 litres, 92 L at 4 h, while the rate is t,
    4 L/h. An empty tank cannot start that flow: it stays empty, at rate zero."""
    r = drained(100, formula(t * q(1, 'L/h/h')))
    assert [r.read(N.tank.water, at) for at in (0, 2, 4)] == [100, 98, 92]
    assert r.read(N.tank.drain.actual_rate, 4) == 4
    r = drained(0, formula(t * q(1, 'L/h/h')))
    assert (r.read(N.tank.water), r.read(N.tank.drain.actual_rate)) == (0, 0)


def test_a_rate_that_reads_since_rises_from_the_start_of_its_event():
    """The request `since(e) * 1 L/h/h`, guarded by `count(e.occurrences) > 0`, is zero until e
    starts at 1 h and then rises: the tank of 100 L holds 100 - (t - 1)^2/2 litres after 1 h, 98 L
    at 3 h and 92 L at 5 h."""
    began = count(this.e.occurrences) > 0
    request = formula(if_(began, since(this.e) * q(1, 'L/h/h'), q(0, 'L/h')))
    plan = event('plan', steps=[after(1, [start(this.e)])])
    r = drained(100, request, events=[event('e'), plan], setup=[start(N.tank.plan)])
    assert [r.read(N.tank.water, at) for at in (1, 3, 5)] == [100, 98, 92]


def alarm(condition):
    once = trigger(condition(this.water), [start(this.alarm)], reset=('when', lit(False)))
    m = Model()
    m.entity(
        'tank',
        fields=[value('water', 11, 0, 100), value('alarms', 0)],
        flows=[flow('drain', this.water, SINK, request=1)],
        events=[event('alarm', triggers=[once], steps=[after(0, [add(this.alarms, 1)])])],
    )
    return Run(m, horizon=5)


def test_threshold_fires_at_first_contact():
    """A tank at 11 L draining 1 L/h; `when this.water <= 10 L` fires at hour 1."""
    r = alarm(lambda w: w <= 10).run()
    assert r.times('fire') == [1]
    assert r.read(this.water, 1, owner='tank') == 10


def test_strict_continuous_threshold_is_refused():
    with pytest.raises(Diagnostic, match='strict threshold'):
        alarm(lambda w: w < 10).run()


def test_a_joining_flow_moves_the_crossing():
    """A tank at 10 L filling 1 L/h; an occurrence drains 2 L/h more from hour 2 to hour 4; the
    trigger on `>= 16 L` fires at hour 10 (12 L at 2 h, 10 L at 4 h), not at hour 6."""
    drain = event('drain', locals=[flow('out', this.water, SINK, request=2)], steps=[after(2, [])])
    alarm = event(
        'alarm', triggers=[trigger(this.water >= 16, [start(this.alarm)], reset=('when', lit(False)))]
    )
    m = Model()
    m.entity(
        'tank',
        fields=[value('water', 10, 0, 100)],
        flows=[flow('fill', SOURCE, this.water, request=1)],
        events=[drain, alarm, event('plan', steps=[after(2, [start(this.drain)])])],
    )
    m.setup = [start(N.tank.plan)]
    r = Run(m, horizon=12).run()
    assert r.times('fire') == [10]
    assert (r.read(N.tank.water, 6), r.read(N.tank.water, 10)) == (12, 16)


def grinder(manual):
    refill = event(
        'refill',
        params=['amount'],
        locals=[value('status', 'WEIGHING')],
        triggers=[trigger(this.low_on_beans, [start(this.refill, 50)], reset=('when', this.beans >= 30))],
        steps=[after(HALF, [add(this.beans, N.amount), set_(N.status, 'ADDED')])],
    )
    m = Model()
    m.entity('grinder', fields=[value('beans', 8), calc('low_on_beans', this.beans <= 10)], events=[refill])
    m.setup = [start(N.grinder.refill, 50)] if manual else []
    return Run(m, horizon=2).run()


def test_trigger_and_manual_start():
    """A grinder at 8 g; its trigger and a manual start of 50 g: 108 g. The manual start neither
    consumes nor resets the trigger."""
    r = grinder(manual=True)
    assert r.read(N.grinder.beans, 1) == 108
    assert r.read(count(N.grinder.refill.occurrences), 1) == 2
    assert r.times('fire') == [0]
    assert r.read(N.grinder.refill.occurrences.at(t).status, 1) == 'ADDED'
    assert grinder(manual=False).read(N.grinder.beans, 1) == 58


def test_clock_with_a_reset_after():
    """`when t >= 3 h` with `reset after 3 h`: hours 3, 6 and 9."""
    inspect = event(
        'inspect',
        triggers=[trigger(t >= 3, [start(this.inspect)], reset=('after', 3))],
        steps=[after(0, [add(this.inspections, 1)])],
    )
    m = Model()
    m.entity('pump', fields=[value('inspections', 0)], events=[inspect])
    r = Run(m, horizon=10).run()
    assert r.times('fire') == [3, 6, 9]
    assert r.read(N.pump.inspections, 10) == 3


def test_cooldown_is_captured_at_firing():
    """An alarm that fires at 0 h, is off from 1 h to 4 h and fires at 4 h: next eligible at 7 h."""
    alarm = event('alarm', triggers=[trigger(this.alarm_on, [start(this.alarm)], reset=('after', 3))])
    weather = event(
        'weather', steps=[after(1, [set_(this.alarm_on, False)]), after(3, [set_(this.alarm_on, True)])]
    )
    m = Model()
    m.entity('pump', fields=[value('alarm_on', True)], events=[alarm, weather])
    m.setup = [start(N.pump.weather)]
    assert Run(m, horizon=11).run().times('fire') == [0, 4, 7, 10]


@pytest.fixture(scope='module')
def history():
    refill = event(
        'refill',
        params=['amount'],
        locals=[value('status', 'WEIGHING')],
        steps=[after(HALF, [add(this.beans, N.amount), set_(N.status, 'ADDED')])],
    )
    plan = event(
        'plan',
        steps=[
            after(1, [start(this.refill, 50)]),
            after(1, [start(this.refill, 10), start(this.refill, 20)]),
            after(F(1, 4), []),
        ],
    )
    m = Model()
    m.entity('grinder', fields=[value('beans', 8)], events=[refill, plan])
    m.setup = [start(N.grinder.plan)]
    return Run(m, horizon=4).run()


OCC = N.grinder.refill.occurrences


def test_history_table(history):
    """Each expression of the history table of `spec.md`."""
    r = history
    assert r.read(N.grinder.beans, 4) == 88
    assert (r.read(count(OCC), HALF), r.read(count(OCC), F(5, 4))) == (0, 1)
    assert (r.read(count(OCC.done), F(5, 4)), r.read(count(OCC.done), F(3, 2))) == (0, 1)
    assert (r.read(any_(OCC.active), F(5, 4)), r.read(any_(OCC.active), F(3, 2))) == (True, False)
    assert (r.read(OCC.at(t).status, F(5, 4)), r.read(OCC.at(t).status, F(3, 2))) == ('WEIGHING', 'ADDED')
    assert r.read(since(N.grinder.refill), F(3, 2)) == HALF


def test_two_starts_at_one_time(history):
    """Two simultaneous starts both count; a lookup at t returns the later-created one."""
    assert history.read(count(OCC), 2) == 3
    assert (history.read(OCC.at(t).amount, 2), history.read(OCC.at(t).started, 2)) == (20, 2)


def test_history_reads_before_the_first_start(history):
    with pytest.raises(RunFailed, match='before the first occurrence'):
        history.read(since(N.grinder.refill), HALF)
    with pytest.raises(RunFailed, match='empty'):
        history.read(OCC.at(t).status, HALF)
    assert history.read((count(OCC) > 0) & (since(N.grinder.refill) >= 3), HALF) is False  # short-circuit
    assert isinstance(history.report(since(N.grinder.refill), [HALF])[0], Unavailable)


def reserve(at_outset):
    if at_outset:  # move at the outset, and keep the request at zero during setup
        locals_ = [value('batch', 0, 0, N.amount), flow('delivery', N.batch, this.customer.water, request=0)]
        steps = [
            after(0, [move(N.amount, this.supply, N.batch)]),
            after(N.setup, [set_(N.delivery.request, N.target_rate)]),
            until(N.batch <= 0),
        ]
        params, args = ['amount', 'target_rate', 'setup'], (10, 5, 1)
    else:
        locals_ = [
            value('batch', 0, 0, N.amount),
            flow('delivery', N.batch, this.customer.water, request=formula(this.delivery_request)),
        ]
        steps = [after(N.setup, [move(N.amount, this.supply, N.batch)]), until(N.batch <= 0)]
        params, args = ['amount', 'setup'], (10, 1)
    m = Model()
    m.entity('home', fields=[value('water', 0, 0, 100)])
    m.entity(
        'depot',
        fields=[value('supply', 12, 0, 100), value('delivery_request', 5), link('customer', 'home')],
        flows=[flow('other', this.supply, SINK, request=1)],
        events=[event('deliver', params=params, locals=locals_, steps=steps)],
    )
    m.setup = [start(N.depot.deliver, *args)]
    return Run(m, horizon=5).run()


def test_reserving_after_setup():
    """The move reserves 10 L when setup ends at 1 h; the batch then drains at 5 L/h into the home."""
    r = reserve(at_outset=False)
    assert r.read(N.depot.supply, 1) == 1  # 12, less 1 h of the other consumer, less the 10 reserved
    assert (r.read(N.home.water, 2), r.read(N.home.water, 5)) == (5, 10)
    assert r.times('done') == [3] and r.conservation()['balanced']


def test_reserving_at_the_outset():
    r = reserve(at_outset=True)
    assert (r.read(N.depot.supply, 0), r.read(N.home.water, 1), r.read(N.home.water, 2)) == (2, 0, 5)
    assert r.times('done') == [3]
    assert r.read(N.depot.supply, 5) == 0  # the other consumer drained what was left, by 2 h
    assert r.conservation()['balanced']


def moving(amount):
    m = Model()
    m.entity('a', fields=[value('water', 8, 0, 20, readonly=True)])
    m.entity('b', fields=[value('water', 0, 0, 4, readonly=True)])
    m.entity('op', events=[event('go', steps=[after(1, [move(amount, N.a.water, N.b.water)])])])
    m.setup = [start(N.op.go)]
    return Run(m, horizon=2)


def test_move_between_readonly_stocks():
    """`move` 3 L from a readonly stock of 8 L into an empty readonly stock capped at 4 L: 5 L and 3 L."""
    r = moving(3).run()
    assert (r.read(N.a.water, 2), r.read(N.b.water, 2)) == (5, 3)
    assert [e[4] for e in r.ledger if e[0] == 'move'] == [3]
    assert r.conservation()['balanced']


def test_a_move_that_breaks_a_bound_moves_nothing():
    """A move of 5 L fails the destination bound and leaves 8 L and 0 L."""
    r = moving(5)
    with pytest.raises(RunFailed, match='would hold 5'):
        r.run()
    assert (now(r, N.a.water), now(r, N.b.water)) == (8, 0)


def test_a_child_is_counted_after_the_stage_commits():
    """`count(child.occurrences)` reads 0 for the rest of the stage that starts the child, and 1 in
    the parent's next delay (1 * 2 h after t = 1 h)."""
    parent = event(
        'parent',
        steps=[
            after(1, [start(this.child), set_(this.seen, count(this.child.occurrences))]),
            after(count(this.child.occurrences) * 2, []),
        ],
    )
    m = Model()
    m.entity('unit', fields=[value('seen', -1)], events=[parent, event('child', steps=[after(5, [])])])
    m.setup = [start(N.unit.parent)]
    r = Run(m, horizon=10).run()
    assert r.read(N.unit.seen, 1) == 0
    assert r.times('done', 'unit.parent#0') == [3]
