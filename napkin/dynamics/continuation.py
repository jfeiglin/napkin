"""Branches of equilibria as an input or the time changes (docs/python-api.md, "Dynamics").

`continue_equilibrium` follows one branch of equilibria of a run as one parameter moves through a span:
an input of the model, which each new value resolves again, or the time `t` at which the field is read,
with the discrete values frozen. The time costs no resolution, so it is the cheap way to follow
equilibria along drivers that the model writes as formulas of `t`.

The branch is followed by pseudo-arclength continuation, in units of each quantity's size and of the
span, so that it passes through a fold, where it turns back in the parameter. A fold is where the
parameter part of the branch's tangent changes sign: on one side of it two equilibria exist, on the
other side none. A Hopf point is where a pair of complex eigenvalues crosses zero: there an equilibrium
gives its stability to an oscillation. Each is located between two points of the branch by the
secant method on its test function.

Where the equilibria make a line or a surface for each value of the parameter, the derivative has
neutral modes (equilibria.py), and the null space of [dG/dz | dG/dq] has one direction more for each.
The tangent is then the part of that null space along the previous tangent, the other directions of the
null space are the neutral ones, and the corrector takes the step with the least norm, which moves
nothing along them. The stability of a point comes from the eigenvalues on the other directions.

At a kink of the field, a branch can have a corner: there the null space holds no direction with a part
in the parameter, and the parameter part of the tangent falls in one step to CORNER or less. A smooth
fold gives that only at a point within about CORNER of the fold. The branch steps over the corner with
a step in the parameter alone, from which the search (`newton`) finds the equilibrium beyond it. Past a
corner the equilibrium can stay on the kink for a while, so the step doubles until the branch is smooth
again.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np

from ..model.ir import ModelError, thaw
from .equilibria import NEUTRAL, classify, newton, solve
from .field import OutsideDomain, VectorField

TIME = 't'
# A unit tangent whose parameter part is at most this is at a corner of the branch, when the tangent
# before it had more.
CORNER = 1e-9


class Inadmissible(ValueError):
    """The model rejects a value of the parameter."""


@dataclass(frozen=True)
class Point:
    parameter: float
    state: np.ndarray  # active values, execution units
    eigenvalues: np.ndarray  # per hour, the neutral modes included
    stability: str  # on the directions other than the neutral ones
    neutral: int = 0  # the number of neutral modes: directions along which the equilibrium continues


@dataclass(frozen=True)
class Bifurcation:
    kind: str  # 'fold' or 'hopf'
    parameter: float
    state: np.ndarray
    frequency: float = 0.0  # per hour: the imaginary part of the pair at a Hopf point


@dataclass
class Branch:
    parameter: str
    names: tuple
    points: list = field(default_factory=list)
    folds: list = field(default_factory=list)
    hopfs: list = field(default_factory=list)
    stop: str = ''


class Family:
    """The fields of one run as its parameter takes values: an input (resolved again for each value,
    in its own unit) or the time `t` (hours)."""

    def __init__(self, model, run, parameter, *, values=None, state=None, store=None, t=0.0, cache=128):
        self.model, self.run, self.parameter = model, run, parameter
        self.values, self.state, self.store, self.t = dict(values or {}), state, store, float(t)
        self.library = thaw(model.library)
        self.cache = cache
        self._fields = OrderedDict()
        self.fixed = self.build(None) if parameter == TIME else None

    def build(self, value):
        values = dict(self.values)
        if value is not None:
            values[self.parameter] = value
        try:
            rs = self.model.resolve(self.run, values)
        except ModelError as exc:
            raise Inadmissible(str(exc)) from exc
        return VectorField(rs, self.library, state=self.state, store=self.store)

    def field(self, p):
        if self.fixed is not None:
            return self.fixed
        key = float(p)
        found = self._fields.get(key)
        if found is None:
            found = self._fields[key] = self.build(key)
            if len(self._fields) > self.cache:
                self._fields.popitem(last=False)
        else:
            self._fields.move_to_end(key)
        return found

    def time(self, p):
        return float(p) if self.parameter == TIME else self.t

    def __call__(self, x, p):
        return self.field(p)(x, self.time(p))


class _Scaled:
    """The field of a family in units of each quantity's size (z) and of the span (q)."""

    def __init__(self, family, start, span):
        self.family = family
        self.p0, self.width = float(span[0]), float(span[1]) - float(span[0])
        if self.width == 0:
            raise ValueError('The span of the parameter has two different ends')
        reference = family.field(start)
        self.reference = reference
        self.scale = reference.scales
        self.horizon = max(reference.horizon, 1.0)

    def p(self, q):
        return self.p0 + q * self.width

    def g(self, u):
        z, q = u[:-1], u[-1]
        return self.family(z * self.scale, self.p(q)) * self.horizon / self.scale

    def jacobian(self, u):
        """[dG/dz | dG/dq] at u."""
        z, q = u[:-1], u[-1]
        p = self.p(q)
        field = self.family.field(p)
        jz = field.jacobian(z * self.scale, self.family.time(p)) * self.scale[None, :] * self.horizon
        jz = jz / self.scale[:, None]
        h = 1e-6
        try:
            up = self.g(np.append(z, q + h))
        except (Inadmissible, OutsideDomain):
            up = None
        try:
            down = self.g(np.append(z, q - h))
        except (Inadmissible, OutsideDomain):
            down = None
        if up is not None and down is not None:
            jq = (up - down) / (2 * h)
        elif up is not None:
            jq = (up - self.g(u)) / h
        elif down is not None:
            jq = (self.g(u) - down) / h
        else:
            raise Inadmissible('The parameter has no admissible neighbour')
        return np.column_stack([jz, jq]), jz

    def eigenvalues(self, jz, neutral=None):
        """(all, transverse): the eigenvalues of the field's derivative per hour, and those on the
        directions other than the rows of `neutral` (directions of u; their parts in z count). z only
        rescales the quantities, so the eigenvalues of dG/dz are the horizon times those of the field."""
        if not jz.size:
            return np.array([]), np.array([])
        values = np.linalg.eigvals(jz) / self.horizon
        if neutral is None or not len(neutral):
            return values, values
        # An orthonormal basis of the directions of z other than the neutral ones.
        _, s, vt = np.linalg.svd(neutral[:, :-1])
        k = int(np.sum(s > NEUTRAL * s[0])) if len(s) and s[0] > 0 else 0
        others = vt[k:].T
        if not others.size:
            return values, np.array([])
        return values, np.linalg.eigvals(others.T @ jz @ others) / self.horizon


def _tangent(augmented, previous):
    """(tangent, neutral): the unit tangent of the branch and the neutral directions, as rows. The
    null space of [dG/dz | dG/dq] has one direction, or one more for each neutral mode; the tangent is
    the part of it along `previous`, and the neutral directions are the rest of it."""
    n = augmented.shape[0]
    _, s, vt = np.linalg.svd(augmented)
    small = int(np.sum(s <= NEUTRAL * s[0])) if len(s) and s[0] > 0 else n
    null = vt[n - small :]
    w = null.T @ (null @ previous)
    size = np.linalg.norm(w)
    if not size > 1e-12 * np.linalg.norm(previous):
        w = null[-1] if null[-1] @ previous >= 0 else -null[-1]
        size = np.linalg.norm(w)
    w = w / size
    if not small:
        return w, np.zeros((0, n + 1))
    rest = null - np.outer(null @ w, w)
    _, s, vt = np.linalg.svd(rest)
    return w, vt[:small]


def _correct(scaled, u_predicted, tangent, tol, iterations=10):
    """Newton on the branch's equations and the arclength condition; (u, converged, augmented, jz)."""
    u = u_predicted.copy()
    for _ in range(iterations):
        try:
            g = scaled.g(u)
            augmented, jz = scaled.jacobian(u)
        except (Inadmissible, OutsideDomain):
            return u, False, None, None
        h = np.append(g, tangent @ (u - u_predicted))
        if np.max(np.abs(g)) <= tol and abs(h[-1]) <= tol:
            return u, True, augmented, jz
        matrix = np.vstack([augmented, tangent])
        try:
            step = solve(matrix, -h)
        except np.linalg.LinAlgError:
            return u, False, None, None
        u = u + step
        if not np.all(np.isfinite(u)):
            return u, False, None, None
    try:
        g = scaled.g(u)
        augmented, jz = scaled.jacobian(u)
    except (Inadmissible, OutsideDomain):
        return u, False, None, None
    return u, bool(np.max(np.abs(g)) <= tol), augmented, jz


def _hopf_test(eigenvalues):
    """The largest real part of a complex pair, or None without a pair."""
    values = np.asarray(eigenvalues)
    if not len(values):
        return None
    size = float(np.max(np.abs(values)))
    complex_pairs = values[np.abs(values.imag) > 1e-6 * size] if size > 0 else []
    return float(np.max(complex_pairs.real)) if len(complex_pairs) else None


def _locate(scaled, a, b, measure, tol, iterations=60):
    """The point between two points of a branch, a and b: (u, tangent, eigenvalues on the directions
    other than the neutral ones), where `measure` changes sign. Each step is a secant step from the end
    with the smaller measure, along that end's own tangent: near a fold, a tangent from further away is
    nearly orthogonal to the branch."""
    ends = [list(a), list(b)]
    best = (a[0], a[1], None)
    for _ in range(iterations):
        (u0, v0, m0), (u1, _, m1) = sorted(ends, key=lambda end: abs(end[2]))
        if m0 == m1 or abs(m0) <= 1e-12:
            break
        chord = u1 - u0
        side = 1.0 if v0 @ chord >= 0 else -1.0
        distance = side * np.linalg.norm(chord) * m0 / (m0 - m1)
        u, ok, augmented, jz = _correct(scaled, u0 + distance * v0, v0, tol)
        if not ok:
            break
        v, neutral = _tangent(augmented, v0)
        _, transverse = scaled.eigenvalues(jz, neutral)
        m = measure(v, transverse)
        if m is None:
            break
        best = (u, v, transverse)
        if abs(m) <= 1e-12 or np.linalg.norm(u - u0) <= 1e-14:
            break
        # The new point replaces the end on its own side of the sign change.
        index = 0 if np.sign(m) == np.sign(ends[0][2]) else 1
        ends[index] = [u, v, m]
    return best


def _step_over(scaled, u, v, neutral, ds, longest, tol):
    """(u, tangent, neutral, eigenvalues, transverse) of the branch beyond a corner at u, or None. The
    step moves the parameter alone, in the direction of the tangent v before the corner: first by as
    much as the last step of arclength `ds` moved it, then twice as much each time, up to what the
    longest step of arclength would move it. The search (`newton`) finds the equilibrium there from the
    corner's state. The branch goes on from the first equilibrium that lies within four steps of
    arclength of the corner, apart from the directions `neutral` of the branch before the corner (rows
    of u), and where the branch has a tangent with a part in the parameter."""
    sign, rate = (1.0 if v[-1] > 0 else -1.0), abs(v[-1])
    others = np.eye(len(u) - 1)
    if len(neutral):
        _, s, vt = np.linalg.svd(neutral[:, :-1])
        others = vt[int(np.sum(s > NEUTRAL * s[0])) if s[0] > 0 else 0 :]
    dq = ds * rate
    while dq <= max(longest, ds) * rate:
        q = u[-1] + sign * dq
        arc, dq = dq / rate, 2 * dq
        try:
            p = scaled.p(q)
            x, converged = newton(
                scaled.family.field(p), u[:-1] * scaled.scale, t=scaled.family.time(p), tol=tol
            )
            if not converged:
                continue
            z = x / scaled.scale
            if np.linalg.norm(others @ (z - u[:-1])) > 4 * arc:
                continue
            beyond = np.append(z, q)
            augmented, jz = scaled.jacobian(beyond)
        except (Inadmissible, OutsideDomain):
            continue
        tangent, neutral = _tangent(augmented, v)
        if abs(tangent[-1]) > CORNER:
            eigenvalues, transverse = scaled.eigenvalues(jz, neutral)
            return beyond, tangent, neutral, eigenvalues, transverse
    return None


def continue_equilibrium(
    model,
    run,
    parameter,
    span,
    *,
    start=None,
    values=None,
    state=None,
    store=None,
    t=0.0,
    step=0.01,
    max_step=0.05,
    min_step=1e-7,
    max_points=2000,
    tol=1e-9,
):
    """The branch of equilibria of `run` through the active state `start` (execution units; by
    default the run's start), from the equilibrium that the search (`newton`) reaches there, as
    `parameter`, an input or 't', moves from span[0] to span[1]. Steps are in units of the span and of
    each quantity's size. The branch stops when the parameter leaves the span ('span'), when a quantity
    that was not on a bound reaches one ('bound'), when the model rejects a value ('inadmissible'), when
    the step falls below `min_step` ('step'), after `max_points` points ('points') or at a corner that it
    cannot step over ('kink'). A quantity on a bound at the start of the branch, such as a stock that is
    empty by construction, does not stop it while it stays there."""
    family = Family(model, run, parameter, values=values, state=state, store=store, t=t)
    scaled = _Scaled(family, span[0], span)
    base = scaled.reference
    x0 = base.start if start is None else np.asarray(start, dtype=float)
    x0, converged = newton(base, x0, t=family.time(span[0]), tol=tol)
    if not converged:
        raise ValueError('Newton finds no equilibrium at the start of the span')
    branch = Branch(parameter=parameter, names=base.names)
    u = np.append(x0 / scaled.scale, 0.0)
    augmented, jz = scaled.jacobian(u)
    direction = np.zeros(len(u))
    direction[-1] = 1.0
    v, neutral = _tangent(augmented, direction)
    eigenvalues, transverse = scaled.eigenvalues(jz, neutral)
    branch.points.append(
        Point(scaled.p(u[-1]), u[:-1] * scaled.scale, eigenvalues, classify(transverse), len(neutral))
    )
    # The quantities on a bound at the start: the branch stops only when another one reaches a bound.
    pinned = set(base.at_bound(x0))

    def ended(u, x):
        """Why the branch ends at the point u, with the active values x, or ''."""
        nonlocal pinned
        if not 0.0 <= u[-1] <= 1.0:
            return 'span'
        on_bound = set(scaled.family.field(scaled.p(u[-1])).at_bound(x))
        if on_bound - pinned:
            return 'bound'
        pinned &= on_bound
        return ''

    ds = step
    while True:
        if len(branch.points) >= max_points:
            branch.stop = 'points'
            break
        u_new, ok, augmented_new, jz_new = _correct(scaled, u + ds * v, v, tol)
        if not ok:
            ds /= 2
            if ds < min_step:
                branch.stop = 'step'
                break
            continue
        v_new, neutral_new = _tangent(augmented_new, v)
        eigenvalues_new, transverse_new = scaled.eigenvalues(jz_new, neutral_new)
        corner = abs(v_new[-1]) <= CORNER < abs(v[-1])
        before_corner, neutral_before = v, neutral
        # A fold: the parameter part of the tangent changes sign.
        if not corner and np.sign(v_new[-1]) != np.sign(v[-1]) and v[-1] != 0:
            located = _locate(
                scaled, (u, v, v[-1]), (u_new, v_new, v_new[-1]), lambda vv, _e: float(vv[-1]), tol
            )
            branch.folds.append(Bifurcation('fold', scaled.p(located[0][-1]), located[0][:-1] * scaled.scale))
        # A Hopf point: the real part of a complex pair changes sign.
        before, after = _hopf_test(transverse), _hopf_test(transverse_new)
        if not corner and before is not None and after is not None and np.sign(before) != np.sign(after):
            located = _locate(scaled, (u, v, before), (u_new, v_new, after), lambda _v, e: _hopf_test(e), tol)
            found = located[2] if located[2] is not None else transverse_new
            size = float(np.max(np.abs(found))) if len(found) else 0.0
            pair = found[np.abs(found.imag) > 1e-6 * size] if size > 0 else found
            frequency = float(np.min(np.abs(pair.imag))) if len(pair) else 0.0
            branch.hopfs.append(
                Bifurcation('hopf', scaled.p(located[0][-1]), located[0][:-1] * scaled.scale, frequency)
            )
        u, v, transverse, neutral = u_new, v_new, transverse_new, neutral_new
        x = u[:-1] * scaled.scale
        branch.points.append(
            Point(scaled.p(u[-1]), x, eigenvalues_new, classify(transverse_new), len(neutral_new))
        )
        branch.stop = ended(u, x)
        if branch.stop:
            break
        if corner:
            beyond = _step_over(scaled, u, before_corner, neutral_before, ds, max_step, tol)
            if beyond is None:
                branch.stop = 'kink'
                break
            u, v, neutral, eigenvalues_new, transverse = beyond
            x = u[:-1] * scaled.scale
            branch.points.append(
                Point(scaled.p(u[-1]), x, eigenvalues_new, classify(transverse), len(neutral))
            )
            branch.stop = ended(u, x)
            if branch.stop:
                break
        ds = min(max_step, ds * 1.5)
    return branch


def fold_curve(model, run, parameter, span, second, grid, *, values=None, **options):
    """[(value of `second`, [the parameter at each fold of the branch])] for each value of the input
    `second` on `grid`: the edges of the region where the run has several equilibria."""
    rows = []
    for value in grid:
        try:
            branch = continue_equilibrium(
                model, run, parameter, span, values={**dict(values or {}), second: value}, **options
            )
        except (ValueError, Inadmissible):
            rows.append((float(value), None))
            continue
        rows.append((float(value), [fold.parameter for fold in branch.folds]))
    return rows
