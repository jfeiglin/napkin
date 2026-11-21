"""Integrals of physical-leg rates on a method's accepted trajectory.

Radau already integrates each store's incidence-weighted sum of leg rates. For a
single leg meeting a store alone its dense polynomial holds the leg's integral
as increments, before adding the starting inventory. When flows overlap, use
the same three collocation nodes for each physical rate. A cut integrates that
polynomial only to the accepted time. Solver/Jacobian trials never post.
"""

from __future__ import annotations

from decimal import Context, Decimal
from fractions import Fraction
from functools import lru_cache

import numpy as np
from numpy.polynomial import Polynomial
from numpy.polynomial.legendre import leggauss
from numpy.polynomial.polynomial import polyval
from scipy.integrate import quad, quad_vec
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
    """An uncapped pipe whose request is polynomial in the clock alone. A method
    must separately certify that local sharing actually gives it this request."""
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


@lru_cache(maxsize=1)
def _gauss_rule():
    """Positive Gauss weights on [0, 1], normalized to sum exactly to one."""
    points, weights = leggauss(24)
    denominator = sum(map(rational, weights))
    return [((1 + rational(x)) / 2, rational(w) / denominator) for x, w in zip(points, weights)]


def certified_amount(rate, a, b, label):
    """Measure a curved rate on QUADPACK's accepted subintervals, accumulating all weights and
    durations before rounding. Neither the numerical error estimate nor the number of intervals
    increases the physical allowance."""
    answer = quad(rate, a, b, epsabs=0, epsrel=1e-13, full_output=True)
    if len(answer) > 3:
        raise SimulationError(f'{label}: {answer[3]}')
    parts = answer[2]
    total = Fraction(0)
    for lo, hi in zip(parts['alist'][: parts['last']], parts['blist'][: parts['last']]):
        start = rational(lo)
        duration = rational(hi) - start
        total += duration * sum(w * rational(rate(float(start + x * duration))) for x, w in _gauss_rule())
    return total


class ClockLeg:
    """The cumulative amount for a pipe whose uncapped request has an exact primitive.

    Only the region changes and reads of this leg evaluate its primitive. When a
    constrained endpoint may alter the allocation, use the numerical leg's accepted
    cumulative increments until the request is again known to be delivered.
    """

    REQUEST, STOPPED, ALLOCATED = range(3)

    def __init__(self, polynomial, start, source, sink, feeds_source, drains_sink):
        self.polynomial = polynomial
        self.source, self.sink = source, sink
        self.feeds_source, self.drains_sink = feeds_source, drains_sink
        self.mode, self.start, self.closed, self.origin = self.REQUEST, start, 0, 0

    @classmethod
    def of(cls, polynomial, start, flow, places, plan):
        return cls(
            polynomial,
            start,
            places.get(flow.source),
            places.get(flow.sink),
            bool(flow.source and plan.incident(flow.source, 'inflow')),
            bool(flow.sink and plan.incident(flow.sink, 'outflow')),
        )

    def selection(self, lower, upper):
        source, sink = self.source, self.sink
        supply = source is not None and lower(source)
        room = sink is not None and upper(sink)
        if (supply and not self.feeds_source) or (room and not self.drains_sink):
            return self.STOPPED
        if supply or room or (self.feeds_source and upper(source)) or (self.drains_sink and lower(sink)):
            return self.ALLOCATED
        return self.REQUEST

    def integral(self, a, b):
        return polyval(rational(b), self.polynomial) - polyval(rational(a), self.polynomial) if a != b else 0

    def amount(self, t, numerical):
        if self.mode == self.ALLOCATED:
            return self.closed + numerical - self.origin
        if self.mode == self.REQUEST:
            return self.closed + self.integral(self.start, t)
        return self.closed

    def change(self, t, mode, numerical):
        self.closed = self.amount(t, numerical)
        self.mode, self.start = mode, t
        self.origin = numerical if mode == self.ALLOCATED else 0


# The canonical decimal spelling of a finite binary64 time or rate has no digit
# below 10**-324. A nonnegative sum of held rectangles is at most max_rate * t,
# below 10**617. Thus 1,300 decimal places of precision cover even the largest
# total with the smallest product (10**-648) still present, without rounding.
_HELD_CONTEXT = Context(prec=1300)
_ZERO = Decimal(0)
ZERO_AMOUNT = Fraction(0)


@lru_cache(maxsize=128)
def _decimal_time(t):
    return Decimal(repr(float(t)))


@lru_cache(maxsize=128, typed=True)
def held_elapsed(start, end):
    """Held legs in a generation use the same exact difference of accepted clock values."""
    return rational(end) - rational(start)


def _rectangle(start, end, rate, previous):
    if not rate or start == end:
        return previous
    duration = _HELD_CONTEXT.subtract(_decimal_time(end), _decimal_time(start))
    return _HELD_CONTEXT.fma(Decimal(repr(float(rate))), duration, previous)


class HeldAmounts:
    """One pending rate rectangle per changed row; untouched rows remain empty.

    Closing a row for the first time only retains the rectangle. A later change
    folds its predecessor into that row's subtotal. A read or checkpoint also
    evaluates the pending rectangle, without changing it. Work and storage per
    row remain bounded over arbitrarily many changes.
    """

    def __init__(self, start, size):
        self.start = start
        self.rows = [None] * size

    def amount(self, row, t, rate):
        held = self.rows[row]
        start, subtotal = self.start, _ZERO
        if held is not None:
            left, start, old_rate, subtotal = held
            subtotal = _rectangle(left, start, old_rate, subtotal)
        if t < start:
            raise ValueError('transfer requested before its current held interval')
        amount = _rectangle(start, t, rate, subtotal)
        return Fraction(amount) if amount else ZERO_AMOUNT

    def change(self, row, t, previous_rate):
        held = self.rows[row]
        if held is None:
            if t != self.start:
                self.rows[row] = self.start, t, previous_rate, _ZERO
            return
        left, start, old_rate, subtotal = held
        if t != start:
            subtotal = _rectangle(left, start, old_rate, subtotal)
            self.rows[row] = start, t, previous_rate, subtotal

    def closed(self):
        for row, held in enumerate(self.rows):
            if held is not None:
                left, right, rate, subtotal = held
                yield row, right, Fraction(_rectangle(left, right, rate, subtotal))

    def restore(self, row, t, amount):
        subtotal = _HELD_CONTEXT.divide(Decimal(amount.numerator), Decimal(amount.denominator))
        self.rows[row] = t, t, 0, subtotal


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
        self.start = start
        self.clocks = {}
        self.all_clock = False
        self.absolute_rates = None
        self.through = start
        self.total = 0.0 if single is not None else np.zeros(rows)
        self.remainder = 0.0 if single is not None else np.zeros(rows)

    def tolerances(self, run, names):
        if self.absolute_rates is None:
            self.absolute_rates = np.array(
                [run.plan.numerics.atol_factor * run.own_scale(name) for name in names]
            )
        return self.absolute_rates

    def clock_legs(self, names, places, plan, values):
        for row, name in enumerate(names):
            flow = plan.flows.get(name)
            if flow is None or flow.kind != 'directed' or name in plan.solved_flows:
                continue
            polynomial = direct_clock_primitive(flow, plan)
            if polynomial is None and flow.capacity is None and flow.request in values:
                ends = (flow.source, 'outflow'), (flow.sink, 'inflow')
                if plan.values[flow.request].kind == 'capture' and not any(
                    key in plan.ends and plan.settled(plan.ends[key]) for key in ends
                ):
                    polynomial = (0, rational(values[flow.request]))
            if polynomial is not None:
                self.clocks[row] = ClockLeg.of(polynomial, self.through, flow, places, plan)
        self.all_clock = bool(self.clocks) and len(self.clocks) == len(names)

    def held_solution(self, rates, t):
        """The installed solver has a fixed problem between bound changes. Use its
        actual delivered rates, including every binding capacity and declared relation."""
        for row, rate in enumerate(rates):
            polynomial = (0, rational(rate))
            previous = self.clocks.get(row)
            if (
                previous is not None
                and previous.source is None
                and previous.sink is None
                and previous.polynomial == polynomial
            ):
                continue
            total = self.amount(row)
            leg = self.clocks[row] = ClockLeg(polynomial, t, None, None, False, False)
            leg.closed = total
        self.all_clock = bool(self.clocks)

    def select_clocks(self, lower, upper):
        for row, leg in self.clocks.items():
            mode = leg.selection(lower, upper)
            if leg.mode != mode:
                leg.change(self.through, mode, self.numerical(row))

    def amount(self, row):
        leg = self.clocks.get(row)
        if leg is not None:
            return leg.amount(self.through, self.numerical(row) if leg.mode == leg.ALLOCATED else 0)
        return self.numerical(row)

    def prefix(self, row, end, mode, interval):
        leg = self.clocks.get(row)
        if leg is None:
            return self.numerical(row, interval())
        previous = self.amount(row)
        if mode == leg.REQUEST:
            return previous + leg.integral(self.through, end)
        if mode == leg.STOPPED:
            return previous
        return previous + (self.numerical(row, interval()) - self.numerical(row))

    def accept(self, start, end, amount):
        if start != self.through or end < start:
            raise ValueError(f'cannot accept transferred amounts over [{start}, {end}] after {self.through}')
        corrected = amount - self.remainder
        total = self.total + corrected
        self.remainder = (total - self.total) - corrected
        self.total, self.through = total, end

    def numerical(self, row, prefix=0):
        total, remainder = self.total, self.remainder
        if self.single is None:
            total, remainder = total[row], remainder[row]
        if prefix:
            corrected = prefix - remainder
            new = total + corrected
            remainder = (new - total) - corrected
            total = new
        return Fraction.from_float(float(total)) - Fraction.from_float(float(remainder))
