"""A stock gets one trajectory per accepted Radau step, including at a stop inside it."""

import math
from dataclasses import replace

import pytest

from napkin.engine.timeline import Plan, Run, plan, resume, saved
from napkin.engine.timeline.moment import Tx, _Savepoint
from napkin.engine.timeline.record import requested
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, dumps, loads
from napkin.program.config import Request
from napkin.program.record import BalancePoint, Entry, Key, Unavailable
from tests.engine.resume_parity import assert_resume_parity

WATER = Key('tank', ('water',))
PULSE = Key('tank', ('pulse',))
SOURCE = """scenario "A tank observed during a solver step"
    horizon 2 h
tank:
    water: L = 10 L
    pulse = 0
    on = 1
    flow fill: SOURCE -> this.water
        request = formula(this.on * (1 L/h + t * 1 L/h/h))
    flow drain: this.water -> SINK
        request = formula(this.on * (0.5 L/h + t * 0.25 L/h/h))
    tick = event():
        after 1 h:
            this.pulse = 1
            this.pause.start()
    pause = event():
        after 0 h
tank.tick.start()
"""


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(plan, 'LIMIT', 0)
    return compile_text(SOURCE, {'L': {'volume': 1}, 'h': {'time': 1}})


def test_projected_first_step_has_its_own_raw_and_assembled_history(model):
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare()
    way = run.ways.instance_of('tank.water')
    way.last_step = 1
    end = way.peek()
    first, second = end / 4, end / 2
    run.now = first
    way.observe(first)
    live_raw = tuple(run.recorder.pieces.get('tank.water', ()))
    live_histories = dict(run.recorder._histories)
    for at in (first, second):
        run.now = at
        way.observe(at)
        view, _ = saved.at_stop(run)
        assert view is not run.recorder and way.recorded_through is None
        observation = view.record(at, pause=Entry(at, 0, 'pause', ''), ongoing=True)
        projected = observation.history(WATER).pieces
        assert projected[-1] == view._histories['tank.water'].pieces[-1]
        assert projected[-1].curve.length == end
        assert projected[-1].at(at) == pytest.approx(way.pending[2](at)[0], rel=1e-14)
        assert isinstance(observation.value(WATER, math.nextafter(at, math.inf)), Unavailable)
        assert tuple(run.recorder.pieces.get('tank.water', ())) == live_raw
        assert run.recorder._histories == live_histories

    # Only a real write enters a live savepoint. The private observation is absent.
    tx = Tx('tank.tick#0')
    tx.writes['tank.water'] = 20
    savepoint = _Savepoint(run, tx)
    run.recorder.add('tank.water', second, 20, 0)
    assert run.recorder.pieces['tank.water'][-1] == (second, 20, 0)
    savepoint.discard()
    assert tuple(run.recorder.pieces.get('tank.water', ())) == live_raw
    way.step()
    (raw,) = run.recorder.pieces['tank.water']
    assert raw[0] == 0 and raw[2].length == end


def test_exact_opening_survives_a_later_physical_post_before_the_first_projection(monkeypatch):
    from fractions import Fraction

    monkeypatch.setattr(plan, 'LIMIT', 0)
    source = SOURCE.replace('water: L = 10 L', 'water: L = 10.000000000000000001 L')
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare()
    way = run.ways.instance_of('tank.water')
    way.last_step = 1
    end = way.peek()
    t = end / 4
    opening = Fraction('10.000000000000000001')
    assert run.stock_state.balances['tank.water'][0] == opening
    way.observe(t)
    assert run.stock_state.post_stock('tank.water', t)
    assert run.stock_state.balances['tank.water'][0] != opening
    view = run.recorder.projection()
    way.record_through(t, view)
    assert view.pieces['tank.water'][0][1] == opening
    way.step()
    assert run.recorder.pieces['tank.water'][0][1] == opening


def test_disk_checkpoint_exposes_only_the_accepted_stock_prefix(model, tmp_path):
    live = Run(Plan.of(model.program, model.configuration), (Breakpoint('tank.pause.step[0]'),))
    checkpoint = live.run()
    time = checkpoint.stop.t
    way = live.ways.instance_of('tank.water')
    start, end = way.pending[:2]
    assert start < time < end
    raw = dict(dict(dict(checkpoint.saved)['recorder'])['pieces'])['tank.water']
    assert raw[-1][0] == start
    stock = checkpoint.record.history(WATER)
    assert stock.pieces[-2].curve == raw[-1][2]
    assert start + stock.pieces[-2].curve.length > time
    assert isinstance(stock.pieces[-1], BalancePoint)
    assert stock.pieces[-1].t == time
    assert stock.pieces[-1].value == float(live.stock_balance('tank.water', time))
    assert isinstance(checkpoint.record.value(WATER, math.nextafter(time, math.inf)), Unavailable)

    path = tmp_path / 'inside-step.napkin'
    path.write_bytes(dumps(checkpoint))
    restored = loads(path.read_bytes())
    assert restored.record == checkpoint.record
    direct = Run(Plan.of(model.program, model.configuration)).run()
    for record in (live.resume(), resume(model.program, restored)):
        assert_resume_parity(model.program, model.configuration, direct, record)


def test_latest_eligible_check_on_either_side_of_each_charged_start(model):
    def run(request):
        return Run(Plan.of(model.program, replace(model.configuration, request=request))).run()

    request = Request(2, everything=False, keys=(WATER, PULSE))
    whole = run(request)
    charged = sorted(
        p.t for h in whole.histories if whole.manifest.names(h.key) for p in h.pieces[: h.charged_pieces()]
    )
    assert 1 in charged
    for budget in range(1, len(charged) + 2):
        bounded = run(replace(request, pieces=budget))
        oracle = requested(whole.within(budget), model.program)
        assert bounded == oracle
        cutoff = max(t for t in whole.manifest.check_times if sum(at < t for at in charged) <= budget)
        assert bounded.end == cutoff
        if bounded.failure:
            assert all(not isinstance(p, BalancePoint) for h in bounded.histories for p in h.pieces)
            assert isinstance(bounded.value(WATER, bounded.end), Unavailable)
        else:
            assert bounded == whole


def test_live_and_offline_cuts_inside_the_same_stock_step_are_identical(monkeypatch):
    from napkin.program.checkpoint import decode, encode

    monkeypatch.setattr(plan, 'LIMIT', 0)
    source = (
        SOURCE.split('    tick = event():')[0]
        + """    tick = event():
        after 0.125 h:
            this.pulse = 1
        after 0.125 h:
            this.pulse = 2
tank.tick.start()
"""
    )
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    request = Request(2, everything=False, keys=(WATER, PULSE))

    def run(request):
        return Run(Plan.of(model.program, replace(model.configuration, request=request))).run()

    whole = run(request)
    postings = whole.history(PULSE).pieces
    assert [(p.t, p.value) for p in postings] == [(0, 0), (0.125, 1), (0.25, 2)]
    stock = whole.history(WATER)
    crossing = next(p for p in reversed(stock.pieces) if p.t < 0.125)
    assert crossing.curve is not None and crossing.t + crossing.curve.length > 0.25
    starts = sorted(p.t for h in whole.histories for p in h.pieces[: h.charged_pieces()])
    first, second = starts.index(0.125), starts.index(0.25)
    live = run(replace(request, pieces=first))
    offline = whole.within(first)
    retrimmed = decode(encode(whole.within(second))).within(first)
    assert live.end == offline.end == 0.125
    assert encode(live) == encode(retrimmed) == encode(offline)
    at = math.nextafter(live.end, 0)
    assert live.value(WATER, at) == pytest.approx(10 + at / 2 + 0.375 * at**2, rel=1e-12)


def test_real_posting_ends_the_moving_step_and_the_new_balance_holds(monkeypatch):
    monkeypatch.setattr(plan, 'LIMIT', 0)
    source = SOURCE.replace('this.pulse = 1', 'this.water = 20 L\n            this.on = 0')
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    record = Run(Plan.of(model.program, model.configuration)).run()
    assert record.failure is None
    stock = record.history(WATER)
    last_moving = next(p for p in reversed(stock.pieces) if p.curve)
    assert last_moving.t < 1 <= last_moving.t + last_moving.curve.length
    assert stock.at(math.nextafter(1, 0)) == pytest.approx(10.875)
    assert [stock.at(t) for t in (1, 1.5, 2)] == [20, 20, 20]
    (posting,) = [p for p in stock.pieces if p.t >= 1]
    assert posting.t == 1 and posting.rate == 0 and posting.curve is None
    assert not isinstance(posting, BalancePoint) and stock.charged_pieces() == len(stock.pieces)


def test_private_prefix_uses_the_same_joint_fit_as_the_completed_step(model):
    """One stock's subdivided fit also supplies the common grid of its held neighbour."""
    import numpy as np
    from scipy.integrate._ivp.radau import RadauDenseOutput

    from napkin.engine.timeline.record import fitted

    start, end = 1000.0, 1000.0000001
    solution = RadauDenseOutput(
        start, end, np.array([10.0, 4.0]), np.array([[0.0, 0.0, 0.0], [0.5, 0.25, 0.25]])
    )
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare()
    way = run.ways.instance_of('tank.water')
    way.stores = ('tank.water', 'tank.spare')
    way.kept_stores = [0, 1]
    way.atol = np.array([1e-8, 1e-8])
    way.kept_flows = []
    way.t = start
    way.pending = (start, end, solution, solution(end), False)
    way._history_span()

    def states(times):
        return np.array([solution(t) for t in times])

    expected = dict(zip(way.stores, fitted(states, start, end, way.atol), strict=True))
    assert len(expected['tank.water']) == len(expected['tank.spare']) > 1
    at = start + 0.7 * (end - start)
    view = run.recorder.projection()
    way.record_through(at, view)
    for name, rows in expected.items():
        assert view.pieces[name] == [row for row in rows if row[0] < at]
        assert not run.recorder.pieces.get(name)
    way.record_through(end)
    for name, rows in expected.items():
        assert run.recorder.pieces[name] == rows


def test_compacted_held_prefix_can_become_curved_without_erasing_same_time_postings(model):
    from napkin.program.record import Curve

    run = Run(Plan.of(model.program, model.configuration))
    run.prepare()
    recorder = run.recorder
    recorder.add('tank.water', 0.5, 11.0, 0.0)
    recorder.add('tank.water', 0.5, 10.0, 0.0)
    raw = recorder.pieces['tank.water']
    postings = list(raw)
    names = ['tank.water']
    opening = (0.5, 10.0, 0.0)
    recorder.store_step(names, lambda start: [[opening]], 0.5, complete=False)
    held = recorder.record(0.6, ongoing=True).history(WATER)
    assert [p.value for p in held.pieces if p.t == 0.5] == [11.0, 10.0]

    def fit(start):
        return [[(start, 10.0, Curve(0.75 - start, (0.0, 2.0))), (0.75, 14.0, 0.0)]]

    # A moving fit at .5 would uncompact the previously held opening. Keep the
    # original prefix, including the two real postings at .5, and fit only from .6.
    recorder.store_step(names, fit, 0.6, complete=False)
    prefix = recorder.record(0.8, ongoing=True).history(WATER)
    assert [(p.t, p.value) for p in prefix.pieces if p.t >= 0.5] == [
        (0.5, 11.0),
        (0.5, 10.0),
        (0.6, 10.0),
        (0.75, 14.0),
    ]
    assert raw == [*postings, opening]
    # Further observations use the .6 origin. A stable tail can now extend normally.
    recorder.store_step(names, fit, 0.8, complete=True)
    final = recorder.record(0.9, ongoing=True).history(WATER)
    assert final == prefix and raw == postings + [opening] + fit(0.6)[0]


@pytest.mark.parametrize('first_held', [True, False])
def test_observed_stock_interval_keeps_its_held_or_moving_shape(model, first_held):
    from napkin.program.record import Curve

    run = Run(Plan.of(model.program, model.configuration))
    run.prepare()
    recorder = run.recorder
    name = 'tank.water'
    recorder.add(name, 0.1, 11.0, 0.0)

    def fit(start, end, held):
        return [[(start, 10.0, 0.0 if held else Curve(end - start, (0.0, 1.0)))]]

    # A different preceding balance gives both shapes the same charged start at .5.
    recorder.store_step([name], lambda t: fit(t, 0.6, first_held), 0.5, complete=False)
    observed = recorder.record(0.6, ongoing=True).history(WATER).pieces[-1]
    assert observed.t == 0.5 and (observed.curve is None) == first_held
    recorder.store_step([name], lambda t: fit(t, 0.8, not first_held), 0.6, complete=True)
    history = recorder.record(0.8, ongoing=True).history(WATER)
    assert history.pieces[-2] == observed
    assert history.pieces[-1].t == 0.6 and (history.pieces[-1].curve is not None) == first_held


def test_stock_prefix_compacts_against_a_retired_producers_coverage_opening(model):
    from napkin.program.record import Curve

    request = replace(model.configuration.request, everything=False, keys=(WATER,))
    run = Run(Plan.of(model.program, replace(model.configuration, request=request)))
    run.prepare(now=False)
    name = 'tank.water'
    recorder = run.recorder
    recorder.add(name, 0.1, 10.0, 0.0)  # the retiring producer's last posting
    recorder._coverage_starts[name] = 0.2

    def starts(at):
        history = recorder.record(at, ongoing=True).history(WATER)
        return [piece.t for piece in history.pieces]

    assert starts(0.3) == [0.2]
    run.ways.build(run.waiting, run.env, 0.5)
    recorder.store_step([name], lambda t: [[(t, 10.0, 0.0)]], 0.5, complete=False)
    assert starts(0.6) == [0.2]

    # A checkpoint rebuilds the history from a private raw sequence while the
    # producer is active. The provisional opening still follows the retired balance.
    recorder.pieces[name] = list(recorder.pieces[name])
    recorder._dirty.add(name)
    assert starts(0.6) == [0.2]

    recorder.store_step([name], lambda t: [[(t, 10.0, Curve(0.8 - t, (0.0, 1.0)))]], 0.6, complete=True)
    assert starts(0.8) == [0.2, 0.6]


def test_subdivisions_at_a_late_pump_start_keep_the_first_excess_and_trace():
    """The first observation is inside a native Radau step. Absolute-time rounding
    gives the full step a different subdivision grid from the observed prefix."""
    source = """scenario "Two pipes with a late start"
    horizon 1000.00000012 h
tank:
    water: L = 4 L scale 1 L
    pump = 0
    signal = 0
    flow fill: SOURCE -> this.water
        request = formula(this.pump * (10000000 L/h + this.water * this.water / (1 L * 1 h)))
    flow bypass: SOURCE -> this.water
        request = formula(this.pump * this.water / (1 h))
    begin = event():
        after 1000 h:
            this.pump = 1
    observe = event():
        after 1000.00000007 h:
            this.signal = 1
tank.begin.start()
tank.observe.start()
"""
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    request = replace(model.configuration.request, everything=False, keys=(WATER,))

    def run(budget):
        config = replace(model.configuration, request=replace(request, pieces=budget))
        return Run(Plan.of(model.program, config)).run()

    whole = run(1000)
    assert whole.failure is None
    water = whole.history(WATER)
    starts = [p.t for p in water.pieces[: water.charged_pieces()]]
    observed = next(e.t for e in whole.entries('commit', 'tank.observe.step[0]'))
    limit = sum(1 for t in starts if t < observed)
    # Before, at, and after the observation as well as the earliest unstable
    # subdivision. An early cutoff could erase the observer's commit and finish.
    for budget in (2, 3, limit - 1, limit, limit + 1):
        direct = run(budget)
        assert direct.end == max(
            t for t in whole.manifest.check_times if sum(at < t for at in starts) <= budget
        )
        assert direct == requested(whole.within(budget), model.program)
