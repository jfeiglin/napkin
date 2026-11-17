"""The facts that are proved for every row of a table reach the plan of the engine
(`hybrid.row_facts`, `timeline.Plan.of`), and the run of a family has its crossing at the time of
the closed form.

The model is a cell whose level rises at a pace that grows with the time: the level at t hours is
`5 + pace / 24 * (t + t^2 / 200)` for a pace in a day, so it reaches 5.2 at
`t = -100 + sqrt(10000 + 960 / pace)`.
"""

import math

import pytest

from napkin.engine import timeline
from napkin.model import hybrid

HEAD = """scenario "A synthetic model"
    summary "A model of a test, with no source."
    horizon 10 days
    scope "Nothing: the model is synthetic."

"""
RECORD = '\nrecord shape: assumption "A synthetic model, with no source."\n'
MOVING = """Cell:  @shape
    "A cell whose level rises at a pace that grows with the time."
    let pace: fraction/day = 0.3 fraction/day  @shape
    var level: fraction = 5 fraction in 0 fraction to 10 fraction size 1 fraction  @shape
    var seen: fraction = 0 fraction size 1 fraction  @shape
    flow gain: -> level at pace * (1 + t / 100 h)
    event high once when level >= 5.2 fraction:  @shape
        "The level is high."
        seen = 1 fraction

cells: Cell from "cells.csv"

output seen: fraction = sum(Cell.seen)  @shape
    "The cells whose level was high"
    level
"""
PACES = (0.3, 0.4, 0.25)


def test_the_plan_of_a_table_has_the_crossing_that_is_proved_for_every_row(tmp_path):
    """The level only rises, whatever the pace of a row is, so the crossing is proved over the
    rows, and the plan has it as a crossing of a quantity that moves one way. Each row has its
    event at the time of the closed form (the tolerance of the level is 1e-10, which the level
    crosses in far less than the 1e-6 h of this check), and all three cells see their level high."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / 'model.scn').write_text(HEAD + MOVING + RECORD, encoding='utf-8')
    rows = '\n'.join(repr(pace) for pace in PACES)
    (tmp_path / 'cells.csv').write_text('pace: fraction/day @shape\n' + rows + '\n', encoding='utf-8')
    plan = timeline.Plan.of(hybrid.compile(tmp_path / 'model.scn'))
    assert list(plan.resolved.proven_monotone_crossings) == ['cells_1.high']
    result = timeline.run(plan)
    times = sorted(time for time, rule, _ in result.trace)
    exact = sorted(-100 + math.sqrt(10000 + 960 / pace) for pace in PACES)
    assert times == pytest.approx(exact, abs=1e-6)
    assert result.outputs['seen'] == 3.0
