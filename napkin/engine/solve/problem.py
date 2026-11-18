"""The problem of one declared solver, in the units of its author, as arrays.

A problem holds what the selection order of the spec reads ("Solver and execution contract"):

    unknowns x        each with bounds lower <= x <= upper (either side open), a positive reference
                      scale, a target and a kind: FLOW (a rate; its target is its request), OTHER (any
                      other unknown; its target is its declared reference) or INTERNAL (an unknown of
                      the solver's own, which no distance step weighs)
    affine rows       row_lower <= a.x <= row_upper, which writes `==`, `<=` and `>=`
    objectives        minimize c.x, in written order
    claims            the served fraction min(1, f.x / request) of a scope, in priority tiers (tier 0
                      is served first); a request of zero makes no claim

Two forms of the language become plain unknowns and rows here. A positive part max(0, e.x + e0),
such as an unmet request, is an INTERNAL unknown s >= 0 with the row s - e.x >= e0 (`positive_part`);
it is exact where an objective minimizes it, which `minimize` checks. A flow with legs is one FLOW
unknown, its served fraction in [0, 1] with scale one and target one (zero when no leg asks); each
leg's rate is that fraction times the leg's request wherever the rows read the leg, and the activity
makes one claim of request one on the fraction.

Unknowns and rows have keys (any hashable values). A `Solver` keeps one HiGHS instance for a run and
matches each new problem to it by these keys, so the engine forms the problem of each moment fresh,
and unknowns that join or leave become columns that the instance adds or deletes. A key names the
same thing in every problem of a run; it is never reused for another thing.

The methods that take one unknown or one row serve small problems and tests; `unknowns`, `rows` and
`claims` take whole arrays, for problems of many thousand places.
"""

from __future__ import annotations

import math

import numpy as np
import scipy.sparse as sp

INF = math.inf
INTERNAL, FLOW, OTHER = 0, 1, 2
KINDS = (INTERNAL, FLOW, OTHER)


class Problem:
    """Unknowns, rows, ranked objectives and claims, in author units (see the module text)."""

    def __init__(self):
        self._keys, self._index = [], {}
        self._lower, self._upper, self._scale, self._target, self._kind = [], [], [], [], []
        self._row_keys, self._row_index = [], {}
        self._row_lower, self._row_upper = [], []
        self._entries = []  # (rows, columns, values): the row entries, in blocks
        self._objectives = []  # (columns, values), in written order
        self._claim_entries, self._requests, self._tiers = [], [], []
        self._positive = []  # blocks of positive parts: (their columns, the matrix, the constants)
        self._positive_columns = set()
        self._arrays = None

    # -- unknowns ----------------------------------------------------------------------------------
    def unknown(self, key, lower=-INF, upper=INF, kind=FLOW, target=0.0, scale=1.0):
        """One unknown; gives its column."""
        return int(self.unknowns([key], [lower], [upper], kind, [target], [scale])[0])

    def unknowns(self, keys, lower, upper, kind=FLOW, target=0.0, scale=1.0):
        """Many unknowns; gives their columns. Each argument but `keys` is an array or one value."""
        keys = list(keys)
        count = len(keys)
        lower, upper = _numbers(lower, count, 'lower'), _numbers(upper, count, 'upper')
        target, scale = _numbers(target, count, 'target'), _numbers(scale, count, 'scale')
        kind = np.broadcast_to(np.asarray(kind, dtype=np.int8), (count,))
        if np.isnan(lower).any() or np.isnan(upper).any():
            raise ValueError('a bound of an unknown is not a number')
        if not np.isfinite(target).all():
            raise ValueError('the target of an unknown is finite')
        if not (np.isfinite(scale).all() and (scale > 0).all()):
            raise ValueError('the reference scale of an unknown is positive and finite')
        if not np.isin(kind, KINDS).all():
            raise ValueError('the kind of an unknown is FLOW, OTHER or INTERNAL')
        first = len(self._keys)
        _register(self._index, keys, first, 'unknowns')
        self._keys += keys
        for store, values in (
            (self._lower, lower),
            (self._upper, upper),
            (self._target, target),
            (self._scale, scale),
            (self._kind, kind),
        ):
            store.append(np.array(values))
        self._arrays = None
        return np.arange(first, first + count)

    def column(self, key):
        """The column of the unknown `key`."""
        return self._index[key]

    @property
    def keys(self):
        """The keys of the unknowns, in the order of their columns."""
        return tuple(self._keys)

    # -- rows --------------------------------------------------------------------------------------
    def row(self, key, terms, lower=-INF, upper=INF):
        """One row `lower <= sum(coefficient * x[column]) <= upper`; `terms` is {column: coefficient}."""
        columns, values = _terms(terms)
        if (columns >= len(self._keys)).any():
            raise ValueError(f'row {key!r} reads a column that the problem does not have')
        self._new_rows([key], [lower], [upper])
        self._entries.append((np.full(len(columns), len(self._row_keys) - 1), columns, values))
        self._arrays = None

    def equal(self, key, terms, value):
        """The row `terms == value`."""
        self.row(key, terms, value, value)

    def at_most(self, key, terms, value):
        """The row `terms <= value`."""
        self.row(key, terms, -INF, value)

    def at_least(self, key, terms, value):
        """The row `terms >= value`."""
        self.row(key, terms, value, INF)

    def rows(self, keys, matrix, lower, upper):
        """Many rows: `lower <= matrix @ x <= upper`, where the columns of the sparse `matrix` are the
        first columns of the problem."""
        keys = list(keys)
        matrix = sp.coo_array(matrix)
        if matrix.shape[0] != len(keys):
            raise ValueError('a row matrix has one row for each key')
        if matrix.shape[1] > len(self._keys):
            raise ValueError('a row matrix reads columns that the problem does not have')
        if not np.isfinite(matrix.data).all():
            raise ValueError('a coefficient of a row is finite')
        first = len(self._row_keys)
        self._new_rows(keys, _numbers(lower, len(keys), 'lower'), _numbers(upper, len(keys), 'upper'))
        self._entries.append((matrix.row + first, matrix.col.astype(np.int64), matrix.data.astype(float)))
        self._arrays = None

    def _new_rows(self, keys, lower, upper):
        lower, upper = np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)
        if np.isnan(lower).any() or np.isnan(upper).any():
            raise ValueError('a bound of a row is not a number')
        _register(self._row_index, keys, len(self._row_keys), 'rows')
        self._row_keys += keys
        self._row_lower.append(lower)
        self._row_upper.append(upper)

    # -- the forms of the language -----------------------------------------------------------------
    def positive_part(self, key, terms, constant=0.0, scale=None):
        """The positive part max(0, terms + constant) as an INTERNAL unknown, keyed `key`; gives its
        column (see `positive_parts`)."""
        columns, values = _terms(terms)
        matrix = sp.csr_array(
            (values, (np.zeros(len(columns), np.int64), columns)), shape=(1, len(self._keys))
        )
        return int(self.positive_parts([key], matrix, [constant], None if scale is None else [scale])[0])

    def positive_parts(self, keys, matrix, constants=0.0, scale=None):
        """Many positive parts max(0, matrix @ x + constants), each an INTERNAL unknown s >= 0 with the
        row s - matrix @ x >= constant, keyed ('positive part', key); gives their columns. The scale
        of each is that of its largest term unless given, so that another spelling of the units
        changes nothing."""
        keys = list(keys)
        matrix = sp.csr_array(matrix)
        count, width = len(keys), matrix.shape[1]
        if matrix.shape[0] != count or width > len(self._keys):
            raise ValueError('a positive part reads one row of columns that the problem has')
        constants = _numbers(constants, count, 'constant')
        if scale is None:
            scales = _join(self._scale)[:width]
            sizes = abs(matrix) @ sp.diags_array(scales) if width else matrix
            largest = sizes.max(axis=1).toarray().ravel() if sizes.nnz else np.zeros(count)
            scale = np.where(largest > 0, largest, 1.0)
        parts = self.unknowns(keys, 0.0, INF, INTERNAL, 0.0, scale)
        terms = sp.coo_array(matrix)
        rows = sp.coo_array(
            (
                np.r_[-terms.data, np.ones(count)],
                (np.r_[terms.row, np.arange(count)], np.r_[terms.col, parts]),
            ),
            shape=(count, len(self._keys)),
        )
        self.rows([('positive part', key) for key in keys], rows, constants, INF)
        self._positive.append((parts, sp.csr_array(matrix), constants))
        self._positive_columns.update(parts.tolist())
        return parts

    # -- ranks -------------------------------------------------------------------------------------
    def minimize(self, terms):
        """The next ranked objective: {column: coefficient}, or a vector over the first columns."""
        if isinstance(terms, dict):
            columns, values = _terms(terms)
        else:
            dense = np.asarray(terms, dtype=float)
            columns = np.flatnonzero(dense)
            values = dense[columns]
        if not np.isfinite(values).all():
            raise ValueError('a coefficient of an objective is finite')
        if (columns >= len(self._keys)).any():
            raise ValueError('an objective reads a column that the problem does not have')
        for column, value in zip(columns.tolist(), values.tolist()):
            if column in self._positive_columns and value < 0:
                # max(0, e) is convex: an objective may minimize it, never maximize it
                raise ValueError(f'objective {len(self._objectives) + 1} maximizes a positive part')
        self._objectives.append((columns, values))
        self._arrays = None

    def maximize(self, terms):
        """The next ranked objective, maximized."""
        if isinstance(terms, dict):
            self.minimize({column: -value for column, value in terms.items()})
        else:
            self.minimize(-np.asarray(terms, dtype=float))

    def claim(self, terms, request, tier=0):
        """A claim of fair sharing: the realized rate of its scope ({column: coefficient}) and its
        positive request. Gives the number of the claim, or None for a request of zero, which makes
        no claim."""
        columns, values = _terms(terms)
        return self._claim(columns, values, request, tier)

    def claims(self, columns, requests, tiers=0):
        """Many claims of one column each; gives their numbers, with -1 where a request is zero."""
        columns = np.asarray(columns, dtype=np.int64)
        requests = _numbers(requests, len(columns), 'request')
        tiers = np.broadcast_to(np.asarray(tiers, dtype=np.int64), (len(columns),))
        made = [
            self._claim(np.array([column]), np.array([1.0]), request, tier)
            for column, request, tier in zip(columns.tolist(), requests.tolist(), tiers.tolist())
        ]
        return np.array([-1 if number is None else number for number in made], dtype=np.int64)

    def _claim(self, columns, values, request, tier):
        request, tier = float(request), int(tier)
        if not math.isfinite(request) or request < 0:
            raise ValueError('a request is finite and at least zero')
        if tier < 0:
            raise ValueError('a priority tier is at least zero')
        if (columns >= len(self._keys)).any():
            raise ValueError('a claim reads a column that the problem does not have')
        if request == 0:
            return None
        self._claim_entries.append((columns, values))
        self._requests.append(request)
        self._tiers.append(tier)
        self._arrays = None
        return len(self._requests) - 1

    # -- arrays ------------------------------------------------------------------------------------
    def arrays(self):
        """The problem as one `Arrays` record (made once while the problem does not change)."""
        if self._arrays is None:
            self._arrays = Arrays(self)
        return self._arrays


class Arrays:
    """A problem gathered into arrays: what a `Solver` reads."""

    def __init__(self, problem):
        n = self.n = len(problem._keys)
        self.keys = list(problem._keys)
        self.lower, self.upper = _join(problem._lower), _join(problem._upper)
        self.scale, self.target = _join(problem._scale), _join(problem._target)
        self.kind = _join(problem._kind, np.int8)
        self.row_keys = list(problem._row_keys)
        m = self.m = len(self.row_keys)
        self.row_lower, self.row_upper = _join(problem._row_lower), _join(problem._row_upper)
        entries = problem._entries
        rows = _join([r for r, _, _ in entries], np.int64)
        columns = _join([c for _, c, _ in entries], np.int64)
        values = _join([v for _, _, v in entries])
        self.A = sp.csr_array((values, (rows, columns)), shape=(m, n))
        self.A.sum_duplicates()
        self.A.eliminate_zeros()
        self.objectives = list(problem._objectives)
        claims = problem._claim_entries
        self.request = np.array(problem._requests, dtype=float)
        self.tier = np.array(problem._tiers, dtype=np.int64)
        counts = np.array([len(c) for c, _ in claims], dtype=np.int64)
        self.F = sp.csr_array(
            (
                np.concatenate([v for _, v in claims]) if claims else np.zeros(0),
                np.concatenate([c for c, _ in claims]) if claims else np.zeros(0, np.int64),
                np.r_[0, np.cumsum(counts)],
            ),
            shape=(len(claims), n),
        )
        self.F.sum_duplicates()
        self.F.eliminate_zeros()  # so that a claim of one column has one entry
        self.positive = [
            (
                parts,
                sp.csr_array((matrix.data, matrix.indices, matrix.indptr), shape=(len(parts), n)),
                constants,
            )
            for parts, matrix, constants in problem._positive
        ]

    def positive_parts(self, x):
        """`x` with each positive part set to its value max(0, e.x + e0) at the other unknowns."""
        x = np.array(x, dtype=float)
        for parts, matrix, constants in self.positive:
            x[parts] = np.maximum(0.0, matrix @ x + constants)
        return x


def _register(index, keys, first, what):
    """Give each new key its position, refusing a key that is taken before any is added."""
    seen = set()
    for key in keys:
        if key in index or key in seen:
            raise ValueError(f'two {what} have the key {key!r}')
        seen.add(key)
    index.update(zip(keys, range(first, first + len(keys))))


def _terms(terms):
    columns = np.fromiter(terms.keys(), dtype=np.int64, count=len(terms))
    values = np.fromiter(terms.values(), dtype=float, count=len(terms))
    if not np.isfinite(values).all():
        raise ValueError('a coefficient is finite')
    if (columns < 0).any():
        raise ValueError('a column is at least zero')
    return columns, values


def _numbers(values, count, what):
    values = np.asarray(values, dtype=float)
    if values.ndim and values.shape != (count,):
        raise ValueError(f'one {what} for each item, or one for all')
    return np.broadcast_to(values, (count,)).astype(float)


def _join(parts, dtype=float):
    return np.concatenate(parts).astype(dtype) if parts else np.zeros(0, dtype=dtype)
