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
rate, a route's signed rate, a served fraction) that the record keeps. It fits the selected
stocks together on the accepted portion of a Radau step. It fits the actual rates on each
accepted interval (`record.fitted`). Sets built at a horizon that is a moment of a run that goes
on too take their values there, with the flags that a new segment would find (`finish`): a read at
the horizon of a run that ends there is the read of a run that goes on, whose first step of the sets
starts there. A reader of a condition that watches the stores reads the form of the next step
(`motion`: the cubic of its dense output, `continuous/dense.py`).
"""

from __future__ import annotations

import math
from bisect import bisect_right
from contextlib import contextmanager

import numpy as np
import scipy.sparse as sp
from scipy.integrate import Radau

from ...core import arrays
from ...core import expr as nodes
from ...core.errors import ExpressionError
from .. import departure
from ..allocation import StockFaces
from ..continuous import dense, integrate, rate_guard
from ..continuous.transfers import (
    CollocationRates,
    MovingAmounts,
    checked_amount,
    radau_amount,
)
from ..errors import SimulationError
from .collections import combined, dynamic_value, looked_up, selected
from .contacts import put_bounds
from .lines import asked_of
from .network import IN, OUT, SIDES, Asked, Instant, network_of
from .plan import DYNAMIC, FORMULA, LOOKUP, REDUCE, Pending, _renamed
from .reads import Reads, lazily
from .record import fitted
from .region import Region, key_surfaces
from .way import MovingTransfers, Way

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
        # Names supplied by earlier levels. Their values belong to a particular evaluation.
        self.rates = frozenset(rates or ())
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

        def values(t, y, rates=None):
            return self._gathered(plan, _Evaluation(self, t, y, rates))

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
            members = self._entries[name]
            reads = dynamic.controls(members, plan)
            if dynamic.steps:
                reads.update(plan.project(member, dynamic.steps) for member in members)
            return sorted(reads - {'t'})
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
                dynamic,
                self._entries[name],
                plan,
                evaluation.read,
                t,
                plan.units,
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

    __slots__ = ('known', 'rates', 't', 'vector', 'y')

    def __init__(self, vector, t, y, rates=None):
        self.vector, self.t, self.y = vector, t, y
        self.rates = rates
        self.known = {}

    def value(self, name):
        """Compute a requested formula or read its leaf in this probe's time, state and rate map."""
        if self.vector.derived(name) and name not in self.known:
            self.compute([name])
        return self.read(name)

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
            return self.rates[name]
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


def identifiable_network(net, connections, plan):
    """In an acyclic network with a fixed split at each source, every leg is
    determined by stock increments. In topological order the known gross inflow
    minus the store's change gives its gross outflow, split in the same fixed
    proportions. Radau's existing stage integrals therefore inherit stock error
    control. The caller excludes capacities/rankings and a receiving upper face.
    """
    if np.any(net.source < 0) or net.classes:
        return False
    interior = net.sink >= 0
    source, sink = net.source[interior], net.sink[interior]
    if np.any(source == sink):
        return False
    if np.any(source > sink):
        count = net.counts.shape[1]
        graph = sp.csr_array((np.ones(len(source)), (source, sink)), shape=(count, count))
        if (
            sp.csgraph.connected_components(graph, directed=True, connection='strong', return_labels=False)
            != count
        ):
            return False

    def constant(node):
        if isinstance(node, nodes.Const):
            return True
        return (
            isinstance(node, nodes.Ref)
            and node.name in plan.values
            and plan.values[node.name].kind in ('input', 'parameter')
        )

    shapes = {}
    for k in np.flatnonzero(net.counts[OUT, net.source] > 1).tolist():
        node = plan.values[connections[k].request].node
        if node is None:
            return False
        if isinstance(node, nodes.Binary) and node.op == 'mul':
            if constant(node.left):
                node = node.right
            elif constant(node.right):
                node = node.left
        source = connections[k].source
        if shapes.setdefault(source, node) != node:
            return False
    return True


class Sparse(MovingTransfers, Way):
    """Connected sets on the sparse integrator from the time `t` on (see the module), a way of a run
    (`ways.py`): one set, or the sets of `sets` in the order of their levels (`levels`), where the
    settings of a set read the rates of a set of an earlier level that move, so that they integrate
    together. An independent group can prepare one dense step past a scheduled observation.
    The run commits its incoming trajectory through each observation. Settlement retires a
    group whose equations changed and retains the others."""

    def __init__(self, run, sets, values, t, key, levels=None, given=None):
        plan = self.plan = run.plan
        sets = list(sets)
        levels = [0] * len(sets) if levels is None else list(levels)
        self.sets, self.set_levels = sets, levels  # which a checkpoint names (`saved.py`)
        self.key, self.alive = key, True
        self.solver, self.pending = None, None
        self.last_step = None
        self._drift = None  # the rates of the stores at the present state, once read (`drift`)
        self.run, self.recorder = run, run.recorder
        stores = [store for connected in sets for store in connected.stores]
        place = self.place = {name: k for k, name in enumerate(stores)}
        self.net, connections, self.recorded = network_of(run, sets, stores)
        self.stores, self.flows = stores, list(self.net.flows)
        single = None
        if len(connections) == 1:
            source, sink = self.net.source[0], self.net.sink[0]
            if source != sink:
                single = (sink, 1) if sink >= 0 else (source, -1)
        self.amounts = MovingAmounts(len(connections), t, single)
        self.leg_rows = {connection.name: k for k, connection in enumerate(connections)}
        self.capture = None
        self.stepped = frozenset(name for connected in sets for name in connected.stepped)
        self.capped = [k for k, connection in enumerate(connections) if connection.capacity is not None]
        self.end_settings = []  # (side, store, which)
        configured_ends = False
        names = [connection.request for connection in connections]
        names += [connections[k].capacity for k in self.capped]
        # The level of each setting: of its connection's set, or of its endpoint's store's set.
        level_of = [levels[int(k)] for k in self.net.flow_sets.tolist()]
        level_of += [level_of[k] for k in self.capped]
        for (store, side), end in plan.ends.items():
            if store in place:
                configured_ends = configured_ends or plan.settled(end)
                for which in ('request', 'capacity'):
                    if getattr(end, which) is not None:
                        self.end_settings.append((SIDES.index(side), place[store], which))
                        names.append(getattr(end, which))
                        level_of.append(levels[int(self.net.store_sets[place[store]])])
        # A keyed read of the settings that moves holds the entry that it selects through a
        # segment, which ends where it selects another (`_switch`). The rates of a level that a later
        # level reads are evaluated on the same trial state (`_prefix`).
        self.selection = {}
        earlier = [name for k, name in enumerate(self.recorded) if levels[self._set_of_flow(k)] < max(levels)]
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
            earlier,
            given,
            self.following,
            {name for name in formulas if plan._is_rate(name)} | set(defined),
        )
        self.outputs = vector.compiled(defined) if defined else None
        self.measured = None
        self.held_rates = set()
        self.selected = False

        self.cap_turns = self.capacity_turns() if self.capped or configured_ends else ()
        self.setting_names = tuple(names)
        self.settings = vector.compiled(names)
        self.size = len(names)
        if self.stores:
            self.amounts.clock_legs(self.net.connections, place, plan, run.env)
        self.constant_requests = self.held_settings(plan, names) or (
            self.amounts.all_clock and all(len(leg.polynomial) == 2 for leg in self.amounts.clocks.values())
        )
        self.single_donor(values)
        self.identifiable = (
            self.amounts.single is None
            and self.net.plain
            and self.stores
            and not (self.capped or configured_ends or self.amounts.all_clock)
            and identifiable_network(self.net, connections, plan)
        )
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
        self.faces = StockFaces.of(run, stores, self.lower, self.upper)
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
        # Ways.build integrates all moving rate suppliers of a stateful group in
        # its own solver. A stateless follower still needs its supplier's window.
        self.local_steps = bool(stores)
        self.pending_evaluations = 0
        self.key_times = sorted({float(at) for name in self.stepped for at in run.stepped_of(name).times})
        self.through_stores = (self.net.counts[0] > 0) & (self.net.counts[1] > 0)
        self.held_comparisons = None
        self.held_levels = self.y
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
            (name, self._selector(plan.keyed[name]))
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
                leaf in place or leaf in vector.rates or leaf in self.following for leaf in found.leaves
            )

        def nodes_of(settings):
            return [
                plan.values[name].node
                for name in settings
                if getattr(plan.values.get(name), 'node', None) is not None
            ]

        self.moves = moves
        surfaces = integrate.surfaces_of(nodes_of([*names, *defined]), formulas, moves)
        self.region = Region(surfaces, key_surfaces(plan, plan.expansion_of(names).leaves, moves, formulas))
        self.surfaces = self.region.surfaces
        self.deciding = integrate.flow_switches(
            ((name, nodes_of(plan.settings_of(plan.flows[name]))) for name in self.flows), formulas, moves
        )
        if self.region.lookups:
            self.lookup_flows = {}
            for flow in self.flows:
                fields = plan.settings_reads(plan.flows[flow])
                for name in fields.leaves & self.region.lookups.keys():
                    self.lookup_flows.setdefault(name, []).append(flow)
                    for pair in self.region.lookup_surfaces(name):
                        self.deciding.setdefault(pair, []).append(flow)
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

    def _selector(self, keyed):
        """A function (t, y) -> the entry that a keyed read selects there (None below its first
        key), from what its key, its members' keys and their tests read."""
        plan = self.plan
        index = self.run.index_for(keyed.name)

        def select(t, y):
            trial = self._probe(t, y)
            return selected(keyed, trial.value, plan.units, t, index)

        return select

    def _select(self):
        """At the start of a segment: each keyed read that moves holds the entry that it selects."""
        y = self.faces.trial(self.y)
        self.selection.clear()
        self.selection.update(dict.fromkeys(self.stepped, self.t))
        for name, select in self.switching:
            self.selection[name] = select(self.t, y)

    def _switch(self, solution, start, end, name, select):
        """The first time in (start, end] at which a keyed read selects another entry than the one
        that it holds through the segment, to within the crossing tolerance; or None. Here the
        observation is the selected row identity, including filters and ranking. A numeric key
        surface exposed by a moving segment is located with the other operands in `_turns`."""
        if name in self.region.lookups:
            return None  # numeric eligibility and ranking comparisons own its switches
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
        if self.levels:
            found, rates = self._prefix(t, y)
            at, settings, _ = self.levels[-1]
            found[at] = settings(t, y, rates)
            return self._asked(found, t, y, rates)
        return self._asked(self.settings(t, y), t, y)

    def _prefix(self, t, y):
        """Settle upstream levels in order at this time and state. The returned rates belong
        to this probe even when another evaluation runs before a later operand is read."""
        found, rates = np.zeros(self.size), {}
        for at, settings, gives in self.levels[:-1]:
            found[at] = settings(t, y, rates)
            asked = self._asked(found, t, y, rates)
            values = Instant(self.net, asked, self.lower_flags, self.upper_flags).values()
            rates.update((name, float(values[k])) for k, name in gives)
        return found, rates

    def _probe(self, t, y):
        rates = self._prefix(t, y)[1] if self.levels else None
        return _Evaluation(self.vector, t, y, rates)

    def _asked(self, found, t, y, rates=None):
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
                trial = _Evaluation(vector, t, y, rates)
                for k in np.flatnonzero(found < 0):
                    if trial.value(self.setting_names[k]) >= 0:
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
        with self._reading_rates():
            if not incoming:
                self._start()
            primary, carried = self.values(t, y)
        answers = dict(zip(self.recorded, map(float, primary)))
        if not self.net.plain:
            answers.update(
                (f'{name}.actual_rate', float(number)) for name, number in zip(self.net.connections, carried)
            )
        return answers

    @contextmanager
    def _reading_rates(self):
        """Observations of a trajectory use no solver evaluations, even at the limit."""
        spent = self.evaluations
        self.evaluations = None
        try:
            yield
        finally:
            self.evaluations = spent

    def values(self, t, y):
        """What the network gives of each flow at time t and state y, with the flags of the segment,
        and the rate of each connection."""
        if self.evaluations is not None:
            self.evaluations += 1
            if self.evaluations > self.plan.numerics.max_evaluations:
                raise SimulationError('Numerical evaluation budget exceeded')
        t, trial = self._held(t, y)
        if self.outputs is not None:
            values = self.outputs(t, trial)
            return values, values
        asked = self.asked(t, trial)
        instant = Instant(self.net, asked, self.lower_flags, self.upper_flags)
        values = instant.values()
        self.measured = instant if instant.rate_errors else None
        return values, self.net.carried(values, asked)

    def field(self, t, y, *, allocation=False):
        carried = self.values(t, y)[1]
        self.last_carried = carried
        return self._net(carried, allocation=allocation)

    def _net(self, carried, *, allocation=False):
        change = self.incidence @ carried
        held = self.lower_flags | self.upper_flags
        if held.any():
            # On a held face, proportional shares can sum a last bit above the inflow.
            # Use the same flow-balance roundoff as Lines; an interior level keeps its headroom.
            gross = self.traffic @ np.abs(carried)
            if self.measured is not None:
                candidates = np.flatnonzero(held & (gross > 0) & (np.abs(change) <= 1e-7 * gross))
                for i in candidates.tolist():
                    change[i] = self.measured.face_rate(
                        i,
                        carried[self.net.ends[IN].of(i)],
                        carried[self.net.ends[OUT].of(i)],
                        change[i],
                        gross[i],
                    )
            change = departure.rates(
                change,
                gross,
                held,
                lambda i: (carried[self.net.ends[IN].of(i)], carried[self.net.ends[OUT].of(i)]),
            )
            if not allocation:
                one_face = self.lower_flags ^ self.upper_flags
                for row in np.flatnonzero(
                    (change == 0) & (gross > 0) & self.through_stores & one_face
                ).tolist():
                    change[row] = self.run.stock_state.physical_face_net(self, row, carried)
        return change

    def _held(self, t, y):
        """The time and state that the settings read at time t and state y. A held store
        keeps its accepted coordinate, including any remainder inside the bound's band.
        A switch that the state crosses at the
        start of the step is read on its far side while the state is within its tolerance, as the
        time is (`_sides`)."""
        trial = self.faces.trial(y)
        for i, low, high, number in self.sides if not self.vector.branches else ():
            if low <= trial[i] <= high:
                trial[i] = number
        if not self.vector.branches and self.clock is not None and self.clock[0] <= t <= self.clock[1]:
            t = self.clock[2]
        return t, trial

    def _side(self, t, y):
        """A function: the value of a side of a switch (a node of `surfaces`) at time t and state y."""
        trial = self._probe(t, y)
        found = dict(zip(self.sided, self._sides_of(t, y, trial.rates))) if self._sides_of else {}
        units = self.plan.units

        def read(name):
            if name not in found:
                # The selected arm of a named formula can ask for a comparison-scale
                # dependency outside the switch operands. Use the same trial state.
                found[name] = trial.value(name)
            return found[name]

        return lambda node: float(lazily(self.region.expression(node), read, units, t))

    def choose(self, signs):
        """Install the same branches in the vector field and in its switch operands."""
        self.vector.choose(signs)
        self.region.set(signs, {})
        if signs and self.region.lookups:
            rows = self.region.selected_rows(self.run, signs, self._side(self.t, self.y))
            for name, row in rows.items():
                self.selection[name] = self.plan.keyed[name].names.index(row)

    def _branch_rates(self, t, y):
        """An unresolved or held face cannot choose an outgoing branch from its booked roundoff."""
        return self.field(t, y, allocation=True)

    def _sides(self, clocks):
        """Select the branch of every rate at the segment start. A located contact uses its
        departing side. The vector uses these branches until the next located root (_turns)."""
        self.sides, self.signs = (), {}
        _, trial = self._held(self.t, self.y)

        def reversal(name):
            raise SimulationError(self._failed(self.t, f'opposing rates on the two sides of {name}'))

        self.sides, self.clock, self.signs, self.held_comparisons = integrate.far_sides(
            self.surfaces,
            self.switch_layers,
            self.t,
            trial,
            self.place,
            (self.lower, self.upper),
            self._side,
            self.moves,
            self._branch_rates,
            self.choose,
            self.plan.units.comparisons,
            physical=self.field,
            held=lambda i: self.lower_flags[i] or self.upper_flags[i],
            reversal=reversal,
            contacted=self.contacted,
            clocks=clocks,
            stock_at=self.run.stock_state.point,
        )

    def _turns(self, solution, start, end):
        """Locate every armed switch on one accepted step, using the actual dense state."""
        if not self.signs:
            return

        def reader(t):
            return self._side(t, solution(t))

        before, after = reader(start), reader(end)
        ends = []  # the stores' rates at the step's two ends, once, when a switch needs them
        for pair, sign in self.signs.items():
            a, b = pair
            if pair in self.labels:
                moving, affine, _ = self.labels[pair]
                at = self.run.triggers.switching_time(a, b, moving, sign, affine)
            else:
                try:
                    accepted = exact = None
                    if sign:
                        first = before(a) - before(b)
                        accepted = first, after(a) - after(b)
                        exact = integrate.fixed_clock(pair, before, self.moves)
                        if exact is None:
                            exact = self._held_root(pair, first, solution, start, end, reader, ends)
                    at = integrate.switch_time(
                        pair,
                        reader,
                        start,
                        end,
                        self.plan.units,
                        sign,
                        accepted=accepted,
                        exact=exact,
                    )
                except (ExpressionError, TypeError, ValueError, ArithmeticError, LookupError):
                    continue
            if at is not None and start < at <= end:
                # Leaving equality restarts the field at its actual state. Only a physical
                # crossing may place a stock on its target or consume a clock contact.
                yield at, pair, 'switch' if sign else 'band exit'

    def _held_root(self, pair, first, solution, start, end, reader, ends):
        """The crossing of a store with a fixed threshold when the store moves at one rate through
        the whole step: the start plus the gap over that rate. A root search on the dense output
        lands a place or two to either side of it, and which side depends on the platform's
        arithmetic. None unless the rate is the same at both ends and the root is in the band."""
        sides = [
            (self.place[node.name], direction)
            for node, other, direction in ((pair[0], pair[1], 1), (pair[1], pair[0], -1))
            if isinstance(node, nodes.Ref) and node.name in self.place and not self.moves(other)
        ]
        if not sides:
            return None
        k, direction = sides[0]
        if not ends:
            with self._reading_rates():
                ends.extend(self._net(self.values(at, solution(at))[1]) for at in (start, end))
        rate = ends[0][k]
        if not rate or rate != ends[1][k]:
            return None
        at = start - first / (direction * rate)
        if not start < at <= end:
            return None
        read = reader(at)
        if not integrate.contact_band(pair, reader, self.plan.units)(at, read(pair[0]) - read(pair[1])):
            return None
        return at

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
        if self.run.consumed:
            self.contact_clocks.update(self.run.consumed_in(self.surfaces, self.t))
            self.contacted = tuple(dict.fromkeys((*self.contacted, *self.contact_clocks)))
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
        if self.region.lookups:
            rows, ranks = self.region.rank_members(
                self.run,
                self.signs,
                self.t,
                self.y,
                self._side,
                self._branch_rates,
                self.place,
                self.moves,
                self.contacted,
            )
            self.signs.update(ranks)
            for name, row in rows.items():
                self.selection[name] = self.plan.keyed[name].names.index(row)
            self.rank_switches = {
                pair: {flow for name in names for flow in self.lookup_flows.get(name, ())}
                for pair, names in self.region.rank_owners.items()
            }
        if self.signs and any(mask.any() for mask in self.faces.flags(self.y)):
            self._flags()  # compute bound release with the actual outgoing branches installed
        if self.outputs is not None:
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
            self.asked(self.t, self.faces.trial(self.y)),
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
        y = self.y
        at_lower, at_upper = self.faces.flags(y)
        self.held_levels = y
        self.lower_flags, self.upper_flags = at_lower, at_upper
        for _ in range(len(y) + 1):
            change = self.field(self.t, y, allocation=True)
            leaving = (self.lower_flags & (change > 0)) | (self.upper_flags & (change < 0))
            if not leaving.any():
                if self.measured is not None:
                    for i, data in self.measured.uncertain.items():
                        departure.record_tie(self.recorder, self.t, self.stores[i], *data)
                break
            self.lower_flags &= ~leaving
            self.upper_flags &= ~leaving

        self.armed_faces = self.faces.armed(
            self.lower_flags, self.upper_flags, releases=(self.held_levels, self.atol)
        )
        if self.constant_requests:
            self.amounts.held_solution(self.last_carried, self.t)
            self.held_since = self.t
            self.held_slopes = self._net(self.last_carried)
        self.set_resting(
            {
                self.stores[k]: self.held_levels[k]
                for k in np.flatnonzero(self.through_stores & (self.lower_flags | self.upper_flags)).tolist()
            },
            self.t,
        )

    def _record(self, solution, start, end):
        """The pieces of the kept stores and actual rates from start to end."""
        recorder = self.recorder
        if self.constant_requests:
            if start == self.held_since:
                for k in self.kept_stores:
                    recorder.add(
                        self.stores[k], start, float(self.held_levels[k]), float(self.held_slopes[k])
                    )
        elif self.kept_stores:
            tolerance = np.maximum(self.atol[self.kept_stores], 1e-300)
            states = lambda times: np.array([solution(at)[self.kept_stores] for at in times])  # noqa: E731
            names = [self.stores[k] for k in self.kept_stores]

            def fit(left):
                return fitted(states, left, end, tolerance)

            recorder.store_step(names, fit, start, complete=end == self.pending[1])
        if self.kept_flows:
            if self.outputs is not None and (self.held_rates or not (self.surfaces or self.stepped)):
                return  # this branch already has its anchor from the sharing
            tolerance = np.array([recorder.tolerance.get(self.recorded[k], 1e-9) for k in self.kept_flows])

            def delivered(times):
                return np.array([self.values(at, solution(at))[0][self.kept_flows] for at in times])

            with self._reading_rates():
                for k, pieces in zip(self.kept_flows, fitted(delivered, start, end, tolerance)):
                    recorder.add_pieces(self.recorded[k], pieces)

    def commit_through(self, t):
        """Post the transfers and record the history of the pending step through t once."""
        if self.pending is None:
            return
        start, _, solution, _, _ = self.pending
        if self.recorded_through is not None:
            start = max(start, self.recorded_through)
        if t <= start:
            return
        self.evaluations += self.pending_evaluations
        self.pending_evaluations = 0
        self._accept(solution, start, t)
        self._record(solution, start, t)
        self.recorded_through = self.t = float(t)
        self.y = self.pending[3] if t == self.pending[1] else np.array(solution(t), dtype=float)
        self._drift = None

    def incoming_history(self, t):
        self.commit_through(t)

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

    def _seal_stores(self):
        for k in self.kept_stores:
            self.recorder.seal_store(self.stores[k])

    def retire(self, key):
        """The set leaves the run's ways."""
        self._seal_stores()
        self.alive = False

    def refresh(self, t):
        """At a key time: the steps start again there."""
        self.cut(t)

    def peek(self, limit=None):
        """The end of the next step of the solver, which is made now if it is not yet: a store that
        reaches a bound, or leaves the bound that holds it, ends it there."""
        ways = self.run.ways
        boundary = min(ways.shared_deadline, ways.deadlines.get(self, self.plan.horizon))
        if self.pending is not None:
            if self.pending[1] <= self.run.clock.apart(boundary):
                return self.pending[1]
            # A stage just scheduled a change inside a previously prepared step.
            # Its observed prefix is final. Restart the controller at that prefix.
            self.cut(self.t)
        required = self.run.limit if limit is None else min(limit, self.run.limit)
        until = self.smooth_until(self.t, required)
        # The first trial selects a branch on the ordinary window. On the smooth field,
        # a longer dense step can serve observations made by other groups.
        solver = self.solver
        if (
            limit is None
            and self.local_steps
            and self.t < until == required
            and solver is not None
            and self.t + solver.h_abs > required
        ):
            if self.next_clock > self.t:
                boundary = min(boundary, self.next_clock)
            if self.key_times:
                place = bisect_right(self.key_times, self.t)
                if place < len(self.key_times):
                    boundary = min(boundary, self.key_times[place])
            # The incoming row and branch may bracket a simultaneous bound in
            # the same time band as the scheduled clock.
            local = self.smooth_until(self.t, self.run.clock.apart(boundary))
            if local > until:
                return self._local_trial(until, local)
        return self._prepare_step(until)

    def _local_trial(self, required, local):
        """Try one step beyond the calendar. A discarded trial spends no work allowance."""
        now = self.run.now
        spent = self.evaluations
        solver = self.solver
        # Radau replaces its iteration arrays on acceptance. The transfer sampler
        # also collects rate samples inside the scalar RHS during a Newton solve.
        state = vars(solver).copy()
        rates = self.measured, self.last_carried
        brief = self.brief, self.brief_from
        contacts = self.contacts
        capture = self.capture
        if capture is not None:
            samples, previous = capture.samples.copy(), capture.previous
        try:
            end = self._prepare_step(local)
        except (SimulationError, ExpressionError, ArithmeticError, ValueError):
            vars(solver).update(state)
            if capture is not None:
                capture.samples, capture.previous = samples, previous
            self.measured, self.last_carried = rates
            self.brief, self.brief_from = brief
            self.contacts = contacts
            self.evaluations = spent
            self.local_steps = False
            end = self._prepare_step(required)
            self.run.now = now
            return end
        self.run.now = now
        # A stop at the current instant has used none of the trial. Its first
        # positive prefix uses the entire collocation polynomial and pays once.
        self.pending_evaluations = self.evaluations - spent
        self.evaluations = spent
        return end

    def _prepare_step(self, until):
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
                first_step=min(self.last_step, until - self.t) if self.last_step is not None else None,
                rtol=numerics.rtol,
                atol=self.atol,
                jac_sparsity=self.pattern(),
            )
            self.capture = (
                CollocationRates(self.solver, lambda: self.last_carried)
                if self.amounts.single is None
                else None
            )
            self.first = self.t
        solver = self.solver
        # Radau stops exactly at t_bound. If only the run's observation window ended,
        # the accepted state, Jacobian and step-size controller remain valid. Extend
        # that solver when the timeline opens its next window.
        if solver.t_bound != until:
            solver.t_bound = until
            if solver.status == 'finished' and solver.t < until:
                solver.status = 'running'
        self.run.now = solver.t
        try:
            message = rate_guard.step(solver, self.guard_for(self.region.signs))
        except (ExpressionError, ArithmeticError, ValueError) as problem:
            raise SimulationError(f'Rate evaluation failed at {solver.t:g} h: {problem}') from None
        if solver.status == 'failed':
            raise SimulationError(self._failed(solver.t, f'the solver failed ({message})'))
        start, end = solver.t_old, solver.t
        self._count(start, end)
        solution = solver.dense_output()
        if self.capture is not None:
            self.capture.finish(solution)
        y = solution(end)
        events = list(self.armed_faces.crossings(solution, start, end, y))
        for name, select in self.switching:
            at = self._switch(solution, start, end, name, select)
            if at is not None:
                events.append((at, name, 'key'))
        if self.held_comparisons:
            for at, row in integrate.exits_of_held_comparisons(
                self.held_comparisons, self.faces.factor, solution, start, end
            ):
                events.append((at, row, 'release'))
        events.extend(self._turns(solution, start, end))
        self.contacts = events
        ended = bool(events) or (solver.status == 'finished' and end in self.cap_turns)
        if events:
            end = min(at for at, _, _ in events)
            y = solution(end)
        if ended and end <= self.first:
            raise SimulationError(self._failed(end, 'Integration made no progress'))
        self.pending = (start, end, solution, np.array(y, dtype=float), ended)
        return end

    def _transfer_amount(self, solution, start, end):
        if self.amounts.single is not None:
            return radau_amount(solution, end, self.amounts.single, start=start)
        if self.amounts.all_clock and not self.lower_flags.any() and not self.upper_flags.any():
            return radau_amount(solution, end, None, start=start)

        if self.identifiable and not self.upper_flags.any():
            return radau_amount(solution, end, None, start=start)

        def rate_at(t):
            return self.values(t, solution(t))[1]

        with self._reading_rates():
            return checked_amount(
                solution,
                end,
                rate_at,
                self.plan.numerics.rtol,
                self.amounts.tolerances(self.run, (f'{name}.actual_rate' for name in self.net.connections)),
                start=start,
            )

    def _accept(self, solution, start, end):
        if self.stores and start < end:
            # Only a committed step supplies a size. A trial beyond a moment does not.
            self.last_step = solution.h
            if self.amounts.clocks:
                self.amounts.select_clocks(self.lower_flags.__getitem__, self.upper_flags.__getitem__)
            self.accept_amounts(start, end, self._transfer_amount(solution, start, end))
            self.mark_rates(solution, start, end)

    def _clock_bounds(self):
        return self.lower_flags.__getitem__, self.upper_flags.__getitem__

    def _pending_end(self):
        return self.pending[1]

    def _pending_amount(self, row, t):
        prefix = self._transfer_amount(self.pending[2], self.amounts.through, t)
        return prefix if self.amounts.single is not None else prefix[row]

    def step(self, levels=()):
        """Commit the next step: the stores and the rates of the set move through it."""
        _, end, _, y, ended = self.pending
        self.commit_through(end)
        self.pending, self._drift = None, None
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
        limit = min(through, self.run.limit)
        if pending[1] >= limit:
            return
        now, brief, brief_from = self.run.now, self.brief, self.brief_from
        try:
            while self.pending[1] < limit and not self.pending[4]:
                self.pending = None
                self.peek(limit)
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
                elif kind == 'switch' and self.region.lookups and owner in self.rank_switches:
                    for flow in self.rank_switches[owner]:
                        yield at, flow, kind
                elif kind == 'switch':
                    for flow in self.deciding.get(owner, ()):
                        yield at, flow, kind
                elif kind == 'key':
                    yield at, owner, 'switch'

    def detected_switches(self):
        if self.pending is not None:
            yield from ((at, pair) for at, pair, kind in self.contacts if kind == 'switch')

    def _on_contacts(self, through, y):
        met = put_bounds(self, y, self._events(through))
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
        with self._reading_rates():
            self._start()
            values, carried = self.values(t, self.y)
        slopes = self.incidence @ carried  # the rate of each store there
        for k in self.kept_stores:
            self.recorder.add(self.stores[k], t, float(self.y[k]), float(slopes[k]))
        for k in self.kept_flows:
            self.recorder.add(self.recorded[k], t, float(values[k]), 0.0)

    def observe(self, t, through=None):
        """Accept incoming work. At an ordinary arrival also settle a contact due in its band."""
        if through is not None and self.pending is not None:
            end = self.pending[1]
            contact = any(self.contacts_at(t, through))
            if end <= t or contact:
                intrinsic = contact or self.pending[4]
                changed, met = self.snap(t, through)
                return (*changed, *met) if intrinsic else ()
        self.commit_through(t)
        return ()

    def cut(self, t):
        """Accept the incoming work through t and discard the remaining trial.
        A live solver uses its last accepted step size for the next trial. After a restore,
        the solver selects its first step. Both runs make the same decisions in the same order.
        Their values agree closely. Inside a long step, the relative difference can exceed rtol."""
        if self.pending is not None:
            self.commit_through(min(t, self.pending[1]))
            self._seal_stores()
            if t > self.pending[0]:
                self.contacted = ()
            self.pending = None
            self.pending_evaluations = 0
        self.solver, self._drift = None, None

    def _step_state(self, t, *, incoming=False):
        """Read the pending step. An incoming contact can read beyond its end."""
        if self.pending is None or not self.stores:
            return self.y
        start, end, solution, _, _ = self.pending
        if t <= start:
            # A moment can commit a prefix and advance self.y inside this step.
            return solution.y_old
        return solution(t if incoming else min(t, end))

    def incoming_level(self, store, t):
        if self.pending is not None:
            return float(self._step_state(t, incoming=True)[self.place[store]])
        return self.level_at(store, t)

    def incoming_rates(self, t):
        # An incoming read must not call _start: it can be part of closing the
        # old face constraints while the outgoing branch is being selected.
        y = self._step_state(t, incoming=True)
        with self._reading_rates():
            carried = self.values(t, y)[1]
        return lambda name: float(carried[self.leg_rows[name]])

    def level_at(self, store, t):
        """The value of a store at time t: at the present time, inside the next step, or, before that
        step is made (at a moment), along the store's present rate (`drift`)."""
        k = self.place[store]
        if self.pending is None and t > self.t:
            return float(self.y[k] + (t - self.t) * self.drift()[k])
        return float(self._step_state(t)[k])

    def drift(self):
        """The rate of each store at the present state: what a condition read an instant after a moment
        (`triggers.AFTER`) follows before the next step is made, as a line follows its rate. The
        evaluation counts for no budget of the run."""
        if self._drift is None:
            with self._reading_rates():
                if self.pending is None and self.solver is None:
                    self._start()  # the rates that the next step starts with
                self._drift = self.field(self.t, self.y)
        return self._drift

    def rate_at(self, name, t):
        """What the network gives of a flow at time t (an actual rate, a route's signed rate or a
        served fraction)."""
        y = self._step_state(t)
        with self._reading_rates():
            if self.pending is None and self.solver is None:
                self._start()  # the rates that the next step starts with
            return float(self.values(t, y)[0][self.recorded.index(name)])

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
