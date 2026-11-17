"""The nearest point: min 1/2 sum ((x - n) / (u - l))^2  s.t.  E x = e,  l <= x <= u.

In the coordinates xi = (x - l) / (u - l) the criterion is the plain distance, and the box is [0, 1].
A variable with l == u is a constant. The method is a regularized semismooth Newton method on the dual
(the primal-dual active set step, with a Levenberg-Marquardt term and a line search). The step is
computed from the augmented (KKT) system of the free variables, so the condition of E is not squared.
For any multipliers lam, x(lam) is in the box and stationary: the only thing left is E x = e."""
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

class Stats:
    def __init__(self):
        self.factorizations = self.solves = self.iterations = self.backtracks = 0
        self.log = []

class Nearest:
    def __init__(self, E, e, l, u, n):
        E = sp.csr_array(E, dtype=float)
        self.l, self.u = l, u
        self.fixed = u <= l
        self.var = np.flatnonzero(~self.fixed)
        span = (u - l)[self.var]
        e0 = e - E @ np.where(self.fixed, l, 0.0) - E[:, self.var] @ l[self.var]
        A = E[:, self.var] @ sp.diags_array(span)           # columns scaled: xi in [0, 1]
        A = A.tocsr()
        norm = np.sqrt(np.asarray(A.multiply(A).sum(axis=1)).ravel())
        self.empty = norm == 0                               # a row with no variable left
        self.rowscale = np.where(self.empty, 1.0, 1.0 / np.where(norm == 0, 1.0, norm))
        self.A = (sp.diags_array(self.rowscale) @ A).tocsr()
        self.b = e0 * self.rowscale
        self.nu = ((n - l)[self.var]) / span
        self.span = span
        self.m, self.N = self.A.shape
        self.AT = self.A.T.tocsr()

    def x_of(self, xi):
        x = self.l.copy()
        x[self.var] = self.l[self.var] + self.span * xi
        return x

    def q(self, lam):
        z = self.nu - self.AT @ lam
        xi = np.clip(z, 0.0, 1.0)
        return float(0.5 * ((xi - self.nu) ** 2).sum() + lam @ (self.A @ xi - self.b)), xi, z

    def search(self, z, g, slope0):
        """The step alpha >= 0 that maximizes the dual along a direction: phi'(alpha) is piecewise linear
        and falls; its slope is minus the sum of g^2 over the variables that are free at alpha. None when
        phi' stays above zero: the dual has no maximum that way, so the conditions cannot hold."""
        moving = g != 0
        zm, gm = z[moving], g[moving]
        with np.errstate(divide='ignore', invalid='ignore'):
            a0, a1 = zm / gm, (zm - 1.0) / gm      # where z - alpha g is 0, and where it is 1
        first, last = np.minimum(a0, a1), np.maximum(a0, a1)
        g2 = gm * gm
        free_now = (zm > 0.0) & (zm < 1.0)
        # On the box or outside it, and moving into it: at a bound exactly, it is free at once.
        enters = ((zm <= 0.0) & (gm < 0)) | ((zm >= 1.0) & (gm > 0))
        leaves = free_now | enters
        alphas = np.r_[np.maximum(first[enters], 0.0), last[leaves]]
        change = np.r_[-g2[enters], g2[leaves]]
        order = np.argsort(alphas, kind='stable')
        alphas, change = alphas[order], change[order]
        slope = -float(g2[free_now].sum())
        slopes = slope + np.r_[0.0, np.cumsum(change)]          # the slope after each event
        widths = np.diff(np.r_[0.0, alphas])
        values = slope0 + np.cumsum(slopes[:-1] * widths)        # phi' at each event
        at = np.flatnonzero(values <= 0.0)
        if not len(at):
            return None
        k = int(at[0])
        before = slope0 if k == 0 else float(values[k - 1])
        left = 0.0 if k == 0 else float(alphas[k - 1])
        return left + before / -slopes[k] if slopes[k] < 0 else left

    def solve(self, lam=None, tol=1e-10, max_iter=100, stats=None, verbose=False, rho=1e8, delta=1e-14):
        """Each step: (A D^-1 A') step = residual, with D = 1 for a free variable and 1 + rho for a
        variable at a bound, from the augmented system (one pattern for every step); then the exact
        line search on the dual."""
        A, b, nu, m, N = self.A, self.b, self.nu, self.m, self.N
        stats = stats or Stats()
        if (np.abs(b[self.empty]) > tol).any():
            return None, lam, 'a condition with no value left to find does not hold', stats
        lam = np.zeros(m) if lam is None else lam.copy()
        q, xi, z = self.q(lam)
        if not hasattr(self, 'K'):
            K = sp.block_array([[sp.eye_array(N), self.AT], [A, -delta * sp.eye_array(m)]]).tocsc()
            K.sort_indices()
            # the places of the diagonal of the first block in the data of K
            diag = np.empty(N, dtype=np.int64)
            for j in range(N):
                lo, hi = K.indptr[j], K.indptr[j + 1]
                diag[j] = lo + np.searchsorted(K.indices[lo:hi], j)
            self.K, self.diag = K, diag
        kept = None
        for it in range(max_iter):
            r = A @ xi - b
            size = float(np.abs(r).max(initial=0.0))
            free = (z > 0.0) & (z < 1.0)
            stats.log.append((it, int(free.sum()), size))
            if verbose:
                print(f'   it {it}: free {int(free.sum())} residual {size:.3e} q {q:.12g}')
            if size <= tol:
                stats.iterations += it
                return xi, lam, None, stats
            key = free.tobytes()
            if kept is None or kept[0] != key:
                self.K.data[self.diag] = np.where(free, 1.0, 1.0 + rho)
                kept = (key, splu(self.K, permc_spec='MMD_AT_PLUS_A'))
                stats.factorizations += 1
            step = kept[1].solve(np.r_[np.zeros(N), -r])[N:]; stats.solves += 1
            slope0 = float(r @ step)
            if slope0 <= 0:
                stats.iterations += it
                return xi, lam, 'no ascent', stats
            alpha = self.search(z, self.AT @ step, slope0)
            if alpha is None:
                stats.iterations += it
                return xi, lam, 'the conditions cannot hold together', stats
            stats.backtracks += abs(alpha - 1.0) > 1e-6
            lam = lam + alpha * step
            q, xi, z = self.q(lam)
        stats.iterations += max_iter
        return xi, lam, 'no convergence', stats

    def polish(self, lam):
        """One exact solve of the final active set with a refinement step, and what it misses."""
        _, xi, z = self.q(lam)
        free = (z > 0.0) & (z < 1.0)
        F = np.flatnonzero(free)
        AF = self.A[:, F]
        K = sp.block_array([[sp.eye_array(len(F)), AF.T], [AF, -1e-12 * sp.eye_array(self.m)]]).tocsc()
        lu = splu(K, permc_spec='MMD_AT_PLUS_A')
        rhs = np.r_[self.nu[F], self.b - self.A @ np.where(free, 0.0, xi)]
        K0 = sp.block_array([[sp.eye_array(len(F)), AF.T], [AF, None]]).tocsc()
        sol = lu.solve(rhs)
        for _ in range(2):
            sol += lu.solve(rhs - K0 @ sol)
        out = xi.copy(); out[F] = sol[:len(F)]
        outside = float(max((-out).max(initial=0.0), (out - 1.0).max(initial=0.0)))
        return out, sol[len(F):], float(np.abs(self.A @ out - self.b).max(initial=0.0)), outside
