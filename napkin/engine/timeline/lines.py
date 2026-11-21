"""Lines: the connected sets whose rates read nothing that moves, run together on one network, at any
size (R-A4a-04, "lines").

The requests and capacities of such a set, of its flows and of its endpoints, change only at key
times. So its rates hold from moment to moment, and each store is a straight line between moments. A
moment is a key time, or the time at which a line reaches a bound. At a moment, only the coupled parts
that the change reaches are solved again (`network.Instant`): the parts of the flows at the store
that met its bound, of the flows whose requests or capacities changed, and of the stores that left a
bound since they were last solved. Every other store keeps its line, so the cost of a moment does not
grow with the number of rows.

The rates of a moment are those that hold just after it (`network.Instant.settle`), as the oracle
settles them, so a run is the same whether a moment falls on it or not: a store rests on a bound
while it holds exactly that value and its sharing keeps it there; one that its sharing moves off a
bound is free just after, and its part is solved with it free (where that would move it back past its
bound, no rates hold just after, and the run stops by name). A store that the closed form of groups
moves off a bound (below), which a release would not change, leaves it, and its part is solved again
at the next moment of the lines (the horizon is one), from where it is then.

**Downstream only.** Where every flow of the sets is directed and rigid (it never carries more than
its request: `Plan.rigid`) and no endpoint has a capacity or a request, every part has the closed
form of groups in supply order (`network.Instant._groups`) while no store rests on its upper bound
with inflows: the outflows of a store at its lower bound share what flows in, every other flow
carries its request within its capacity. A flow's rate then depends only on what is upstream of it.
So when a store meets or leaves its bound, only the outflows of that store, and of the stores at
their lower bound downstream of it, change; a moment solves those groups alone, upstream first,
with the same arithmetic (`Instant.fill`), and every other rate is the one that the whole part would
give again. This holds while every solve of the sets has been of a closed form: once the selection
order solves a part, or a store rests on its upper bound with inflows, moments solve whole parts.

The recorder takes a piece of each store at each change of its line, and a piece of what the network
gives of each flow (`Flows`: an actual rate, a route's signed rate, a served fraction) at each change
of it: all are exact.
"""

from __future__ import annotations

import heapq
import math

import numpy as np

from ..allocation import StockFaces
from ..continuous.transfers import HeldAmounts
from ..errors import SimulationError
from .contacts import continued_lines, put_lines
from .family import Columns, due_through
from .network import BACKWARD, FORWARD, IN, OUT, ROUNDOFF, SIDES, Asked, Instant, network_of
from .way import Way


class Lines(Way):
    """Sets of one run that run on lines, from the time `t` on (see the module). `keys` are the
    ids that the run gives the sets."""

    def __init__(self, run, sets, values, t=0.0, keys=None):
        plan = self.plan = run.plan
        self.t0 = float(t)
        self.sets = list(sets)  # its sets, which a checkpoint names (`saved.py`)
        keys = list(keys if keys is not None else range(len(sets)))
        self.keys = keys
        self.run, self.recorder, self.columns = run, run.recorder, Columns(run)
        stores = [name for connected in sets for name in connected.stores]
        place = {name: k for k, name in enumerate(stores)}
        self.net, connections, self.recorded = network_of(run, sets, stores)
        self.flows, self.stores = self.net.flows, stores
        self.requests = [connection.request for connection in connections]
        self.capped = [k for k, connection in enumerate(connections) if connection.capacity is not None]
        self.capacities = [connections[k].capacity for k in self.capped]
        self.end_settings = []  # (side, store, which, engine name)
        for (store, side), end in plan.ends.items():
            if store in place:
                self.end_settings.append((SIDES.index(side), place[store], 'request', end.request))
                if end.capacity is not None:
                    self.end_settings.append((SIDES.index(side), place[store], 'capacity', end.capacity))
        self.stepped = frozenset(name for connected in sets for name in connected.stepped)
        self.y = np.array([float(values[name]) for name in stores])
        self.since = np.zeros(len(stores))
        self.slope = np.zeros(len(stores))
        self.lower = np.array([run.bounds[name][0] for name in stores])
        self.upper = np.array([run.bounds[name][1] for name in stores])
        self.faces = StockFaces.of(run, stores, self.lower, self.upper)
        self.value = np.zeros(len(self.flows))  # what the network gives of each flow
        self.amounts = HeldAmounts(t, len(connections))
        self.rate = np.zeros(len(connections))  # the rate of each connection
        self.version = np.zeros(len(stores), dtype=np.int64)
        self.due = []  # (time, store, version): a line that reaches a bound
        self.stale = set()  # the stores that left a bound since their part was solved
        self.asked = None
        self.instant = None
        # Whether a moment may solve downstream only (see the module).
        self.closed = (
            self.net.plain
            and all(
                plan.rigid(plan.flows[flow], run.held)
                for flow in self.flows
                if plan.flows[flow].source is not None or plan.flows[flow].sink is not None
            )
            and not any(plan.settled(end) for (store, _), end in plan.ends.items() if store in place)
        )
        self.selected = False  # whether the selection order has solved a part of the sets
        self.place = place
        self.row = {name: k for k, name in enumerate(self.flows)}
        self.leg_rows = (
            self.row if self.net.plain else {name: k for k, name in enumerate(self.net.connections)}
        )
        # The stores of each set, by its id, and the stores whose sets left the lines.
        self.members = {key: [place[name] for name in connected.stores] for key, connected in zip(keys, sets)}
        self.dead = np.zeros(len(stores), dtype=bool)
        self.dead_flows = np.zeros(len(self.flows), dtype=bool)
        self.flows_of = {
            key: [self.row[name] for name in connected.flows] for key, connected in zip(keys, sets)
        }
        self.alive = bool(self.members)

    def __len__(self):
        return len(self.flows)

    # ---- what is asked --------------------------------------------------------------------------

    def _asked(self, t):
        """What the connections and the endpoints ask at time t."""
        columns, count = self.columns, len(self.stores)
        request = asked_of(self.net, np.array(columns.at(self.requests, t), dtype=float), t)
        capacity = np.full(len(self.rate), math.inf)
        if self.capped:
            capacity[self.capped] = columns.at(self.capacities, t)
        end_request, end_capacity = np.zeros((2, count)), np.full((2, count), math.inf)
        if self.end_settings:
            found = columns.at([name for *_, name in self.end_settings], t).tolist()
            for (side, s, which, _), number in zip(self.end_settings, found):
                (end_request if which == 'request' else end_capacity)[side, s] = number
        for what, numbers, finite in (
            ('capacity', capacity, False),
            ('outflow or inflow request', end_request, True),
            ('outflow or inflow capacity', end_capacity, False),
        ):
            bad = np.isnan(numbers) | (numbers < 0) | (np.isinf(numbers) if finite else False)
            if numbers is capacity:
                bad &= ~self.net.free_pipe
            if bad.any():
                where = np.argwhere(bad)[0]
                part = (
                    self.net.connections[where[0]]
                    if numbers.ndim == 1
                    else f'{self.stores[where[1]]}.{SIDES[where[0]]}'
                )
                raise SimulationError(f'{part}: a {what} that is {numbers[tuple(where)]:g} at {t:g} h')
        return Asked(request, capacity, end_request, end_capacity)

    # ---- lines ------------------------------------------------------------------------------------

    def _value(self, s, t):
        return self.y[s] + self.slope[s] * (t - self.since[s])

    def _flags(self, stores, t):
        """Set the flags of stores from their values at time t."""
        for s in stores:
            value = self._value(s, t)
            self.instant.lower[s] = self.faces.at_lower(s, value)
            self.instant.upper[s] = self.faces.at_upper(s, value)

    def _solve(self, t, seeds):
        """Solve the parts of the flows `seeds` at time t; gives the stores whose flows changed."""
        instant, net = self.instant, self.net
        touched, done = set(), set()
        pending = [int(f) for f in seeds]

        def ends(flows):
            return {
                int(s)
                for g in flows
                for c in ([g] if net.plain else net.conns.of(g).tolist())
                for s in (net.source[c], net.sink[c])
                if s >= 0
            }

        while pending:
            f = pending.pop()
            if f in done:
                continue
            # The flags of the stores of the part are the state at t; a change of a flag can widen or
            # narrow the part, so the part is found again until its flags hold. The seed's own ends
            # are in its part: their flags are set first.
            self._flags(ends([f]), t)
            while True:
                part = instant.part(f)
                stores = ends(part)
                before = [(bool(instant.lower[s]), bool(instant.upper[s])) for s in stores]
                self._flags(stores, t)
                if before == [(bool(instant.lower[s]), bool(instant.upper[s])) for s in stores]:
                    break
            found = instant.settle(part)
            done.update(part)
            for g, value in zip(part, found.tolist()):
                if value != self.value[g]:
                    self.value[g] = value
                    self.recorder.add(self.recorded[g], t, value, 0.0)
            # A leg's rate follows its request too, which can change while its fraction holds.
            mine = np.concatenate([net.conns.of(g) for g in part]) if not net.plain else np.array(part)
            rates = net.carried(self.value, self.asked, mine)
            for c in mine[rates != self.rate[mine]].tolist():
                self.amounts.change(c, t, self.rate[c])
                for s in (net.source[c], net.sink[c]):
                    if s >= 0:
                        touched.add(int(s))
            self.rate[mine] = rates
            for s in stores:
                self.stale.discard(s)
        return touched

    def _lines(self, t, stores, forced=()):
        """Start again the line of each store whose rate changed (or that is `forced`), from its
        value at t."""
        net, instant = self.net, self.instant
        changed_faces = {}
        for s in sorted(set(stores) | set(forced)):
            inflow = float(self.rate[net.ends[IN].of(s)].sum())
            outflow = float(self.rate[net.ends[OUT].of(s)].sum())
            slope = inflow - outflow
            value = self._value(s, t)
            low, high = self.faces.at_lower(s, value), self.faces.at_upper(s, value)
            if low or high:
                # A store at its bound, held or released (`Instant.settle`): a rate within the
                # roundoff of its flows holds it there.
                if abs(slope) <= ROUNDOFF * (inflow + outflow):
                    slope = 0.0
                if (low and slope < 0) or (high and slope > 0):
                    raise SimulationError(
                        f'{self.stores[s]}: local sharing moves it past its bound at {t:g} h'
                    )
                if slope != 0.0 and (instant.lower[s] or instant.upper[s]):
                    # Held by the closed form of groups (`_downstream`), which a release would not
                    # change: it leaves all the same, and its part is solved again at the next moment.
                    self.stale.add(s)
            if (low or high) and slope == 0 and inflow and outflow:
                changed_faces[s] = OUT if low else IN
            elif self.resting_rates is not None and s in self.resting_rates.sides:
                changed_faces[s] = None
            if slope == self.slope[s] and s not in forced:
                continue
            if t > self.t0 and slope == 0 and s not in forced:
                value = float(self.run.stock_balance(self.stores[s], t))
            self.y[s], self.since[s], self.slope[s] = value, t, slope
            self.version[s] += 1
            self.recorder.add(self.stores[s], t, float(value), float(slope))
            reach = math.inf
            if slope < 0 and math.isfinite(self.lower[s]):
                reach = t + (value - self.lower[s]) / -slope
            elif slope > 0 and math.isfinite(self.upper[s]):
                reach = t + (self.upper[s] - value) / slope
            if reach <= self.run.clock.apart(self.plan.horizon):
                heapq.heappush(self.due, (reach, s, int(self.version[s])))
        self.balance_rates(changed_faces, self.rate, t)

    # ---- moments ----------------------------------------------------------------------------------

    def begin(self, t=None):
        """Every set from its start (or from time t)."""
        t = self.t0 if t is None else t
        self.asked = self._asked(t)
        count = len(self.stores)
        self.instant = Instant(self.net, self.asked, np.zeros(count, dtype=bool), np.zeros(count, dtype=bool))
        self._flags(range(count), t)
        self.value = self.instant.values(after=True)
        self.selected = bool(self.instant.selected)
        self.rate = self.net.carried(self.value, self.asked)
        for k, name in enumerate(self.recorded):
            self.recorder.add(name, t, float(self.value[k]), 0.0)
        self._lines(t, (), forced=range(count))

    def refresh(self, t):
        """At a key time: the parts of the flows and endpoints whose settings changed are solved again,
        whole."""
        asked = self._asked(t)
        old = self.asked
        net = self.net
        changed = set(
            net.of[np.flatnonzero((asked.request != old.request) | (asked.capacity != old.capacity))].tolist()
        )
        ends = np.argwhere((asked.end_request != old.end_request) | (asked.end_capacity != old.end_capacity))
        for side, s in ends.tolist():
            changed.update(net.of[net.ends[side].of(s)].tolist())
        changed = {f for f in changed if not self.dead_flows[f]}
        self.asked = asked
        self.instant = Instant(net, asked, self.instant.lower, self.instant.upper)
        self._moment(t, changed)

    def _moment(self, t, seeds, forced=()):
        """Solve again the parts of the flows `seeds` and of the stores that left a bound, or, where
        a moment may, the groups downstream of the stores `forced` and of those (see the module)."""
        net = self.net
        touched = None
        if self.closed and not self.selected and not seeds:
            touched = self._downstream(t, set(forced) | self.stale)
        if touched is None:
            seeds = set(seeds)
            for s in set(self.stale) | set(forced):
                seeds.update(net.of[net.ends[OUT].of(s)].tolist())
                seeds.update(net.of[net.ends[IN].of(s)].tolist())
            touched = self._solve(t, sorted(seeds)) if seeds else set()
            self.selected = self.selected or bool(self.instant.selected)
        self._lines(t, touched, forced)

    def _downstream(self, t, changed):
        """The groups downstream of the stores `changed`, whose flags are set again at t, upstream
        first (see the module); gives the stores whose flows changed. The stores that the groups
        reach are flagged at t as a part's stores are. None, with no rate changed, where a store rests
        on its upper bound with inflows: the whole parts are solved then."""
        instant, net, asked = self.instant, self.net, self.asked
        lower, upper, request = instant.lower, instant.upper, asked.request
        self._flags(changed, t)
        flagged = set(changed)
        region = set(changed)
        stack = list(region)
        while stack:
            for d in net.sink[net.ends[OUT].of(stack.pop())].tolist():
                if d >= 0 and d not in flagged:
                    flagged.add(d)
                    self._flags((d,), t)
                    if lower[d]:
                        region.add(d)
                        stack.append(d)
        if (upper & (net.counts[IN] > 0)).any():
            return None
        depth = instant.depths()
        order = []
        for s in region:
            outs = net.ends[OUT].of(s)
            claimed = bool(lower[s] and len(outs) and (request[outs] > 0).any())
            order.append((depth(s) if claimed else 0, s))
        touched = set()
        for _, s in sorted(order):
            outs = net.ends[OUT].of(s).tolist()
            if lower[s]:
                found = instant.fill(outs, OUT, s, self.value.__getitem__, net.ends[IN].of(s).tolist())
            else:
                found = {f: float(min(request[f], instant.capacity[f])) for f in outs}
            for f, rate in found.items():
                if rate != self.value[f]:
                    self.amounts.change(f, t, self.rate[f])
                    self.value[f] = self.rate[f] = rate
                    self.recorder.add(self.recorded[f], t, rate, 0.0)
                    touched.update(int(e) for e in (net.source[f], net.sink[f]) if e >= 0)
        self.stale -= flagged
        return touched

    def finish(self, t):
        """At the horizon, as at any moment: the parts of the stores that left a bound are solved
        again, so the values read at the horizon follow the state there."""
        self.stale -= {s for s in self.stale if self.dead[s]}
        self._moment(t, ())

    # ---- the interface of a way (`ways.py`) ------------------------------------------------------

    def _transferred(self, name, t):
        if t > self.run.now:
            raise ValueError('transfer requested outside the accepted interval')
        row = self.leg_rows[name]
        return self.amounts.amount(row, t, 0 if self.dead_flows[self.net.of[row]] else self.rate[row])

    def retire(self, key):
        """The set `key` leaves the lines: its stores have no event from now on."""
        for s in self.members.pop(key):
            self.dead[s] = True
            self.version[s] += 1
            self.stale.discard(s)
        for f in self.flows_of.pop(key):
            for c in (f,) if self.net.plain else self.net.conns.of(f):
                self.amounts.change(c, self.run.now, self.rate[c])
            self.dead_flows[f] = True
        self.alive = bool(self.members)

    def answers_at(self, t, incoming, flows):
        answers = {}
        for flow in flows:
            row = self.row[flow]
            answers[self.recorded[row]] = float(self.value[row])
            if not self.net.plain:
                for c in self.net.conns.of(row):
                    answers[f'{self.net.connections[c]}.actual_rate'] = float(self.rate[c])
        return answers

    def level_at(self, store, t):
        """The value of a store at time t, on its present line."""
        return float(self._value(self.place[store], t))

    def rate_at(self, name, t):
        """What the network gives of a flow: its actual rate, a route's signed rate, or a served
        fraction."""
        return float(self.value[self.row[name.rsplit('.', 1)[0]]])

    def linear(self, store):
        """The line of a store: (value, rate, since)."""
        s = self.place[store]
        return float(self.y[s]), float(self.slope[s]), float(self.since[s])

    def peek(self):
        """The time at which the next line reaches its bound, or inf."""
        due = self.due
        while due and due[0][2] != self.version[due[0][1]]:
            heapq.heappop(due)
        return due[0][0] if due else math.inf

    def step(self, levels=()):
        """The next line that reaches its bound: the store is put on its bound, and the parts of its
        flows are solved again. Gives the stores whose lines and the rates whose values change."""
        reach = self.peek()
        (store,) = put_lines(self, invalidate=False)
        s = self.place[store]
        self.run.now = reach
        before = self.value.copy()
        versions = self.version.copy()
        self._moment(reach, (), forced=(s, *continued_lines(self, levels, reach)) if levels else (s,))
        stores = [self.stores[k] for k in np.flatnonzero(self.version != versions).tolist()]
        rates = [self.recorded[g] for g in np.flatnonzero(self.value != before).tolist()]
        return stores, rates, True

    def timing_events(self, through):
        for reach, s, version in due_through(self.due, through):
            if version == self.version[s]:
                yield reach, self.stores[s], 'lower bound' if self.slope[s] < 0 else 'upper bound'

    def snap(self, t=None, through=None):
        """Put each due store on its bound at the time of the moment."""
        met = put_lines(self, t, through)
        return met, met

    def cut(self, t):
        """Nothing to commit: a line holds to its next event."""

    def advance(self, until):
        """Each line that reaches its bound at or before `until`, in time order."""
        while self.peek() <= until:
            self.step()


def asked_of(net, raw, t):
    """The requests of the connections from the values of their request names at time t: a leg of a
    route reads the positive part of the route's signed request in its direction (the request that
    the route's sign names may cross zero), and any other request must be a number not below zero."""
    request = raw.copy()
    if not net.plain:
        forward, backward = net.roles == FORWARD, net.roles == BACKWARD
        request[forward] = np.maximum(raw[forward], 0.0)
        request[backward] = np.maximum(-raw[backward], 0.0)
        signed = forward | backward
    else:
        signed = np.zeros(len(raw), dtype=bool)
    if not np.isfinite(raw).all():
        k = int(np.flatnonzero(~np.isfinite(raw))[0])
        raise SimulationError(f'{net.connections[k]}: a request that is {raw[k]:g} at {t:g} h')
    negative = (raw < 0) & ~signed & ~net.free_pipe
    if negative.any():
        k = int(np.flatnonzero(negative)[0])
        raise SimulationError(f'Negative flow rates: {net.connections[k]} asks {raw[k]:g} at {t:g} h')
    return request
