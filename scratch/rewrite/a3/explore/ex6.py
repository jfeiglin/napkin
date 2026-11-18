"""Explore: parallel filling with groups certified by the components of the dual support."""
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
T0 = time.perf_counter()
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
TF = time.perf_counter()
claims = at['use']; q = need; K = len(claims)
TOL = 1e-9
# columns: floor phi_i (fixed 0), then group columns. rows: u_i - phi_i - sum t >= 0
phi = k.add_cols(np.zeros(K), np.zeros(K), np.zeros(K))
rows = sp.coo_array((np.r_[1.0 / q, -np.ones(K)], (np.r_[np.arange(K), np.arange(K)], np.r_[claims, phi])), shape=(K, k.n)).tocsr()
frows = k.add_rows(np.zeros(K), np.full(K, INF), rows)
# my copy of the structure, as triplets
base = sp.vstack([sp.hstack([A, sp.csr_array((m, K))]), rows]).tocoo()
trip_r, trip_c, trip_v = [base.row], [base.col], [base.data]
col_lo = np.r_[lo, np.zeros(K)]; col_hi = np.r_[hi, np.zeros(K)]
group_of = np.full(K, -1)          # the column of the group of each pending claim
level = np.full(K, np.nan)
pending = np.ones(K, bool)
last_level = {}                    # group column -> level at its last round
def new_groups(member_lists):
    """Add one column for each list of claims."""
    global col_lo, col_hi
    G = len(member_lists)
    if not G: return
    sizes = np.array([len(mm) for mm in member_lists])
    members = np.concatenate(member_lists)
    start = np.r_[0, np.cumsum(sizes)]
    colmat = sp.csc_array((-np.ones(len(members)), frows[members], start), shape=(k.m, G))
    cols = k.add_cols(-np.ones(G), np.zeros(G), np.ones(G), colmat)
    trip_r.append(frows[members]); trip_c.append(np.repeat(cols, sizes)); trip_v.append(-np.ones(len(members)))
    col_lo = np.r_[col_lo, np.zeros(G)]; col_hi = np.r_[col_hi, np.ones(G)]
    group_of[members] = np.repeat(cols, sizes)
    return cols
def retire(cols):
    cols = np.asarray(cols, dtype=int)
    if len(cols):
        k.set_bounds(cols, np.zeros(len(cols)), np.zeros(len(cols))); k.set_costs(cols, np.zeros(len(cols)))
        col_lo[cols] = 0.0; col_hi[cols] = 0.0
cols = new_groups([np.array([i]) for i in range(K)])
basis = k.s.getBasis(); cs = list(basis.col_status)
for c in cols.tolist(): cs[c] = AT_UPPER
b2 = h.HighsBasis(); b2.col_status = cs; b2.row_status = list(basis.row_status); b2.valid = True; k.s.setBasis(b2)
rnd = 0
while pending.any():
    rnd += 1
    t = time.perf_counter(); status, x, d, r, y, val = k.run(); dt = time.perf_counter() - t
    if status != OPTIMAL:
        print('status', status); break
    tc = time.perf_counter()
    lam = y[frows]
    pos = pending & (lam > TOL)
    tg = np.where(pending, x[np.where(pending, group_of, 0)], np.nan)      # level of the group of each pending claim
    # components of the dual support
    Mfull = sp.coo_array((np.concatenate(trip_v), (np.concatenate(trip_r), np.concatenate(trip_c))), shape=(k.m, k.n)).tocsr()
    support = np.flatnonzero(np.abs(y) > TOL)
    free = np.flatnonzero(col_hi > col_lo)
    Msub = Mfull[support][:, free]
    nr, nc = Msub.shape
    ncomp, lab = connected_components(sp.block_array([[None, Msub], [Msub.T, None]]).tocsr(), directed=False)
    comp_of_row = np.full(k.m, -1); comp_of_row[support] = lab[:nr]
    comp = comp_of_row[frows]                     # component of each claim row (-1: not in the support)
    pidx = np.flatnonzero(pos)
    # level range of the positive claims of each component
    cmin = np.full(ncomp, np.inf); cmax = np.full(ncomp, -np.inf)
    np.minimum.at(cmin, comp[pidx], tg[pidx]); np.maximum.at(cmax, comp[pidx], tg[pidx])
    pure = (cmax - cmin) <= TOL
    certified = pos & pure[np.where(comp >= 0, comp, 0)] & (comp >= 0)
    full = pending & (tg >= 1 - TOL)
    undecided = pending & ~certified & ~full
    tau_rule = tg[undecided].min() if undecided.any() else np.inf
    freeze = (certified & (tg <= tau_rule + TOL)) | (full & (tau_rule >= 1 - TOL))
    fidx = np.flatnonzero(freeze)
    level[fidx] = np.minimum(tg[fidx], 1.0)
    # regroup: (1) retire the columns of groups that lose members or merge
    changed_cols = set(group_of[fidx].tolist())
    # merge: union of the groups of positive claims in each component that is not pure
    mixed = np.flatnonzero(~pure & np.isfinite(cmin))
    merge_claims = pos & np.isin(comp, mixed)
    # groups to merge: for each mixed component, the set of group columns
    newlists = []
    if merge_claims.any():
        mi = np.flatnonzero(merge_claims)
        # union-find over group columns through components
        pairs = np.unique(np.c_[comp[mi], group_of[mi]], axis=0)
        # graph: component nodes and group nodes
        ucomp, ci = np.unique(pairs[:, 0], return_inverse=True); ugrp, gi = np.unique(pairs[:, 1], return_inverse=True)
        Bi = sp.coo_array((np.ones(len(pairs)), (ci, gi)), shape=(len(ucomp), len(ugrp)))
        nc2, lab2 = connected_components(sp.block_array([[None, Bi], [Bi.T, None]]).tocsr(), directed=False)
        glab = lab2[len(ucomp):]
        merged_into = dict(zip(ugrp.tolist(), glab.tolist()))
        changed_cols |= set(ugrp.tolist())
    else:
        merged_into = {}
    pending[fidx] = False
    # frozen claims: floor column at the level
    k.set_bounds(phi[fidx], level[fidx], level[fidx]); col_lo[phi[fidx]] = level[fidx]; col_hi[phi[fidx]] = level[fidx]
    # rebuild the changed groups
    ch = np.array(sorted(changed_cols), dtype=int)
    stalled = 0
    if len(ch):
        affected = pending & np.isin(group_of, ch)
        ai = np.flatnonzero(affected)
        key = np.array([merged_into.get(g, -1 - g) for g in group_of[ai].tolist()])
        # a group that did not rise since its last round and lost members: split into singletons
        lists = {}
        for i, kk, g in zip(ai.tolist(), key.tolist(), group_of[ai].tolist()):
            lists.setdefault(kk, []).append(i)
        out = []
        for kk, mem in lists.items():
            g = group_of[mem[0]]
            lv = x[g]
            if kk < 0 and last_level.get(g, -1.0) >= lv - TOL and len(mem) > 1:
                out += [np.array([i]) for i in mem]; stalled += 1
            else:
                out.append(np.array(mem))
        for g in ch.tolist():
            pass
        retire(ch)
        newcols = new_groups(out)
        for c, mem in zip(newcols.tolist(), out):
            last_level[c] = float(np.nanmin(tg[mem]))
    ta = time.perf_counter() - tc
    print(f' round {rnd}: LP {dt*1000:.0f}ms iters {k.last_iterations}; analysis {ta*1000:.0f}ms; comps {ncomp} mixed {len(mixed)}; positive {pos.sum()} certified {certified.sum()} full {full.sum()} undecided {undecided.sum()} tau {tau_rule:.6f}; frozen {len(fidx)}; pending {pending.sum()}; groups rebuilt {len(ch)} stalled {stalled}; cols {k.n}')
    if rnd > 300: break
print(f'fair: {rnd} rounds in {time.perf_counter()-TF:.2f}s; total {time.perf_counter()-T0:.2f}s')
np.save(f'plevels_{scen}_{share}.npy', level)
try:
    ref = np.load(f'levels_{scen}_{share}.npy')
    ok = ~np.isnan(ref)
    print('max difference from the sequential levels', np.nanmax(np.abs(ref[ok] - level[ok])), 'distinct levels', len(np.unique(np.round(level, 9))))
except Exception as e:
    print('no reference', e)
