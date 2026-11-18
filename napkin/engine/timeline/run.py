"""One run of a plan: the values at the start, then each connected set to the horizon, and the record.

This slice has no events, so a run has one setup and the segments of its components:

1. **The start** evaluates each input, draw, stored value and captured request or capacity once, in
   the order of what it reads (a formula that one of them reads is evaluated there and then). A
   draw is the median of its distribution in a median run, and in a sampled run the quantile of a
   uniform number from the stream of its site and its member under the seed; each draw is an entry
   of the trace. An input that the configuration sets must lie in its admitted range.
2. **The sizes.** A store's size sets its absolute tolerance (`atol_factor` times it, D8): its
   `scale` when it declares one, else the largest of one of its unit, its start value, its finite
   bounds and the largest start value of the stores that flows connect it to. A store must start
   within its bounds.
3. **The components.** Each connected set of the plan is a component (`component.py`). The run
   takes the next segment of the component that stands earliest, until each stands at the horizon,
   and the recorder (`record.py`) takes the pieces of each segment as it is made.

A run that fails stops there: its record holds the failure, as the last entry of its trace, and the
histories to the time at which it stopped.
"""

from __future__ import annotations

import heapq
import math

import numpy as np

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...distributions import FAMILIES, quantile
from ...expressions import evaluate
from ...program.config import MEDIAN, ConfigurationError
from .. import sampling
from ..continuous.system import Context, run_settings, solver_step, step_cap
from ..errors import SimulationError
from .component import Component, NetFlow, Network
from .plan import RATE, STARTS, STATE, Outside
from .record import Recorder


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


class Run:
    """See the module."""

    def __init__(self, plan):
        self.plan = plan
        self.cap = step_cap(plan.numerics)
        self.settings = run_settings(plan.numerics, self.cap)
        self.recorder = Recorder(plan, {}, {})
        self.now = 0.0  # the time of the component that the run advances, for a failure

    # ---- the start --------------------------------------------------------------------------------

    def start(self):
        """{engine name: value at the start} of each input, draw, stored value and captured request
        or capacity, with an entry of the trace for each draw."""
        plan, configuration = self.plan, self.plan.configuration
        env, visiting = {'t': 0.0}, []

        def value_of(name):
            if name in env:
                return env[name]
            if name in visiting:
                raise SimulationError(f'{name}: a starting value that reads itself')
            if name in plan.draws:
                found = plan.draws[name]
                key = f'{found.site}|{found.member}'
                env[name] = drawn(found.distribution, plan.units, configuration.mode, configuration.seed, key)
                self.recorder.entry(0.0, 'draw', found.site, found.member, value=env[name])
                return env[name]
            value = plan.values[name]
            if value.kind == RATE:
                raise Outside(f'{name}: a starting value that reads an actual rate (S2)')
            visiting.append(name)
            for read in sorted(set(nodes.names(value.node)) - {'t'}):
                value_of(read)
            visiting.pop()
            env[name] = evaluate(value.node, env, plan.units)
            return env[name]

        def number(node):
            if node is None:
                return None
            for read in sorted(set(nodes.names(node)) - {'t'}):
                value_of(read)
            return float(evaluate(node, env, plan.units))

        self.bounds, self.scales = {}, {}
        for name, value in plan.values.items():
            if value.kind not in STARTS:
                continue
            found = value_of(name)
            lower, upper = number(value.lower), number(value.upper)
            outside = (lower is not None and found < lower) or (upper is not None and found > upper)
            if value.given and not value.boolean and outside:
                raise ConfigurationError(f'{name}: {found:g} is outside its admitted range')
            self.bounds[name] = (-math.inf if lower is None else lower, math.inf if upper is None else upper)
            self.scales[name] = number(value.scale)
        return {name: found for name, found in env.items() if name != 't'}

    def sizes(self, values):
        """The size of each store (see the module)."""
        plan = self.plan
        parent = {name: name for name in plan.moving}

        def root(name):
            while parent[name] != name:
                parent[name] = parent[parent[name]]
                name = parent[name]
            return name

        for flow in plan.flows.values():
            if flow.source is not None and flow.sink is not None:
                parent[root(flow.source)] = root(flow.sink)
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
        sources = {flow.source for flow in plan.flows.values()}
        sinks = {flow.sink for flow in plan.flows.values()}
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
        computed = {name: {'expr': plan.values[name].node} for name in connected.formulas}
        leaves = set()
        for flow in flows.values():
            leaves |= plan.formula_reads(flow.rate)[0]
        parameters = sorted(name for name in leaves if name in values and name not in stores)
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
            (),
            (),
            (),
        )
        atol = [numerics.atol_factor * sizes[name] for name in stores]
        slack = [
            a + (numerics.rtol * sizes[name] if kinds[name] == 'cumulative' else 0.0)
            for a, name in zip(atol, stores)
        ]
        system = network.of(
            numerics, plan.units, plan.horizon, self.cap, solver_step(numerics), atol, slack, values
        )
        context = Context(
            stores,
            {name: values[name] for name in parameters},
            [(name, computed[name]['expr']) for name in connected.formulas],
            plan.units,
            system.bounds,
            self.settings,
        )
        return Component(system, context, [values[name] for name in stores])

    def prepare(self):
        """The run at its start: the values at the start, the size of each store, and each
        connected set as a component at its start, as (component, set)."""
        plan = self.plan
        values = self.start()
        self.recorder.constants = values
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
        components = [(self.component(connected, values, sizes, kinds), connected) for connected in plan.sets]
        for name in plan.moving:
            self.recorder.tolerance[name] = factor * sizes[name]
        for flow in plan.flows.values():
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

    def advance(self, components):
        """The segments of the components, the earliest first, to the horizon."""
        horizon, limit = self.plan.horizon, self.plan.configuration.limits.max_rounds
        standing = [(0.0, k) for k in range(len(components))]
        heapq.heapify(standing)
        still = [0] * len(components)  # the segments of no length in a row, of each component
        while standing:
            t, k = heapq.heappop(standing)
            if t >= horizon:
                continue
            self.now = t
            component, connected = components[k]
            segment = component.next(horizon)
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
