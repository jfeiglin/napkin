"""One run of a plan: the values at the start, then moment after moment to the horizon, and the record.

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
   within its bounds. A store of an occurrence takes its size when the occurrence starts.
3. **Moments** (`moment.py`): the setup is round zero at time 0; then, at each moment, rounds of
   stages, the settling of the sets that the round touched (`ways.py`), and the conditions
   (`triggers.py`). Occurrences are in `occurrences.py`.
4. **Between moments** each instance of a way runs its sets (`ways.py`). The next moment is the
   earliest of a stage that is due, a reset timer, a key time of a keyed read by the time, the
   horizon (`limit`) and the first contact of a watched condition (a contact within the crossing
   tolerance before a known moment is in that moment); an event inside an instance
   (a store that reaches a bound, the end of a segment) before it is committed first, and is itself
   a moment when it changes what a watched condition or another set's setting reads. An event at
   the time of a moment only puts its store on its bound: the moment's settling solves its set after
   the stages of the moment, as the oracle settles once.
5. **The horizon** is an inclusive cutoff: the work due there settles as at any moment, and the
   record holds the state that its last round committed.

The present (`value`): the value of an engine name now, or at a time inside the present window of
the ways (`t`): a store of a set from its instance, one written by this moment's commits from what
was written, an actual rate or a served fraction from the instance of its flow (zero for a flow that
is in no set), a formula from what it reads (a formula of a finished occurrence keeps its frozen
value), a reduction, a keyed read and a dynamic read of a collection from their members, and any
other value from what the run holds between moments (`env`). A stage reads its own writes first.

A run that fails stops there: its record holds the failure, as the last entry of its trace, and the
histories to the time at which it stopped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...distributions import FAMILIES, quantile
from ...expressions import evaluate
from ...program.config import MEDIAN, ConfigurationError
from ...program.record import Unavailable
from .. import sampling
from ..continuous.system import run_settings, step_cap
from ..errors import SimulationError
from .collections import dynamic_value, index_of, kept, looked_up, reduced
from .moment import Moment
from .occurrences import Occurrences
from .plan import DYNAMIC, FORMULA, LEGS, LOOKUP, RATE, REDUCE, STARTS, STATE, Outside
from .record import Recorder, remember
from .triggers import Triggers
from .ways import Ways


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
        self.env = {'t': 0.0}  # the values of the start, and later each value held between moments
        self._kept, self._stepped, self._indexes = {}, {}, {}
        self.started = False  # once true, `value_of` reads the present
        self.written = {}  # a store of a set that a commit of this moment wrote, and its value
        self.frozen = {}  # a formula of a finished occurrence -> its value or `Unavailable` (D7)
        self.limit = plan.horizon  # the next moment that the run knows (`next_moment`)
        self._keyed = None  # {key time: the keyed reads by the time that change there}
        self.changed = set()  # what a commit or an event of the ways changed: names and sources
        self.joined, self.left = [], []  # the flows that join and that leave at this moment
        self.ways = Ways(self)
        self.occurrences = Occurrences(self)
        self.triggers = Triggers(self)
        self.moment = Moment(self)

    # ---- the start --------------------------------------------------------------------------------

    def _missing(self, name):
        """The names that `name` reads and that are not known yet: the tests of a collection before
        its members' values, and of a keyed read the keys of its kept entries and its key, then the
        value of the entry that it finds."""
        plan, env = self.plan, self.env
        if name in plan.draws:
            return []
        value = plan.values[name]
        if value.kind == DYNAMIC:
            return []  # no occurrence has started, and no flow of one is present
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
        if kind == DYNAMIC:
            return self.value(name)
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
        """The value of an engine name at the start, evaluated once, after what it reads; once the
        run has started, its value now (`value`)."""
        if self.started:
            return self.value(name)
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

    def sizes_of(self, values):
        """The size of each stored number (see the module): of a store that a flow meets, and of one
        that a flow of an occurrence or a move may meet later."""
        plan = self.plan
        stores = [
            name
            for name, value in plan.values.items()
            if value.kind == STATE and not value.boolean and isinstance(values.get(name), int | float)
        ]
        parent = {name: name for name in stores}

        def root(name):
            while parent[name] != name:
                parent[name] = parent[parent[name]]
                name = parent[name]
            return name

        for connection in plan.connections.values():
            if connection.source is not None and connection.sink is not None:
                parent[root(connection.source)] = root(connection.sink)
        largest = {}
        for name in stores:
            largest[root(name)] = max(largest.get(root(name), 0.0), abs(values[name]))
        found = {}
        for name in stores:
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

    # ---- the present ----------------------------------------------------------------------------------

    def value(self, name, t=None, tx=None):
        """The value of an engine name now, or at a time t inside the present window of the ways (see
        the module); a stage's own writes (`tx`) first."""
        if tx is not None and name in tx.writes:
            return tx.writes[name]
        if name == 't':
            return self.now if t is None else float(t)
        t = self.now if t is None else float(t)
        if name in self.written:
            return self.written[name]
        plan = self.plan
        found = plan.values.get(name)
        kind = found.kind if found is not None else None
        if kind == RATE:
            return self.ways.rate(name, t)
        if kind == FORMULA:
            frozen = self.frozen.get(name)
            if frozen is not None:
                if isinstance(frozen, Unavailable):
                    raise ExpressionError(frozen.reason)
                return frozen
            node = found.node
            if isinstance(node, nodes.Ref):
                return self.value(node.name, t, tx)
            env = {read: _known(self.value(read, t, tx)) for read in nodes.names(node) if read != 't'}
            env['t'] = t
            return evaluate(node, env, plan.units)
        if kind == REDUCE:
            return reduced(
                plan.reductions[name], lambda read: self.value(read, t, tx), plan.units, self.kept_of(name)
            )
        if kind == LOOKUP:
            keyed = plan.keyed[name]
            if keyed.by_time:
                return self.stepped_of(name).at(t)
            return looked_up(keyed, lambda read: self.value(read, t, tx), plan.units, t)
        if kind == DYNAMIC:
            dynamic = plan.dynamic[name]
            return dynamic_value(
                dynamic,
                plan.members(dynamic.source),
                lambda point: plan.project(point, dynamic.steps),
                lambda read: self.value(read, t, tx),
                t,
            )
        if name in self.ways.set_of:
            return self.ways.value(name, t)
        try:
            return self.env[name]
        except KeyError:
            raise ExpressionError(f'{name} has no value yet') from None

    def held(self, name):
        """The value now of a name that holds between moments (an input, a parameter of a set)."""
        return self.value(name)

    def truth(self, node, tx=None):
        """The value of a node over engine names now, through a stage's own writes."""
        env = {read: _known(self.value(read, tx=tx)) for read in nodes.names(node) if read != 't'}
        env['t'] = float(self.now)
        return evaluate(node, env, self.plan.units)

    # ---- what a moment changes ---------------------------------------------------------------------

    def write(self, name, value):
        """A commit writes a value: a store of a set waits for the settling, any other value holds
        it from now on."""
        plan = self.plan
        if name in self.ways.set_of:
            self.written[name] = value
        else:
            self.env[name] = value
            self.recorder.add(name, self.now, value, 0.0)
        self.changed.add(name)
        found = plan.values.get(name)
        owner = found.key.owner if found is not None and found.key is not None else ''
        if '#' in owner:
            receiver, event = owner.rsplit('#', 1)[0].rsplit('.', 1)
            self.changed.add(('occurrences', receiver, event))
        for end in plan.setting_ends(name):
            self.changed.add(('flows', *end))

    def hold(self, store, value):
        """A store that no flow meets any more holds its value."""
        self.env[store] = value
        self.recorder.add(store, self.now, value, 0.0)

    def flow_joins(self, flow):
        """A flow of an occurrence joins its endpoints' collections; the settling builds its set."""
        self.joined.append(flow)
        self._present(flow, True)

    def flow_leaves(self, flow):
        """A flow of a finished occurrence leaves its endpoints' collections, all together."""
        self.left.append(flow)
        self._present(flow, False)

    def _present(self, flow, joins):
        plan = self.plan
        for connection in plan.flows[flow].connections:
            for side, store in zip(('outflow', 'inflow'), (connection.source, connection.sink)):
                if store is None:
                    continue
                present = plan.end_flows.setdefault((store, side), [])
                if joins:
                    present.append(connection.name)
                    plan.end_history.setdefault((store, side), []).append(connection.name)
                else:
                    present.remove(connection.name)
                end = plan.ends.get((store, side))
                if end is not None:
                    plan.ends[(store, side)] = replace(end, flows=tuple(present))
                self.changed.add(('flows', store, side))

    def flow_left(self, flow):
        """A flow that left reads zero from now on: its actual rate, or its served fraction."""
        found = self.plan.flows[flow]
        name = f'{flow}.served_fraction' if found.kind == LEGS else f'{flow}.actual_rate'
        self.recorder.add(name, self.now, 0.0, 0.0)

    def changed_names(self):
        """The engine names that changed at this moment so far, with the dynamic reads of the
        collections whose members changed."""
        names = {item for item in self.changed if isinstance(item, str)}
        sources = {item for item in self.changed if isinstance(item, tuple)}
        if sources:
            names |= {name for name, dynamic in self.plan.dynamic.items() if dynamic.source in sources}
        return names

    def settled(self):
        """The changes of a round are settled."""
        self.written.clear()
        self.joined.clear()
        self.left.clear()
        self.changed.clear()

    def kept_entries(self, entries):
        """The places of the entries of a collection that its where tests keep."""
        return kept(entries.tests, self.value_of, self.plan.units)

    # ---- the run ----------------------------------------------------------------------------------

    def prepare(self):
        """The values at the start, the checks of the setup, the size and the bounds of each store,
        the tolerances that the record keeps, and the instances of the ways of the connected sets
        at time 0: (the values, the sizes, the instances)."""
        plan = self.plan
        values = self.start()
        self.recorder.constants = values
        self.check()
        self.sizes = self.sizes_of(values)
        factor = plan.numerics.atol_factor
        outside = [
            name
            for name, value in plan.values.items()
            if value.kind == STATE
            and not value.boolean
            and isinstance(values.get(name), float | int)
            and not self.bounds[name][0] - factor * self.sizes.get(name, 0.0)
            <= values[name]
            <= self.bounds[name][1] + factor * self.sizes.get(name, 0.0)
        ]
        if outside:
            raise SimulationError(f'State bounds violated: {outside}')
        for name, size in self.sizes.items():
            self.recorder.tolerance[name] = factor * size
        for flow in plan.flows.values():
            self.tolerate(flow)
        self.started = True
        self.ways.build(plan.sets, self.env, 0.0)
        return values, self.sizes, list(self.ways.instances)

    def tolerate(self, flow):
        """The tolerance of what the network gives of a flow, which the record keeps: a rate's error
        over an hour moves what a store's tolerance allows; a served fraction is a number from zero
        to one."""
        factor = self.plan.numerics.atol_factor
        if flow.kind == LEGS:
            self.recorder.tolerance[f'{flow.name}.served_fraction'] = factor
            return
        size = max(self.sizes[end] for end in (flow.source, flow.sink) if end is not None)
        self.recorder.tolerance[f'{flow.name}.actual_rate'] = factor * size

    def run(self):
        """The record of the run."""
        try:
            self.prepare()
            self.moment.setup()
            self.loop()
        except (SimulationError, ExpressionError, ArithmeticError) as problem:
            return self.recorder.record(self.now, self.recorder.failure(self.now, str(problem)))
        return self.recorder.record(self.plan.horizon)

    def loop(self):
        """Moment after moment to the horizon, which is a moment too."""
        horizon = self.plan.horizon
        while self.now < horizon:
            t, touched = self.next_moment()
            self.moment.at(t, touched)
        self.ways.finish(horizon)

    def discrete(self):
        """The next time after now at which a stage is due, a trigger rearms or a keyed read by the
        time changes, or the horizon."""
        found = [self.plan.horizon, self.occurrences.next_due(), self.triggers.next_timer()]
        found += [at for at in self.key_times() if at > self.now]
        return min(at for at in found if at is not None)

    def key_times(self):
        """The key times inside the run of the keyed reads by the time that the run reads."""
        return sorted(self._keyed_at())

    def keyed_changes(self, t):
        """The keyed reads by the time whose value changes at time t, a key time."""
        return self._keyed_at().get(t, ())

    def _keyed_at(self):
        """{key time inside the run: the keyed reads by the time that change there}, made once."""
        if self._keyed is None:
            self._keyed = {}
            for name, keyed in self.plan.keyed.items():
                if keyed.by_time:
                    for at in self.stepped_of(name).times.tolist():
                        if 0 < at <= self.plan.horizon:
                            self._keyed.setdefault(float(at), []).append(name)
        return self._keyed

    def next_moment(self):
        """Run the ways to the next moment; gives its time and the engine names that changed in the
        ways at that time (an event of an instance that a condition or a set reads)."""
        limit = self.limit = float(self.discrete())
        while True:
            at, instance = self.ways.peek()
            at = float(at)
            contact = float(self.triggers.next_contact())
            moment = min(limit, contact)
            if contact < limit <= contact + self.plan.numerics.crossing:
                # Two moments nearer than the crossing tolerance are one (`Numerics.crossing`): a
                # contact just before a known moment is in it, where it holds within its tolerance.
                moment = limit
            if at < moment:
                self.now = at
                stores, rates, jumped = instance.step()
                changed = set(stores) | set(rates)
                if (jumped and self.triggers.reads_any(changed)) or self.ways.touched_by(rates):
                    self.ways.cut(at)
                    return at, changed
                self.triggers.predict(changed)
                continue
            self.now = moment
            # An event of an instance at the time of the moment puts its store on its bound, and the
            # moment's settling, after its stages, solves the set again (as the oracle settles once).
            changed = set()
            while at == moment:
                changed |= set(instance.snap())
                at, instance = self.ways.peek()
            self.ways.cut(moment)
            return moment, changed


def _known(value):
    """A value that an expression can read: an `Unavailable` one raises its reason (D7)."""
    if isinstance(value, Unavailable):
        raise ExpressionError(value.reason)
    return value
