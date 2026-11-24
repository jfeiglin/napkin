"""Refreshing a curved global formula twice at one moment preserves its fitted pieces."""

from math import exp

from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.record import Recorder
from napkin.program.build import Builder, add, after, call, event, formula, named, q, start, t, this, value
from napkin.program.config import Configuration, Numerics, Request
from napkin.program.record import Key
from tests.engine.record_history_oracle import check_history_rebuilds


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
    for end, (before, after) in checks.items():
        assert before[-1].curve is not None and before[-1].t < end
        assert after == before
        exact = exp(end)
        assert abs(after[-1].at(end) - exact) <= Numerics().atol_factor * max(1.0, abs(exact))
    times = (0, 0.5, 1, 1.5, 2)
    (public,) = read(record, curve_program(), ('plant.curve',), times)
    assert tuple(public.values) == tuple(exp(t) for t in times)
    assert record.history(Key('plant', ('curve',))).pieces == checks[2][1]
    assert reference.updates >= 4
    assert not reference.closed_spans
