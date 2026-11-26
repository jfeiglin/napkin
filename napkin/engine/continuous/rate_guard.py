"""Bound an explicit-time input's departure from its three Radau stage values.

Radau interpolates a quadratic rate through its three collocation points. An
interval bound on its absolute error times the step length also bounds the
amount missed on every prefix. This checks authored requests and capacities.
The solver and physical transfer ledger still decide what can be delivered.
The roundoff of the floating calculation is an estimate (`_roundoff`), not a bound.
"""

from __future__ import annotations

import math
from functools import cache, lru_cache

import numpy as np
from scipy.integrate._ivp.radau import C

from ...core import derivatives, expr, intervals, ops
from ...core.comparisons import against
from ...core.errors import ExpressionError
from ..errors import SimulationError
from ..solvers import retry_shorter
from .transfers import _WEIGHTS

# What a proof can raise when a bound is unavailable.
_UNPROVED = (ExpressionError, ArithmeticError, LookupError, TypeError, ValueError, RecursionError)
# The most halvings of a step's proof cell before the guard retries the physical step.
DEPTH = 4


def _bind(run, name, definition, fixed, aliases, operands, sides):
    """Inline time formulas. Evaluate fixed inputs once on this installation.

    `sides` gets each node that the rate reads as a side of a switch: a side of a comparison, an
    argument of a call. `operands` gets the bound node of such a side, when it can be bound.

    A fixed part can have no value on a branch that the run does not take. Such a part keeps its
    operation and binds its own parts, so that a proof fails only where it reads that branch. A name
    with no value has no range: the prover reads it as any number."""

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
                try:
                    found = value(ref)
                except (*_UNPROVED, SimulationError):
                    continue
                fixed[read] = (found, found)
        if isinstance(part, expr.Compare):
            sides.update(part.operands)
            for arg in part.operands:
                operands[arg] = bind(arg)
        elif isinstance(part, expr.Call):
            sides.update(part.args)
            for arg in part.args:
                try:
                    operands[arg] = bind(arg)
                except (*_UNPROVED, SimulationError):
                    pass  # the prover reads the test through its names
        return part

    @lru_cache(None)
    def bind(part):
        if not moving(part):
            try:
                found = value(part)
            except (*_UNPROVED, SimulationError):
                if not part.children:
                    return part
            else:
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

        found = expr.made(type(part), *(bound(getattr(part, field)) for field in part.FIELDS))
        if isinstance(part, expr.Compare):
            sides.update(part.operands)
            operands.update(zip(part.operands, found.operands))
        elif isinstance(part, expr.Call):
            sides.update(part.args)
            operands.update(zip(part.args, found.args))
        return found

    return bind(expr.ref(name))


def _roundoff(node, bound, time_size):
    """Estimate the rounding of a floating calculation of `node`: propagate each operation's
    rounding through the range of its partial derivatives. This is an estimate, not a bound."""

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


class _Ranges:
    """The intervals of the arguments of one operation on a cell (`ops.Operation.active`). Each is
    proved when it is first read. A yes/no has the interval of `1 if it holds else 0`. An argument
    that the prover cannot bound can be any number."""

    def __init__(self, parts, bound):
        self.parts, self.bound, self.found = parts, bound, {}

    def __len__(self):
        return len(self.parts)

    def __getitem__(self, index):
        if index not in self.found:
            part = self.parts[index]
            operation = ops.OPERATIONS.get(ops.operation_of(part))
            if operation is not None and operation.kinks == ops.STEP:
                part = expr.if_else(part, expr.const(1), expr.const(0))
            try:
                self.found[index] = self.bound(part)
            except _UNPROVED:
                self.found[index] = intervals.WHOLE
        return self.found[index]


def _subdivided(error, start, end, allowance):
    """A bound on the error on every prefix of [start, end] as a sum over cells, or None.

    `error(a, b)` bounds the integrated error on the cell [a, b]. A prefix meets its cells, so its
    error is at most the sum of their errors: all cells share the one allowance. Halve the cell with
    the largest error, to DEPTH halvings of the step, until the sum fits."""
    middle = start + (end - start) / 2
    cells = [(error(start, middle), start, middle, 1), (error(middle, end), middle, end, 1)]
    while (total := math.fsum(cell[0] for cell in cells)) > allowance:
        # Stop when the cells cannot fit even if each halving left halves their errors. This only
        # saves work: the step is then retried. A cell with no finite bound yet can still fit.
        hoped = (
            size / 2 ** (DEPTH - depth) for size, _, _, depth in cells if size < math.inf or depth == DEPTH
        )
        if math.fsum(hoped) > allowance:
            return None
        worst = max(cell for cell in cells if cell[3] < DEPTH)
        cells.remove(worst)
        _, a, b, depth = worst
        middle = a + (b - a) / 2
        cells += [(error(a, middle), a, middle, depth + 1), (error(middle, b), middle, b, depth + 1)]
    return total


def _stage_range(stages, a, b):
    """The range on [a, b] (fractions of the step) of the quadratic through rates in the three stage
    intervals. It is the range of the quadratic through their middles, widened by their half-widths
    times the sum of the absolute Lagrange basis values (below 5), and by its own rounding."""
    middles = [low + (high - low) / 2 for low, high in stages]
    c0, c1, c2 = (_WEIGHTS @ middles).tolist()
    points = [a, b]
    if c2 and a < -c1 / (2 * c2) < b:
        points.append(-c1 / (2 * c2))
    values = [c0 + x * (c1 + x * c2) for x in points]
    spread = 2.5 * max(high - low for low, high in stages)
    spread += 16 * math.ulp(1.0) * float(np.sum(np.abs(_WEIGHTS) @ np.abs(middles)))
    if not all(map(math.isfinite, (*values, spread))):
        return intervals.WHOLE
    return min(values) - spread, max(values) + spread


def _shorter_step(start, end):
    """The retry size, or None when Radau cannot take a shorter physical step."""
    minimum = 10 * (math.nextafter(start, end) - start)  # Radau._step_impl
    if start + minimum >= end:
        return None
    return max(minimum, (end - start) / 2)


class RateGuard:
    """Check the rates of a trial step. The guard of the arm that the solver uses can also check the
    authored rates (`authored`, on the branches of `switches`, by `holding`): see `check`."""

    authored = switches = holding = None

    def __init__(self, run, rates, place, definition):
        self.crossing = run.plan.numerics.crossing
        self.fixed, aliases, self.operands, self.sides = {}, {}, {}, set()
        self.rates = []
        for name, stocks in rates.items():
            rows = tuple(place[stock] for stock in stocks if stock in place)
            if rows:
                try:
                    node = _bind(run, name, definition, self.fixed, aliases, self.operands, self.sides)
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
        """Return an expression differentiable on this whole cell, or None. An operation with kinks
        becomes the piece that it is on this cell (`ops.Operation.active`)."""
        if isinstance(node, (expr.Const, expr.Ref)):
            return node
        operation = ops.OPERATIONS.get(ops.operation_of(node))
        if operation is None:
            return None
        if operation.kinks != ops.SMOOTH:
            found = operation.active(_Ranges(node.children, bound)) if operation.active else None
            if found is None:
                return None
            if found is not ops.ITSELF:
                index, sign = found
                piece = self._smooth(node.children[index], bound)
                return piece if piece is None or sign > 0 else expr.unary('neg', piece)
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

    def holds(self, pair, start, end):
        """Whether the rates read the switch `pair` on its incoming side up to its first root in
        [start, end], or do not read it. The difference of its two sides is then monotone on
        [start, end]: it has one root there at most, which the way locates from the two ends of the
        step, and the committed prefix ends at that root."""
        if not all(node in self.sides or isinstance(node, expr.Const) for node in pair):
            return True
        a, b = (self.operands.get(node, node if isinstance(node, expr.Const) else None) for node in pair)
        if a is None or b is None:
            return False
        prove = self.prove.over({**self.fixed, 't': (start, end)})
        try:
            smooth = self._smooth(expr.binary('sub', a, b), prove)
            if smooth is None:
                return False
            low, high = prove(derivatives.derivative(smooth, 't', memo=self.memo))
        except _UNPROVED:
            return False
        return low >= 0 or high <= 0

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
            # Apply the mean-value theorem to the exact formulas. Add an estimate
            # of the rounding of both floating operands at the trial time.
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
        except _UNPROVED:
            return None

    def _taken(self, node, start, end):
        """The polynomial that the solver took for `node` on [start, end]: intervals of the rate at its
        three stage times, and a function that estimates the rounding of their floating calculation."""
        h = end - start
        times = (start + h * float(C[0]), start + h * float(C[1]), end)
        stages = [self.prove.over({**self.fixed, 't': (at, at)})(node) for at in times]

        def rounding():
            try:
                prove = self.prove.over({**self.fixed, 't': (start, end)})
                return _roundoff(node, prove, max(abs(start), abs(end)))
            except _UNPROVED:
                return math.inf

        return stages, rounding

    def _bounds(self, node, start, end, allowance, taken=None):
        """Bound the integrated error on every prefix in real arithmetic. Then add an estimate of roundoff.

        When the whole step does not fit, bound it on cells of the step (`_subdivided`). A cell has no
        stage times of its own, so the error on a cell is the gap between the ranges of the rate and of
        the polynomial that the solver took over the whole step (`taken()`), times the length of the
        cell. With no `taken`, the whole step must fit."""
        if node is None:
            return math.inf, math.inf
        mathematical, with_roundoff = self._whole(node, start, end, allowance)
        if mathematical <= allowance or taken is None:
            return mathematical, with_roundoff
        duration = end - start
        try:
            stages, rounding = taken()
        except _UNPROVED:
            return mathematical, with_roundoff

        def error(a, b):
            try:
                low, high = self.prove.over({**self.fixed, 't': (a, b)})(node)
            except _UNPROVED:
                return math.inf
            p_low, p_high = _stage_range(stages, (a - start) / duration, (b - start) / duration)
            gap = max(high - p_low, p_high - low)
            return math.nextafter(gap * (b - a), math.inf) if math.isfinite(gap) else math.inf

        found = _subdivided(error, start, end, allowance)
        if found is None:
            return mathematical, with_roundoff
        return found, min(with_roundoff, found + 6 * duration * rounding())

    def _whole(self, node, start, end, allowance):
        """The bounds of `_bounds` from the whole step: its range, else its third derivative."""
        duration = end - start
        prove = self.prove.over({**self.fixed, 't': (start, end)})
        try:
            low, high = prove(node)
        except _UNPROVED:
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
            except _UNPROVED:
                pass  # the range bound still applies when a derivative is unavailable
        return mathematical, with_roundoff

    def check(self, solver, taken=None):
        """Notes on the rates of a trial step, or None to retry it shorter. `taken` gives, by name, the
        polynomial that the solver took for a rate (`_taken`). By default the solver took this guard's
        rates.

        The guard of an arm also checks the authored rates, against the polynomial of the arm. It
        holds each switch that keeps its side up to its first root in the step (`holds`), as the arm
        does: on the committed prefix the authored rate reads that side. It reads any other switch as
        authored. When every switch holds, the authored rates are this arm, and need no check."""
        start, end = solver.t_old, solver.t
        duration = end - start
        own = {
            name: cache(lambda node=node: self._taken(node, start, end))
            for name, node, _ in self.rates
            if node is not None
        }
        taken = own if taken is None else taken
        authored = self.authored
        if authored is not None and all(node is not None for _, node, _ in authored.rates):
            # An authored rate that the guard cannot read is checked as it is.
            held = {pair: sign for pair, sign in self.switches.items() if authored.holds(pair, start, end)}
            authored = self.holding(held)
        notes = authored.check(solver, own) if authored is not None and authored is not self else {}
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
            mathematical, with_roundoff = self._bounds(node, start, end, budget, taken.get(name))
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
