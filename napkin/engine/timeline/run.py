"""One run of a plan: the values at the start, then each connected set to the horizon, and the record.

This slice has no events, so a run has one setup and the segments of its connected sets:

1. **The start** evaluates each input, draw, link, stored value and captured request or capacity once,
   in the order of what it reads, across members (a formula, a reduction or a keyed read that one of
   them reads is evaluated there and then, at time 0). The order is found as the values are asked,
   with no recursion, so a chain through the rows of a large table is no limit. A draw is the median
   of its distribution in a median run, and in a sampled run the quantile of a uniform number from
   the stream of its site and its member under the seed; each draw is an entry of the trace. An
   input that the configuration sets must lie in its admitted range. The entries that each `where`
   keeps are found from fixed values, once (`kept_of`), and so is the sorted index of the keys of
   each keyed read (`stepped_of`). Then each assertion over inputs is checked once; one that does not
   hold fails the run at the start, as an error of the setup that the plan found does.
2. **The sizes.** A store's size sets its absolute tolerance (`atol_factor` times it, D8): its
   `scale` when it declares one, else the largest of one of its unit, its start value, its finite
   bounds and the largest start value of the stores that flows connect it to. A store must start
   within its bounds.
3. **The sets.** The sets of one flow whose rate reads nothing that moves run together as the family
   (`family.py`). Each other connected set is a component (`component.py`): a reduction that its
   rates read is a formula node over the kept entries, and a keyed read by the time is an entry of
   the component's store, which the run sets at each key time. The key times of the keyed reads by
   the time that the sets read cut the run into windows: in each, the family takes the rows that
   reach a bound, then each component takes its next segment, the earliest first, until it stands at
   the window's end; at that end the keyed reads change, and the sets that read them evaluate their
   rates again. The recorder (`record.py`) takes the pieces of each segment as it is made.

A run that fails stops there: its record holds the failure, as the last entry of its trace, and the
histories to the time at which it stopped.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...distributions import FAMILIES, quantile
from ...expressions import evaluate
from ...program.config import MEDIAN, ConfigurationError
from .. import sampling
from ..continuous.system import Context, run_settings, solver_step, step_cap
from ..errors import SimulationError
from .collections import index_of, kept, looked_up, node_of, reduced
from .component import Component, NetFlow, Network
from .family import Family
from .lines import Lines
from .plan import COMPONENT, FAMILY, LEGS, LINES, LOOKUP, RATE, REDUCE, SPARSE, STARTS, STATE, Outside
from .record import Recorder, remember
from .sparse import Sparse


def drawn(distribution, units, mode, seed, key):
    """One draw of a distribution in canonical units: its median in a median run, else the quantile
    of the first uniform number of the stream `key` under the seed (`sampling.stream`)."""
    family = FAMILIES[distribution.family]
    scale = units.scale(distribution.unit) if distribution.unit else 1.0
    args = {
        name: float(value) * (1.0 if name in family.dimensionless else scale)
        for name, value in zip(family.parameters, distribution.params)
    }
    if 'min' in family.parameters and 'min' not in args:
        # The unbounded forms of `normal` and `lognormal`.
        args.update(min=0.0 if family.name == 'lognormal' else -math.inf, max=math.inf)
    u = 0.5 if mode == MEDIAN else float(sampling._open(sampling.stream(seed, key), 1)[0])
    with np.errstate(divide='ignore'):
        return float(quantile(family.name, args, u))


def _literal(node, units):
    """The value of a constant or of a quantity `q(number, unit)` (a table's cell, a bound, what a
    configuration gives), as `evaluate` has it, or None for any other node."""
    if isinstance(node, nodes.Const) and isinstance(node.value, (bool, int, float)):
        return node.value
    if (
        isinstance(node, nodes.Call)
        and node.function == 'q'
        and len(node.args) == 2
        and all(isinstance(arg, nodes.Const) for arg in node.args)
        and isinstance(node.args[0].value, (int, float))
        and not isinstance(node.args[0].value, bool)
    ):
        return units.normalize(node.args[0].value, node.args[1].value)
    return None


@dataclass(frozen=True)
class Stepped:
    """A keyed read by the time: its value from each distinct key of its kept entries (`times`) to
    the next; below the first key it fails."""

    spelled: str
    times: np.ndarray
    values: tuple

    def at(self, t):
        """The value at time t, or an ExpressionError below the first key."""
        place = int(np.searchsorted(self.times, t, side='right')) - 1
        if place < 0:
            raise ExpressionError(f'{self.spelled}: no member has a key at or below {t:g}')
        return self.values[place]


class Run:
    """See the module."""

    def __init__(self, plan):
        self.plan = plan
        self.cap = step_cap(plan.numerics)
        self.settings = run_settings(plan.numerics, self.cap)
        self.recorder = Recorder(plan, {}, {})
        self.recorder.run = self
        remember(plan)
        self.now = 0.0  # the time that the run has reached, for a failure
        self.env = {'t': 0.0}  # the values at the start, by engine name
        self._kept, self._stepped, self._indexes = {}, {}, {}
        self.family = self.lines = None
        self.sparse = []

    # ---- the start --------------------------------------------------------------------------------

    def _missing(self, name):
        """The names that `name` reads and that are not known yet: the tests of a collection before
        its members' values, and of a keyed read the keys of its kept entries and its key, then the
        value of the entry that it finds."""
        plan, env = self.plan, self.env
        if name in plan.draws:
            return []
        value = plan.values[name]
        if value.kind == RATE:
            raise Outside(f'{name}: a starting value that reads an actual rate (S2)')
        if value.kind in (REDUCE, LOOKUP):
            derived = plan.reductions.get(name) or plan.keyed[name]
            tests = {read for test in derived.tests if test is not None for read in nodes.names(test)} - {'t'}
            missing = sorted(read for read in tests if read not in env)
            if missing:
                return missing
            entries = self.kept_of(name)
            if value.kind == REDUCE:
                return (
                    [derived.names[k] for k in entries if derived.names[k] not in env]
                    if derived.names
                    else []
                )
            reads = {derived.keys[k] for k in entries if isinstance(derived.keys[k], str)}
            reads |= set(nodes.names(derived.key)) - {'t'}
            missing = sorted(read for read in reads if read not in env)
            if missing:
                return missing
            found = self._found(name)
            return [] if found is None or found in env else [found]
        return sorted(read for read in set(nodes.names(value.node)) - {'t'} if read not in env)

    def _found(self, name):
        """The engine name of the value that a keyed read finds at the start, or None."""
        keyed, entries = self.plan.keyed[name], self.kept_of(name)
        index = self._index(name)
        x = 0.0 if keyed.by_time else float(evaluate(keyed.key, self.env, self.plan.units))
        place = index.find(x)
        return None if place is None else keyed.names[entries[place]]

    def _compute(self, name):
        """The value of a name whose reads are known."""
        plan, configuration, env = self.plan, self.plan.configuration, self.env
        if name in plan.draws:
            found = plan.draws[name]
            key = f'{found.site}|{found.member}'
            value = drawn(found.distribution, plan.units, configuration.mode, configuration.seed, key)
            self.recorder.entry(0.0, 'draw', found.site, found.member, value=value)
            return value
        kind = plan.values[name].kind
        found = _literal(plan.values[name].node, plan.units)
        if found is not None:
            return found
        if kind == REDUCE:
            return reduced(plan.reductions[name], env.__getitem__, plan.units, self.kept_of(name))
        if kind == LOOKUP:
            index = (self._index(name), self.kept_of(name))
            return looked_up(plan.keyed[name], env.__getitem__, plan.units, 0.0, index)
        node = plan.values[name].node
        if isinstance(node, nodes.Ref):
            return env[node.name]  # a value that names another: no expression to compile
        return evaluate(node, env, plan.units)

    def value_of(self, name):
        """The value of an engine name at the start, evaluated once, after what it reads."""
        env = self.env
        if name in env:
            return env[name]
        value = self.plan.values.get(name)
        found = _literal(value.node, self.plan.units) if value is not None else None
        if found is not None:
            env[name] = found  # a table's cell, a constant: it reads nothing
            return found
        stack, expanded = [name], set()
        while stack:
            top = stack[-1]
            if top in env:
                stack.pop()
                continue
            missing = self._missing(top)
            if not missing:
                env[top] = self._compute(top)
                stack.pop()
                continue
            if top in expanded:
                raise SimulationError(f'{top}: a starting value that reads itself')
            expanded.add(top)
            for read in missing:
                if read in expanded:
                    raise SimulationError(f'{read}: a starting value that reads itself')
                stack.append(read)
        return env[name]

    def classes_of(self, store, side, items, number):
        """The priority classes of an endpoint as the numbers of its flows (`number`): a flow that an
        item names is a class, a keyed projection gives a class for each distinct key, lower keys
        first, and the flows that no item names are the last class."""
        mine = self.plan.ends[(store, side)].flows
        classes, named = [], set()
        for kind, item in items:
            if kind == 'one':
                found = [[item]]
            else:
                keyed = {}
                for key, flow in item:
                    keyed.setdefault(float(self.value_of(key) if isinstance(key, str) else key), []).append(
                        flow
                    )
                found = [keyed[key] for key in sorted(keyed)]
            for written in found:
                members = [flow for flow in written if flow in mine]
                if members:
                    classes.append(tuple(number[flow] for flow in members))
                    named.update(members)
        rest = tuple(number[flow] for flow in mine if flow not in named)
        return tuple(classes) + ((rest,) if rest else ())

    def kept_of(self, name):
        """The places of the entries that the where tests of a reduction or a keyed read keep."""
        if name not in self._kept:
            derived = self.plan.reductions.get(name) or self.plan.keyed[name]
            self._kept[name] = kept(derived.tests, self.value_of, self.plan.units)
        return self._kept[name]

    def _index(self, name):
        if name not in self._indexes:
            self._indexes[name] = index_of(
                self.plan.keyed[name], self.value_of, self.plan.units, self.kept_of(name)
            )[0]
        return self._indexes[name]

    def stepped_of(self, name):
        """The keyed read by the time `name` (`Stepped`), from the keys of its kept entries."""
        if name not in self._stepped:
            keyed, entries, index = self.plan.keyed[name], self.kept_of(name), self._index(name)
            times = index.times()
            values = tuple(self.value_of(keyed.names[entries[index.find(key)]]) for key in times.tolist())
            self._stepped[name] = Stepped(keyed.spelled, times, values)
        return self._stepped[name]

    def start(self):
        """{engine name: value at the start} of each input, draw, link, stored value and captured
        request or capacity, with an entry of the trace for each draw."""
        plan = self.plan

        def number(node):
            if node is None:
                return None
            found = _literal(node, plan.units)
            if found is not None:
                return float(found)
            for read in sorted(set(nodes.names(node)) - {'t'}):
                self.value_of(read)
            return float(evaluate(node, self.env, plan.units))

        self.bounds, self.scales = {}, {}
        for name, value in plan.values.items():
            if value.kind not in STARTS:
                continue
            found = self.value_of(name)
            lower, upper = number(value.lower), number(value.upper)
            outside = (lower is not None and found < lower) or (upper is not None and found > upper)
            if value.given and not value.boolean and outside:
                raise ConfigurationError(f'{name}: {found:g} is outside its admitted range')
            self.bounds[name] = (-math.inf if lower is None else lower, math.inf if upper is None else upper)
            self.scales[name] = number(value.scale)
        return {name: found for name, found in self.env.items() if name != 't'}

    def check(self):
        """The errors of the setup that the plan found, and the assertions over inputs: each fails
        the run at its start."""
        plan = self.plan
        if plan.failures:
            raise SimulationError(plan.failures[0])
        for origin, member, node in plan.asserts:
            for read in sorted(set(nodes.names(node)) - {'t'}):
                self.value_of(read)
            if not evaluate(node, self.env, plan.units):
                raise SimulationError(
                    f'{origin}: the assertion does not hold{f" for {member}" if member else ""}'
                )

    def sizes(self, values):
        """The size of each store (see the module)."""
        plan = self.plan
        parent = {name: name for name in plan.moving}

        def root(name):
            while parent[name] != name:
                parent[name] = parent[parent[name]]
                name = parent[name]
            return name

        for connection in plan.connections.values():
            if connection.source is not None and connection.sink is not None:
                parent[root(connection.source)] = root(connection.sink)
        largest = {}
        for name in plan.moving:
            largest[root(name)] = max(largest.get(root(name), 0.0), abs(values[name]))
        found = {}
        for name in plan.moving:
            if self.scales[name] is not None:
                found[name] = abs(self.scales[name])
                continue
            unit = plan.values[name].unit
            size = max(plan.units.scale(unit) if unit else 1.0, abs(values[name]), largest[root(name)])
            for bound in self.bounds[name]:
                if math.isfinite(bound):
                    size = max(size, abs(bound))
            found[name] = size
        return found

    # ---- the components ---------------------------------------------------------------------------

    def kinds(self):
        """The kind of each store as the continuous engine reads it (`component.Network`)."""
        plan = self.plan
        sources = {connection.source for connection in plan.connections.values()}
        sinks = {connection.sink for connection in plan.connections.values()}
        found = {}
        for name in plan.moving:
            if name in sinks and name not in sources:
                found[name] = 'cumulative'
            elif self.bounds[name][0] == 0:
                found[name] = 'stock'
            else:
                found[name] = 'state'
        return found

    def component(self, connected, values, sizes, kinds):
        """The component of a connected set, at its start."""
        plan, numerics = self.plan, self.plan.numerics
        stores = connected.stores
        lower = [self.bounds[name][0] for name in stores]
        upper = [self.bounds[name][1] for name in stores]
        flows = {}
        for name in connected.flows:
            flow = plan.flows[name]
            flows[name] = NetFlow(flow.rate, flow.source, flow.sink, None)
        computed = {}
        for name in connected.formulas:
            if name in plan.reductions:
                try:
                    node = node_of(plan.reductions[name], self.kept_of(name))
                except ExpressionError as problem:
                    raise SimulationError(str(problem)) from None
            else:
                node = plan.values[name].node
            computed[name] = {'expr': node}
        leaves = set()
        for flow in flows.values():
            leaves |= plan.expansion(flow.rate).leaves
        stepped = set(connected.stepped)
        parameters = sorted(name for name in leaves if name not in stores and name not in stepped)
        known = {**values, **{name: self.value_of(name) for name in parameters}}
        network = Network(
            stores[0],
            stores,
            kinds,
            lower,
            upper,
            flows,
            {},
            {},
            {},
            computed,
            set(stores),
            parameters,
            stepped,
            (),
            (),
        )
        atol = [numerics.atol_factor * sizes[name] for name in stores]
        slack = [
            a + (numerics.rtol * sizes[name] if kinds[name] == 'cumulative' else 0.0)
            for a, name in zip(atol, stores)
        ]
        system = network.of(
            numerics, plan.units, plan.horizon, self.cap, solver_step(numerics), atol, slack, known
        )
        context = Context(
            stores,
            {name: known[name] for name in parameters},
            [(name, computed[name]['expr']) for name in connected.formulas],
            plan.units,
            system.bounds,
            self.settings,
        )
        rigid = [name for name in connected.flows if plan.rigid(plan.flows[name])]
        component = Component(system, context, [values[name] for name in stores], rigid)
        self._set_stepped(component, connected, 0.0)
        return component

    def _set_stepped(self, component, connected, t):
        """The keyed reads by the time of a component at time t, in its store. One that has no value
        there is left out: a rate that reads it fails."""
        store = component.state.store
        for name in connected.stepped:
            try:
                store[name] = self.stepped_of(name).at(t)
            except ExpressionError:
                store.pop(name, None)

    def prepare(self):
        """The run at its start: the values at the start, the size of each store, and each
        connected set that is not in the family as a component at its start, as (component, set).
        The family is `self.family`."""
        plan = self.plan
        values = self.start()
        self.recorder.constants = values
        self.check()
        sizes = self.sizes(values)
        factor = plan.numerics.atol_factor
        outside = [
            name
            for name, value in plan.values.items()
            if value.kind == STATE
            and not value.boolean
            and not self.bounds[name][0] - factor * sizes.get(name, 0.0)
            <= values[name]
            <= self.bounds[name][1] + factor * sizes.get(name, 0.0)
        ]
        if outside:
            raise SimulationError(f'State bounds violated: {outside}')
        kinds = self.kinds()
        ways = {
            way: [connected for connected in plan.sets if connected.way == way]
            for way in (FAMILY, LINES, COMPONENT, SPARSE)
        }
        components = [
            (self.component(connected, values, sizes, kinds), connected) for connected in ways[COMPONENT]
        ]
        self.sparse = [Sparse(self, connected, values, sizes) for connected in ways[SPARSE]]
        self.family = Family(self, ways[FAMILY], values)
        self.lines = Lines(self, ways[LINES], values)
        for name in plan.moving:
            self.recorder.tolerance[name] = factor * sizes[name]
        for flow in plan.flows.values():
            if flow.kind == LEGS:
                # A served fraction is a number from zero to one.
                self.recorder.tolerance[f'{flow.name}.served_fraction'] = factor
                continue
            # A rate's error over an hour moves what a store's tolerance allows.
            size = max(sizes[end] for end in (flow.source, flow.sink) if end is not None)
            self.recorder.tolerance[f'{flow.name}.actual_rate'] = factor * size
        return values, sizes, components

    def run(self):
        """The record of the run."""
        try:
            self.advance(self.prepare()[2])
        except (SimulationError, ExpressionError, ArithmeticError) as problem:
            return self.recorder.record(self.now, self.recorder.failure(self.now, str(problem)))
        return self.recorder.record(self.plan.horizon)

    def key_times(self, components):
        """The key times inside the run of the keyed reads by the time that the sets read."""
        names = set(self.family.stepped if self.family is not None else ())
        names |= set(self.lines.stepped if self.lines is not None else ())
        for _, connected in components:
            names |= set(connected.stepped)
        for one in self.sparse:
            names |= set(one.stepped)
        found = set()
        for name in names:
            found |= {float(t) for t in self.stepped_of(name).times if 0 < t < self.plan.horizon}
        return sorted(found)

    def advance(self, components):
        """The family and the components, window by window, to the horizon (see the module)."""
        horizon, limit = self.plan.horizon, self.plan.configuration.limits.max_rounds
        family, lines = self.family, self.lines
        family.begin(0.0)
        lines.begin(0.0)
        standing = [(0.0, k) for k in range(len(components))]
        heapq.heapify(standing)
        still = [0] * len(components)  # the segments of no length in a row, of each component
        for end in [*self.key_times(components), horizon]:
            family.advance(end)
            lines.advance(end)
            for one in self.sparse:
                one.advance(end)
            while standing and standing[0][0] < end:
                t, k = heapq.heappop(standing)
                self.now = t
                component, connected = components[k]
                segment = component.next(end)
                self.recorder.segment(
                    component,
                    segment,
                    component.system.state_ids,
                    [f'{flow}.actual_rate' for flow in component.system.flow_ids],
                )
                component.proceed(segment)
                still[k] = still[k] + 1 if segment.end <= segment.start else 0
                if still[k] > limit:
                    raise SimulationError(f'{connected.flows[0]}: {limit} segments of no length at {t:g} h')
                heapq.heappush(standing, (segment.end, k))
            if end >= horizon:
                lines.finish(horizon)
                break
            self.now = end
            for component, connected in components:
                if any(end in self.stepped_of(name).times for name in connected.stepped):
                    self._set_stepped(component, connected, end)
            if any(end in self.stepped_of(name).times for name in family.stepped):
                family.refresh(end)
            if any(end in self.stepped_of(name).times for name in lines.stepped):
                lines.refresh(end)
