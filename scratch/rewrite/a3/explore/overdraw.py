"""Find a small network where a place that takes more than its request lowers the total unmet.
Run: python overdraw.py [TRIALS]"""
import sys
sys.path.insert(0, '/home/user/napkin/scratch/rewrite/a3')
import numpy as np
from network import network, program
from solve.lp import Kept

trials = int(sys.argv[1]) if len(sys.argv) > 1 else 300
found = 0
for seed in range(trials):
    places = 8 + seed % 6
    net = network(places, places + 3, 2, seed=seed)
    need = net['need'] * 2.0
    out = []
    for shortfall in (True, False):
        A, rl, ru, lo, hi, at = program(net, need=need, shortfall=shortfall)
        cost = np.zeros(A.shape[1])
        if shortfall:
            cost[at['short']] = 1.0
        else:
            cost[at['use']] = -1.0
        x, d, r, y, v = Kept(A, rl, ru, lo, hi, cost).solve()
        unmet = np.maximum(need - x[at['use']], 0).sum()
        out.append((unmet, x[at['use']] - need))
    if out[0][0] < out[1][0] - 1e-6:
        found += 1
        over = np.flatnonzero(out[0][1] > 1e-6)
        print(f'seed {seed} places {places}: unmet {out[0][0]:.4f} (use unbounded) against {out[1][0]:.4f} (use <= need); '
              f'over-request at {over.tolist()} by {np.round(out[0][1][over], 4).tolist()}')
print(f'{found} of {trials}')
