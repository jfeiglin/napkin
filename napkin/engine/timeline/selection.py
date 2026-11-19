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
unknown of the program, at least the part and zero. HiGHS holds a row to an absolute tolerance, so a
part is solved in units of its size (`size_of`), and the rows of a claim are written in served
fractions, so that the tolerance is relative to what it asks. Rank 4 is the projection of the targets
onto the rows that the earlier ranks leave, by the dual active-set method of Goldfarb and Idnani: it
starts from the targets, needs no feasible point (a row of a linear program holds only to HiGHS's
tolerance), adds the row that the point breaks most, relative to the size of its terms, and ends in a
finite number of steps, exact but for roundoff. A row with positive parts joins it through its
linear piece at the point. A part that does not settle stops the run (`SimulationError`) and never
gets another answer.
"""

from __future__ import annotations

import math

import numpy as np

from ..continuous import highs
from ..errors import SimulationError

TIGHT = 1e-9  # a claim can rise above its level only by more than this part of it (the oracle's)
FEASIBLE = 1e-9  # a row holds to this part of the size of its terms
BREAKS = 1e-12  # rank 4 takes a row that the point breaks by more than this part of its terms
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

    def scaled(self, size):
        """The same rows in units of `size`."""
        found = Rows(self.n)
        found.upper = [(a, b / size) for a, b in self.upper]
        found.equal = [(a, b / size) for a, b in self.equal]
        found.convex = [(a, parts, b / size) for a, parts, b in self.convex]
        return found


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
    """Rank 2 for the claims of one tier: their rows are added to `rows`, in served fractions."""
    n = rows.n
    pending = [np.asarray(a, dtype=float) / r for a, r in claims]  # f.x is the served fraction
    while pending:
        cost = np.zeros(n + 1)
        cost[-1] = -1.0
        floor = [(np.concatenate([-f, [1.0]]), 0.0) for f in pending]
        found = _program(rows, [*limits, (-math.inf, 1.0)], cost, floor)
        if not found.success:
            _failed(found, 'the fair level of a tier')
        level = min(1.0, float(found.x[-1]))
        if level >= 1.0 - 1e-12:
            for f in pending:
                rows.at_least(f, 1.0)
            return
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
    rows.at_least(share, float(found.x[-1]))


def nearest(rows, lower, upper, target):
    """Rank 4: the point of the rows and bounds nearest `target`, by the dual active-set method of
    Goldfarb and Idnani (see the module). The active rows are kept independent: a row in their span
    makes a dual step, which drops the row whose multiplier would turn negative first."""
    n = rows.n
    eye = np.eye(n)
    plain = [(a, b, True) for a, b in rows.equal] + [(a, b, False) for a, b in rows.upper]
    plain += [(eye[j], float(upper[j]), False) for j in range(n) if math.isfinite(upper[j])]
    plain += [(-eye[j], -float(lower[j]), False) for j in range(n) if math.isfinite(lower[j])]
    target = np.asarray(target, dtype=float)
    x = target.copy()
    normals, values, equal, multipliers = [], [], [], []  # the active rows

    def size(a, b):
        return abs(b) + np.abs(a) @ (np.abs(x) + np.abs(target))

    def broken():
        """The row that x breaks most, by its distance, as (a, b, equality), or None."""
        worst, found = 0.0, None
        for a, b, is_equal in plain:
            gap = a @ x - b
            if is_equal and gap < 0:
                a, b, gap = -a, -b, -gap
            if gap > BREAKS * size(a, b):
                distance = gap / max(float(np.linalg.norm(a)), 1e-300)
                if distance > worst:
                    worst, found = distance, (a, b, is_equal)
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
            for k, (value, is_eq) in enumerate(zip(multipliers, equal)):
                if not is_eq and r[k] > 1e-14 * max(1.0, float(np.abs(r).max())):
                    if value / r[k] < partial:
                        partial, leaving = value / r[k], k
            room = float(z @ z)
            gap = a @ x - b
            full = gap / room if room > 1e-28 * max(1.0, float(a @ a)) else math.inf
            if math.isinf(full) and math.isinf(partial):
                raise SimulationError('local sharing: the rows of the rates nearest their requests have no answer')
            step = min(full, partial)
            if not math.isinf(full):
                x = x + step * z
            multipliers = [value - step * r[k] for k, value in enumerate(multipliers)]
            added += step
            if step == full:
                normals.append(a)
                values.append(b)
                equal.append(is_equal)
                multipliers.append(added)
                break
            for found in (normals, values, equal, multipliers):
                found.pop(leaving)
    else:
        raise SimulationError('local sharing: the rates nearest their requests did not settle')
    x = np.clip(x, lower, upper)
    for a, b, is_equal in plain:
        gap = a @ x - b
        if (abs(gap) if is_equal else gap) > FEASIBLE * (1.0 + size(a, b)):
            raise SimulationError('local sharing: the rates nearest their requests break a hard row')
    for a, parts, b in rows.convex:
        gap = a @ x + sum(max(sign * x[j], 0.0) for j, sign in parts) - b
        if gap > FEASIBLE * (1.0 + size(a, b) + sum(abs(x[j]) for j, _ in parts)):
            raise SimulationError('local sharing: the rates nearest their requests break a hard row')
    return x


def size_of(rows, upper, tiers, prefs, target):
    """The size of a part: its largest request or preferred amount, else its largest finite
    capacity or row, else one. The tolerances of HiGHS and of the ranks are absolute, so a part is
    solved in units of its size: then they are relative to what it asks. The selection order gives
    the same answer in any unit (a served fraction is a ratio, the rows and the distance scale
    with the rates), so the change of unit is exact but for roundoff."""
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


def select(rows, lower, upper, tiers, prefs, target):
    """The unknowns of one coupled part: `rows` (`Rows`), the bounds of each unknown (-inf and inf
    for none), the tiers of claims in order (each a list of (a, request)), the preferred routes in
    order (each (a, amount)) and the target of each unknown (rank 4). The part is solved in units of
    its size (`size_of`)."""
    size = size_of(rows, upper, tiers, prefs, target)
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    scaled = rows.scaled(size)
    limits = [(float(lo) / size, float(hi) / size) for lo, hi in zip(lower, upper)]
    found = _program(scaled, limits, np.zeros(rows.n))
    if not found.success:
        _failed(found, 'the hard rows')
    for claims in tiers:
        _share(scaled, limits, [(a, r / size) for a, r in claims])
    for a, amount in prefs:
        _prefer(scaled, limits, a, amount / size)
    found = nearest(scaled, lower / size, upper / size, np.asarray(target, dtype=float) / size) * size
    # The roundoff of the linear algebra is no rate: an unknown within it of zero or of a bound is
    # put there, so that a junction or a store at its bound is held exactly.
    found[np.abs(found) <= 1e-12 * size] = 0.0
    for bound in (lower, upper):
        with np.errstate(invalid='ignore'):
            near = np.isfinite(bound) & (np.abs(found - bound) <= 1e-12 * (size + np.abs(bound)))
        found[near] = bound[near]
    return found
