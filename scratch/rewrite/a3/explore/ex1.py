import sys, time
sys.path.insert(0, '/home/user/napkin/scratch/rewrite/a3')
import numpy as np, scipy.sparse as sp
from network import network, program, damaged, layout
from solve.lp import Kept, OPTIMAL

share = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
t = time.perf_counter()
net = network(int(30000 * share), int(35000 * share), int(15000 * share))
print('network', time.perf_counter() - t, net['routes'])
P, S, R = net['places'], net['sources'], net['routes']
for label, need, up in (('normal', net['need'], None), ('need x1.45', net['need'] * 1.45, None), ('damaged 1000', net['need'], damaged(net, int(1000 * share)))):
    for shortfall in (True, False):
        A, rl, ru, lo, hi, at = program(net, need=need, up=up, shortfall=shortfall)
        n = A.shape[1]
        cost = np.zeros(n)
        if shortfall:
            cost[at['short']] = 1.0
        else:
            cost[at['use']] = -1.0
        t = time.perf_counter(); k = Kept(A, rl, ru, lo, hi, cost); tb = time.perf_counter() - t
        t = time.perf_counter(); status, x, d, r, y, val = k.run(); ts = time.perf_counter() - t
        unmet = need - x[at['use']]
        print(f'{label:14s} shortfall={shortfall!s:5s} rows {A.shape[0]} cols {n} nnz {A.nnz}: build {tb:.2f}s cold {ts:.2f}s iters {k.last_iterations} status {str(status).split(".")[-1]} total unmet {np.maximum(unmet,0).sum():.4f} places short {(unmet > 1e-7).sum()} max level {np.abs(x[at["level"]]).max():.2f}')
