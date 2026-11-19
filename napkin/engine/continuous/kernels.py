"""The segment classifier and the exact kernels: constant-rate (affine) segments and positive linear
compartment segments, solved by their matrix exponential.

The matrix exponential (`expm`) is the scaling and squaring of the [13/13] Pade approximant
(Higham, "The scaling and squaring method for the matrix exponential revisited", 2005), made of
NumPy's products and one solve. SciPy's `expm` gives the same to rounding, but its compiled routine
took 4 to 10 ms for a 4 x 4 matrix where OpenBLAS runs on several threads on a loaded machine (7 us
on one): a linear chain of three compartments, whose record reads the exponential at each point of
each fit, took 9 to 12 s."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...expressions import evaluate, names_in, stock_face_dependencies


# The coefficients of the [13/13] Pade approximant of the exponential, and the largest 1-norm for
# which it holds to double precision (Higham 2005, table 2.3).
_PADE = (
    64764752532480000.0,
    32382376266240000.0,
    7771770303897600.0,
    1187353796428800.0,
    129060195264000.0,
    10559470521600.0,
    670442572800.0,
    33522128640.0,
    1323241920.0,
    40840800.0,
    960960.0,
    16380.0,
    182.0,
    1.0,
)
_THETA = 5.371920351148152


def expm(matrix):
    """The exponential of a square matrix (see the module)."""
    a = np.asarray(matrix, dtype=float)
    norm = float(np.abs(a).sum(axis=0).max()) if a.size else 0.0
    squarings = max(0, math.ceil(math.log2(norm / _THETA))) if norm > _THETA else 0
    a = a / 2.0**squarings
    b, eye = _PADE, np.eye(len(a))
    a2 = a @ a
    a4 = a2 @ a2
    a6 = a2 @ a4
    u = a @ (a6 @ (b[13] * a6 + b[11] * a4 + b[9] * a2) + b[7] * a6 + b[5] * a4 + b[3] * a2 + b[1] * eye)
    v = a6 @ (b[12] * a6 + b[10] * a4 + b[8] * a2) + b[6] * a6 + b[4] * a4 + b[2] * a2 + b[0] * eye
    found = np.linalg.solve(v - u, v + u)
    for _ in range(squarings):
        found = found @ found
    return found


@dataclass
class Segment:
    start: float
    end: float
    solution: Any
    store: dict  # the discrete store throughout the segment


# The closed-form solutions of a segment, as values rather than closures so a record of them pickles.
@dataclass
class Affine:
    start: float
    initial: np.ndarray
    slope: np.ndarray

    def __call__(self, at):
        return self.initial + self.slope * (at - self.start)


@dataclass
class MatrixExponential:
    """The exact solution of a positive linear compartment segment, y' = A y + c from `initial` at
    `start`.

    A quantity whose rate reads no quantity (its row of A is zero) moves on a straight line,
    y + c (t - start). Only the others need the exponential, of the augmented matrix
    [[A, c], [0, 0]] of themselves and the quantities that they read (`columns`, in order of the
    state): the `block`. These quantities read no others, so the block alone gives their values, as
    the exponential of the whole augmented matrix does. `rows` are the places in `columns` of the
    quantities whose rates read quantities.
    """

    start: float
    initial: np.ndarray
    slope: np.ndarray
    columns: np.ndarray
    rows: np.ndarray
    block: np.ndarray

    @classmethod
    def of(cls, matrix, dimension, start, state):
        """The solution from `state` at `start` of the augmented matrix [[A, c], [0, 0]] of a segment."""
        linear, constant = matrix[:dimension, :dimension], matrix[:dimension, dimension]
        moving = np.flatnonzero(np.any(linear != 0, axis=1))
        columns = np.union1d(moving, np.flatnonzero(np.any(linear[moving] != 0, axis=0)))
        block = np.zeros((len(columns) + 1, len(columns) + 1))
        block[:-1, :-1] = linear[np.ix_(columns, columns)]
        block[:-1, -1] = constant[columns]
        return cls(start, state.copy(), constant.copy(), columns, np.searchsorted(columns, moving), block)

    def __call__(self, at):
        elapsed = at - self.start
        state = self.initial + self.slope * elapsed
        if len(self.rows):
            moved = expm(self.block * elapsed) @ np.append(self.initial[self.columns], 1.0)
            state[self.columns[self.rows]] = moved[self.rows]
        return state


class Classifier:
    """What moves in one segment. A rate proven zero in the current discrete mode leaves its
    quantity stationary; an expression that reads only stationary names, or that is constant on
    every stock-zero face, does not move. The classification is syntactic: no probe guesses it."""

    def __init__(self, system, run, environment):
        s = self.system = system
        self.dynamic_dependencies = s.evolving | {'t'}
        self.env = environment(run.time, run.y)  # time and state are fixed for this classification
        self._zero = {}  # valid while dynamic_dependencies is unchanged
        self._face_inputs = None
        y, index, lower = run.y, s.index, s.lower
        # Propagate states proven stationary in the current discrete mode.
        # A state may occur in another expression yet remain constant until the
        # next event; treating every declared derivative as permanently dynamic
        # would turn a five-year inactive tail into 43,800 needless steps.
        blocked_flows = set()
        while True:
            stationary = set()
            for name in self.dynamic_dependencies - {'t'}:
                derivative_def = s.resolved.rates.get(name)
                if derivative_def and not self.proven_zero(derivative_def.expr):
                    continue
                connected = s.flows_of[name]
                if all(key in blocked_flows or self.proven_zero(flow.rate) for key, flow in connected):
                    stationary.add(name)
                elif y[index[name]] == lower[index[name]] and all(
                    key in blocked_flows or self.proven_zero(flow.rate)
                    for key, flow in connected
                    if flow.target == name
                ):
                    # At the lower face, allocation admits no withdrawal without
                    # incoming mass. With zero inflow the coordinate stays fixed.
                    stationary.add(name)
            if not stationary:
                break
            self.dynamic_dependencies -= stationary
            blocked_flows.update(
                key
                for key, flow in s.flows.items()
                if flow.source in stationary and y[index[flow.source]] == lower[index[flow.source]]
            )
            while True:
                coupled_blocked = {
                    name
                    for group in s.couplings.values()
                    if set(group.flows) & blocked_flows
                    for name in group.flows
                }
                if coupled_blocked <= blocked_flows:
                    break
                blocked_flows.update(coupled_blocked)
            # A proof reads the moving names only through the names that its expression reads (its
            # parts and the formulas that it calls read no others), so only a proof whose expression
            # reads a name that has just stopped moving can change.
            self._zero = {
                key: proved
                for key, proved in self._zero.items()
                if s.expanded_frozen(key[0]).isdisjoint(stationary)
            }

    def proven_zero(self, expr, assumptions=frozenset(), seen=frozenset()):
        """Whether an expression (a number or a node) is proved zero in this segment.
        `assumptions` holds the nodes that a branch knows not to be zero."""
        node = nodes.read(expr)
        key = (node, assumptions, seen)
        if key not in self._zero:
            try:
                self._zero[key] = self._proven_zero(node, assumptions, seen)
            except ExpressionError:
                # A fixed part that reads a value with none now (on a side that the rate does not
                # take): nothing is proved.
                self._zero[key] = False
        return self._zero[key]

    def _proven_zero(self, node, assumptions=frozenset(), seen=frozenset()):
        """Prove inactive rates zero while preserving arithmetic domains."""
        s = self.system
        units, index, lower, computed = s.units, s.index, s.lower, s.computed
        env = self.env
        dynamic_dependencies = self.dynamic_dependencies

        def static(n):
            return s.expanded_frozen(n).isdisjoint(dynamic_dependencies)

        def safe(n):
            if isinstance(n, (nodes.Const, nodes.Ref)):
                return True
            if isinstance(n, nodes.Unary):
                return safe(n.operand)
            if isinstance(n, nodes.Binary) and n.op in ('add', 'sub', 'mul'):
                return safe(n.left) and safe(n.right)
            if isinstance(n, nodes.Binary) and n.op == 'div':
                return safe(n.left) and safe(n.right) and fixed_nonzero(n.right)
            if isinstance(n, nodes.Call) and n.function in ('min', 'max', 'abs'):
                return all(safe(a) for a in n.args)
            return static(n)

        def nonnegative(n, visiting=frozenset()):
            if static(n):
                return evaluate(n, env, units) >= 0
            if isinstance(n, nodes.Ref):
                name = n.name
                if name in index:
                    return lower[index[name]] >= 0
                if name in computed and name not in visiting:
                    return nonnegative(nodes.read(computed[name]['expr']), visiting | {name})
            if isinstance(n, nodes.Binary):
                if n.op in ('add', 'mul'):
                    return nonnegative(n.left, visiting) and nonnegative(n.right, visiting)
                if n.op == 'div':
                    return (
                        nonnegative(n.left, visiting)
                        and static(n.right)
                        and evaluate(n.right, env, units) > 0
                    )
            if isinstance(n, nodes.Call):
                if n.function == 'max':
                    return any(nonnegative(a, visiting) for a in n.args)
                if n.function == 'min':
                    return all(nonnegative(a, visiting) for a in n.args)
            if isinstance(n, nodes.IfElse):
                if static(n.test):
                    return nonnegative(n.body if evaluate(n.test, env, units) else n.orelse, visiting)
                return nonnegative(n.body, visiting) and nonnegative(n.orelse, visiting)
            return False

        def fixed_nonzero(n):
            """A denominator fixed in the segment and not zero."""
            return static(n) and evaluate(n, env, units) != 0

        def zero(n, facts):
            if static(n):
                return evaluate(n, env, units) == 0
            if isinstance(n, nodes.Ref):
                name = n.name
                if name in computed and name not in seen:
                    return self.proven_zero(computed[name]['expr'], facts, seen | {name})
                return False
            if isinstance(n, nodes.Unary):
                return zero(n.operand, facts)
            if isinstance(n, nodes.Binary):
                if n.op == 'mul':
                    return (zero(n.left, facts) and safe(n.right)) or (zero(n.right, facts) and safe(n.left))
                if n.op in ('add', 'sub'):
                    return zero(n.left, facts) and zero(n.right, facts)
                if n.op == 'div':
                    nonzero = n.right in facts or fixed_nonzero(n.right)
                    return nonzero and zero(n.left, facts)
            if isinstance(n, nodes.IfElse):
                if static(n.test):
                    return zero(n.body if evaluate(n.test, env, units) else n.orelse, facts)
                body_facts = set(facts)
                test = n.test
                if (
                    isinstance(test, nodes.Compare)
                    and len(test.ops) == 1
                    and test.ops[0] in ('gt', 'lt', 'ne')
                    and static(test.operands[1])
                    and evaluate(test.operands[1], env, units) == 0
                ):
                    body_facts.add(test.operands[0])
                return zero(n.body, frozenset(body_facts)) and zero(n.orelse, facts)
            if isinstance(n, nodes.Call) and n.function == 'min':
                return any(zero(a, facts) for a in n.args) and all(nonnegative(a) for a in n.args)
            if isinstance(n, nodes.Call) and n.function == 'max':
                return all(zero(a, facts) for a in n.args)
            return False

        return zero(node, assumptions)

    def on_faces(self, expr):
        """Whether ``expr`` is proved constant on every stock-zero face in this segment."""
        s = self.system
        if self._face_inputs is None:
            parameters = {name: self.env[name] for name in s.resolved.parameters}
            self._face_inputs = (frozenset(self.env), parameters, tuple(parameters.items()))
        names, parameters, parameter_key = self._face_inputs
        key = (nodes.read(expr), frozenset(self.dynamic_dependencies), names, parameter_key)
        if key not in s.face_proofs:
            s.face_proofs[key] = stock_face_dependencies(
                expr,
                set(names) - self.dynamic_dependencies - set(s.computed),
                set(s.proven_faces),
                {name: signal['expr'] for name, signal in s.computed.items()},
                parameters,
                s.units,
            )
        return s.face_proofs[key] is not None

    def dynamic(self, expr, seen=None):
        """Whether ``expr`` can change between moments in this segment."""
        s = self.system
        if self.proven_zero(expr):
            return False
        if s.proven_faces and self.on_faces(expr):
            return False
        seen = set(seen or ())
        for name in names_in(expr):
            if name in self.dynamic_dependencies:
                return True
            if (
                name in s.computed
                and name not in seen
                and self.dynamic(s.computed[name]['expr'], seen | {name})
            ):
                return True
        return False


def affine_segment(system, run, classifier, departures, derivative, descriptors, end, environment):
    """The constant-rate solution up to the first bound or threshold crossing, or None when a rate,
    capacity or watched threshold moves within the segment.

    Returns the segment end, the solution, the bounds that the solution reaches at that end and the
    watched level rules whose crossing is at that end.
    """
    s, y, time = system, run.y, run.time
    if (
        departures
        or not all(not classifier.dynamic(d.expr) for d in s.resolved.rates.values())
        or not all(not classifier.dynamic(f.rate) for f in s.flows.values())
        or not all(not classifier.dynamic(g.capacity) for g in s.groups.values())
    ):
        return None
    stops = []
    exact_targets = []
    crossings = []
    for kind, desc in descriptors:
        if kind == 'bound':
            i, bound = desc
            limit = s.lower[i] if bound == 'min' else s.upper[i]
            if derivative[i] != 0:
                crossing = time + (limit - y[i]) / derivative[i]
                desired_sign = -1 if bound == 'min' else 1
                if derivative[i] * desired_sign > 0 and crossing > time:
                    stops.append(crossing)
                    exact_targets.append((crossing, i, limit))
        elif kind == 'event':
            cond = run.guards[desc]
            i = s.index[cond['var']]
            if classifier.dynamic(cond['value']):
                return None
            threshold = float(evaluate(cond['value'], environment(time, y), s.units))
            if derivative[i] != 0:
                crossing = time + (threshold - y[i]) / derivative[i]
                desired_sign = 1 if cond['op'] == '>=' else -1
                if derivative[i] * desired_sign > 0 and crossing > time:
                    stops.append(crossing)
                    crossings.append((crossing, desc))
    end = min([end] + [stop for stop in stops if stop <= end])
    targets = {i: limit for at, i, limit in exact_targets if abs(at - end) <= s.cfg.crossing}
    due = [desc for at, desc in crossings if abs(at - end) <= s.cfg.crossing]
    return end, Affine(time, y.copy(), derivative.copy()), targets, due


def repayment_shapes(system):
    """Each `min(debt / a, max(zero, cash - floor) / b)` of a formula, with two different quantities
    for the debt and the cash, in the order of the formulas: (node, debt, cash, [zero, floor, a, b]).
    These are the possible arms of a coupled repayment (`compartment_solution`). They read only the
    run's expressions, so a run finds them once.
    """
    s = system
    if 'repayment' in s.analysis:
        return s.analysis['repayment']
    shapes = []
    for signal in s.computed.values():
        for node in nodes.breadth_first(nodes.read(signal['expr'])):
            if not (isinstance(node, nodes.Call) and node.function == 'min' and len(node.args) == 2):
                continue
            left, right = node.args
            if not (
                isinstance(left, nodes.Binary)
                and left.op == 'div'
                and isinstance(right, nodes.Binary)
                and right.op == 'div'
            ):
                continue
            debt = nodes.text(left.left)
            if debt not in s.index:
                continue
            cash_arm = right.left
            if not (
                isinstance(cash_arm, nodes.Call) and cash_arm.function == 'max' and len(cash_arm.args) == 2
            ):
                continue
            zero, excess = cash_arm.args
            if not (isinstance(excess, nodes.Binary) and excess.op == 'sub'):
                continue
            cash = nodes.text(excess.left)
            if cash not in s.index or debt == cash:
                continue
            shapes.append((node, debt, cash, [zero, excess.right, left.right, right.right]))
    s.analysis['repayment'] = tuple(shapes)
    return s.analysis['repayment']


def compartment_solution(system, run, field, classifier, departures, end, descriptors):
    """Exact positive linear compartment kernel, established structurally.

    Algebraic extraction preserves live discrete branches. Constant terms
    follow the allocated field; exact coefficient cancellation is used when
    the complete transaction has proved capacity and inward boundary rates.
    Dynamic allocation capacities must equal their complete requested rate.
    Constant caps admit a nonincreasing affine arm. A coupled repayment admits
    debt control while its conservation certificate holds. The aggregate matrix
    preserves the resulting positive compartments for the entire segment.

    Returns the segment end, the solution, the bounds it reaches at that end and the watched level
    rules whose crossing is at that end, or None, with the repayment surfaces found, which a
    numerical segment watches instead.
    """
    s = system
    start, state = run.time, run.y
    units, index, lower, upper, atol = s.units, s.index, s.lower, s.upper, s.atol
    flows, groups, couplings, definitions = s.flows, s.groups, s.couplings, s.quantities
    repayment_surfaces = []
    if departures:
        return None, repayment_surfaces
    proven_zero, dynamic_dependencies = classifier.proven_zero, classifier.dynamic_dependencies
    env = field.environment(start, state)
    face_stocks = set(s.proven_faces)
    aliases = {name: signal['expr'] for name, signal in s.computed.items()}
    parameter_env = {name: env[name] for name in s.resolved.parameters}
    static_names = set(env) - dynamic_dependencies - set(aliases)
    repayment_certificates = {}
    coverage = {}
    decreasing_caps = {}

    def repayment_certificate(debt, cash, constants):
        """Extract a repayment arm for subsequent whole-field certification.

        Equal coupled repayments preserve cash-debt. Other active flows
        increase that difference. With cash-debt>=floor>=0 and a>=b>0,
        the cash arm dominates the debt arm for the entire segment.
        """
        if any(s.expanded_names(n) & dynamic_dependencies for n in constants):
            return None
        z, floor, a, b = [float(evaluate(n, env, units)) for n in constants]
        if z != 0 or floor < 0 or not a >= b > 0:
            return None
        if lower[index[cash]] != 0 or lower[index[debt]] != 0:
            return None
        if math.isfinite(upper[index[cash]]) or math.isfinite(upper[index[debt]]):
            return None
        for name in (cash, debt):
            derivative = s.resolved.rates.get(name)
            if derivative and not proven_zero(derivative.expr):
                return None
        weights = {cash: 1.0, debt: -1.0}
        grouped = {}
        for name, flow in flows.items():
            if proven_zero(flow.rate):
                continue
            weight = weights.get(flow.target, 0) - weights.get(flow.source, 0)
            if not weight:
                continue
            group = next((key for key, g in couplings.items() if name in g.flows), name)
            key = (group, nodes.read(flow.rate))
            grouped[key] = grouped.get(key, 0) + weight
        if any(weight < 0 for weight in grouped.values()):
            return None
        repayment_surfaces.append((cash, debt, floor))
        if state[index[cash]] - state[index[debt]] >= floor:
            coverage[cash] = debt
            return 0.0, {index[debt]: 1 / a}
        return None

    for node, debt, cash, constants in repayment_shapes(s):
        certificate = repayment_certificate(debt, cash, constants)
        if certificate:
            repayment_certificates[node] = certificate

    def face_constant(expr):
        return (
            stock_face_dependencies(expr, static_names, face_stocks, aliases, parameter_env, units)
            is not None
        )

    def linear(expr, visiting=frozenset()):
        """Extract affine coefficients algebraically, preserving each live branch."""
        if proven_zero(expr):
            return 0.0, {}

        def walk(node):
            if not (s.expanded_names(node) & dynamic_dependencies):
                return float(evaluate(node, env, units)), {}
            if isinstance(node, nodes.Ref):
                name = node.name
                if name in aliases and name not in visiting:
                    return linear(aliases[name], visiting | {name})
                if name in index:
                    return 0.0, {index[name]: 1.0}
                return None
            if isinstance(node, nodes.IfElse):
                if not face_constant(node.test):
                    return None
                branch = node.body if evaluate(node.test, env, units) else node.orelse
                return walk(branch)
            if isinstance(node, nodes.Unary) and node.op in ('pos', 'neg'):
                value = walk(node.operand)
                if value is None:
                    return None
                sign = -1 if node.op == 'neg' else 1
                return sign * value[0], {k: sign * v for k, v in value[1].items()}
            if isinstance(node, nodes.Binary):
                a, b = walk(node.left), walk(node.right)
                if a is None or b is None:
                    return None
                if node.op in ('add', 'sub'):
                    sign = -1 if node.op == 'sub' else 1
                    keys = a[1].keys() | b[1].keys()
                    return a[0] + sign * b[0], {k: a[1].get(k, 0) + sign * b[1].get(k, 0) for k in keys}
                if node.op == 'mul' and (not a[1] or not b[1]):
                    if a[1]:
                        a, b = b, a
                    return a[0] * b[0], {k: a[0] * v for k, v in b[1].items()}
                if node.op == 'div' and not b[1] and b[0] != 0:
                    return a[0] / b[0], {k: v / b[0] for k, v in a[1].items()}
            certificate = repayment_certificates.get(node)
            if certificate:
                return certificate
            if isinstance(node, nodes.Call) and node.function == 'min' and len(node.args) == 2:
                a, b = walk(node.args[0]), walk(node.args[1])
                if a is not None and b is not None:
                    if b[1] and not a[1]:
                        constant_arm, variable_arm = a, b
                    elif a[1] and not b[1]:
                        constant_arm, variable_arm = b, a
                    else:
                        return None
                    value = variable_arm[0] + sum(v * state[k] for k, v in variable_arm[1].items())
                    if (
                        value <= constant_arm[0]
                        and variable_arm[0] >= 0
                        and all(v >= 0 for v in variable_arm[1].values())
                    ):
                        decreasing_caps[node] = variable_arm
                        return variable_arm
            if face_constant(node):
                return float(evaluate(node, env, units)), {}
            return None

        value = walk(nodes.read(expr))
        if value is None:
            return None
        return value[0], {k: v for k, v in value[1].items() if v != 0}

    dimension = len(state)
    matrix = np.zeros((dimension + 1, dimension + 1))
    nominal_constant = np.zeros(dimension)
    constrained = {s.flow_index[name] for coupling in couplings.values() for name in coupling.flows}
    constrained |= {j for j, f in enumerate(flows.values()) if f.allocation in groups}
    unconstrained = set()
    for gid, group in groups.items():
        members = [f for f in flows.values() if f.allocation == gid and not proven_zero(f.rate)]
        if members and not face_constant(group.capacity):
            forms = [linear(f.rate) for f in members]
            capacity = linear(group.capacity)
            if capacity is None or any(form is None for form in forms):
                return None, repayment_surfaces
            total = (sum(form[0] for form in forms), {})
            for _, coefficients in forms:
                for k, v in coefficients.items():
                    total[1][k] = total[1].get(k, 0) + v
            if capacity != total:
                return None, repayment_surfaces
            unconstrained.update(name for name, f in flows.items() if f.allocation == gid)
    for group in couplings.values():
        members = [name for name in group.flows if not proven_zero(flows[name].rate)]
        forms = [linear(flows[name].rate) for name in members]
        if (
            forms
            and all(
                form is not None and all(v >= 0 for v in form[1].values()) and form[0] >= 0 for form in forms
            )
            and all(
                not (flows[name].allocation is not None and name not in unconstrained) for name in members
            )
        ):
            unconstrained.update(members)
    for j, (name, flow) in enumerate(flows.items()):
        expr = flow.rate
        if proven_zero(expr):
            continue
        form = linear(expr)
        if form is None:
            return None, repayment_surfaces
        constant, coefficients = form
        for endpoint, sign in ((flow.source, -1), (flow.target, 1)):
            if endpoint:
                nominal_constant[index[endpoint]] += sign * constant
        if not coefficients:
            continue
        if j in constrained and name not in unconstrained:
            return None, repayment_surfaces
        source = flow.source
        if source:
            if constant < 0 or any(v < 0 for v in coefficients.values()):
                return None, repayment_surfaces
            if definitions[source].kind == 'cumulative':
                return None, repayment_surfaces
            for column, coefficient in coefficients.items():
                matrix[index[source], column] -= coefficient
                if flow.target:
                    matrix[index[flow.target], column] += coefficient
        else:
            if constant < 0 or any(c < 0 for c in coefficients.values()):
                return None, repayment_surfaces
            if flow.target:
                for column, c in coefficients.items():
                    matrix[index[flow.target], column] += c
    for name, derivative in s.resolved.rates.items():
        if proven_zero(derivative.expr):
            continue
        form = linear(derivative.expr)
        if form is None:
            return None, repayment_surfaces
        constant, coefficients = form
        nominal_constant[index[name]] += constant
        if constant < 0 or any(c < 0 for c in coefficients.values()):
            return None, repayment_surfaces
        for column, c in coefficients.items():
            matrix[index[name], column] += c
    linear_part = matrix[:dimension, :dimension]
    matrix[:dimension, dimension] = field.rates(start, state) - linear_part @ state
    # When all requested linear transactions have proved full capacity and
    # their aggregate field points inward at every zero face, coefficient
    # cancellation supplies the constant term exactly in expression algebra.
    # This keeps a balanced pass-through queue stationary at its zero face.
    nominal_positive = all(
        nominal_constant[i] >= 0
        and all(
            linear_part[i, k] >= 0
            for k in range(dimension)
            if k != i and not (s.state_ids[i] in coverage and k == index[coverage[s.state_ids[i]]])
        )
        for i in range(dimension)
        if np.any(linear_part[i])
    )
    nominal_positive = nominal_positive and all(
        nominal_constant[i] >= 0 if bound == 'min' else nominal_constant[i] <= 0
        for i, bound in run.active_bounds
        if not np.any(linear_part[i])
    )
    if nominal_positive and all(
        s.flow_ids[j] in unconstrained for j in constrained if not proven_zero(flows[s.flow_ids[j]].rate)
    ):
        matrix[:dimension, dimension] = nominal_constant
    for _constant, coefficients in decreasing_caps.values():
        weights = np.zeros(dimension)
        for column, coefficient in coefficients.items():
            weights[column] = coefficient
        slope = weights @ matrix[:dimension]
        # A nonnegative affine rate below its constant cap stays below it
        # when every coefficient of its derivative is nonpositive.
        if np.any(slope > 0):
            # A positive closed ancestor block also preserves a componentwise
            # nonpositive initial velocity: v'=T v and exp(Tt) is positive.
            # Each ancestor stock and therefore this nonnegative affine rate
            # then decreases, even when it receives another declining queue.
            ancestors = set(coefficients)
            pending = list(ancestors)
            while pending:
                i = pending.pop()
                if definitions[s.state_ids[i]].kind != 'stock' or lower[i] != 0:
                    return None, repayment_surfaces
                if matrix[i, dimension] < 0 or any(linear_part[i, k] < 0 for k in range(dimension) if k != i):
                    return None, repayment_surfaces
                for k in np.nonzero(linear_part[i])[0]:
                    if k not in ancestors:
                        ancestors.add(int(k))
                        pending.append(int(k))
            columns = sorted(ancestors)
            initial_velocity = (
                linear_part[np.ix_(columns, columns)] @ state[columns] + matrix[columns, dimension]
            )
            if np.any(initial_velocity > 0):
                return None, repayment_surfaces
    for i in range(dimension):
        row = linear_part[i]
        if not np.any(row):
            continue
        if math.isfinite(upper[i]) or (math.isfinite(lower[i]) and lower[i] != 0):
            return None, repayment_surfaces
        # Positive compartments: nonnegative inputs and off-diagonal couplings keep stocks nonnegative.
        allowed_negative = index[coverage[s.state_ids[i]]] if s.state_ids[i] in coverage else i
        if matrix[i, dimension] < -atol[i] or any(
            row[k] < 0 for k in range(dimension) if k not in (i, allowed_negative)
        ):
            return None, repayment_surfaces
        if definitions[s.state_ids[i]].kind == 'cumulative' and row[i] < 0:
            return None, repayment_surfaces
    exact_targets = []
    crossings = []
    # A clipped boundary allocation stays fixed only while its rows are constant-rate.
    for i, _ in run.active_bounds:
        if np.any(linear_part[i]) and not (
            lower[i] == 0
            and not math.isfinite(upper[i])
            and matrix[i, dimension] >= 0
            and all(linear_part[i, k] >= 0 for k in range(dimension) if k != i)
        ):
            return None, repayment_surfaces
    for kind, desc in descriptors:
        if kind == 'bound':
            i, bound = desc
            # Positive compartments preserve zero lower bounds. Other
            # bounds are eligible only on established constant-rate rows.
            if bound == 'min' and lower[i] == 0 and np.any(matrix[i, :dimension]):
                continue
            slope = matrix[i, dimension]
            target = lower[i] if bound == 'min' else upper[i]
            toward = -1 if bound == 'min' else 1
            if slope * toward > 0:
                crossing = start + (target - state[i]) / slope
                if crossing > start:
                    exact_targets.append((crossing, i, target))
                if start < crossing < end:
                    end = crossing
        elif kind == 'event':
            # Authored affine thresholds may share a model with compartments.
            cond = run.guards[desc]
            i = index[cond['var']]
            if np.any(matrix[i, :dimension]):
                return None, repayment_surfaces
            slope = matrix[i, dimension]
            target = float(evaluate(cond['value'], field.environment(start, state), units))
            if slope:
                crossing = start + (target - state[i]) / slope
                if crossing > start:
                    crossings.append((crossing, desc))
                if start < crossing < end:
                    end = crossing
    targets = {i: target for at, i, target in exact_targets if abs(at - end) <= s.cfg.crossing}
    due = [desc for at, desc in crossings if abs(at - end) <= s.cfg.crossing]
    return (end, MatrixExponential.of(matrix, dimension, start, state), targets, due), repayment_surfaces
