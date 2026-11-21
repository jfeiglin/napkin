"""The sparse integrator: a connected set whose rates move, of any size (D3), on one network, or
several sets that integrate together because the settings of one read the moving rates of another.

A set runs here when a request or a capacity of its flows or endpoints reads a store that moves (or
the time), and it is no component of the continuous engine (`plan.py`, `Connected.way`): it shares
stores between flows, has endpoint settings, has a route or a flow with legs, or holds more stores
than a component may. Its state is the vector of its stores; its rates at a time and a state are
the local sharing of the network (`network.Instant`) of what its connections and endpoints ask
there. One evaluation touches only the nonzeros: the settings are evaluated as arrays (`Vector`: a
formula that a template's members share is evaluated once over their rows, with
`napkin/core/arrays`), the sharing of the flows that meet no bound is one array operation, and the
change of each store is one product with the sparse incidence of the connections. A setting reads
only the sides that it takes (`reads.py`): a value that has none now (`since(e)` before the first
start) fails where an evaluation takes it, and a column with no value for a row that another row's
branch reads makes each row evaluate by itself. A route's signed
request may cross zero: its legs carry the positive parts of its rate, which stays continuous.

Sets that integrate together are levels: the settings of a level read the rates that the levels
before it give, and since the sets share no store, local sharing settles them level by level at each
time and state (the stores of the levels before a flow are in the pattern of what it reads). A keyed
read of the settings whose key or members move holds the member that it selects through a segment,
which ends where the read selects another, found to within the crossing tolerance.

SciPy's Radau integrates it step by step, with the sparse pattern of its Jacobian: the stores that the
settings of a flow read, joined across each coupled part. The flags of the bounds hold through a
segment, and a store held on a bound is read at its bound. A segment ends where a store reaches a
bound, or where a store held on a bound leaves it; the step is cut at that time, found in the step's
dense output to within the crossing tolerance of the run, the store is put on its bound, and a new
segment starts from there with its flags. A failure in an evaluation is timed at the step where it
happens. A failure of the solver, or `integrate.STALLED_STEPS` steps in a row each shorter than the
crossing tolerance, stops the run; where a setting reads a store through a condition, the failure
says that the rates chatter there and names the stores and the flows.

The recorder takes the pieces of the stores and of what the network gives of each flow (an actual
rate, a route's signed rate, a served fraction) that the record keeps, fitted step by step to the
step's dense output (`record.fitted`). Sets built at a horizon that is a moment of a run that goes
on too take their values there, with the flags that a new segment would find (`finish`): a read at
the horizon of a run that ends there is the read of a run that goes on, whose first step of the sets
starts there. A reader of a condition that watches the
stores reads the form of the next step (`motion`: the cubic of its dense output,
`continuous/dense.py`).
"""

from __future__ import annotations

import math

import numpy as np
import scipy.sparse as sp
from scipy.integrate import Radau

from ...core import arrays
from ...core import expr as nodes
from ...core.errors import ExpressionError
from ..continuous import dense, integrate
from ..errors import SimulationError
from .collections import combined, dynamic_value, looked_up, selected
from .contacts import put_bounds
from .lines import asked_of
from .network import ROUNDOFF, SIDES, Asked, Instant, network_of
from .plan import DYNAMIC, FORMULA, LOOKUP, REDUCE, Pending, _renamed
from .reads import Reads, lazily
from .record import fitted
from .region import Region, key_surfaces
from .way import Way

_MISSING = object()


class Vector:
    """The values of engine names at a time and a state of a set's stores, as arrays (see the
    module). `stores` are the names of the state, in its order; `held` gives, for a keyed read that
    an instance holds through its segment, the entry that it selects (`Sparse`). A value that holds
    between moments is read once, when it is first compiled or met (`constants`: its value, or the
    reason why it has none), or taken from `given`, the constants that a restored instance had
    (`saved.py`). A yes/no, an enum member or a text is held as it is, and an array that holds one
    holds objects.

    A derived value (a formula, a reduction, a keyed read) is computed where an evaluation reads it,
    with no recursion (re-audit 15), so a chain of formulas is no limit: one evaluation
    (`_Evaluation`) keeps the values that it computed, and a value that reads a derived one that it
    has not computed yet asks for it (`Pending`) and is computed again once it is known, as the
    driver of the timeline does (`walk.walked`). The members of a template that share a formula and
    that are asked together are computed together, over their rows."""

    def __init__(self, run, stores, held=None, rates=None, given=None, following=None, defined=()):
        self.run, self.plan = run, run.plan
        self.place = {name: k for k, name in enumerate(stores)}
        self.held = {} if held is None else held
        # The rates that the instance gives as it evaluates its levels: the rates of a level that a
        # later level reads, at the same time and state (`Sparse`).
        self.rates = {} if rates is None else rates
        self.given = given
        self.following, self.defined = following or {}, defined
        self.constants = {}  # name -> (value, None), or (nan, the reason why it has no value)
        self.branches = {}
        self.nodes, self.shapes = {}, {}
        self.formulas = {}  # the definitions this installed set shares, until rebuilt
        self._kinds = {}  # name -> how an evaluation gets it (`_kind`)
        self._plans = {}  # a tuple of names -> what an evaluation of them does (`_plan`)
        self._groups = {}  # members of a template -> their formula, columns and timed reads
        self._entries = {}  # a reduction -> its kept entries
        self._met = set()  # the names whose kinds a compile has found, with what they read

    def constant(self, name):
        """(the value now of a name that holds between moments, or nan, and None or the reason)."""
        if self.given is not None and name in self.given:
            found = self.given[name]
        else:
            try:
                value = self.run.value_of(name)
            except ExpressionError as problem:
                # A value that has none now (`since(e)` before the first start): what reads it fails
                # where its evaluation takes it, and no sooner.
                found = (math.nan, str(problem))
            else:
                plain = isinstance(value, bool | str) or not isinstance(value, int | float)
                found = (value if plain else float(value), None)
        self.constants[name] = found
        return found

    def _kind(self, name):
        """How an evaluation gets a name: a leaf (`store`, `rate` of an earlier level, `time`,
        `constant`, read once) or a derived value (`formula`, `member` of a template's shared
        formula, `reduction`, `stepped` keyed read by the time, `lookup`)."""
        found = self._kinds.get(name)
        if found is None:
            value = self.plan.values.get(name)
            kind = value.kind if value is not None else None
            if name in self.place:
                found = 'store'
            elif name in self.rates:
                found = 'rate'
            elif name == 't':
                found = 'time'
            elif name in self.following:
                found = 'trajectory'
            elif kind == FORMULA or (name in self.defined and value is not None and value.node is not None):
                self.formulas[name] = value
                found = 'member' if value.shape is not None else 'formula'
            elif kind == DYNAMIC and self.defined:
                dynamic = self.plan.dynamic[name]
                members = tuple(self.plan.members(dynamic.source))
                self._entries[name] = members  # the installed membership, until the next sharing
                found = 'dynamic'
            elif kind == REDUCE:
                found = 'reduction'
            elif kind == LOOKUP:
                found = 'stepped' if self.plan.stepped(name) else 'lookup'
            else:
                found = 'constant'
                if name not in self.constants:
                    self.constant(name)
            self._kinds[name] = found
        return found

    def derived(self, name):
        """Whether an evaluation computes a name from others."""
        return self._kind(name) in ('formula', 'member', 'reduction', 'stepped', 'lookup', 'dynamic')

    def compiled(self, names):
        """A function (t, y) -> the array of the values of `names`, in their order. Each value that
        they may read is met now, on an explicit stack, so that the constants are read when the
        instance is made (a keyed read that moves meets its members as it reads them)."""
        names = tuple(names)
        stack = [name for name in names if name not in self._met]
        while stack:
            name = stack.pop()
            if name in self._met:
                continue
            self._met.add(name)
            stack.extend(read for read in self._reads(name) if read not in self._met)
        plan = self._plan(names)

        def values(t, y):
            return self._gathered(plan, _Evaluation(self, t, y))

        return values

    def _reads(self, name):
        """What an evaluation of a derived value may read, which a compile meets."""
        plan, kind = self.plan, self._kind(name)
        if kind == 'formula':
            return sorted(nodes.names(self.formulas[name].node) - {'t'})
        if kind == 'member':
            return [bound for _, bound in self.formulas[name].binding if bound != 't']
        if kind == 'dynamic':
            dynamic = plan.dynamic[name]
            return (
                [plan.project(member, dynamic.steps) for member in self._entries[name]]
                if dynamic.steps
                else []
            )
        if kind == 'reduction':
            reduction = plan.reductions[name]
            return [] if reduction.names is None else [reduction.names[k] for k in self._kept(name)]
        if kind == 'stepped':
            return list(self.run.stepped_of(name).names)
        return []

    def _kept(self, name):
        """The kept entries of a reduction, found once."""
        found = self._entries.get(name)
        if found is None:
            found = self._entries[name] = self.run.kept_of(name)
        return found

    def _plan(self, names):
        """What an evaluation of a tuple of names does, made once: the places of the stores of the
        state and of the constants among them, and the other names, which it reads one by one."""
        found = self._plans.get(names)
        if found is None:
            unique = list(dict.fromkeys(names))
            position = {name: k for k, name in enumerate(unique)}
            held_at, held_from, constant_at, constants, failed, read_at, read = [], [], [], [], [], [], []
            for k, name in enumerate(unique):
                kind = self._kind(name)
                if kind == 'store':
                    held_at.append(k)
                    held_from.append(self.place[name])
                elif kind == 'constant':
                    value, reason = self.constants[name]
                    constant_at.append(k)
                    constants.append(value)
                    if reason is not None:
                        failed.append(reason)
                else:
                    read_at.append(k)
                    read.append(name)
            plain = any(isinstance(value, bool | str) for value in constants)
            kind = object if plain else float
            found = self._plans[names] = _Plan(
                np.array([position[name] for name in names], dtype=np.int64),
                len(unique),
                kind,
                np.array(held_at, dtype=np.int64),
                np.array(held_from, dtype=np.int64),
                np.array(constant_at, dtype=np.int64),
                np.array(constants, dtype=kind),
                tuple(failed),
                np.array(read_at, dtype=np.int64),
                tuple(read),
                tuple(name for name in read if self.derived(name)),
            )
        return found

    def _gathered(self, plan, evaluation, ask=False):
        """The array of the values of a plan's names in an evaluation: its derived values computed
        first, or, with `ask` (a column of a template's formula), asked for (`Pending`)."""
        if plan.failed:
            raise ExpressionError(plan.failed[0])
        found = np.empty(plan.size, dtype=plan.kind)
        found[plan.held_at] = evaluation.y[plan.held_from]
        found[plan.constant_at] = plan.constants
        if plan.read:
            if ask:
                evaluation.need(plan.derived)
            else:
                evaluation.compute(plan.derived, plan)
            found[plan.read_at] = [evaluation.read(name) for name in plan.read]
        return found[plan.back]

    def _reader(self):
        """A function (name, t, y) -> its value: a keyed read reads its key and the member that it
        selects, not every member."""

        def read(name, t, y):
            return _plain(self.compiled([name])(t, y)[0])

        return read

    def choose(self, signs):
        """Keep branch choices only on expressions that read their switching operands."""
        if signs == self.branches:
            return
        self.branches = signs
        self.nodes, self.shapes = {}, {}
        self._groups.clear()
        for plan in self._plans.values():
            plan.order = None  # groups of rows can split or join when their selected expressions change
        if signs:
            for name, definition in self.formulas.items():
                node = integrate.branch_expression(definition.node, signs)
                if node is not definition.node:
                    self.nodes[name] = node
                    if definition.shape is not None:
                        places = {bound: nodes.ref(read) for read, bound in definition.binding}
                        self.shapes[name] = _renamed(node, places)

    def shape(self, name):
        return self.shapes.get(name, self.formulas[name].shape)

    def one(self, name, evaluation):
        """A derived value by itself, from what `evaluation` holds (`Pending` for what it has not
        computed): a formula reads only the sides that it takes (`reads.py`)."""
        plan, kind, t = self.plan, self._kind(name), evaluation.t
        if kind in ('formula', 'member'):
            return float(
                lazily(self.nodes.get(name, self.formulas[name].node), evaluation.read, plan.units, t)
            )
        if kind == 'dynamic':
            dynamic = plan.dynamic[name]
            return dynamic_value(
                dynamic, self._entries[name], lambda m: plan.project(m, dynamic.steps), evaluation.read, t
            )
        if kind == 'reduction':
            reduction, entries = plan.reductions[name], self._kept(name)
            if reduction.names is None:
                return float(combined(reduction.op, [None] * len(entries), reduction.spelled))
            names = [reduction.names[k] for k in entries]
            evaluation.need(names)
            return float(combined(reduction.op, [evaluation.read(each) for each in names], reduction.spelled))
        if kind == 'stepped':
            stepped = self.run.stepped_of(name)
            selected_at = self.held.get(name, t)
            return evaluation.read(stepped.name_at(selected_at))
        keyed = plan.keyed[name]
        if name in self.held:
            # The entry that the instance holds through its segment.
            entry = self.held[name]
            if entry is None:
                x = float(lazily(keyed.key, evaluation.read, plan.units, t))
                raise ExpressionError(f'{keyed.spelled}: no member has a key at or below {x:g}')
            return evaluation.read(keyed.names[entry])
        return float(looked_up(keyed, evaluation.read, plan.units, t, self.run.index_for(name)))

    def group(self, members, evaluation):
        """The members of a template that share one formula, evaluated once over their rows: each
        column of what it reads is made when the evaluation over the rows first reads it
        (`reads.py`), its derived values asked for (`Pending`)."""
        found = self._groups.get(members)
        if found is None:
            shape = self.shape(members[0])
            reads = sorted(nodes.names(shape))
            columns = {
                read: tuple(dict(self.formulas[name].binding)[read] for name in members) for read in reads
            }
            timed = frozenset(read for read, column in columns.items() if all(name == 't' for name in column))
            found = self._groups[members] = (shape, columns, timed)
        shape, columns, timed = found
        t = evaluation.t

        def column(read):
            if read in timed:
                return float(t)
            return self._gathered(self._plan(columns[read]), evaluation, ask=True)

        values = arrays.values(
            shape, Reads(frozenset(columns), column), self.plan.units, len(members), columns, evaluation.read
        )
        return np.broadcast_to(np.asarray(values, dtype=float), (len(members),)).tolist()


class _Plan:
    """What an evaluation of a tuple of names does (`Vector._plan`): the place of each name among
    the distinct ones (`back`), how many and of what kind they are, the places of the stores and
    where the state holds them, the places and the values of the constants and the reasons of those
    that have none, and the places of the other names, which an evaluation reads one by one, with
    the derived ones among them; and the tasks that its first evaluation completed, in their order
    (`order`), which a later one runs first (`_Evaluation.compute`)."""

    __slots__ = (
        'back',
        'constant_at',
        'constants',
        'derived',
        'failed',
        'held_at',
        'held_from',
        'kind',
        'order',
        'read',
        'read_at',
        'size',
    )

    def __init__(
        self, back, size, kind, held_at, held_from, constant_at, constants, failed, read_at, read, derived
    ):
        self.back, self.size, self.kind = back, size, kind
        self.held_at, self.held_from = held_at, held_from
        self.constant_at, self.constants, self.failed = constant_at, constants, failed
        self.read_at, self.read, self.derived = read_at, read, derived
        self.order = None


class _Failed:
    """The error that a derived value raised in an evaluation: a read of it raises it again."""

    __slots__ = ('problem',)

    def __init__(self, problem):
        self.problem = problem


class _Evaluation:
    """One evaluation of a vector at a time `t` and a state `y` (see `Vector`): the derived values
    that it computed, each once, or the error that each raised, which a read of it raises again."""

    __slots__ = ('known', 't', 'vector', 'y')

    def __init__(self, vector, t, y):
        self.vector, self.t, self.y = vector, t, y
        self.known = {}

    def read(self, name):
        """The value of a name: a leaf at once, a derived value that this evaluation computed, or
        `Pending` for one that it has not."""
        vector = self.vector
        kind = vector._kind(name)
        if kind == 'store':
            return float(self.y[vector.place[name]])
        if kind == 'constant':
            value, reason = vector.constants[name]
            if reason is not None:
                raise ExpressionError(reason)
            return value
        if kind == 'rate':
            return vector.rates[name]
        if kind == 'trajectory':
            way = vector.following[name]
            if name in way.stores or name in vector.run.ways.result_of:
                return way.level_at(name, self.t)
            return way.rate_at(name, self.t)
        if kind == 'time':
            return float(self.t)
        found = self.known.get(name, _MISSING)
        if found is _MISSING:
            raise Pending(name)
        if isinstance(found, _Failed):
            raise found.problem
        return found

    def need(self, names):
        """`Pending` for the derived names among `names` that this evaluation has not computed: a
        value that reads them all asks for them at once."""
        missing = [
            name for name in dict.fromkeys(names) if name not in self.known and self.vector.derived(name)
        ]
        if missing:
            raise Pending(*missing)

    def compute(self, names, plan=None):
        """Each of the derived names `names` that this evaluation has not computed, each after what
        it reads, with no recursion. A task is the members of a template that share a formula,
        computed together over their rows, or a value by itself; the stack holds the path of tasks
        from the first to the one that runs, and a task that asks for values not known yet waits
        while it runs their tasks one after the other, then runs again. A value that a task on the
        path holds is computed by itself, and one asked for on the path of its own computation
        reads itself, which a plan refuses (a guard).

        The first evaluation of a `plan` keeps the tasks that it completed, in their order; a later
        one runs them in that order first, so that each finds what it reads, and leaves to the
        stack a task that asks for more (a branch that it did not take before). A value that it so
        computes and does not read fails nothing: its error is raised where a read takes it."""
        vector = self.vector
        if plan is not None and plan.order is not None:
            for task in plan.order:
                if all(name in self.known for name in task):
                    continue
                try:
                    if len(task) == 1:
                        self.known[task[0]] = vector.one(task[0], self)
                    else:
                        self.known.update(zip(task, vector.group(task, self)))
                except Pending:
                    continue
                except Exception as problem:  # raised where a read of it takes it, as a call raises
                    if len(task) == 1:
                        self.known[task[0]] = _Failed(problem)
        completed = [] if plan is not None and plan.order is None else None
        holding, alone = {}, set()  # the names of the tasks on the path; those of a value by itself

        def tasks(missing):
            """The tasks of the names `missing`, in the order in which they run (popped last first)."""
            found, grouped = [], {}
            for name in missing:
                if name in holding or vector._kind(name) != 'member':
                    found.append((name,))
                else:
                    grouped.setdefault(vector.shape(name), []).append(name)
            found += [tuple(members) for members in grouped.values()]
            return found[::-1]

        def enter(task):
            if len(task) == 1:
                if task[0] in alone:
                    raise SimulationError(f'{task[0]}: a value that reads itself at t = {self.t:g} h')
                alone.add(task[0])
            for name in task:
                holding[name] = holding.get(name, 0) + 1
            stack.append([task, []])

        def leave():
            task, _ = stack.pop()
            for name in task:
                holding[name] -= 1
                if not holding[name]:
                    del holding[name]
            if len(task) == 1:
                alone.discard(task[0])

        missing = [name for name in dict.fromkeys(names) if name not in self.known and vector.derived(name)]
        stack = [[(), tasks(missing)]]  # the first entry holds no task of its own
        while stack:
            entry = stack[-1]
            task, waiting = entry
            while waiting and all(name in self.known for name in waiting[-1]):
                waiting.pop()
            if waiting:
                enter(waiting.pop())
                continue
            if not task:
                stack.pop()
                continue
            if all(name in self.known for name in task):
                leave()
                continue
            try:
                if len(task) == 1:
                    self.known[task[0]] = vector.one(task[0], self)
                else:
                    self.known.update(zip(task, vector.group(task, self)))
            except Pending as pending:
                entry[1] = tasks(
                    [
                        name
                        for name in dict.fromkeys(pending.names)
                        if name not in self.known and vector.derived(name)
                    ]
                )
                continue
            except Exception as problem:  # raised where a read of it takes it, as a call raises
                if len(task) > 1:
                    # A column with no value for some member, which another member's branch reads:
                    # each member by itself reads only its own branch.
                    entry[1] = [(name,) for name in reversed(task) if name not in self.known]
                    continue
                self.known[task[0]] = _Failed(problem)
            if completed is not None:
                completed.append(task)
            leave()
        if completed is not None:
            plan.order = tuple(completed)


def _plain(value):
    """A value of an array as a Python value: a number as a float, a yes/no, an enum member or a text
    as it is."""
    return value if isinstance(value, bool | str) else float(value)


class Sparse(Way):
    """Connected sets on the sparse integrator from the time `t` on (see the module), a way of a run
    (`ways.py`): one set, or the sets of `sets` in the order of their levels (`levels`), where the
    settings of a set read the rates of a set of an earlier level that move, so that they integrate
    together. Each step of the solver is made when the run first asks for its end (`peek`), as far as
    the next moment that the run knows (`run.limit`), and committed when the run reaches its end
    (`step`), or cut at a moment inside it (`cut`)."""

    def __init__(self, run, sets, values, t, key, levels=None, given=None):
        plan = self.plan = run.plan
        sets = list(sets)
        levels = [0] * len(sets) if levels is None else list(levels)
        self.sets, self.set_levels = sets, levels  # which a checkpoint names (`saved.py`)
        self.key, self.alive = key, True
        self.solver, self.pending = None, None
        self._drift = None  # the rates of the stores at the present state, once read (`drift`)
        self.run, self.recorder = run, run.recorder
        stores = [store for connected in sets for store in connected.stores]
        place = self.place = {name: k for k, name in enumerate(stores)}
        self.net, connections, self.recorded = network_of(run, sets, stores)
        self.stores, self.flows = stores, list(self.net.flows)
        self.stepped = frozenset(name for connected in sets for name in connected.stepped)
        self.capped = [k for k, connection in enumerate(connections) if connection.capacity is not None]
        self.end_settings = []  # (side, store, which)
        names = [connection.request for connection in connections]
        names += [connections[k].capacity for k in self.capped]
        # The level of each setting: of its connection's set, or of its endpoint's store's set.
        level_of = [levels[int(k)] for k in self.net.flow_sets.tolist()]
        level_of += [level_of[k] for k in self.capped]
        for (store, side), end in plan.ends.items():
            if store in place:
                for which in ('request', 'capacity'):
                    if getattr(end, which) is not None:
                        self.end_settings.append((SIDES.index(side), place[store], which))
                        names.append(getattr(end, which))
                        level_of.append(levels[int(self.net.store_sets[place[store]])])
        # A keyed read of the settings that moves holds the entry that it selects through a
        # segment, which ends where it selects another (`_switch`). The rates of a level that a later
        # level reads are those of this evaluation (`current`).
        self.selection, self.current = {}, {}
        earlier = [name for k, name in enumerate(self.recorded) if levels[self._set_of_flow(k)] < max(levels)]
        self.current.update(dict.fromkeys(earlier, 0.0))
        # An empty state reads the installed steps of its producers, including declared answers.
        # No source changes integrator or gains another stock merely because a pipe reads its value.
        self.following = {}
        if not stores:
            ways = run.ways
            for name in sets[0].rates:
                key_of = ways.set_of.get(name, ways.result_of.get(name))
                if key_of is None:
                    key_of = ways.set_of.get(name.rsplit('.', 1)[0])
                if key_of is not None and (name in plan.moving or ways.moving(key_of)):
                    self.following[name] = ways.sets[key_of][1]
        defined = [name for name in self.recorded if not stores and plan.values[name].node is not None]
        formulas = {name for connected in sets for name in connected.formulas}
        vector = self.vector = Vector(
            run,
            stores,
            self.selection,
            self.current,
            given,
            self.following,
            {name for name in formulas if plan._is_rate(name)} | set(defined),
        )
        self.outputs = vector.compiled(defined) if defined else None
        self.held_rates = set()
        self.selected = False

        self.setting_names = tuple(names)
        self.settings = vector.compiled(names)
        self.size = len(names)
        # Each level: the places of its settings, their values, and the rates that it gives.
        self.levels = []
        if max(levels) > 0:
            for level in sorted(set(levels)):
                at = [k for k, found in enumerate(level_of) if found == level]
                gives = [
                    (k, name) for k, name in enumerate(self.recorded) if levels[self._set_of_flow(k)] == level
                ]
                self.levels.append(
                    (np.array(at, dtype=np.int64), vector.compiled([names[k] for k in at]), gives)
                )
        self.y = np.array([float(values[name]) for name in stores])
        self.lower = np.array([run.bounds[name][0] for name in stores])
        self.upper = np.array([run.bounds[name][1] for name in stores])
        # Radau already scales its relative term with the current inventory. The absolute
        # floor belongs to the unit and must be the same when this instance is restored.
        self.atol = np.array([run.amount_tolerance(name) for name in stores])
        self.t = float(t)
        net = self.net
        self.incidence = sp.csr_array(
            (
                np.r_[-np.ones(np.sum(net.source >= 0)), np.ones(np.sum(net.sink >= 0))],
                (
                    np.r_[net.source[net.source >= 0], net.sink[net.sink >= 0]],
                    np.r_[np.flatnonzero(net.source >= 0), np.flatnonzero(net.sink >= 0)],
                ),
            ),
            shape=(len(stores), len(connections)),
        )
        self.traffic = abs(self.incidence)
        # The stores that the settings of each flow read, and those of the endpoints at its ends; a
        # flow whose settings read the rates of an earlier level reads its stores too.
        self.reads = []
        for f, flow in enumerate(self.flows):
            found = plan.settings_reads(plan.flows[flow])
            mine = {place[name] for name in found.leaves if name in place}
            level = levels[self._set_of_flow(f)]
            if level > 0:
                mine |= {k for k in range(len(stores)) if levels[int(self.net.store_sets[k])] < level}
            self.reads.append(sorted(mine))
        self.evaluations = 0
        self.lower_flags = np.zeros(len(stores), dtype=bool)
        self.upper_flags = np.zeros(len(stores), dtype=bool)
        wanted = run.recorder.wanted
        self.kept_stores = [k for k, name in enumerate(stores) if wanted(name)]
        self.kept_flows = [k for k, name in enumerate(self.recorded) if wanted(name)]
        # The stores of the set that a setting reads through a condition, with those flows.
        self.switches = {}
        for f in self.flows:
            for store in self._conditioned(plan.settings_of(plan.flows[f])):
                if store in place:
                    self.switches.setdefault(store, []).append(f)
        self.brief, self.brief_from = 0, None  # the steps in a row shorter than a moment (`_count`)
        self.switching = [
            (name, self._selector(vector, plan.keyed[name]))
            for name in sorted(plan.expansion_of(names).leaves)
            if name in plan.keyed and not plan.stepped(name) and plan.lookup_moves(name, place)
        ]
        # The switching surfaces of the settings (`integrate.surfaces_of`), as a component has them:
        # a step starts on the far side of one that its state crosses there (`_sides`), ends where
        # one changes side (`_turns`), and a moment at the end of a step finds the ones that it
        # reached there (`switched_at`). A surface's sides are read through their names.
        formulas = {
            name: plan.values[name].node
            for name in formulas
            if getattr(plan.values.get(name), 'node', None) is not None
        }

        def moves(node):
            found = plan.expansion(node)
            if stores and vector.defined:
                found = plan.field_inputs(found)
            return found.time or any(
                leaf in place or leaf in self.current or leaf in self.following for leaf in found.leaves
            )

        def nodes_of(settings):
            return [
                plan.values[name].node
                for name in settings
                if getattr(plan.values.get(name), 'node', None) is not None
            ]

        self.moves = moves
        surfaces = integrate.surfaces_of(nodes_of([*names, *defined]), formulas, moves)
        self.region = Region(
            surfaces, key_surfaces(plan, plan.expansion_of(names).leaves, moves) if defined else {}
        )
        self.surfaces = self.region.surfaces
        self.deciding = integrate.flow_switches(
            ((name, nodes_of(plan.settings_of(plan.flows[name]))) for name in self.flows), formulas, moves
        )
        self.labels = {}
        if not stores:
            from .triggers import _affine

            for pair in self.surfaces:
                a, b = pair
                found = plan.expansion_of(set(nodes.names(a)) | set(nodes.names(b)))
                moving = found.leaves & self.following.keys()
                affine = (
                    moving <= plan.moving and _affine(a, plan.moving, plan) and _affine(b, plan.moving, plan)
                )
                if found.time:
                    moving = moving | {'t'}
                self.labels[pair] = (moving, affine, f'switch ({nodes.text(a)}, {nodes.text(b)})')
                self.deciding[pair] = list(self.flows)
        sided = {name for a, b in self.surfaces for name in (*nodes.names(a), *nodes.names(b))}
        self.switch_layers = integrate.switch_layers(self.surfaces, formulas)
        self.sided = sorted(sided - {'t'})
        self._sides_of = vector.compiled(self.sided) if self.sided else None
        self.sides, self.clock = (), None  # the far sides that the present step reads (`_sides`)
        self.signs = {}  # the side of each switch that the present step holds (`_turns`)
        self.contact_clocks = run.consumed_in(self.surfaces, t)
        self.contacted = tuple(self.contact_clocks)
        self.contacts = []  # located contacts on the pending smooth step
        self.next_clock = math.inf  # the next switch of the time against a fixed value

    def _selector(self, vector, keyed):
        """A function (t, y) -> the entry that a keyed read selects there (None below its first
        key), from what its key, its members' keys and their tests read."""
        plan = self.plan
        index, read = self.run.index_for(keyed.name), vector._reader()

        def select(t, y):
            return selected(keyed, lambda name: read(name, t, y), plan.units, t, index)

        return select

    def _select(self):
        """At the start of a segment: each keyed read that moves holds the entry that it selects."""
        y = np.minimum(np.maximum(self.y, self.lower), self.upper)
        self.selection.clear()
        self.selection.update(dict.fromkeys(self.stepped, self.t))
        for name, select in self.switching:
            self.selection[name] = select(self.t, y)

    def _switch(self, solution, start, end, name, select):
        """The first time in (start, end] at which a keyed read selects another entry than the one
        that it holds through the segment, to within the crossing tolerance; or None. Here the
        observation is the selected row identity, including filters and ranking. A numeric key
        surface exposed by a moving segment is located with the other operands in `_turns`."""
        held = self.selection[name]
        if select(end, solution(end)) == held:
            return None
        crossing = self.plan.numerics.crossing
        left, right = start, end
        while right - left > crossing:
            middle = 0.5 * (left + right)
            if select(middle, solution(middle)) == held:
                left = middle
            else:
                right = middle
        return right

    def _conditioned(self, names):
        """The stores that the settings `names` read through a comparison, a membership or an
        if/else."""
        plan, found = self.plan, set()
        for name in names:
            for formula in plan.expanded(name).formulas | {name}:
                node = getattr(plan.values.get(formula), 'node', None)
                switches = node is not None and any(
                    isinstance(part, (nodes.IfElse, nodes.Compare)) or nodes.membership(part) is not None
                    for part in nodes.walk(node)
                )
                if switches:
                    found |= plan.expanded(formula).leaves & plan.moving
        return found

    def _set_of_flow(self, f):
        """The place in `sets` of the set of the flow `f`."""
        return int(self.net.flow_sets[int(self.net.first[f]) if not self.net.plain else f])

    # ---- the field --------------------------------------------------------------------------------

    def asked(self, t, y):
        """What the connections and the endpoints ask at time t and state y."""
        return self._asked(self.settings(t, y), t, y)

    def _asked(self, found, t, y):
        """What the connections and the endpoints ask, from the values of their settings."""
        count, size = len(self.stores), len(self.net.source)
        if self.vector.nodes and np.any(found < 0):
            # A smooth continuation of max(0, x) can be negative outside the current
            # segment. Local sharing has a zero floor on service. Keep its floor there
            # only when the authored setting is valid at the trial state.
            vector = self.vector
            held = vector.nodes, vector.shapes, vector._groups
            try:
                vector.nodes, vector.shapes, vector._groups = {}, {}, {}
                read = vector._reader()
                for k in np.flatnonzero(found < 0):
                    if read(self.setting_names[k], t, y) >= 0:
                        found[k] = 0.0
            finally:
                vector.nodes, vector.shapes, vector._groups = held
        request = asked_of(self.net, found[:size], t)
        capacity = np.full(size, math.inf)
        capacity[self.capped] = found[size : size + len(self.capped)]
        end_request, end_capacity = np.zeros((2, count)), np.full((2, count), math.inf)
        for (side, s, which), number in zip(self.end_settings, found[size + len(self.capped) :].tolist()):
            (end_request if which == 'request' else end_capacity)[side, s] = number
        if (
            np.isnan(found).any()
            or ((capacity < 0) & ~self.net.free_pipe).any()
            or (end_capacity < 0).any()
            or not (np.isfinite(end_request) & (end_request >= 0)).all()
        ):
            raise SimulationError(f'{self.stores[0]}: a capacity or a request below zero at {t:g} h')
        return Asked(request, capacity, end_request, end_capacity)

    sample_on_read = True

    def answers_at(self, t, incoming, flows):
        pending = self.pending
        y = self.y if pending is None else pending[2](t)
        evaluations = self.evaluations
        try:
            if not incoming:
                self._start()
            primary, carried = self.values(t, y)
        finally:
            self.evaluations = evaluations
        answers = dict(zip(self.recorded, map(float, primary)))
        if not self.net.plain:
            answers.update(
                (f'{name}.actual_rate', float(number)) for name, number in zip(self.net.connections, carried)
            )
        return answers

    def values(self, t, y):
        """What the network gives of each flow at time t and state y, with the flags of the segment,
        and the rate of each connection."""
        self.evaluations += 1
        if self.evaluations > self.plan.numerics.max_evaluations:
            raise SimulationError('Numerical evaluation budget exceeded')
        t, trial = self._held(t, y)
        if self.outputs is not None:
            values = self.outputs(t, trial)
            return values, values
        if not self.levels:
            asked = self.asked(t, trial)
            values = Instant(self.net, asked, self.lower_flags, self.upper_flags).values()
            return values, self.net.carried(values, asked)
        # Level by level: the sets share no store, so the local sharing of a level is its own, and
        # the settings of the next read the rates that it gave (the later ones ask nothing yet).
        found = np.zeros(self.size)
        for at, settings, gives in self.levels:
            found[at] = settings(t, trial)
            asked = self._asked(found, t, trial)
            values = Instant(self.net, asked, self.lower_flags, self.upper_flags).values()
            for k, name in gives:
                if name in self.current:
                    self.current[name] = float(values[k])
        return values, self.net.carried(values, asked)

    def field(self, t, y):
        carried = self.values(t, y)[1]
        change = self.incidence @ carried
        held = self.lower_flags | self.upper_flags
        if held.any():
            # On a held face, proportional shares can sum a last bit above the inflow.
            # Use the same flow-balance roundoff as Lines; an interior level keeps its headroom.
            change[held & (np.abs(change) <= ROUNDOFF * (self.traffic @ np.abs(carried)))] = 0.0
        return change

    def _held(self, t, y):
        """The time and the state that the settings read at time t and state y: a store held on a
        bound through the segment is on it (what its settings read of it is the bound, not the
        roundoff of the integrator within its tolerance), and a switch that the state crosses at the
        start of the step is read on its far side while the state is within its tolerance, as the
        time is (`_sides`)."""
        trial = np.minimum(np.maximum(y, self.lower), self.upper)
        trial[self.lower_flags] = self.lower[self.lower_flags]
        trial[self.upper_flags] = self.upper[self.upper_flags]
        for i, low, high, number in self.sides if not self.vector.branches else ():
            if low <= trial[i] <= high:
                trial[i] = number
        if not self.vector.branches and self.clock is not None and self.clock[0] <= t <= self.clock[1]:
            t = self.clock[2]
        return t, trial

    def _side(self, t, y):
        """A function: the value of a side of a switch (a node of `surfaces`) at time t and state y."""
        found = dict(zip(self.sided, self._sides_of(t, y))) if self._sides_of is not None else {}
        units = self.plan.units
        return lambda node: float(lazily(self.region.expression(node), found.__getitem__, units, t))

    def choose(self, signs):
        """Install the same branches in the vector field and in its switch operands."""
        self.vector.choose(signs)
        self.region.set(signs, {})

    def _sides(self, clocks):
        """Select the branch of every rate at the segment start. A located contact uses its
        departing side. The vector uses these branches until the next located root (_turns)."""
        self.sides, self.signs = (), {}
        _, trial = self._held(self.t, self.y)

        def reversal(name):
            raise SimulationError(self._failed(self.t, f'opposing rates on the two sides of {name}'))

        self.sides, self.clock, self.signs = integrate.far_sides(
            self.surfaces,
            self.switch_layers,
            self.t,
            trial,
            self.place,
            (self.lower, self.upper),
            self._side,
            self.moves,
            self.field,
            self.choose,
            self.plan.units.comparisons,
            held=lambda i: self.lower_flags[i] or self.upper_flags[i],
            reversal=reversal,
            contacted=self.contacted,
            clocks=clocks,
        )

    def _turns(self, solution, start, end):
        """Locate every armed switch on one accepted step, using the actual dense state."""
        if not self.signs:
            return

        def reader(t):
            return self._side(t, solution(t))

        before, after = reader(start), reader(end)
        for pair, sign in self.signs.items():
            a, b = pair
            if pair in self.labels:
                moving, affine, _ = self.labels[pair]
                at = self.run.triggers.switching_time(a, b, moving, sign, affine)
            else:
                try:
                    at = integrate.switch_time(
                        pair,
                        reader,
                        start,
                        end,
                        self.plan.units,
                        sign,
                        accepted=(before(a) - before(b), after(a) - after(b)),
                        exact=integrate.fixed_clock(pair, before, self.moves),
                    )
                except (ExpressionError, TypeError, ValueError, ArithmeticError, LookupError):
                    continue
            if at is not None and start < at <= end:
                yield at, pair, 'switch'

    def switched_at(self, t):
        """The settings whose actual switching root was reached at this instant."""
        if t != self.t:
            return set()
        return {flow for pair in self.contacted for flow in self.deciding.get(pair, ())}

    def _start(self):
        """Where a step starts: the entries that the keyed reads hold, the flags of the bounds, and the
        far sides of the switches that the state crosses there (`_sides`)."""
        if self.outputs is not None and self.selected:
            return
        self.choose({})
        self.sides, self.clock = (), None
        self._select()
        # The clock switches before the new segment decides which stores stay on their bounds.
        clocks = integrate.clock_sides(
            self.surfaces,
            self.t,
            self._side(self.t, self.y),
            self.moves,
            consumed=self.contact_clocks,
        )
        self.clock, self.next_clock, _ = clocks
        self._flags()
        self._sides(clocks)
        if self.signs and np.any((self.y <= self.lower) | (self.y >= self.upper)):
            self._flags()  # compute bound release with the actual outgoing branches installed
        if self.outputs is not None:
            rows = self.region.selected_rows(self.run, self.signs, self._side(self.t, self.y))
            for name, row in rows.items():
                self.selection[name] = self.plan.keyed[name].names.index(row)
            self.held_rates = {name for name in self.recorded if self._holds(name)}
            self.selected = True

    def _holds(self, name):
        """Whether the chosen arithmetic reads only values held on this segment."""
        seen, pending = set(), [name]
        while pending:
            key = pending.pop()
            if key in seen:
                continue
            seen.add(key)
            kind = self.vector._kind(key)
            if kind in ('member', 'formula'):
                node = self.vector.nodes.get(key, self.vector.formulas[key].node)
                pending.extend(nodes.names(node))
            elif key in self.selection:
                if kind == 'stepped':
                    pending.append(self.run.stepped_of(key).name_at(self.selection[key]))
                elif self.selection[key] is not None:
                    pending.append(self.plan.keyed[key].names[self.selection[key]])
            elif kind != 'constant':
                return False
        return True

    def pattern(self):
        """The sparse pattern of the Jacobian for the flags of the segment."""
        net, count = self.net, len(self.stores)
        instant = Instant(
            net,
            self.asked(self.t, np.minimum(np.maximum(self.y, self.lower), self.upper)),
            self.lower_flags,
            self.upper_flags,
        )
        reads = [list(found) for found in self.reads]
        coupled = [f for f in range(len(self.flows)) if instant.coupled(f)]
        for part in instant.parts(coupled):
            joined = sorted({s for f in part for s in self.reads[f]})
            for f in part:
                reads[f] = joined
        rows, columns = [], []
        for c, f in enumerate(net.of.tolist()):
            for end in (net.source[c], net.sink[c]):
                if end >= 0:
                    rows += [end] * len(reads[f])
                    columns += reads[f]
        rows += list(range(count))
        columns += list(range(count))
        return sp.csr_array((np.ones(len(rows)), (rows, columns)), shape=(count, count))

    # ---- the segments -----------------------------------------------------------------------------

    def _flags(self):
        """The flags of a new segment: a store on a bound is held there while its sharing keeps it."""
        y, lower, upper = self.y, self.lower, self.upper
        at_lower, at_upper = y <= lower, y >= upper
        y[at_lower] = lower[at_lower]
        y[at_upper] = upper[at_upper]
        self.lower_flags, self.upper_flags = at_lower, at_upper
        for _ in range(len(y) + 1):
            change = self.field(self.t, y)
            leaving = (self.lower_flags & (change > 0)) | (self.upper_flags & (change < 0))
            if not leaving.any():
                break
            self.lower_flags &= ~leaving
            self.upper_flags &= ~leaving

    def _record(self, solution, start, end):
        """The pieces of the kept stores and actual rates from start to end."""
        recorder = self.recorder
        if end <= start or end == self.recorded_through:
            return
        self.recorded_through = end
        if self.kept_stores:
            tolerance = np.maximum(self.atol[self.kept_stores], 1e-300)
            states = lambda times: np.array([solution(at)[self.kept_stores] for at in times])  # noqa: E731
            for k, pieces in zip(self.kept_stores, fitted(states, start, end, tolerance)):
                recorder.add_pieces(self.stores[k], pieces)
        if self.kept_flows:
            if self.outputs is not None and (self.held_rates or not (self.surfaces or self.stepped)):
                return  # this branch already has its anchor from the sharing
            evaluations = self.evaluations
            tolerance = np.array([recorder.tolerance.get(self.recorded[k], 1e-9) for k in self.kept_flows])

            def delivered(times):
                return np.array([self.values(at, solution(at))[0][self.kept_flows] for at in times])

            for k, pieces in zip(self.kept_flows, fitted(delivered, start, end, tolerance)):
                recorder.add_pieces(self.recorded[k], pieces)
            self.evaluations = evaluations

    def incoming_history(self, t):
        """Give the recorder this pending step up to the moment, leaving its state in place."""
        if self.pending is not None:
            self._record(self.pending[2], self.pending[0], t)

    def _crossing(self, solution, start, end, k, level):
        """Locate the physical level on this step's dense state."""
        return integrate.crossing_time(lambda at: solution(at)[k] - level, start, end)

    def _count(self, start, end):
        """A step of the solver from start to end: after `integrate.STALLED_STEPS` steps in a row
        that are each shorter than the shortest time between two moments that the run tells apart
        (`Numerics.crossing`), across the segments, the run stops: it has stalled."""
        if end - start >= self.plan.numerics.crossing:
            self.brief, self.brief_from = 0, None
            return
        if not self.brief:
            self.brief_from = float(start)
        self.brief += 1
        if self.brief >= integrate.STALLED_STEPS:
            raise SimulationError(
                self._failed(
                    end,
                    f'the steps of the solver stayed shorter than {self.plan.numerics.crossing:g} h for '
                    f'{integrate.STALLED_STEPS} steps in a row, from t = {self.brief_from:g} h',
                )
            )

    def _failed(self, t, why):
        """What a failure of the solver at time t says: why, and where a setting reads a store through
        a condition, that the rates switch back and forth there (chattering), with the stores and the
        flows."""
        found = f'The run stops at t = {t:g} h: {why}'
        if not self.switches:
            return found
        stores = ', '.join(sorted(self.switches))
        flows = ', '.join(sorted({f for named in self.switches.values() for f in named}))
        return (
            f'{found}. chattering: the rates of {flows} read {stores} through a condition, and switch '
            'back and forth there: each branch takes the state back across the switch. A condition that '
            'turns the outflows of a stock off when it is empty does this when they ask for more than '
            'comes in: remove the condition, as the engine gives the outflows of an empty stock what '
            'comes in'
        )

    # ---- the interface of a way (`ways.py`) ------------------------------------------------------

    def begin(self):
        """Anchor an algebraic output at its sharing. Its smooth span reads its input histories."""
        if self.outputs is not None:
            self._start()
            self._anchor()

    def _anchor(self):
        numbers = self.values(self.t, self.y)[0]
        for k in self.kept_flows:
            name = self.recorded[k]
            held = name in self.held_rates or self.surfaces or self.stepped
            self.recorder.add(name, self.t, float(numbers[k]), 0.0 if held else None)

    def retire(self, key):
        """The set leaves the run's ways."""
        self.alive = False

    def refresh(self, t):
        """At a key time: the steps start again there."""
        self.cut(t)

    def peek(self):
        """The end of the next step of the solver, which is made now if it is not yet: a store that
        reaches a bound, or leaves the bound that holds it, ends it there."""
        if self.pending is not None:
            return self.pending[1]
        until = self.run.limit
        if self.t >= until:
            return math.inf
        if not self.stores:
            choose = not self.selected
            self._start()
            if choose and self.outputs is not None:
                self._anchor()
            until = min((until, *(way.peek() for way in set(self.following.values()))))
            if until <= self.t:
                return math.inf  # the producer commits its due step before the next window
            self.run.now = self.t
            self.contacts = list(self._turns(lambda at: self.y, self.t, until))
            end = min((at for at, _, _ in self.contacts), default=until)
            self.pending = self.t, end, lambda at: self.y, self.y, bool(self.contacts)
            return end
        if self.solver is None:
            self._start()
            numerics = self.plan.numerics
            # Time-keyed rows remain selected until the scheduled key. The incoming trial
            # may extend through its time band to bracket a simultaneous store bound.
            self.solver = Radau(
                self.field,
                self.t,
                self.y.copy(),
                until,
                rtol=numerics.rtol,
                atol=self.atol,
                jac_sparsity=self.pattern(),
            )
            self.first = self.t
        solver = self.solver
        self.run.now = solver.t
        try:
            message = solver.step()
        except (ExpressionError, ArithmeticError, ValueError) as problem:
            raise SimulationError(f'Rate evaluation failed at {solver.t:g} h: {problem}') from None
        if solver.status == 'failed':
            raise SimulationError(self._failed(solver.t, f'the solver failed ({message})'))
        start, end = solver.t_old, solver.t
        self._count(start, end)
        solution = solver.dense_output()
        y = solution(end)
        free = ~(self.lower_flags | self.upper_flags)
        events = []
        initial = solution(start)
        for k in np.flatnonzero(free & (y <= self.lower) & (initial > self.lower)).tolist():
            events.append((self._crossing(solution, start, end, k, self.lower[k]), k, 'lower bound'))
        for k in np.flatnonzero(free & (y >= self.upper) & (initial < self.upper)).tolist():
            events.append((self._crossing(solution, start, end, k, self.upper[k]), k, 'upper bound'))
        for k in np.flatnonzero(self.lower_flags & (y > self.lower + self.atol)).tolist():
            events.append(
                (self._crossing(solution, start, end, k, self.lower[k] + self.atol[k]), k, 'release')
            )
        for k in np.flatnonzero(self.upper_flags & (y < self.upper - self.atol)).tolist():
            events.append(
                (self._crossing(solution, start, end, k, self.upper[k] - self.atol[k]), k, 'release')
            )
        for name, select in self.switching:
            at = self._switch(solution, start, end, name, select)
            if at is not None:
                events.append((at, name, 'key'))
        events.extend(self._turns(solution, start, end))
        self.contacts = events
        ended = bool(events) or solver.status != 'running'
        if events:
            end = min(at for at, _, _ in events)
            y = solution(end)
            self._on_contacts(end, y)
        if ended and end <= self.first:
            raise SimulationError(self._failed(end, 'Integration made no progress'))
        self.pending = (start, end, solution, np.array(y, dtype=float), ended)
        return end

    def step(self, levels=()):
        """Commit the next step: the stores and the rates of the set move through it."""
        start, end, solution, y, ended = self.pending
        self.pending, self._drift = None, None
        self._record(solution, start, end)
        for name in levels:
            if name in self.place:
                y[self.place[name]] = levels[name]
        self.t, self.y = end, y
        self.contacted = tuple(pair for at, pair, kind in self.contacts if at == end and kind == 'switch')
        self.contact_clocks = {pair: at for pair, at in self.contact_clocks.items() if at >= end}
        self.run.now = end
        if ended:
            self.solver = None
            self.selected = False
        return list(self.stores), list(self.recorded), ended

    def lookahead(self, t, through):
        """A numerical step can end between the anchored moment and the far edge of its band.
        Search the rest of the band for an independently due physical contact. The first step
        still owns the dense state at the moment. All trial steps after it end with this round."""
        pending = self.pending
        if pending is None or pending[4] or not t <= pending[1] < through or self.solver is None:
            return
        now, brief, brief_from = self.run.now, self.brief, self.brief_from
        try:
            self.solver.t_bound = min(through, self.solver.t_bound)
            while self.pending[1] < through and not self.pending[4]:
                self.pending = None
                self.peek()
        finally:
            self.pending, self.solver = pending, None
            self.run.now, self.brief, self.brief_from = now, brief, brief_from

    def timing_events(self, through):
        if self.pending is not None:
            yield from self._events(through)

    def _events(self, through):
        for at, owner, kind in self.contacts:
            if at <= through:
                if kind in ('lower bound', 'upper bound'):
                    yield at, self.stores[owner], kind
                elif kind == 'switch' and owner in self.labels:
                    yield at, self.recorded[0], self.labels[owner][2]
                elif kind == 'switch':
                    for flow in self.deciding.get(owner, ()):
                        yield at, flow, kind
                elif kind == 'key':
                    yield at, owner, 'switch'

    def crossed_operands(self, t, through):
        if self.pending is not None:
            yield from (
                (at, pair)
                for at, pair, kind in self.contacts
                if kind == 'switch' and at <= through and self.run.clock.within(at, t)
            )

    def _on_contacts(self, through, y):
        met = put_bounds(self, y, self._events(through))
        for at, owner, kind in self.contacts:
            if at <= through and kind == 'switch':
                for here, other in (owner, owner[::-1]):
                    if isinstance(here, nodes.Ref) and here.name in self.place and not self.moves(other):
                        y[self.place[here.name]] = self._side(at, y)(other)
        return met

    def snap(self, t=None, through=None):
        """Commit the incoming piece at the moment's time and put its due stores on their bounds."""
        start, end, solution, y, ended = self.pending
        at = end if t is None else t
        through = end if through is None else through
        if at != end:
            y = np.array(solution(at), dtype=float)
        met = self._on_contacts(through, y)
        self.pending = start, at, solution, y, ended
        stores, rates, _ = self.step()
        self.contacted = tuple(
            pair for when, pair, kind in self.contacts if when <= through and kind == 'switch'
        )
        return stores + rates, met

    def finish(self, t):
        """At the horizon, where the run stands (`ways.finish`): sets built there, which have made no
        step (and so no evaluation, which a checkpoint keeps), record the kept stores and rates of
        the state there, with the selections and the flags of a new segment, as the first step of a
        run that goes on would from there; sets that have made steps hold their values there in
        their pieces. The evaluations count for no budget of the run."""
        if self.pending is not None or self.t != t or self.outputs is not None:
            return
        evaluations = self.evaluations
        try:
            self._start()
            values, carried = self.values(t, self.y)
        finally:
            self.evaluations = evaluations
        slopes = self.incidence @ carried  # the rate of each store there
        for k in self.kept_stores:
            self.recorder.add(self.stores[k], t, float(self.y[k]), float(slopes[k]))
        for k in self.kept_flows:
            self.recorder.add(self.recorded[k], t, float(values[k]), 0.0)

    def cut(self, t):
        """The run stands at time t inside the next step: the step up to t is committed, and the
        solver starts again from there. It starts again at every moment, even at the end of one of its
        steps, so that no state of the solver crosses a moment (`saved.py`)."""
        self.solver, self._drift = None, None
        if self.pending is None or t >= self.pending[1]:
            return
        start, _, solution, _, _ = self.pending
        self.pending = None
        if t <= start:
            return
        self._record(solution, start, t)
        self.t, self.y = float(t), np.array(solution(t), dtype=float)
        self.contacted = ()

    def incoming_level(self, store, t):
        if self.pending is not None and self.pending[0] < t:
            return float(self.pending[2](t)[self.place[store]])
        return self.level_at(store, t)

    def level_at(self, store, t):
        """The value of a store at time t: at the present time, inside the next step, or, before that
        step is made (at a moment), along the store's present rate (`drift`)."""
        k = self.place[store]
        if self.pending is None and t > self.t:
            return float(self.y[k] + (t - self.t) * self.drift()[k])
        if self.pending is None or t <= self.pending[0]:
            return float(self.y[k])
        return float(self.pending[2](min(t, self.pending[1]))[k])

    def drift(self):
        """The rate of each store at the present state: what a condition read an instant after a moment
        (`triggers.AFTER`) follows before the next step is made, as a line follows its rate. The
        evaluation counts for no budget of the run."""
        if self._drift is None:
            evaluations = self.evaluations
            try:
                if self.pending is None and self.solver is None:
                    self._start()  # the rates that the next step starts with
                self._drift = self.field(self.t, self.y)
            finally:
                self.evaluations = evaluations
        return self._drift

    def rate_at(self, name, t):
        """What the network gives of a flow at time t (an actual rate, a route's signed rate or a
        served fraction)."""
        y = (
            self.y
            if self.pending is None or t <= self.pending[0]
            else self.pending[2](min(t, self.pending[1]))
        )
        evaluations = self.evaluations
        try:
            if self.pending is None and self.solver is None:
                self._start()  # the rates that the next step starts with
            return float(self.values(t, y)[0][self.recorded.index(name)])
        finally:
            self.evaluations = evaluations

    def linear(self, store):
        """A store of the sparse integrator moves on a curve."""
        return None

    def breaks(self, start, end):
        """None: the next step of the solver is one form, the cubic of its dense output."""
        return []

    def motion(self, weights, start, end):
        """How the sum of the stores of `weights` ({store: weight}) moves from start to end inside the
        next step, from its dense output (`continuous/dense.py`), which the run reads as it is."""
        rows = np.array([self.place[name] for name in weights], dtype=np.int64)
        w = np.array(list(weights.values()), dtype=float)
        if self.pending is None:
            return dense.held(self.y[rows], w)
        return dense.of_step(self.pending[2], rows, w, start, end)

    def advance(self, until):
        """The set from its time to `until`, step by step."""
        while self.peek() <= until:
            self.step()
        self.cut(until)
