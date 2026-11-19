"""The flow network of connected sets, and local sharing at an instant.

`Network` holds the flows and the stores of one or more connected sets as arrays: the two ends of
each flow (a store, or -1 for SOURCE and SINK), the incident flows of each store by side (`Csr`), and
the priority classes of the endpoints (`store.outflow`, `store.inflow`) that rank their flows. What
the flows and the endpoints ask at an instant is an `Asked`; the stores that rest on a bound are two
arrays of flags. `Instant` gives the rates that follow.

**Local sharing** (G0; spec, "Local allocation"). Each endpoint shares among its own flows by its own
rule, and the rates follow the selection order without objectives (`selection.py`): the hard rows
(each flow's capacity, each endpoint's capacity, and the row of each store that rests on a bound:
what leaves a store at its lower bound must also arrive, what arrives at a store at its upper bound
must also leave), then fair sharing of the claims tier by tier, then the preferred routes of a
priority endpoint that has a request, then the rates nearest their requests. A claim is a positive
request: of a flow on its rate, of an endpoint on its total. Its tier is (its level, its layer):

- the **level** is the supply depth of the stores that it draws from, so that claims are settled in
  the direction of supply: 0 for SOURCE or a store that holds stock, and for a store at its lower
  bound one more than the deepest store that feeds it. A junction shares what reaches it, after its
  feeders decided;
- the **layer** orders the flows that some endpoint ranks (`priority(a, b)`): a flow comes after
  every flow ranked ahead of it, and flows whose ranks contradict each other share a layer. The claim
  of an endpoint is in the first layer.

The rates of flows that share no row and no claim are independent, so an instant cuts the flows into
**coupled parts**: a store at its lower bound with outflows, or at its upper bound with inflows,
couples its incident flows, and so does an endpoint of two flows or more that has a capacity or a
request. A part is solved alone, by a closed form where one holds, else by `selection.select`:

- **one flow**: its request within its capacities, raised to the largest request of an endpoint that
  it alone serves (a request is soft);
- **groups in supply order** (R-A3-09: a proportional group alone and a priority order are exact
  closed forms). A group is the outflow of a store at its lower bound, which shares what flows in, or
  an endpoint of two flows or more with a capacity. The form holds when each flow is in one group at
  most, no store of the part rests on its upper bound with inflows, no endpoint of two flows makes a
  request, and every flow into a store at its lower bound is rigid (its capacity at most its
  request), so that nothing later raises it. The groups go upstream first, and each fills its claims
  tier by tier within what it has: equal served fractions within the capacities (water-filling).

Where local sharing has no answer that the oracle defines, the run stops with a failure that names
the stores (`SimulationError`): a ring of stores at their lower bound that feed one another, and room
passed upstream through two full stores (the oracle raises `NotCovered` for both).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..errors import SimulationError
from .pools import Csr
from .selection import Rows, select

OUT, IN = 0, 1  # the two sides of a store: its outflow and its inflow
SIDES = ('outflow', 'inflow')


@dataclass(frozen=True)
class Asked:
    """What the flows and the endpoints ask at an instant: each flow's request and capacity (inf
    for none), and each endpoint's request (0 for none) and capacity, by side and store."""

    request: np.ndarray
    capacity: np.ndarray
    end_request: np.ndarray  # shape (2, stores)
    end_capacity: np.ndarray  # shape (2, stores)


def layers(count, rankings):
    """The priority layer of each of `count` flows (the oracle's `_layers`): `rankings` holds, for
    each endpoint that ranks its flows, its classes of flows from first to last."""
    ahead = {}
    for classes in rankings:
        for i, members in enumerate(classes):
            for f in members:
                for earlier in classes[:i]:
                    ahead.setdefault(f, set()).update(earlier)
    changed = True
    while changed:  # what is ahead of something ahead of f is ahead of f
        changed = False
        for f, before in ahead.items():
            more = set().union(*(ahead.get(g, set()) for g in before)) - before
            if more:
                before |= more
                changed = True
    layer = np.ones(count, dtype=np.int64)
    done = {}
    for f in sorted(ahead):
        stack = [f]
        while stack:  # each flow after those ahead of it that it is not also ahead of
            top = stack[-1]
            if top in done:
                stack.pop()
                continue
            needed = [g for g in ahead.get(top, ()) if top not in ahead.get(g, ()) and g not in done]
            if needed:
                stack.extend(needed)
                continue
            done[top] = 1 + max(
                (done[g] for g in ahead.get(top, ()) if top not in ahead.get(g, ())), default=0
            )
            stack.pop()
    for f, found in done.items():
        layer[f] = found
    return layer


def water(requests, capacities, available):
    """Equal served fractions within capacities: each rate min(phi * request, capacity), with the
    rates adding up to `available`; each min(request, capacity) when those fit."""
    full = np.minimum(requests, capacities)
    if full.sum() <= available:
        return full
    rates = np.empty(len(requests))
    pending, remaining = np.arange(len(requests)), max(0.0, float(available))
    while True:
        fraction = remaining / float(requests[pending].sum())
        capped = pending[capacities[pending] <= fraction * requests[pending]]
        if not len(capped):
            rates[pending] = fraction * requests[pending]
            return rates
        rates[capped] = capacities[capped]
        remaining = max(0.0, remaining - float(capacities[capped].sum()))
        pending = np.setdiff1d(pending, capped)


class Network:
    """The flows and stores of connected sets as arrays (see the module). `sets` gives the connected
    set of each flow and of each store; `classes` the priority classes of each ranking endpoint,
    {(side, store): classes of flow numbers, first to last, with its unranked flows last}."""

    def __init__(self, flows, stores, source, sink, classes, flow_sets, store_sets):
        self.flows, self.stores = tuple(flows), tuple(stores)
        count = len(self.stores)
        self.source = np.asarray(source, dtype=np.int64).reshape(-1)
        self.sink = np.asarray(sink, dtype=np.int64).reshape(-1)
        self.ends = (Csr(self.source, count), Csr(self.sink, count))
        self.counts = np.stack(
            [
                np.bincount(self.source[self.source >= 0], minlength=count),
                np.bincount(self.sink[self.sink >= 0], minlength=count),
            ]
        )
        self.classes = dict(classes)
        self.layer = layers(len(self.flows), self.classes.values())
        self.flow_sets = np.asarray(flow_sets, dtype=np.int64)
        self.store_sets = np.asarray(store_sets, dtype=np.int64)


class Instant:
    """The rates of a network at one instant: what is asked, and the stores at their lower and upper
    bounds (flags, which the caller may change between calls of `parts` and `solve`)."""

    def __init__(self, network, asked, lower, upper):
        self.net, self.asked = network, asked
        self.lower, self.upper = lower, upper
        net = network
        # A flow's capacity within those of the endpoints that it alone serves, and the largest
        # request of those endpoints.
        self.capacity = asked.capacity.astype(float)
        self.extra = np.zeros(len(net.flows))
        for side, ends in ((OUT, net.source), (IN, net.sink)):
            alone = np.flatnonzero((ends >= 0) & (net.counts[side][np.maximum(ends, 0)] == 1))
            self.capacity[alone] = np.minimum(self.capacity[alone], asked.end_capacity[side][ends[alone]])
            self.extra[alone] = np.maximum(self.extra[alone], asked.end_request[side][ends[alone]])
        sets = int(max(net.flow_sets.max(initial=-1), net.store_sets.max(initial=-1))) + 1
        claimed = np.zeros(sets, dtype=bool)
        claimed[net.flow_sets[asked.request > 0]] = True
        for side in (OUT, IN):
            claimed[net.store_sets[asked.end_request[side] > 0]] = True
        self.claimed = claimed  # the connected sets that have a claim

    # ---- the coupled parts ----------------------------------------------------------------------

    def couples(self, s):
        """Whether store s couples all of its flows: it rests on a bound that they meet."""
        counts = self.net.counts
        return bool((self.lower[s] and counts[OUT][s]) or (self.upper[s] and counts[IN][s]))

    def end_couples(self, side, s):
        """Whether an endpoint couples its flows: two or more, with a capacity or a request."""
        asked = self.asked
        return bool(
            self.net.counts[side][s] >= 2
            and (math.isfinite(asked.end_capacity[side][s]) or asked.end_request[side][s] > 0)
        )

    def coupled(self, f):
        """Whether flow f shares a row or a claim with another flow, or meets a store at its bound."""
        net = self.net
        for side, s in ((OUT, net.source[f]), (IN, net.sink[f])):
            if s >= 0 and (self.couples(s) or self.end_couples(side, s)):
                return True
        return False

    def part(self, seed):
        """The coupled part that holds flow `seed`, as sorted flow numbers."""
        net = self.net
        seen, stack = {int(seed)}, [int(seed)]
        while stack:
            f = stack.pop()
            for side, s in ((OUT, net.source[f]), (IN, net.sink[f])):
                if s < 0:
                    continue
                if self.couples(s):
                    near = np.concatenate([net.ends[OUT].of(s), net.ends[IN].of(s)])
                elif self.end_couples(side, s):
                    near = net.ends[side].of(s)
                else:
                    continue
                for g in near.tolist():
                    if g not in seen:
                        seen.add(g)
                        stack.append(g)
        return sorted(seen)

    def parts(self, seeds):
        """The coupled parts that hold the flows `seeds`, each once."""
        found, placed = [], set()
        for f in seeds:
            if int(f) not in placed:
                part = self.part(f)
                placed.update(part)
                found.append(part)
        return found

    def alone(self, flows):
        """The rates of flows that are in no coupled part."""
        flows = np.asarray(flows, dtype=np.int64)
        return np.minimum(self.capacity[flows], np.maximum(self.asked.request[flows], self.extra[flows]))

    def rates(self):
        """The rate of every flow."""
        net = self.net
        rates = self.alone(np.arange(len(net.flows)))
        stores = np.flatnonzero(
            (self.lower & (net.counts[OUT] > 0)) | (self.upper & (net.counts[IN] > 0))
        ).tolist()
        seeds = [int(f) for s in stores for side in (OUT, IN) for f in net.ends[side].of(s)[:1]]
        for side in (OUT, IN):
            for s in np.flatnonzero(net.counts[side] >= 2).tolist():
                if self.end_couples(side, s):
                    seeds.append(int(net.ends[side].of(s)[0]))
        for part in self.parts(seeds):
            rates[part] = self.solve(part)
        return rates

    # ---- one part ----------------------------------------------------------------------------------

    def solve(self, part):
        """The rates of the flows of one coupled part, in its order."""
        if len(part) == 1 and not self.coupled(part[0]):
            return self.alone(part)
        self._check_full(part)
        found = self._groups(part)
        return found if found is not None else self._general(part)

    def _name(self, s):
        return self.net.stores[s]

    def _check_full(self, part):
        """Room passed upstream through two full stores has no answer of local sharing."""
        net, lower, upper = self.net, self.lower, self.upper
        for f in part:
            s, d = net.source[f], net.sink[f]
            if s >= 0 and d >= 0 and upper[s] and not lower[s] and upper[d] and self.claimed[net.flow_sets[f]]:
                raise SimulationError(
                    f'{self._name(s)} and {self._name(d)}: room passed upstream through two full stores; '
                    'local sharing settles in the direction of supply and has no answer here'
                )

    def depths(self):
        """A function: the supply depth of a store (0 for -1, which is SOURCE), found as asked."""
        net, lower, memo = self.net, self.lower, {}

        def feeders(s):
            return net.source[net.ends[IN].of(s)].tolist()

        def depth(s0):
            if s0 < 0 or not lower[s0]:
                return 0
            if s0 in memo:
                return memo[s0]
            stack, on, best = [(s0, iter(feeders(s0)))], [s0], {s0: 0}
            while stack:
                s, pending = stack[-1]
                for t in pending:
                    if t < 0 or not lower[t]:
                        continue
                    if t in memo:
                        best[s] = max(best[s], memo[t])
                        continue
                    if t in best:
                        ring = on[on.index(t) :] + [t]
                        raise SimulationError(
                            'a ring of stores at their lower bound passes supply around: '
                            + ' -> '.join(self._name(r) for r in ring)
                            + '; local sharing settles in the direction of supply and has no answer here'
                        )
                    best[t] = 0
                    on.append(t)
                    stack.append((t, iter(feeders(t))))
                    break
                else:
                    stack.pop()
                    on.pop()
                    memo[s] = 1 + best.pop(s)
                    if stack:
                        parent = stack[-1][0]
                        best[parent] = max(best[parent], memo[s])
            return memo[s0]

        return depth

    def _groups(self, part):
        """The rates of a part by groups in supply order (see the module), or None where that form
        does not hold."""
        net, asked, lower, upper = self.net, self.asked, self.lower, self.upper
        request, capacity = asked.request, self.capacity
        if (self.extra[part] > 0).any():
            return None  # a flow with a claim of its own endpoint beside its own claim
        stores = sorted({int(s) for f in part for s in (net.source[f], net.sink[f]) if s >= 0})
        groups, member = [], {}
        for s in stores:
            outs, ins = net.ends[OUT].of(s), net.ends[IN].of(s)
            if upper[s] and len(ins):
                return None  # a full store passes room upstream
            if any(len(here) >= 2 and asked.end_request[side][s] > 0 for side, here in ((OUT, outs), (IN, ins))):
                return None  # an aggregate request
            if lower[s] and len(outs):
                if not all(capacity[g] <= request[g] or capacity[g] == 0 for g in ins.tolist()):
                    return None  # a flow into an empty store that a later claim could raise
                groups.append(('supply', s, outs))
            elif len(outs) >= 2 and math.isfinite(asked.end_capacity[OUT][s]):
                groups.append(('out', s, outs))
            if len(ins) >= 2 and math.isfinite(asked.end_capacity[IN][s]):
                groups.append(('in', s, ins))
        for k, (_, _, members) in enumerate(groups):
            for f in members.tolist():
                if f in member:
                    return None  # a flow in two groups
                member[f] = k
        rates = {f: float(min(request[f], capacity[f])) for f in part if f not in member}
        depth = self.depths()
        order = []
        for k, (kind, s, members) in enumerate(groups):
            claimed = bool((request[members] > 0).any())
            order.append((0 if kind != 'supply' or not claimed else depth(s), k))
        for _, k in sorted(order):
            kind, s, members = groups[k]
            side = IN if kind == 'in' else OUT
            available = float(asked.end_capacity[side][s])
            if kind == 'supply':
                available = min(available, sum(rates[g] for g in net.ends[IN].of(s).tolist()))
            members = members.tolist()
            for f in members:
                rates[f] = 0.0
            claims = [f for f in members if request[f] > 0]
            for layer in sorted({int(net.layer[f]) for f in claims}):
                tier = np.array([f for f in claims if net.layer[f] == layer], dtype=np.int64)
                given = water(request[tier], capacity[tier], available)
                for f, rate in zip(tier.tolist(), given.tolist()):
                    rates[f] = rate
                available = max(0.0, available - float(given.sum()))
        return np.array([rates[f] for f in part])

    def _general(self, part):
        """The rates of a part by the selection order (`selection.select`)."""
        net, asked, lower, upper = self.net, self.asked, self.lower, self.upper
        place = {f: k for k, f in enumerate(part)}
        n = len(part)
        rows = Rows(n)
        depth = self.depths()

        def vector(flows):
            a = np.zeros(n)
            a[[place[f] for f in flows]] = 1.0
            return a

        claims, prefs = [], []
        stores = sorted({int(s) for f in part for s in (net.source[f], net.sink[f]) if s >= 0})
        for s in stores:
            outs, ins = net.ends[OUT].of(s).tolist(), net.ends[IN].of(s).tolist()
            if (lower[s] and outs) or (upper[s] and ins):
                net_in = vector(ins) - vector(outs)
                if lower[s]:
                    rows.at_least(net_in, 0.0)  # what leaves must also arrive
                if upper[s]:
                    rows.at_most(net_in, 0.0)  # what arrives must also leave
            for side, here in ((OUT, outs), (IN, ins)):
                if not here or any(f not in place for f in here):
                    continue
                total = vector(here)
                if math.isfinite(asked.end_capacity[side][s]):
                    rows.at_most(total, asked.end_capacity[side][s])
                wanted = float(asked.end_request[side][s])
                if wanted > 0:
                    level = max(depth(int(net.source[f])) for f in here)
                    claims.append(((level, 1), total, wanted))
                    ranked = net.classes.get((side, s))
                    if ranked:
                        carried = np.zeros(n)
                        for members in ranked[:-1]:
                            carried = carried + vector(members)
                            prefs.append((carried, wanted))
        for f in part:
            if asked.request[f] > 0:
                claims.append(((depth(int(net.source[f])), int(net.layer[f])), vector([f]), float(asked.request[f])))
        tiers = {}
        for tier, a, wanted in claims:
            tiers.setdefault(tier, []).append((a, wanted))
        found = select(
            rows,
            asked.capacity[part],
            [tiers[key] for key in sorted(tiers)],
            prefs,
            asked.request[part],
        )
        return found
