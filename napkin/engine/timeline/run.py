"""One run of a plan: the values at the start, then moment after moment to the horizon, and the record.

1. **The start** evaluates each input, draw, link, stored value and captured request or capacity once,
   in the order of what it reads, across members (a formula, a reduction or a keyed read that one of
   them reads is evaluated there and then, at time 0). The order is found as the values are asked,
   with no recursion, so a chain through the rows of a large table is no limit: an evaluation that
   asks for a read that is not known yet waits while that read is computed (`Pending`, on the stack
   of `walk.walked`), so a side that its evaluation does not take is never read (`reads.py`). A draw is executed there,
   keyed by its site and its member (`chance.py`); each is an entry of the trace. An input that the configuration sets must lie in its admitted range. The entries that each `where`
   keeps are found from fixed values, once (`kept_of`), and so is the sorted index of the keys of
   each keyed read (`stepped_of`). Then each assertion over inputs is checked once; one that does not
   hold fails the run at the start, as an error of the setup that the plan found does.
2. **The sizes.** A store's size sets its absolute tolerance (`atol_factor` times it, D8): its
   `scale` when it declares one, else the largest of one of its unit, its start value, its finite
   bounds and the largest start value of the stores that flows connect it to. A store must start
   within its bounds. A store of an occurrence takes its size when the occurrence starts.
3. **Moments** (`moment.py`): the setup is round zero at time 0, after whose commit every connected
   set starts and the flows first settle; then, at each moment, rounds of stages, the settling of the
   sets that the round touched (`ways.py`), and the conditions (`triggers.py`). Occurrences are in `occurrences.py`.
4. **Between moments** each instance of a way runs its sets (`ways.py`). The next moment is the
   earliest of a stage that is due, a reset timer, a key time of a keyed read by the time, the
   horizon (`limit`) and the first contact of a watched condition or assertion; an event inside an
   instance (a store that reaches a bound, the end of a segment) before it is committed first, and
   is itself a moment when it changes what a watched condition or another set's setting reads. A
   known moment that is due at a contact or at such an event (`moment.Clock`) is one moment with it,
   at the time that the run knows exactly; there an event only puts its store on its bound, at its
   own time, and the moment's settling solves its set after the stages of the moment, as the oracle
   settles once. A flow present at a store of a finished occurrence carries no rate through each
   window up to the next event or moment (`Occurrences.carried`): the run fails where one does.
5. **The horizon** is an inclusive cutoff: the work due there settles as at any moment, by the
   clock's rule (`moment.Clock`): the last moment is the first at which the horizon is due, and the
   record holds the state that its last round committed. A value there reads as it does in a run
   that goes on (`ways.finish`): where something else is due at the horizon, a run that goes on has
   that moment too, and a set built there records its state with the rates that it settled; where
   the horizon is all (`bare`), the segments that end there hold their values in their pieces.

A stage reads its own direct writes first (`value`). A store follows its set between commits.
Formulas, reductions, keyed reads and dynamic reads use the values and members they read
(`_derived`, on the stack of `walk.walked`). A finished occurrence keeps its frozen formulas.
`changed_at` gives the time of a stored value's last change. Other stored values come from `env`.
A draw executes when an expression of a stage, an entry, a delay or a firing reads it (`truth`).

Every stage and firing reads the rates and results of the last sharing at its time (PLAN, change
27). This includes a flow from SOURCE to SINK. A flow that joins reads zero until the next sharing.
A flow that leaves keeps its last shared rate until then. Setup precedes the first sharing.

A run that fails stops there: its record holds the failure, as the last entry of its trace, and the
histories to the time at which it stopped, without the stage that failed. A run that a breakpoint
stops gives its checkpoint, whose record so far ends with a `pause` entry, and `resume` goes on in
place (`checkpoints.py`). A record that stops early gives no value after its stop (`Record.after`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace

import numpy as np

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...expressions import evaluate
from ...program.checkpoint import CheckpointError
from ...program.config import ConfigurationError
from ...program.record import Unavailable
from ..continuous.system import run_settings, step_cap
from ..continuous.walk import walked
from ..errors import SimulationError
from .chance import Chance
from .checkpoints import Breaks, Stopped
from .collections import dynamic_value, index_of, kept, looked_up, reduced
from .contacts import bound_values
from .moment import Clock, Defined, Moment, quantity, span
from .occurrences import Occurrences
from .plan import (
    CHANGED,
    DECLARED,
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
    Pending,
)
from .reads import lazily
from .record import HistoryFull, Recorder, remember
from .saved import restore
from .triggers import Triggers
from .ways import Ways

_MISSING = object()

# Reads in these phases use the preceding sharing. The settling itself reads the committed inputs.
UNSETTLED = ('stages', 'conditions')


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
    """A keyed read by the time with fixed keys (`Plan.stepped`): the engine name of the value of
    the member that it selects from each distinct key of its kept entries (`times`) to the next; it
    reads that value, as it is then. Below the first key it fails."""

    spelled: str
    times: np.ndarray
    names: tuple

    def place(self, t, incoming=False):
        """The place of the key interval of time t, or an ExpressionError below the first key."""
        place = int(np.searchsorted(self.times, t, side='left' if incoming else 'right')) - 1
        if place < 0:
            raise ExpressionError(f'{self.spelled}: no member has a key at or below {t:g}')
        return place

    def name_at(self, t, incoming=False):
        """The engine name of the value that the read selects at time t."""
        return self.names[self.place(t, incoming)]


class Run:
    """See the module. `breakpoints` stop the run (`checkpoints.py`)."""

    def __init__(self, plan, breakpoints=()):
        self.plan = plan
        self.cap = step_cap(plan.numerics)
        self.settings = run_settings(plan.numerics, self.cap)
        self.recorder = Recorder(plan, {}, {})
        self.recorder.run = self
        remember(plan)
        self.now = 0.0  # the time that the run has reached, for a failure
        self.env = {'t': 0.0}  # the values of the start, and later each value held between moments
        # The kept entries, the keyed reads by the time and the indexes of keys of the collections
        # (by name, and by the tuples that the reads of one collection share); the keys known.
        self._kept, self._stepped, self._indexes, self._known = {}, {}, {}, {}
        self.started = False  # once true, `value_of` reads the present
        self.written = {}  # a store of a set that a commit of this moment wrote, and its value
        self.frozen = {}  # a formula of a finished occurrence -> its value or `Unavailable` (D7)
        self.limit = plan.horizon  # the next moment that the run knows (`next_moment`)
        # Whether the last moment is the horizon and nothing else, which a longer run does not have
        # (`ways.finish`); a run stopped at a stage there is not.
        self.bare = False
        self.clock = Clock(plan)  # when something is due (`moment.Clock`)
        self._keyed = None  # {key time: the keyed reads by the time that change there}
        self._sources = (0, {})  # (how many dynamic reads the plan names, them by their collection)
        # Written names and changed collections, and the stores and flows due for rebuilding.
        self.published = {}  # plain answers of the last sharing, at the current moment
        self.arriving = False
        self.saved_arrival = None
        self.cut_at_resume = []
        self.opening_levels = {}
        self.contacts = ()
        self.prior_contacts = ()  # grouped switches whose located time is still ahead of the run
        self.bound_at = {}
        self.changed, self.moved = set(), set()
        self.joined, self.left = [], []  # the flows that join and that leave at this moment
        # The sets that wait for the settling of the setup: those of declared solvers, and those that
        # read their rates or results.
        self.waiting = []
        self.changes = {}  # a stored value -> the times of the commits that changed it (`elapsed`)
        self.checkpoint = None  # the checkpoint of a run stopped at a breakpoint, until `resume`
        self.breaks = Breaks(self, breakpoints)
        self.chance = Chance(self)
        self.ways = Ways(self)
        self.occurrences = Occurrences(self)
        self.triggers = Triggers(self)
        self.moment = Moment(self)

    # ---- the start --------------------------------------------------------------------------------

    def _missing(self, name):
        """The names that a reduction or a keyed read needs and that are not known yet: the tests of
        a collection before its members' values, and of a keyed read the keys of its kept entries and
        its key, then the value of the entry that it finds. Any other value asks for what it reads as
        its expression is evaluated (`_compute`): a branch that is not taken reads nothing, and a read
        that is not known yet stops the evaluation (`Pending`)."""
        plan, env = self.plan, self.env
        if name in plan.draws:
            return []
        value = plan.values[name]
        if value.kind == RATE or name in plan.shared:
            raise SimulationError(
                f'{name} is read before its flows first settle: a starting value reads it, and the '
                'rates settle after the setup; read it through a formula, or capture it in a stage'
            )
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
            if self._known.get(id(derived.keys)) is not derived.keys:
                reads = {derived.keys[k] for k in entries if isinstance(derived.keys[k], str)}
                missing = sorted(read for read in reads if read not in env)
                if missing:
                    return missing
                # The keys of this collection are known: the keyed reads that share it ask no more.
                self._known[id(derived.keys)] = derived.keys
            found = self._found(name)
            return [] if found is None or found in env else [found]
        return []

    def _found(self, name):
        """The engine name of the value that a keyed read finds at the start, or None."""
        keyed, entries = self.plan.keyed[name], self.kept_of(name)
        index = self._index(name)
        x = float(lazily(keyed.key, self.value_of, self.plan.units, 0.0))
        place = index.find(x)
        return None if place is None else keyed.names[entries[place]]

    def _compute(self, name):
        """The value of a name at the start, from the values known so far; `Pending` names a read
        that its evaluation asks for and that is not known yet."""
        plan, env = self.plan, self.env
        if name in plan.draws:
            return self.chance.draw(name)
        kind = plan.values[name].kind
        if kind == DYNAMIC:
            return self.value(name)
        if kind == CHANGED:
            return 0.0
        if kind == DESCRIBED:
            return self.chance.described(name)
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
                raise Pending(node.name)
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
        return walked(self._starting(name, set()))

    def _starting(self, name, waiting):
        """The computation of a starting value (`walk.walked`): after what it reads, each computed
        first on the driver's stack, and evaluated again once they are known (`Pending`). A read
        that waits already is one of the values that wait for this one: a cycle."""
        env = self.env
        waiting.add(name)
        while name not in env:
            missing = self._missing(name)
            if not missing:
                try:
                    env[name] = self._compute(name)
                    break
                except Pending as pending:
                    missing = pending.names
            for read in missing:
                if read in env:
                    continue
                if read in waiting:
                    raise SimulationError(f'{read}: a starting value that reads itself')
                yield self._starting(read, waiting)
        waiting.discard(name)
        return env[name]

    def classes_of(self, store, side, items, number):
        """The priority classes of an endpoint as the numbers of its flows (`number`): a flow that an
        item names is a class, a keyed projection gives a class for each distinct key, lower keys
        first, and the flows that no item names are the last class. The flows are those of `number`
        that are present: a set made again from a checkpoint saved after a flow joined its endpoint
        has the flows that it was built with, which the settling then builds again (`saved.py`)."""
        mine = [flow for flow in self.plan.ends[(store, side)].flows if flow in number]
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
        """The places of the entries that the where tests of a reduction or a keyed read keep: the
        tests read what is fixed for each member, so the reads of one collection share them."""
        found = self._kept.get(name)
        if found is None:
            derived = self.plan.reductions.get(name) or self.plan.keyed[name]
            shared = self._kept.get(id(derived.tests))
            if shared is None or shared[1] is not derived.tests:
                shared = self._kept[id(derived.tests)] = (
                    kept(derived.tests, self.value_of, self.plan.units),
                    derived.tests,
                )
            found = self._kept[name] = shared[0]
        return found

    def _index(self, name):
        """The index of the keys of a keyed read's kept entries at the start, which the keyed reads
        of one collection share."""
        found = self._indexes.get(name)
        if found is None:
            keyed = self.plan.keyed[name]
            shared = self._indexes.get((id(keyed.keys), id(keyed.tests)))
            if shared is None or shared[1] is not keyed.keys:
                made = index_of(keyed, self.value_of, self.plan.units, self.kept_of(name))[0]
                shared = self._indexes[(id(keyed.keys), id(keyed.tests))] = (made, keyed.keys)
            found = self._indexes[name] = shared[0]
        return found

    def index_for(self, name):
        """(the index of keys, the kept entries) of a keyed read whose keys the inputs fix, which holds
        for the whole run; None for one whose keys change, whose index is made at each read."""
        if not self.plan.fixed_keys(name):
            return None
        return self._index(name), self.kept_of(name)

    def stepped_of(self, name):
        """The stepped keyed read `name` (`Stepped`), from the keys of its kept entries."""
        if name not in self._stepped:
            keyed, entries, index = self.plan.keyed[name], self.kept_of(name), self._index(name)
            times = index.times()
            names = tuple(keyed.names[entries[index.find(key)]] for key in times.tolist())
            self._stepped[name] = Stepped(keyed.spelled, times, names)
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
                low = -math.inf if lower is None else lower
                high = math.inf if upper is None else upper
                raise ConfigurationError(
                    f'{name} = {quantity(plan, name, found)} is outside its admitted range '
                    f'{span(plan, name, low, high)}'
                )
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

    def value(self, name, t=None, tx=None, *, observations=None):
        """The value of an engine name now, or at a time t inside the present window of the ways (see
        the module); a stage's own writes (`tx`) first."""
        t = self.now if t is None else float(t)
        plan = self.plan
        found = plan.values.get(name)
        kind = found.kind if found is not None else None
        if (
            t == self.now
            and self.moment.phase in UNSETTLED
            and (kind in (RATE, RESULT) or name in plan.shared)
        ):
            if self.moment.phase == 'stages' and self.moment.round == 0:
                first = (
                    'its first solve'
                    if kind == RESULT or name.rsplit('.', 1)[0] in plan.solved_flows
                    else 'the flows first settle'
                )
                raise SimulationError(f'{name} is read before {first}: the setup reads it')
            if name in self.published:
                return self.ways.shared_value(name)
            if kind != RESULT:
                return 0.0  # a flow that this round added has not shared yet
        if tx is not None and name in tx.writes:
            value = tx.writes[name]
            if isinstance(value, Unavailable):
                raise ExpressionError(value.reason)
            if isinstance(value, Defined):  # a calculation that the stage gave the value
                return walked(self._derived(name, t, tx, {}, set(), observations=observations))
            return value
        if name == 't':
            return t
        if name in self.written:
            return self.written[name]
        if t == self.now and name in self.bound_at:
            return self.bound_at[name]
        if t == self.now and name in self.opening_levels:
            return self.opening_levels[name]
        if kind is None and name in plan.draws:
            return self.chance.draw(name, tx=tx)
        if kind == RATE:
            return self.ways.rate(name, t)
        if kind == RESULT:
            if name not in self.ways.result_of:
                raise SimulationError(f'{name} is read before its first solve')
            return self.ways.result(name, t)
        if kind == CHANGED:
            return self.changed_at(name, tx)
        if kind == DESCRIBED:
            return self.chance.described(name, tx)
        if kind == FORMULA:
            frozen = self.frozen.get(name)
            if frozen is not None:
                if isinstance(frozen, Unavailable):
                    raise ExpressionError(frozen.reason)
                return frozen
        if kind in (FORMULA, REDUCE, LOOKUP, DYNAMIC):
            return walked(self._derived(name, t, tx, {}, set(), observations=observations))
        if name in self.ways.set_of:
            return self.ways.value(name, t)
        try:
            return self.env[name]
        except KeyError:
            raise ExpressionError(f'{name} has no value yet') from None

    def _is_derived(self, name, tx):
        """Whether a value is computed from others where it is read: a formula (not frozen), a
        reduction, a keyed or a dynamic read, or a calculation that a stage gave it."""
        if tx is not None and name in tx.writes:
            return isinstance(tx.writes[name], Defined)
        if self.moment.phase in UNSETTLED and name in self.plan.shared:
            return False
        found = self.plan.values.get(name)
        kind = found.kind if found is not None else None
        return kind in (REDUCE, LOOKUP, DYNAMIC) or (kind == FORMULA and name not in self.frozen)

    def in_region(self, name, t, region):
        """Read a calculation on the branches selected for its segment."""
        found = self.plan.values.get(name)
        if name in region.defined or (
            found is not None and found.kind in (FORMULA, REDUCE, LOOKUP, DYNAMIC) and name not in self.frozen
        ):
            return walked(self._derived(name, t, None, {}, set(), region))
        return self.value(name, t)

    def _derived(self, name, t, tx, known, waiting, region=None, observations=None):
        """The value of a derived value (`_is_derived`) at time t, as a computation of `walk.walked`
        (re-audit 15): what it reads is read as its evaluation asks for it (`reads.py`), and each
        derived value among those that this read has not computed yet (`known`) is computed first,
        on the driver's stack, after which it is evaluated again with the reads that it made kept.
        A reduction, and a dynamic read of every member, asks for all its derived entries at once.
        `known` keeps each derived value of one read of the present, or the error that it raised,
        which a read of it raises again; a value that waits for itself (`waiting`) reads itself."""
        own = {}

        def read(each):
            found = own.get(each, _MISSING)
            if found is not _MISSING:
                return found
            if self._is_derived(each, tx) or (region is not None and each in region.defined):
                if each not in known:
                    raise Pending(each)
                found = known[each]
                if isinstance(found, _Failed):
                    raise found.problem
            else:
                found = self.value(each, t, tx)
            own[each] = found
            return found

        take = read
        if observations is not None:
            asked = observations.setdefault(name, {})

            def take(each):
                asked[each] = None
                return read(each)

        waiting.add(name)
        while True:
            try:
                found = self._evaluated(name, t, tx, take, known, region)
            except Pending as pending:
                for each in pending.names:
                    if each in known:
                        continue
                    if each in waiting:
                        raise SimulationError(f'{each}: a value that reads itself at t = {t:g} h') from None
                    try:
                        known[each] = yield self._derived(each, t, tx, known, waiting, region, observations)
                    except Exception as problem:  # raised where the evaluation reads it, as a call raises
                        known[each] = _Failed(problem)
                continue
            waiting.discard(name)
            return found

    def _evaluated(self, name, t, tx, read, known, region):
        """One evaluation of a derived value from `read` (`_derived`); a reduction or a dynamic read
        of every member first asks for those of its entries that this read has not computed."""
        plan = self.plan
        if tx is not None and name in tx.writes:
            return lazily(tx.writes[name].node, read, plan.units, t)
        value = plan.values[name]
        kind = value.kind
        if kind == FORMULA or (region is not None and name in region.defined):
            node = value.node if region is None else region.expression(value.node)
            return read(node.name) if isinstance(node, nodes.Ref) else lazily(node, read, plan.units, t)
        if kind == REDUCE:
            reduction, entries = plan.reductions[name], self.kept_of(name)
            if reduction.names is not None:
                self._ask((reduction.names[k] for k in entries), tx, known)
            return reduced(reduction, read, plan.units, entries)
        if kind == LOOKUP:
            entry = region.keyed(name) if region is not None else None
            if entry is not None:
                return read(entry)
            if plan.stepped(name):
                return read(self.stepped_of(name).name_at(t))
            return looked_up(plan.keyed[name], read, plan.units, t, self.index_for(name))
        dynamic = plan.dynamic[name]
        members = plan.members(dynamic.source)
        if dynamic.keep is None and dynamic.steps and dynamic.op not in ('at', 'latest'):
            self._ask((plan.project(point, dynamic.steps) for point in members), tx, known)
        return dynamic_value(dynamic, members, lambda point: plan.project(point, dynamic.steps), read, t)

    def _ask(self, names, tx, known):
        """Raise `Pending` for the derived names among `names` that the read in progress has not
        computed (`known`): a computation that reads them all asks for them at once, so a reduction
        over thousands of formulas is evaluated once, not once for each."""
        missing = [name for name in dict.fromkeys(names) if name not in known and self._is_derived(name, tx)]
        if missing:
            raise Pending(*missing)

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

    # ---- what a moment changes ---------------------------------------------------------------------

    def write(self, name, value):
        """A commit writes a value: a store of a set waits for the settling, any other value holds
        it from now on. A definition (`Defined`), and a number in place of a request's or a
        capacity's formula, changes what the value is from now on (`define`)."""
        plan = self.plan
        found = plan.values.get(name)  # none for a distribution-valued value
        if isinstance(value, Defined) or (found is not None and found.kind == FORMULA):
            self.define(name, value.node if isinstance(value, Defined) else None)
            if isinstance(value, Defined):
                return
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
            # `elapsed` restarts at a commit that changes the value.
            self.changes.setdefault(name, []).append(self.now)
            if name in plan.changed_of:
                self.changed.add(plan.changed_of[name])
        found = plan.values.get(name)
        owner = found.key.owner if found is not None and found.key is not None else ''
        if '#' in owner:
            receiver, event = owner.rsplit('#', 1)[0].rsplit('.', 1)
            self.changed.add(('occurrences', receiver, event))
        for end in plan.setting_ends(name):
            self.changed.add(('flows', *end))

    def define(self, name, node):
        """A commit gives a value a new definition: a formula's node, or None for a captured number
        in place of a formula (`Plan.define`). What reads the value is touched, so the sets that read
        it are built again and read it so; a record of some keys keeps what the new one reads."""
        plan = self.plan
        plan.define(name, node, self.now, plan.start_of(name))
        # The source of the node, an expression of a statement that a stage read, for `saved.py`.
        source = None if node is None else self.occurrences.sources[id(node)]
        plan.log.append(('define', name, source, self.now, plan.start_of(name)))
        self.changed.add(name)
        self.changed.update(self.recorder.defined(name))
        owner = plan.occurrence_of(name)
        if owner is not None:
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
        plan.log.append(('present', flow, joins))
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
        """Record zero for the departing flow's rate or fraction from this time on."""
        found = self.plan.flows[flow]
        name = f'{flow}.served_fraction' if found.kind == LEGS else f'{flow}.actual_rate'
        self.published[name] = 0.0
        for connection in found.connections:
            self.published[f'{connection.name}.actual_rate'] = 0.0
            for side, store in zip(('outflow', 'inflow'), (connection.source, connection.sink)):
                if store is not None and not self.plan.incident(store, side):
                    self.published[f'{store}.{side}.actual_rate'] = 0.0
        self.recorder.add(name, self.now, 0.0, 0.0)

    def changed_names(self):
        """The names that the settling must rebuild: the written and moving stores, rates and
        settings, and the reads of any collection whose membership or fields changed."""
        names = {item for item in self.changed if isinstance(item, str)} | set(self.written)
        sources = {item for item in self.changed if isinstance(item, tuple)}
        if sources:
            dynamic = self.plan.dynamic
            if self._sources[0] != len(dynamic):  # the plan names dynamic reads as the run reads them
                index = {}
                for name, found in dynamic.items():
                    index.setdefault(found.source, []).append(name)
                self._sources = (len(dynamic), index)
            names.update(name for source in sources for name in self._sources[1].get(source, ()))
        return names | self.moved

    def settled(self):
        """The changes of a round are settled."""
        self.written.clear()
        self.joined.clear()
        self.left.clear()
        self.changed.clear()
        self.moved.clear()

    def kept_entries(self, entries):
        """The places of the entries of a collection that its where tests keep."""
        return kept(entries.tests, self.value_of, self.plan.units)

    # ---- the run ----------------------------------------------------------------------------------

    def prepare(self, now=True):
        """The values at the start, the checks of the setup, the size and the bounds of each store,
        the tolerances that the record keeps, and the instances of the ways of the connected sets
        at time 0: (the values, the sizes, the instances). A run (`now` false) starts no set here:
        every set waits for the settling of the setup's commit, where the flows first settle, so that
        what local sharing has no answer for (a ring of stores) fails there, from the state that the
        setup leaves, as the oracle has it; `now` starts the sets at the start, for a reader of the run
        at its start (`dynamics/field.py`)."""
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
        if now:
            self.ways.build(self._now(plan.sets), self.env, 0.0)
        else:
            self.waiting = list(plan.sets)
        return values, self.sizes, list(self.ways.instances)

    def _now(self, sets):
        """The sets that start at the start, for a reader of the run there (`prepare`): those of no
        declared solver and that read none of their rates and results, which settle after the setup's
        commit (`waiting`)."""
        given = set()
        waiting = [connected for connected in sets if connected.way == DECLARED]
        for connected in waiting:
            given |= self._given(connected)
        while True:
            more = [connected for connected in sets if connected not in waiting and connected.rates & given]
            if not more:
                break
            waiting += more
            for connected in more:
                given |= self._given(connected)
        self.waiting = waiting
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
        sizes = [self.sizes[end] for end in (flow.source, flow.sink) if end is not None]
        if sizes:
            self.recorder.tolerance[f'{flow.name}.actual_rate'] = factor * max(sizes)

    def run(self):
        """The record of the run: to the horizon, or to the failure that stopped it; or the checkpoint
        of a breakpoint that stopped it (`checkpoints.py`), which holds the record so far."""
        return self._go(self._start)

    def resume(self):
        """Go on in place past the breakpoint that stopped the run: the stage that stopped runs again
        from its start with the draws that it made, and the edits made at its stops, and commits once
        (`checkpoints.py`). The record is the one of the run straight through, or of the run with the
        edits; or the checkpoint of the next stop."""
        if self.checkpoint is None:
            raise CheckpointError('the run waits at no stop')
        self.breaks.passing, self.checkpoint = self.checkpoint.stop.hit, None
        return self._go(self._resume)

    def edit(self, target, value):
        """Edit a stored value at the stop where the run waits (`checkpoint.Checkpoint.edit`), in
        place; gives the checkpoint with the edit, which a fresh process resumes as this run goes on."""
        if self.checkpoint is None:
            raise CheckpointError('the run waits at no stop')
        checkpoint = self.checkpoint.edit(target, value)
        self.breaks.edit(checkpoint)
        self.checkpoint = checkpoint
        return checkpoint

    @classmethod
    def restored(cls, plan, checkpoint):
        """The run of a plan that a checkpoint stopped, made again from its saved state (`saved.py`),
        waiting at its stop: `resume` goes on, `edit` edits."""
        made = cls(plan, checkpoint.breakpoints)
        restore(made, checkpoint.saved)
        made.breaks.restored(checkpoint)
        made.checkpoint = checkpoint
        return made

    def _start(self):
        self.prepare(now=False)
        self.moment.setup()

    def _resume(self):
        self.moment.resume()

    def _go(self, begin):
        try:
            begin()
            self.loop()
        except HistoryFull as full:
            return full.record
        except Stopped as stopped:
            # The draws that the stopped stage made are in the trace: the stage that runs again keeps them.
            self.chance.kept = {(site, owner) for site, owner, _ in self.chance.made}
            self.checkpoint = self.breaks.checkpoint(stopped.stop)
            return self.checkpoint
        except (SimulationError, ExpressionError, ArithmeticError) as problem:
            if self.arriving and self.moment.phase == 'stages':
                self.finish_arrival()
            return self.recorder.record(self.now, self.recorder.failure(self.now, str(problem)))
        return self.recorder.record(self.plan.horizon)

    def loop(self):
        """Moment after moment to the horizon, which is a moment too: the first moment at which it is
        due (`moment.Clock`)."""
        horizon = self.plan.horizon
        while not self.clock.due(horizon, self.now):
            moment = self.next_moment()
            self.recorder.check_budget(moment[0], before=True)
            self.moment.at(*moment)
        self.ways.finish(horizon, not self.bare)

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
        """The keyed reads by the time whose value changes at time t."""
        return self._keyed_at().get(t, ())

    def _keyed_at(self):
        """{key time inside the run: the keyed reads by the time that change there}, made once."""
        if self._keyed is None:
            self._keyed = {}
            for name in self.plan.keyed:
                if self.plan.stepped(name):
                    for at in self.stepped_of(name).times.tolist():
                        if 0 < at <= self.plan.horizon:
                            self._keyed.setdefault(float(at), []).append(name)
        return self._keyed

    def next_moment(self):
        """Run the ways to the next moment; gives its time, the engine names that changed in the
        ways at that time (an event of an instance that a condition or a set reads), the stores that
        met a bound there, at an event of an instance at the time of the moment, and the switches of
        rates that the ways' states reached there (`Ways.switched`)."""
        before = self.now
        limit = float(self.discrete())
        self.limit = self.clock.apart(limit)
        while True:
            at, instance = self.ways.peek()
            at = float(at)
            contact = float(self.triggers.next_contact())
            moment = min(limit, contact)
            if contact < limit and self.clock.within(contact, limit):
                # A known moment due at a contact is one moment with it (`moment.Clock`), at the time
                # that the run knows exactly: the contact holds there within its tolerance.
                moment = limit
            independent = not (
                at < moment
                and not self.clock.within(at, moment)
                and not instance.stores
                and any(instance.timing_events(at))
            )
            if not independent:
                moment = at  # a switch in an output rate cuts its suppliers' incoming segments here
            if at < moment and (
                not self.clock.within(at, moment) or not any(instance.timing_events(self.clock.apart(moment)))
            ):
                # A flow at a store of a finished occurrence carries no rate up to the event.
                self.occurrences.carried(self.now, at)
                self.now = at
                stores, rates, jumped = instance.step()
                self.recorder.check_budget(at)
                changed = set(stores) | set(rates)
                readers = self.ways.touched_outside(changed if jumped else rates, instance)
                if not jumped:
                    readers -= self.ways.followers  # these sets follow each smooth step of their suppliers
                if readers or (jumped and self.triggers.reads_any(changed)):
                    # The instance settled its event itself: no stage is due at its time.
                    self.ways.cut(at)
                    return at, changed, set(), self.ways.switched(at)
                flows = [
                    name.rsplit('.', 1)[0] for name in rates if name.rsplit('.', 1)[0] in self.plan.flows
                ]
                if jumped and flows and not self.ways.moving(self.ways.set_of[flows[0]]):
                    self.ways.publish(instance, at, flows=flows)
                self.triggers.predict(changed)
                continue
            self.occurrences.carried(self.now, moment)
            self.now = moment
            threshold = self.clock.apart(moment)
            if independent:
                for way in self.ways.instances:
                    way.lookahead(moment, threshold)
            self.contacts = tuple(
                sorted(
                    {
                        event
                        for way in self.ways.instances
                        if independent
                        for event in way.contacts_at(moment, threshold)
                    }
                )
            )
            self.ways.opening(moment)
            self.bound_at = bound_values(self.bounds, self.contacts)
            self.arriving = True
            self.bare = (
                moment == self.plan.horizon
                and not self.contacts
                and not self._besides(before, moment, contact)
            )
            return moment, set(), set(), set()

    def finish_arrival(self):
        """Commit incoming segments after the opening stages; grouped contacts use the moment's time."""
        if not self.arriving:
            return
        self.arriving = False
        if self.contacts or self.prior_contacts:
            self.prior_contacts = tuple(
                dict.fromkeys(
                    event
                    for event in (*self.prior_contacts, *self.contacts)
                    if event[0] > self.now and event[2].startswith('switch')
                )
            )
        if self.saved_arrival is not None:
            replaced = {self.ways.instances[k]: instance for k, _, instance in self.cut_at_resume}
            for k, keys, instance in self.cut_at_resume:
                self.ways.instances[k] = instance
                for key in keys:
                    self.ways.sets[key] = self.ways.sets[key][0], instance
            for key in self.ways.followers:
                inputs = self.ways.sets[key][1].following
                inputs.update((name, replaced[way]) for name, way in inputs.items() if way in replaced)
            self.moved.update(self.saved_arrival[1])
            self.saved_arrival = None
            self.cut_at_resume.clear()
            self.opening_levels.clear()
            return
        t = self.now
        through = self.clock.apart(t) if self.contacts else t
        for way in self.ways.cut_order():
            self.moved.update(way.arrive(t, through))
        self.moved.update(self.ways.switched(t))
        self.now = t

    def _besides(self, before, t, contact):
        """Whether a moment at time t is due for more than the horizon: a stage, a timer, a key time
        after `before` or a contact due there, so that a run that goes on has it too."""
        found = [self.occurrences.next_due(), self.triggers.next_timer(), contact]
        found += [at for at in self.key_times() if at > before]
        return any(at is not None and self.clock.due(at, t) for at in found)


class _Failed:
    """The error that a derived value raised where a read of the present computed it: a later read
    of it in that read raises it again (`Run._derived`)."""

    __slots__ = ('problem',)

    def __init__(self, problem):
        self.problem = problem


class _Known(Mapping):
    """The values known at the start, as an evaluation of a starting value reads them: a read that
    is not known yet raises `Pending`, so that the start computes it first."""

    __slots__ = ('env',)

    def __init__(self, env):
        self.env = env

    def __getitem__(self, name):
        try:
            return self.env[name]
        except KeyError:
            raise Pending(name) from None

    def __contains__(self, name):
        return True  # each read of the evaluation asks, so that an unknown one is named

    def __iter__(self):
        return iter(self.env)

    def __len__(self):
        return len(self.env)
