"""A problem in working units, in the order of the columns and rows of a kept HiGHS instance.

Flow coordinates use their physical rate units. Nonflow unknowns enter the hard constraints,
written ranks and fair-sharing problems in physical coordinates. Their declared reference scales
specify the metric on the final feasible face and are retained separately for that distance.
Rows and objectives are normalized after choosing these working coordinates.
"""

from __future__ import annotations

import copy

import numpy as np
import scipy.sparse as sp

from .failures import NUMERICAL, SolveFailure
from .problem import OTHER


class Scaled:
    """The working form of an `Arrays` record; `reordered` puts it in the order of an instance."""

    def __init__(self, arrays):
        self.arrays = arrays
        self.n, self.m = arrays.n, arrays.m
        self.metric_scale = arrays.scale
        s = self.scale = np.where(arrays.kind == OTHER, 1.0, arrays.scale)
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
        self.F = served_rows(arrays.F, self.request, s) if len(self.request) else sp.csr_array(arrays.F)
        self.F.sort_indices()
        self.columns, self.rows = np.arange(arrays.n), np.arange(arrays.m)

    def reordered(self, columns, rows):
        """The same form with its columns and rows in the order `columns` and `rows` (positions in
        this form)."""
        other = copy.copy(self)
        for name in ('scale', 'metric_scale', 'lower', 'upper', 'target', 'kind', 'columns'):
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


def served_rows(F, request, scale=None):
    """The served fraction of each claim per unit of the unknowns (in working units, times `scale`):
    claim i's row of F over request_i. A request below `TINY` is no claim (`network.is_claim`), but a
    small normal request can still overflow on the way: (1 / request) times a coefficient, or times a
    large scale. Such rows are formed again in one step, F_i * scale / request_i. A row that is still
    not finite has a served fraction that no float holds: a named failure, never a dropped claim."""
    with np.errstate(over='ignore'):
        rows = sp.diags_array(1.0 / request) @ F
        if scale is not None:
            rows = rows @ sp.diags_array(scale)
    rows = sp.csr_array(rows)
    if np.isfinite(rows.data).all():
        return rows
    rows = sp.csr_array(F @ sp.diags_array(scale) if scale is not None else F, copy=True)
    with np.errstate(over='ignore'):
        rows.data = rows.data / np.repeat(request, np.diff(rows.indptr))
    bad = np.flatnonzero(~np.isfinite(rows.data))
    if len(bad):
        claim = int(np.searchsorted(rows.indptr, bad[0], side='right') - 1)
        raise SolveFailure(
            NUMERICAL,
            'served fractions',
            f'the request {float(request[claim]):g} of claim {claim} is too small for the scale of its '
            'unknowns: no float holds its served fraction',
        )
    return rows
