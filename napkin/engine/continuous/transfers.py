"""Integrals of physical-leg rates on a method's accepted trajectory.

Radau already integrates each store's incidence-weighted sum of leg rates. For a
single leg meeting a store alone its dense polynomial holds the leg's integral
as increments, before adding the starting inventory. When flows overlap, use
the same three collocation nodes for each physical rate. A cut integrates that
polynomial only to the accepted time. Solver/Jacobian trials never post.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
from numpy.polynomial import Polynomial
from numpy.polynomial.polynomial import polyval
from scipy.integrate import quad_vec
from scipy.integrate._ivp.radau import C

from ...core import expr as nodes
from ...core.literals import Literals, node_parts
from ...core.units import rational
from ..errors import SimulationError
from .walk import walked


def _clock_polynomial(node, values, literals):
    """Coefficients of a polynomial in t, in canonical units. Fold constant subexpressions with
    the literal evaluator. Stop expanding at degree 47, the precision of the 24-point Gauss rule
    used for the remaining rates; high powers can otherwise expand exponentially."""
    if isinstance(node, nodes.Ref) and isinstance(values.get(node.name), Polynomial):
        return values[node.name]
    op, args, data = node_parts(node)
    if op in ('add', 'sub', 'mul', 'div', 'pow', 'sum', 'q', 'neg', 'pos') and args:
        terms = []
        for arg in args:
            term = yield _clock_polynomial(arg, values, literals)
            if term is None:
                return None
            terms.append(term)
        first = terms[0]
        if op in ('sum', 'add'):
            return sum(terms)
        if op == 'sub':
            return first - terms[1]
        if op == 'mul':
            return first * terms[1] if first.degree() + terms[1].degree() <= 47 else None
        if op == 'q':
            return first * literals.scale(data)
        if op in ('neg', 'pos'):
            return -first if op == 'neg' else first
        if terms[1].degree() == 0:
            scalar = terms[1].coef[0]
            if op == 'div' and scalar:
                return first / scalar
            if op == 'pow' and scalar.denominator == 1 and scalar >= 0 and first.degree() * scalar <= 47:
                if scalar > 1024:
                    return None
                if not first.degree() or not scalar:
                    return Polynomial([Fraction(first.coef[0]) ** int(scalar)])
                return first ** int(scalar)
    constant = literals.value(node)
    return Polynomial([constant]) if isinstance(constant, Fraction) else None


def direct_clock_primitive(flow, plan):
    """An unrestricted single pipe whose request is polynomial in the clock alone.
    The method separately checks whether a physical bound holds the pipe."""
    if flow.capacity is not None:
        return None
    expression = plan.expanded(flow.request)
    if not expression.time or expression.leaves or expression.stepped:
        return None
    ends = ((flow.source, 'outflow'), (flow.sink, 'inflow'))
    if any(key in plan.ends and plan.settled(plan.ends[key]) for key in ends):
        return None
    literals = Literals(node_parts, plan.units.exact_scale, plan.units.comparisons.factor)
    values = {'t': Polynomial([Fraction(0), Fraction(1)])}
    for name in plan.ordered(expression.formulas):
        node = plan.values[name].node
        values[name] = walked(_clock_polynomial(node, values, literals))
        if values[name] is None:
            return None
    poly = values.get(flow.request)
    if poly is not None:
        return (Fraction(0), *(Fraction(c) / (k + 1) for k, c in enumerate(poly.coef)))
    return None


def clock_primitives(flows, plan):
    rates = []
    for name in flows:
        primitive = direct_clock_primitive(plan.flows[name], plan)
        if primitive is None:
            return None
        rates.append(primitive)
    return rates


class HeldAmounts:
    """Only a change of a held leg's rate closes its previous rectangle."""

    def __init__(self, start):
        self.start = start
        self.closed = {}

    def amount(self, row, t, rate):
        start, previous = self.closed.get(row, (self.start, 0))
        if t < start:
            raise ValueError('transfer requested before its current held interval')
        return previous + (rational(t) - rational(start)) * rational(rate) if rate else previous

    def change(self, row, t, previous_rate):
        self.closed[row] = t, self.amount(row, t, previous_rate)


class CollocationRates:
    """Capture physical rates alongside Newton's scalar RHS. Finite-difference
    Jacobian probes use SciPy's separate vectorized function. On acceptance keep
    the last solve's two interior rates and its converged endpoint rate.
    """

    def __init__(self, solver, read_rates):
        self.samples = {}
        self.previous = None
        original = solver.fun

        def evaluate(t, y):
            change = original(t, y)
            self.samples[t] = read_rates()
            return change

        solver.fun = evaluate

    def finish(self, step):
        first, second = step.t_old + step.h * C[:2]
        step.leg_rates = self.samples[first], self.samples[second], self.samples[step.t]
        step.prior_rates = None
        if self.previous is not None and self.previous[0] == step.t_old:
            step.prior_rates = self.previous[1:]
        self.previous = step.t, step.h, step.leg_rates
        self.samples.clear()


# Integral from 0 to x of the three Lagrange basis functions on Radau's nodes.
# At x=1 use the fifth-order collocation quadrature weights.
_WEIGHTS = np.linalg.inv(np.vander(C, increasing=True))
_FULL = (np.array([1.0, 0.5, 1 / 3]) @ _WEIGHTS).tolist()


def radau_amount(step, end, single):
    x = (end - step.t_old) / step.h
    if single is not None:
        row, sign = single
        q0, q1, q2 = step.Q[row]
        return sign * x * (q0 + x * (q1 + x * q2))
    weights = _FULL if x == 1 else (np.array([x, x * x / 2, x**3 / 3]) @ _WEIGHTS)
    a, b, c = step.leg_rates
    return step.h * (weights[0] * a + weights[1] * b + weights[2] * c)


def checked_amount(step, end, rate_at, rtol, absolute_rates):
    """Control the error of physical rates hidden in a store's net derivative.

    Six existing nodes on adjacent accepted Radau steps integrate a fifth-degree
    interpolant. Compare against the present step's third-order dense integral
    (fifth order for a complete step). On the first step check its omitted start.
    Refine the actual allocated rates on the accepted trajectory where the two
    estimates disagree. A tiny leg has its own error budget even beside a large leg.
    """
    amount = radau_amount(step, end, None)
    if end == step.t_old:
        return amount
    x = (end - step.t_old) / step.h
    if step.prior_rates is None or not 0.125 <= step.prior_rates[0] / step.h <= 8:
        # A restart, or two disparate step sizes, cannot support an accurate
        # two-step interpolant. Check the omitted node on this step alone.
        estimated = (
            step.h * x * (rate_at(step.t_old) - sum(w * r for w, r in zip(_WEIGHTS[0], step.leg_rates)))
        )
    else:
        previous_h, previous = step.prior_rates
        nodes = np.concatenate(((C - 1) * (previous_h / step.h), C))
        powers = np.arange(1, 7)
        weights = np.linalg.solve(np.vander(nodes, increasing=True).T, x**powers / powers)
        higher = step.h * sum(weight * rate for weight, rate in zip(weights, (*previous, *step.leg_rates)))
        estimated = higher - amount
    tolerance = np.maximum(absolute_rates * (end - step.t_old) + rtol * np.abs(amount), np.finfo(float).tiny)
    if np.all(np.abs(estimated) <= tolerance) and np.all(amount >= -tolerance):
        return np.maximum(amount, 0)
    # Normalize each connection separately so a weak circulation never inherits
    # the numerical budget of a much larger inter-store transfer.
    result, _, info = quad_vec(
        lambda t: rate_at(t) / tolerance,
        step.t_old,
        end,
        epsabs=0.5,
        epsrel=0,
        norm='max',
        quadrature='gk15',
        full_output=True,
    )
    if not info.success and info.status != 2:
        raise SimulationError('Cannot certify the transferred amounts on the accepted interval')
    return np.maximum(result * tolerance, 0)


class MovingAmounts:
    """Accumulate only the local batch whose interval the timeline accepts."""

    def __init__(self, rows, start, single):
        self.single = single
        self.primitive = None
        self.clock_rates = None
        self.absolute_rates = None
        self.exact = Fraction(0)
        self.through = start
        self.total = 0.0 if single is not None else np.zeros(rows)
        self.remainder = 0.0 if single is not None else np.zeros(rows)

    def polynomial_amount(self, start, end):
        return polyval(rational(end), self.primitive) - polyval(rational(start), self.primitive)

    def tolerances(self, run, names):
        if self.absolute_rates is None:
            self.absolute_rates = np.array(
                [run.plan.numerics.atol_factor * run.own_scale(name) for name in names]
            )
        return self.absolute_rates

    def clock_amounts(self, start, end):
        left, right = rational(start), rational(end)
        return np.array([float(polyval(right, poly) - polyval(left, poly)) for poly in self.clock_rates])

    def accept(self, start, end, amount):
        if start != self.through or end < start:
            raise ValueError(f'cannot accept transferred amounts over [{start}, {end}] after {self.through}')
        if self.primitive is not None:
            self.exact += amount
            self.through = end
            return
        corrected = amount - self.remainder
        total = self.total + corrected
        self.remainder = (total - self.total) - corrected
        self.total, self.through = total, end

    def amount(self, row, prefix=0):
        if self.primitive is not None:
            return self.exact + prefix
        total, remainder = self.total, self.remainder
        if self.single is None:
            total, remainder = total[row], remainder[row]
        if prefix:
            corrected = prefix - remainder
            new = total + corrected
            remainder = (new - total) - corrected
            total = new
        return Fraction.from_float(float(total)) - Fraction.from_float(float(remainder))
