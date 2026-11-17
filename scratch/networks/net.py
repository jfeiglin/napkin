"""A synthetic network of places, routes and sources, as arrays (S0 experiments; outside the repo)."""
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import minimum_spanning_tree, connected_components
from scipy.spatial import cKDTree


def network(places=30000, routes=35000, sources=15000, seed=0):
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
    ncomp, _ = connected_components(graph, directed=False)
    edges = {(min(a, b), max(a, b)) for a, b in zip(tree.row.tolist(), tree.col.tolist())}
    # the shortest other neighbour edges, until `routes`
    g = sp.triu(graph).tocoo()
    order = np.argsort(g.data)
    for i in order.tolist():
        if len(edges) >= routes:
            break
        edges.add((int(g.row[i]), int(g.col[i])))
    edges = np.array(sorted(edges))[:routes]
    frm, to = edges[:, 0], edges[:, 1]
    length = np.linalg.norm(xy[frm] - xy[to], axis=1)
    b = 1.0 / np.maximum(length, 1e-4) * 0.01  # susceptance
    need = rng.uniform(0.2, 2.0, places)
    at = rng.integers(0, places, sources)  # the place of each source
    pmax = rng.uniform(1.0, 20.0, sources)
    pmax *= 1.6 * need.sum() / pmax.sum()  # 60% reserve
    p0 = pmax * need.sum() / pmax.sum()  # normal output: all in proportion
    return dict(xy=xy, frm=frm, to=to, b=b, need=need, at=at, pmax=pmax, p0=p0, components=ncomp,
                places=places, routes=len(edges), sources=sources)


def incidence(net, up=None):
    """C (routes x places): +1 at from, -1 at to."""
    R, P = net['routes'], net['places']
    C = sp.coo_array((np.r_[np.ones(R), -np.ones(R)], (np.r_[np.arange(R), np.arange(R)], np.r_[net['frm'], net['to']])), shape=(R, P)).tocsr()
    return C

if __name__ == '__main__':
    import time
    t = time.perf_counter(); n = network(); print(time.perf_counter() - t, n['routes'], n['components'])
    deg = np.bincount(np.r_[n['frm'], n['to']], minlength=n['places'])
    print('degree', deg.min(), deg.mean(), deg.max())
