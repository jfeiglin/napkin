"""The continuous field of one run at its start, outside a simulation (docs/python-api.md, "Dynamics").

Between moments, the stores that flows meet move by the rates of their flows. `VectorField` gives
those rates at any state and time. It starts a run of a program under a configuration as the engine
does (`timeline.Run.prepare`: the values at the start, the size and the bounds of each store, and
an instance of the way of each connected set), and it reads the rates of each set that moves from
the engine's own instance: a component of the continuous engine (`timeline/component.py`) or the
sparse integrator (`timeline/sparse.py`). So the equations of the analysis are the equations that
the engine runs: one implementation.

- **The state** is the stores of the sets that move, in the order of the program, each in the
  canonical unit of its dimension, as the engine holds it. Several such sets make one field: the
  rates of a set read its own stores only, so its block of the derivative is its own.
- **What holds.** The values that the rates read and that hold between moments keep their values at
  the start: stored values that no flow meets (`held`), captured requests and capacities, the rates
  of the sets that do not move. Nothing of the setup runs and no rule fires. A keyed read by the time
  selects its member at the time at which the field is read.
- **Inside the bounds.** No bound and no stock face holds, so the field is the one inside the bounds,
  where no bound cuts a flow. Capacities, the settings of endpoints and local sharing still apply.
- **Active and passive.** The analysis follows the active stores: those that the requests and the
  capacities of the flows read, through formulas. A store that only fills or drains and that nothing
  reads, such as a tally that counts, is passive: it has no equilibrium and changes nothing of the
  others. So are the stores of the sets whose rates read nothing that moves.

Other start values and input values make another program and another configuration (`started`,
`configured`): a configuration sets inputs only. A set of a declared solver whose problem moves, and
a set that waits for the solve of the setup, give no field: the constructor names them.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..core.errors import ExpressionError
from ..engine.errors import SimulationError
from ..engine.timeline.component import ComponentWay
from ..engine.timeline.plan import COMPONENT, DECLARED, SPARSE, STATE, Plan
from ..engine.timeline.record import key_of
from ..engine.timeline.run import Run
from ..engine.timeline.sparse import Sparse
from ..program import parts as p
from ..program.build import X, expr_of, q
from ..program.config import InputValue, Quantity
from ..program.refs import EnumValue

# The relative step of a finite difference, in units of a quantity's size.
DIFFERENCE_STEP = 1e-6
# A derivative has a kink where the forward and the backward differences of an entry differ by more
# than this share of the largest entry (in units of the sizes), and the difference stays when the step
# halves. On a smooth field the difference is the curvature times the step, so it halves too.
KINK = 1e-6
# What an evaluation of a set's rates raises where the field has no value.
FAILURES = (SimulationError, ExpressionError, ArithmeticError)


class OutsideDomain(ValueError):
    """The field cannot be evaluated at a state: a rate is negative, not finite or fails."""


def _part(program, path):
    """(member id, name, part) of the value at a path of a member or of the root, or KeyError."""
    key = key_of(program, path)
    if len(key.steps) != 1:
        raise KeyError(f'{path} is no value of a member or of the root')
    name = key.steps[0]
    part = program.member(key.owner)[0].part(name) if key.owner else program.root_value(name)
    if not isinstance(part, p.Value):
        raise KeyError(f'{path} is no value of the program')
    return key.owner, name, part


def _member_of(program, value_type, value, path):
    """An enum member's name as the record of its read, after it is checked against its enum."""
    members = program.enum(value_type.enum).members
    if value not in members:
        raise ValueError(f'{path} takes a member of {value_type.enum} ({", ".join(members)}), not {value!r}')
    return EnumValue(value_type.enum, value)


def configured(program, configuration, values):
    """The configuration with the input values `values`: {path of an input: its value}, a number in
    the input's declared unit, a yes/no, the name of an enum member, a text or a distribution. The
    engine checks each against the input's type and range when a run starts (D2)."""
    given = {(item.member, item.name): item for item in configuration.inputs}
    for path, value in values.items():
        member, name, part = _part(program, path)
        if part.kind != p.INPUT:
            raise KeyError(f'{path} is no input: a configuration sets only inputs')
        if isinstance(part.type, p.Number):
            value = Quantity(float(value), part.type.unit)
        elif isinstance(part.type, p.EnumType):
            value = _member_of(program, part.type, value, path)
        given[(member, name)] = InputValue(member, name, value)
    return replace(configuration, inputs=tuple(given.values()))


def started(program, values):
    """The program whose stored values of `values` start at other values: {path of a stored value of
    a member or of the root: its start value}, a number in the value's declared unit, a yes/no, the
    name of an enum member or a text. The engine checks the bounds of each when a run starts."""
    for path, value in values.items():
        member, name, part = _part(program, path)
        if part.kind != p.STATE:
            raise KeyError(f'{path} is no stored value: an input is set by a configuration (`configured`)')
        if isinstance(part.type, p.Number):
            init = expr_of(q(float(value), part.type.unit))
        elif isinstance(part.type, p.EnumType):
            init = expr_of(X.read(_member_of(program, part.type, value, path)))
        else:
            init = expr_of(value)
        if not member:
            root = tuple(replace(each, init=init) if each.name == name else each for each in program.root)
            program = replace(program, root=root)
            continue
        template, row = program.member(member)
        own = template.members[row]
        inits = tuple((found, each) for found, each in own.values if found != name) + ((name, init),)
        members = list(template.members)
        members[row] = replace(own, values=inits)
        templates = tuple(
            replace(each, members=tuple(members)) if each is template else each for each in program.templates
        )
        program = replace(program, templates=templates)
    return program


class _Moving:
    """An instance of a way whose rates move: its stores' places in the state of a field, and its
    rates at a time and a state of its stores."""

    def __init__(self, instance, rows):
        self.instance, self.rows = instance, rows
        self.component = isinstance(instance, ComponentWay)
        # A component holds its keyed reads by the time in its store: they change at their key times.
        self.stepped = self.component and bool(instance.connected.stepped)
        self.time = 0.0

    def rates(self, t, y):
        """The rate of each store of the instance. The evaluations of the analysis count for no budget
        of the run, as those of the record do (`ComponentWay.delivered`)."""
        instance = self.instance
        if self.stepped and t != self.time:
            instance.refresh(t)
            self.time = t
        owner = instance.component.state if self.component else instance
        evaluations = owner.evaluations
        try:
            if self.component:
                return instance.component.field.rates(t, y)
            return instance.field(t, y)
        finally:
            owner.evaluations = evaluations


class VectorField:
    """The rates of the active stores of a program's run at a state and a time, in canonical units
    per hour (see the module). A call `field(x, t)` gives the rates of the active stores at the active
    values `x`, with every other store of a set that moves at its value at the start."""

    def __init__(self, program, configuration):
        self.program, self.configuration = program, configuration
        plan = self.plan = Plan.of(program, configuration)
        run = self.run = Run(plan)
        start, sizes, _ = run.prepare()
        waiting = {id(connected) for connected in run.waiting}
        moving, still, instances = [], [], {}
        for connected in plan.sets:
            name = (connected.flows or (connected.solver,))[0]
            if connected.way == DECLARED and connected.moves:
                raise ValueError(
                    f'{name}: a declared solver determines these rates, and its problem moves; the '
                    'field reads the rates of the continuous engine and of the sparse integrator'
                )
            if id(connected) in waiting and connected.way in (COMPONENT, SPARSE):
                raise ValueError(
                    f'{name}: these rates read what a declared solver gives, which settles after the '
                    'setup; the field reads the run at its start'
                )
            # A set whose settings read a moving rate of another set integrates with it, on the
            # sparse integrator (`ways.Ways.build`): its instance says whether it moves.
            instance = run.ways.instance_of(connected.flows[0]) if connected.flows else None
            if isinstance(instance, ComponentWay | Sparse):
                moving.append(connected)
                instances[id(instance)] = instance
            else:
                still.append(connected)
        place = {name: k for k, name in enumerate(plan.values)}
        stores = {name for instance in instances.values() for name in instance.stores}
        self.state_ids = tuple(sorted(stores, key=place.__getitem__))
        index = {name: k for k, name in enumerate(self.state_ids)}
        self.moving = [
            _Moving(instance, np.array([index[name] for name in instance.stores], dtype=int))
            for instance in instances.values()
        ]
        reads = set().union(*(connected.reads for connected in moving))
        self.base = np.array([float(start[name]) for name in self.state_ids], dtype=float)
        self.rows = np.array([k for k, name in enumerate(self.state_ids) if name in reads], dtype=int)
        self.names = tuple(self.state_ids[k] for k in self.rows)
        resting = [name for name in self.state_ids if name not in reads]
        resting += [store for connected in still for store in connected.stores]
        self.passive = tuple(sorted(set(resting), key=place.__getitem__))
        held = {name for name in reads - set(self.state_ids) if name in place and plan.values[name].kind == STATE}
        self.held = tuple(sorted(held, key=place.__getitem__))
        self.scales = np.array([float(sizes[name]) for name in self.names], dtype=float)
        self.lower = np.array([run.bounds[name][0] for name in self.names], dtype=float)
        self.upper = np.array([run.bounds[name][1] for name in self.names], dtype=float)
        # One of each active store's declared unit in canonical units: a value divided by it is the
        # value in the store's own unit.
        units = [plan.values[name].unit for name in self.names]
        self.unit_scales = np.array([plan.units.scale(unit) if unit else 1.0 for unit in units], dtype=float)
        self.horizon = float(plan.horizon)

    @property
    def start(self):
        """The active values at the start of the run."""
        return self.base[self.rows].copy()

    def full(self, x):
        """The whole state: the active values `x`, and every other store at its value at the start."""
        y = self.base.copy()
        y[self.rows] = np.asarray(x, dtype=float)
        return y

    def rates_of(self, y, t=0.0):
        """The rate of every store of the state `y` (`state_ids`) at the time t."""
        y = np.asarray(y, dtype=float)
        derivative = np.zeros(len(y))
        try:
            for part in self.moving:
                derivative[part.rows] = part.rates(float(t), y[part.rows])
        except FAILURES as exc:
            raise OutsideDomain(str(exc)) from exc
        if not np.all(np.isfinite(derivative)):
            raise OutsideDomain('A rate is not finite')
        return derivative

    def __call__(self, x, t=0.0):
        return self.rates_of(self.full(x), t)[self.rows]

    def steps(self, x):
        """The finite-difference step of each active store at `x`."""
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
        """{store: value in its own unit} of the active values `x`."""
        return {name: float(v) / scale for name, v, scale in zip(self.names, x, self.unit_scales)}

    def at_bound(self, x, tolerance=1e-9):
        """The active stores within `tolerance` of their size from a bound."""
        x = np.asarray(x, dtype=float)
        near = (x - self.lower <= tolerance * self.scales) | (self.upper - x <= tolerance * self.scales)
        return tuple(name for name, flag in zip(self.names, near) if flag)


def vector_field(program, configuration, values=None):
    """The field of a run of a program under a configuration, with the input values `values`
    (`configured`)."""
    return VectorField(program, configured(program, configuration, values) if values else configuration)
