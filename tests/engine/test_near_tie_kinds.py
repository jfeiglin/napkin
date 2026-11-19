"""The near-ties that make no firing and no commit (change 10; `triggers.py`, `moment.py`): a false
guard (`skip`), a trigger that came within tolerance of its threshold and did not fire (`miss`), a
gate's release (`release`) and a split of who is served at a settling (`settle`), each with the detail
`near` and its message in the report. The cases are worked by hand in floats: 0.1 + 0.2 exceeds 0.3,
and 0.7 + 0.1 falls short of 0.8, by one unit in the last place, far inside a store's tolerance of
1e-10 of its size (1 L here); 0.30001 and 0.79 miss them by far more.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.engine.report import report
from napkin.program.build import (
    SOURCE,
    Builder,
    add,
    after,
    assign,
    endpoint,
    event,
    flow,
    named,
    priority,
    q,
    start,
    this,
    until,
    value,
    when,
)
from napkin.program.config import Configuration, Request
from tests.program.examples import UNITS

TOLERANCE = 1e-10  # the tolerance of a store of size 1 L: `atol_factor` 1e-10 times it
OVER = (0.1 + 0.2) - 0.3  # one unit in the last place of 0.3
UNDER = (0.7 + 0.1) - 0.8  # one unit in the last place of 0.8, below it


def tank(*parts, first=0.1, second=0.2, setup=(), horizon=3):
    """A tank whose level rises by `first` and then by `second` at 1 h, with the parts given; the
    events named in `setup` start with the run. (The record, the program, the configuration.)"""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('level', 'L', 0, lower=0),
        value('flag', 'L', 0),
        event('top', after(q(1, 'h'), add(this.level, q(first, 'L')), add(this.level, q(second, 'L')))),
        *parts,
    )
    b.setup(start(named('tank').top), *(start(getattr(named('tank'), name)) for name in setup))
    program, configuration = b.finish(), Configuration(Request(horizon))
    return run(program, configuration), program, configuration


def messages(record, program, configuration):
    """The messages of the report's near-ties."""
    return [tie.message for tie in report(record, program, configuration, ['tank.level'], [0]).near_ties]


def test_a_guard_false_within_tolerance_marks_the_stage_that_ran_nothing():
    """At 2 h the level is 0.1 + 0.2, and the guard `level <= 0.3 L` is false by one unit in the last
    place: the stage runs nothing (the flag stays 0) and has an entry `skip`."""
    check = event('check', after(q(2, 'h'), assign(this.flag, q(1, 'L')), when=this.level <= q(0.3, 'L')))
    record, program, configuration = tank(check, setup=['check'])
    (entry,) = record.entries('skip')
    ((origin, comparison, difference, tolerance),) = entry.detail('near')
    assert (entry.t, entry.part, entry.owner) == (2, 'tank.check.step[0]', 'tank.check#0')
    assert (origin, comparison) == ('tank.check.step[0]', "tank.level <= q(0.3, 'L')")
    assert difference == OVER and tolerance == pytest.approx(TOLERANCE)
    assert record.entries('commit', 'tank.check.step[0]') == ()
    assert read(record, program, ['tank.flag'], [3])[0].values == (0,)
    (message,) = messages(record, program, configuration)
    assert 'this guard was false within tolerance of its boundary, and the stage ran nothing' in message


def test_a_guard_false_by_more_than_the_tolerance_has_no_entry():
    check = event('check', after(q(2, 'h'), assign(this.flag, q(1, 'L')), when=this.level <= q(0.3, 'L')))
    record, *_ = tank(check, setup=['check'], second=0.20001)
    assert record.entries('skip') == () and record.near_ties() == ()


def alarm(test, *more):
    """A trigger on the tank that starts an event of no duration, and the statements of a later stage."""
    return event('alarm', when(test, start(this.alarm)), after(q(0, 'h'))), *more


def test_a_trigger_within_tolerance_that_did_not_fire_is_marked_once_until_it_fires():
    """The level is 0.7 + 0.1 at 1 h, short of 0.8 by one unit in the last place: the armed trigger
    `level >= 0.8 L` does not fire, and has an entry `miss`. At the moment of 2 h it reads the same
    near-tie, which is not written again. At 2.5 h the level is 0.9 - 0.1 + 0.1 above 0.8 and it fires;
    at 2.75 h it is back below by one unit in the last place, the trigger rearms, and the miss after
    its firing is marked again."""
    steps = event(
        'steps',
        after(q(1, 'h')),
        after(q(1, 'h'), assign(this.flag, q(1, 'L'))),
        after(q(0.5, 'h'), add(this.level, q(0.1, 'L'))),
        after(q(0.25, 'h'), add(this.level, q(-0.1, 'L'))),
    )
    record, program, configuration = tank(
        *alarm(this.level >= q(0.8, 'L')), steps, first=0.7, second=0.1, setup=['steps']
    )
    level = (0.7 + 0.1) + 0.1 - 0.1  # at 2.75 h
    assert level - 0.8 == UNDER
    misses = record.entries('miss')
    assert [(entry.t, entry.part, entry.owner) for entry in misses] == [
        (1, 'tank.alarm.when[0]', 'tank'),
        (2.75, 'tank.alarm.when[0]', 'tank'),
    ]
    for entry in misses:
        ((origin, comparison, difference, tolerance),) = entry.detail('near')
        assert (origin, comparison) == ('tank.alarm.when[0]', "tank.level >= q(0.8, 'L')")
        assert difference == UNDER and tolerance == pytest.approx(TOLERANCE)
    assert [entry.t for entry in record.entries('fire')] == [2.5]
    found = messages(record, program, configuration)
    assert len(found) == 2
    assert all(
        'this trigger came within tolerance of its threshold and did not fire' in line for line in found
    )


def test_a_trigger_that_misses_by_more_than_the_tolerance_has_no_entry():
    record, *_ = tank(*alarm(this.level >= q(0.8, 'L')), first=0.7, second=0.09)
    assert record.entries('miss') == () and record.entries('fire') == ()


def test_only_the_terms_that_decide_an_answer_are_marked():
    """At 1 h the level is 0.1 + 0.2, within tolerance of 0.3. `level >= 0.3 L and flag >= 5 L` is
    false by its second term, 5 L short: had the first turned, nothing would change, so it is no
    near-tie. `level == 0.3 L or level >= 0.25 L` holds by its second term, 0.05 L clear, so the near
    first term decides nothing either: the alarm fires with no near-tie."""
    level = this.level >= q(0.3, 'L')
    record, *_ = tank(*alarm(level & (this.flag >= q(5, 'L'))))
    assert record.entries('miss') == () and record.entries('fire') == ()
    record, *_ = tank(*alarm((this.level == q(0.3, 'L')) | (this.level >= q(0.25, 'L'))))
    (entry,) = record.entries('fire')
    assert entry.t == 1 and entry.detail('near') is None and record.near_ties() == ()


def test_a_gate_released_within_tolerance_is_marked_in_its_occurrence():
    """The gate `until level >= 0.3 L` opens at 1 h, when the level is 0.1 + 0.2: an entry `release`
    of the occurrence at the gate; then its stage commits."""
    wait = event('wait', until(this.level >= q(0.3, 'L')), after(q(0, 'h'), assign(this.flag, q(1, 'L'))))
    record, program, configuration = tank(wait, setup=['wait'])
    (entry,) = record.entries('release')
    ((origin, comparison, difference, tolerance),) = entry.detail('near')
    assert (entry.t, entry.part, entry.owner) == (1, 'tank.wait.step[0]', 'tank.wait#0')
    assert (origin, comparison) == ('tank.wait.step[0]', "tank.level >= q(0.3, 'L')")
    assert difference == OVER and tolerance == pytest.approx(TOLERANCE)
    assert [entry.t for entry in record.entries('commit', 'tank.wait.step[1]')] == [1]
    (message,) = messages(record, program, configuration)
    assert 'this gate released its occurrence within tolerance of its threshold' in message


def test_a_gate_released_by_more_than_the_tolerance_has_no_entry():
    wait = event('wait', until(this.level >= q(0.3, 'L')), after(q(0, 'h'), assign(this.flag, q(1, 'L'))))
    record, *_ = tank(wait, setup=['wait'], second=0.20001)
    assert record.entries('release') == ()
    assert [entry.t for entry in record.entries('commit', 'tank.wait.step[1]')] == [1]


def junction(second, use1=0.3, limit=None, later=()):
    """A store held empty whose outflow serves `use1` (asking `use1` L/h), then `use2` (1 L/h), fed by
    two rigid fills of 0.1 and `second` L/h; with `limit`, the outflow has that capacity. A stage at
    1 h makes the statements of `later`."""
    b = Builder(UNITS)
    b.entity(
        's',
        value(
            'w',
            'L',
            0,
            lower=0,
            outflow=endpoint(capacity=limit, allocation=priority(this.use1, this.use2)),
        ),
        value('u1', 'L', 0, lower=0),
        value('u2', 'L', 0, lower=0),
        flow('fill_a', SOURCE, this.w, request=q(0.1, 'L/h'), capacity=q(0.1, 'L/h')),
        flow('fill_b', SOURCE, this.w, request=q(second, 'L/h'), capacity=q(second, 'L/h')),
        flow('use1', this.w, this.u1, request=q(use1, 'L/h')),
        flow('use2', this.w, this.u2, request=q(1, 'L/h')),
        event('change', after(q(1, 'h'), *later)),
    )
    b.setup(start(named('s').change))
    program, configuration = b.finish(), Configuration(Request(2))
    return run(program, configuration), program, configuration


def test_a_split_of_who_is_served_within_tolerance_is_marked_at_its_settling():
    """What flows into the empty store, 0.1 + 0.2 L/h, exceeds what use1 asks, 0.3 L/h, by one unit in
    the last place: whether use2 gets anything is decided within tolerance. The sets start in round
    zero, which has the entry `settle` of the outflow."""
    record, program, configuration = junction(0.2)
    (entry,) = record.entries('settle')
    ((origin, comparison, difference, tolerance),) = entry.detail('near')
    assert (entry.t, entry.round, entry.part, entry.owner) == (0, 0, 's.w.outflow', 's')
    assert origin == 's.w.outflow'
    assert comparison == 'what flows into s.w against the claims of s.use1, served before s.use2'
    assert difference == OVER and tolerance == pytest.approx(TOLERANCE)
    (tie,) = report(record, program, configuration, ['s.w'], [0]).near_ties
    assert (tie.kind, tie.part, tie.owner) == ('settle', 's.w.outflow', 's')
    assert 'this split of who is served was decided within tolerance of its boundary' in tie.message


def test_a_split_by_more_than_the_tolerance_has_no_entry():
    """0.1 + 0.25 L/h flows in: use2 gets 0.05 L/h, far from the boundary."""
    record, *_ = junction(0.25)
    assert record.entries('settle') == ()


def test_a_capacity_that_splits_within_tolerance_is_marked_where_a_stage_moves_the_claims():
    """The outflow's capacity is 0.1 L/h + 0.2 L/h, and 0.5 L/h flows in, so the store fills and
    nothing but the capacity limits the outflow. use1 asks 0.2 L/h until a stage at 1 h makes it
    0.3 L/h: the set settles again then, and the capacity splits use1 from use2 within tolerance."""
    capacity = q(0.1, 'L/h') + q(0.2, 'L/h')
    record, *_ = junction(0.4, use1=0.2, limit=capacity, later=(assign(this.use1.request, q(0.3, 'L/h')),))
    (entry,) = record.entries('settle')
    ((_, comparison, difference, _),) = entry.detail('near')
    assert (entry.t, entry.round) == (1, 1)
    assert comparison == 'the capacity of s.w.outflow against the claims of s.use1, served before s.use2'
    assert difference == OVER
