"""What a record holds and whether a run within its budget succeeds follow one rule as the run goes
(the readiness audit of `8b3a01a`, rows 11 and 18; `program/record.py`, `Recorder`, `Breaks`,
`store.run`).

A run stops when the next trajectory piece or posting for a requested value exceeds the budget.
The record can also contain a point that gives a stock's exact balance at its cutoff.
A store's ledger begins with the edit that changed it. The same request has one outcome and set
of values on a fresh run, on a store hit and on a run resumed from its checkpoint.

The rule test: random plants on lines (two tanks, a fill, a pipe whose request a stage changes, a drain,
a count and a sum), stopped at random stages and statements of their tick, edited at random stops (a
tank lowered or raised, the pipe's request or the count set), recorded within random budgets, to random
horizons, of every value or of some: the three ways agree, in outcome to the time and the reason, and
in each value that the request holds at many times. Then the audit's two cases, worked by hand.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from napkin import store
from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.record import requested
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    event,
    flow,
    formula,
    move,
    named,
    q,
    start,
    this,
    value,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, Edit, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import BalancePoint, Curve, History, Key, Piece, Unavailable
from napkin.session import Log
from tests.engine.resume_parity import assert_resume_parity

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
LONGEST = 4  # the horizon of the stored longer run
PATHS = ['plant.w0', 'plant.w1', 'plant.ticks', 'plant.want', 'plant.total', 'plant.pipe.actual_rate']
LEDGERS = ['plant.w0.external', 'plant.w1.external']


def plant(rng, curved=False):
    """A random plant: tanks `w0` and `w1`, a fill into `w0`, a pipe from `w0` to `w1` at the request
    `want`, a drain from `w1`, the count `ticks` and the sum `total`; its tick's three stages, an hour
    apart, each add one to the count and set `want`. On lines, or, `curved`, with a drain that takes
    half of `w1` an hour, so that `w1`, its drain and `total` are on curves."""
    drain = formula(this.w1 / q(2, 'h')) if curved else q(rng.choice([0.5, 1, 3]), 'L/h')
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('w0', 'L', rng.randint(2, 8), lower=0),
        value('w1', 'L', rng.randint(0, 4), lower=0, upper=rng.choice([None, 10])),
        value('ticks', '', 0),
        value('want', 'L/h', rng.choice([0.5, 1, 2])),
        value('total', 'L', formula(this.w0 + this.w1)),
        flow('fill', SOURCE, this.w0, request=q(rng.choice([0.5, 1, 2]), 'L/h')),
        flow('pipe', this.w0, this.w1, request=formula(this.want)),
        flow('drain', this.w1, SINK, request=drain),
        event(
            'tick',
            *(
                after(q(1, 'h'), add(this.ticks, 1), assign(this.want, q(rng.choice([0, 1, 3]), 'L/h')))
                for _ in range(3)
            ),
        ),
    )
    b.setup(start(named('plant').tick))
    return b.finish()


def log(rng):
    """Random breakpoints at the stages of the tick and before their second statements, and random
    edits at the stops: {hit: [(target, value)]}."""
    places = [f'plant.tick.step[{k}]' for k in range(3)] + [f'plant.tick.step[{k}].do[1]' for k in range(3)]
    breakpoints = tuple(Breakpoint(at) for at in rng.sample(places, rng.randint(0, 3)))
    edits = {}
    for hit in range(1, 4):
        if rng.random() < 0.7:
            target = rng.choice(['plant.w0', 'plant.w1', 'plant.ticks', 'plant.want'])
            new = {'plant.ticks': 7, 'plant.want': rng.choice([0, 2])}.get(target, rng.choice([0.5, 3, 9]))
            edits.setdefault(hit, []).append((Key('plant', (target.split('.')[1],)), new))
    return breakpoints, edits


def fresh(program, configuration, breakpoints, edits):
    """The run of a log straight on: stopped at each hit, edited there, resumed in place. Gives its
    record and its checkpoints."""
    made = Run(Plan.of(program, configuration), breakpoints)
    found, stops = made.run(), []
    while isinstance(found, Checkpoint):
        stops.append(found)
        for target, new in edits.get(found.stop.hit, ()):
            made.edit(target, new)
        found = made.resume()
    return found, stops


def resumed(program, configuration, breakpoints, edits):
    """The same run, saved at its first stop with the edits made there, loaded as a fresh process
    loads it and resumed from its saved state, then edited at each later stop."""
    made = Run(Plan.of(program, configuration), breakpoints)
    found = made.run()
    if not isinstance(found, Checkpoint):
        return found
    for target, new in edits.get(found.stop.hit, ()):
        found = made.edit(target, new)
    again = Run.restored(Plan.of(program, configuration), loads(dumps(found)))
    found = again.resume()
    while isinstance(found, Checkpoint):
        for target, new in edits.get(found.stop.hit, ()):
            again.edit(target, new)
        found = again.resume()
    return found


def outcome(record):
    """Finished, or stopped: the kind of the stop, the time of the end and the reason."""
    stop = record.stop
    return ('finished', record.end) if stop is None else (stop.kind, record.end, record.stopped())


def held(record, program, times):
    """Each path that the record holds, with its values at `times`."""
    found = {}
    for path in PATHS + LEDGERS:
        (reading,) = read(record, program, [path], times)
        if not all(
            isinstance(each, Unavailable) and 'names other values' in each.reason for each in reading.values
        ):
            found[path] = reading.values
    return found


def differences(one, other):
    """What differs between two records, for a failure's message: the keys of the histories that one
    holds and the other does not, those whose pieces differ, and whether the traces and the failures
    differ."""
    mine = {history.key: history.pieces for history in one.histories}
    theirs = {history.key: history.pieces for history in other.histories}
    return (
        sorted(map(str, mine.keys() ^ theirs.keys())),
        sorted(str(key) for key in mine.keys() & theirs.keys() if mine[key] != theirs[key]),
        one.trace != other.trace,
        one.failure != other.failure,
    )


def same(left, right):
    if isinstance(left, (bool, str, Unavailable)) or isinstance(right, (bool, str, Unavailable)):
        return left == right
    return left == pytest.approx(right, rel=1e-12, abs=1e-12)


def charged_starts(record):
    return sorted(
        float(piece.t)
        for history in record.histories
        if record.manifest.names(history.key)
        for piece in history.pieces
        if not isinstance(piece, BalancePoint)
    )


@pytest.mark.parametrize('curved', [False, True], ids=['lines', 'curves'])
@pytest.mark.parametrize('seed', range(40))
def test_fresh_stored_and_resumed_runs_of_a_request_have_one_outcome_and_one_set_of_values(
    seed, curved, tmp_path
):
    rng = random.Random(seed)
    program = plant(rng, curved)
    breakpoints, edits = log(rng)
    _, stops = fresh(program, Configuration(Request(LONGEST)), breakpoints, edits)
    recorded_log = Log(
        breakpoints,
        tuple(cp.stop for cp in stops),
        tuple(Edit(cp.stop.hit, target, new) for cp in stops for target, new in edits.get(cp.stop.hit, ())),
    )
    for _ in range(4):
        horizon = rng.choice([0.5, 1, 1.5, 2, 2.5, 3, 4])
        keys = ()
        if rng.random() < 0.5:
            keys = tuple(Key('plant', tuple(path.split('.')[1:])) for path in rng.sample(PATHS + LEDGERS, 2))
        asked = Request(horizon, everything=not keys, keys=keys)
        whole, _ = fresh(program, Configuration(asked), breakpoints, edits)
        count = len(charged_starts(whole))
        request = Request(horizon, everything=not keys, keys=keys, pieces=rng.randint(1, count + 2))
        configuration = Configuration(request)
        alone, stops = fresh(program, configuration, breakpoints, edits)
        assert outcome(alone) == outcome(whole.within(request.pieces)), (seed, request, breakpoints, edits)
        # A run whose record would exceed its budget stops then: no checkpoint is past its budget.
        for checkpoint in stops:
            assert checkpoint.record.failure is None, (seed, request, checkpoint.stop)
            assert checkpoint.stop.t <= alone.end, (seed, request, checkpoint.stop)
        with store.use(tmp_path):
            cold = store.run(program, configuration, recorded_log)
            warm = store.run(program, configuration, recorded_log)
        later = resumed(program, configuration, breakpoints, edits)
        assert cold == warm == alone, (seed, request, differences(alone, warm))
        times = sorted({0, horizon, *(round(rng.uniform(0, horizon), 3) for _ in range(5))})
        assert_resume_parity(program, configuration, alone, later, sample_times=times)
        expected = held(alone, program, times)
        for record in (warm, later):
            found = held(record, program, times)
            assert found.keys() == expected.keys(), (seed, request)
            for path, values in expected.items():
                for at, a, b in zip(times, found[path], values, strict=True):
                    if record is warm or isinstance(a, Unavailable) or isinstance(b, Unavailable):
                        assert same(a, b), (seed, request, path, at, a, b)


# ---- the audit's cases, by hand ----------------------------------------------------------------------------


def tank(*before_tick):
    """A tank of 10 L that drains at 2 L/h, and a tick at 2 h, where a breakpoint stops the run."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        value('ticks', '', 0),
        flow('drain', this.water, SINK, request=q(2, 'L/h')),
        event('tick', after(q(2, 'h'), *before_tick, add(this.ticks, 1))),
    )
    b.setup(start(named('tank').tick))
    return b.finish()


WATER = Key('tank', ('water',))


def test_a_two_piece_budget_keeps_the_exact_tank_balance_at_the_checkpoint_and_horizon():
    program = tank()
    configuration = Configuration(Request(4, everything=False, keys=(WATER,), pieces=2))
    straight = Run(Plan.of(program, configuration)).run()
    live = Run(Plan.of(program, configuration), (Breakpoint('tank.tick.step[0]'),))
    checkpoint = live.run()
    assert isinstance(checkpoint, Checkpoint) and checkpoint.stop.t == 2
    saved = loads(dumps(checkpoint))
    assert saved.record == checkpoint.record

    for record, time, balance in ((saved.record, 2, 6), (straight, 4, 2)):
        assert record.end == time and record.failure is None
        opening, drain, point = record.history(WATER).pieces
        assert opening.t == drain.t == 0 and opening.value == drain.value == 10
        assert drain.at(time) == balance
        assert isinstance(point, BalancePoint)
        assert (point.t, point.value, point.rate, point.curve) == (time, balance, 0, None)
        assert record.value(WATER, time) == balance
        assert record.within(2) == record
        assert record.within(1).failure.t == 0

    for final in (live.resume(), Run.restored(Plan.of(program, configuration), saved).resume()):
        assert_resume_parity(program, configuration, straight, final)


def test_a_real_tick_exhausts_the_budget_while_the_tank_drains():
    program = tank()
    ticks = Key('tank', ('ticks',))
    request = Request(4, everything=False, keys=(WATER, ticks))
    whole = Run(Plan.of(program, Configuration(request))).run()
    assert whole.failure is None and whole.value(ticks, 2) == 1
    bounded = Run(Plan.of(program, Configuration(replace(request, pieces=3)))).run()

    assert bounded == requested(whole.within(3), program)
    assert bounded.end == 2 and bounded.failure.detail('budget') == 3
    assert [(p.t, p.value) for p in bounded.history(ticks).pieces] == [(0, 0)]
    assert all(piece.t < bounded.end for history in bounded.histories for piece in history.pieces)
    assert charged_starts(bounded) == [0, 0, 0]
    assert bounded.value(WATER, 1.75) == 6.5
    assert isinstance(bounded.value(WATER, 2), Unavailable)


def test_an_inclusive_stage_failure_keeps_the_exact_stock_balance():
    program = tank(assign(this.ticks, 1 / this.ticks))
    request = Request(4, everything=False, keys=(WATER,), pieces=2)
    record = Run(Plan.of(program, Configuration(request))).run()
    assert record.end == 2 and 'division by zero' in record.failure.detail('message')
    assert record.failure.detail('budget') is None
    assert record.history(WATER).pieces[-1] == BalancePoint(2, 6)
    assert record.value(WATER, 2) == 6
    assert charged_starts(record) == [0, 0]
    assert record.within(2) == record


def test_an_exact_fitted_line_ends_with_the_physical_balance_point():
    engine = Run(Plan.of(tank(), Configuration(Request(4, everything=False, keys=(WATER,)))))
    record = engine.run()
    # This degree-one Chebyshev series reads exactly 10 L at 0 h and 2 L at 4 h.
    line = Piece(0, 10.0, curve=Curve(4.0, (6.0, -4.0)))
    assert line.at(4) == record.value(WATER, 4) == 2
    incoming = replace(record, histories=(History(WATER, (line,)),))
    projected = engine.stock_state.project(incoming)
    assert projected.history(WATER).pieces == (line, BalancePoint(4, 2.0))
    assert projected.within(1) == projected


def test_a_stock_posting_at_the_horizon_still_uses_a_piece():
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 10),
        value('bottle', 'L', 0),
        event('fill', after(q(2, 'h'), move(q(1, 'L'), this.water, this.bottle))),
    )
    b.setup(start(named('tank').fill))
    program = b.finish()
    full = Run(Plan.of(program, Configuration(Request(2, everything=False, keys=(WATER,), pieces=2)))).run()
    assert full.failure is None and full.value(WATER, 2) == 9
    one = Run(Plan.of(program, Configuration(Request(2, everything=False, keys=(WATER,), pieces=1)))).run()
    assert one.failure.t == 2 and one.failure.detail('budget') == 1
    assert one == requested(full.within(1), program)


def test_checkpoint_after_a_child_starts_counts_projected_pieces_separately():
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('count', '', 0),
        event('driver', after(q(1, 'h'), add(this.count, 1), start(this.child))),
        event('child', after(q(2, 'h'))),
        event('watch', after(q(1, 'h'), add(this.count, 1))),
    )
    plant = named('plant')
    b.setup(start(plant.driver), start(plant.watch))
    program = b.finish()
    count = Key('plant', ('count',))
    configuration = Configuration(Request(2, everything=False, keys=(count,), pieces=2))
    engine = Run(Plan.of(program, configuration), (Breakpoint('plant.watch.step[0]'),))
    checkpoint = engine.run()
    # The driver's write and start precede the watch in the same round. Only the projection
    # has assembled that write. The live run still has one piece counted from setup.
    assert [piece.value for piece in checkpoint.record.history(count).pieces] == [0, 1]
    assert engine.recorder._counted['plant.count'] == engine.recorder._total == 1
    record = engine.resume()
    assert_resume_parity(program, configuration, Run(Plan.of(program, configuration)).run(), record)
    assert record.failure.t == 1 and record.failure.detail('budget') == 2


def test_an_edit_after_the_horizon_of_a_request_adds_no_ledger():
    """Row 11: the tank is lowered to 4 L at the stop at 2 h. A request of the water to 1 h within two
    pieces holds its opening and its drain line. An extra point holds its balance at 1 h.
    No ledger exists because nothing came from outside by 1 h. The 4 h run holds the ledger
    from its edit at 2 h, -2 L (6 L lowered to 4 L)."""
    program, stops = tank(), (Breakpoint('tank.tick.step[0]'),)
    edits = {1: [(WATER, 4)]}
    longer, _ = fresh(program, Configuration(Request(4)), stops, edits)
    assert read(longer, program, ['tank.water.external'], [1, 3])[0].values == (0, -2)
    request = Request(1, everything=False, keys=(WATER,), pieces=2)
    alone, _ = fresh(program, Configuration(request), stops, edits)
    assert alone.failure is None and alone.end == 1
    assert read(alone, program, ['tank.water', 'tank.water.external'], [1])[0].values == (8,)
    assert read(alone, program, ['tank.water.external'], [1])[0].values == (0,)
    assert sum(len(history.pieces) for history in alone.histories if alone.manifest.names(history.key)) == 3
    assert alone.within(2) == alone


def test_a_run_past_its_budget_at_0_h_gives_no_checkpoint_at_2_h():
    """Row 18: within one piece the tank's record stops at 0 h, where its water has two pieces (its
    start and its line); so the run with a breakpoint at 2 h stops there by its budget, with no
    checkpoint, as the run with none does."""
    program, stops = tank(), (Breakpoint('tank.tick.step[0]'),)
    configuration = Configuration(Request(4, pieces=1))
    found = Run(Plan.of(program, configuration), stops).run()
    straight = Run(Plan.of(program, configuration)).run()
    assert not isinstance(found, Checkpoint)
    assert found == straight and found.end == 0 and found.failure.detail('budget') == 1


def test_a_rate_at_the_horizon_is_the_one_that_its_last_round_committed():
    """A read at a moment sees what its last round committed (`program/record.py`): the pipe's request
    is set from 2 L/h to 1 L/h at 1 h, so its rate at 1 h is 1 L/h, in a run to 1 h as in a run to 4 h,
    on curves (a drain that takes half of the tank an hour) as on lines. On curves no segment starts at
    the horizon: the set records its state there, with the rates of its next segment (`ways.finish`;
    on every way, `test_horizon_reads.py`)."""
    for curved in (False, True):
        b = Builder(UNITS)
        drain = formula(this.w1 / q(2, 'h')) if curved else q(1, 'L/h')
        b.entity(
            'plant',
            value('w0', 'L', 8, lower=0),
            value('w1', 'L', 2, lower=0),
            value('want', 'L/h', 2),
            flow('pipe', this.w0, this.w1, request=formula(this.want)),
            flow('drain', this.w1, SINK, request=drain),
            event('tick', after(q(1, 'h'), assign(this.want, q(1, 'L/h')))),
        )
        b.setup(start(named('plant').tick))
        program = b.finish()
        for horizon in (1, 4):
            record = Run(Plan.of(program, Configuration(Request(horizon)))).run()
            assert read(record, program, ['plant.pipe.actual_rate'], [1])[0].values == (1,), (curved, horizon)


def test_history_budget_stops_work_at_the_first_excess_piece(monkeypatch):
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('count', '', 0),
        event('tick', *(after(q(1, 'h'), add(this.count, 1)) for _ in range(10))),
    )
    b.setup(start(named('plant').tick))
    request = Request(10, everything=False, keys=(Key('plant', ('count',)),), pieces=1)
    made = Run(Plan.of(b.finish(), Configuration(request)))
    visited = []
    at = made.moment.at

    def observe(t, *args):
        visited.append(t)
        return at(t, *args)

    monkeypatch.setattr(made.moment, 'at', observe)
    record = made.run()
    assert record.failure.t == 1
    assert visited == [1]


@pytest.mark.parametrize('first_stage', [None, 1, 10])
def test_a_clock_formula_exhausts_its_budget_on_the_first_completed_span(first_stage):
    """The first completed span is [0,1] with hourly stages, otherwise [0,10].
    The former needs one piece. The latter splits [0,1.25] into halves."""
    from napkin.program.build import call, t

    b = Builder(UNITS)
    ticks = (
        [
            event(
                'tick',
                after(q(0, 'h'), assign(this.ticks, 0)),
                after(q(0, 'h'), assign(this.ticks, 0)),
                *(after(q(first_stage, 'h'), add(this.ticks, 1)) for _ in range(10 // first_stage)),
            )
        ]
        if first_stage is not None
        else []
    )
    b.entity(
        'plant',
        value('curve', '', formula(call('exp', t / q(1, 'h')))),
        value('ticks', '', 0),
        *ticks,
    )
    if ticks:
        b.setup(start(named('plant').tick))
    key = Key('plant', ('curve',))
    request = Request(10, everything=False, keys=(key,), pieces=1)
    made = Run(Plan.of(b.finish(), Configuration(request)))
    record = made.run()
    cutoff = 1 if first_stage == 1 else 0.625
    assert record.failure is not None and record.failure.t == cutoff
    assert record.failure.round == (1 if ticks else 0)
    assert record.history(key).pieces[0].curve.length == cutoff
    assert made.env['plant.ticks'] == (1 if first_stage == 1 else 0)


def test_a_completed_fit_stops_before_the_next_write_to_its_input():
    """The first two completed spans begin at 0 and 1 h. Ticks advance the
    recorder even though the offset will not change until 5 h."""
    from napkin.program.build import call, t

    b = Builder(UNITS)
    b.entity(
        'plant',
        value('offset', '', 0),
        value('ticks', '', 0),
        value('curve', '', formula(call('exp', t / q(1, 'h')) + this.offset)),
        event(
            'tick',
            after(q(1, 'h'), add(this.ticks, 1)),
            after(q(1, 'h'), add(this.ticks, 1)),
            after(q(3, 'h'), add(this.offset, 1)),
            after(q(1, 'h'), add(this.ticks, 1)),
        ),
    )
    b.setup(start(named('plant').tick))
    key = Key('plant', ('curve',))
    request = Request(10, everything=False, keys=(key,), pieces=1)
    made = Run(Plan.of(b.finish(), Configuration(request)))
    record = made.run()
    assert record.failure is not None and record.failure.t == 1
    assert record.history(key).pieces[0].curve.length == 1
    assert (made.env['plant.offset'], made.env['plant.ticks']) == (0, 1)


@pytest.mark.parametrize('offset_time', [2, 5])
def test_a_raw_counter_and_a_curve_stop_before_the_next_input_write(offset_time):
    """The counter and the curve each start a piece at 0 h. The counter adds
    one at 1 h, independently of how long it takes for the offset to change."""
    from napkin.program.build import call, t

    b = Builder(UNITS)
    b.entity(
        'plant',
        value('offset', '', 0),
        value('count', '', 0),
        value('curve', '', formula(call('exp', t / q(1, 'h')) + this.offset)),
        event(
            'tick',
            after(q(1, 'h'), add(this.count, 1)),
            after(q(offset_time - 1, 'h'), add(this.offset, 1)),
            after(q(1, 'h'), add(this.count, 1)),
        ),
    )
    b.setup(start(named('plant').tick))
    curve = Key('plant', ('curve',))
    request = Request(10, everything=False, keys=(curve, Key('plant', ('count',))), pieces=2)
    made = Run(Plan.of(b.finish(), Configuration(request)))
    record = made.run()
    assert record.failure.t == 1
    assert record.history(curve).pieces[0].curve.length == 1
    assert (made.env['plant.offset'], made.env['plant.count']) == (0, 1)


def test_a_selected_tanks_starting_line_exhausts_the_budget_before_the_tick():
    """The 10 L starting piece and the -2 L/h line both begin at 0 h."""
    request = Request(4, everything=False, keys=(WATER,), pieces=1)
    made = Run(Plan.of(tank(), Configuration(request)))
    record = made.run()
    assert record.failure.t == 0
    assert made.env['tank.ticks'] == 0


@pytest.mark.parametrize('ticks', [32, 128])
def test_repeated_budget_checks_append_only_the_changed_selected_pieces(ticks, monkeypatch):
    """Double the counter at each hour. Unselected peers and past counter values need no visit."""
    from napkin.engine.timeline import record as recording

    b = Builder(UNITS)
    b.entity(
        'plant',
        value('count', '', 0),
        value('double', '', formula(this.count + this.count)),
        *(value(f'spare{k}', '', formula(this.count + k)) for k in range(60)),
        event('tick', *(after(q(1, 'h'), add(this.count, 1)) for _ in range(ticks))),
    )
    b.setup(start(named('plant').tick))
    key = Key('plant', ('double',))
    request = Request(ticks, everything=False, keys=(key,), pieces=ticks + 1)
    visits, materialized = [], []
    compact, record = recording._compact, recording.Recorder.record

    def count_pieces(pieces):
        visits.append(len(pieces))
        return compact(pieces)

    def count_records(self, end, *args, **kwargs):
        materialized.append(end)
        return record(self, end, *args, **kwargs)

    monkeypatch.setattr(recording, '_compact', count_pieces)
    monkeypatch.setattr(recording.Recorder, 'record', count_records)
    found = Run(Plan.of(b.finish(), Configuration(request))).run()
    assert found.history(key).at(ticks) == 2 * ticks
    assert len(found.history(key).pieces) == ticks + 1
    assert sum(visits) <= 10 * (ticks + 1)
    assert materialized == [ticks]


def fitting_plant(curve, *, drain='still', delay=1, write_delay=1):
    from napkin.program.build import call, t

    b = Builder(UNITS)
    clock = t / q(1, 'h')
    observed = (
        call('exp', clock) + this.offset + this.water / q(1, 'L')
        if curve == 'exponential'
        else 10**10 * clock + 0.03 * call('exp', -100 * clock)
    )
    b.entity(
        'plant',
        value('water', 'L', 3, lower=0),
        value('offset', '', 0),
        value('count', '', 0),
        value('curve', '', formula(observed)),
        flow(
            'drain',
            this.water,
            SINK,
            request=formula(this.water / q(4, 'h'))
            if drain == 'curve'
            else q(0.25 if drain == 'line' else 0, 'L/h'),
        ),
        event(
            'tick',
            after(q(delay, 'h'), add(this.count, 1)),
            after(q(write_delay, 'h'), add(this.offset, 1)),
            after(q(2, 'h'), add(this.count, 1)),
        ),
    )
    b.setup(start(named('plant').tick))
    return b.finish()


@pytest.mark.parametrize('formula_kind', ['exponential', 'fast decay'])
def test_a_breakpoint_preserves_the_completed_fits_and_the_budget_cutoff(formula_kind):
    program = fitting_plant(formula_kind, write_delay=4)
    key = Key('plant', ('curve',))
    stops = (Breakpoint('plant.tick.step[0]'),)
    request = Request(10, everything=False, keys=(key,))
    whole, checkpoints = fresh(program, Configuration(request), stops, {})
    (checkpoint,) = checkpoints
    early = tuple(p for p in checkpoint.record.history(key).pieces if p.t < 1)
    assert early == tuple(p for p in whole.history(key).pieces if p.t < 1)
    for budget in (1, 2, 3):
        bounded = Configuration(Request(10, everything=False, keys=(key,), pieces=budget))
        expected = whole.within(budget)
        straight, _ = fresh(program, bounded, (), {})
        observed, stops_seen = fresh(program, bounded, stops, {})
        assert outcome(straight) == outcome(expected)
        assert_resume_parity(program, bounded, straight, observed)
        assert all(cp.stop.t <= expected.end for cp in stops_seen)


@pytest.mark.parametrize(
    'seed', [*range(8), *[pytest.param(k, marks=pytest.mark.deep) for k in range(8, 40)]]
)
def test_budget_cutoffs_follow_the_complete_records_committed_piece_starts(seed):
    rng = random.Random(seed)
    program = fitting_plant(
        rng.choice(['exponential', 'fast decay']),
        drain=rng.choice(['still', 'line', 'curve']),
        delay=rng.choice([0.5, 1, 2]),
    )
    stops = (Breakpoint('plant.tick.step[0]'), Breakpoint('plant.tick.step[1].do[0]'))
    edits = {rng.choice([1, 2]): [(Key('plant', ('offset',)), rng.choice([0.5, 2]))]}
    for keys in ((), (Key('plant', ('curve',)),), (Key('plant', ('count',)), Key('plant', ('water',)))):
        horizon = 5
        whole, _ = fresh(
            program, Configuration(Request(horizon, everything=not keys, keys=keys)), stops, edits
        )
        times = charged_starts(whole)
        # The sorted list deliberately retains different pieces that start at the same instant.
        for budget in (rng.randint(1, len(times)), max(1, len(times) - 1), len(times)):
            config = Configuration(Request(horizon, everything=not keys, keys=keys, pieces=budget))
            record, held_stops = fresh(program, config, stops, edits)
            restored = resumed(program, config, stops, edits)
            assert_resume_parity(program, config, record, restored)
            expected = requested(whole.within(budget), program)
            assert record == expected, differences(record, expected)
            assert record.end == (times[budget] if budget < len(times) else horizon)
            assert (record.failure is not None) == (budget < len(times))
            assert all(cp.stop.t <= record.end for cp in held_stops)
