"""E8: a cascade at full size. Routes trip when the amount on them passes their rating.
Rounds: every route that is over its rating trips, then one solve. Count the solves and the time.
A solve after each single trip would need one solve for each trip."""
import time, sys
import numpy as np, scipy.sparse as sp
from net import network, incidence
from nearest import Nearest, Stats
from hs import Island
from e6_full import physics

scale = float(sys.argv[1]); margin = float(sys.argv[2])
net = network(int(30000 * scale), int(35000 * scale), int(15000 * scale)); net['b'] *= 100.0
P, S, R = net['places'], net['sources'], net['routes']
C = incidence(net)
rng = np.random.default_rng(11)

def solve(up, lam=None):
    E, e, l, u, n, cost = physics(net, up)
    t = time.perf_counter(); stats = dict(lp=0.0, facts=0)
    goal = cost != 0
    lb, ub = l.copy(), u.copy(); lb[goal] = u[goal]
    prob = Nearest(E, e, lb, ub, n)
    xi, lam2, why, st = prob.solve(lam=lam, max_iter=8)
    stats['facts'] += st.factorizations
    if why:
        t1 = time.perf_counter()
        isl = Island(E, e, e, l, u, cost); status, xl, info = isl.run()
        stats['lp'] = time.perf_counter() - t1
        d = np.array(isl.s.getSolution().col_dual)
        lb, ub = l.copy(), u.copy(); ub[d > 1e-7] = l[d > 1e-7]; lb[d < -1e-7] = u[d < -1e-7]
        prob = Nearest(E, e, lb, ub, n)
        xi, lam2, why, st = prob.solve(lam=None, max_iter=300)
        stats['facts'] += st.factorizations
    x = prob.x_of(xi)
    stats['time'] = time.perf_counter() - t; stats['why'] = why
    return x, lam2, stats

up = np.ones(R)
x, lam, st = solve(up)
flow0 = net['b'] * (C @ x[:P])
rating = np.maximum(margin * np.abs(flow0), np.quantile(np.abs(flow0), 0.5))
print(f'places {P} routes {R}; rating = max({margin} x normal amount, median amount)')
up[rng.choice(R, int(1000 * scale), replace=False)] = 0.0
total, rounds, trips, lp_time, facts = 0.0, 0, 0, 0.0, 0
while True:
    x, lam, st = solve(up, None)
    total += st['time']; lp_time += st['lp']; facts += st['facts']; rounds += 1
    flow = net['b'] * up * (C @ x[:P])
    over = np.flatnonzero((up > 0) & (np.abs(flow) >= rating))
    cut = float((net['need'] - x[P + S:]).sum())
    print(f'  round {rounds}: solve {st["time"]:.2f}s (LP {st["lp"]:.2f}s, {st["facts"]} factorizations, {st["why"] or "ok"}); cut {cut:9.2f}; routes over their rating {len(over)}')
    if not len(over) or rounds > 60:
        break
    up[over] = 0.0; trips += len(over)
print(f'rounds {rounds}, trips {trips}, time of the solves {total:.1f}s (of which LP cold {lp_time:.1f}s), factorizations {facts}')
print(f'a solve after each single step would be about {int(1000*scale) + trips} solves')
