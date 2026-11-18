"""The timeline engine (`napkin/engine/timeline/`) on the hybrid core of a model.

The oracles are independent of the engine:

- closed forms of the models, from the numbers that each test writes into its table and gives to its
  inputs: the times of clocks and crossings, the sums of lines, and the solution of a linear and of a
  logistic equation;
- the run of the same file from its flat structure (`simulate`), where each row of a table is
  written out and the whole model is one component of the general tier: the order and the names of
  the events, and the values, within the tolerances of the solvers. It is a second path through the
  engine, not an oracle of its own: each test that uses it has a closed form too;
- properties: the count of the readings of the rules, a batch against its runs one by one, and the one
  difference between the two readings of the rules that D-65 names.

The engine has two tiers for the things outside the tables: the general tier, which is the continuous
engine on one component, and the fast tier, which the families use. Each test runs with those things
in each tier (`tier`): the same closed forms hold for both.
"""

import dataclasses
import json
import math
import pathlib

import mpmath
import numpy as np
import pytest

from napkin import expressions
from napkin.core import expr
from napkin.distributions import quantile
from napkin.engine import timeline
from napkin.engine.continuous.system import System
from napkin.engine.errors import SimulationError
from napkin.engine.runtime import NumericalSettings, simulate
from napkin.engine.sampling import draws
from napkin.model import ModelError, hybrid
from napkin.model import structure as typed
from napkin.model.ir import thaw
from napkin.model.model import build_model

HEAD = """scenario "A synthetic model"
    summary "A model of a test, with no source."
    horizon 10 days
    scope "Nothing: the model is synthetic."

"""
RECORD = '\nrecord shape: assumption "A synthetic model, with no source."\n'
DAY = 24.0
HORIZON = 10 * DAY


@pytest.fixture(autouse=True, params=['general', 'fast'])
def tier(request, monkeypatch):
    """The tier of the things outside the tables in the plans that a test makes without naming one."""
    if request.param == 'fast':
        of = timeline.Plan.of.__func__

        def fast(cls, core, run=None, values=None, scalars=None):
            return of(cls, core, run, values, scalars or 'fast')

        monkeypatch.setattr(timeline.Plan, 'of', classmethod(fast))
    return request.param


def package(tmp_path, body, **tables):
    """The path of a model with `body` after its head, and its tables {name: (header, values)}."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / 'model.scn'
    path.write_text(HEAD + body + RECORD, encoding='utf-8')
    for name, (header, values) in tables.items():
        text = '\n'.join([header, *(repr(float(value)) for value in values)]) + '\n'
        (tmp_path / f'{name}.csv').write_text(text, encoding='utf-8')
    return path


def flat_run(path, values=None, luck=None, names=()):
    """The run from the flat structure of the file: its trace as (time, rule, outcome), and the
    value of each output at the horizon; with `names`, also the value of each of them there.
    `luck` is the luck of a sample of a study, {seed, sample}."""
    model = build_model(path)
    library = thaw(model.library)
    resolved = model.resolve(next(iter(model.runs)), values)
    if luck is not None:
        resolved = dataclasses.replace(resolved, luck=typed.frozen(dict(luck)))
    trajectory = simulate(resolved, library)
    units = expressions.UnitSystem(library['units'])
    env = dict(trajectory.env_at(trajectory.horizon))
    # An output can read another output: each estimated output is evaluated when what it reads is
    # there. An output that the model does not estimate has no expression and no value.
    pending = {name: item.expr for name, item in resolved.outcomes.items() if item.expr is not None}
    outputs = {}
    while pending:
        ready = [
            name for name, source in pending.items() if not expressions.names_in(source) & pending.keys()
        ]
        assert ready, sorted(pending)
        for name in ready:
            outputs[name] = env[name] = float(expressions.evaluate(pending.pop(name), env, units))
    trace = [(entry['t'], entry['rule'], entry['outcome']) for entry in trajectory.trace]
    if names:
        return trace, outputs, {name: env[name] for name in names}
    return trace, outputs


def same_trace(found, expected, tolerance=1e-6):
    return len(found) == len(expected) and all(
        a[1:] == b[1:] and abs(a[0] - b[0]) <= tolerance for a, b in zip(found, expected)
    )


# ---- lines, clocks and a guard over a list ---------------------------------------------------------------

FLAGS = """Cell:  @shape
    "One cell."
    input pace: fraction/day = 0.05 fraction/day in 0 fraction/day to 1 fraction/day  @shape
    let due: h = 9 days  @shape
    var flag = false  @shape
    var filled: fraction = 0 size 1  @shape
    flow fill: -> filled at pace while not flag
    event raise_flag once when t >= due:  @shape
        "The cell raises its flag."
        flag = true

cells: Cell from "cells.csv"

watch:  @shape
    "The watcher of the cells."
    var alarm: "off" | "on" = "off"
    event sound once when count(Cell.flag) >= {n}:  @shape
        "Every cell has its flag up."
        alarm = "on"

output filled_total: fraction = sum(Cell.filled)  @shape
    "Content of all cells"
"""


def flags(tmp_path, dues):
    return package(tmp_path, FLAGS.replace('{n}', str(len(dues))), cells=('due: h @shape', dues))


@pytest.mark.parametrize('count', [1, 7, 60])
def test_lines_and_clocks_give_the_closed_form_and_the_guard_fires_after_the_last_flag(tmp_path, count):
    """Each cell fills at its pace until its own clock: the content of all cells is the pace times the
    sum of the times. The rows are not in the order of their times, so the order of the events is that
    of the times and not of the rows."""
    dues = [5.0 + ((k * 37) % count) * 150.0 / count + 0.25 * k / count for k in range(1, count + 1)]
    pace = 0.31
    plan = timeline.Plan.of(hybrid.compile(flags(tmp_path, dues)))
    result = timeline.run(plan, {'cells_1.pace': pace})
    assert result.outputs['filled_total'] == pytest.approx(pace / DAY * sum(dues), rel=1e-13)
    order = sorted(range(count), key=dues.__getitem__)
    expected = [(dues[k], f'cells_{k + 1}.raise_flag', 'done') for k in order]
    expected.append((max(dues), 'watch.sound', 'done'))
    assert same_trace(result.trace, expected, 1e-12)
    assert list(result.final('watch.alarm')) == ['on']
    assert np.array_equal(result.final('cells_1.filled'), pace / DAY * np.array(dues))


def test_the_flat_structure_of_a_table_gives_the_same_events_and_values(tmp_path):
    dues = [40.0, 12.5, 200.0, 77.0, 12.5]
    path = flags(tmp_path, dues)
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    trace, outputs = flat_run(path)
    assert same_trace(result.trace, trace)
    assert result.outputs['filled_total'] == pytest.approx(outputs['filled_total'], rel=1e-12)


def test_a_rule_is_read_only_when_its_answer_can_have_changed(tmp_path):
    """Each event writes the flag of one cell. The scoped reading reads the rule of that cell and the
    guard, so the readings of a run grow with the number of cells; the reading of every rule at every
    moment grows with its square. The events and the values of the two are the same."""
    counts = {}
    for count in (40, 400):
        dues = [1.0 + 200.0 * k / count for k in range(1, count + 1)]
        plan = timeline.Plan.of(hybrid.compile(flags(tmp_path / str(count), dues)))
        scoped, every = timeline.run(plan), timeline.run(plan, reading='every')
        assert scoped.trace == every.trace and scoped.outputs == every.outputs
        counts[count] = (scoped.counts['readings'], every.counts['readings'])
    assert counts[400][0] <= 11 * counts[40][0]
    assert counts[400][0] <= 5 * 400
    assert counts[400][1] >= 80 * counts[40][1]


# ---- a numeric block for each instance, a crossing and a delay ---------------------------------------------

GATES = """Cell:  @shape
    "One cell."
    input inflow: fraction/day = 0.06 fraction/day in 0 fraction/day to 1 fraction/day  @shape
    input leak: ratio/day = 0.02 ratio/day in 0 ratio/day to 1 ratio/day  @shape
    input spillway: fraction/day = 0.15 fraction/day in 0 fraction/day to 5 fraction/day  @shape
    let level: fraction = 0.02  @shape
    var water: fraction = 0.6 size 1  @shape
    var gate: "closed" | "open" = "closed"
    var spilled: fraction = 0 size 1  @shape
    var seeped: fraction = 0 size 1  @shape
    var arrived: fraction = 0 size 1  @shape
    flow arrive: -> arrived at inflow
    flow storm: -> water at inflow
    flow seep: water -> seeped at leak * water
    flow spill: water -> spilled at spillway while gate is "open"
    share water limit 10 fraction/day
    event open once when arrived >= level:  @shape
        "The gate opens."
        gate = "open"
    event shut once after 2 days when count(open) > 0:  @shape
        "The gate shuts."
        gate = "closed"

cells: Cell from "cells.csv"

output spilled_total: fraction = sum(Cell.spilled)  @shape
    "Water that all cells spill"

output seeped_total: fraction = sum(Cell.seeped)  @shape
    "Water that seeps from all cells"
"""


# The same cells with a delay that each run draws, and with what was in the cell 12 h before its gate
# shuts.
DRAWN = GATES.replace(
    '    event shut once after 2 days when count(open) > 0:  @shape\n'
    '        "The gate shuts."\n'
    '        gate = "closed"\n',
    '    var noted: fraction = 0 size 1  @shape\n'
    '    event shut once after uniform(1 days, 3 days) when count(open) > 0:  @shape\n'
    '        "The gate shuts."\n'
    '        gate = "closed"\n'
    '        noted = delayed(water, 12 h)\n',
)

# The same cells with two pairs that move by one fraction.
PAIRED = GATES.replace(
    '    flow storm: -> water at inflow\n',
    '    var twin: fraction = 0 size 1  @shape\n    flow storm at inflow:  @shape\n        -> water\n        -> twin\n',
)

# The same with a pair that takes from the water, so that it is of the group of the water's flows:
# the engine gives such a thing to the allocation in full.
SHARED_PAIR = PAIRED.replace('        -> twin\n', '        water -> twin at 0.001 fraction/day\n')

# The same with a seepage that reads the water of every cell: the cells then read one another, and the
# allocation is of one instance. A part that the timeline engine does not run yet.
OUTSIDE = SHARED_PAIR.replace(
    '    flow seep: water -> seeped at leak * water\n',
    '    flow seep: water -> seeped at leak * water * max(0, 1 - pool.mean)\n',
).replace(
    'Cell:  @shape\n',
    'pool:  @shape\n    "What the cells hold together."\n'
    '    let mean: fraction = sum(Cell.water) / 100000  @shape\n\nCell:  @shape\n',
    1,
)

# The same cells with an actor that decides.
DECIDED = GATES.replace(
    '\noutput spilled_total',
    '\nkeeper:  @shape\n    "A keeper of the cells."\n    sees keeper.calm\n    var calm = true  @shape\n'
    '    event decide once when t >= 30 h:  @shape\n        "The keeper decides."\n        choice\n'
    '        act 0.6:\n            calm = false\n        wait else:\n\noutput spilled_total',
    1,
)


def water_after(start, inflow, leak, spill, span):
    """The water of a cell after `span` hours of `water' = inflow - leak * water - spill`."""
    rest = (inflow - spill) / leak
    return rest + (start - rest) * math.exp(-leak * span)


def test_a_numeric_block_of_each_instance_gives_the_closed_form_of_its_linear_equation(tmp_path):
    levels = [0.05, 0.31, 0.12, 0.2]
    inflow, leak, spillway = 0.07, 0.04, 0.2
    path = package(tmp_path, GATES, cells=('level: fraction @shape', levels))
    values = {'cells_1.inflow': inflow, 'cells_1.leak': leak, 'cells_1.spillway': spillway}
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)), values)
    a, k, s = inflow / DAY, leak / DAY, spillway / DAY
    seeped, events = 0.0, []
    for row, level in enumerate(levels, 1):
        opens = level / a
        shuts = opens + 2 * DAY
        water = water_after(0.6, a, k, 0.0, opens)
        water = water_after(water, a, k, s, shuts - opens)
        water = water_after(water, a, k, 0.0, HORIZON - shuts)
        # What came in is in the cell, spilled or seeped.
        seeped += 0.6 + a * HORIZON - s * (shuts - opens) - water
        events += [(opens, row, f'cells_{row}.open', 'done'), (opens, row, f'cells_{row}.shut', None)]
        events.append((shuts, row, f'cells_{row}.shut', 'done'))
    assert result.outputs['spilled_total'] == pytest.approx(len(levels) * s * 2 * DAY, rel=1e-12)
    assert result.outputs['seeped_total'] == pytest.approx(seeped, rel=1e-7)
    expected = [(at, rule, outcome) for at, _, rule, outcome in sorted(events, key=lambda e: (e[0], e[1]))]
    assert same_trace(result.trace, expected, 1e-9)
    # The flat structure: the same events, and the values within the tolerances.
    flat = {f'cells.{row}.{name[8:]}': value for row in range(1, 5) for name, value in values.items()}
    trace, outputs = flat_run(path, flat)
    assert same_trace(result.trace, trace)
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-8)
    assert timeline.check(timeline.Plan.of(hybrid.compile(path)), values) == []


def test_an_event_of_one_instance_starts_only_its_own_block_again(tmp_path):
    """Three events for each cell: the block of a cell starts again at the two that change its gate,
    and at no event of another cell."""
    levels = [0.05 + 0.02 * k for k in range(6)]
    path = package(tmp_path, GATES, cells=('level: fraction @shape', levels))
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert len(result.trace) == 3 * len(levels)
    assert result.counts['block restarts'] == 2 * len(levels)


# ---- a list that feeds the rate of every instance ------------------------------------------------------

GROWTH = """pool:  @shape
    "What the cells hold together."
    let mean: fraction = sum(Cell.level) / {n}  @shape

Cell:  @shape
    "One cell."
    input gain: ratio/day = 0.5 ratio/day in 0 ratio/day to 2 ratio/day  @shape
    let start: fraction = 0.05  @shape
    var level: fraction = start size 1  @shape
    flow grow: -> level at gain * level * max(0, 1 - pool.mean)

cells: Cell from "cells.csv"

output level_total: fraction = sum(Cell.level)  @shape
    "Level of all cells"
"""


def test_a_list_in_the_rate_of_every_instance_is_one_block_with_the_logistic_closed_form(tmp_path):
    """Each level grows at `gain * level * (1 - mean)`, so the sum S of the levels has
    `S' = gain * S * (1 - S / n)`: the logistic curve."""
    starts = [0.05, 0.4, 0.11, 0.27, 0.33, 0.02, 0.19]
    count, gain = len(starts), 0.63
    path = package(tmp_path, GROWTH.replace('{n}', str(count)), cells=('start: fraction @shape', starts))
    plan = timeline.Plan.of(hybrid.compile(path))
    assert [(block.names, block.whole) for block in plan.blocks] == [(('cells_1.level',), True)]
    result = timeline.run(plan, {'cells_1.gain': gain})
    ratio, days = count / sum(starts) - 1, 10.0
    decay = math.exp(-gain * days)
    assert result.outputs['level_total'] == pytest.approx(count / (1 + ratio * decay), rel=1e-7)
    # Each level keeps its share of the sum: the levels grow by one factor.
    levels = result.final('cells_1.level')
    assert levels / levels.sum() == pytest.approx(np.array(starts) / sum(starts), rel=1e-7)
    trace, outputs = flat_run(path, {f'cells.{row}.gain': gain for row in range(1, count + 1)})
    assert trace == [] and result.trace == []
    assert result.outputs['level_total'] == pytest.approx(outputs['level_total'], rel=1e-8)


# ---- D-65: the two readings of the rules ---------------------------------------------------------------

TWO_PARTS = """first:  @shape
    "The part with a clock."
    let due: h = 99.99995 h  @shape
    var seen = false  @shape
    event ring once when t >= due:  @shape
        "The clock rings."
        seen = true

second:  @shape
    "The part with a crossing."
    let pace: fraction/h = 0.000001 fraction/h  @shape
    let mark: fraction = 0.0001  @shape
    var level: fraction = 0 size 1  @shape
    var crossed = false  @shape
    flow fill: -> level at pace
    event cross once when level >= mark:  @shape
        "The level reaches its mark."
        crossed = true

output level: fraction = second.level  @shape
    "The level"
"""


def test_the_one_difference_of_the_scoped_reading_is_the_crossing_inside_its_band_at_anothers_moment(
    tmp_path,
):
    """The level reaches its mark at 100 h. At the moment of the clock of the other part, 0.00005 h
    before, the level is inside its tolerance band (1e-10 of its size) and below its mark. The reading
    of every rule at every moment fires the crossing there, as the engine before D-65 did; the scoped
    reading fires it at its own time (D-65). Nothing else differs."""
    path = package(tmp_path, TWO_PARTS)
    plan = timeline.Plan.of(hybrid.compile(path))
    assert timeline.run(plan).trace == [
        (99.99995, 'first.ring', 'done'),
        (pytest.approx(100.0, abs=1e-9), 'second.cross', 'done'),
    ]
    found = timeline.check(plan)
    assert [(place, one[1:], other[1:]) for place, one, other in found] == [
        (1, ('second.cross', 'done'), ('second.cross', 'done'))
    ]
    assert found[0][1][0] == pytest.approx(100.0, abs=1e-9) and found[0][2][0] == 99.99995
    # The flat structure has the scoped reading too.
    trace, _ = flat_run(path)
    assert same_trace(timeline.run(plan).trace, trace, 1e-9)
    # Within the time that the level takes to cross its band, the two readings are one.
    assert timeline.check(plan, time_tolerance=1e-4) == []


# ---- a batch, and what the engine does not run ----------------------------------------------------------


def test_a_sample_of_a_batch_is_its_run_alone_and_a_failure_is_of_its_sample(tmp_path):
    levels = [0.05, 0.2, 0.11]
    path = package(tmp_path, GATES, cells=('level: fraction @shape', levels))
    plan = timeline.Plan.of(hybrid.compile(path))
    samples = [
        {'cells_1.inflow': 0.05},
        {'cells_1.inflow': 0.09, 'cells_1.leak': 0.1},
        # The spillway takes more than the cell holds, so the water comes to its bound. The fast tier
        # of the family does not run that state: the run of this sample is made in the general tier.
        {'cells_1.spillway': 4.0},
        {'cells_1.inflow': [0.05, 0.07, 0.11]},
        # The inflow of a cell is from 0 to 1: the run of this sample is refused, and no other.
        {'cells_1.inflow': -0.01},
    ]
    found = timeline.batch(plan, samples)
    assert [sample.status for sample in found] == ['finished'] * 4 + ['failed']
    assert 'bounds' in found[4].error and 'cells_1.inflow' in found[4].error
    family = plan.space_of_host['cells_1']
    assert [family in sample.result.run.plan.general for sample in found[:4]] == [False, False, True, False]
    for sample, values in zip(found, samples):
        if sample.status == 'finished':
            alone = timeline.run(plan, values)
            assert sample.result.outputs == alone.outputs and sample.result.trace == alone.trace
    # The run in the general tier has the events of the flat structure, and its values within the
    # tolerances of the solver: the flat structure has the three cells as one problem, and the
    # family each cell as its own. What came into a cell is in it, spilled or seeped, also while it
    # is empty.
    emptied = found[2].result
    trace, outputs = flat_run(path, {f'cells_{k}.spillway': 4.0 for k in (1, 2, 3)})
    assert same_trace(emptied.trace, trace, 1e-6)
    for name, value in outputs.items():
        assert emptied.outputs[name] == pytest.approx(value, rel=1e-7)
    held = sum(emptied.final(f'cells_1.{name}') for name in ('water', 'spilled', 'seeped'))
    assert list(held) == pytest.approx(list(0.6 + emptied.final('cells_1.arrived')), rel=1e-9)
    assert emptied.outputs['spilled_total'] > 3 * 0.6
    # An input of a family takes one value for all rows or one for each.
    opens = [at for at, rule, _ in found[3].result.trace if rule.endswith('.open')]
    assert sorted(opens) == pytest.approx(
        sorted(level / (a / DAY) for level, a in zip(levels, (0.05, 0.07, 0.11)))
    )


def test_a_part_that_the_engine_does_not_run_from_the_hybrid_core_is_an_error_that_names_it(tmp_path):
    path = package(tmp_path, GATES, cells=('level: fraction @shape', [0.05, 0.2]))
    core = hybrid.compile(path)
    assert len(timeline.run(timeline.Plan.of(core), {'cells_1.spillway': 0.2}).trace) == 6
    # A value of a family that brings its water to the bound is known in the run. The fast tier of
    # the family names that state as outside it, and the run is made in the general tier.
    plan = timeline.Plan.of(core)
    family = plan.space_of_host['cells_1']
    with pytest.raises(timeline.Outside, match='at a bound') as raised:
        timeline.Run(plan, {'cells_1.spillway': 4.0}).run()
    assert raised.value.space == family and family not in plan.general
    assert timeline.run(plan, {'cells_1.spillway': 4.0}).run.plan.general == {family}
    # Flows that move by one fraction and share a limit, in a thing whose rates read the other
    # instances, are a part that the engine does not run from the hybrid core: the error names the
    # part. The flat structure of the same file, where the cells are one component, runs.
    assert OUTSIDE != GATES
    other = package(tmp_path / 'other', OUTSIDE, cells=('level: fraction @shape', [0.05, 0.2]))
    with pytest.raises(timeline.Outside, match=r'move by one fraction.*another instance'):
        timeline.Plan.of(hybrid.compile(other))
    trace, _ = flat_run(other)
    assert [rule for _, rule, _ in trace].count('cells_2.shut') == 2


def test_a_list_in_a_line_of_the_template_of_its_own_table_is_refused_before_the_engine(tmp_path):
    """The hybrid core does not hold such a model, so no plan is made of a wrong one."""
    body = GROWTH.replace('{n}', '3').replace('max(0, 1 - pool.mean)', 'max(0, 1 - sum(Cell.level) / 3)')
    path = package(tmp_path, body, cells=('start: fraction @shape', [0.1, 0.2, 0.3]))
    with pytest.raises(ModelError) as raised:
        hybrid.compile(path)
    assert [item['code'] for item in raised.value.diagnostics] == ['hybrid']


# ---- a step that writes one member of a block ---------------------------------------------------------

CUTS = """pool:  @shape
    "What the cells hold together."
    let mean: fraction = sum(Cell.level) / {n}  @shape

Cell:  @shape
    "One cell."
    input gain: ratio/day = 0.5 ratio/day in 0 ratio/day to 2 ratio/day  @shape
    input keep: fraction = 0.5 in 0 to 1  @shape
    input mark: fraction = 0.3 in 0 to 1  @shape
    let start: fraction = 0.05  @shape
    var level: fraction = start size 1  @shape
    var grown: fraction = 0 size 1  @shape
    var gone: fraction = 0 size 1  @shape
    flow grow: -> level at gain * level * max(0, 1 - pool.mean)
    flow track: -> grown at gain * level * max(0, 1 - pool.mean)
    flow leave: level -> gone at 0 fraction/day
    event cut once when grown >= mark:  @shape
        "A part of the level is cut."
        level = keep * level

cells: Cell from "cells.csv"

output level_total: fraction = sum(Cell.level)  @shape
    "Level of all cells"
    level
"""


def test_a_step_that_writes_one_member_of_a_block_reads_again_the_rules_of_the_other_members(tmp_path):
    """The cut of one cell sets its level. Every level and every `grown` are in one block, because the
    mean of the levels feeds each rate. So the cut changes when the `grown` of each other cell reaches
    its mark: those crossings are read again, though the step wrote none of the values that they read.
    The oracles: the flat structure, and the reading of every rule at every moment."""
    starts = [0.05, 0.1, 0.2, 0.15]
    point = {'gain': 0.63, 'keep': 0.5, 'mark': 0.1}
    path = package(tmp_path, CUTS.replace('{n}', '4'), cells=('start: fraction @shape', starts))
    plan = timeline.Plan.of(hybrid.compile(path))
    assert [(len(block.names), block.whole) for block in plan.blocks] == [(2, True)]
    values = {f'cells_1.{name}': value for name, value in point.items()}
    result = timeline.run(plan, values)
    assert len(result.trace) == 4
    flat = {f'cells.{row}.{name}': value for row in range(1, 5) for name, value in point.items()}
    trace, outputs = flat_run(path, flat)
    assert same_trace(result.trace, trace, 1e-5)
    assert result.outputs['level_total'] == pytest.approx(outputs['level_total'], rel=1e-7)
    assert timeline.check(plan, values, time_tolerance=1e-6) == []


# ---- one moment ----------------------------------------------------------------------------------------


def test_a_crossing_whose_time_is_within_the_tolerance_of_a_moment_is_due_in_that_moment(tmp_path):
    """The level reaches its mark 5e-9 h after the clock of the other part, which is inside the
    1e-8 h of one moment. The level is then far outside its tolerance band (it rises by 1 for each
    hour, and the band is 1e-10). With the scoped reading the two rules are due in one moment, as two
    clocks would be (D-65). With the reading of every rule, as in the engine before D-65, the crossing
    has a moment of its own, 5e-9 h later. That is the second difference that D-65 names."""
    body = (
        TWO_PARTS.replace('99.99995 h', '99.999999995 h')
        .replace('0.000001 fraction/h', '1 fraction/h')
        .replace('let mark: fraction = 0.0001', 'let mark: fraction = 100')
    )
    path = package(tmp_path, body)
    plan = timeline.Plan.of(hybrid.compile(path))
    scoped, every = timeline.run(plan), timeline.run(plan, reading='every')
    assert scoped.trace == [(99.999999995, 'first.ring', 'done'), (99.999999995, 'second.cross', 'done')]
    assert scoped.counts['moments'] == every.counts['moments'] - 1
    assert every.trace[1][0] == pytest.approx(100.0, abs=1e-12) and every.trace[1][0] > 99.999999995
    # The flat structure has the scoped reading too.
    trace, _ = flat_run(path)
    assert scoped.trace == trace
    assert timeline.check(plan, time_tolerance=1e-8) == []


CUBIC = """vat:  @shape
    "A vat whose content grows faster as it gets older."
    var age: fraction = 0 size 1  @shape
    var content: fraction = 0 size 1  @shape
    var full = false  @shape
    flow older: -> age at 1 fraction/h
    flow grow: -> content at 1 ratio/h * age * age / 1 fraction
    event fill once when content >= 9000 fraction:  @shape
        "The content reaches its mark."
        full = true

clock:  @shape
    "A clock that looks at the vat."
    var saw = false  @shape
    event ring once when t >= 29.999999995 h:  @shape
        "The clock rings."
        saw = vat.full

output content: fraction = vat.content  @shape
    "The content"
"""


def test_a_crossing_of_a_solver_within_the_tolerance_after_a_moment_is_due_in_that_moment(tmp_path):
    """The age is the time in hours, so the content is `t^3 / 3` and reaches 9000 at 30 h. The rate
    of the content is not linear, so a solver makes the segment; the rate is a polynomial of the
    second degree in the time, which the formula of the solver integrates with no error but that of
    the arithmetic. The clock of the other part is 5e-9 h before, inside the 1e-8 h of one moment;
    the content is then 4.5e-6 under its mark, far outside its tolerance band.

    The two rules are due in one moment (D-65, "One moment"), in the order of the file: the crossing
    first, and the clock reads what the crossing wrote. A solver finds only the crossings inside the
    segment that it was asked for, which ends at the clock."""
    path = package(tmp_path, CUBIC)
    model = build_model(path)
    record = timeline.trajectory(model.resolve(next(iter(model.runs))), thaw(model.library))
    assert [(entry['t'], entry['rule']) for entry in record.trace] == [
        (29.999999995, 'vat.fill'),
        (29.999999995, 'clock.ring'),
    ]
    assert record.env_at(HORIZON)['clock.saw'] == 1.0
    assert record.env_at(HORIZON)['vat.content'] == pytest.approx(HORIZON**3 / 3, rel=1e-12)
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert result.trace == [(29.999999995, 'vat.fill', 'done'), (29.999999995, 'clock.ring', 'done')]


# ---- links between tables, moves, named events and the choice of an outcome ---------------------------------

LINKED = """Pool:  @shape
    "A pool."
    let factor: fraction = 1  @shape
    var open = false  @shape
    event opens once when t >= factor * 100 h:  @shape
        "The pool opens."
        open = true

Tank:  @shape
    "A tank."
    let pool: Pool
    let pace: fraction/h = 0.01 fraction/h  @shape
    var held: fraction = 0 size 1  @shape
    flow fill: -> held at pace * pool.factor while pool.open

pools: Pool from "pools.csv"
tanks: Tank from "tanks.csv"

output total: fraction = sum(Tank.held)  @shape
    "What all tanks hold"
"""


def test_a_part_of_one_table_reads_the_row_of_another_table_that_its_own_row_links_to(tmp_path):
    """A tank fills at the factor of its pool, from the time at which its pool opens: the closed form
    is `pace * f * (T - 100 f)` for each tank, with f the factor of its pool. The event of a pool starts
    again the lines of the tanks that link to it, and of no other tank."""
    factors = [1.0, 0.5, 0.25]
    links = [1 + (5 * k) % 3 for k in range(7)]
    path = package(tmp_path, LINKED, pools=('factor: fraction @shape', factors))
    (tmp_path / 'tanks.csv').write_text('pool\n' + '\n'.join(f'pools.{k}' for k in links) + '\n')
    plan = timeline.Plan.of(hybrid.compile(path))
    result = timeline.run(plan)
    held = [0.01 * factors[k - 1] * (HORIZON - 100 * factors[k - 1]) for k in links]
    assert result.outputs['total'] == pytest.approx(sum(held), rel=1e-13)
    assert list(result.final('tanks_1.held')) == pytest.approx(held, rel=1e-13)
    # At the start each line starts once; then each tank starts again once, when its pool opens.
    assert result.counts['line restarts'] == 2 * len(links)
    trace, outputs = flat_run(path)
    assert same_trace(result.trace, trace) and result.outputs['total'] == pytest.approx(outputs['total'])


STEPS = """store:  @shape
    "A store."
    var stock: fraction = 0.8 size 1  @shape
    var taken: fraction = 0 size 1  @shape
    var seen = false  @shape
    flow rest: stock -> taken at 0 fraction/day
    event note:  @shape
        "The taking is noted."
        seen = true
    event take once when t >= 30 h:  @shape
        "A part is taken, or nothing happens."
        most {chance}:
            move 0.25 from stock to taken
            note
        nothing else:

output left: fraction = store.stock  @shape
    "What the store holds"
    level
"""


@pytest.mark.parametrize(('chance', 'taken'), [('0.7', True), ('0.4', False), ('0.5', True)])
def test_the_central_run_takes_the_likeliest_outcome_which_moves_an_amount_and_names_an_event(
    tmp_path, chance, taken
):
    """The outcome with the larger chance happens, and the first in the file on a tie. The move takes
    its amount out of one number and puts it into the other, and the event that the outcome names
    triggers after the lines of the outcome."""
    path = package(tmp_path, STEPS.replace('{chance}', chance))
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    if taken:
        assert result.trace == [(30.0, 'store.take', 'most'), (30.0, 'store.note', 'done')]
        assert result.outputs['left'] == pytest.approx(0.8 - 0.25, rel=1e-15)
        assert list(result.final('store.taken')) == [0.25] and list(result.final('store.seen')) == [1.0]
    else:
        assert result.trace == [(30.0, 'store.take', 'nothing')]
        assert result.outputs['left'] == 0.8 and list(result.final('store.seen')) == [0.0]
    trace, outputs = flat_run(path)
    assert result.trace == trace and result.outputs['left'] == pytest.approx(outputs['left'], rel=1e-15)


# ---- a block is integrated when a reader asks; a model too large for a flat structure -----------------------


def test_a_block_is_integrated_only_as_far_as_a_reader_asks(tmp_path):
    starts = [0.05, 0.4, 0.11]
    path = package(tmp_path, GROWTH.replace('{n}', '3'), cells=('start: fraction @shape', starts))
    run = timeline.Run(timeline.Plan.of(hybrid.compile(path)))
    run.start()
    run.settle(0.0)
    assert run.counts['solver steps'] == 0 and run.counts['evaluations'] == 0
    run.column('cells_1.level', 5.0)
    solution = run.whole[0]
    assert run.counts['solver steps'] > 0 and 5.0 <= solution.frontier < run.horizon / 2


def test_a_model_too_large_for_a_flat_structure_with_a_part_outside_the_engine_has_an_error_by_name(tmp_path):
    """A sum over 700 rows is one node of the hybrid core and too long for a flat structure. A part
    that the engine does not run from the hybrid core (flows that move by one fraction, one of them
    in an allocation group, in a thing whose rates read the other instances) then has no run: the
    engine names the part, and the compiler refuses the flat structure."""
    levels = [0.05 + 0.2 * k / 700 for k in range(700)]
    path = package(tmp_path, OUTSIDE, cells=('level: fraction @shape', levels))
    with pytest.raises(timeline.Outside, match='move by one fraction'):
        timeline.Plan.of(hybrid.compile(path))
    with pytest.raises(ModelError):
        build_model(path)


# ---- a status, a firing that waits while a condition holds, and a window ------------------------------------

STATUS = """plant:  @shape
    "A plant."
    var load: "low" | "high" = "low"
    var risen: fraction = 0  @shape
    status failed when load is "high"
        "The plant fails."
    status ok
        "The plant works."
    event rise once when t >= {at} h:  @shape
        "The load rises."
        load = "high"
        risen = 1

output risen: fraction = plant.risen  @shape
    "Whether the load rose"
    level
"""


@pytest.mark.parametrize(('at', 'status'), [(50, 'failed'), (500, 'ok')])
def test_a_status_is_the_value_of_its_first_case_that_holds(tmp_path, at, status):
    """The status is `failed` from the event that makes the load high, and `ok` when no event does
    (500 h is after the horizon of 240 h)."""
    path = package(tmp_path, STATUS.replace('{at}', str(at)))
    plan = timeline.Plan.of(hybrid.compile(path))
    (name,) = plan.s.labels
    run = timeline.Run(plan)
    result = run.run()
    assert list(result.final(name)) == [status]
    assert list(run.column(name, HORIZON)) == [status]
    assert result.trace == ([(float(at), 'plant.rise', 'done')] if at < HORIZON else [])


TWO_CASES = """plant:  @shape
    "A plant."
    var load: "low" | "high" = "low"
    var worn: fraction = 0  @shape
    status failed when load is "high"
        "The plant fails."
    status degraded when worn >= 1
        "The plant works badly."
    status ok
        "The plant works."
    event wear once when t >= 20 h:  @shape
        "The plant wears."
        worn = 1
    event rise once when t >= {at} h:  @shape
        "The load rises."
        load = "high"

output worn: fraction = plant.worn  @shape
    "Whether the plant is worn"
    level
"""


@pytest.mark.parametrize(('at', 'status'), [(50, 'failed'), (500, 'degraded')])
def test_a_status_with_two_cases_that_hold_is_the_first_of_them(tmp_path, at, status):
    """The plant is worn from 20 h, so the second case holds at the end of each run. Where the load
    is high too (from 50 h), both cases hold, and the status is that of the first case of the file.
    Where the load does not rise (500 h is after the horizon of 240 h), it is that of the second."""
    plan = timeline.Plan.of(hybrid.compile(package(tmp_path, TWO_CASES.replace('{at}', str(at)))))
    (name,) = plan.s.labels
    assert list(timeline.run(plan).final(name)) == [status]


WAITS = """plant:  @shape
    "A plant."
    var alarm: "off" | "on" = "off"
    var fixed: fraction = 0  @shape
    event sound once when t >= 20 h:  @shape
        "The alarm sounds."
        alarm = "on"
    event quiet once when t >= {quiet} h:  @shape
        "The alarm stops."
        alarm = "off"
    event again once when t >= 100 h:  @shape
        "The alarm sounds again."
        alarm = "on"
    event repair after 30 h when alarm is "on" while alarm is "on":  @shape
        "The repair is done."
        fixed += 1

output fixed: fraction = plant.fixed  @shape
    "The repairs"
    level
"""


@pytest.mark.parametrize('quiet', [40, 60])
def test_a_firing_that_waits_is_cancelled_when_its_while_fails_and_the_event_can_trigger_again(
    tmp_path, quiet
):
    """The repair triggers when the alarm sounds, at 20 h, and waits 30 h. An alarm that stops at 40 h
    cancels it; an alarm that stops at 60 h is after it. The alarm sounds again at 100 h, and the
    repair triggers again and fires at 130 h. The times are sums of the numbers of the model."""
    path = package(tmp_path, WAITS.replace('{quiet}', str(quiet)))
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    expected = [(20.0, 'plant.sound', 'done'), (20.0, 'plant.repair', None)]
    if quiet == 40:
        expected += [(40.0, 'plant.quiet', 'done')]
    else:
        expected += [(50.0, 'plant.repair', 'done'), (60.0, 'plant.quiet', 'done')]
    expected += [
        (100.0, 'plant.again', 'done'),
        (100.0, 'plant.repair', None),
        (130.0, 'plant.repair', 'done'),
    ]
    assert result.trace == expected
    assert result.outputs['fixed'] == (1 if quiet == 40 else 2)
    trace, outputs = flat_run(path)
    assert result.trace == trace and result.outputs == outputs
    assert timeline.check(timeline.Plan.of(hybrid.compile(path))) == []


WINDOWS = """clock:  @shape
    "A clock."
    var beat: fraction = 0  @shape
    event first once when t >= 10 h:  @shape
        "The first beat."
        beat = 1
    event second once when t >= 30 h:  @shape
        "The second beat."
        beat = 2
    event third once when t >= 60 h:  @shape
        "The first beat again."
        beat = 1
    event fourth once when t >= 90 h:  @shape
        "The same beat: no new window."
        beat = 1

watcher:  @shape
    "A watcher."
    var seen: fraction = 0  @shape
    var awake = true  @shape
    event review each clock.beat when awake:  @shape
        "The watcher looks once in each window."
        seen += 1

output seen: fraction = watcher.seen  @shape
    "The looks of the watcher"
    level
"""


def test_an_event_with_a_window_triggers_once_in_each_window_and_a_value_seen_before_opens_a_new_one(
    tmp_path,
):
    """The window is the value of the beat. The watcher looks at the start, at each change of the
    beat (to 1, to 2, and back to 1), and not when an event sets the beat to the value that it has."""
    path = package(tmp_path, WINDOWS)
    plan = timeline.Plan.of(hybrid.compile(path))
    result = timeline.run(plan)
    assert result.trace == [
        (0.0, 'watcher.review', 'done'),
        (10.0, 'clock.first', 'done'),
        (10.0, 'watcher.review', 'done'),
        (30.0, 'clock.second', 'done'),
        (30.0, 'watcher.review', 'done'),
        (60.0, 'clock.third', 'done'),
        (60.0, 'watcher.review', 'done'),
        (90.0, 'clock.fourth', 'done'),
    ]
    assert result.outputs['seen'] == 4
    trace, outputs = flat_run(path)
    assert result.trace == trace and result.outputs == outputs
    assert timeline.check(plan) == []


# ---- an outcome with a condition, and the checks of the state ----------------------------------------------

GUARDED = """store:  @shape
    "A store."
    var stock: fraction = 0.8 size 1  @shape
    var taken: fraction = 0 size 1  @shape
    var open = {open}  @shape
    flow rest: stock -> taken at 0 fraction/day
    assert stock + taken is 0.8 within 0.001  @shape
        "What the store had is in the store or taken."
    assert taken <= 0.9  @shape
        "No more is taken than the store had."
    event take once when t >= 30 h:  @shape
        "A part is taken, or nothing happens."
        most {chance} when open:
            move 0.25 from stock to taken
        nothing else:
    event lose once when t >= 60 h:  @shape
        "A part is lost."
        stock -= {lost}

output left: fraction = store.stock  @shape
    "What the store holds"
    level
"""


def guarded(tmp_path, **values):
    body = GUARDED
    for name, value in {'open': 'true', 'chance': '0.7', 'lost': '0', **values}.items():
        body = body.replace('{' + name + '}', value)
    return package(tmp_path, body)


def stops(run):
    """The codes of the diagnostics of the error that stops a run, and the time that they name."""
    with pytest.raises(SimulationError) as raised:
        run()
    return [(item['code'], item['t']) for item in raised.value.diagnostics]


def test_an_outcome_can_happen_only_while_its_condition_holds(tmp_path):
    """With the store open, the likelier outcome takes its part. With the store shut and a chance that
    is 0 then, the other outcome happens. With the store shut and a chance of 0.7, the model gives a
    chance to an outcome that cannot happen: the run stops at the event, from the hybrid core and
    from the flat structure."""
    path = guarded(tmp_path / 'open')
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert result.trace[0] == (30.0, 'store.take', 'most') and result.outputs['left'] == pytest.approx(
        0.8 - 0.25
    )
    path = guarded(tmp_path / 'shut', open='false', chance='(0.7 if open else 0)')
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert result.trace[0] == (30.0, 'store.take', 'nothing') and result.outputs['left'] == 0.8
    assert (result.trace, result.outputs) == flat_run(path)
    path = guarded(tmp_path / 'wrong', open='false')
    plan = timeline.Plan.of(hybrid.compile(path))
    assert stops(lambda: timeline.run(plan)) == [('chances', 30.0)] == stops(lambda: flat_run(path))


def test_a_partition_that_a_step_breaks_stops_the_run_at_that_step(tmp_path):
    """The store and what was taken add up to what the store had. The move keeps the sum; the loss of
    0.1 at 60 h breaks it by more than its tolerance of 0.001, and a loss of 0.0005 does not."""
    path = guarded(tmp_path / 'small', lost='0.0005')
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert result.outputs['left'] == pytest.approx(0.8 - 0.25 - 0.0005)
    path = guarded(tmp_path / 'large', lost='0.1')
    plan = timeline.Plan.of(hybrid.compile(path))
    assert stops(lambda: timeline.run(plan)) == [('partition_failed', 60.0)] == stops(lambda: flat_run(path))


MARKS = """Cell:  @shape
    "One cell."
    let cap: fraction = 1  @shape
    let due: h = 30 h  @shape
    var mark: fraction = 0  @shape
    assert mark <= cap  @shape
        "The mark stays at or below its cap."
    event lift once when t >= due:  @shape
        "The mark is lifted."
        mark = 2

cells: Cell from "cells.csv"

output marks: fraction = sum(Cell.mark)  @shape
    "The marks"
    level
"""


def test_a_check_of_a_template_is_read_for_the_row_whose_step_wrote_what_it_reads(tmp_path):
    """Each cell lifts its mark to 2 at its own time. The caps of the first and the third cell are
    above 2; the cap of the second is 1.5, so its check fails at its event, at 50 h, after the first
    cell lifted its mark at 20 h with no failure. The error names the check of that row as the flat
    structure names it."""
    caps, dues = [3.0, 1.5, 5.0], [20.0, 50.0, 10.0]
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = package(tmp_path, MARKS)
    (tmp_path / 'cells.csv').write_text(
        'cap: fraction @shape,due: h @shape\n'
        + '\n'.join(f'{cap},{due}' for cap, due in zip(caps, dues))
        + '\n'
    )
    plan = timeline.Plan.of(hybrid.compile(path))
    with pytest.raises(SimulationError) as raised:
        timeline.run(plan)
    assert [(item['code'], item['t'], item['check']) for item in raised.value.diagnostics] == [
        ('check_failed', 50.0, 'Cell.0.cells_2')
    ]
    with pytest.raises(SimulationError) as flat:
        flat_run(path)
    assert [(item['code'], item['t'], item['check']) for item in flat.value.diagnostics] == [
        ('check_failed', 50.0, 'Cell.0.cells_2')
    ]
    # With every cap above 2 no check fails, and each cell has its mark.
    (tmp_path / 'cells.csv').write_text(
        'cap: fraction @shape,due: h @shape\n'
        + '\n'.join(f'{cap + 2},{due}' for cap, due in zip(caps, dues))
        + '\n'
    )
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert result.outputs['marks'] == 6 and [at for at, _, _ in result.trace] == sorted(dues)


def test_a_block_that_takes_more_evaluations_than_its_budget_between_two_moments_stops_the_run(tmp_path):
    starts = [0.05, 0.4, 0.11]
    path = package(tmp_path, GROWTH.replace('{n}', '3'), cells=('start: fraction @shape', starts))
    plan = timeline.Plan.of(hybrid.compile(path))
    enough = timeline.run(plan).counts['evaluations']
    assert timeline.run(plan, settings={'max_evaluations': enough}).counts['evaluations'] == enough
    with pytest.raises(SimulationError, match='evaluations'):
        timeline.run(plan, settings={'max_evaluations': enough - 1})


# ---- a value that a firing draws, the luck of a sample, and a value of the past ---------------------------


def test_a_delay_that_a_run_draws_is_its_central_value_and_with_luck_the_next_number_of_its_stream(tmp_path):
    """The gate of a cell shuts a time after it opens that the run draws between 1 and 3 days. The
    central run takes the middle, 2 days. A sample of a study takes the number of the stream of the
    event of that cell: the test draws the same number from the stream by its name and puts it
    through the quantile of the distribution, and the flat structure gives the same events."""
    levels = [0.05, 0.2, 0.11]
    path = package(tmp_path, DRAWN, cells=('level: fraction @shape', levels))
    plan = timeline.Plan.of(hybrid.compile(path))
    inflow = 0.06 / DAY
    opens = [level / inflow for level in levels]
    central = timeline.run(plan)
    shuts = {rule: at for at, rule, outcome in central.trace if outcome == 'done' and rule.endswith('.shut')}
    assert [shuts[f'cells_{k}.shut'] for k in (1, 2, 3)] == pytest.approx([at + 2 * DAY for at in opens])
    luck = {'seed': 20261112, 'sample': 5}
    sampled = timeline.run(plan, luck=luck)
    expected = []
    for k, at in enumerate(opens, 1):
        number = draws(luck['seed'], f'cells_{k}.shut/draw/{luck["sample"]}')()
        expected.append(at + quantile('uniform', {'min': 1 * DAY, 'max': 3 * DAY}, number))
    shuts = {rule: at for at, rule, outcome in sampled.trace if outcome == 'done' and rule.endswith('.shut')}
    assert [shuts[f'cells_{k}.shut'] for k in (1, 2, 3)] == pytest.approx(expected, rel=1e-12)
    assert len(set(expected)) == 3 and all(abs(at - (o + 2 * DAY)) > 1e-3 for at, o in zip(expected, opens))
    trace, outputs = flat_run(path, luck=luck)
    assert same_trace(sampled.trace, trace)
    for name, value in outputs.items():
        assert sampled.outputs[name] == pytest.approx(value, rel=1e-8)
    # The same luck gives the same run; another sample gives other draws.
    assert timeline.run(plan, luck=luck).trace == sampled.trace
    assert timeline.run(plan, luck={**luck, 'sample': 6}).trace != sampled.trace


def test_a_value_of_the_past_is_the_value_at_that_time_from_the_record_of_the_run(tmp_path):
    """When its gate shuts, a cell notes what it held 12 h before. The gate was open then (it is open
    for 2 days in the central run), so the water of that time has the closed form of the open gate
    from the time at which it opened."""
    levels = [0.05, 0.2]
    inflow, leak, spillway = 0.07, 0.04, 0.2
    path = package(tmp_path, DRAWN, cells=('level: fraction @shape', levels))
    values = {'cells_1.inflow': inflow, 'cells_1.leak': leak, 'cells_1.spillway': spillway}
    plan = timeline.Plan.of(hybrid.compile(path))
    assert plan.records
    result = timeline.run(plan, values)
    a, k, s = inflow / DAY, leak / DAY, spillway / DAY
    noted = []
    for level in levels:
        opens = level / a
        at_opening = water_after(0.6, a, k, 0.0, opens)
        noted.append(water_after(at_opening, a, k, s, 2 * DAY - 12.0))
    assert list(result.final('cells_1.noted')) == pytest.approx(noted, rel=1e-9)
    flat = {f'cells.{row}.{name[8:]}': value for row in (1, 2) for name, value in values.items()}
    trace, _, found = flat_run(path, flat, names=('cells_1.noted', 'cells_2.noted'))
    assert same_trace(result.trace, trace)
    assert list(result.final('cells_1.noted')) == pytest.approx(list(found.values()), rel=1e-8)


def test_with_luck_an_outcome_is_drawn_from_the_stream_of_its_event(tmp_path):
    """The outcome of the firing is the one whose share of the chances holds the number of the stream
    of the event: below 0.7 the first, else the second. The test reads the same number from the stream
    by its name, for several samples, and both outcomes come up."""
    path = package(tmp_path, STEPS.replace('{chance}', '0.7'))
    plan = timeline.Plan.of(hybrid.compile(path))
    taken = []
    for sample in range(12):
        luck = {'seed': 99, 'sample': sample}
        number = draws(luck['seed'], f'store.take/{sample}')()
        result = timeline.run(plan, luck=luck)
        assert result.trace[0] == (30.0, 'store.take', 'most' if number < 0.7 else 'nothing')
        trace, outputs = flat_run(path, luck=luck)
        assert result.trace == trace and result.outputs == outputs
        taken.append(number < 0.7)
    assert True in taken and False in taken


def test_chance_takes_the_decision_of_an_actor_in_a_run_that_nobody_plays(tmp_path):
    """The keeper decides at 30 h between two outcomes, and nobody plays the run: the central run
    takes the likelier one, as for any event, and the cells run as they do without the keeper."""
    levels = [0.05, 0.2]
    path = package(tmp_path, DECIDED, cells=('level: fraction @shape', levels))
    plan = timeline.Plan.of(hybrid.compile(path))
    result = timeline.run(plan)
    assert (30.0, 'keeper.decide', 'act') in result.trace
    assert list(result.final('keeper.calm')) == [0.0]
    trace, outputs = flat_run(path)
    assert same_trace(result.trace, trace)
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-8)
    without = timeline.run(
        timeline.Plan.of(
            hybrid.compile(package(tmp_path / 'plain', GATES, cells=('level: fraction @shape', levels)))
        )
    )
    assert [entry for entry in result.trace if entry[1] != 'keeper.decide'] == without.trace
    assert result.outputs == without.outputs
    # A run that a person plays stops at the decision for a pick, with what the keeper sees; with
    # the pick of the other outcome, the keeper stays calm and the cells run as before
    # (tests/engine/test_timeline_play.py has the played run in full).
    reader = {'keeper': 'reader'}
    paused = timeline.run(plan, play={'control': reader}, pause_at_decision=True)
    assert paused.paused and paused.end_time == 30.0
    assert paused.decision['event'] == 'keeper.decide' and paused.decision['view'] == {'keeper.calm': True}
    pick = [{'event': 'keeper.decide', 'outcome': 'wait'}]
    waited = timeline.run(plan, play={'control': reader, 'picks': pick}, pause_at_decision=True)
    assert not waited.paused and list(waited.final('keeper.calm')) == [1.0]
    assert [entry for entry in waited.trace if entry[1] != 'keeper.decide'] == without.trace
    # A resolver answers the decision. With a spillway that empties a cell after the decision, the
    # run is made again with the family in the general tier: the resolver is still asked once.
    later = package(tmp_path / 'later', DECIDED, cells=('level: fraction @shape', [0.2, 0.25]))
    plan = timeline.Plan.of(hybrid.compile(later))
    with pytest.raises(timeline.Outside, match='at a bound'):
        timeline.Run(plan, {'cells_1.spillway': 4.0}, play={'control': reader, 'picks': pick}).run()
    asked = []

    def resolver(decision, env, trace):
        asked.append((decision['event'], decision['t'], decision['pick_index']))
        return pick[0]

    options = {'play': {'control': reader}, 'pause_at_decision': True, 'decision_resolver': resolver}
    emptied = timeline.run(plan, {'cells_1.spillway': 4.0}, **options)
    assert emptied.run.plan.general - plan.general == {plan.space_of_host['cells_1']}
    assert asked == [('keeper.decide', 30.0, 0)] and list(emptied.final('keeper.calm')) == [1.0]


# ---- the limit of a group of flows -------------------------------------------------------------------------

SHARED = """tank:  @shape
    "A tank that two flows drain."
    input first_rate: fraction/day = 0.3 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    input second_rate: fraction/day = 0.1 fraction/day in 0 fraction/day to 2 fraction/day  @shape
    var held: fraction = 5 size 1  @shape
    var one: fraction = 0 size 1  @shape
    var two: fraction = 0 size 1  @shape
    var boost = false  @shape
    flow first: held -> one at first_rate
    flow second: held -> two at 4 * second_rate if boost else second_rate
    share held limit {limit} fraction/day{order}
    event rise once when t >= 5 days:  @shape
        "The second flow asks four times as much."
        boost = true

output one: fraction = tank.one  @shape
    "What the first flow moved"

output two: fraction = tank.two  @shape
    "What the second flow moved"
"""


def shared(tmp_path, limit, order=''):
    return package(tmp_path, SHARED.replace('{limit}', str(limit)).replace('{order}', order))


def test_flows_that_ask_more_than_the_limit_of_their_group_share_it_in_proportion(tmp_path):
    """The flows ask 0.3 and 0.1 a day for 5 days, and then 0.3 and 0.4. With a limit of 0.5 a day
    the first 5 days are below it; then each flow gets 0.5 / 0.7 of what it asks."""
    path = shared(tmp_path, 0.5)
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert result.outputs['one'] == pytest.approx(0.3 * 5 + 0.3 * 0.5 / 0.7 * 5, rel=1e-13)
    assert result.outputs['two'] == pytest.approx(0.1 * 5 + 0.4 * 0.5 / 0.7 * 5, rel=1e-13)
    assert list(result.final('tank.held')) == pytest.approx([5 - 0.4 * 5 - 0.5 * 5], rel=1e-13)
    trace, outputs = flat_run(path)
    assert result.trace == trace
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-12)


def test_a_group_with_an_order_serves_its_flows_one_after_the_other(tmp_path):
    """With a limit of 0.35 a day and the order first, second: the first flow has its 0.3 in full and
    the second the 0.05 that is left, also when it asks 0.4."""
    path = shared(tmp_path, 0.35, ' order first, second')
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert result.outputs['one'] == pytest.approx(0.3 * 10, rel=1e-13)
    assert result.outputs['two'] == pytest.approx(0.05 * 10, rel=1e-12)
    trace, outputs = flat_run(path)
    assert result.trace == trace
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-12)
    # The other order: the second flow first, 0.1 and then 0.35 a day, and the first what is left.
    other = shared(tmp_path / 'other', 0.35, ' order second, first')
    result = timeline.run(timeline.Plan.of(hybrid.compile(other)))
    assert result.outputs['two'] == pytest.approx(0.1 * 5 + 0.35 * 5, rel=1e-13)
    assert result.outputs['one'] == pytest.approx(0.25 * 5 + 0.0 * 5, abs=1e-12)


SEEPING = """tank:  @shape
    "A tank that seeps."
    input inflow: fraction/day = 1 fraction/day in 0 fraction/day to 5 fraction/day  @shape
    input leak: ratio/day = 0.5 ratio/day in 0 ratio/day to 5 ratio/day  @shape
    var held: fraction = {start} size 1  @shape
    var seeped: fraction = 0 size 1  @shape
    flow fill: -> held at inflow
    flow seep: held -> seeped at leak * held
    share held limit {limit} fraction/day

output seeped: fraction = tank.seeped  @shape
    "What seeped"

output held: fraction = tank.held  @shape
    "What the tank holds"
    level
"""


def test_a_flow_that_reaches_the_limit_of_its_group_is_held_at_the_limit_from_that_time(tmp_path, tier):
    """The tank fills at 1 a day and seeps at half of what it holds a day, from 1: it holds
    `2 - e^(-t/2)`. The seepage reaches its limit of 0.8 a day when the tank holds 1.6, at
    `2 ln 2.5` days. From then the tank gains 0.2 a day. In the fast tier the block is linear, so the
    engine takes its closed form to that time, which it puts on the timeline, and the solver from
    there."""
    path = package(tmp_path, SEEPING.replace('{start}', '1').replace('{limit}', '0.8'))
    plan = timeline.Plan.of(hybrid.compile(path))
    assert [block.linear for block in plan.blocks] == [tier == 'fast']
    result = timeline.run(plan)
    reached = 2 * math.log(2.5)
    held = 1.6 + 0.2 * (10 - reached)
    assert result.outputs['held'] == pytest.approx(held, rel=1e-8)
    # What came in is in the tank or seeped.
    assert result.outputs['seeped'] == pytest.approx(1 + 1.0 * 10 - held, rel=1e-8)
    if tier == 'fast':
        assert result.counts['block restarts'] == 1 and result.counts['solver steps'] > 0
    trace, outputs = flat_run(path)
    assert trace == [] and result.trace == []
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-7)


def test_a_flow_above_the_limit_of_its_group_from_the_start_comes_below_it_later(tmp_path):
    """With no inflow, a tank of 5 that seeps at 0.2 of what it holds a day asks 1 a day, above the
    limit of 0.4: it loses 0.4 a day until it holds 2, at 7.5 days, and then seeps freely:
    `2 e^(-0.2 (t - 7.5))`."""
    path = package(tmp_path, SEEPING.replace('{start}', '5').replace('{limit}', '0.4'))
    plan = timeline.Plan.of(hybrid.compile(path))
    values = {'tank.inflow': 0.0, 'tank.leak': 0.2}
    result = timeline.run(plan, values)
    held = 2 * math.exp(-0.2 * 2.5)
    assert result.outputs['held'] == pytest.approx(held, rel=1e-7)
    assert result.outputs['seeped'] == pytest.approx(5 - held, rel=1e-7)
    trace, outputs = flat_run(path, values)
    assert trace == [] and result.trace == []
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-7)


# ---- a quantity that rests on its lower bound ---------------------------------------------------------------

DRAINED = """Tank:  @shape
    "A tank that a flow drains."
    input inflow: fraction/day = 0 fraction/day in 0 fraction/day to 5 fraction/day  @shape
    input outflow: fraction/day = 1 fraction/day in 0 fraction/day to 5 fraction/day  @shape
    let start: fraction = 5  @shape
    var held: fraction = start size 1  @shape
    var out: fraction = 0 size 1  @shape
    var raised = false  @shape
    flow fill: -> held at 3 * inflow if raised else inflow
    flow drain: held -> out at outflow
    event empty once when held <= 0:  @shape
        "The tank is empty."
    event rise once when t >= 9 days:  @shape
        "Three times as much comes in."
        raised = true

tanks: Tank from "tanks.csv"

output out: fraction = sum(Tank.out)  @shape
    "What the flows moved"

output held: fraction = sum(Tank.held)  @shape
    "What the tanks hold"
    level
"""


def test_a_flow_out_of_an_empty_tank_gets_what_comes_in_and_the_tank_fills_again_when_more_comes_in(tmp_path):
    """A tank of s that gets 0.4 a day and gives 1 a day is empty at s / 0.6 days. From then its flow
    moves the 0.4 that comes in. At 9 days the inflow is 1.2: the flow has its 1 again, and the tank
    gains 0.2 a day. A tank of 30 is never empty. Each tank comes to rest at its own time, and the
    event of an empty tank fires then."""
    starts = [1.5, 4.5, 30.0, 3.0]
    a, b = 0.4, 1.0
    path = package(tmp_path, DRAINED, tanks=('start: fraction @shape', starts))
    plan = timeline.Plan.of(hybrid.compile(path))
    values = {'tanks_1.inflow': a, 'tanks_1.outflow': b}
    result = timeline.run(plan, values)
    out, held, empties = [], [], []
    for row, start in enumerate(starts, 1):
        empty = start / (b - a)
        if empty < 9:
            out.append(b * empty + a * (9 - empty) + b * 1)
            held.append((3 * a - b) * 1)
            empties.append((empty * DAY, f'tanks_{row}.empty', 'done'))
        else:
            out.append(b * 10)
            held.append(start + a * 9 + 3 * a * 1 - b * 10)
    assert list(result.final('tanks_1.out')) == pytest.approx(out, rel=1e-12)
    assert list(result.final('tanks_1.held')) == pytest.approx(held, rel=1e-9)
    expected = sorted(empties) + [(9 * DAY, f'tanks_{row}.rise', 'done') for row in range(1, 5)]
    assert same_trace(result.trace, expected, 1e-9)
    assert list(result.final('tanks_1.held__rests')) == [False] * 4
    flat = {f'tanks.{row}.{name[8:]}': value for row in range(1, 5) for name, value in values.items()}
    trace, outputs = flat_run(path, flat)
    assert same_trace(result.trace, trace)
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-9)
    assert timeline.check(plan, values, time_tolerance=1e-6) == []


SPLIT = """tank:  @shape
    "A tank that two flows drain."
    var held: fraction = 2 size 1  @shape
    var one: fraction = 0 size 1  @shape
    var two: fraction = 0 size 1  @shape
    flow fill: -> held at 0.2 fraction/day
    flow first: held -> one at 0.3 fraction/day
    flow second: held -> two at 0.5 fraction/day
    share held limit 100 fraction/day{order}

output one: fraction = tank.one  @shape
    "What the first flow moved"

output two: fraction = tank.two  @shape
    "What the second flow moved"
"""


@pytest.mark.parametrize('order', ['', ' order first, second', ' order second, first'])
def test_the_flows_out_of_an_empty_tank_share_what_comes_in_as_their_group_says(tmp_path, order):
    """The tank of 2 gets 0.2 a day and its flows ask 0.3 and 0.5: it is empty at 2 / 0.6 days. Then
    the flows share the 0.2: in proportion to what they ask (0.075 and 0.125), or in the order of the
    group (the first in the order has its request up to 0.2, the other what is left)."""
    path = package(tmp_path, SPLIT.replace('{order}', order))
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    empty = 2 / 0.6
    if not order:
        shares = (0.2 * 0.3 / 0.8, 0.2 * 0.5 / 0.8)
    elif order.endswith('first, second'):
        shares = (0.2, 0.0)
    else:
        shares = (0.0, 0.2)
    assert result.outputs['one'] == pytest.approx(0.3 * empty + shares[0] * (10 - empty), rel=1e-12)
    assert result.outputs['two'] == pytest.approx(0.5 * empty + shares[1] * (10 - empty), rel=1e-12)
    assert list(result.final('tank.held')) == [0.0]
    trace, outputs = flat_run(path)
    assert trace == [] and result.trace == []
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-9)


CHAIN = """line:  @shape
    "Two tanks, one after the other."
    var first: fraction = 2 size 1  @shape
    var second: fraction = 2 size 1  @shape
    var out: fraction = 0 size 1  @shape
    flow fill: -> first at 0.3 fraction/day
    flow hand: first -> second at 1 fraction/day
    flow leave: second -> out at 1.5 fraction/day

output out: fraction = line.out  @shape
    "What left the second tank"
"""


def test_an_empty_tank_limits_the_tank_after_it(tmp_path):
    """The first tank (2, with 0.3 a day in and 1 a day out) is empty at 2 / 0.7 days; it then passes
    on 0.3 a day. The second tank loses 0.5 a day until then and 1.2 a day after, and is empty in its
    turn; from then 0.3 a day goes out. What went out is what was in the tanks and what came in."""
    path = package(tmp_path, CHAIN)
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    first_empty = 2 / 0.7
    second_empty = first_empty + (2 - 0.5 * first_empty) / 1.2
    out = 1.5 * second_empty + 0.3 * (10 - second_empty)
    assert result.outputs['out'] == pytest.approx(out, rel=1e-12)
    assert out == pytest.approx(2 + 2 + 0.3 * 10, rel=1e-12)
    assert list(result.final('line.first')) == [0.0] and list(result.final('line.second')) == [0.0]
    _, outputs = flat_run(path)
    assert result.outputs['out'] == pytest.approx(outputs['out'], rel=1e-9)


# ---- flows that move by one fraction ----------------------------------------------------------------------

TOGETHER = """plant:  @shape
    "A plant that takes two materials together."
    var a: fraction = 2 size 1  @shape
    var c: fraction = 10 size 1  @shape
    var b: fraction = 0 size 1  @shape
    var d: fraction = 0 size 1  @shape
    flow feed: -> a at {inflow} fraction/day
    flow make at 1 fraction/day:  @shape
        a -> b
        c -> d at 2 fraction/day

output b: fraction = plant.b  @shape
    "What the first pair moved"

output d: fraction = plant.d  @shape
    "What the second pair moved"
"""


@pytest.mark.parametrize('inflow', [0.0, 0.25])
def test_flows_that_move_by_one_fraction_are_cut_together_when_one_source_is_empty(tmp_path, inflow):
    """The two pairs move 1 and 2 a day. The first source (2, with `inflow` a day in) is empty at
    `2 / (1 - inflow)` days; from then the first pair moves what comes in, the fraction `inflow` of
    its request, and the second pair that fraction of its 2 a day, though its source has material."""
    path = package(tmp_path, TOGETHER.replace('{inflow}', str(inflow)))
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    empty = 2 / (1 - inflow)
    assert result.outputs['b'] == pytest.approx(1 * empty + inflow * (10 - empty), rel=1e-12)
    assert result.outputs['d'] == pytest.approx(2 * empty + 2 * inflow * (10 - empty), rel=1e-12)
    assert list(result.final('plant.c')) == pytest.approx([10 - result.outputs['d']], rel=1e-12)
    _, outputs = flat_run(path)
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-9)


def test_the_pairs_of_one_flow_of_each_row_of_a_table_move_together(tmp_path):
    """The cells with a storm of two pairs: each pair moves the inflow, into the water and into its
    twin, so the twin of a cell has what arrived in it."""
    levels = [0.05, 0.2, 0.11]
    path = package(tmp_path, PAIRED, cells=('level: fraction @shape', levels))
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert list(result.final('cells_1.twin')) == pytest.approx(
        list(result.final('cells_1.arrived')), rel=1e-13
    )
    trace, outputs = flat_run(path)
    assert same_trace(result.trace, trace)
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-8)


# ---- the examples of the repository, and outputs that read outputs ------------------------------------------

EXAMPLES = sorted((pathlib.Path(__file__).resolve().parents[2] / 'examples').glob('*/model.scn'))


@pytest.mark.parametrize('path', EXAMPLES, ids=lambda path: path.parent.name)
def test_an_example_of_the_repository_gives_the_same_events_and_outputs_from_its_two_structures(path):
    """The examples are found in their folder, not named here. Each runs from its hybrid core with no
    part outside the engine, and gives the events and the outputs of its flat structure."""
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    trace, outputs = flat_run(path)
    assert same_trace(result.trace, trace, 1e-6)
    assert set(result.outputs) == set(outputs)
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-8, abs=1e-12)


READS = STEPS.replace(
    'output left: fraction = store.stock  @shape\n    "What the store holds"\n    level\n',
    'output left: fraction = store.stock  @shape\n    "What the store holds"\n    level\n\n'
    'output gone: fraction = 0.8 - left  @shape\n    "What the store lost"\n    level\n    signed\n\n'
    'output unknown: fraction  @shape\n    "What nobody estimates"\n    unestimated "No source gives it."\n',
)


def test_an_output_reads_another_output_and_an_output_that_is_not_estimated_has_no_value(tmp_path):
    assert READS != STEPS
    path = package(tmp_path, READS.replace('{chance}', '0.7'))
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert result.outputs['gone'] == pytest.approx(0.8 - result.outputs['left'], rel=1e-15)
    assert result.outputs['left'] == pytest.approx(0.8 - 0.25)
    # Not estimated is not zero: the output has no value, and the result names it.
    assert 'unknown' not in result.outputs and result.unestimated == ('unknown',)


# ---- flows that move by one fraction and share a limit: the allocation in full ---------------------------

WARD = """ward:  @shape
    "A ward that treats a queue with a supply that another flow also drains."
    var supply: fraction = 3 size 1  @shape
    var queue: fraction = 40 size 1  @shape
    var treated: fraction = 0 size 1  @shape
    var used: fraction = 0 size 1  @shape
    var other: fraction = 0 size 1  @shape
    flow restock: -> supply at {inflow} fraction/day
    flow treat at 1 fraction/day:  @shape
        queue -> treated
        supply -> used at 0.5 fraction/day
    flow drain: supply -> other at 0.4 fraction/day
    share supply limit 100 fraction/day

output treated: fraction = ward.treated  @shape
    "The treated part of the queue"

output other: fraction = ward.other  @shape
    "What the other flow took"
"""


@pytest.mark.parametrize('inflow', [0.0, 0.3])
def test_a_treatment_and_another_flow_share_an_empty_supply_and_the_treatment_slows_as_one(tmp_path, inflow):
    """The treatment moves 1 of the queue and 0.5 of the supply a day, by one fraction; another flow
    takes 0.4 of the supply a day; the two flows out of the supply are one group. The supply (3, with
    `inflow` a day in) is empty at `3 / (0.9 - inflow)` days. From then the two flows share what comes
    in, in proportion to what they ask: each gets `inflow / 0.9` of its request, and the queue is
    treated at that fraction of 1 a day. The plan gives this thing to the allocation in full
    (`engine/allocation.py`)."""
    path = package(tmp_path, WARD.replace('{inflow}', str(inflow)))
    plan = timeline.Plan.of(hybrid.compile(path))
    assert plan.general == {0}
    result = timeline.run(plan)
    empty = 3 / (0.9 - inflow)
    share = inflow / 0.9
    # Each rate is constant between the two times, so each segment has its closed form: no solver.
    assert result.counts['solver steps'] == 0
    assert result.outputs['treated'] == pytest.approx(1 * empty + share * (10 - empty), rel=1e-12)
    assert result.outputs['other'] == pytest.approx(0.4 * empty + 0.4 * share * (10 - empty), rel=1e-12)
    assert list(result.final('ward.supply')) == [0.0]
    assert list(result.final('ward.queue')) == pytest.approx([40 - result.outputs['treated']], rel=1e-12)
    trace, outputs = flat_run(path)
    assert trace == [] and result.trace == []
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-9)


def test_cells_whose_flows_move_by_one_fraction_and_share_a_limit_run_with_the_allocation_in_full(tmp_path):
    """Each cell has a storm of two pairs, of which one takes from its water and so is of the group of
    the flows out of the water; its seepage reads the water. The engine makes one block of the
    quantities of a cell, whose rates the allocation in full gives at each state. The comparison is
    with the flat structure, where the cells are one problem: the events, and the outputs within the
    tolerances of the solver."""
    assert SHARED_PAIR != PAIRED
    levels = [0.05, 0.2, 0.11]
    path = package(tmp_path, SHARED_PAIR, cells=('level: fraction @shape', levels))
    plan = timeline.Plan.of(hybrid.compile(path))
    assert [(block.net, block.whole) for block in plan.blocks] == [(True, False)]
    result = timeline.run(plan)
    trace, outputs = flat_run(path)
    assert same_trace(result.trace, trace, 1e-6)
    for name, value in outputs.items():
        assert result.outputs[name] == pytest.approx(value, rel=1e-7)
    # What came into a cell is in it, in its twin, spilled or seeped.
    held = sum(result.final(f'cells_1.{name}') for name in ('water', 'twin', 'spilled', 'seeped'))
    arrived = result.final('cells_1.arrived')
    assert list(held) == pytest.approx(list(0.6 + arrived), rel=1e-8)


# ---- the tolerances and the longest step ---------------------------------------------------------------

YARD = """yard:  @shape
    "Stores that flows connect, one alone, and one with a size that the file writes."
    input tau: h = 16 h in 1 h to 100 h  @shape
    var big: fraction = 50  @shape
    var small: fraction = 2  @shape
    var drawn: fraction = 0  @shape
    var alone: fraction = 3  @shape
    var sized: fraction = 7 size 4  @shape
    flow hand: big -> small at 0.5 fraction/day
    flow draw: small -> drawn at 2 fraction/day
    share small limit 30 fraction/day

Cell:  @shape
    "One cell of a row, which fills a twin."
    let first: fraction = 0  @shape
    var held: fraction = first  @shape
    var twin: fraction = 2  @shape
    flow fill: held -> twin at 0.1 fraction/day

cells: Cell from "cells.csv"

output drawn: fraction = yard.drawn  @shape
    "What was drawn"
"""


def test_the_size_of_a_quantity_is_the_largest_of_what_bounds_it(tmp_path):
    """The size of a quantity sets its tolerance (`atol_factor` times it). It is the size that the
    file writes, else the largest of: one of its unit, its start value, the largest start value of
    the quantities that flows connect it to, and the limit of a group that rations a flow of it,
    over the horizon. Here, in fractions: `big`, `small` and `drawn` are connected, with the largest
    start 50; the group of the flow out of `small` has the limit 30 a day, 300 in the 10 days, which
    bounds `small` and `drawn`; `alone` starts at 3; `sized` has the size 4. Each cell and its twin
    are connected: the larger of the start of the row and 2. The system of the flat structure has
    the same sizes."""
    starts = [50.0, 0.5, 9.0]
    path = package(tmp_path, YARD, cells=('first: fraction @shape', starts))
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    factor = NumericalSettings().atol_factor
    expected = {'yard.big': 50, 'yard.small': 300, 'yard.drawn': 300, 'yard.alone': 3, 'yard.sized': 4}
    for name, size in expected.items():
        assert list(result.run.atol[name]) == pytest.approx([factor * size], rel=1e-12)
    for name in ('cells_1.held', 'cells_1.twin'):
        assert list(result.run.atol[name]) == pytest.approx([factor * max(start, 2) for start in starts])
    model = build_model(path)
    system = System(model.resolve(next(iter(model.runs))), thaw(model.library), NumericalSettings())
    flat = dict(zip(system.state_ids, system.atol))
    for name in expected:
        assert result.run.atol[name][0] == flat[name]
    for k in (1, 2, 3):
        for member in ('held', 'twin'):
            assert result.run.atol[f'cells_1.{member}'][k - 1] == flat[f'cells_{k}.{member}']


def test_a_limit_that_reads_a_formula_bounds_no_size(tmp_path):
    """The same yard, with the limit of its group as a formula: 480 a day times 1 h over the input
    `tau` of 16 h, the same 30 a day. A size reads a limit that is a number or reads inputs, and no
    limit that reads a formula. So `small` and `drawn` have the size of the quantities that the
    flows connect them to, the start of `big`, and no longer the 300 of the limit. The system of
    the flat structure has the same sizes."""
    yard = YARD.replace(
        '    share small limit 30 fraction/day\n',
        '    let most: fraction/day = 480 fraction/day * 1 h / tau  @shape\n    share small limit most\n',
    )
    assert yard != YARD
    path = package(tmp_path, yard, cells=('first: fraction @shape', [50.0, 0.5, 9.0]))
    plan = timeline.Plan.of(hybrid.compile(path))
    assert plan.kind['yard.most'] == 'formula'
    result = timeline.run(plan)
    factor = NumericalSettings().atol_factor
    model = build_model(path)
    system = System(model.resolve(next(iter(model.runs))), thaw(model.library), NumericalSettings())
    flat = dict(zip(system.state_ids, system.atol))
    for name in ('yard.big', 'yard.small', 'yard.drawn'):
        assert list(result.run.atol[name]) == pytest.approx([factor * 50], rel=1e-12)
        assert result.run.atol[name][0] == flat[name]
    # The limit is the 30 a day of the yard of the test before: what is drawn is the same.
    number = package(tmp_path / 'number', YARD, cells=('first: fraction @shape', [50.0, 0.5, 9.0]))
    drawn = timeline.run(timeline.Plan.of(hybrid.compile(number))).outputs['drawn']
    assert result.outputs['drawn'] == pytest.approx(drawn, rel=1e-6)


@pytest.mark.parametrize(
    'tau, scale, longest',
    # The resolution of 6 h, times the setting; an eighth of the timescale, when that is shorter.
    [(16.0, 1.0, 2.0), (80.0, 1.0, 6.0), (80.0, 0.5, 3.0), (16.0, 0.25, 1.5)],
)
def test_the_longest_step_is_the_resolution_or_an_eighth_of_a_timescale(tmp_path, tau, scale, longest):
    """A numerical segment takes steps of at most the resolution of the scenario, which the setting
    `max_step` scales, and of at most an eighth of each timescale that it declares
    (docs/engine.md, "The step")."""
    lines = '    horizon 10 days\n    resolution 6 h\n    timescales yard.tau\n'
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / 'model.scn'
    path.write_text(HEAD.replace('    horizon 10 days\n', lines) + YARD + RECORD, encoding='utf-8')
    (tmp_path / 'cells.csv').write_text('first: fraction @shape\n1.0\n', encoding='utf-8')
    plan = timeline.Plan.of(hybrid.compile(path))
    run = timeline.Run(plan, {'yard.tau': tau}, settings={'max_step': scale})
    assert run.max_step == longest


# ---- a condition on stocks at zero ---------------------------------------------------------------------

EMPTY = """tank:  @shape
    "A tank and a store that drain into one pool, which fills the store again."
    var water: fraction = 3 size 1  @shape
    var store: fraction = 1 size 1  @shape
    var pool: fraction = 0 size 1  @shape
    var lows: fraction = 0 size 1  @shape
    var mode: "run" | "back" = "run"
    var wet: "wet" | "dry" = "wet"
    var stocked: "stocked" | "spent" = "stocked"
    flow drain: water -> pool at 1 fraction/day while mode is "run"
    flow use: store -> pool at 0.5 fraction/day while mode is "run"
    flow back: pool -> store at 1 fraction/day while mode is "back"
    event water_out once when water <= 0 fraction:  @shape
        "The water is out."
        wet = "dry"
    event store_out once when store <= 0 fraction:  @shape
        "The store is out."
        stocked = "spent"
    event low when water <= 0 fraction or store <= 0 fraction:  @shape
        "One of the two is empty."
        lows = lows + 1 fraction
        mode = "back"
    event resume after 1 days when mode is "back":  @shape
        "The two drain again."
        mode = "run"

output lows: fraction = tank.lows  @shape
    "How many times one of the two was empty"

output pool: fraction = tank.pool  @shape
    "What the pool holds"
    level
"""


def test_a_condition_on_stocks_at_zero_is_read_where_a_segment_of_their_block_ends(tmp_path):
    """The store (1, less 0.5 a day) is empty at 2 days: `low` triggers, and for one day the pool
    fills the store again, so the condition is false. The tank (3, less 1 a day in 3 days of
    draining) is empty at 4 days: `low` triggers again. From then the tank stays empty, so the
    condition stays true and `low` triggers no more, also when the store is empty again at 8 days.
    The condition is no crossing of one quantity: the engine reads it where a segment of the block
    ends, which is where a stock reaches zero. At the horizon all 4 are in the pool."""
    path = package(tmp_path, EMPTY)
    plan = timeline.Plan.of(hybrid.compile(path))
    assert plan.general == {0}
    assert {rule.name: rule.kind for rule in plan.rules}['tank.low'] == 'face'
    result = timeline.run(plan)
    lows = [at / DAY for at, rule, outcome in result.trace if rule == 'tank.low']
    assert lows == pytest.approx([2.0, 4.0], abs=1e-9)
    fired = [at / DAY for at, rule, outcome in result.trace if rule == 'tank.resume' and outcome is not None]
    assert fired == pytest.approx([3.0, 5.0], abs=1e-9)
    assert result.outputs == {'lows': 2.0, 'pool': pytest.approx(4.0, rel=1e-12)}
    assert list(result.final('tank.store')) == [0.0] and list(result.final('tank.water')) == [0.0]
    trace, outputs = flat_run(path)
    assert same_trace(result.trace, trace, 1e-9)
    assert result.outputs == pytest.approx(outputs, rel=1e-12)
    assert timeline.check(plan) == []


# ---- what a step writes: a value at a bound, and a move ---------------------------------------------------

STEPS_AT_BOUNDS = """yard:  @shape
    "Stores that the steps of events set and move between."
    input taken: fraction = 1 fraction in 0 fraction to 5 fraction  @shape
    var left: fraction = 9 size 1  @shape
    var spare: fraction = 0 size 1  @shape
    var full: fraction = 1 size 1  @shape
    var got: fraction = 0 size 1  @shape
    var both: fraction = 0 size 1  @shape
    var other: fraction = 0 size 1  @shape
    event write once when t >= 1 days:  @shape
        "A value that the arithmetic of doubles puts just below zero, in a store that a move takes from."
        left = 0.3 fraction - 0.1 fraction - 0.2 fraction
        move 0 fraction from left to spare
    event take once when t >= 2 days:  @shape
        "A move that leaves a part of the store that the solver cannot resolve."
        move taken from full to got
    event set_and_move once when t >= 3 days:  @shape
        "A value that the step sets, and a move out of it in the same step."
        both = 5 fraction
        move 2 fraction from both to other

output got: fraction = yard.got  @shape
    "What was taken"
    level
"""


def test_a_step_puts_a_value_that_misses_a_bound_by_roundoff_on_the_bound(tmp_path):
    """In doubles, `0.3 - 0.1 - 0.2` is just below zero (about -2.8e-17). A step that writes it to
    a stock leaves the stock on its bound, 0 itself, so the next segment starts inside the domain. A
    move of all of a store but 1e-12 of it, less than the tolerance of the store (1e-10), moves
    everything and leaves 0 itself. A step that sets a value and moves an amount out of it moves the
    amount out of the value that it sets."""
    assert 0.3 - 0.1 - 0.2 < 0
    path = package(tmp_path, STEPS_AT_BOUNDS)
    plan = timeline.Plan.of(hybrid.compile(path))
    result = timeline.run(plan, {'yard.taken': 1 - 1e-12})
    assert list(result.final('yard.left')) == [0.0]
    assert list(result.final('yard.full')) == [0.0] and list(result.final('yard.got')) == [1.0]
    assert list(result.final('yard.both')) == [3.0] and list(result.final('yard.other')) == [2.0]
    names = ('yard.left', 'yard.full', 'yard.got', 'yard.both', 'yard.other')
    _, _, flat = flat_run(path, {'yard.taken': 1 - 1e-12}, names=names)
    assert {name: result.final(name)[0] for name in names} == flat
    # A move of more than the store holds does not fit: the run stops.
    with pytest.raises(SimulationError, match='does not fit'):
        timeline.run(plan, {'yard.taken': 1.5})
    with pytest.raises(SimulationError, match='does not fit'):
        flat_run(path, {'yard.taken': 1.5})


# ---- a crossing that comes again, and the whole record of a run ---------------------------------------------

AGAIN = """tank:  @shape
    "A tank that fills, and that an event empties by 2 each time it holds 2."
    var level: fraction = 0 fraction in 0 fraction to 10 fraction size 1 fraction  @shape
    var total: fraction = 0 size 1  @shape
    var mode: "low" | "high" = "low"
    flow fill: -> level at 1 fraction/h
    event drain when mode is "low" and level >= 2 fraction:  @shape
        "The tank is emptied by 2."
        mode = "high"
        level = level - 2 fraction
        total = total + 2 fraction
    event reset when mode is "high":  @shape
        "The tank can be emptied again."
        mode = "low"

output total: fraction = tank.total  @shape
    "What the event took"
"""


def test_a_crossing_that_was_reached_holds_no_more_after_its_step_wrote_its_quantity(tmp_path):
    """The level rises at 1 an hour, and `drain` takes 2 each time it reaches 2: at 2, 4, 6 and 8 h
    and so on. In the moment of a crossing, `reset` opens the gate of `drain` again; the level is then
    0, so `drain` does not trigger a second time in that moment (the crossing was reached, and the
    step of the rule wrote its quantity)."""
    path = package(tmp_path, AGAIN)
    plan = timeline.Plan.of(hybrid.compile(path))
    result = timeline.run(plan)
    drains = [at for at, rule, _ in result.trace if rule == 'tank.drain']
    assert drains == pytest.approx([2.0 * k for k in range(1, 121)], abs=1e-9)
    assert result.outputs['total'] == 240.0 and list(result.final('tank.level')) == [0.0]
    trace, outputs = flat_run(path)
    assert same_trace(result.trace, trace, 1e-9) and result.outputs == outputs


def test_the_whole_record_of_a_run_is_the_same_from_the_hybrid_core_and_from_the_flat_structure(tmp_path):
    """`Run(…, keep=True)` keeps the state and the store at the start of each moment and after each
    step, and the segments; `Result.trajectory` gives them as a `Trajectory`.
    The total is a value that only a step writes and that no rate reads: between two moments it has
    the value of the last step (240 h: 2 for each 2 h that have passed)."""
    path = package(tmp_path, AGAIN)
    core = hybrid.compile(path)
    plan = timeline.Plan.of(core, scalars='general')
    new = timeline.Run(plan, keep=True).run().trajectory()
    model = build_model(path)
    old = simulate(model.resolve(next(iter(model.runs))), thaw(model.library))
    assert new.trace == old.trace and new.layers == old.layers
    assert len(new._steps) == len(old._steps) == len(old.trace)
    for (at, state, store), (at_old, state_old, store_old) in zip(new._steps, old._steps):
        assert at == at_old and list(state) == list(state_old) and store == store_old
    assert [(s.start, s.end) for s in new._segments] == [(s.start, s.end) for s in old._segments]
    for hours in (0.0, 1.0, 2.0, 2.5, 7.0, 100.5, 240.0):
        assert new.env_at(hours) == old.env_at(hours)
        assert new.env_at(hours)['tank.total'] == 2.0 * (hours // 2)
    assert new.env_at(2.0, side='left')['tank.total'] == 0.0
    with pytest.raises(ValueError, match='keep'):
        timeline.run(plan).trajectory()
    # The record has the segments of the general tier: the fast tier says that it keeps none.
    with pytest.raises(timeline.Outside, match='fast tier'):
        timeline.Run(timeline.Plan.of(core, scalars='fast'), keep=True)


# ---- a check of the state inside a segment of a solver -----------------------------------------------------

VAT = """vat:  @shape
    "A vat whose first part turns into a second part, which drains."
    var first: fraction = 1 size 1  @shape
    var second: fraction = 0 fraction in 0 fraction to 1 fraction size 1 fraction  @shape
    var gone: fraction = 0 size 1  @shape
    flow turn: first -> second at 2 ratio/day * first * first / 1 fraction
    flow drain: second -> gone at 0.5 ratio/day * second
    assert second <= 1 fraction  @shape
        "The second part stays under its cap."

output gone: fraction = vat.gone  @shape
    "What drained"
"""


def test_a_check_of_the_state_holds_at_each_accepted_point_of_a_solver(tmp_path):
    """The first part is `1 / (1 + 2 t)` (t in days), so the second part gets `2 / (1 + 2 t)^2` a day
    and loses half of itself a day: it rises, has its top between 0.4 and 0.5 near one day, and falls
    again. No event comes in the 10 days, so the run is one segment of a solver.

    The compiler admits a check on a value that moves only with a proof, so that no model has a
    check that fails inside a segment. The check is changed here after the compilation, to a cap of
    0.3: it is passed inside the segment, long before the end, where the second part is under the
    cap again. The run stops at the first accepted point of the solver after the cap is passed, which
    is within one step (1 h) of the time at which it is passed."""

    def second(days):
        days = mpmath.mpf(days)
        return mpmath.quad(lambda u: 2 / (1 + 2 * u) ** 2 * mpmath.exp(-(days - u) / 2), [0, days])

    passed = float(mpmath.findroot(lambda days: second(days) - 0.3, 0.2)) * DAY
    assert second(10) < 0.3 < second(1)
    path = package(tmp_path, VAT)
    model = build_model(path)
    library = thaw(model.library)
    resolved = model.resolve(next(iter(model.runs)))
    # Under the cap of the file, above the top, the run goes to the horizon.
    whole = timeline.trajectory(resolved, library)
    assert whole.env_at(HORIZON)['vat.second'] == pytest.approx(float(second(10)), rel=1e-7)
    (name,) = resolved.state_checks
    capped = resolved.with_part(
        'state_checks', name, resolved.state_checks[name].changed(expr=expr.read('vat.second <= 0.3'))
    )
    with pytest.raises(SimulationError) as stopped:
        timeline.trajectory(capped, library)
    (found,) = stopped.value.diagnostics
    assert found['code'] == 'check_failed' and passed < found['t'] <= passed + 1.0
    with pytest.raises(SimulationError) as flat:
        simulate(capped, library)
    assert flat.value.diagnostics[0]['t'] == found['t']


SUMMED = VAT.replace(
    '    assert second <= 1 fraction  @shape\n',
    '    let twice: fraction = 2 * second  @shape\n'
    '    assert first + second + gone is 1 within 0.001  @shape\n'
    '        "The parts of the vat add up to the whole."\n'
    '    assert twice <= 2 fraction  @shape\n',
)


@pytest.mark.parametrize('part', ['state_checks', 'partitions'])
def test_a_check_through_a_formula_and_a_sum_hold_at_each_accepted_point_of_a_solver(tmp_path, part):
    """The same vat, with a check on a formula that no rate reads (twice the second part) and a sum
    of the three parts. As in the test before, the condition is changed after the compilation so
    that it fails inside the one segment of the run, while the second part is above 0.3, and holds
    again at the end: the check as `twice <= 0.6`, and the total of the sum as 2 while the second
    part is above 0.3. The run stops at the first accepted point of the solver after the second
    part passes 0.3, which is within one step (1 h) of that time."""

    def second(days):
        days = mpmath.mpf(days)
        return mpmath.quad(lambda u: 2 / (1 + 2 * u) ** 2 * mpmath.exp(-(days - u) / 2), [0, days])

    passed = float(mpmath.findroot(lambda days: second(days) - 0.3, 0.2)) * DAY
    assert SUMMED != VAT and second(10) < 0.3 < second(1)
    path = package(tmp_path, SUMMED)
    model = build_model(path)
    library = thaw(model.library)
    resolved = model.resolve(next(iter(model.runs)))
    whole = timeline.trajectory(resolved, library)
    assert whole.env_at(HORIZON)['vat.twice'] == pytest.approx(2 * float(second(10)), rel=1e-7)
    (name,) = getattr(resolved, part)
    item = getattr(resolved, part)[name]
    if part == 'state_checks':
        changed, code = item.changed(expr=expr.read('vat.twice <= 0.6')), 'check_failed'
    else:
        changed, code = item.changed(total=expr.read('1 if vat.second <= 0.3 else 2')), 'partition_failed'
    with pytest.raises(SimulationError) as stopped:
        timeline.trajectory(resolved.with_part(part, name, changed), library)
    (found,) = stopped.value.diagnostics
    assert found['code'] == code and passed < found['t'] <= passed + 1.0


REFILLED = VAT.replace(
    '    assert second',
    """    event refill once when t >= 12 h:  @shape
        "The first part is made full again."
        first = 1 fraction
    assert second""",
)


def test_the_record_of_a_segment_that_a_moment_cuts_keeps_the_state_that_it_started_from(tmp_path):
    """The first part is `1 / (1 + 2 t)` (t in days) to the event at half a day, which makes it 1
    again: after the event it is `1 / (1 + 2 (t - 1/2))`. The second part is the integral of what it
    gets and loses, which starts again at the event from the value that it has there.

    The solver makes the first segment as far as the horizon, and the event cuts it. The record of
    the cut segment reads the state at its start (the first dense step of a solver is from that
    state), so the state of the component after the event must be another array: a time just after
    the start of the run has the values of the start, not those after the event."""

    def second(days, start=0.0, level=0.0):
        days = mpmath.mpf(days)
        gain = mpmath.quad(
            lambda u: 2 / (1 + 2 * (u - start)) ** 2 * mpmath.exp(-(days - u) / 2), [start, days]
        )
        return level * mpmath.exp(-(days - start) / 2) + gain

    path = package(tmp_path, REFILLED)
    model = build_model(path)
    record = timeline.trajectory(model.resolve(next(iter(model.runs))), thaw(model.library))
    assert [entry['rule'] for entry in record.trace] == ['vat.refill']
    at_event = second(0.5)
    for hours in (1e-6, 1e-3, 0.5, 6.0, 11.999):
        found, days = record.env_at(hours), hours / DAY
        assert found['vat.first'] == pytest.approx(1 / (1 + 2 * days), rel=1e-7)
        assert found['vat.second'] == pytest.approx(float(second(days)), rel=1e-6, abs=1e-12)
    for hours in (12.0 + 1e-6, 12.001, 13.0, 100.0, HORIZON):
        found, days = record.env_at(hours), hours / DAY
        assert found['vat.first'] == pytest.approx(1 / (1 + 2 * (days - 0.5)), rel=1e-7)
        assert found['vat.second'] == pytest.approx(float(second(days, 0.5, at_event)), rel=1e-6)


# ---- the events of the instances of a template at one moment ----------------------------------------------

HANDS = """pot:  @shape
    "A pot that the hands change."
    var level: fraction = 0 size 1  @shape

Hand:  @shape
    "A hand that changes the pot."
    input weight: ratio = 2 ratio in 0 ratio to 10 ratio  @shape
    var done = false  @shape
    event take once when t >= 1 day:  @shape
        "The hand changes the pot."
        done = true
        pot.level = pot.level * weight + 1 fraction

zulu: Hand
    weight = 2 ratio  @shape

alpha: Hand
    weight = 3 ratio  @shape

output level: fraction = pot.level  @shape
    "The level of the pot"
"""


def test_the_events_of_the_instances_of_a_template_go_in_the_order_of_the_instances_in_the_file(tmp_path):
    """Two instances of a template have the same event at the same time. The language says that
    they go in the order of the instances in the file, and that each reads what the one before it
    wrote: `zulu` is first in the file and `alpha` is first by name. With `zulu` first the level is
    0 * 2 + 1 = 1 and then 1 * 3 + 1 = 4; with `alpha` first it is 1 and then 1 * 2 + 1 = 3."""
    path = package(tmp_path, HANDS)
    model = build_model(path)
    record = timeline.trajectory(model.resolve(next(iter(model.runs))), thaw(model.library))
    assert [entry['rule'] for entry in record.trace] == ['zulu.take', 'alpha.take']
    assert record.env_at(HORIZON)['pot.level'] == 4.0
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)))
    assert [rule for _, rule, _ in result.trace] == ['zulu.take', 'alpha.take']
    assert result.outputs['level'] == 4.0


# ---- a flow that would ask a rate below zero inside a segment ----------------------------------------------

LEVELS = """Cell:  @shape
    "Two parts of a cell, with a flow from the first to the second by their difference."
    input pace: ratio/day = 0.5 ratio/day in 0 ratio/day to 2 ratio/day  @shape
    input inflow: fraction/day = 0.2 fraction/day in 0 fraction/day to 1 fraction/day  @shape
    var a: fraction = 0.6 size 1  @shape
    var b: fraction = 0 size 1  @shape
    flow fill: -> b at inflow
    flow level_out: a -> b at pace * (a - b)

cells: Cell from "cells.csv"

output a_total: fraction = sum(Cell.a)  @shape
    "What the cells hold in their first part"
    level
"""


def test_a_flow_that_would_ask_a_rate_below_zero_inside_a_segment_stops_the_run(tmp_path):
    """The difference d of the two parts follows `d' = -2 k d - inflow`: with k = 0.5 a day and an
    inflow of 0.2 a day from d = 0.6, `d = 0.8 e^(-t) - 0.2` (t in days), which is 0 at ln 4 days.
    From then the flow between the parts would ask a rate below zero. The equation is linear, and
    its start state is fine, so only a look at the states inside the segment finds it: the run
    stops there, and does not go on with a flow that runs backward.

    With no inflow the difference is `0.6 e^(-t)`, which stays above zero: the run goes to the
    horizon, where the first part is `0.3 + 0.3 e^(-10)`."""
    path = package(tmp_path, LEVELS, cells=('pace: ratio/day @shape', [0.5, 0.25]))
    plan = timeline.Plan.of(hybrid.compile(path))
    with pytest.raises(SimulationError) as stopped:
        timeline.run(plan)
    assert 'level_out' in str(stopped.value)
    still = timeline.run(plan, {'cells_1.inflow': 0.0, 'cells_1.pace': [0.5, 0.5]})
    assert list(still.final('cells_1.a')) == pytest.approx([0.3 + 0.3 * math.exp(-10.0)] * 2, rel=1e-7)


# ---- the checks of the inputs, for every row ---------------------------------------------------------------

SHARES = """Cell:  @shape
    "One cell, with its share of a whole."
    let share: fraction = 0.25  @shape
    let most: fraction = 0.5  @shape
    var held: fraction = 0 size 1  @shape
    flow fill: -> held at share * 1 ratio/day
    assert share <= most  @shape
        "The share of a cell is at most the most that a cell can have."

cells: Cell from "cells.csv"

output held: fraction = sum(Cell.held)  @shape
    "What the cells hold"
"""


def test_a_check_of_the_inputs_holds_for_every_row_of_a_table(tmp_path):
    """Each row gives its share, and the check says that it is at most 0.5. The model of the
    representatives has the check for one row of the class. The rows at places 3 and 5 fail it: their
    checks are named by their rows, and the run is refused, as the compiler refuses the flat model
    of the same file."""
    shares = [0.1, 0.5, 0.7, 0.2, 0.5000001, 0.3]
    path = package(tmp_path, SHARES, cells=('share: fraction @shape', shares))
    core = hybrid.compile(path)
    plan = timeline.Plan.of(core)
    found = timeline.input_failures(plan)
    failing = [place for place, share in enumerate(shares, 1) if share > 0.5]
    assert failing == [3, 5]
    assert [item['code'].rsplit('.', 1)[1] for item in found] == [f'cells_{place}' for place in failing]
    assert {item['severity'] for item in found} == {'error'} and all(item['path'] for item in found)
    with pytest.raises(ModelError) as refused:
        timeline.admit(core)
    with pytest.raises(ModelError) as flat:
        build_model(path)
    codes = sorted({item['code'] for item in flat.value.diagnostics})
    # Each failure is plain data that a report can write, with the record of the check as its
    # evidence: the record that the flat model gives for the check of the same row.
    assert json.loads(json.dumps(found)) == found
    evidence = {item['code']: item['evidence'] for item in flat.value.diagnostics}
    assert all(item['evidence'] == evidence[item['code']] for item in found)
    assert sorted(item['code'] for item in refused.value.diagnostics) == codes
    assert sorted(item['code'] for item in found) == codes
    # A run of the table is refused when it starts, with the same checks; a sample of a batch
    # with such inputs has the status of a failure, and the other sample runs.
    with pytest.raises(ModelError) as stopped:
        timeline.run(plan)
    assert sorted(item['code'] for item in stopped.value.diagnostics) == codes
    one, other = timeline.batch(plan, [{}, {'cells_1.share': 0.4}])
    assert (one.status, other.status) == ('failed', 'finished') and all(code in one.error for code in codes)
    assert other.result.outputs['held'] == pytest.approx(len(shares) * 0.4 * 10)
    # An input of the family for all rows is read too: with every share inside, no check fails.
    assert timeline.input_failures(plan, {'cells_1.share': 0.4}) == []
    assert len(timeline.input_failures(plan, {'cells_1.most': 0.05})) == len(shares)
    inside = package(tmp_path / 'inside', SHARES, cells=('share: fraction @shape', [0.1, 0.5, 0.2]))
    timeline.admit(hybrid.compile(inside))
    build_model(inside)


# ---- the values that a run is given, for every row ---------------------------------------------------------

DIVIDED = """Cell:  @shape
    "A cell that fills at a pace over its divisor."
    let divisor: ratio = 2 ratio  @shape
    var held: fraction = 0 size 1  @shape
    flow fill: -> held at 1 fraction/day / divisor

cells: Cell from "cells.csv"

output held: fraction = sum(Cell.held)  @shape
    "What the cells hold"
"""


def test_the_values_that_a_run_is_given_are_proved_for_every_row_before_the_run_starts(tmp_path):
    """Each cell fills at 1 a day over the divisor of its row: in the 10 days it holds
    `10 / divisor`. With the divisors of the table (2, 4 and 5) the cells hold 9.5 together, and a
    run that is given the divisors 1, 2 and 4 holds 17.5.

    A run that is given a zero for one row has a division with no value in that row. The compiler
    proved the table as it is, not these values, so the run makes the proofs over the rows again and
    is refused before it starts. The definition is the compiler on the table that has the zero: it
    refuses it with the same code. A sample of a batch with such values has the status of a
    failure, and the other sample runs."""
    header = 'divisor: ratio @shape'
    plan = timeline.Plan.of(hybrid.compile(package(tmp_path, DIVIDED, cells=(header, [2, 4, 5]))))
    assert timeline.run(plan).outputs['held'] == pytest.approx(10 * (1 / 2 + 1 / 4 + 1 / 5))
    other = {'cells_1.divisor': [1, 2, 4]}
    assert timeline.run(plan, other).outputs['held'] == pytest.approx(10 * (1 + 1 / 2 + 1 / 4))
    zero = {'cells_1.divisor': [2, 0, 5]}
    with pytest.raises(ModelError) as refused:
        timeline.run(plan, zero)
    with pytest.raises(ModelError) as flat:
        build_model(package(tmp_path / 'zero', DIVIDED, cells=(header, [2, 0, 5])))
    codes = [item['code'] for item in flat.value.diagnostics]
    assert [item['code'] for item in refused.value.diagnostics] == codes == ['dynamic_domain']
    one, two = timeline.batch(plan, [zero, other])
    assert (one.status, two.status) == ('failed', 'finished') and 'dynamic_domain' in one.error


# ---- one plan for the runs of one structure --------------------------------------------------------------

FILLS = """tank:  @shape
    "A tank that fills at the pace of its input."
    input pace: fraction/day = 0.1 fraction/day in 0 fraction/day to 1 fraction/day  @shape
    var held: fraction = 0 size 1  @shape
    flow fill: -> held at pace

output held: fraction = tank.held  @shape
    "What the tank holds"
    level
"""


def test_the_runs_of_one_structure_share_one_plan_and_each_has_its_own_inputs(tmp_path, monkeypatch):
    """A plan follows from the structure alone. Three runs of one model with three paces make one
    plan, and each holds its own pace times the 10 days. A structure that was changed after the
    compilation (a start of 2 in the place of 0) is another structure: it has a plan of its own, and
    its run starts at 2."""
    made = []
    flat = timeline.Plan.flat.__func__
    monkeypatch.setattr(
        timeline.Plan, 'flat', classmethod(lambda cls, *args, **kw: made.append(1) or flat(cls, *args, **kw))
    )
    timeline._plans.clear()
    model = build_model(package(tmp_path, FILLS))
    library, run = thaw(model.library), next(iter(model.runs))
    for pace in (0.1, 0.25, 0.4):
        resolved = model.resolve(run, {'tank.pace': pace})
        held = timeline.trajectory(resolved, library).env_at(HORIZON)['tank.held']
        assert held == pytest.approx(pace * 10, rel=1e-12)
    assert len(made) == 1
    resolved = model.resolve(run, {'tank.pace': 0.25})
    other = resolved.with_part(
        'quantities', 'tank.held', resolved.quantities['tank.held'].changed(initial=expr.read('2'))
    )
    assert timeline.trajectory(other, library).env_at(HORIZON)['tank.held'] == pytest.approx(
        2 + 2.5, rel=1e-12
    )
    assert len(made) == 2


def test_the_plan_reads_an_expression_of_a_part_from_a_node_or_a_number_and_not_from_a_text(tmp_path):
    """The parts of a compiled model hold nodes: a text that a caller writes into a part is a
    TypeError, as at the entries of `napkin.expressions`."""
    plan = timeline.Plan.of(
        hybrid.compile(package(tmp_path, GATES, cells=('level: fraction @shape', [0.05])))
    )
    space = plan.spaces[0]
    assert plan.node(expr.read('1 + 1'), space, 'a test') is expr.read('1 + 1')
    assert plan.plain(2.5, space, 'a test') == 2.5
    for read in (plan.node, plan.plain):
        with pytest.raises(TypeError, match='a test: an expression is a node or a number'):
            read('1 + 1', space, 'a test')
