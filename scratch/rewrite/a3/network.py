"""The synthetic network of the earlier trials (`scratch/networks/net.py`, copied), and the
route-and-level program of the specification on it, as sparse arrays.

Each place has a level (a unitless unknown in [-30, 30] with the reference value zero), a store held
at zero, a flow `use` to outside with a request (its need), and the sources at it (flows from outside
with a capacity). Each route has one signed rate, a capacity for its magnitude and the law

    carried == strength * (level of its origin - level of its destination)      (0 when it is down).

`program` gives the columns in the order: level[P], supply[S], use[P], carried[R], short[P].
`short` is the positive-part shortfall of each place, an extra unknown with `use + short >= need`.
"""
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import minimum_spanning_tree
from scipy.spatial import cKDTree

INF = np.inf


def network(places=30000, routes=35000, sources=15000, seed=0):
    """`scratch/networks/net.py`, with the strengths of `e6_full.py` (b * 100) and its route capacities."""
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 1, (places, 2))
    k = 6
    dist, near = cKDTree(xy).query(xy, k + 1)
    rows = np.repeat(np.arange(places), k)
    cols = near[:, 1:].ravel()
    d = dist[:, 1:].ravel()
    graph = sp.coo_array((d, (rows, cols)), shape=(places, places)).tocsr()
    graph = graph.maximum(graph.T)
    tree = minimum_spanning_tree(graph).tocoo()
    edges = {(min(a, b), max(a, b)) for a, b in zip(tree.row.tolist(), tree.col.tolist())}
    g = sp.triu(graph).tocoo()
    for i in np.argsort(g.data).tolist():
        if len(edges) >= routes:
            break
        edges.add((int(g.row[i]), int(g.col[i])))
    edges = np.array(sorted(edges))[:routes]
    frm, to = edges[:, 0], edges[:, 1]
    length = np.linalg.norm(xy[frm] - xy[to], axis=1)
    b = 1.0 / np.maximum(length, 1e-4)
    need = rng.uniform(0.2, 2.0, places)
    at = rng.integers(0, places, sources)
    pmax = rng.uniform(1.0, 20.0, sources)
    pmax *= 1.6 * need.sum() / pmax.sum()
    cap = np.random.default_rng(3).uniform(2.0, 12.0, len(edges))
    return dict(xy=xy, frm=frm, to=to, b=b, need=need, at=at, pmax=pmax, cap=cap,
                places=places, routes=len(edges), sources=sources)


def layout(net):
    P, S, R = net['places'], net['sources'], net['routes']
    level = np.arange(P)
    supply = P + np.arange(S)
    use = P + S + np.arange(P)
    carried = 2 * P + S + np.arange(R)
    short = 2 * P + S + R + np.arange(P)
    return dict(level=level, supply=supply, use=use, carried=carried, short=short, n=3 * P + S + R)


def program(net, need=None, up=None, level_range=30.0, shortfall=True):
    """(A, row_lower, row_upper, lower, upper) of the route-and-level network, and its layout.

    Rows: balance[P] (==), law[R] (==), and with `shortfall` unmet[P] (use + short >= need)."""
    P, S, R = net['places'], net['sources'], net['routes']
    need = net['need'] if need is None else need
    up = np.ones(R) if up is None else up
    at = layout(net)
    n = at['n'] if shortfall else at['n'] - P
    r = np.arange(R)
    # balance of place p: supply into it + carried into it - carried out of it - use == 0
    rows = [net['at'], np.arange(P), net['frm'], net['to']]
    cols = [at['supply'], at['use'], at['carried'], at['carried']]
    vals = [np.ones(S), -np.ones(P), -np.ones(R), np.ones(R)]
    # law of route r: carried - pull * (level[frm] - level[to]) == 0
    pull = net['b'] * up
    rows += [P + r, P + r, P + r]
    cols += [at['carried'], at['level'][net['frm']], at['level'][net['to']]]
    vals += [np.ones(R), -pull, pull]
    m = P + R
    if shortfall:
        rows += [m + np.arange(P), m + np.arange(P)]
        cols += [at['use'], at['short']]
        vals += [np.ones(P), np.ones(P)]
        m += P
    A = sp.coo_array((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(m, n)).tocsr()
    row_lower = np.zeros(m)
    row_upper = np.zeros(m)
    lower = np.zeros(n)
    upper = np.full(n, INF)
    lower[at['level']], upper[at['level']] = -level_range, level_range
    upper[at['supply']] = net['pmax']
    lower[at['carried']], upper[at['carried']] = -net['cap'] * up, net['cap'] * up
    if shortfall:
        row_lower[P + R:] = need
        row_upper[P + R:] = INF
    else:
        upper[at['use']] = need
    return A, row_lower, row_upper, lower, upper, at


def damaged(net, count, seed=3):
    """`up` with `count` routes down."""
    up = np.ones(net['routes'])
    up[np.random.default_rng(seed).choice(net['routes'], count, replace=False)] = 0.0
    return up
