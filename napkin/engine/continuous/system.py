"""The fixed description of one run, and the state that changes as it proceeds."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from ...core import expr as nodes
from ...expressions import ExpressionError, UnitSystem, evaluate, names_in
from ...model import structure as typed
from ...model.analysis.structure import evolving_parts
from ...model.ir import COUNT, ENTERED, TIME
from ..errors import SimulationError

# A numerical step resolves each declared physical timescale with at least eight steps.
PHYSICAL_STEP_FRACTION = 0.125
# The longest step of a scenario without a resolution line, in hours: `NumericalSettings.max_step`
# gives it, and scales the resolution of a scenario that has the line.
DEFAULT_STEP_H = 1.0


def initial_store(rs):
    """The store at t = 0: each mode's start value, entered at 0, and no event yet."""
    store = {}
    for mid, mode in rs.modes.items():
        store[mid] = mode.initial
        store[mid + ENTERED] = 0.0
    for event in rs.events:
        store[event + COUNT] = 0
        store[event + TIME] = 0.0
    return store


def label_expression(label):
    """A label as one expression: the value of its first true case, else the default. Each value is
    the node that a text writes for it."""
    node = nodes.read(repr(label.default.value))
    for case in reversed(label.cases):
        node = nodes.if_else(case.when, nodes.read(repr(case.value)), node)
    return node


def step_cap(time, values, units, cfg):
    """The longest step of a numerical segment of a run, in hours, with the physical timescales that
    the run declares. `time`: the horizon, resolution and timescales of the run; `values`: its inputs.

    A scenario's resolution replaces the default step of 1 h; the settings' `max_step` scales it, so a
    caller still refines every run by the same factor. A step resolves each declared physical
    timescale with at least eight steps."""
    timescales = []
    for expression in time.timescales or ():
        if names_in(expression) - values.keys():
            raise SimulationError('Physical timescales must depend only on parameters')
        timescale = float(evaluate(expression, values, units))
        if not math.isfinite(timescale) or timescale <= 0 or timescale * PHYSICAL_STEP_FRACTION == 0:
            raise SimulationError('Physical timescales must be finite and strictly positive')
        timescales.append(timescale)
    resolution = time.resolution
    if resolution is not None and (not math.isfinite(float(resolution)) or float(resolution) <= 0):
        raise SimulationError('The resolution must be a finite and positive time')
    requested = cfg.max_step if resolution is None else float(resolution) * cfg.max_step / DEFAULT_STEP_H
    return min([requested] + [timescale * PHYSICAL_STEP_FRACTION for timescale in timescales]), timescales


def solver_step(timescales):
    """The longest step that the solver of a numerical segment takes, in hours: one eighth of the
    shortest physical timescale that the run declares, or no limit. The step cap of the run
    (`step_cap`) is the interval at which the engine reads the roots and the field of the segment;
    between two such times the solver's own control of the error decides its step."""
    return min((timescale * PHYSICAL_STEP_FRACTION for timescale in timescales), default=math.inf)


def run_settings(time, cfg, max_step, timescales):
    """The numerical settings of a run as its result gives them."""
    settings = {
        **vars(cfg),
        'requested_max_step': cfg.max_step,
        'max_step': max_step,
        'resolution_step_h': max_step,
        'integration_segments': [],
        'resolution_policy': 'structural_exact',
        'actual_max_step_h': None,
        'physical_timescales_h': timescales,
        'physical_step_fraction': PHYSICAL_STEP_FRACTION,
    }
    if time.resolution is not None:
        settings['scenario_resolution_h'] = float(time.resolution)
    return settings


class System:
    """Everything about one run that stays fixed from its start to its horizon: the quantities and
    their bounds and tolerances, the flows, allocation groups and couplings, and the step cap."""

    def __init__(self, rs: typed.Resolved, library: Mapping, cfg):
        self.resolved = rs
        self.cfg = cfg
        self.units = units = UnitSystem(library['units'])
        self.quantities = definitions = rs.quantities
        self.state_ids = state_ids = tuple(definitions)
        self.index = index = {name: i for i, name in enumerate(state_ids)}
        self.values = values = dict(rs.values)
        # The engine's own mapping of the formulas and the statuses, each as one expression.
        self.computed = {
            **{name: {'expr': c.expr} for name, c in rs.computed.items()},
            **{name: {'expr': label_expression(label)} for name, label in rs.labels.items()},
        }
        self.max_step, timescales = step_cap(rs.time, values, units, cfg)
        self.solver_step = solver_step(timescales)
        self.settings = run_settings(rs.time, cfg, self.max_step, timescales)
        self.horizon = float(rs.time.horizon)
        if not math.isfinite(self.horizon) or self.horizon < 0:
            raise SimulationError('Horizon must be finite and nonnegative')
        self.lower = np.array(
            [
                float(d.minimum if d.minimum is not None else 0 if d.kind == 'stock' else -np.inf)
                * units.scale(d.unit)
                for d in definitions.values()
            ]
        )
        self.upper = np.array(
            [
                float(d.maximum) * units.scale(d.unit) if d.maximum is not None else np.inf
                for d in definitions.values()
            ]
        )
        self.monotone = np.array(
            [d.kind == 'cumulative' for d in definitions.values()],
            dtype=bool,
        )
        # Each quantity's size sets its absolute tolerance.
        self.sizes = sizes = self.sizes_of(self.initial_state(initial_store(rs)))
        if np.any(~np.isfinite(sizes)) or np.any(sizes <= 0):
            raise SimulationError('Every state requires a positive finite size')
        self.atol = cfg.atol_factor * sizes
        # A nondecreasing ledger cannot truly fall below its lower bound; a dip there is solver
        # error (Newton and interpolation), bounded by the accuracy on the ledger's own size.
        self.ledger_slack = np.where(self.monotone, self.atol + cfg.rtol * sizes, self.atol)

        self.flows = flows = dict(rs.flows)
        self.flow_ids = tuple(flows)
        self.flow_index = flow_index = {name: j for j, name in enumerate(self.flow_ids)}
        self.groups = groups = rs.allocation
        self.couplings = couplings = rs.coupling
        self.evolving = evolving_parts(rs)
        # Quantities that only rules set: constant between moments, pinned in every evaluation.
        self.discrete = [i for i, name in enumerate(state_ids) if name not in self.evolving]
        self.discrete_rows = np.array(self.discrete, dtype=int)
        self.flow_matrix = np.zeros((len(state_ids), len(flows)))
        for j, flow in enumerate(flows.values()):
            if flow.source:
                self.flow_matrix[index[flow.source], j] -= 1
            if flow.target:
                self.flow_matrix[index[flow.target], j] += 1
        self.derivative_ids = list(rs.rates)
        self.derivative_rows = np.array([index[name] for name in self.derivative_ids], dtype=int)
        self.proven_faces = tuple(rs.proven_zero_stock_faces)
        self.proven_face_set = frozenset(self.proven_faces)
        self.abs_flow_matrix = np.abs(self.flow_matrix)
        # The flows of each state, in flow order: (flow, other end) out of it and into it, and the flows
        # that join it to the outside (`Field._balance`).
        self.legs = {name: ([], [], []) for name in state_ids}
        # The flows that join each state, as (flow id, flow), in flow order (`kernels.Classifier`).
        self.flows_of = {name: [] for name in state_ids}
        for key, flow in flows.items():
            for end in dict.fromkeys((flow.source, flow.target)):
                if end:
                    self.flows_of[end].append((key, flow))
        for j, flow in enumerate(flows.values()):
            source, target = flow.source, flow.target
            if source:
                self.legs[source][0].append((j, target))
                if not target:
                    self.legs[source][2].append(j)
            if target:
                self.legs[target][1].append((j, source))
                if not source:
                    self.legs[target][2].append(j)
        self.monotone_crossings = frozenset(rs.proven_monotone_crossings)
        self.group_indices = {
            gid: [j for j, f in enumerate(flows.values()) if f.allocation == gid] for gid in groups
        }
        self.coupling_members = [
            [flow_index[name] for name in coupling.flows] for coupling in couplings.values()
        ]
        # Stocks whose zero lower bound can balance an allocated face (lower == 0, kind stock).
        self.zero_floor_stocks = np.array(
            [self.lower[i] == 0 and definitions[name].kind == 'stock' for i, name in enumerate(state_ids)],
            dtype=bool,
        )
        self._expanded = {}
        self._reads = {}
        # Proofs that an expression is constant on the stock-zero faces depend only on the
        # expression, the names that stay fixed in a segment and the parameter values.
        self.face_proofs = {}
        # What the segments read of the run's expressions alone, found once for the run: the
        # switching surfaces (`integrate.switching_surfaces`) and the repayment arms
        # (`kernels.repayment_shapes`).
        self.analysis = {}
        # The names of the discrete store, which a run keeps from its start to its horizon.
        self.store_names = frozenset(initial_store(rs))
        # The inputs that the run's generated programs write as literals: each one that no quantity,
        # entry of the store, formula or the time hides in an environment (`expressions.compile_program`).
        hidden = set(state_ids) | self.store_names | set(self.computed) | {'t'}
        self.known = {name: value for name, value in values.items() if name not in hidden}

    @property
    def bounds(self):
        return self.lower, self.upper, self.ledger_slack, self.atol

    def sizes_of(self, start):
        """The size of each quantity, in execution units: the `size` that the file writes, else the
        largest of one of its unit, its start value, its finite bounds, the largest start value of the
        quantities that flows and transfers connect it to, and the capacity of an allocation group
        that rations a flow of it, over the horizon. The size sets the quantity's absolute tolerance
        (`atol_factor` times it)."""
        rs, index = self.resolved, self.index
        unit = np.array([self.units.scale(d.unit) for d in self.quantities.values()])
        found = np.maximum(unit, np.abs(start))
        for bound in (self.lower, self.upper):
            finite = np.isfinite(bound)
            found[finite] = np.maximum(found[finite], np.abs(bound[finite]))
        # The quantities that flows and transfers connect: each takes the largest start value of them.
        parent = list(range(len(found)))

        def root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        pairs = [(flow.source, flow.target) for flow in rs.flows.values()]
        for rule in rs.rules.values():
            for outcome in rule.outcomes:
                pairs += [(move.source, move.target) for move in outcome.do.transfer]
        for a, b in pairs:
            if a in index and b in index:
                parent[root(index[a])] = root(index[b])
        largest = {}
        for i, value in enumerate(np.abs(start)):
            largest[root(i)] = max(largest.get(root(i), 0.0), value)
        found = np.maximum(found, [largest[root(i)] for i in range(len(found))])
        # A rationed flow moves at most its group's capacity: over the horizon, that bounds what its
        # quantities can gain or lose.
        env = {**self.values, **dict(zip(self.state_ids, map(float, start))), **initial_store(rs), 't': 0.0}
        for gid, group in rs.allocation.items():
            if names_in(group.capacity) - env.keys():
                continue  # a capacity that reads a computed value bounds nothing here
            try:
                capacity = abs(float(evaluate(group.capacity, env, self.units))) * self.horizon
            except ExpressionError:
                continue
            if not math.isfinite(capacity):
                continue
            for flow in rs.flows.values():
                if flow.allocation == gid:
                    for end in (flow.source, flow.target):
                        if end in index:
                            found[index[end]] = max(found[index[end]], capacity)
        for i, d in enumerate(self.quantities.values()):
            if d.size is not None:
                found[i] = float(d.size) * unit[i]
        return found

    def read(self, name):
        """The code of a generated program of the run, `program(Y, T, S, V, R)`, that reads a name that
        is not a literal: the time T, an entry of the store S, a quantity of the state Y or an input of
        V, in the order in which an environment gives them (`Trajectory._environment`)."""
        if name == 't':
            return 'T', False
        if name in self.store_names:
            return f'S[{name!r}]', False
        if name in self.index:
            return f'Y[{self.index[name]}]', False
        if name in self.values:
            return f'V[{name!r}]', False
        return f'_missing({name!r})', True

    def expanded_frozen(self, expr):
        """The names that an expression (a text or a node) reads, through computed values and labels, as
        one shared frozen set: for tests that do not change it."""
        found = self._expanded.get(expr)
        if found is None:
            found = self._expanded[expr] = frozenset(self.expanded_names(expr, ()))
        return found

    def expanded_names(self, expr, seen=None):
        """The names an expression reads, through computed values and labels."""
        if seen is None and isinstance(expr, (str, nodes.Node)):
            if expr not in self._expanded:
                self._expanded[expr] = frozenset(self._expand(expr, frozenset(), self._reads)[0])
            return set(self._expanded[expr])
        seen = frozenset(seen or ())
        # The kept names of a value hold for calls that start with none seen; any other call keeps its own.
        return self._expand(expr, seen, {} if seen else self._reads)[0]

    def _expand(self, expr, seen, reads):
        """The names that `expr` reads through computed values, and whether a computed value on the path
        reached itself. `reads` keeps the names that each computed value reads once found; a value whose
        expansion meets such a cycle is not kept, so every result is the one of the plain recursion."""
        names = set(names_in(expr))
        cyclic = False
        for name in list(names):
            if name not in self.computed:
                continue
            if name in seen:
                cyclic = True
                continue
            kept = reads.get(name)
            if kept is None:
                found, hit = self._expand(self.computed[name]['expr'], seen | {name}, reads)
                if hit:
                    names |= found
                    cyclic = True
                    continue
                kept = reads[name] = frozenset(found)
            names |= kept
        return names, cyclic

    def initial_state(self, store):
        """The state at t=0, with initial values resolved in dependency order."""
        env = {**self.values, **store, 't': 0.0}
        pending = {name: d.initial for name, d in self.quantities.items()}
        pending.update({name: d['expr'] for name, d in self.computed.items()})
        initial = {}
        while pending:
            ready = [name for name, expr in pending.items() if names_in(expr) <= env.keys()]
            if not ready:
                raise SimulationError(f'Unresolved initial values: {sorted(pending)}')
            for name in ready:
                env[name] = evaluate(pending.pop(name), env, self.units)
                if name in self.quantities:
                    initial[name] = float(env[name])
        return np.array([initial[name] for name in self.state_ids], dtype=float)


@dataclass
class Run:
    """What changes as a run proceeds: the time, the state and the discrete store, the bounds the
    state rests on, the stock faces of the current segment and the level rules it watches."""

    time: float
    y: np.ndarray
    store: dict
    active_bounds: set = field(default_factory=set)  # (quantity index, 'min' | 'max')
    zero_faces: set = field(default_factory=set)  # stocks held on their zero face
    right_faces: set = field(default_factory=set)  # stocks evaluated just above zero
    guards: dict = field(default_factory=dict)  # the segment's armed level rules, by rule
    evaluations: int = 0
