"""What does one more run of a kept instance cost when almost nothing changed?"""
import sys, time
sys.path.insert(0, '/home/user/napkin/scratch/rewrite/a3')
import numpy as np, scipy.sparse as sp
from network import network, program, damaged, layout
from solve.lp import Kept, OPTIMAL, INF
share = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
net = network(int(30000 * share), int(35000 * share), int(15000 * share))
A, rl, ru, lo, hi, at = program(net, shortfall=True)
n = A.shape[1]
cost = np.zeros(n); cost[at['short']] = 1.0
def trial(**opts):
    k = Kept(A, rl, ru, lo, hi, cost)
    for name, value in opts.items():
        k.s.setOptionValue(name, value)
    t = time.perf_counter(); status, x, d, r, y, val = k.run(); cold = time.perf_counter() - t
    out = []
    for kind in ('nothing', 'same bound', 'tiny bound', 'cost'):
        ts = []
        for rep in range(3):
            j = int(at['supply'][rep])
            if kind == 'same bound':
                k.set_bounds([j], [lo[j]], [hi[j]])
            elif kind == 'tiny bound':
                k.set_bounds([j], [lo[j]], [hi[j] * (1 - 1e-9 * (rep + 1))])
            elif kind == 'cost':
                c = cost.copy(); c[at['short'][rep]] = 1.0 + 1e-9; k.set_cost(c)
            t = time.perf_counter(); k.s.run(); ts.append(time.perf_counter() - t)
            it = k.s.getInfo().simplex_iteration_count
        out.append(f'{kind}: {min(ts)*1000:.1f} ms ({it} it)')
    t = time.perf_counter(); sol = k.s.getSolution(); a = np.array(sol.col_value); b = np.array(sol.row_dual); g = time.perf_counter() - t
    print(opts, f'cold {cold:.2f}s', '; '.join(out), f'; read solution {g*1000:.1f} ms')
trial()
trial(simplex_strategy=4)
trial(simplex_scale_strategy=0)
trial(simplex_scale_strategy=0, simplex_strategy=4)
