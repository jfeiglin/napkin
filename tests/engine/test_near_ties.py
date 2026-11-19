"""Near-ties (change 10; `triggers.py`, `moment.near_ties`): a firing or a test of a stage that was
decided within tolerance of its boundary is marked as the detail `near` of its trace entry, and the
engine computes nothing more precisely. The cases are worked by hand: in floats, 0.1 + 0.2 exceeds 0.3
by one unit in the last place, far inside a store's tolerance of 1e-10 of its size (1 L here), while
0.30001 exceeds it by far more.
"""

from __future__ import annotations

import pytest

from napkin.engine import run
from napkin.program.build import (
    BOOL,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    case,
    count,
    event,
    flow,
    formula,
    if_,
    named,
    q,
    start,
    switch,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request
from tests.program.examples import UNITS

TOLERANCE = 1e-10  # the tolerance of a store of size 1 L: `atol_factor` 1e-10 times it
OVER = (0.1 + 0.2) - 0.3  # one unit in the last place of 0.3


def tank(*parts, second=0.2):
    """A tank whose level rises by 0.1 L and then by `second` at 1 h, and the parts given."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('level', 'L', 0, lower=0),
        value('flag', 'L', 0),
        event('top', after(q(1, 'h'), add(this.level, q(0.1, 'L')), add(this.level, q(second, 'L')))),
        *parts,
    )
    b.setup(
        start(named('tank').top),
        *(start(getattr(named('tank'), part.name)) for part in parts if part.name == 'check'),
    )
    return run(b.finish(), Configuration(Request(3)))


def alarm(test):
    return event('alarm', when(test, start(this.alarm)), after(q(0, 'h')))


def test_a_firing_within_tolerance_of_its_threshold_is_marked():
    record = tank(alarm(this.level >= q(0.3, 'L')))
    (entry,) = record.entries('fire')
    ((origin, comparison, difference, tolerance),) = entry.detail('near')
    assert (entry.t, origin) == (1, 'tank.alarm.when[0]')
    assert comparison == "tank.level >= q(0.3, 'L')"
    assert difference == OVER and tolerance == pytest.approx(TOLERANCE)
    assert record.near_ties() == ((entry, entry.detail('near')[0]),)


def test_a_firing_by_more_than_the_tolerance_is_not():
    record = tank(alarm(this.level >= q(0.3, 'L')), second=0.20001)
    (entry,) = record.entries('fire')
    assert entry.detail('near') is None and record.near_ties() == ()


def test_a_comparison_inside_a_boolean_formula_is_read_through_it():
    record = tank(value('ready', BOOL, formula(this.level >= q(0.3, 'L'))), alarm(this.ready))
    (entry,) = record.entries('fire')
    assert [tie[1] for tie in entry.detail('near')] == ["tank.level >= q(0.3, 'L')"]


def test_a_crossing_and_a_clock_move_through_their_thresholds():
    """A tally that fills at 1 L/h crosses 2 L at 2 h, and the clock reaches 2.5 h: both differ by far
    more than their tolerance an instant later, so the firings follow from when they cross."""
    b = Builder(UNITS)
    b.entity(
        'meter',
        value('filled', 'L', 0, lower=0),
        flow('fill', SOURCE, this.filled, request=q(1, 'L/h')),
        event('full', when(this.filled >= q(2, 'L'), start(this.full)), after(q(0, 'h'))),
        event('late', when(t >= q(2.5, 'h'), start(this.late)), after(q(0, 'h'))),
    )
    record = run(b.finish(), Configuration(Request(3)))
    assert [entry.t for entry in record.entries('fire')] == pytest.approx([2, 2.5])
    assert record.near_ties() == ()


def test_an_exact_comparison_of_a_count_has_no_tolerance():
    record = tank(alarm(count(this.top.occurrences) >= 1))
    (entry,) = record.entries('fire')
    assert entry.t == 0 and entry.detail('near') is None


def test_an_if_and_a_guard_of_a_stage_are_marked_in_its_commit():
    """At 2 h the level is 0.1 + 0.2: the `if` and the guard each read it against 0.3."""
    check = event(
        'check',
        after(q(2, 'h'), if_(this.level >= q(0.3, 'L'), (assign(this.flag, q(1, 'L')),))),
        after(q(0, 'h'), assign(this.flag, q(2, 'L')), when=this.level >= q(0.3, 'L')),
    )
    record = tank(check)
    commits = {entry.part: entry for entry in record.entries('commit')}
    ((origin, *_),) = commits['tank.check.step[0]'].detail('near')
    assert origin == 'tank.check.step[0].do[0]'
    ((origin, *_),) = commits['tank.check.step[1]'].detail('near')
    assert origin == 'tank.check.step[1]'


def test_the_guard_of_a_case_is_marked_in_its_commit():
    b = Builder(UNITS)
    mode = b.enum('enum[ON, OFF]', 'ON', 'OFF')
    b.entity(
        'tank',
        value('level', 'L', 0, lower=0),
        value('mode', mode, mode.ON),
        value('flag', 'L', 0),
        event('top', after(q(1, 'h'), add(this.level, q(0.1, 'L')), add(this.level, q(0.2, 'L')))),
        event(
            'check',
            after(
                q(2, 'h'),
                switch(
                    this.mode, case(mode.ON, assign(this.flag, q(1, 'L')), when=this.level >= q(0.3, 'L'))
                ),
            ),
        ),
    )
    b.setup(start(named('tank').top), start(named('tank').check))
    record = run(b.finish(), Configuration(Request(3)))
    (commit,) = record.entries('commit', 'tank.check.step[0]')
    assert [tie[0] for tie in commit.detail('near')] == ['tank.check.step[0].do[0].ON']


def test_or_stops_at_the_term_that_decides():
    """At 1 h the clock reaches 1 h, moving through it, and the level reaches 0.1 + 0.2. `t >= 1 h or
    level >= 0.3 L` holds by its first term, so the near-tie of its second term decides nothing and is
    not marked; in the other order the near-tie decides, and is."""
    level, clock = this.level >= q(0.3, 'L'), t >= q(1, 'h')
    (entry,) = tank(alarm(clock | level)).entries('fire')
    assert entry.t == 1 and entry.detail('near') is None
    (entry,) = tank(alarm(level | clock)).entries('fire')
    assert entry.t == 1 and [tie[1] for tie in entry.detail('near')] == ["tank.level >= q(0.3, 'L')"]
