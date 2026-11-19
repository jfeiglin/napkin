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
junction of B and C, the first junction splits 1/2 and 1/2 and the second 1/4 and 1/4. Inside one
level the fair-sharing rank of the selection order applies. A declared solver shares across all of
its claims: they stand on one level, and A, B and C then receive 1/3 each.

`motion` gives the level of each store and the rate of each flow as polynomials in the time after
the moment, and the times at which a rate input or a store bound asks for a new settlement.
"""

from dataclasses import dataclass, field
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
    key: frozenset = None
    deps: set = field(default_factory=set)
    busy: bool = False
    done: bool = False


def var_of(flow):
    """The one independent unknown of a flow: its rate, or the served fraction of a flow with legs."""
    return ('frac' if flow.kind == 'legs' else 'rate', flow)


def connections(flow):
    """The connections of a flow: its legs (a reversible flow has two), or itself."""
    return list(flow.legs.values()) if flow.legs else [flow]


def stores_of(flow):
    """The modeled stores at the ends of a flow's connections."""
    return {cell for c in connections(flow) for cell in (c.src, c.dst) if cell is not None}


def incident(view, end):
    """The connections of `store.outflow` or `store.inflow` that are present, in creation order."""
    found = []
    for f in view.live:
        for c in connections(f):
            if (c.src if end.side == 'outflow' else c.dst) == end.cell:
                found.append((c, f))
    return sorted(found, key=lambda p: p[0].number)


# --- the structure of an instant ---------------------------------------------------------------------


def _targets(x, entry):
    if isinstance(x, Res):
        return [x.var]
    if isinstance(x, Cell):
        return [('cell', x)]
    if isinstance(x, Coll):
        return [v for _, _, item in x.items for v in _targets(item, entry)]
    raise Diagnostic(f'solve_for {show(entry)}: not a rate, a served fraction or a stored field')


def structure(run):
    """The components of this instant. Flows that share a store are one calculation, and so are
    the unknowns of one declared solver."""
    view = run.view
    sols, owner = [], {}
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
            for v in claimed:
                if v in owner:
                    raise Diagnostic(f'{label(v)} has two writers: {label(owner[v])} and {label(sol)}')
                owner[v] = sol
            sols.append((sol, decl, scope, claimed))
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
        comps.append(Component(vs, flows, mine, frozenset(label(v) for v in vs)))
    comps.sort(key=lambda c: min(sorted(c.key)))
    return comps


def settle(run):
    """Rates and solver results for the state as it stands. Each affected calculation is solved once."""
    comps = structure(run)
    run.components = comps
    run.component_of = {v: c for c in comps for v in c.vars}
    run.solved_cells = {v[1] for c in comps for v in c.vars if v[0] == 'cell'}
    run.settling = True
    try:
        for comp in comps:
            if not comp.done:
                solve(run, comp)
    finally:
        run.settling = None


def pull(run, var):
    """A calculation reads the result of another: that one is solved first."""
    comp = run.component_of.get(var)
    if comp is None or comp.done:
        return
    if comp.busy:
        raise Diagnostic(f'{label(var)} depends on its own solve through another computed result')
    solve(run, comp)


def solve(run, comp):
    """Assemble one component, solve it unless the cache holds the same problem, and publish."""
    comp.busy = True
    ev = Ev(run, run.view, None, unknowns=set(comp.vars))
    problem = assemble(run, comp, ev)
    comp.deps = set(ev.shared.reads) | problem['stores']
    for var in ev.shared.results:  # a result of another calculation brings that calculation's inputs
        other = run.component_of.get(var)
        if other is not None and other is not comp:
            comp.deps |= other.deps
    cached = run.cache.get(comp.key)
    if cached is not None and cached[0] == problem['signature']:
        answer = cached[1]
    else:
        try:
            answer = select(
                comp.vars,
                problem['rows'],
                problem['objectives'],
                problem['tiers'],
                problem['prefs'],
                problem['groups'],
            )
        except RunFailed as e:
            who = (
                label(comp.sols[0][0]) if comp.sols else 'the flows ' + ', '.join(f.label for f in comp.flows)
            )
            raise type(e)(f'{e} [{who}, t = {run.view.t} h]') from None
        run.cache[comp.key] = (problem['signature'], answer)
        who = label(comp.sols[0][0]) if comp.sols else 'network'
        run._note('solve', who, origin=comp.sols[0][1].origin if comp.sols else '')
    for var, value in answer.items():
        run.view.results[var] = value
    comp.busy, comp.done = False, True


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


def _at_bound(view, cell, which):
    lo, hi = view.bounds.get(cell, (None, None))
    bound = lo if which == 'lo' else hi
    return bound is not None and view.cells[cell] == bound


def _supply_depths(view, at_store):
    """The supply depth of a store (None is SOURCE): 0 when it can supply from what it holds, and
    for a store at its lower bound one more than the deepest store that feeds it."""
    depth = {}

    def of(cell, path=()):
        if cell is None or not _at_bound(view, cell, 'lo'):
            return 0
        if cell in path:
            raise NotCovered(
                f'{label(cell)}: a ring of stores at their lower bound passes supply around; the oracle '
                'settles local sharing in the direction of supply'
            )
        if cell not in depth:
            feeders = [c.src for c, _ in at_store[cell]['inflow']]
            depth[cell] = 1 + max((of(s, (*path, cell)) for s in feeders), default=0)
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
    leg_request = {}
    at_store = {}

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
                if cap is not None:
                    rows.append(relation(x * r, '<=', cap))
            asks = any(leg_request[one] > 0 for one in f.legs.values())
            if asks:
                claims.append((f, x, Fraction(1), connections(f)))
            else:
                rows.append(relation(x, '==', 0))  # every leg asks for nothing: the fraction is zero
            flow_targets['frac', f] = (Fraction(1 if asks else 0), Fraction(1))
        else:
            x = Lin.var(('rate', f))
            cap = setting(fe, f, 'capacity')
            req = setting(fe, f, 'request', f if f.kind == 'directed' else None) or Fraction(0)
            if cap is not None and cap < 0:
                raise RunFailed(f'{f.label}: a capacity below zero')
            if f.kind == 'directed':
                if req < 0:
                    raise RunFailed(f'{f.label}: a request below zero')
                rows.append(relation(x, '>=', 0))
                if cap is not None:
                    rows.append(relation(x, '<=', cap))
                if req > 0:
                    claims.append((f, x, req, [f]))
            else:
                if cap is not None:
                    rows += [relation(x, '<=', cap), relation(x, '>=', -cap)]
                if req != 0:  # the signed request names the direction of the one claim
                    claims.append((f, x if req > 0 else -x, abs(req), connections(f)))
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

    for cell, sides in at_store.items():
        level = view.cells[cell]
        lo, hi = view.bounds.get(cell, (None, None))
        if (lo is not None and level < lo) or (hi is not None and level > hi):
            raise RunFailed(f'{label(cell)} holds {level}, outside its range [{lo}, {hi}]')
        net = sum((signed(c, f) for c, f in sides['inflow']), Lin()) - sum(
            (signed(c, f) for c, f in sides['outflow']), Lin()
        )
        if lo is not None and level == lo:
            rows.append(relation(net, '>=', 0))  # at its lower bound: what leaves must also arrive
        if hi is not None and level == hi:
            rows.append(relation(net, '<=', 0))  # at its upper bound: what arrives must also leave
        owner_ev = ev.fork(run.scope_of(cell.owner))
        for side in ('outflow', 'inflow'):
            end = End(cell, side)
            here = sides[side]
            total = sum((term(c, f) for c, f in here), Lin())
            cap = setting(owner_ev, end, 'capacity')
            req = setting(owner_ev, end, 'request') or Fraction(0)
            if cap is not None:
                rows.append(relation(total, '<=', cap))
            if req > 0:
                if total.parts:
                    raise NotCovered(f'{label(end)}.request with a reversible flow at that endpoint')
                claims.append((end, total, req, [c for c, _ in here]))
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
                listed = [tuple(c for c in cls if c in present) for cls in alloc.classes]
                rest = tuple(c for c, _ in here if not any(c in cls for cls in listed))
                classes = [cls for cls in listed if cls] + ([rest] if rest else [])
                rankings.append([{present[c] for c in cls} for cls in classes])
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
                rows += [relation(Lin.var(var), '>=', lo)] if lo is not None else []
                rows += [relation(Lin.var(var), '<=', hi)] if hi is not None else []
                declared = run.fields.get(var[1])
                other_targets[var] = (view.cells[var[1]], scale(declared.scale if declared else None, lo, hi))
        for c in decl.constraints:
            rows += _rows(se.val(c))
        for sense, e in decl.objective:
            v = se.val(e)
            if isinstance(v, Lin):
                objectives.append((v if sense == 'min' else -v, show(e)))

    tiers = {}
    layer = _layers(comp.flows, rankings)
    level = _levels(view, comp, claims, at_store)
    for node, amount, r, conns in claims:
        tiers.setdefault((level(conns), layer.get(node, 1)), []).append((amount, r))
    tiers = [tiers[k] for k in sorted(tiers)]
    signature = (
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
        'stores': set(at_store),
    }


def _levels(view, comp, claims, at_store):
    """How a claim is placed in the order of local sharing: a function of the connections that
    serve it. A declared solver puts all of its claims on one level."""
    if comp.sols or not claims:
        return lambda conns: 0
    for cell, sides in at_store.items():
        # A full store passes room upstream: the oracle does not follow room through two of them.
        if _at_bound(view, cell, 'hi') and not _at_bound(view, cell, 'lo'):
            for c, _ in sides['outflow']:
                if c.dst is not None and _at_bound(view, c.dst, 'hi'):
                    raise NotCovered(
                        f'{label(cell)} and {label(c.dst)}: room passed upstream through two full stores; '
                        'the oracle settles local sharing in the direction of supply'
                    )
    depth = _supply_depths(view, at_store)
    return lambda conns: max(depth(c.src) for c in conns) if conns else 0


def _live(view, c):
    return (c.flow if isinstance(c, LegRT) else c) in view.live


def _rises(view, f, request):
    """A flow at rate zero whose moving request is zero at this moment and positive just after, as
    `t * 1 L/h/h` at 0 h or `since(e) * 1 L/h/h` when e starts: it follows its request (D3) unless
    an end of it is a store held at the bound that the flow would leave, which the flow cannot
    start to move by itself; such a flow, and one whose rate is zero below a positive request, is
    held at zero, starved."""
    return (
        request(0) == 0
        and request.sign_after() > 0
        and not (f.src is not None and _at_bound(view, f.src, 'lo'))
        and not (f.dst is not None and _at_bound(view, f.dst, 'hi'))
    )


# --- between two moments -----------------------------------------------------------------------------


def motion(run):
    """Set `view.levels` and `view.rates` for the time after this moment, and return the stops:
    the times (after the moment) at which a rate input changes or a store meets a bound."""
    view = run.view
    view.levels, view.rates = {}, {}
    follow = {}
    for comp in run.components:  # first look: which requests move, with every store held still
        assemble(run, comp, Ev(run, view, None, mode='germ', unknowns=set(comp.vars)), follow)
    net, moving = {}, []

    def carry(src, dst, p, name):
        if p.c != (0,):
            moving.append((src, dst, p, name))
            for cell, q in ((src, -p), (dst, p)):
                if cell is not None:
                    net[cell] = net.get(cell, Poly([0])) + q

    here = Ev(run, view, None)
    for f in view.live:
        if f.kind == 'legs':
            fraction = view.results.get(('frac', f), Fraction(0))
            for one in f.legs.values():
                carry(
                    one.src,
                    one.dst,
                    Poly([fraction * here.fork(f.scope).cell(Cell(one, 'request'))]),
                    one.label,
                )
            continue
        rate = view.results.get(('rate', f), Fraction(0))
        p = follow.get(f)
        if p is not None and (rate != 0 or _rises(view, f, p)):  # the flow follows a moving request
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
            view.rates['rate', f] = p
        else:
            p = Poly([rate])
        carry(f.src, f.dst, p, f.label)
    for cell, p in net.items():
        if p.c != (0,):
            view.levels[cell] = Poly([view.cells[cell]]) + p.integral()
    stops = []
    for comp in run.components:  # second look, with the stores moving: nothing else may move
        again = {}
        ev = Ev(run, view, None, mode='germ', unknowns=set(comp.vars))
        assemble(run, comp, ev, again)
        stops += ev.shared.stops
        for f in comp.flows:
            if (again.get(f) is None) != (follow.get(f) is None) or (
                f in again and again[f].c != follow[f].c
            ):
                raise NotCovered(f'{f.label}: a request that reads a store while that store moves')
    for cell, p in view.levels.items():
        lo, hi = view.bounds.get(cell, (None, None))
        for bound, outward in ((lo, -1), (hi, 1)):
            if bound is None:
                continue
            gap = p - bound
            if gap.c[0] == 0 and gap.sign_after() == outward:
                raise NotCovered(
                    f'{label(cell)} would leave its range: a rate that moves while its store is on a bound'
                )
            root = gap.first_root()
            if root is not None:
                stops.append(root)
    run.moving = moving
    return stops
