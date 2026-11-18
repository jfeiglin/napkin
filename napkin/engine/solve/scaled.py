"""A problem in working units, in the order of the columns and rows of a kept HiGHS instance.

Each column is divided by its reference scale, so that a value of one is one scale of its unknown,
and each row is then divided by its largest coefficient. An objective is divided by its largest
coefficient, and the rate of a claim by its request, so that a claim reads a served fraction. Every
tolerance of the library is in these units. Another spelling of the units of an unknown (W or kW)
changes its bounds, its scale and its coefficients together, so its working form is the same but
for rounding, and so is the answer.
"""

from __future__ import annotations

import copy

import numpy as np
import scipy.sparse as sp


class Scaled:
    """The working form of an `Arrays` record; `reordered` puts it in the order of an instance."""

    def __init__(self, arrays):
        self.arrays = arrays
        self.n, self.m = arrays.n, arrays.m
        s = self.scale = arrays.scale
        self.lower, self.upper = arrays.lower / s, arrays.upper / s
        self.target = arrays.target / s
        self.kind = arrays.kind
        A = (arrays.A @ sp.diags_array(s)).tocsr() if arrays.m else sp.csr_array((0, arrays.n))
        size = row_max(A)
        self.row_scale = 1.0 / np.where(size > 0, size, 1.0)
        self.A = (sp.diags_array(self.row_scale) @ A).tocsr() if arrays.m else A
        self.A.sort_indices()
        self.row_lower = arrays.row_lower * self.row_scale
        self.row_upper = arrays.row_upper * self.row_scale
        # objective k in author units is norms[k] * (costs[k] . xi)
        self.costs, self.norms = [], []
        for columns, values in arrays.objectives:
            cost = np.zeros(arrays.n)
            np.add.at(cost, columns, values * s[columns])
            norm = float(np.abs(cost).max(initial=0.0)) or 1.0
            self.costs.append(cost / norm)
            self.norms.append(norm)
        # the served fraction of claim i is min(1, F_i . xi)
        self.request, self.tier = arrays.request, arrays.tier
        K = len(self.request)
        F = sp.diags_array(1.0 / self.request) @ arrays.F @ sp.diags_array(s) if K else arrays.F
        self.F = sp.csr_array(F)
        self.F.sort_indices()
        self.columns, self.rows = np.arange(arrays.n), np.arange(arrays.m)

    def reordered(self, columns, rows):
        """The same form with its columns and rows in the order `columns` and `rows` (positions in
        this form)."""
        other = copy.copy(self)
        for name in ('scale', 'lower', 'upper', 'target', 'kind', 'columns'):
            setattr(other, name, getattr(self, name)[columns])
        for name in ('row_scale', 'row_lower', 'row_upper', 'rows'):
            setattr(other, name, getattr(self, name)[rows])
        other.A = sp.csr_array(self.A[rows][:, columns])
        other.A.sort_indices()
        other.costs = [cost[columns] for cost in self.costs]
        other.F = sp.csr_array(self.F[:, columns])
        other.F.sort_indices()
        return other

    def author(self, xi):
        """Working values in the order of the problem and in the units of its author."""
        x = np.empty(self.n)
        x[self.columns] = xi * self.scale
        return x


def row_max(A):
    """The largest magnitude in each row of a CSR matrix (0 for an empty row)."""
    out = np.zeros(A.shape[0])
    if A.nnz:
        filled = np.diff(A.indptr) > 0
        out[filled] = np.maximum.reduceat(np.abs(A.data), A.indptr[:-1][filled])
    return out
