"""E6: LP + nearest at full size, for a network with physics and for a transport network; cold and warm."""
import time, sys
import numpy as np, scipy.sparse as sp
from net import network, incidence
from nearest import Nearest, Stats
from hs import Island

def physics(net, up, theta_range=30.0):
    P, S, R = net['places'], net['sources'], net['routes']
    C = incidence(net)
    L = (C.T @ sp.diags_array(net['b'] * up) @ C).tocsr()
    G = sp.coo_array((np.ones(S), (net['at'], np.arange(S))), shape=(P, S)).tocsr()
    E = sp.hstack([-L, G, -sp.eye_array(P)]).tocsr()
    l = np.r_[np.full(P, -theta_range), np.zeros(S), np.zeros(P)]
    u = np.r_[np.full(P, theta_range), net['pmax'], net['need']]
    n = np.r_[np.zeros(P), net['p0'], net['need']]
    cost = np.r_[np.zeros(P + S), -np.ones(P)]
    return E, np.zeros(P), l, u, n, cost

def transport(net, up):
    """x = (carried[R] in -cap..cap, used[S] in 0..pmax, served[P] in 0..need); balance at each place."""
    P, S, R = net['places'], net['sources'], net['routes']
    C = incidence(net)   # carried flows from `frm` to `to`: leaves frm (+1 row frm), arrives to
    G = sp.coo_array((np.ones(S), (net['at'], np.arange(S))), shape=(P, S)).tocsr()
    E = sp.hstack([-C.T.tocsr(), G, -sp.eye_array(P)]).tocsr()
    cap = net['cap'] * up
    l = np.r_[-cap, np.zeros(S), np.zeros(P)]
    u = np.r_[cap, net['pmax'], net['need']]
    n = np.r_[np.zeros(R), net['p0'], net['need']]
    cost = np.r_[np.zeros(R + S), -np.ones(P)]
    return E, np.zeros(P), l, u, n, cost

def lexicographic(E, e, l, u, n, cost, isl=None, lam=None, label='', try_first=True):
    out = {}
    t0 = time.perf_counter()
    goal = cost != 0
    if try_first:
        lb, ub = l.copy(), u.copy()
        best = np.where(cost < 0, u, l)
        lb[goal], ub[goal] = best[goal], best[goal]
        prob = Nearest(E, e, lb, ub, n)
        xi, lam2, why, st = prob.solve(lam=lam, max_iter=10)
        out['try'] = (why or 'converged', len(st.log), st.factorizations, time.perf_counter() - t0)
    else:
        why = 'skipped'
    if why:
        t = time.perf_counter()
        if isl is None:
            isl = Island(E, e, e, l, u, cost)
        status, xl, info = isl.run()
        out['lp'] = (str(status).split('.')[-1], info.simplex_iteration_count, time.perf_counter() - t)
        d = np.array(isl.s.getSolution().col_dual)
        lb, ub = l.copy(), u.copy()
        ub[d > 1e-7] = l[d > 1e-7]; lb[d < -1e-7] = u[d < -1e-7]
        t = time.perf_counter()
        prob = Nearest(E, e, lb, ub, n)
        xi, lam2, why, st = prob.solve(lam=None, max_iter=300)
        out['nearest'] = (why or 'converged', len(st.log), st.factorizations, time.perf_counter() - t)
        out['goal gap'] = float(-(cost @ prob.x_of(xi)) + info.objective_function_value)
    t = time.perf_counter()
    xp, lamp, resid, outside = prob.polish(lam2)
    x = prob.x_of(xp)
    scale_ = np.abs(E) @ np.abs(x) + np.abs(e) + 1e-300
    out['polish'] = (f'{time.perf_counter()-t:.2f}s', f'rel residual {float((np.abs(E @ x - e) / scale_).max()):.1e}', f'outside {outside:.1e}')
    out['total'] = time.perf_counter() - t0
    print(label, {k: (tuple(round(i, 3) if isinstance(i, float) else i for i in v) if isinstance(v, tuple) else round(v, 12)) for k, v in out.items()})
    return x, lam2, isl, prob

if __name__ == '__main__':
    kind = sys.argv[1]; scale = float(sys.argv[2])
    net = network(int(30000 * scale), int(35000 * scale), int(15000 * scale))
    net['b'] = net['b'] * 100.0
    P, S, R = net['places'], net['sources'], net['routes']
    rng = np.random.default_rng(3)
    net['cap'] = rng.uniform(2.0, 12.0, R)
    build = physics if kind == 'physics' else transport
    base_need = net['need'].copy()
    up = np.ones(R)
    print(f'=== {kind}: places {P} routes {R} sources {S}')
    x, lam, isl, prob = lexicographic(*build(net, up), label='normal day, cold:')
    # the next hours: need moves by a few percent; warm multipliers
    for hour in range(3):
        net['need'] = base_need * (1 + 0.1 * np.sin(hour + 1)) * rng.uniform(0.97, 1.03, P)
        x, lam, isl, prob = lexicographic(*build(net, up), lam=lam, label=f'hour {hour+1}, warm:')
    # high demand: sources at their limits
    net['need'] = base_need * 1.45
    x, lam, _, _ = lexicographic(*build(net, up), label='demand x1.45, cold:')
    # 1,000 routes down (scaled), normal demand: islands with no source
    net['need'] = base_need
    up2 = up.copy(); up2[rng.choice(R, int(1000 * scale), replace=False)] = 0.0
    x, lam, isl, prob = lexicographic(*build(net, up2), label='routes down, cold:')
    np.save(f'x_{kind}_{scale}.npy', x)
    print('   places cut', int((x[-P:] < net['need'] - 1e-9).sum()), 'total cut', float((net['need'] - x[-P:]).sum()))
    # one more route fails: warm (multipliers), LP not warm here
    up3 = up2.copy(); up3[rng.choice(np.flatnonzero(up2 > 0), 1)] = 0.0
    lexicographic(*build(net, up3), lam=lam, label='one more route down:', try_first=False)
