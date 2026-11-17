"""The continuous field of one run, outside a simulation (docs/python-api.md, "Dynamics").

A run's quantities move between moments by the rates of its flows and tallies. `VectorField` gives
those rates at any state and time, with the run's discrete values (named states, event counts and
times, number states that only rules set) frozen. It builds the engine's own `System`, `Run` and
`Field` as `simulate` does, so the equations of the analysis are the equations of the engine: one
implementation. It leaves the bounds and stock faces of a segment empty, so it gives the field inside
the bounds, where no bound allocation acts; the capacities of shares and the couplings still apply.

The analysis follows the active quantities: those that the rates read, through formulas and statuses,
and that the flows and tallies change. A quantity that only fills or drains and that no rate reads, such
as a tally that counts, is passive: it has no equilibrium, and it changes nothing of the others.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from ..engine.continuous.fields import Field
from ..engine.continuous.system import Run, System, initial_store
from ..engine.errors import SimulationError
from ..engine.runtime import NumericalSettings, Trajectory
from ..model import structure as typed
from ..model.ir import thaw

# An analysis evaluates the field many times; it never runs out of the engine's evaluation budget.
UNBOUNDED_EVALUATIONS = 2**62
# The relative step of a finite difference, in units of a quantity's size.
DIFFERENCE_STEP = 1e-6
# A derivative has a kink where the forward and the backward differences of an entry differ by more
# than this share of the largest entry (in units of the sizes), and the difference stays when the step
# halves. On a smooth field the difference is the curvature times the step, so it halves too.
KINK = 1e-6


class OutsideDomain(ValueError):
    """The field cannot be evaluated at a state: a rate is negative, not finite or fails."""


class VectorField:
    """The rates of a run's active quantities at a state and a time, in execution units per hour.

    `rs` is a resolved run (`Model.resolve`). `state`
    gives quantities other values than their start values, and `store` the discrete values, both in
    execution units; by default they are the run's start. A call `field(x, t)` gives the rates of the
    active quantities at the active values `x`, with every other quantity at its base value."""

    def __init__(self, rs: typed.Resolved, library: Mapping, *, state: Mapping | None = None, store=None):
        self.rs = rs
        self.system = s = System(rs, library, NumericalSettings(max_evaluations=UNBOUNDED_EVALUATIONS))
        self.store = dict(initial_store(rs) if store is None else store)
        base = np.array(s.initial_state(self.store), dtype=float)
        for name, value in (state or {}).items():
            if name not in s.index:
                raise KeyError(f'{name} is not a quantity of the run')
            base[s.index[name]] = float(value)
        self.base = base
        self.trajectory = Trajectory(
            s.horizon, [], [], s.settings, s.state_ids, s.values, s.computed, s.units, s.bounds
        )
        self.run = Run(0.0, base.copy(), self.store)
        self.field = Field(s, self.run, self.trajectory)
        reads = set()
        for rate in rs.rates.values():
            reads |= s.expanded_names(rate.expr)
        for flow in rs.flows.values():
            reads |= s.expanded_names(flow.rate)
        for group in rs.allocation.values():
            reads |= s.expanded_names(group.capacity)
        evolving = set(s.evolving)
        self.rows = np.array(
            [i for i, name in enumerate(s.state_ids) if name in evolving and name in reads], dtype=int
        )
        self.names = tuple(s.state_ids[i] for i in self.rows)
        self.passive = tuple(name for name in s.state_ids if name in evolving and name not in reads)
        self.discrete = tuple(s.state_ids[i] for i in s.discrete)
        self.scales = s.sizes[self.rows].astype(float)
        self.lower = s.lower[self.rows].astype(float)
        self.upper = s.upper[self.rows].astype(float)
        # One unit of each active quantity in execution units: a value divided by it is the value in
        # the quantity's own unit.
        self.unit_scales = np.array(
            [s.units.scale(rs.quantities[name].unit) for name in self.names], dtype=float
        )
        self.horizon = float(s.horizon)

    @property
    def start(self):
        """The active values of the base state."""
        return self.base[self.rows].copy()

    def full(self, x):
        """The whole state: the active values `x`, and every other quantity at its base value."""
        y = self.base.copy()
        y[self.rows] = np.asarray(x, dtype=float)
        return y

    def rates_of(self, y, t=0.0):
        """The rate of every quantity at the whole state `y`."""
        try:
            derivative = self.field.rates(float(t), np.asarray(y, dtype=float))
        except SimulationError as exc:
            raise OutsideDomain(str(exc)) from exc
        if not np.all(np.isfinite(derivative)):
            raise OutsideDomain('A rate is not finite')
        return derivative

    def __call__(self, x, t=0.0):
        return self.rates_of(self.full(x), t)[self.rows]

    def steps(self, x):
        """The finite-difference step of each active quantity at `x`."""
        return DIFFERENCE_STEP * np.maximum(np.abs(np.asarray(x, dtype=float)), self.scales)

    def jacobian(self, x, t=0.0):
        """The derivative of the active rates by the active values at `x`, per hour: central
        differences, or one-sided ones where a bound lies within one step."""
        x = np.asarray(x, dtype=float)
        h = self.steps(x)
        columns = []
        for j in range(len(x)):
            up, down = x.copy(), x.copy()
            up[j] += h[j]
            down[j] -= h[j]
            if down[j] < self.lower[j]:
                columns.append((self(up, t) - self(x, t)) / h[j])
            elif up[j] > self.upper[j]:
                columns.append((self(x, t) - self(down, t)) / h[j])
            else:
                columns.append((self(up, t) - self(down, t)) / (2 * h[j]))
        return np.array(columns).T if columns else np.zeros((0, 0))

    def one_sided(self, x, t=0.0):
        """(forward, backward, kinks): the derivative of the active rates by the active values at `x`,
        per hour, from forward and from backward differences, column by column, and for each column
        whether the field has a kink at `x`. Where a bound lies within one step, or the field has no
        value on one side, both derivatives take the other side.

        At the kink of a min() or a max(), the central difference mixes the two sides. The test of a kink
        compares the second difference at the step and at half the step: on a smooth field it halves
        with the step, at a kink it stays."""
        x = np.asarray(x, dtype=float)
        n = len(x)
        if not n:
            return np.zeros((0, 0)), np.zeros((0, 0)), np.zeros(0, dtype=bool)
        h = self.steps(x)
        f0 = self(x, t)

        def moved(j, step):
            y = x.copy()
            y[j] += step
            if y[j] < self.lower[j] or y[j] > self.upper[j]:
                return None
            try:
                return self(y, t)
            except OutsideDomain:
                return None

        forward, backward = np.zeros((n, n)), np.zeros((n, n))
        both = []
        for j in range(n):
            up, down = moved(j, h[j]), moved(j, -h[j])
            if up is None and down is None:
                raise OutsideDomain(f'The field has no value on either side of {self.names[j]}')
            ahead = (up - f0) / h[j] if up is not None else None
            behind = (f0 - down) / h[j] if down is not None else None
            forward[:, j] = ahead if ahead is not None else behind
            backward[:, j] = behind if behind is not None else ahead
            if ahead is not None and behind is not None:
                both.append(j)
        # In units of the sizes, so that one share compares every entry.
        sizes = self.scales[None, :] / self.scales[:, None]
        floor = KINK * float(np.max(np.abs((forward + backward) / 2 * sizes)))
        kinks = np.zeros(n, dtype=bool)
        for j in both:
            jump = np.abs(forward[:, j] - backward[:, j]) * sizes[:, j]
            rows = jump > floor
            if not rows.any():
                continue
            up, down = moved(j, h[j] / 2), moved(j, -h[j] / 2)
            if up is None or down is None:
                continue
            half = np.abs((up - 2 * f0 + down) / (h[j] / 2)) * sizes[:, j]
            kinks[j] = bool(np.any(half[rows] > 0.75 * jump[rows]))
        return forward, backward, kinks

    def values(self, x):
        """{quantity: value in its own unit} of the active values `x`."""
        return {name: float(v) / scale for name, v, scale in zip(self.names, x, self.unit_scales)}

    def at_bound(self, x, tolerance=1e-9):
        """The active quantities within `tolerance` of their size from a bound."""
        x = np.asarray(x, dtype=float)
        near = (x - self.lower <= tolerance * self.scales) | (self.upper - x <= tolerance * self.scales)
        return tuple(name for name, flag in zip(self.names, near) if flag)


def vector_field(model, run, values=None, *, state=None, store=None):
    """The field of a run of a compiled model, with `values` for some of its inputs (in their own
    units, as `Model.resolve` takes them)."""
    rs = model.resolve(run, values)
    return VectorField(rs, thaw(model.library), state=state, store=store)
