"""A connected set that goes to the solver takes steps longer than the step cap, and the engine reads
each such step inside (`napkin/engine/continuous/integrate.py`, the check interval; docs/engine.md,
"Steps"). Each model is a table of cells, each cell one component of the continuous engine.

The oracles are closed forms, from the numbers that each test writes into its table:

- `y' = -p y²` from `y0` is `y0 / (1 + p y0 t)`: it comes to a mark `m` at `(1/m - 1/y0) / p`;
- a rate that is a pulse `exp(-((t - c) / w)²)` adds the area of the pulse, `w √π`;
- `y' = -k (1 + y²)` from `y0` is `tan(atan(y0) - k t)`: it is at zero at `atan(y0) / k`;
- `y' = -p y (0.4 - r t)` from `y0` is `y0 exp(-p (0.4 t - r t² / 2))`, and its rate is below zero
  from `0.4 / r` on;
- a chain of two decays, `feed -> level -> out` at the rates `a` and `b`, gives the level
  `a / (b - a) (e^(-a t) - e^(-b t))`, with its peak at `ln(b / a) / (b - a)`.

Each test also states the property that makes it a test of the long steps: the solver took fewer
steps than the run has caps, or one of its steps holds the times that the test is about.
"""

import importlib
import math
from itertools import pairwise

import pytest
from scipy.optimize import brentq

from napkin.engine import read, run
from napkin.engine.continuous.kernels import MatrixExponential
from napkin.engine.timeline import Plan, Run
from napkin.program import build
from napkin.program.build import SOURCE, Builder, flow, formula, fsum, ifelse, input_, q, t, this, value
from napkin.program.config import Configuration, Request
from napkin.program.record import Key

UNITS = {'h': {'time': 1}, 'day': ({'time': 1}, 24)}
DAY = 24.0


def cells(parts, rows, total=None):
    """A program of a table of cells, each with `parts`, and the sum of the field `total` over them."""
    b = Builder(UNITS)
    cell = b.template('Cell', *parts)
    b.table('cells', cell, rows)
    if total is not None:
        b.root(value('total', '', formula(fsum(cell.instances.__getattr__(total)))))
    return b.finish()


def configured(hours):
    return Configuration(Request(hours))


def at(record, program, path, *times):
    (reading,) = read(record, program, [path], [float(time) for time in times])
    return reading.values


def solver_steps(program, hours):
    """The steps (start, end) that the solver accepted in the numerical segments of the components
    of a run, from a run of the components alone."""
    made = Run(Plan.of(program, configured(hours)))
    _, _, components = made.prepare()
    steps = []
    for component, _ in components:
        while component.state.time < hours:
            segment = component.next(hours)
            if segment.numerical is not None:
                times = segment.numerical.t
                steps += list(pairwise(times))
            component.proceed(segment)
    return steps


# ---- a crossing in a long quiet time ------------------------------------------------------------------


def test_a_crossing_in_a_long_quiet_time_is_where_the_closed_form_puts_it_with_far_fewer_steps_than_caps():
    """Each cell falls as `y0 / (1 + p y0 t)` while it is above its mark, and holds there: the fall
    stops where the rate's branch changes, after more than 120 days. The level moves slowly there
    (it loses a hundredth of itself in a day), so the solver takes steps of many caps. What each cell
    lost is what it had above the mark."""
    starts, pace, mark = [0.9, 0.5, 0.31], 0.37, 0.02
    fall = ifelse(this.level > this.mark, this.pace * this.level * this.level, q(0, '1/day'))
    parts = (
        input_('pace', '1/day', pace),
        input_('initial', '', 0.5),
        input_('mark', '', mark),
        value('level', '', this.initial, scale=1),
        value('gone', '', 0, scale=1),
        flow('fade', this.level, this.gone, request=formula(fall)),
    )
    program = cells(parts, [{'initial': start} for start in starts])
    record = run(program, configured(200 * DAY))
    assert record.failure is None
    times = [(1 / mark - 1 / start) / pace * DAY for start in starts]
    # The error of a run adds the errors of its steps: an error of the level of 200 times the
    # tolerance of a step is a time of `200 rtol m / (p m²)` days.
    part = 200 * 1e-9
    slack = part * mark / (pace * mark * mark) * DAY
    for row, (start, when) in enumerate(zip(starts, times)):
        pieces = record.history(Key(f'cells[{row}]', ('level',))).pieces
        assert min(abs(piece.t - when) for piece in pieces) <= slack
        half = when / 2
        assert at(record, program, f'cells[{row}].level', half) == pytest.approx(
            [start / (1 + pace / DAY * start * half)], rel=part
        )
    lost = [at(record, program, f'cells[{row}].gone', 200 * DAY)[0] for row in range(len(starts))]
    assert lost == pytest.approx([start - mark for start in starts], rel=part)
    steps = solver_steps(program, 200 * DAY)
    assert 0 < len(steps) < sum(times) / 4


# ---- a short pulse in a long quiet time ---------------------------------------------------------------


def test_a_short_pulse_of_a_rate_in_a_long_quiet_time_is_not_jumped_over(monkeypatch):
    """The rate of each cell is a pulse of a tenth of an hour, or half of that, at one time of 42
    days, and nothing else: the cell ends at the area of its pulse. Before its pulse a cell does not
    move, so the solver takes steps of many caps there, and a step over the pulse reads the rate at
    no time inside it. The engine reads the rate at each half of a cap inside a long step and does
    not use the step. The pulses are at a whole cap, at a half, between the two, early in the run;
    the last one is narrow, and in the middle between two whole caps. A solver that the cap limits
    finds them all too, with more than twice as many steps."""
    pulses = [(500.25, 0.1), (500.0, 0.1), (499.75, 0.1), (123.4, 0.1), (700.5, 0.05)]
    rate = build.call('exp', -(((t - this.center) / this.width) ** 2)) * q(1, '1/h')
    parts = (
        input_('center', 'h', 500),
        input_('width', 'h', 0.1),
        value('filled', '', 0, scale=1),
        flow('burst', SOURCE, this.filled, request=formula(rate)),
    )
    program = cells(parts, [{'center': center, 'width': width} for center, width in pulses], total='filled')
    areas = [width * math.sqrt(math.pi) for _, width in pulses]
    record = run(program, configured(42 * DAY))
    found = [at(record, program, f'cells[{row}].filled', 42 * DAY)[0] for row in range(len(pulses))]
    assert found == pytest.approx(areas, rel=1e-6)
    assert at(record, program, 'total', 42 * DAY) == pytest.approx([sum(areas)], rel=1e-7)
    long = solver_steps(program, 42 * DAY)
    running = importlib.import_module('napkin.engine.timeline.run')
    monkeypatch.setattr(running, 'solver_step', lambda numerics: numerics.max_step)
    limited = solver_steps(program, 42 * DAY)
    assert max(b - a for a, b in limited) <= 1.0 + 1e-12 < max(b - a for a, b in long)
    assert 0 < len(long) < len(limited) / 2


# ---- a bound inside a long step ------------------------------------------------------------------------


def test_a_level_that_reaches_its_bound_inside_a_long_step_is_held_there_from_the_closed_form_time():
    """The level of a cell falls as `tan(atan(y0) - k t)` and is at zero, its lower bound, at
    `atan(y0) / k`: 400 h for the slowest cell. The solver takes steps of tens of hours there; the
    level stays on its bound from that time, and what the cell lost is its start."""
    start = 0.5
    paces = [math.atan(start) / hours for hours in (400.0, 300.0, 395.0)]
    parts = (
        input_('pace', '1/h', 0.001),
        value('level', '', start, lower=0, scale=1),
        value('gone', '', 0, scale=1),
        flow('drain', this.level, this.gone, request=formula(this.pace * (1 + this.level * this.level))),
    )
    program = cells(parts, [{'pace': pace} for pace in paces], total='gone')
    record = run(program, configured(40 * DAY))
    assert record.failure is None
    for row, pace in enumerate(paces):
        zero = math.atan(start) / pace
        before = [0.25 * zero, 0.5 * zero, 0.9 * zero]
        assert at(record, program, f'cells[{row}].level', *before) == pytest.approx(
            [math.tan(math.atan(start) - pace * when) for when in before], rel=1e-7
        )
        assert at(record, program, f'cells[{row}].level', zero + 1, 40 * DAY) == pytest.approx(
            [0, 0], abs=1e-9
        )
    assert at(record, program, 'total', 40 * DAY) == pytest.approx([3 * start], rel=1e-9)
    assert 0 < len(solver_steps(program, 40 * DAY)) < sum(math.atan(start) / pace for pace in paces) / 4


def test_a_flow_whose_rate_goes_below_zero_inside_a_long_step_stops_the_run():
    """The drain of a cell has the rate `p y (0.4 - r t)`: it is below zero from `0.4 / r` hours on,
    and a flow cannot ask a rate below zero. With `r` of 0.0003 an hour that time is after the 30
    days of the run: the run ends, and the level is `y0 exp(-p (0.4 t - r t² / 2))`. With `r` of
    0.001 an hour the time is 400 h, in the middle of a step of tens of hours: the run stops in the
    segment that holds it, and its record names the flow."""
    pace, hours = 0.001, 30 * DAY
    parts = (
        input_('rise', '1/h', 0.0003),
        value('level', '', 0.5, scale=1),
        value('gone', '', 0, scale=1),
        value('other', '', 0, scale=1),
        flow('fill', SOURCE, this.other, request=this.rise),
        flow(
            'drain', this.level, this.gone, request=formula(q(pace, '1/h') * this.level * (0.4 - this.other))
        ),
    )
    rises = [0.0003, 0.0002, 0.00041]
    assert all(0.4 / rise > hours for rise in rises)
    program = cells(parts, [{'rise': rise} for rise in rises], total='gone')
    record = run(program, configured(hours))
    assert record.failure is None
    levels = [0.5 * math.exp(-pace * (0.4 * hours - rise * hours * hours / 2)) for rise in rises]
    found = [at(record, program, f'cells[{row}].level', hours)[0] for row in range(len(rises))]
    assert found == pytest.approx(levels, rel=200 * 1e-9)
    assert 0 < len(solver_steps(program, hours)) < 3 * hours / 4
    below = cells(parts, [{'rise': 0.0003}, {'rise': 0.001}])
    record = run(below, configured(hours))
    assert "Negative flow rates: ['cells[1].drain']" in record.failure.detail('message')
    assert record.failure.t <= 0.4 / 0.001


# ---- a value over a mark for a time that is shorter than a step ------------------------------------------


def test_a_value_that_is_over_a_mark_only_for_a_short_time_is_read_there():
    """The level of a chain of two slow decays rises to a peak after 130 days and falls again. A
    mark at two parts in a million below the peak is under the level for 12.6 hours. The rates are
    linear in the stores, so the continuous engine gives the whole run as one segment of the matrix
    exponential: no step of a solver can jump over that time. The reader reads the level at the peak
    and at the two times at which it is at the mark, as the closed form has them, and a yes/no
    formula over the mark is true at the peak and false a day before and after."""
    enter, leave = 0.0004, 0.00025

    def level(when):
        return enter / (leave - enter) * (math.exp(-enter * when) - math.exp(-leave * when))

    peak = math.log(leave / enter) / (leave - enter)
    mark = level(peak) * (1 - 2e-6)
    over = brentq(lambda when: level(when) - mark, 0.0, peak, xtol=1e-12)
    under = brentq(lambda when: level(when) - mark, peak, 300 * DAY, xtol=1e-12)
    parts = (
        input_('mark', '', 0.3),
        value('feed', '', 1, scale=1),
        value('level', '', 0, scale=1),
        value('out', '', 0, scale=1),
        value('high', build.BOOL, formula(this.level >= this.mark)),
        flow('come', this.feed, this.level, request=formula(q(enter, '1/h') * this.feed)),
        flow('go', this.level, this.out, request=formula(q(leave, '1/h') * this.level)),
    )
    program = cells(parts, [{'mark': mark}])
    record = run(program, configured(300 * DAY))
    assert at(record, program, 'cells[0].level', peak, over, under) == pytest.approx(
        [level(peak), mark, mark], rel=1e-8
    )
    assert at(record, program, 'cells[0].high', peak, over - DAY, under + DAY) == (True, False, False)
    assert under - over > 1.0
    _, _, ((component, _),) = Run(Plan.of(program, configured(300 * DAY))).prepare()
    segment = component.next(300 * DAY)
    assert isinstance(segment.solution, MatrixExponential) and segment.end == 300 * DAY
