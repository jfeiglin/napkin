"""A held-row budget stop keeps the last eligible boundary of the complete record."""

from unittest.mock import patch

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.family import Family
from napkin.engine.timeline.lines import Lines
from napkin.engine.timeline.record import Recorder, requested
from napkin.engine.timeline.saved import at_stop
from napkin.program.build import (
    BOOL,
    SINK,
    Builder,
    after,
    assign,
    event,
    flow,
    formula,
    fsum,
    input_,
    item,
    named,
    q,
    root,
    start,
    t,
    this,
    value,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key


def held_program(*, clock=False, pause=False, keyed=False):
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    demand = q(1, 'L/h')
    if keyed:
        phase = b.template('Phase', input_('hour', 'h', 0), input_('rate', 'L/h', 1))
        b.table(
            'phases',
            phase,
            [
                {'id': f'p{k}', 'hour': at, 'rate': rate}
                for k, (at, rate) in enumerate([(0, 1), (1.25, 0.5), (2.25, 1.5), (3.25, 0.5), (4.25, 2)])
            ],
        )
        demand = formula(phase.instances.by('hour').at(t).rate)
    tank = b.template(
        'Tank',
        input_('initial', 'L', 1),
        input_('observed', BOOL, True),
        value('water', 'L', this.initial, lower=0),
        value('level', 'L', formula(this.water)),
        flow('drain', this.water, SINK, request=demand),
    )
    b.table(
        'tanks',
        tank,
        [
            {'id': f'r{k}', 'initial': initial, 'observed': k % 2 == 0}
            for k, initial in enumerate([1, 2, 2, 3, 4])
        ],
    )
    b.root(
        value('water', 'L', formula(fsum(tank.instances.level))),
        value('observed', 'L', formula(fsum(tank.instances.where(item.observed).level))),
        value('rate', 'L/h', formula(fsum(tank.instances.drain.actual_rate))),
        value('filtered', 'L', formula(fsum(tank.instances.where(item.initial > q(6, 'L')).level))),
        value('alias', 'L', formula(root.observed)),
        *([value('later', BOOL, formula(t > q(2.25, 'h')))] if clock else []),
    )
    if pause:
        b.entity('reader', event('pause', after(q(2, 'h')), after(q(2, 'h'))))
        b.setup(start(named('reader').pause))
    return b.finish()


def run_held(program, keys, pieces, *, horizon=5):
    seen = []
    original = Family.step

    def step(family, levels=()):
        seen.append(family.peek())
        return original(family, levels)

    request = Request(horizon, everything=not keys, keys=keys, pieces=pieces)
    engine = Run(Plan.of(program, Configuration(request)))
    with patch.object(Family, 'step', step):
        record = engine.run()
    return record, seen


@pytest.mark.parametrize(
    'keys',
    [(), (Key('', ('alias',)), Key('', ('filtered',))), (Key('tanks.r1', ('water',)),)],
)
def test_held_budget_matches_the_latest_complete_prefix_that_fits(keys):
    program = held_program()
    whole, visits = run_held(program, keys, 100_000)
    assert whole.failure is None
    assert sorted(set(visits)) == [1, 2, 3, 4]
    assert set(visits) <= set(whole.manifest.check_times)
    count = sum(h.charged_pieces() for h in whole.histories if whole.manifest.names(h.key))
    for budget in [*range(1, count + 2), 100_000]:
        actual, _ = run_held(program, keys, budget)
        assert actual == requested(whole.within(budget), program), (keys, budget)
        assert sum(h.charged_pieces() for h in actual.histories if actual.manifest.names(h.key)) <= budget


def test_clock_changes_between_held_stock_boundaries_count_toward_the_budget():
    program = held_program(clock=True)
    key = Key('', ('later',))
    whole, _ = run_held(program, (key,), 100_000)
    assert [p.value for p in whole.history(key).pieces] == [False, True]
    limited, _ = run_held(program, (key,), 1)
    assert limited == requested(whole.within(1), program)
    assert limited.end == 2


@pytest.mark.parametrize('keys', [(), (Key('', ('alias',)),)])
def test_zero_horizon_ends_at_the_same_budget(keys):
    program = held_program()
    full, _ = run_held(program, keys, 100_000, horizon=0)
    for budget in (1, 100_000):
        actual, steps = run_held(program, keys, budget, horizon=0)
        assert actual == requested(full.within(budget), program) and steps == []


def test_repeated_checkpoint_projections_at_an_independent_bound_keep_the_same_record():
    program = held_program()
    boundary, snapshots = Recorder.boundary, []

    def check(self, end, **options):
        boundary(self, end, **options)
        if options.get('internal') and end == 3:
            for _ in range(2):
                recorder, _ = at_stop(self.run)
                snapshots.append(recorder.record(end, ongoing=True))

    expected, _ = run_held(program, (), 100_000)
    with patch.object(Recorder, 'boundary', check):
        actual, _ = run_held(program, (), 100_000)
    assert actual == expected
    assert len(snapshots) == 2 and snapshots[0] == snapshots[1]


def test_stage_breakpoints_on_held_bounds_and_serialized_resume_obey_the_budget():
    program = held_program(pause=True)
    keys = (Key('', ('alias',)),)
    stops = (Breakpoint('reader.pause.step[0]'), Breakpoint('reader.pause.step[1]'))

    def paused(budget):
        config = Configuration(Request(5, everything=False, keys=keys, pieces=budget))
        engine = Run(Plan.of(program, config), stops)
        found, prefixes = engine.run(), []
        while isinstance(found, Checkpoint):
            prefixes.append((found.stop.t, found.record))
            restored = Run.restored(Plan.of(program, config), loads(dumps(found)))
            found = restored.resume()
        return found, prefixes

    whole, checkpoints = paused(100_000)
    assert [at for at, _ in checkpoints] == [2, 4]
    for budget in (1, 2, 3, 4, 5, 100_000):
        actual, prefixes = paused(budget)
        assert actual == requested(whole.within(budget), program)
        available = [(at, record) for at, record in checkpoints if record.within(budget).failure is None]
        assert prefixes == available
        if budget == 1:
            assert actual.end == 1 and not prefixes


def test_keyed_flow_stops_at_the_last_boundary_that_fits():
    program = held_program(keyed=True)
    whole, _ = run_held(program, (), 100_000)
    starts = [p.t for h in whole.histories for p in h.pieces[: h.charged_pieces()]]
    budget = len(starts) - 1
    actual, _ = run_held(program, (), budget)
    assert actual == whole.within(budget)
    assert actual.failure is not None
    assert actual.end == max(t for t in whole.manifest.check_times if sum(at < t for at in starts) <= budget)


@pytest.mark.parametrize('keys', [(), (Key('plant', ('alias',)),)])
def test_summed_held_connections_keep_the_same_budget_failure_and_checkpoint_projection(keys):
    b = Builder({'L': {'volume': 1}, 'h': {'time': 1}})
    b.entity(
        'plant',
        value('left', 'L', 4, lower=0),
        value('right', 'L', 3, lower=0),
        value('tank', 'L', 0, lower=0, upper=2),
        flow('a', this.left, this.tank, request=q(2, 'L/h')),
        flow('b', this.right, this.tank, request=q(1, 'L/h')),
        flow('out', this.tank, SINK, request=q(1, 'L/h')),
        value('combined', 'L/h', formula(this.a.actual_rate + this.b.actual_rate)),
        value('alias', 'L/h', formula(this.combined)),
    )
    b.setup(assign(named('plant').left, q(4, 'L')))
    program = b.finish()
    boundary = Recorder.boundary

    def observe(pieces, horizon, restore=False):
        config = Configuration(Request(horizon, everything=not keys, keys=keys, pieces=pieces))
        engine = Run(Plan.of(program, config), (Breakpoint('setup[0]'),) if restore else ())
        prefixes = []

        def execute():
            nonlocal engine
            result = engine.run()
            if isinstance(result, Checkpoint):
                assert restore
                prefixes.append((result.stop.t, result.record))
                engine = Run.restored(Plan.of(program, config), loads(dumps(result)))
                return engine.resume()
            if restore:
                assert result.failure.detail('budget') == pieces
            return result

        def budget(recorder, end, **options):
            boundary(recorder, end, **options)
            if options.get('internal'):
                stopped, _ = at_stop(engine)
                prefixes.append((end, stopped.record(end, ongoing=True)))

        with patch.object(Recorder, 'boundary', budget):
            result = execute()
        assert all(isinstance(way, Lines) for way in engine.ways.instances)
        return result, prefixes

    for horizon, restore in ((0, False), (6, False), (6, True)):
        whole, snapshots = observe(100_000, horizon, restore=restore)
        assert whole.failure is None
        if horizon:
            assert len(snapshots) >= 2
        total = sum(h.charged_pieces() for h in whole.histories if whole.manifest.names(h.key))
        for limit in (1, max(1, total - 1), total, total + 1):
            actual, seen = observe(limit, horizon, restore=restore)
            assert actual == requested(whole.within(limit), program)
            assert all(record.within(limit) == record for _, record in seen if record.failure is None)
