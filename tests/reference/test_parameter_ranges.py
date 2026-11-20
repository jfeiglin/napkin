"""An event's parameter keeps its declared range (spec.md:572: "Check declared parameter types, units
and entry bounds"), in the reference interpreter as in the engine.

A start whose argument lies outside the declared range of its parameter fails the run where the start
registers (the commit of the setup or of a stage, or a firing), naming the parameter; an argument on
an edge of its range is inside it. The rule test: random ranges (a lower bound, an upper bound or
both, in L or in mL), random arguments inside, on the edges of and outside them, and a start from the
setup, from a stage or from a firing of the event's own trigger: the oracle and the engine fail at the
same time, or both run with the same values.
"""

from __future__ import annotations

import random
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    Builder,
    add,
    after,
    event,
    named,
    param,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}, 'mL': ({'volume': 1}, Fraction(1, 1000))}
HORIZON = 3


def program(seed):
    """`plant.take(amount)` with a random range, started with a random argument from the setup, from
    a stage at 1 h or from its own trigger at 1 h; its stage adds the amount to `plant.got`."""
    rng = random.Random(seed)
    unit = rng.choice(['L', 'mL'])
    scale = 1000 if unit == 'mL' else 1
    low, high = rng.choice([(0, 10), (2, 6), (None, 4), (1, None)])
    argument = q(rng.choice([low or 0, high or 8, 3, 5, 12, -1]) * scale, unit)
    lower = None if low is None else q(low * scale, unit)
    upper = None if high is None else q(high * scale, unit)
    how = rng.choice(['setup', 'stage', 'firing'])
    fired = (
        [when(t >= q(1, 'h'), start(this.take, argument), reset=reset_when(False))] if how == 'firing' else []
    )
    take = event(
        'take',
        param('amount', unit, lower=lower, upper=upper),
        after(q(1, 'h'), add(named('plant').got, named('plant').unit_amount)),
        *fired,
    )
    b = Builder(UNITS)
    parts = [value('got', 'L', 0), value('unit_amount', 'L', q(1, 'L')), take]
    if how == 'stage':
        parts.append(event('kick', after(q(1, 'h'), start(this.take, argument))))
    b.entity('plant', *parts)
    b.setup(*([start(named('plant').take, argument)] if how == 'setup' else []))
    if how == 'stage':
        b.setup(start(named('plant').kick))
    return b.finish()


@pytest.mark.parametrize('seed', range(80))
def test_an_argument_outside_its_parameter_s_range_fails_both_runs_at_the_start(seed):
    program_ = program(seed)
    configuration = Configuration(Request(HORIZON))
    oracle, failed = run_of(program_, configuration)
    record = run(program_, configuration)
    if failed is not None:
        assert record.failure is not None, (seed, str(failed))
        at = 0 if oracle is None else float(oracle.view.t)
        assert record.failure.t == pytest.approx(at), (seed, str(failed), record.failure)
        assert 'amount' in record.failure.detail('message') and 'amount' in str(failed)
        return
    assert record.failure is None, (seed, record.failure.detail('message'))
    found = read(record, program_, [Key('plant', ('got',))], [0, 1, 2, 3])[0].values
    expected = [float(value_at(oracle, program_, Key('plant', ('got',)), time)) for time in (0, 1, 2, 3)]
    assert list(found) == pytest.approx(expected)


def test_twenty_litres_into_a_parameter_of_at_most_ten_fails_at_the_start():
    """The review's case (R06): `take = event(amount: L in [0 L, 10 L])` started with 20 L from the
    setup fails at 0 h in both (on 2cd1751 the oracle ran it to the horizon, got = 20 L)."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('got', 'L', 0),
        event(
            'take',
            param('amount', 'L', lower=q(0, 'L'), upper=q(10, 'L')),
            after(q(1, 'h'), add(this.got, q(1, 'L'))),
        ),
    )
    b.setup(start(named('plant').take, q(20, 'L')))
    program_ = b.finish()
    configuration = Configuration(Request(4))
    oracle, failed = run_of(program_, configuration)
    assert failed is not None and 'amount' in str(failed) and oracle.view.t == 0
    record = run(program_, configuration)
    assert record.failure is not None and record.failure.t == 0
