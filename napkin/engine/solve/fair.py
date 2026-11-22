"""The fair-sharing rank: within one priority tier, raise the smallest served fraction as far as the
face allows, then the next smallest, until no claim can rise without lowering one that is no higher
(the lexicographic max-min of fraction_i = min(1, max(0, F_i . x))). Tiers go in order, tier 0 first.
A fraction counts from zero (spec, "Selection order": a positive request measures its fulfilled
fraction up to 100%): a route's claim reads its signed rate in the direction of its request, below
zero where it carries against it, where its fraction is zero, the rate of its leg in that direction.
So where the smallest fraction of a part is zero, the claims that no answer serves are held at zero
and nothing more (`_unserved`), and a route may carry against its request to make room for another
one; where each claim left can be served but not all together, the part is held as below.

The exact sequential method (prototype A3): one linear program `max t` with F_i . x >= t for each
pending claim of the tier and t <= 1. At its optimum t*, a claim whose row has a dual above TAU is at
t* in every optimal answer, by complementary slackness, and the max-min answer is one of them, so
that claim is held at t*. The duals of the claim rows times their level coefficients sum to one
(the cost of the working level), so each program
holds at least one claim, and t* rises or stays. When t* reaches one, every pending claim is served
in full. A claim whose columns the face has fixed reads one value in every answer, so it is held at
that value without a program (a closed flow that keeps its request).

A held claim gets a lower bound below t* by at most FIX, never an equality: t* is known only to the
feasibility tolerance of HiGHS, and an equality at the computed level made a later program
infeasible at 30,000 places (A3). A held claim cannot rise above its level in the later programs
without lowering a claim at that level, so the lower bound holds it. A claim of one column is held by
a bound of that column, and any other claim by a row. The programs run at HiGHS's tightest primal
tolerance, so that t* - FIX can be reached: at the default 1e-7, t* came out high by more than FIX on
a random network of 8 places, the face that the distance step reads was empty at 1e-9, and its
method could not converge. At 30,000 places with need x1.45, one of 1,287 programs at that tolerance
ended on the kept instance with HiGHS's status kUnknown, which says nothing of the program; a fresh
instance holding the same program answered it, as `kept.Kept.run` does, with the same t*.

A program of a tier takes few iterations, and HiGHS keeps updating one factorization of the basis
over many of them (5,000 updates by default). At 30,000 places with need x1.7 the values drifted
from the rows by up to 3.4e-5 of their size, t* came out 3.4e-7 high, and the claims held there cut
the face (`kept`). So the programs of a tier refactorize every UPDATES updates: the drift was then at
most 5.1e-8, at no measured cost. `kept.Kept.run` checks each answer against its program as well.

The claims of a tier often fall into parts that share no row: claims and rows join only through
columns that the face leaves free, and a column that the earlier ranks fixed joins nothing (a route
that is down splits a network of places). Each part gets its own t, and one program maximizes their
sum: it is the programs of the parts side by side, so each t* is its part's level, the duals of a
part's claims sum to one, and each part holds its own claims by the rule above. A round of programs
advances every part, and the number of programs is that of the part with the most levels, not the
sum over the parts (30,000 places with 1,000 routes down: 22 programs instead of 693, 35 s instead
of 174 s, the same levels to 5e-11, prototype P1). A connected face is one part, as before.

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
from scipy.sparse.csgraph import connected_components

from . import ranked
from .failures import FAIR_BUDGET, NUMERICAL, UNBOUNDED, SolveFailure
from .kept import INF, PRIMAL_SIMPLEX, TIGHT
from .scaled import row_max

TAU = 1e-9  # a dual above this holds its claim
FIX = 1e-7  # a held claim keeps its level to this (the feasibility tolerance of HiGHS)
FULL = 1e-9  # t* within this of one serves every pending claim in full
UPDATES = 100  # the updates of a factorization of the basis before HiGHS factorizes it again
SMALL_GAIN = np.sqrt(TIGHT)  # below this, a tight fractional tolerance loses over half its digits in a rate


def share(kept, face, w, budget, work):
    """The fair-sharing rank of every tier, in order; gives the level of each claim."""
    levels = np.full(len(w.request), np.nan)
    for tier in np.unique(w.tier).tolist():
        chosen = np.flatnonzero(w.tier == tier)
        levels[chosen] = _tier(kept, face, sp.csr_array(w.F[chosen]), tier, budget, work)
    return levels


def _tier(kept, face, F, tier, budget, work):
    """The max-min levels of the claims F of one tier, which the face then holds: one program a round
    for all the parts of the tier (`_parts`), each with its own t."""
    K, width = F.shape
    levels = np.full(K, np.nan)
    fixed = face.lower == face.upper
    constant = np.diff(F.indptr) == np.diff(sp.csr_array(F[:, fixed]).indptr) if K else np.zeros(0, bool)
    if constant.any():
        levels[constant] = np.clip(F[constant] @ np.where(fixed, face.lower, 0.0), 0.0, 1.0)
    pending = ~constant
    if not pending.any():
        return levels
    step = f'fair sharing, tier {tier}'
    part = _parts(kept, F, pending, ~fixed)
    count = int(part.max()) + 1
    gain = row_max(F)
    # Each independent part can choose its own unit of t without changing its optimum. If a unit
    # of rate buys a tiny fraction, give that fraction one working unit: both the rate and the
    # level participate in the row and in the LP's reduced costs. Ordinary parts keep t in fractions.
    fraction_unit = np.ones(count)
    small = pending & (gain < SMALL_GAIN)
    if small.any():
        np.minimum.at(fraction_unit, part[small], gain[small])
    unit = fraction_unit[part]
    scale = 1.0 / np.maximum(unit, gain)
    # Where another claim of this same part gains much faster, normalizing just its rate entry
    # would vanish its t entry. Balance their magnitudes about one in that row instead.
    disparate = (unit < 1.0) & (scale * unit < SMALL_GAIN)
    scale[disparate] = np.sqrt(scale[disparate]) / np.sqrt(unit[disparate])
    t_coefficient = scale * unit
    single = np.diff(F.indptr) == 1
    t = kept.add_cols(np.full(count, -INF), 1.0 / fraction_unit, sp.csc_array((kept.m, count)))
    cost = np.zeros(kept.n)
    cost[t] = -1.0
    kept.set_cost(cost)
    claims = np.flatnonzero(pending)
    own = sp.csr_array((-t_coefficient[claims], (claims, part[claims])), shape=(K, count))
    rows = sp.hstack([sp.diags_array(scale) @ F, sp.csr_array((K, kept.n - width - count)), own]).tocsr()
    first = kept.add_rows(np.where(pending, 0.0, -INF), np.full(K, INF), rows)
    # each t starts at its upper bound: with no shortage the first program needs no iteration
    kept.start_at_upper(t)
    reached = [[] for _ in range(count)]  # t* of each program, part by part
    programs = 0
    try:
        with (
            ExitStack() as primal,
            kept.option('primal_feasibility_tolerance', TIGHT),
            kept.option('simplex_update_limit', UPDATES),
        ):
            while pending.any():
                if work.fair_programs >= budget.fair_programs:
                    raise _exceeded(step, reached, programs, levels, pending, budget)
                try:
                    run = ranked.solve(kept, step)
                except SolveFailure as failure:
                    # Every t has a finite upper bound. After adding an aggregate row, primal
                    # simplex can report an unbounded direction. Recheck with the default method.
                    if failure.name != UNBOUNDED or programs == 0:
                        raise
                    primal.close()
                    run = ranked.solve(kept, step)
                work.programs += 1
                work.fair_programs += 1
                programs += 1
                run = ranked.exact(kept, run, work, step)
                if programs == 1:
                    primal.enter_context(kept.option('simplex_strategy', PRIMAL_SIMPLEX))
                found = run.x[t] * fraction_unit  # the physical fraction of each part
                # A served fraction counts from zero: in a part whose smallest fraction is zero or
                # below, the claims that no answer serves are held at zero and nothing more, and the
                # part shares the rest (`_unserved`); where each can be served but not all together,
                # the part is held as below, on the signed fractions.
                low = pending.copy()
                low[pending] = found[part[pending]] <= FIX
                if low.any():

                    def check():
                        if work.fair_programs >= budget.fair_programs:
                            raise _exceeded(step, reached, programs, levels, pending, budget)

                    unserved = _unserved(kept, F, np.flatnonzero(low), width, step, work, check)
                    if len(unserved):
                        levels[unserved] = 0.0
                        pending[unserved] = False
                        _hold_zero(kept, face, F, scale, first, unserved, single, width)
                        continue
                full = found >= 1.0 - FULL
                for p in np.unique(part[pending]).tolist():
                    reached[p].append(1.0 if full[p] else float(found[p]))
                served = pending & full[part]
                # The dual of an unscaled claim is y_i * t_coefficient_i, with uncertainty
                # TAU * t_coefficient_i. Compare in the library's row units: a positive, resolved
                # dual still proves the level forced if the claim has a very small share of t's cost.
                held = served | (pending & ~full[part] & (run.y[first] > TAU))
                # The claim duals weighted by their t coefficients sum to t's unit cost.
                short = np.unique(part[pending & ~full[part]])
                if not np.isin(short, part[held]).all():
                    raise SolveFailure(NUMERICAL, step, 'no claim has a dual', {'programs': programs})
                index = np.flatnonzero(held)
                level = np.where(served, 1.0, found[part])[index]
                levels[index] = level
                pending[index] = False
                _hold(kept, face, F, scale, first, index, single, level, width)
    finally:
        kept.delete_rows(first)
        kept.delete_cols(t)
        kept.set_cost(np.zeros(kept.n))
    work.levels += sum(_distinct(each) for each in reached)
    return levels


def _parts(kept, F, pending, free):
    """The part of each pending claim (-1 for the others), numbered from zero in the order of their
    first claims: two claims are in one part when rows of the face (the program of the kept
    instance) and pending claims join them through columns that the face leaves free. Parts share no
    row, so one program with a t for each part solves each part as if it were alone."""
    width = F.shape[1]
    joined = sp.csr_array(
        sp.vstack([sp.csr_array(kept.A[:, :width]), F[pending]]) @ sp.diags_array(free * 1.0)
    )
    joined.eliminate_zeros()
    graph = sp.block_array([[None, joined], [joined.T, None]]).tocsr()  # rows and claims, then columns
    _, label = connected_components(graph, directed=False)
    own = label[kept.A.shape[0] : joined.shape[0]]  # the pending claims' labels
    _, first, inverse = np.unique(own, return_index=True, return_inverse=True)
    rank = np.empty(len(first), dtype=np.int64)
    rank[np.argsort(first, kind='stable')] = np.arange(len(first))
    part = np.full(F.shape[0], -1, dtype=np.int64)
    part[pending] = rank[inverse]
    return part


def _hold(kept, face, F, scale, first, index, single, level, width):
    """The lower bound at the claims' levels with the working tolerance: a bound for a claim of one
    column, else a row."""
    kept.set_row_bounds(first[index], np.full(len(index), -INF), np.full(len(index), INF))
    # FIX is an allowance in the working row. In a row scaled up to measure the physical rate,
    # a full FIX of the fraction would allow the distance step to undo part of the sharing.
    floor = np.nextafter(np.minimum(level, 1.0) - FIX / np.maximum(1.0, scale[index]), -np.inf)
    one = single[index]
    if one.any():
        claims = index[one]
        columns = F.indices[F.indptr[claims]]
        a = F.data[F.indptr[claims]]
        rising = a > 0
        # two claims can read one column (a flow and its endpoint): the larger floor wins
        np.maximum.at(face.lower, columns[rising], floor[one][rising] / a[rising])
        np.minimum.at(face.upper, columns[~rising], floor[one][~rising] / a[~rising])
        kept.set_bounds(columns, face.lower[columns], face.upper[columns])
    many = index[~one]
    if len(many):
        rows = sp.csr_array(sp.diags_array(scale[many]) @ F[many])
        lower = scale[many] * floor[~one]
        kept.add_rows(
            lower, np.full(len(many), INF), sp.hstack([rows, sp.csr_array((len(many), kept.n - width))])
        )
        face.add(rows, lower, np.full(len(many), INF))


def _unserved(kept, F, claims, width, step, work, check):
    """The claims of `claims` that no answer of the face serves: the largest F_i . x, by a program of
    its own, is at most TAU (a route's claim reads its signed rate in the direction of its request,
    which is below zero where it carries against it). The programs run on a fresh instance of the
    kept program (`kept.Kept.fresh`), so that the basis and the factorization that the tier's own
    programs go on from are the ones that they had. Each counts toward the budget of fair sharing
    (`check`)."""
    found, probe = [], kept.fresh()
    with probe.option('primal_feasibility_tolerance', TIGHT):
        for i in claims.tolist():
            check()
            cost = np.zeros(probe.n)
            start, end = F.indptr[i], F.indptr[i + 1]
            terms = F.data[start:end]
            gain = np.max(np.abs(terms))
            unit = gain if gain < SMALL_GAIN else 1.0
            cost[F.indices[start:end]] = -terms / unit
            probe.set_cost(cost)
            try:
                run = ranked.solve(probe, step)
            except SolveFailure as failure:
                if failure.name == UNBOUNDED:
                    continue  # served without end
                raise
            work.programs += 1
            work.fair_programs += 1
            if -float(run.objective) * unit <= TAU:
                found.append(i)
    return np.array(found, dtype=np.int64)


def _hold_zero(kept, face, F, scale, first, index, single, width):
    """F_i . x <= 0 for the claims `index`, which no answer serves: a bound for a claim of one column,
    else a row; their rows of the tier's program hold nothing more."""
    kept.set_row_bounds(first[index], np.full(len(index), -INF), np.full(len(index), INF))
    one = single[index]
    if one.any():
        claims = index[one]
        columns = F.indices[F.indptr[claims]]
        rising = F.data[F.indptr[claims]] > 0
        np.minimum.at(face.upper, columns[rising], 0.0)
        np.maximum.at(face.lower, columns[~rising], 0.0)
        kept.set_bounds(columns, face.lower[columns], face.upper[columns])
    many = index[~one]
    if len(many):
        rows = sp.csr_array(sp.diags_array(scale[many]) @ F[many])
        lower, upper = np.full(len(many), -INF), np.zeros(len(many))
        kept.add_rows(lower, upper, sp.hstack([rows, sp.csr_array((len(many), kept.n - width))]))
        face.add(rows, lower, upper)


def _distinct(reached):
    """The number of distinct levels among the t* of a part's programs (t* rises or stays)."""
    return int(sum(1 for k, level in enumerate(reached) if k == 0 or level > reached[k - 1] + FIX))


def _exceeded(step, reached, programs, levels, pending, budget):
    count = sum(_distinct(each) for each in reached)
    held = int(np.count_nonzero(~np.isnan(levels)))
    return SolveFailure(
        FAIR_BUDGET,
        step,
        f'{count} levels in {programs} programs, {int(pending.sum())} claims pending '
        f'(budget: {budget.fair_programs} programs)',
        {'levels': count, 'programs': programs, 'held': held, 'pending': int(pending.sum())},
    )
