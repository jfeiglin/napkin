"""What holds of a structure with the values of its inputs: one resolved run.

`value_facts` gives the diagnostics of a resolved run, and never stops at the first: the bounds, the
initial values, the domains of the arithmetic, the proofs of the crossings, the conservation and the
claims of the outputs. `input_check_failures` serves the checks of a run's inputs. Each function
reads the typed parts of the run (`structure.Resolved`), never a mapping of the builder.

The proofs are conservative: a proof that does not go through rejects the model, and no sampled value
counts as proof. Crossings: a stock that reaches zero through constant flows, a quantity that moves in
one direction only, and a condition on stock faces. Claims: cumulative, nonnegative and lagged outcomes
and quantities, and checks on the state.
"""

from __future__ import annotations

import contextlib
import dataclasses
import itertools
import math
from types import MappingProxyType

from ...core import expr as nodes
from ...distributions import support
from ...expressions import (
    ExpressionError,
    UnitSystem,
    domain_prover,
    evaluate,
    names_in,
    stock_face_dependencies,
)
from ..ir import COUNT, ENTERED, TIME, ModelError, diagnostic
from ..structure import thawed
from .structure import case_path, evolving_parts, lag_delays, topological

# ---- the proofs of the crossings and of the claims ------------------------------------------------------


def _tree(source):
    """The node of an expression of a part that a proof reads: its node, or the node of a number as
    its text reads (`_literal`)."""
    if isinstance(source, nodes.Node):
        return source
    if isinstance(source, (bool, int, float)):
        return _literal(source)
    raise TypeError(f'an expression of a part is a node or a number, not {type(source).__name__}')


def _literal(value):
    """The node of a number or a yes/no as its text (`str`) reads: a number below zero is the
    negation of the number above it, and an infinity or a NaN is the name that its text writes."""
    if isinstance(value, float) and not math.isfinite(value):
        name = nodes.ref('nan' if math.isnan(value) else 'inf')
        return nodes.unary('neg', name) if value < 0 else name
    return nodes.written(value)


# The proofs of the claims make expressions of the expressions of a run: a sum of terms, the
# difference of the two sides of a check, an expression under the guard of its rule. Each is made as
# a node, with the number of characters of the text that the proofs wrote of it before they made
# nodes (`_Made`). The proof of an interval of such an expression applies the limits of size that the
# reading of that text applied (`_readable`), and the proof of a linear form the limit of depth.


class _Made:
    """A node that a proof made of other expressions, and the number of characters of the text that
    the proofs wrote of it."""

    __slots__ = ('length', 'node')

    def __init__(self, node, length):
        self.node, self.length = node, length


def _own(source):
    """The `_Made` of an expression of a part, with its text as a proof wrote it (`str`)."""
    node = _tree(source)
    return _Made(node, len(str(source)))


def _product(coefficient, source):
    """`(coefficient)*(source)`."""
    term = _own(source)
    factor = _literal(coefficient)
    return _Made(nodes.binary('mul', factor, term.node), len(repr(coefficient)) + term.length + 5)


def _change(coefficient, source, name):
    """`(coefficient)*((source)-(name))`: what a step that sets `name` to `source` changes. The proof
    of a linear form reads it, with the limit of depth alone, so it has no length."""
    change = nodes.binary('sub', _tree(source), nodes.ref(name))
    return nodes.binary('mul', _literal(coefficient), change)


def _added(terms):
    """`a + b + c`: the nodes added from the left."""
    total = terms[0]
    for term in terms[1:]:
        total = nodes.binary('add', total, term)
    return total


def _total(terms):
    """The `_Made` of `a + b + c`: the terms added from the left."""
    return _Made(
        _added([term.node for term in terms]), sum(term.length for term in terms) + 3 * (len(terms) - 1)
    )


def _readable(made):
    """The node of a `_Made`, when the limits of size that the reading of its text applied
    (`expr.read`) hold: at most `LONGEST` characters, at most `LARGEST` parts of Python's tree of
    the expression and no deeper than `DEEPEST`. Else the ExpressionError of the limit."""
    if made.length > nodes.LONGEST:
        raise ExpressionError(f'Expression exceeds {nodes.LONGEST} characters')
    nodes.shallow(made.node)
    if nodes.parts(made.node) > nodes.LARGEST:
        raise ExpressionError('Expression exceeds complexity budget')
    return made.node


def transactions(rs):
    """Every flat step a rule can commit: the step of each of its outcomes."""
    for rule in rs.rules.values():
        yield from rule.steps()


def _limits(quantity):
    """(the least, the greatest) that a quantity can be, in its unit: its bounds as they are written,
    with 0 for a stock that has no minimum, and no limit for any other bound that is not there."""
    low, high = quantity.minimum, quantity.maximum
    if low is None:
        low = 0 if quantity.kind == 'stock' else -math.inf
    return low, math.inf if high is None else high


class _Index:
    """What the proofs of the crossings ask of one resolved run again and again, found once: a proof
    for one quantity then reads the flows of that quantity, and not every flow of the run. Each list
    keeps the order of the run's flows and groups."""

    def __init__(self, rs):
        self.zero_stocks = {
            name
            for name, definition in rs.quantities.items()
            if definition.kind == 'stock' and _limits(definition)[0] == 0
        }
        # Proofs read this transaction's effective values, never the authored defaults.
        self.parameters = dict(rs.values)
        self.aliases = {name: value.expr for name, value in rs.computed.items()}
        self.static = self.parameters.keys() | rs.modes.keys()
        self.flows_at, self.by_allocation, self.couplings_of = {}, {}, {}
        for flow_id, flow in rs.flows.items():
            for end in dict.fromkeys((flow.source, flow.target)):
                if end:
                    self.flows_at.setdefault(end, []).append((flow_id, flow))
            if flow.allocation:
                self.by_allocation.setdefault(flow.allocation, []).append(flow)
        for group in rs.coupling.values():
            for flow_id in group.flows:
                self.couplings_of.setdefault(flow_id, []).append(group)


def _index(rs, proof_cache=None):
    """The index of a resolved run. The cache of the proofs of one run keeps it."""
    if proof_cache is None:
        return _Index(rs)
    if ('index',) not in proof_cache:
        proof_cache[('index',)] = _Index(rs)
    return proof_cache[('index',)]


def stock_zero_crossing(rs, when, mode_only, units, proof_cache=None, spread=None, weights=None):
    """Prove finite zero crossings in a conservative piecewise constant network.

    Each face has constant allocated rates. A declining coordinate reaches zero
    with a strictly negative slope; a zero slope leaves it stationary. Every
    stock controlling a face belongs to the same proved conservative closure.
    A rule that changes only modes observes the first boundary crossing without changing mass.
    `when` is the trigger of the rule; `spread` and `weights` are those of `_prover`.
    """
    state = when.var
    index = _index(rs, proof_cache)
    zero_stocks, parameters = index.zero_stocks, index.parameters
    if state not in zero_stocks or when.op != '<=' or not mode_only:
        return None
    try:
        if names_in(when.value) - parameters.keys() or evaluate(when.value, parameters, units) != 0:
            return None
        if proof_cache is not None and state in proof_cache:
            return proof_cache[state]
        aliases, static = index.aliases, index.static
        # Within one structure every proof reads the same values, bounds and aliases, so the cache keeps
        # the prover and what each rate gives (`_rate_facts`) for every crossing of the structure.
        prove = _prover(rs, units, proof_cache, spread, weights)
        closure, pending, visited_flows = set(), {state}, set()
        while pending:
            name = pending.pop()
            if name in closure:
                continue
            closure.add(name)
            derivative = rs.rates.get(name)
            if derivative and (
                names_in(derivative.expr) - parameters.keys()
                or evaluate(derivative.expr, parameters, units) != 0
            ):
                return None
            for flow_id, flow in index.flows_at.get(name, ()):
                if flow_id in visited_flows:
                    continue
                visited_flows.add(flow_id)
                if not flow.source or not flow.target or flow.source not in zero_stocks:
                    return None
                pending.update((flow.source, flow.target))
                expressions = [flow.rate]
                if flow.allocation:
                    group = rs.allocation[flow.allocation]
                    expressions.append(group.capacity)
                    pending.update(
                        endpoint
                        for f in index.by_allocation[flow.allocation]
                        for endpoint in (f.source, f.target)
                        if endpoint
                    )
                for group in index.couplings_of.get(flow_id, ()):
                    pending.update(
                        endpoint
                        for key in group.flows
                        for endpoint in (rs.flows[key].source, rs.flows[key].target)
                        if endpoint
                    )
                for expression in expressions:
                    dependencies = _rate_facts(
                        expression, static, zero_stocks, aliases, parameters, units, prove, proof_cache
                    )
                    if dependencies is None:
                        return None
                    pending.update(dependencies)
        faces = frozenset(closure & zero_stocks)
        if proof_cache is not None:
            proof_cache.update({name: faces for name in faces})
        return faces
    except (ExpressionError, KeyError, TypeError, ValueError):
        return None


def monotone_quantity(rs, var, units, proof_cache=None, spread=None, weights=None):
    """The direction in which a quantity can move between moments: 1 (it never falls), -1 (it never
    rises), or None when no proof holds.

    Between moments a quantity moves only by its own rate and its flows. A flow rate is never negative
    (a negative rate stops the run), so a flow into the quantity can only raise it and a flow out of
    it can only lower it; allocation and coupling scale a flow by a share from 0 to 1, and a bound
    stops the quantity without reversing it. A nondecreasing quantity or a cumulative one never falls:
    the engine stops a run where its rate is negative. So the quantity is monotone when every flow
    that moves it moves it the same way and its own rate is proven, on the declared ranges, to have
    that sign or to be zero. Transfers and boundary corrections happen at moments, where every rule
    is tested. `spread` and `weights` are those of `_prover`."""
    definition = rs.quantities.get(var)
    if definition is None:
        return None
    if definition.kind == 'cumulative':
        return 1
    signs = set()
    index = _index(rs, proof_cache)
    for _, flow in index.flows_at.get(var, ()):
        into, out = flow.target == var, flow.source == var
        if into and out:
            return None
        if into:
            signs.add(1)
        elif out:
            signs.add(-1)
    rate = rs.rates.get(var)
    if rate is not None:
        parameters = index.parameters
        if names_in(rate.expr) <= parameters.keys():
            try:
                value = evaluate(rate.expr, parameters, units)
            except (ExpressionError, TypeError, ValueError):
                return None
            low = high = float(value)
        else:
            try:
                low, high = _prover(rs, units, proof_cache, spread, weights)(_readable(_own(rate.expr)))
            except (ExpressionError, KeyError, TypeError, ValueError):
                return None
        if low < 0 < high:
            return None
        if high > 0:
            signs.add(1)
        elif low < 0:
            signs.add(-1)
    if len(signs) != 1:
        return None
    return signs.pop()


def _prover(rs, units, proof_cache=None, spread=None, weights=None):
    """The domain prover of a structure: its values, the declared ranges of its quantities and its
    computed values as aliases. The cache keeps one per structure. With the rows of a table
    (`_checked`), `spread` has the inputs that differ from row to row, as ranges, and `weights` the
    rows of each class."""
    if proof_cache is not None and ('prover',) in proof_cache:
        return proof_cache[('prover',)]
    parameters = dict(rs.values)
    aliases = {name: value.expr for name, value in rs.computed.items()}
    ranges = {name: (value, value) for name, value in parameters.items()}
    ranges.update(spread or {})
    ranges.update({name: _limits(definition) for name, definition in rs.quantities.items()})
    prove = domain_prover(ranges, units, aliases, weights)
    if proof_cache is not None:
        proof_cache[('prover',)] = prove
    return prove


def _rate_facts(expression, static, zero_stocks, aliases, parameters, units, prove, proof_cache):
    """The stocks whose zero faces a rate reads, or None when the rate is not constant on each face or can
    be negative (`stock_zero_crossing`). The cache keeps the answer for each rate of one structure."""
    key = ('rate', str(expression))
    if proof_cache is not None and key in proof_cache:
        return proof_cache[key]
    try:
        dependencies = stock_face_dependencies(expression, static, zero_stocks, aliases, parameters, units)
        if dependencies is not None and prove(_readable(_own(expression)))[0] < 0:
            dependencies = None
    except (ExpressionError, KeyError, TypeError, ValueError):
        dependencies = None
    if proof_cache is not None:
        proof_cache[key] = dependencies
    return dependencies


def closed_stock_face(rs, expression, faces, parameters, units):
    """Prove the Boolean truth set contains each of its stock-zero limits."""

    aliases = {name: value.expr for name, value in rs.computed.items()}
    needed = set()

    def expand(source):
        for name in names_in(source):
            if name in needed:
                continue
            needed.add(name)
            if name in aliases:
                expand(aliases[name])

    expand(expression)
    stocks = sorted(faces & needed)
    modes = {name: rs.modes[name].values for name in sorted(needed) if name in rs.modes}
    if 2 ** len(stocks) * math.prod(len(values) for values in modes.values()) > 2048:
        return False
    # Every case reads only the needed names, and the alias evaluation order does not depend
    # on the case: derive both once.
    base = {name: parameters[name] for name in needed if name in parameters}
    order, available = [], base.keys() | modes.keys() | set(stocks)
    pending = {name: aliases[name] for name in needed if name in aliases}
    while pending:
        ready = [name for name, source in pending.items() if names_in(source) <= available]
        if not ready:
            return False
        for name in ready:
            order.append((name, pending.pop(name)))
            available.add(name)
    try:
        for choices in itertools.product(*modes.values()):
            truths = {}
            for presence in itertools.product((False, True), repeat=len(stocks)):
                env = {**base, **dict(zip(modes, choices)), **dict(zip(stocks, map(float, presence)))}
                for name, source in order:
                    env[name] = evaluate(source, env, units)
                value = evaluate(expression, env, units)
                if not isinstance(value, bool):
                    return False
                truths[presence] = value
            for presence, value in truths.items():
                if not value:
                    continue
                for i, present in enumerate(presence):
                    if present:
                        zero_face = (*presence[:i], False, *presence[i + 1 :])
                        if not truths[zero_face]:
                            return False
        return True
    except (ExpressionError, TypeError, ValueError, RecursionError):
        return False


def static_values(rs, units):
    """The value of each input of a run, and of each formula that does not move in the run: one that
    reads only inputs and such formulas. The names that a formula reads are found once. With the
    order of the formulas of the structure (`computed_order`: each formula after those that it
    reads) one pass finds them; a structure with no such order takes passes until one finds nothing."""
    found = dict(rs.values)
    formulas = rs.computed
    reads = {name: names_in(definition.expr) for name, definition in formulas.items()}
    order = rs.computed_order
    if len(order) == len(reads) and set(order) == reads.keys():
        for name in order:
            if reads[name] <= found.keys():
                found[name] = evaluate(formulas[name].expr, found, units)
        return found
    pending = dict(reads)
    while pending:
        ready = [name for name, names in pending.items() if names <= found.keys()]
        if not ready:
            break
        for name in ready:
            del pending[name]
            found[name] = evaluate(formulas[name].expr, found, units)
    return found


def quantity_claims(rs, lib, initial_env, ranges, aliases, interval, spread=None, weights=None):
    """Conservative structural proofs for nonnegative and cumulative outputs.

    Returns the diagnostics and the outcomes that are proved cumulative.

    Balanced flows expose exact cancellation of survivor transfers. Positive
    reporting kernels preserve cumulative incidence; incidence minus its delayed
    occurrence is nonnegative pending mass, but need not itself be cumulative.
    `interval(source)` gives the interval of an expression over `ranges`
    (`expressions.domain_prover`). With the rows of a table (`_checked`), `spread` has the inputs
    that differ from row to row, as ranges, and `weights` the rows of each class.
    """

    units = UnitSystem(lib['units'])
    errors = []
    static_env = static_values(rs, units)
    outcome_defs = rs.outcomes
    lag_prefix = '@lag:'
    # With the rows of a table (`_checked`): an input that a column gives does not move in a run,
    # as any input, but it differs from row to row. A part that reads only such inputs and fixed
    # values is one term of a linear form, under this prefix and its text: its interval over the
    # rows bounds it, and it adds nothing to a derivative or to the effect of a step.
    row_prefix = '@row:'
    spread = spread or {}
    still_names = static_env.keys() | spread.keys()

    def still(node):
        return bool(spread) and nodes.names(node) <= still_names

    # The node of each term of a linear form that reads only inputs that differ from row to row, by
    # its key.
    row_nodes = {}

    # The flows of each quantity, and the steps of the rules that move or set each quantity, found
    # once: a proof for an outcome reads those of the quantities that it counts.
    flows_at, steps, steps_at = {}, list(transactions(rs)), {}
    for flow in rs.flows.values():
        for end in dict.fromkeys((flow.target, flow.source)):
            if end is not None:
                flows_at.setdefault(end, []).append(flow)
    for position, step in enumerate(steps):
        touched = [end for t in step.transfer for end in (t.target, t.source)]
        touched += [name for name, value in step.set.items() if value.expr is not None]
        for name in touched:
            steps_at.setdefault(name, set()).add(position)

    def add(left, right, factor=1.0):
        constant = left[0] + factor * right[0]
        coefficients = dict(left[1])
        for name, value in right[1].items():
            coefficients[name] = coefficients.get(name, 0.0) + factor * value
        return constant, {name: value for name, value in coefficients.items() if value != 0}

    def multiply(form, factor):
        return form[0] * factor, {
            name: coefficient * factor for name, coefficient in form[1].items() if coefficient * factor != 0
        }

    def linear(source, seen=frozenset()):
        node = _tree(source)

        def walk(node):
            if nodes.names(node) <= static_env.keys():
                value = evaluate(node, static_env, units)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError('Non-numeric linear quantity')
                return float(value), {}
            if still(node):
                key = row_prefix + nodes.text(node)
                row_nodes[key] = node
                return 0.0, {key: 1.0}
            if isinstance(node, nodes.Call) and node.function == 'sum':
                # A list as one node (the structure of a hybrid core): its members added, each
                # counted once for each row of the class that it stands for.
                total = (0.0, {})
                for member in node.args:
                    count = 1
                    if weights:
                        count = max((weights.get(name, 1) for name in nodes.names(member)), default=1)
                    total = add(total, multiply(walk(member), count))
                return total
            if isinstance(node, nodes.Ref):
                text = node.name
                if text in rs.quantities or text == 't':
                    return 0.0, {text: 1.0}
                if text in outcome_defs and outcome_defs[text].lag is not None:
                    return 0.0, {lag_prefix + text: 1.0}
                if text in aliases and text not in seen:
                    return linear(aliases[text], seen | {text})
                raise ValueError(f'Unresolved quantity {text}')
            if isinstance(node, nodes.Unary) and node.op in ('pos', 'neg'):
                return multiply(walk(node.operand), -1 if node.op == 'neg' else 1)
            if isinstance(node, nodes.Binary):
                left, right = walk(node.left), walk(node.right)
                if node.op == 'add':
                    return add(left, right)
                if node.op == 'sub':
                    return add(left, right, -1)
                if node.op == 'mul':
                    if not left[1]:
                        return multiply(right, left[0])
                    if not right[1]:
                        return multiply(left, right[0])
                if node.op == 'div' and not right[1] and right[0] != 0:
                    return multiply(left, 1 / right[0])
                if node.op == 'pow' and not right[1] and right[0] == 1:
                    return left
            if isinstance(node, nodes.IfElse) and nodes.names(node.test) <= static_env.keys():
                return walk(node.body if evaluate(node.test, static_env, units) else node.orelse)
            raise ValueError('Quantity is outside the supported linear conservation proof')

        return walk(node)

    cumulative_memo = {}

    def cumulative(source, visiting=frozenset()):
        key = str(source)
        if key in cumulative_memo:
            return cumulative_memo[key]
        if key in visiting:
            return False
        visiting = visiting | {key}
        try:
            _constant, coefficients = linear(source)
        except (ValueError, ExpressionError):
            # Sums, min/max and a fixed nonnegative factor preserve monotonicity of their proved
            # operands; a formula stands for its expression.
            node = _tree(source)
            if isinstance(node, nodes.Ref) and node.name in aliases:
                return cumulative(aliases[node.name], visiting)
            if isinstance(node, nodes.Binary) and node.op == 'add':
                return cumulative(node.left, visiting) and cumulative(node.right, visiting)
            if isinstance(node, nodes.Binary) and node.op in ('mul', 'div'):
                sides = (
                    [(node.right, node.left)]
                    if node.op == 'div'
                    else [
                        (node.left, node.right),
                        (node.right, node.left),
                    ]
                )
                for factor, operand in sides:
                    if nodes.names(factor) <= static_env.keys():
                        value = evaluate(factor, static_env, units)
                        if (
                            isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            and (value > 0 if node.op == 'div' else value >= 0)
                        ):
                            return cumulative(operand, visiting)
                    elif still(factor):
                        # A factor that does not move in a run and that has this sign for every row.
                        try:
                            least = interval(_readable(_own(factor)))[0]
                        except ExpressionError:
                            continue
                        if least > 0 if node.op == 'div' else least >= 0:
                            return cumulative(operand, visiting)
                return False
            if isinstance(node, nodes.Call) and node.function in ('min', 'max', 'sum'):
                return all(cumulative(arg, visiting) for arg in node.args)
            return False
        for name, coefficient in list(coefficients.items()):
            if name.startswith(lag_prefix):
                definition = outcome_defs[name[len(lag_prefix) :]]
                if coefficient < 0 or not cumulative(definition.expr, visiting):
                    return False
                try:
                    if lower(linear(definition.expr), visiting | {name}) < 0:
                        return False
                except (ValueError, ExpressionError):
                    return False
        raw = {
            name: value
            for name, value in coefficients.items()
            if not name.startswith((lag_prefix, row_prefix))
        }
        # The proof holds for every run that completes: the engine stops a run in which a flow's rate
        # or a transfer's amount is negative (`Field.rates`, `Scheduler._evaluate`), as an interval
        # often cannot show it. A transfer can only increase the weighted outcome, or cancel exactly
        # when both endpoints are counted.
        # A flow with no end among the counted quantities changes nothing here.
        for flow in {id(flow): flow for name in raw for flow in flows_at.get(name, ())}.values():
            net = raw.get(flow.target, 0.0) - raw.get(flow.source, 0.0)
            if net < 0:
                return False
        derivative_terms = []
        for name, coefficient in raw.items():
            if name == 't':
                derivative_terms.append(_Made(_literal(coefficient), len(str(coefficient))))
            elif name in rs.rates:
                derivative_terms.append(_product(coefficient, rs.rates[name].expr))
        if derivative_terms and not nonnegative_sum(derivative_terms):
            return False
        # So does a step that moves and sets none of them. The others are read in their order.
        for step in (steps[k] for k in sorted(set().union(*(steps_at.get(name, ()) for name in raw)))):
            for transfer in step.transfer:
                if raw.get(transfer.target, 0) - raw.get(transfer.source, 0) < 0:
                    return False
            set_terms = [
                _change(coefficient, step.set[name].expr, name)
                for name, coefficient in raw.items()
                if name in step.set and step.set[name].expr is not None
            ]
            if set_terms:
                try:
                    # Linear simplification removes x from x + impulse - x.
                    changed = linear(nodes.shallow(_added(set_terms)))
                    if lower(changed, visiting) < 0:
                        return False
                except (ValueError, ExpressionError):
                    # x := x + delta with a nonlinear delta: the interval of delta decides.
                    for name, coefficient in raw.items():
                        if name not in step.set or step.set[name].expr is None:
                            continue
                        delta = increment(step.set[name].expr, name)
                        if delta is None:
                            return False
                        try:
                            low, high = interval(_readable(_own(delta)))
                        except ExpressionError:
                            return False
                        if (coefficient > 0 and low < 0) or (coefficient < 0 and high > 0):
                            return False
        cumulative_memo[key] = True
        return True

    def nonnegative_sum(terms):
        """Whether a sum of terms is never negative: each term on its own, as a sum of terms that are
        never negative is never negative, or else the whole sum, whose interval can be tighter."""
        try:
            if all(interval(_readable(term))[0] >= 0 for term in terms):
                return True
        except ExpressionError:
            pass
        try:
            return interval(_readable(_total(terms)))[0] >= 0
        except ExpressionError:
            return False

    def increment(source, name):
        """delta when `source` is `name + delta` (either order), else None."""
        node = _tree(source)
        if isinstance(node, nodes.Binary) and node.op == 'add':
            if nodes.text(node.left) == name:
                return node.right
            if nodes.text(node.right) == name:
                return node.left
        return None

    def lower(form, visiting=frozenset()):
        constant, coefficients = form
        coefficients = dict(coefficients)
        # A negative lagged occurrence can be paired with its undelayed
        # monotone incidence, leaving a nonnegative pending compartment.
        for name, coefficient in list(coefficients.items()):
            if not name.startswith(lag_prefix) or coefficient >= 0:
                continue
            definition = outcome_defs[name[len(lag_prefix) :]]
            if not cumulative(definition.expr, visiting):
                return -math.inf
            try:
                source_form = linear(definition.expr)
            except ValueError:
                return -math.inf
            if lower(source_form, visiting | {name}) < 0:
                return -math.inf
            del coefficients[name]
            constant, coefficients = add((constant, coefficients), source_form, coefficient)
        total = constant
        for name, coefficient in coefficients.items():
            if name.startswith(lag_prefix):
                return -math.inf  # only a lagged term paired with its incidence is bounded
            if name.startswith(row_prefix):
                try:
                    bounds = interval(_readable(_own(row_nodes[name])))
                except ExpressionError:
                    return -math.inf
            else:
                bounds = ranges.get(name, (-math.inf, math.inf))
            bound = bounds[0] if coefficient >= 0 else bounds[1]
            if (
                coefficient >= 0
                and name in rs.quantities
                and name not in visiting
                and cumulative(nodes.ref(name), visiting)
            ):
                bound = max(bound, initial_env[name])
            total += coefficient * bound
        return total

    def always_estimated(name, visiting=frozenset()):
        if name in visiting:
            return False
        definition = outcome_defs[name]
        if definition.status != 'estimated':
            return False
        return definition.expr is not None and all(
            always_estimated(dependency, visiting | {name})
            for dependency in names_in(definition.expr) & outcome_defs.keys()
        )

    def invariant_supported(node):
        """Endpoint assertions are safe only with a structural no-excursion proof.

        Balanced conservation is constant. A monotone scalar comparison cannot
        fail and recover between endpoint checks. Conjunction preserves this
        property; arbitrary Boolean combinations and interior extrema do not.
        """
        if nodes.names(node) <= static_env.keys():
            return True
        if isinstance(node, nodes.BoolOp) and node.op == 'and':
            return all(invariant_supported(child) for child in node.values)
        if not isinstance(node, nodes.Compare) or len(node.ops) != 1:
            return False
        (left, right), op = node.operands, node.ops[0]
        # Absolute conservation-error bounds are two monotone inequalities.
        if isinstance(left, nodes.Call) and left.function == 'abs' and op in ('lt', 'le'):
            return all(
                invariant_supported(nodes.compare([op], [term, right]))
                for term in (left.args[0], nodes.unary('neg', left.args[0]))
            )
        difference = _Made(
            nodes.binary('sub', left, right), len(nodes.text(left)) + len(nodes.text(right)) + 7
        )
        try:
            bounds = interval(_readable(difference))
            if op == 'ne':
                return bounds[1] < 0 or bounds[0] > 0
            if op in ('lt', 'le') and bounds[1] <= (0 if op == 'le' else -math.ulp(0.0)):
                return True
            if op in ('gt', 'ge') and bounds[0] >= (0 if op == 'ge' else math.ulp(0.0)):
                return True
            return cumulative(nodes.shallow(difference.node)) or cumulative(
                nodes.shallow(nodes.unary('neg', difference.node))
            )
        except (ValueError, ExpressionError):
            return False

    for definition in rs.state_checks.values():
        if not invariant_supported(_tree(definition.expr)):
            errors.append(
                diagnostic(
                    'invariant_proof',
                    definition.path,
                    'Continuous invariant needs a bounded, balanced-conservation or monotone comparison proof; unsupported interior excursions cannot be checked only at solver endpoints',
                )
            )

    proven_cumulative = []
    for name, definition in rs.outcomes.items():
        expr = definition.expr
        if expr is None:
            continue
        if definition.nonnegative:
            proved = False
            with contextlib.suppress(ExpressionError):
                proved = interval(_readable(_own(expr)))[0] >= 0
            if not proved:
                with contextlib.suppress(ValueError, ExpressionError):
                    proved = lower(linear(expr)) >= 0
            if not proved:
                errors.append(
                    diagnostic(
                        'nonnegative_proof',
                        f'outcomes/{name}',
                        'Nonnegative annotation is not established by bounds, balanced accounting, or pending incidence',
                    )
                )
        if definition.kind == 'cumulative':
            proved = cumulative(expr)
            if proved and definition.lag is not None:
                try:
                    proved = lower(linear(expr)) >= 0
                except (ValueError, ExpressionError):
                    proved = False
            if proved:
                # A numerical curve alone cannot certify a peak while its
                # declared estimation status may be unknown during the run.
                if always_estimated(name):
                    proven_cumulative.append(name)
            else:
                errors.append(
                    diagnostic(
                        'cumulative_proof',
                        f'outcomes/{name}',
                        'Cumulative annotation requires nondecreasing balanced flows, integrals, and event effects',
                    )
                )
    for name, definition in rs.quantities.items():
        if definition.kind == 'cumulative' and not cumulative(nodes.ref(name)):
            errors.append(
                diagnostic(
                    'cumulative_proof',
                    definition.path,
                    'Nondecreasing state annotation is not established by its flows, derivative, and event effects',
                )
            )
    return errors, proven_cumulative


# ---- the checks of a resolved run -----------------------------------------------------------------------

# The two bounds of a quantity: the key of each in the facts, and the field of each in its part.
BOUNDS = (('min', 'minimum'), ('max', 'maximum'))


def numeric_bound(q, field, values, units):
    """A bound of a quantity (its `minimum` or its `maximum`) in display units, evaluated from
    parameters when written as an expression."""
    bound = getattr(q, field)
    if isinstance(bound, nodes.Node):
        return evaluate(bound, values, units) / units.scale(q.unit)
    return bound


# What the proofs of a run prove, as the keys of a resolved run, in their order.
PROVED = ('proven_zero_stock_faces', 'proven_monotone_crossings', 'proven_cumulative_outcomes')


class Proofs:
    """What the checks of one structure keep from one set of values to the next: a prover of its
    formulas. The next set of values takes it over its own ranges (`intervals.prover`, `over`), and
    the two keep their answers together: a formula or an expression is not proved again when every
    name that it reads has the range that it had in a proof before. The diagnostics and the facts
    are those of checks that keep nothing.

    A caller keeps one for each structure and each library, in one process: it is empty in a copy
    that goes to another process. The caller can also keep with it the typed parts of the structure
    (`typed`), which every check of a resolution reads and every resolved run shares."""

    __slots__ = ('held', 'typed')

    def __init__(self):
        self.held = None, None, None
        self.typed = None

    def __reduce__(self):
        return (Proofs, ())

    def kept(self, aliases, library):
        """The prover that is kept, when it is of these formulas and of this library. A formula is
        its node, and the parts of a structure hold one node for one expression: the formulas of
        two resolutions of one structure are the same."""
        formulas, of, prove = self.held
        return prove if of is library and formulas == aliases else None

    def keep(self, aliases, library, prove):
        self.held = aliases, library, prove


def value_facts(rs, library, rows=None, proofs=None):
    """(the diagnostics of a resolved run, what the checks find of it). `rs` is the typed parts of
    the run (`structure.Resolved`), which cannot change: the caller makes the run with the facts
    (`Resolved.over`).

    The facts: `bounds`, the number of each bound of a quantity that is written as an expression
    (quantity → `min` / `max` → number); and, when the checks reach their proofs, the stocks with a
    proved zero face, the rules whose crossing is proved by a quantity that moves one way, and the
    outcomes that are proved cumulative.

    `rows` is for the structure of a hybrid core, in which one instance stands for each row of a
    class of a table (`model/hybrid.py`): `ranges` (input → (low, high) of its values over the rows
    of its class, in execution units, for each input that a column gives), `starts` (quantity → the
    same of its start, for each start that a column gives) and `weights` (`weights.get(name, 1)`:
    the rows of the class of the instance that `name` is of). The checks then hold for every row:
    each proof is over those ranges, and a sum over a list counts a member once for each row. They
    are conservative: a proof can fail over the range of a class where it holds for each row by
    itself (two columns that go together), and the model is then refused.

    `proofs` is what the caller keeps for this structure from one set of values to the next
    (`Proofs`); it changes no diagnostic and no fact."""
    facts = {'bounds': {}}
    return _checked(rs, library, facts, rows, proofs), facts


def _checked(rs, library, facts, rows=None, proofs=None):
    units = UnitSystem(library['units'])
    errors = []
    spread, weights = {}, None
    values = dict(rs.values)
    if rows is not None:
        # An input that differs from row to row is no fixed value of the run. Every proof reads the
        # fixed values through the values of the run, so the input is taken out of them: an
        # expression that reads it goes to the interval prover, which has its range, or it has no
        # proof.
        spread = {name: pair for name, pair in rows['ranges'].items() if pair[0] != pair[1]}
        same = {name: pair[0] for name, pair in rows['ranges'].items() if pair[0] == pair[1]}
        weights = rows['weights']
        kept = {name: value for name, value in values.items() if name not in spread}
        values = {**kept, **same}
    # The checks below read each bound as a number: they read a copy of the run whose quantities
    # have them.
    quantities = {}
    for qid, written in rs.quantities.items():
        numbers = {}
        for key, field in BOUNDS:
            bound = getattr(written, field)
            if not isinstance(bound, nodes.Node):
                continue
            if names_in(bound) & spread.keys():
                errors.append(
                    diagnostic(
                        'bounds',
                        f'{written.path}/{key}',
                        'The bound reads a value that a column of a table gives: the rows of one '
                        'class have one bound',
                    )
                )
                continue
            try:
                numbers[field] = numeric_bound(written, field, values, units)
            except ExpressionError as exc:
                errors.append(diagnostic('bounds', f'{written.path}/{key}', exc))
                continue
            facts['bounds'].setdefault(qid, {})[key] = numbers[field]
        q = quantities[qid] = written.changed(**numbers) if numbers else written
        low, high = q.minimum, q.maximum
        if isinstance(low, (int, float)) and isinstance(high, (int, float)) and low > high:
            errors.append(diagnostic('bounds', q.path, f'The minimum {low:g} is above the maximum {high:g}'))
    if errors:
        return errors  # every check below reads each bound as a number
    rs = dataclasses.replace(rs, values=MappingProxyType(values), quantities=MappingProxyType(quantities))
    env = dict(values)
    env['t'] = 0.0
    env.update({mid: mode.initial for mid, mode in rs.modes.items()})
    env.update({mid + ENTERED: 0.0 for mid in rs.modes})
    env.update({e + COUNT: 0 for e in rs.events})
    env.update({e + TIME: 0.0 for e in rs.events})
    try:
        order = initial_order(rs)
    except ModelError as exc:
        return exc.diagnostics
    at = {}  # with rows: the interval of the start of each name that has no one number there
    if rows is None:
        try:
            for i, expr in enumerate(rs.time.timescales or ()):
                if evaluate(expr, env, units) <= 0:
                    errors.append(
                        diagnostic(
                            'timescale',
                            f'time/timescales/{i}',
                            'Physical timescale must be strictly positive',
                        )
                    )
            for name in order:
                quantity = rs.quantities.get(name)
                source = quantity.initial if quantity is not None else rs.computed[name].expr
                env[name] = evaluate(source, env, units)
                if quantity is not None:
                    scale = units.scale(quantity.unit)
                    low, high = _limits(quantity)
                    if env[name] < low * scale or env[name] > high * scale:
                        errors.append(
                            diagnostic('initial_bound', quantity.path, 'Initial value violates its bounds')
                        )
            for name, outcome in rs.outcomes.items():
                lag = outcome.lag
                if lag is None:
                    continue
                delays = [evaluate(expr, env, units) for expr in lag_delays(lag)]
                if any(d < 0 for d in delays) or (lag.type == 'uniform' and delays[0] > delays[1]):
                    errors.append(
                        diagnostic('lag', f'outcomes/{name}', 'Delays require nonnegative, ordered values')
                    )
        except ExpressionError as exc:
            errors.append(diagnostic('initial_expression', '', exc))
    else:
        at = _starts_over_rows(rs, env, order, units, rows, spread, errors)
    ranges = {key: (value, value) for key, value in values.items()}
    ranges.update(spread)
    ranges['t'] = (0.0, float(rs.time.horizon))
    for qid, q in rs.quantities.items():
        scale = units.scale(q.unit)
        low, high = _limits(q)
        ranges[qid] = (low * scale, high * scale)
    aliases = {cid: c.expr for cid, c in rs.computed.items()}
    aliases.update({name: o.expr for name, o in rs.outcomes.items() if o.expr is not None and o.lag is None})
    ranges.update({name: (0.0, math.inf) for name, o in rs.outcomes.items() if o.lag is not None})
    # One prover for every expression of the run. The ranges of the values that events read and of
    # the held quantities are found with it first: each step takes it over the ranges of the step
    # (`over`), and what it found of a formula holds wherever the formula reads the same ranges.
    # A prover that the caller keeps from other values of this structure is where it starts.
    if rows is not None:
        proofs = None  # the weights of the rows are a part of a prover
    kept = None if proofs is None else proofs.kept(aliases, library)
    first = _extra_ranges(rs, ranges, values, units, aliases, weights, kept)
    prove = held_ranges(rs, ranges, {**env, **at}, units, aliases, weights=weights, prove=first)
    if proofs is not None:
        proofs.keep(aliases, library, prove)
    dynamic = (
        *((part, part.expr) for part in rs.computed.values()),
        *((part, part.expr) for part in rs.rates.values()),
        *((part, part.rate) for part in rs.flows.values()),
        *((part, part.capacity) for part in rs.allocation.values()),
    )
    for part, source in dynamic:
        try:
            prove(_readable(_own(source)))
        except ExpressionError as exc:
            errors.append(diagnostic('dynamic_domain', part.path, exc))
    for name, outcome in rs.outcomes.items():
        if outcome.expr is not None:
            try:
                prove(_readable(_own(outcome.expr)))
            except ExpressionError as exc:
                errors.append(diagnostic('output_domain', f'outcomes/{name}/expr', exc))
    for label in rs.labels.values():
        for i, case in enumerate(label.cases):
            try:
                prove(_readable(_own(case.when)))
            except ExpressionError as exc:
                errors.append(diagnostic('label_domain', f'{case_path(case.path, label.path, i)}/when', exc))
    for item in rs.state_checks.values():
        try:
            prove(_readable(_own(item.expr)))
        except ExpressionError as exc:
            errors.append(diagnostic('check_domain', item.path, exc))
    for partition in rs.partitions.values():
        for key, source in (('total', partition.total), ('tolerance', partition.tolerance)):
            if source:
                try:
                    prove(_readable(_own(source)))
                except ExpressionError as exc:
                    errors.append(diagnostic('check_domain', f'{partition.path}/{key}', exc))
    for code, where, made in _rule_expressions(rs):
        try:
            prove(_readable(made))
        except ExpressionError as exc:
            errors.append(diagnostic(code, where, exc))
    if rows is None:
        errors.extend(_crossing_errors(rs, units, facts))
        if not errors:
            found, facts['proven_cumulative_outcomes'] = quantity_claims(
                rs, library, env, ranges, aliases, prove
            )
            errors.extend(found)
        return errors
    # With rows: a quantity that never falls is at or above the least of its starts over the rows.
    lows = {**env, **{name: pair[0] for name, pair in at.items()}}
    try:
        errors.extend(_crossing_errors(rs, units, facts, spread, weights))
        if not errors:
            found, facts['proven_cumulative_outcomes'] = quantity_claims(
                rs, library, lows, ranges, aliases, prove, spread, weights
            )
            errors.extend(found)
    except (ExpressionError, KeyError, TypeError, ValueError) as problem:
        # A proof asked for the one value of an input that has a range over the rows.
        errors.append(
            diagnostic('rows', '', f'A proof of the run needs one value where the rows differ: {problem}')
        )
    return errors


def _starts_over_rows(rs, env, order, units, rows, spread, errors):
    """The start of a run of a structure with the rows of a table (`_checked` with `rows`), for every
    row of each class. A name whose value at the start is one number for every row goes into `env`,
    as in a model with no table. The others get the interval of their start over the rows, which is
    returned: an input that a column gives has the range of the column (`spread`), a start that a
    column gives has the range of that column, and an expression that reads one of these, or that
    adds over a list, has the interval that the prover gives it, with a member of a list counted
    once for each row of its class.

    The checks of the start hold over those intervals: each timescale above zero, each start inside
    its bounds, and the delays of a lag at or above zero and in their order."""
    weights = rows['weights']
    at = dict(spread)

    def value(source):
        """One number, or the interval over the rows."""
        if not isinstance(source, nodes.Node):
            return evaluate(source, env, units)
        adds = any(isinstance(part, nodes.Call) and part.function == 'sum' for part in nodes.walk(source))
        if not adds and not nodes.names(source) & at.keys():
            return evaluate(source, env, units)
        numbers = {
            name: (float(found), float(found))
            for name, found in env.items()
            if isinstance(found, (int, float))
        }
        low, high = domain_prover({**numbers, **at}, units, {}, weights)(_readable(_own(source)))
        return low if low == high else (low, high)

    def pair(found):
        return found if isinstance(found, tuple) else (found, found)

    try:
        for i, expr in enumerate(rs.time.timescales or ()):
            if pair(value(expr))[0] <= 0:
                errors.append(
                    diagnostic(
                        'timescale', f'time/timescales/{i}', 'Physical timescale must be strictly positive'
                    )
                )
        for name in order:
            quantity = rs.quantities.get(name)
            given = rows['starts'].get(name)
            if given is not None:
                found = given[0] if given[0] == given[1] else tuple(given)
            else:
                found = value(quantity.initial if quantity is not None else rs.computed[name].expr)
            if isinstance(found, tuple):
                at[name] = found
            else:
                env[name] = found
            if quantity is not None:
                scale = units.scale(quantity.unit)
                low, high = _limits(quantity)
                least, most = pair(found)
                if least < low * scale or most > high * scale:
                    errors.append(
                        diagnostic('initial_bound', quantity.path, 'Initial value violates its bounds')
                    )
        for name, outcome in rs.outcomes.items():
            lag = outcome.lag
            if lag is None:
                continue
            delays = [pair(value(expr)) for expr in lag_delays(lag)]
            if any(d[0] < 0 for d in delays) or (lag.type == 'uniform' and delays[0][1] > delays[1][0]):
                errors.append(
                    diagnostic('lag', f'outcomes/{name}', 'Delays require nonnegative, ordered values')
                )
    except ExpressionError as exc:
        errors.append(diagnostic('initial_expression', '', exc))
    return at


def _extra_ranges(rs, ranges, values, units, aliases, weights=None, prove=None):
    """The ranges of the values that events read when they fire: a draw's support when its arguments
    are fixed values of the run (else any number), and a delayed value the range of its value.

    Returns the prover of the formulas of the run over the ranges that it read the delayed values
    in. `prove` is a prover of the same formulas over other ranges, when the caller has one."""
    extras = [item for rule in rs.rules.values() for item in rule.extras or ()]
    for item in extras:
        if item.kind != 'draw':
            continue
        ranges[item.name] = (-math.inf, math.inf)
        if all(names_in(source) <= values.keys() for source in item.args.values()):
            try:
                args = {name: float(evaluate(source, values, units)) for name, source in item.args.items()}
                ranges[item.name] = tuple(float(v) for v in support(item.family, args))
            except (ExpressionError, TypeError, ValueError, KeyError):
                pass
    prove = domain_prover(ranges, units, aliases, weights) if prove is None else prove.over(ranges)
    for item in extras:
        if item.kind == 'delayed':
            try:
                ranges[item.name] = prove(_readable(_own(item.expr)))
            except ExpressionError:
                ranges[item.name] = (-math.inf, math.inf)
    return prove


def _rule_expressions(rs):
    """(code, path, expression) of every expression of a rule, under the guards that the engine reads
    before it: a step happens when its trigger holds, and it reads its requirements in order, then
    its values and amounts. Each expression is a `_Made`: an expression of the rule is its node, and
    one under a guard is the `and` of the guard and of the expression."""
    for rid, rule in rs.rules.items():
        path = rule.path or f'rules/{rid}'
        when = rule.trigger.when
        yield 'rule_domain', f'{path}/when', _own(when)
        # The step of an event that fires at once reads its values where its trigger holds; one that
        # waits fires where its trigger may no longer hold.
        guards = [when] if rule.delay is None else []

        def guarded(source):
            value = _own(source)
            if not guards:
                return _Made(value.node, value.length + 2)
            guard = _own(guards[0])
            return _Made(nodes.boolean('and', [guard.node, value.node]), guard.length + value.length + 9)

        def place(own):
            """The place of a part of the rule: its own, or that of the rule."""
            return path if own is None else own

        if rule.delay is not None:
            yield 'rule_domain', place(rule.delay_path), guarded(rule.delay)
        for item in rule.each or ():
            yield 'rule_domain', place(rule.each_path), _own(item)
        for item in rule.extras or ():
            for source in (*(item.args or {}).values(), item.expr, item.delay):
                if source is not None:
                    yield 'rule_domain', path, _own(source)
        if rule.keep:
            yield 'rule_domain', place(rule.keep_path), _own(rule.keep)
        for outcome in rule.outcomes:
            if outcome.chance not in (None, 'else'):
                yield 'rule_domain', f'{outcome.path}/chance', guarded(outcome.chance)
            if outcome.available:
                yield 'rule_domain', f'{outcome.path}/available', guarded(outcome.available)
            step = outcome.do
            for value in step.set.values():
                if value.expr is not None:
                    yield 'rule_domain', value.path or path, guarded(value.expr)
            for transfer in step.transfer:
                yield 'rule_domain', transfer.path or path, guarded(transfer.amount)


def held_ranges(rs, ranges, initial, units, aliases, rounds=12, weights=None, prove=None):
    """Narrow the range of each held quantity (no rate, no flow) to the hull of its initial value
    and every value a rule can assign it, within its declared bounds.

    A bound that moves twice is widened to its declared limit, so accumulators settle. A quantity
    that a transfer moves keeps its declared bounds. An initial value can be an interval (low,
    high): the starts of the rows of a class of a table.

    Returns the prover of the formulas of the run over the ranges as they are at the end. `prove`
    is a prover of the same formulas over other ranges, when the caller has one: each round takes
    it over the ranges of the round (`over`), and proves again only what reads a range that no
    proof before had.
    """
    moved = {end for step in transactions(rs) for t in step.transfer for end in (t.source, t.target)}
    moving = evolving_parts(rs)
    held = [q for q in rs.quantities if q not in moving and q not in moved]
    assigned = {q: [] for q in held}
    for step in transactions(rs):
        for target, value in step.set.items():
            if target in assigned and value.expr is not None:
                assigned[target].append(value.expr)
    declared = {q: ranges[q] for q in held}
    current, moves = {}, {}
    for q in held:
        start = initial.get(q)
        finite = isinstance(start, (int, float)) and not isinstance(start, bool) and math.isfinite(start)
        if isinstance(start, tuple) and all(math.isfinite(end) for end in start):
            current[q] = (max(float(start[0]), declared[q][0]), min(float(start[1]), declared[q][1]))
        else:
            current[q] = (float(start), float(start)) if finite else declared[q]
        moves[q] = [0, 0]
    for _ in range(rounds):
        changed = False
        now = {**ranges, **current}
        prove = domain_prover(now, units, aliases, weights) if prove is None else prove.over(now)
        for q, sources in assigned.items():
            low, high = current[q]
            for source in sources:
                try:
                    a, b = prove(_readable(_own(source)))
                except ExpressionError:
                    a, b = declared[q]
                low, high = min(low, a), max(high, b)
            if low < current[q][0]:
                moves[q][0] += 1
                low = declared[q][0] if moves[q][0] > 1 else low
            if high > current[q][1]:
                moves[q][1] += 1
                high = declared[q][1] if moves[q][1] > 1 else high
            low, high = max(low, declared[q][0]), min(high, declared[q][1])
            if (low, high) != current[q]:
                current[q], changed = (low, high), True
        if not changed:
            ranges.update(current)
            return prove
    # No rest in the rounds: the held quantities keep their declared ranges.
    return domain_prover(ranges, units, aliases, weights) if prove is None else prove.over(ranges)


def initial_order(rs):
    """Evaluation order of initial quantities and computed values, which may read each other at t=0."""
    names = rs.quantities.keys() | rs.computed.keys()
    graph = {name: set(names_in(q.initial)) & names for name, q in rs.quantities.items()}
    graph.update({name: set(names_in(c.expr)) & names for name, c in rs.computed.items()})
    return topological(graph, 'initial_values')


def _crossing_errors(rs, units, facts, spread=None, weights=None):
    """Every level rule on an evolving quantity belongs to a proven crossing class. The stocks with a
    proved zero face and the rules with a proved monotone crossing go into `facts`. `spread` and
    `weights` are those of `_prover`."""
    errors = []
    moving = evolving_parts(rs) | {'t'}
    cache, proven, monotone = {}, set(), set()
    for rule in rs.rules.values():
        trigger = rule.trigger
        if trigger.kind != 'crossing':
            continue
        mode_only = all(
            not any(value.expr for value in step.set.values()) and not step.transfer for step in rule.steps()
        )
        faces = stock_zero_crossing(rs, trigger, mode_only, units, cache, spread, weights)
        if faces is not None:
            proven |= faces
            continue
        var = trigger.var
        index = _index(rs, cache)
        rates = [rs.rates[var].expr] if var in rs.rates else []
        for fid, flow in index.flows_at.get(var, ()):
            rates.append(flow.rate)
            if flow.allocation is not None:
                rates.append(rs.allocation[flow.allocation].capacity)
                rates.extend(m.rate for m in rs.flows.values() if m.allocation == flow.allocation)
            for group in index.couplings_of.get(fid, ()):
                rates.extend(rs.flows[m].rate for m in group.flows)
        # The names through the formulas and the statuses, as the checks of a structure read them.
        if not any(rs.expanded(rate, labels=True) & moving for rate in rates):
            continue
        if monotone_quantity(rs, var, units, cache, spread, weights) is not None:
            monotone.add(rule.id)
            continue
        errors.append(
            diagnostic(
                'unsupported_condition',
                trigger.path,
                'A condition on an evolving quantity needs constant rates in each mode, a quantity that '
                'only rises or only falls between moments, or a stock reaching zero through constant flows',
            )
        )
    for rule in rs.rules.values():
        trigger = rule.trigger
        if trigger.kind != 'face':
            continue
        parameters = dict(rs.values)
        static = parameters.keys() | rs.modes.keys()
        found = stock_face_dependencies(
            trigger.face,
            static,
            proven,
            {c: v.expr for c, v in rs.computed.items()},
            parameters,
            units,
        )
        if not found or not closed_stock_face(rs, trigger.face, set(found), parameters, units):
            errors.append(
                diagnostic(
                    'unsupported_condition',
                    trigger.path,
                    'A condition on stocks must compare a proven stock face with zero, and be true on each of its '
                    'zero limits; to watch one quantity reach a value, compare it by >= or <=',
                )
            )
    facts['proven_zero_stock_faces'] = sorted(proven)
    facts['proven_monotone_crossings'] = sorted(monotone)
    return errors


# ---- the checks of the inputs -------------------------------------------------------------------


def input_check_failures(structure, units, values=None):
    """The failing checks that read only parameters and the computed values built from them.
    `structure` is the typed parts of a structure (`structure.Structure`), and `values` the values
    of the inputs in execution units: by default those of a resolved run."""
    env = dict(structure.values if values is None else values)
    for name in structure.computed_order:
        expression = structure.computed[name].expr
        if names_in(expression) <= env.keys():
            env[name] = evaluate(expression, env, units)
    found = []
    for cid, check in structure.input_checks.items():
        if not evaluate(check.expr, env, units):
            found.append(
                {
                    'code': 'check:' + cid,
                    'severity': 'error' if check.severity == 'block' else 'warning',
                    'message': check.message,
                    'path': check.path,
                    'evidence': thawed(check.basis),
                }
            )
    return found
