"""Triggers on values that turn (docs/design/decisions.md, change 20; `timeline/triggers.py`, `continuous/dense.py`).

A value that rises and falls between moments is certified step by step from the form of its segment:
a step of Radau's dense output, or the closed form of compartments. The cases:

- a reservoir that a storm fills and a spill empties, whose spill reads the water: a storm of
  9 exp(-t) L/h and a spill of twice the water an hour give w' = 9 exp(-t) - 2 w, so from 0 L
  w(t) = 9 (exp(-t) - exp(-2 t)) = 9 (u - u^2) with u = exp(-t). It crosses 2 L where u = 2/3, at
  ln 1.5 h rising, and where u = 1/3, at ln 3 h falling, with its peak of 2.25 L at ln 2 h between.
  It runs on the continuous engine's solver and on the sparse integrator; a cloud of 9 L that rains
  its content an hour into the reservoir gives the same water on the closed form of compartments;
- a weighted sum of two stores that turns: for a cloud of 8 L, water + cloud / 4 = 8 (1.25 u - u^2),
  2 L at 0 h, which crosses 3 L where u = 3/4 (ln 4/3 h) and u = 1/2 (ln 2 h);
- a value that touches its level: an inflow of 2 L/h and an outflow of t L/h^2 from 10 L give the
  parabola w(t) = 12 - (t - 2)^2 / 2, which the solver's cubic holds exactly. A level half a
  tolerance above the peak is reached within tolerance where the water enters its band,
  12 - (t - 2)^2 / 2 = 12 - tolerance / 2, at 2 - sqrt(tolerance) h: the trigger fires there, marked
  as a near-tie. A level two tolerances above the peak is never reached;
- a quick rise and fall inside one step: a level 1e-4 L below the peak is crossed at
  2 -+ sqrt(2e-4) h, between two ends of a step of the solver, both below it;
- a strict threshold, which is still a diagnostic;
- exact resume three ways (`test_checkpoints.py`) at the reservoir's rise.

Every expected value is worked by hand from these closed forms.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.integrate import Radau

from napkin.engine import run
from napkin.engine.continuous import dense
from napkin.engine.continuous.kernels import MatrixExponential
from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.plan import COMPONENT, SPARSE
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    call,
    endpoint,
    event,
    flow,
    formula,
    named,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request
from tests.engine.test_checkpoints import Case, in_a_fresh_process, in_one_process, stages, ticks

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
RISE, FALL = math.log(1.5), math.log(3)  # h: where 9 (u - u^2) = 2 L, at u = 2/3 and u = 1/3
TOLERANCE = 1e-9 * 12  # change 29: rtol times the level at the 12 L threshold


def watch(name, test, reset=None):
    """An event `name` that its trigger on `test` starts, and that adds one to `<name>s`."""
    return (
        value(f'{name}s', '', 0),
        event(
            name,
            when(test, start(getattr(this, name)), reset=reset),
            after(q(0, 'h'), add(getattr(this, f'{name}s'), 1)),
        ),
    )


def watches(level=None, reading=None):
    """`high`, once, where the reading (the water) reaches the level (2 L), and `low` where it is at
    most the level, which rearms when it is above."""
    level = q(2, 'L') if level is None else level
    reading = this.water if reading is None else reading
    return (*watch('high', reading >= level, reset_when(False)), *watch('low', reading <= level))


def reservoir(way, *parts, cloud=9, horizon=3, ticking=False):
    """The reservoir of the module on `way`: `solver` (the continuous engine integrates a storm that
    reads the time), `sparse` (the same storm, on the sparse integrator, which an outflow capacity
    that never binds puts it on) or `closed` (a cloud of `cloud` L that rains into it: compartments)."""
    b = Builder(UNITS)
    outflow = endpoint(capacity=q(100, 'L/h')) if way == 'sparse' else None
    if way == 'closed':
        storm = (
            value('cloud', 'L', cloud, lower=0),
            flow('rain', this.cloud, this.water, request=formula(this.cloud / q(1, 'h'))),
        )
    else:
        storm = (
            flow('storm', SOURCE, this.water, request=formula(q(9, 'L/h') * call('exp', -(t / q(1, 'h'))))),
        )
    b.entity(
        'reservoir',
        value('water', 'L', 0, lower=0, outflow=outflow),
        *storm,
        flow('spill', this.water, SINK, request=formula(this.water * 2 / q(1, 'h'))),
        *parts,
    )
    if ticking:
        b.setup(start(named('reservoir').tick))
    return b.finish(), Configuration(Request(horizon))


def parabola(level, horizon=4):
    """A tank that holds 12 - (t - 2)^2 / 2 L, with `high` where it reaches `level`."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0, scale=10),
        flow('fill', SOURCE, this.water, request=q(2, 'L/h')),
        flow('use', this.water, SINK, request=formula(t / q(1, 'h') * q(1, 'L/h'))),
        *watch('high', this.water >= level, reset_when(False)),
    )
    return b.finish(), Configuration(Request(horizon))


def fired(record, part):
    return [entry.t for entry in record.entries('fire', part)]


@pytest.mark.parametrize('way', ['solver', 'sparse', 'closed'])
def test_a_reservoir_that_rises_and_falls_crosses_its_level_both_ways(way):
    made = Run(Plan.of(*reservoir(way, *watches())))
    record = made.run()
    assert record.failure is None
    assert {connected.way for connected, _ in made.ways.sets.values()} == {
        SPARSE if way == 'sparse' else COMPONENT
    }
    # The solver integrates the storm that reads the time; the cloud's closed form integrates nothing.
    assert bool(made.settings['integration_segments']) == (way == 'solver')
    assert fired(record, 'reservoir.high.when[0]') == pytest.approx([RISE], abs=1e-6)
    assert fired(record, 'reservoir.low.when[0]') == pytest.approx([0, FALL], abs=1e-6)
    assert record.near_ties() == ()


def test_a_weighted_sum_of_two_stores_that_turns_crosses_its_level():
    sum_ = this.water + this.cloud / 4
    record = run(*reservoir('closed', *watches(q(3, 'L'), sum_), cloud=8))
    assert record.failure is None
    assert fired(record, 'reservoir.high.when[0]') == pytest.approx([math.log(4 / 3)], abs=1e-6)
    assert fired(record, 'reservoir.low.when[0]') == pytest.approx([0, math.log(2)], abs=1e-6)


def test_a_value_that_touches_its_level_within_tolerance_fires_there_as_a_near_tie():
    record = run(*parabola(q(12 + TOLERANCE / 2, 'L')))
    assert record.failure is None
    (entry,) = record.entries('fire')
    assert entry.t == pytest.approx(2 - math.sqrt(TOLERANCE), abs=1e-7)
    ((origin, comparison, difference, tolerance),) = entry.detail('near')
    assert origin == 'tank.high.when[0]' and comparison.startswith('tank.water >= ')
    assert tolerance == pytest.approx(TOLERANCE)
    # Where it enters its band, the difference is the band's edge, within the crossing tolerance.
    assert -TOLERANCE <= difference < -0.99 * TOLERANCE
    record = run(*parabola(q(12 + 2 * TOLERANCE, 'L')))
    assert record.failure is None and record.entries('fire') == ()


def test_a_rise_and_fall_inside_one_step_is_found_though_the_ends_of_the_step_are_below(monkeypatch):
    seen = []
    breaks = ComponentWay.breaks

    def spied(self, start, end):
        found = breaks(self, start, end)
        seen.append((start, end, found))
        return found

    monkeypatch.setattr(ComponentWay, 'breaks', spied)
    delta = 1e-4
    up, down = 2 - math.sqrt(2 * delta), 2 + math.sqrt(2 * delta)
    record = run(*parabola(q(12 - delta, 'L')))
    assert record.failure is None
    assert fired(record, 'tank.high.when[0]') == pytest.approx([up], abs=1e-7)
    # The prediction at 0 h reads the segment to the horizon step by step: no step of the solver ends
    # between the two crossings, so the step that holds them has both its ends below the level.
    start_, end, found = seen[0]
    assert start_ == 0 and end == 4
    assert found and not [at for at in found if up <= at <= down]


def test_a_strict_threshold_on_a_value_that_turns_is_still_a_diagnostic():
    record = run(*reservoir('solver', *watch('high', this.water > q(2, 'L'))))
    assert 'strict threshold' in record.failure.detail('message')
    assert record.failure.t == 0


def turning(way):
    """The reservoir on `way`, with ticks around its rise through 2 L at ln 1.5 = 0.405465 h, and a
    breakpoint at each tick."""
    program, configuration = reservoir(
        way, *watches(), value('ticks', '', 0), ticks(0.2, 0.4054, 0.40547, 1, 2), ticking=True
    )
    return Case(
        program,
        configuration,
        stages('reservoir.tick', 5),
        frozenset({SPARSE if way == 'sparse' else COMPONENT}),
    )


@pytest.mark.parametrize('way', ['solver', 'sparse'])
def test_a_resumed_run_crosses_where_the_run_straight_through_does_three_ways(way, tmp_path):
    case = turning(way)
    straight = run(case.program, case.configuration)
    assert straight.failure is None
    stops, final, made = in_one_process(case)
    assert {connected.way for connected, _ in made.ways.sets.values()} == case.ways
    assert [stop.stop.t for stop in stops] == pytest.approx([0.2, 0.4054, 0.40547, 1, 2])
    assert final == straight
    (at,) = fired(final, 'reservoir.high.when[0]')
    assert at == pytest.approx(RISE, abs=1e-6) and stops[1].stop.t < at < stops[2].stop.t
    assert fired(final, 'reservoir.low.when[0]') == pytest.approx([0, FALL], abs=1e-6)
    assert in_a_fresh_process(case.program, stops, tmp_path) == [*stops[1:], final]


def test_the_motion_of_a_step_is_the_cubic_of_its_dense_output():
    # y' = t^2 from 0: Radau's collocation cubic is y = t^3 / 3 exactly, and 3 y = t^3. Over [s, e]
    # its rate at s is 3 s^2 and differs from the rate inside by at most 3 (e^2 - s^2), and it moves
    # by e^3 - s^3: the bounds give each exactly, as every term of the cubic rises.
    solver = Radau(lambda at, y: [at * at], 0.0, [0.0], 10.0, first_step=2.0)
    solver.step()
    output = solver.dense_output()
    s, e = 0.25 * output.t, 0.75 * output.t
    found = dense.of_step(output, np.array([0]), np.array([3.0]), s, e)
    assert found.value == pytest.approx(s**3, rel=1e-9)
    assert found.rate == pytest.approx(3 * s * s, rel=1e-9)
    assert found.spread == pytest.approx(3 * (e * e - s * s), rel=1e-9)
    assert found.change == pytest.approx(e**3 - s**3, rel=1e-9)


def test_the_motion_of_a_closed_form_bounds_its_rate_by_the_growth_of_its_matrix():
    # y' = -y / 2 from 4 at 0 h: over [1, 3] the rate at 1 h is -2 exp(-1/2), and the rate inside
    # differs from it by 2 exp(-1/2) (1 - exp(-1)) at most; it moves by 4 exp(-1/2) (1 - exp(-1)).
    # With the logarithmic norm -1/2, phi(2) = (exp(-1) - 1) / (-1/2) = 2 (1 - exp(-1)), and the
    # bounds |A^T w| phi |y'(1)| and |w| phi |y'(1)| give each exactly.
    solution = MatrixExponential.of(np.array([[-0.5, 0.0]]), 1, 0.0, np.array([4.0]))
    found = dense.of_exponential(solution, np.array([0]), np.array([1.0]), 1.0, 3.0)
    assert found.value == pytest.approx(4 * math.exp(-0.5), rel=1e-12)
    assert found.rate == pytest.approx(-2 * math.exp(-0.5), rel=1e-12)
    assert found.spread == pytest.approx(2 * math.exp(-0.5) * (1 - math.exp(-1)), rel=1e-12)
    assert found.change == pytest.approx(4 * math.exp(-0.5) * (1 - math.exp(-1)), rel=1e-12)


def test_a_sum_that_a_closed_form_conserves_holds_through_any_piece():
    # A transfer, waiting' = -waiting / 20 and served' = waiting / 20 from 1000 and 0: waiting + served
    # holds at 1000, and A^T w = 0 says so for a piece of any length, though each store moves.
    matrix = np.array([[-0.05, 0.0, 0.0], [0.05, 0.0, 0.0]])
    solution = MatrixExponential.of(matrix, 2, 0.0, np.array([1000.0, 0.0]))
    found = dense.of_exponential(solution, np.array([0, 1]), np.array([1.0, 1.0]), 0.0, 120.0)
    assert found.value == pytest.approx(1000, rel=1e-15)
    assert (found.rate, found.spread, found.change) == (0, 0, 0)
    waiting = dense.of_exponential(solution, np.array([0]), np.array([1.0]), 0.0, 120.0)
    assert waiting.rate == -50 and waiting.change >= 1000 * (1 - math.exp(-6))
