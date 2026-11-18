"""Explore: singleton sum-LP on the pinned face; the components of the dual support."""
import sys, time
sys.path.insert(0, '/home/user/napkin/scratch/rewrite/a3')
import numpy as np, scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from network import network, program, damaged, layout
from solve.lp import Kept, OPTIMAL, INF, BASIC, AT_LOWER, AT_UPPER
from scipy.optimize._highspy import _core as h

share = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
scen = sys.argv[2] if len(sys.argv) > 2 else 'normal'
do_obj = (sys.argv[3] if len(sys.argv) > 3 else 'obj') == 'obj'
net = network(int(30000 * share), int(35000 * share), int(15000 * share))
P, S, R = net['places'], net['sources'], net['routes']
mult = {'high': 1.45, 'low': 0.5, 'global': 1.7}.get(scen, 1.0)
need = net['need'] * mult
up = damaged(net, int(1000 * share)) if scen == 'damaged' else None
A, rl, ru, lo, hi, at = program(net, need=need, up=up, shortfall=True)
n = A.shape[1]; m = A.shape[0]
cost = np.zeros(n); cost[at['short']] = 1.0
k = Kept(A, rl, ru, lo, hi, cost)
if do_obj:
    t = time.perf_counter(); status, x, d, r, y, val = k.run(); print(f'objective 1 cold {time.perf_counter()-t:.2f}s iters {k.last_iterations} value {val:.6f}')
    tau = 1e-9
    newlo, newhi = lo.copy(), hi.copy()
    atlow = d > tau; atup = d < -tau
    newhi[atlow] = lo[atlow]; newlo[atup] = hi[atup]
    pc = np.flatnonzero(atlow | atup)
    k.set_bounds(pc, newlo[pc], newhi[pc])
    pr = np.flatnonzero(np.abs(y) > tau)
    nrl, nru = rl.copy(), ru.copy()
    nru[y > tau] = rl[y > tau]; nrl[y < -tau] = ru[y < -tau]
    k.set_row_bounds(pr, nrl[pr], nru[pr])
    lo, hi, rl, ru = newlo, newhi, nrl, nru
    k.set_cost(np.zeros(n))
claims = at['use']; q = need; K = len(claims)
# singleton groups: v_i <= use_i/q_i, v_i <= 1; max sum v_i
vcols = k.add_cols(-np.ones(K), np.zeros(K), np.ones(K))
rows = sp.coo_array((np.r_[1.0 / q, -np.ones(K)], (np.r_[np.arange(K), np.arange(K)], np.r_[claims, vcols])), shape=(K, k.n)).tocsr()
frows = k.add_rows(np.zeros(K), np.full(K, INF), rows)
t = time.perf_counter(); status, x, d, r, y, val = k.run(); print(f'singleton sum-LP {time.perf_counter()-t:.2f}s iters {k.last_iterations} status {status} value {-val:.4f} of {K}')
v = x[vcols]
print('claims below 1:', int((v < 1 - 1e-9).sum()), 'at 0:', int((v < 1e-9).sum()), 'strictly between:', int(((v > 1e-9) & (v < 1 - 1e-9)).sum()))
# dual support
Afull = sp.vstack([sp.hstack([A, sp.csr_array((m, K))]), rows]).tocsr()
lo_all = np.r_[lo, np.zeros(K)]; hi_all = np.r_[hi, np.ones(K)]
free = hi_all > lo_all
support = np.abs(y) > 1e-9
print('support rows', int(support.sum()), 'of', len(y), '; fairness rows in support', int(support[m:].sum()))
M = Afull[support][:, free]
nr, nc = M.shape
G = sp.block_array([[None, M], [M.T, None]]).tocsr()
ncomp, lab = connected_components(G, directed=False)
rowlab = lab[:nr]
srows = np.flatnonzero(support)
is_f = srows >= m
# claims per component
comp_claims = np.bincount(rowlab[is_f], minlength=ncomp)
sizes = np.sort(comp_claims[comp_claims > 0])[::-1]
print('components with claims:', len(sizes), 'largest', sizes[:10], 'singletons', int((sizes == 1).sum()))
lam = y[m:]
print('lam>0:', int((lam > 1e-9).sum()), 'lam range', lam.min(), lam.max())
