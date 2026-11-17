"""A block of a table model that goes to the solver takes steps longer than the step cap, and the
engine reads each such step inside (`Solution.advance`, `Solution.settle` and `Solution.first_root`
of `napkin/engine/timeline/run.py`; docs/engine.md, "Steps").

The oracles are closed forms, from the numbers that each test writes into its model and its table:

- `y' = -p y²` from `y0` is `y0 / (1 + p y0 t)`: it comes to a mark `m` at `(1/m - 1/y0) / p`;
- a rate that is a pulse `exp(-((t - c) / w)²)` adds the area of the pulse, `w √π`;
- `y' = -k (1 + y²)` from `y0` is `tan(atan(y0) - k t)`: it is at zero at `atan(y0) / k`;
- a chain of two decays, `feed -> level -> out` at the rates `a` and `b`, gives the level
  `a / (b - a) (e^(-a t) - e^(-b t))`, with its peak at `ln(b / a) / (b - a)`. The times at which
  it is at a mark are roots of that formula, found here by a search on the formula.

Each test also states the property that makes it a test of the long steps: the solver took fewer
steps than the run has caps, or one of its steps holds the times that the test is about.
"""

import math

import numpy as np
import pytest
from scipy.optimize import brentq

from napkin.engine import solvers, timeline
from napkin.engine.timeline.plan import Outside
from napkin.model import hybrid

HEAD = """scenario "A synthetic model"
    summary "A model of a test, with no source."
    horizon {days} days
    scope "Nothing: the model is synthetic."

"""
RECORD = '\nrecord shape: assumption "A synthetic model, with no source."\n'
DAY = 24.0


def plan_of(tmp_path, days, body, header, rows):
    """The plan of a model with `body` after its head and one table, `cells.csv`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / 'model.scn'
    path.write_text(HEAD.replace('{days}', str(days)) + body + RECORD, encoding='utf-8')
    lines = [','.join(repr(float(value)) for value in np.atleast_1d(row)) for row in rows]
    (tmp_path / 'cells.csv').write_text('\n'.join([header, *lines]) + '\n', encoding='utf-8')
    return timeline.Plan.of(hybrid.compile(path))


@pytest.fixture(params=sorted(solvers.ADAPTERS))
def adapter(request):
    """Each solver adapter that is here: the engine reads a long step of each in the same way."""
    return solvers.ADAPTERS[request.param]


def caps_of(run, hours):
    """The number of step caps in `hours` of a run."""
    return hours / run.max_step


# ---- a crossing in a long quiet time ------------------------------------------------------------------

FADE = """Cell:  @shape
    "One cell."
    input pace: ratio/day = 0.5 ratio/day in 0 ratio/day to 2 ratio/day  @shape
    let start: fraction = 0.9  @shape
    let mark: fraction = 0.02  @shape
    var level: fraction = start size 1  @shape
    var gone: fraction = 0 size 1  @shape
    var low = false  @shape
    flow fade: level -> gone at pace * level * level while not low
    event reach once when level <= mark:  @shape
        "The level is at its mark."
        low = true

cells: Cell from "cells.csv"

output level_left: fraction = sum(Cell.level)  @shape
    "Level that all cells still have"
    level

output gone_total: fraction = sum(Cell.gone)  @shape
    "Level that all cells lost"
"""


def test_a_crossing_in_a_long_quiet_time_is_where_the_closed_form_puts_it_with_far_fewer_steps_than_caps(
    tmp_path, adapter
):
    """Each cell falls as `y0 / (1 + p y0 t)` and stops at its mark, after 90 days and more. The
    level moves slowly there (it loses a hundredth of itself in a day), so the solver takes steps
    of many caps. The event of each cell is at the time of the closed form; the level stays at
    the mark from there; what the cells lost is what they had above the mark."""
    starts, pace, mark = [0.9, 0.5, 0.31], 0.37, 0.02
    plan = plan_of(tmp_path, 200, FADE, 'start: fraction @shape', starts)
    assert [(block.whole, block.linear) for block in plan.blocks] == [(False, False)]
    run = timeline.Run(plan, {'cells_1.pace': pace}, adapter=adapter)
    result = run.run()
    times = [(1 / mark - 1 / start) / pace * DAY for start in starts]
    expected = sorted((at, f'cells_{row}.reach') for row, at in enumerate(times, 1))
    assert [(rule, outcome) for _, rule, outcome in result.trace] == [(rule, 'done') for _, rule in expected]
    # The level loses `p m²` in a day at the mark. The error of a run adds the errors of its
    # steps: an error of the level of 200 times the tolerance of a step is a time of
    # `200 rtol m / (p m²)` days.
    part = 200 * run.cfg.rtol
    slack = part * mark / (pace * mark * mark) * DAY
    for (found, _, _), (at, _) in zip(result.trace, expected):
        assert found == pytest.approx(at, abs=slack)
    assert list(result.final('cells_1.level')) == pytest.approx([mark] * 3, rel=part)
    assert result.outputs['level_left'] == pytest.approx(3 * mark, rel=part)
    assert result.outputs['gone_total'] == pytest.approx(sum(starts) - 3 * mark, rel=part)
    # A solver that the cap limits takes one step for each cap at the least.
    assert 0 < result.counts['solver steps'] < caps_of(run, sum(times)) / 4


# ---- a short pulse in a long quiet time ---------------------------------------------------------------

PULSE = """Cell:  @shape
    "One cell."
    let center: h = 500 h  @shape
    let width: h = 0.1 h  @shape
    var filled: fraction = 0 size 1  @shape
    flow burst: -> filled at 1 fraction/h * exp(-((t - center) / width) ** 2)

cells: Cell from "cells.csv"

output filled_total: fraction = sum(Cell.filled)  @shape
    "What all cells hold"
"""


def test_a_short_pulse_of_a_rate_in_a_long_quiet_time_is_not_jumped_over(tmp_path, adapter):
    """The rate of each cell is a pulse of a tenth of an hour, or half of that, at one time of 42
    days, and nothing else: the cell ends at the area of its pulse. Before its pulse a cell does
    not move, so the solver takes steps of many caps there, and a step over the pulse reads the
    rate at no time inside it. The engine reads the rate at each half of a cap inside a long step
    and does not use the step. The pulses are at a whole cap, at a half, between the two, early in
    the run; the last one is narrow, and in the middle between two whole caps.

    What a solver that the cap limits finds is the measure: the long steps lose no pulse that it
    finds. The solver of the engine reads the rate inside each of its steps, and finds all five.
    (A solver that reads the rate only at the ends of its steps finds a narrow pulse between two
    of its steps with no cap: the cap is the resolution of the engine for such a solver.)"""
    pulses = [(500.25, 0.1), (500.0, 0.1), (499.75, 0.1), (123.4, 0.1), (700.5, 0.05)]
    plan = plan_of(tmp_path, 42, PULSE, 'center: h @shape,width: h @shape', pulses)
    assert [(block.whole, block.linear) for block in plan.blocks] == [(False, False)]
    areas = [width * math.sqrt(math.pi) for _, width in pulses]

    def found(run):
        result = run.run()
        cells = list(result.final('cells_1.filled'))
        return result, [abs(cell - area) <= 1e-6 * area for cell, area in zip(cells, areas)]

    held = timeline.Run(plan, adapter=adapter)
    held.solver_step = held.max_step  # the solver takes no step longer than the cap
    limited, by_cap = found(held)
    run = timeline.Run(plan, adapter=adapter)
    result, by_long_steps = found(run)
    assert all(long or not cap for long, cap in zip(by_long_steps, by_cap))
    assert sum(by_long_steps) >= 4
    if adapter is solvers.DEFAULT:
        assert all(by_cap) and all(by_long_steps)
        assert result.outputs['filled_total'] == pytest.approx(sum(areas), rel=1e-7)
    # Long steps in the quiet time, and steps that were not used at the pulses.
    assert 0 < result.counts['solver steps'] < limited.counts['solver steps'] / 2
    assert limited.counts['solver steps'] > caps_of(held, len(pulses) * 42 * DAY) / 2
    assert result.counts['solver steps not used'] >= len(pulses)
    assert limited.counts['solver steps not used'] == 0


# ---- a state far after the time that a reader reads -----------------------------------------------------

DRAIN = """Cell:  @shape
    "One cell."
    let pace: ratio/h = 0.001 ratio/h  @shape
    let start: fraction = 0.5  @shape
    let shut_at: h = 380 h  @shape
    var level: fraction = start size 1  @shape
    var gone: fraction = 0  @shape
    var shut = false  @shape
    flow drain: level -> gone at pace * (1 fraction + level * level / 1 fraction) while not shut
    event close once when t >= shut_at:  @shape
        "The drain closes."
        shut = true

cells: Cell from "cells.csv"

output level_left: fraction = sum(Cell.level)  @shape
    "Level that all cells still have"
    level
"""


def test_a_state_of_a_long_step_after_the_time_of_an_event_that_starts_the_block_again_is_not_checked(
    tmp_path, adapter
):
    """The level of a cell falls as `tan(atan(y0) - k t)`: with nothing else it is below zero, its
    lower bound, from `atan(y0) / k` on. The drain of each cell closes before that time, so the
    level of the run never comes to zero. The solver takes steps of tens of hours here, and the
    step that holds the time of the event ends after the time of zero: the states of that step
    after the event are no states of the run. The run ends, with the level of the closed form at
    the time of the event."""
    start, shuts = 0.5, [380.0, 300.0, 395.0]
    pace = math.atan(start) / 400.0
    body = DRAIN.replace('0.001 ratio/h', f'{pace!r} ratio/h')
    plan = plan_of(tmp_path, 40, body, 'shut_at: h @shape', shuts)
    assert [(block.whole, block.linear) for block in plan.blocks] == [(False, False)]
    run = timeline.Run(plan, adapter=adapter)
    result = run.run()
    assert sorted(result.trace) == sorted(
        (at, f'cells_{row}.close', 'done') for row, at in enumerate(shuts, 1)
    )
    levels = [math.tan(math.atan(start) - pace * at) for at in shuts]
    assert min(levels) > 0
    assert list(result.final('cells_1.level')) == pytest.approx(levels, rel=1e-7)
    assert result.outputs['level_left'] == pytest.approx(sum(levels), rel=1e-7)
    assert 0 < result.counts['solver steps'] < caps_of(run, sum(shuts)) / 4


@pytest.mark.parametrize('shuts', [[380.0, 700.0, 395.0], [5000.0, 6000.0]])
def test_a_state_of_a_long_step_below_its_bound_before_the_time_that_a_reader_reads_is_outside(
    tmp_path, adapter, shuts
):
    """The same cells with a drain that closes after the time at which the level is at zero, or
    not in the run at all: the level of the run goes below its bound, in the middle of a step of
    tens of hours. A state of a block of the fast tier outside its bounds is outside what that
    tier runs, in a long step as in a short one: with an event after it, and with none, where the
    whole caps inside the step are the only times at which the engine reads the state."""
    start = 0.5
    pace = math.atan(start) / 400.0
    body = DRAIN.replace('0.001 ratio/h', f'{pace!r} ratio/h')
    plan = plan_of(tmp_path, 40, body, 'shut_at: h @shape', shuts)
    with pytest.raises(Outside):
        timeline.Run(plan, adapter=adapter).run()


TURN = """Cell:  @shape
    "One cell."
    let pace: ratio/h = 0.001 ratio/h  @shape
    let rise: fraction/h = 0.0003 fraction/h  @shape
    var level: fraction = 0.5 size 1  @shape
    var gone: fraction = 0 size 1  @shape
    var other: fraction = 0 size 1  @shape
    flow fill: -> other at rise
    flow drain: level -> gone at pace * level * (0.4 fraction - other) / 1 fraction

cells: Cell from "cells.csv"

output gone_total: fraction = sum(Cell.gone)  @shape
    "Level that all cells lost"
"""


def test_a_flow_whose_rate_goes_below_zero_inside_a_long_step_is_outside(tmp_path, adapter):
    """The drain of a cell has the rate `p y (0.4 - r t)`: it is below zero from `0.4 / r` hours
    on, and a flow cannot ask a rate below zero. With `r` of 0.0003 an hour that time is after
    the 30 days of the run: the run ends, and the level is `y0 exp(-p (0.4 t - r t² / 2))`. With
    `r` of 0.001 an hour the time is 400 h, in the middle of a step of tens of hours and with no
    event in the run: the state at the next whole cap is a state of the run, and it is outside
    what the fast tier runs. No value leaves its bounds in the 30 days (what went out is back
    in the cell at 800 h only), so the sign of the rate is all that says so."""
    pace, hours = 0.001, 30 * DAY
    rises = [0.0003, 0.0002, 0.00041]
    assert all(0.4 / rise > hours for rise in rises)
    plan = plan_of(tmp_path / 'above', 30, TURN, 'rise: fraction/h @shape', rises)
    assert [(block.whole, block.linear) for block in plan.blocks] == [(False, False)]
    run = timeline.Run(plan, adapter=adapter)
    result = run.run()
    levels = [0.5 * math.exp(-pace * (0.4 * hours - rise * hours * hours / 2)) for rise in rises]
    assert list(result.final('cells_1.level')) == pytest.approx(levels, rel=200 * run.cfg.rtol)
    assert result.outputs['gone_total'] == pytest.approx(3 * 0.5 - sum(levels), rel=200 * run.cfg.rtol)
    assert 0 < result.counts['solver steps'] < caps_of(run, 3 * hours) / 4
    below = plan_of(tmp_path / 'below', 30, TURN, 'rise: fraction/h @shape', [0.0003, 0.001])
    assert 0.4 / 0.001 < hours < 2 * 0.4 / 0.001
    with pytest.raises(Outside):
        timeline.Run(below, adapter=adapter).run()


# ---- a value over a mark for a time that is shorter than a step ------------------------------------------

HUMP = """Cell:  @shape
    "One cell."
    let enter: ratio/h = 0.0004 ratio/h  @shape
    let leave: ratio/h = 0.00025 ratio/h  @shape
    let mark: fraction = 0.3  @shape
    var feed: fraction = 1 size 1  @shape
    var level: fraction = 0 size 1  @shape
    var out: fraction = 0 size 1  @shape
    flow come: feed -> level at enter * feed
    flow go: level -> out at leave * level

cells: Cell from "cells.csv"

output out_total: fraction = sum(Cell.out)  @shape
    "What left all cells"
"""


def test_a_value_that_is_over_a_mark_only_inside_one_long_step_is_found_at_a_whole_cap(tmp_path, adapter):
    """The level of a chain of two slow decays rises to a peak after 130 days and falls again. A
    mark at two parts in a million below the peak is under the level for 12.6 hours. The solver
    takes steps of more than a day there, and one of them holds that whole time: the level is
    below the mark at the two ends of the step. The engine reads the level at each whole cap
    inside the step, as the ends of the steps of a solver that the cap limits read it, so the
    crossing is found, at the time of the closed form. (A model cannot write a condition on such
    a value: the reader of the roots of a block is asked here, as the engine asks it.)"""
    enter, leave = 0.0004, 0.00025

    def level(at):
        return enter / (leave - enter) * (math.exp(-enter * at) - math.exp(-leave * at))

    peak_at = math.log(leave / enter) / (leave - enter)
    marks = [level(peak_at) * (1 - part) for part in (2e-6, 1e-5, 1e-4)]
    plan = plan_of(tmp_path, 300, HUMP, 'mark: fraction @shape', marks)
    run = timeline.Run(plan, adapter=adapter)
    run.start()
    run.settle(0.0)
    inside = []
    for solution, mark in zip(run.single[0], marks):
        over = brentq(lambda at, mark=mark: level(at) - mark, 0.0, peak_at, xtol=1e-12)
        under = brentq(lambda at, mark=mark: level(at) - mark, peak_at, 300 * DAY, xtol=1e-12)
        place = solution.slices['cells_1.level'].start
        found = solution.first_root(place, mark, True, 0.0)
        # The level rises by `level''(peak) (over - peak)` an hour at the crossing: an error of
        # the level of a part in 1e8 is a time of that part over that rate.
        rate = enter * leave * level(peak_at) * (peak_at - over)
        assert found == pytest.approx(over, abs=1e-8 * mark / rate)
        inside.append(any(step.t_old < over and under < step.t for step in solution.steps))
        assert under - over > run.max_step
    assert inside[0], 'no step holds the whole time over the first mark: the test reads no long step'
