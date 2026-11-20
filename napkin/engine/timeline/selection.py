"""The selection order of local sharing on one coupled part of a network, in floats.

Outside a declared solver, the unknowns of a coupled part (`network.py`: the rate of a directed flow,
the signed rate of a reversible route, the served fraction of a flow with legs) follow the spec's
selection order with no objective (spec, "Local allocation"; the oracle's `tests/reference/order.py`):

1. the hard rows: each unknown within its bounds, and each row `a.x <= b` or `a.x == b` (the
   capacity of an endpoint, the row of a store that rests on a bound). A row can also hold positive
   parts, `a.x + sum(max(s * x_j, 0)) <= b` (`Rows.convex`): the capacity of an endpoint that a leg
   of a route meets, which carries the positive part of the route's rate in its direction;
2. fair sharing, tier by tier: the smallest served fraction of the claims of a tier is made as large
   as it can be, then the next. A claim is (a, request): its served fraction is a.x / request,
   counted up to one. A claim that cannot rise above its level while the others keep theirs is held
   there by an equality; a claim served in full keeps the lower bound `a.x >= request`, so that a
   later tier can still raise its rate (a request is soft, D15);
3. the preferred routes of each aggregate request, in order: as much of its amount on them as can be;
4. the unknowns nearest their targets (a rate's request, a fraction's one): the least squared
   distance.

Ranks 2 and 3 are linear programs of HiGHS (`continuous/highs.py`); a positive part takes one more
unknown of the program, at least the part and zero. HiGHS holds a row to an absolute tolerance, so
its programs are in units of the part (each rate in units of the part's size, a fraction as it is),
the rows of a claim are written in served fractions, so that the tolerance is relative to what it
asks, and a level is the optimum value of its program, which no point of it lies past.

Rank 4 is the projection of the targets onto the rows that the earlier ranks leave. From the point of
the last program, where that point holds every row, by the primal active-set method: where the point
is the answer it stays as it is, with the numbers of its vertex (an event time that follows from the
rates is then exact). Otherwise (a row of a program holds only to HiGHS's tolerance, and the primal
method can keep that or cycle at a degenerate vertex), or where the primal method does not settle,
by the dual active-set method of Goldfarb and Idnani: it starts from the targets, needs no feasible
point, adds the row that the point breaks most, each row held to the size of its own terms, and ends
in a finite number of steps, exact but for roundoff. A row with positive parts joins it through its
linear piece at the point. A part that does not settle stops the run (`SimulationError`) and never
gets another answer.

What follows rank 4 changes the answer only by roundoff: an unknown within it of zero or of a bound
is put there, and the point then exactly on the rows that it holds by the other unknowns (`_exact`):
an unknown at zero or at a bound stays there, so a junction that a route at zero meets balances
exactly. Each change is a
candidate that takes the answer's place only where it is no worse on any rank, the last included, as
a change of a declared solver's answer (`_kept`; `solve.Answer.admits`): it holds every row as the
answer does, serves each claim no less, and is no farther from the targets but by its roundings. So
a small delivery in a large part is never taken for roundoff, and no delivery moves onto a flow that
does not ask for it.
"""

from __future__ import annotations

import math

import numpy as np

from ..continuous import highs
from ..errors import SimulationError
from ..solve.solver import farther, rate_rounding

TIGHT = 1e-9  # a claim can rise above its level only by more than this part of it (the oracle's)
FEASIBLE = 1e-9  # a row holds to this part of the size of its terms
BREAKS = 1e-12  # rank 4 takes a row that the point breaks by more than this part of its terms
NOISE = 1e-2  # the roundoff of a term, as a part of BREAKS times the largest unknown of the part
STEPS = 50  # the most steps of rank 4, for each unknown and row of the part


class Rows:
    """The hard rows of a part over its n unknowns: `a.x <= b` (`upper`), `a.x == b` (`equal`), and
    `a.x + sum(max(s * x_j, 0) for j, s in parts) <= b` (`convex`)."""

    def __init__(self, n):
        self.n, self.upper, self.equal, self.convex = n, [], [], []

    def at_most(self, a, b):
        self.upper.append((np.asarray(a, dtype=float), float(b)))

    def at_least(self, a, b):
        self.upper.append((-np.asarray(a, dtype=float), -float(b)))

    def equal_to(self, a, b):
        self.equal.append((np.asarray(a, dtype=float), float(b)))

    def with_parts(self, a, parts, b):
        """`a.x` plus the positive part of `s * x_j` for each (j, s) of `parts`, at most b."""
        self.convex.append((np.asarray(a, dtype=float), tuple(parts), float(b)))


def _program(rows, limits, cost, upper=(), equal=()):
    """Minimize cost.z over z: the unknowns of the part, then any unknowns of this program alone,
    within `limits`; `upper` and `equal` are rows over the whole of z. Each positive part of a row of
    `rows.convex` takes one more unknown, at least the part and zero; the result leaves them out."""
    width = len(cost)
    extra = sum(len(parts) for _, parts, _ in rows.convex)
    total = width + extra

    def wide(a):
        return np.concatenate([a, np.zeros(total - len(a))])

    a_ub = [wide(a) for a, _ in rows.upper] + [wide(a) for a, _ in upper]
    b_ub = [b for _, b in rows.upper] + [b for _, b in upper]
    column = width
    for a, parts, b in rows.convex:
        row = wide(a)
        for j, sign in parts:
            part = np.zeros(total)
            part[j], part[column] = sign, -1.0
            a_ub.append(part)  # s * x_j <= u
            b_ub.append(0.0)
            row[column] = 1.0
            column += 1
        a_ub.append(row)
        b_ub.append(b)
    a_eq = [wide(a) for a, _ in rows.equal] + [wide(a) for a, _ in equal]
    b_eq = [b for _, b in rows.equal] + [b for _, b in equal]
    found = highs.solve(
        np.concatenate([np.asarray(cost, dtype=float), np.zeros(extra)]),
        np.array(a_ub, dtype=float).reshape(len(a_ub), total),
        np.array(b_ub, dtype=float),
        np.array(a_eq, dtype=float).reshape(len(a_eq), total) if a_eq else None,
        np.array(b_eq, dtype=float) if b_eq else None,
        [*limits, *[(0.0, math.inf)] * extra],
    )
    if found.success:
        found.x = found.x[:width]
    return found


def _failed(result, what):
    status = getattr(result, 'status', None)
    reason = 'the hard rows have no answer' if status == 2 else getattr(result, 'message', 'no optimum')
    raise SimulationError(f'local sharing: {what}: {reason}')


def _share(rows, limits, claims):
    """Rank 2 for the claims of one tier: their rows are added to `rows`, in served fractions.

    A served fraction counts from zero (spec, "Selection order"): a route's claim is its signed rate
    in the direction of its request, below zero where it carries against it, and its fraction is
    then zero, the rate of its leg in that direction. So where the smallest fraction is zero, a claim
    that no point serves is held at zero and nothing more, and a route may carry against its request
    to make room for another one; where every claim left can be served alone, but not all of them
    together, the tier is shared on their signed fractions, as before (the oracle's
    `order._maxmin`)."""
    n = rows.n
    pending = [np.asarray(a, dtype=float) / r for a, r in claims]  # f.x is the served fraction
    while pending:
        cost = np.zeros(n + 1)
        cost[-1] = -1.0
        floor = [(np.concatenate([-f, [1.0]]), 0.0) for f in pending]
        found = _program(rows, [*limits, (-math.inf, 1.0)], cost, floor)
        if not found.success:
            _failed(found, 'the fair level of a tier')
        # The level is the optimum of the program: its value, which no point of it can lie past.
        level = min(1.0, -float(found.fun))
        if level >= 1.0 - 1e-12:
            for f in pending:
                rows.at_least(f, 1.0)
            return
        if level <= TIGHT:
            # The smallest fraction is zero: the claims that no point serves are held there.
            unserved = []
            for f in pending:
                found = _program(rows, limits, -f, [])
                if getattr(found, 'status', 0) != 3 and found.success and -found.fun <= TIGHT:
                    unserved.append(f)
            if unserved:
                for f in unserved:
                    rows.at_most(f, 0.0)
                pending = [f for f in pending if not any(f is g for g in unserved)]
                continue
        hold = [(-f, -level) for f in pending]
        still = []
        for f in pending:
            # Can this claim rise above the level while every pending claim keeps it?
            found = _program(rows, limits, -f, hold)
            if getattr(found, 'status', 0) == 3:
                still.append(f)
                continue
            if not found.success:
                _failed(found, 'a claim at its fair level')
            if -found.fun > level + TIGHT:
                still.append(f)
            else:
                rows.equal_to(f, level)
        if len(still) == len(pending):
            raise SimulationError('local sharing: fair sharing made no progress in a tier')
        pending = still


def _prefer(rows, limits, a, amount):
    """Rank 3 for one preferred route: as much of `amount` on `a.x` as can be."""
    n = rows.n
    share = np.asarray(a, dtype=float) / amount  # the part of the amount on the route
    cost = np.zeros(n + 1)
    cost[-1] = -1.0
    found = _program(rows, [*limits, (-math.inf, 1.0)], cost, [(np.concatenate([-share, [1.0]]), 0.0)])
    if not found.success:
        _failed(found, 'a preferred route')
    rows.at_least(share, min(1.0, -float(found.fun)))
    return found.x[:n]


def _plain(rows, lower, upper):
    """The rows of a part without positive parts, with the bounds of its unknowns, as (a, b,
    equality)."""
    n = rows.n
    eye = np.eye(n)
    plain = [(a, b, True) for a, b in rows.equal] + [(a, b, False) for a, b in rows.upper]
    plain += [(eye[j], float(upper[j]), False) for j in range(n) if math.isfinite(upper[j])]
    plain += [(-eye[j], -float(lower[j]), False) for j in range(n) if math.isfinite(lower[j])]
    return plain


def _size(a, b, x, target):
    """The size of the terms of a row at x, and of the roundoff that the largest unknown leaves in
    each of its terms: a row of small unknowns is held to its own size, down to that."""
    scale = max(float(np.abs(x).max(initial=0.0)), float(np.abs(target).max(initial=0.0)))
    return abs(b) + np.abs(a) @ (np.abs(x) + np.abs(target)) + NOISE * float(np.abs(a).sum()) * scale


def _holds(rows, plain, x, target):
    """Whether x holds every row of a part, each to `FEASIBLE` of its size."""
    for a, b, is_equal in plain:
        gap = a @ x - b
        if (abs(gap) if is_equal else gap) > FEASIBLE * _size(a, b, x, target):
            return False
    for a, parts, b in rows.convex:
        gap = a @ x + sum(max(sign * x[j], 0.0) for j, sign in parts) - b
        if gap > FEASIBLE * (_size(a, b, x, target) + sum(abs(x[j]) for j, _ in parts)):
            return False
    return True


def nearest(rows, lower, upper, target, start, size):
    """Rank 4: the point of the rows and bounds nearest `target`. From the point `start` of the
    linear programs, when it holds every row and no row has positive parts, by the primal
    active-set method, in units of the part's `size` (its tolerances are absolute): where that
    point is the answer it stays as it is, with the numbers of its vertex. Otherwise, or where the
    primal method does not settle, by the dual method, which needs no feasible start (see the
    module)."""
    target = np.asarray(target, dtype=float)
    plain = _plain(rows, lower, upper)
    start = np.clip(np.asarray(start, dtype=float), lower, upper)
    if not rows.convex and _holds(rows, plain, start, target):
        # The same distance in any unit of all the unknowns: the rows scale with them.
        scaled = Rows(rows.n)
        scaled.upper = [(a, b / size) for a, b in rows.upper]
        scaled.equal = [(a, b / size) for a, b in rows.equal]
        try:
            return size * _primal(scaled, lower / size, upper / size, target / size, start / size)
        except SimulationError:
            pass
    return _dual(rows, plain, lower, upper, target)


def _primal(rows, lower, upper, target, start):
    """The primal active-set method from the feasible point `start`."""
    n = rows.n
    plain = [(a, b) for a, b, is_equal in _plain(rows, lower, upper) if not is_equal]
    G = np.array([a for a, _ in plain], dtype=float).reshape(len(plain), n)
    g = np.array([b for _, b in plain], dtype=float)
    E = np.array([a for a, _ in rows.equal], dtype=float).reshape(len(rows.equal), n)
    e = np.array([b for _, b in rows.equal], dtype=float)
    E, e = _independent(E, e)
    x = start
    size = 1.0 + np.abs(g) + np.abs(G) @ (np.abs(x) + np.abs(target))
    working = []
    for i in np.flatnonzero(g - G @ x <= FEASIBLE * size).tolist():
        trial = np.vstack([E, G[[*working, i]]])
        if np.linalg.matrix_rank(trial, tol=1e-12 * max(1.0, np.abs(trial).max())) == len(trial):
            working.append(i)
    scale = 1.0 + float(np.abs(target).max(initial=0.0)) + float(np.abs(x).max(initial=0.0))
    for _ in range(STEPS * (n + len(g) + 1)):
        A = np.vstack([E, G[working]])
        d = target - x
        if len(A):
            coefficients = np.linalg.lstsq(A.T, d, rcond=None)[0]
            p = d - A.T @ coefficients
        else:
            coefficients, p = np.zeros(0), d
        if np.abs(p).max(initial=0.0) <= 1e-13 * scale:
            multipliers = coefficients[len(E) :]
            if not len(multipliers) or multipliers.min() >= -1e-12 * scale:
                break
            working.pop(int(np.argmin(multipliers)))
            continue
        moved = G @ p
        slack = np.maximum(g - G @ x, 0.0)
        step, blocking = 1.0, None
        for i in np.flatnonzero(moved > 1e-15 * scale).tolist():
            if i not in working and slack[i] / moved[i] < step:
                step, blocking = slack[i] / moved[i], i
        x = x + step * p
        if blocking is not None:
            working.append(blocking)
    else:
        raise SimulationError('local sharing: the rates nearest their requests did not settle')
    x = np.clip(x, lower, upper)
    if not _holds(rows, _plain(rows, lower, upper), x, target):
        raise SimulationError('local sharing: the rates nearest their requests break a hard row')
    return x


def _independent(matrix, values):
    """The rows of `matrix` that add to the rank of those before them, with their values."""
    kept = []
    for i in range(len(matrix)):
        trial = matrix[[*kept, i]]
        if np.linalg.matrix_rank(trial, tol=1e-12 * max(1.0, np.abs(trial).max())) == len(kept) + 1:
            kept.append(i)
    return matrix[kept], values[kept]


def _dual(rows, plain, lower, upper, target):
    """The dual active-set method of Goldfarb and Idnani (see the module). The active rows are kept
    independent: a row in their span makes a dual step, which drops the row whose multiplier would
    turn negative first."""
    n = rows.n
    x = target.copy()
    normals, equal, multipliers = [], [], []  # the active rows

    def size(a, b):
        return _size(a, b, x, target)

    def broken():
        """The row that x breaks most, by its distance, as (a, b, equality), or None."""
        worst, found = 0.0, None
        for a, b, is_equal in plain:
            # An equality that x breaks below is the row `-a.x <= -b`.
            sign = -1.0 if is_equal and a @ x < b else 1.0
            gap = sign * (a @ x - b)
            if gap > BREAKS * size(a, b):
                distance = gap / max(float(np.linalg.norm(a)), 1e-300)
                if distance > worst:
                    worst, found = distance, (sign * a, sign * b, is_equal)
        for a, parts, b in rows.convex:
            # The linear piece of the row at x: each part whose argument is positive there.
            piece = a.copy()
            for j, sign in parts:
                if sign * x[j] > 0:
                    piece[j] += sign
            gap = piece @ x - b
            if gap > BREAKS * size(piece, b):
                distance = gap / max(float(np.linalg.norm(piece)), 1e-300)
                if distance > worst:
                    worst, found = distance, (piece, b, False)
        return found

    for _ in range(STEPS * (n + len(plain) + len(rows.convex) + 1)):
        chosen = broken()
        if chosen is None:
            break
        a, b, is_equal = chosen
        added = 0.0  # the multiplier of the chosen row
        while True:
            if normals:
                matrix = np.array(normals).T
                r = np.linalg.lstsq(matrix, a, rcond=None)[0]
                z = matrix @ r - a  # the step of x: minus the part of a outside the active rows
            else:
                r, z = np.zeros(0), -a
            # The longest step before the multiplier of an active row turns negative.
            partial, leaving = math.inf, None
            largest = float(np.abs(r).max(initial=0.0))
            for k, (value, is_eq) in enumerate(zip(multipliers, equal)):
                if not is_eq and r[k] > 1e-12 * largest and value / r[k] < partial:
                    partial, leaving = value / r[k], k
            # The chosen row is in the span of the active rows when the step of x is no step.
            room = float(z @ z)
            gap = a @ x - b
            full = gap / room if room > 1e-20 * float(a @ a) else math.inf
            if math.isinf(full) and math.isinf(partial):
                raise SimulationError('local sharing: the rows of the nearest rates have no answer')
            step = min(full, partial)
            if not math.isinf(full):
                x = x + step * z
            multipliers = [value - step * r[k] for k, value in enumerate(multipliers)]
            added += step
            if step == full:
                normals.append(a)
                equal.append(is_equal)
                multipliers.append(added)
                break
            for found in (normals, equal, multipliers):
                found.pop(leaving)
    else:
        raise SimulationError('local sharing: the rates nearest their requests did not settle')
    x = np.clip(x, lower, upper)
    if not _holds(rows, plain, x, target):
        raise SimulationError('local sharing: the rates nearest their requests break a hard row')
    return x


def size_of(rows, upper, tiers, prefs, target):
    """The size of a part whose unknowns are all rates: its largest request or preferred amount,
    else its largest finite capacity or row, else one."""
    asked = [abs(float(r)) for claims in tiers for _, r in claims]
    asked += [abs(float(amount)) for _, amount in prefs]
    asked += np.abs(np.asarray(target, dtype=float)).tolist()
    found = max(asked, default=0.0)
    if found > 0.0:
        return found
    limits = [float(c) for c in np.asarray(upper, dtype=float) if math.isfinite(c)]
    limits += [abs(b) for _, b in (*rows.upper, *rows.equal)]
    limits += [abs(b) for _, _, b in rows.convex]
    found = max(limits, default=0.0)
    return found if found > 0.0 else 1.0


def select(rows, lower, upper, tiers, prefs, target, units=None):
    """The unknowns of one coupled part: `rows` (`Rows`, in the units of the rates), the bounds of
    each unknown (-inf and inf for none), the tiers of claims in order (each a list of (a,
    request)), the preferred routes in order (each (a, amount)) and the target of each unknown
    (rank 4).

    HiGHS holds a row to an absolute tolerance, so its programs are in units of the part: each
    unknown in its own unit (`units`: the size of the part for a rate, one for a served fraction;
    all rates in the units of `size_of` when it is None), and each row over the size of the part.
    The selection order gives the same answer in any unit (a served fraction is a ratio, and the
    rows scale with the rates), so the change is exact but for roundoff. Rank 4 is in the units of
    the rates, as the distance is: its tolerances are relative to each row."""
    n = rows.n
    lower, upper = np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)
    target = np.asarray(target, dtype=float)
    if units is None:
        units = np.full(n, size_of(rows, upper, tiers, prefs, target))
    units = np.asarray(units, dtype=float)
    size = float(units.max(initial=1.0))
    # The programs read z = x / units, and each row over the size of the part.
    scaled = Rows(n)
    scaled.upper = [(a * units / size, b / size) for a, b in rows.upper]
    scaled.equal = [(a * units / size, b / size) for a, b in rows.equal]
    scaled.convex = [
        (a * units / size, tuple((j, s * units[j] / size) for j, s in parts), b / size)
        for a, parts, b in rows.convex
    ]
    limits = [(float(lo / u), float(hi / u)) for lo, hi, u in zip(lower, upper, units)]
    found = _program(scaled, limits, np.zeros(n))
    if not found.success:
        _failed(found, 'the hard rows')
    start = found.x
    made = len(scaled.upper), len(scaled.equal)
    for claims in tiers:
        _share(scaled, limits, [(np.asarray(a, dtype=float) * units / size, r / size) for a, r in claims])
    for a, amount in prefs:
        start = _prefer(scaled, limits, np.asarray(a, dtype=float) * units / size, amount / size)
    if tiers and not prefs:
        found = _program(scaled, limits, np.zeros(n))
        if not found.success:
            _failed(found, 'the rows of fair sharing')
        start = found.x
    # The rows of the ranks, back in the units of the rates: f.z = f.(x / units).
    final = Rows(n)
    final.upper = rows.upper + [(f / units, b) for f, b in scaled.upper[made[0] :]]
    final.equal = rows.equal + [(f / units, b) for f, b in scaled.equal[made[1] :]]
    final.convex = rows.convex
    found = nearest(final, lower, upper, target, start * units, size)
    if not np.isfinite(found).all():
        raise SimulationError('local sharing: the rates of a part are no finite numbers')
    # The roundoff of the linear algebra is no rate: an unknown within it of zero or of a bound is
    # put there, so that a junction or a store at its bound is held exactly, and then on the rows
    # that it holds. Each is a candidate for the answer (`_kept`).
    snapped = found.copy()
    snapped[np.abs(snapped) <= 1e-12 * units] = 0.0
    for bound in (lower, upper):
        with np.errstate(invalid='ignore'):
            near = np.isfinite(bound) & (np.abs(snapped - bound) <= 1e-12 * (units + np.abs(bound)))
        snapped[near] = bound[near]
    claims = [claim for tier in tiers for claim in tier] + list(prefs)
    candidates = (_exact(final, lower, upper, snapped, target), snapped)
    return _kept(final, lower, upper, target, claims, found, candidates)


def _kept(rows, lower, upper, target, claims, answer, candidates):
    """The first of `candidates` (changes of `answer` after the selection order) that is no worse
    than the answer on any rank, the last included: it holds every row and bound of the part as the
    answer does (`_holds`, the end check of rank 4), serves each claim and each preferred route's
    share (`claims`, as (a, request)) no less than the answer serves it, to `FEASIBLE`, and is no
    farther from the targets (`solve.solver.farther`, the rule of every change of a published answer):
    a correction fits FEASIBLE of the coordinate's own value or target, and a flow selected at
    zero stays zero. Else the answer. A change
    that would take a small delivery for the roundoff of a large part, break a row, or move a
    delivery onto a flow that does not ask for it, is dropped."""
    plain = _plain(rows, lower, upper)

    def served(x):  # from zero (a route against its request) up to one
        return np.array([min(1.0, max(0.0, float(np.asarray(a, dtype=float) @ x) / r)) for a, r in claims])

    floor = served(answer) - FEASIBLE * (1.0 + np.abs(served(answer)))
    precision = FEASIBLE * np.maximum(np.abs(answer), np.abs(target))
    for candidate in candidates:
        if (
            rate_rounding(candidate, answer, precision)
            and _holds(rows, plain, candidate, target)
            and (served(candidate) >= floor).all()
            and farther(candidate, answer, target, precision) <= 0
        ):
            return candidate
    return answer


def _exact(rows, lower, upper, x, target):
    """The point x put exactly on the plain rows that it holds, by the least change of the unknowns
    that rest on no bound, are not zero and meet no row with positive parts. The programs read each
    rate in units of the part and each claim in served fractions, so a vertex comes back from them
    with the roundoff of those changes (3 L/h over a part of 5 L/h came back 1e-15 short, which moved
    the time at which a tank emptied); the rows that hold it give its numbers again. An unknown at
    zero is exact already (the snap of `select` put it there) and stays: the change of the least
    squares would give it the roundoff of the others, and a route at zero that is the one connection
    of a `[0, 0]` junction would then move the junction off its balance. The change is a candidate,
    which `_kept` checks."""
    loose = (x != lower) & (x != upper) & (x != 0)
    for _, parts, _ in rows.convex:
        loose[[j for j, _ in parts]] = False
    free = np.flatnonzero(loose)
    held = [
        (a, b)
        for a, b, is_equal in _plain(rows, lower, upper)
        if np.abs(a).sum() > 0 and (is_equal or abs(a @ x - b) <= FEASIBLE * _size(a, b, x, target))
    ]
    if not len(free) or not held:
        return x
    A = np.array([a for a, _ in held], dtype=float)
    residual = np.array([b for _, b in held], dtype=float) - A @ x
    if not np.abs(residual).max() > 0:
        return x
    found = x.copy()
    found[free] += np.linalg.lstsq(A[:, free], residual, rcond=None)[0]
    return np.clip(found, lower, upper)
