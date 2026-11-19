"""The selection order of local sharing on one coupled part of a network, in floats.

Outside a declared solver, the rates of the flows of a coupled part (`network.py`) follow the spec's
selection order with no objective (spec, "Local allocation"; the oracle's `tests/reference/order.py`):

1. the hard rows: each rate within [0, its capacity], and each row `a.x <= b` or `a.x == b` (the
   capacity of an endpoint, the row of a store that rests on a bound);
2. fair sharing, tier by tier: the smallest served fraction of the claims of a tier is made as large
   as it can be, then the next. A claim is (a, request): its served fraction is a.x / request,
   counted up to one. A claim that cannot rise above its level while the others keep theirs is held
   there by an equality; a claim served in full keeps the lower bound `a.x >= request`, so that a
   later tier can still raise its rate (a request is soft, D15);
3. the preferred routes of each aggregate request, in order: as much of its amount on them as can be;
4. the rates nearest their requests: the least squared distance.

Ranks 2 and 3 are linear programs of HiGHS (`continuous/highs.py`). An optimum is a vertex, so a
level is exact but for the roundoff of its basis. Rank 4 is the projection of the requests onto the
face that the earlier ranks leave, by a primal active-set method: it ends in a finite number of
steps, exact but for the roundoff of its linear algebra. A part that does not settle stops the run
(`SimulationError`) and never gets another answer.
"""

from __future__ import annotations

import math

import numpy as np

from ..continuous import highs
from ..errors import SimulationError

TIGHT = 1e-9  # a claim can rise above its level only by more than this part of its rate (the oracle's)
FEASIBLE = 1e-9  # a row holds to this part of the size of its terms
STEPS = 200  # the most steps of the least squares, for each unknown and row of the part


class Rows:
    """The hard rows of a part over its n rates: `a.x <= b` (`upper`) and `a.x == b` (`equal`)."""

    def __init__(self, n):
        self.n, self.upper, self.equal = n, [], []

    def at_most(self, a, b):
        self.upper.append((np.asarray(a, dtype=float), float(b)))

    def at_least(self, a, b):
        self.upper.append((-np.asarray(a, dtype=float), -float(b)))

    def equal_to(self, a, b):
        self.equal.append((np.asarray(a, dtype=float), float(b)))


def _program(rows, limits, cost, upper=(), equal=()):
    """Minimize cost.z over z: the rates, then any unknowns of this program alone, within `limits`;
    `upper` and `equal` are rows over the whole of z."""
    width = len(cost)

    def wide(a):
        return np.concatenate([a, np.zeros(width - len(a))])

    a_ub = [wide(a) for a, _ in rows.upper] + [a for a, _ in upper]
    b_ub = [b for _, b in rows.upper] + [b for _, b in upper]
    a_eq = [wide(a) for a, _ in rows.equal] + [a for a, _ in equal]
    b_eq = [b for _, b in rows.equal] + [b for _, b in equal]
    return highs.solve(
        np.asarray(cost, dtype=float),
        np.array(a_ub, dtype=float).reshape(len(a_ub), width),
        np.array(b_ub, dtype=float),
        np.array(a_eq, dtype=float).reshape(len(a_eq), width) if a_eq else None,
        np.array(b_eq, dtype=float) if b_eq else None,
        limits,
    )


def _failed(result, what):
    status = getattr(result, 'status', None)
    reason = 'the hard rows have no answer' if status == 2 else getattr(result, 'message', 'no optimum')
    raise SimulationError(f'local sharing: {what}: {reason}')


def _share(rows, limits, claims):
    """Rank 2 for the claims of one tier: their rows are added to `rows`."""
    n, pending = rows.n, list(claims)
    while pending:
        cost = np.zeros(n + 1)
        cost[-1] = -1.0
        floor = [(np.concatenate([-a, [r]]), 0.0) for a, r in pending]
        found = _program(rows, [*limits, (-math.inf, 1.0)], cost, floor)
        if not found.success:
            _failed(found, 'the fair level of a tier')
        level = min(1.0, float(found.x[-1]))
        if level >= 1.0 - 1e-12:
            for a, r in pending:
                rows.at_least(a, r)
            return
        hold = [(-a, -level * r) for a, r in pending]
        still = []
        for a, r in pending:
            # Can this claim rise above the level while every pending claim keeps it?
            found = _program(rows, limits, -a, hold)
            if getattr(found, 'status', 0) == 3:
                still.append((a, r))
                continue
            if not found.success:
                _failed(found, 'a claim at its fair level')
            if -found.fun > level * r + TIGHT * max(1.0, level * r):
                still.append((a, r))
            else:
                rows.equal_to(a, level * r)
        if len(still) == len(pending):
            raise SimulationError('local sharing: fair sharing made no progress in a tier')
        pending = still


def _prefer(rows, limits, a, amount):
    """Rank 3 for one preferred route: as much of `amount` on `a.x` as can be."""
    n = rows.n
    cost = np.zeros(n + 1)
    cost[-1] = -1.0
    found = _program(rows, [*limits, (-math.inf, amount)], cost, [(np.concatenate([-a, [1.0]]), 0.0)])
    if not found.success:
        _failed(found, 'a preferred route')
    rows.at_least(a, float(found.x[-1]))
    return found.x[:n]


def _independent(matrix, values):
    """The rows of `matrix` that add to the rank of those before them, with their values."""
    kept = []
    for i in range(len(matrix)):
        trial = matrix[[*kept, i]]
        if np.linalg.matrix_rank(trial, tol=1e-12 * max(1.0, np.abs(trial).max())) == len(kept) + 1:
            kept.append(i)
    return matrix[kept], values[kept]


def nearest(rows, lower, upper, target, start):
    """Rank 4: the point of the rows and bounds nearest `target`, from the feasible point `start`."""
    n = rows.n
    eye = np.eye(n)
    upper_rows = [(a, b) for a, b in rows.upper]
    upper_rows += [(eye[j], upper[j]) for j in range(n) if math.isfinite(upper[j])]
    upper_rows += [(-eye[j], -lower[j]) for j in range(n)]
    G = np.array([a for a, _ in upper_rows], dtype=float).reshape(len(upper_rows), n)
    g = np.array([b for _, b in upper_rows], dtype=float)
    E = np.array([a for a, _ in rows.equal], dtype=float).reshape(len(rows.equal), n)
    e = np.array([b for _, b in rows.equal], dtype=float)
    E, e = _independent(E, e)
    x = np.clip(np.asarray(start, dtype=float), lower, upper)
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
    size = 1.0 + np.abs(g) + np.abs(G) @ np.abs(x)
    if (G @ x - g > FEASIBLE * size).any() or (
        len(E) and (np.abs(E @ x - e) > FEASIBLE * (1.0 + np.abs(e) + np.abs(E) @ np.abs(x))).any()
    ):
        raise SimulationError('local sharing: the rates nearest their requests break a hard row')
    return x


def select(rows, upper, tiers, prefs, target):
    """The rates of one coupled part: `rows` (`Rows`), the capacity of each rate (inf for none),
    the tiers of claims in order (each a list of (a, request)), the preferred routes in order (each
    (a, amount)) and the request of each rate. `rows` gains the rows of the ranks."""
    n = rows.n
    lower = np.zeros(n)
    upper = np.asarray(upper, dtype=float)
    limits = [(0.0, float(c)) for c in upper]
    found = _program(rows, limits, np.zeros(n))
    if not found.success:
        _failed(found, 'the hard rows')
    start = found.x[:n]
    for claims in tiers:
        _share(rows, limits, claims)
    for a, amount in prefs:
        start = _prefer(rows, limits, a, amount)
    if tiers and not prefs:
        found = _program(rows, limits, np.zeros(n))
        if not found.success:
            _failed(found, 'the rows of fair sharing')
        start = found.x[:n]
    return nearest(rows, lower, upper, np.asarray(target, dtype=float), start)
