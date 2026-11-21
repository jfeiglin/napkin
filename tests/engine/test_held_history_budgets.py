"""A held row's independent stop must enforce the same first excess piece as the full recorder."""

import math
from unittest.mock import patch

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.family import Family
from napkin.engine.timeline.lines import Lines
from napkin.engine.timeline.record import Recorder
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


def run_held(program, keys, pieces, *, exact, horizon=5):
    seen = []
    original = Family.step

    def step(family):
        seen.append(family.peek())
        return original(family)

    request = Request(horizon, everything=not keys, keys=keys, pieces=pieces)
    engine = Run(Plan.of(program, Configuration(request)))
    with patch.object(Family, 'step', step):
        if exact:
            with patch.object(Recorder, '_held_piece_bound', return_value=(math.inf, 0)):
                record = engine.run()
        else:
            record = engine.run()
    return record, seen, engine.recorder


@pytest.mark.parametrize(
    'keys',
    [(), (Key('', ('alias',)), Key('', ('filtered',))), (Key('tanks.r1', ('water',)),)],
)
def test_held_budget_matches_complete_histories_and_stops_work_at_first_excess(keys):
    program = held_program()
    whole, visits, counted = run_held(program, keys, 100_000, exact=False)
    assert whole.failure is None
    assert counted._held_upper < 100_000
    assert sorted(set(visits)) == [1, 2, 3, 4]
    count = sum(len(h.pieces) for h in whole.histories if whole.manifest.names(h.key))
    for budget in [*range(1, count + 2), 100_000]:
        actual, actual_steps, _ = run_held(program, keys, budget, exact=False)
        expected, expected_steps, _ = run_held(program, keys, budget, exact=True)
        assert actual == expected, (keys, budget)
        assert actual_steps == expected_steps, (keys, budget)
        assert all(at <= actual.end for at in actual_steps), (keys, budget)


def test_clock_reader_falls_back_to_committing_the_actual_fits():
    program = held_program(clock=True)
    model, _, counter = run_held(program, (), 100_000, exact=False)
    assert counter._held_upper == math.inf
    assert model == run_held(program, (), 100_000, exact=True)[0]
    clock = model.history(Key('', ('later',)))
    assert [p.value for p in clock.pieces] == [False, True]


@pytest.mark.parametrize('keys', [(), (Key('', ('alias',)),)])
def test_zero_horizon_ends_at_the_same_budget(keys):
    program = held_program()
    for budget in (1, 100_000):
        actual, steps, _ = run_held(program, keys, budget, exact=False, horizon=0)
        expected, _, _ = run_held(program, keys, budget, exact=True, horizon=0)
        assert actual == expected and steps == []


def test_repeated_checkpoint_projections_at_an_independent_bound_keep_the_same_record():
    program = held_program()
    budget, snapshots = Recorder.check_budget, []

    def check(self, end, **options):
        budget(self, end, **options)
        if options.get('internal') and end == 3:
            for _ in range(2):
                recorder, _ = at_stop(self.run)
                snapshots.append(recorder.record(end, ongoing=True))

    with patch.object(Recorder, 'check_budget', check):
        actual, _, _ = run_held(program, (), 100_000, exact=False)
        expected, _, _ = run_held(program, (), 100_000, exact=True)
    assert actual == expected
    assert len(snapshots) == 4
    assert all(prefix == snapshots[0] for prefix in snapshots)


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

    for budget in (1, 2, 3, 4, 5, 100_000):
        actual, prefixes = paused(budget)
        with patch.object(Recorder, '_held_piece_bound', return_value=(math.inf, 0)):
            assert (actual, prefixes) == paused(budget)
        assert all(at <= actual.end for at, _ in prefixes)
        if budget == 100_000:
            assert [at for at, _ in prefixes] == [2, 4]
        if budget == 1:
            assert actual.end == 1 and not prefixes


def test_a_safe_early_bound_can_precede_a_later_budget_failure():
    program = held_program(keyed=True)
    whole, _, _ = run_held(program, (), 100_000, exact=True)
    count = sum(len(h.pieces) for h in whole.histories)
    visits = []
    original = Recorder._advance

    def advance(self, end):
        visits.append(end)
        return original(self, end)

    with patch.object(Recorder, '_advance', advance):
        actual, steps, _ = run_held(program, (), count - 1, exact=False)
    expected, exact_steps, _ = run_held(program, (), count - 1, exact=True)
    assert actual == expected and steps == exact_steps
    assert actual.failure is not None
    assert steps[0] == 1 and steps[0] not in visits
    assert actual.end in visits


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
    check = Recorder.check_budget

    def observe(pieces, horizon, exact, restore=False):
        config = Configuration(Request(horizon, everything=not keys, keys=keys, pieces=pieces))
        engine = Run(Plan.of(program, config), (Breakpoint('setup[0]'),) if restore else ())
        prefixes = []

        def execute():
            nonlocal engine
            result = engine.run()
            if restore:
                assert isinstance(result, Checkpoint)
                prefixes.append((result.stop.t, result.record))
                engine = Run.restored(Plan.of(program, config), loads(dumps(result)))
                return engine.resume()
            return result

        def budget(recorder, end, **options):
            check(recorder, end, **options)
            if options.get('internal'):
                stopped, _ = at_stop(engine)
                prefixes.append((end, stopped.record(end, ongoing=True)))

        with patch.object(Recorder, 'check_budget', budget):
            if exact:
                with patch.object(Recorder, '_held_piece_bound', return_value=(math.inf, 0)):
                    result = execute()
            else:
                result = execute()
        assert all(isinstance(way, Lines) for way in engine.ways.instances)
        return result, prefixes, engine.recorder

    complete, prefix, recorder = observe(100_000, 6, False)
    assert complete.failure is None and len(prefix) >= 2
    assert math.isfinite(recorder._held_upper)
    total = sum(len(history.pieces) for history in complete.histories)
    for horizon, pieces in [(0, 1), (0, 100_000), (6, 1), (6, total - 1), (6, total), (6, total + 1)]:
        assert observe(pieces, horizon, False)[:2] == observe(pieces, horizon, True)[:2]
    for limit in (total - 1, 100_000):
        assert observe(limit, 6, False, restore=True)[:2] == observe(limit, 6, True, restore=True)[:2]
