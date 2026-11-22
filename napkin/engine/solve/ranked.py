"""Hard constraints and ranked objectives on one kept instance, each attained optimum kept by pinning.

After objective k, a column whose reduced cost is not zero goes to the bound it rests on, and a row
whose dual is not zero becomes an equality on the side it rests on. By complementary slackness, the
answers that meet these conditions with an optimal dual are exactly the optimal answers, whichever
optimal dual HiGHS gives, so this is the optimal face itself, and it adds no row (prototype A3,
R-A3-01: pinning lost 0 of an optimum where an added row `c.x <= optimum + tol` lost 3.1e-7, and the
row would be dense in the distance step). The end of the solve checks each optimum on the answer.

Pinning is exact only with an optimal dual. HiGHS stops when every dual has the right sign to within
its tolerance (1e-7), so a dual that it gives can have the wrong sign by less than that. A pin read
from such a dual could cut optimal answers away and change the later ranks silently. So `exact` runs
HiGHS once more, with its tightest tolerances, when a dual has the wrong sign by more than TAU; a
column or row is pinned only where its dual has the sign of the bound it rests on. (A3 pinned by the
sign of the dual alone, which sends a column with a dual of the wrong sign to its other bound.) It
does so too where the answer misses a row by more than the tightest tolerance: two rows of one
unknown that nearly tie (a moving solver whose two bounds meet) were answered on the looser, the
other missed by less than 1e-7, and the pin of the looser left the later ranks an empty face.

All values are in working units (`scaled.Scaled`), where each objective has a largest coefficient of
one.
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from .failures import INFEASIBLE, NUMERICAL, UNBOUNDED, SolveFailure
from .kept import OPTIMAL, TIGHT, Status

TAU = 1e-9  # a reduced cost or a dual above this is not zero
KEPT = 1e-7  # an optimum is kept to this, relative to the size of its terms (HiGHS's feasibility)
NEAR = 1e-9  # a value this near its bound, relative to the bound's size, rests on it


class Face:
    """The feasible set as the ranks narrow it: the bounds of the columns and the rows of the
    problem, and the rows that fair sharing adds (sparse rows over the columns, with their bounds)."""

    def __init__(self, w):
        self.lower, self.upper = w.lower.copy(), w.upper.copy()
        self.row_lower, self.row_upper = w.row_lower.copy(), w.row_upper.copy()
        self.extra = []

    def add(self, rows, lower, upper):
        self.extra.append((sp.csr_array(rows), np.asarray(lower, float), np.asarray(upper, float)))

    def arrays(self, A):
        """(rows, row_lower, row_upper) of the face: the problem's rows `A` and the added ones."""
        if not self.extra:
            return A, self.row_lower, self.row_upper
        width = A.shape[1]
        extra = [sp.csr_array(rows[:, :width]) for rows, _, _ in self.extra]
        return (
            sp.vstack([A, *extra]).tocsr(),
            np.concatenate([self.row_lower, *(lower for _, lower, _ in self.extra)]),
            np.concatenate([self.row_upper, *(upper for _, _, upper in self.extra)]),
        )


def solve(kept, step, first=False):
    """One run of the kept instance, or the named failure of its status. `first` marks the first
    program of a solve, whose infeasibility is that of the hard constraints; a later program runs
    on a face that an earlier one found feasible, so its infeasibility is numerical. A run that is no
    answer (a status that says nothing of the program, or an optimum whose values miss it) is the last
    of three: the kept instance, then two fresh ones (`kept.Kept.run`)."""
    run = kept.run()
    if run.status == OPTIMAL and run.answered:
        return run
    status = run.status
    reached = {'status': str(status).split('.')[-1]}
    if status == OPTIMAL:
        reached.update(missed=run.missed, rows=kept.m, columns=kept.n)
        raise SolveFailure(
            NUMERICAL,
            step,
            f'the optimum of HiGHS misses the program by {run.missed:.1e} of the size of its terms on a '
            f'program of {kept.m} rows and {kept.n} columns, and so did two fresh instances of it',
            reached,
        )
    if status == Status.kUnboundedOrInfeasible:
        # the presolve of HiGHS can tell only that one of the two holds; a run with no cost decides
        status = Status.kUnbounded if not first or _feasible(kept) else Status.kInfeasible
    if status == Status.kInfeasible and first:
        raise SolveFailure(INFEASIBLE, 'the hard constraints', 'no answer meets them', reached)
    if status == Status.kInfeasible:
        raise SolveFailure(NUMERICAL, step, 'no answer on the face that the earlier ranks left', reached)
    if status == Status.kUnbounded:
        raise SolveFailure(UNBOUNDED, step, 'the objective has no finite optimum', reached)
    reached.update(rows=kept.m, columns=kept.n)
    raise SolveFailure(
        NUMERICAL,
        step,
        f'HiGHS ended with the status {reached["status"]} on a program of {kept.m} rows and {kept.n} '
        'columns, and so did two fresh instances of it, one with its basis and one with none',
        reached,
    )


def _feasible(kept):
    """Whether the hard constraints have an answer: a run with no cost (the solve stops after it)."""
    kept.set_cost(np.zeros(kept.n))
    return kept.run().status == OPTIMAL


def exact(kept, run, work, step):
    """`run`, or a second run with tight tolerances when a dual of `run` has the wrong sign by more
    than TAU, or when its answer misses a row or a bound of the program by more than the tight
    tolerance (`Kept._missed`): HiGHS holds a row to its own tolerance, so where two rows nearly tie
    it can answer on one and miss the other, and a pin of that answer would make an equality that
    the other row cuts away, a face that the ranks after it, which hold their rows to the tight
    tolerance, find empty. The miss is measured as those ranks measure it, in the program's working
    units (`missed_by`). Measured relative to the size of the terms, a miss of 2.1e-10 on a row of
    size 3 read 7e-11, passed, and left the next rank an empty face (a moving solver whose two
    bounds meet, on one platform's arithmetic)."""
    if _wrong_sign(kept, run) > TAU or (run.missed_by is not None and run.missed_by > TIGHT):
        work.tight += 1
        run = kept.tight()
        if run.status != OPTIMAL or not run.answered:
            reached = {'status': str(run.status).split('.')[-1]}
            raise SolveFailure(
                NUMERICAL, step, 'a run with tight tolerances ended without an answer', reached
            )
    return run


def _sides(value, lower, upper):
    """Whether each value rests on its lower and on its upper bound. HiGHS gives a column that is
    not basic exactly its bound; a row's value is its activity, so it is near its bound."""
    low = np.isfinite(lower) & (np.abs(value - lower) <= NEAR * (1.0 + np.abs(lower)))
    high = np.isfinite(upper) & (np.abs(value - upper) <= NEAR * (1.0 + np.abs(upper)))
    return low, high


def _wrong_sign(kept, run):
    """The largest dual of the wrong sign for the side that its column or row rests on."""
    return max(
        _wrong(run.x, run.d, kept.lower, kept.upper),
        _wrong(run.row_value, run.y, kept.row_lower, kept.row_upper),
    )


def _wrong(value, dual, lower, upper):
    if not len(dual):
        return 0.0
    low, high = _sides(value, lower, upper)
    bad = np.where(low, -dual, np.where(high, dual, np.abs(dual)))
    bad[low & high] = 0.0  # a fixed column or an equality row takes a dual of either sign
    return float(bad.max(initial=0.0))


def pin(kept, face, run):
    """Narrow `face` and the kept instance to the optimal face of `run`: (columns, rows) pinned."""
    lower, upper = face.lower, face.upper
    width = len(lower)
    low, high = _sides(run.x[:width], lower, upper)
    d = run.d[:width]
    up = low & ~high & (d > TAU)
    down = high & ~low & (d < -TAU)
    upper[up] = lower[up]
    lower[down] = upper[down]
    changed = np.flatnonzero(up | down)
    kept.set_bounds(changed, lower[changed], upper[changed])
    m = len(face.row_lower)
    row_lower, row_upper = face.row_lower, face.row_upper
    low, high = _sides(run.row_value[:m], row_lower, row_upper)
    y = run.y[:m]
    rising = low & ~high & (y > TAU)
    falling = high & ~low & (y < -TAU)
    row_upper[rising] = row_lower[rising]
    row_lower[falling] = row_upper[falling]
    pinned = np.flatnonzero(rising | falling)
    kept.set_row_bounds(pinned, row_lower[pinned], row_upper[pinned])
    return len(changed), len(pinned)


def optimize(kept, face, w, work):
    """The hard constraints, then each objective in written order, each optimum pinned. Gives the
    optima in working units; with no objective, one run with no cost finds the hard constraints
    feasible."""
    optima = []
    if not w.costs:
        kept.set_cost(np.zeros(kept.n))
        solve(kept, 'the hard constraints', first=True)
        work.programs += 1
        return optima
    for k, cost in enumerate(w.costs):
        kept.set_cost(np.r_[cost, np.zeros(kept.n - len(cost))])
        step = f'objective {k + 1}'
        run = solve(kept, step, first=k == 0)
        work.programs += 1
        run = exact(kept, run, work, step)
        optima.append(float(run.objective))
        pin(kept, face, run)
    kept.set_cost(np.zeros(kept.n))
    return optima


def lost(w, optima, xi):
    """The objectives whose optimum the answer `xi` (working units) does not keep, each with its
    value and its optimum. Each term is held to KEPT of its size: a sum of 300 shortfalls that the
    QP of HiGHS holds each to its tolerance loses 6.7e-6 of an optimum of 0.38, which a tolerance of
    the whole sum (A3's 1e-7 * max(1, |c|.|x|)) refuses."""
    out = []
    for k, (cost, best) in enumerate(zip(w.costs, optima)):
        value = float(cost @ xi)
        if value > best + KEPT * float(np.abs(cost) @ (1.0 + np.abs(xi))):
            out.append((k + 1, value, best))
    return out
