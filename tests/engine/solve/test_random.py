"""Seeded random problems against references that share no code with the library.

1. The whole selection order on tiny problems with small rational data, against the exact
   reference of `exact.py` (rational simplex, brute-force fair sharing, Fourier-Motzkin projection
   and the enumeration of active sets).
2. The distance step alone, with `==`, `<=` and `>=` rows, open and closed bounds and unequal
   scales, against the exact nearest point.
3. Fair sharing after a total-shortfall objective on small route-and-level networks, with shortage
   and closed routes, against brute force: linprog's `max t`, then one program for each pending
   claim, on the optimal face given as a row.

A held claim keeps its level to 1e-7 of its request (`fair.FIX`), so an answer that follows from
fair sharing is compared within 1e-5 of the sizes of its problem.
"""

from fractions import Fraction

import numpy as np
import pytest
import scipy.sparse as sp
from scipy.optimize import linprog

from napkin.engine.solve import FLOW, INTERNAL, OTHER, Problem, Solver

from . import exact

F = Fraction


def rational(rng, low, high, halves=True):
    """A random number in [low, high] in halves."""
    return F(int(rng.integers(2 * low, 2 * high + 1)), 2) if halves else F(int(rng.integers(low, high + 1)))


def tiny(rng):
    """A tiny problem with small rational data: 1 to 3 flows, at most one other unknown, 1 to 2 rows
    through a point of the boxes, up to two objectives (one of them a positive part), and claims on
    the flows in one or two tiers."""
    flows, others = int(rng.integers(1, 4)), int(rng.integers(0, 2))
    n = flows + others
    boxes, target, scale, kind = [], [], [], []
    for j in range(n):
        lower = rational(rng, -2, 0) if rng.random() < 0.3 else F(0)
        upper = lower + rational(rng, 1, 6)
        boxes.append((lower, upper))
        target.append(rational(rng, 0, 6) if j < flows else rational(rng, -1, 1))
        scale.append(F(int(rng.choice([1, 2]))))
        kind.append(FLOW if j < flows else OTHER)
    point = [lower + (upper - lower) * F(int(rng.integers(1, 4)), 4) for lower, upper in boxes]
    rows = []
    for _ in range(int(rng.integers(1, 3))):
        a = [F(int(v)) for v in rng.integers(-2, 3, n)]
        if not any(a):
            a[0] = F(1)
        value = sum(x * y for x, y in zip(a, point))
        sense = rng.choice(['<=', '==', '>='])
        rows.append((a, str(sense), value + {'<=': 1, '==': 0, '>=': -1}[str(sense)] * rational(rng, 0, 2)))
    objectives, parts = [], []
    if rng.random() < 0.5:
        objectives.append([F(int(v)) for v in rng.integers(-1, 2, flows)] + [F(0)] * others)
    if rng.random() < 0.5:
        j = int(rng.integers(flows))
        parts.append((j, max(F(1), target[j])))  # max(0, request - rate) of flow j
    claims = []
    for j in range(flows):
        if target[j] > 0 and rng.random() < 0.8:
            claims.append((j, target[j], int(rng.integers(0, 2))))
    return dict(n=n, flows=flows, boxes=boxes, target=target, scale=scale, kind=kind, rows=rows,
                objectives=objectives, parts=parts, claims=claims)  # fmt: skip


def library(spec):
    p = Problem()
    columns = [
        p.unknown(
            j, float(lower), float(upper), spec['kind'][j], float(spec['target'][j]), float(spec['scale'][j])
        )
        for j, (lower, upper) in enumerate(spec['boxes'])
    ]
    for i, (a, sense, b) in enumerate(spec['rows']):
        terms = {columns[j]: float(v) for j, v in enumerate(a) if v}
        {'<=': p.at_most, '==': p.equal, '>=': p.at_least}[sense](('row', i), terms, float(b))
    parts = [
        p.positive_part(('unmet', j), {columns[j]: -1.0}, float(request)) for j, request in spec['parts']
    ]
    for cost in spec['objectives']:
        p.minimize({columns[j]: float(v) for j, v in enumerate(cost) if v})
    for part in parts:
        p.minimize({part: 1.0})
    for j, request, tier in spec['claims']:
        p.claim({columns[j]: 1.0}, float(request), tier)
    return p


def reference(spec):
    n, parts = spec['n'], spec['parts']
    width = n + len(parts)
    pad = [F(0)] * len(parts)
    rows = [(list(a) + pad, sense, b) for a, sense, b in spec['rows']]
    boxes = list(spec['boxes'])
    for k, (j, request) in enumerate(parts):
        # s >= request - x_j and 0 <= s (a box wide enough never to bind)
        a = [F(0)] * width
        a[n + k], a[j] = F(1), F(1)
        rows.append((a, '>=', request))
        boxes.append((F(0), F(100)))
    objectives = [list(cost) + pad for cost in spec['objectives']]
    for k in range(len(parts)):
        objectives.append([F(int(i == n + k)) for i in range(width)])
    claims = [([F(int(i == j)) for i in range(width)], request, tier) for j, request, tier in spec['claims']]
    flows = [j for j in range(n) if spec['kind'][j] == FLOW]
    others = [j for j in range(n) if spec['kind'][j] == OTHER]
    target = list(spec['target']) + pad
    scale = list(spec['scale']) + [F(1)] * len(parts)
    return exact.select(width, boxes, rows, objectives, claims, flows, others, target, scale)


@pytest.mark.parametrize('seed', range(30))
def test_the_whole_order_against_the_exact_reference(seed):
    spec = tiny(np.random.default_rng(seed))
    answer = Solver().solve(library(spec))
    flows, others, levels = reference(spec)
    size = 1.0 + max(float(abs(v)) for box in spec['boxes'] for v in box)
    for j, value in {**flows, **others}.items():
        assert answer[j] == pytest.approx(float(value), abs=1e-5 * size), (j, spec)
    assert answer.levels == pytest.approx([float(v) for v in levels], abs=1e-6)


def nearest_problem(rng):
    """2 or 3 other unknowns with unequal scales, 1 to 3 rows of every kind through a point, boxes
    open on either side or both."""
    n = int(rng.integers(2, 4))
    point = [rational(rng, -2, 2) for _ in range(n)]
    boxes = []
    for x in point:
        lower = x - rational(rng, 0, 2) if rng.random() < 0.5 else None
        upper = x + rational(rng, 0, 2) if rng.random() < 0.5 else None
        boxes.append((lower, upper))
    rows = []
    for _ in range(int(rng.integers(1, 4))):
        a = [F(int(v)) for v in rng.integers(-2, 3, n)]
        if not any(a):
            a[-1] = F(1)
        value = sum(x * y for x, y in zip(a, point))
        sense = str(rng.choice(['<=', '==', '>=', 'both']))
        if sense == '==':
            rows.append((a, sense, value, value))
        else:
            rows.append((a, sense, value - rational(rng, 0, 1), value + rational(rng, 0, 1)))
    target = [rational(rng, -3, 3) for _ in range(n)]
    scale = [F(int(rng.choice([1, 2, 4])), int(rng.choice([1, 2]))) for _ in range(n)]
    return n, boxes, rows, target, scale


@pytest.mark.parametrize('seed', range(60))
def test_the_distance_step_against_the_exact_nearest_point(seed):
    n, boxes, rows, target, scale = nearest_problem(np.random.default_rng(1000 + seed))
    p = Problem()
    for j, (lower, upper) in enumerate(boxes):
        low = -np.inf if lower is None else float(lower)
        high = np.inf if upper is None else float(upper)
        p.unknown(j, low, high, OTHER, float(target[j]), float(scale[j]))
    constraints = []
    for j, (lower, upper) in enumerate(boxes):
        unit = [F(int(k == j)) for k in range(n)]
        constraints += [(unit, '>=', lower)] if lower is not None else []
        constraints += [(unit, '<=', upper)] if upper is not None else []
    for i, (a, sense, low, high) in enumerate(rows):
        terms = {j: float(v) for j, v in enumerate(a) if v}
        if sense == '==':
            p.equal(i, terms, float(low))
            constraints.append((a, '==', low))
        else:
            lower = float(low) if sense in ('>=', 'both') else -np.inf
            upper = float(high) if sense in ('<=', 'both') else np.inf
            p.row(i, terms, lower, upper)
            constraints += [(a, '>=', low)] if sense in ('>=', 'both') else []
            constraints += [(a, '<=', high)] if sense in ('<=', 'both') else []
    answer = Solver().solve(p)
    weight = [1 / s**2 for s in scale]
    want = exact.nearest(constraints, set(range(n)), target, weight, n)
    assert answer.x == pytest.approx([float(want[j]) for j in range(n)], abs=1e-7)


def network(rng, places):
    """A random route-and-level network: a random tree and a few more routes, strengths and
    capacities, sources at a few places, a need at each place; columns level, supply, use, carried."""
    edges = {(int(rng.integers(k)), k) for k in range(1, places)}
    while len(edges) < places + 3:
        a, b = sorted(rng.choice(places, 2, replace=False).tolist())
        edges.add((a, b))
    edges = sorted(edges)
    at = rng.choice(places, max(2, places // 4), replace=False)
    return dict(
        places=places,
        frm=np.array([a for a, _ in edges]),
        to=np.array([b for _, b in edges]),
        strength=rng.uniform(0.5, 3.0, len(edges)),
        cap=rng.uniform(0.5, 4.0, len(edges)),
        at=at,
        limit=rng.uniform(1.0, 6.0, len(at)),
        need=rng.uniform(0.2, 2.0, places),
    )


def route_program(net, need, up):
    """(A, row_lower, row_upper, lower, upper) and the columns of each part, with a shortfall column
    for each place: balance == 0, the route law == 0, use + short >= need."""
    P, R, S = net['places'], len(net['frm']), len(net['at'])
    level, supply = np.arange(P), P + np.arange(S)
    use, carried = P + S + np.arange(P), 2 * P + S + np.arange(R)
    short = 2 * P + S + R + np.arange(P)
    n = 3 * P + S + R
    r = np.arange(R)
    pull = net['strength'] * up
    rows = np.r_[
        net['at'],
        np.arange(P),
        net['frm'],
        net['to'],
        P + r,
        P + r,
        P + r,
        P + R + np.arange(P),
        P + R + np.arange(P),
    ]
    cols = np.r_[supply, use, carried, carried, carried, level[net['frm']], level[net['to']], use, short]
    vals = np.r_[
        np.ones(S), -np.ones(P), -np.ones(R), np.ones(R), np.ones(R), -pull, pull, np.ones(P), np.ones(P)
    ]
    A = sp.csr_array((vals, (rows, cols)), shape=(2 * P + R, n))
    row_lower = np.r_[np.zeros(P + R), need]
    row_upper = np.r_[np.zeros(P + R), np.full(P, np.inf)]
    lower = np.r_[np.full(P, -30.0), np.zeros(S + P), -net['cap'] * up, np.zeros(P)]
    upper = np.r_[np.full(P, 30.0), net['limit'], np.full(P, np.inf), net['cap'] * up, np.full(P, np.inf)]
    return (
        A,
        row_lower,
        row_upper,
        lower,
        upper,
        dict(level=level, supply=supply, use=use, carried=carried, short=short),
    )


def brute_levels(A, row_lower, row_upper, lower, upper, F, tol=1e-7):
    """The lexicographic max-min of min(1, F x) by brute force: after each `max t`, one program for
    each pending claim decides whether it can rise (A3's reference, with linprog)."""
    n, K = A.shape[1], F.shape[0]
    equal = row_lower == row_upper
    ub_rows = sp.vstack([A[~equal], -A[~equal]]).tocsr()
    ub = np.r_[row_upper[~equal], -row_lower[~equal]]
    finite = np.isfinite(ub)
    ub_rows, ub = ub_rows[finite], ub[finite]
    bounds = [
        (lo if np.isfinite(lo) else None, hi if np.isfinite(hi) else None) for lo, hi in zip(lower, upper)
    ]
    pending, levels, floors = np.ones(K, bool), np.full(K, np.nan), np.zeros(K)

    def program(cost, extra_rows, extra):
        claim_rows = sp.csr_array(
            sp.hstack([-F, sp.csr_array(pending.astype(float).reshape(-1, 1))])
        )  # t - F_i x <= 0 for a pending claim, -F_i x <= -floor for a held one
        rhs = np.where(pending, 0.0, -floors)
        G = sp.vstack([sp.hstack([ub_rows, sp.csr_array((ub_rows.shape[0], 1))]), claim_rows, *extra_rows])
        E = sp.hstack([A[equal], sp.csr_array((int(equal.sum()), 1))])
        res = linprog(cost, A_ub=G, b_ub=np.r_[ub, rhs, extra], A_eq=E, b_eq=row_lower[equal],
                      bounds=[*bounds, (None, 1.0)], method='highs')  # fmt: skip
        assert res.status == 0, res.message
        return -res.fun

    while pending.any():
        top = program(np.r_[np.zeros(n), -1.0], [], np.zeros(0))
        if top >= 1 - tol:
            levels[pending] = 1.0
            break
        held = []
        for i in np.flatnonzero(pending).tolist():
            at_least = sp.csr_array(np.r_[np.zeros(n), -1.0].reshape(1, -1))
            if program(np.r_[-F[[i]].toarray().ravel(), 0.0], [at_least], np.array([-top])) <= top + tol:
                held.append(i)
        assert held, 'no claim is held'
        levels[held], floors[held] = top, top - tol
        pending[held] = False
    return levels


@pytest.mark.parametrize('seed', range(16))
def test_fair_sharing_on_networks_against_brute_force(seed):
    rng = np.random.default_rng(2000 + seed)
    net = network(rng, int(rng.integers(6, 11)))
    need = net['need'] * float(rng.choice([1.0, 1.5, 2.5]))
    up = np.ones(len(net['frm']))
    if seed % 3 == 0:
        up[rng.choice(len(up), 2, replace=False)] = 0.0
    A, row_lower, row_upper, lower, upper, at = route_program(net, need, up)
    n = A.shape[1]
    kind = np.full(n, FLOW, dtype=np.int8)
    kind[at['level']], kind[at['short']] = OTHER, INTERNAL
    target = np.zeros(n)
    target[at['use']] = need
    p = Problem()
    p.unknowns(range(n), lower, upper, kind, target)
    p.rows(range(A.shape[0]), A, row_lower, row_upper)
    cost = np.zeros(n)
    cost[at['short']] = 1.0
    p.minimize(cost)
    p.claims(at['use'], need)
    answer = Solver().solve(p)
    # the reference's face of the objective: its optimum as a row, independent of pinning
    best = linprog(cost, A_ub=sp.vstack([A[need.size + len(up) :]]).multiply(-1), b_ub=-row_lower[need.size + len(up) :],
                   A_eq=A[: need.size + len(up)], b_eq=row_lower[: need.size + len(up)],
                   bounds=list(zip(lower, [None if np.isinf(u) else u for u in upper])), method='highs')  # fmt: skip
    face = sp.vstack([A, sp.csr_array(cost.reshape(1, -1))]).tocsr()
    claims = sp.csr_array((1.0 / need, (np.arange(len(need)), at['use'])), shape=(len(need), n))
    want = brute_levels(
        face, np.r_[row_lower, -np.inf], np.r_[row_upper, best.fun + 1e-9], lower, upper, claims
    )
    assert answer.levels == pytest.approx(want, abs=1e-6)
