"""P1: the grid of the earlier trials, written as the syntax proposal writes it.

A: the earlier form. x = (angle[P], used[S], served[P]); one balance for each place.
B: the proposal's form. Each route is two directed flows with rates >= 0, each place is a store with
   the interval [0, 0], and a relation of the route gives `forward - backward = b * (angle difference)`.
   x = (forward[R], backward[R], angle[P], used[S], served[P]).

For each: the linear program cold, then after every need changes (from the last basis). For B also the
ranked objectives of the proposal: least unmet request, then least total flow. Then: is the answer one?
The range of one angle, and of one route, over the best answers."""
import sys, time
import numpy as np, scipy.sparse as sp

sys.path.insert(0, '/home/user/napkin/scratch/networks')
from net import network, incidence
from hs import Island

scale = float(sys.argv[1])
net = network(int(30000 * scale), int(35000 * scale), int(15000 * scale)); net['b'] *= 100.0
P, S, R = net['places'], net['sources'], net['routes']
rng = np.random.default_rng(3)
up = np.ones(R); up[rng.choice(R, int(1000 * scale), replace=False)] = 0.0   # a damaged network: a cut is necessary
C = incidence(net)
G = sp.coo_array((np.ones(S), (net['at'], np.arange(S))), shape=(P, S)).tocsr()
I = sp.eye_array(P).tocsr()
TH = 30.0
base = net['need'].copy()


def form_a():
    L = (C.T @ sp.diags_array(net['b'] * up) @ C).tocsr()
    E = sp.hstack([-L, G, -I]).tocsr()
    l = np.r_[np.full(P, -TH), np.zeros(S), np.zeros(P)]
    u = np.r_[np.full(P, TH), net['pmax'], net['need']]
    cost = np.r_[np.zeros(P + S), -np.ones(P)]
    return E, np.zeros(P), l, u, cost


def form_b():
    Z = sp.csr_array((R, S)); Zp = sp.csr_array((R, P))
    balance = sp.hstack([-C.T, C.T, sp.csr_array((P, P)), G, -I])
    physics = sp.hstack([sp.eye_array(R), -sp.eye_array(R), -(sp.diags_array(net['b'] * up) @ C), Z, Zp])
    E = sp.vstack([balance, physics]).tocsr()
    l = np.r_[np.zeros(2 * R), np.full(P, -TH), np.zeros(S), np.zeros(P)]
    u = np.r_[np.full(2 * R, np.inf), np.full(P, TH), net['pmax'], net['need']]
    cost = np.r_[np.zeros(2 * R + P + S), -np.ones(P)]
    return E, np.zeros(P + R), l, u, cost


def timed(isl):
    t = time.perf_counter(); status, x, info = isl.run()
    return (time.perf_counter() - t) * 1000, x, info, str(status).split('.')[-1]


def pin(isl, l, u):
    """Hold each value with a reduced cost at its end: what is left is the set of the best answers."""
    d = np.array(isl.s.getSolution().col_dual)
    lb, ub = l.copy(), u.copy()
    ub[d > 1e-7] = l[d > 1e-7]; lb[d < -1e-7] = u[d < -1e-7]
    return lb, ub


def span(isl, j, n, idx):
    """(least, greatest) of value j over the answers that the bounds of `isl` leave."""
    out = []
    for sign in (1.0, -1.0):
        c = np.zeros(n); c[j] = sign
        isl.s.changeColsCost(n, idx, c)
        ms, x, info, status = timed(isl)
        out.append(x[j] if status == 'kOptimal' else (-np.inf if sign > 0 else np.inf))
    return out


for name, form in (('A (one balance for each place)', form_a), ('B (two directed flows, a relation for each route)', form_b)):
    net['need'] = base.copy()
    E, e, l, u, cost = form()
    n = len(l); idx = np.arange(n, dtype=np.int32)
    print(f'=== {name}: {E.shape[0]} conditions, {n} values, {E.nnz} nonzeros')
    isl = Island(E, e, e, l, u, cost)
    ms, x, info, status = timed(isl)
    print(f'  cold                 {ms:7.0f} ms  {info.simplex_iteration_count:6d} iterations  {status}  cut {base.sum() + info.objective_function_value:.4f}')
    for hour in range(1, 4):
        net['need'] = base * (1 + 0.1 * np.sin(hour)) * rng.uniform(0.97, 1.03, P)
        E, e, l, u, cost = form()
        isl.s.changeColsBounds(n, idx, l, u)
        ms, x, info, status = timed(isl)
        print(f'  hour {hour}, last basis   {ms:7.0f} ms  {info.simplex_iteration_count:6d} iterations  {status}')
    lb, ub = pin(isl, l, u)
    isl.s.changeColsBounds(n, idx, lb, ub)
    if name.startswith('B'):
        # the second ranked objective of the proposal: least total flow, among the answers of the first
        both = (x[:R] > 1e-9) & (x[R:2 * R] > 1e-9)
        print(f'  after the first objective: routes with flow in both directions {int(both.sum())}')
        c2 = np.r_[np.ones(2 * R), np.zeros(n - 2 * R)]
        isl.s.changeColsCost(n, idx, c2)
        ms, x, info, status = timed(isl)
        both = (x[:R] > 1e-9) & (x[R:2 * R] > 1e-9)
        print(f'  second objective     {ms:7.0f} ms  {info.simplex_iteration_count:6d} iterations  {status}  both directions {int(both.sum())}')
        lb, ub = pin(isl, lb, ub)
        isl.s.changeColsBounds(n, idx, lb, ub)
        angle0, used0, served0, route0 = 2 * R, 2 * R + P, 2 * R + P + S, 0
    else:
        angle0, used0, served0, route0 = 0, P, P + S, None
    # Is the answer one? The range of some values over the best answers.
    live = int(np.flatnonzero(net['need'] > 0)[0])
    lo, hi = span(isl, angle0 + live, n, idx); print(f'  range of one angle over the best answers:  {lo:.4f} to {hi:.4f}')
    widths = []
    for j in rng.choice(S, 5, replace=False):
        lo, hi = span(isl, used0 + int(j), n, idx); widths.append(hi - lo)
    print(f'  width of the range of 5 sources:           {np.round(widths, 4)}')
    widths = []
    for j in rng.choice(P, 5, replace=False):
        lo, hi = span(isl, served0 + int(j), n, idx); widths.append(hi - lo)
    print(f'  width of the range of what 5 places get:   {np.round(widths, 4)}')
