"""The spike of brief A4b: an engine whose members come and go, in plain numpy.

It is no part of napkin. It shows one way to hold what step S4 of the plan must hold, and it gives
the costs of `measure.py`. `FINDINGS.md` says which parts are proposals for the engine.

What it has:

- `Columns`: arrays of one length that grow together. A pool is a `Columns`.
- `Frames`: the pool of the occurrences of one event. A row is one occurrence, for good: its
  parameters, its locals, its step pointer, `started`, `finished`, `active`, `done`, and the ids of
  its local stores and flows. Rows are never moved and never used again, so a row number is an
  identity. A list of the active rows is kept beside the pool.
- stores and edges: every stored quantity is a row of one table of stores, and every flow a row of
  one table of edges. A store is a line between two moments (`y0 + rate * (t - t0)`). An edge joins
  the member lists of its two endpoints when its owner starts and leaves them when it finishes. The
  totals of an endpoint follow at once: the count, and the exact sum of the requests (`exact.py`).
- one sharing pass for each round over the endpoints that changed, and a restart of each store
  whose rate changed.
- `Predictions`: for each row of a pool, the time at which its condition can hold next. One row
  that changes puts one time on the timeline. Many rows that change together put one time there,
  the least of them, and the rows are found in the column when that time comes.
- the reader graph, made from the program: for each name that can be written, who reads it and
  how. The membership of a collection is such a name.
- triggers with their three resets, `after` stages, `until` gates, moves, the retirement rule, and
  the two budgets of occurrences.

What it does not have: numeric blocks (every store is a line), an edge that is limited at both
ends (that is the solve library of S2), flows with legs, reversible flows, draws and choices.
"""

from __future__ import annotations

import heapq
import math
import time as clock
from collections import Counter

import numpy as np
from exact import ExactSum, total
from expr import X, conjuncts, ev, lift, names
from program import SINK, SOURCE, After, Assign, Move, SetFlow, Start, Until

TOL = 1e-8  # a moment takes the times within this of the earliest (EVENT_TIME_TOLERANCE_H)
ATOL_FACTOR = 1e-10  # the tolerance of a store is this times its size
OUTSIDE = -1
STAGE, PRED_ROW, PRED_BULK, EXTERNAL = 0, 1, 2, 3
BULK = 8  # this many rows or more that change together are one entry of the timeline


class RunStopped(Exception):
    """The run stops, with a message that names the part."""


class Columns:
    """Arrays of one length that grow together. `n` rows are in use."""

    def __init__(self, spec, room=64):
        self.spec = dict(spec)  # name -> (dtype, fill)
        self.n, self.room = 0, room  # `room`, not `capacity`: a column may be named `capacity`
        for name, (dtype, fill) in self.spec.items():
            setattr(self, name, np.full(room, fill, dtype=dtype))

    def add(self, count=1):
        """`count` new rows with their fill values: the first of them."""
        first, need = self.n, self.n + count
        if need > self.room:
            self.room = max(need, 2 * self.room)
            for name, (dtype, fill) in self.spec.items():
                grown = np.full(self.room, fill, dtype=dtype)
                grown[:first] = getattr(self, name)[:first]
                setattr(self, name, grown)
        self.n = need
        return first

    def column(self, name, dtype, fill):
        """One more column, before any row is in use."""
        self.spec[name] = (dtype, fill)
        setattr(self, name, np.full(self.room, fill, dtype=dtype))

    def nbytes(self):
        return sum(getattr(self, name)[: self.n].nbytes for name in self.spec)


class Members:
    """The members of one endpoint collection: edge ids, in no order. Join and leave are O(1)."""

    __slots__ = ('ids', 'n')

    def __init__(self):
        self.ids, self.n = np.empty(4, dtype=np.int64), 0

    def join(self, edge):
        if self.n == len(self.ids):
            self.ids = np.concatenate([self.ids, np.empty(len(self.ids), dtype=np.int64)])
        self.ids[self.n] = edge
        self.n += 1
        return self.n - 1

    def leave(self, place):
        """Take the member at `place` out: the last member takes its place. The id of that member."""
        self.n -= 1
        moved = self.ids[self.n]
        self.ids[place] = moved
        return int(moved)

    def now(self):
        return self.ids[: self.n]


class Predictions:
    """For each row of a pool, the time at which its condition can hold next (inf: no time).

    A row that changes alone puts its own time on the timeline, with the version of the row. Rows
    that change together (`BULK` or more) put one time there, the least of them: when it comes,
    the rows that are due are found in the column, among the rows that `domain()` gives. So a
    change of a thousand predictions costs a few array operations and one entry of the timeline."""

    def __init__(self, engine, role, ident, domain):
        self.engine, self.role, self.ident, self.domain = engine, role, ident, domain
        self.pid = len(engine.predictions)
        engine.predictions.append(self)
        self.time = np.full(64, np.inf)
        self.version = np.zeros(64, dtype=np.int64)
        self.bulk = np.zeros(64, dtype=bool)
        self.wakes = []  # the times of the bulk entries on the timeline

    def fit(self, rows):
        if rows > len(self.time):
            size = max(rows, 2 * len(self.time))
            for name, fill in (('time', np.inf), ('version', 0), ('bulk', False)):
                old = getattr(self, name)
                grown = np.full(size, fill, dtype=old.dtype)
                grown[: len(old)] = old
                setattr(self, name, grown)

    def set_one(self, row, at):
        self.version[row] += 1
        self.bulk[row] = False
        self.time[row] = at
        self.engine.count['predictions: ' + self.role] += 1
        if at < np.inf:
            self.engine.push(at, PRED_ROW, self.pid, row, int(self.version[row]))

    def set_many(self, rows, times):
        if len(rows) < BULK:
            for row, at in zip(rows.tolist(), np.broadcast_to(times, rows.shape).tolist()):
                self.set_one(row, at)
            return
        self.version[rows] += 1
        self.bulk[rows] = True
        self.time[rows] = times
        self.engine.count['predictions: ' + self.role] += len(rows)
        self.wake(float(np.min(times)))

    def wake(self, at):
        if at < np.inf and (not self.wakes or at < min(self.wakes)):
            self.wakes.append(at)
            self.engine.push(at, PRED_BULK, self.pid, 0, 0)

    def clear(self, rows):
        """These rows have no prediction now: an entry of theirs on the timeline is stale."""
        self.version[rows] += 1
        self.bulk[rows] = False
        self.time[rows] = np.inf

    def due_row(self, row, version):
        return self.version[row] == version

    def due_bulk(self, at, t):
        """The rows whose bulk prediction is due at t. The next wake goes on the timeline."""
        self.wakes.remove(at)
        rows = self.domain()
        rows = rows[self.bulk[rows]]
        times = self.time[rows]
        due = times <= t + TOL
        rest = times[~due]
        if len(rest):
            self.wake(float(rest.min()))
        return rows[due]


class Cond:
    """A condition of a trigger or of a gate, read as the engine of today reads the `when` of a rule
    (`analysis.structure.classify`): a gate on values that change only at moments, clocks
    (`t >= X`), and at most one crossing, `store >= value` or `store <= value`, of a store that
    moves between moments."""

    def __init__(self, engine, x, scope):
        self.x, self.scope = lift(x), scope
        self.kind, self.gate, self.times = 'discrete', [], []
        self.var = self.value = None
        self.rising = True
        for part in conjuncts(self.x):
            found = self.crossing(engine, part)
            if found and self.var is None:
                self.kind = 'crossing'
                self.var, self.rising, self.value = found
            elif part.op in ('ge', 'gt') and part.args[0].op == 'ref' and part.args[0].args[0] == 't':
                self.times.append(part.args[1])
            elif part.op in ('le', 'lt') and part.args[1].op == 'ref' and part.args[1].args[0] == 't':
                self.times.append(part.args[0])
            else:
                if engine.moving_names(part, scope):
                    raise RunStopped(
                        f'{part}: a condition on a value that moves between moments must compare '
                        'one store with a value by >= or <='
                    )
                self.gate.append(part)
        if self.kind != 'crossing' and self.times:
            self.kind = 'timer'

    def crossing(self, engine, part):
        if part.op not in ('ge', 'le'):
            return None
        left, right = part.args
        rising = part.op == 'ge'
        if right.op == 'ref' and engine.is_moving(right.args[0], self.scope):
            left, right, rising = right, left, not rising
        if left.op != 'ref' or not engine.is_moving(left.args[0], self.scope):
            return None
        if engine.moving_names(right, self.scope):
            return None
        return left.args[0], rising, right

    def holds(self, env, reached):
        """Whether the condition holds for the rows of `env`. `reached`: the predicted time of the
        crossing of the row is a time of this moment; the crossing then holds, as a clock within
        the tolerance of its time does (D-65)."""
        found = True
        for part in self.gate:
            found = np.logical_and(found, ev(part, env))
        for at in self.times:
            found = np.logical_and(found, ev(at, env) <= env.t + TOL)
        if self.kind == 'crossing':
            level, mark = env.get(self.var), ev(self.value, env)
            past = (level >= mark) if self.rising else (level <= mark)
            found = np.logical_and(found, np.logical_or(reached, past))
        return np.broadcast_to(found, env.shape).copy() if env.shape else bool(found)

    def predict(self, env):
        """The time at which the condition can hold next for each row where it does not hold now:
        the latest clock when one is still to come, else the time at which the line of the store
        reaches the value. inf where only a write can change the answer."""
        engine, t = env.engine, env.t
        shape = env.shape or (1,)
        at = np.full(shape, np.inf)
        open_ = np.ones(shape, dtype=bool)
        for part in self.gate:
            open_ &= np.broadcast_to(ev(part, env), shape)
        latest = np.full(shape, -np.inf)
        for clock_ in self.times:
            latest = np.maximum(latest, ev(clock_, env))
        waits = latest > t + TOL
        at[open_ & waits] = latest[open_ & waits]
        if self.kind == 'crossing':
            stores = engine.stores
            ids = np.atleast_1d(env.store_ids(self.var))
            rate = stores.rate[ids]
            toward = (rate > 0) if self.rising else (rate < 0)
            mark = np.broadcast_to(ev(self.value, env), shape)
            with np.errstate(divide='ignore', invalid='ignore'):
                reach = stores.t0[ids] + (mark - stores.y0[ids]) / rate
            seek = open_ & ~waits & toward
            at[seek] = np.maximum(reach[seek], t)
        return at if env.shape else float(at[0])


class Env:
    """What an expression reads for some rows at one time. `frames` is None for the members of a
    template (`rows` are members); else `rows` are occurrences of that pool."""

    __slots__ = ('engine', 'frames', 'rows', 'shape', 't', 'template')

    def __init__(self, engine, template, frames, rows, t):
        self.engine, self.template, self.frames, self.rows, self.t = engine, template, frames, rows, t
        self.shape = rows.shape if isinstance(rows, np.ndarray) else ()

    def member(self):
        if self.frames is None:
            return self
        return Env(self.engine, self.template, None, self.frames.c.receiver[self.rows], self.t)

    def get(self, name):
        if name == 't':
            return self.t
        engine, frames = self.engine, self.frames
        if frames is not None and not name.startswith('this.'):
            head, _, prop = name.partition('.')
            if prop:  # a property of a local flow
                edge = getattr(frames.c, 'flow:' + head)[self.rows]
                return getattr(engine.edges, 'rate' if prop == 'actual_rate' else prop)[edge]
            if head in frames.stores:
                return engine.level(getattr(frames.c, 'store:' + head)[self.rows], self.t)
            return getattr(frames.c, head)[self.rows]
        if frames is not None:
            return self.member().get(name)
        template, rows, field = engine.follow(self.template, self.rows, name)
        if field in template.formulas:
            return ev(template.formulas[field], Env(engine, template, None, rows, self.t))
        if field in engine.sids[template.name]:
            return engine.level(engine.sids[template.name][field][rows], self.t)
        return engine.fields[template.name][field][rows]

    def store_ids(self, name):
        engine, frames = self.engine, self.frames
        if frames is not None and not name.startswith('this.'):
            return getattr(frames.c, 'store:' + name)[self.rows]
        env = self.member()
        template, rows, field = engine.follow(env.template, env.rows, name)
        return engine.sids[template.name][field][rows]

    def reduce(self, node):
        engine = self.engine
        env = self.member()
        op, path = node.op, node.args[0]
        template, rows, last = engine.follow(env.template, env.rows, path)
        if op in ('n_flows', 'sum_request', 'actual'):
            ids, side = engine.sids[template.name][last][rows], node.args[1]
            if isinstance(ids, np.ndarray):
                return np.array([engine.endpoint_total(op, int(s), side) for s in ids])
            return engine.endpoint_total(op, int(ids), side)
        frames = engine.frames[(template.name, last)]
        if op == 'count_occ':
            return frames.started_count[rows]
        if op == 'count_done':
            return frames.done_count[rows]
        if op == 'any_active':
            return frames.active_count[rows] > 0
        newest = frames.newest[rows]
        if np.any(newest < 0):
            raise RunStopped(f'{node}: no occurrence has started (t = {self.t:g} h)')
        if op == 'since':
            return self.t - frames.c.started[newest]
        return Env(engine, template, frames, newest, self.t).get(node.args[1])


class Frames:
    """The pool of the occurrences of one event (see the module)."""

    def __init__(self, engine, template, event, members):
        self.engine, self.template, self.event = engine, template, event
        self.pool = len(engine.pools)
        engine.pools.append(self)
        spec = {
            'receiver': (np.int64, -1),
            'started': (np.float64, np.nan),
            'finished': (np.float64, np.nan),
            'due': (np.float64, np.nan),
            'step': (np.int16, 0),
            'active': (bool, False),
            'done': (bool, False),
            'version': (np.int64, 0),
            'before': (np.int64, -1),  # the occurrence that its receiver started before it
            'place': (np.int64, -1),  # its place in the list of the active rows
        }
        self.params = [name for name, _, _ in event.params]
        self.locals = [name for name, _ in event.locals]
        self.stores = {store.name: store for store in event.stores}
        self.flows = {flow.name: flow for flow in event.flows}
        for name in self.params:
            spec[name] = (np.float64, np.nan)
            spec['arg:' + name] = (np.float64, np.nan)  # the argument as it was given
        for name in self.locals:
            spec[name] = (np.float64, np.nan)
        for name in self.stores:
            spec['store:' + name] = (np.int64, -1)
        for name in self.flows:
            spec['flow:' + name] = (np.int64, -1)
        self.c = Columns(spec)
        self.alive, self.n_alive = np.empty(64, dtype=np.int64), 0
        # For each receiver: its newest occurrence, and the three counts that every model reads.
        self.newest = np.full(members, -1, dtype=np.int64)
        self.started_count = np.zeros(members, dtype=np.int64)
        self.done_count = np.zeros(members, dtype=np.int64)
        self.active_count = np.zeros(members, dtype=np.int64)
        self.gates = {}  # step -> (Cond, Predictions)
        self.gate_reached = np.full(64, -1, dtype=np.int64)
        self.bounds = {}  # local store -> Predictions of the time at which it reaches a bound
        self.decl = {}  # local flow -> its place among the flow declarations of the program

    def active_rows(self):
        return self.alive[: self.n_alive]

    def add(self):
        row = self.c.add()
        if self.n_alive == len(self.alive):
            self.alive = np.concatenate([self.alive, np.empty(len(self.alive), dtype=np.int64)])
        self.alive[self.n_alive] = row
        self.c.place[row] = self.n_alive
        self.n_alive += 1
        if row >= len(self.gate_reached):
            self.gate_reached = np.concatenate([self.gate_reached, np.full(len(self.gate_reached), -1, np.int64)])
        for _, predictions in self.gates.values():
            predictions.fit(row + 1)
        for predictions in self.bounds.values():
            predictions.fit(row + 1)
        return row

    def retire(self, row):
        """The row is no longer active. It stays in the pool."""
        place = self.c.place[row]
        self.n_alive -= 1
        moved = self.alive[self.n_alive]
        self.alive[place] = moved
        self.c.place[moved] = place
        self.c.place[row] = -1

    def name(self, row):
        return f'{self.engine.member_name(self.template, int(self.c.receiver[row]))}.{self.event.name}#{int(row)}'


class TriggerState:
    def __init__(self, engine, template, event, k, trigger, members):
        self.template, self.event, self.k, self.trigger = template, event, k, trigger
        self.ident = (template.name, event.name, k)
        scope = ('member', template.name)
        self.cond = Cond(engine, trigger.when, scope)
        self.reset = trigger.reset
        self.rcond = Cond(engine, trigger.reset[1], scope) if trigger.reset and trigger.reset[0] == 'when' else None
        self.armed = np.ones(members, dtype=bool)
        # The moment at which a prediction came due; -1: none yet (moment 0 is the setup).
        self.reached = np.full(members, -1, dtype=np.int64)
        self.reset_reached = np.full(members, -1, dtype=np.int64)
        every = np.arange(members)
        self.main = Predictions(engine, 'trigger', ('trigger', *self.ident), lambda: every)
        self.again = Predictions(engine, 'reset', ('reset', *self.ident), lambda: every)
        self.main.fit(members)
        self.again.fit(members)
        self.fired = 0


class Engine:
    def __init__(
        self,
        templates,
        members=None,
        links=None,
        names=None,
        record=False,
        forget_membership=False,
        max_occurrences=1_000_000,
        max_active=100_000,
        max_rounds=1_000,
        timing=False,
    ):
        """`members`: {template: how many}, 1 by default. `links`: {(template, link): the member of
        the other template that each member links to}. `forget_membership`: the fault of the 6 h
        case: a member that joins or leaves changes the rates, and no prediction is made again."""
        self.templates = {template.name: template for template in templates}
        self.members = {name: int((members or {}).get(name, 1)) for name in self.templates}
        self.links = {key: np.asarray(value, dtype=np.int64) for key, value in (links or {}).items()}
        self.member_names = names or {}
        self.record, self.forget_membership = record, forget_membership
        self.max_occurrences, self.max_active, self.max_rounds = max_occurrences, max_active, max_rounds
        self.now, self.moment, self.rounds = 0.0, 0, 0
        self.heap, self.seq = [], 0
        self.count = Counter()
        self.timing, self.spent = timing, Counter()
        self.log = []  # (t, text) of what each moment did, when `self.say` is set
        self.say = False
        self.pieces = []  # with `record`: (store, t, level, rate) at each restart
        self.predictions, self.pools = [], []
        self.stores = Columns(
            {
                'y0': (np.float64, 0.0),
                't0': (np.float64, 0.0),
                'rate': (np.float64, 0.0),
                'version': (np.int64, 0),
                'lower': (np.float64, 0.0),
                'upper': (np.float64, np.inf),
                'atol': (np.float64, 0.0),
                'alive': (bool, True),
                'rest': (np.int8, 0),  # -1: it rests on its lower bound; +1: on its upper bound
                'spool': (np.int32, -1),  # its pool of stores
                'row': (np.int64, -1),  # its member, or its occurrence
                'out_cap': (np.float64, np.inf),
                'in_cap': (np.float64, np.inf),
                'n_in': (np.int32, 0),
                'n_out': (np.int32, 0),
            }
        )
        self.edges = Columns(
            {
                'src': (np.int64, OUTSIDE),
                'dst': (np.int64, OUTSIDE),
                'request': (np.float64, 0.0),
                'capacity': (np.float64, np.inf),
                'rate': (np.float64, 0.0),
                'rank': (np.float64, np.nan),
                'alive': (bool, False),
                'out_place': (np.int64, -1),
                'in_place': (np.int64, -1),
                'pool': (np.int32, -1),  # the pool of the occurrence that owns it; -1: an entity
                'owner': (np.int64, -1),
                'decl': (np.int32, -1),
            }
        )
        self.outs, self.ins = [], []  # for each store: Members, or None while it has none
        self.out_sum, self.in_sum = [], []  # for each store: the ExactSum of the requests
        self.spools = []  # (kind, template, event or None, store, Predictions for its bounds)
        self.spool_of = {}
        self.flow_decls = []  # (scope, flow) of each flow declaration
        self.fields, self.sids, self.frames, self.triggers = {}, {}, {}, {}
        self.readers = {}
        self.back = {}  # (template, link) -> {member of the target: the members that link to it}
        for key, to in self.links.items():
            found = {}
            for member, target in enumerate(to.tolist()):
                found.setdefault(target, []).append(member)
            self.back[key] = {target: np.array(rows, dtype=np.int64) for target, rows in found.items()}
        self.moving = self.moving_stores()
        self.build()
        # What a round keeps until its next phase.
        self.written = {}  # key -> [rows]
        self.dirty = set()  # (store, side) endpoints whose sharing is made again
        self.unrated = set()  # stores whose rate is made again
        self.queued, self.released = [], []
        self.due, self.read_triggers, self.read_gates, self.reeval = [], {}, {}, {}
        self.from_network = set()
        self.setup()

    # ---- the program -----------------------------------------------------------------------------

    def moving_stores(self):
        """The stores that move between moments: each end of a flow, of an entity or of an event."""
        found = set()
        for template in self.templates.values():
            scopes = [(('member', template.name), template.flows)]
            scopes += [(('frame', template.name, event.name), event.flows) for event in template.events]
            for scope, flows in scopes:
                for flow in flows:
                    for end in (flow.source, flow.sink):
                        if end not in (SOURCE, SINK):
                            found.add(self.store_key(end, scope))
        return found

    def store_key(self, path, scope):
        """The key of the pool of the store that a path names in a scope."""
        if scope[0] == 'frame' and not path.startswith('this.'):
            return ('lstore', scope[1], scope[2], path)
        template, _, field = self.follow(self.templates[scope[1]], None, path)
        return ('store', template.name, field)

    def follow(self, template, rows, path):
        """(template, rows, last name) of a path `this.a.b` from the members `rows` of a template."""
        parts = path.split('.')
        if parts[0] != 'this':
            raise RunStopped(f'{path}: a path of a member starts with this')
        for link in parts[1:-1]:
            if rows is not None:
                rows = self.links[(template.name, link)][rows]
            template = self.templates[template.links[link]]
        return template, rows, parts[-1]

    def is_store(self, name, scope):
        if scope[0] == 'frame' and not name.startswith('this.'):
            event = self.templates[scope[1]].event(scope[2])
            return any(store.name == name for store in event.stores)
        if not name.startswith('this.'):
            return False
        template, _, field = self.follow(self.templates[scope[1]], None, name)
        return any(store.name == field for store in template.stores)

    def is_moving(self, name, scope):
        return name != 't' and self.is_store(name, scope) and self.store_key(name, scope) in self.moving

    def moving_names(self, x, scope):
        """The names of an expression that move between moments: `t`, and each store with a flow."""
        found = set()
        for name in self.expanded(x, scope):
            if name == 't' or (isinstance(name, str) and self.is_moving(name, scope)):
                found.add(name)
        return found

    def expanded(self, x, scope):
        """The names that an expression reads, with each formula of a member opened."""
        found = set()
        for name in names(lift(x)):
            if isinstance(name, str) and name.startswith('this.'):
                template, _, field = self.follow(self.templates[scope[1]], None, name)
                if field in template.formulas:
                    prefix = name.rsplit('.', 1)[0]
                    for inner in self.expanded(template.formulas[field], ('member', template.name)):
                        found.add(self.rebased(inner, prefix))
                    continue
            found.add(name)
        return found

    @staticmethod
    def rebased(name, prefix):
        """A name that a formula of the member at `prefix` reads, as its reader names it."""
        if isinstance(name, tuple):
            return (name[0], prefix + name[1][4:], *name[2:])
        return prefix + name[4:] if name.startswith('this.') else name

    def build(self):
        for template in self.templates.values():
            n = self.members[template.name]
            self.fields[template.name] = {
                name: np.full(n, start, dtype=np.float64) for name, start in template.fields.items()
            }
            self.sids[template.name] = {}
            for store in template.stores:
                first = self.new_stores(n)
                ids = np.arange(first, first + n)
                self.sids[template.name][store.name] = ids
                key = ('store', template.name, store.name)
                predictions = Predictions(self, 'bound', key, lambda n=n: np.arange(n))
                predictions.fit(n)
                self.spool_of[key] = len(self.spools)
                self.spools.append(('entity', template, None, store, predictions))
                self.stores.spool[ids] = self.spool_of[key]
                self.stores.row[ids] = np.arange(n)
        for template in self.templates.values():
            n = self.members[template.name]
            for event in template.events:
                frames = self.frames[(template.name, event.name)] = Frames(self, template, event, n)
                scope = ('frame', template.name, event.name)
                for store in event.stores:
                    key = ('lstore', template.name, event.name, store.name)
                    predictions = Predictions(self, 'bound', key, frames.active_rows)
                    frames.bounds[store.name] = predictions
                    self.spool_of[key] = len(self.spools)
                    self.spools.append(('local', template, event, store, predictions))
                for flow in event.flows:
                    frames.decl[flow.name] = len(self.flow_decls)
                    self.flow_decls.append((scope, flow))
                for place, step in enumerate(event.steps):
                    if isinstance(step, Until):
                        cond = Cond(self, step.cond, scope)
                        predictions = Predictions(self, 'gate', (frames.pool, place), frames.active_rows)
                        frames.gates[place] = (cond, predictions)
                        self.reads(cond.x, scope, ('gate', frames.pool, place))
            for flow in template.flows:
                self.flow_decls.append((('member', template.name), flow))
        for template in self.templates.values():
            n = self.members[template.name]
            for event in template.events:
                for k, trigger in enumerate(event.triggers):
                    state = TriggerState(self, template, event, k, trigger, n)
                    self.triggers[state.ident] = state
                    scope = ('member', template.name)
                    self.reads(state.cond.x, scope, ('trigger', *state.ident))
                    if state.rcond is not None:
                        self.reads(state.rcond.x, scope, ('trigger', *state.ident))
        for decl, (scope, flow) in enumerate(self.flow_decls):
            for value in (flow.request, flow.capacity):
                if isinstance(value, X):
                    if self.moving_names(value, scope):
                        raise RunStopped(
                            f'{flow.name}: a request or a capacity that reads a value that moves between '
                            'moments is outside the spike (a numeric block of the engine)'
                        )
                    self.reads(value, scope, ('request', decl))

    def reads(self, x, scope, reader):
        """Put a reader in the reader graph: for each name that it reads, the key that a write of
        that name has, and how the rows of the write give the rows of the reader."""
        for name in self.expanded(x, scope):
            if name == 't':
                continue
            if isinstance(name, tuple):
                op, path = name[0], name[1]
                template, how = self.owner_of(path, scope)
                last = path.rsplit('.', 1)[1]
                kind = 'flows' if op in ('n_flows', 'sum_request', 'actual') else 'occ'
                key = (kind, template.name, last)
            elif scope[0] == 'frame' and not name.startswith('this.'):
                head = name.partition('.')[0]
                event = self.templates[scope[1]].event(scope[2])
                if any(flow.name == head for flow in event.flows):
                    continue  # a property of its own flow: the stage that sets it reads again
                kind = 'lstore' if any(store.name == head for store in event.stores) else 'var'
                key, how = (kind, scope[1], scope[2], head), ('FRAME',)
            else:
                template, how = self.owner_of(name, scope)
                field = name.rsplit('.', 1)[1]
                kind = 'store' if any(store.name == field for store in template.stores) else 'field'
                key = (kind, template.name, field)
            entry = (reader, how)
            if entry not in self.readers.setdefault(key, []):
                self.readers[key].append(entry)

    def owner_of(self, path, scope):
        """(the template that owns the last name of a path, how a write there finds its readers)."""
        parts = path.split('.')
        template, chain = self.templates[scope[1]], []
        for link in parts[1:-1]:
            chain.append((template.name, link))
            template = self.templates[template.links[link]]
        how = ('LINK', *chain) if chain else ('SAME',)
        return template, (('RECEIVER', *how) if scope[0] == 'frame' else how)

    def new_stores(self, count=1):
        first = self.stores.add(count)
        self.outs.extend([None] * count)
        self.ins.extend([None] * count)
        self.out_sum.extend([None] * count)
        self.in_sum.extend([None] * count)
        return first

    def member_name(self, template, member):
        names_ = self.member_names.get(template.name)
        return names_[member] if names_ else (template.name.lower() if self.members[template.name] == 1 else f'{template.name.lower()}[{member}]')

    def store_name(self, sid):
        kind, template, event, store, _ = self.spools[self.stores.spool[sid]]
        row = int(self.stores.row[sid])
        if kind == 'entity':
            return f'{self.member_name(template, row)}.{store.name}'
        return f'{self.frames[(template.name, event.name)].name(row)}.{store.name}'

    # ---- the start of a run ----------------------------------------------------------------------

    def setup(self):
        stores = self.stores
        for template in self.templates.values():
            n = self.members[template.name]
            env = Env(self, template, None, np.arange(n), 0.0)
            for store in template.stores:
                ids = self.sids[template.name][store.name]
                for name, source in (('y0', store.start), ('lower', store.lower), ('upper', store.upper)):
                    getattr(stores, name)[ids] = ev(lift(source), env)
                stores.out_cap[ids] = ev(lift(store.out_capacity), env)
                stores.in_cap[ids] = ev(lift(store.in_capacity), env)
                self.size(ids)
                if self.record:
                    self.pieces.extend((int(sid), 0.0, float(stores.y0[sid]), 0.0) for sid in ids)
        for decl, (scope, flow) in enumerate(self.flow_decls):
            if scope[0] != 'member':
                continue
            template = self.templates[scope[1]]
            for member in range(self.members[template.name]):
                env = Env(self, template, None, member, 0.0)
                self.join(decl, flow, env, -1, member)
        self.settle(0.0, first=True)
        for state in self.triggers.values():
            self.read_triggers[state.ident] = [np.arange(self.members[state.template.name])]
        self.conditions(0.0)
        self.push(0.0, EXTERNAL, -1, 0, 0)

    def size(self, ids):
        """The tolerance of some stores: `ATOL_FACTOR` times the largest of 1, the start and the
        finite bounds, as the engine sizes a quantity (`Run.sizes`)."""
        stores = self.stores
        size = np.maximum(1.0, np.abs(stores.y0[ids]))
        for bound in (stores.lower[ids], stores.upper[ids]):
            size = np.maximum(size, np.where(np.isfinite(bound), np.abs(bound), 0.0))
        stores.atol[ids] = ATOL_FACTOR * size

    # ---- the timeline ------------------------------------------------------------------------------

    def push(self, at, kind, a, b, version):
        self.seq += 1
        self.count['timeline entries'] += 1
        heapq.heappush(self.heap, (float(at), self.seq, kind, int(a), int(b), int(version)))

    def start_at(self, at, template, event, member=0, args=()):
        """A start from outside the model, as a setup line or a test makes it."""
        self.queued_later = getattr(self, 'queued_later', [])
        self.queued_later.append((float(at), template, event, int(member), tuple(args)))
        self.push(at, EXTERNAL, len(self.queued_later) - 1, 0, 1)

    def write_at(self, at, template, field, value, member=0):
        """A write of a field from outside the model."""
        self.queued_later = getattr(self, 'queued_later', [])
        self.queued_later.append((float(at), template, None, int(member), (field, value)))
        self.push(at, EXTERNAL, len(self.queued_later) - 1, 0, 1)

    def run(self, until):
        """Go to the time `until`: every moment at or before it is settled."""
        heap = self.heap
        while heap and heap[0][0] <= until + TOL:
            at = heap[0][0]
            if self.stale(heap[0]):
                heapq.heappop(heap)
                continue
            self.at_moment(min(at, until))
        self.now = until
        return self

    def stale(self, entry):
        _, _, kind, a, b, version = entry
        if kind == STAGE:
            return self.pools[a].c.version[b] != version
        if kind == PRED_ROW:
            return not self.predictions[a].due_row(b, version)
        return False

    def at_moment(self, t):
        self.now = t
        self.moment += 1
        self.count['moments'] += 1
        heap, rounds = self.heap, 0
        while True:
            took = False
            while heap and heap[0][0] <= t + TOL:
                entry = heapq.heappop(heap)
                if not self.stale(entry):
                    self.take(entry, t)
                    took = True
            if not (took or self.queued or self.released or self.due):
                break
            rounds += 1
            if rounds > self.max_rounds:
                raise RunStopped(
                    f'The moment t = {t:g} h does not settle within {self.max_rounds} rounds; '
                    f'next: {self.next_name()}'
                )
            self.round(t)
        self.count['rounds'] += rounds

    def next_name(self):
        if self.queued:
            template, event, member, _ = self.queued[0]
            return f'a start of {self.member_name(self.templates[template], member)}.{event}'
        if self.due:
            pool, row = self.due[0]
            return f'a stage of {self.pools[pool].name(row)}'
        return 'a condition'

    def take(self, entry, t):
        """One time of the timeline came: what is due goes to the round."""
        at, _, kind, a, b, version = entry
        if kind == STAGE:
            self.due.append((a, b))
        elif kind == EXTERNAL:
            if version:
                _, template, event, member, args = self.queued_later[a]
                if event is None:
                    self.fields[template][args[0]][member] = args[1]
                    self.wrote(('field', template, args[0]), member)
                else:
                    self.queued.append((template, event, member, args))
        else:
            predictions = self.predictions[a]
            rows = np.array([b]) if kind == PRED_ROW else predictions.due_bulk(at, t)
            if len(rows):
                self.reached(predictions, rows)

    def reached(self, predictions, rows):
        """The predicted times of these rows came."""
        role, ident = predictions.role, predictions.ident
        if role == 'gate':
            frames = self.pools[ident[0]]
            frames.gate_reached[rows] = self.moment
            self.read_gates.setdefault(ident, []).append(rows)
        elif role == 'bound':
            self.at_bound(ident, rows)
        else:
            state = self.triggers[ident[1:]]
            (state.reached if role == 'trigger' else state.reset_reached)[rows] = self.moment
            self.read_triggers.setdefault(ident[1:], []).append(rows)

    # ---- one round ---------------------------------------------------------------------------------

    def round(self, t):
        """One round of a moment (spec, "Solver and execution contract"): the stages that are due
        commit; the starts, the finishes and the flows that join and leave are registered; the
        sharing is made once; then the conditions that read what changed are read."""
        tick = clock.perf_counter() if self.timing else 0.0
        released, self.released = self.released, []
        for pool, row in released:
            self.advance(self.pools[pool], row, t)
        due, self.due = sorted(set(self.due)), []
        for pool, row in due:
            self.stage(self.pools[pool], row, t)
        queued, self.queued = self.queued, []
        for template, event, member, args in queued:
            self.start(self.frames[(template, event)], member, args, t)
        if self.timing:
            tock = clock.perf_counter()
            self.spent['commit'] += tock - tick
            tick = tock
        self.settle(t)
        if self.timing:
            tock = clock.perf_counter()
            self.spent['network'] += tock - tick
            tick = tock
        self.conditions(t)
        if self.timing:
            self.spent['conditions'] += clock.perf_counter() - tick

    def settle(self, t, first=False):
        """The requests that read what was written, then one pass of the sharing, then the restart
        of each store whose rate changed."""
        self.requests(t)
        if self.dirty or self.unrated or first:
            self.network(t, first)

    # ---- occurrences -------------------------------------------------------------------------------

    def start(self, frames, member, args, t):
        template, event, c = frames.template, frames.event, frames.c
        if c.n >= self.max_occurrences:
            raise RunStopped(
                f'The run stops at t = {t:g} h: {template.name}.{event.name} has started {c.n} occurrences '
                f'(max_occurrences). {c.n - frames.n_alive} have finished and {frames.n_alive} are active.'
            )
        if frames.n_alive >= self.max_active:
            oldest = int(frames.active_rows()[np.argmin(c.started[frames.active_rows()])])
            step = event.steps[c.step[oldest]] if c.step[oldest] < len(event.steps) else None
            waits = f'`until {step.cond}`' if isinstance(step, Until) else 'a stage'
            same = int(np.count_nonzero(c.step[frames.active_rows()] == c.step[oldest]))
            raise RunStopped(
                f'The run stops at t = {t:g} h: {frames.n_alive} occurrences of {template.name}.{event.name} '
                f'are active at once (max_active). The oldest, {frames.name(oldest)}, started at '
                f't = {c.started[oldest]:g} h and waits at {waits}; {same} of them wait at that step.'
            )
        row = frames.add()
        self.count['starts'] += 1
        c.receiver[row], c.started[row], c.active[row] = member, t, True
        c.before[row] = frames.newest[member]
        frames.newest[member] = row
        frames.started_count[member] += 1
        frames.active_count[member] += 1
        if len(args) != len(frames.params):
            raise RunStopped(f'{frames.name(row)}: {len(frames.params)} arguments, not {len(args)}')
        for (name, low, high), value in zip(event.params, args):
            if not low <= value <= high:
                raise RunStopped(f'{frames.name(row)}: {name} = {value:g} is outside [{low:g}, {high:g}]')
            getattr(c, name)[row] = value
            getattr(c, 'arg:' + name)[row] = value
        env = Env(self, template, frames, row, t)
        for name, source in event.locals:
            getattr(c, name)[row] = ev(lift(source), env)
        stores = self.stores
        for store in event.stores:
            sid = self.new_stores()
            getattr(c, 'store:' + store.name)[row] = sid
            stores.y0[sid], stores.t0[sid] = ev(lift(store.start), env), t
            stores.lower[sid], stores.upper[sid] = ev(lift(store.lower), env), ev(lift(store.upper), env)
            stores.spool[sid] = self.spool_of[('lstore', template.name, event.name, store.name)]
            stores.row[sid] = row
            self.size(np.array([sid]))
            if self.record:
                self.pieces.append((sid, t, float(stores.y0[sid]), 0.0))
        for flow in event.flows:
            getattr(c, 'flow:' + flow.name)[row] = self.join(frames.decl[flow.name], flow, env, frames.pool, row)
        self.wrote(('occ', template.name, event.name), member)
        if self.say:
            self.log.append((t, f'{frames.name(row)} starts'))
        self.advance(frames, row, t)

    def advance(self, frames, row, t):
        """The occurrence comes to its next step: the delay of an `after` is captured now; a gate
        that holds lets it pass at once; after its last step it finishes."""
        c, steps = frames.c, frames.event.steps
        while True:
            place = int(c.step[row])
            c.version[row] += 1
            if place >= len(steps):
                self.finish(frames, row, t)
                return
            step = steps[place]
            env = Env(self, frames.template, frames, row, t)
            if isinstance(step, After):
                delay = float(ev(lift(step.delay), env))
                if not (math.isfinite(delay) and delay >= 0):
                    raise RunStopped(f'{frames.name(row)}: a delay is a finite time from 0, not {delay} h')
                c.due[row] = t + delay
                self.push(t + delay, STAGE, frames.pool, row, c.version[row])
                return
            cond, predictions = frames.gates[place]
            if cond.holds(env, False):
                c.step[row] += 1
                continue
            predictions.set_one(row, cond.predict(env))
            return

    def stage(self, frames, row, t):
        """The stage of an `after` step: its guard is read once, its statements run in order and
        see the writes before them, and the starts that it queues are registered when it commits."""
        c = frames.c
        step = frames.event.steps[c.step[row]]
        env = Env(self, frames.template, frames, row, t)
        self.count['stages'] += 1
        if step.guard is None or ev(lift(step.guard), env):
            for statement in step.body:
                self.statement(frames, row, statement, env, t)
        c.step[row] += 1
        c.due[row] = np.nan
        self.advance(frames, row, t)

    def statement(self, frames, row, statement, env, t):
        c, template = frames.c, frames.template
        if isinstance(statement, Assign):
            value = ev(lift(statement.value), env)
            target = statement.target
            if target.startswith('this.'):
                owner, member, field = self.follow(template, int(c.receiver[row]), target)
                if field in self.sids[owner.name]:
                    raise RunStopped(f'{frames.name(row)}: {target} is a store: a flow or a move changes it')
                column, key, place = self.fields[owner.name][field], ('field', owner.name, field), member
            else:
                column, key, place = getattr(c, target), ('var', template.name, frames.event.name, target), row
            old = column[place]
            column[place] = value if statement.op == '=' else old + value if statement.op == '+=' else old - value
            self.wrote(key, place)
        elif isinstance(statement, Move):
            amount = float(ev(lift(statement.amount), env))
            if not (math.isfinite(amount) and amount >= 0):
                raise RunStopped(f'{frames.name(row)}: a move takes a finite amount from 0, not {amount}')
            source, dest = int(env.store_ids(statement.source)), int(env.store_ids(statement.dest))
            stores = self.stores
            have, held = float(self.level(source, t)), float(self.level(dest, t))
            left = have - amount
            if abs(left - stores.lower[source]) <= stores.atol[source]:
                # A move that would leave less than the tolerance behind moves everything.
                amount, left = have - float(stores.lower[source]), float(stores.lower[source])
            if left < stores.lower[source] or held + amount > stores.upper[dest] + stores.atol[dest]:
                raise RunStopped(
                    f'{frames.name(row)} at t = {t:g} h: a move of {amount:g} does not fit: '
                    f'{self.store_name(source)} holds {have:g} and {self.store_name(dest)} holds {held:g} '
                    f'of {stores.upper[dest]:g}'
                )
            self.set_level(source, left, t)
            self.set_level(dest, min(held + amount, float(stores.upper[dest])), t)
        elif isinstance(statement, Start):
            owner, member, name = self.follow(template, int(c.receiver[row]), statement.event)
            args = tuple(float(ev(lift(arg), env)) for arg in statement.args)
            self.queued.append((owner.name, name, member, args))
        elif isinstance(statement, SetFlow):
            edge = int(getattr(c, 'flow:' + statement.flow)[row])
            value = float(ev(lift(statement.value), env))
            self.set_edge(edge, statement.prop, value)
        else:
            raise TypeError(statement)

    def finish(self, frames, row, t):
        """The occurrence finishes. Its flows leave their endpoints together; each local store must
        be empty within its tolerance (the retirement rule); the row stays as a record."""
        c, event, stores = frames.c, frames.event, self.stores
        member = int(c.receiver[row])
        for flow in event.flows:
            self.leave(int(getattr(c, 'flow:' + flow.name)[row]))
        for store in event.stores:
            sid = int(getattr(c, 'store:' + store.name)[row])
            left = float(self.level(sid, t))
            if abs(left) > stores.atol[sid]:
                raise RunStopped(
                    f'{frames.name(row)} cannot finish at t = {t:g} h: its store {store.name} still '
                    f'holds {left:g}. Wait until it is empty, move the rest to a stock, or send it to SINK.'
                )
            stores.y0[sid], stores.t0[sid], stores.rate[sid] = 0.0, t, 0.0
            stores.alive[sid] = False
            stores.version[sid] += 1
            frames.bounds[store.name].clear(row)
            self.unrated.discard(sid)
            if self.record:
                self.pieces.append((sid, t, 0.0, 0.0))
        for _, predictions in frames.gates.values():
            predictions.clear(row)
        c.active[row], c.done[row], c.finished[row] = False, True, t
        c.version[row] += 1
        frames.retire(row)
        frames.active_count[member] -= 1
        frames.done_count[member] += 1
        self.count['finishes'] += 1
        self.wrote(('occ', frames.template.name, event.name), member)
        if self.say:
            self.log.append((t, f'{frames.name(row)} finishes'))

    # ---- flows that join and leave -----------------------------------------------------------------

    def join(self, decl, flow, env, pool, owner):
        """A flow joins the network: one new edge, in the member lists of its two endpoints."""
        edges = self.edges
        edge = edges.add()
        edges.pool[edge], edges.owner[edge], edges.decl[edge] = pool, owner, decl
        edges.request[edge] = ev(lift(flow.request), env)
        edges.capacity[edge] = ev(lift(flow.capacity), env)
        if flow.rank is not None:
            edges.rank[edge] = ev(lift(flow.rank), env)
        if not (edges.request[edge] >= 0 and edges.capacity[edge] >= 0):
            raise RunStopped(f'{flow.name}: a request and a capacity are at or above zero')
        edges.alive[edge] = True
        for end, column, members, sums, place, count in (
            (flow.source, edges.src, self.outs, self.out_sum, edges.out_place, self.stores.n_out),
            (flow.sink, edges.dst, self.ins, self.in_sum, edges.in_place, self.stores.n_in),
        ):
            if end in (SOURCE, SINK):
                continue
            sid = int(env.store_ids(end))
            column[edge] = sid
            if members[sid] is None:
                members[sid], sums[sid] = Members(), ExactSum()
            place[edge] = members[sid].join(edge)
            sums[sid].add(float(edges.request[edge]))
            count[sid] += 1
            self.dirty.add((sid, 'out' if column is edges.src else 'in'))
            self.membership(sid)
        self.count['joins'] += 1
        return edge

    def leave(self, edge):
        """A flow leaves the network: out of both member lists together. The edge stays as a
        record: its key, its endpoints, its last request, and a rate of zero."""
        edges = self.edges
        for column, members, sums, place, count, side in (
            (edges.src, self.outs, self.out_sum, edges.out_place, self.stores.n_out, 'out'),
            (edges.dst, self.ins, self.in_sum, edges.in_place, self.stores.n_in, 'in'),
        ):
            sid = int(column[edge])
            if sid == OUTSIDE:
                continue
            moved = members[sid].leave(int(place[edge]))
            if moved != edge:
                place[moved] = place[edge]
            place[edge] = -1
            sums[sid].add(-float(edges.request[edge]))
            count[sid] -= 1
            self.dirty.add((sid, side))
            self.unrated.add(sid)
            self.membership(sid)
        edges.alive[edge] = False
        edges.rate[edge] = 0.0
        self.count['leaves'] += 1

    def membership(self, sid):
        """The collection of the flows at a store of an entity changed: that is a write of a name."""
        kind, template, _, store, _ = self.spools[self.stores.spool[sid]]
        if kind == 'entity':
            self.wrote(('flows', template.name, store.name), int(self.stores.row[sid]))

    def set_edge(self, edge, prop, value):
        edges = self.edges
        if prop == 'request':
            for column, sums in ((edges.src, self.out_sum), (edges.dst, self.in_sum)):
                if column[edge] != OUTSIDE:
                    sums[column[edge]].add(-float(edges.request[edge]))
                    sums[column[edge]].add(value)
        getattr(edges, prop)[edge] = value
        for column, side in ((edges.src, 'out'), (edges.dst, 'in')):
            if column[edge] != OUTSIDE:
                self.dirty.add((int(column[edge]), side))
                self.membership(int(column[edge]))

    def endpoint_total(self, op, sid, side):
        """The three totals of an endpoint: the count of its connections, the sum of their requests,
        and its actual rate, which is the sum of their rates."""
        members = (self.outs if side == 'out' else self.ins)[sid]
        if members is None or members.n == 0:
            return 0 if op == 'n_flows' else 0.0
        if op == 'n_flows':
            return members.n
        if op == 'sum_request':
            return (self.out_sum if side == 'out' else self.in_sum)[sid].value
        return total(self.edges.rate[members.now()].tolist())

    # ---- the sharing, and the restarts ---------------------------------------------------------------

    def requests(self, t):
        """Evaluate again the requests and the capacities that read a name that was written."""
        self.resolve_writes(t, only='request')
        reeval, self.reeval = self.reeval, {}
        edges = self.edges
        for decl, chunks in reeval.items():
            scope, flow = self.flow_decls[decl]
            for owner in np.unique(np.concatenate(chunks)).tolist():
                if scope[0] == 'member':
                    raise RunStopped('the spike makes again only the requests of flows of occurrences')
                frames = self.frames[(scope[1], scope[2])]
                if not frames.c.active[owner]:
                    continue
                edge = int(getattr(frames.c, 'flow:' + flow.name)[owner])
                env = Env(self, frames.template, frames, owner, t)
                for prop, source in (('request', flow.request), ('capacity', flow.capacity)):
                    if isinstance(source, X):
                        value = float(ev(source, env))
                        if value != getattr(edges, prop)[edge]:
                            self.set_edge(edge, prop, value)

    def network(self, t, first=False):
        """One pass of the sharing over the endpoints that changed. Then each store whose rate
        changed starts again from where it is."""
        stores, edges = self.stores, self.edges
        self.count['network passes'] += 1
        changed_many, settled = [], set()
        passes = 0
        while self.dirty:
            passes += 1
            if passes > 10_000:
                raise RunStopped('the sharing does not settle')
            sid, side = self.dirty.pop()
            members = (self.outs if side == 'out' else self.ins)[sid]
            self.unrated.add(sid)
            if members is None or members.n == 0:
                continue
            ids = members.now()
            limit = float(stores.out_cap[sid] if side == 'out' else stores.in_cap[sid])
            other = edges.dst[ids] if side == 'out' else edges.src[ids]
            if side == 'out' and stores.rest[sid] < 0:
                # It rests on its lower bound: the flows out of it share what comes in.
                limit = min(limit, self.side_total(sid, 'in'))
            if side == 'in' and stores.rest[sid] > 0:
                limit = min(limit, self.side_total(sid, 'out'))
            caps = edges.capacity[ids]
            inside = other >= 0
            decides = np.ones(len(ids), dtype=bool)
            if inside.any():
                far = other[inside]
                if side == 'out':
                    # A sink with a limit of its own decides the flows into it.
                    tight = np.isfinite(stores.in_cap[far])
                    held = stores.rest[far] > 0
                else:
                    # A flow from a store is decided at that store; a flow from outside, here.
                    tight = np.ones(len(far), dtype=bool) if not math.isfinite(limit) else (
                        np.isfinite(stores.out_cap[far]) | (stores.rest[far] < 0)
                    )
                    held = np.zeros(len(far), dtype=bool)
                if tight.any() and math.isfinite(limit):
                    raise RunStopped(
                        f'{self.store_name(sid)}: a flow that is limited at both of its ends is outside '
                        'the spike (the solve library of S2)'
                    )
                if tight.any():
                    decides[np.flatnonzero(inside)[tight]] = False
                    if side == 'out':
                        for s_far in np.unique(far[tight]).tolist():
                            if (s_far, 'in') not in settled:
                                self.dirty.add((s_far, 'in'))
                if held.any():
                    # The far end rests on its upper bound: the flow gets what that store lets out.
                    caps = caps.copy()
                    caps[np.flatnonzero(inside)[held]] = [self.side_total(int(s_far), 'out') for s_far in far[held]]
            settled.add((sid, side))
            if not decides.any():
                continue
            if decides.all():
                sums = (self.out_sum if side == 'out' else self.in_sum)[sid]
                new = share(edges.request[ids], caps, limit, edges.rank[ids], sums)
            else:
                new = edges.rate[ids].copy()
                new[decides] = np.minimum(edges.request[ids], caps)[decides]
            moved = new != edges.rate[ids]
            if not moved.any():
                continue
            which = ids[moved]
            edges.rate[which] = new[moved]
            self.count['rates made again'] += len(which)
            ends = other[moved]
            ends = ends[ends >= 0]
            if len(ends) >= BULK:
                simple = (stores.n_in[ends] + stores.n_out[ends] == 1) & (stores.rest[ends] == 0)
                if simple.all():
                    changed_many.append((ends, new[moved][other[moved] >= 0] * (1.0 if side == 'out' else -1.0)))
                    continue
            self.unrated.update(ends.tolist())
        for ends, rates in changed_many:
            self.restart_many(ends, rates, t)
        unrated, self.unrated = self.unrated, set()
        for sid in sorted(unrated):
            if not stores.alive[sid]:
                continue
            rate = self.side_total(sid, 'in') - self.side_total(sid, 'out')
            if stores.rest[sid] < 0 and rate > 0 or stores.rest[sid] > 0 and rate < 0:
                stores.rest[sid] = 0  # it leaves its bound
                self.dirty.add((sid, 'out'))
                self.dirty.add((sid, 'in'))
            elif stores.rest[sid] != 0:
                rate = 0.0
            if rate != stores.rate[sid] or first:
                self.restart(sid, t, rate=rate)
        if self.dirty:
            self.network(t)

    def side_total(self, sid, side):
        members = (self.outs if side == 'out' else self.ins)[sid]
        if members is None or members.n == 0:
            return 0.0
        if members.n == 1:
            return float(self.edges.rate[members.ids[0]])
        return total(self.edges.rate[members.now()].tolist())

    def level(self, ids, t):
        stores = self.stores
        return stores.y0[ids] + stores.rate[ids] * (t - stores.t0[ids])

    def restart(self, sid, t, rate=None, level=None):
        """The line of one store starts again at t: from a new level, or with a new rate. The time
        at which it reaches a bound is predicted again, and its readers are read again."""
        stores = self.stores
        y = float(self.level(sid, t)) if level is None else level
        if rate is None:
            rate = float(stores.rate[sid])
        stores.y0[sid], stores.t0[sid], stores.rate[sid] = y, t, rate
        stores.version[sid] += 1
        self.count['store restarts'] += 1
        if self.record:
            self.pieces.append((sid, t, y, rate))
        kind, template, event, store, predictions = self.spools[stores.spool[sid]]
        row = int(stores.row[sid])
        reach = np.inf
        if rate < 0 and math.isfinite(stores.lower[sid]):
            reach = t + (stores.lower[sid] - y) / rate
        elif rate > 0 and math.isfinite(stores.upper[sid]):
            reach = t + (stores.upper[sid] - y) / rate
        predictions.set_one(row, max(reach, t))
        if kind == 'entity':
            key = ('store', template.name, store.name)
        else:
            key = ('lstore', template.name, event.name, store.name)
        self.wrote(key, row, network=level is None)

    def restart_many(self, ids, rates, t):
        """The lines of many stores start again together with new rates: the stores of the
        occurrences that one endpoint serves. A few array operations, whatever their number."""
        stores = self.stores
        y = stores.y0[ids] + stores.rate[ids] * (t - stores.t0[ids])
        stores.y0[ids], stores.t0[ids], stores.rate[ids] = y, t, rates
        stores.version[ids] += 1
        self.count['store restarts'] += len(ids)
        if self.record:
            self.pieces.extend(zip(ids.tolist(), [t] * len(ids), y.tolist(), rates.tolist()))
        for spool in np.unique(stores.spool[ids]).tolist():
            kind, template, event, store, predictions = self.spools[spool]
            mine = stores.spool[ids] == spool
            some, rows = ids[mine], stores.row[ids[mine]]
            rate, level = rates[mine], y[mine]
            with np.errstate(divide='ignore', invalid='ignore'):
                reach = np.where(
                    rate > 0, t + (stores.upper[some] - level) / rate, t + (stores.lower[some] - level) / rate
                )
            reach = np.where((rate == 0) | ~np.isfinite(reach), np.inf, np.maximum(reach, t))
            predictions.set_many(rows, reach)
            if kind == 'entity':
                key = ('store', template.name, store.name)
            else:
                key = ('lstore', template.name, event.name, store.name)
            self.wrote(key, rows, network=True)

    def set_level(self, sid, level, t):
        """A step wrote the level of a store (a move): its line starts again from the new level."""
        stores = self.stores
        if stores.rest[sid] and stores.lower[sid] < level < stores.upper[sid]:
            stores.rest[sid] = 0
            self.dirty.add((sid, 'out'))
            self.dirty.add((sid, 'in'))
        self.restart(sid, t, level=level)

    def at_bound(self, key, rows):
        """Stores reach a bound: each is put on the bound and rests there. While it rests on its
        lower bound, the flows out of it get what comes in; on its upper bound, the flows into it
        get what goes out."""
        stores, t = self.stores, self.now
        kind, template, event, store, predictions = self.spools[self.spool_of[key]]
        if kind == 'entity':
            ids = self.sids[template.name][store.name][rows]
        else:
            ids = getattr(self.frames[(template.name, event.name)].c, 'store:' + store.name)[rows]
        for sid, row in zip(np.atleast_1d(ids).tolist(), np.atleast_1d(rows).tolist()):
            falling = stores.rate[sid] < 0
            stores.y0[sid] = stores.lower[sid] if falling else stores.upper[sid]
            stores.t0[sid], stores.rate[sid] = t, 0.0
            stores.rest[sid] = -1 if falling else 1
            stores.version[sid] += 1
            predictions.clear(row)
            self.count['bounds reached'] += 1
            if self.record:
                self.pieces.append((sid, t, float(stores.y0[sid]), 0.0))
            self.dirty.add((sid, 'out' if falling else 'in'))
            # The flows at the other side of it, too: each is held by what this store lets through.
            members = (self.ins if not falling else self.outs)[sid]
            if members is not None:
                column = self.edges.src if not falling else self.edges.dst
                for far in column[members.now()].tolist():
                    if far != OUTSIDE:
                        self.dirty.add((far, 'out' if not falling else 'in'))
            self.wrote(key, row)

    # ---- the reader graph ----------------------------------------------------------------------------

    def wrote(self, key, rows, network=False):
        """A name was written for some rows. `network`: by the sharing, after a member joined or
        left (the fault `forget_membership` drops the readers of such a write)."""
        if key not in self.readers:
            return
        if network and self.forget_membership:
            return
        self.written.setdefault(key, []).append(rows)

    def resolve_writes(self, t, only=None):
        """From what was written to who reads it: the triggers and the gates to read again, and
        the requests to evaluate again. `only='request'`: the requests alone; the rest waits for
        the sharing."""
        written, kept = self.written, {}
        self.written = {}
        for key, chunks in written.items():
            rows = np.unique(np.atleast_1d(np.concatenate([np.atleast_1d(chunk) for chunk in chunks])))
            for reader, how in self.readers[key]:
                if (reader[0] == 'request') != (only == 'request'):
                    if only == 'request':
                        kept[key] = [rows]  # its other readers are read after the sharing
                    continue
                if reader[0] == 'trigger':
                    self.read_triggers.setdefault(reader[1:], []).append(self.members_for(how, rows))
                elif reader[0] == 'gate':
                    frames = self.pools[reader[1]]
                    self.read_gates.setdefault(reader[1:], []).append(self.frames_for(frames, how, rows))
                else:
                    scope = self.flow_decls[reader[1]][0]
                    frames = self.frames[(scope[1], scope[2])]
                    self.reeval.setdefault(reader[1], []).append(self.frames_for(frames, how, rows))
        for key, chunks in kept.items():
            self.written.setdefault(key, []).extend(chunks)

    def members_for(self, how, rows):
        """The members of the reader's template that read the written rows."""
        if how[0] == 'SAME':
            return rows
        for key in reversed(how[1:]):
            back = self.back[key]
            found = [back[row] for row in rows.tolist() if row in back]
            rows = np.unique(np.concatenate(found)) if found else np.empty(0, dtype=np.int64)
        return rows

    def frames_for(self, frames, how, rows):
        """The active occurrences that read the written rows."""
        if how[0] == 'FRAME':
            return rows
        members = self.members_for(how[1:], rows)
        active = frames.active_rows()
        if len(members) == 1:
            return active[frames.c.receiver[active] == members[0]]
        return active[np.isin(frames.c.receiver[active], members)]

    def conditions(self, t):
        """Read the triggers and the gates that read what the round wrote, or whose time came."""
        self.resolve_writes(t)
        triggers, self.read_triggers = self.read_triggers, {}
        for ident in sorted(triggers):
            rows = np.unique(np.concatenate([np.atleast_1d(chunk) for chunk in triggers[ident]]))
            if len(rows):
                self.read_trigger(self.triggers[ident], rows, t)
        gates, self.read_gates = self.read_gates, {}
        for ident in sorted(gates):
            rows = np.unique(np.concatenate([np.atleast_1d(chunk) for chunk in gates[ident]]))
            if len(rows):
                self.read_gate(self.pools[ident[0]], ident[1], rows, t)

    def read_trigger(self, state, members, t):
        """Read a trigger for some members, as `Run.read_rule` reads a rule: a trigger that is not
        armed looks at its reset; one that is armed fires where its condition holds, and predicts
        the time at which it can hold where it does not."""
        template = state.template
        self.count['trigger readings'] += len(members)
        idle = members[~state.armed[members]]
        if len(idle):
            env = Env(self, template, None, idle, t)
            if state.reset is None:
                again = ~state.cond.holds(env, state.reached[idle] == self.moment)
            elif state.reset[0] == 'when':
                again = state.rcond.holds(env, state.reset_reached[idle] == self.moment)
            elif state.reset[0] == 'after':
                again = state.reset_reached[idle] == self.moment
            else:
                again = np.zeros(len(idle), dtype=bool)
            state.armed[idle[again]] = True
            state.again.clear(idle[again])
            still = idle[~again]
            if len(still) and state.rcond is not None:
                state.again.set_many(still, state.rcond.predict(Env(self, template, None, still, t)))
        ready = members[state.armed[members]]
        if not len(ready):
            return
        env = Env(self, template, None, ready, t)
        holds = state.cond.holds(env, state.reached[ready] == self.moment)
        for member in ready[holds].tolist():
            one = Env(self, template, None, member, t)
            args = tuple(float(ev(lift(arg), one)) for arg in state.trigger.args)
            state.armed[member] = False
            state.fired += 1
            state.main.clear(member)
            self.queued.append((template.name, state.event.name, member, args))
            if self.say:
                self.log.append((t, f'the trigger of {self.member_name(template, member)}.{state.event.name} fires'))
            if state.reset is not None and state.reset[0] == 'after':
                state.again.set_one(member, t + float(ev(lift(state.reset[1]), one)))
            elif state.rcond is not None:
                at = t if state.rcond.holds(one, False) else state.rcond.predict(one)
                state.again.set_one(member, at)
        waits = ready[~holds]
        if len(waits):
            state.main.set_many(waits, state.cond.predict(Env(self, template, None, waits, t)))

    def read_gate(self, frames, place, rows, t):
        """Read the gate `until C` of some occurrences: those that it lets pass go on in the next
        round; the others get the time at which C can hold."""
        c = frames.c
        rows = rows[c.active[rows] & (c.step[rows] == place)]
        if not len(rows):
            return
        cond, predictions = frames.gates[place]
        self.count['gate readings'] += len(rows)
        env = Env(self, frames.template, frames, rows, t)
        holds = cond.holds(env, frames.gate_reached[rows] == self.moment)
        passed = rows[holds]
        if len(passed):
            predictions.clear(passed)
            c.step[passed] += 1
            self.released.extend((frames.pool, row) for row in passed.tolist())
        waits = rows[~holds]
        if len(waits):
            predictions.set_many(waits, cond.predict(Env(self, frames.template, frames, waits, t)))

    # ---- reading the run -----------------------------------------------------------------------------

    def read(self, x, template, member=0):
        """The value of an expression of a member, now."""
        return ev(lift(x), Env(self, self.templates[template], None, member, self.now))

    def history(self, sid):
        """The pieces of a store, from the record: (t, level, rate)."""
        return [(t, y, rate) for store, t, y, rate in self.pieces if store == sid]


def share(requests, caps, limit, ranks, sums=None):
    """The rates of the flows of one endpoint. Each flow claims the least of its request and its
    cap. While the claims fit under the limit, each gets its claim. Else the flows with a rank are
    served in the order of the ranks, and the flows of one rank (and, last, those with none) share
    in proportion: each gets the same fraction of its request, up to its cap, and what a capped
    flow leaves goes to the others. `sums`: the exact sum of the requests, when the endpoint keeps
    it."""
    claims = np.minimum(requests, caps)
    if not math.isfinite(limit):
        return claims
    ranked = ~np.isnan(ranks)
    if not ranked.any():
        capped = not np.all(np.isinf(caps))
        return fill(requests, caps, claims, limit, None if capped or sums is None else sums.value)
    rates = np.zeros(len(requests))
    left = limit
    for rank in [*np.unique(ranks[ranked]).tolist(), None]:
        mine = ~ranked if rank is None else ranks == rank
        if not mine.any():
            continue
        rates[mine] = fill(requests[mine], caps[mine], claims[mine], left, None)
        left = max(0.0, left - total(rates[mine].tolist()))
    return rates


def fill(requests, caps, claims, limit, asked):
    """Proportional sharing of `limit` with caps: the largest fraction f, up to 1, with
    `sum(min(cap, f * request)) <= limit`."""
    if asked is None:
        asked = total(claims.tolist())
        if asked <= limit:
            return claims
        if np.all(caps >= requests):
            return requests * (limit / total(requests.tolist()))
        # Some caps bind: fill in the order of cap / request.
        with np.errstate(divide='ignore', invalid='ignore'):
            ratio = np.where(requests > 0, caps / requests, np.inf)
        order = np.argsort(ratio, kind='stable')
        rates, left, open_ = np.zeros(len(requests)), limit, total(requests.tolist())
        for place, k in enumerate(order.tolist()):
            fraction = left / open_ if open_ > 0 else 0.0
            if ratio[k] >= fraction:
                rest = order[place:]
                rates[rest] = requests[rest] * min(1.0, fraction)
                break
            rates[k] = caps[k]
            left -= caps[k]
            open_ -= requests[k]
        return rates
    if asked <= limit:
        return claims
    return requests * (limit / asked)
