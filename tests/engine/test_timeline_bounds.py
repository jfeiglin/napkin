"""A bound that the file writes as an expression, in a model with a table (`timeline/plan.py`,
`Plan._bound`): the plan has the number that the values of its inputs give.

The model is a cell that fills at a constant pace over a divisor that a table gives, up to a cap
that is an input. Its level at the horizon is a product, written beside each test.
"""

import numpy as np
import pytest

from napkin.engine import timeline
from napkin.model import hybrid

HEAD = """scenario "A synthetic model"
    summary "A model of a test, with no source."
    horizon 10 days
    scope "Nothing: the model is synthetic."

"""
RECORD = '\nrecord shape: assumption "A synthetic model, with no source."\n'
CAPPED = """Cell:  @shape
    "A cell that fills up to its cap."
    input cap: fraction = 1 fraction in 0.5 fraction to 2 fraction  @shape
    input pace: fraction/day = 0.01 fraction/day in 0 fraction/day to 1 fraction/day  @shape
    let divisor: fraction = 2  @shape
    input limit: days = 3 days in 1 days to 9 days  @shape
    var held: fraction = 0 fraction in 0 fraction to cap size 1 fraction  @shape
    var waited: days = 1 days in 0.5 days to 2 * limit size 1 days  @shape
    flow fill: -> held at pace / divisor

cells: Cell from "cells.csv"

output held: fraction = sum(Cell.held)  @shape
    "What the cells hold"

output waited: days = sum(Cell.waited)  @shape
    "The days of all cells"
    level
"""
DIVISORS = (2.0, 4.0, 5.0)


def core_of(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / 'model.scn').write_text(HEAD + CAPPED + RECORD, encoding='utf-8')
    rows = '\n'.join(repr(divisor) for divisor in DIVISORS)
    (tmp_path / 'cells.csv').write_text('divisor: fraction @shape\n' + rows + '\n', encoding='utf-8')
    return hybrid.compile(tmp_path / 'model.scn')


def test_a_bound_that_reads_an_input_has_the_number_of_the_values_of_the_plan(tmp_path):
    """The cap is 1 by the file, and each cell holds `0.01 * 10 / divisor` after 10 days: the sum
    is 0.1 (1/2 + 1/4 + 1/5). The plan has the cap as the upper bound of the level. A second
    quantity, in days, has the bounds 0.5 days and twice a limit of 3 days: the plan holds them in
    hours, the unit in which the engine keeps a time. A plan that is made with the cap 1.5 has
    that bound, and the bounds of the other quantity as before."""
    core = core_of(tmp_path)
    plan = timeline.Plan.of(core)
    assert (plan.quantities['cells_1.held'].lower, plan.quantities['cells_1.held'].upper) == (0.0, 1.0)
    assert (plan.quantities['cells_1.waited'].lower, plan.quantities['cells_1.waited'].upper) == (12.0, 144.0)
    assert plan.bound_reads == {'cells_1.cap', 'cells_1.limit'}
    exact = 0.1 * sum(1 / divisor for divisor in DIVISORS)
    assert timeline.run(plan).outputs['held'] == pytest.approx(exact, rel=1e-12)
    wider = timeline.Plan.of(core, None, {'cells_1.cap': 1.5})
    assert wider.quantities['cells_1.held'].upper == 1.5
    assert wider.quantities['cells_1.waited'].upper == 144.0
    assert timeline.run(wider).outputs['held'] == pytest.approx(exact, rel=1e-12)


def test_a_run_that_gives_the_input_of_a_bound_another_value_needs_its_own_plan(tmp_path):
    """The plan holds one bound. A run that gave the cap another value would run with the bound
    of the plan: the run is refused, and the message names the input. Another input is free."""
    plan = timeline.Plan.of(core_of(tmp_path))
    with pytest.raises(ValueError, match=r'A bound of a quantity reads cells_1\.cap'):
        timeline.run(plan, {'cells_1.cap': 1.5})
    faster = timeline.run(plan, {'cells_1.pace': 0.02})
    assert faster.outputs['held'] == pytest.approx(0.2 * sum(1 / divisor for divisor in DIVISORS), rel=1e-12)
    assert np.all(faster.final('cells_1.held') <= 1.0)


def test_a_plan_of_a_run_with_no_table_reads_no_input_for_a_bound(tmp_path):
    """A resolved run has each bound as a number: its plan keeps no input of a bound, and a run
    of it can take any value of the cap that the checks of the model admit."""
    core = core_of(tmp_path)
    flat = timeline.Plan.flat(core.model.resolve(next(iter(core.model.runs))), dict(core.model.library))
    assert flat.bound_reads == set()
