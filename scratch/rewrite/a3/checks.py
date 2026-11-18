"""Random checks against exact references. Run: python checks.py [COUNT]

1. distance: random small problems with ==, <= and >= rows and boxes, against `distance.exact`.
2. fair: small random route-and-level networks (with and without shortage, some routes down), the
   sequential method on a kept instance against `fair.brute` (one program for each pending claim).
"""
import sys
import numpy as np
import scipy.sparse as sp

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from solve.distance import nearest, exact
from solve.lp import Kept
from solve import fair, ranked
from network import network, program, damaged

INF = np.inf


def distance_checks(count, rng):
    worst, bad = 0.0, 0
    for trial in range(count):
        n = int(rng.integers(2, 5))
        m = int(rng.integers(1, 4))
        A = np.round(rng.normal(size=(m, n)), 1)
        x0 = rng.normal(size=n)
        v = A @ x0
        kind = rng.integers(0, 4, m)          # ==, <=, >=, interval
        rl = np.where(kind == 1, -INF, v - rng.uniform(0, 1, m) * (kind != 0))
        ru = np.where(kind == 2, INF, v + rng.uniform(0, 1, m) * (kind != 0))
        lo = np.where(rng.random(n) < 0.5, x0 - rng.uniform(0, 1, n), -INF)
        hi = np.where(rng.random(n) < 0.5, x0 + rng.uniform(0, 1, n), INF)
        target = rng.normal(size=n) * 2
        weight = rng.uniform(0.5, 2.0, n)
        want = exact(A, rl, ru, lo, hi, target, weight)
        got, _ = nearest(A, rl, ru, lo, hi, target, weight)
        err = float(np.abs(got - want).max())
        worst = max(worst, err)
        bad += err > 1e-6
    return worst, bad


def fair_checks(count, rng):
    worst, bad, levels = 0.0, 0, []
    for trial in range(count):
        places = int(rng.integers(10, 16))
        net = network(places, places + 4, max(2, places // 4), seed=int(rng.integers(1 << 30)))
        mult = float(rng.choice([1.0, 1.5, 2.5]))
        need = net['need'] * mult
        up = damaged(net, 3, seed=trial) if trial % 3 == 0 else None
        A, rl, ru, lo, hi, at = program(net, need=need, up=up, shortfall=True)
        n = A.shape[1]
        objective = trial % 2 == 0
        k = Kept(A, rl, ru, lo, hi)
        face = ranked.Face(lo, hi, rl, ru)
        costs = []
        if objective:
            c = np.zeros(n); c[at['short']] = 1.0; costs = [c]
        ranked.optimize(k, face, costs)
        claims = at['use']
        F = sp.csr_array((1.0 / need, (np.arange(len(claims)), claims)), shape=(len(claims), n))
        got, _ = fair.sequential(k, face, F)
        # the reference on the face that the objective left (the same face, given as plain arrays)
        want = fair.brute(A, rl, ru, lo, hi, F) if not objective else \
            fair.brute(*_face_after(A, rl, ru, lo, hi, costs[0]), F)
        err = float(np.abs(got - want).max())
        worst = max(worst, err)
        bad += err > 1e-6
        levels.append(len(np.unique(np.round(want, 6))))
    return worst, bad, levels


def _face_after(A, rl, ru, lo, hi, cost):
    """The optimal face of `cost` as a row c.x <= optimum (independent of the pin method)."""
    from scipy.optimize import linprog
    eq = rl == ru
    Ub = sp.vstack([A[~eq], -A[~eq]])
    ub = np.r_[ru[~eq], -rl[~eq]]
    keep = np.isfinite(ub)
    res = linprog(cost, A_ub=Ub[keep], b_ub=ub[keep], A_eq=A[eq], b_eq=rl[eq],
                  bounds=list(zip(np.where(np.isfinite(lo), lo, None), np.where(np.isfinite(hi), hi, None))), method='highs')
    A2 = sp.vstack([A, sp.csr_array(cost.reshape(1, -1))]).tocsr()
    return A2, np.r_[rl, -INF], np.r_[ru, res.fun + 1e-9], lo, hi


if __name__ == '__main__':
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rng = np.random.default_rng(7)
    worst, bad = distance_checks(count, rng)
    print(f'distance: {count} random problems, largest difference from the enumeration {worst:.2e}, {bad} above 1e-6')
    worst, bad, levels = fair_checks(max(20, count // 5), rng)
    print(f'fair: {len(levels)} random networks, largest difference from brute force {worst:.2e}, {bad} above 1e-6; '
          f'distinct levels per network {min(levels)}..{max(levels)}')
