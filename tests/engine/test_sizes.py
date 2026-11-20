"""The engine sizes each store (`timeline/run.py`, "The sizes").

A store's absolute tolerance is `atol_factor` times its size: its `scale` when it declares one (D8),
else the largest of one of its unit, its start value, its finite bounds and the largest start value
of the stores that flows connect it to. The expectations are that rule, applied by hand to small
programs, and closed forms of their runs.
"""

import math

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run
from napkin.program.build import SOURCE, Builder, flow, formula, q, this, value
from napkin.program.config import Configuration, Request

START = 1e8  # people
RATE = 1e6  # people an hour: the stock is empty at 100 h
HORIZON = 150
UNITS = {'person': {'people': 1}, 'h': {'time': 1}}


def drained(*parts):
    """A stock of 1e8 people that drains into a tally at 1e6 people an hour until it is empty, at
    100 h, in a run of 150 h. Neither declares a scale."""
    b = Builder(UNITS)
    b.entity(
        's',
        value('stock', 'person', START, lower=0),
        value('drained', 'person', 0, lower=0),
        *parts,
        flow('drain', this.stock, this.drained, request=q(RATE, 'person/h')),
    )
    return b.finish()


def sizes(program):
    """{store: its size} at the start of a run of the program."""
    made = Run(Plan.of(program, Configuration(Request(HORIZON))))
    return made.prepare()[1]


def test_each_store_takes_the_size_of_its_rule():
    found = sizes(
        drained(
            # A clock that only its own flow fills, from outside: nothing but its unit sizes it.
            value('clock', 'h', 0),
            flow('tick', SOURCE, this.clock, request=q(1, 'h/h')),
            # A store with a scale of its own, which the engine takes as written.
            value('kept', 'person', 0, scale=500),
            flow('keep', SOURCE, this.kept, request=q(0, 'person/h')),
        )
    )
    assert found['s.stock'] == START  # its start value
    assert found['s.drained'] == START  # the start value of the stock that its flow drains
    assert found['s.clock'] == 1  # one of its unit
    assert found['s.kept'] == 500


def draining(scale):
    """A stock of 1e8 people drains into a tally at 2e6 people an hour times t / (t + 1 h), which the
    solver integrates: S(t) = 1e8 - 2e6 (t - ln(1 + t)) until it is empty, at about 54 h. `scale` is
    the scale that both declare (None: the engine sizes them)."""
    b = Builder(UNITS)
    b.entity(
        's',
        value('stock', 'person', START, lower=0, scale=scale),
        value('drained', 'person', 0, lower=0, scale=scale),
        value('clock', 'h', 0, lower=0),
        flow('tick', SOURCE, this.clock, request=q(1, 'h/h')),
        flow(
            'drain',
            this.stock,
            this.drained,
            request=formula(q(2 * RATE, 'person/h') * this.clock / (this.clock + q(1, 'h'))),
        ),
    )
    return b.finish()


@pytest.mark.parametrize('scale', [None, 1])
def test_a_large_stock_that_the_solver_drains_takes_its_own_size(scale):
    """The stock follows its integral to zero. At depletion a root bracketed by adjacent
    representable times is placed exactly on its bound even with a scale of one person."""
    program = draining(scale)
    record = run(program, Configuration(Request(HORIZON)))
    assert record.failure is None
    times = (10.0, 30.0, 50.0, HORIZON)
    stock, drained_ = read(record, program, ['s.stock', 's.drained'], times)
    for t, left_, moved in zip(times, stock.values, drained_.values, strict=True):
        left = max(0.0, START - 2 * RATE * (t - math.log1p(t)))
        assert left_ == pytest.approx(left, rel=1e-9, abs=1e-9 * START)
        assert moved == pytest.approx(START - left, rel=1e-9)
    assert stock.values[-1] == 0
