"""Equilibria of a run's field and their stability (docs/python-api.md, "Dynamics").

An equilibrium is a state of the active quantities where every rate is zero. The search works in units
of each quantity's size, and its iterates stay within the bounds. The residual is the largest drift of
a quantity over the run's horizon, as a share of its size.

- **The search.** Newton's method first, with a line search that halves the step until the residual
  falls. The line search stalls where the field has a kink, as at a min() or a max(), and where the
  steps run into a corner of the bounds. Then the search starts again from the same state with
  pseudo-transient continuation: implicit Euler steps of the flow, each step of time the last one times
  the fall of the residual (switched evolution relaxation; Kelley and Keyes, 1998). Short steps follow
  the flow across the kinks; long steps are Newton steps. Below the residual `SWITCH`, Newton's method
  ends the search.
- **Neutral modes.** Where the equilibria make a line or a surface, the derivative has a zero
  eigenvalue for each direction along it, and its right null space holds those directions. A direction
  of the null space is neutral only if the equilibrium continues along it: a fold point has a null
  direction too, but no equilibrium next to it. The stability comes from the eigenvalues on the other
  directions, and two equilibria that differ only along the neutral directions of one are one.
- **Kinks.** At the kink of a min() or a max(), the central difference mixes the two sides of the
  kink, and it can hide an instability on one side. Each side then has its own class, from the forward
  or the backward differences, and the equilibrium has the class of its least stable side.

The eigenvalues of the derivative give its stability: every real part below zero is stable, every one
above zero unstable, both kinds a saddle, and one within the tolerance of zero is not hyperbolic, where
the linear part does not decide.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .field import OutsideDomain, VectorField

STABLE, UNSTABLE, SADDLE, NONHYPERBOLIC = 'stable', 'unstable', 'saddle', 'nonhyperbolic'
# The classes from the most stable to the least stable: at a kink, the least stable side decides.
ORDER = (STABLE, NONHYPERBOLIC, SADDLE, UNSTABLE)
# Two equilibria are one when no quantity differs by more than this share of its size.
SAME = 1e-6
# A singular value below this share of the largest one is zero, as an eigenvalue is in `classify`.
NEUTRAL = 1e-7
# The step along a null direction, in units of the sizes, that tests whether the equilibrium continues.
PROBE = 1e-4
# Pseudo-transient continuation. Newton's method takes over below the residual SWITCH. The first step
# of time is FIRST_STEP of the horizon. A step grows at most GROWTH times and is never longer than
# LONGEST horizons; a step that multiplies the residual by more than REJECT is taken again with a
# quarter of its time, and below SHORTEST the continuation stops.
SWITCH = 1e-3
FIRST_STEP = 1e-2
GROWTH = 10.0
LONGEST = 1e12
SHORTEST = 1e-14
REJECT = 100.0
TRANSIENT_STEPS = 300
# The halvings of Newton's line search before it stalls.
HALVINGS = 30


@dataclass(frozen=True)
class Side:
    """The linear part of the field on one side of a kink: from forward or from backward differences.
    A side has neutral modes of its own: where the equilibria continue on one side of the kink only."""

    name: str  # 'forward' or 'backward'
    eigenvalues: np.ndarray  # per hour, on the directions other than the neutral modes of the side
    stability: str
    neutral: int  # the number of neutral modes of the side


@dataclass(frozen=True)
class Equilibrium:
    """An equilibrium of the active quantities `names` at `state` (execution units) and time `t`."""

    names: tuple
    state: np.ndarray
    t: float
    residual: float
    jacobian: np.ndarray
    eigenvalues: np.ndarray  # per hour, of the central derivative: the neutral modes included
    stability: str  # on the directions other than the neutral ones; at a kink, of the least stable side
    at_bound: tuple
    neutral_modes: np.ndarray  # (quantities, modes): unit directions in units of the sizes
    transverse: np.ndarray  # per hour: the eigenvalues on the directions other than the neutral ones
    sides: tuple = ()  # at a kink: the forward and the backward Side

    @property
    def neutral(self):
        """The number of neutral modes: the directions along which the equilibrium continues."""
        return int(self.neutral_modes.shape[1])

    @property
    def kink(self):
        """Whether the field has a kink at the equilibrium."""
        return bool(self.sides)

    def value(self, name):
        return float(self.state[self.names.index(name)])


def residual(field: VectorField, x, t):
    """The largest drift of a quantity over the horizon, as a share of its size."""
    horizon = max(field.horizon, 1.0)
    return float(np.max(np.abs(field(x, t)) * horizon / field.scales)) if len(x) else 0.0


def classify(eigenvalues, tolerance=1e-7):
    """The stability of an equilibrium from the eigenvalues of its linear part."""
    values = np.asarray(eigenvalues)
    if not len(values):
        return STABLE
    # A real part within `tolerance` of the fastest eigenvalue's size is zero to the accuracy of a
    # finite-difference derivative.
    margin = tolerance * float(np.max(np.abs(values)))
    real = values.real
    if np.any(np.abs(real) <= margin):
        return NONHYPERBOLIC
    if np.all(real < 0):
        return STABLE
    if np.all(real > 0):
        return UNSTABLE
    return SADDLE


def least_stable(*classes):
    """The least stable of the classes, in the order stable, nonhyperbolic, saddle, unstable."""
    return max(classes, key=ORDER.index)


def solve(matrix, rhs):
    """The solution of `matrix` @ x = `rhs` with the least norm. A direction whose singular value is
    below NEUTRAL times the largest one is a neutral mode: the solution has no part along it."""
    u, s, vt = np.linalg.svd(matrix)
    if not len(s) or not s[0] > 0:
        raise np.linalg.LinAlgError('The matrix is zero')
    keep = s > NEUTRAL * s[0]
    if keep.all() and matrix.shape[0] == matrix.shape[1]:
        return np.linalg.solve(matrix, rhs)
    return vt[: len(s)][keep].T @ ((u[:, : len(s)][:, keep].T @ rhs) / s[keep])


class _Problem:
    """The field at the time t in units of each quantity's size: z = x / size, and the drift g(z) over the
    horizon in sizes."""

    def __init__(self, field: VectorField, t):
        self.field, self.t = field, float(t)
        self.scale = field.scales
        self.horizon = max(field.horizon, 1.0)
        self.lower, self.upper = field.lower / self.scale, field.upper / self.scale

    def g(self, z):
        return self.field(z * self.scale, self.t) * self.horizon / self.scale

    def jacobian(self, z):
        return (
            self.field.jacobian(z * self.scale, self.t)
            * self.scale[None, :]
            * self.horizon
            / self.scale[:, None]
        )

    def clip(self, z):
        return np.clip(z, self.lower, self.upper)


def _norm(g):
    return float(np.max(np.abs(g))) if len(g) else 0.0


def _newton_steps(problem: _Problem, z, tol, max_iterations):
    """(z, residual, converged): Newton's method from z, with a line search that halves the step until
    the residual falls. It stops when a step moves nothing, or when the residual does not fall in
    HALVINGS halvings: the line search stalls."""
    try:
        g = problem.g(z)
    except OutsideDomain:
        return z, np.inf, False
    for _ in range(max_iterations):
        norm = _norm(g)
        if norm <= tol:
            return z, norm, True
        try:
            step = solve(problem.jacobian(z), -g)
        except (np.linalg.LinAlgError, OutsideDomain):
            return z, norm, False
        damping = 1.0
        for _ in range(HALVINGS):
            trial = problem.clip(z + damping * step)
            try:
                found = problem.g(trial)
            except OutsideDomain:
                damping /= 2
                continue
            if _norm(found) < (1 - 1e-4 * damping) * norm:
                break
            damping /= 2
        else:
            return z, norm, False
        moved = np.max(np.abs(trial - z))
        z, g = trial, found
        if moved <= 1e-15 * max(1.0, float(np.max(np.abs(z)))):
            break
    norm = _norm(g)
    return z, norm, bool(norm <= tol)


def _transient(problem: _Problem, z, until, steps=TRANSIENT_STEPS):
    """(z, residual, reached): pseudo-transient continuation from z until the residual is at most
    `until`. Each step solves (I / tau - J) dz = g, an implicit Euler step of the flow with the time
    step tau (units of the horizon), and multiplies tau by the fall of the residual (switched evolution
    relaxation). It stops when the bounds hold the state, so that a step moves nothing."""
    try:
        g = problem.g(z)
    except OutsideDomain:
        return z, np.inf, False
    norm = _norm(g)
    if norm <= until:
        return z, norm, True
    tau = FIRST_STEP
    identity = np.eye(len(z))
    jacobian = None
    for _ in range(steps):
        if jacobian is None:
            try:
                jacobian = problem.jacobian(z)
            except OutsideDomain:
                return z, norm, False
        new, trial, found = np.inf, None, None
        try:
            trial = problem.clip(z + solve(identity / tau - jacobian, g))
            if np.all(np.isfinite(trial)):
                found = problem.g(trial)
                new = _norm(found)
        except (np.linalg.LinAlgError, OutsideDomain):
            pass
        if not np.isfinite(new) or new > REJECT * norm:
            tau /= 4
            if tau < SHORTEST:
                return z, norm, False
            continue
        if np.max(np.abs(trial - z)) <= 1e-15 * max(1.0, float(np.max(np.abs(z)))):
            return z, norm, False
        tau = min(tau * min(norm / new if new > 0 else GROWTH, GROWTH), LONGEST)
        z, g, norm, jacobian = trial, found, new, None
        if norm <= until:
            return z, norm, True
    return z, norm, False


def newton(field: VectorField, x0, *, t=0.0, tol=1e-10, max_iterations=80):
    """(state, converged) of the search for an equilibrium from `x0` (execution units). Newton's method
    first; where its line search stalls, pseudo-transient continuation from `x0` to the residual SWITCH,
    then Newton's method again; and where that stalls too, pseudo-transient continuation to `tol`.
    Without a converged search, the state is the one with the smallest residual."""
    problem = _Problem(field, t)
    start = problem.clip(np.asarray(x0, dtype=float) / problem.scale)
    z, norm, converged = _newton_steps(problem, start, tol, max_iterations)
    if converged:
        return z * problem.scale, True
    tried = [(norm, z)]
    z, norm, reached = _transient(problem, start, max(SWITCH, tol))
    tried.append((norm, z))
    if reached:
        z, norm, converged = _newton_steps(problem, z, tol, max_iterations)
        if converged:
            return z * problem.scale, True
        tried.append((norm, z))
        z, norm, reached = _transient(problem, z, tol)
        if reached:
            return z * problem.scale, True
        tried.append((norm, z))
    return min(tried, key=lambda item: item[0])[1] * problem.scale, False


def _continues(field: VectorField, x, t, direction):
    """Whether the equilibrium at `x` continues along `direction`, a unit vector in units of the sizes:
    from a step of PROBE along it, on one side or the other and within the bounds, Newton's method
    finds an equilibrium that keeps at least half of the step."""
    problem = _Problem(field, t)
    z = np.asarray(x, dtype=float) / problem.scale
    try:
        level = max(10 * _norm(problem.g(z)), 1e-10)
    except OutsideDomain:
        return False
    for sign in (1.0, -1.0):
        moved = problem.clip(z + sign * PROBE * direction)
        # A bound that takes half of the step closes this side.
        if sign * float((moved - z) @ direction) < PROBE / 2:
            continue
        end, _, converged = _newton_steps(problem, moved, level, 20)
        if converged and sign * float((end - z) @ direction) >= PROBE / 2:
            return True
    return False


def neutral_basis(field: VectorField, x, t, jacobian):
    """(modes, others): orthonormal directions in units of the sizes, as columns. The modes are the
    directions of the right null space of the derivative `jacobian` along which the equilibrium at `x`
    continues; the others span the rest."""
    n = len(x)
    if not n:
        return np.zeros((0, 0)), np.zeros((0, 0))
    scaled = jacobian * field.scales[None, :] / field.scales[:, None]
    _, s, vt = np.linalg.svd(scaled)
    null = s <= NEUTRAL * s[0] if s[0] > 0 else np.ones(n, dtype=bool)
    neutral = np.array([bool(null[i]) and _continues(field, x, t, vt[i]) for i in range(n)])
    return vt[neutral].T, vt[~neutral].T


def _transverse(field: VectorField, x, t, matrix):
    """(neutral modes, eigenvalues per hour on the other directions) of the derivative `matrix` at the
    equilibrium `x`."""
    modes, others = neutral_basis(field, x, t, matrix)
    if not modes.size:
        return modes, np.linalg.eigvals(matrix) if matrix.size else np.array([])
    if not others.size:
        return modes, np.array([])
    scaled = matrix * field.scales[None, :] / field.scales[:, None]
    return modes, np.linalg.eigvals(others.T @ scaled @ others)


def equilibrium_at(field: VectorField, x, t=0.0):
    """The equilibrium at `x`, with its derivative, eigenvalues, neutral modes and stability, and the
    stability of each side where the field has a kink there."""
    x = np.asarray(x, dtype=float)
    jacobian = field.jacobian(x, t)
    eigenvalues = np.linalg.eigvals(jacobian) if jacobian.size else np.array([])
    modes, transverse = _transverse(field, x, t, jacobian)
    stability = classify(transverse)
    sides = ()
    if len(x):
        forward, backward, kinks = field.one_sided(x, t)
        if kinks.any():
            for name, matrix in (('forward', forward), ('backward', backward)):
                side_modes, values = _transverse(field, x, t, matrix)
                sides += (Side(name, values, classify(values), int(side_modes.shape[1])),)
            stability = least_stable(stability, *(side.stability for side in sides))
    return Equilibrium(
        names=field.names,
        state=x,
        t=float(t),
        residual=residual(field, x, t),
        jacobian=jacobian,
        eigenvalues=eigenvalues,
        stability=stability,
        at_bound=field.at_bound(x),
        neutral_modes=modes,
        transverse=transverse,
        sides=sides,
    )


def same(field: VectorField, x, other: Equilibrium):
    """Whether the state `x` is the equilibrium `other`: no quantity differs by more than SAME of its
    size, once the parts along the neutral modes of `other` are left out."""
    d = (np.asarray(x, dtype=float) - other.state) / field.scales
    modes = other.neutral_modes
    if modes.size:
        d = d - modes @ (modes.T @ d)
    return bool(np.max(np.abs(d)) <= SAME) if len(d) else True


def starting_points(field: VectorField, count, seed, box=None):
    """The base state, then `count` seeded points of the box: {name: (low, high)} in execution units,
    by default the base value plus or minus three sizes, within the bounds."""
    generator = np.random.Generator(np.random.PCG64(seed))
    start = field.start
    low = np.maximum(field.lower, start - 3 * field.scales)
    high = np.minimum(field.upper, start + 3 * field.scales)
    for name, (lo, hi) in (box or {}).items():
        i = field.names.index(name)
        low[i], high[i] = float(lo), float(hi)
    yield start
    for _ in range(count):
        yield low + (high - low) * generator.random(len(start))


def equilibria(field: VectorField, *, t=0.0, starts=32, seed=0, box=None, tol=1e-10, include=()):
    """Every distinct equilibrium that the search (`newton`) reaches from the base state, from `starts`
    seeded points of the box, and from the states of `include`, ordered by their values."""
    found = []
    points = list(starting_points(field, starts, seed, box)) + [np.asarray(x, dtype=float) for x in include]
    for x0 in points:
        x, converged = newton(field, x0, t=t, tol=tol)
        if not converged:
            continue
        if any(same(field, x, other) for other in found):
            continue
        found.append(equilibrium_at(field, x, t))
    return sorted(found, key=lambda item: tuple(item.state))
