"""A membership in the conditions that the engine reads itself (re-audit 12, `briefs/audit3.md` F, E).

`x in [lo, hi]` is one operation of the program, `within(x, lo, hi)`, which fails by name when its
interval is reversed, wherever it is evaluated (spec: "reversed bounds are an error"; agent F's
operation). The engine reads some conditions by their comparisons, not only by their value: a
trigger's, a reset's, a gate's and an assertion's, within the tolerance of what they read, with the
first contact predicted between moments; a stage's test for its near-ties; a rate's branches for
their switching surfaces. There a membership is read as its chain `lo <= x <= hi`, once the
membership itself is evaluated. The rule, worked by hand on a tank of 10 L that drains at 1 L/h
(`water = 10 - t` L) between `lo = 3 L` and `hi = 5 L`:

- a trigger and a gate on `water in [lo, hi]`, directly and through a yes/no formula, meet it at
  5 h, the first contact (both ends belong to the interval);
- a reversed interval fails the run by name at the moment that the condition is read: after a stage
  writes `lo = 6 L`, the trigger's condition and the gate's at that moment, a stage's guard when it is
  read; and after an edit at a stop that reverses it, when the resumed run reads them;
- a guard read at 5 h, on the boundary, is a near-tie of its comparison `water <= hi`;
- a rate of 2 L/h inside the interval and 1 L/h outside switches at its ends: 5 L at 5 h, 3 L at
  6 h, 2.5 L at 6.5 h.
"""

from __future__ import annotations

import textwrap
from dataclasses import replace

import pytest

from napkin.engine.timeline import Plan, Run, read, run
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.config import Request
from napkin.program.record import Key

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
REVERSED = 'the interval of a membership test is reversed'

TANK = """
scenario "Within"
    horizon 8 h

tank:
    water: L = 10 L in [0,]
    lo: L = 3 L
    hi: L = 5 L
    INSIDE
    flow drain: this.water -> SINK
        request = 1 L/h
    swap = event():
        after 1 h:
            this.lo = 6 L

watch:
    rung: h = 0 h
    opened: h = 0 h
    ring = event():
        when CONDITION:
            this.ring.start()
            reset when false
        after 0 h:
            this.rung = t
    wait = event():
        until CONDITION
        after 0 h:
            this.opened = t

watch.wait.start()
"""


def compiled(text):
    return compile_text(textwrap.dedent(text), UNITS)


def tank(condition, *starts):
    """The tank and the watch with `condition`: `tank.inside` is a yes/no formula of the tank."""
    inside = 'inside = formula(this.water in [this.lo, this.hi])' if 'inside' in condition else ''
    return compiled(TANK.replace('INSIDE', inside).replace('CONDITION', condition) + ''.join(starts))


def value_at(record, program, path, t):
    (reading,) = read(record, program, [path], [t])
    return reading.values[0]


@pytest.mark.parametrize('condition', ['tank.water in [tank.lo, tank.hi]', 'tank.inside'])
def test_a_trigger_and_a_gate_on_a_membership_meet_its_interval_at_the_first_contact(condition):
    found = tank(condition)
    record = run(found.program, found.configuration)
    assert record.failure is None, record.failure.detail('message')
    assert value_at(record, found.program, 'watch.rung', 8) == pytest.approx(5)
    assert value_at(record, found.program, 'watch.opened', 8) == pytest.approx(5)


@pytest.mark.parametrize('condition', ['tank.water in [tank.lo, tank.hi]', 'tank.inside'])
def test_a_condition_on_an_interval_that_a_stage_reverses_fails_the_run_then(condition):
    """The swap at 1 h makes the interval [6, 5] L: the conditions of that moment read it. (The
    record keeps the watch's values: a record of the formula itself is the record's, agent R.)"""
    found = tank(condition, 'tank.swap.start()\n')
    request = Request(8, everything=False, keys=(Key('watch', ('rung',)), Key('watch', ('opened',))))
    record = run(found.program, replace(found.configuration, request=request))
    assert record.failure is not None and record.failure.t == 1
    assert REVERSED in record.failure.detail('message')


GUARD = """
scenario "Within"
    horizon 8 h

tank:
    water: L = 10 L in [0,]
    lo: L = 3 L
    hi: L = 5 L
    seen: L = 0 L
    flow drain: this.water -> SINK
        request = 1 L/h
    look = event():
        after AT h when this.water in [this.lo, this.hi]:
            this.seen = this.water
    swap = event():
        after 1 h:
            this.lo = 6 L

tank.look.start()
"""


def test_a_guard_on_the_boundary_is_a_near_tie_and_on_a_reversed_interval_fails_when_read():
    found = compiled(GUARD.replace('AT', '5'))
    record = run(found.program, found.configuration)
    assert record.failure is None, record.failure.detail('message')
    assert value_at(record, found.program, 'tank.seen', 8) == pytest.approx(5)
    (commit,) = record.entries('commit', 'tank.look.step[0]')
    (near,) = commit.detail('near')
    assert near[1] == 'tank.lo <= tank.water <= tank.hi' and abs(near[2]) <= near[3]
    reversed_ = compiled(GUARD.replace('AT', '2') + 'tank.swap.start()\n')
    record = run(reversed_.program, reversed_.configuration)
    assert record.failure is not None and record.failure.t == 2
    assert REVERSED in record.failure.detail('message')


def test_an_edit_at_a_stop_that_reverses_the_interval_fails_the_resumed_run_when_it_reads_it():
    """Stopped before a stage at 1 h that writes `lo = 1 L`, an edit writes `hi = 0.5 L`: the
    resumed run reads the trigger's condition at that moment on [1, 0.5] L and fails, in place."""
    text = TANK.replace('this.lo = 6 L', 'this.lo = 1 L')
    found = compiled(
        text.replace('INSIDE', '').replace('CONDITION', 'tank.water in [tank.lo, tank.hi]')
        + 'tank.swap.start()\n'
    )
    made = Run(Plan.of(found.program, found.configuration), (Breakpoint('tank.swap.step[0]'),))
    stopped = made.run()
    assert isinstance(stopped, Checkpoint) and stopped.stop.t == 1
    made.edit(Key('tank', ('hi',)), 0.5)
    record = made.resume()
    assert record.failure is not None and record.failure.t == 1
    assert f'{REVERSED}: [1.0, 0.5]' in record.failure.detail('message')
    # Unedited, the interval stays ordered and the trigger fires at 5 h.
    unedited = run(found.program, found.configuration)
    assert value_at(unedited, found.program, 'watch.rung', 8) == pytest.approx(5)


RATE = """
scenario "Within"
    horizon 7 h

tank:
    water: L = 10 L in [0,]
    lo: L = 3 L
    hi: L = 5 L
    flow drain: this.water -> SINK
        request = formula(2 L/h if this.water in [this.lo, this.hi] else 1 L/h)
"""


def test_a_rate_with_a_membership_switches_at_the_ends_of_its_interval():
    found = compiled(RATE)
    record = run(found.program, found.configuration)
    assert record.failure is None, record.failure.detail('message')
    found_values = [value_at(record, found.program, 'tank.water', t) for t in (5, 6, 6.5)]
    assert found_values == [
        pytest.approx(5, abs=1e-6),
        pytest.approx(3, abs=1e-6),
        pytest.approx(2.5, abs=1e-6),
    ]
