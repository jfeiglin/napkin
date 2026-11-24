"""Assertions over state (spec, "Assertions and their timing"; R-A2-15; `triggers.Triggers.check`).

An assertion that reads state is checked after every round and at each
contact with its boundary that the engine finds between moments: a store that leaves its asserted
interval between two scheduled events fails the run at the time that it leaves. An assertion over
inputs is checked once, at the start. The expected times are the closed forms of lines and of an
exponential, worked by hand, and the oracle's (`tests/reference/`).
"""

from __future__ import annotations

import math

import pytest

from napkin.engine import run
from napkin.engine.timeline import Plan, Run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assertion,
    assign,
    endpoint,
    event,
    flow,
    formula,
    ifelse,
    input_,
    named,
    q,
    start,
    subtract,
    this,
    value,
)
from napkin.program.config import Configuration, Numerics, Request
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def tank(check, *stages, water=10, request=None, horizon=9):
    """A tank of `water` L that drains at 1 L/h (or `request`), with the assertion `check` and an
    event of `stages`, started by the setup; the run's record, and the oracle's failure."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', water, lower=0),
        input_('floor', 'L', 5),
        flow('drain', this.water, SINK, request=request if request is not None else q(1, 'L/h')),
        assertion(check),
        event('care', *stages),
    )
    b.setup(start(named('tank').care))
    program = b.finish()
    configuration = Configuration(Request(horizon))
    try:
        _, failed = run_of(program, configuration)
    except NotCovered:  # the oracle moves no store on a curve
        failed = None
    return run(program, configuration), failed


def test_a_store_that_leaves_its_interval_between_moments_fails_when_it_leaves():
    """R-A2-15: 10 L drains at 1 L/h with `assert water >= 5 L`, and a stage refills it at 7 h: the
    run fails just after 5 h, not at the refill."""
    record, oracle = tank(this.water >= q(5, 'L'), after(q(7, 'h'), assign(this.water, q(10, 'L'))))
    assert record.failure.t == pytest.approx(5)
    message = record.failure.detail('message')
    assert 'tank.assert[0]: the assertion does not hold for tank at t = 5 h' in message
    assert 'just after t = 5 h' in str(oracle)


def test_a_strict_assertion_fails_at_its_boundary():
    """`water > 5 L` no longer holds when the tank holds 5 L, at 5 h."""
    record, oracle = tank(this.water > q(5, 'L'), after(q(7, 'h')))
    assert record.failure.t == pytest.approx(5)
    assert 'does not hold for tank at t = 5 h' in record.failure.detail('message')
    assert 'fails at t = 5 h' in str(oracle)


def test_a_write_that_breaks_an_assertion_fails_at_its_commit():
    """A stage at 2 h takes 6 L of the 8 L left: 2 L is below the floor of 5 L at once."""
    record, oracle = tank(this.water >= this.floor, after(q(2, 'h'), subtract(this.water, q(6, 'L'))))
    assert record.failure.t == 2
    assert 'at t = 2 h' in record.failure.detail('message') and 'at t = 2 h' in str(oracle)


def test_an_assertion_that_holds_throughout_lets_the_run_reach_its_horizon():
    """A refill at 4 h puts 6 L back: the tank holds 6 L at its lowest, at 4 h, and 1 L at 9 h is
    above the floor of 0 L."""
    record, oracle = tank(this.water >= q(0, 'L'), after(q(4, 'h'), add(this.water, q(6, 'L'))))
    assert record.failure is None and oracle is None


def test_an_assertion_on_a_curve_fails_where_its_store_crosses():
    """A leak of a tenth of the water an hour: 10 e^(-t/10) reaches 5 L at 10 ln 2 h."""
    record, _ = tank(this.water >= q(5, 'L'), after(q(8, 'h')), request=formula(this.water / q(10, 'h')))
    # The contact is found to the crossing tolerance (1e-8 h), at or just after the crossing.
    assert record.failure.t == pytest.approx(10 * math.log(2), abs=1e-7)
    assert 'the assertion does not hold for tank' in record.failure.detail('message')


def test_an_assertion_still_inside_its_band_at_the_horizon_holds():
    """At 5 h the stock is at raw equality. It leaves the closed band after the horizon."""
    record, oracle = tank(this.water >= q(5, 'L'), after(q(7, 'h')), horizon=5)
    assert record.failure is None and record.end == 5
    assert oracle is not None  # the exact-arithmetic oracle has no comparison band


@pytest.mark.parametrize('factor', [1e-9, 1e-7], ids=['tight', 'wide'])
@pytest.mark.parametrize('method', ['component', 'sparse'])
def test_a_leak_breaks_an_inclusive_assertion_only_at_the_band_exit(factor, method):
    b = Builder(UNITS)
    settings = {'outflow': endpoint(capacity=q(10, 'L/h'))} if method == 'sparse' else {}
    b.entity(
        'vat',
        value('stock', 'L', 1000, lower=0, **settings),
        flow(
            'leak',
            this.stock,
            SINK,
            request=formula(ifelse(this.stock > q(10, 'L'), q(1, 'L/h'), q(0, 'L/h'))),
        ),
        assertion(this.stock >= q(999.999, 'L')),
    )
    numeric = Numerics(rtol=factor, atol_factor=factor / 10)
    program = b.finish()
    live = Run(Plan.of(program, Configuration(Request(2), numerics=numeric)))
    record = live.run()
    assert live.ways.sets[live.ways.set_of['vat.stock']][0].way == method
    exit_time = (1000 - 999.999) + factor * 999.999
    assert record.failure is not None and 'vat.assert[0]' in record.failure.detail('message')
    assert abs(record.failure.t - exit_time) <= numeric.crossing


@pytest.mark.parametrize('factor', [1e-9, 1e-7], ids=['tight', 'wide'])
@pytest.mark.parametrize('cross_zero', [False, True], ids=['growing-band', 'shrinking-then-growing-band'])
def test_a_constant_gap_can_cross_a_moving_comparison_band(factor, cross_zero):
    # The gap stays at 1 L. In the second case the two stocks pass through zero.
    # Equality holds at both ends of the run and fails inside it.
    rate = round(1 / factor)
    initial = -2 * rate if cross_zero else 0
    b = Builder(UNITS)
    b.entity(
        'vat',
        value('a', 'L', initial + 1),
        value('b', 'L', initial),
        flow('fill_a', SOURCE, this.a, request=q(rate, 'L/h')),
        flow('fill_b', SOURCE, this.b, request=q(rate, 'L/h')),
        assertion(this.a == this.b if cross_zero else this.a > this.b),
    )
    numeric = Numerics(rtol=factor, atol_factor=factor / 10)
    record = run(b.finish(), Configuration(Request(4), numerics=numeric))
    exit_time = 1 if cross_zero else (1 / factor - 1) / rate
    assert record.failure is not None and 'vat.assert[0]' in record.failure.detail('message')
    assert abs(record.failure.t - exit_time) <= numeric.crossing


def test_a_strict_assertion_can_fail_at_the_settled_horizon():
    record, _ = tank(this.water > q(0, 'L'), after(q(5, 'h'), assign(this.water, q(0, 'L'))), horizon=5)
    assert record.failure is not None and record.failure.t == 5
    assert 'tank.assert[0]' in record.failure.detail('message')


def test_an_assertion_over_inputs_is_checked_once_at_the_start():
    """`floor <= 4 L` reads an input only: with the floor at 5 L the run fails at its start."""
    record, oracle = tank(this.floor <= q(4, 'L'), after(q(1, 'h')))
    assert record.failure.t == 0 and 'the assertion does not hold for tank' in record.failure.detail(
        'message'
    )
    assert oracle is not None
