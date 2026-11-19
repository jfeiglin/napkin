"""The classes of a trigger's condition, as the engine reads them (the class tables of the old analysis,
`tests/model/test_analysis.py` and `tests/model/test_structure_checks.py`, as runs).

A condition is read at every round on the settled state; between moments, each of its comparisons
that reads what moves gives the first time at which its answer can change (`timeline/triggers.py`).
So a discrete condition fires at the commit that makes it true, a clock at its time, a crossing of a
store at its first contact, also through formulas, behind a gate or with a clock, and comparisons of
two stores or of the time with a store at the root of their lines. A strict comparison of what moves
has no first instant and is a diagnostic. In the fixture a tank holds 10 L and drains at 1 L/h, a
basin fills from 0 at 1 L/h, a clock opens a gate at 2 h and another counts a call at 4 h; each time
below is worked by hand from those lines.
"""

from __future__ import annotations

import pytest

from napkin.engine import run
from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    event,
    flow,
    formula,
    input_,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request


def liters(number):
    return q(number, 'L')


def hours(number):
    return q(number, 'h')


def at_time(name, at, *body):
    return event(
        name,
        when(t >= hours(at), start(getattr(this, name)), reset=reset_when(False)),
        after(hours(0), *body),
    )


def fired(condition):
    """The times at which a trigger on `condition` fires, at most once, in the fixture."""
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    b.entity(
        'plant',
        input_('level0', 'L', 6),
        input_('fill_time', 'h', 3),
        input_('drain_rate', 'L/h', 1),
        value('water', 'L', 10, lower=0),
        value('basin', 'L', 0, lower=0),
        value('half', 'L', formula(this.level0 / 2)),
        value('open', BOOL, False),
        value('calls', '', 0),
        value('noticed_at', 'h', 0),
        flow('drain', this.water, SINK, request=this.drain_rate),
        flow('fill', SOURCE, this.basin, request=q(1, 'L/h')),
        at_time('opening', 2, assign(this.open, True), assign(this.noticed_at, t)),
        at_time('call', 4, add(this.calls, 1)),
        event('alarm', when(condition, start(this.alarm), reset=reset_when(False))),
    )
    record = run(b.finish(), Configuration(Request(12)))
    if record.failure is not None:
        return record.failure.detail('message')
    return [entry.t for entry in record.entries('fire', 'plant.alarm.when[0]')]


CLASSES = [
    # Discrete: what it reads changes only at commits.
    ('a gate and a count', lambda: this.open & (this.calls > 0), 4),
    # Clocks: the time against what holds between moments.
    ('a clock', lambda: t >= this.fill_time, 3),
    ('a clock written the other way', lambda: this.fill_time <= t, 3),
    ('a clock from a time that a stage wrote', lambda: t - this.noticed_at >= this.fill_time, 5),
    # Crossings: a store that moves against what holds between moments, also through a formula.
    ('a falling store', lambda: this.water <= this.level0 / 2, 7),
    ('a falling store written the other way', lambda: this.level0 / 2 >= this.water, 7),
    ('a falling store against a formula', lambda: this.water <= this.half, 7),
    ('a rising store', lambda: this.basin >= this.level0, 6),
    (
        'a crossing behind a gate and a clock',
        lambda: this.open & (this.basin >= this.level0) & (t >= this.fill_time),
        6,
    ),
    ('a crossing that holds before its gate opens', lambda: (this.basin >= liters(1)) & this.open, 2),
    # Two values that move, and the time against a store: lines meet at the root of their difference.
    ('two stores', lambda: this.basin >= this.water, 5),
    ('the time against a store', lambda: t >= this.water / this.drain_rate, 5),
    ('two crossings', lambda: (this.water <= this.level0) & (this.basin >= this.level0), 6),
]


@pytest.mark.parametrize(
    ('make', 'expected'), [case[1:] for case in CLASSES], ids=[case[0] for case in CLASSES]
)
def test_a_condition_fires_at_the_time_of_its_class(make, expected):
    assert fired(make()) == pytest.approx([expected], abs=1e-9)


@pytest.mark.parametrize(
    'make',
    [
        lambda: this.water > this.level0,
        lambda: this.water < this.basin,
        lambda: t > this.water / this.drain_rate,
    ],
    ids=['a strict falling store', 'two stores, strictly', 'the time, strictly'],
)
def test_a_strict_comparison_of_what_moves_is_a_diagnostic(make):
    assert 'strict threshold' in fired(make())
