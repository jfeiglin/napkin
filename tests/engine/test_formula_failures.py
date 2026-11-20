"""A formula that cannot be evaluated inside a piece of its history (`timeline/record.py`, `formula`).

The record makes the history of a formula from the histories of what it reads, after the run. A
formula that cannot be evaluated holds `Unavailable` with the reason (D7). It failed only where it
was evaluated at the start of a piece: inside one (a yes/no whose interval is reversed once an end
that moves passes the other, agent E's finding) the failure escaped `run()` as a bare exception, and
a number that failed inside a piece held `Unavailable` over the whole piece, also where it has a
value. The rule: a formula holds its values up to where it cannot be evaluated, found to within the
crossing tolerance of the run as a change of a yes/no is, and `Unavailable` with the reason from
there, on every path that reads it: the record's own history (`Record.value`), the record's reader,
a report, and the run store, cold and warm at each horizon. The run itself never evaluates
these formulas, and finishes.

The expected values are worked by hand. A plant's `lo` rises from 0 L at 1 L/h toward `hi` = 1 L,
around x = 0.5 L: x is in [lo, hi] until 0.5 h, out of it until 1 h, and from 1 h the interval is
reversed, an error that names itself (`ops.REVERSED`). A tank drains from 3 L at 1 L/h, and a keyed
read selects a level by the tank's water in litres: the level of rank 2 to 1 h, of rank 1 to 2 h,
then none (no member has a key at or below the water).
"""

from __future__ import annotations

import textwrap
from dataclasses import replace

import pytest

from napkin import store
from napkin.core import ops
from napkin.engine import read, run
from napkin.engine.report import report
from napkin.model.compile import compile_text
from napkin.program.record import Key, Unavailable

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
CROSSING = 1e-6  # the times read stand this far from each change, which a record finds to 1e-8 h

PLANT = """
    scenario "Moving ends"
        horizon 4 h

    plant:
        lo: L = 0 L in [0,]
        hi: L = 1 L
        x: L = 0.5 L
        ok = formula(this.x in [this.lo, this.hi])
        level = formula(2 L if this.x in [this.lo, this.hi] else 3 L)
        flow fill: SOURCE -> this.lo
            request = 1 L/h
    """

LEVELS = """
    scenario "Moving key"
        horizon 4 h

    Level:
        input rank = 1
        height: L = 10 L

    low: Level
        rank = 1
        height = 10 L
    high: Level
        rank = 2
        height = 20 L

    tank:
        water: L = 3 L in [0,]
        flow drain: this.water -> SINK
            request = 1 L/h
        pick = formula(Level.instances.by(rank).at(this.water / 1 L).height)
    """

# Each formula: its path, the text of its model, and its values by hand on each stretch of time
# (from, to, value), the last `Unavailable` with the words of its reason.
CASES = {
    'yes/no': ('plant.ok', PLANT, [(0, 0.5, True), (0.5, 1, False), (1, 4, ops.REVERSED)]),
    'number': ('plant.level', PLANT, [(0, 0.5, 2.0), (0.5, 1, 3.0), (1, 4, ops.REVERSED)]),
    'keyed': (
        'tank.pick',
        LEVELS,
        [(0, 1, 20.0), (1, 2, 10.0), (2, 4, 'no member has a key at or below')],
    ),
}


def compiled(text):
    return compile_text(textwrap.dedent(text), UNITS)


def expected(stretches, t):
    """The value at t by hand, away from the ends of the stretches."""
    return next(value for start, end, value in stretches if start < t < end)


def agrees(found, value):
    """Whether a value read is the value by hand: a number, a yes/no, or `Unavailable` whose reason
    holds the text."""
    if isinstance(value, str):
        return isinstance(found, Unavailable) and value in found.reason
    return not isinstance(found, Unavailable) and found == pytest.approx(value)


def times(stretches, horizon):
    """Times inside each stretch up to the horizon, and on each side of its ends."""
    found = []
    for start, stop, _ in stretches:
        end = min(stop, horizon)
        if start < end:
            found += [start + CROSSING, 0.5 * (start + end), end - CROSSING]
    return found


@pytest.mark.parametrize('case', sorted(CASES))
def test_a_formula_holds_its_values_until_it_cannot_be_evaluated_and_unavailable_from_there(case):
    path, text, stretches = CASES[case]
    model = compiled(text)
    record = run(model.program, model.configuration)
    assert record.failure is None
    owner, name = path.split('.')
    key = Key(owner, (name,))
    at = times(stretches, 4)
    for t in at:
        assert agrees(record.value(key, t), expected(stretches, t)), (t, record.value(key, t))
    for found in (
        read(record, model.program, [path], at)[0].values,
        report(record, model.program, model.configuration, [path], at).values[0].values,
    ):
        for t, value in zip(at, found, strict=True):
            assert agrees(value, expected(stretches, t)), (t, value)


@pytest.mark.parametrize('case', sorted(CASES))
def test_the_run_store_gives_the_same_values_cold_and_warm_at_each_horizon(case, tmp_path):
    """The requests to 3 h and 4 h keep their own histories and each reads as a fresh run."""
    path, text, stretches = CASES[case]
    model = compiled(text)
    shorter = replace(model.configuration, request=replace(model.configuration.request, horizon=3))
    owner, name = path.split('.')
    key = Key(owner, (name,))
    at = times(stretches, 3)
    with store.use(tmp_path):
        cold = store.run(model.program, model.configuration)
        warm = store.run(model.program, model.configuration)
        short = store.run(model.program, shorter)
        again = store.run(model.program, shorter)
    fresh = run(model.program, shorter)
    # One record however the store got there, its histories included.
    assert warm == cold and short == again == fresh
    for record in (cold, warm, short, again, fresh):
        assert record.failure is None
        for t in at:
            assert agrees(record.value(key, t), expected(stretches, t)), (t, record.value(key, t))
        for t, value in zip(at, read(record, model.program, [path], at)[0].values, strict=True):
            assert agrees(value, expected(stretches, t)), (t, value)
