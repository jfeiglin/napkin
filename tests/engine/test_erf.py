"""The error function `erf` of the expression language (docs/language.md, §2.4).

`erf(x)` takes a number without a unit and gives a number without a unit. Its values come from the
same function in a compiled program and in an evaluation; mpmath, which computes erf with its own
series, is the independent reference. The domain prover reads that erf rises on the whole line and
stays between -1 and 1. A tally that fills at `erf(t / tau)` has a closed form, the integral of erf,
which a program (`napkin/program/build.py`) run on the engine gives.
"""

from __future__ import annotations

import math

import mpmath
import pytest

from napkin.core.expr import read
from napkin.engine import read as engine_read
from napkin.engine import run as engine_run
from napkin.expressions import (
    ExpressionError,
    UnitSystem,
    compile_program,
    domain_prover,
    evaluate,
    infer,
)
from napkin.program.build import SOURCE, Builder, call, flow, formula, input_, t, this, value
from napkin.program.config import Configuration, Request
from tests.units import UNITS

REGISTRY = UnitSystem(UNITS)
# Arguments from deep in both tails to zero, where erf changes fastest.
TAILS = [-30.0, -6.0, -3.5, 3.0, 5.9, 27.0]
ARGUMENTS = [*TAILS, -2.0, -1.0, -0.5, -1e-3, -1e-12, 0.0, 1e-12, 1e-3, 0.25, 0.5, 1.0, 1.7]


def ulps_apart(a, b):
    """How many floating-point steps lie between two doubles."""
    if a == b:
        return 0
    return abs(a - b) / math.ulp(max(abs(a), abs(b)))


@pytest.mark.parametrize('x', ARGUMENTS)
def test_erf_matches_mpmath_within_two_units_in_the_last_place(x):
    with mpmath.workdps(50):
        reference = float(mpmath.erf(mpmath.mpf(x)))
    value = evaluate(read('erf(x)'), {'x': x}, REGISTRY)
    assert ulps_apart(value, reference) <= 2
    # The function is odd: the value at -x is the negative of the value at x.
    assert ulps_apart(evaluate(read('erf(-x)'), {'x': x}, REGISTRY), -reference) <= 2


def test_a_program_gives_the_evaluated_erf_bit_for_bit_and_folds_a_known_argument():
    program = compile_program(
        [], [read('erf(x)'), read('erf(p.a / 2)')], constants={'p.a': 1.5}, units=REGISTRY
    )
    for x in ARGUMENTS:
        values = program({'x': x}, REGISTRY)
        assert values[0].hex() == evaluate(read('erf(x)'), {'x': x}, REGISTRY).hex()
        assert values[1].hex() == math.erf(0.75).hex()


def test_erf_takes_a_number_without_a_unit():
    # The typing of an expression: a dimensionless argument gives a dimensionless number.
    assert not infer(read('erf(d / q(2, "h"))'), {'d': 'h'}, REGISTRY).dimensions
    with pytest.raises(ExpressionError):
        infer(read('erf(d)'), {'d': 'h'}, REGISTRY)
    with pytest.raises(ExpressionError):
        infer(read('erf(x, x)'), {'x': 'fraction'}, REGISTRY)


def test_the_domain_prover_bounds_erf_between_minus_one_and_one():
    prove = domain_prover({'x': (-1e300, 1e300), 'y': (0.0, 1.0)}, REGISTRY)
    low, high = prove(read('erf(x)'))
    assert (low, high) == (-1.0, 1.0)
    # 2 - erf(x) lies from 1 to 3 for every x, so its reciprocal is finite.
    assert prove(read('1 / (2 - erf(x))')) == pytest.approx((1 / 3, 1.0))
    # erf(y) is 0 at y = 0, so a division by it cannot be proved safe on [0, 1].
    with pytest.raises(ExpressionError):
        prove(read('1 / erf(y)'))
    # On [0, 1] the ends of erf are erf(0) and erf(1): erf rises.
    assert prove(read('erf(y)')) == (0.0, math.erf(1.0))


def test_a_tally_that_fills_at_erf_of_time_matches_the_integral_of_erf():
    # The tally fills at erf(t / tau) people an hour, so after T hours it holds
    # T erf(T / tau) + tau (exp(-(T / tau)^2) - 1) / sqrt(pi) people.
    horizon, tau = 10.0, 4.0
    b = Builder({'h': {'time': 1}, 'person': {'people': 1}})
    b.entity(
        'area',
        input_('tau', 'h', tau),
        input_('flow_unit', 'person/h', 1),
        value('people', 'person', 0),
        flow('fill', SOURCE, this.people, request=formula(call('erf', t / this.tau) * this.flow_unit)),
    )
    program = b.finish()
    record = engine_run(program, Configuration(Request(horizon)))
    assert record.failure is None
    (reading,) = engine_read(record, program, ['area.people'], [horizon])
    ratio = horizon / tau
    expected = horizon * math.erf(ratio) + tau * (math.exp(-(ratio**2)) - 1) / math.sqrt(math.pi)
    assert reading.values[0] == pytest.approx(expected, rel=1e-7)
