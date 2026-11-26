"""What a record holds and whether a run within its budget succeeds follow one rule as the run goes
(the readiness audit of `8b3a01a`, rows 11 and 18; `program/record.py`, `Recorder`, `Breaks`,
`store.run`).

A limited run returns the latest check boundary whose exclusive prefix fits its piece budget.
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
from napkin.program.record import (
    BalancePoint,
    Curve,
    Entry,
    History,
    Key,
    Manifest,
    Piece,
    Record,
    Unavailable,
)
from napkin.session import Log
from tests.engine.resume_parity import assert_resume_parity

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
LONGEST = 4  # the horizon of the stored longer run
PATHS = ['plant.w0', 'plant.w1', 'plant.ticks', 'plant.want', 'plant.total', 'plant.pipe.actual_rate']
LEDGERS = ['plant.w0.external', 'plant.w1.external']


def test_exclusive_budget_failure_has_round_zero_with_or_without_a_later_pause():
    water = Key('plant', ('water',))
    history = History(water, tuple(Piece(t, t) for t in range(146)))
    observation = Entry(129, 1, 'finish', 'plant.observe', 'plant.observe#0')
    whole = Record(Manifest(146, check_times=tuple(range(147))), (history,), (observation,))
    at_check = replace(
        whole,
        manifest=replace(whole.manifest, check_times=tuple(range(146))),
        trace=(observation, Entry(145, 1, 'pause', '')),
    )
    for budget in range(130, 145):
        expected = whole.within(budget)
        assert expected.failure.t == budget
        assert expected.failure.round == 0
        assert at_check.within(budget) == expected


@pytest.mark.parametrize('path', ['water', 'report'])
def test_unrelated_tick_checks_the_budget_without_publishing_the_open_step(monkeypatch, path):
    from napkin.engine.timeline import plan
    from napkin.engine.timeline.record import Recorder
    from napkin.model.compile import compile_text

    monkeypatch.setattr(plan, 'LIMIT', 0)  # Exercise the same two directed meters on Sparse.
    program = compile_text(
        """scenario "An unrelated clock reads a pending budget"
    horizon 2 h
tank:
    water: L = 10 L
    flow fill: SOURCE -> this.water
        request = formula(1 L/h + t * 1 L/h/h)
    flow drain: this.water -> SINK
        request = formula(0.5 L/h + t * 0.25 L/h/h)
    report = formula(max(this.water, 10.75 L))
    tick = event():
        after 1 h
tank.tick.start()
""",
        UNITS,
    ).program
    key = Key('tank', (path,))
    config = Configuration(Request(2, everything=False, keys=(key,)))
    live = Run(Plan.of(program, config))
    checks = []
    check = Recorder.check_budget

    def observed(recorder, end, **options):
        pending = list(live.ways.unrecorded(end)) if recorder is live.recorder and end == 1 else []
        before = [(way.recorded_through, tuple(recorder.pieces.get('tank.water', ()))) for way in pending]
        try:
            return check(recorder, end, **options)
        finally:
            if before:
                after = [
                    (way.recorded_through, tuple(recorder.pieces.get('tank.water', ()))) for way in pending
                ]
                assert after == before
                checks.append(end)

    with monkeypatch.context() as observed_run:
        observed_run.setattr(Recorder, 'check_budget', observed)

        def private_view(*args, **kwargs):
            pytest.fail('An unlimited run must not assemble a private record at a budget check')

        observed_run.setattr(Recorder, 'projection', private_view)
        whole = live.run()
    assert whole.failure is None and checks
    # water(t) = 10 + t/2 + 3t²/8. The report follows that stock after its bend.
    assert whole.history(key).at(1) == pytest.approx(10.875)
    assert whole.history(key).at(2) == pytest.approx(12.5)
    starts = charged_starts(whole)
    assert len(starts) >= 2
    for limit in (1, len(starts) - 1, len(starts)):
        bounded = replace(config, request=replace(config.request, pieces=limit))
        actual = Run(Plan.of(program, bounded)).run()
        expected = requested(whole.within(limit), program)
        assert actual == expected
        assert len(charged_starts(actual)) <= limit

    stopped = Run(Plan.of(program, config), (Breakpoint('tank.tick.step[0]'),))
    cutoff = stopped.run()
    assert isinstance(cutoff, Checkpoint) and cutoff.stop.t == 1
    restored = Run.restored(Plan.of(program, config), loads(dumps(cutoff)))
    assert_resume_parity(program, config, whole, restored.resume())


@pytest.mark.parametrize('stage_fails', [False, True], ids=['horizon', 'stage-failure'])
def test_four_charged_tank_pieces_stop_at_the_last_solver_boundary_that_fits(monkeypatch, stage_fails):
    from napkin.engine.timeline.record import Recorder
    from napkin.model.compile import compile_text

    final_write = 'this.marker = 1 / (this.marker - 1)' if stage_fails else 'this.marker = 2'
    model = compile_text(
        f"""scenario "A stock with unpublished incoming pieces"
    horizon 2 h
tank:
    water: L = 10 L
    flow fill: SOURCE -> this.water
        request = formula(1 L/h + t * 1 L/h/h)
    flow spare: SOURCE -> this.water
        request = 0.1 L/h
    flow drain: this.water -> SINK
        request = formula(0.5 L/h + t * 0.25 L/h/h)
clock:
    marker = 0
    tick = event():
        after 0.75 h:
            this.marker = 1
        after 0.25 h:
            {final_write}
clock.tick.start()
""",
        UNITS,
    )
    request = replace(model.configuration.request, everything=False, keys=(WATER,))
    times = []
    boundary = Recorder.boundary

    def observe(recorder, end, **options):
        times.append(end)
        return boundary(recorder, end, **options)

    def run(request):
        return Run(Plan.of(model.program, replace(model.configuration, request=request))).run()

    with monkeypatch.context() as witness:
        witness.setattr(Recorder, 'boundary', observe)
        whole = run(request)
    if stage_fails:
        assert whole.failure.t == 1 and 'division by zero' in whole.failure.detail('message')
    else:
        assert whole.failure is None
    starts = charged_starts(whole)
    assert 0.75 in times and 1 in times
    assert sum(at < 0.75 for at in starts) == sum(at < 1 for at in starts) == 5
    cutoff = max(t for t in times if sum(at < t for at in starts) <= 4)
    assert 0 < cutoff < 0.75 and sum(at < cutoff for at in starts) == 4
    limited = run(replace(request, pieces=4))
    assert limited == requested(whole.within(4), model.program)
    assert limited.failure.t == cutoff and limited.failure.round == 0
    assert charged_starts(limited) == [at for at in starts if at < cutoff]
    assert isinstance(limited.value(WATER, cutoff), Unavailable)


def test_a_formula_landing_cleared_in_the_same_moment_does_not_exhaust_one_piece():
    from napkin.model.compile import compile_text

    model = compile_text(
        """scenario "Two rounds at the same moment"
    horizon 2 h
box:
    x = 0
    reading = formula(2 * this.x)
    tick = event():
        after 1 h:
            this.x = 1
            this.clear_flag.start()
    clear_flag = event():
        after 0 h:
            this.x = 0
box.tick.start()
""",
        {'h': {'time': 1}},
    )
    key = Key('box', ('reading',))
    request = replace(model.configuration.request, everything=False, keys=(key,))

    def run(request):
        return Run(Plan.of(model.program, replace(model.configuration, request=request))).run()

    whole = run(request)
    limited = run(replace(request, pieces=1))
    assert whole.end == 2 and whole.failure is None
    writes = [entry for entry in whole.trace if entry.kind == 'commit' and entry.t == 1]
    assert len(writes) == 2 and writes[0].round < writes[1].round
    assert whole.history(key).pieces == (Piece(0, 0),)
    assert limited == whole.within(1) == whole


def test_a_pause_between_two_rounds_keeps_the_record_within_its_budget_and_does_not_end_the_run():
    from napkin.model.compile import compile_text

    # At 1 h a first round sets x = 1 and a second round clears it: the finished run has one piece.
    model = compile_text(
        """scenario "Two rounds at the same moment"
    horizon 2 h
box:
    x = 0
    reading = formula(2 * this.x)
    tick = event():
        after 1 h:
            this.x = 1
            this.clear_flag.start()
    clear_flag = event():
        after 0 h:
            this.x = 0
box.tick.start()
""",
        {'h': {'time': 1}},
    )
    key = Key('box', ('reading',))
    configuration = replace(
        model.configuration,
        request=replace(model.configuration.request, everything=False, keys=(key,), pieces=1),
    )
    straight = Run(Plan.of(model.program, configuration)).run()
    assert straight.failure is None and straight.history(key).pieces == (Piece(0, 0),)
    live = Run(Plan.of(model.program, configuration), (Breakpoint('box.clear_flag.step[0]'),))
    checkpoint = live.run()
    # Between the rounds the record holds the one piece before 1 h; the state holds x = 1.
    assert isinstance(checkpoint, Checkpoint) and checkpoint.stop.t == 1
    assert checkpoint.record.failure is None and checkpoint.record.history(key).pieces == (Piece(0, 0),)
    saved = loads(dumps(checkpoint))
    assert dict(saved.state.values)['box.x'] == 1
    assert any(occurrence.id.startswith('box.clear_flag#') for occurrence in saved.state.occurrences)
    assert Run.restored(Plan.of(model.program, configuration), saved).resume() == straight
    assert live.resume() == straight


def test_a_rolled_back_posting_does_not_use_the_budget():
    from napkin.engine.timeline.moment import Tx, _Savepoint

    program = plant(random.Random(1))
    name = 'plant.want'
    key = Key('plant', ('want',))
    run = Run(Plan.of(program, Configuration(Request(7, everything=False, keys=(key,), pieces=1))))
    run.prepare()
    recorder = run.recorder
    original = recorder.record(0, ongoing=True)
    tx = Tx('plant.tick#0')
    tx.writes[name] = 4.0
    point = _Savepoint(run, tx)
    recorder.add(name, 2, 4.0, 0)
    point.discard()
    after = recorder.record(2, ongoing=True)
    assert after.failure is None
    assert after.history(key) == original.history(key)


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
    # The driver writes once before the watch in the same round. The checkpoint keeps that write.
    assert [piece.value for piece in checkpoint.record.history(count).pieces] == [0, 1]
    assert checkpoint.record.within(2) == checkpoint.record
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


def test_committed_posting_stops_at_the_last_boundary_that_fits(monkeypatch):
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
    The former needs one piece. With the default fit tolerance, the first piece
    of the longer span covers [0,0.625], but there is no check at 0.625 h."""
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
    full_request = replace(request, pieces=1_000)
    whole = Run(Plan.of(made.plan.program, Configuration(full_request))).run()
    assert record == requested(whole.within(1), made.plan.program)
    if first_stage != 1:
        starts = charged_starts(whole)
        assert 0 < starts[1] < 10
        assert whole.manifest.check_times == (0, 10)
    cutoff = 1 if first_stage == 1 else 0
    assert record.failure is not None and record.failure.t == cutoff
    assert record.failure.round == 0
    if cutoff:
        assert record.history(key).pieces[0].curve.length == cutoff
    else:
        assert not record.histories
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
def test_budget_cutoffs_follow_the_last_check_boundary_that_fits(seed):
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
            if budget < len(times):
                boundary = max(t for t in whole.manifest.check_times if sum(at < t for at in times) <= budget)
                assert record.end == boundary
                assert len(charged_starts(record)) <= budget
            else:
                assert record.end == horizon
            assert (record.failure is not None) == (budget < len(times))
            assert all(cp.stop.t <= record.end for cp in held_stops)
