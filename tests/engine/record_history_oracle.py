"""Compare the recorder's incremental assembly with a fresh assembly of its committed inputs."""

from copy import copy
from dataclasses import dataclass, field
from itertools import groupby, zip_longest
from operator import attrgetter
from unittest.mock import patch

from napkin.engine.timeline.record import FAILURES, Recorder
from napkin.program.checkpoint import encode


@dataclass
class RebuildReport:
    updates: int = 0
    closed_spans: list = field(default_factory=list)


@dataclass(frozen=True)
class ClosedSpanDifference:
    name: str
    first: float
    rejoins: float
    span: tuple
    count_delta: int
    first_piece: str


def _first_piece_difference(actual, expected):
    for index, (left, right) in enumerate(zip_longest(actual, expected)):
        if encode(left) != encode(right):
            return f'piece[{index}] live={repr(left)[:240]} rebuilt={repr(right)[:240]}'
    return 'pieces agree'


def _mismatch(live, ref, name, where):
    actual = live._histories[name].pieces if name in live._histories else ()
    expected = ref._histories[name].pieces if name in ref._histories else ()
    return (
        f'{name} {where}: live={len(actual)} pieces (counted {live._counted.get(name)}), '
        f'rebuilt={len(expected)} pieces (counted {ref._counted.get(name)}), '
        f'{_first_piece_difference(actual, expected)}'
    )


def _copy_tables(owner):
    """Detach mutable tables and lazy indexes; declarations, expressions and numeric inputs are read-only."""
    other = copy(owner)
    for name, value in vars(owner).items():
        if isinstance(value, (list, dict, set)):
            setattr(other, name, copy(value))
    return other


class _CommittedWays:
    """Membership can be read. A query that would enter a live solver must have a recorded observation."""

    def __init__(self, ways):
        self.set_of = dict(ways.set_of)
        self.result_of = dict(ways.result_of)

    def __getattr__(self, name):
        raise AssertionError(f'forced history rebuild needs an unobserved live physics query: {name}')


def _fresh(live, observed, closed):
    plan = _copy_tables(live.plan)
    plan.units = _copy_tables(plan.units)
    comparisons = plan.units.comparisons = _copy_tables(plan.units.comparisons)
    comparisons.units = plan.units
    comparisons.named = lambda name: plan.comparison_quantity(name, plan.comparison_scales)

    ref = Recorder(plan, dict(live.constants), dict(live.tolerance))
    ref.pieces = {name: list(pieces) for name, pieces in live.saved_pieces()}
    ref.transfers = {name: (start, list(items)) for name, (start, items) in live.transfers.items()}
    ref.trace = list(live.trace)
    ref.round = live.round
    ref.formulas = set(live.formulas)
    ref._wanted = None if live._wanted is None else set(live._wanted)
    ref.fits.ends = list(live.fits.ends)
    ref.fits.closed = closed

    run = ref.run = _copy_tables(live.run)
    run.plan, run.recorder = plan, ref
    run.ways = _CommittedWays(run.ways)
    run.stock_state = _copy_tables(run.stock_state)
    run.stock_state.run = run
    run.chance = _copy_tables(run.chance)
    run.chance.run, run.chance.plan = run, plan
    value_of = run.value_of

    def read(name):
        if name in observed:
            succeeded, value = observed[name]
            if succeeded:
                return value
            raise copy(value)
        return value_of(name)

    run.value_of = read
    return ref


def _closed_differences(name, actual, expected, closed, previous_end):
    """Each differing group must regain the identical outgoing piece by the end of an old fit."""
    if previous_end is None:
        return None
    old = [(a, b) for key, a, b in closed if key == name and b <= previous_end]
    if not old:
        return None

    def by_time(pieces):
        return {t: tuple(group) for t, group in groupby(pieces, attrgetter('t'))}

    left, right = by_time(actual), by_time(expected)
    first, delta, differences = None, 0, []
    for t in sorted(left.keys() | right.keys()):
        actual_group, rebuilt_group = left.get(t, ()), right.get(t, ())
        if encode(actual_group) != encode(rebuilt_group):
            if first is None:
                first = t
                first_piece = _first_piece_difference(actual_group, rebuilt_group)
            delta += len(actual_group) - len(rebuilt_group)
        elif first is not None:
            span = next(((a, b) for a, b in old if a < first < t <= b), None)
            if span is None:
                return None
            differences.append(ClosedSpanDifference(name, first, t, span, delta, first_piece))
            first, delta = None, 0
    return differences if first is None else None


def check_history_rebuilds(monkeypatch):
    """Install the boundary oracle and return its update count and strictly closed-span discrepancies.

    Comparison is before any stop overlay. Each rebuild starts with the fit decisions that were
    already committed on entry to that boundary. Reads of mutable filters can query live physics:
    replay the actual query result, and fail explicitly if the rebuild needs an unseen solver read.
    """
    advance = Recorder._advance
    report = RebuildReport()

    def checked(live, end):
        previous_end = live._as_of
        closed = {key: list(pieces) for key, pieces in live.fits.closed.items()}
        old_spans = tuple(closed)
        observed = {}
        value_of = live.run.value_of

        def observe(name):
            try:
                result = value_of(name)
            except FAILURES as problem:
                observed[name] = False, problem
                raise
            observed[name] = True, result
            return result

        with patch.object(live.run, 'value_of', observe):
            advance(live, end)
        ref = _fresh(live, observed, closed)
        advance(ref, end)
        report.updates += 1
        where = f'at {end} h, round {live.round}'
        assert ref.plan.size() == live.plan.size(), f'forced rebuild declared new inputs {where}'
        if live._histories.keys() != ref._histories.keys():
            name = min(live._histories.keys() ^ ref._histories.keys())
            raise AssertionError(f'retained history names differ: {_mismatch(live, ref, name, where)}')
        if live._counted.keys() != ref._counted.keys():
            name = min(live._counted.keys() ^ ref._counted.keys())
            raise AssertionError(f'counted names differ: {_mismatch(live, ref, name, where)}')
        permitted_delta = 0
        for name, actual in live._histories.items():
            expected = ref._histories[name]
            assert actual.key == expected.key, (
                f'history keys {actual.key} and {expected.key} differ for {name} {where}'
            )
            counted = name in live._counted
            if counted and (
                live._counted[name] != len(actual.pieces) or ref._counted[name] != len(expected.pieces)
            ):
                raise AssertionError(f'inconsistent counter: {_mismatch(live, ref, name, where)}')
            if encode(tuple(actual.pieces)) == encode(tuple(expected.pieces)):
                continue
            differences = _closed_differences(name, actual.pieces, expected.pieces, old_spans, previous_end)
            assert differences, f'prefix mismatch: {_mismatch(live, ref, name, where)}'
            if counted:
                explained = sum(d.count_delta for d in differences)
                assert live._counted[name] - ref._counted[name] == explained, (
                    f'unexplained count delta: {_mismatch(live, ref, name, where)}, '
                    f'closed spans explain {explained}'
                )
                permitted_delta += explained
            report.closed_spans.extend(differences)
        for label, recorder in (('live', live), ('rebuilt', ref)):
            extra = recorder._counted.keys() - recorder._histories.keys()
            assert not extra, f'{label} counted an absent history {where}: {min(extra)}'
            summed = sum(recorder._counted.values())
            assert recorder._total == summed, (
                f'{label} total {recorder._total} differs from sum of per-name counts {summed} {where}'
            )
        assert live._total - ref._total == permitted_delta, (
            f'total piece counts {where}: live={live._total}, rebuilt={ref._total}, '
            f'closed spans explain delta {permitted_delta}'
        )

    monkeypatch.setattr(Recorder, '_advance', checked)
    return report
