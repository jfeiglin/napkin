"""Lines: the connected sets whose rates read nothing that moves, run together on one network, at any
size (R-A4a-04, "lines").

The requests and capacities of such a set, of its flows and of its endpoints, change only at key
times. So its rates hold from moment to moment, and each store is a straight line between moments. A
moment is a key time, or the time at which a line reaches a bound. At a moment, only the coupled parts
that the change reaches are solved again (`network.Instant`): the parts of the flows at the store
that met its bound, of the flows whose requests or capacities changed, and of the stores that left a
bound since they were last solved. Every other store keeps its line, so the cost of a moment does not
grow with the number of rows.

The flags of a part are the state at the moment, as the oracle reads them: a store rests on its lower
(upper) bound while it holds exactly that value. A store at its bound whose sharing gives it a rate
away from the bound leaves it; it is solved again at the next moment, from where it is then.

The recorder takes a piece of each store at each change of its line, and a piece of each actual rate
at each change of its rate: all are exact.
"""

from __future__ import annotations

import heapq
import math

import numpy as np

from ..errors import SimulationError
from .family import Columns
from .network import IN, OUT, SIDES, Asked, Instant, Network


class Lines:
    """The sets of one run that run on lines (see the module)."""

    def __init__(self, run, sets, values):
        plan = self.plan = run.plan
        self.run, self.recorder, self.columns = run, run.recorder, Columns(run)
        flows = [name for connected in sets for name in connected.flows]
        stores = [name for connected in sets for name in connected.stores]
        place = {name: k for k, name in enumerate(stores)}
        number = {name: k for k, name in enumerate(flows)}
        source = [place[plan.flows[f].source] if plan.flows[f].source else -1 for f in flows]
        sink = [place[plan.flows[f].sink] if plan.flows[f].sink else -1 for f in flows]
        flow_sets = [k for k, connected in enumerate(sets) for _ in connected.flows]
        store_sets = [k for k, connected in enumerate(sets) for _ in connected.stores]
        classes = {}
        for (store, side), items in plan.rankings.items():
            if store in place:
                classes[(SIDES.index(side), place[store])] = run.classes_of(store, side, items, number)
        self.net = Network(flows, stores, source, sink, classes, flow_sets, store_sets)
        self.flows, self.stores = flows, stores
        self.requests = [plan.flows[f].request for f in flows]
        self.capped = [k for k, f in enumerate(flows) if plan.flows[f].capacity is not None]
        self.capacities = [plan.flows[flows[k]].capacity for k in self.capped]
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
        self.rate = np.zeros(len(flows))
        self.version = np.zeros(len(stores), dtype=np.int64)
        self.due = []  # (time, store, version): a line that reaches a bound
        self.stale = set()  # the stores that left a bound since their part was solved
        self.asked = None
        self.instant = None

    def __len__(self):
        return len(self.flows)

    # ---- what is asked --------------------------------------------------------------------------

    def _asked(self, t):
        """What the flows and the endpoints ask at time t."""
        columns, count = self.columns, len(self.stores)
        request = np.array(columns.at(self.requests, t), dtype=float)
        capacity = np.full(len(self.flows), math.inf)
        if self.capped:
            capacity[self.capped] = columns.at(self.capacities, t)
        end_request, end_capacity = np.zeros((2, count)), np.full((2, count), math.inf)
        if self.end_settings:
            found = columns.at([name for *_, name in self.end_settings], t).tolist()
            for (side, s, which, _), number in zip(self.end_settings, found):
                (end_request if which == 'request' else end_capacity)[side, s] = number
        for what, numbers, finite in (
            ('request', request, True),
            ('capacity', capacity, False),
            ('outflow or inflow request', end_request, True),
            ('outflow or inflow capacity', end_capacity, False),
        ):
            bad = np.isnan(numbers) | (numbers < 0) | (np.isinf(numbers) if finite else False)
            if bad.any():
                where = np.argwhere(bad)[0]
                part = self.flows[where[0]] if numbers.ndim == 1 else f'{self.stores[where[1]]}.{SIDES[where[0]]}'
                raise SimulationError(f'{part}: a {what} that is {numbers[tuple(where)]:g} at {t:g} h')
        return Asked(request, capacity, end_request, end_capacity)

    # ---- lines ------------------------------------------------------------------------------------

    def _value(self, s, t):
        return self.y[s] + self.slope[s] * (t - self.since[s])

    def _flags(self, stores, t):
        """Set the flags of stores from their values at time t."""
        for s in stores:
            value = self._value(s, t)
            self.instant.lower[s] = value <= self.lower[s]
            self.instant.upper[s] = value >= self.upper[s]

    def _solve(self, t, seeds):
        """Solve the parts of the flows `seeds` at time t; gives the stores whose flows changed."""
        instant, net = self.instant, self.net
        touched, done = set(), set()
        pending = [int(f) for f in seeds]
        while pending:
            f = pending.pop()
            if f in done:
                continue
            # The flags of the stores of the part are the state at t; a change of a flag can widen or
            # narrow the part, so the part is found again until its flags hold.
            while True:
                part = instant.part(f)
                stores = {int(s) for g in part for s in (net.source[g], net.sink[g]) if s >= 0}
                before = [(bool(instant.lower[s]), bool(instant.upper[s])) for s in stores]
                self._flags(stores, t)
                if before == [(bool(instant.lower[s]), bool(instant.upper[s])) for s in stores]:
                    break
            rates = instant.solve(part)
            done.update(part)
            for g, rate in zip(part, rates.tolist()):
                if rate != self.rate[g]:
                    self.rate[g] = rate
                    self.recorder.add(f'{self.flows[g]}.actual_rate', t, rate, 0.0)
                    for s in (net.source[g], net.sink[g]):
                        if s >= 0:
                            touched.add(int(s))
            for s in stores:
                self.stale.discard(s)
        return touched

    def _lines(self, t, stores, forced=()):
        """Start again the line of each store whose rate changed (or that is `forced`), from its
        value at t."""
        net, instant = self.net, self.instant
        for s in sorted(set(stores) | set(forced)):
            inflow = float(self.rate[net.ends[IN].of(s)].sum())
            outflow = float(self.rate[net.ends[OUT].of(s)].sum())
            slope = inflow - outflow
            value = self._value(s, t)
            low, high = instant.lower[s] and value <= self.lower[s], instant.upper[s] and value >= self.upper[s]
            if low or high:
                # A store at its bound: a rate within the roundoff of its flows holds it there.
                if abs(slope) <= 1e-12 * (inflow + outflow):
                    slope = 0.0
                if (low and slope < 0) or (high and slope > 0):
                    raise SimulationError(f'{self.stores[s]}: local sharing moves it past its bound at {t:g} h')
                if slope != 0.0:
                    self.stale.add(s)  # it leaves its bound: solved again at the next moment
            if slope == self.slope[s] and s not in forced:
                continue
            self.y[s], self.since[s], self.slope[s] = value, t, slope
            self.version[s] += 1
            self.recorder.add(self.stores[s], t, float(value), float(slope))
            reach = math.inf
            if slope < 0 and math.isfinite(self.lower[s]):
                reach = t + (value - self.lower[s]) / -slope
            elif slope > 0 and math.isfinite(self.upper[s]):
                reach = t + (self.upper[s] - value) / slope
            if reach <= self.plan.horizon:
                heapq.heappush(self.due, (reach, s, int(self.version[s])))

    # ---- moments ----------------------------------------------------------------------------------

    def begin(self, t):
        """Every set from time t."""
        self.asked = self._asked(t)
        count = len(self.stores)
        self.instant = Instant(self.net, self.asked, np.zeros(count, dtype=bool), np.zeros(count, dtype=bool))
        self._flags(range(count), t)
        self.rate = self.instant.rates()
        for k, name in enumerate(self.flows):
            self.recorder.add(f'{name}.actual_rate', t, float(self.rate[k]), 0.0)
        self._lines(t, (), forced=range(count))

    def refresh(self, t):
        """At a key time: the parts of the flows and endpoints whose settings changed are solved again."""
        asked = self._asked(t)
        old = self.asked
        changed = set(
            np.flatnonzero((asked.request != old.request) | (asked.capacity != old.capacity)).tolist()
        )
        net = self.net
        ends = np.argwhere((asked.end_request != old.end_request) | (asked.end_capacity != old.end_capacity))
        for side, s in ends.tolist():
            changed.update(net.ends[side].of(s).tolist())
        self.asked = asked
        self.instant = Instant(net, asked, self.instant.lower, self.instant.upper)
        self._moment(t, changed)

    def _moment(self, t, seeds, forced=()):
        """Solve again the parts of the flows `seeds` and of the stores that left a bound."""
        net = self.net
        seeds = set(seeds)
        for s in self.stale:
            seeds.update(net.ends[OUT].of(s).tolist())
            seeds.update(net.ends[IN].of(s).tolist())
        touched = self._solve(t, sorted(seeds)) if seeds else set()
        self._lines(t, touched, forced)

    def advance(self, until):
        """Each line that reaches its bound at or before `until`, in time order: the store is put on
        its bound, and the parts of its flows are solved again."""
        net = self.net
        while self.due and self.due[0][0] <= until:
            reach, s, version = heapq.heappop(self.due)
            if version != self.version[s]:
                continue
            # The store is put on its bound exactly, and holds there until its part is solved.
            bound = self.lower[s] if self.slope[s] < 0 else self.upper[s]
            self.y[s], self.since[s], self.slope[s] = bound, reach, 0.0
            seeds = net.ends[OUT].of(s).tolist() + net.ends[IN].of(s).tolist()
            self.run.now = reach
            self._moment(reach, seeds, forced=(s,))
