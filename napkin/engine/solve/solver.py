"""The selection order of a declared solver on one kept HiGHS instance (spec: "Solver and execution
contract"):

1. the hard constraints: the bounds and rows of the problem;
2. the written objectives in order, each attained optimum kept (`ranked`);
3. fair sharing of the claims, one priority tier after another (`fair`);
4. the flows nearest their targets, then, with the flows fixed, the other unknowns nearest their
   references (`distance`).

A `Solver` belongs to one run of the engine, never to a compiled plan: the engine makes one for each
declared solver of a run, so that the state of its kept instance (basis, factorization, scaling,
fresh instances) follows from that run's own problems alone. Each `solve` takes the whole problem of
the moment. The kept instance follows it by the keys of the unknowns and rows: what left is deleted,
what joined is added at the end, and a row whose working coefficients changed is replaced. The
instance then holds the program of the problem formed fresh, in another order, and starts warm from
its last basis; each answer equals that of a fresh solve to the tolerances of the steps.

The answer is checked before it is given: each kept optimum, each fair level, and every bound and
row of the problem. A solve that cannot give the answer raises a `SolveFailure` by name and never
gives another answer in its place.

Reproducibility (the owner's rule): the same run, with the same code, configuration, seed and
thread settings on one machine, gives the same answers bit for bit, which one `Solver` for each run
and no state outside it ensure. Anything else agrees within the tolerances of the steps, not bit
for bit: a sample alone and in a batch, a solver formed fresh against a kept one, another platform.
A threshold at a tolerance boundary can fire differently there: a dual against TAU (`ranked`,
`fair`), t* against FULL (`fair`), a miss against MISS (`kept`), a residual against the stall rule
(`distance`); the work then differs, the answers agree within the tolerances, and a solve near a
budget can pass in one setting and stop by name in another.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp

from . import distance, fair, ranked
from .failures import INFEASIBLE, NUMERICAL, SolveFailure
from .kept import Kept
from .scaled import Scaled

CHECK = 1e-6  # the end checks of a row, a bound and a fair level, relative to the size of the terms


@dataclass(frozen=True)
class Budget:
    """The budgets of the two costly steps, in deterministic work (G0, D0), never in seconds, so
    that a run that succeeds on one machine succeeds on another.

    The defaults pass the cases of prototype A3 at 3,000 places with room to spare: there fair
    sharing takes 50 to 170 programs, and the distance method converges on the face that fair sharing
    leaves in 98 to 177 Newton steps (163 at 1,000 places with shortage), with no fallback
    (`scratch/rewrite/b1/solve/bench.py`). A3's QP took 20,561 iterations on that face."""

    fair_programs: int = 1000  # the linear programs of the fair-sharing step, over all tiers of a solve
    newton_steps: int = 500  # the Newton steps of each distance stage before the exact fallback
    qp_iterations: int = 100_000  # the iterations of the QP of HiGHS in that fallback


@dataclass
class Work:
    """The work that one solve did, in the units of its budgets."""

    programs: int = 0  # linear programs run (hard constraints, objectives, fair sharing)
    iterations: int = 0  # simplex iterations of those programs
    tight: int = 0  # programs run again with tight tolerances for exact duals
    renewals: int = 0  # fresh instances that took the kept one's place (`kept.Kept.run`)
    fair_programs: int = 0
    levels: int = 0  # distinct fair levels, over all tiers
    newton: list = field(default_factory=list)  # Newton steps of each distance stage
    factorizations: int = 0
    qp: list = field(default_factory=list)  # iterations of each QP fallback
    methods: list = field(default_factory=list)  # 'newton' or 'qp', for each distance stage


class Answer:
    """The answer of one solve: the value of each unknown in author units and in the order of the
    problem, each objective's optimum, each claim's fair level (its served fraction, at most one),
    and the work done."""

    def __init__(self, keys, x, optima, levels, work):
        self.keys, self.x, self.optima, self.levels, self.work = keys, x, optima, levels, work
        self._at = {key: i for i, key in enumerate(keys)}

    def __getitem__(self, key):
        return float(self.x[self._at[key]])


class Solver:
    """The selection order for one run, on one kept HiGHS instance (see the module text)."""

    def __init__(self, budget=None):
        self.budget = budget or Budget()
        self._kept = None
        self.stale = False  # the next solve starts on a fresh instance with the kept one's basis
        self._columns, self._rows = [], []  # the keys of the instance's columns and rows, in its order
        self._scale = np.zeros(0)  # the reference scale of each of its columns
        self._A = sp.csr_array((0, 0))  # its working matrix

    def renew(self):
        """The next solve starts on a fresh instance with the program and the basis of the kept one
        (`kept.Kept.fresh`): the state of the solver between two solves is then its program and its
        basis, which a checkpoint holds as data, and nothing else of HiGHS."""
        self.stale = self._kept is not None

    def solve(self, problem):
        """The answer of the selection order for `problem` (a `Problem`)."""
        if self.stale:
            self._kept, self.stale = self._kept.fresh(), False
        arrays = problem.arrays()
        _check_hard(arrays)
        w = self._follow(Scaled(arrays))
        kept, work = self._kept, Work()
        start, renewed = kept.iterations, kept.renewals
        face = ranked.Face(w)
        try:
            optima = ranked.optimize(kept, face, w, work)
            levels = fair.share(kept, face, w, self.budget, work)
            xi = distance.select(face, w, self.budget, work)
        finally:
            self._restore(w)
            work.iterations = kept.iterations - start
            work.renewals = kept.renewals - renewed
        return _answer(arrays, w, xi, optima, levels, work)

    def _follow(self, w):
        """Make the kept instance hold the program of `w`; gives `w` in the instance's order."""
        if self._kept is None:
            self._kept = Kept(w.A, w.row_lower, w.row_upper, w.lower, w.upper)
            self._remember(w)
            return w
        kept = self._kept
        keys, row_keys = w.arrays.keys, w.arrays.row_keys
        at = {key: i for i, key in enumerate(self._columns)}
        place = np.array([at.get(key, -1) for key in keys], dtype=np.int64)
        same = place >= 0
        same[same] = self._scale[place[same]] == w.scale[same]  # a new scale makes a new column
        at = {key: i for i, key in enumerate(self._rows)}
        row_place = np.array([at.get(key, -1) for key in row_keys], dtype=np.int64)
        stays = row_place >= 0
        if stays.any() and same.any():
            # a row stays only with the same working coefficients on the columns that stay
            new = sp.csr_array(w.A[np.flatnonzero(stays)][:, np.flatnonzero(same)])
            old = sp.csr_array(self._A[row_place[stays]][:, place[same]])
            change = sp.csr_array(new - old)
            change.eliminate_zeros()
            stays[np.flatnonzero(stays)[np.diff(change.indptr) > 0]] = False
        kept_columns = np.sort(place[same])
        kept_rows = np.sort(row_place[stays])
        kept.delete_rows(np.setdiff1d(np.arange(kept.m), kept_rows))
        kept.delete_cols(np.setdiff1d(np.arange(kept.n), kept_columns))
        # the instance's order: what stays, in its old order, then what joins, in the problem's order
        columns = np.r_[np.flatnonzero(same)[np.argsort(place[same])], np.flatnonzero(~same)].astype(np.int64)
        rows = np.r_[np.flatnonzero(stays)[np.argsort(row_place[stays])], np.flatnonzero(~stays)].astype(
            np.int64
        )
        joined, staying = np.flatnonzero(~same), rows[: len(kept_rows)]
        if len(joined):
            kept.add_cols(w.lower[joined], w.upper[joined], w.A[staying][:, joined])
        added = np.flatnonzero(~stays)
        if len(added):
            kept.add_rows(w.row_lower[added], w.row_upper[added], w.A[added][:, columns])
        w = w.reordered(columns, rows)
        kept.bounds(w.lower, w.upper)
        kept.row_bounds(w.row_lower, w.row_upper)
        self._remember(w)
        return w

    def _remember(self, w):
        self._columns = [w.arrays.keys[j] for j in w.columns.tolist()]
        self._rows = [w.arrays.row_keys[i] for i in w.rows.tolist()]
        self._scale, self._A = w.scale.copy(), w.A

    def _restore(self, w):
        """Take the ranks' rows, columns, bounds and costs out of the kept instance; its basis stays."""
        kept = self._kept
        if kept.m > w.m:
            kept.delete_rows(np.arange(w.m, kept.m))
        if kept.n > w.n:
            kept.delete_cols(np.arange(w.n, kept.n))
        kept.bounds(w.lower, w.upper)
        kept.row_bounds(w.row_lower, w.row_upper)
        kept.set_cost(np.zeros(kept.n))


def _check_hard(arrays):
    """The contradictions that need no program: a crossed interval, and an empty row that fails."""
    crossed = np.flatnonzero(arrays.lower > arrays.upper)
    if len(crossed):
        j = int(crossed[0])
        raise SolveFailure(
            INFEASIBLE,
            'the hard constraints',
            f'unknown {arrays.keys[j]!r} has lower bound {arrays.lower[j]} above upper bound {arrays.upper[j]}',
            {'unknown': arrays.keys[j]},
        )
    empty = np.diff(arrays.A.indptr) == 0
    failing = np.flatnonzero(
        (arrays.row_lower > arrays.row_upper) | (empty & ((arrays.row_lower > 0) | (arrays.row_upper < 0)))
    )
    if len(failing):
        i = int(failing[0])
        raise SolveFailure(
            INFEASIBLE,
            'the hard constraints',
            f'row {arrays.row_keys[i]!r} cannot hold: [{arrays.row_lower[i]}, {arrays.row_upper[i]}]',
            {'row': arrays.row_keys[i]},
        )


def _answer(arrays, w, xi, optima, levels, work):
    """The checked answer in author units and in the order of the problem."""
    x = arrays.positive_parts(w.author(xi))
    xi = x[w.columns] / w.scale
    lost = ranked.lost(w, optima, xi)
    if lost:
        k, value, best = lost[0]
        raise SolveFailure(
            NUMERICAL,
            f'objective {k}',
            f'the answer reads {value:.9g} against the optimum {best:.9g}',
            {'lost': lost},
        )
    if len(levels):
        served = w.F @ xi
        short = np.flatnonzero(served < np.minimum(levels, 1.0) - CHECK * (1.0 + abs(w.F) @ np.abs(xi)))
        if len(short):
            i = int(short[0])
            raise SolveFailure(
                NUMERICAL,
                f'fair sharing, tier {int(w.tier[i])}',
                f'claim {i} is served {served[i]:.9g} against its level {levels[i]:.9g}',
                {'claim': i},
            )
    size = 1.0 + abs(w.A) @ np.abs(xi)
    value = w.A @ xi
    missed = np.maximum(w.row_lower - value, value - w.row_upper) - CHECK * size
    outside = np.maximum(w.lower - xi, xi - w.upper) - CHECK * (1.0 + np.abs(xi))
    if (missed > 0).any() or (outside > 0).any():
        where = (
            f'row {arrays.row_keys[w.rows[int(np.argmax(missed))]]!r}'
            if (missed > 0).any()
            else f'unknown {arrays.keys[w.columns[int(np.argmax(outside))]]!r}'
        )
        raise SolveFailure(NUMERICAL, 'the end check', f'the answer misses {where}', {'where': where})
    return Answer(arrays.keys, x, tuple(v * norm for v, norm in zip(optima, w.norms)), levels, work)
