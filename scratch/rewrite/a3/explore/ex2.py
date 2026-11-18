"""Explore: the fair-sharing rank at scale: levels, time per level, with pin after objective 1."""
import sys, time
sys.path.insert(0, '/home/user/napkin/scratch/rewrite/a3')
import numpy as np, scipy.sparse as sp
from network import network, program, damaged, layout
from solve.lp import Kept, OPTIMAL, INF, BASIC, AT_LOWER, AT_UPPER
from scipy.optimize._highspy import _core as h

share = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
scen = sys.argv[2] if len(sys.argv) > 2 else 'normal'
do_obj = (sys.argv[3] if len(sys.argv) > 3 else 'obj') == 'obj'
net = network(int(30000 * share), int(35000 * share), int(15000 * share))
P, S, R = net['places'], net['sources'], net['routes']
need = net['need'] * (1.45 if scen == 'high' else 0.5 if scen == 'low' else 1.0)
up = damaged(net, int(1000 * share)) if scen == 'damaged' else None
A, rl, ru, lo, hi, at = program(net, need=need, up=up, shortfall=True)
n = A.shape[1]; m = A.shape[0]
cost = np.zeros(n); cost[at['short']] = 1.0
k = Kept(A, rl, ru, lo, hi, cost)
T0 = time.perf_counter()
if do_obj:
    t = time.perf_counter(); status, x, d, r, y, val = k.run(); print(f'objective 1 cold {time.perf_counter()-t:.2f}s iters {k.last_iterations} value {val:.6f}')
    # pin by duals
    t = time.perf_counter()
    basis = k.s.getBasis(); cs = np.array([int(v) for v in basis.col_status]); rs = np.array([int(v) for v in basis.row_status])
    tau = 1e-9
    pc = np.flatnonzero(np.abs(d) > tau)
    newlo, newhi = lo.copy(), hi.copy()
    atlow = d > tau; atup = d < -tau
    newhi[atlow] = lo[atlow]; newlo[atup] = hi[atup]
    k.set_bounds(pc, newlo[pc], newhi[pc])
    pr = np.flatnonzero(np.abs(y) > tau)
    nrl, nru = rl.copy(), ru.copy()
    nru[y > tau] = rl[y > tau]; nrl[y < -tau] = ru[y < -tau]
    k.set_row_bounds(pr, nrl[pr], nru[pr])
    print(f'pin: {len(pc)} columns, {len(pr)} rows in {time.perf_counter()-t:.3f}s; small duals in (1e-12,1e-7): cols {((np.abs(d)>1e-12)&(np.abs(d)<1e-7)).sum()} rows {((np.abs(y)>1e-12)&(np.abs(y)<1e-7)).sum()}')
    lo, hi, rl, ru = newlo, newhi, nrl, nru
    k.set_cost(np.zeros(n))
# fairness structure: t column, rows use_i/q_i - t >= 0
claims = at['use']; q = need
K = len(claims)
t = time.perf_counter()
tcol = k.add_cols([-1.0], [0.0], [1.0])[0]
rows = sp.coo_array((np.r_[1.0 / q, -np.ones(K)], (np.r_[np.arange(K), np.arange(K)], np.r_[claims, np.full(K, tcol)])), shape=(K, k.n)).tocsr()
frows = k.add_rows(np.zeros(K), np.full(K, INF), rows)
# start t at its upper bound
basis = k.s.getBasis()
cs = list(basis.col_status); cs[tcol] = AT_UPPER
b2 = h.HighsBasis(); b2.col_status = cs; b2.row_status = list(basis.row_status); b2.valid = True
print('setBasis', k.s.setBasis(b2), 'valid', k.s.getBasis().valid)
print(f'fair structure added in {time.perf_counter()-t:.3f}s')
pending = np.ones(K, bool)
level = np.full(K, np.nan)
nlev = 0; tlast = -1.0
TF = time.perf_counter()
while pending.any():
    t = time.perf_counter(); status, x, d, r, y, val = k.run(); dt = time.perf_counter() - t
    if status != OPTIMAL:
        print('status', status); break
    tstar = x[tcol]
    lam = y[frows]
    frac = x[claims] / q
    fixed = pending & (lam > 1e-9)
    active = pending & (frac <= tstar + 1e-9)
    nlev += 1
    print(f'  LP {nlev}: t*={tstar:.9f} time {dt*1000:.0f}ms iters {k.last_iterations} fixed-by-dual {fixed.sum()} active-rows {active.sum()} pending {pending.sum()} sum lam {lam[pending].sum():.6f}')
    if tstar >= 1 - 1e-9:
        level[pending] = 1.0; pending[:] = False; break
    if not fixed.any():
        print('  no dual found'); break
    idx = np.flatnonzero(fixed)
    level[idx] = tstar
    # freeze: fix use at q*t, release the row
    k.set_bounds(claims[idx], q[idx] * tstar, q[idx] * tstar)
    k.set_row_bounds(frows[idx], np.full(len(idx), -INF), np.full(len(idx), INF))
    pending[idx] = False
    if nlev > 400: break
print(f'fair: {nlev} LPs in {time.perf_counter()-TF:.2f}s; total {time.perf_counter()-T0:.2f}s; levels distinct {len(np.unique(np.round(level[~np.isnan(level)], 9)))} pending left {pending.sum()}')
np.save(f'levels_{scen}_{share}.npy', level)
