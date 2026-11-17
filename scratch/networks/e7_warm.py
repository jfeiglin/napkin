"""E7: a network that needs a cut at each hour: warm linear program (one persistent solver) and warm
multipliers for the nearest step. Then a cascade: routes that fail one after another."""
import time, sys
import numpy as np, scipy.sparse as sp
from net import network
from nearest import Nearest, Stats
from hs import Island
from e6_full import transport, physics

kind, scale = sys.argv[1], float(sys.argv[2])
net = network(int(30000 * scale), int(35000 * scale), int(15000 * scale)); net['b'] *= 100.0
P, S, R = net['places'], net['sources'], net['routes']
rng = np.random.default_rng(3); net['cap'] = rng.uniform(2.0, 12.0, R)
build = physics if kind == 'physics' else transport
base = net['need'].copy(); up = np.ones(R)
if kind == 'physics':
    up[rng.choice(R, int(1000 * scale), replace=False)] = 0.0   # a damaged network, so that a cut is needed
E, e, l, u, n, cost = build(net, up)
isl = Island(E, e, e, l, u, cost)
lam = None
N = len(l)
def one(label, l, u, n, lam, E=E):
    t0 = time.perf_counter()
    status, xl, info = isl.run(); t_lp = time.perf_counter() - t0
    d = np.array(isl.s.getSolution().col_dual)
    lb, ub = l.copy(), u.copy(); ub[d > 1e-7] = l[d > 1e-7]; lb[d < -1e-7] = u[d < -1e-7]
    t = time.perf_counter()
    prob = Nearest(E, e, lb, ub, n)
    xi, lam2, why, st = prob.solve(lam=lam, max_iter=300); t_n = time.perf_counter() - t
    if why and lam is not None:      # the multipliers of another problem did not help: start cold
        xi, lam2, why, st2 = prob.solve(lam=None, max_iter=300); st.factorizations += st2.factorizations
        t_n = time.perf_counter() - t
    print(f'{label:28s} LP {t_lp*1000:6.0f} ms ({info.simplex_iteration_count} it)   nearest {t_n*1000:6.0f} ms ({st.factorizations} fact, {why or "ok"})   cut {float(-cost @ (np.where(cost<0,u,0)) + info.objective_function_value):.3f}')
    return lam2, prob.x_of(xi)
lam, x = one('first hour (cold)', l, u, n, None)
idx = np.arange(N, dtype=np.int32)
for hour in range(1, 6):
    net['need'] = base * (1 + 0.1 * np.sin(hour)) * rng.uniform(0.97, 1.03, P)
    E2, e2, l, u, n, cost = build(net, up)
    isl.s.changeColsBounds(N, idx, l, u)
    lam, x = one(f'hour {hour} (warm)', l, u, n, lam)
# a cascade: one route after another goes down (bounds of its flow to 0 for transport)
if kind == 'transport':
    for k in range(5):
        r = int(rng.choice(np.flatnonzero(up > 0))); up[r] = 0.0
        E2, e2, l, u, n, cost = build(net, up)
        isl.s.changeColBounds(r, 0.0, 0.0)
        lam, x = one(f'route {r} fails (warm)', l, u, n, lam)
