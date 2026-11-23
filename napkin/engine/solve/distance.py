"""The two distance steps of the selection order: the flows nearest their targets, then, with the
flows fixed, the other unknowns nearest their references (spec: "Final targets for flows and other
unknowns"). Each stage solves

    min 1/2 sum_j w_j (x_j - c_j)^2   with   row_lower <= A x <= row_upper,   lower <= x <= upper

in working units on the face that the earlier ranks left, where w_j is one for each coordinate of the
stage and zero for every other one (the INTERNAL unknowns, and the unknowns of the other stage). The
criterion is strictly convex in the coordinates of the stage, so their answer is unique.

The method is the dual semismooth Newton method of `scratch/networks/nearest.py` at af5428b: for each dual y,
x(y) = clip(c - A'y / w) is in the box, so only the rows are left to meet; each Newton step solves the
augmented system of the free coordinates, so the condition of A is not squared, with one factorization
while the free set stays, and an exact line search (the dual is piecewise quadratic along a step).
With rows that are all equalities and weights that are all positive, that is the whole method.
Prototype A3 adds two parts, where they are needed:

- a row with lower < upper gets a slack s in [lower, upper] and becomes A x - s == 0;
- a coordinate with no weight (a slack, an INTERNAL unknown, an unknown of the other stage) gets a
  proximal weight around a centre that moves to its last value (the proximal point method), until
  the weight times the last move, which is what the proximal term leaves in the conditions of the
  true problem, is within the tolerance of the rows.

Two changes to A3's method make it converge on the face that fair sharing leaves, where A3's did not
(1,200 Newton steps at 3,000 places):

- The line search stays exact with slacks too, where A3 used Armijo's. Each held claim has a width
  of about 1e-7, the dual is nearly flat outside it, and every coordinate can rest on a bound, so the
  Newton step is huge; Armijo's backtracking from a whole step stalls far from the maximum (the two
  bottlenecks: no convergence in 200 steps), where the exact search, which does not depend on the
  length of the step, converges in 3.
- The proximal weight starts at EPS_START, the weight of a coordinate of the stage, and falls tenfold
  after each proximal problem that took at most SETTLED Newton steps, down to A3's EPS. With A3's
  weight from the start, a zero-weight level moves a thousand times as far as the dual, the free set
  changes at every step, and the first problem does not converge in 400 steps; with the weight one
  throughout, 176 proximal problems are needed. The schedule took 9 (101 Newton steps, 3.1 s).

The rows are met to TOL of their size where the method gets there. The earlier ranks met them only
to HiGHS's tolerance, so where the method stalls (STALL steps that do not halve the largest
residual) with every row met to FEASIBLE, they count as met to that precision, and so does the stop
rule of the proximal method. (At 1,000 places with shortage, the first proximal problem cycled at a
residual of 1.9e-7 for 900 steps before it reached 4e-12.)

The Newton system [[D, E'], [E, -delta I]] has D > 0 and delta > 0: it is quasi-definite, so it has
an LDL' factorization in any symmetric order. Its pattern stays over a stage and only its diagonal
follows the free set, so `qdldl` (OSQP's LDL', Apache-2.0) orders it and analyses its pattern once a
stage, and each new diagonal is a numeric factorization alone, where SuperLU orders and pivots
afresh each time; each solve is refined REFINE times against the system, since LDL' does not pivot.
At 30,000 places at normal need the method then takes its 446 steps in 45 s instead of 342 s
(`scratch/rewrite/p1/adopted.py` at af5428b); in prototype P1 its answers were within 6e-7 of SuperLU's. Without pivoting LDL' is not as sure: with
weights up to 1 + RHO and delta = DELTA, a solve's backward error |K x - b| / (|K| |x| + |b|) rose
to 0.15 on the objective's face of 3,000 places, where SuperLU's stays below 1e-15, and on another
face its steps, accurate to 1e-12, stalled where SuperLU's converged. So a stage starts by LDL' and
goes on by SuperLU from the dual point that it has reached, for the rest of the stage, at its first
solve whose backward error is above ACCURATE or a factorization that LDL' refuses; and a stage that
does not converge so within its Newton steps runs again by SuperLU alone, within as many. Every step
keeps the method's rules; only the factorization of its system changes.

Budget: the Newton steps of one stage, for each of its two runs. A stage whose method does not
converge within them, or whose line search finds no maximum of the dual, goes to the QP of HiGHS,
the exact fallback, with a budget of QP iterations; a QP that does not finish within them stops the
solve with 'distance budget exceeded'. (A3: on the face that fair sharing leaves at 3,000 places the
method did not converge in 1,200 Newton steps; the QP took 38 s and 20,561 iterations.) The fallback
is not a sure answer: on that face at 3,000 places it now ends with an error of HiGHS (a numerical
failure), and on the fair face of the spec's worked network, three places, it cycles to its
iteration limit. At 300 and 1,000 places it finishes and agrees with the method to 6.4e-7
(`scratch/rewrite/b1/solve/bench.py verify` at af5428b).
"""

from __future__ import annotations

import numpy as np
import qdldl
import scipy.sparse as sp
from scipy.sparse.linalg import splu

from .failures import DISTANCE_BUDGET, NUMERICAL, SolveFailure
from .kept import OPTIMAL, Status, quadratic
from .problem import FLOW, OTHER
from .scaled import row_max

EPS_START = 1.0  # the first proximal weight of a coordinate with no weight
EPS = 1e-3  # its last proximal weight
SETTLED = 3  # a proximal problem solved in this many Newton steps lowers the weight tenfold
TOL = 1e-9  # a row is met when its residual is below this times (1 + the size of its terms)
FEASIBLE = 1e-7  # or below this, HiGHS's tolerance, to which the ranks met the rows, once it stalls
STALL = 10  # Newton steps that do not halve the largest residual make a stall
LOOSE = 1e-6  # a row of fixed columns alone holds to this times (1 + its size): the ranks met it
RHO = 1e8  # a coordinate at a bound weighs (1 + RHO) times more in the Newton system
DELTA = 1e-14  # the regularization of the Newton system
REFINE = 2  # the steps of iterative refinement of a solve by LDL'
ACCURATE = 1e-10  # a solve by LDL' whose backward error is above this goes to SuperLU for the stage


class Unconverged(Exception):
    """The method did not meet the rows within its steps, or its dual has no maximum."""

    def __init__(self, steps, residual):
        super().__init__(f'no convergence in {steps} Newton steps (residual {residual:.1e})')
        self.steps, self.residual = steps, residual


def select(face, w, budget, work):
    """The two stages on the face; gives the answer in working units (the order of `w`)."""
    A, row_lower, row_upper = face.arrays(w.A)
    lower, upper = face.lower.copy(), face.upper.copy()
    flows, others = w.kind == FLOW, w.kind == OTHER
    xi = None
    if flows.any():
        xi = stage(A, row_lower, row_upper, lower, upper, w.target, flows * 1.0, budget, work, 'the flows')
        lower[flows] = upper[flows] = xi[flows]
    if others.any() or xi is None:
        # The LP chose the face in physical coordinates. Only the distance between remaining
        # nonflow values uses their declared metric. Change coordinates once for either QP method.
        free = others & (lower < upper)
        scale, target = None, w.target
        if np.any(w.metric_scale[free] != w.scale[free]):
            scale = np.ones(w.n)
            scale[free] = w.metric_scale[free] / w.scale[free]
            # A common change of the metric leaves its minimizer unchanged. Fit the relative
            # lengths to the physical boxes so QP primal tolerances still resolve their widths.
            widths = upper[free] - lower[free]
            widths = np.where(np.isfinite(widths), widths, 1.0)
            scale[free] /= np.max(scale[free] / widths)
            A = sp.csr_array(A.multiply(scale))
            size = row_max(A)
            rows = np.where(size > 0, size, 1.0)
            A = sp.csr_array(A.multiply((1.0 / rows)[:, None]))
            row_lower, row_upper = row_lower / rows, row_upper / rows
            lower, upper, target = lower / scale, upper / scale, target / scale
        xi = stage(A, row_lower, row_upper, lower, upper, target, others * 1.0, budget, work, 'the others')
        if scale is not None:
            xi *= scale
    return xi


def stage(A, row_lower, row_upper, lower, upper, target, weight, budget, work, what):
    """One distance stage: the method within its budget, by LDL' and, where it does not converge so,
    again by SuperLU alone; else the QP of HiGHS within its own budget."""
    step = f'distance of {what}'
    for superlu in (False, True):
        try:
            x, steps = nearest(
                A, row_lower, row_upper, lower, upper, target, weight, budget.newton_steps, work, superlu
            )
            work.newton.append(steps)
            work.methods.append('newton')
            return x
        except Unconverged as stopped:
            work.newton.append(stopped.steps)
            newton, residual = stopped.steps, stopped.residual
    status, x, taken = quadratic(A, row_lower, row_upper, lower, upper, target, weight, budget.qp_iterations)
    work.qp.append(taken)
    work.methods.append('qp')
    reached = {'newton steps': newton, 'residual': residual, 'qp iterations': taken}
    if status == OPTIMAL:
        # the QP holds a bound to its tolerance; the answer of the method is always within it
        return np.clip(x, lower, upper)
    if status == Status.kIterationLimit:
        raise SolveFailure(
            DISTANCE_BUDGET,
            step,
            f'the method did not converge in {newton} Newton steps (residual {residual:.1e}) '
            f'and the QP did not finish in {budget.qp_iterations} iterations',
            reached,
        )
    reached['status'] = str(status).split('.')[-1]
    raise SolveFailure(NUMERICAL, step, f'the QP of HiGHS ended with the status {reached["status"]}', reached)


def nearest(A, row_lower, row_upper, lower, upper, target, weight, steps, work, superlu=False):
    """The method of the module text within `steps` Newton steps, its systems factorized by LDL' (and
    SuperLU where LDL' falls short) or, with `superlu`, by SuperLU alone; gives (x, the steps taken),
    or raises `Unconverged`."""
    A = sp.csr_array(A)
    m = A.shape[0]
    if np.any(lower > upper + TOL * (1.0 + np.abs(lower))):
        raise Unconverged(0, np.inf)  # a crossed interval: the QP tells the failure
    fixed = upper <= lower
    x = np.where(fixed, np.minimum(lower, upper), 0.0)
    free = np.flatnonzero(~fixed)
    shift = A[:, np.flatnonzero(fixed)] @ x[fixed] if fixed.any() else np.zeros(m)
    size = abs(A[:, np.flatnonzero(fixed)]) @ np.abs(x[fixed]) if fixed.any() else np.zeros(m)
    B = sp.csr_array(A[:, free])
    lo_r, hi_r = row_lower - shift, row_upper - shift
    empty = np.diff(B.indptr) == 0
    slack = LOOSE * (1.0 + size)
    if np.any(empty & ((lo_r > slack) | (hi_r < -slack))):
        raise Unconverged(0, float(np.max(np.maximum(lo_r, -hi_r)[empty])))
    keep = np.flatnonzero(~empty & (np.isfinite(lo_r) | np.isfinite(hi_r)))
    B, lo_r, hi_r = sp.csr_array(B[keep]), lo_r[keep], hi_r[keep]
    equal = lo_r == hi_r
    loose = np.flatnonzero(~equal)
    mk, nf, ns = B.shape[0], len(free), len(loose)
    # the coordinates z = (x of the free columns, a slack for each row with lower < upper), and the
    # rows B x - S s = e
    S = sp.csr_array((np.ones(ns), (loose, np.arange(ns))), shape=(mk, ns))
    E = sp.hstack([B, -S]).tocsr()
    e = np.where(equal, lo_r, 0.0)
    zl, zu = np.r_[lower[free], lo_r[loose]], np.r_[upper[free], hi_r[loose]]
    w = np.r_[weight[free], np.zeros(ns)]
    prox = w <= 0
    eps = EPS_START
    w = np.where(prox, eps, w)
    c = np.r_[target[free], np.zeros(ns)]
    # the first centres of the proximal coordinates: the target in the box, a slack at its row there
    cx = np.clip(c[:nf], zl[:nf], zu[:nf])
    c[:nf][prox[:nf]] = cx[prox[:nf]]
    c[nf:] = np.clip(B[loose] @ cx, zl[nf:], zu[nf:])
    tolerance = TOL * (1.0 + np.abs(e) + abs(B) @ np.abs(cx))
    dual = _Dual(E, e, zl, zu, w, superlu)
    y = np.zeros(mk)
    taken = outer = 0
    try:
        while True:
            outer += 1
            z, y1, residual, used, met = _attempt(dual, c, y, tolerance, steps - taken)
            taken += used
            if met is None and taken < steps:
                # the retry of A3: a Levenberg-Marquardt term, as in a face of no width
                dual.lm = True
                z, y1, residual, used, met = _attempt(dual, c, y, tolerance, steps - taken)
                taken += used
                dual.lm = False
            if met is None:
                raise Unconverged(taken, residual)
            y = y1
            if not prox.any():
                break
            move = float(np.abs(z[prox] - c[prox]).max())
            c[prox] = z[prox]
            # the proximal term leaves eps * move in the conditions of the true problem: stop when
            # that is within the precision to which the rows were met (a tighter rule cycles there)
            if eps * move <= met * (1.0 + float(np.abs(z[prox]).max())):
                break
            if taken >= steps or outer >= steps:
                raise Unconverged(taken, residual)
            if used <= SETTLED and eps > EPS:
                eps = max(EPS, eps / 10.0)
                dual.weigh(np.where(prox, eps, dual.w))
    finally:
        work.factorizations += dual.factorizations
        work.superlu += dual.superlu
    x[free] = z[:nf]
    return x, taken


def _attempt(dual, c, y, tolerance, steps):
    """`dual.solve`, where a singular Newton system is a step that did not converge."""
    try:
        return dual.solve(c, y, tolerance, steps)
    except RuntimeError:
        return None, y, np.inf, 1, None


class _Dual:
    """The dual of one proximal problem of `nearest` and its Newton steps, its systems factorized by
    LDL' (`_LDL`, one analysis of the pattern for the stage) until it falls short, then by SuperLU
    for the rest of the stage (see the module text)."""

    def __init__(self, E, e, zl, zu, w, superlu=False):
        self.E, self.ET, self.e, self.zl, self.zu, self.w = E, E.T.tocsr(), e, zl, zu, w
        self.m, self.N = E.shape
        self.lm = False
        self.superlu = superlu  # SuperLU factorizes the systems from now on
        self.ldl = None  # the LDL' of the stage's pattern, made at its first factorization
        self.factor = None
        self.factorizations = 0
        if self.m:
            K = sp.block_array(
                [[sp.diags_array(np.ones(self.N)), self.ET], [E, sp.diags_array(-np.ones(self.m))]]
            ).tocsc()
            K.sort_indices()
            # the place of each diagonal entry of K in its data
            columns = np.repeat(np.arange(K.shape[1]), np.diff(K.indptr))
            self.diagonal = np.flatnonzero(K.indices == columns)
            self.K = K

    def weigh(self, w):
        """New weights; the next step factorizes again."""
        self.w = w
        self.factor = None

    def point(self, c, y):
        """x(y) and the residual of the rows there (the gradient of the dual)."""
        z = np.clip(c - (self.ET @ y) / self.w, self.zl, self.zu)
        return z, self.E @ z - self.e

    def solve(self, c, y, tolerance, steps):
        """Newton steps on the dual from y until every row is met; gives (z, y, the largest residual,
        the steps taken, the precision to which the rows are met: TOL, FEASIBLE after a stall, or
        None)."""
        z, r = self.point(c, y)
        if not self.m:
            return z, y, 0.0, 0, TOL
        best, since = np.inf, 0
        for used in range(max(steps, 0)):
            if np.all(np.abs(r) <= tolerance):
                return z, y, float(np.abs(r).max()), used, TOL
            size = float(np.abs(r).max())
            best, since = (size, 0) if size <= 0.5 * best else (best, since + 1)
            if since >= STALL and np.all(np.abs(r) <= tolerance * (FEASIBLE / TOL)):
                return z, y, size, used, FEASIBLE
            u = c - (self.ET @ y) / self.w
            free = (u > self.zl) & (u < self.zu)
            # Levenberg-Marquardt: delta follows the residual, a power of ten, so that one
            # factorization serves while the free set and delta stay
            delta = 10.0 ** np.clip(np.ceil(np.log10(size)) - 2, -14, -4) if self.lm else DELTA
            key = (free.tobytes(), delta)
            if self.factor is None or self.factor[0] != key:
                self.K.data[self.diagonal] = np.r_[
                    np.where(free, self.w, self.w * (1.0 + RHO)), np.full(self.m, -delta)
                ]
                self.factor = (key, self._factorized())
                self.factorizations += 1
            step = self._solved(key, np.r_[np.zeros(self.N), -r])[self.N :]
            # dual ascent: the gradient of the dual is r, and the step solves (E D E' + delta) step = r
            slope = float(r @ step)
            if slope <= 0:
                step, slope = r.copy(), float(r @ r)
            alpha = self.search(c, y, step, slope)
            if alpha is None:
                return z, y, size, used + 1, None  # the dual has no maximum: the rows cannot hold
            y = y + alpha * step
            z, r = self.point(c, y)
        met = TOL if np.all(np.abs(r) <= tolerance) else None
        return z, y, float(np.abs(r).max()), max(steps, 0), met

    def _factorized(self):
        """K with its present diagonal, factorized: by LDL' on the stage's analysis, or by SuperLU
        once LDL' has fallen short or where it refuses K."""
        if not self.superlu:
            try:
                if self.ldl is None:
                    self.ldl = _LDL(self.K)
                else:
                    self.ldl.update()
                return self.ldl
            except RuntimeError:  # a pivot of LDL' at zero: K is not quasi-definite enough for it
                self.superlu = True
        return splu(self.K, permc_spec='MMD_AT_PLUS_A')

    def _solved(self, key, rhs):
        """K x = rhs by the present factorization; a solve by LDL' that misses ACCURATE makes the
        stage go on by SuperLU, from this system."""
        try:
            return self.factor[1].solve(rhs)
        except _Inaccurate:
            self.superlu = True
            self.factor = (key, self._factorized())
            self.factorizations += 1
            return self.factor[1].solve(rhs)

    def search(self, c, y, step, slope):
        """The exact step along `step`: the derivative of the dual along it is piecewise linear and
        falls; between events its slope is minus the sum of w g^2 over the coordinates that are free.
        None when the derivative stays above zero: the dual has no maximum that way."""
        u = c - (self.ET @ y) / self.w
        g = (self.ET @ step) / self.w
        moving = g != 0
        u, g, w, zl, zu = u[moving], g[moving], self.w[moving], self.zl[moving], self.zu[moving]
        with np.errstate(divide='ignore', invalid='ignore'):
            at_lower = np.where(np.isfinite(zl), (u - zl) / g, np.where(g > 0, np.inf, -np.inf))
            at_upper = np.where(np.isfinite(zu), (u - zu) / g, np.where(g > 0, -np.inf, np.inf))
        enter, leave = np.minimum(at_lower, at_upper), np.maximum(at_lower, at_upper)
        wg2 = w * g * g
        now = (enter <= 0) & (leave > 0)
        later = enter > 0
        ends = (now | later) & np.isfinite(leave)
        alphas = np.r_[enter[later], leave[ends]]
        change = np.r_[-wg2[later], wg2[ends]]
        order = np.argsort(alphas, kind='stable')
        alphas, change = alphas[order], change[order]
        slopes = -float(wg2[now].sum()) + np.r_[0.0, np.cumsum(change)]
        widths = np.diff(np.r_[0.0, alphas])
        values = slope + np.cumsum(slopes[:-1] * widths)
        at = np.flatnonzero(values <= 0.0)
        if not len(at):
            last = slopes[-1]
            base = float(values[-1]) if len(values) else slope
            left = float(alphas[-1]) if len(alphas) else 0.0
            return left + base / -last if last < 0 else None
        k = int(at[0])
        before = slope if k == 0 else float(values[k - 1])
        left = 0.0 if k == 0 else float(alphas[k - 1])
        return left + before / -slopes[k] if slopes[k] < 0 else left


class _Inaccurate(Exception):
    """A solve by LDL' whose backward error is above ACCURATE."""


class _LDL:
    """The LDL' factorization of the quasi-definite Newton system K by qdldl: its order and the
    analysis of its pattern are made once (`__init__`), and `update` factorizes the values that K
    holds now, the pattern unchanged. A solve is refined REFINE times against K, and one whose
    backward error is above ACCURATE raises `_Inaccurate`."""

    def __init__(self, K):
        self.K = K
        self.solver = qdldl.Solver(sp.csc_matrix(K))
        self.size = abs(K)

    def update(self):
        self.solver.update(sp.csc_matrix(self.K))
        self.size = abs(self.K)

    def solve(self, rhs):
        x = self.solver.solve(rhs)
        for _ in range(REFINE):
            x = x + self.solver.solve(rhs - self.K @ x)
        error = np.abs(self.K @ x - rhs).max(initial=0.0)
        scale = (self.size @ np.abs(x) + np.abs(rhs)).max(initial=0.0)
        if not (np.all(np.isfinite(x)) and error <= ACCURATE * scale):
            raise _Inaccurate
        return x
