"""Refreshing a curved global formula twice at one moment preserves its fitted pieces."""

from math import exp, nextafter

import numpy as np
import pytest

from napkin.engine.errors import SimulationError
from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline import record as recording
from napkin.engine.timeline.record import Recorder, fitted
from napkin.program.build import Builder, add, after, call, event, formula, named, q, start, t, this, value
from napkin.program.config import Configuration, Numerics, Request
from napkin.program.record import Key
from tests.engine.record_history_oracle import check_history_rebuilds


def test_fit_preserves_held_linear_and_curved_columns():
    def values(times):
        return np.column_stack((np.full_like(times, 11), 2 - 3 * times, times**2 + 1))

    held, line, curved = fitted(values, 2.0, 4.0, np.full(3, 1e-12))
    assert held == [(2.0, 11.0, 0.0)]
    for pieces, expected_degree, expected in ((line, 1, -7.0), (curved, 8, 10.0)):
        (piece,) = pieces
        at, opening, shape = piece
        assert at == 2.0
        assert len(shape.coefficients) == expected_degree + 1
        assert opening + shape.increase(3.0 - at) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize(
    'neighbour', [lambda ts: ts**2, lambda ts: np.abs(ts - 3.1)], ids=['smooth', 'kinked']
)
def test_a_line_fits_to_the_same_bytes_alone_and_beside_another_value(neighbour):
    """A value's pieces do not depend on what is fitted beside it: neither where they start (a kinked
    neighbour is cut many times) nor their last bits (a matrix product of two columns rounds a line's
    coefficients otherwise)."""

    def line(times):
        return 0.1 - 0.2 * times

    tolerance = np.full(2, 1e-12)
    (alone,) = fitted(lambda times: line(times)[:, None], 2.0, 4.0, tolerance[:1])
    beside, _ = fitted(lambda times: np.column_stack((line(times), neighbour(times))), 2.0, 4.0, tolerance)
    assert len(alone) == 1 and repr(beside) == repr(alone)


def _fit_or_failure(fit):
    try:
        return repr(fit())
    except SimulationError as problem:
        return f'failure: {problem}'


@pytest.mark.parametrize('seed', range(60))
def test_the_fit_of_one_value_gives_the_bytes_of_the_fit_of_columns(seed):
    """The fit of one value in floats (`_fitted_one`, for a formula and the gap of two operands) gives
    the pieces of `fitted` with one column, byte for byte: a held, a straight, a smooth, a kinked, a
    jumping and a NaN value, on short and long spans, to small and large tolerances."""
    rng = np.random.default_rng(seed)
    start = float(rng.choice([0.0, 2.0, 1000.0]))
    end = start + float(rng.choice([1e-10, 1e-3, 0.5, 7.0]))
    tolerance = float(rng.choice([1e-12, 1e-8, 1e-3]))
    a, b, c = rng.normal(size=3).tolist()
    middle = start + float(rng.uniform(0.2, 0.8)) * (end - start)
    shapes = (
        lambda t: 11.0,
        lambda t: a + b * t,
        lambda t: a * np.sin(b * t) + c * t * t,
        lambda t: a * abs(t - middle),
        lambda t: a if t < middle else b,
        lambda t: a if t < middle else float('nan'),
    )
    shape = shapes[seed % len(shapes)]
    columns = _fit_or_failure(
        lambda: fitted(
            lambda times: np.array([[float(shape(t))] for t in times]), start, end, np.array([tolerance])
        )[0]
    )
    one = _fit_or_failure(
        lambda: recording._fitted_one(
            lambda times: [float(shape(t)) for t in times], start, end, np.float64(tolerance)
        )
    )
    assert one == columns


def test_a_value_past_the_cut_limit_is_a_failure_by_its_name(monkeypatch):
    """The cut limit counts the cuts of each value. A value whose fit still misses after them is a
    failure by its name; a smooth value beside it is cut as it would be alone."""
    monkeypatch.setattr(recording, 'MOST', 8)

    def smooth(times):
        return np.exp(times)

    tolerance = np.full(2, 1e-12)
    (alone,) = fitted(lambda times: smooth(times)[:, None], 0.0, 2.0, tolerance[:1])
    (again,) = fitted(lambda times: smooth(times)[:, None], 0.0, 2.0, tolerance[:1], ['tank.smooth'])
    assert len(alone) > 1 and repr(again) == repr(alone)
    with pytest.raises(SimulationError, match=r'the fit of tank\.rough from .* needed more than 8 cuts'):
        fitted(
            lambda times: np.column_stack((np.sin(1e6 * times), smooth(times))),
            0.0,
            2.0,
            tolerance,
            ['tank.rough', 'tank.smooth'],
        )


def test_a_fast_value_at_a_late_time_is_held_to_the_spacing_of_its_times():
    """A float holds a time near 1 h only to about 1e-16 h, in which a value that moves 1e8 an hour
    changes by about 1e-8: a fit holds it to that, not to a tolerance below it."""

    def line(times):
        return (751 + 1e8 * (0.9999925 - times))[:, None]

    (pieces,) = fitted(line, 0.99999, 1.0, np.full(1, 1e-16), ['yard.stock'])
    ((at, opening, shape),) = pieces
    for time in (0.99999, 0.999992, 0.9999925, 0.999999):
        made = opening + shape.increase(time - at)
        assert abs(made - line(np.array([time]))[0, 0]) <= recording.SAMPLED * 1e8 * np.spacing(1.0)


def test_a_steep_part_elsewhere_does_not_widen_a_quiet_part():
    def quiet(times):
        return 1e-4 * np.sin(3 * times)

    def kinked(times):
        return np.where(times < 1, quiet(times), quiet(1.0) + 1e12 * (times - 1))

    tolerance = np.full(1, 1e-12)
    (alone,) = fitted(lambda times: quiet(times)[:, None], 0.0, 1.0, tolerance)
    (both,) = fitted(lambda times: kinked(times)[:, None], 0.0, 2.0, tolerance)
    assert len(alone) > 1 and repr([piece for piece in both if piece[0] < 1]) == repr(alone)


def curve_program():
    builder = Builder({'h': {'time': 1}})
    builder.entity(
        'plant',
        value('curve', '', formula(call('exp', t / q(1, 'h')))),
        value('count', '', 0),
        event('tick', after(q(1, 'h'), add(this.count, 1))),
    )
    builder.setup(start(named('plant').tick))
    return builder.finish()


def repeated_curve_checks(monkeypatch):
    key = Key('plant', ('curve',))
    request = Request(2, everything=False, keys=(key,))
    live = Run(Plan.of(curve_program(), Configuration(request)))
    checks = {}
    advance = Recorder._advance
    derive = Recorder._derived_history
    visits = []

    def count_visits(recorder, name, value, end, since):
        if recorder is live.recorder and name == 'plant.curve':
            visits.append(end)
        return derive(recorder, name, value, end, since)

    def repeat(recorder, end):
        advance(recorder, end)
        if recorder is live.recorder and end in (1, 2) and end not in checks:
            name = 'plant.curve'
            before = tuple(recorder._histories[name].pieces)
            # The tick provides a real boundary. Explicitly request the same formula again
            # because the independent count posting does not change any of its inputs.
            recorder._dirty.add(name)
            count = len(visits)
            advance(recorder, end)
            assert visits[count:] == [end]
            checks[end] = (before, tuple(recorder._histories[name].pieces))

    monkeypatch.setattr(Recorder, '_derived_history', count_visits)
    monkeypatch.setattr(Recorder, '_advance', repeat)
    return live.run(), checks


def test_refreshing_a_curve_twice_at_a_moment_keeps_its_exact_pieces(monkeypatch):
    reference = check_history_rebuilds(monkeypatch)
    record, checks = repeated_curve_checks(monkeypatch)
    assert record.failure is None
    assert tuple(checks) == (1, 2)
    for end, (before, again) in checks.items():
        assert before[-1].curve is not None and before[-1].t < end
        assert again == before
        exact = exp(end)
        assert abs(again[-1].at(end) - exact) <= Numerics().atol_factor * max(1.0, abs(exact))
    times = (0, 0.5, 1, 1.5, 2)
    (public,) = read(record, curve_program(), ('plant.curve',), times)
    assert tuple(public.values) == tuple(exp(t) for t in times)
    assert record.history(Key('plant', ('curve',))).pieces == checks[2][1]
    assert reference.updates >= 4
    assert not reference.closed_spans


def test_a_bend_one_float_before_a_moment_uses_the_moment_boundary(monkeypatch):
    moment = 1.0
    root = nextafter(moment, 0.0)
    builder = Builder({'h': {'time': 1}})
    builder.entity(
        'plant',
        value('offset', '', 0),
        value('reading', '', formula(this.offset + call('max', root - t / q(1, 'h'), 0))),
        event('tick', after(q(moment, 'h'), add(this.offset, 10))),
    )
    builder.setup(start(named('plant').tick))
    key = Key('plant', ('reading',))
    plan = Plan.of(builder.finish(), Configuration(Request(2, everything=False, keys=(key,))))

    # Observe the root before the recorder chooses which fit boundaries to keep.
    located = []
    locate = recording.crossing_time

    def observe(gap, lo, hi, *, accepted):
        found = locate(gap, lo, hi, accepted=accepted)
        if found is not None:
            located.append((found, gap(found)))
        return found

    monkeypatch.setattr(recording, 'crossing_time', observe)
    result = Run(plan).run()
    assert result.failure is None
    assert (root, 0.0) in located
    history = result.history(key)
    assert [p.t for p in history.pieces if abs(p.t - moment) <= plan.numerics.crossing] == [moment]
    assert history.at(0.5) == pytest.approx(root - 0.5, abs=plan.numerics.atol_factor, rel=0)
    assert history.at(root) == pytest.approx(0, abs=plan.numerics.atol_factor, rel=0)
    assert history.at(moment) == history.at(2) == 10


def test_a_formula_keeps_both_input_boundaries_around_a_short_transition():
    builder = Builder({'h': {'time': 1}})
    builder.entity(
        'plant',
        value('recovery', '', 0),
        value('loss', '', formula(this.recovery + 1)),
    )
    program = builder.finish()
    live = Run(Plan.of(program, Configuration(Request(2))))
    live.prepare()
    begin = 1.0
    landed = begin + live.plan.numerics.crossing / 4
    # Supply the short moving piece and the value posted at its end directly to the recorder.
    live.recorder.add_pieces('plant.recovery', [(begin, 5.0, 2.0), (landed, 12.0, 0.0)])
    record = live.recorder.record(2, ongoing=True)

    loss = record.history(Key('plant', ('loss',)))
    assert [p.t for p in loss.pieces if begin <= p.t <= landed] == [begin, landed]
    times = (begin, nextafter(landed, begin), landed, nextafter(landed, 2.0))
    expected = (6.0, 6.0 + 2.0 * (times[1] - begin), 13.0, 13.0)
    assert tuple(loss.at(t) for t in times) == pytest.approx(expected, rel=live.plan.numerics.atol_factor)
    (public,) = read(record, program, ('plant.loss',), times)
    assert tuple(public.values) == expected


def test_a_later_cutoff_preserves_a_closed_fit_through_a_formula_chain():
    from dataclasses import replace

    from napkin.model.compile import compile_text

    source = """scenario "Closed fits at a nearby horizon"
    horizon 1.00000001 h
tank:
    water: L = 0 L
    flow fill: SOURCE -> this.water
        request = 1 L/h
    source = formula(exp(10 * this.water / (1 L)))
    square = formula(this.source ** 2)
    fourth = formula(this.square ** 2)
    marker = 0
    tick = event():
        after 1 h:
            this.marker = 1
tank.tick.start()
"""
    model = compile_text(source, {'h': {'time': 1}, 'L': {'volume': 1}})
    keys = tuple(Key('tank', (name,)) for name in ('source', 'square', 'fourth'))
    config = model.configuration
    request = replace(config.request, everything=False, keys=keys)

    def simulate(req):
        return Run(Plan.of(model.program, replace(config, request=req))).run()

    closed = simulate(replace(request, horizon=1))
    extended = simulate(request)
    assert closed.failure is None and extended.failure is None
    for key, charged in zip(keys, (16, 32, 64), strict=True):
        earlier = closed.history(key).pieces
        later = extended.history(key).pieces
        assert len(earlier) == charged
        assert tuple(piece for piece in later if piece.t < 1) == earlier
        assert any(piece.t == 1 for piece in later)

    for budget in (8, 9, 10):
        limited = simulate(replace(request, pieces=budget))
        assert limited.failure is not None and limited.failure.detail('budget') == budget
        assert limited == recording.requested(extended.within(budget), model.program)
