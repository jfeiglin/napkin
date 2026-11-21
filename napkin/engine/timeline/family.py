"""The family: every connected set of one flow whose rate reads nothing that moves, run together on
arrays (R-A4a-04, "arrays").

Such a flow asks one rate from moment to moment: `min(request, capacity)` holds between the moments
of the run, since its request and its capacity read inputs, fixed values and keyed reads that change
only at their key times. So each of its stores is a line between moments, and the flow delivers what
it asks until a store at one of its ends reaches the bound that holds it back: its source at a lower
bound, or its sink at an upper bound. From then on the flow delivers nothing, as the continuous
engine has it for one flow at a bound; a flow from a full store into a full store, which nothing
drains, delivers nothing either (`network.py`: room). Each flow is a row of the family:

- `begin(t)` evaluates the rates of every row as columns (`Columns`) and starts their lines;
- `advance(until)` takes, in time order, each row whose store reaches its bound before `until`: the
  store is put on its bound exactly, and the flow stops;
- `refresh(t)` evaluates the rates again at a key time and starts again the lines of the rows whose
  rate changed.

The recorder takes a piece of each store and of each actual rate at each change of its line, and a
piece of a request or a capacity that is a formula at each change of its value: all are exact.

`Columns` gives the values of engine names at a time as arrays: a formula that the members of a
template share is evaluated once over the rows (`napkin/core/arrays.values`) with each of its names
read as a column when the evaluation first reads it, and any other value is read from the start of
the run, or from the keyed read by the time that holds it. A column with no value for a row that
another row's branch reads makes each row evaluate by itself, reading only its own branch
(`reads.py`). The values are found with no recursion (`walk.walked`): an evaluation that reads a
formula, a reduction, a keyed read or a column that this read has not found yet asks for it
(`Pending`), which is found first on the driver's stack, and evaluates again with the reads that it
made kept; so a chain of formulas of any length is read to its end, and each value once in a read.
"""

from __future__ import annotations

import heapq
import math

import numpy as np

from ...core import arrays
from ...core.errors import ExpressionError
from ..continuous.transfers import HeldAmounts
from ..continuous.walk import walked
from ..errors import SimulationError
from .collections import combined, looked_up
from .contacts import put_bounds
from .plan import FORMULA, LOOKUP, REDUCE, Pending
from .reads import Reads, lazily
from .way import Way


class Columns:
    """The values of engine names at a time (see the module), for one run."""

    def __init__(self, run):
        self.run, self.plan = run, run.plan

    def one(self, name, t):
        """The value of one engine name at time t."""
        return walked(self._one(name, float(t), _Known(), set()))

    def at(self, names, t):
        """The values of engine names at time t, as an array in their order."""
        return walked(self._at(list(names), float(t), _Known(), set()))

    def _derived(self, name):
        """Whether a value is computed from others where it is read: a formula, a reduction or a
        keyed read."""
        value = self.plan.values.get(name)
        return value is not None and value.kind in (FORMULA, REDUCE, LOOKUP)

    def _one(self, name, t, known, waiting):
        """The computation of `one` (`walk.walked`). `known` keeps what this read found, a value or
        the error that it raised (`_Failed`), which a later read of it raises again; a value that
        waits for itself (`waiting`) reads itself."""
        plan, run = self.plan, self.run
        if name == 't':
            return t
        value = plan.values.get(name)
        kind = value.kind if value is not None else None
        if kind == FORMULA:
            return (
                yield from self._evaluated(
                    name, lambda read: lazily(value.node, read, plan.units, t), t, known, waiting
                )
            )
        if kind == REDUCE:
            reduction = plan.reductions[name]
            entries = run.kept_of(name)
            if reduction.names is None:
                return combined(reduction.op, [None] * len(entries), reduction.spelled)
            found = yield self._at([reduction.names[k] for k in entries], t, known, waiting)
            return combined(reduction.op, list(found), reduction.spelled)
        if kind == LOOKUP and plan.stepped(name):
            return (yield self._one(run.stepped_of(name).name_at(t), t, known, waiting))
        if kind == LOOKUP:
            keyed, index = plan.keyed[name], run.index_for(name)
            return (
                yield from self._evaluated(
                    name, lambda read: looked_up(keyed, read, plan.units, t, index), t, known, waiting
                )
            )
        return run.value_of(name)

    def _evaluated(self, name, evaluate, t, known, waiting):
        """The value of `evaluate(read)`, for `yield from`: each derived value that it reads and that
        this read has not found yet (`Pending`) is found first, then it evaluates again, with what it
        read kept."""
        own = {}

        def read(each):
            found = own.get(each, _MISSING)
            if found is not _MISSING:
                return found
            if not self._derived(each):
                found = t if each == 't' else self.run.value_of(each)
            else:
                found = known.read(each)
            own[each] = found
            return found

        waiting.add(name)
        while True:
            try:
                found = evaluate(read)
            except Pending as pending:
                yield from self._found(pending.names, t, known, waiting)
                continue
            waiting.discard(name)
            return found

    def _found(self, names, t, known, waiting):
        """Find each of `names` that this read has not, or the error that it raises (`_Failed`)."""
        for each in names:
            if each in known:
                continue
            if each in waiting:
                raise SimulationError(f'{each}: a value that reads itself at t = {t:g} h')
            try:
                if isinstance(each, tuple):  # a column of a formula that rows share (`_at`)
                    known[each] = yield self._at(list(each[1]), t, known, waiting)
                else:
                    known[each] = yield self._one(each, t, known, waiting)
            except Exception as problem:  # raised where the evaluation reads it, as a call raises
                known[each] = _Failed(problem)

    def _at(self, names, t, known, waiting):
        """The computation of `at` (`walk.walked`)."""
        plan = self.plan
        unique = list(dict.fromkeys(names))
        found, groups = {}, {}
        for name in unique:
            value = plan.values.get(name)
            if value is not None and value.kind == FORMULA and value.shape is not None:
                groups.setdefault(id(value.shape), []).append(name)
            elif name in known:
                found[name] = known.read(name)
            else:
                found[name] = yield self._one(name, t, known, waiting)
        for members in groups.values():
            first = plan.values[members[0]]
            columns = {
                read: tuple(dict(plan.values[name].binding)[read] for name in members)
                for read, _ in first.binding
            }

            def column(read, columns=columns):
                # A column is made when the evaluation over the rows first reads it (`reads.py`): one
                # that this read has not found is found first (`Pending`).
                return known.read(('column', columns[read]))

            env = Reads(frozenset(columns), column)
            while True:
                try:
                    computed = arrays.values(first.shape, env, plan.units, len(members), columns, known.read)
                except Pending as pending:
                    yield from self._found(pending.names, t, known, waiting)
                    continue
                except ExpressionError:
                    # A column with no value for some row, which another row's branch reads: each
                    # row by itself reads only its own branch.
                    computed = []
                    for name in members:
                        computed.append((yield self._one(name, t, known, waiting)))
                break
            computed = np.broadcast_to(np.asarray(computed), (len(members),))
            for name, number in zip(members, computed.tolist()):
                found[name] = number
        return np.array([found[name] for name in names])


_MISSING = object()


class _Failed:
    """The error that a value raised where a read of `Columns` found it: a later read of it in that
    read raises it again."""

    __slots__ = ('problem',)

    def __init__(self, problem):
        self.problem = problem


class _Known(dict):
    def read(self, key):
        if key not in self:
            raise Pending(key)
        found = self[key]
        if isinstance(found, _Failed):
            raise found.problem
        return found


class Family(Way):
    """Rows of the family of one run, from the time `t` on (see the module). `keys` are the ids that
    the run gives the sets, one for each row."""

    def __init__(self, run, sets, values, t=0.0, keys=None):
        plan = self.plan = run.plan
        self.t0 = float(t)
        self.sets = list(sets)  # its sets, one for each row, which a checkpoint names (`saved.py`)
        self.keys = {key: k for k, key in enumerate(keys if keys is not None else range(len(sets)))}
        self.run, self.recorder, self.columns = run, run.recorder, Columns(run)
        flows = [plan.flows[connected.flows[0]] for connected in sets]
        self.flows = [flow.name for flow in flows]
        stores = sorted({end for flow in flows for end in (flow.source, flow.sink) if end is not None})
        place = {name: k for k, name in enumerate(stores)}
        self.stores = stores
        self.source = np.array([place[flow.source] if flow.source else -1 for flow in flows], dtype=np.int64)
        self.sink = np.array([place[flow.sink] if flow.sink else -1 for flow in flows], dtype=np.int64)
        self.y = np.array([float(values[name]) for name in stores])
        self.since = np.zeros(len(stores))  # the time at which the line of each store starts
        self.slope = np.zeros(len(stores))
        self.lower = np.array([run.bounds[name][0] for name in stores])
        self.upper = np.array([run.bounds[name][1] for name in stores])
        self.requests = [flow.request for flow in flows]
        self.capped = [k for k, flow in enumerate(flows) if flow.capacity is not None]
        self.capacities = [flows[k].capacity for k in self.capped]
        # A request or a capacity that is a formula has its pieces from the family.
        self.recorded = [
            (k, name) for k, name in enumerate(self.requests) if plan.values[name].kind == FORMULA
        ]
        self.recorded += [
            (k, name) for k, name in zip(self.capped, self.capacities) if plan.values[name].kind == FORMULA
        ]
        self.recorder.formulas.update(name for _, name in self.recorded)
        self.stepped = frozenset(name for connected in sets for name in connected.stepped)
        self.asked = np.full(len(flows), np.nan)
        self.wanted = np.zeros(len(flows))  # the request of each flow, before its capacity
        self.amounts = HeldAmounts(t, len(flows))
        self.rate = np.zeros(len(flows))
        self.version = np.zeros(len(flows), dtype=np.int64)
        self.due = []  # (time, row, version) of the rows whose store reaches its bound
        self.settings = {}  # the formula values recorded last, by name
        self.place = place
        self.row = {name: k for k, name in enumerate(self.flows)}
        self.dead = np.zeros(len(flows), dtype=bool)  # the rows of sets that left the family
        self.alive = bool(len(flows))

    def __len__(self):
        return len(self.flows)

    # ---- the rates ------------------------------------------------------------------------------

    def _asked(self, t):
        """What each flow asks at time t: its request, within its capacity."""
        asked = np.array(self.columns.at(self.requests, t), dtype=float)
        self.wanted = asked.copy()
        if self.capped:
            capacities = np.array(self.columns.at(self.capacities, t), dtype=float)
            asked[self.capped] = np.minimum(asked[self.capped], capacities)
        if not np.all(np.isfinite(asked)):
            bad = [self.flows[k] for k in np.flatnonzero(~np.isfinite(asked))]
            raise SimulationError(f'Nonfinite flow rates at {t:g} h: {bad}')
        if np.any(asked < 0):
            bad = [self.flows[k] for k in np.flatnonzero(asked < 0)]
            raise SimulationError(f'Negative flow rates: {bad}')
        if self.recorded:
            names = [name for _, name in self.recorded]
            for name, number in zip(names, self.columns.at(names, t).tolist()):
                if self.settings.get(name) != number:
                    self.settings[name] = number
                    self.recorder.add(name, t, number, 0.0)
        return asked

    def _value(self, store, t):
        return self.y[store] + self.slope[store] * (t - self.since[store])

    def _start(self, k, t):
        """Row k delivers what it asks from time t, unless a bound holds it back: its stores start
        their lines there, and the time at which one reaches its bound is due."""
        source, sink, asked = self.source[k], self.sink[k], self.asked[k]
        ends = [end for end in (source, sink) if end >= 0]
        for end in ends:
            self.y[end], self.since[end] = self._value(end, t), t
        held = (source >= 0 and self.y[source] <= self.lower[source]) or (
            sink >= 0 and self.y[sink] >= self.upper[sink]
        )
        rate = 0.0 if held else float(asked)
        if t > self.t0 and rate != self.rate[k]:
            self.amounts.change(k, t, self.rate[k])
        self.rate[k] = rate
        if t > self.t0 and held:
            for end in ends:
                self.y[end] = float(self.run.stock_balance(self.stores[end], t))
        self.version[k] += 1
        if source >= 0:
            self.slope[source] = -rate
        if sink >= 0:
            # A flow from a store into itself moves nothing.
            self.slope[sink] = 0.0 if sink == source else rate
        for end in ends:
            self.recorder.add(self.stores[end], t, float(self.y[end]), float(self.slope[end]))
        self.recorder.add(f'{self.flows[k]}.actual_rate', t, rate, 0.0)
        if rate > 0 and source != sink:
            # The store that reaches its bound first; on a tie, both.
            reach, bounded = math.inf, ()
            for end, room in (
                (source, self.y[source] - self.lower[source] if source >= 0 else math.inf),
                (sink, self.upper[sink] - self.y[sink] if sink >= 0 else math.inf),
            ):
                if math.isfinite(room):
                    at = float(t + room / rate)
                    if at < reach:
                        reach, bounded = at, (int(end),)
                    elif at == reach:
                        bounded += (int(end),)
            if reach <= self.run.clock.apart(self.plan.horizon):
                heapq.heappush(self.due, (reach, k, int(self.version[k]), bounded))

    def begin(self, t=None):
        """Every row from its start (or from time t)."""
        t = self.t0 if t is None else t
        self.asked = self._asked(t)
        for k in range(len(self.flows)):
            self._start(k, t)

    def refresh(self, t):
        """The rows whose rate changes at the key time t start again from t."""
        asked = self._asked(t)
        changed = np.flatnonzero((asked != self.asked) & ~self.dead)
        self.asked = asked
        for k in changed.tolist():
            self._start(k, t)

    # ---- the interface of a way (`ways.py`) ------------------------------------------------------

    def _transferred(self, name, t):
        if t > self.run.now:
            raise ValueError('transfer requested outside the accepted interval')
        row = self.row[name]
        return self.amounts.amount(row, t, 0 if self.dead[row] else self.rate[row])

    def retire(self, key):
        """The set `key` leaves the family: its row has no event and no refresh from now on."""
        k = self.keys[key]
        self.amounts.change(k, self.run.now, self.rate[k])
        self.dead[k] = True
        self.version[k] += 1
        self.alive = not self.dead.all()

    def answers_at(self, t, incoming, flows):
        return {f'{flow}.actual_rate': float(self.rate[self.row[flow]]) for flow in flows}

    def level_at(self, store, t):
        """The value of a store at time t, on its present line."""
        return float(self._value(self.place[store], t))

    def rate_at(self, name, t):
        """The actual rate of a flow."""
        return float(self.rate[self.row[name.rsplit('.', 1)[0]]])

    def linear(self, store):
        """The line of a store: (value, rate, since)."""
        s = self.place[store]
        return float(self.y[s]), float(self.slope[s]), float(self.since[s])

    def peek(self):
        """The time at which the next row reaches its bound, or inf."""
        due = self.due
        while due and due[0][2] != self.version[due[0][1]]:
            heapq.heappop(due)
        return due[0][0] if due else math.inf

    def step(self):
        """The next row that reaches its bound: the store is put on its bound, and the flow stops
        there. Gives the stores and the rates that change."""
        reach, k, _, bounded = heapq.heappop(self.due)
        for end in (self.source[k], self.sink[k]):
            if end >= 0:
                self.y[end], self.since[end] = self._value(end, reach), reach
        put_bounds(self, self.y, self._bounds(reach, k, bounded))
        self._start(k, reach)
        stores = [self.stores[end] for end in (self.source[k], self.sink[k]) if end >= 0]
        return stores, [f'{self.flows[k]}.actual_rate'], True

    def _bounds(self, reach, k, bounded):
        for end in bounded:
            yield reach, self.stores[end], 'lower bound' if end == self.source[k] else 'upper bound'

    def timing_events(self, through):
        for reach, k, version, bounded in due_through(self.due, through):
            if version == self.version[k]:
                yield from self._bounds(reach, k, bounded)

    def snap(self, t=None, through=None):
        """Put the rows whose contact is due on their bounds at the moment's time."""
        changed, met = [], []
        while self.due:
            reach, k, _, bounded = heapq.heappop(self.due)
            at = reach if t is None else t
            for end in (self.source[k], self.sink[k]):
                if end >= 0:
                    self.y[end], self.since[end] = self._value(end, at), at
                    self.slope[end] = 0.0
                    changed.append(self.stores[end])
            met.extend(put_bounds(self, self.y, self._bounds(reach, k, bounded)))
            self.version[k] += 1
            if through is None or self.peek() > through:
                break
        return changed, met

    def cut(self, t):
        """Nothing to commit: a line holds to its next event."""

    def advance(self, until):
        """Each row whose store reaches its bound at or before `until`, in time order."""
        while self.peek() <= until:
            self.step()


def due_through(heap, through):
    """Entries at or before the cutoff, pruning entire subtrees of the time heap."""
    pending = [0] if heap else []
    while pending:
        k = pending.pop()
        if heap[k][0] > through:
            continue
        yield heap[k]
        pending.extend(i for i in (2 * k + 1, 2 * k + 2) if i < len(heap))
