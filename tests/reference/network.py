"""The rates and the solver results of one instant, and how they move until the next moment.

`settle` cuts the unknowns of the instant into independent calculations, assembles each as a
problem of `order.select`, and publishes the answers. A calculation is "affected" when its assembled
problem differs from the one that it solved last: only then is it solved again.

**Sharing is local** (decision of G0). Each endpoint shares among its own flows by its own rule.
Where a store holds nothing, the flows out of it can only pass on what flows into it, so their
claims wait for the claims that bring that supply: claims are settled level by level in the
direction of supply ("upstream supply first"). The level of a claim is the supply depth of the
stores that it draws from: 0 for SOURCE or a store that holds stock, and one more than its deepest
feeder for a store at its lower bound. So with 1 L/h into a junction that feeds A and a second
junction of B and C, the first junction splits 1/2 and 1/2 and the second 1/4 and 1/4. Where a
store is full, the flows into it can only take the room that its outflows make, so room is settled
against the direction of flow: the claims into a full store wait for those into the full stores that
its outflows fill, and the level of a claim is also at least the room depth of the stores that it
fills (one more than the deepest full store that their outflows fill, 0 for none, so one full store
shares on the levels of supply). Inside one level the fair-sharing rank of the selection order
applies.

**A declared solver decides only what it names** (the owner's rule after G2). An endpoint's rule ranks
every claim of its flows, named or not, and the solver's own sharing acts only among the claims that
the endpoints' rules leave equal (`_places`). A flow of the calculation that the solver does not name
keeps the local sharing of its endpoints: the solver sees it through its bounds and the rows that it
meets, so that the books still balance, and its claim keeps its place of local sharing, as does every
claim that shares an endpoint with it. The solver's own claims share across endpoints: a solver over
the four requesting flows of the junctions gives A, B and C 1/3 each; one that names only the feed
leaves 1/2, 1/4 and 1/4; and where the first junction ranks A ahead of the onward pipe, B and C,
which that pipe serves, wait for A. A relation or an objective of the solver that reads a flow that it
does not name is refused: to decide who is served, it names them.

**Just after the instant** (the rule of every moment): the rates over the interval after a moment are
those of the state just after it, whether or not a moment falls there. So a solve reads its settings
as just after the instant (mode 'germ': a comparison at the closed side of its switch answers for the
instants after it), and again with the stores moving as its answer moves them where that changes them
(`settle`); and a store holds its bound only while the answer keeps it there, for local sharing as for
a declared solver (`solve`).

The structure of an instant is that of the connections that can carry flow: one of capacity zero,
at its flow or at an endpoint, and a leg that asks nothing, pass neither supply nor room, close no
ring and rank in no class.

`motion` gives the level of each store and the rate of each flow as polynomials in the time after
the moment, and the times at which a rate input or a store bound asks for a new settlement.
"""

from dataclasses import dataclass
from fractions import Fraction

from .errors import Diagnostic, NotCovered, RunFailed
from .evaluate import Cell, Coll, End, Ev, FlowRT, LegRT, Res, Scope, Sol, _rows, label
from .model import Unknown, show
from .order import Lin, relation, select
from .poly import Poly, plain


@dataclass(eq=False)
class Component:
    """One independent calculation: its unknowns, its flows and at most one declared solver."""

    vars: list
    flows: list
    sols: list
    key: frozenset
    faces: frozenset  # allocation constraints at this instant; balances stay in the view
    busy: bool = False
    done: bool = False
    released: frozenset = frozenset()  # (store, 'lo' or 'hi'): a bound that its solve does not hold
    signature: tuple = None  # the signature of the problem that its solve settled on (`_moving`)


def var_of(flow):
    """The one independent unknown of a flow: its rate, or the served fraction of a flow with legs."""
    return ('frac' if flow.kind == 'legs' else 'rate', flow)


def connections(flow):
    """The connections of a flow: its legs (a reversible flow has two), or itself."""
    return list(flow.legs.values()) if flow.legs else [flow]


def stores_of(flow):
    """The modeled stores at the ends of a flow's connections."""
    return {cell for c in connections(flow) for cell in (c.src, c.dst) if cell is not None}


def incident(flows, end):
    """The connections of `store.outflow` or `store.inflow` that are present, in creation order."""
    found = []
    for f in flows:
        for c in connections(f):
            if (c.src if end.side == 'outflow' else c.dst) == end.cell:
                found.append((c, f))
    return sorted(found, key=lambda p: p[0].number)


# --- the structure of an instant ---------------------------------------------------------------------


def _targets(x, entry):
    if isinstance(x, Res) and not isinstance(x.var[1], (End, LegRT)):
        return [x.var]
    if isinstance(x, Cell):
        return [('cell', x)]
    if isinstance(x, Coll):
        return [v for _, _, item in x.items for v in _targets(item, entry)]
    raise Diagnostic(f'solve_for {show(entry)}: not a rate, a served fraction or a stored field')


def declarations(run):
    """Each solver, its scope and the results it determines at this instant."""
    view = run.view
    for ent in run.ents.values():
        for decl in ent.template.solvers:
            sol = Sol(ent, decl.name)
            ev = Ev(run, view, Scope(ent))
            scope = Scope(ent, None, {name: ev.ref(e) for name, e in decl.inputs.items()})
            claimed = []
            for entry in decl.solve_for:
                if isinstance(entry, Unknown):
                    scope.extra[entry.name] = Res(('local', sol, entry.name))
                    claimed.append(('local', sol, entry.name))
                else:
                    claimed += _targets(Ev(run, view, scope).ref(entry), entry)
            yield sol, decl, scope, claimed


def structure(run):
    """The components of this instant. Flows that share a store are one calculation, and so are
    the unknowns of one declared solver."""
    view = run.view
    sols, owner = list(declarations(run)), {}
    for sol, _, _, claimed in sols:
        for v in claimed:
            if v in owner:
                raise Diagnostic(f'{label(v)} has two writers: {label(owner[v])} and {label(sol)}')
            owner[v] = sol
    parent = {}

    def find(v):
        parent.setdefault(v, v)
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    def union(vs):
        for v in vs[1:]:
            parent[find(v)] = find(vs[0])

    at_store = {}
    for f in view.live:
        find(var_of(f))
        for c in connections(f):
            for cell in (c.src, c.dst):
                if cell is not None:
                    at_store.setdefault(cell, []).append(var_of(f))
    for vs in at_store.values():
        union(vs)
    for _, _, _, claimed in sols:
        for v in claimed:
            find(v)
        union(claimed)
    groups = {}
    for v in parent:
        groups.setdefault(find(v), []).append(v)
    comps = []
    for vs in groups.values():
        flows = sorted((f for f in view.live if var_of(f) in vs), key=lambda f: f.number)
        mine = [s for s in sols if s[3] and s[3][0] in vs]
        if len(mine) > 1:
            raise Diagnostic(
                'two solvers meet in one calculation: '
                + ' and '.join(label(s[0]) for s in mine)
                + '; one solver must own the joint decision'
            )
        cells = {cell for flow in flows for cell in stores_of(flow)}
        faces = frozenset(
            (cell, which)
            for cell in cells
            for which, bound in zip(('lo', 'hi'), view.bounds.get(cell, (None, None)), strict=True)
            if run.on_stock_target(cell, view.cells[cell], bound)
        )
        comps.append(Component(vs, flows, mine, frozenset(label(v) for v in vs), faces))
    comps.sort(key=lambda c: min(sorted(c.key)))
    return comps


def settle(run):
    """Rates and solver results for the state as it stands, as they hold just after the instant (the
    rule of every moment: the rates over the interval after a moment are those of the state just
    after it, whether or not a moment falls there). Each affected calculation is solved once, and
    again where its settings, read with the stores moving as its answer moves them, are not those
    that it was solved with (`_moving`)."""
    comps = structure(run)
    run.components = comps
    run.component_of = {v: c for c in comps for v in c.vars}
    run.solved_cells = {v[1] for c in comps for v in c.vars if v[0] == 'cell'}
    previous, run.view.results = run.view.results, {}
    run.settling = True
    try:
        for comp in comps:
            if not comp.done:
                solve(run, comp)
        _moving(run, comps)
    except (RunFailed, NotCovered):
        run.view.results = previous
        raise
    finally:
        run.settling = None


def _moving(run, comps):
    """Solve again each calculation whose problem, read with the stores moving as the published rates
    move them (a comparison on a store at the closed side of its switch, which the store crosses as it
    moves: `s <= 2 L` while s rises from 2 L), differs from the one that it was solved with, with the
    stores moving, until no problem changes. Where the answers move the stores back across their
    switches, the rates switch back and forth and local sharing has no answer that holds just after
    the moment."""
    view = run.view
    for _ in range(len(comps) + 1):
        try:
            changed, _, _, _ = _trajectories(run, settling=True)
            for comp in changed:
                comp.done = False
            for comp in changed:
                if not comp.done:
                    solve(run, comp)
        finally:
            view.levels, view.rates = {}, {}
        if not changed:
            return
    raise NotCovered(
        'the rates switch back and forth: the answer of '
        + ', '.join(
            c.sols[0][0].label if c.sols else 'the flows ' + ', '.join(f.label for f in c.flows)
            for c in changed
        )
        + ' moves a store back across a switch of its settings'
    )


def pull(run, var):
    """A calculation reads the result of another: that one is solved first."""
    comp = run.component_of.get(var)
    if comp is None or comp.done:
        return
    if comp.busy:
        raise Diagnostic(f'{label(var)} depends on its own solve through another computed result')
    solve(run, comp)


def solve(run, comp):
    """Assemble one component, solve it unless the cache holds the same problem, and publish.

    The answer is the one that holds just after the instant (the rule of every moment: the rates over
    the interval after a moment are those of the state just after it, whether or not a moment falls
    there). So the settings are read as just after it (`_after`: a branch on the time at the closed
    side of its comparison takes its other branch), and a store holds its bound only where the answer
    keeps it there: a store at a bound that the answer moves off is released, and the problem is
    solved again without that bound, until the bounds that it holds stay. This is one rule for local
    sharing and for a declared solver: where a store that local sharing holds at its lower bound
    makes the claims that it supplies wait for its supply, an answer that fills it is no answer just
    after, when it holds stock and they wait no more. Where the answer with a released store free
    moves it back past its bound, no answer holds just after the instant: the run stops by name
    (`NotCovered`, as the engine stops; PLAN, change 10), for local sharing and for a solver. The cache holds the problem that the solve settled on, with its
    answer and its releases: it serves again where the problem is that one, as assembled or with the
    bounds released that the cached answer moves off. The solve is noted once."""
    comp.busy = True
    problem = _after(run, comp)
    answer = _cached(run, comp, problem)
    if answer is None:
        answer = _select(run, comp, problem)
        while True:
            leaving = _moved(problem, answer, _one_bound(problem, comp), inward=True)
            if not leaving:
                break
            before = comp.released
            comp.released = before | leaving
            trial = _after(run, comp)
            found = _select(run, comp, trial)
            back = _moved(trial, found, leaving, inward=False)
            if back:
                cell, which = sorted(back, key=lambda b: label(b[0]))[0]
                who = (
                    f'the solver {label(comp.sols[0][0])} has no answer that holds'
                    if comp.sols
                    else 'local sharing has no rates that hold'
                )
                raise NotCovered(
                    f'{label(cell)}: {who} just after the moment: held at its '
                    f'{"lower" if which == "lo" else "upper"} bound, its sharing moves it off, and free, back '
                    'past it; the rates switch back and forth at its bound'
                )
            problem, answer = trial, found
        run.cache[comp.key] = (problem['signature'], answer)
        comp.signature = problem['signature']
        who = label(comp.sols[0][0]) if comp.sols else 'network'
        run._note('solve', who, origin=comp.sols[0][1].origin if comp.sols else '')
    else:
        comp.signature = run.cache[comp.key][0]  # served again: the problem that it settled on
    run.view.results.update(answer)
    for leg, request in problem['leg_request'].items():
        run.view.results['rate', leg] = answer['frac', leg.flow] * request
    comp.busy, comp.done = False, True


def _after(run, comp):
    """The problem of a component as it holds just after the instant: each setting
    read in the time since the moment (mode 'germ'), at its value as that time starts, so that a
    comparison answers for the instants just after the moment. A request that moves gives its value
    at the moment (`motion` follows it)."""
    ev = Ev(run, run.view, None, mode='germ', unknowns=set(comp.vars))
    return assemble(run, comp, ev, {})


def _cached(run, comp, problem):
    """The cached answer of a component whose problem is the one that it settled on last, as
    assembled or with the bounds released that the cached answer moves off (then released here
    too); else None."""
    cached = run.cache.get(comp.key)
    if cached is None:
        return None
    if cached[0] == problem['signature']:
        return cached[1]
    leaving = _moved(problem, cached[1], _one_bound(problem, comp), inward=True)
    if leaving:
        comp.released = frozenset(leaving)
        if _after(run, comp)['signature'] == cached[0]:
            return cached[1]
        comp.released = frozenset()
    return None


def _select(run, comp, problem):
    """The answer of the selection order for the problem of a component."""
    try:
        return select(
            comp.vars,
            problem['rows'],
            problem['objectives'],
            problem['tiers'],
            problem['prefs'],
            problem['groups'],
        )
    except RunFailed as e:
        who = label(comp.sols[0][0]) if comp.sols else 'the flows ' + ', '.join(f.label for f in comp.flows)
        raise type(e)(f'{e} [{who}, t = {run.view.t} h]') from None


def _one_bound(problem, comp):
    """The bounds (store, 'lo' or 'hi') that a problem holds, of the stores held at one bound only: a
    store held at both balances, and moves neither way."""
    found = set()
    for cell in problem['nets']:
        lo, hi = (_held(cell, which, comp) for which in ('lo', 'hi'))
        if lo != hi:
            found.add((cell, 'lo' if lo else 'hi'))
    return found


def _departs(change, traffic):
    """The owner's strict traffic-relative release, on exact values or their outgoing polynomials."""
    difference = change * 10**12 - traffic
    return difference.sign_after() > 0 if isinstance(difference, Poly) else difference > 0


def _moved(problem, answer, bounds, inward):
    """The bounds of `bounds` whose store the answer moves off (`inward`) or past (not `inward`)."""
    found = set()
    for cell, which in bounds:
        rate = problem['nets'][cell].at(answer)
        off = rate if which == 'lo' else -rate  # positive when the store moves off its bound
        change = off if inward else -off
        if change <= 0:
            continue
        gross = sum(side.at(answer) for side in problem['traffic'][cell])
        # Compare the exact rational rates without an absolute rate floor.
        if _departs(change, gross):
            found.add((cell, which))
    return found


def placement_problems(run, candidates):
    """Incoming hard rows and affected component legs for a candidate physical correction."""
    problems = []
    shared = []
    for comp in run.components:
        relevant = {
            var_of(flow): {leg.label for leg in (flow.legs.values() if flow.kind == 'legs' else (flow,))}
            & candidates
            for flow in comp.flows
        }
        if not any(relevant.values()):
            continue
        problem = _after(run, comp)
        problems.append((comp, problem, set.union(*relevant.values())))
        shared.extend(legs for legs in relevant.values() if len(legs) > 1)
        for row in problem['rows']:
            variables = set(row.lin.c)
            for part in row.lin.parts:
                variables.update(part.c)
            legs = set().union(*(relevant.get(v, ()) for v in variables))
            if len(legs) > 1:
                shared.append(legs)
    return problems, shared


def check_placement(run, problems, end, moving, corrections, *, start=0):
    """Integrate the incoming hard rows over the whole interval or its stock-contact suffix."""
    duration = end - start
    accepted = {}
    for _, _, poly, name in moving:
        primitive = poly.integral()
        accepted[name] = primitive(end) - primitive(start)

    def integrated(lin, values):
        # Unknowns are integrals of the rate or served fraction. Constants accrue
        # only over the admitted duration, including a zero-width contact at its edge.
        return (
            lin.k * duration
            + sum(c * values[v] for v, c in lin.c.items())
            + sum(max(integrated(part, values), 0) for part in lin.parts)
        )

    for comp, problem, candidates in problems:
        affected = candidates & corrections.keys()
        if not affected:
            continue
        answer = {v: x * duration for v, x in run.view.results.items()}
        for flow in comp.flows:
            if flow.kind == 'legs':
                fractions = set()
                for leg in flow.legs.values():
                    amount = accepted.get(leg.label, 0) + corrections.get(leg.label, 0)
                    request = problem['leg_request'][leg]
                    if request:
                        fractions.add(amount / request)
                    elif amount:
                        return RunFailed(f'placement would put flow through closed leg {leg.label}')
                if len(fractions) > 1:
                    return RunFailed(f'placement would split the common served fraction of {flow.label}')
                answer[var_of(flow)] = next(iter(fractions), Fraction(0))
            else:
                answer[var_of(flow)] = accepted.get(flow.label, 0) + corrections.get(flow.label, 0)
        for row in problem['rows']:
            residual = integrated(row.lin, answer)
            if residual > 0 or (row.op == '==' and residual):
                return RunFailed(
                    f'placement at {run.view.t + end} h would break a hard flow condition on '
                    + ', '.join(sorted(affected))
                )
    return None


# --- one calculation as a problem ----------------------------------------------------------------------


def _canon(x):
    return (
        x.k,
        tuple(sorted((label(v), c) for v, c in x.c.items())),
        tuple(sorted(_canon(p) for p in x.parts)),
    )


def _layers(flows, rankings):
    """The priority layer of each flow. `rankings` holds, for each endpoint that ranks its
    connections, its classes (sets of flows) from first to last. A flow is decided after every flow
    that some endpoint ranks ahead of it; flows whose ranks contradict each other (a before b here,
    b before a there) share a layer."""
    ahead = {f: set() for f in flows}
    for classes in rankings:
        for i, cls in enumerate(classes):
            for f in cls:
                for earlier in classes[:i]:
                    ahead[f] |= set(earlier)
    changed = True
    while changed:  # everything that is ahead of something ahead of f is ahead of f
        changed = False
        for f in flows:
            more = set().union(*(ahead[g] for g in ahead[f])) - ahead[f] if ahead[f] else set()
            if more:
                ahead[f] |= more
                changed = True
    layer = {}

    def of(f):
        if f not in layer:
            layer[f] = 1 + max((of(g) for g in ahead[f] if f not in ahead[g]), default=0)
        return layer[f]

    return {f: of(f) for f in flows}


def _held(cell, which, comp):
    """The stock is in this bound's band and the allocation has not released it."""
    return (cell, which) in comp.faces and (cell, which) not in comp.released


def _supply_depths(at_store, comp, shut):
    """The supply depth of a store (None is SOURCE): 0 when it can supply from what it holds, and
    for a store held at its lower bound one more than the deepest store that feeds it through a
    connection that can carry flow (not in `shut`)."""
    depth = {}

    def of(cell, path=()):
        if cell is None or not _held(cell, 'lo', comp):
            return 0
        if cell in path:
            raise NotCovered(
                f'{label(cell)}: a ring of stores at their lower bound passes supply around; the oracle '
                'settles local sharing in the direction of supply'
            )
        if cell not in depth:
            feeders = [c.src for c, _ in at_store[cell]['inflow'] if c not in shut]
            depth[cell] = 1 + max((of(s, (*path, cell)) for s in feeders), default=0)
        return depth[cell]

    return of


def _full(cell, comp):
    """Whether a store is full: held at its upper bound and not at its lower bound."""
    return cell is not None and _held(cell, 'hi', comp) and not _held(cell, 'lo', comp)


def _room_depths(at_store, comp, shut):
    """The room depth of a store (None is SINK). A full store, at its upper bound and not at its
    lower bound, passes on the room that its outflows make through connections that can carry flow
    (not in `shut`): its depth is one more than that of the deepest full store that they fill, and 0
    when they fill none, so that one full store shares on the levels of supply. Any other store is at
    depth 0: a store with room, and a store held at both bounds, which local sharing settles in the
    direction of supply."""
    depth = {}

    def of(cell, path=()):
        if not _full(cell, comp):
            return 0
        if cell in path:
            raise NotCovered(
                f'{label(cell)}: a ring of stores at their upper bound passes room around; the oracle settles '
                'room against the direction of flow'
            )
        if cell not in depth:
            fills = [c.dst for c, _ in at_store[cell]['outflow'] if c not in shut and _full(c.dst, comp)]
            depth[cell] = max((1 + of(d, (*path, cell)) for d in fills), default=0)
        return depth[cell]

    return of


def assemble(run, comp, ev, follow=None):
    """The problem of one component at this instant.

    With an evaluator in mode 'germ' the same code looks just after the instant: a rate input must
    then be constant, except the request of a directed flow, which `follow` receives as a
    polynomial when it moves."""
    view = run.view
    rows, objectives, claims, prefs, rankings = [], [], [], [], []
    flow_targets, other_targets = {}, {}
    decided = {v for _, _, _, claimed in comp.sols for v in claimed}  # what the solver determines
    leg_request = {}
    at_store = {}
    nets = {}  # the net rate of each store, inflow less outflow
    traffic = {}  # the two gross rates at stocks where allocation can decide a departure
    shut = (
        set()
    )  # the connections that cannot carry flow at this instant: a capacity of zero, a leg that asks nothing
    ranked = set()  # the endpoints that rank their connections in more than one class

    def fixed(value, what, flow=None):
        value = plain(value)
        if isinstance(value, Lin):
            raise Diagnostic(f'{what} reads an unknown of the same solve')
        if isinstance(value, Poly):
            if follow is None or flow is None:
                raise NotCovered(f'{what} changes continuously between two moments')
            follow[flow] = value
            return value(0)
        if value is not None and (isinstance(value, bool) or not isinstance(value, Fraction)):
            raise RunFailed(f'{what} must be a number, and is {value!r}')
        return value

    def setting(e, owner, name, flow=None):
        c = Cell(owner, name)
        return fixed(e.setting(c), label(c), flow)

    for f in comp.flows:
        fe = ev.fork(f.scope)
        if f.kind == 'legs':
            x = Lin.var(('frac', f))
            rows += [relation(x, '>=', 0), relation(x, '<=', 1)]
            for one in f.legs.values():
                r = setting(fe, one, 'request') or Fraction(0)
                cap = setting(fe, one, 'capacity')
                if r < 0 or (cap is not None and cap < 0):
                    raise RunFailed(f'{one.label}: a request or a capacity below zero')
                leg_request[one] = r
                if r == 0 or cap == 0:
                    shut.add(one)
                if cap is not None:
                    rows.append(relation(x * r, '<=', cap))
            asks = any(leg_request[one] > 0 for one in f.legs.values())
            if asks:
                claims.append((f, x, Fraction(1), connections(f), var_of(f) in decided))
            else:
                rows.append(relation(x, '==', 0))  # every leg asks for nothing: the fraction is zero
            flow_targets['frac', f] = (Fraction(1 if asks else 0), Fraction(1))
        else:
            x = Lin.var(('rate', f))
            cap = setting(fe, f, 'capacity')
            req = setting(fe, f, 'request', f if f.kind == 'directed' else None) or Fraction(0)
            if cap is not None and cap < 0:
                raise RunFailed(f'{f.label}: a capacity below zero')
            if cap == 0:
                shut.update(connections(f))
            if f.kind == 'directed':
                if req < 0:
                    raise RunFailed(f'{f.label}: a request below zero')
                rows.append(relation(x, '>=', 0))
                if cap is not None:
                    rows.append(relation(x, '<=', cap))
                if req > 0:
                    claims.append((f, x, req, [f], var_of(f) in decided))
            else:
                if cap is not None:
                    rows += [relation(x, '<=', cap), relation(x, '>=', -cap)]
                if req != 0:  # the signed request names the direction of the one claim
                    claims.append((f, x if req > 0 else -x, abs(req), connections(f), var_of(f) in decided))
            # Every number is in the canonical unit of its dimension, so one canonical unit is 1.
            flow_targets['rate', f] = (req, Fraction(1))
        for c in connections(f):
            for side, cell in (('outflow', c.src), ('inflow', c.dst)):
                if cell is not None:
                    at_store.setdefault(cell, {'outflow': [], 'inflow': []})[side].append((c, f))

    def term(c, f):
        """The nonnegative rate of one connection."""
        if f.kind == 'directed':
            return Lin.var(('rate', f))
        if f.kind == 'legs':
            return Lin.var(('frac', f)) * leg_request[c]
        x = Lin.var(('rate', f))
        return (x if c.name == 'forward' else -x).positive()

    def signed(c, f):
        """The same rate with its sign kept: a reversible flow counts once, on its forward leg."""
        if f.kind == 'reversible':
            return Lin.var(('rate', f)) if c.name == 'forward' else Lin()
        return term(c, f)

    for cell, sides in at_store.items():  # an endpoint of capacity zero closes its connections
        owner_ev = ev.fork(run.scope_of(cell.owner))
        for side in ('outflow', 'inflow'):
            if setting(owner_ev, End(cell, side), 'capacity') == 0:
                shut.update(c for c, _ in sides[side])
    for cell, sides in at_store.items():
        level = view.cells[cell]
        lo, hi = view.bounds.get(cell, (None, None))
        if (lo is not None and level < lo and (cell, 'lo') not in comp.faces) or (
            hi is not None and level > hi and (cell, 'hi') not in comp.faces
        ):
            raise RunFailed(f'{label(cell)} holds {level}, outside its range [{lo}, {hi}]')
        net = sum((signed(c, f) for c, f in sides['inflow']), Lin()) - sum(
            (signed(c, f) for c, f in sides['outflow']), Lin()
        )
        nets[cell] = net
        if _held(cell, 'lo', comp):
            rows.append(relation(net, '>=', 0))  # at its lower bound: what leaves must also arrive
        if _held(cell, 'hi', comp):
            rows.append(relation(net, '<=', 0))  # at its upper bound: what arrives must also leave
        owner_ev = ev.fork(run.scope_of(cell.owner))
        for side in ('outflow', 'inflow'):
            end = End(cell, side)
            here = sides[side]
            total = sum((term(c, f) for c, f in here), Lin())
            if (cell, 'lo') in comp.faces or (cell, 'hi') in comp.faces:
                traffic.setdefault(cell, []).append(total)
            cap = setting(owner_ev, end, 'capacity')
            req = setting(owner_ev, end, 'request') or Fraction(0)
            if cap is not None:
                rows.append(relation(total, '<=', cap))
            if req > 0:
                if total.parts:
                    raise NotCovered(f'{label(end)}.request with a reversible flow at that endpoint')
                # the solver's where it determines every connection of the endpoint that can carry flow
                mine = all(var_of(f) in decided for c, f in here if c not in shut)
                claims.append((end, total, req, [c for c, _ in here], mine))
            alloc = owner_ev.setting(Cell(end, 'allocation'))
            if alloc is not None and alloc.classes:
                present = dict(here)
                for cls in alloc.classes:
                    for c in cls:
                        if not isinstance(c, (FlowRT, LegRT)) or (c not in present and _live(view, c)):
                            raise Diagnostic(
                                f'priority(...) at {label(end)} names {label(c)}, which is not a connection '
                                'of that endpoint; name the leg of that direction'
                            )
                # A connection that cannot carry flow is not eligible, and ranks nothing.
                listed = [tuple(c for c in cls if c in present and c not in shut) for cls in alloc.classes]
                rest = tuple(c for c, _ in here if c not in shut and not any(c in cls for cls in listed))
                classes = [cls for cls in listed if cls] + ([rest] if rest else [])
                rankings.append([{present[c] for c in cls} for cls in classes])
                if len(classes) > 1:
                    ranked.add(end)
                if req > 0:  # the preferred routes carry the aggregate request first
                    carried = Lin()
                    for cls in classes[:-1]:
                        carried = carried + sum((term(c, present[c]) for c in cls), Lin())
                        prefs.append((carried, req))

    for sol, decl, scope, claimed in comp.sols:
        se = ev.fork(scope)

        def scale(declared, lo, hi):
            if declared is not None:
                return fixed(se.val(declared), 'a scale')
            return hi - lo if lo is not None and hi is not None and hi > lo else Fraction(1)

        for entry in decl.solve_for:
            if isinstance(entry, Unknown):
                var = ('local', sol, entry.name)
                lo = fixed(se.val(entry.lo), f'the range of {entry.name}') if entry.lo is not None else None
                hi = fixed(se.val(entry.hi), f'the range of {entry.name}') if entry.hi is not None else None
                if lo is not None and hi is not None and lo > hi:
                    floor = (
                        abs(fixed(se.val(entry.scale), 'a scale'))
                        if entry.scale is not None
                        else entry.unit_size
                    )
                    band = max(run.config.atol_factor, run.config.rtol) * max(floor, abs(lo), abs(hi))
                    if lo - hi <= band:
                        lo = hi = (lo + hi) / 2
                if lo is not None and hi == lo:
                    rows.append(relation(Lin.var(var), '==', lo))
                else:
                    rows += [relation(Lin.var(var), '>=', lo)] if lo is not None else []
                    rows += [relation(Lin.var(var), '<=', hi)] if hi is not None else []
                init = entry.init
                target = (
                    fixed(se.val(init), f'the initializer of {entry.name}')
                    if init is not None
                    else Fraction(0)
                )
                other_targets[var] = (target, scale(entry.scale, lo, hi))
        for var in claimed:
            if var[0] == 'cell':
                lo, hi = view.bounds.get(var[1], (None, None))
                if lo is not None and hi == lo:
                    rows.append(relation(Lin.var(var), '==', lo))
                else:
                    rows += [relation(Lin.var(var), '>=', lo)] if lo is not None else []
                    rows += [relation(Lin.var(var), '<=', hi)] if hi is not None else []
                declared = run.fields.get(var[1])
                other_targets[var] = (view.cells[var[1]], scale(declared.scale if declared else None, lo, hi))
        for c in decl.constraints:
            found = _rows(se.val(c))
            for rel in found:
                _refuse_undecided(sol, rel.lin, decided, show(c))
            rows += found
        for sense, e in decl.objective:
            v = se.val(e)
            if isinstance(v, Lin):
                _refuse_undecided(sol, v, decided, show(e))
                objectives.append((v if sense == 'min' else -v, show(e)))

    # The endpoints' rules rank every claim, and the solver's own sharing acts only among the claims
    # that they leave equal (the owner's rule after G2, `_places`).
    tiers = {}
    layer = _layers(comp.flows, rankings)
    places = _places(at_store, comp, claims, shut, ranked, layer)
    for (_, amount, r, _, _), place in zip(claims, places):
        tiers.setdefault(place, []).append((amount, r))
    tiers = [tiers[k] for k in sorted(tiers)]
    signature = (
        tuple(sorted((leg.label, request) for leg, request in leg_request.items())),
        tuple(sorted((r.op, _canon(r.lin)) for r in rows)),
        tuple(_canon(o) for o, _ in objectives),
        tuple(tuple(sorted((_canon(a), r) for a, r in tier)) for tier in tiers),
        tuple((_canon(a), r) for a, r in prefs),
        tuple(sorted((label(v), x) for v, x in {**flow_targets, **other_targets}.items())),
    )
    return {
        'rows': rows,
        'objectives': objectives,
        'tiers': tiers,
        'prefs': prefs,
        'groups': [flow_targets, other_targets],
        'signature': signature,
        'leg_request': leg_request,
        'nets': nets,
        'traffic': traffic,
    }


def _levels(at_store, comp, shut):
    """How a claim is placed in the order of local sharing: a function of the connections that
    serve it, the largest of the supply depth of the stores that they draw from and the room depth
    of the stores that they fill. A depth is found only for a claim that asks for it."""
    supply, room = _supply_depths(at_store, comp, shut), _room_depths(at_store, comp, shut)
    return lambda conns: max((max(supply(c.src), room(c.dst)) for c in conns), default=0)


def _places(at_store, comp, claims, shut, ranked, layer):
    """The place of each claim in the order, as (level, layer) (the owner's rule after G2: an
    endpoint's rule ranks every claim of its flows, named or not, and the solver's own sharing acts
    only among the claims that the endpoints' rules leave equal).

    Two claims that rank at one endpoint are linked, and so are the claims that a chain of such links
    joins. Where a chain holds a claim that the solver does not determine, each of its claims keeps
    its place of local sharing: its level (`_levels`) and its layer. The other claims are the
    solver's: a claim waits for the decisions of local sharing that its stores' supply and room come
    through, as there, and not for the solver's own connections, which pass the level of what they
    carry on, except where an endpoint ranks one of them: there what it serves waits, as in local
    sharing. The stores of a ring of the solver's connections share one level: the solver decides the
    ring together. A claim reads all this through its connections that can carry flow; one that has
    none is served nothing, and takes the first place."""
    local = _levels(at_store, comp, shut)
    supply = _supply_depths(at_store, comp, shut)
    room = _room_depths(at_store, comp, shut)

    def ends(node, conns):
        if isinstance(node, End):
            return {node}
        found = {End(c.src, 'outflow') for c in conns if c.src is not None}
        return found | {End(c.dst, 'inflow') for c in conns if c.dst is not None}

    chain = {}  # each endpoint, and each claim, to the chain that holds it

    def root(x):
        while chain.get(x, x) != x:
            x = chain[x]
        return x

    # A claim reads the structure through its connections that can carry flow; one that has none is
    # served nothing, takes the first place and links nothing.
    open_ = [[c for c in conns if c not in shut] for _, _, _, conns, _ in claims]
    live = [bool(mine) for mine in open_]
    for k, (node, _, _, _, _) in enumerate(claims):
        for end in ends(node, open_[k]) if live[k] else ():
            chain[root(('claim', k))] = root(end)
    undecided = {root(('claim', k)) for k, claim in enumerate(claims) if live[k] and not claim[4]}
    keeps = [root(('claim', k)) in undecided for k in range(len(claims))]
    held = {
        end for k, (node, *_) in enumerate(claims) if keeps[k] and live[k] for end in ends(node, open_[k])
    }

    def own(c):
        """None where local sharing decides what connection c passes; else whether it is ranked."""
        mine = ends(None, [c])
        return None if mine & held else bool(mine & ranked)

    def passing(active, inputs):
        """The level of each active store: the largest of its inputs, a store's level plus a step or
        a value; the stores of a ring share the largest of the inputs from outside it."""
        cells = [cell for cell in at_store if active(cell)]
        onward = {
            cell: [item for kind, item, _ in inputs(cell) if kind == 'store' and active(item)]
            for cell in cells
        }
        reach = {}
        for cell in cells:
            seen, stack = set(), [cell]
            while stack:
                for item in onward[stack.pop()]:
                    if item not in seen:
                        seen.add(item)
                        stack.append(item)
            reach[cell] = seen
        ring = {cell: {cell} | {other for other in reach[cell] if cell in reach[other]} for cell in cells}
        level = {}
        for _ in range(len(cells) + 1):  # the rings form no cycle, so this ends
            changed = False
            for cell in cells:
                best = 0
                for member in ring[cell]:
                    for kind, item, step in inputs(member):
                        if kind == 'value':
                            best = max(best, item + step)
                        elif not (active(item) and item in ring[cell]):
                            best = max(best, (level.get(item, 0) if active(item) else 0) + step)
                if best != level.get(cell, 0):
                    level[cell], changed = best, True
            if not changed:
                break
        return lambda cell: level.get(cell, 0) if cell is not None and active(cell) else 0

    def feeds(cell):
        for c, _ in at_store[cell]['inflow']:
            if c in shut:
                continue
            mine = own(c)
            yield ('value', supply(c.src) + 1, 0) if mine is None else ('store', c.src, int(mine))

    def drains(cell):
        for c, _ in at_store[cell]['outflow']:
            if c in shut:
                continue
            mine, step = own(c), int(_full(c.dst, comp))
            if mine is None:
                yield ('value', room(c.dst) + 1 if step else 0, 0)
            elif step:
                yield ('store', c.dst, int(mine))

    def kept(k):
        return local(open_[k]) if live[k] else 0

    if all(keeps[k] or not live[k] for k in range(len(claims))):
        return [(kept(k), layer.get(node, 1)) for k, (node, *_) in enumerate(claims)]
    passed_supply = passing(lambda cell: cell is not None and _held(cell, 'lo', comp), feeds)
    passed_room = passing(lambda cell: _full(cell, comp), drains)
    return [
        (
            kept(k)
            if keeps[k] or not live[k]
            else max(max(passed_supply(c.src), passed_room(c.dst)) for c in open_[k]),
            layer.get(node, 1),
        )
        for k, (node, *_) in enumerate(claims)
    ]


def _refuse_undecided(sol, value, decided, text):
    """A relation or an objective of a solver that reads the rate of a flow of its calculation that
    it does not determine is refused: such a flow keeps the local sharing of its endpoints."""
    for v in value.c:
        if v[0] in ('rate', 'frac') and v not in decided:
            raise Diagnostic(
                f'{label(sol)}: {text} reads {label(v)}, which the solver does not determine; a flow '
                'that a solver does not name keeps the local sharing of its endpoints: name it in '
                'solve_for to decide it'
            )
    for part in value.parts:
        _refuse_undecided(sol, part, decided, text)


def _live(view, c):
    return (c.flow if isinstance(c, LegRT) else c) in view.live


def _rises(comp, f, request):
    """A flow at rate zero whose moving request is zero at this moment and positive just after, as
    `t * 1 L/h/h` at 0 h or `since(e) * 1 L/h/h` when e starts: it follows its request (D3) unless
    an end of it is a store held at the bound that the flow would leave, which the flow cannot
    start to move by itself; such a flow, and one whose rate is zero below a positive request, is
    held at zero, starved."""
    return (
        request(0) == 0
        and request.sign_after() > 0
        and (f.src, 'lo') not in comp.faces
        and (f.dst, 'hi') not in comp.faces
    )


# --- between two moments -----------------------------------------------------------------------------


def _carried(run, follow=None):
    """The motion after this moment of the published rates. Give the level of each moving store,
    the rate of each flow that follows a moving request, the transfers for the ledger, and those
    requests. The first look reads requests with stores held still. Later looks use the supplied
    polynomials."""
    view = run.view
    if follow is None:
        follow = {}
        for comp in run.components:
            assemble(run, comp, Ev(run, view, None, mode='germ', unknowns=set(comp.vars)), follow)
    net, moving, rates = {}, [], {}

    def carry(src, dst, p, name):
        if p.c != (0,):
            moving.append((src, dst, p, name))
            for cell, q in ((src, -p), (dst, p)):
                if cell is not None:
                    net[cell] = net.get(cell, Poly([0])) + q

    for f in view.live:
        if f.kind == 'legs':
            for one in f.legs.values():
                carry(one.src, one.dst, Poly([view.results['rate', one]]), one.label)
            continue
        rate = view.results.get(('rate', f), Fraction(0))
        p = follow.get(f)
        if p is not None and (
            rate != 0 or _rises(run.component_of[var_of(f)], f, p)
        ):  # the flow follows a moving request
            ends = [(c, s) for c, s in ((f.src, 'outflow'), (f.dst, 'inflow')) if c is not None]
            free = (
                not run.component_of['rate', f].sols
                and view.cells.get(Cell(f, 'capacity')) is None
                and rate == p(0)
                and all(
                    view.cells.get(Cell(End(c, s), k)) is None
                    for c, s in ends
                    for k in ('capacity', 'request')
                )
            )
            if not free:
                raise NotCovered(
                    f'{f.label}: a request that changes continuously on a flow that something limits'
                )
            rates['rate', f] = p
        else:
            p = Poly([rate])
        carry(f.src, f.dst, p, f.label)
    levels = {cell: Poly([view.cells[cell]]) + p.integral() for cell, p in net.items() if p.c != (0,)}
    # A held stock still books each physical leg. Its small net is not a
    # departure when comparing branches. A genuinely rising curved inflow
    # without opposing traffic, including one that is zero now, can depart.
    held = {c for comp in run.components for c, face in comp.faces - comp.released if c in levels}
    view.held_drifts = set()
    if held:
        traffic = {c: Poly([0]) for c in held}
        for src, dst, rate, _ in moving:
            amount = -rate if rate.sign_after() < 0 else rate
            for c in (src, dst):
                if c in held:
                    traffic[c] = traffic[c] + amount
        for c in held:
            speed = -net[c] if net[c].sign_after() < 0 else net[c]
            if not _departs(speed, traffic[c]):
                direction = net[c].sign_after()
                for bound in view.bounds[c]:
                    if run.on_stock_target(c, view.cells[c], bound):
                        edge = run.stock_band_edge(c, bound, direction)
                        if ((levels[c] - edge) * direction).sign_after() < 0:
                            view.held_drifts.add(c)
    return levels, rates, moving, follow


def _trajectories(run, *, settling):
    """Propagate polynomial requests, rates and store levels over the incoming dependencies.

    The problems immediately after a contact depend on these same trajectories as the
    contact search. A first pass can see the clock's rate but still hold a store-driven
    or downstream rate constant. Only the converged pass can choose an outgoing branch.
    """
    view = run.view
    view.levels, view.rates = {}, {}
    view.levels, view.rates, moving, follow = _carried(run)
    if settling and not (view.levels or view.rates):
        return [], moving, [], []
    for depth in range(len(view.live) + 1):
        changed, stops, contacts, again = [], [], [], {}
        for comp in run.components:
            ev = Ev(run, view, None, mode='germ', unknowns=set(comp.vars))
            problem = assemble(run, comp, ev, again)
            if settling and problem['signature'] != comp.signature:
                changed.append(comp)
            stops += ev.shared.stops
            contacts.extend(ev.shared.contacts)
        difference = next(
            (
                f
                for f in view.live
                if (f in again) != (f in follow) or (f in again and again[f].c != follow[f].c)
            ),
            None,
        )
        if difference is None:
            return changed, moving, stops, contacts
        if depth == len(view.live):
            raise NotCovered(
                f'{difference.label}: a request that reads a store while that store moves in a feedback loop'
            )
        view.levels, view.rates, moving, follow = _carried(run, again)


def motion(run):
    """Set the exact store and rate trajectories and find their first setting and bound contacts."""
    view = run.view
    _, moving, stops, contacts = _trajectories(run, settling=False)
    run.bound_contacts = []
    for cell, p in view.levels.items():
        lo, hi = view.bounds.get(cell, (None, None))
        for bound, outward in ((lo, -1), (hi, 1)):
            if bound is None:
                continue
            gap = p - bound
            if cell in view.held_drifts and run.on_stock_target(cell, view.cells[cell], bound):
                # An accumulated physical net can end this allocation regime even
                # though no single instantaneous rate was large enough to release it.
                for direction in (-1, 1):
                    edge = run.stock_band_edge(cell, bound, direction)
                    reached = (p - edge).first_root()
                    if reached is not None:
                        stops.append(reached)
            if gap.c[0] == 0 and gap.sign_after() == outward:
                raise NotCovered(
                    f'{label(cell)} would leave its range: a rate that moves while its store is on a bound'
                )
            root = gap.first_root()
            if root is not None:
                stops.append(root)
                run.bound_contacts.append((root, cell, bound))
    run.moving = moving
    run.switch_contacts = contacts
    return stops
