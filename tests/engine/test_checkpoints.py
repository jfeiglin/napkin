"""Breakpoints, checkpoints and exact resume (PLAN, change 15; `timeline/checkpoints.py`).

A breakpoint at a stage or a statement stops a run with a checkpoint, and the run resumed from it
gives the same recorded values, draws, event times and event order as the run straight through. Each
case runs three ways: with no breakpoint; stopped and resumed in place in one process, at each stop;
and each checkpoint saved, loaded and resumed in a fresh process (a subprocess under another hash
seed), which must give the next checkpoint of the run in one process, or its final record, equal in
every bit. The subprocess builds the program from the same Python code of this module, until the
loadable program of S7-F replaces that.

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
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
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
    this,
    uniform,
    value,
    when,
)
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
from tests.program.examples import EXAMPLES

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


def alarm(test):
    """An event that a trigger on `test` starts once, and that adds one to `alarms`."""
    return event('alarm', when(test, start(this.alarm), reset=reset_when(False)), after(q(0, 'h'), add(this.alarms, 1)))


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
    return Case(b.finish(), Configuration(Request(5)), (Breakpoint('tank.tick'),), frozenset({SPARSE if sparse else COMPONENT}))


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
    return Case(b.finish(), Configuration(Request(7)), (Breakpoint('tank.tick'),), frozenset({FAMILY}))


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
    return Case(b.finish(), Configuration(Request(7)), (Breakpoint('tank.tick'),), frozenset({LINES}))


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
    return Case(b.finish(), Configuration(Request(2)), (Breakpoint('tank.tick'),), frozenset({DECLARED}))


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
    return Case(b.finish(), Configuration(Request(1.5)), (Breakpoint('clock.tick'),), frozenset({DECLARED}))


SCENARIOS = {
    case.__name__: case
    for case in (draining, draining_sparse, family, lines, ordering, staffing, pumping, tapering)
}

# A fresh process: it builds the scenario's program and resumes each checkpoint that it is given.
FRESH = """
import sys
from napkin.engine.timeline import resume
from napkin.program.checkpoint import encode, loads
from tests.engine.test_checkpoints import SCENARIOS

program = SCENARIOS[sys.argv[1]]().program
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


def in_a_fresh_process(name, stops, folder):
    """What a fresh process gives for each checkpoint: the next checkpoint, or the final record."""
    paths = []
    for k, checkpoint in enumerate(stops):
        path = folder / f'{k}.checkpoint'
        path.write_bytes(dumps(checkpoint))
        paths.append(str(path))
    environment = {**os.environ, 'PYTHONHASHSEED': '4321', 'NAPKIN_STORE': 'off'}
    done = subprocess.run(
        [sys.executable, '-c', FRESH, name, *paths],
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
    assert len(stops) >= 2
    assert {connected.way for connected, _ in made.ways.sets.values()} == case.ways
    assert final == straight
    assert [entry.kind for entry in final.trace] == [entry.kind for entry in straight.trace]
    for checkpoint in stops:
        # The record so far is the run's to the stop, with the entry of the stop at its end.
        assert checkpoint.record.trace[:-1] == straight.trace[: len(checkpoint.record.trace) - 1]
        assert paused(checkpoint.record).detail('hit') == checkpoint.stop.hit
        assert loads(dumps(checkpoint)) == checkpoint
    assert in_a_fresh_process(name, stops, tmp_path) == [*stops[1:], final]


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
    assert starts(final, 'tank.alarm') == [at]
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


# ---- breakpoints ---------------------------------------------------------------------------------


def stops_of(case, *breakpoints):
    stops, _, _ = in_one_process(case._replace(breakpoints=breakpoints))
    return [(stop.stop.at, stop.stop.owner, stop.stop.t) for stop in stops]


def test_a_breakpoint_names_an_event_a_stage_or_a_statement_for_any_owner_or_one():
    case = family()
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
    with pytest.raises(CheckpointError, match='tank.nowhere: no event, stage or statement'):
        Run(plan, (Breakpoint('tank.nowhere'),))
    with pytest.raises(CheckpointError, match='the body of a trigger'):
        Run(plan, (Breakpoint('tank.alarm.when[0].do[0]'),))


# ---- the representation --------------------------------------------------------------------------


def test_the_representation_reads_back_every_value_it_holds():
    for value in (
        0.1,
        1e-300,
        -0.0,
        math.inf,
        2**70,
        (True, None, 'text', (1, 2.5)),
        Breakpoint('tank.tick', 'tank'),
        State((('x', 1.0),), (), (), ()),
    ):
        assert decode(encode(value)) == value
    assert math.isnan(decode(encode(math.nan)))
    assert encode(1.0) != encode(1)


def test_another_format_or_a_damaged_checkpoint_is_refused_by_name():
    with pytest.raises(CheckpointError, match='format 2; this napkin reads format 1'):
        loads(b'napkin checkpoint 2\n{}')
    with pytest.raises(CheckpointError, match='not a napkin checkpoint'):
        loads(b'{"$": "Breakpoint"}')
    with pytest.raises(CheckpointError, match='holds no record'):
        loads(b'napkin checkpoint 1\n{"$": "Plan"}')


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
    with pytest.raises(CheckpointError, match='the state differs'):
        resume(case.program, changed)
    stops, _, _ = in_one_process(case)
    assert resume(case.program, checkpoint) == stops[1]
