"""Breakpoints, checkpoints and resume (docs/design/decisions.md, change 15; `timeline/checkpoints.py`).

A breakpoint at a stage or a statement stops a run with a checkpoint, and the run resumed from it
preserves draws and decision order. The recorded values agree closely. Each
case runs three ways: with no breakpoint; stopped and resumed in place in one process, at each stop;
and each checkpoint saved, loaded and resumed in a fresh process (a subprocess under another hash
seed, which loads the program from its artifact, `napkin.program.artifact`, and runs no code of
this module), which must give the next checkpoint of the run in one process, or its final record,
with the same decisions and values within tolerance.

The cases: a continuously changing value near a trigger threshold, on the continuous engine and on the
sparse integrator (a tank that drains at 2 sqrt(water / 1 L) L/h from 100 L holds (10 - t)^2 L, so it
crosses 50 L at 10 - sqrt(50) h, between breakpoints at 2.9289 h and 2.929 h); a stop inside a stage
that has drawn, queued a child and written, twice in one stage; a declared solver between two solves,
on lines and on a moving problem; and the family and the lines. The expected values are worked by
hand from these rules; none comes from a run of the engine.
"""

from __future__ import annotations

import hashlib
import math
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import NamedTuple

import pytest

from napkin.engine.timeline import Plan, Run, paused, read, resume, run
from napkin.engine.timeline.plan import COMPONENT, DECLARED, FAMILY, LINES, SPARSE
from napkin.program.artifact import Artifact
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    categorical,
    constraint,
    draw,
    endpoint,
    event,
    flow,
    fmax,
    formula,
    given,
    local,
    minimize,
    named,
    q,
    reset_when,
    solve_for,
    solver,
    sqrt,
    start,
    switch,
    t,
    this,
    uniform,
    value,
    when,
)
from napkin.program.build import case as on
from napkin.program.checkpoint import (
    Breakpoint,
    Checkpoint,
    CheckpointError,
    State,
    decode,
    dumps,
    encode,
    loads,
)
from napkin.program.config import SAMPLED, Configuration, Request
from tests.engine.resume_parity import assert_resume_parity, assert_trace_prefix
from tests.program.examples import DISPATCH, DISPATCH_SWITCH, EXAMPLES, pump_dispatch

ROOT = Path(__file__).resolve().parents[2]
UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


class Case(NamedTuple):
    program: object
    configuration: Configuration
    breakpoints: tuple
    ways: frozenset  # the ways of running of the sets at the horizon


def ticks(*times):
    """An event whose stages come due at `times` (h), each adding one to `ticks`."""
    steps, at = [], 0
    for time in times:
        steps.append(after(q(time - at, 'h'), add(this.ticks, 1)))
        at = time
    return event('tick', *steps)


def stages(event_, count):
    """Breakpoints at each of the first `count` stages of an event (`tank.tick`)."""
    return tuple(Breakpoint(f'{event_}.step[{k}]') for k in range(count))


def alarm(test):
    """An event that a trigger on `test` starts once, and that adds one to `alarms`."""
    return event(
        'alarm', when(test, start(this.alarm), reset=reset_when(False)), after(q(0, 'h'), add(this.alarms, 1))
    )


def _draining(sparse):
    b = Builder(UNITS)
    outflow = endpoint(capacity=q(50, 'L/h')) if sparse else None
    b.entity(
        'tank',
        value('water', 'L', 100, lower=0, outflow=outflow),
        value('ticks', '', 0),
        value('alarms', '', 0),
        flow('drain', this.water, SINK, request=formula(sqrt(this.water / q(1, 'L')) * q(2, 'L/h'))),
        ticks(1, 2.9289, 2.92893, 2.929, 4),
        alarm(this.water <= q(50, 'L')),
    )
    b.setup(start(named('tank').tick))
    return Case(
        b.finish(),
        Configuration(Request(5)),
        stages('tank.tick', 5),
        frozenset({SPARSE if sparse else COMPONENT}),
    )


def draining():
    """The tank of the module on the continuous engine: one flow out of one store."""
    return _draining(False)


def draining_sparse():
    """The same tank with an outflow capacity (50 L/h, which never binds): the sparse integrator."""
    return _draining(True)


def family():
    """A tank of 10 L that drains at 2 L/h: 3 L at 3.5 h, when the alarm starts, empty at 5 h."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        value('ticks', '', 0),
        value('alarms', '', 0),
        flow('drain', this.water, SINK, request=q(2, 'L/h')),
        ticks(1, 2, 3, 3.5, 4, 6),
        alarm(this.water <= q(3, 'L')),
    )
    b.setup(start(named('tank').tick))
    return Case(b.finish(), Configuration(Request(7)), stages('tank.tick', 6), frozenset({FAMILY}))


def lines():
    """A tank of at most 10 L that fills at 3 L/h and gives 1 L/h: 6 L at 3 h, when the alarm starts,
    full at 5 h, and from then it passes the 3 L/h that it takes on (a request is soft, D15)."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 0, lower=0, upper=10),
        value('ticks', '', 0),
        value('alarms', '', 0),
        flow('fill', SOURCE, this.water, request=q(3, 'L/h')),
        flow('use', this.water, SINK, request=q(1, 'L/h')),
        ticks(1, 2, 3, 4, 5, 6),
        alarm(this.water >= q(6, 'L')),
    )
    b.setup(start(named('tank').tick))
    return Case(b.finish(), Configuration(Request(7)), stages('tank.tick', 6), frozenset({LINES}))


def ordering():
    """At 1 h a stage draws a demand from uniform(1 L, 3 L), queues a child, counts an order and notes
    the demand; the child adds one to the note at 2 h. Breakpoints after the draw and before the note."""
    b = Builder(UNITS)
    b.entity(
        'depot',
        value('demand', 'L', 0),
        value('orders', '', 0),
        value('noted', '', 0),
        event('child', after(q(1, 'h'), add(this.noted, 1))),
        event(
            'order',
            after(
                q(1, 'h'),
                assign(this.demand, draw(uniform(1, 3, 'L'))),
                start(this.child),
                add(this.orders, 1),
                assign(this.noted, this.demand / q(1, 'L')),
            ),
        ),
    )
    b.setup(start(named('depot').order))
    breakpoints = (Breakpoint('depot.order.step[0].do[1]'), Breakpoint('depot.order.step[0].do[3]'))
    configuration = Configuration(Request(3), mode=SAMPLED, seed=7)
    return Case(b.finish(), configuration, breakpoints, frozenset())


def staffing():
    """The example `two_writes_one_solve`: solves at 0 h, and at 1 h in two rounds. Breakpoints at the
    second write of 1 h, before the first solve there, and at the stage of the second round."""
    example = EXAMPLES['two_writes_one_solve']()
    breakpoints = (Breakpoint('office.trim.step[0]'), Breakpoint('office.restore.step[0]'))
    return Case(example.program, example.configuration, breakpoints, frozenset({DECLARED}))


def pumping():
    """A provider's solver feeds a tank of 10 L that gives 6 L/h to a clinic, from a pump of at most
    4 L/h that it minimizes: the tank gives its 10 L alone until it empties at 5/3 h, then the pump
    fills 4 L/h, which the clinic takes. The ticks at 0.5 h and 1.5 h write nothing that the solver
    reads, so its set goes on across them."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 10, lower=0, upper=20),
        value('ticks', '', 0),
        ticks(0.5, 1.5),
    )
    pump = b.entity('pump', flow('fill', SOURCE, tank.water, capacity=q(4, 'L/h')))
    clinic = b.entity('clinic', flow('delivery', tank.water, SINK, request=q(6, 'L/h')))
    zero = q(0, 'L/h')
    b.entity(
        'provider',
        solver(
            'supply',
            given('fill', pump.fill),
            given('use', clinic.delivery),
            solve_for(local.fill.actual_rate),
            solve_for(local.use.actual_rate),
            minimize(fmax(zero, local.use.request - local.use.actual_rate)),
            minimize(local.fill.actual_rate),
        ),
    )
    b.setup(start(named('tank').tick))
    return Case(b.finish(), Configuration(Request(2)), stages('tank.tick', 2), frozenset({DECLARED}))


def tapering():
    """Two tanks fill toward 10 L at their headroom per hour, at most 6 L/h each, under one limit of
    8 L/h that a solver shares; the first stops at 5 L, at 1.25 h (`test_solvers.py`)."""
    b = Builder(UNITS)
    tanks = []
    for k in range(2):
        tanks.append(
            b.entity(
                f'tank{k}',
                value('water', 'L', 0, lower=0, upper=5 if k == 0 else None),
                flow(
                    'fill',
                    SOURCE,
                    this.water,
                    request=formula((q(10, 'L') - this.water) / q(1, 'h')),
                    capacity=q(6, 'L/h'),
                ),
            )
        )
    b.entity('clock', value('ticks', '', 0), ticks(0.5, 1.3))
    rates = [getattr(local, f'f{k}').actual_rate for k in range(2)]
    b.entity(
        'provider',
        solver(
            'share',
            *[given(f'f{k}', tank.fill) for k, tank in enumerate(tanks)],
            *[solve_for(rate) for rate in rates],
            constraint(rates[0] + rates[1] <= q(8, 'L/h')),
        ),
    )
    b.setup(start(named('clock').tick))
    return Case(b.finish(), Configuration(Request(1.5)), stages('clock.tick', 2), frozenset({DECLARED}))


def dispatch(spares=1):
    """The acceptance example of change 15 (`examples.pump_dispatch`): a depot's request draws the
    dispatcher's forecast, which always waits, into its field `order` and switches on it; sending
    needs a spare. A breakpoint before the switch."""
    breakpoints = (Breakpoint(DISPATCH_SWITCH, DISPATCH),)
    return Case(pump_dispatch(spares), Configuration(Request(1)), breakpoints, frozenset())


def dispatch_no_spare():
    """The acceptance example with no spare."""
    return dispatch(0)


def emptying():
    """A tank of 1 L that drains at 1 L/h and its water an hour, a component: 2 e^-t - 1 L, empty at
    ln 2 h, when a trigger starts a check. Its first stage reads the drain there, 0 L/h, so the
    component finds the bound that its tank rests on; the run stops before the second, which reads
    it again, and goes on to 2 h with the tank empty."""
    b = Builder(UNITS)
    rate = formula(q(1, 'L/h') + this.water / q(1, 'h'))
    b.entity(
        'tank',
        value('water', 'L', 1, lower=0),
        value('seen', 'L/h', -1),
        value('late', 'L/h', -1),
        value('at', 'h', -1),
        flow('drain', this.water, SINK, request=rate, capacity=rate),
        event(
            'check',
            when(this.water <= q(0, 'L'), start(this.check), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.seen, this.drain.actual_rate), assign(this.at, t)),
            after(q(0, 'h'), assign(this.late, this.drain.actual_rate)),
        ),
    )
    breakpoints = (Breakpoint('tank.check.step[1]'),)
    return Case(b.finish(), Configuration(Request(2)), breakpoints, frozenset({COMPONENT}))


SCENARIOS = {
    case.__name__: case
    for case in (
        draining,
        draining_sparse,
        emptying,
        family,
        lines,
        ordering,
        staffing,
        pumping,
        tapering,
        dispatch,
        dispatch_no_spare,
    )
}

# A fresh process: it loads a program from its artifact and resumes each checkpoint that it is given.
FRESH = """
import sys
from napkin.engine.timeline import resume
from napkin.program.artifact import load
from napkin.program.checkpoint import encode, loads

program = load(sys.argv[1]).program
for path in sys.argv[2:]:
    with open(path, 'rb') as file:
        print(encode(resume(program, loads(file.read()))))
"""


def in_one_process(case):
    """Each checkpoint of a run stopped and resumed in place, and its final record."""
    made = Run(Plan.of(case.program, case.configuration), case.breakpoints)
    found, stops = made.run(), []
    while isinstance(found, Checkpoint):
        stops.append(found)
        found = made.resume()
    return stops, found, made


def in_a_fresh_process(program, stops, folder):
    """What a fresh process gives for each checkpoint of a run of `program`, which it loads from its
    artifact: the next checkpoint, or the final record."""
    Artifact(program).save(folder / 'program')
    paths = [str(folder / 'program')]
    for k, checkpoint in enumerate(stops):
        path = folder / f'{k}.checkpoint'
        path.write_bytes(dumps(checkpoint))
        paths.append(str(path))
    environment = {**os.environ, 'PYTHONHASHSEED': '4321', 'NAPKIN_STORE': 'off'}
    done = subprocess.run(
        [sys.executable, '-c', FRESH, *paths],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return [decode(line) for line in done.stdout.splitlines()]


@pytest.mark.parametrize('name', sorted(SCENARIOS))
def test_a_resumed_run_is_the_run_straight_through_three_ways(name, tmp_path):
    case = SCENARIOS[name]()
    straight = run(case.program, case.configuration)
    assert straight.failure is None and paused(straight) is None
    stops, final, made = in_one_process(case)
    assert stops
    assert {connected.way for connected, _ in made.ways.sets.values()} == case.ways
    assert_resume_parity(case.program, case.configuration, straight, final)
    for checkpoint in stops:
        # The record so far is the run's to the stop, with the entry of the stop at its end.
        assert_trace_prefix(case.program, case.configuration, straight, checkpoint.record)
        assert paused(checkpoint.record).detail('hit') == checkpoint.stop.hit
        assert loads(dumps(checkpoint)) == checkpoint
    fresh_results = in_a_fresh_process(case.program, stops, tmp_path)
    for expected, actual in zip([*stops[1:], final], fresh_results, strict=True):
        assert_resume_parity(case.program, case.configuration, expected, actual)


def bounds_of(made):
    """The state of the bounds of each component of a run: whether it has found the bounds that its
    state rests on, and those bounds, and the faces of its stocks (`ComponentWay`)."""
    found = []
    for _, way in made.ways.sets.values():
        state = getattr(getattr(way, 'component', None), 'state', None)
        if state is not None:
            found.append(
                (
                    way.bounded,
                    frozenset(state.active_bounds),
                    frozenset(state.zero_faces),
                    frozenset(state.right_faces),
                )
            )
    return found


def test_a_component_that_rests_on_its_bound_at_a_stop_is_restored_on_it(tmp_path):
    """The restored run holds the same active bounds as the live run at the stop. The tank of `emptying` rests on its bound at the stop at ln 2 h, which the
    component found when the first stage read the drain: restored in this process from the
    checkpoint's bytes, it holds that bound, and finds none again (`ComponentWay._settle`). The
    stages read 0 L/h at ln 2 h, and the run is the run straight through, three ways."""
    case = emptying()
    made = Run(Plan.of(case.program, case.configuration), case.breakpoints)
    stop = made.run()
    assert isinstance(stop, Checkpoint) and stop.stop.t == pytest.approx(math.log(2), abs=1e-9)
    remaining = made.stock_balance('tank.water', stop.stop.t)
    assert 0 <= remaining <= made.comparison_band('tank.water', float(remaining), 0)
    held = bounds_of(made)
    assert held == [(True, frozenset({(0, 'min')}), frozenset(), frozenset())], held
    again = Run.restored(Plan.of(case.program, case.configuration), loads(dumps(stop)))
    assert bounds_of(again) == held
    straight = run(case.program, case.configuration)
    (fresh,) = in_a_fresh_process(case.program, [stop], tmp_path)
    for final in (made.resume(), again.resume(), fresh):
        assert_resume_parity(case.program, case.configuration, straight, final)
    found = read(straight, case.program, ['tank.seen', 'tank.late', 'tank.at', 'tank.water'], [2])
    assert [reading.values[0] for reading in found] == [
        0,
        0,
        pytest.approx(math.log(2), abs=1e-9),
        float(remaining),
    ]
    assert made.stock_balance('tank.water', 2) == again.stock_balance('tank.water', 2) == remaining
    if remaining:
        (decision,) = [entry for entry in straight.entries('settle') if entry.detail('placements')]
        assert decision.detail('placements') == (('tank.water', float(remaining), 0.0),)
        assert 'tank.drain.capacity' in decision.detail('reason')


def starts(record, part):
    return [entry.t for entry in record.entries('start', part)]


@pytest.mark.parametrize('name', ['draining', 'draining_sparse'])
def test_a_value_on_a_curve_crosses_its_threshold_at_the_same_time_after_a_stop_just_before(name):
    """The alarm starts at 10 - sqrt(50) h, between the stops at 2.92893 h and 2.929 h, in the run
    straight through and in the run that stopped at each tick."""
    case = SCENARIOS[name]()
    straight = run(case.program, case.configuration)
    stops, final, _ = in_one_process(case)
    crossing = 10 - math.sqrt(50)
    (at,) = starts(straight, 'tank.alarm')
    assert at == pytest.approx(crossing, abs=1e-6)
    assert [stop.stop.t for stop in stops] == pytest.approx([1, 2.9289, 2.92893, 2.929, 4])
    assert stops[2].stop.t < at < stops[3].stop.t
    assert starts(final, 'tank.alarm') == pytest.approx([at], abs=case.configuration.numerics.crossing, rel=0)
    (water,) = read(final, case.program, ['tank.water'], [1, 2.9289, 4, 5])
    assert water.values == pytest.approx([81, (10 - 2.9289) ** 2, 36, 25], rel=1e-6)
    assert stops[1].state.value('tank.water') == pytest.approx((10 - 2.9289) ** 2, rel=1e-6)


def test_family_and_lines_cross_their_thresholds_on_their_lines():
    """The family's tank holds 3 L at 3.5 h, the lines' tank 6 L at 3 h; each alarm starts there."""
    for name, at, store in (('family', 3.5, 3), ('lines', 3, 6)):
        stops, final, _ = in_one_process(SCENARIOS[name]())
        assert starts(final, 'tank.alarm') == [pytest.approx(at, abs=1e-12)]
        found = next(stop for stop in stops if stop.stop.t == at)
        assert found.state.value('tank.water') == pytest.approx(store, abs=1e-12)
    stops, final, _ = in_one_process(lines())
    (use,) = read(final, lines().program, ['tank.use.actual_rate'], [4, 6])
    assert use.values == pytest.approx([1, 3])


def test_a_stage_that_stopped_after_a_draw_a_start_and_a_write_commits_once():
    """The demand is 1 + 2u L for u the uniform number of the seed, the site and the occurrence (the
    first 64 bits of SHA-256, `chance.py`): drawn once, traced once; one child, one order."""
    case = ordering()
    stops, final, _ = in_one_process(case)
    assert [(stop.stop.at, stop.stop.next) for stop in stops] == [
        ('depot.order.step[0].do[1]', 'depot.order.step[0]'),
        ('depot.order.step[0].do[3]', 'depot.order.step[0]'),
    ]
    # Nothing of the stage is visible at its stops: no order, no child, no note.
    assert all(stop.state.value('depot.orders') == 0 for stop in stops)
    assert [occurrence.id for occurrence in stops[1].state.occurrences] == ['depot.order#0']
    (drawn,) = final.entries('draw')
    digest = hashlib.sha256(f'7|{drawn.part}|depot.order#0'.encode()).digest()
    demand = 1 + 2 * ((int.from_bytes(digest[:8], 'big') * 2 + 1) / 2**65)
    assert drawn.detail('value') == pytest.approx(demand, rel=1e-12)
    assert [entry.owner for entry in final.entries('start')] == ['depot.order#0', 'depot.child#0']
    assert len(final.entries('commit', 'depot.order.step[0]')) == 1
    noted, orders = read(final, case.program, ['depot.noted', 'depot.orders'], [1, 2])
    assert noted.values == pytest.approx([demand, demand + 1], rel=1e-12)
    assert orders.values == (1, 1)


def test_a_declared_solver_between_two_solves():
    """`two_writes_one_solve`: solves in the setup, and at 1 h in rounds 1 and 2, whatever the stops; at 1 h
    care has 70 h. The pump's solve: once at 0 h and once when the tank empties at 5/3 h."""
    case = staffing()
    stops, final, _ = in_one_process(case)
    assert [(stop.stop.t, stop.stop.round) for stop in stops] == [(1, 1), (1, 2)]
    assert [(entry.t, entry.round) for entry in final.entries('solve')] == [(0, 0), (1, 1), (1, 2)]
    (care,) = read(final, case.program, ['office.staffing.care'], [1])
    assert care.values == pytest.approx([70])
    case = pumping()
    stops, final, _ = in_one_process(case)
    assert [stop.stop.t for stop in stops] == [0.5, 1.5]
    assert [entry.t for entry in final.entries('solve')] == pytest.approx([0, 5 / 3])
    fill, water = read(final, case.program, ['pump.fill.actual_rate', 'tank.water'], [0.5, 1.5, 2])
    assert fill.values == pytest.approx([0, 0, 4], abs=1e-6)
    assert water.values == pytest.approx([7, 1, 0], abs=1e-6)


def test_a_moving_solver_between_two_trial_states():
    """The first tank reaches 5 L at 1.25 h, between the stops at 0.5 h and 1.3 h; the second holds
    10 - 5 e^-(t - 1.25) L from then."""
    case = tapering()
    stops, final, _ = in_one_process(case)
    assert [stop.stop.t for stop in stops] == [0.5, 1.3]
    first, second = read(final, case.program, ['tank0.water', 'tank1.water'], [1, 1.5])
    assert first.values == pytest.approx([4, 5], rel=1e-6)
    assert second.values == pytest.approx([4, 10 - 5 * math.exp(-0.25)], rel=1e-6)


def boundary(at):
    """An actor whose events all come due at `at` (h): `prior` sets a value, then `decide` switches on
    a draw of a forecast (NO is likelier) and sets `chosen`, then `following` sets `later`; `future`
    is due an hour after. A tally fills at 1 h an hour. A breakpoint before the switch."""
    b = Builder({'h': {'time': 1}})
    plan = b.enum('enum[YES, NO]', 'YES', 'NO')
    b.entity(
        'actor',
        value('value', '', 0),
        value('chosen', '', 0),
        value('later', '', 0),
        value('accumulated', 'h', 0),
        flow('accumulate', SOURCE, this.accumulated, request=q(1, 'h/h')),
        event('prior', after(q(at, 'h'), assign(this.value, 7))),
        event(
            'decide',
            after(
                q(at, 'h'),
                switch(
                    draw(categorical(plan, YES=0.4, NO=0.6)),
                    on(plan.YES, assign(this.chosen, 1)),
                    on(plan.NO, assign(this.chosen, 2)),
                ),
            ),
        ),
        event('following', after(q(at, 'h'), assign(this.later, 1))),
        event('future', after(q(at + 1, 'h'), assign(this.later, 2))),
    )
    actor = named('actor')
    b.setup(start(actor.prior), start(actor.decide), start(actor.following), start(actor.future))
    return b.finish(), (Breakpoint('actor.decide.step[0].do[0]'),)


@pytest.mark.parametrize('at', [0, 2, 4])
def test_a_stop_keeps_what_its_moment_committed_before_the_stage_and_holds_the_rest(at):
    """At the stop, `prior` has committed in the moment, and nothing of `decide` or of `following`,
    which wait for it; resumed, the run is the run straight through: NO (the median) gives 2."""
    program, breakpoints = boundary(at)
    configuration = Configuration(Request(4))
    straight = run(program, configuration)
    made = Run(Plan.of(program, configuration), breakpoints)
    checkpoint = made.run()
    assert (checkpoint.stop.t, checkpoint.stop.owner) == (at, 'actor.decide#0')
    assert [checkpoint.state.value(f'actor.{name}') for name in ('value', 'chosen', 'later')] == [7, 0, 0]
    assert checkpoint.state.value('actor.accumulated') == pytest.approx(at)
    assert {entry.part for entry in checkpoint.record.entries('commit')} == {'actor.prior.step[0]'}
    assert checkpoint.state.pending == (
        ('actor.decide#0', 'actor.decide.step[0]'),
        ('actor.following#0', 'actor.following.step[0]'),
    )
    final = made.resume()
    assert_resume_parity(program, configuration, straight, final)
    assert [reading.values[0] for reading in read(final, program, ['actor.chosen'], [4])] == [2]


# ---- breakpoints ---------------------------------------------------------------------------------


def stops_of(case, *breakpoints):
    stops, _, _ = in_one_process(case._replace(breakpoints=breakpoints))
    return [(stop.stop.at, stop.stop.owner, stop.stop.t) for stop in stops]


def test_a_breakpoint_names_an_event_a_stage_or_a_statement_for_any_owner_or_one():
    case = family()
    assert stops_of(case, Breakpoint('tank.tick')) == [('tank.tick.step[0]', 'tank.tick#0', 1)]
    assert stops_of(case, Breakpoint('tank.tick.step[1]')) == [('tank.tick.step[1]', 'tank.tick#0', 2)]
    assert stops_of(case, Breakpoint('tank.tick', 'tank.tick#1')) == []
    assert stops_of(case, Breakpoint('tank.alarm', 'tank')) == [('tank.alarm.step[0]', 'tank.alarm#0', 3.5)]
    assert stops_of(case, Breakpoint('tank.alarm.step[0].do[0]')) == [
        ('tank.alarm.step[0].do[0]', 'tank.alarm#0', 3.5)
    ]
    assert stops_of(case, Breakpoint('setup[0]')) == [('setup[0]', '', 0)]


def test_a_breakpoint_where_a_run_cannot_stop_is_refused_by_name():
    case = family()
    plan = Plan.of(case.program, case.configuration)
    with pytest.raises(CheckpointError, match=r'tank\.nowhere: no event, stage or statement'):
        Run(plan, (Breakpoint('tank.nowhere'),))
    with pytest.raises(CheckpointError, match='the body of a trigger'):
        Run(plan, (Breakpoint('tank.alarm.when[0].do[0]'),))


# ---- the representation --------------------------------------------------------------------------


def test_the_representation_reads_back_every_value_it_holds():
    for held in (
        0.1,
        1e-300,
        -0.0,
        math.inf,
        2**70,
        (True, None, 'text', (1, 2.5)),
        Breakpoint('tank.tick', 'tank'),
        State((('x', 1.0),), (), (), ()),
    ):
        assert decode(encode(held)) == held
    assert math.isnan(decode(encode(math.nan)))
    assert encode(1.0) != encode(1)


def test_another_format_or_a_damaged_checkpoint_is_refused_by_name():
    with pytest.raises(CheckpointError, match='format 1; this napkin reads format 2'):
        loads(b'napkin checkpoint 1\n{}')
    with pytest.raises(CheckpointError, match='not a napkin checkpoint'):
        loads(b'{"$": "Breakpoint"}')
    with pytest.raises(CheckpointError, match='holds no record'):
        loads(b'napkin checkpoint 2\n{"$": "Plan"}')


def test_a_checkpoint_resumes_only_its_own_run():
    case = family()
    checkpoint = Run(Plan.of(case.program, case.configuration), case.breakpoints).run()
    other = lines().program
    with pytest.raises(CheckpointError, match='another program'):
        resume(other, checkpoint)
    with pytest.raises(CheckpointError, match='another version of the engine'):
        resume(case.program, replace(checkpoint, engine='0' * 64))
    values = tuple((name, 9.0 if name == 'tank.ticks' else found) for name, found in checkpoint.state.values)
    changed = replace(checkpoint, state=replace(checkpoint.state, values=values))
    with pytest.raises(CheckpointError, match='its saved state does not make its state again'):
        resume(case.program, changed)
    stops, _, _ = in_one_process(case)
    assert_resume_parity(case.program, case.configuration, stops[1], resume(case.program, checkpoint))
