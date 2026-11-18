"""A bound written as an expression of inputs, in a model with a table: a run takes the bounds that
the values of its inputs give (`timeline/run.py`, "The start").

The model is a table of cells, each filling at a constant pace over a divisor that the table gives,
up to a cap that is an input, beside a second stored value in days whose bounds are half a day and
twice an input limit. Each level at the horizon is a product, written beside each test.
"""

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run
from napkin.program.build import SOURCE, Builder, flow, formula, fsum, input_, q, this, value
from napkin.program.config import Configuration, InputValue, Quantity, Request

UNITS = {'h': {'time': 1}, 'day': ({'time': 1}, 24)}
DIVISORS = (2, 4, 5)
HORIZON = 10 * 24.0  # 10 days


def cells(pace):
    """Cells that fill at `pace` a day over their divisor, up to their cap."""
    b = Builder(UNITS)
    cell = b.template(
        'Cell',
        input_('cap', '', 1, lower=0.5, upper=2),
        input_('pace', '1/day', pace, lower=0, upper=1),
        input_('divisor', '', 2),
        input_('limit', 'day', 3, lower=1, upper=9),
        value('held', '', 0, lower=0, upper=this.cap),
        value('waited', 'day', 1, lower=q(0.5, 'day'), upper=2 * this.limit),
        flow('fill', SOURCE, this.held, request=formula(this.pace / this.divisor)),
    )
    b.table('cells', cell, [{'divisor': divisor} for divisor in DIVISORS])
    b.root(value('held', '', formula(fsum(cell.instances.held))))
    return b.finish()


def every(name, number, unit=''):
    """The same value of an input for each cell."""
    return tuple(InputValue(f'cells[{row}]', name, Quantity(number, unit)) for row in range(len(DIVISORS)))


def held(program, *inputs):
    record = run(program, Configuration(Request(HORIZON), inputs=inputs))
    assert record.failure is None
    (reading,) = read(record, program, ['held'], [HORIZON])
    return reading.values[0]


def test_a_bound_that_reads_an_input_has_the_number_of_the_values_of_the_run():
    """The cap is 1, and each cell holds `0.01 * 10 / divisor` after 10 days: the sum is
    0.1 (1/2 + 1/4 + 1/5) = 0.095. The waited value has the bounds half a day and twice a limit of
    3 days: the run holds them in hours, the unit in which the engine keeps a time. A run with the
    cap 1.5 has that bound, and the bounds of the other value as before."""
    program = cells(0.01)
    made = Run(Plan.of(program, Configuration(Request(HORIZON))))
    made.start()
    assert made.bounds['cells[0].held'] == (0.0, 1.0)
    assert made.bounds['cells[0].waited'] == (12.0, 144.0)
    exact = 0.1 * sum(1 / divisor for divisor in DIVISORS)
    assert held(program) == pytest.approx(exact, rel=1e-12)
    wider = Run(Plan.of(program, Configuration(Request(HORIZON), inputs=every('cap', 1.5))))
    wider.start()
    assert wider.bounds['cells[1].held'] == (0.0, 1.5)
    assert wider.bounds['cells[1].waited'] == (12.0, 144.0)
    assert held(program, *every('cap', 1.5)) == pytest.approx(exact, rel=1e-12)


def test_a_cap_that_the_configuration_sets_holds_each_cell_at_its_bound():
    """At 0.4 a day the cells would hold 4 / divisor after 10 days, 2, 1 and 0.8: with the cap 1 they
    hold 1, 1 and 0.8 (2.8), and with the cap 1.5 they hold 1.5, 1 and 0.8 (3.3). The first cell
    reaches the cap 1 at 5 days. Another input is free: at 0.02 a day the cells hold 0.19 in all."""
    program = cells(0.4)
    assert held(program) == pytest.approx(2.8, rel=1e-12)
    assert held(program, *every('cap', 1.5)) == pytest.approx(3.3, rel=1e-12)
    record = run(program, Configuration(Request(HORIZON)))
    (first,) = read(record, program, ['cells[0].held'], [4 * 24.0, 5 * 24.0, 8 * 24.0])
    assert first.values == pytest.approx((0.8, 1.0, 1.0))
    assert held(cells(0.01), *every('pace', 0.02, '1/day')) == pytest.approx(
        0.2 * sum(1 / divisor for divisor in DIVISORS), rel=1e-12
    )
