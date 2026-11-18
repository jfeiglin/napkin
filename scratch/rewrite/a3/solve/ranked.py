"""Ranked linear objectives on one kept instance, each attained optimum kept.

Two ways to keep an optimum, both here so that `measure.py` can compare them:

- `pin` (chosen): after objective k, a column with a reduced cost goes to the bound it rests on, and a
  row with a dual becomes an equality on its active side. For one optimal dual y, the answers that meet
  complementary slackness with y are exactly the optimal answers, so this is the optimal face itself,
  with no new row. The bounds are tightened in place; the caller keeps the arrays for the distance step.
- `row`: a new row `c.x <= optimum + tol * max(1, |optimum|)`. Simple, but the row is dense and later
  ranks may spend the slack.

All values are in working units (`form.Work`): each cost is scaled to a largest entry of one.
"""
import numpy as np
import scipy.sparse as sp

TAU = 1e-9      # a reduced cost or a dual above this is not zero (working units)
TOL = 1e-9      # relative tolerance of a kept optimum


class Face:
    """The feasible set as it narrows: bounds of columns and rows, and rows added by later ranks."""

    def __init__(self, lower, upper, row_lower, row_upper):
        self.lower, self.upper = lower.copy(), upper.copy()
        self.row_lower, self.row_upper = row_lower.copy(), row_upper.copy()
        self.extra = []          # (sparse rows over the columns, lower, upper)

    def add(self, rows, lower, upper):
        self.extra.append((sp.csr_array(rows), np.asarray(lower, float), np.asarray(upper, float)))


def pin(kept, face, x, d, y, tau=TAU):
    """Narrow `face` (and the kept instance) to the optimal face of the last solve."""
    lo, hi = face.lower, face.upper
    up = (d > tau) & np.isfinite(lo) & (hi > lo)
    down = (d < -tau) & np.isfinite(hi) & (hi > lo)
    hi[up] = lo[up]
    lo[down] = hi[down]
    cols = np.flatnonzero(up | down)
    kept.set_bounds(cols, lo[cols], hi[cols])
    rl, ru = face.row_lower, face.row_upper
    m = len(rl)
    yy = y[:m]
    low = (yy > tau) & np.isfinite(rl) & (ru > rl)
    high = (yy < -tau) & np.isfinite(ru) & (ru > rl)
    ru[low] = rl[low]
    rl[high] = ru[high]
    rows = np.flatnonzero(low | high)
    kept.set_row_bounds(rows, rl[rows], ru[rows])
    return len(cols), len(rows)


def optimize(kept, face, costs, method='pin', tau=TAU, tol=TOL):
    """Each cost in written order. Returns (x, optima, stats). With no cost, one feasibility solve."""
    n = kept.n
    optima, stats = [], []
    if not costs:
        kept.set_cost(np.zeros(n))
        x, d, r, y, value = kept.solve('the hard constraints')
        return x, optima, stats
    for k, cost in enumerate(costs):
        kept.set_cost(np.r_[cost, np.zeros(n - len(cost))])
        x, d, r, y, value = kept.solve(f'objective {k + 1}')
        optima.append(value)
        if k == len(costs) - 1 and method == 'pin':
            # the last objective is pinned too: the later ranks must keep it
            pass
        if method == 'pin':
            stats.append(pin(kept, face, x, d, y, tau))
        else:
            c = sp.csr_array(cost.reshape(1, -1))
            bound = value + tol * max(1.0, abs(value))
            kept.add_rows([-np.inf], [bound], sp.hstack([c, sp.csr_array((1, n - len(cost)))]))
            face.add(c, [-np.inf], [bound])
            stats.append((0, 1))
    kept.set_cost(np.zeros(n))
    return x, optima, stats


def check(costs, optima, x, tol=1e-7):
    """Each optimum is kept at `x` within the tolerance: the list of the ranks that are not."""
    bad = []
    for k, (cost, best) in enumerate(zip(costs, optima)):
        value = float(cost @ x[:len(cost)])
        scale = max(1.0, float(np.abs(cost) @ np.abs(x[:len(cost)])))
        if value > best + tol * scale:
            bad.append((k, value, best))
    return bad
