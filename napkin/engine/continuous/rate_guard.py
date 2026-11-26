"""Bound an explicit-time input's departure from its three Radau stage values.

Radau interpolates a quadratic rate through its three collocation points. An
interval bound on its absolute error times the step length also bounds the
amount missed on every prefix. This checks authored requests and capacities.
The solver and physical transfer ledger still decide what can be delivered.
"""

from __future__ import annotations

import math
from functools import lru_cache

from ...core import derivatives, expr, intervals, ops
from ...core.comparisons import against
from ...core.errors import ExpressionError
from ..errors import SimulationError
from ..solvers import retry_shorter


def _bind(run, name, definition, fixed, aliases, operands):
    """Inline time formulas. Evaluate fixed inputs once on this installation."""

    @lru_cache(None)
    def sources(part):
        return run.plan.inputs_now(run.plan.expansion(part))

    def moving(part):
        return sources(part).time

    def value(part):
        # A trial must never execute a draw in a branch the run has not taken.
        # A captured draw is already an ordinary fixed value in this installation.
        if not sources(part).leaves.isdisjoint(run.plan.draws):
            raise ExpressionError('uncaptured draw in a rate input')
        return run.initial(part)

    def predicate(part):
        if not moving(part):
            return expr.const(bool(value(part)))
        if isinstance(part, expr.BoolOp):
            kept = []
            for child in part.values:
                found = predicate(child)
                if isinstance(found, expr.Const):
                    if found.value == (part.op == 'or'):
                        return found  # later tests cannot affect this choice
                else:
                    kept.append(found)
            if not kept:
                return expr.const(part.op == 'and')
            return kept[0] if len(kept) == 1 else expr.boolean(part.op, kept)
        if isinstance(part, expr.Unary) and part.op == 'not':
            found = predicate(part.operand)
            return expr.const(not found.value) if isinstance(found, expr.Const) else expr.unary('not', found)
        # Keep the original comparison: a named operand's declared scale
        # can place the switch far from the mathematical equality. Supply
        # its value through the prover's ordinary ranges and aliases.
        reads = set(expr.names(part))
        if isinstance(part, expr.Compare):
            # Selecting a named operand's scale can read the condition in its
            # definition. Use the same controls as the expression evaluator.
            reads.update(run.plan.units.comparisons.control_names(part.operands))
        for read in sorted(reads - {'t'}):
            ref = expr.ref(read)
            if moving(ref):
                aliases[read] = bind(ref)
            else:
                found = value(ref)
                fixed[read] = (found, found)
        if isinstance(part, expr.Compare):
            for arg in part.operands:
                operands[arg] = bind(arg)
        return part

    @lru_cache(None)
    def bind(part):
        if not moving(part):
            found = value(part)
            return expr.const(found if isinstance(found, (bool, str)) else float(found))
        if isinstance(part, expr.Ref):
            if part.name == 't':
                return part
            replacement = definition(run, part.name)
            if replacement is None:
                raise ExpressionError(f'no expression for {part.name}')
            return bind(replacement)
        if isinstance(part, expr.IfElse):
            test = predicate(part.test)
            if isinstance(test, expr.Const):
                return bind(part.body if test.value else part.orelse)
            return expr.if_else(test, bind(part.body), bind(part.orelse))

        def bound(field):
            if isinstance(field, expr.Node):
                return bind(field)
            return tuple(bound(item) for item in field) if isinstance(field, tuple) else field

        return expr.made(type(part), *(bound(getattr(part, field)) for field in part.FIELDS))

    return bind(expr.ref(name))


def _roundoff(node, bound, time_size):
    """Propagate one operation's rounding through its range of partial derivatives."""

    @lru_cache(None)
    def magnitude(part):
        return max(map(abs, bound(part)))

    @lru_cache(None)
    def propagated(part):
        if isinstance(part, expr.Const):
            return 0.0
        if isinstance(part, expr.Ref):
            # A collocation timestamp is formed by one product and one sum.
            return 2 * math.ulp(time_size)
        op = ops.OPERATIONS[ops.operation_of(part)]
        children = part.children
        result = 2 * math.ulp(magnitude(part))
        if op.name == 'sum':
            result += len(children) * math.ulp(math.fsum(map(magnitude, children)))
        for child, partial in zip(children, op.partials(*children), strict=True):
            source = propagated(child)
            if partial is not None and source:
                result += source * magnitude(partial)
        return result

    return propagated(node)


def _shorter_step(start, end):
    """The retry size, or None when Radau cannot take a shorter physical step."""
    minimum = 10 * (math.nextafter(start, end) - start)  # Radau._step_impl
    if start + minimum >= end:
        return None
    return max(minimum, (end - start) / 2)


class RateGuard:
    authored = None

    def __init__(self, run, rates, place, definition):
        self.crossing = run.plan.numerics.crossing
        self.fixed, aliases, self.operands = {}, {}, {}
        self.rates = []
        for name, stocks in rates.items():
            rows = tuple(place[stock] for stock in stocks if stock in place)
            if rows:
                try:
                    node = _bind(run, name, definition, self.fixed, aliases, self.operands)
                except (
                    ExpressionError,
                    ArithmeticError,
                    LookupError,
                    TypeError,
                    ValueError,
                    SimulationError,
                    RecursionError,
                ):
                    # A fixed input can be unavailable on an untaken time branch.
                    # Preserve the runtime's lazy semantics and mark an unproved trial.
                    node = None
                self.rates.append((name, node, rows))
        self.prove = intervals.prover(self.fixed, run.plan.units, aliases, outward=True, order=self._order)
        # One memo of derivatives by time for this installation, whose expressions do not change.
        # It lives as long as the installation, so a run's sampled parameters are not kept after it.
        self.memo = {}

    def __deepcopy__(self, memo):
        # Checkpoint projections consume only previously prepared dense steps.
        # This installation's bound expressions and certificates are immutable.
        return self

    def _third(self, node):
        derived = node
        for _ in range(3):
            derived = derivatives.derivative(derived, 't', memo=self.memo)
        return derived

    def _smooth(self, node, bound):
        """Return an expression differentiable on this whole cell, or None."""
        if isinstance(node, (expr.Const, expr.Ref)):
            return node
        if isinstance(node, expr.IfElse):
            low, high = bound(expr.if_else(node.test, expr.const(1), expr.const(0)))
            if low <= 0 and high >= 1:
                return None
            return self._smooth(node.body if low > 0 else node.orelse, bound)
        if isinstance(node, expr.Call) and node.function in ('min', 'max') and len(node.args) == 2:
            left, right = node.args
            a, b = bound(left), bound(right)
            if a[1] <= b[0]:
                return self._smooth(left if node.function == 'min' else right, bound)
            if b[1] <= a[0]:
                return self._smooth(right if node.function == 'min' else left, bound)
            return None
        key = ops.operation_of(node)
        if key == 'pow':
            if not isinstance(node.right, expr.Const):
                return None
            exponent = float(node.right.value)
            if not (exponent.is_integer() and exponent >= 0) and bound(node.left)[0] <= 0:
                return None
        elif key == 'sqrt':
            if bound(node.args[0])[0] <= 0:
                return None
        elif key not in ops.OPERATIONS or ops.OPERATIONS[key].kinks != ops.SMOOTH:
            return None
        children = {}
        for child in node.children:
            smooth = self._smooth(child, bound)
            if smooth is None:
                return None
            children[child] = smooth
        if all(child is selected for child, selected in children.items()):
            return node

        def replaced(value):
            if isinstance(value, expr.Node):
                return children[value]
            return tuple(replaced(item) for item in value) if isinstance(value, tuple) else value

        return expr.made(type(node), *(replaced(getattr(node, field)) for field in node.FIELDS))

    def _order(self, op, left, right, time, policy, read):
        """Test two moving operands on the same clock. Keep their correlated change."""
        if not time or left not in self.operands or right not in self.operands:
            return None
        a, b = self.operands[left], self.operands[right]
        start, end = time
        middle = start + (end - start) / 2
        prove = self.prove.over({**self.fixed, 't': time})
        at = self.prove.over({**self.fixed, 't': (middle, middle)})
        try:
            a, b = self._smooth(a, prove), self._smooth(b, prove)
            if a is None or b is None:
                return None
            low, high = policy.band_interval(left, right, prove(a), prove(b), read)
            difference = expr.binary('sub', a, b)
            speed = max(map(abs, prove(derivatives.derivative(difference, 't', memo=self.memo))))
            radius = max(middle - start, end - middle)
            # Apply the mean-value theorem to the exact formulas. Enclose the
            # additional rounding of both floating operands at the trial time.
            rounding = _roundoff(a, prove, max(abs(start), abs(end))) + _roundoff(
                b, prove, max(abs(start), abs(end))
            )
            variation = math.nextafter(speed * radius + rounding, math.inf)
            gap = at(difference)
            lo, hi = (
                math.nextafter(gap[0] - variation, -math.inf),
                math.nextafter(gap[1] + variation, math.inf),
            )
            if not all(map(math.isfinite, (lo, hi, low, high))):
                return None
            results = {against(op, g, w) for g in (lo, hi, min(max(0, lo), hi)) for w in (low, high)}
            return results.pop() if len(results) == 1 else None
        except (ExpressionError, ArithmeticError, LookupError, TypeError, ValueError, RecursionError):
            return None

    def _bounds(self, node, start, end, allowance):
        """Bound the integrated error on every prefix, first in real arithmetic, then with roundoff."""
        if node is None:
            return math.inf, math.inf
        duration = end - start
        prove = self.prove.over({**self.fixed, 't': (start, end)})
        try:
            low, high = prove(node)
        except (ExpressionError, ArithmeticError, LookupError, TypeError, ValueError, RecursionError):
            return math.inf, math.inf
        if not math.isfinite(low) or not math.isfinite(high):
            return math.inf, math.inf
        # On [0,1], the absolute values of the three Radau Lagrange basis
        # polynomials sum to less than 5. Center the range on its midpoint.
        # |rate - interpolant| <= (1 + 5) times the half-width of the range.
        range_error = 3 * (high - low) * duration
        mathematical = with_roundoff = range_error
        if range_error > allowance:
            try:
                smooth = self._smooth(node, prove)
                if smooth is None:
                    return mathematical, with_roundoff
                lower, upper = prove(self._third(smooth))
                # The maximum of |(x-c1)(x-c2)(x-1)| on [0,1] is 1/10.
                # Interpolation remainder = f'''(xi) * h^3 * product / 3!.
                interpolation = max(abs(lower), abs(upper)) * duration**4 / 60
                if interpolation < range_error:
                    mathematical = interpolation
                    # The mathematical formula and its floating stage samples can
                    # differ, especially after cancellation of large operands.
                    rounding = _roundoff(smooth, prove, max(abs(start), abs(end)))
                    with_roundoff = min(range_error, interpolation + 6 * duration * rounding)
            except (ExpressionError, ArithmeticError, LookupError, TypeError, ValueError, RecursionError):
                pass  # the range bound still applies when a derivative is unavailable
        return mathematical, with_roundoff

    def check(self, solver):
        start, end = solver.t_old, solver.t
        duration = end - start
        notes = self.authored.check(solver) if self.authored is not None else {}
        if notes is None:
            return None
        for name, node, rows in self.rates:
            budget = min(
                solver.atol[i] + solver.rtol * max(abs(solver.y[i]), abs(solver.y_old[i])) for i in rows
            )
            if node is None:
                # The guard could not read this rate (`__init__`). A shorter step cannot change that,
                # so the step stands, with a note: a check must not make a correct model fail.
                notes[name] = ('the guard cannot read this rate', float(budget), math.inf, math.inf)
                continue
            mathematical, with_roundoff = self._bounds(node, start, end, budget)
            if with_roundoff <= budget:
                continue
            # A physically selected arm and the authored expression can both
            # lack a certificate for this rate. Keep the bounds covering both.
            if name in notes:
                _, _, previous_math, previous_total = notes[name]
                mathematical = max(mathematical, previous_math)
                with_roundoff = max(with_roundoff, previous_total)
            if mathematical <= budget:
                reason = 'roundoff prevents certification'
            elif duration > self.crossing and _shorter_step(start, end) is not None:
                return None
            else:
                limit = 'crossing tolerance' if duration <= self.crossing else 'minimum solver step'
                reason = f'mathematical error unresolved at the {limit}'
            notes[name] = (reason, float(budget), mathematical, with_roundoff)
        return notes


def step(solver, guard):
    """Take one solver step, retrying a trial whose rate interpolation misses its budget."""
    if guard is None:
        return solver.step()
    original_limit = solver.max_step
    try:
        while True:
            held = dict(vars(solver))
            message = solver.step()
            if solver.status == 'failed':
                return message
            notes = guard.check(solver)
            if notes is not None:
                if notes:
                    solver.dense_output().rate_warnings = notes
                return message
            retry_shorter(solver, held, _shorter_step(solver.t_old, solver.t))
    finally:
        solver.max_step = original_limit


def mark(recorder, solution, start, end):
    """Publish an unresolved cell only when its physical prefix enters the record."""
    steps = getattr(solution, 'interpolants', (solution,))
    for dense in steps:
        notes = getattr(dense, 'rate_warnings', ())
        if not notes:
            continue
        left, right = max(start, dense.t_old), min(end, dense.t)
        if left >= right:
            continue
        for name, (reason, allowance, mathematical, with_roundoff) in notes.items():
            details = dict(start=float(left), end=float(right), tolerance=allowance, reason=reason)
            details['mathematical_bound'] = mathematical if math.isfinite(mathematical) else None
            details['bound_with_roundoff'] = with_roundoff if math.isfinite(with_roundoff) else None
            recorder.entry(end, 'rate_unresolved', name, **details)
