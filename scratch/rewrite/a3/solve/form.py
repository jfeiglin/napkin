"""The one problem form of the selection order, and its working form.

A `Problem` is written in the units of its author:

    unknowns x with bounds                         lower <= x <= upper
    affine rows                                    row_lower <= A x <= row_upper   (==, <= and >=)
    ranked linear objectives                       minimize c.x, in written order
    claims in priority tiers                       fraction_i = min(1, rate_i.x / request_i)
    the squared distance of the flows              sum ((x_j - target_j) / scale_j)^2 over kind FLOW
    the squared distance of the other unknowns     the same over kind OTHER

A positive-part shortfall `max(0, request - rate)` is an extra unknown s >= 0 of kind INTERNAL with the
row `rate + s >= request`; an objective then names s. A flow with legs is one unknown, its served
fraction, with a claim of request 1 on it.

`Work` is the same problem in working units: each column is divided by its reference scale, so that a
value of one is one scale of the column, and each row is divided by its largest coefficient. The
tolerances of the library are in these units. Another spelling of the units of a column changes its
bounds, its scale and its coefficients together, so the working form stays the same but for rounding.
"""
import numpy as np
import scipy.sparse as sp

INF = np.inf
INTERNAL, FLOW, OTHER = 0, 1, 2


class Problem:
    def __init__(self, lower, upper, scale=None, target=None, kind=None):
        self.lower = np.array(lower, dtype=float)
        self.upper = np.array(upper, dtype=float)
        n = self.n = len(self.lower)
        self.scale = np.ones(n) if scale is None else np.array(scale, dtype=float)
        self.target = np.zeros(n) if target is None else np.array(target, dtype=float)
        self.kind = np.full(n, FLOW, dtype=np.int8) if kind is None else np.array(kind, dtype=np.int8)
        self._rows = []          # (columns, values, lower, upper)
        self._matrix = None      # (A, row_lower, row_upper) given whole
        self.objectives = []     # (columns, values)
        self._claims = []        # (columns, values, request, tier)

    # -- rows ---------------------------------------------------------------------------------
    def rows(self, A, row_lower, row_upper):
        """Many rows at once, as a sparse matrix."""
        assert self._matrix is None and not self._rows
        self._matrix = (sp.csr_array(A, dtype=float), np.array(row_lower, dtype=float), np.array(row_upper, dtype=float))

    def row(self, terms, lower=-INF, upper=INF):
        """One row: `terms` is {column: coefficient}."""
        cols = np.fromiter(terms.keys(), dtype=np.int64, count=len(terms))
        vals = np.fromiter(terms.values(), dtype=float, count=len(terms))
        self._rows.append((cols, vals, float(lower), float(upper)))
        return len(self._rows) - 1

    def equal(self, terms, value):
        return self.row(terms, value, value)

    def at_most(self, terms, value):
        return self.row(terms, -INF, value)

    def at_least(self, terms, value):
        return self.row(terms, value, INF)

    # -- ranks --------------------------------------------------------------------------------
    def minimize(self, terms):
        """The next ranked objective: {column: coefficient}, or a dense vector."""
        if isinstance(terms, dict):
            cols = np.fromiter(terms.keys(), dtype=np.int64, count=len(terms))
            vals = np.fromiter(terms.values(), dtype=float, count=len(terms))
        else:
            dense = np.asarray(terms, dtype=float)
            cols = np.flatnonzero(dense)
            vals = dense[cols]
        self.objectives.append((cols, vals))

    def maximize(self, terms):
        if isinstance(terms, dict):
            self.minimize({j: -v for j, v in terms.items()})
        else:
            self.minimize(-np.asarray(terms, dtype=float))

    def claim(self, rate, request, tier=0):
        """A claim: the realized rate of its scope ({column: coefficient}, or one column) and its
        request. A request of zero makes no claim."""
        if request <= 0:
            return None
        if isinstance(rate, dict):
            cols = np.fromiter(rate.keys(), dtype=np.int64, count=len(rate))
            vals = np.fromiter(rate.values(), dtype=float, count=len(rate))
        else:
            cols, vals = np.array([int(rate)]), np.array([1.0])
        self._claims.append((cols, vals, float(request), int(tier)))
        return len(self._claims) - 1

    def claims(self, columns, requests, tiers=None):
        """Many claims of one column each."""
        columns, requests = np.asarray(columns), np.asarray(requests, dtype=float)
        tiers = np.zeros(len(columns), dtype=int) if tiers is None else np.asarray(tiers)
        for j, q, t in zip(columns.tolist(), requests.tolist(), tiers.tolist()):
            self.claim(j, q, t)

    # -- arrays -------------------------------------------------------------------------------
    def matrix(self):
        """(A, row_lower, row_upper) of all rows."""
        if self._matrix is not None:
            A, lo, hi = self._matrix
            if not self._rows:
                return A, lo, hi
            extra = _stack(self._rows, self.n)
            return (sp.vstack([A, extra[0]]).tocsr(), np.r_[lo, extra[1]], np.r_[hi, extra[2]])
        if not self._rows:
            return sp.csr_array((0, self.n)), np.zeros(0), np.zeros(0)
        return _stack(self._rows, self.n)

    def claim_arrays(self):
        """(F, request, tier): `F x` is the rate of each claim."""
        K = len(self._claims)
        if not K:
            return sp.csr_array((0, self.n)), np.zeros(0), np.zeros(0, dtype=int)
        F, _, _ = _stack([(c, v, 0.0, 0.0) for c, v, _, _ in self._claims], self.n)
        return F, np.array([q for _, _, q, _ in self._claims]), np.array([t for _, _, _, t in self._claims], dtype=int)


def _stack(rows, n):
    counts = np.array([len(c) for c, _, _, _ in rows])
    indptr = np.r_[0, np.cumsum(counts)]
    cols = np.concatenate([c for c, _, _, _ in rows]) if len(rows) else np.zeros(0, dtype=np.int64)
    vals = np.concatenate([v for _, v, _, _ in rows]) if len(rows) else np.zeros(0)
    A = sp.csr_array((vals, cols, indptr), shape=(len(rows), n))
    A.sum_duplicates()
    return A, np.array([lo for _, _, lo, _ in rows]), np.array([hi for _, _, _, hi in rows])


class Work:
    """A problem in working units (see the module text)."""

    def __init__(self, problem):
        p = self.problem = problem
        n = self.n = p.n
        s = self.scale = p.scale
        if not (np.all(s > 0) and np.all(np.isfinite(s))):
            raise ValueError('each reference scale is positive and finite')
        A, row_lower, row_upper = p.matrix()
        A = (A @ sp.diags_array(s)).tocsr() if A.shape[0] else A
        size = _row_max(A)
        self.row_scale = np.where(size > 0, 1.0 / np.where(size > 0, size, 1.0), 1.0)
        self.A = (sp.diags_array(self.row_scale) @ A).tocsr() if A.shape[0] else A
        self.A.sort_indices()
        self.m = self.A.shape[0]
        self.row_lower = row_lower * self.row_scale
        self.row_upper = row_upper * self.row_scale
        self.lower = p.lower / s
        self.upper = p.upper / s
        self.target = p.target / s
        self.kind = p.kind
        # objectives: c.x = norm * (cost . xi)
        self.costs, self.cost_norms = [], []
        for cols, vals in p.objectives:
            cost = np.zeros(n)
            np.add.at(cost, cols, vals * s[cols])
            norm = float(np.abs(cost).max(initial=0.0))
            self.cost_norms.append(norm if norm > 0 else 1.0)
            self.costs.append(cost / (norm if norm > 0 else 1.0))
        # claims: fraction_i = min(1, F_i . xi); the row is scaled so that no entry is above one
        F, request, tier = p.claim_arrays()
        self.K = F.shape[0]
        self.tier = tier
        self.request = request
        if self.K:
            F = (sp.diags_array(1.0 / request) @ F @ sp.diags_array(s)).tocsr()
            F.sort_indices()
        self.F = F
        self.claim_scale = 1.0 / np.maximum(1.0, _row_max(F)) if self.K else np.zeros(0)

    def x(self, xi):
        """Working values back in the units of the author."""
        return xi * self.scale


def _row_max(A):
    """The largest magnitude of each row of a CSR matrix (0 for an empty row)."""
    out = np.zeros(A.shape[0])
    if A.nnz:
        lengths = np.diff(A.indptr)
        filled = lengths > 0
        out[filled] = np.maximum.reduceat(np.abs(A.data), A.indptr[:-1][filled])
    return out
