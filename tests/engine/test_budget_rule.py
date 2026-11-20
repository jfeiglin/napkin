"""What a record holds and whether a run within its budget succeeds follow one rule as the run goes
(the readiness audit of `8b3a01a`, rows 11 and 18; `program/record.py`, `Recorder`, `Breaks`,
`store.run`).

A run whose record would hold more pieces than its budget stops then, before any later stop or
checkpoint: no checkpoint holds a record past its budget. The run keeps what its request names and the budget counts those pieces.
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

import pytest

from napkin import store
from napkin.engine.timeline import Plan, Run, read
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
    named,
    q,
    start,
    this,
    value,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, Edit, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key, Unavailable
from napkin.session import Log

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
        count = sum(len(history.pieces) for history in whole.histories if whole.manifest.names(history.key))
        request = Request(horizon, everything=not keys, keys=keys, pieces=rng.randint(1, count + 2))
        configuration = Configuration(request)
        alone, stops = fresh(program, configuration, breakpoints, edits)
        # A run whose record would exceed its budget stops then: no checkpoint is past its budget.
        for checkpoint in stops:
            assert checkpoint.record.failure is None, (seed, request, checkpoint.stop)
            assert checkpoint.stop.t <= alone.end, (seed, request, checkpoint.stop)
        with store.use(tmp_path):
            cold = store.run(program, configuration, recorded_log)
            warm = store.run(program, configuration, recorded_log)
        later = resumed(program, configuration, breakpoints, edits)
        assert outcome(warm) == outcome(alone) == outcome(later), (seed, request, breakpoints, edits)
        assert cold == warm == alone == later, (
            seed,
            request,
            differences(alone, warm),
            differences(alone, later),
        )
        times = sorted({0, horizon, *(round(rng.uniform(0, horizon), 3) for _ in range(5))})
        expected = held(alone, program, times)
        for record in (warm, later):
            found = held(record, program, times)
            assert found.keys() == expected.keys(), (seed, request)
            for path, values in expected.items():
                for at, a, b in zip(times, found[path], values, strict=True):
                    assert same(a, b), (seed, request, path, at, a, b)


# ---- the audit's cases, by hand ----------------------------------------------------------------------------


def tank():
    """A tank of 10 L that drains at 2 L/h, and a tick at 2 h, where a breakpoint stops the run."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        value('ticks', '', 0),
        flow('drain', this.water, SINK, request=q(2, 'L/h')),
        event('tick', after(q(2, 'h'), add(this.ticks, 1))),
    )
    b.setup(start(named('tank').tick))
    return b.finish()


WATER = Key('tank', ('water',))


def test_an_edit_after_the_horizon_of_a_request_adds_no_ledger():
    """Row 11: the tank is lowered to 4 L at the stop at 2 h. A request of the water to 1 h within two
    pieces holds the water at 0 h, 10 L, and on its line from 0 h at -2 L/h: two pieces, by hand, and no
    ledger, since nothing came from outside by 1 h. The 4 h run holds the ledger
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
    assert sum(len(history.pieces) for history in alone.histories if alone.manifest.names(history.key)) == 2


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
