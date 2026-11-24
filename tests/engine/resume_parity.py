"""Assertions for a run continued from a breakpoint and the corresponding uninterrupted run."""

from dataclasses import fields, is_dataclass
from itertools import pairwise
from math import inf, isfinite, nextafter
from numbers import Integral, Real

from napkin.engine.timeline.record import Reader
from napkin.program.checkpoint import Checkpoint
from tests.engine.decision_trace import decisions
from tests.engine.record_jumps import moved_jumps, public_jump, short_piece_windows

RESUME_TOLERANCE = 1e-4


def _compare(a, b, scales, path, scale=1.0):
    """Keep identities, choices and discrete counts exact. Scale numeric observations in their own units."""
    if isinstance(a, bool) or isinstance(b, bool):
        assert a is b, path
    elif a == b:
        return
    elif isinstance(a, Integral) and isinstance(b, Integral):
        raise AssertionError((path, a, b))
    elif isinstance(a, Real) and isinstance(b, Real):
        limit = RESUME_TOLERANCE * max(scale, abs(a), abs(b))
        assert isfinite(a) and isfinite(b) and abs(a - b) <= limit, (path, a, b, limit)
    elif isinstance(a, tuple) and isinstance(b, tuple):
        if a and isinstance(a[0], str):
            scale = scales.get(a[0], scale)
        for i, (left, right) in enumerate(zip(a, b, strict=True)):
            _compare(left, right, scales, (path, i), scale)
    elif is_dataclass(a) and type(a) is type(b):
        for field in fields(a):
            _compare(getattr(a, field.name), getattr(b, field.name), scales, (path, field.name), scale)
    else:
        raise AssertionError((path, a, b))


def _entries(left, right, scales):
    prior = None
    for a, b in zip(left, right, strict=True):
        assert (a.round, a.kind, a.owner, a.part) == (b.round, b.kind, b.owner, b.part)
        if prior is not None:
            assert (prior[0] == a.t) == (prior[1] == b.t), (a, b)
        prior = a.t, b.t
        _compare(a.t, b.t, scales, (a.part, 'time'))
        if a.kind == 'draw':
            assert a.details == b.details
        else:
            _compare(a.details, b.details, scales, (a.kind, a.part))


def _scales(reader):
    unit_scales = {
        name: reader.units.scale(v.unit) if v.unit else 1.0 for name, v in reader.plan.values.items()
    }
    return unit_scales | reader.comparison_scales


def assert_trace_prefix(program, configuration, straight, paused):
    """The trace before the pause follows the uninterrupted run through that moment."""
    prefix = decisions(paused.trace[:-1])
    _entries(
        decisions(straight.trace)[: len(prefix)],
        prefix,
        _scales(Reader(straight, program)),
    )


def _readings(key, times, windows, first, second, scale):
    """Check both exterior edges on the same clock, including any landed cutoff balance."""
    edges = {max(times[0], min(t, times[-1])) for bounds in windows for t in bounds}
    for t in sorted(edges | set(times)):
        if t in edges or not any(low < t < high for low, high in windows):
            _compare(first(t), second(t), {}, (key, t), scale)


def assert_resume_parity(program, configuration, straight, resumed, *, sample_times=()):
    """Compare trace, coverage, stored and public values on the same clock and both sides of jumps."""
    assert type(straight) is type(resumed)
    if straight == resumed:
        return
    numerics = configuration.numerics
    checkpoint = isinstance(straight, Checkpoint)
    a, b = (straight.record, resumed.record) if checkpoint else (straight, resumed)
    ar, br = Reader(a, program), Reader(b, program)
    scales = _scales(ar)
    if checkpoint:
        for name in ('program', 'engine', 'configuration', 'breakpoints', 'edits'):
            assert getattr(straight, name) == getattr(resumed, name), name
        for name in ('state', 'stop', 'stops'):
            _compare(getattr(straight, name), getattr(resumed, name), scales, name)
    assert a.manifest == b.manifest
    _compare(a.end, b.end, scales, 'record cutoff')
    trace_a, trace_b = decisions(a.trace), decisions(b.trace)
    _entries(trace_a, trace_b, scales)
    event_times = {x.t: y.t for x, y in zip(trace_a, trace_b, strict=True)}
    _compare(a.failure, b.failure, scales, 'failure')

    through = min(a.end, b.end)
    for left, right in zip(a.histories, b.histories, strict=True):
        key = left.key
        assert key == right.key and type(left) is type(right)
        _compare(getattr(left, 'changes', ()), getattr(right, 'changes', ()), scales, (key, 'changes'))
        assert bool(left.pieces) == bool(right.pieces), key
        if not left.pieces:
            continue
        assert left.pieces[0].t == right.pieces[0].t, (key, 'coverage start')
        boundaries = {float(p.t) for h in (left, right) for p in h.pieces if p.t <= through}
        times = sorted(boundaries | {float(through)})
        probes = set(times) | {t for t in sample_times if times[0] <= t <= through}
        for start, end in pairwise(times):
            probes.add(nextafter(end, -inf))
            probes.add(start + (end - start) / 2)
        scale = scales.get(str(key.store or key), 1.0)
        windows = moved_jumps(left, right, crossing=numerics.crossing, scale=scale, event_times=event_times)
        stored = [(window.low, window.high) for window in windows]
        stored.extend(short_piece_windows(left, right, crossing=numerics.crossing, through=through))
        _readings(key, sorted(probes), stored, left.at, right.at, scale)
        if a.manifest.names(key):

            def first(t):
                return ar.value(key, t)

            def second(t):
                return br.value(key, t)

            public = [
                (jump.low, jump.high)
                for window in windows
                if (jump := public_jump(window, first, second, scale))
            ]
            _readings(key, sorted(probes), public, first, second, scale)
