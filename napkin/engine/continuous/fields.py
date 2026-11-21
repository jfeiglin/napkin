"""The allocated vector field of a run: rates, allocation where a bound holds a stock, and the
structural Jacobian pattern."""

from __future__ import annotations

import math

import numpy as np

from ...expressions import ExpressionError, compile_program, evaluate, names_in
from ..allocation import Allocation
from ..errors import SimulationError
from .integrate import branch_expression
from .system import Formulas


def finite(value, where, diagnostics):
    value = float(value)
    if not math.isfinite(value):
        raise SimulationError(f'Nonfinite {where}', diagnostics)
    return value


class Field:
    """The rate of every quantity at one time and state. Requested flow rates are cut to their
    group capacities and coupled fractions, then allocated where an active bound holds a stock."""

    def __init__(self, system, run, context):
        self.system = system
        self.run = run
        self.context = context  # the formulas, the diagnostics and the settings (`system.Context`)
        self.leg_rates = None
        self.paired_requests = None
        self.branches = {}
        self._expressions = {}
        self._program = None
        self._pattern = None
        # The faces change only between segments; their arrays serve every evaluation of a segment.
        self._faces = {}
        self._value_programs = {}  # `values_program`, by its sources
        # What each flow delivers of what it asks: the capacities, the coupled fractions and the
        # active bounds (`engine/allocation.py`).
        self.allocation = Allocation(system)

    def choose(self, signs):
        if signs != self.branches:
            self.branches = signs
            self._expressions.clear()
            self._program = None

    def expression(self, node):
        if not self.branches:
            return node
        if node not in self._expressions:
            self._expressions[node] = branch_expression(node, self.branches)
        return self._expressions[node]

    def environment(self, at, state):
        return self.context.environment(at, state, self.run.store)

    def branch_environment(self, at, state):
        """A root's operands or a slow rate evaluation, with nested formula branches held."""
        if not self.branches:
            return self.environment(at, state)
        context = self.context
        data = {**context.values, **dict(zip(context.states, state)), **self.run.store, 't': at}
        return Formulas(
            data,
            {name: self.expression(node) for name, node in context.order},
            context.missing,
            context.units,
        )

    def operands(self, at, state):
        """Read switch operands, including named formulas, on the installed branches."""
        env = self.branch_environment(at, state)
        return lambda node: float(evaluate(self.expression(node), env, self.system.units))

    def compiled(self, at, state):
        """Every computed value, rate, flow rate and group capacity from one generated program of the
        run: the inputs are literals in it, and it reads the time, the store and the state directly."""
        s = self.system
        if self._program is None:
            outputs = (
                [s.resolved.rates[name].expr for name in s.derivative_ids]
                + [f.rate for f in s.flows.values()]
                + [g.capacity for g in s.groups.values()]
            )
            order = [(name, self.expression(node)) for name, node in self._formulas_for(outputs)]
            outputs = [self.expression(node) for node in outputs]

            def read(name):
                # The state is checked once, before the program runs (below).
                if name in s.index:
                    return f'Y[{s.index[name]}]', True
                return s.read(name)

            try:
                self._program = compile_program(
                    order,
                    outputs,
                    constants=s.known,
                    units=s.units,
                    read=read,
                    arguments=('Y', 'T', 'S', 'V', 'R'),
                    write=False,
                    lean=True,  # a failure goes to the interpreted path, which reports it
                )
            except (SyntaxError, RecursionError, ValueError):
                self._program = False  # a program too deep for Python: the interpreter evaluates each value
        if not self._program or not np.all(np.isfinite(state)):
            return None  # the interpreted path reports a value that is not finite
        try:
            out = np.array(
                self._program(state.tolist(), float(at), self.run.store, s.values, s.units), dtype=float
            )
        except (ArithmeticError, ValueError, TypeError, KeyError):
            return None  # the interpreted path reports the failing expression
        if not np.all(np.isfinite(out)):
            return None
        nd, nf = len(s.derivative_ids), len(s.flows)
        return out[:nd], out[nd : nd + nf].copy(), out[nd + nf :]

    def _formulas_for(self, sources):
        """The formulas that `sources` read, directly or through other formulas, in their order."""
        needed, pending = set(), list(sources)
        computed = dict(self.context.order)
        while pending:
            for name in names_in(pending.pop()):
                if name in computed and name not in needed:
                    needed.add(name)
                    pending.append(computed[name])
        return [(name, source) for name, source in self.context.order if name in needed]

    def values_program(self, sources):
        """`values(at, state)`: the values of `sources` from one generated program that reads the
        time, the store and the state directly and computes only the formulas that they read, with
        the semantics of evaluating them in an environment; None when it cannot be made."""
        s, run = self.system, self.run
        key = (tuple(sources), tuple(self.branches.items()))
        program = self._value_programs.get(key)
        if program is None:
            try:
                program = compile_program(
                    [(name, self.expression(node)) for name, node in self._formulas_for(sources)],
                    list(sources),
                    constants=s.known,
                    units=s.units,
                    read=s.read,
                    arguments=('Y', 'T', 'S', 'V', 'R'),
                    write=False,
                )
            except (SyntaxError, RecursionError, ValueError):
                program = False
            self._value_programs[key] = program
        if not program:
            return None
        return lambda at, state: program(state.tolist(), float(at), run.store, s.values, s.units)

    def _face_arrays(self, key):
        run = self.run
        found = self._faces.get(key)
        if found is None:
            zero = np.array(sorted(run.zero_faces), dtype=int)
            right = np.array(sorted(run.right_faces), dtype=int)
            found = self._faces[key] = (zero, right, np.nextafter(self.system.lower[right], np.inf))
        return found

    def rates(self, at, state, *, trial=False):
        s, run = self.system, self.run
        lower, upper, index, flows, groups = s.lower, s.upper, s.index, s.flows, s.groups
        diagnostics = self.context.diagnostics
        run.evaluations += 1
        if run.evaluations > s.cfg.max_evaluations:
            raise SimulationError('Numerical evaluation budget exceeded', diagnostics)
        # Integrators evaluate rejected internal stages outside the physical
        # domain. Extend the vector field using boundary values for those trial
        # stages only; stored/accepted states are never clipped and are checked.
        trial_state = np.minimum(np.maximum(state, lower), upper)
        # Event-only coordinates remain constant throughout a continuous
        # segment. Jacobian probes obey the same discrete mode as solver stages.
        trial_state[s.discrete_rows] = run.y[s.discrete_rows]
        # The faces and bounds hold through the evaluation; their keys are read once.
        zero_key = frozenset(run.zero_faces)
        zero_faces, right_faces, right_floor = self._face_arrays((zero_key, frozenset(run.right_faces)))
        bound_key = (frozenset(run.active_bounds), zero_key)
        trial_state[zero_faces] = lower[zero_faces]
        trial_state[right_faces] = np.maximum(trial_state[right_faces], right_floor)
        # A switch that the state crosses at the start of the segment is read on its far side while
        # the state is within its tolerance (`integrate.starting_sides`).
        for i, low, high, number in () if self.branches else run.switches:
            if low <= trial_state[i] <= high:
                trial_state[i] = number
        if not self.branches and run.clock is not None and run.clock[0] <= at <= run.clock[1]:
            at = run.clock[2]
        base = np.zeros(len(run.y))
        capacities = self.compiled(at, trial_state)
        if capacities is not None:
            derivative_values, requested, capacities = capacities
            base[s.derivative_rows] += derivative_values
        else:
            # The one-expression path names the failing expression. A failure here is a numerical
            # failure of the run, never a root-location failure to retry with smaller steps.
            try:
                env = self.branch_environment(at, trial_state)
                for name, derivative in s.resolved.rates.items():
                    base[index[name]] += finite(
                        evaluate(self.expression(derivative.expr), env, s.units),
                        f'derivative {name}',
                        diagnostics,
                    )
                requested = np.array(
                    [
                        finite(evaluate(self.expression(f.rate), env, s.units), f'flow {name}', diagnostics)
                        for name, f in flows.items()
                    ]
                )
                capacities = [
                    finite(
                        evaluate(self.expression(g.capacity), env, s.units),
                        f'allocation capacity {gid}',
                        diagnostics,
                    )
                    for gid, g in groups.items()
                ]
            except ExpressionError as exc:
                raise SimulationError(f'Rate evaluation failed at {at:g} h: {exc}', diagnostics) from exc
        # A solver stage beyond a max(0, x) switch can see a negative smooth continuation.
        # Check the authored request at that state. Outside its selected branch the continuation
        # is only an ODE trial; at a located endpoint publish the nonnegative limit.
        extended = False
        if np.any(requested < 0):
            env = self.environment(at, trial_state) if self.branches else None
            bad = []
            for j in np.flatnonzero(requested < 0):
                name = s.flow_ids[j]
                if env is None or evaluate(flows[name].rate, env, s.units) < 0:
                    bad.append(name)
                elif trial:
                    extended = True
                else:
                    requested[j] = 0.0
            if bad:
                raise SimulationError(f'Negative flow rates: {bad}', diagnostics)
        for j, (gid, capacity) in enumerate(zip(groups, capacities)):
            if capacity < 0:
                if (
                    not self.branches
                    or evaluate(groups[gid].capacity, self.environment(at, trial_state), s.units) < 0
                ):
                    raise SimulationError(f'Negative capacity for {gid}')
                capacities[j] = 0.0
        # The rates of the states, and the rates that the flows deliver, after capacities, couplings
        # and bounds.
        if self.paired_requests is not None and run.active_bounds:
            self.paired_requests(at, trial_state, requested, run.active_bounds)
        derivative, self.delivered = self.allocation.allocated(
            state, base, requested, capacities, run.active_bounds, run.zero_faces, bound_key
        )
        if not extended and np.any(derivative[s.monotone] < 0):
            name = next(name for i, name in enumerate(s.state_ids) if s.monotone[i] and derivative[i] < 0)
            raise SimulationError(f'Nondecreasing state {name} has a negative rate')
        return derivative

    def jacobian_pattern(self):
        """Structural Jacobian sparsity, widened across every allocation-coupled flow."""
        if self._pattern is not None:
            return self._pattern
        s = self.system
        index, flows = s.index, s.flows
        matrix = np.eye(len(s.state_ids), dtype=bool)

        def dependency(expr):
            return [index[name] for name in s.expanded_names(expr) if name in index]

        def rows_of(flow):
            return [index[x] for x in (flow.source, flow.target) if x]

        for name, derivative in s.resolved.rates.items():
            for j in dependency(derivative.expr):
                matrix[index[name], j] = True
        linked = {}
        flow_rows, flow_dependencies = {}, {}
        for name, flow in flows.items():
            key = flow.allocation
            deps = dependency(flow.rate) + (dependency(s.groups[key].capacity) if key in s.groups else [])
            deps += [index[flow.source]] if flow.source else []
            flow_rows[name], flow_dependencies[name] = rows_of(flow), deps
            for r in rows_of(flow):
                for j in deps:
                    matrix[r, j] = True
            if key:
                linked.setdefault(('allocation', key), set()).add(name)
            for endpoint in (flow.source, flow.target):
                if endpoint:
                    linked.setdefault(('stock', endpoint), set()).add(name)
        for key, coupling in s.couplings.items():
            linked[('coupling', key)] = set(coupling.flows)
        # Shared stocks, allocation groups and coupled material legs form one
        # dependency component. A restriction propagates through all three.
        components = []
        for members in linked.values():
            merged = set(members)
            remaining = []
            for component in components:
                if component & merged:
                    merged.update(component)
                else:
                    remaining.append(component)
            components = [*remaining, merged]
        for members in components:
            rows = [r for name in members for r in flow_rows[name]]
            deps = [j for name in members for j in flow_dependencies[name]]
            for r in rows:
                for j in deps:
                    matrix[r, j] = True
        # States set only by events (flags, levels) are not part of the continuous system:
        # no Jacobian column, so implicit stages keep them exactly at their current value.
        # Perturbing a flag that gates a rate would otherwise switch that rate on inside a
        # Newton iteration and accrue flow before its event.
        for j, name in enumerate(s.state_ids):
            if name not in s.evolving:
                matrix[:, j] = False
        self._pattern = matrix
        return matrix
