"""The fair-sharing rank: within one priority tier, raise the smallest served fraction as far as the
face allows, then the next smallest, until no claim can rise without lowering one that is no higher
(the lexicographic max-min of fraction_i = min(1, F_i . x)). Tiers go in order, tier 0 first.

The exact sequential method (prototype A3): one linear program `max t` with F_i . x >= t for each
pending claim of the tier and t <= 1. At its optimum t*, a claim whose row has a dual above TAU is at
t* in every optimal answer, by complementary slackness, and the max-min answer is one of them, so
that claim is held at t*. The duals of the claim rows sum to one (the cost of t), so each program
holds at least one claim, and t* rises or stays. When t* reaches one, every pending claim is served
in full. A claim whose columns the face has fixed reads one value in every answer, so it is held at
that value without a program (a closed flow that keeps its request).

A held claim gets the lower bound F_i . x >= t* - FIX, never an equality: t* is known only to the
feasibility tolerance of HiGHS, and an equality at the computed level made a later program
infeasible at 30,000 places (A3). A held claim cannot rise above its level in the later programs
without lowering a claim at that level, so the lower bound holds it. A claim of one column is held by
a bound of that column, and any other claim by a row. The programs run at HiGHS's tightest primal
tolerance, so that t* - FIX can be reached: at the default 1e-7, t* came out high by more than FIX on
a random network of 8 places, the face that the distance step reads was empty at 1e-9, and its
method could not converge.

After the first program of a tier only bounds change, and the last answer stays feasible, so the
later programs run the primal simplex from the last basis (A3: 5 to 40 iterations each at 3,000
places). The duals decide which claims are held, so a program whose duals have the wrong sign beyond
TAU runs again with tight tolerances (`ranked.exact`).

Budget: the linear programs that one solve may run in this step, over all its tiers. A solve that
reaches it with claims pending stops with 'fair-sharing budget exceeded', naming the levels that it
reached.
"""

from __future__ import annotations

from contextlib import ExitStack

import numpy as np
import scipy.sparse as sp

from . import ranked
from .failures import FAIR_BUDGET, NUMERICAL, SolveFailure
from .kept import INF, PRIMAL_SIMPLEX, TIGHT
from .scaled import row_max

TAU = 1e-9  # a dual above this holds its claim
FIX = 1e-7  # a held claim keeps its level to this (the feasibility tolerance of HiGHS)
FULL = 1e-9  # t* within this of one serves every pending claim in full


def share(kept, face, w, budget, work):
    """The fair-sharing rank of every tier, in order; gives the level of each claim."""
    levels = np.full(len(w.request), np.nan)
    for tier in np.unique(w.tier).tolist():
        chosen = np.flatnonzero(w.tier == tier)
        levels[chosen] = _tier(kept, face, sp.csr_array(w.F[chosen]), tier, budget, work)
    return levels


def _tier(kept, face, F, tier, budget, work):
    """The max-min levels of the claims F of one tier, which the face then holds."""
    K, width = F.shape
    levels = np.full(K, np.nan)
    fixed = face.lower == face.upper
    constant = np.diff(F.indptr) == np.diff(sp.csr_array(F[:, fixed]).indptr) if K else np.zeros(0, bool)
    if constant.any():
        levels[constant] = np.minimum(1.0, F[constant] @ np.where(fixed, face.lower, 0.0))
    pending = ~constant
    if not pending.any():
        return levels
    step = f'fair sharing, tier {tier}'
    scale = 1.0 / np.maximum(1.0, row_max(F))  # no entry of a claim row above one
    single = np.diff(F.indptr) == 1
    t = kept.add_cols([-INF], [1.0], sp.csc_array((kept.m, 1)))[0]
    cost = np.zeros(kept.n)
    cost[t] = -1.0
    kept.set_cost(cost)
    rows = sp.hstack([sp.diags_array(scale) @ F, sp.csr_array(-scale.reshape(-1, 1))]).tocsr()
    first = kept.add_rows(np.where(pending, 0.0, -INF), np.full(K, INF), rows)
    # t starts at its upper bound: with no shortage the first program needs no iteration
    kept.start_at_upper(t)
    reached = []  # t* of each program
    try:
        with ExitStack() as primal, kept.option('primal_feasibility_tolerance', TIGHT):
            while pending.any():
                if work.fair_programs >= budget.fair_programs:
                    raise _exceeded(step, reached, levels, pending, budget)
                run = ranked.solve(kept, step)
                work.programs += 1
                work.fair_programs += 1
                run = ranked.exact(kept, run, work, step)
                if len(reached) == 0:
                    primal.enter_context(kept.option('simplex_strategy', PRIMAL_SIMPLEX))
                level = float(run.x[t])
                if level >= 1.0 - FULL:
                    held, level = pending.copy(), 1.0
                else:
                    held = pending & (run.y[first] > TAU)
                    if not held.any():
                        raise SolveFailure(
                            NUMERICAL, step, 'no claim has a dual', {'programs': len(reached) + 1}
                        )
                reached.append(level)
                index = np.flatnonzero(held)
                levels[index] = level
                pending[index] = False
                _hold(kept, face, F, scale, first, index, single, level, width)
    finally:
        kept.delete_rows(first)
        kept.delete_cols([t])
        kept.set_cost(np.zeros(kept.n))
    work.levels += _distinct(reached)
    return levels


def _hold(kept, face, F, scale, first, index, single, level, width):
    """F_i . x >= level - FIX for the claims `index`: a bound for a claim of one column, else a row."""
    kept.set_row_bounds(first[index], np.full(len(index), -INF), np.full(len(index), INF))
    floor = min(level, 1.0) - FIX
    one = index[single[index]]
    if len(one):
        columns = F.indices[F.indptr[one]]
        a = F.data[F.indptr[one]]
        rising = a > 0
        # two claims can read one column (a flow and its endpoint): the larger floor wins
        np.maximum.at(face.lower, columns[rising], floor / a[rising])
        np.minimum.at(face.upper, columns[~rising], floor / a[~rising])
        kept.set_bounds(columns, face.lower[columns], face.upper[columns])
    many = index[~single[index]]
    if len(many):
        rows = sp.csr_array(sp.diags_array(scale[many]) @ F[many])
        lower = scale[many] * floor
        kept.add_rows(
            lower, np.full(len(many), INF), sp.hstack([rows, sp.csr_array((len(many), kept.n - width))])
        )
        face.add(rows, lower, np.full(len(many), INF))


def _distinct(reached):
    """The number of distinct levels among the t* of the programs (t* rises or stays)."""
    return int(sum(1 for k, level in enumerate(reached) if k == 0 or level > reached[k - 1] + FIX))


def _exceeded(step, reached, levels, pending, budget):
    count = _distinct(reached)
    held = int(np.count_nonzero(~np.isnan(levels)))
    return SolveFailure(
        FAIR_BUDGET,
        step,
        f'{count} levels in {len(reached)} programs, {int(pending.sum())} claims pending '
        f'(budget: {budget.fair_programs} programs)',
        {'levels': count, 'programs': len(reached), 'held': held, 'pending': int(pending.sum())},
    )
