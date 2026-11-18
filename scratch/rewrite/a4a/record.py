"""The record of a run that A4a proposes: histories, not readings. A prototype.

A history is the exact value of one recorded value over the whole run, as pieces. A piece starts at
a time and holds until the next piece starts:

    value(t) = y[k] + rate[k] * (t - t[k])        for t[k] <= t < t[k + 1]

So a piece is three numbers. A constant has the rate 0. Where the value jumps at a moment, the next
piece starts at the same time with the value after the moment; the value just before the moment is
the end of the piece before it. A piece that a solver made (a numeric segment) would hold, in the
place of `rate`, the factors of the polynomial of the step; this prototype runs on lines and has
none.

`Recorder` is what a run of `lines.py` writes to. A request names:

- stores (`rows`) and flows (`flow_rows`), each with its own history;
- reductions over a set of stores or of flows, each with one history. The history of a reduction is
  kept up to date as its members change, and never by a pass over the members at each moment:
  `SumOfStores` (two sum trees), `CountOfStores` (the members at or below a level, with the times at
  which a member crosses the level between moments), `Extreme` (the greatest or the least member:
  the winner, and the next time at which another member passes it), `SumOfFlows` and
  `CountOfFlows`.

With `everything`, each store and each flow has its history: what a small model records. The pieces
are then kept in one log and sorted by store at the end.

A reader of a record gets the value at any time (`History.at`), and the mean over any window
exactly (`History.mean`): what a reporting lag needs. Recording changes nothing in the run: a
recorder only reads the lines.
"""

from __future__ import annotations

import heapq
from bisect import bisect_right

import numpy as np


class History:
    """The pieces of one value."""

    __slots__ = ('rate', 't', 'y')

    def __init__(self):
        self.t, self.y, self.rate = [], [], []

    def add(self, t, y, rate=0.0):
        if self.t and self.t[-1] == t:
            self.y[-1], self.rate[-1] = y, rate  # a second change at one time: the last one stays
        elif self.t and self.y[-1] == y and self.rate[-1] == rate == 0.0:
            return  # the same constant goes on
        else:
            self.t.append(t)
            self.y.append(y)
            self.rate.append(rate)

    def __len__(self):
        return len(self.t)

    def arrays(self):
        return np.array(self.t), np.array(self.y), np.array(self.rate)

    def at(self, t, side='right'):
        """The value at a time: after the moment of that time, or (`left`) just before it."""
        k = bisect_right(self.t, t) - 1
        if side == 'left' and k > 0 and self.t[k] == t:
            k -= 1
        k = max(k, 0)
        return self.y[k] + self.rate[k] * (t - self.t[k])

    def integral(self, a, b):
        """The integral of the value from a to b, exactly: each piece is a line."""
        t, y, rate = self.t, self.y, self.rate
        total, k = 0.0, max(bisect_right(t, a) - 1, 0)
        while k < len(t) and t[k] < b:
            lo = max(a, t[k])
            hi = min(b, t[k + 1]) if k + 1 < len(t) else b
            if hi > lo:
                mid = (lo + hi) / 2 - t[k]
                total += (y[k] + rate[k] * mid) * (hi - lo)
            k += 1
        return total

    def mean(self, a, b):
        return self.at(a) if b == a else self.integral(a, b) / (b - a)


class Tree:
    """A sum of n numbers that one member at a time can change: the total reads the present values
    only (the idea of `napkin/engine/timeline/trees.py`, on a list)."""

    def __init__(self, values):
        n = len(values)
        self.size = size = 1 if n <= 1 else 1 << (n - 1).bit_length()
        tree = np.zeros(2 * size)
        tree[size : size + n] = values
        level = size
        while level > 1:
            half = level // 2
            tree[half:level] = tree[level : 2 * level : 2] + tree[level + 1 : 2 * level : 2]
            level = half
        self.tree = tree.tolist()

    def set(self, index, value):
        tree, k = self.tree, self.size + index
        tree[k] = value
        k >>= 1
        while k:
            tree[k] = tree[2 * k] + tree[2 * k + 1]
            k >>= 1

    @property
    def total(self):
        return self.tree[1]


class Reduction:
    """One reduction of a request. `places`: the stores (or the flows) that it is over."""

    over = 'stores'

    def __init__(self, name, places):
        self.name = name
        self.places = np.asarray(places, dtype=np.int64)
        self.leaf = {int(place): k for k, place in enumerate(self.places.tolist())}
        self.history = History()

    def start(self, run):
        pass

    def line(self, s, t, y, rate):
        pass

    def flow(self, f, t, a, want):
        pass

    def advance(self, t):
        pass


class SumOfStores(Reduction):
    """sum(c.field) over stores that are lines: C + R t, with C the sum of `y - rate * t0` and R the
    sum of the rates."""

    def start(self, run):
        at = self.places
        self.C = Tree(run.y0[at] - run.rate[at] * run.t0[at])
        self.R = Tree(run.rate[at])
        self.history.add(0.0, self.C.total, self.R.total)

    def line(self, s, t, y, rate):
        k = self.leaf.get(s)
        if k is None:
            return
        self.C.set(k, y - rate * t)
        self.R.set(k, rate)
        R = self.R.total
        self.history.add(t, self.C.total + R * t, R)


class CountOfStores(Reduction):
    """count(c.flag) where `flag = formula(this.field <= level)`: the members at or below a level.
    A member on a line crosses the level between moments: the reduction keeps the time. `any`:
    record whether the count is above zero, and not the count."""

    def __init__(self, name, places, level, any=False):
        super().__init__(name, places)
        self.level, self.any = float(level), any

    def start(self, run):
        self.run = run
        at = self.places
        self.inside = (run.y0[at] <= self.level).tolist()
        self.count = sum(self.inside)
        self.version = [0] * len(at)
        self.heap = []
        self.write(0.0)
        falling = np.flatnonzero((run.rate[at] < 0) & (run.y0[at] > self.level))
        for k in falling.tolist():
            s = at[k]
            heapq.heappush(self.heap, (run.t0[s] + (run.y0[s] - self.level) / -run.rate[s], k, 0))

    def write(self, t):
        self.history.add(t, float(self.count > 0) if self.any else float(self.count))

    def line(self, s, t, y, rate):
        k = self.leaf.get(s)
        if k is None:
            return
        self.version[k] += 1
        inside = y <= self.level
        if inside != self.inside[k]:
            self.inside[k] = inside
            self.count += 1 if inside else -1
            self.write(t)
        if (rate < 0 and not inside) or (rate > 0 and inside):
            heapq.heappush(self.heap, (t + (self.level - y) / rate, k, self.version[k]))

    def advance(self, t):
        heap = self.heap
        while heap and heap[0][0] <= t:
            at, k, version = heapq.heappop(heap)
            if version != self.version[k]:
                continue
            self.inside[k] = not self.inside[k]
            self.count += 1 if self.inside[k] else -1
            self.write(at)


class Extreme(Reduction):
    """max(c.field) or min(c.field) over stores that are lines. It keeps the member that wins, and
    the next time at which another member passes it. A change of a member that is not the winner
    costs one comparison; a change of the winner, and each time at which the winner changes, cost one
    pass over the members."""

    def __init__(self, name, places, least=False):
        super().__init__(name, places)
        self.sign = -1.0 if least else 1.0
        self.passes = 0

    def start(self, run):
        self.run = run
        self.winner, self.stale, self.next = None, None, np.inf
        self.rebuild(0.0)

    def values(self, t):
        run, at = self.run, self.places
        return self.sign * (run.y0[at] + run.rate[at] * (t - run.t0[at])), self.sign * run.rate[at]

    def rebuild(self, t):
        """The winner at t, and the next time at which a member passes it."""
        self.passes += 1
        value, rate = self.values(t)
        top = value.max()
        near = np.flatnonzero(value >= top - 1e-12 * max(1.0, abs(top)))
        k = int(near[np.argmax(rate[near])])  # of the members at the top, the one that rises fastest
        faster = np.flatnonzero(rate > rate[k])
        if len(faster):
            ahead = (value[k] - value[faster]) / (rate[faster] - rate[k])
            self.next = t + max(float(ahead.min()), 0.0)
        else:
            self.next = np.inf
        if k != self.winner or not self.history.t or self.stale is not None:
            self.history.add(t, self.sign * float(value[k]), self.sign * float(rate[k]))
        self.winner = k

    def line(self, s, t, y, rate):
        k = self.leaf.get(s)
        if k is None or self.stale is not None:
            return
        if k == self.winner:
            self.stale = t
            return
        run, w = self.run, self.places[self.winner]
        top = self.sign * (run.y0[w] + run.rate[w] * (t - run.t0[w]))
        top_rate = self.sign * run.rate[w]
        mine, my_rate = self.sign * y, self.sign * rate
        if mine > top or (mine == top and my_rate > top_rate):
            self.stale = t
        elif my_rate > top_rate:
            self.next = min(self.next, t + (top - mine) / (my_rate - top_rate))

    def advance(self, t):
        if self.stale is not None:
            at, self.stale = self.stale, None
            self.stale = at  # `rebuild` writes the piece of a winner whose own line changed
            self.rebuild(at)
            self.stale = None
        while self.next < t:
            self.rebuild(self.next)


class SumOfFlows(Reduction):
    """sum(c.flow.actual_rate), or (`unmet`) the sum of what the flows ask and do not get."""

    over = 'flows'

    def __init__(self, name, places, unmet=False):
        super().__init__(name, places)
        self.unmet = unmet

    def start(self, run):
        at = self.places
        self.tree = Tree(run.want[at] - run.a[at] if self.unmet else run.a[at])
        self.history.add(0.0, self.tree.total)

    def flow(self, f, t, a, want):
        k = self.leaf.get(f)
        if k is None:
            return
        self.tree.set(k, want - a if self.unmet else a)
        self.history.add(t, self.tree.total)


class CountOfFlows(Reduction):
    """count(c.short) where `short = formula(this.flow.actual_rate < this.flow.request)`."""

    over = 'flows'

    def start(self, run):
        at = self.places
        self.short = (run.a[at] < run.want[at]).tolist()
        self.count = sum(self.short)
        self.history.add(0.0, float(self.count))

    def flow(self, f, t, a, want):
        k = self.leaf.get(f)
        if k is None:
            return
        short = a < want
        if short != self.short[k]:
            self.short[k] = short
            self.count += 1 if short else -1
        self.history.add(t, float(self.count))


class Recorder:
    """What a run writes to. `rows`: places of stores; `flow_rows`: places of flows; `reductions`."""

    def __init__(self, rows=(), flow_rows=(), reductions=(), everything=False):
        self.rows = {int(s): History() for s in rows}
        self.flow_rows = {int(f): History() for f in flow_rows}
        self.reductions = list(reductions)
        self.of_stores = [item for item in self.reductions if item.over == 'stores']
        self.of_flows = [item for item in self.reductions if item.over == 'flows']
        self.everything = everything
        self.log = ([], [], [], [])  # store, time, value, rate of each piece, in the order of the run
        self.flow_log = ([], [], [])  # flow, time, rate
        self.calls = 0

    def start(self, run):
        self.run = run
        for s, history in self.rows.items():
            history.add(0.0, float(run.y0[s]), float(run.rate[s]))
        for f, history in self.flow_rows.items():
            history.add(0.0, float(run.a[f]))
        for item in self.reductions:
            item.start(run)
        if self.everything:
            S, F = len(run.y0), len(run.a)
            self.log[0].extend(range(S))
            self.log[1].extend([0.0] * S)
            self.log[2].extend(run.y0.tolist())
            self.log[3].extend(run.rate.tolist())
            self.flow_log[0].extend(range(F))
            self.flow_log[1].extend([0.0] * F)
            self.flow_log[2].extend(run.a.tolist())

    def line(self, s, t, y, rate):
        """A store starts a new line at t."""
        self.calls += 1
        s, y, rate = int(s), float(y), float(rate)
        history = self.rows.get(s)
        if history is not None:
            history.add(t, y, rate)
        for item in self.of_stores:
            item.line(s, t, y, rate)
        if self.everything:
            log = self.log
            log[0].append(s)
            log[1].append(t)
            log[2].append(y)
            log[3].append(rate)

    def flows(self, flows, t, a, want):
        """Some flows deliver another rate from t on."""
        for f, rate, asked in zip(flows.tolist(), a.tolist(), want.tolist()):
            history = self.flow_rows.get(f)
            if history is not None:
                history.add(t, rate)
            for item in self.of_flows:
                item.flow(f, t, rate, asked)
            if self.everything:
                log = self.flow_log
                log[0].append(f)
                log[1].append(t)
                log[2].append(rate)

    def advance(self, t):
        """The run goes on to the time t: what happens to a recorded value before t is written."""
        for item in self.of_stores:
            item.advance(t)

    # ---- the finished record ------------------------------------------------------------------

    def pieces(self):
        """How many pieces the record holds."""
        total = sum(len(h) for h in self.rows.values()) + sum(len(h) for h in self.flow_rows.values())
        total += sum(len(item.history) for item in self.reductions)
        return total + len(self.log[0]) + len(self.flow_log[0])

    def arrays(self):
        """The record as arrays: what a store of runs keeps. Each history has its times, its values
        and its rates; with `everything`, the pieces of all stores are in one table, sorted by store
        and then by time, with the place of the first piece of each store."""
        found = {}
        for s, history in self.rows.items():
            found[f'store/{s}'] = np.stack(history.arrays())
        for f, history in self.flow_rows.items():
            found[f'flow/{f}'] = np.stack(history.arrays()[:2])
        for item in self.reductions:
            t, y, rate = item.history.arrays()
            found[f'reduction/{item.name}'] = np.stack([t, y, rate] if rate.any() else [t, y])
        if self.everything:
            store, t, y, rate = (np.array(column) for column in self.log)
            order = np.lexsort((np.arange(len(store)), store))  # by store; the order of the run inside
            store, t, y, rate = store[order], t[order], y[order], rate[order]
            # Of several lines that one store starts at one time, the last one stays.
            last = np.ones(len(store), dtype=bool)
            last[:-1] = (store[1:] != store[:-1]) | (t[1:] != t[:-1])
            store, t, y, rate = store[last], t[last], y[last], rate[last]
            found['stores/first'] = np.searchsorted(store, np.arange(len(self.run.y0) + 1)).astype(np.int32)
            found['stores/t'], found['stores/y'], found['stores/rate'] = t, y, rate
            flow, t, a = (np.array(column) for column in self.flow_log)
            order = np.lexsort((np.arange(len(flow)), flow))
            flow, t, a = flow[order], t[order], a[order]
            last = np.ones(len(flow), dtype=bool)
            last[:-1] = (flow[1:] != flow[:-1]) | (t[1:] != t[:-1])
            flow, t, a = flow[last], t[last], a[last]
            found['flows/first'] = np.searchsorted(flow, np.arange(len(self.run.a) + 1)).astype(np.int32)
            found['flows/t'], found['flows/rate'] = t, a
        return found


def store_history(arrays, s):
    """The history of one store from the table of a record with everything."""
    first = arrays['stores/first']
    history = History()
    cut = slice(first[s], first[s + 1])
    history.t = arrays['stores/t'][cut].tolist()
    history.y = arrays['stores/y'][cut].tolist()
    history.rate = arrays['stores/rate'][cut].tolist()
    return history
