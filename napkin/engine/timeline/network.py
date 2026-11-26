"""The flow network of connected sets, and local sharing at an instant.

`Network` holds the flows and the stores of one or more connected sets as arrays. A flow is one
unknown of local sharing, of one of three kinds (`kinds`): a directed flow has its rate, a
reversible route its one signed rate (positive from its first end to its second), and a flow with
legs its one served fraction. What meets the stores are the flows' **connections**: a directed flow
is one; a route has two, its legs `forward` (from its first end to its second) and `backward`, each
of which carries the positive part of the signed rate in its direction; a flow with legs has one for
each leg, which carries the fraction times the leg's request. Each connection has its two ends (a
store, or -1 for SOURCE and SINK); the incident connections of each store by side are a `Csr`, and
an endpoint (`store.outflow`, `store.inflow`) that ranks its connections has its priority classes.
What the connections and the endpoints ask at an instant is an `Asked`: each connection's request
and capacity, both nonnegative (a route's signed request is its forward leg's request less its
backward leg's, and its capacity, on the magnitude, is the capacity of both legs). The stores that
rest on a bound are two arrays of flags. `Instant` gives the value of each flow that follows, and
`carried` the rate of each connection.

**Local sharing** (G0; spec, "Local allocation"). Each endpoint shares among its own connections by
its own rule, and the flows follow the selection order without objectives (`selection.py`): the
hard rows (each flow's bounds: a rate within [0, its capacity], a route's within [-capacity,
capacity], a fraction within [0, 1] and each leg within its own capacity; each endpoint's capacity;
and the row of each store that rests on a bound: what leaves a store at its lower bound must also
arrive, what arrives at a store at its upper bound must also leave), then fair sharing of the claims
tier by tier, then the preferred routes of a priority endpoint that has a request, then the values
nearest their targets. A claim is a positive request (above `TINY`, the smallest normal float, which
alone can be its served fraction's divisor): of a directed flow on its rate, of a route on
its rate in the direction of its request, of a flow with legs on its fraction (as a request of one,
when a leg asks anything; when none does, the fraction is zero), and of an endpoint on its total.
Its tier is (its level, its layer), one rule for local sharing and for a declared solver
(`claim_order`):

- the **level** is the largest of the supply depth of the stores that its connections draw from
  and the room depth of the stores that they fill (`claim_level`). Supply is settled in its
  direction: 0 for SOURCE or a store that holds stock, and for a store at its lower bound one more
  than the deepest store that feeds it, so a junction shares what reaches it after its feeders
  decided. Room is settled against it: a full store (at its upper bound, not at its lower bound)
  passes on the room that its outflows make, and its depth is one more than that of the deepest full
  store that its outflows fill, 0 when they fill none (so one full store shares on the levels of
  supply). With two full tanks in series, the claims into the upper tank wait for the room that the
  lower tank's outflows make. Depths read the connections that can carry flow at the instant
  (`carrying`): a closed pipe passes neither supply nor room, and a ring that it closes is none;
- the **layer** orders the flows that some endpoint ranks (`priority(a, b)`, which names
  connections: a leg ranks its flow): a flow comes after every flow ranked ahead of it, and flows
  whose ranks contradict each other share a layer (R-A2-12). The claim of an endpoint is in the
  first layer.

The capacity of an endpoint that a leg of a route meets holds the positive part of the route's rate
(`Rows.convex`). The request of such an endpoint has no answer of local sharing (fair sharing would
maximize a convex function, and the oracle does not settle it either): the run stops with a failure
that names the endpoint.

**Just after the instant.** The rates of a moment are those of the state just after it, whether or
not a moment falls there (`Instant.settle`, which lines read; the sparse integrator holds its flags the
same way): a store rests on a bound while its sharing keeps it there. Where the rates found with a store
held at one of its bounds move it off, it is free just after, and the part is solved again with it
free: an empty store whose claims wait for its supply, and whose sharing fills it, holds stock just
after, where they wait no more. Where its sharing with it free moves it back past its bound, no rates
hold just after the moment, and the run stops by name: the rates switch back and forth at its bound.

The flows that share no row and no claim are independent, so an instant cuts the flows into
**coupled parts**: a store at its lower bound with outflows, or at its upper bound with inflows,
couples the flows of its connections, and so does an endpoint of two connections or more that has a
capacity or a request. A part is solved alone, by a closed form where one holds, else by
`selection.select`:

- **one flow**: a directed flow's request within its capacities, raised to the largest request of
  an endpoint that it alone serves (a request is soft); a route's signed request within the
  capacities of its legs; a flow with legs at the largest fraction, up to one, that its legs'
  capacities allow;
- **groups in supply order**, for a part of directed flows (R-A3-09: a proportional group alone and
  a priority order are exact closed forms). A group is the outflow of a store at its lower bound,
  which shares what flows in, or an endpoint of two flows or more with a capacity. The form holds
  when each flow is in one group at most, no store of the part rests on its upper bound with
  inflows, no endpoint of two flows makes a request, and every flow into a store at its lower bound
  is rigid (its capacity at most its request), so that nothing later raises it. The groups go
  upstream first, and each fills its claims tier by tier within what it has: equal served
  fractions within the capacities (water-filling).

Where local sharing has no answer that the oracle defines, the run stops with a failure that names
the stores (`SimulationError`): a ring of stores at their lower bound that feed one another, and a
ring of full stores that pass room around, through connections that can carry flow (the oracle
raises `NotCovered` for both).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .. import departure
from ..errors import SimulationError
from . import plan as plans
from .pools import Csr
from .selection import Rows, select

OUT, IN = 0, 1  # the two sides of a store: its outflow and its inflow
SIDES = ('outflow', 'inflow')
DIRECTED, ROUTE, LEGS = 0, 1, 2  # the kinds of a flow
DIRECT, FORWARD, BACKWARD, LEG = 0, 1, 2, 3  # the roles of a connection
# A request at or below the smallest normal float is no claim of the selection order: no float holds
# its served fraction (one over it overflows), and only underflow makes one, such as the request of
# a rate that decays toward zero over a long run (9 e^-t L/h at 708 h). Nor does it size a part.
TINY = float(np.finfo(float).tiny)


def is_claim(request):
    """Whether a request (a number, or each of an array's) is a claim of the selection order: above
    `TINY`. The one test of it, for local sharing and for a declared solver."""
    return request > TINY


@dataclass(frozen=True)
class Asked:
    """What the connections and the endpoints ask at an instant: each connection's request and
    capacity (inf for none), and each endpoint's request (0 for none) and capacity, by side and
    store."""

    request: np.ndarray
    capacity: np.ndarray
    end_request: np.ndarray  # shape (2, stores)
    end_capacity: np.ndarray  # shape (2, stores)


def paired_rates(inward, outward, inlet_capacity, outlet_capacity, lower, upper):
    """One inlet and one outlet, with only their own claims and one stock between them.
    Fulfilling one request never competes with fulfilling the other. Raise its partner
    only as far as conservation requires, cutting both at the limiting capacity."""
    incoming, outgoing = min(inward, inlet_capacity), min(outward, outlet_capacity)
    if lower and outgoing > incoming:
        incoming = outgoing = min(outgoing, inlet_capacity)
    elif upper and incoming > outgoing:
        incoming = outgoing = min(incoming, outlet_capacity)
    return incoming, outgoing


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
        for before in ahead.values():
            more = set().union(*(ahead.get(g, set()) for g in before)) - before
            if more:
                before.update(more)
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


def carrying(net, request, capacity, end_capacity):
    """Whether each connection can carry flow at the instant: its capacity and the capacity of each
    endpoint that it meets are above zero, and a leg asks something (it carries its request times
    its flow's fraction). The structure of sharing is that of these connections, found again at each
    instant (re-audit row 05): the depths and the rings of local sharing, the priority classes and
    layers (`Network.ranking`), and the clusters of the order of the claims (`claim_order`). A closed
    valve passes neither supply nor room, closes no ring and takes no place in a priority."""
    found = np.asarray(capacity, dtype=float) > 0
    if end_capacity is not None:
        for side, ends in ((OUT, net.source), (IN, net.sink)):
            met = np.flatnonzero(ends >= 0)
            found[met] &= end_capacity[side][ends[met]] > 0
    legs = np.flatnonzero(net.roles == LEG)
    found[legs] &= request[legs] > 0
    return found


def physical_capacities(net, capacity, rows, lower, upper):
    """A directed pipe cannot draw from a lower face without an inlet or fill an upper
    face without an outlet. Those incidence rows imply an exact zero upper bound,
    independent of the rate's units or the solver's feasibility tolerance."""
    limits = capacity[rows]
    if not len(net.stores):
        return limits
    source, sink = net.source[rows], net.sink[rows]
    closed = ((source >= 0) & lower[source] & (net.counts[IN][source] == 0)) | (
        (sink >= 0) & upper[sink] & (net.counts[OUT][sink] == 0)
    )
    return np.where((net.roles[rows] == DIRECT) & closed, 0.0, limits)


def _through(connections, carries):
    """The connections of `connections` that can carry flow (all of them when `carries` is None)."""
    return connections if carries is None else connections[carries[connections]]


def supply_depths(net, lower, carries=None):
    """A function: the supply depth of a store of a network, 0 for -1 (SOURCE). A store at its
    lower bound passes on what flows in, so its depth is one more than that of the deepest store that
    feeds it through a connection that can carry flow (`carrying`); any other store holds stock, at
    depth 0. A ring of stores at their lower bound has no depth: finding one fails, naming the ring."""
    return _depths(
        net,
        lower,
        lambda s: net.source[_through(net.ends[IN].of(s), carries)].tolist(),
        'a ring of stores at their lower bound passes supply around: {}; local sharing settles in '
        'the direction of supply and has no answer here',
    )


def room_depths(net, lower, upper, carries=None):
    """A function: the room depth of a store of a network, 0 for -1 (SINK). A full store (at its
    upper bound and not at its lower bound) passes on the room that its outflows make. Its depth is
    one more than that of the deepest full store that its outflows fill through a connection that can
    carry flow, and 0 when they fill none: one full store shares on the levels of supply alone. A
    store with room, and a store held at both bounds, which local sharing settles in the direction of
    supply, are at depth 0. A ring of full stores has no depth: finding one fails, naming the ring."""
    full = np.asarray(upper, dtype=bool) & ~np.asarray(lower, dtype=bool)
    depth = _depths(
        net,
        full,
        lambda s: net.sink[_through(net.ends[OUT].of(s), carries)].tolist(),
        'a ring of stores at their upper bound passes room around: {}; local sharing settles room '
        'against the direction of flow and has no answer here',
    )
    return lambda s: max(0, depth(s) - 1)


def claim_level(net, supply, room):
    """A function: the level of a claim from the connections that serve it (see the module), with
    `supply` and `room` the depths of the stores. A claim waits for the supply of the store that its
    connections draw from and for the room of the store that they fill; each is found only for a
    claim, as the oracle finds it."""

    def level(connections):
        return max(max(supply(int(net.source[c])), room(int(net.sink[c]))) for c in connections)

    return level


@dataclass(frozen=True)
class Claim:
    """A claim as the order of the claims reads it: the connections that serve it, the endpoint
    (side, store) whose request it is (None for the claim of a flow), its layer, and whether a solver
    determines it (a flow that the solver names, or an endpoint all of whose connections it names)."""

    connections: tuple
    endpoint: tuple | None
    layer: int
    named: bool = False

    def ends(self, net, connections=None):
        """The endpoints that rank this claim: its own, or those of the connections of its flow (or
        of `connections` of them)."""
        if self.endpoint is not None:
            return {self.endpoint}
        found = set()
        for c in self.connections if connections is None else connections:
            for side, ends in ((OUT, net.source), (IN, net.sink)):
                if ends[c] >= 0:
                    found.add((side, int(ends[c])))
        return found


def claim_order(net, lower, upper, carries, claims):
    """The place of each claim (`Claim`) in the selection order, as (level, layer): the claims of one
    place share a tier, and the places go in order. One rule for local sharing and for a declared
    solver, built from the endpoints' rules (the owner's rule after G2: an endpoint's rule ranks all
    its flows, named or not):

    - **local sharing**: a claim's level is the largest of the supply depth of the stores that its
      connections draw from and the room depth of the stores that they fill (`claim_level`), and its
      layer orders it after what an endpoint ranks ahead of it. Claims linked by an endpoint that
      they share, directly or through other claims, are a cluster; every claim of a cluster that
      holds a claim that no solver determines keeps this place, so a flow that a solver does not name
      keeps its endpoints' local sharing, and so does each flow that shares an endpoint with it;
    - **the solver's own sharing**, in a cluster of claims that the solver determines only: levels
      count the steps of local sharing (each a decision that the claim waits for) except across a
      connection of the solver whose endpoints rank nothing, where the solver decides what passes
      together with what it serves, and the level passes on. So a solver of the four requested rates
      of the spec's junctions puts A, B and C on one level (1/3 each), while a priority at the
      first junction (A ahead of the onward pipe) keeps B and C, which the onward pipe serves, after
      A. Across endpoints, claims of one place share their tier (spec, "Selection order").

    A claim reads the structure through its connections that can carry flow, and one that has none
    is served nothing: it takes the first place and reads nothing. A ring of stores at a bound has no
    order where local sharing reads it, which fails by name (its depths); the stores of a ring of the
    solver's own connections share one level, which the solver decides together."""
    supply = supply_depths(net, lower, carries)
    room = room_depths(net, lower, upper, carries)
    level = claim_level(net, supply, room)
    through = [
        claim.connections if carries is None else tuple(c for c in claim.connections if carries[c])
        for claim in claims
    ]
    live = [bool(mine) for mine in through]

    def local(i):
        return level(through[i]) if live[i] else 0

    if not any(claim.named for claim in claims):
        return [(local(i), claim.layer) for i, claim in enumerate(claims)]
    parent = list(range(len(claims)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # A claim that no connection of it can carry is served nothing, and links nothing.
    ends = [claim.ends(net, through[i]) if live[i] else set() for i, claim in enumerate(claims)]
    first = {}
    for i, mine in enumerate(ends):
        for end in mine:
            parent[find(i)] = find(first.setdefault(end, i))
    undecided = {find(i) for i, claim in enumerate(claims) if live[i] and not claim.named}
    kept = [find(i) in undecided for i in range(len(claims))]
    held = {end for i, mine in enumerate(ends) if kept[i] for end in mine}  # local sharing's endpoints
    ranked = {end for end, classes in net.ranking(carries).items() if len(classes) > 1}
    full = np.asarray(upper, dtype=bool) & ~np.asarray(lower, dtype=bool)

    def own(c):
        """Whether the solver decides what connection c passes: neither of its endpoints keeps local
        sharing. Gives None if not, else whether an endpoint of it ranks its connections."""
        sides = [(side, int(at[c])) for side, at in ((OUT, net.source), (IN, net.sink)) if at[c] >= 0]
        if any(end in held for end in sides):
            return None
        return any(end in ranked for end in sides)

    def feeds(s):
        found = []
        for c in _through(net.ends[IN].of(s), carries).tolist():
            t, mine = int(net.source[c]), own(c)
            found.append((None, supply(t) + 1) if mine is None else (t, int(mine)))
        return found

    def drains(s):
        found = []
        for c in _through(net.ends[OUT].of(s), carries).tolist():
            d, mine = int(net.sink[c]), own(c)
            step = int(d >= 0 and full[d])
            if mine is None:
                found.append((None, room(d) + 1 if step else 0))
            else:
                found.append((d, step if mine else 0) if step else (None, 0))
        return found

    solver = [through[i] for i in range(len(claims)) if live[i] and not kept[i]]
    if not held and not ranked:
        passed = None  # every connection is the solver's and none is ranked: one level
    else:
        reached = {
            int(e) for connections in solver for c in connections for e in (net.source[c], net.sink[c])
        }
        passed_supply = _passing(net, np.asarray(lower, dtype=bool), feeds, reached)
        passed_room = _passing(net, full, drains, reached)

        def passed(connections):
            level = 0
            for c in connections:
                s, d = int(net.source[c]), int(net.sink[c])
                level = max(level, passed_supply[s] if s >= 0 else 0, passed_room[d] if d >= 0 else 0)
            return level

    return [
        (
            local(i) if kept[i] or not live[i] else passed(through[i]) if passed else 0,
            claim.layer,
        )
        for i, claim in enumerate(claims)
    ]


def _passing(net, active, inputs, roots):
    """The depth of the stores that `roots` reach (an array; 0 for the others): 0 for a store that
    is not `active`, else the largest of its `inputs(s)`, each (t, step) the depth of store t (0 for -1
    or a store that is not active) plus `step`, or (None, value) a value. The stores of a cycle share
    one depth, the largest of the inputs from outside it: a ring has no first store, and the solver
    decides it together. The cycles are the strongly connected parts of the stores' inputs (Tarjan's
    method, iterative): each part is found after every part that it reads, so its depth is known when
    it is found."""
    count = len(net.stores)
    depth = np.zeros(count, dtype=np.int64)
    index = np.full(count, -1, dtype=np.int64)
    low = np.zeros(count, dtype=np.int64)
    on = np.zeros(count, dtype=bool)
    stack, counter = [], 0

    def reads(t):
        return t is not None and t >= 0 and active[t]

    for root in sorted(roots):
        if not reads(root) or index[root] >= 0:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on[root] = True
        work = [(root, iter(inputs(root)))]
        while work:
            s, pending = work[-1]
            for t, _ in pending:
                if not reads(t):
                    continue
                if index[t] < 0:
                    index[t] = low[t] = counter
                    counter += 1
                    stack.append(t)
                    on[t] = True
                    work.append((t, iter(inputs(t))))
                    break
                if on[t]:
                    low[s] = min(low[s], index[t])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[s])
                if low[s] != index[s]:
                    continue
                members = []
                while True:
                    t = stack.pop()
                    on[t] = False
                    members.append(t)
                    if t == s:
                        break
                inside = set(members)
                best = 0
                for m in members:
                    for t, step in inputs(m):
                        if t not in inside:
                            best = max(best, (int(depth[t]) if reads(t) else 0) + step)
                depth[members] = best
    return depth


def _depths(net, active, onward, ring):
    """A function, found as asked: the depth of a store, 0 for -1 and for a store that is not
    `active`, else one more than the deepest of the stores that `onward(s)` gives; a cycle of active
    stores fails with the text `ring`, which names the stores of the cycle."""
    memo = {}

    def depth(s0):
        if s0 < 0 or not active[s0]:
            return 0
        if s0 in memo:
            return memo[s0]
        stack, on, best = [(s0, iter(onward(s0)))], [s0], {s0: 0}
        while stack:
            s, pending = stack[-1]
            for t in pending:
                if t < 0 or not active[t]:
                    continue
                if t in memo:
                    best[s] = max(best[s], memo[t])
                    continue
                if t in best:
                    cycle = [*on[on.index(t) :], t]
                    raise SimulationError(ring.format(' -> '.join(net.stores[r] for r in cycle)))
                best[t] = 0
                on.append(t)
                stack.append((t, iter(onward(t))))
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


class Network:
    """The flows and stores of connected sets as arrays (see the module). `flows` are the names of
    the flows. `source`, `sink` and `flow_sets` are of the connections, each in the connected set
    `flow_sets` gives; `store_sets` gives the set of each store; `classes` the priority classes of
    each ranking endpoint, {(side, store): classes of connection numbers, first to last, with its
    unranked connections last}, which `ranking` and `layers` read among the connections that can
    carry flow at an instant. Without `of`, each flow is directed and is its one connection;
    else `of`, `roles` and `connections` give the flow, the role and the name of each connection,
    and `kinds` the kind of each flow, whose connections are in the order of their numbers."""

    def __init__(
        self,
        flows,
        stores,
        source,
        sink,
        classes,
        flow_sets,
        store_sets,
        *,
        of=None,
        roles=None,
        kinds=None,
        connections=None,
        own_scales=None,
    ):
        self.flows, self.stores = tuple(flows), tuple(stores)
        self.own_scales = np.ones(len(flows)) if own_scales is None else np.asarray(own_scales, dtype=float)
        count = len(self.stores)
        self.source = np.asarray(source, dtype=np.int64).reshape(-1)
        self.sink = np.asarray(sink, dtype=np.int64).reshape(-1)
        size = len(self.source)
        self.plain = of is None
        self.of = np.arange(size, dtype=np.int64) if of is None else np.asarray(of, dtype=np.int64)
        self.roles = np.full(size, DIRECT, dtype=np.int64) if roles is None else np.asarray(roles)
        self.kinds = (
            np.full(len(self.flows), DIRECTED, dtype=np.int64) if kinds is None else np.asarray(kinds)
        )
        self.free_pipe = (self.roles == DIRECT) & (self.source < 0) & (self.sink < 0)
        self.connections = self.flows if connections is None else tuple(connections)
        self.conns = Csr(self.of, len(self.flows))  # the connections of each flow
        self.first = self.conns.items[self.conns.start[:-1]] if size else np.zeros(0, dtype=np.int64)
        self.ends = (Csr(self.source, count), Csr(self.sink, count))
        self.counts = np.stack(
            [
                np.bincount(self.source[self.source >= 0], minlength=count),
                np.bincount(self.sink[self.sink >= 0], minlength=count),
            ]
        )
        self.classes = dict(classes)
        self._layers = {}
        self.flow_sets = np.asarray(flow_sets, dtype=np.int64)
        self.store_sets = np.asarray(store_sets, dtype=np.int64)

    def ranking(self, carries=None):
        """The priority classes of each ranking endpoint among its connections that can carry flow
        (`carrying`; all of them when `carries` is None): a closed connection is not eligible (spec:
        "`priority(a, b)` gives `a` first access when both are eligible"), and a class left empty
        is none."""
        if carries is None:
            return self.classes
        found = {}
        for end, classes in self.classes.items():
            kept = [
                members for members in ([c for c in members if carries[c]] for members in classes) if members
            ]
            if kept:
                found[end] = tuple(tuple(members) for members in kept)
        return found

    def layers(self, carries=None):
        """The priority layer of each flow from the classes of `ranking(carries)`, kept for each
        set of connections that can carry flow."""
        if carries is None:
            rankings = self.classes.values()
        else:
            key = np.packbits(carries).tobytes()
            if key in self._layers:
                return self._layers[key]
            rankings = self.ranking(carries).values()
        found = layers(
            len(self.flows), [[{int(self.of[c]) for c in members} for members in m] for m in rankings]
        )
        if carries is not None:
            if len(self._layers) > 64:
                self._layers.clear()
            self._layers[key] = found
        return found

    def carried(self, values, asked, which=None):
        """The rate of each connection (or of the connections `which`) from the value of each flow:
        a directed flow's rate, the positive part of a route's rate in the direction of each leg, and
        each leg of a flow with legs at its fraction of its request."""
        which = np.arange(len(self.source)) if which is None else np.asarray(which, dtype=np.int64)
        if self.plain:
            return np.array(values[which], dtype=float)
        found, roles = values[self.of[which]], self.roles[which]
        found = np.where(roles == FORWARD, np.maximum(found, 0.0), found)
        found = np.where(roles == BACKWARD, np.maximum(-found, 0.0), found)
        return np.where(roles == LEG, found * asked.request[which], found)


KINDS = {plans.DIRECTED: DIRECTED, plans.ROUTE: ROUTE, plans.LEGS: LEGS}
ROLES = {plans.DIRECT: DIRECT, plans.FORWARD: FORWARD, plans.BACKWARD: BACKWARD, plans.LEG: LEG}


def network_of(run, sets, stores):
    """The network of connected sets of a run's plan (`plan.Connected`), its stores in the order of
    `stores`: (the `Network`, the plan's `Connection` of each of its connections, and the engine name
    under which the run records what the network gives of each flow: its actual rate, or its served
    fraction)."""
    plan = run.plan
    flows = [name for connected in sets for name in connected.flows]
    place = {name: k for k, name in enumerate(stores)}
    connections = [connection for flow in flows for connection in plan.flows[flow].connections]
    number = {connection.name: k for k, connection in enumerate(connections)}
    source = [place[connection.source] if connection.source else -1 for connection in connections]
    sink = [place[connection.sink] if connection.sink else -1 for connection in connections]
    flow_sets = [
        k
        for k, connected in enumerate(sets)
        for flow in connected.flows
        for _ in plan.flows[flow].connections
    ]
    store_sets = [k for k, connected in enumerate(sets) for _ in connected.stores]
    classes = {}
    for (store, side), items in plan.rankings.items():
        if store in place:
            classes[(SIDES.index(side), place[store])] = run.classes_of(store, side, items, number)
    extra = {}
    if any(plan.flows[flow].kind != plans.DIRECTED for flow in flows):
        extra = {
            'of': [k for k, flow in enumerate(flows) for _ in plan.flows[flow].connections],
            'roles': [ROLES[connection.role] for connection in connections],
            'kinds': [KINDS[plan.flows[flow].kind] for flow in flows],
            'connections': [connection.name for connection in connections],
        }
    recorded = [
        f'{flow}.served_fraction' if plan.flows[flow].kind == plans.LEGS else f'{flow}.actual_rate'
        for flow in flows
    ]
    network = Network(
        flows,
        stores,
        source,
        sink,
        classes,
        flow_sets,
        store_sets,
        own_scales=[run.own_scale(name) for name in recorded],
        **extra,
    )
    return network, connections, recorded


class Instant:
    """The values of the flows of a network at one instant: what is asked, and the stores at their
    lower and upper bounds (flags, which the caller may change between calls of `parts` and
    `solve`)."""

    def __init__(self, network, asked, lower, upper):
        self.net, self.asked = network, asked
        self.lower, self.upper = lower, upper
        net = network
        # A connection's capacity within those of the endpoints that it alone serves, and the
        # largest request of those endpoints.
        self.capacity = asked.capacity.astype(float)
        self.extra = np.zeros(len(net.source))
        # With no endpoint there is no competing claim, including a claim of zero.
        self.extra[net.free_pipe] = -math.inf
        for side, ends in ((OUT, net.source), (IN, net.sink)):
            met = np.flatnonzero(ends >= 0)
            alone = met[net.counts[side][ends[met]] == 1]
            self.capacity[alone] = np.minimum(self.capacity[alone], asked.end_capacity[side][ends[alone]])
            self.extra[alone] = np.maximum(self.extra[alone], asked.end_request[side][ends[alone]])
        sets = int(max(net.flow_sets.max(initial=-1), net.store_sets.max(initial=-1))) + 1
        claimed = np.zeros(sets, dtype=bool)
        claimed[net.flow_sets[asked.request > 0]] = True
        for side in (OUT, IN):
            claimed[net.store_sets[asked.end_request[side] > 0]] = True
        self.claimed = claimed  # the connected sets that have a claim
        self.rate_errors = {}  # numerical differences on legs refined by the general solver
        self.uncertain = {}  # unresolved stock departures at this instant
        self.selected = 0  # the parts that the selection order solved, not a closed form
        self.carries = carrying(
            net, asked.request, asked.capacity, asked.end_capacity
        )  # the connections that can carry flow at the instant
        self.layer = net.layers(self.carries)  # the priority layer of each flow among them
        self._full = None  # the value of each flow, for the nets of a part's stores (`_nets`)

    # ---- the coupled parts ----------------------------------------------------------------------

    def couples(self, s):
        """Whether store s couples all of its connections: it rests on a bound that they meet."""
        counts = self.net.counts
        return bool((self.lower[s] and counts[OUT][s]) or (self.upper[s] and counts[IN][s]))

    def end_couples(self, side, s):
        """Whether an endpoint couples its connections: two or more, with a capacity or a request."""
        asked = self.asked
        return bool(
            self.net.counts[side][s] >= 2
            and (math.isfinite(asked.end_capacity[side][s]) or asked.end_request[side][s] > 0)
        )

    def _connections(self, f):
        net = self.net
        return [int(f)] if net.plain else net.conns.of(f).tolist()

    def coupled(self, f):
        """Whether flow f shares a row or a claim with another flow, or meets a store at its bound."""
        net = self.net
        for c in self._connections(f):
            for side, s in ((OUT, net.source[c]), (IN, net.sink[c])):
                if s >= 0 and (self.couples(s) or self.end_couples(side, s)):
                    return True
        return False

    def part(self, seed):
        """The coupled part that holds flow `seed`, as sorted flow numbers. Each store that couples
        its connections, and each endpoint that couples its own, is gone through once."""
        net = self.net
        seen, stack, through = {int(seed)}, [int(seed)], set()
        while stack:
            f = stack.pop()
            for c in self._connections(f):
                for side, s in ((OUT, int(net.source[c])), (IN, int(net.sink[c]))):
                    if s < 0 or (2, s) in through or (side, s) in through:
                        continue
                    if self.couples(s):
                        through.add((2, s))
                        near = np.concatenate([net.ends[OUT].of(s), net.ends[IN].of(s)])
                    elif self.end_couples(side, s):
                        through.add((side, s))
                        near = net.ends[side].of(s)
                    else:
                        continue
                    for g in (near if net.plain else net.of[near]).tolist():
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
        """The values of flows that are in no coupled part."""
        net, asked = self.net, self.asked
        flows = np.asarray(flows, dtype=np.int64)
        first = flows if net.plain else net.first[flows]
        values = np.minimum(self.capacity[first], np.maximum(asked.request[first], self.extra[first]))
        if net.plain:
            return values
        for k in np.flatnonzero(net.kinds[flows] != DIRECTED).tolist():
            f = int(flows[k])
            mine = net.conns.of(f)
            if net.kinds[f] == ROUTE:
                forward, backward = mine.tolist()
                self._refuse_request(f)
                signed = asked.request[forward] - asked.request[backward]
                values[k] = min(max(signed, -self.capacity[backward]), self.capacity[forward])
            else:
                values[k] = self._fraction(mine)
        return values

    def _fraction(self, legs):
        """The served fraction of a flow with legs that no other flow couples: the largest, up to
        one, that the capacities of its legs allow; zero when no leg asks anything."""
        request, capacity = self.asked.request[legs], self.capacity[legs]
        asking = request > 0
        if not asking.any():
            return 0.0
        return float(min(1.0, (capacity[asking] / request[asking]).min()))

    def _refuse_request(self, f):
        """A route at an endpoint that makes a request: local sharing has no answer."""
        net, asked = self.net, self.asked
        for c in net.conns.of(f).tolist():
            for side, s in ((OUT, net.source[c]), (IN, net.sink[c])):
                if s >= 0 and asked.end_request[side][s] > 0:
                    self._no_request(side, s, f)

    def _no_request(self, side, s, f):
        raise SimulationError(
            f'{self._name(s)}.{SIDES[side]}: a request at an endpoint that the route {self.net.flows[f]} '
            'meets; local sharing has no answer for the positive part of a signed rate in a claim'
        )

    def values(self, after=False):
        """The value of every flow: a rate, a signed rate or a served fraction; with `after`, as they
        hold just after the instant (`settle`)."""
        net, asked = self.net, self.asked
        values = self.alone(np.arange(len(net.flows)))
        stores = np.flatnonzero((self.lower & (net.counts[OUT] > 0)) | (self.upper & (net.counts[IN] > 0)))
        ends = (net.counts >= 2) & (np.isfinite(asked.end_capacity) | (asked.end_request > 0))
        if not len(stores) and not ends.any():
            return values  # no flow meets a bound or shares an endpoint
        seeds = [
            int(net.of[c]) for s in stores.tolist() for side in (OUT, IN) for c in net.ends[side].of(s)[:1]
        ]
        for side, s in np.argwhere(ends).tolist():
            seeds.append(int(net.of[net.ends[side].of(s)[0]]))
        for part in self.parts(seeds):
            values[part] = self.settle(part) if after else self.solve(part)
        return values

    def settle(self, part):
        """The values of the flows of one coupled part as they hold just after the instant (the rule
        of every moment: the rates over the interval after a moment are those of the state just after
        it). A store rests on a bound while its sharing keeps it there: where the values move a store
        held at one of its bounds off it, it is free just after, so its flags are cleared (released)
        and the part is solved again, until the bounds that it holds stay. So a store at its lower
        bound whose claims wait for its supply, and whose sharing fills it, holds stock just after,
        where they wait no more. Where the values with the store free move it back past its bound,
        no rates hold just after the instant (held, they move it off; free, back): the rates switch
        back and forth at its bound, and the run stops, naming it (docs/design/decisions.md, change 10: a run that cannot
        answer stops by name). A net rate within the roundoff of its flows holds a store where it is."""
        found = self.solve(part)
        while True:
            leaving = [
                s
                for s, change in self._nets(part, found)
                if (self.lower[s] and change > 0) or (self.upper[s] and change < 0)
            ]
            if not leaving:
                return found
            saved = [(s, bool(self.lower[s]), bool(self.upper[s])) for s in leaving]
            self.lower[leaving] = False
            self.upper[leaving] = False
            found = self.solve(part)
            nets = dict(self._nets(part, found, leaving))
            back = [s for s, low, high in saved if (low and nets[s] < 0) or (high and nets[s] > 0)]
            if back:
                which = 'lower' if dict((s, low) for s, low, _ in saved)[back[0]] else 'upper'
                raise SimulationError(
                    f'{self._name(back[0])}: local sharing has no rates that hold just after the moment: '
                    f'held at its {which} bound, its sharing moves it off, and free, back past it; the '
                    'rates switch back and forth at its bound'
                )

    def _nets(self, part, values, stores=None):
        """(store, net rate) of each store of a part that its bound couples, held at one bound only
        (or of `stores`): what flows in less what flows out at the part's `values`, 0 within the
        roundoff of its flows. Every connection of such a store is in the part (`part`), so the
        values of the other flows, which a buffer of the instant holds at zero, are not read."""
        net = self.net
        if self._full is None:
            self._full = np.zeros(len(net.flows))
        full = self._full
        full[part] = values
        if stores is None:
            ends = {
                int(e)
                for f in part
                for c in self._connections(f)
                for e in (net.source[c], net.sink[c])
                if e >= 0
            }
            stores = [s for s in sorted(ends) if self.lower[s] != self.upper[s] and self.couples(s)]
        found = []
        for s in stores:
            incoming = net.carried(full, self.asked, net.ends[IN].of(s))
            outgoing = net.carried(full, self.asked, net.ends[OUT].of(s))
            inflow, outflow = float(incoming.sum()), float(outgoing.sum())
            found.append((s, self.face_rate(s, incoming, outgoing, inflow - outflow, inflow + outflow)))
        full[part] = 0.0
        return found

    def face_rate(self, s, incoming, outgoing, net, traffic):
        """Use the general solver's refinement error only where the stock has measured legs."""
        self.uncertain.pop(s, None)
        if self.rate_errors and traffic and abs(net) <= 1e-7 * traffic and self.lower[s] != self.upper[s]:
            legs = (*self.net.ends[IN].of(s), *self.net.ends[OUT].of(s))
            error = sum(self.rate_errors.get(c, 0) for c in legs)
            if error:
                rate, unresolved = departure.refined(incoming, outgoing, error)
                if unresolved:
                    self.uncertain[s] = net, traffic, error
                return rate
        return departure.rate(net, traffic, lambda: (incoming, outgoing))

    def rates(self):
        """The rate of every connection."""
        return self.net.carried(self.values(), self.asked)

    # ---- one part ----------------------------------------------------------------------------------

    def solve(self, part):
        """The values of the flows of one coupled part, in its order."""
        if len(part) == 1 and not self.coupled(part[0]):
            return self.alone(part)
        found = self._groups(part) if (self.net.kinds[part] == DIRECTED).all() else None
        return found if found is not None else self._general(part)

    def _name(self, s):
        return self.net.stores[s]

    def depths(self):
        """A function: the supply depth of a store (`supply_depths`), through the connections that
        can carry flow at the instant."""
        return supply_depths(self.net, self.lower, self.carries)

    def _groups(self, part):
        """The rates of a part of directed flows by groups in supply order (see the module), or None
        where that form does not hold. It reads connections: each flow of the part is one."""
        net, asked, lower, upper = self.net, self.asked, self.lower, self.upper
        request, capacity = asked.request, self.capacity
        part = [int(c) for c in (part if net.plain else net.first[part])]
        if (self.extra[part] > 0).any():
            return None  # a flow with a claim of its own endpoint beside its own claim
        stores = sorted({int(s) for f in part for s in (net.source[f], net.sink[f]) if s >= 0})
        if len(part) == 2 and not any(request[c] > 0 and not is_claim(request[c]) for c in part):
            constrained = [
                s for s in stores if (lower[s] and net.counts[OUT][s]) or (upper[s] and net.counts[IN][s])
            ]
            if len(constrained) == 1 and not any(
                net.counts[side][s] > 1
                and (
                    asked.end_request[side][s] > 0
                    or math.isfinite(asked.end_capacity[side][s])
                    or (side, s) in net.classes
                )
                for s in stores
                for side in (IN, OUT)
            ):
                s = constrained[0]
                ins, outs = net.ends[IN].of(s), net.ends[OUT].of(s)
                if len(ins) == len(outs) == 1 and {ins[0], outs[0]} == set(part):
                    inlet, outlet = int(ins[0]), int(outs[0])
                    incoming, outgoing = paired_rates(
                        request[inlet], request[outlet], capacity[inlet], capacity[outlet], lower[s], upper[s]
                    )
                    return np.array([incoming if c == inlet else outgoing for c in part])
        groups, member = [], {}
        for s in stores:
            outs, ins = net.ends[OUT].of(s), net.ends[IN].of(s)
            if upper[s] and len(ins):
                return None  # a full store passes room upstream
            if any(
                len(here) >= 2 and asked.end_request[side][s] > 0 for side, here in ((OUT, outs), (IN, ins))
            ):
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
            members = members.tolist()
            for f in members:
                rates[f] = 0.0  # a member that flows into its own store brings nothing
            # What flows in through a connection that can carry flow (a closed one brings nothing,
            # and the depths that order the groups do not read it).
            supplied = (
                [g for g in net.ends[IN].of(s).tolist() if self.carries[g]] if kind == 'supply' else None
            )
            rates.update(self.fill(members, IN if kind == 'in' else OUT, s, rates.__getitem__, supplied))
        return np.array([rates[f] for f in part])

    def fill(self, members, side, s, rate_of, supplied=None):
        """The rates of the connections `members` of one group at the endpoint (side, s): its claims
        tier by tier by layer within what the endpoint's capacity allows and, for the outflow of a
        store at its lower bound, within what its inflows `supplied` bring (`rate_of` gives their
        rates), each tier by equal served fractions within the capacities (water-filling). A member
        that asks nothing gets nothing; when none asks, what flows in does not matter."""
        net, asked = self.net, self.asked
        request, capacity = asked.request, self.capacity
        rates = dict.fromkeys(members, 0.0)
        claims = [f for f in members if is_claim(request[f])]
        if not claims:
            return rates
        available = float(asked.end_capacity[side][s])
        if supplied is not None:
            available = min(available, sum(rate_of(g) for g in supplied))
        for layer in sorted({int(self.layer[net.of[f]]) for f in claims}):
            tier = np.array([f for f in claims if self.layer[net.of[f]] == layer], dtype=np.int64)
            given = water(request[tier], capacity[tier], available)
            for f, rate in zip(tier.tolist(), given.tolist()):
                rates[f] = rate
            available = max(0.0, available - float(given.sum()))
        return rates

    def _general(self, part):
        """The values of a part by the selection order (`selection.select`)."""
        self.selected += 1
        net, asked, lower, upper = self.net, self.asked, self.lower, self.upper
        request = asked.request
        place = {f: k for k, f in enumerate(part)}
        n = len(part)
        rows = Rows(n)
        mine = {f: self._connections(f) for f in part}
        stores = sorted(
            {int(s) for f in part for c in mine[f] for s in (net.source[c], net.sink[c]) if s >= 0}
        )

        def term(connections):
            """The total rate of connections: its linear part over the part's flows, and the
            positive parts of the routes' rates, as (flow's place, sign)."""
            a, parts = np.zeros(n), []
            for c in connections:
                k, role = place[int(net.of[c])], net.roles[c]
                if role == DIRECT:
                    a[k] += 1.0
                elif role == LEG:
                    a[k] += request[c]
                else:
                    parts.append((k, 1.0 if role == FORWARD else -1.0))
            return a, parts

        def signed(connections):
            """The same total with the sign of a route kept: a route counts once, on its forward leg."""
            a = np.zeros(n)
            for c in connections:
                k, role = place[int(net.of[c])], net.roles[c]
                a[k] += {DIRECT: 1.0, FORWARD: 1.0, BACKWARD: 0.0, LEG: request[c]}[int(role)]
            return a

        claims, prefs = [], []
        for s in stores:
            outs, ins = net.ends[OUT].of(s).tolist(), net.ends[IN].of(s).tolist()
            if (lower[s] and outs) or (upper[s] and ins):
                net_in = signed(ins) - signed(outs)
                if lower[s]:
                    rows.at_least(net_in, 0.0)  # what leaves must also arrive
                if upper[s]:
                    rows.at_most(net_in, 0.0)  # what arrives must also leave
            for side, here in ((OUT, outs), (IN, ins)):
                if not here or any(int(net.of[c]) not in place for c in here):
                    continue
                total, parts = term(here)
                if math.isfinite(asked.end_capacity[side][s]):
                    if parts:
                        rows.with_parts(total, parts, asked.end_capacity[side][s])
                    else:
                        rows.at_most(total, asked.end_capacity[side][s])
                wanted = float(asked.end_request[side][s])
                if is_claim(wanted):
                    if parts:
                        route = next(c for c in here if net.roles[c] in (FORWARD, BACKWARD))
                        self._no_request(side, s, int(net.of[route]))
                    claims.append((Claim(tuple(here), (side, s), 1), total, wanted))
                    ranked = net.ranking(self.carries).get((side, s))
                    if ranked:
                        carried = np.zeros(n)
                        for members in ranked[:-1]:
                            carried = carried + term(members)[0]
                            prefs.append((carried, wanted))
        low, high, target = np.zeros(n), np.full(n, math.inf), np.zeros(n)
        units = np.ones(n)
        rates = [k for k, f in enumerate(part) if net.kinds[f] != LEGS]
        ceilings = physical_capacities(net, asked.capacity, [mine[f][0] for f in part], lower, upper)
        for f in part:
            k, cs = place[f], mine[f]
            kind = int(net.kinds[f])
            one = np.zeros(n)
            one[k] = 1.0

            def claim(served, wanted, cs=cs, f=f):
                claims.append((Claim(tuple(cs), None, int(self.layer[f])), served, wanted))

            if kind == DIRECTED:
                c = cs[0]
                high[k], target[k] = ceilings[k], request[c]
                if is_claim(request[c]):
                    claim(one, float(request[c]))
            elif kind == ROUTE:
                forward, backward = cs
                signed_request = float(request[forward] - request[backward])
                low[k], high[k], target[k] = -asked.capacity[forward], asked.capacity[forward], signed_request
                if is_claim(abs(signed_request)):  # its sign names the direction of its one claim
                    claim(math.copysign(1.0, signed_request) * one, abs(signed_request))
            else:
                asking = [c for c in cs if request[c] > 0]
                high[k] = 1.0 if asking else 0.0  # every leg asks nothing: the fraction is zero
                target[k] = high[k]
                for c in asking:
                    if math.isfinite(asked.capacity[c]):
                        rows.at_most(request[c] * one, asked.capacity[c])
                if asking:
                    claim(one, 1.0)
        # The programs read each rate in units of the part's size, and a fraction as it is.
        sizes = [float(x) for x in request[[c for f in part for c in mine[f]]] if is_claim(x)]
        sizes += [
            float(x)
            for x in asked.capacity[[c for f in part for c in mine[f]]]
            if math.isfinite(x) and is_claim(x)
        ]
        sizes += [float(x) for x in asked.end_request[:, stores].ravel() if is_claim(x)]
        units[rates] = max(sizes, default=1.0)
        tiers = {}
        places = claim_order(net, lower, upper, self.carries, [claim for claim, _, _ in claims])
        for place, (_, a, wanted) in zip(places, claims):
            tiers.setdefault(place, []).append((a, wanted))

        def measure(raw, refined):
            for k, flow in enumerate(part):
                for c in mine[flow]:
                    self.rate_errors.pop(c, None)
                    if refined[k] in (low[k], high[k], target[k]):
                        continue
                    uncertainty = max(abs(refined[k] - raw[k]), math.ulp(float(refined[k])))
                    self.rate_errors[c] = uncertainty * (request[c] if net.roles[c] == LEG else 1.0)

        try:
            return select(
                rows,
                low,
                high,
                [tiers[key] for key in sorted(tiers)],
                prefs,
                target,
                units,
                net.own_scales[list(part)],
                measure,
            )
        except SimulationError as problem:
            raise SimulationError(
                f'{problem}; the part: the stores {", ".join(self._name(s) for s in stores)} and the '
                f'flows {", ".join(net.flows[f] for f in part)}'
            ) from None
