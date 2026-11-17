import numpy as np, scipy.sparse as sp
from nearest import Nearest
rng = np.random.default_rng(0)
bad = 0
for trial in range(300):
    m, N = 4, 9
    E = sp.csr_array(rng.normal(size=(m, N)) * (rng.random((m, N)) < 0.6))
    l = np.zeros(N); u = rng.uniform(0.5, 2, N); n = np.where(rng.random(N) < 0.5, u, rng.uniform(0, 1, N) * u)
    p = Nearest(E, rng.normal(size=m), l, u, n)
    lam = rng.normal(size=p.m) * (trial % 3)
    d = rng.normal(size=p.m)
    q0, xi, z = p.q(lam)
    slope0 = float((p.A @ xi - p.b) @ d)
    if slope0 <= 0: d, slope0 = -d, -slope0
    a = p.search(z, p.AT @ d, slope0)
    grid = np.linspace(0, 50, 20001)
    vals = np.array([p.q(lam + t * d)[0] for t in grid[:4000]])
    if a is None:
        ok = vals[-1] >= vals.max() - 1e-9
    else:
        ok = p.q(lam + a * d)[0] >= vals.max() - 1e-7
    bad += not ok
print('line search wrong in', bad, 'of 300')
