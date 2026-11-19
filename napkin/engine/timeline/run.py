"""One run of a plan: the values at the start, then moment after moment to the horizon, and the record.

1. **The start** evaluates each input, draw, link, stored value and captured request or capacity once,
   in the order of what it reads, across members (a formula, a reduction or a keyed read that one of
   them reads is evaluated there and then, at time 0). The order is found as the values are asked,
   with no recursion, so a chain through the rows of a large table is no limit: an evaluation that
   asks for a read that is not known yet waits while that read is computed (`_Unknown`), so a side
   that its evaluation does not take is never read (`reads.py`). A draw and a choice
   are executed there, keyed by their site and their member (`chance.py`); each is an entry of the
   trace. An input that the configuration sets must lie in its admitted range. The entries that each `where`
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
   earliest of a stage that is due, a reset timer, a key time of a keyed read by the time, a time at
   which a `delayed` read of a value that holds between moments changes (a commit that changed the
   value, plus the delay), the horizon (`limit`) and the first contact of a watched condition or
   assertion (a contact within the crossing
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
value), a reduction, a keyed read and a dynamic read of a collection from their members, the time
of the last change of a stored value at a commit (`changed_at`), the past of a stored value from the
pieces that the run recorded (`delayed`), and any other value from what the run holds between
moments (`env`). A stage reads its own writes first. A draw or a choice is executed when an
expression of a stage, an entry, a delay or a firing reads it (`truth`), which reads each name as
its evaluation asks for it.

A run that fails stops there: its record holds the failure, as the last entry of its trace, and the
histories to the time at which it stopped. A run that a player's choice pauses stops there too, with
a `pause` entry, and `resume` goes on in place (`chance.py`).
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace

import numpy as np

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...expressions import evaluate
from ...program.config import ConfigurationError
from ...program.record import Curve, Unavailable
from ..continuous.system import run_settings, step_cap
from ..errors import SimulationError
from .chance import Chance, Paused
from .collections import dynamic_value, index_of, kept, looked_up, reduced
from .moment import Moment
from .occurrences import Occurrences
from .plan import (
    CHANGED,
    DECLARED,
    DELAYED,
    DESCRIBED,
    DYNAMIC,
    FORMULA,
    LEGS,
    LOOKUP,
    RATE,
    REDUCE,
    RESULT,
    STARTS,
    STATE,
    Outside,
)
from .reads import lazily
from .record import Recorder, remember
from .triggers import Triggers
from .ways import Ways

_MISSING = object()


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
        # The sets that wait for the settling of the setup: those of declared solvers, and those that
        # read their rates or results; and what they give.
        self.waiting, self.waiting_names = [], set()
        self.changes = {}  # a stored value -> the times of the commits that changed it (`elapsed`)
        self.delayed_at = []  # (time, delayed read): when a `delayed` of a held value changes
        self.pause = None  # the `pause` entry of a paused run, until `resume`
        self.chance = Chance(self)
        self.ways = Ways(self)
        self.occurrences = Occurrences(self)
        self.triggers = Triggers(self)
        self.moment = Moment(self)

    # ---- the start --------------------------------------------------------------------------------

    def _missing(self, name):
        """The names that a reduction, a keyed read or a `delayed` read needs and that are not known
        yet: the tests of a collection before its members' values, and of a keyed read the keys of
        its kept entries and its key, then the value of the entry that it finds. Any other value asks
        for what it reads as its expression is evaluated (`_compute`): a branch that is not taken
        reads nothing, and a read that is not known yet stops the evaluation (`_Unknown`)."""
        plan, env = self.plan, self.env
        if name in plan.draws or name in plan.choices:
            return []
        value = plan.values[name]
        if value.kind == DELAYED:
            return sorted(read for read in plan.reads(name) if read not in env)
        if value.kind == RATE:
            raise Outside(f'{name}: a starting value that reads an actual rate (S2)')
        if value.kind == RESULT:
            raise SimulationError(f'{name} is read before its first solve: a starting value reads it')
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
            missing = sorted(read for read in reads if read not in env)
            if missing:
                return missing
            found = self._found(name)
            return [] if found is None or found in env else [found]
        return []

    def _found(self, name):
        """The engine name of the value that a keyed read finds at the start, or None."""
        keyed, entries = self.plan.keyed[name], self.kept_of(name)
        index = self._index(name)
        x = 0.0 if keyed.by_time else float(lazily(keyed.key, self.value_of, self.plan.units, 0.0))
        place = index.find(x)
        return None if place is None else keyed.names[entries[place]]

    def _compute(self, name):
        """The value of a name at the start, from the values known so far; `_Unknown` names a read
        that its evaluation asks for and that is not known yet."""
        plan, env = self.plan, self.env
        if name in plan.draws or name in plan.choices:
            return self.chance.produce(name)
        kind = plan.values[name].kind
        if kind == DYNAMIC:
            return self.value(name)
        if kind == CHANGED:
            return 0.0
        if kind == DESCRIBED:
            return self.chance.described(name)
        if kind == DELAYED:
            stored = plan.delays[name][0]
            if stored not in env:
                raise _Unknown(stored)
            return env[stored]  # at the start, the value at the start
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
            if node.name not in env:
                raise _Unknown(node.name)
            return env[node.name]  # a value that names another: no expression to compile
        return evaluate(node, _Known(env), plan.units)

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
        # Depth first, with no recursion: a value whose evaluation asks for a read that is not
        # known yet waits on the stack while that read is computed, and is evaluated again. A read
        # that waits already is one of the values that wait for this one: a cycle.
        stack, waiting = [name], set()
        while stack:
            top = stack[-1]
            if top in env:
                stack.pop()
                continue
            missing = self._missing(top)
            if not missing:
                try:
                    env[top] = self._compute(top)
                except _Unknown as unknown:
                    missing = [unknown.name]
                else:
                    stack.pop()
                    continue
            waiting.add(top)
            for read in missing:
                if read in waiting and read not in env:
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
            return float(lazily(node, self.value_of, plan.units, 0.0))

        self.bounds, self.scales = {}, {}
        for name, value in plan.values.items():
            if value.kind == DESCRIBED:
                self.value_of(name)  # recorded from its value at the start
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
            if not lazily(node, self.value_of, plan.units, 0.0):
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
        if kind is None and (name in plan.draws or name in plan.choices):
            return self.chance.produce(name, None, tx)  # executed: a node of a stage reads it once
        if kind == RATE:
            if self.moment.phase == 'stages':
                self.ways.fresh(name, tx)
            return self.ways.rate(name, t)
        if kind == RESULT:
            if self.moment.phase == 'stages' or name not in self.ways.result_of:
                self.ways.fresh(name, tx)
            return self.ways.result(name, t)
        if kind == CHANGED:
            return self.changed_at(name, tx)
        if kind == DELAYED:
            return self.delayed(name, t)
        if kind == DESCRIBED:
            return self.chance.described(name)
        if kind == FORMULA:
            frozen = self.frozen.get(name)
            if frozen is not None:
                if isinstance(frozen, Unavailable):
                    raise ExpressionError(frozen.reason)
                return frozen
            node = found.node
            if isinstance(node, nodes.Ref):
                return self.value(node.name, t, tx)
            return lazily(node, lambda read: self.value(read, t, tx), plan.units, t)
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
        """The value of a node over engine names now, through a stage's own writes. Each name is read
        when the evaluation asks for it, so a branch that is not taken executes no draw (`reads.py`)."""
        return lazily(node, lambda read: self.value(read, tx=tx), self.plan.units, self.now)

    def changed_at(self, name, tx=None):
        """The time at which a stored value last changed at a commit: of a write of this stage that
        differs from the committed value, now (R-A2-08); else of its last change, or its start."""
        stored = self.plan.changed[name]
        if tx is not None and stored in tx.writes and tx.writes[stored] != self.value(stored):
            return float(self.now)
        found = self.changes.get(stored)
        return found[-1] if found else self.changed_start(stored)

    def changed_start(self, stored):
        """The time from which a stored value exists: 0, or the start of its occurrence."""
        owner = self.plan.occurrence_of(stored)
        return 0.0 if owner is None else float(self.env[f'{owner}.started'])

    def delayed(self, name, t):
        """`delayed(x, d)` at time t: the committed value of x at t - d, from 0 (R-A2-09: with d = 0
        the committed value, never a stage's own write)."""
        stored, delay = self.plan.delays[name]
        d = lazily(delay, lambda read: self.value(read, t), self.plan.units, t)
        if isinstance(d, bool) or not isinstance(d, int | float) or not d >= 0:
            raise ExpressionError(f'{name}: the delay must be a duration that is not negative, not {d!r}')
        at = max(t - float(d), 0.0)
        if at >= self.now:
            return self.value(stored, at)
        return self.past(stored, at)

    def past(self, name, at):
        """The committed value of a stored value at a time before now, from what the run recorded: the
        last piece at or before it."""
        pieces = self.recorder.pieces.get(name, ())
        for t, value, rate in reversed(pieces):
            if t <= at:
                if isinstance(value, bool | str) or rate == 0:
                    return value
                if isinstance(rate, Curve):
                    return value + rate.increase(at - t)
                return value + rate * (at - t)
        if name in self.recorder.constants:
            return self.recorder.constants[name]
        raise ExpressionError(f'{name} has no value at {at:g} h')

    # ---- what a moment changes ---------------------------------------------------------------------

    def write(self, name, value):
        """A commit writes a value: a store of a set waits for the settling, any other value holds
        it from now on."""
        plan = self.plan
        if name in self.ways.set_of:
            old = self.value(name)
            self.written[name] = value
        else:
            old = self.env.get(name, _MISSING)
            self.env[name] = value
            self.recorder.add(name, self.now, value, 0.0)
        self.changed.add(name)
        for described in plan.described_of.get(name, ()):
            # A distribution that a stage replaced has a new mean and standard deviation.
            self.recorder.add(described, self.now, self.chance.described(described), 0.0)
            self.changed.add(described)
        if old != value:
            # `elapsed` restarts at a commit that changes the value, and a `delayed` read of it
            # changes when its delay has passed.
            self.changes.setdefault(name, []).append(self.now)
            if name in plan.changed_of:
                self.changed.add(plan.changed_of[name])
            for delayed in plan.delays_of.get(name, ()):
                self._delayed_change(delayed)
        found = plan.values.get(name)
        owner = found.key.owner if found is not None and found.key is not None else ''
        if '#' in owner:
            receiver, event = owner.rsplit('#', 1)[0].rsplit('.', 1)
            self.changed.add(('occurrences', receiver, event))
        for end in plan.setting_ends(name):
            self.changed.add(('flows', *end))

    def _delayed_change(self, name):
        """A `delayed` read of a value that a commit changed changes when its delay has passed: that
        time is a moment of the run (a delay that is not fixed has no such time)."""
        delay = self.plan.delays[name][1]
        if not self.plan.fixed_node(delay):
            return
        d = self.truth(delay)
        if not isinstance(d, bool) and isinstance(d, int | float) and d > 0:
            heapq.heappush(self.delayed_at, (self.now + float(d), name))

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
        self.started = plan.started = True
        self.ways.build(self._now(plan.sets), self.env, 0.0)
        return values, self.sizes, list(self.ways.instances)

    def _now(self, sets):
        """The sets that start before the setup: those of no declared solver and that read none of
        their rates and results, which settle after the setup's commit (`waiting`)."""
        given = set()
        waiting = [connected for connected in sets if connected.way == DECLARED]
        for connected in waiting:
            given |= self._given(connected)
        while True:
            more = [
                connected
                for connected in sets
                if connected not in waiting and connected.rates & given
            ]
            if not more:
                break
            waiting += more
            for connected in more:
                given |= self._given(connected)
        self.waiting, self.waiting_names = waiting, given
        return [connected for connected in sets if connected not in waiting]

    def _given(self, connected):
        names = {name for flow in connected.flows for name in self.plan.rates_of_flow(flow)}
        return names | set(connected.results)

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
        """The record of the run: to the horizon, to the failure that stopped it, or to the pause of
        a player's choice that no pick answers (`chance.py`)."""
        return self._go(self._start)

    def resume(self, *picks):
        """Answer the choice that a paused run waits for with picks (`config.Pick`) and go on in place:
        the paused stage runs again with the draws that it made, and commits once. The record is the
        one that a run with these picks in its configuration gives."""
        if self.pause is None:
            raise SimulationError('the run waits for no choice')
        for pick in picks:
            self.chance.picks[(pick.site, pick.occurrence)] = pick.value
        self.pause = None
        return self._go(self._resume)

    def _start(self):
        self.prepare()
        self.moment.setup()

    def _resume(self):
        self.moment.resume()

    def _go(self, begin):
        try:
            begin()
            self.loop()
        except Paused as paused:
            # The draws that the paused stage made are in the trace: a resumed stage keeps them.
            self.chance.kept = {(site, owner) for site, owner, _ in self.chance.made}
            self.pause = self.recorder.pause(self.now, paused)
            return self.recorder.record(self.now, pause=self.pause)
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
        """The next time after now at which a stage is due, a trigger rearms, a keyed read by the
        time changes or a `delayed` read of a held value does, or the horizon."""
        found = [self.plan.horizon, self.occurrences.next_due(), self.triggers.next_timer()]
        found += [at for at in self.key_times() if at > self.now]
        found += [at for at, _ in self.delayed_at[:1] if at > self.now]
        return min(at for at in found if at is not None)

    def key_times(self):
        """The key times inside the run of the keyed reads by the time that the run reads."""
        return sorted(self._keyed_at())

    def keyed_changes(self, t):
        """The keyed reads by the time, and the `delayed` reads, whose value changes at time t."""
        found = list(self._keyed_at().get(t, ()))
        while self.delayed_at and self.delayed_at[0][0] <= t:
            found.append(heapq.heappop(self.delayed_at)[1])
        return found

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


class _Unknown(Exception):
    """A read that the evaluation of a starting value asks for and that is not known yet."""

    def __init__(self, name):
        super().__init__(name)
        self.name = name


class _Known(Mapping):
    """The values known at the start, as an evaluation of a starting value reads them: a read that
    is not known yet raises `_Unknown`, so that the start computes it first."""

    __slots__ = ('env',)

    def __init__(self, env):
        self.env = env

    def __getitem__(self, name):
        try:
            return self.env[name]
        except KeyError:
            raise _Unknown(name) from None

    def __contains__(self, name):
        return True  # each read of the evaluation asks, so that an unknown one is named

    def __iter__(self):
        return iter(self.env)

    def __len__(self):
        return len(self.env)
