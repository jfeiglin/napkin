"""The squared-distance step with `==`, `<=` and `>=` rows.

    min 1/2 sum_j w_j (x_j - c_j)^2    with   row_lower <= A x <= row_upper,   lower <= x <= upper

for w_j >= 0 (working units: w_j is 1 for a coordinate of the step, 0 for every other one).

Method, extending `scratch/networks/nearest.py`:
- fixed columns (lower == upper) leave the problem; a row with no column left is checked and dropped;
- each row with lower < upper gets a slack s in [lower, upper] and becomes `A x - s == 0`;
- a coordinate with no weight (a slack, an internal unknown, an unknown of a later stage) gets the
  proximal weight EPS around a centre that moves to its last value (the proximal point method): the
  answer of the true problem is a fixed point, and the method stops when the centres stop moving, so the
  stopping point meets the conditions of the true problem up to EPS times the last move;
- each proximal problem is solved on its dual by a semismooth Newton method: x(y) = clip(c - A'y / w)
  is in the box for every y, and the Newton step comes from the augmented system of the free
  coordinates (one factorization while the free set does not change), with an Armijo search;
- the stop rule is relative: each row residual below TOL times (1 + the size of the terms of the row).
  (The rule of `nearest.py`, an absolute 1e-10, is the one that was too strict.)
"""
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

EPS = 1e-3
TOL = 1e-9
RHO = 1e8
LM = False         # Levenberg-Marquardt delta from the residual (else 1e-14); used as a retry
SEARCH = 'armijo'  # or 'exact' (measured slower: measure.py, FINDINGS.md)


class Stats:
    def __init__(self):
        self.outer = self.newton = self.factorizations = 0
        self.residual = 0.0
        self.move = 0.0


def nearest(A, row_lower, row_upper, lower, upper, target, weight, tol=TOL, eps=EPS, max_outer=200,
            max_newton=200, stats=None, y0=None):
    """`y0`: duals of the rows to start from (as returned in stats.y)."""
    stats = stats or Stats()
    A = sp.csr_array(A, dtype=float)
    m, n = A.shape
    lower, upper = np.asarray(lower, float), np.asarray(upper, float)
    if np.any(lower > upper + tol * (1 + np.abs(lower))):
        raise ValueError('a column has an empty interval')
    fixed = upper <= lower
    x = np.where(fixed, lower, 0.0)
    free = np.flatnonzero(~fixed)
    shift = A[:, fixed.nonzero()[0]] @ lower[fixed] if fixed.any() else np.zeros(m)
    B = A[:, free].tocsr()
    lo_r, hi_r = row_lower - shift, row_upper - shift
    size = np.abs(A) @ np.where(np.isfinite(np.abs(x)), np.abs(x), 0.0) + np.abs(shift)
    empty = np.diff(B.indptr) == 0
    for i in np.flatnonzero(empty):
        slack = 1e-7 * (1.0 + size[i])     # the rows were met by an earlier stage to its tolerance
        if lo_r[i] > slack or hi_r[i] < -slack:
            raise ValueError(f'row {i} holds only fixed columns and does not hold')
    keep = np.flatnonzero(~empty)
    B, lo_r, hi_r = B[keep], lo_r[keep], hi_r[keep]
    eq = lo_r == hi_r
    ineq = np.flatnonzero(~eq)
    mk, nf, ns = B.shape[0], len(free), len(ineq)
    # variables z = (x_free, s); rows B x - S s = e
    S = sp.csr_array((np.ones(ns), (ineq, np.arange(ns))), shape=(mk, ns))
    E = sp.hstack([B, -S]).tocsr()
    e = np.where(eq, lo_r, 0.0)
    zl = np.r_[lower[free], lo_r[ineq]]
    zu = np.r_[upper[free], hi_r[ineq]]
    w = np.r_[np.asarray(weight, float)[free], np.zeros(ns)]
    prox = w <= 0
    w = np.where(prox, eps, w)
    c = np.r_[np.asarray(target, float)[free], np.zeros(ns)]
    # the first centres of the proximal coordinates: their target clipped, the slacks at B x of it
    c[:nf][prox[:nf]] = np.clip(c[:nf], zl[:nf], zu[:nf])[prox[:nf]]
    cx = np.clip(np.where(np.isfinite(c[:nf]), c[:nf], 0.0), zl[:nf], zu[:nf])
    c[nf:] = np.clip(B[ineq] @ cx, zl[nf:], zu[nf:])
    row_size = 1.0 + np.abs(e) + np.abs(B) @ np.abs(cx)
    ET = E.T.tocsr()
    N = nf + ns
    y = np.zeros(mk) if y0 is None else np.asarray(y0, float)[keep]
    solver = _Newton(E, ET, e, zl, zu, w, N, mk)
    z = None
    for outer in range(max_outer):
        z, y1, res = solver.solve(c, y, tol * row_size, max_newton, stats)
        if res > tol * float(row_size.max(initial=1.0)) and not solver.lm:
            solver.lm = True            # the retry: a singular Newton system, as in a set of no width
            z, y1, res = solver.solve(c, y, tol * row_size, max_newton, stats)
            solver.lm = LM
        y = y1
        stats.outer += 1
        move = float(np.abs(z[prox] - c[prox]).max(initial=0.0))
        stats.move, stats.residual = move, res
        c[prox] = z[prox]
        if move <= tol * (1.0 + float(np.abs(z[prox]).max(initial=0.0))):
            break
    x[free] = z[:nf]
    stats.y = np.zeros(m)
    stats.y[keep] = y
    return x, stats


class _Newton:
    def __init__(self, E, ET, e, zl, zu, w, N, m):
        self.E, self.ET, self.e, self.zl, self.zu, self.w, self.N, self.m = E, ET, e, zl, zu, w, N, m
        if m:
            K = sp.block_array([[sp.diags_array(np.ones(N)), ET], [E, sp.diags_array(-np.ones(m))]]).tocsc()
            K.sort_indices()
            diag = np.empty(N + m, dtype=np.int64)
            for j in range(N + m):
                lo, hi = K.indptr[j], K.indptr[j + 1]
                diag[j] = lo + np.searchsorted(K.indices[lo:hi], j)
            self.K, self.diag = K, diag
        self.kept = None
        self.lm = LM

    def point(self, c, y):
        z = np.clip(c - (self.ET @ y) / self.w, self.zl, self.zu)
        r = self.E @ z - self.e
        q = 0.5 * float(self.w @ (z - c) ** 2) + float(y @ r)
        return z, r, q

    def search(self, c, y, step, slope0):
        """The exact step along `step`: the derivative of the dual along it is piecewise linear and falls;
        between events its slope is minus the sum of w g^2 over the coordinates that are free."""
        u = c - (self.ET @ y) / self.w
        g = (self.ET @ step) / self.w
        mv = g != 0
        u, g, w, zl, zu = u[mv], g[mv], self.w[mv], self.zl[mv], self.zu[mv]
        with np.errstate(divide='ignore', invalid='ignore'):
            a_l = np.where(np.isfinite(zl), (u - zl) / g, np.where(g > 0, np.inf, -np.inf))
            a_u = np.where(np.isfinite(zu), (u - zu) / g, np.where(g > 0, -np.inf, np.inf))
        enter, leave = np.minimum(a_l, a_u), np.maximum(a_l, a_u)
        wg2 = w * g * g
        now = (enter <= 0) & (leave > 0)
        later = enter > 0
        alphas = np.r_[enter[later], leave[(now | later) & np.isfinite(leave)]]
        change = np.r_[-wg2[later], wg2[(now | later) & np.isfinite(leave)]]
        order = np.argsort(alphas, kind='stable')
        alphas, change = alphas[order], change[order]
        slopes = -float(wg2[now].sum()) + np.r_[0.0, np.cumsum(change)]
        widths = np.diff(np.r_[0.0, alphas])
        values = slope0 + np.cumsum(slopes[:-1] * widths)
        at = np.flatnonzero(values <= 0.0)
        if not len(at):
            last = slopes[-1]
            base = float(values[-1]) if len(values) else slope0
            left = float(alphas[-1]) if len(alphas) else 0.0
            return left + base / -last if last < 0 else None
        k = int(at[0])
        before = slope0 if k == 0 else float(values[k - 1])
        left = 0.0 if k == 0 else float(alphas[k - 1])
        return left + before / -slopes[k] if slopes[k] < 0 else left

    def solve(self, c, y, tol, max_newton, stats):
        z, r, q = self.point(c, y)
        if not self.m:
            return z, y, 0.0
        for it in range(max_newton):
            if np.all(np.abs(r) <= tol):
                return z, y, float(np.abs(r).max(initial=0.0))
            u = c - (self.ET @ y) / self.w
            free = (u > self.zl) & (u < self.zu)
            # Levenberg-Marquardt: delta follows the residual (a power of ten, so that a factorization
            # serves while the free set and delta stay)
            size = float(np.abs(r).max())
            delta = 10.0 ** np.clip(np.ceil(np.log10(size)) - 2, -14, -4) if self.lm else 1e-14
            key = (free.tobytes(), delta)
            if self.kept is None or self.kept[0] != key:
                self.K.data[self.diag] = np.r_[np.where(free, self.w, self.w * (1.0 + RHO)), np.full(self.m, -delta)]
                self.kept = (key, splu(self.K, permc_spec='MMD_AT_PLUS_A'))
                stats.factorizations += 1
            step = self.kept[1].solve(np.r_[np.zeros(self.N), -r])[self.N:]
            # dual ascent: the gradient of q is r, and the step solves (E D E' + delta) step = r
            slope = float(r @ step)
            if slope <= 0:
                step, slope = r.copy(), float(r @ r)
            if SEARCH == 'armijo':
                alpha, q0 = 1.0, q
                for _ in range(60):
                    if self.point(c, y + alpha * step)[2] >= q0 + 1e-4 * alpha * slope:
                        break
                    alpha *= 0.5
            else:
                alpha = self.search(c, y, step, slope)
            if alpha is None:
                raise ValueError('the conditions cannot hold together (the dual has no maximum)')
            z1, r1, q1 = self.point(c, y + alpha * step)
            y = y + alpha * step
            z, r, q = z1, r1, q1
            stats.newton += 1
        return z, y, float(np.abs(r).max(initial=0.0))


# -- the reference: enumerate the active sets ------------------------------------------------------
def exact(A, row_lower, row_upper, lower, upper, target, weight):
    """Brute force for a small problem with positive weights: for each set of active constraints, the
    nearest point of its affine hull; the best feasible one is the answer."""
    import itertools
    A = np.atleast_2d(np.asarray(A, float))
    m, n = A.shape
    G = np.vstack([A, np.eye(n)])
    gl = np.r_[row_lower, lower]
    gu = np.r_[row_upper, upper]
    W = np.sqrt(np.asarray(weight, float))
    best, value = None, np.inf
    options = []
    for i in range(m + n):
        o = [None]
        if np.isfinite(gl[i]):
            o.append(gl[i])
        if np.isfinite(gu[i]) and gu[i] != gl[i]:
            o.append(gu[i])
        if gl[i] == gu[i]:
            o = [gl[i]]
        options.append(o)
    for choice in itertools.product(*options):
        act = [i for i, v in enumerate(choice) if v is not None]
        if len(act) > n:
            continue
        # min |W (x - c)|^2 with G_act x = v: x = c + W^-2 G' mu
        if act:
            Ga = G[act]
            v = np.array([choice[i] for i in act])
            M = Ga @ np.diag(1 / W ** 2) @ Ga.T
            mu, *_ = np.linalg.lstsq(M, v - Ga @ target, rcond=None)
            x = target + np.diag(1 / W ** 2) @ Ga.T @ mu
            if np.abs(Ga @ x - v).max() > 1e-9:
                continue
        else:
            x = np.array(target, float)
        g = G @ x
        if np.all(g >= gl - 1e-9) and np.all(g <= gu + 1e-9):
            f = float(((W * (x - target)) ** 2).sum())
            if f < value - 1e-12:
                best, value = x, f
    return best
