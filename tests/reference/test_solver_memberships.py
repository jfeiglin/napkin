"""A membership in a declared solver's constraint, on the oracle (spec, "Units, comparisons and
layout": `x in [lo, hi]` holds when `lo <= x <= hi`, and reversed bounds are an error).

The oracle reads a constraint as every evaluation reads an expression (`Ev._within`, through
`network.assemble`): the value and the ends once, ends that the instant knows checked first, so
that a reversed interval stops the run by the one name of the failure (`REVERSED`, the words of
`napkin.core.ops`), and ends in order are the chain's two relations. The engine has the same rule
(`timeline/declared.Former._membership`): the two agree on the plant of
`tests/engine/test_solver_memberships.py`, with the ends in order and equal, reversed by a stage,
and reversed by an edit at a stop. By hand: the provider maximizes the clinic's rate within
[lo, hi]: 3 L/h in [1, 3], so the tank of 100 L holds 97 L at 1 h; 2 L/h in [2, 2]; [4, 2] at 1 h
stops both runs there by name.
"""

from fractions import Fraction

import pytest

from napkin.core import ops
from napkin.engine import read, run
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_solver_memberships import plant
from tests.reference.evaluate import REVERSED
from tests.reference.from_program import run_of, value_at

CONFIGURATION = Configuration(Request(2))
RATE, WATER = Key('clinic', ('use', 'actual_rate')), Key('tank', ('water',))


def test_the_oracle_names_the_reversed_interval_as_the_engine_does():
    assert REVERSED == ops.REVERSED


@pytest.mark.parametrize(('low', 'high', 'rate'), [(1, 3, 3), (2, 2, 2)])
def test_a_membership_in_order_is_its_two_relations_on_the_oracle_and_the_engine(low, high, rate):
    program = plant(low, high)
    oracle, failed = run_of(program, CONFIGURATION)
    assert failed is None
    assert value_at(oracle, program, RATE, Fraction(1, 2)) == rate
    assert value_at(oracle, program, WATER, 1) == 100 - rate
    record = run(program, CONFIGURATION)
    assert record.failure is None
    assert read(record, program, [RATE], [0.5])[0].values == (pytest.approx(rate),)


def test_a_membership_that_a_stage_reverses_stops_both_runs_by_name_at_the_solve():
    program = plant(swap=True)
    oracle, failed = run_of(program, CONFIGURATION)
    assert failed is not None and REVERSED in str(failed) and oracle.view.t == 1
    record = run(program, CONFIGURATION)
    assert record.failure.t == pytest.approx(1) and ops.REVERSED in record.failure.detail('message')


def test_a_membership_that_an_edit_reverses_stops_the_oracle_by_name_at_the_solve():
    """Stopped before the tick at 1 h, lo and hi edited to 4 L/h and 2 L/h: the next solve, after the
    round's stages, finds the interval reversed (the engine's case is in the engine's tests)."""
    edits = [(Key('provider', ('lo',)), 4), (Key('provider', ('hi',)), 2)]
    oracle, failed = run_of(plant(), CONFIGURATION, [('provider.tick.step[0]', None, edits)])
    assert failed is not None and REVERSED in str(failed) and oracle.view.t == 1
