"""E3/E4: the linear program of the goal, cold and warm, and the quadratic program toward `near`, with HiGHS."""
import time, sys
import numpy as np
import scipy.sparse as sp
from net import network, incidence
from hs import Island, h

def clock(label, fn):
    t = time.perf_counter(); out = fn(); dt = time.perf_counter() - t
    print(f'{label:62s} {dt*1000:9.1f} ms'); return out

def full(net, up=None, theta_range=1000.0, rating=None):
    """x = (theta[P], p[S], served[P]).  G p - L theta - served = 0.  goal: most sum(served)."""
    P, S, R = net['places'], net['sources'], net['routes']
    C = incidence(net)
    b = net['b'] if up is None else net['b'] * up
    L = (C.T @ sp.diags_array(b) @ C).tocsr()
    G = sp.coo_array((np.ones(S), (net['at'], np.arange(S))), shape=(P, S)).tocsr()
    A = sp.hstack([-L, G, -sp.eye_array(P)]).tocsr()
    lower = np.r_[np.full(P, -theta_range), np.zeros(S), np.zeros(P)]
    upper = np.r_[np.full(P, theta_range), net['pmax'], net['need']]
    near = np.r_[np.zeros(P), net['p0'], net['need']]
    w = 1.0 / (upper - lower) ** 2
    cost = np.r_[np.zeros(P + S), -np.ones(P)]
    rows = [A]; lo = [np.zeros(P)]; hi = [np.zeros(P)]
    if rating is not None:  # line limits as inequalities: -rating <= b * C theta <= rating
        F = sp.hstack([sp.diags_array(b) @ C, sp.csr_array((R, S + P))]).tocsr()
        rows.append(F); lo.append(-rating); hi.append(rating)
    return sp.vstack(rows).tocsr(), np.concatenate(lo), np.concatenate(hi), lower, upper, near, w, cost

if __name__ == '__main__':
    scale = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    stress = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    net = network(int(30000 * scale), int(35000 * scale), int(15000 * scale))
    net['need'] = net['need'] * stress
    A, rl, ru, lower, upper, near, w, cost = full(net)
    P, S = net['places'], net['sources']
    isl = clock('build the HiGHS model', lambda: Island(A, rl, ru, lower, upper, cost))
    st, x, info = clock('LP cold (presolve on)', lambda: isl.run())
    print('   ', st, 'goal', -info.objective_function_value, 'of need', net['need'].sum(), 'simplex iters', info.simplex_iteration_count)
    g = info.objective_function_value
    # warm: one route fails -> change of coefficients of L (4 entries)
    def trip(isl, net, l, bnew=0.0):
        f, t, b = int(net['frm'][l]), int(net['to'][l]), float(net['b'][l])
        # row f: -L[f,f], -L[f,t]; L[f,f] += -(b-bnew) ...  get the present entries and change them
        for (r, c, d) in ((f, f, +1), (t, t, +1), (f, t, -1), (t, f, -1)):
            pass
        return f, t, b
    Lc = (incidence(net).T @ sp.diags_array(net['b']) @ incidence(net)).tolil()
    rng = np.random.default_rng(1)
    def warm_trip():
        l = int(rng.integers(net['routes']))
        f, t, b = int(net['frm'][l]), int(net['to'][l]), float(net['b'][l])
        Lc[f, f] -= b; Lc[t, t] -= b; Lc[f, t] += b; Lc[t, f] += b
        for r, c in ((f, f), (t, t), (f, t), (t, f)):
            isl.s.changeCoeff(r, c, -Lc[r, c])
        return isl.run()
    for k in range(3):
        st, x, info = clock('LP warm after one route fails', warm_trip)
        print('   ', st, 'goal', -info.objective_function_value, 'simplex iters', info.simplex_iteration_count)
    def warm_need():
        need = net['need'] * rng.uniform(0.9, 1.1, P)
        idx = np.arange(P + S, 2 * P + S, dtype=np.int32)
        isl.s.changeColsBounds(P, idx, np.zeros(P), need)
        return isl.run()
    for k in range(2):
        st, x, info = clock('LP warm after every need changes by up to 10%', warm_need)
        print('   ', st, 'goal', -info.objective_function_value, 'simplex iters', info.simplex_iteration_count)
    # QP: nearest to near among goal-optimal. New instance: goal row as a constraint.
    A, rl, ru, lower, upper, near, w, cost = full(net)
    isl = Island(A, rl, ru, lower, upper, cost)
    st, x, info = isl.run(); g = -info.objective_function_value
    Aq = sp.vstack([A, sp.csr_array(-cost[None, :])]).tocsr()
    slack = 1e-9 * max(1.0, abs(g))
    q = Island(Aq, np.r_[rl, g - slack], np.r_[ru, np.inf], lower, upper, cost=-2 * w * near)
    q.hessian(2 * w)
    t0 = time.perf_counter()
    q.s.setOptionValue('time_limit', 300.0)
    st, xq, info = clock('QP cold toward near (goal row fixed)', lambda: q.run())
    print('   ', st, 'qp iters', info.qp_iteration_count, 'obj', info.objective_function_value + (w * near**2).sum())
    print('    sources at a bound', int((xq[P:P+S] < 1e-9).sum()), int((xq[P:P+S] > net['pmax'] - 1e-9).sum()), 'served cut', int((xq[P+S:] < net['need'] - 1e-9).sum()))
    np.save(f'qp_x_{scale}_{stress}.npy', xq)
