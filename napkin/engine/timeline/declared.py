"""The way of a connected set that a declared solver owns (spec: "An entity owns its solver",
"Solver and execution contract"), on lines.

A declared solver determines the rates of the flows that its `solve_for` names, the stored numbers
that it names and its own unknowns, and nothing else (the owner's rule after G2, PLAN.md change 19;
spec, "Solver and execution contract": "Flows that no solver determines follow their own
endpoints"). A flow that shares a store with one of its flows is in the same calculation
(`plan.connect`), so that the books of the store still balance: the solver sees it through its
bounds and the rows that it meets (a junction passes no more than its pipes can carry), and its
claim keeps its place of local sharing, so local sharing splits what arrives. A relation or an
objective of the solver that reads such a flow is refused by name: to decide who is served, the
provider names those rates. The problem of the set at an instant
(`Former`) is formed from the program by the rules of the solve library (`napkin/engine/solve/`):

- **unknowns**: each flow of the set, with its request as its target and one canonical unit of its
  dimension as its reference scale (so flows of two dimensions that trade off are each divided by one
  canonical unit): a directed flow's rate within [0, its capacity], a route's signed rate within its
  capacity on the magnitude, a flow with legs' served fraction within [0, 1], with its target one
  when a leg asks (zero, and the fraction held at zero, when none does) and each leg within its own
  capacity; each other result within its domain, its reference as its target (a stored number's
  initializer, which the run evaluates at its first solve, or an unknown's own initializer, zero
  without one), and as its scale its declared scale, else its finite width, else one canonical unit;
- **rows**: each store that rests on a bound (what leaves a store at its lower bound must also
  arrive, what arrives at a store at its upper bound must also leave, and a store at both bounds,
  such as one held at [0, 0], balances: one row `==`), each endpoint's capacity, and each relation
  of `constraints`;
- **objectives**, in written order, maximized ones negated;
- **claims**: each positive request of a flow (a route's in the direction of its sign, a flow with
  legs' on its fraction, as a request of one) and of an endpoint, in tiers by one rule with local
  sharing (`network.claim_order`): the endpoints' rules rank every claim, named or not (an
  endpoint's `priority(...)` orders its flows' claims, `network.layers`, and its own claim is in the
  first layer), and the solver's own sharing acts only among the claims that they leave equal. A
  claim that shares an endpoint with a claim that the solver does not determine, directly or
  through others, keeps its tier of local sharing: its level (from the supply and the room of its
  stores, through the connections that can carry flow) and its layer. The solver's own claims share
  across endpoints: their level passes on across the solver's connections that no endpoint ranks,
  so a solver of the four requested rates of the spec's junctions gives A, B and C 1/3 each, while
  B and C, which an onward pipe ranked after A serves, wait for A. The preferred classes of an
  endpoint that has a request carry it first (spec: "A preferred route has first access to useful
  requested work, up to the outstanding claim it serves"): after every tier, as much of the request
  as can be on its first class, then on its first two, and so on, each a claim alone in a tier of
  its own.

The expressions of the solver read its unknowns as symbols (`Affine`): a formula, a reduction or a
dynamic read that reads an unknown is expanded where it is read, a keyed read whose key and keys are
known numbers reads the member that it selects (one keyed by an unknown is refused by name, as the
spec leaves it out), and any other value is a number of the instant, read from the run. The forms
are those of the spec: affine `==`, `<=` and `>=`, their conjunction, `all(...)` and sums, products
and quotients by known numbers, a membership `x in [lo, hi]` (the chain `lo <= x <= hi` of its two
relations, once the ends that the solve knows are checked as every evaluation of a membership checks
them: a reversed interval stops the run by the name of its failure, `ops.REVERSED`), and positive
parts (`max` of an unknown is `a + max(0, b - a)`, one INTERNAL unknown of the library for each),
where they are convex: minimized, or on the small side of `<=`. A strict relation, `!=`, `or`,
`any`, `not` of a relation, a relation under a condition, `min` of an unknown, a product of two
unknowns, a division by one, another function of one, and a request or a capacity of the set that
reads one fail the run with a diagnostic that names the solver and the form. An expression is read
with no recursion (`walk.walked`): a chain of formulas that read an unknown is followed to its end,
each formula once at an instant.

**Between moments the answer holds** where the problem reads nothing that moves between moments:
the rates are constant and each store is a line, as on the lines (`lines.py`). A store that reaches
a bound is put on it, and the problem is solved again with its row; that is an event of the
instance, and the stores whose lines and the rates and results whose values change are a moment
when a watched condition or another set reads them (`run.next_moment`). A store at its bound whose
answer moves it away is released at once and the problem solved again without its bound
(`DeclaredWay._settled`), so that the answer is the one that holds just after the instant. A moment
that changes what the problem reads (a written input, a flow that joins or leaves, a keyed read at
its key time, a store that met a bound at the moment) builds the set again (`ways.py`), so the
problem is solved once in a round, after the stages commit, in the order of the sets' levels. A
problem equal to the one that the solver settled on last is not solved again, as the oracle caches
it; each solve is an entry `solve` of the trace, at its time and round.

A problem that reads what moves (a store of the set through a setting, a relation or a domain, or
the time) runs on `MovingDeclared`: its rates follow the state, solved at each trial state of an
integrator, in a set of at most `MOVING` stores; a larger one stops by name (D3).

The answer is polished (`polished`): put exactly on the bounds and rows that it holds to the
library's tolerance, so that at a vertex its numbers are the vertex's, as exact arithmetic gives.
The polish, and the clip to the bounds, are candidates (`published`): one takes the solver's answer's
place only where it passes the solve's end checks and is no worse on any rank
(`solve.Answer.admits`), and the solver's checked answer is published otherwise.

One `solve.Solver` serves each declared solver for the whole run (`Ways.kept`): its HiGHS instance
follows the problem by the keys of its unknowns and rows, so members that join and leave the set add
and delete columns and rows. Keys are engine names: `('flow', name)`, `('value', name)`, a positive
part by the text of its node, a row by its store, endpoint, leg or relation.

A solve that cannot give the answer of the selection order (`SolveFailure`: infeasible, unbounded,
a budget exceeded, a numerical failure) stops the run there, naming the solver, the step and the
time, before a trigger or a report can read a partial answer: nothing of the failed solve is
published.
"""

from __future__ import annotations

import hashlib
import heapq
import math

import numpy as np
import scipy.sparse as sp
from scipy.integrate import solve_ivp
from scipy.sparse.linalg import splu

from ...core import expr as nodes
from ...core import ops
from ...core.errors import ExpressionError
from ..continuous import dense
from ..continuous.walk import walked
from ..errors import SimulationError
from ..solve import FLOW, OTHER, Budget, Problem, SolveFailure, Solver
from .collections import selected
from .family import Columns
from .lines import asked_of
from .network import (
    BACKWARD,
    FORWARD,
    IN,
    LEG,
    LEGS,
    OUT,
    ROUTE,
    SIDES,
    Claim,
    claim_order,
    network_of,
)
from .plan import DYNAMIC, FORMULA, LOOKUP, REDUCE
from .reads import lazily
from .record import fitted

SLACK = 1e-6  # a store at its bound holds there when its answer moves it out by less than this part
MOVING = 20  # the most stores of a declared solver's set whose problem moves between moments
ANSWER = 1e-7  # the precision of an answer of the solve library, relative to its size
# An answer this near a bound or a row's side, relative to their size, holds it exactly: the
# library keeps each optimum and each fair level to about 1e-7 (`solve/ranked.py` KEPT, `fair.py`
# FIX), which the distance step may take, and checks its answer to this (`solve/solver.py` CHECK).
NEAR = 1e-6


class Unsupported(SimulationError):
    """A form that the constraint language of a solver does not have."""


class Affine:
    """`constant + sum(terms[j] * x_j)` over the columns of a problem."""

    __slots__ = ('constant', 'terms')

    def __init__(self, terms=None, constant=0.0):
        self.terms = terms if terms is not None else {}
        self.constant = float(constant)

    def plus(self, other, sign=1.0):
        """self + sign * other, for an Affine or a number."""
        if not isinstance(other, Affine):
            return Affine(dict(self.terms), self.constant + sign * _number(other))
        terms = dict(self.terms)
        for column, value in other.terms.items():
            terms[column] = terms.get(column, 0.0) + sign * value
        return Affine(terms, self.constant + sign * other.constant)

    def times(self, factor):
        """self * factor, for a number."""
        factor = _number(factor)
        if factor == 0:
            return Affine({}, 0.0)
        return Affine(
            {column: value * factor for column, value in self.terms.items()}, self.constant * factor
        )


def _number(value):
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise Unsupported(f'a solver reads {value!r} where a number is expected')
    return float(value)


def _affine(value):
    return value if isinstance(value, Affine) else Affine({}, _number(value))


class Former:
    """The problem of a declared solver's set at an instant (see the module). One former serves an
    instance of the way: what each name reads is found once."""

    def __init__(self, run, connected, net, connections):
        self.run, self.plan = run, run.plan
        self.declared = run.plan.solvers[connected.solver]
        self.connected, self.net, self.connections = connected, net, connections
        self.columns = Columns(run)
        plan = self.plan
        # The engine names that are unknowns of the problem: the value of each flow, and the results.
        self.unknown = {}
        self.named = set(self.declared.flows)  # the flows whose values the solver determines
        self.undecided = set()  # the values of the set's other flows, which local sharing gives
        for flow in net.flows:
            found = plan.flows[flow]
            name = f'{flow}.served_fraction' if found.kind == 'legs' else f'{flow}.actual_rate'
            self.unknown[name] = ('flow', flow)
            if flow not in self.named:
                self.undecided.add(name)
        for name in connected.results:
            self.unknown[name] = ('value', name)
        self._reads = {}
        self._names = {}  # what each name that reads an unknown gives at the instant (`_name`)
        self._touch = None  # the place of each store in the oracle's order (`_first_touch`)

    # ---- whether a name reads an unknown -------------------------------------------------------

    def reads_unknown(self, name):
        """Whether a value reads an unknown of the problem, through formulas, reductions and the
        members of dynamic reads."""
        found = self._reads.get(name)
        if found is None:
            if name in self.unknown:
                found = True
            else:
                expanded = self.plan.reads_now(self.plan.expanded(name))
                found = any(leaf in self.unknown for leaf in expanded.leaves)
            self._reads[name] = found
        return found

    def _symbolic(self, node):
        return any(self.reads_unknown(name) for name in nodes.names(node) if name != 't')

    # ---- the problem -------------------------------------------------------------------------------

    def problem(self, t, lower, upper):
        """The problem (`solve.Problem`) at time t, with the stores flagged on their lower and upper
        bounds; the request of each connection is `requests`."""
        plan, net, declared = self.plan, self.net, self.declared
        self.t, self.problem_, self.cols, self.convex, self.parts = t, Problem(), {}, set(), {}
        self._names = {}  # what each name that reads an unknown gives at this instant (`_name`)
        self.pending, self.rows = [], []  # positive parts (key, Affine), rows (key, terms, lower, upper)
        problem = self.problem_
        requests = asked_of(
            net, np.array(self.columns.at([c.request for c in self.connections], t), float), t
        )
        capped = [k for k, c in enumerate(self.connections) if c.capacity is not None]
        capacity = np.full(len(self.connections), math.inf)
        if capped:
            capacity[capped] = self.columns.at([self.connections[k].capacity for k in capped], t)
        bad = np.isnan(capacity) | (capacity < 0)
        if bad.any():
            k = int(np.flatnonzero(bad)[0])
            raise SimulationError(
                f'{self.connections[k].name}: a capacity that is {capacity[k]:g} at {t:g} h'
            )
        self.requests = requests
        ends = self._ends(t)
        # The connections that can carry flow at t: the structure that the order of the claims reads.
        carries = capacity > 0
        for (side, s), (_, cap) in ends.items():
            if cap is not None and not cap > 0:
                carries[net.ends[side].of(s)] = False
        legs = net.roles == LEG
        carries[legs] &= requests[legs] > 0
        layer = net.layers(carries)  # the priority layers among the connections that can carry flow
        classes = net.ranking(carries)

        def claim(f, connections):
            """A flow's claim as the order reads it (`network.Claim`)."""
            return Claim(tuple(connections), None, int(layer[f]), net.flows[f] in self.named)

        claims, order = [], []  # (terms, request) of each claim, and each claim as the order reads it
        for f, flow in enumerate(net.flows):
            mine = net.conns.of(f).tolist() if not net.plain else [f]
            kind = int(net.kinds[f])
            if kind == LEGS:
                asks = bool((requests[mine] > 0).any())
                column = problem.unknown(
                    ('flow', flow), 0.0, 1.0 if asks else 0.0, FLOW, 1.0 if asks else 0.0
                )
                for c in mine:
                    if math.isfinite(capacity[c]) and requests[c] > 0:
                        self.rows.append(
                            (
                                ('leg', self.connections[c].name),
                                {column: float(requests[c])},
                                -math.inf,
                                capacity[c],
                            )
                        )
                if asks:
                    claims.append(({column: 1.0}, 1.0))
                    order.append(claim(f, mine))
                self.cols[f'{flow}.served_fraction'] = column
                continue
            if kind == ROUTE:
                signed = float(self.columns.at([plan.flows[flow].request], t)[0])
                if not math.isfinite(signed):
                    raise SimulationError(f'{flow}: a request that is {signed:g} at {t:g} h')
                cap = capacity[mine[0]]
                column = problem.unknown(('flow', flow), -cap, cap, FLOW, signed)
                if signed != 0:
                    claims.append(({column: 1.0 if signed > 0 else -1.0}, abs(signed)))
                    order.append(claim(f, mine))
            else:
                column = problem.unknown(
                    ('flow', flow), 0.0, capacity[mine[0]], FLOW, float(requests[mine[0]])
                )
                if requests[mine[0]] > 0:
                    claims.append(({column: 1.0}, float(requests[mine[0]])))
                    order.append(claim(f, mine))
            self.cols[f'{flow}.actual_rate'] = column
        for name in self.connected.results:
            self.cols[name] = self._result(name)
        preferred = []  # (the place of the endpoint in the oracle's order, terms, amount)
        for (side, s), (wanted, cap) in ends.items():
            store = net.stores[s]
            here = net.ends[side].of(s).tolist()
            total = self._total(here)
            if cap is not None and math.isfinite(cap):
                self._relation(total.plus(cap, -1.0), '<=', ('end', store, SIDES[side]))
            if wanted > 0:
                if any(int(net.roles[c]) in (FORWARD, BACKWARD) for c in here):
                    raise Unsupported(
                        f'{store}.{SIDES[side]}.request with a route at that endpoint, in the solver '
                        f'{declared.id}: a request on the positive parts of a route is not convex'
                    )
                # An endpoint's claim is in the first layer; it is the solver's when the solver
                # determines every connection of the endpoint that can carry flow.
                claims.append((total.terms, wanted))
                mine = all(net.flows[int(net.of[c])] in self.named for c in here if carries[c])
                order.append(Claim(tuple(here), (side, s), 1, mine))
                # The preferred routes of the aggregate request carry it first, class after class
                # (spec: "A preferred route has first access to useful requested work, up to the
                # outstanding claim it serves"): as much of it as can be on the first class, then on
                # the first two, after every tier of fair sharing.
                carried = Affine()
                for members in classes.get((side, s), ())[:-1]:
                    carried = carried.plus(self._total(list(members)))
                    preferred.append(((self._first_touch(s), side), dict(carried.terms), wanted))
        for s, store in enumerate(net.stores):
            if not (lower[s] or upper[s]):
                continue
            balance = Affine()
            for c in net.ends[IN].of(s).tolist():
                balance = balance.plus(self._signed(c))
            for c in net.ends[OUT].of(s).tolist():
                balance = balance.plus(self._signed(c), -1.0)
            if lower[s] and upper[s]:
                # A store held at both bounds balances: one equality, not two rows of one sign each,
                # which leave the distance step a slack on a row that the other row repeats (at
                # 30,000 places a Newton system of 316k unknowns instead of 233k, P1)
                self._relation(balance, '==', ('store', store, 'held'))
            elif lower[s]:
                self._relation(balance.times(-1.0), '<=', ('store', store, 'lower'))
            else:
                self._relation(balance, '<=', ('store', store, 'upper'))
        for origin, node in declared.constraints:
            seen = {}
            for affine, op, label in _relations(self.value(node), origin):
                # A row is named by where it comes from, so it keeps its key while others join or leave.
                seen[label] = seen.get(label, -1) + 1
                self._relation(affine, op, ('relation', origin, *label, seen[label]))
        objectives = []
        for sense, node, origin in declared.objectives:
            found = self.value(node)
            if not isinstance(found, Affine):
                _number(found)  # a constant objective ranks nothing
                continue
            terms = found.terms if sense == 'minimize' else {j: -v for j, v in found.terms.items()}
            if any(terms.get(j, 0.0) < 0 for j in self.convex):
                raise Unsupported(
                    f'{origin}: an objective that maximizes a positive part, in the solver {declared.id} '
                    '(not convex)'
                )
            objectives.append(terms)
        made = self._parts()
        problem.rows(
            [key for key, _, _, _ in self.rows],
            _matrix([made(terms) for _, terms, _, _ in self.rows], len(problem.keys)),
            [low for _, _, low, _ in self.rows],
            [high for _, _, _, high in self.rows],
        )
        for terms in objectives:
            problem.minimize(made(terms))
        places = self._order(lower, upper, carries, order)
        tiers = {key: k for k, key in enumerate(sorted(set(places)))}
        for (terms, wanted), key in zip(claims, places):
            problem.claim(made(terms), wanted, tiers[key])
        # Each preferred class is a tier of its own after the others, in the order in which the
        # oracle meets the endpoints: one claim alone in a tier is served as far as it can be.
        for k, (_, terms, wanted) in enumerate(sorted(preferred, key=lambda item: item[0])):
            problem.claim(made(terms), wanted, len(tiers) + k)
        return problem

    def _order(self, lower, upper, carries, order):
        """The place of each claim in the selection order (`network.claim_order`): the endpoints'
        rules rank every claim, and the solver's own sharing acts only among the claims that they
        leave equal. A ring that local sharing reads, among flows that the solver does not name, fails
        with what to name."""
        try:
            return claim_order(self.net, lower, upper, carries, order)
        except SimulationError as ring:
            raise SimulationError(
                f'{ring}; the solver {self.declared.id} does not name every flow there, and a flow that '
                'it does not name keeps local sharing: name them in its solve_for to decide them'
            ) from None

    def _first_touch(self, s):
        """The place of a store in the order in which the oracle meets the stores of a problem: by
        the first connection that meets it, its flows in their order of creation, a connection's
        source before its sink."""
        found = self._touch
        if found is None:
            net, plan = self.net, self.plan
            found = self._touch = {}
            order = sorted(range(len(net.source)), key=lambda c: (plan.number(net.flows[int(net.of[c])]), c))
            for place, c in enumerate(order):
                for end, which in ((int(net.source[c]), 0), (int(net.sink[c]), 1)):
                    if end >= 0:
                        found.setdefault(end, (place, which))
        return found[s]

    def _parts(self):
        """Make the positive parts of the problem, in one block for each depth (a part of an
        expression that holds parts comes after them); gives the map from the terms of an Affine,
        whose parts are placeholders (negative columns), to terms over the problem's columns."""
        problem, column = self.problem_, {}
        depth = {}
        for p, (_, affine) in enumerate(self.pending):
            depth[-(p + 1)] = 1 + max((depth[j] for j in affine.terms if j < 0), default=0)
        for level in sorted(set(depth.values())):
            places = [p for p in range(len(self.pending)) if depth[-(p + 1)] == level]
            terms = [{column.get(j, j): v for j, v in self.pending[p][1].terms.items()} for p in places]
            found = problem.positive_parts(
                [self.pending[p][0] for p in places],
                _matrix(terms, len(problem.keys)),
                [self.pending[p][1].constant for p in places],
            )
            column.update({-(p + 1): int(j) for p, j in zip(places, found.tolist())})

        def made(terms):
            return {column.get(j, j): v for j, v in terms.items()}

        return made

    def _result(self, name):
        """The column of a result that is no flow: its domain, its reference and its scale."""
        run, plan = self.run, self.plan
        value = plan.values[name]
        reader = self._reader()

        def number(node, what):
            if node is None:
                return None
            found = lazily(node, reader, plan.units, self.t)
            if isinstance(found, bool) or not isinstance(found, int | float) or math.isnan(found):
                raise SimulationError(f'{name}: {what} is {found!r}, not a number')
            return float(found)

        low, high = number(value.lower, 'its lower bound'), number(value.upper, 'its upper bound')
        references = run.ways.references
        if name not in references or self._own_unknown(name):
            references[name] = number(value.node, 'its reference')
        scale = number(value.scale, 'its scale')
        if scale is None:
            width = (high - low) if low is not None and high is not None else math.inf
            scale = width if math.isfinite(width) and width > 0 else 1.0
        lower = -math.inf if low is None else low
        upper = math.inf if high is None else high
        return self.problem_.unknown(('value', name), lower, upper, OTHER, references[name], abs(scale))

    def _own_unknown(self, name):
        """Whether a result is an unknown of the solver's own, whose preferred value it evaluates at
        each solve (a stored number keeps the reference of its initializer, evaluated once)."""
        key = self.plan.values[name].key
        return len(key.steps) == 2 and f'{key.owner}.{key.steps[0]}' == self.declared.id

    def _ends(self, t):
        """{(side, store): (request, capacity)} of the endpoints of the set's stores that have one."""
        plan, net = self.plan, self.net
        found, names = {}, []
        place = {store: s for s, store in enumerate(net.stores)}
        for (store, side), end in plan.ends.items():
            if store in place and (end.capacity is not None or plan.settled(end)):
                names.append(((SIDES.index(side), place[store]), end))
        if not names:
            return found
        values = self.columns.at(
            [end.request for _, end in names]
            + [end.capacity for _, end in names if end.capacity is not None],
            t,
        ).tolist()
        requests, caps = values[: len(names)], iter(values[len(names) :])
        for (where, end), wanted in zip(names, requests):
            cap = next(caps) if end.capacity is not None else None
            if not math.isfinite(wanted) or wanted < 0 or (cap is not None and (math.isnan(cap) or cap < 0)):
                raise SimulationError(
                    f'{end.store}.{end.side}: a request or a capacity that is {wanted:g}, {cap} at {t:g} h'
                )
            found[where] = (wanted, cap)
        return found

    def _term(self, c):
        """The nonnegative rate of a connection: a directed flow's rate, a leg's fraction times its
        request, the positive part of a route's rate in the direction of its leg."""
        net = self.net
        f, role = int(net.of[c]), int(net.roles[c])
        column = self.cols[self._flow_name(f)]
        if role == LEG:
            return Affine({column: float(self.requests[c])})
        if role == FORWARD:
            return self._positive(('leg rate', net.connections[c]), Affine({column: 1.0}))
        if role == BACKWARD:
            return self._positive(('leg rate', net.connections[c]), Affine({column: -1.0}))
        return Affine({column: 1.0})

    def _signed(self, c):
        """The same rate with its sign kept: a route counts once, on its forward leg."""
        net = self.net
        role = int(net.roles[c])
        if role == FORWARD:
            return Affine({self.cols[self._flow_name(int(net.of[c]))]: 1.0})
        if role == BACKWARD:
            return Affine()
        return self._term(c)

    def _total(self, connections):
        total = Affine()
        for c in connections:
            total = total.plus(self._term(c))
        return total

    def _flow_name(self, f):
        flow = self.net.flows[f]
        return f'{flow}.served_fraction' if int(self.net.kinds[f]) == LEGS else f'{flow}.actual_rate'

    def _positive(self, key, affine):
        """max(0, affine) as an INTERNAL unknown of the problem, one for each key: a placeholder (a
        negative column) until the problem's parts are made together (`_parts`)."""
        if not affine.terms:
            return max(affine.constant, 0.0)
        column = self.parts.get(key)
        if column is None:
            column = self.parts[key] = -(len(self.pending) + 1)
            self.pending.append((key, affine))
            self.convex.add(column)
        return Affine({column: 1.0})

    def _relation(self, affine, op, key):
        """The row `affine <= 0` or `affine == 0`."""
        affine = _affine(affine)
        if any(affine.terms.get(j, 0.0) < 0 for j in self.convex) or (
            op == '==' and any(j in self.convex for j in affine.terms)
        ):
            raise Unsupported(
                f'{key[1] if len(key) > 1 else key}: a positive part on the large side of a relation, in the '
                f'solver {self.declared.id} (not convex)'
            )
        self.rows.append((key, affine.terms, -affine.constant if op == '==' else -math.inf, -affine.constant))

    # ---- expressions with unknowns ----------------------------------------------------------------

    def _reader(self):
        t = self.t
        return lambda name: self.run.value(name, t)

    def value(self, node, label=()):
        """The value of a node at the instant: a number, a yes/no or a text where it reads no
        unknown; else an `Affine`, or the relations of a test (a list of (Affine, op, label)). It is
        found with no recursion (`walk.walked`): each part of the node, and each formula that it reads
        and that reads an unknown, is a computation on the driver's stack, so a chain of formulas of
        any length reads the unknown at its end; what each such name gives is found once at the
        instant."""
        return walked(self._value(node, label))

    def _value(self, node, label):
        """The computation of `value` (`walk.walked`): it yields the computation of each part."""
        if not self._symbolic(node):
            return lazily(node, self._reader(), self.plan.units, self.t)
        if isinstance(node, nodes.Ref):
            return (yield self._name(node.name))
        if isinstance(node, nodes.Unary):
            found = yield self._value(node.operand, label)
            if node.op == 'neg':
                return _affine(found).times(-1.0) if isinstance(found, Affine) else -found
            if node.op == 'pos':
                return found
            raise self._refused('not of a relation or of an unknown')
        if isinstance(node, nodes.Binary):
            left = yield self._value(node.left, label)
            right = yield self._value(node.right, label)
            if isinstance(left, list) or isinstance(right, list):
                raise self._refused('arithmetic on a relation')
            if node.op == 'add':
                return _affine(left).plus(right)
            if node.op == 'sub':
                return _affine(left).plus(right, -1.0)
            if node.op == 'mul':
                if isinstance(left, Affine) and isinstance(right, Affine):
                    raise self._refused('a product of two unknowns')
                return left.times(right) if isinstance(left, Affine) else right.times(left)
            if node.op == 'div':
                if isinstance(right, Affine):
                    raise self._refused('a division by an unknown')
                if _number(right) == 0:
                    raise SimulationError(f'a division by zero in the solver {self.declared.id}')
                return left.times(1.0 / right)
            raise self._refused(f'the operation {node.op} of an unknown')
        if isinstance(node, nodes.Compare):
            values = []
            for part in node.operands:
                values.append((yield self._value(part, label)))
            return self._chain(node.ops, values, label)
        if isinstance(node, nodes.BoolOp):
            found = []
            for part in node.values:
                value = yield self._value(part, label)
                if node.op == 'or' and isinstance(value, list | Affine):
                    raise self._refused('a disjunction')
                if isinstance(value, list):
                    found += value
                elif node.op == 'and' and not value:
                    return [(Affine({}, 1.0), '<=', label)]  # false can never hold
                elif node.op == 'or' and value:
                    return True
            return found if node.op == 'and' else False
        if isinstance(node, nodes.IfElse):
            test = yield self._value(node.test, label)
            if isinstance(test, list | Affine):
                raise self._refused('a relation under a condition')
            return (yield self._value(node.body if test else node.orelse, label))
        if isinstance(node, nodes.Call):
            if node.function == 'within':
                return (yield self._membership(node, label))
            if node.function == 'max':
                values = []
                for part in node.args:
                    values.append((yield self._value(part, label)))
                best = values[0]
                for k, value in enumerate(values[1:], 1):
                    if isinstance(best, Affine) or isinstance(value, Affine):
                        gap = _affine(value).plus(best, -1.0)
                        best = _affine(best).plus(self._positive(('max', nodes.text(node), k), gap))
                    else:
                        best = max(best, value)
                return best
            if node.function == 'min':
                raise self._refused('min of an unknown (not convex)')
            raise self._refused(f'the function {node.function} of an unknown')
        raise self._refused(f'an expression of kind {type(node).__name__}')

    def _chain(self, ops_, values, label):
        """The relations of a chain of comparisons of `values`, each pair once (`_compare`)."""
        found = []
        for op, a, b in zip(ops_, values, values[1:]):
            found += _compare(op, a, b, label, self)
        return found

    def _membership(self, node, label):
        """A membership `x in [lo, hi]` that reads an unknown (`expr.membership`): x and its ends are
        read once, the ends that the instant knows are checked as every evaluation of a membership
        checks them (a reversed interval is an error that names itself, `ops.REVERSED`; spec: "Reversed
        bounds are an error"), and the membership is the chain `lo <= x <= hi` of its relations."""
        chain, _, _ = nodes.membership(node)
        values = []
        for part in node.args:
            values.append((yield self._value(part, label)))
        x, low, high = values
        if not isinstance(low, Affine | list) and not isinstance(high, Affine | list) and low > high:
            raise ExpressionError(f'{ops.REVERSED}: [{low!r}, {high!r}]')
        return self._chain(chain.ops, [low, x, high], label)

    def _refused(self, what):
        return Unsupported(f'unsupported in the solver {self.declared.id}: {what}')

    def _name(self, name):
        """A name that reads an unknown: the unknown, or what a formula, a reduction or a dynamic
        read gives of it (a computation of `walk.walked`), found once at the instant."""
        found = self._names.get(name)
        if found is None:
            found = self._names[name] = yield self._named(name)
        return found

    def _named(self, name):
        if name in self.undecided:
            raise Unsupported(
                f'the solver {self.declared.id} reads {name}, which it does not determine: a flow that '
                'a solver does not name keeps the local sharing of its endpoints; name it in solve_for '
                'to decide it'
            )
        if name in self.cols:
            return Affine({self.cols[name]: 1.0})
        value = self.plan.values[name]
        if value.kind == FORMULA:
            # An enforced equality is the equality here; its readers compare it within the solver's
            # tolerance (`plan.Plan._tolerate_enforced`).
            found = yield self._value(self.plan.enforced.get(name, value.node), ())
            if isinstance(found, list):
                return [(affine, op, (name, *label)) for affine, op, label in found]
            return found
        if value.kind == REDUCE:
            reduction = self.plan.reductions[name]
            entries = self.run.kept_of(name)
            return (
                yield self._reduced(reduction.op, [reduction.names[k] for k in entries], reduction.spelled)
            )
        if value.kind == DYNAMIC:
            dynamic = self.plan.dynamic[name]
            members = self.plan.members(dynamic.source)
            names = [self.plan.project(point, dynamic.steps) for point in members]
            return (yield self._reduced(dynamic.op, names, dynamic.spelled))
        if value.kind == LOOKUP:
            # A keyed read that selects its member from known numbers reads that member's value.
            keyed = self.plan.keyed[name]
            if self._symbolic(keyed.key) or any(
                self.reads_unknown(read) for read in keyed.reads() - set(keyed.names)
            ):
                raise self._refused(f'{keyed.spelled}: a lookup keyed by an unknown of the solver')
            entry = selected(keyed, self._reader(), self.plan.units, self.t)
            if entry is None:
                x = float(lazily(keyed.key, self._reader(), self.plan.units, self.t))
                raise SimulationError(f'{keyed.spelled}: no member has a key at or below {x:g}')
            return (yield self._value(nodes.ref(keyed.names[entry]), ()))
        raise self._refused(f'{name}, which the problem reads as an unknown')

    def _reduced(self, op, names, spelled):
        """What a sum, an `all` or a `max` of the values of `names` gives (a computation of
        `walk.walked`)."""
        if op == 'sum':
            total = Affine()
            for name in names:
                found = yield self._value(nodes.ref(name), ())
                if isinstance(found, list):
                    raise self._refused(f'{spelled}: a sum of relations')
                total = total.plus(found)
            return total
        if op == 'all':
            found = []
            for name in names:
                value = yield self._value(nodes.ref(name), ())
                if isinstance(value, list):
                    found += [(affine, o, label or (name,)) for affine, o, label in value]
                elif not value:
                    return [(Affine({}, 1.0), '<=', (name,))]
            return found
        if op == 'max':
            values = []
            for name in names:
                values.append((yield self._value(nodes.ref(name), ())))
            if not values:
                raise SimulationError(f'{spelled} reads an empty collection')
            best = values[0]
            for name, value in zip(names[1:], values[1:]):
                gap = _affine(value).plus(best, -1.0)
                best = _affine(best).plus(self._positive(('max', spelled, name), gap))
            return best
        raise self._refused(f'{spelled}: {op} of an unknown')


def _compare(op, a, b, label, former):
    """The relations of `a op b`, or the yes/no of two numbers."""
    if not isinstance(a, Affine) and not isinstance(b, Affine):
        if isinstance(a, list) or isinstance(b, list):
            raise former._refused('a comparison of a relation')
        return [] if _plain(op, a, b) else [(Affine({}, 1.0), '<=', label)]
    if op in ('lt', 'gt', 'ne'):
        spelling = {'lt': '<', 'gt': '>', 'ne': '!='}[op]
        raise former._refused(f'the relation {spelling} (use <=, >= or ==)')
    if op == 'le':
        return [(_affine(a).plus(b, -1.0), '<=', label)]
    if op == 'ge':
        return [(_affine(b).plus(a, -1.0), '<=', label)]
    return [(_affine(a).plus(b, -1.0), '==', label)]


def _plain(op, a, b):
    return {
        'le': a <= b,
        'ge': a >= b,
        'lt': a < b,
        'gt': a > b,
        'eq': a == b,
        'ne': a != b,
    }[op]


def _relations(found, origin):
    """The relations of a constraint's value: a yes holds, a no can never hold."""
    if isinstance(found, list):
        return found
    if isinstance(found, Affine):
        raise Unsupported(f'{origin}: a constraint is a relation, not a number')
    return [] if found else [(Affine({}, 1.0), '<=', ())]


class DeclaredWay:
    """One connected set of a declared solver, as a way of a run (`ways.py`), from the time `t` on
    (see the module). Its rates hold between its events (`lines`)."""

    lines = True

    def __init__(self, run, connected, values, t, key):
        plan = self.plan = run.plan
        self.run, self.key, self.connected, self.t0 = run, key, connected, float(t)
        self.recorder = run.recorder
        self.declared = plan.solvers[connected.solver]
        stores = list(connected.stores)
        self.net, connections, self.recorded = network_of(run, [connected], stores)
        self.former = Former(run, connected, self.net, connections)
        self.stores, self.flows = stores, list(self.net.flows)
        self.place = {name: s for s, name in enumerate(stores)}
        self.row = {name: f for f, name in enumerate(self.flows)}
        self.y = np.array([float(values[name]) for name in stores])
        self.since = np.full(len(stores), self.t0)
        self.slope = np.zeros(len(stores))
        self.lower = np.array([run.bounds[name][0] for name in stores])
        self.upper = np.array([run.bounds[name][1] for name in stores])
        self.value = np.zeros(len(self.flows))
        self.results = {}
        self.version = np.zeros(len(stores), dtype=np.int64)
        self.due = []
        self.alive = True
        tolerance = run.recorder.tolerance
        factor = plan.numerics.atol_factor
        for name in connected.results:
            tolerance.setdefault(name, factor)

    # ---- solving ------------------------------------------------------------------------------------

    def answer(self, t, lower, upper):
        """The answer of the problem at time t with the stores flagged on their bounds: (the value of
        each flow, {result: value}). A problem equal to the one that the solver answered last is not
        solved again. Used at the trial states of a moving set (`MovingDeclared`), which traces its
        own solves."""
        problem, arrays, signature = self._formed(t, lower, upper)
        last = self.run.ways.last.get(self.declared.id)
        if last is not None and last[0] == signature:
            return self._values(arrays, last[1])
        x = self._solved(t, problem, arrays)
        self.run.ways.last[self.declared.id] = (signature, x)
        return self._values(arrays, x)

    def _formed(self, t, lower, upper):
        """(the problem at time t with the stores flagged on their bounds, its arrays, its digest)."""
        declared = self.declared
        try:
            problem = self.former.problem(t, lower, upper)
        except ExpressionError as problem:
            raise SimulationError(f'{problem} [the solver {declared.id}, t = {t:g} h]') from None
        except ValueError as problem:
            raise SimulationError(f'the solver {declared.id} at t = {t:g} h: {problem}') from None
        arrays = problem.arrays()
        return problem, arrays, _signature(arrays)  # a digest: a checkpoint holds it as data (`saved.py`)

    def _solved(self, t, problem, arrays):
        """The polished answer of a problem by the selection order, on the solver that the run keeps."""
        run, declared = self.run, self.declared
        kept = run.ways.kept.get(declared.id)
        if kept is None:
            budgets = self.plan.configuration.budgets
            kept = run.ways.kept[declared.id] = Solver(
                Budget(budgets.fair_programs, budgets.newton_steps, budgets.qp_iterations)
            )
        try:
            found = kept.solve(problem)
        except SolveFailure as failure:
            raise SimulationError(
                f'the solver {declared.id} cannot answer at t = {t:g} h: {failure}'
            ) from None
        return published(arrays, found)

    def _values(self, arrays, x):
        """(the value of each flow, {result: value}) of an answer. The unknowns of a problem do not
        depend on the flags of its stores, so an answer serves each problem of the instant."""
        at = {key: j for j, key in enumerate(arrays.keys)}
        flows = np.array([x[at[('flow', flow)]] for flow in self.flows], dtype=float)
        return flows, {name: float(x[at[('value', name)]]) for name in self.connected.results}

    def _publish(self, t, flows, results):
        """The answer of a solve at time t becomes the present; gives the names of the rates and the
        results whose values changed."""
        changed = []
        for f, found in enumerate(flows.tolist()):
            if found != self.value[f] or t == self.t0:
                self.value[f] = found
                self.recorder.add(self.recorded[f], t, found, 0.0)
                changed.append(self.recorded[f])
        for name, found in results.items():
            if found != self.results.get(name):
                self.results[name] = found
                self.recorder.add(name, t, found, 0.0)
                changed.append(name)
        return changed

    def _solve(self, t):
        """Solve the problem at time t, from the stores' values on their lines; gives the names of
        the rates and the results whose values changed."""
        values = self.y + self.slope * (t - self.since)
        return self._publish(t, *self._settled(t, values <= self.lower, values >= self.upper))

    def _settled(self, t, low, high):
        """The answer at time t with the stores flagged on their bounds (`low`, `high`) where it holds
        them there: a store on one bound that the answer moves off is released, and the problem is
        solved again without that bound, until the flags stay. The answer is then the one that holds
        just after t, whatever moments other sets have, as the oracle's (`tests/reference/network.py`,
        `solve`); it matters where a claim's level reads the bound (`network.supply_depths`). A
        release whose answer would move a released store past its bound is not made.

        The solver keeps the problem that it settled on and its answer (`Ways.last`), which serve
        again, unsolved, where the problem is that one, as formed or with the bounds released that
        the kept answer moves off. A solve that runs is traced once, as one of the run's. Gives
        (flows, results)."""
        ways, sid = self.run.ways, self.declared.id
        problem, arrays, signature = self._formed(t, low, high)
        last = ways.last.get(sid)
        # A kept answer of other unknowns (a flow joined or left since) answers no problem here.
        if last is not None and len(last[1]) == len(arrays.keys):
            if last[0] == signature:
                return self._values(arrays, last[1])
            leaving = self._moved(self._values(arrays, last[1])[0], low ^ high, low, inward=True)
            if leaving.any() and self._formed(t, low & ~leaving, high & ~leaving)[2] == last[0]:
                return self._values(arrays, last[1])
        x = self._solved(t, problem, arrays)
        flows, results = self._values(arrays, x)
        for _ in range(len(self.stores)):
            leaving = self._moved(flows, low ^ high, low, inward=True)
            if not leaving.any():
                break
            again = self._formed(t, low & ~leaving, high & ~leaving)
            found = self._solved(t, again[0], again[1])
            moved = self._values(again[1], found)
            if self._moved(moved[0], leaving, low, inward=False).any():
                break
            low, high = low & ~leaving, high & ~leaving
            signature, x, (flows, results) = again[2], found, moved
        ways.last[sid] = (signature, x)
        self.recorder.entry(t, 'solve', self.declared.origin, self.declared.member)
        return flows, results

    def _moved(self, flows, stores, low, inward):
        """The flags of the stores of `stores` (each on its lower bound where `low` holds, else on its
        upper) that the values of the flows move off their bound (`inward`) or past it, by more than
        `NEAR` of what flows through them."""
        inflow, outflow = self._through(flows)
        off = np.where(low, 1.0, -1.0) * (inflow - outflow)
        margin = NEAR * (inflow + outflow)
        return stores & (off > margin if inward else off < -margin)

    def _through(self, flows):
        """(what flows into each store, what flows out of it) from the values of the flows."""
        net = self.net
        rate = net.carried(flows, _Asked(self.former.requests)) if len(self.flows) else np.zeros(0)
        inflow = np.array([rate[net.ends[IN].of(s)].sum() for s in range(len(self.stores))])
        outflow = np.array([rate[net.ends[OUT].of(s)].sum() for s in range(len(self.stores))])
        return inflow, outflow

    def _lines(self, t, forced=()):
        """Start again the line of each store whose rate changed (or that is `forced`: the indices of
        stores that were put on a bound), from its value at t; gives the stores whose lines changed."""
        net = self.net
        rate = net.carried(self.value, _Asked(self.former.requests)) if len(self.flows) else np.zeros(0)
        changed = []
        for s, store in enumerate(self.stores):
            inflow = float(rate[net.ends[IN].of(s)].sum())
            outflow = float(rate[net.ends[OUT].of(s)].sum())
            slope = inflow - outflow
            value = float(self.y[s] + self.slope[s] * (t - self.since[s]))
            low, high = value <= self.lower[s], value >= self.upper[s]
            if (low and slope < 0) or (high and slope > 0):
                # A store at its bound: an answer within the solver's tolerance holds it there.
                if abs(slope) > SLACK * (1.0 + inflow + outflow):
                    raise SimulationError(
                        f'{store}: the solver {self.declared.id} moves it past its bound at {t:g} h'
                    )
                slope = 0.0
            if slope == self.slope[s] and s not in forced:
                continue
            self.y[s], self.since[s], self.slope[s] = value, t, slope
            self.version[s] += 1
            self.recorder.add(store, t, value, slope)
            changed.append(store)
            reach = math.inf
            if slope < 0 and math.isfinite(self.lower[s]):
                reach = t + (value - self.lower[s]) / -slope
            elif slope > 0 and math.isfinite(self.upper[s]):
                reach = t + (self.upper[s] - value) / slope
            if reach <= self.plan.horizon:
                heapq.heappush(self.due, (reach, s, int(self.version[s])))
        return changed

    # ---- the interface of a way (`ways.py`) --------------------------------------------------------

    def begin(self):
        """Solve at the start of the instance, and start each store's line."""
        self._solve(self.t0)
        self._lines(self.t0, forced=range(len(self.stores)))

    def retire(self, key):
        """The set leaves its instance: nothing of it moves from now on."""
        self.alive = False
        self.due = []

    def level_at(self, name, t):
        """The value of a store on its line at time t, or of a result."""
        s = self.place.get(name)
        if s is None:
            return self.results[name]
        return float(self.y[s] + self.slope[s] * (t - self.since[s]))

    def rate_at(self, name, t):
        """What the solver gives of a flow: its actual rate, a route's signed rate, or a served
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

    def _put(self, reach):
        """Each store whose line reaches its bound at `reach` is put on it; gives their indices."""
        found = []
        while self.peek() == reach:
            _, s, _ = heapq.heappop(self.due)
            bound = self.lower[s] if self.slope[s] < 0 else self.upper[s]
            self.y[s], self.since[s], self.slope[s] = bound, reach, 0.0
            self.version[s] += 1
            found.append(s)
        return found

    def step(self):
        """The next lines that reach their bounds: the stores are put on them, and the problem is
        solved again. Gives the stores whose lines and the rates and results whose values change."""
        reach = self.peek()
        self.run.now = reach
        met = self._put(reach)
        changed = self._solve(reach)
        return self._lines(reach, forced=met), changed, True

    def snap(self):
        """The next lines reach their bounds at the time of a moment: the stores are put on them, and
        the moment's settling solves the set again (`ways.py`). Gives the stores, as what changed and
        as what met its bound."""
        stores = [self.stores[s] for s in self._put(self.peek())]
        return stores, stores

    def cut(self, t):
        """Nothing to commit: a line holds to its next event."""


class Segment:
    """A segment of a moving set: from `start` to `end`, its dense output (`state(t)`), and the
    store whose event ended it (None at the end of the window)."""

    def __init__(self, start, end, solution, event):
        self.start, self.end, self.solution, self.event = start, end, solution, event


class MovingDeclared(DeclaredWay):
    """A declared solver's set whose problem reads what moves between moments: a store of the set,
    through a request, a capacity, a relation or a domain, or the time. Its rates follow the state, as
    every rate that reads a moving quantity does (spec, "A rate can follow a moving quantity"; D3):
    SciPy's Radau integrates its stores, and the rates at each trial state of a step are the answer
    of the selection order there, solved on the solver's kept instance and not traced (spec,
    "Rounds": evaluations at trial states are separate from the once-in-a-round rule). The flags of
    the bounds hold through a segment, and a store held on a bound stays on it; a segment ends where
    a store reaches a bound or where the answer would move a store held on a bound off it, and the
    problem is solved there with the new flags (a traced solve). Its pieces are fitted to each
    segment (`record.fitted`): the stores from the integrator's dense output, the rates and the
    results from solves at the fitted times.

    Each evaluation of the rates is a whole solve, and Radau's Jacobian by differences costs one for
    each store, so a step costs a few solves times the stores. A set of more than `MOVING` stores
    stops the run when it is built, with a diagnostic that names the solver, what moves and the
    limit, and never holds a moving rate at its value of the last moment (D3: a large valid model may
    stop with an explicit failure of time; it never freezes a moving rate)."""

    lines = False

    def __init__(self, run, connected, values, t, key):
        super().__init__(run, connected, values, t, key)
        if len(self.stores) > MOVING:
            raise SimulationError(
                f'the solver {self.declared.id}: its problem reads what moves between moments, so its '
                f'{len(self.stores)} stores follow a solve at each trial state of the integrator; a '
                f'set of more than {MOVING} stores would take a whole solve for each store at each '
                'step, and stops here: read values that hold between moments, or split the set'
            )
        self.time = self.t0
        self.low, self.high = self.y <= self.lower, self.y >= self.upper
        self.pending = None
        self.trial = None
        self._cache = {}
        numerics = self.plan.numerics
        sizes = [run.recorder.tolerance.get(name, numerics.atol_factor) for name in self.stores]
        self.atol = np.maximum(np.array(sizes, dtype=float), 1e-12)
        self.rtol = numerics.rtol

    # ---- rates at a state ----------------------------------------------------------------------

    def _held(self, y):
        """A state with each store held on a bound at its bound."""
        y = np.array(y, dtype=float)
        y[self.low] = self.lower[self.low]
        y[self.high] = self.upper[self.high]
        return y

    def _net(self, flows):
        """The rate of change of each store from the values of the flows."""
        inflow, outflow = self._through(flows)
        return inflow - outflow

    def _at(self, t, y):
        """(flows, results, the rate of each store) at a trial state, solved once for each state."""
        key = (float(t), self._held(y).tobytes())
        found = self._cache.get(key)
        if found is None:
            self.trial = self._held(y)
            try:
                flows, results = self.answer(float(t), self.low, self.high)
                found = (flows, results, self._net(flows))
            finally:
                self.trial = None
            if len(self._cache) > 256:
                self._cache.clear()
            self._cache[key] = found
        return found

    def _derivative(self, t, y):
        rate = self._at(t, y)[2].copy()
        rate[self.low | self.high] = 0.0  # a held store stays on its bound through the segment
        return rate

    # ---- segments ----------------------------------------------------------------------------------

    def _settle(self, t):
        """At time t: a store held on a bound whose answer moves it off is released, until the
        flags hold; then the answer there is the present (a traced solve)."""
        for _ in range(len(self.stores) + 1):
            self.trial = self._held(self.y)
            try:
                flows, results = self.answer(t, self.low, self.high)
            finally:
                self.trial = None
            rate = self._net(flows)
            leaving = (self.low & (rate > SLACK * (1.0 + np.abs(rate)))) | (
                self.high & (rate < -SLACK * (1.0 + np.abs(rate)))
            )
            if not leaving.any():
                break
            self.low, self.high = self.low & ~leaving, self.high & ~leaving
        self.recorder.entry(t, 'solve', self.declared.origin, self.declared.member)
        changed = self._publish(t, flows, results)
        for s, store in enumerate(self.stores):
            self.recorder.add(store, t, float(self.y[s]), 0.0)
        return changed

    def _segment(self, until):
        """The next segment, from the present to `until` or the first event before it."""
        events = []
        for s in range(len(self.stores)):
            if self.low[s]:
                events.append((s, lambda t, y, s=s: self._at(t, y)[2][s] - SLACK * self.atol[s], 1.0))
            elif self.high[s]:
                events.append((s, lambda t, y, s=s: -self._at(t, y)[2][s] - SLACK * self.atol[s], 1.0))
            else:
                if math.isfinite(self.lower[s]):
                    events.append((s, lambda t, y, s=s: y[s] - self.lower[s], -1.0))
                if math.isfinite(self.upper[s]):
                    events.append((s, lambda t, y, s=s: self.upper[s] - y[s], -1.0))
        functions = []
        for _, function, direction in events:
            function.terminal, function.direction = True, direction
            functions.append(function)
        solution = solve_ivp(
            self._derivative,
            (self.time, until),
            self.y,
            method='Radau',
            rtol=self.rtol,
            atol=self.atol,
            events=functions or None,
            dense_output=True,
            max_step=self.plan.numerics.max_step,
        )
        if solution.status < 0:
            raise SimulationError(f'the solver {self.declared.id}: {solution.message} at {self.time:g} h')
        end, event = float(solution.t[-1]), None
        if solution.status == 1:
            event = next(events[k][0] for k, times in enumerate(solution.t_events) if len(times))
        return Segment(self.time, end, solution.sol, event)

    def _state(self, t):
        segment = self.pending
        if segment is None or t <= segment.start:
            return self._held(self.y)
        return self._held(segment.solution(min(t, segment.end)))

    def _commit(self, end):
        """The pending segment to `end`: its pieces are recorded and the state is there. The stores
        are fitted to the integrator's dense output, to their tolerances; the rates and the results,
        each value of which is a solve, to the precision of the solver (`ANSWER` of their size)."""
        segment = self.pending
        if end > segment.start:
            tolerance = np.array([self.recorder.tolerance.get(name, 1e-9) for name in self.stores])

            def states(times):
                return np.array([self._state(at) for at in np.asarray(times).tolist()])

            for name, pieces in zip(self.stores, fitted(states, segment.start, end, tolerance)):
                self.recorder.add_pieces(name, pieces)
            names = [*self.recorded, *self.connected.results]

            def answers(times):
                rows = []
                for at in np.asarray(times, dtype=float).tolist():
                    flows, results, _ = self._at(at, self._state(at))
                    rows.append([*flows, *(results[name] for name in self.connected.results)])
                return np.array(rows, dtype=float)

            first = answers([segment.start])[0]
            tolerance = np.array(
                [
                    max(self.recorder.tolerance.get(name, 0.0), ANSWER * (1.0 + abs(v)))
                    for name, v in zip(names, first)
                ]
            )
            if names:
                for name, pieces in zip(names, fitted(answers, segment.start, end, tolerance)):
                    self.recorder.add_pieces(name, pieces)
        self.y = self._state(end)
        self.time = end
        self.pending = None

    # ---- the interface of a way (`ways.py`) --------------------------------------------------------

    def begin(self):
        """The answer at the start of the instance; the first segment is made when the run asks."""
        self._settle(self.t0)

    def peek(self):
        """The end of the next segment, which is made now if it is not yet."""
        if self.pending is None:
            until = min(self.run.limit, self.plan.horizon)
            if self.time >= until:
                return math.inf
            self.pending = self._segment(until)
        return self.pending.end

    def step(self):
        """Commit the next segment; at an event a store meets or leaves its bound, and the problem
        is solved there. Gives the stores and the rates and results that change."""
        segment = self.pending
        self._commit(segment.end)
        self.run.now = segment.end
        s = segment.event
        if s is not None:
            if self.low[s] or self.high[s]:
                self.low[s] = self.high[s] = False  # it leaves its bound
            else:
                at_lower = abs(self.y[s] - self.lower[s]) <= abs(self.y[s] - self.upper[s])
                self.y[s] = self.lower[s] if at_lower else self.upper[s]
                (self.low if at_lower else self.high)[s] = True
        changed = self._settle(segment.end)
        return list(self.stores), sorted(set(changed) | set(self.recorded)), True

    def snap(self):
        """The next segment ends at the time of a moment: committed as any other. Gives what changed,
        and the store whose event ended it where the store met its bound there."""
        s = self.pending.event
        met = [] if s is None or self.low[s] or self.high[s] else [self.stores[s]]
        stores, rates, _ = self.step()
        return stores + rates, met

    def cut(self, t):
        """The run stands at time t inside the next segment: the segment up to t is committed, and
        the answer there is the present. A segment that starts at t is made again after the moment,
        and the answers of trial states are forgotten, so that none crosses a moment (`saved.py`)."""
        segment = self.pending
        self._cache.clear()
        if segment is not None and t <= segment.start:
            self.pending = None
            return
        if segment is None or t >= segment.end:
            return
        self._commit(t)
        flows, results, _ = self._at(t, self.y)
        self.value[:] = flows
        self.results.update(results)

    def level_at(self, name, t):
        """The value of a store, or of a result, at a time inside the present window; of a store,
        before the next segment is made (at a moment), along its present rate (`drift`)."""
        s = self.place.get(name)
        if s is not None:
            if self.trial is not None:
                return float(self.trial[s])
            if self.pending is None and t > self.time:
                return float(self._held(self.y)[s] + (t - self.time) * self.drift()[s])
            return float(self._state(t)[s])
        if self.pending is None or t <= self.pending.start:
            return self.results[name]
        return self._at(t, self._state(t))[1][name]

    def drift(self):
        """The rate of each store at the present state, a store held on a bound at zero: what a
        condition read an instant after a moment (`triggers.AFTER`) follows before the next segment
        is made, as a line follows its rate. It is the answer of an untraced solve there."""
        return self._derivative(self.time, self.y)

    def breaks(self, start, end):
        """The times strictly between start and end at which the form of the next segment changes:
        the ends of the steps of its integrator."""
        segment = self.pending
        if segment is None:
            return []
        return [float(at) for at in segment.solution.ts.tolist() if start < at < end]

    def motion(self, weights, start, end):
        """How the sum of the stores of `weights` ({store: weight}) moves from start to end, a piece
        inside one step of the next segment (`continuous/dense.py`): the cubic of the step of Radau
        that holds the piece, which the run reads as it is, and a store held on a bound at its bound."""
        rows = np.array([self.place[name] for name in weights], dtype=np.int64)
        w = np.array(list(weights.values()), dtype=float)
        still = (self.low | self.high)[rows]
        segment = self.pending
        if segment is None or end <= segment.start:
            return dense.held(self._held(self.y)[rows], w)
        solution = segment.solution
        k = int(np.searchsorted(solution.ts, 0.5 * (start + end), side='right')) - 1
        output = solution.interpolants[min(max(k, 0), len(solution.interpolants) - 1)]
        found = dense.held(self._held(self.y)[rows[still]], w[still])
        if not still.all():
            found += dense.of_step(output, rows[~still], w[~still], start, end)
        return found

    def rate_at(self, name, t):
        """What the solver gives of a flow at a time inside the present window."""
        f = self.row[name.rsplit('.', 1)[0]]
        if self.pending is None or t <= self.pending.start:
            return float(self.value[f])
        return float(self._at(t, self._state(t))[0][f])

    def linear(self, store):
        """None: a store of a moving set is on a curve."""
        return None


class _Asked:
    """The requests of the connections, as `Network.carried` reads them."""

    def __init__(self, request):
        self.request = request


def published(arrays, found):
    """The answer that a solve publishes: its polish (`polished`) within the bounds, else the
    library's answer within the bounds, else the library's answer as it is. Each change of the
    answer after the solve is a candidate that takes its place only if it passes the solve's own end
    checks and is no worse on any rank (`solve.Answer.admits`: each kept optimum and each objective
    against the answer's, each claim's served fraction against its fair level and the answer's,
    every row and bound), and a candidate that fails is dropped."""
    for answer in (polished(arrays, found.x, found.levels), found.x):
        candidate = np.clip(answer, arrays.lower, arrays.upper)
        if found.admits(candidate):
            return candidate
    return found.x


def polished(arrays, x, levels):
    """The answer put exactly on the bounds and rows that it holds to within `NEAR` of their own
    size, its claims that fair sharing held together at one level on one fraction, and its claims
    served in full that it leaves at most at their requests on them, by the least change of the other
    unknowns in the metric of the distance step, each over its reference scale, so that an answer that
    the distance step projected stays its projection (the least-norm solution of those rows, by one
    sparse factorization).

    The library meets its rows to 1e-9 of their size, keeps an optimum to 1e-7 of its size, which
    the later ranks may take, and holds a claim that it cannot serve in full at its level less 1e-7
    (`solve/fair.py`, FIX), and one served in full at its request less as much, which the distance
    step may take. In exact arithmetic the claims that one program of fair sharing holds rest on one
    level, which the rows that bind them give, and a claim served in full that is served no more
    rests on its request. So at a vertex the polished answer has the numbers of the vertex, and an
    event time that follows from its rates is what exact arithmetic gives. The polished answer is a
    candidate: `published` gives it only where it passes the solve's end checks.

    Each unknown is near a bound by its own size (`_sizes`, at most the width of its interval), so
    that an idle pipe whose capacity is 1e-7 L/h stays at zero, not at its capacity; and a flow that
    the library serves in full keeps its request, which its claim's row then holds exactly, rather
    than a bound near it (`_served`): a requested delivery of 1e-7 L/h is no rounding of zero. So too
    the terms of a claim served in full that its terms on their bounds would serve short keep their
    values (`_starved`): a delivery of 5e-7 L/h split between two pipes is none either. A row is near
    its side by the sizes of its own terms, and a row that is an equality, such as the books of a
    store held at both bounds, always holds exactly."""
    x = np.array(x, dtype=float)
    lower, upper = arrays.lower, arrays.upper
    size = _sizes(arrays)
    levels = np.asarray(levels, dtype=float)
    kept = _served(arrays, x, levels)
    low = np.isfinite(lower) & (np.abs(x - lower) <= NEAR * size) & ~kept
    high = np.isfinite(upper) & (np.abs(x - upper) <= NEAR * size) & ~low & ~kept
    kept = _starved(arrays, x, levels, low, high)
    low, high = low & ~kept, high & ~kept
    found = x.copy()
    found[low], found[high] = lower[low], upper[high]
    blocks, sides = [], []
    A = arrays.A
    if A.shape[0]:
        value = A @ found
        own = abs(A) @ size
        equal = arrays.row_lower == arrays.row_upper
        left = np.isfinite(arrays.row_lower) & (equal | (np.abs(value - arrays.row_lower) <= NEAR * own))
        right = np.isfinite(arrays.row_upper) & ~left & (np.abs(value - arrays.row_upper) <= NEAR * own)
        rows = np.flatnonzero(left | right)
        blocks.append(A[rows])
        sides.append(np.where(left, arrays.row_lower, arrays.row_upper)[rows])
    if len(levels):
        fraction = sp.diags_array(1.0 / arrays.request) @ arrays.F
        served = fraction @ found
        full = np.flatnonzero((levels >= 1.0) & (served <= 1.0 + NEAR))
        blocks.append(fraction[full])
        sides.append(np.ones(len(full)))
        groups = {}
        for i, level in enumerate(levels.tolist()):
            if level < 1.0:
                groups.setdefault(level, []).append(i)
        for members in groups.values():
            if len(members) > 1:
                # One program held them at one level: their fractions are equal.
                first = fraction[[members[0]] * (len(members) - 1)]
                blocks.append(sp.csr_array(fraction[members[1:]] - first))
                sides.append(np.zeros(len(members) - 1))
    free = np.flatnonzero(~(low | high))
    if blocks and len(free):
        B = sp.csr_array(sp.vstack(blocks))
        residual = np.concatenate(sides) - B @ found
        if len(residual) and np.abs(residual).max() > 0:
            # The least change in the metric of the distance step, each unknown over its reference
            # scale S, so that a projection of the distance step stays one: d = S e with B S e = r,
            # [[I, (BS)'], [BS, -eps I]] [e; m] = [0; r], which a dependent row leaves nonsingular.
            scale = arrays.scale[free]
            B = sp.csc_array(B[:, free] @ sp.diags_array(scale))
            m, n = B.shape
            K = sp.block_array([[sp.eye_array(n), B.T], [B, -1e-12 * sp.eye_array(m)]], format='csc')
            try:
                move = splu(K).solve(np.r_[np.zeros(n), residual])[:n]
            except RuntimeError:  # a singular system: the answer stays as the library gave it
                return x
            found[free] += scale * move
    return arrays.positive_parts(found)


def _starved(arrays, x, levels, low, high):
    """The unknowns that are terms of a claim that the library serves in full, all of whose terms
    the polish would put on a bound (`low`, `high`) where they would serve it short: the polish
    leaves them off their bounds, and the claim's row holds them on its request."""
    found = np.zeros(arrays.n, dtype=bool)
    if not len(levels):
        return found
    F = sp.csr_array(arrays.F)
    served = (F @ x) / arrays.request
    on = np.where(low, arrays.lower, np.where(high, arrays.upper, x))
    short = (F @ on) / arrays.request < 1.0 - NEAR
    snapped = low | high
    for i in np.flatnonzero((levels >= 1.0) & (served <= 1.0 + NEAR) & short).tolist():
        terms = F.indices[F.indptr[i] : F.indptr[i + 1]]
        if snapped[terms].all():
            found[terms] = True
    return found


def _sizes(arrays):
    """The own size of each unknown of a problem, by which its answer is near a bound or a row: its
    reference scale (one canonical unit for a flow, in which the library keeps its answer), at most
    the width of its interval, where that is finite and positive."""
    width = arrays.upper - arrays.lower
    return np.where(np.isfinite(width) & (width > 0), np.minimum(arrays.scale, width), arrays.scale)


def _served(arrays, x, levels):
    """The unknowns that are the one term of a claim that the library serves in full, and no more
    than in full: the polish holds each on its request, not on a bound."""
    found = np.zeros(arrays.n, dtype=bool)
    if len(levels):
        F = sp.csr_array(arrays.F)
        served = (F @ x) / arrays.request
        alone = np.flatnonzero((np.diff(F.indptr) == 1) & (levels >= 1.0) & (served <= 1.0 + NEAR))
        found[F.indices[F.indptr[alone]]] = True
    return found


def _matrix(rows, width):
    """A sparse matrix of the rows given as {column: coefficient}, `width` columns wide."""
    count = sum(len(terms) for terms in rows)
    at, columns, values = np.empty(count, np.int64), np.empty(count, np.int64), np.empty(count)
    k = 0
    for i, terms in enumerate(rows):
        n = len(terms)
        at[k : k + n] = i
        columns[k : k + n] = np.fromiter(terms.keys(), np.int64, n)
        values[k : k + n] = np.fromiter(terms.values(), float, n)
        k += n
    return sp.csr_array((values, (at, columns)), shape=(len(rows), width))


def _signature(arrays):
    """What a problem is, to compare it with the one solved last: the SHA-256 of its keys and its
    arrays, which a checkpoint holds as data."""
    parts = [
        tuple(arrays.keys),
        tuple(arrays.row_keys),
        arrays.lower.tobytes(),
        arrays.upper.tobytes(),
        arrays.scale.tobytes(),
        arrays.target.tobytes(),
        arrays.kind.tobytes(),
        arrays.row_lower.tobytes(),
        arrays.row_upper.tobytes(),
        arrays.A.data.tobytes(),
        arrays.A.indices.tobytes(),
        arrays.A.indptr.tobytes(),
        arrays.request.tobytes(),
        arrays.tier.tobytes(),
        arrays.F.data.tobytes(),
        arrays.F.indices.tobytes(),
        arrays.F.indptr.tobytes(),
    ]
    parts += [(np.asarray(c).tobytes(), np.asarray(v).tobytes()) for c, v in arrays.objectives]
    digest = hashlib.sha256()
    for part in parts:
        found = part if isinstance(part, bytes) else repr(part).encode()
        digest.update(b'%d:' % len(found) + found)
    return digest.hexdigest()
