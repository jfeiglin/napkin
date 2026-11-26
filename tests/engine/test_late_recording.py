"""A selected observation first needs an already-moving stock when a collection member joins."""

from dataclasses import replace
from math import exp

import pytest

from napkin.engine.timeline import Plan, Run, read, run
from napkin.engine.timeline.record import Reader, key_of
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.record import Unavailable
from tests.engine.record_history_oracle import check_history_rebuilds
from tests.engine.resume_parity import assert_resume_parity
from tests.engine.test_frozen_occurrences import in_a_fresh_process
from tests.engine.test_sparse_rate_snapshots import SOURCE as SPARSE_METER


def meter_observation(meter=SPARSE_METER, setup=''):
    source = (
        meter
        + """    prior = formula(this.meter * 3)
    worker = event():
        observation = formula(this.prior + 1 L)
        after 0.2 h
    total = formula(sum(this.worker.occurrences.observation))
    clock = event():
        after 0.3 h:
            this.worker.start()
    watch = event():
        after 0.3 h

yard.clock.start()
yard.watch.start()
"""
        + setup
    )
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    request = replace(
        model.configuration.request, everything=False, keys=(key_of(model.program, 'yard.total'),)
    )
    return model, replace(model.configuration, request=request)


def observation(t):
    # meter' = 3 * meter + 4 * t, with meter(0) = 1 L. The worker reads 3 * meter + 1 L.
    return (13 * exp(3 * t) - 12 * t - 1) / 3


def test_a_selected_total_uses_the_moving_stock_from_the_join(monkeypatch):
    model, selected = meter_observation()
    program = model.program
    full = run(program, model.configuration)
    check_history_rebuilds(monkeypatch)
    result = run(program, selected)
    assert full.failure is None and result.failure is None
    assert result.trace == full.trace

    times = (0.2, 0.3, 0.45, 1.0)
    expected = (0, observation(0.3), observation(0.45), observation(0.5))
    for record in (full, result):
        (total,) = read(record, program, ('yard.total',), times)
        assert total.values == pytest.approx(expected, rel=1e-7)

    meter = result.history(key_of(program, 'yard.meter'))
    assert meter.pieces[0].t == 0.3
    with pytest.raises(LookupError):
        meter.at(0.2)
    # Read the formula as a dependency, bypassing public rejection of an unrequested path.
    reader = Reader(result, program)
    try:
        prior = reader.at('yard.prior', 0.2)
    except LookupError:
        pass
    else:
        assert isinstance(prior, Unavailable)
    assert reader.at('yard.prior', 0.45) == pytest.approx(observation(0.45) - 1, rel=1e-7)


def test_a_checkpoint_between_siblings_sees_the_newly_needed_stock(tmp_path):
    model, selected = meter_observation()
    program = model.program
    straight = run(program, selected)
    live = Run(Plan.of(program, selected), (Breakpoint('yard.watch.step[0]'),))
    checkpoint = live.run()
    assert isinstance(checkpoint, Checkpoint) and checkpoint.stop.t == 0.3
    assert any(e.kind == 'start' and e.owner == 'yard.worker#0' for e in checkpoint.record.trace)
    meter_key = key_of(program, 'yard.meter')
    total_key = key_of(program, 'yard.total')
    assert checkpoint.record.history(meter_key).at(0.3) == pytest.approx((observation(0.3) - 1) / 3)
    assert checkpoint.record.history(total_key).at(0.3) == pytest.approx(observation(0.3))
    (total,) = read(checkpoint.record, program, ('yard.total',), (0.2, 0.3))
    assert total.values == pytest.approx((0, observation(0.3)), rel=1e-7)
    saved_recorder = dict(dict(checkpoint.saved)['recorder'])
    assert dict(saved_recorder['coverage_starts'])['yard.meter'] == 0.3
    assert all(t != 0.3 for t, _, _ in live.recorder.pieces.get('yard.meter', ()))
    cached = live.recorder._histories.get('yard.meter')
    assert cached is None or all(piece.t != 0.3 for piece in cached.pieces)
    continuation = live.resume()
    assert_resume_parity(program, selected, straight, continuation)
    assert sum(piece.t == 0.3 for piece in continuation.history(meter_key).pieces) == 1
    assert_resume_parity(program, selected, straight, in_a_fresh_process(program, checkpoint, tmp_path))


def test_the_first_total_piece_at_the_join_exceeds_a_one_piece_budget():
    model, selected = meter_observation()
    configuration = replace(selected, request=replace(selected.request, pieces=1))
    straight = run(model.program, configuration)
    assert straight.failure is not None and straight.failure.t == 0.3
    assert straight.failure.detail('budget') == 1
    assert [p.t for p in straight.history(key_of(model.program, 'yard.total')).pieces] == [0]
    stopped = run(model.program, configuration, (Breakpoint('yard.watch.step[0]'),))
    assert stopped == straight


def test_skipped_stock_remains_identifiable_after_its_sparse_producer_retires(tmp_path):
    # The two parallel inflows share a stock. While the pump runs, meter' = 2 * meter.
    meter = """scenario "Meter filled before the first observation"
    horizon 1 h
yard:
    meter: L = 1 L
    pump = event():
        flow first: SOURCE -> this.meter
            request = formula(this.meter / (1 h))
        flow second: SOURCE -> this.meter
            request = formula(this.meter / (1 h))
        after 0.2 h
"""
    model, selected = meter_observation(meter, 'yard.pump.start()\n')
    program = model.program
    live = Run(Plan.of(program, selected), (Breakpoint('yard.clock.step[0]'),))
    before_join = live.run()
    assert isinstance(before_join, Checkpoint) and before_join.stop.t == 0.3
    assert any(
        e.kind == 'finish' and e.owner == 'yard.pump#0' and e.t == 0.2 for e in before_join.record.trace
    )
    saved_recorder = dict(dict(before_join.saved)['recorder'])
    assert dict(saved_recorder['coverage_starts'])['yard.meter'] is None

    result = live.resume()
    assert_resume_parity(program, selected, run(program, selected), result)
    assert_resume_parity(program, selected, result, in_a_fresh_process(program, before_join, tmp_path))
    stock = result.history(key_of(program, 'yard.meter'))
    assert stock.pieces[0].t == 0.3
    with pytest.raises(LookupError):
        stock.at(0.15)
    (total,) = read(result, program, ('yard.total',), (0.2, 0.3, 0.45, 1.0))
    settled = 3 * exp(0.4) + 1
    assert total.values == pytest.approx((0, settled, settled, settled), rel=1e-7)
