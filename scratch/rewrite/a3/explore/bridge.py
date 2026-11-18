"""A five-route bridge where a place that takes more than its request lowers the total unmet.
Places J (source 10), X (need 0.1), Y (need 0), B (need 10). Routes with strength: J-X 2, J-Y 1, X-B 1,
Y-B 2, X-Y 1 with capacity 0.1 (the bridge). Run: python bridge.py"""
import sys
sys.path.insert(0, '/home/user/napkin/scratch/rewrite/a3')
import numpy as np
from network import program
from solve.lp import Kept
net = dict(places=4, sources=1, routes=5, at=np.array([0]), pmax=np.array([10.0]),
           frm=np.array([0, 0, 1, 2, 1]), to=np.array([1, 2, 3, 3, 2]), b=np.array([2.0, 1, 1, 2, 1]),
           cap=np.array([100.0, 100, 100, 100, 0.1]), need=np.array([0.0, 0.1, 0.0, 10.0]))
for shortfall in (True, False):
    A, rl, ru, lo, hi, at = program(net, shortfall=shortfall)
    cost = np.zeros(A.shape[1])
    if shortfall: cost[at['short']] = 1.0
    else: cost[at['use']] = -1.0
    x = Kept(A, rl, ru, lo, hi, cost).solve()[0]
    use = x[at['use']]
    print(f"use {'unbounded' if shortfall else '<= need  '}: use J X Y B = {np.round(use, 4)}, "
          f"unmet {np.maximum(net['need'] - use, 0).sum():.4f}, levels {np.round(x[at['level']], 4)}")
