"""The third way of running a connected set: the rates of the flows are found at each moment and
held between moments, so each store is a straight line between two moments. A prototype.

It runs a `layout.Network` whose requests read nothing that moves between moments. A moment is:

- the time at which a store reaches its lower bound (the timeline predicts it from the line);
- the time of a scheduled move (an instantaneous transfer of an amount between two stores);
- the time of a scheduled change of a request.

At a moment only the parts that the change reaches are brought up to date: the flows out of the
stores that it touches, then the stores at the other ends of those flows, and so on while a store
rests on its bound. Every other store keeps its line. So the cost of a moment does not grow with
the number of rows.

**The rule at a bound is a stand-in.** A store that rests on its lower bound gives its outflows
what comes in: each outflow gets the same fraction of what it asks. Where empty stores feed one
another, the answer is the largest rates that satisfy this rule at each of them. The rules of the
language for sharing (ranks, endpoint requests, max-min fractions, a declared solver) are the work
of the solve library (prototype A3). They replace `Lines.share` and nothing else here: the
lines, the timeline, the indexes and the record do not depend on the rule.

Upper bounds are not in this prototype: a store has a lower bound only.
"""

from __future__ import annotations

import heapq
import math

import numpy as np

DEPLETE, MOVE, SET = 0, 1, 2
ATOL_FACTOR = 1e-10  # the absolute tolerance of a store is this factor times its size (docs/engine.md)
SETTLE_LIMIT = 200_000  # the most steps of the sharing at one moment


class RunStopped(RuntimeError):
    """The run stops: the message names the part, as a message of the engine does."""


class Lines:
    def __init__(self, net, y, lower, want, horizon, recorder=None):
        self.net = net
        S, F = net.stores.count, net.count
        self.src, self.dst = net.src, net.dst
        self.out_of, self.into = net.out_of, net.into
        self.y0 = np.array(y, dtype=float)
        self.t0 = np.zeros(S)
        self.rate = np.zeros(S)
        self.lower = np.broadcast_to(np.asarray(lower, dtype=float), (S,)).copy()
        self.want = np.array(want, dtype=float)  # what each flow asks, after its own capacity
        self.a = self.want.copy()  # what each flow delivers
        self.rest = np.zeros(S, dtype=bool)  # the store is on its lower bound and stays there
        self.version = np.zeros(S, dtype=np.int64)
        self.horizon = float(horizon)
        self.now = 0.0
        self.heap = []
        self.recorder = recorder
        self.counts = dict.fromkeys(('moments', 'depletions', 'moves', 'sets', 'line restarts', 'share steps', 'stale'), 0)
        self.trace = []  # (time, kind, index, amount): the moves and the changes of requests
        # The size of each store sets its tolerance: the largest start value of the stores that
        # flows join to it, by row. (The table path of today refuses this: run.py:2080.)
        count, label = net.islands()
        largest = np.zeros(count)
        np.maximum.at(largest, label, np.abs(self.y0))
        self.atol = ATOL_FACTOR * np.maximum(1.0, largest[label])
        self._seq = 0

    # ---- reading ------------------------------------------------------------------------------

    def value(self, s, t):
        return self.y0[s] + self.rate[s] * (t - self.t0[s])

    def values(self, t=None):
        """Every store at a time from the present moment on (default: now)."""
        t = self.now if t is None else t
        return self.y0 + self.rate * (t - self.t0)

    def net_rate(self, s):
        return float(self.a[self.into.of(s)].sum() - self.a[self.out_of.of(s)].sum())

    # ---- the timeline -------------------------------------------------------------------------

    def push(self, at, kind, index, version=0):
        self._seq += 1
        heapq.heappush(self.heap, (at, kind, self._seq, index, version))

    def predict(self, s):
        if self.rate[s] < 0 and self.y0[s] > self.lower[s]:
            self.push(self.t0[s] + (self.y0[s] - self.lower[s]) / -self.rate[s], DEPLETE, s, self.version[s])

    def restart(self, s, t, y=None, rate=None):
        """The line of a store starts again at t: from where it is, or from `y`, with its rate or `rate`."""
        if y is None:
            y = self.y0[s] + self.rate[s] * (t - self.t0[s])
        self.y0[s], self.t0[s] = y, t
        if rate is not None:
            self.rate[s] = rate
        self.version[s] += 1
        self.counts['line restarts'] += 1
        if self.recorder is not None:
            self.recorder.line(s, t, y, self.rate[s])
        self.predict(s)

    def schedule_move(self, at, flow_like, source, target, amount):
        self.push(float(at), MOVE, (flow_like, int(source), int(target), float(amount)))

    def schedule_set(self, at, flow, want):
        self.push(float(at), SET, (int(flow), float(want)))

    # ---- the start ----------------------------------------------------------------------------

    def start(self):
        S = len(self.y0)
        self.rate[:] = self.net.B @ self.a
        if self.recorder is not None:
            self.recorder.start(self)
        on = np.flatnonzero((self.y0 <= self.lower) & (self.rate < 0))
        self.rest[on] = True
        self.y0[on] = self.lower[on]
        dirty = set(on.tolist())
        self.settle(0.0, list(on.tolist()), dirty)
        falling = np.flatnonzero((self.rate < 0) & (self.y0 > self.lower))
        at = self.t0[falling] + (self.y0[falling] - self.lower[falling]) / -self.rate[falling]
        for s, when in zip(falling.tolist(), at.tolist()):
            self.push(when, DEPLETE, s, int(self.version[s]))
        return self

    # ---- one moment ---------------------------------------------------------------------------

    def run(self, until=None):
        end = self.horizon if until is None else min(until, self.horizon)
        heap = self.heap
        while heap and heap[0][0] <= end:
            at, kind, _, index, version = heapq.heappop(heap)
            if kind == DEPLETE:
                if version != self.version[index]:
                    self.counts['stale'] += 1
                    continue
                self.advance(at)
                self.deplete(index, at)
            elif kind == MOVE:
                self.advance(at)
                self.move(index, at)
            else:
                self.advance(at)
                self.set(index, at)
            self.counts['moments'] += 1
        self.advance(end)
        return self

    def advance(self, at):
        if self.recorder is not None:
            self.recorder.advance(at)
        self.now = at

    def deplete(self, s, t):
        """The store reaches its lower bound: it is put on the bound exactly, and what roundoff left
        goes to the first leg that delivers, so the total keeps it."""
        self.counts['depletions'] += 1
        left = self.value(s, t) - self.lower[s]
        if abs(left) > self.atol[s]:
            raise RunStopped(f'{self.net.stores.name(s)} is {left:g} from its bound at the time when its line reaches it')
        self.rest[s] = True
        self.restart(s, t, y=self.lower[s], rate=0.0)
        dirty = {s}
        if left != 0.0:
            for f in self.out_of.of(s).tolist():
                d = self.dst[f]
                if d >= 0 and self.a[f] > 0:
                    self.restart(d, t, y=self.value(d, t) + left)
                    dirty.add(int(d))
                    break
        self.settle(t, [s], dirty)

    def move(self, item, t):
        """An instantaneous transfer: the amount leaves one store and enters the other, or the run stops."""
        self.counts['moves'] += 1
        label, source, target, amount = item
        if not math.isfinite(amount) or amount < 0:
            raise RunStopped(f'{label}: a move takes a finite amount from 0, not {amount}')
        held, got = self.value(source, t), self.value(target, t)
        left = held - amount
        if left < self.lower[source] - self.atol[source]:
            raise RunStopped(
                f'{label} at t={t:g} h: a move does not fit: {self.net.stores.name(source)} holds '
                f'{held:g}, less than the amount {amount:g}'
            )
        if left != self.lower[source] and abs(left - self.lower[source]) <= self.atol[source]:
            amount += left - self.lower[source]  # a transfer leaves no residue (docs/engine.md)
            left = self.lower[source]
        self.trace.append((t, 'move', label, amount))
        self.restart(source, t, y=left)
        self.restart(target, t, y=got + amount)
        dirty, queue = {source, target}, []
        if self.rest[target] and got + amount > self.lower[target]:
            self.rest[target] = False
            self.grow(target, queue, dirty)
        self.settle(t, queue, dirty)

    def set(self, item, t):
        """A request changes at a moment (a route closes, a reading changes)."""
        self.counts['sets'] += 1
        f, want = item
        self.want[f] = want
        self.trace.append((t, 'set', f, want))
        s, d = int(self.src[f]), int(self.dst[f])
        dirty, queue = set(), []
        if s >= 0 and self.rest[s]:
            # Its source rests: the flows out of it share again what comes in.
            self.grow(s, queue, dirty)
            queue.append(s)
            dirty.add(s)
        else:
            before = self.a[f]
            self.a[f] = want
            self.flow_changed(np.array([f]), t)
            if s >= 0:
                dirty.add(s)
            if d >= 0:
                dirty.add(d)
                if self.rest[d]:
                    if want > before:
                        self.grow(d, queue, dirty)
                    queue.append(d)
        self.settle(t, queue, dirty)

    def flow_changed(self, flows, t):
        if self.recorder is not None:
            self.recorder.flows(flows, t, self.a[flows], self.want[flows])

    # ---- the sharing at a bound (a stand-in for the solve library) ---------------------------

    def grow(self, s, queue, dirty):
        """A store gets more than before, or leaves its bound: the flows out of it, and out of the
        resting stores after it, go back to what they ask, and the sharing lowers them again from
        there. So the answer does not depend on the path of the run."""
        stack, seen = [s], {s}
        while stack:
            c = stack.pop()
            outs = self.out_of.of(c)
            changed = outs[self.a[outs] != self.want[outs]]
            if len(changed):
                self.a[changed] = self.want[changed]
                self.flow_changed(changed, self.now)
            for d in self.dst[outs].tolist():
                if d < 0:
                    continue
                dirty.add(d)
                if self.rest[d] and d not in seen:
                    seen.add(d)
                    queue.append(d)
                    stack.append(d)

    def share(self, s):
        """What the flows out of a resting store deliver: what they ask when no more than what
        comes in, else each the same fraction of what it asks. (The stand-in rule.)"""
        outs = self.out_of.of(s)
        coming = float(self.a[self.into.of(s)].sum())
        asked = self.want[outs]
        total = float(asked.sum())
        if total <= coming:
            return outs, asked, coming - total
        new = asked * (coming / total)
        # What roundoff leaves of what comes in goes to the largest leg: the store stays at rest.
        if len(new):
            new[int(np.argmax(new))] += coming - float(new.sum())
        return outs, new, 0.0

    def settle(self, t, queue, dirty):
        """Bring up to date what a change reaches: the outflows of each resting store of `queue`,
        then the resting stores that they feed, until nothing changes; then the line of each store
        whose rate changed, once."""
        a, rest, dst = self.a, self.rest, self.dst
        steps = 0
        while True:
            while queue:
                s = queue.pop()
                if not rest[s]:
                    continue
                steps += 1
                if steps > SETTLE_LIMIT:
                    raise RunStopped(
                        f'The moment t={t:g} h does not settle within {SETTLE_LIMIT} steps of the '
                        f'sharing; next: {self.net.stores.name(s)}'
                    )
                outs, new, spare = self.share(s)
                if spare > 0:
                    rest[s] = False  # more comes in than its outflows ask: it leaves its bound
                dirty.add(s)
                old = a[outs]
                changed = np.abs(new - old) > 1e-13 * np.maximum(self.want[outs], 1e-300)
                if changed.any():
                    flows = outs[changed]
                    a[flows] = new[changed]
                    self.flow_changed(flows, t)
                    for d in dst[flows].tolist():
                        if d >= 0:
                            dirty.add(d)
                            if rest[d]:
                                queue.append(d)
            for s in sorted(dirty):
                if rest[s]:
                    rate = 0.0
                else:
                    rate = self.net_rate(s)
                    if rate < 0 and self.value(s, t) <= self.lower[s]:
                        # It is on its bound and would fall: it rests, and its outflows share.
                        rest[s] = True
                        if self.y0[s] != self.lower[s] or self.t0[s] != t or self.rate[s] != 0.0:
                            self.restart(s, t, y=self.lower[s], rate=0.0)
                        queue.append(s)
                        continue
                if rate != self.rate[s]:
                    self.restart(s, t, rate=rate)
            self.counts['share steps'] += steps
            steps = 0
            if not queue:
                break
            dirty = set(queue)
