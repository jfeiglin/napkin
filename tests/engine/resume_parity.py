"""Assertions for a run continued from a breakpoint and the corresponding uninterrupted run."""

from collections import defaultdict
from dataclasses import fields, is_dataclass, replace
from itertools import pairwise
from math import inf, isfinite, nextafter
from numbers import Integral, Real

import pytest

from napkin.engine.timeline.record import Reader
from napkin.program.checkpoint import Checkpoint
from tests.engine.band_contacts import band_preemptions, decision_identity, paired_fire_details
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


def _entries(left, right, scales, horizon):
    shifts = defaultdict(set)
    for a, b in zip(left, right, strict=True):
        assert decision_identity(a) == decision_identity(b), (a, b)
        times = [(a.t, b.t)]
        if a.kind == 'contact':
            times.append((a.detail('located'), b.detail('located')))
        for old, new in times:
            assert abs(old - new) <= 1e-6 * horizon, (a.part, old, new)
            shifts[old].add(new)
        if a.kind == 'draw':
            assert a.details == b.details
        elif a.kind == 'contact':
            # The identity contains the surface. The two clocks were checked above.
            def observations(entry):
                details = dict(entry.details)
                details.pop('located')
                details['near'] = tuple((origin, gap, band) for origin, _, gap, band in details['near'])
                return tuple(details.items())

            _compare(observations(a), observations(b), scales, ('contact', a.part))
        else:
            left_details, right_details = paired_fire_details(a, b)
            _compare(left_details, right_details, scales, (a.kind, a.part))
    return shifts


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
        straight.manifest.horizon,
    )


def _readings(key, times, windows, first, second, scale):
    """Check both exterior edges on the same clock, including any landed cutoff balance."""
    edges = {max(times[0], min(t, times[-1])) for bounds in windows for t in bounds}
    for t in sorted(edges | set(times)):
        if t in edges or not any(low < t < high for low, high in windows):
            _compare(first(t), second(t), {}, (key, t), scale)


def assert_same_manifest_settings(*records):
    """A resumed solver can use a different step sequence. Each record keeps its own check times."""
    expected = replace(records[0].manifest, check_times=None)
    for record in records:
        assert replace(record.manifest, check_times=None) == expected
        times = record.manifest.check_times
        assert times and times[0] == 0 and times[-1] == record.end
        assert all(earlier < later for earlier, later in pairwise(times))
        if record.failure is not None and (budget := record.failure.detail('budget')) is not None:
            charged = sum(h.charged_pieces() for h in record.histories if record.manifest.names(h.key))
            assert charged <= budget and record.failure.round == 0
            assert all(p.t < record.end for h in record.histories for p in h.pieces)


def assert_resume_parity(program, configuration, straight, resumed, *, sample_times=()):
    """Compare trace, coverage, stored and public values on the same clock and both sides of jumps."""
    assert type(straight) is type(resumed)
    checkpoint = isinstance(straight, Checkpoint)
    a, b = (straight.record, resumed.record) if checkpoint else (straight, resumed)
    assert_same_manifest_settings(a, b)
    if straight == resumed:
        return
    numerics = configuration.numerics
    ar, br = Reader(a, program), Reader(b, program)
    scales = _scales(ar)
    if checkpoint:
        for name in ('program', 'engine', 'configuration', 'breakpoints', 'edits'):
            assert getattr(straight, name) == getattr(resumed, name), name
        for name in ('state', 'stop', 'stops'):
            _compare(getattr(straight, name), getattr(resumed, name), scales, name)
    _compare(a.end, b.end, scales, 'record cutoff')
    trace_a, trace_b = decisions(a.trace), decisions(b.trace)
    omissions = band_preemptions(trace_a, trace_b, ar, br, numerics.crossing)
    skipped = {'before': set(), 'after': set()}
    for case in omissions:
        skipped[case.contact_side].update(case.contact_indices)
    trace_a = [e for i, e in enumerate(trace_a) if i not in skipped['before']]
    trace_b = [e for i, e in enumerate(trace_b) if i not in skipped['after']]
    event_times = _entries(trace_a, trace_b, scales, a.manifest.horizon)
    births = {x.owner: (x.t, y.t) for x, y in zip(trace_a, trace_b, strict=True) if x.kind == 'start'}
    _compare(a.failure, b.failure, scales, 'failure')

    through = min(a.end, b.end)
    for left, right in zip(a.histories, b.histories, strict=True):
        key = left.key
        assert key == right.key and type(left) is type(right)
        _compare(getattr(left, 'changes', ()), getattr(right, 'changes', ()), scales, (key, 'changes'))
        assert bool(left.pieces) == bool(right.pieces), key
        if not left.pieces:
            continue
        first_times = left.pieces[0].t, right.pieces[0].t
        begin = max(first_times)
        if first_times[0] != first_times[1]:
            assert births.get(key.owner) == first_times, (key, 'coverage start', first_times)
            low = max(0.0, min(first_times) - numerics.crossing)
            if low < min(first_times):
                for history in (left, right):
                    with pytest.raises(LookupError):
                        history.at(low)
                if a.manifest.names(key):
                    _compare(ar.value(key, low), br.value(key, low), scales, (key, low))
            begin = min(through, begin + numerics.crossing)
        boundaries = {float(p.t) for h in (left, right) for p in h.pieces if begin <= p.t <= through}
        times = sorted(boundaries | {float(begin), float(through)})
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
