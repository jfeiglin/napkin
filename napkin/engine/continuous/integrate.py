"""Roots that end a segment, and the numerical (Radau) segment."""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
from scipy.integrate import OdeSolution, Radau, solve_ivp
from scipy.optimize import OptimizeResult, brentq

from ...core import expr as nodes
from ...core.comparisons import against, band_from_floor_width
from ...expressions import ExpressionError, compile_program, evaluate, names_in
from ...program.config import Numerics
from ..errors import SimulationError
from ..solvers import radau_rate
from . import dense
from .bounds import state_limits
from .transfers import CollocationRates
from .walk import walked

# The other side of the surface of `abs(x)`: the number zero.
ZERO = nodes.read('0')

# The tolerances of solve_ivp's root location (`solve_event_equation` in scipy.integrate._ivp.ivp).
ROOT_TOLERANCE = 4 * np.finfo(float).eps
# solve_ivp's messages for an integration that reaches its end (0) and one that a root ends (1).
MESSAGES = {
    0: 'The solver successfully reached the end of the integration interval.',
    1: 'A termination event occurred.',
}


class Root(NamedTuple):
    """A root that ends a segment: a function of the time and the state (`root_value`) whose sign
    changes in `direction` (1 up, -1 down, 0 either way) where the segment ends. `target` is the
    (quantity index, value) that the state reaches at the root, if any."""

    kind: str  # 'guard', 'release', 'bound', 'repayment', 'surface' or 'band-exit'
    direction: int
    data: tuple
    target: tuple | None = None
    start: float | None = None  # a switch this segment has just departed
    fixed_time: float | None = None  # an authored clock contact has an exact time
    band_pair: tuple | None = None  # authored operands before resolving nested field branches


def root_value(system, environment, root, at, state):
    """The value of one root at a time and state.

    - guard (i, value, offset): the quantity of a crossing rule less its value, plus the offset. A
      crossing of a quantity that only rises or only falls (`proven_monotone_crossings`) is watched half
      a tolerance before its value, inside the band where the rule holds: such a quantity can approach
      its value without reaching it (a stock that drains in proportion to itself), and the rule holds
      from where it comes within its tolerance.
    - release (i, limit, sign): the distance from the bound that the quantity rests on, less twice
      its tolerance.
    - bound (i, limit, start): the physical distance to the bound. A free store that starts
      on a bound left it there, so the start carries the sign of its interior.
    - repayment (cash, debt, floor): the cash less the debt and the floor.
    - surface (a, b): one side of a switching surface less the other.
    - band-exit (a, b): negative while a held equality holds, positive after it ends.
    """
    s = system
    kind, direction, data = root.kind, root.direction, root.data
    if kind == 'guard':
        i, value, offset = data
        return state[i] - float(evaluate(value, environment(at, state), s.units)) + offset
    if kind == 'release':
        i, limit, sign = data
        return sign * (state[i] - limit) - 2 * s.atol[i]
    if kind == 'bound':
        i, limit, start = data
        val = state[i] - limit
        if at == start and val == 0:
            return -direction * s.atol[i]
        return val
    if kind == 'repayment':
        cash, debt, floor = data
        return state[cash] - state[debt] - floor
    a, b = data
    env = environment(at, state)

    def read(node):
        return evaluate(node, env, s.units)

    if kind == 'band-exit':
        return band_root(root, read, s.units.comparisons, (read(a), read(b)))
    gap = float(read(a)) - float(read(b))
    if root.start is not None and (at == root.start or gap == 0):
        return -direction * np.finfo(float).tiny
    return gap


class Roots:
    """The roots of a numerical segment, evaluated together at each step (`values`) and one at a time
    to locate a crossing (`value`).

    Both give each root's `root_value`, bit for bit. The values of the crossing rules and the sides of
    the switching surfaces come from one generated program of the run over one environment of the
    time and state; the other roots are array arithmetic with the same operations in the same order.
    When the program or the arithmetic fails, the roots are evaluated one by one, in their order, so
    the first that fails reports itself.
    """

    def __init__(self, system, environment, roots, values_program=None):
        s = self.system = system
        self.environment = environment
        self.roots = roots = list(roots)
        self.direction = np.array([root.direction for root in roots], dtype=float)
        kinds = {}
        for k, root in enumerate(roots):
            kinds.setdefault(root.kind, []).append(k)

        def column(kind, field, dtype=float):
            return np.array([roots[k].data[field] for k in kinds.get(kind, [])], dtype=dtype)

        self.kinds = {kind: np.array(ks, dtype=int) for kind, ks in kinds.items()}
        self.guard_rows = column('guard', 0, int)
        self.guard_offsets = column('guard', 2)
        self.release_rows, self.release_limits = column('release', 0, int), column('release', 1)
        self.release_signs = column('release', 2)
        self.release_twice = 2 * s.atol[self.release_rows]
        self.bound_rows, self.bound_limits = column('bound', 0, int), column('bound', 1)
        self.bound_starts = column('bound', 2)
        self.bound_directions = np.array([roots[k].direction for k in kinds.get('bound', [])], dtype=float)
        self.bound_atol = s.atol[self.bound_rows]
        self.bound_start_value = -self.bound_directions * self.bound_atol
        self.cash_rows, self.debt_rows = column('repayment', 0, int), column('repayment', 1, int)
        self.floors = column('repayment', 2)
        # The expressions that the program computes: the value of each crossing rule, then both sides
        # of each switching surface.
        sources = [roots[k].data[1] for k in kinds.get('guard', [])]
        for kind in ('surface', 'band-exit'):
            sources.extend(side for k in kinds.get(kind, []) for side in roots[k].data)
        index = {source: n for n, source in enumerate(dict.fromkeys(sources))}
        self.guard_values = np.array([index[roots[k].data[1]] for k in kinds.get('guard', [])], dtype=int)
        self.left = np.array([index[roots[k].data[0]] for k in kinds.get('surface', [])], dtype=int)
        self.surface_starts = np.array([roots[k].start for k in kinds.get('surface', [])], dtype=float)
        self.right = np.array([index[roots[k].data[1]] for k in kinds.get('surface', [])], dtype=int)
        self.band_operands = [
            (k, *(index[node] for node in roots[k].data)) for k in kinds.get('band-exit', [])
        ]
        # `values_program(sources)` gives `values(at, state)` without an environment (`Field`), when it
        # can be made; else the program reads an environment.
        self.direct = None
        if index and values_program is not None:
            self.direct = values_program(tuple(index))
        self.program = self._program(tuple(index)) if index and self.direct is None else None
        if self.direct is not None:
            self.program = self.direct

    def _program(self, sources):
        """The generated program of these expressions; a run makes each set of them once. False when
        it cannot be made: the roots are then evaluated one by one."""
        s = self.system
        programs = s.analysis.setdefault('roots', {})
        if sources not in programs:
            try:
                programs[sources] = compile_program([], list(sources), constants=s.known, units=s.units)
            except (SyntaxError, RecursionError, ValueError):
                programs[sources] = False
        return programs[sources]

    def __len__(self):
        return len(self.roots)

    def value(self, k, at, state):
        return root_value(self.system, self.environment, self.roots[k], at, state)

    def values(self, at, state):
        if self.program is not False:
            try:
                return self._together(at, state)
            except Exception:  # the roots one by one report the failure
                pass
        return np.array([self.value(k, at, state) for k in range(len(self.roots))], dtype=float)

    def _together(self, at, state):
        s, kinds, out = self.system, self.kinds, np.empty(len(self.roots))
        if self.program is not None:
            values = (
                self.direct(at, state)
                if self.direct is not None
                else self.program(self.environment(at, state), s.units)
            )
            computed = np.array(values, dtype=float)
            if 'guard' in kinds:
                out[kinds['guard']] = (
                    state[self.guard_rows] - computed[self.guard_values] + self.guard_offsets
                )
            if 'surface' in kinds:
                rows = kinds['surface']
                gaps = computed[self.left] - computed[self.right]
                leaving = np.isfinite(self.surface_starts) & ((at == self.surface_starts) | (gaps == 0))
                out[rows] = np.where(leaving, -self.direction[rows] * np.finfo(float).tiny, gaps)
            if self.band_operands:
                env = None

                def read(node):
                    nonlocal env
                    if env is None:
                        env = self.environment(at, state)
                    return evaluate(node, env, s.units)

                for k, left, right in self.band_operands:
                    out[k] = band_root(
                        self.roots[k], read, s.units.comparisons, (computed[left], computed[right])
                    )
        if 'release' in kinds:
            out[kinds['release']] = (
                self.release_signs * (state[self.release_rows] - self.release_limits) - self.release_twice
            )
        if 'bound' in kinds:
            val = state[self.bound_rows] - self.bound_limits
            on_start = (at == self.bound_starts) & (val == 0)
            out[kinds['bound']] = np.where(on_start, self.bound_start_value, val)
        if 'repayment' in kinds:
            out[kinds['repayment']] = state[self.cash_rows] - state[self.debt_rows] - self.floors
        return out


def active_roots(before, after, direction):
    """The roots whose sign changes in their direction from one accepted step to the next
    (`find_active_events` in scipy.integrate._ivp.ivp)."""
    up = (before <= 0) & (after >= 0)
    down = (before >= 0) & (after <= 0)
    either = up | down
    return np.nonzero((up & (direction > 0)) | (down & (direction < 0)) | (either & (direction == 0)))[0]


def crossing_time(gap, start, end, *, side=None, accepted=None, exact=None, speed=None, within=None):
    """Locate a contact on an incoming trajectory. A switch armed on `side` must leave that
    open side in (start, end]. The caller can also supply a bracket already certified by the
    step, or an analytically known time. At either endpoint the accepted samples take precedence
    over dense interpolation, which can round a bracket away there."""
    first = accepted[0] if accepted is not None else gap(start)
    if side is not None and first * side <= 0:
        return None
    if exact is not None and (start < exact <= end or (side is None and exact == start)):
        return exact
    last = accepted[1] if accepted is not None else gap(end)
    if side is not None and last * side > 0:
        return None
    if first == 0:
        return start
    if last == 0:
        return end

    def difference(at):
        if at == start:
            return first
        if at == end:
            return last
        value = gap(at)
        if speed is not None and value * first < 0:
            # On a monotone piece a candidate on the outgoing side is already the physical
            # crossing to the locator's time precision if the incoming side is that close.
            width = ROOT_TOLERANCE * (1 + abs(at))
            if abs(value) <= speed * width and (at - width <= start or gap(at - width) * first >= 0):
                return 0.0
        return value

    at = brentq(difference, start, end, xtol=ROOT_TOLERANCE, rtol=ROOT_TOLERANCE)
    if at == start and math.nextafter(start, end) >= end:
        return end
    if at == start:
        # The absolute timestamp can round a positive interval to zero. Locate the short interval
        # relative to its start; it occupies at least the following representable time.
        length = brentq(
            lambda h: difference(start + h),
            0,
            end - start,
            xtol=math.ulp(start) if start else np.finfo(float).tiny,
            rtol=ROOT_TOLERANCE,
        )
        at = max(math.nextafter(start, end), start + length)
    if within is not None and not within(at, gap(at)):
        # A narrow operand band can require a much tighter root than the time tolerance.
        # Refine on the same dense trajectory down to adjacent representable instants.
        low, high = start, end
        while low < high:
            mid = low + 0.5 * (high - low)
            if mid in (low, high):
                return min((low, high), key=lambda t: abs(gap(t)))
            residual = gap(mid)
            if within(mid, residual):
                return mid
            if (residual > 0) == (first > 0):
                low = mid
            else:
                high = mid
    return at


def locate(roots, k, solution, start, end, before, after):
    """Locate a component's already bracketed root using its accepted endpoint states."""
    target = roots.roots[k] if isinstance(roots, Roots) else None
    within = None
    if target is not None and target.kind == 'band-exit':
        return first_outside(lambda at: roots.value(k, at, solution(at)) > 0, start, end)
    if target is not None and target.kind == 'surface':
        pair, units = target.data, roots.system.units

        def reader(at):
            env = roots.environment(at, solution(at))
            return lambda node: evaluate(node, env, units)

        within = contact_band(pair, reader, units)
    return crossing_time(
        lambda at: roots.value(k, at, solution(at)),
        start,
        end,
        accepted=(before, after),
        exact=target.fixed_time if target is not None else None,
        within=within,
    )


def comparison_side(pair, read, comparisons, values=None):
    """The comparison sign on either open side, or zero in the closed equality band."""
    a, b = values if values is not None else (read(node) for node in pair)
    gap, band = comparisons.gap_band(*pair, a, b, read)
    if against('eq', gap, band):
        return 0
    return 1 if gap > 0 else -1


def band_root(root, read, comparisons, values):
    side = comparison_side(root.band_pair or root.data, read, comparisons, values)
    return 1.0 if side else -1.0


def first_outside(outside, start, end):
    """The first representable time outside the band in a bracket with an inside start."""
    while (mid := start + 0.5 * (end - start)) not in (start, end):
        if outside(mid):
            end = mid
        else:
            start = mid
    return end


def switch_time(pair, reader, start, end, units, side, *, accepted=None, exact=None):
    """Locate departure from held equality or a physical return from the selected open side."""
    if side == 0:

        def outside(t):
            return comparison_side(pair, reader(t), units.comparisons) != 0

        if not outside(end) or outside(start):
            return None
        return first_outside(outside, start, end)

    def gap(t):
        read = reader(t)
        return read(pair[0]) - read(pair[1])

    return crossing_time(
        gap, start, end, side=side, accepted=accepted, exact=exact, within=contact_band(pair, reader, units)
    )


def contact_band(pair, reader, units):
    """Test the residual of a located switch in the units of its two operands."""

    def within(t, gap):
        read = reader(t)
        difference, width = units.comparisons.gap_band(*pair, *(read(node) for node in pair), read, gap)
        return against('eq', difference, width)

    return within


# The rate of change of the dense solution of one Radau step at a time of the step.
slope = radau_rate


def apart(length, field, rate, state, rtol, atol):
    """How far the solution of a step of `length` is from the field at a time inside the step, from
    the field there and the rate of the solution there: their difference times the length of the
    step, in the solver's own norm (the root of the mean of the squares of the differences, each
    over `atol + rtol * |state|`). The error of the solution in the step is no more than this
    difference added up over the step, so a value of 1 or less at each time says that the solution
    is within the tolerance of the solver in the whole step.

    A step that the solver accepts has a small value between its own points when the field is
    smooth there. The value is large where the field changes between those points in a way that
    they do not see: a short pulse, or a switch of a rate inside the step."""
    scale = atol + rtol * np.abs(state)
    difference = length * (field - rate) / scale
    return float(np.linalg.norm(difference) / difference.size**0.5)


def departure(fun, solution, at, state, rtol, atol):
    """`apart` for the dense solution of one Radau step: the field is asked for at the time."""
    return apart(solution.h, fun(at, state), slope(solution, at), state, rtol, atol)


# The difference of a step that the next step aims at (`departure`): a quarter of the tolerance, so
# that a step whose difference is a few times that of the step before it is still used.
AIM = 0.25
# A step longer than the check interval is read at each half of an interval inside it. Below two
# intervals that costs more evaluations of the field than the steps that it saves.
WORTH = 2.0


def next_limit(length, far, check, ceiling):
    """The longest step after a step of `length` whose largest difference is `far`: the difference
    grows as the fourth power of the step, so this is the step that brings it to `AIM`, with a
    margin; the check interval when that is not worth more than the interval; `ceiling` at the most."""
    longest = 0.9 * length * (AIM / max(far, 1e-6)) ** 0.25 if math.isfinite(far) else 0.0
    return min(ceiling, longest) if longest >= WORTH * check else min(ceiling, check)


# The most steps of the check interval that the solver takes before it tries a longer step again.
LONGEST_WAIT = 32

# A segment is stalled after STALLED_STEPS accepted steps in a row, each shorter than the shortest
# time between two moments that the engine tells apart (the run's `Numerics.crossing`): with the
# default, it has then moved less than 1e-5 h in that many steps. This is what a rate that switches
# back and forth at a condition makes the solver do (`Limit.accepted`).
STALLED_STEPS = 1000
# The status of an integration that stopped stalled (`radau`).
STALLED = -2


class Limit:
    """The longest step that the solver can take next, from its steps so far: `allowed`. `check` is
    the interval at which the engine reads the segment, and `ceiling` the longest step of all.

    - A step longer than the check interval that is used sets the limit from its largest
      difference (`next_limit`).
    - A step that is not used does the same from the difference that was too large. When that
      holds the solver at the check interval, the limit grows again (to two intervals, then by
      what the steps show) after `wait` steps of the interval at most. The wait is one step after
      a first step that is not used. It doubles with each further one, to `LONGEST_WAIT` at the
      most, until a longer step is used and allows a longer step after it: in a part of the
      solution where a longer step fails each time, about one step in `LONGEST_WAIT` is lost,
      and not each second one.

    It also counts the accepted steps in a row that are shorter than `moment`, the time between two
    moments that the engine tells apart (`accepted`): after `STALLED_STEPS` of them, the segment is
    stalled. A run gives its own (`Numerics.crossing`); the default is that of a configuration."""

    def __init__(self, check, ceiling, moment=Numerics.crossing):
        self.check, self.ceiling, self.allowed = check, ceiling, ceiling
        self.moment = moment
        self.wait, self.after = 0, 1
        # The accepted steps in a row that are shorter than a moment, and the time at which the
        # first of them started.
        self.brief, self.brief_from = 0, None

    def accepted(self, start, end):
        """The solver accepted a step from `start` to `end`. True when the segment is stalled: this
        step and the `STALLED_STEPS - 1` accepted steps before it are each shorter than `moment`. A
        step that is not used does not change the count; a longer step starts it again."""
        if end - start < self.moment:
            if self.brief == 0:
                self.brief_from = float(start)
            self.brief += 1
        else:
            self.brief, self.brief_from = 0, None
        return self.brief >= STALLED_STEPS

    def short(self):
        """A step of the check interval at most was taken."""
        if self.wait > 0:
            self.wait -= 1
        if self.wait == 0:
            self.allowed = min(self.ceiling, 2 * self.allowed)

    def used(self, length, largest):
        """A step of `length`, longer than the check interval, is used: `largest` is its largest
        difference."""
        self.allowed = next_limit(length, largest, self.check, self.ceiling)
        if self.allowed > self.check:
            self.wait, self.after = 0, 1
        else:
            self.wait, self.after = self.after, min(2 * self.after, LONGEST_WAIT)

    def unused(self, length, far):
        """A step of `length` is not used: its difference `far` is too large."""
        self.allowed = next_limit(length, far, self.check, self.ceiling)
        if not self.allowed > self.check:
            self.wait, self.after = self.after, min(2 * self.after, LONGEST_WAIT)


def radau(
    fun,
    interval,
    initial,
    roots=None,
    check=None,
    moment=Numerics.crossing,
    leg_rates=None,
    held_comparisons=None,
    comparison_factor=None,
    **options,
):
    """`solve_ivp(fun, interval, initial, method='Radau', dense_output=True, events=...)` for roots
    that each end the integration.

    `roots` (a `Roots`) gives the values of all its roots together (`values`), and the value of one
    root to locate its crossing (`locate`). The first root in time ends the integration. `moment` is
    the time between two moments that the engine tells apart, which tells a stalled solver
    (`Limit`). `options` go to the Radau solver.

    With no `check`, the roots are read at each accepted step: the steps, the roots and the result
    of `solve_ivp`, bit for bit. `check` is the interval, from the start of the integration, at
    which the engine reads the segment (the step cap of the run). A step of the solver can be
    longer; a step of that interval at most is read at its end, as before. Inside a longer step, on
    the dense solution of the step:

    - at each half of a check interval, the field is compared with the rate of the dense solution
      (`departure`). A solver that the check interval limits reads the field at the points of each
      of its steps, which are less than half a step apart: the field is read as often here. The
      largest difference of a step sets the longest next step (`next_limit`). When the dense
      solution is too far from the field at one of these times, the step is not used: the
      integration goes on from the start of that step with that shorter limit. With the check
      interval as the limit, the integration is that of a solver that the check interval limits;
    - stock bounds are located on the dense polynomial of every accepted step. Other roots are
      read at each check time and located between the two observations that bracket them.
    """
    t0, tf = map(float, interval)
    solver = Radau(fun, t0, initial, tf, vectorized=False, **options)
    capture = CollocationRates(solver, leg_rates) if leg_rates is not None else None
    ts, ys, interpolants = [t0], [initial], []
    if roots is not None:
        g = roots.values(t0, initial)
        t_events, y_events = [[] for _ in range(len(g))], [[] for _ in range(len(g))]
    else:
        g = None
        t_events = y_events = None
    status = None
    candidates = []
    bound_ids = roots.kinds.get('bound') if isinstance(roots, Roots) else None
    directions = roots.direction if roots is not None else None
    if bound_ids is not None:
        # The dense locator owns bound events. Only the remaining roots use endpoint sign changes.
        directions = directions.copy()
        directions[bound_ids] = np.nan
    half = None if check is None else check / 2
    halves = 0  # the halves of a check interval before the step, from the start
    # The longest step that the differences of the steps before allow the solver now.
    limit = None if check is None else Limit(check, solver.max_step, moment)
    while status is None:
        if check is not None:
            solver.max_step = limit.allowed
            # What the solver holds before the step. A step replaces what it holds and changes
            # nothing in place, so this is the solver at the start of the step again
            # (`scipy.integrate._ivp.radau.Radau._step_impl`).
            held = dict(vars(solver))
        message = solver.step()
        if solver.status == 'finished':
            status = 0
        elif solver.status == 'failed':
            status = -1
            break
        t_old, t, y = solver.t_old, solver.t, solver.y
        sol = solver.dense_output()
        if capture is not None:
            capture.finish(sol)
        if held_comparisons:
            exits = exits_of_held_comparisons(held_comparisons, comparison_factor, sol, t_old, t)
            change = min((at for at, _ in exits), default=None)
            if change is not None:
                t, y, status = change, sol(change), 0
        candidates = []
        if bound_ids is not None:
            candidates = [
                (at, int(bound_ids[k]))
                for at, k in dense.bound_crossings(
                    sol,
                    t_old,
                    t,
                    roots.bound_rows,
                    roots.bound_limits,
                    roots.bound_directions,
                    accepted_end=y,
                )
            ]
            if candidates:
                # The scheduler may group a neighboring contact. Search for other roots on the
                # same incoming trajectory, within its timing window.
                through = candidates[0][0] + 2 * moment
                if through < t:
                    t, y = through, sol(through)
        ended = None  # (the time, the root) of the first root inside the step
        if check is not None and not t - t_old > check:
            # A step of the check interval at most is read at its end, as each step was before.
            while t0 + (halves + 1) * half < t:
                halves += 1
            limit.short()
            if limit.accepted(t_old, t) and status is None:
                status = STALLED
                break
        if check is not None and t - t_old > check:
            # The times inside the step that are a whole number of half intervals from the start.
            # Each second one is a check time.
            before, g_before, count, largest = t_old, g, halves, 0.0
            while ended is None:
                at = t0 + (count + 1) * half
                if not at < t:
                    break
                count += 1
                if at <= t_old:
                    continue
                state = sol(at)
                far = departure(fun, sol, at, state, options['rtol'], options['atol'])
                if not far <= 1.0:
                    ended = 'unused'
                    break
                largest = max(largest, far)
                if roots is not None and count % 2 == 0:
                    g_at = roots.values(at, state)
                    active = active_roots(g_before, g_at, directions)
                    if active.size > 0:
                        found = [locate(roots, k, sol, before, at, g_before[k], g_at[k]) for k in active]
                        first = int(np.argmin(found))
                        ended = (found[first], int(active[first]))
                        # A check inside this accepted step can split two roots belonging to one
                        # scheduled moment. Search the remainder of a full timing window under the
                        # same incoming field. The scheduler checks each root against its anchor.
                        through = min(t, found[first] + 2 * moment)
                        if at < through:
                            other = roots.values(through, sol(through))
                            later = np.setdiff1d(active_roots(g_at, other, directions), active)
                            found.extend(locate(roots, k, sol, at, through, g_at[k], other[k]) for k in later)
                            active = np.concatenate((active, later))
                    before, g_before = at, g_at
            if ended == 'unused':
                # The solver as it was at the start of this step, with a shorter limit on its
                # steps. The counts of its work stay: the step that is not used was work.
                limit.unused(t - t_old, far)
                counts = {name: getattr(solver, name) for name in ('nfev', 'njev', 'nlu')}
                vars(solver).clear()
                vars(solver).update(held)
                vars(solver).update(counts)
                status = None
                continue
            halves = count
            limit.used(t - t_old, largest)
            limit.accepted(t_old, t)
            if ended is None and roots is not None:
                g_new = roots.values(t, y)
                active = active_roots(g_before, g_new, directions)
                if active.size > 0:
                    found = np.asarray(
                        [locate(roots, k, sol, before, t, g_before[k], g_new[k]) for k in active]
                    )
                    first = int(np.argmin(found))
                    ended = (float(found[first]), int(active[first]))
                g = g_new
            if ended is not None:
                candidates.extend((float(at), int(k)) for at, k in zip(found, active))
        elif roots is not None:
            g_new = roots.values(t, y)
            active = active_roots(g, g_new, directions)
            if active.size > 0:
                candidates.extend((locate(roots, k, sol, t_old, t, g[k], g_new[k]), int(k)) for k in active)
            g = g_new
        if candidates:
            te, k = min(candidates) if t >= t_old else max(candidates)
            t_events[k].append(te)
            y_events[k].append(sol(te))
            status = 1
            t, y = te, sol(te)
        interpolants.append(sol)
        if len(ts) > 1 and ts[-1] == t:
            interpolants.pop()
        else:
            ts.append(t)
            ys.append(y)
    message = MESSAGES.get(status, message)
    if t_events is not None:
        t_events = [np.asarray(te) for te in t_events]
        y_events = [np.asarray(ye) for ye in y_events]
    ts = np.array(ts)
    ys = np.vstack(ys).T
    return OptimizeResult(
        # With STALLED, or when the solver failed: (the start of the accepted steps in a row that are
        # shorter than the event time tolerance, or the time of the last accepted state when there
        # is none; the time of the last accepted state).
        short=(limit.brief_from if limit.brief else float(solver.t), float(solver.t))
        if limit is not None and status in (STALLED, -1)
        else None,
        root_candidates=candidates,
        t=ts,
        y=ys,
        sol=OdeSolution(ts, interpolants, alt_segment=False),
        t_events=t_events,
        y_events=y_events,
        nfev=solver.nfev,
        njev=solver.njev,
        nlu=solver.nlu,
        status=status,
        message=message,
        success=status >= 0,
    )


def release_root(run, i, bound):
    """The root at which a quantity resting on a bound leaves it by twice its tolerance."""
    return Root('release', 1, (i, run.y[i], 1 if bound == 'min' else -1))


def segment_roots(system, run, watcher, environment):
    """The roots that end a segment: every armed level rule, the release of every active bound and
    every finite bound a quantity can reach. Each comes with its descriptor."""
    s = system
    roots, descriptors = [], []
    run.guards.clear()
    for rid, cond in watcher.guards(environment(run.time, run.y)):
        i = s.index[cond['var']]
        target = None
        if not s.expanded_names(cond['value']) & (s.evolving | {'t'}):
            value = float(evaluate(cond['value'], environment(run.time, run.y), s.units))
            if value == s.lower[i]:
                target = (i, value)
        direction = 1 if cond['op'] == '>=' else -1
        offset = 0.0
        if rid in s.monotone_crossings:
            # Watched inside the band where the rule holds; the quantity stays where the root finds it.
            offset, target = 0.5 * direction * float(s.atol[i]), None
        roots.append(Root('guard', direction, (i, cond['value'], offset), target))
        descriptors.append(('event', rid))
        run.guards[rid] = cond
    for i, bound in sorted(run.active_bounds):
        roots.append(release_root(run, i, bound))
        descriptors.append(('release', (i, bound)))
    start = run.time
    for i in range(len(run.y)):
        for bound, limit, direction in (('min', s.lower[i], -1), ('max', s.upper[i], 1)):
            if not math.isfinite(limit) or (i, bound) in run.active_bounds:
                continue
            if bound == 'min' and s.monotone[i] and run.y[i] >= limit:
                continue  # a nondecreasing state cannot fall to its lower bound
            roots.append(Root('bound', direction, (i, limit, start), (i, limit)))
            descriptors.append(('bound', (i, bound)))
    return roots, descriptors


def switching_surfaces(system):
    """Every min/max/clip/abs argument pair and every state-dependent condition (a comparison, a
    membership's two ends) in the rate expressions, in their first order: the switching surfaces of
    the run (`switching_roots`).

    They read only the run's expressions and the quantities that move, so a run finds them once.
    """
    s = system
    if 'switching' not in s.analysis:
        sources = [f.rate for f in s.flows.values()]
        sources += [d.expr for d in s.resolved.rates.values()] + [g.capacity for g in s.groups.values()]
        formulas = {name: found['expr'] for name, found in s.computed.items()}
        moving = s.evolving | {'t'}
        surfaces = surfaces_of(sources, formulas, lambda node: s.expanded_names(node) & moving)
        s.analysis['switching'] = surfaces
        s.analysis['switch_layers'] = switch_layers(surfaces, formulas)
    return s.analysis['switching']


def surfaces_of(sources, formulas, moving):
    """The switching surfaces of some expressions and of the formulas that they read (`formulas`: a
    name -> the node that computes it), in their first order: each pair of the arguments of min, max,
    clip and abs, and of the sides of a comparison or of a membership's ends, of which one side moves
    (`moving(node)`: whether it reads the time or a quantity that moves, through formulas)."""
    found, seen, pending = [], set(), list(sources)
    while pending:
        expr = nodes.read(pending.pop())
        if expr in seen:
            continue
        seen.add(expr)
        found.append(expr)
        pending += [formulas[n] for n in names_in(expr) if n in formulas]
    surfaces = {}
    for expr in found:
        for node in nodes.breadth_first(expr):
            for a, b in switch_pairs(node):
                if moving(a) or moving(b):
                    surfaces[(a, b)] = None
    return tuple(surfaces)


def switch_pairs(node):
    """Operand pairs whose ordering selects a piece of this operation."""
    if isinstance(node, nodes.Compare):
        return [
            (left, right)
            for left, op, right in zip(node.operands, node.ops, node.operands[1:])
            if op not in ('eq', 'ne')
        ]
    if isinstance(node, nodes.Call):
        args = node.args
        if node.function in ('min', 'max'):
            return [(a, b) for k, a in enumerate(args) for b in args[k + 1 :]]
        if node.function == 'clip' and len(args) == 3:
            return [(args[0], args[1]), (args[0], args[2])]
        if node.function == 'abs' and len(args) == 1:
            return [(args[0], ZERO)]
        if nodes.membership(node) is not None:
            return [(args[1], args[0]), (args[0], args[2])]
    return ()


def switch_layers(surfaces, formulas):
    """Group surfaces by the nested branch decisions their operands read, through named formulas.
    The ordering belongs to the installed expressions and is reused at every contact."""
    if len(surfaces) < 2:
        return (surfaces,) if surfaces else ()
    present = set(surfaces)
    depths = {}

    def depth(node):
        if node not in depths:
            children = node.children
            if isinstance(node, nodes.Ref) and node.name in formulas:
                children = (nodes.read(formulas[node.name]),)
            value = 0
            for child in children:
                value = max(value, (yield depth(child)))
            depths[node] = value + any(pair in present for pair in switch_pairs(node))
        return depths[node]

    groups = {}
    for a, b in surfaces:
        level = max(walked(depth(a)), walked(depth(b)))
        groups.setdefault(level, []).append((a, b))
    return tuple(groups[k] for k in sorted(groups))


def flow_switches(settings, formulas, moving):
    """The authored flows whose settings include each physical switching surface."""
    owners = {}
    for name, sources in settings:
        for pair in surfaces_of(sources, formulas, moving):
            owners.setdefault(pair, []).append(name)
    return owners


def branch_sides(surfaces, side, comparisons):
    """Classify readable operands in their band, retaining equal-band values for the departure probe.
    An undefined side in an untaken branch leaves its expression alone."""
    signs, equal = {}, {}
    for pair in surfaces:
        try:
            left, right = side(pair[0]), side(pair[1])
            if math.isfinite(left) and math.isfinite(right):
                sign = comparison_side(pair, side, comparisons, (left, right))
                signs[pair] = sign
                if not sign:
                    equal[pair] = left, right
        except (ExpressionError, TypeError, ValueError, ArithmeticError, LookupError):
            continue
    return signs, equal


def curved_motion(t, y, h, drift, rates, side_at, place):
    """Read displacements along one short outgoing trial shared by all curved comparisons."""
    displacement = h * drift
    middle = h * rates(t + h / 2, y + displacement / 2)
    if not np.array_equal(middle, displacement):
        # Integrate increments, not the full inventory: a large starting level
        # must not set the accuracy of a small relative movement between operands.
        scale = np.maximum(abs(middle), abs(displacement))
        trial = solve_ivp(
            lambda s, increment: h * rates(t + s * h, y + increment),
            (0, 1),
            np.zeros_like(y),
            method='DOP853',
            first_step=1,
            rtol=Numerics.rtol,
            atol=np.maximum(np.finfo(float).tiny, Numerics.rtol * scale),
        )
        if not trial.success:
            raise SimulationError(f'cannot resolve the departing switch at {t:g} h: {trial.message}')
        displacement = trial.y[:, -1]
    following = side_at(t + h, y + displacement)

    def motion(node, initial):
        if isinstance(node, nodes.Ref) and node.name in place:
            # A small increment may round away in a large starting inventory.
            return displacement[place[node.name]]
        return following(node) - initial

    return motion


def departing_branches(surfaces, t, y, side_at, rates, place, moving, contacted, comparisons):
    """Select the sides a segment leaves on, including comparisons between two moving expressions.
    At a contact their equal values alone cannot pick a side. Compare their values along the
    outgoing trajectory; arithmetic outside the condition continues to read the actual state."""
    if not surfaces:
        return {}
    side = side_at(t, y)
    signs, equal = branch_sides(surfaces, side, comparisons)
    contacts = {
        pair: values for pair, values in equal.items() if t or values[0] == values[1] or pair in contacted
    }
    if contacts:
        h = math.sqrt(np.finfo(float).eps) * max(1.0, abs(t))
        drift = rates(t, y)
        probe = y + h * drift
        following = side_at(t + h, probe)
        motion = None

        def directed(node, other):
            return (
                isinstance(node, nodes.Ref)
                and (node.name == 't' or (node.name in place and drift[place[node.name]] != 0))
                and not moving(other)
            )

        for (a, b), (left, right) in contacts.items():
            try:
                if left != right and (a, b) not in contacted:
                    # An interpolated inventory at a scheduled cut can miss a physical
                    # tangency by a few ulps. Require an actual equality on the local
                    # trajectory at a neighbouring clock float. A nonzero gap elsewhere
                    # inside the band stays held until its band-exit root.
                    def touches(toward):
                        at = t
                        for _ in range(8):
                            at = math.nextafter(at, toward)
                            read = side_at(at, y + (at - t) * drift)
                            if read(a) == read(b):
                                return True
                        return False

                    if not (touches(math.inf) or touches(0.0)):
                        continue
                change = (following(a) - left) - (following(b) - right)
                if change == 0 or not (directed(a, b) or directed(b, a)):
                    if motion is None:
                        motion = curved_motion(t, y, h, drift, rates, side_at, place)
                    da, db = motion(a, left), motion(b, right)
                    change = da - db
                    if moving(a) and moving(b):
                        # A stock has a directly integrated increment. A formula subtracts
                        # two rounded coordinates to obtain the same increment. Allow the
                        # rounding of those coordinates and of the two integrated changes.
                        error = math.ulp(left) + math.ulp(right) + math.ulp(left + da) + math.ulp(right + db)
                        error += Numerics.rtol * (abs(da) + abs(db))
                        if abs(change) <= error:
                            change = 0
            except (ExpressionError, TypeError, ValueError, ArithmeticError, LookupError):
                continue
            signs[a, b] = int(change > 0) - int(change < 0)
    return signs


def branch_expression(source, signs):
    """Read a segment's selected branches with the trial state's actual arithmetic operands.
    Only comparisons that separate smooth fields change. A nested or short-circuit condition
    keeps its own order and the expressions of its untaken branches stay unevaluated."""
    if not signs:
        return source

    def comparison(node):
        parts = []
        for left, op, right in zip(node.operands, node.ops, node.operands[1:]):
            sign = signs.get((left, right))
            # An armed equality holds its ordered comparisons on the entire smooth
            # segment, including trial states perturbed for the numerical Jacobian.
            if sign is None or op in ('eq', 'ne'):
                parts.append(nodes.compare([op], [changed[left], changed[right]]))
            else:
                parts.append(
                    nodes.const({'lt': sign < 0, 'le': sign <= 0, 'gt': sign > 0, 'ge': sign >= 0}[op])
                )
        if len(parts) == 1:
            return parts[0]
        if all(isinstance(part, nodes.Const) for part in parts):
            return nodes.const(all(part.value for part in parts))
        return nodes.boolean('and', parts)

    def chosen(node):
        if isinstance(node, nodes.Compare):
            return comparison(node)
        if isinstance(node, nodes.Call):
            args = node.args
            if node.function == 'abs' and signs.get((args[0], ZERO)):
                value = changed[args[0]]
                return nodes.unary('neg', value) if signs[(args[0], ZERO)] < 0 else value
            if node.function in ('min', 'max') and len(args) >= 2:
                way = 1 if node.function == 'min' else -1
                beaten = set()
                for k, left in enumerate(args):
                    for j in range(k + 1, len(args)):
                        sign = signs.get((left, args[j]))
                        if sign:
                            beaten.add(k if sign * way > 0 else j)
                kept = [changed[arg] for k, arg in enumerate(args) if k not in beaten]
                if len(kept) == 1:
                    return kept[0]
                if kept:
                    return nodes.call(node.function, kept)
            if node.function == 'clip' and len(args) == 3:
                x, low, high = args
                lower_sign, upper_sign = signs.get((x, low)) or None, signs.get((x, high)) or None
                if lower_sign is not None or upper_sign is not None:
                    value = changed[x]
                    if lower_sign is None:
                        value = nodes.call('max', [value, changed[low]])
                    elif lower_sign < 0:
                        value = changed[low]
                    if upper_sign is None:
                        value = nodes.call('min', [value, changed[high]])
                    elif upper_sign > 0:
                        value = changed[high]
                    return nodes.if_else(nodes.compare(['le'], [changed[low], changed[high]]), value, node)
            within = nodes.membership(node)
            if within is not None:
                x, low, high = args
                if (low, x) in signs or (x, high) in signs:
                    # Preserve the native diagnostic for a reversed interval.
                    return nodes.if_else(
                        nodes.compare(['le'], [changed[low], changed[high]]),
                        comparison(within[0]),
                        node,
                    )
            return nodes.call(node.function, (changed[child] for child in args))
        if isinstance(node, nodes.IfElse):
            test = changed[node.test]
            if isinstance(test, nodes.Const):
                return changed[node.body if test.value else node.orelse]
            return nodes.if_else(test, changed[node.body], changed[node.orelse])
        if isinstance(node, nodes.Unary):
            return nodes.unary(node.op, changed[node.operand])
        if isinstance(node, nodes.Binary):
            return nodes.binary(node.op, changed[node.left], changed[node.right])
        if isinstance(node, nodes.BoolOp):
            return nodes.boolean(node.op, (changed[child] for child in node.values))
        return node

    root = nodes.read(source)
    changed = {}
    stack = [(root, False)]
    while stack:
        node, ready = stack.pop()
        if node in changed:
            continue
        if ready:
            changed[node] = chosen(node)
        else:
            stack.append((node, True))
            stack.extend((child, False) for child in node.children)
    return changed[root]


def switching_roots(system, side, repayment_surfaces, at, state, signs=None, contacted=(), consumed=()):
    """End numerical segments where a piecewise rate changes branch.

    Every switching surface of the run (`switching_surfaces`) splits two smooth regimes;
    integrating across one mixes them in a single step, so each surface that is not
    already at its switch at the segment start becomes a terminal root. A switch the state
    leaves at its start also has a directed root for a later return. Returns those roots and
    the surfaces already at their switch.
    """
    s = system
    index = s.index
    dynamic_names = s.evolving | {'t'}
    surfaces = switching_surfaces(s)
    roots, at_switch = [], []
    for cash, debt, floor in repayment_surfaces:
        gap = state[index[cash]] - state[index[debt]] - floor
        if gap >= 0:
            continue
        roots.append(Root('repayment', 1, (index[cash], index[debt], floor)))
    for a, b in surfaces:
        try:
            left, right = side(a), side(b)
        except (ExpressionError, TypeError, ValueError):
            continue  # an untaken branch outside its domain is not a live surface
        gap = left - right
        clock = fixed_clock(
            (a, b),
            lambda node: left if node == a else right,
            lambda node: bool(s.expanded_names(node) & dynamic_names),
        )
        if (a, b) in consumed and consumed[a, b] == clock:
            continue
        direction, start = 0, None
        if not math.isfinite(gap):
            continue
        pair = a, b
        side_now = comparison_side(pair, side, s.units.comparisons, (left, right))
        if not side_now or pair in contacted:
            at_switch.append(pair)
            sign = (signs or {}).get(pair)
            if sign == 0 and not side_now:
                roots.append(Root('band-exit', 1, pair, band_pair=pair))
                continue
            if sign is None:
                continue
            # A later return to the same switch ends this segment too. While the operands
            # remain equal, give the root its departure sign to avoid a second event at rest.
            direction, start = -sign, at
        # A located stock-face switch carries its exact physical target.
        # Positive interpolation roundoff at zero needs the same balanced
        # correction as negative roundoff before the next smooth segment.
        target = None
        for coordinate, target_expr in ((a, b), (b, a)):
            # A side that is the name of a quantity, against a side that does not move.
            if not isinstance(coordinate, nodes.Ref) or coordinate.name not in index:
                continue
            if s.expanded_names(target_expr) & dynamic_names:
                continue
            i = index[coordinate.name]
            value = side(target_expr)
            if value == s.lower[i]:
                target = (i, value)
        roots.append(Root('surface', direction, (a, b), target, start, clock))
    return roots, at_switch


def starting_sides(system, run, field):
    """The sides of the switches at which a segment of a component starts, as `far_sides` finds them,
    which the field reads through the segment (`Run.switches`, `Run.clock`)."""
    s = system
    moving = s.evolving | {'t'}

    def reversal(name):
        raise SimulationError(f'chattering at {run.time:g} h: rates switch back and forth at {name}')

    run.switches, run.clock, _, run.held_comparisons = far_sides(
        switching_surfaces(s),
        s.analysis['switch_layers'],
        run.time,
        run.y,
        s.index,
        (s.lower, s.upper),
        field.operands,
        lambda node: bool(s.expanded_names(node) & moving),
        lambda t, y: field.rates(t, y, allocation=True),
        field.choose,
        s.units.comparisons,
        physical=field.rates,
        held=lambda i: (i, 'min') in run.active_bounds or (i, 'max') in run.active_bounds,
        reversal=reversal,
        contacted=run.contacted,
        consumed=run.contact_clocks,
    )


def fixed_clock(pair, side, moving):
    """The authored clock time of a switch, or None when its threshold moves."""
    for node, other in (pair, pair[::-1]):
        if isinstance(node, nodes.Ref) and node.name == 't' and not moving(other):
            return side(other)
    return None


def clock_sides(surfaces, t, side, moving, consumed=()):
    """Each fixed clock is evaluated once. An early grouped clock moves the clock probe
    beyond its located time. A past clock keeps its outgoing sign even inside the amount band."""
    limits, far, following = {}, None, math.inf
    for pair in surfaces:
        try:
            limit = fixed_clock(pair, side, moving)
        except (ExpressionError, TypeError, ValueError, ArithmeticError, LookupError):
            continue
        if limit is None or not math.isfinite(limit):
            continue
        limits[pair] = limit
        if t == limit or (pair in consumed and consumed[pair] == limit and t <= limit):
            beyond = math.nextafter(limit, math.inf)
            far = beyond if far is None else max(far, beyond)
        elif t < limit:
            following = min(following, limit)
    at = t if far is None else far
    signs = {
        pair: 1 if isinstance(pair[0], nodes.Ref) and pair[0].name == 't' else -1
        for pair, limit in limits.items()
        if 0 <= limit <= at
    }
    return None if far is None else (t, far, far), following, signs


def far_sides(
    surfaces,
    layers,
    t,
    y,
    place,
    bounds,
    side_at,
    moving,
    rates,
    choose,
    comparisons,
    *,
    held,
    reversal,
    physical,
    contacted=(),
    consumed=(),
    clocks=None,
):
    """Select the open segment at the actual state after the round's edits. The outgoing clock
    chooses the velocity used to resolve coincident store and composite switches. All fields
    install the same branches; only their evaluation of rates and operands differs."""
    if not surfaces:
        choose({})
        return (), None, {}, None
    side = side_at(t, y)
    if clocks is None:
        clocks = clock_sides(surfaces, t, side, moving, consumed)
    lower, upper = bounds
    clock, _, clock_branches = clocks
    at = t if clock is None else clock[2]  # every store crosses under the rates after the clock switches
    switches, derivative = [], None
    watched = band_edges = None
    choose(clock_branches)
    for a, b in surfaces:
        for here_node, other in ((a, b), (b, a)):
            if not isinstance(here_node, nodes.Ref) or here_node.name not in place:
                continue
            if moving(other):
                continue
            try:
                limit = side(other)
            except (ExpressionError, TypeError, ValueError, ArithmeticError, LookupError):
                continue
            if not math.isfinite(limit):
                continue
            i = place[here_node.name]
            here = float(y[i])
            if limit in (lower[i], upper[i]) and held(i):
                # While the stock stays in its band a booked residual cannot choose a
                # departure. Exactly on the band's edge the physical direction decides
                # whether the next open interval is still inside it.
                gap, band = comparisons.gap_band(here_node, other, here, limit, side)
                if abs(gap) <= band:
                    # These time-steppers fit a dense accepted segment. Its incoming
                    # piece must end before an otherwise stationary comparison switches.
                    if watched is None:
                        watched = set()
                    watched.add((i, limit, comparisons.band_floor(here_node, other, side)))
                if gap and abs(gap) == band:
                    if band_edges is None:
                        band_edges = {}
                    band_edges[a, b] = i, gap, 1 if here_node == a else -1
            # At the switch means within its band, as every comparison reads it. An exact float
            # test here let a ledger balance one place short of the threshold choose the
            # incoming side by its raw sign.
            gap, band = comparisons.gap_band(here_node, other, here, limit, side)
            if not against('eq', gap, band):
                continue  # away from the switch, or an edit replaced the stock or its threshold
            if held(i):
                continue  # sharing keeps the store on its bound throughout the segment
            velocity = 0.0
            if here != limit:
                # Roundoff at a located switch can reverse the apparent direction of departure.
                contact = y.copy()
                contact[i] = limit
                velocity = rates(at, contact)[i]
            if velocity == 0:
                # If the contact holds the store, keep the approach direction for the far-side probe.
                if derivative is None:
                    derivative = rates(at, y)
                velocity = derivative[i]
            way = 1 if velocity > 0 else -1 if velocity < 0 else 0
            if (limit == lower[i] and way <= 0) or (limit == upper[i] and way >= 0):
                continue  # the store cannot leave its interval
            beyond = math.nextafter(limit, way * math.inf) if way else here
            if way == 0 or (here - beyond) * way >= 0:
                continue  # it does not move, or it is on the far side already
            probe = np.array(y, dtype=float)
            probe[i] = beyond
            # Leave the arithmetic coordinates alone. A nextafter probe alone is still equal
            # under change 29 and would read the arriving branch on both sides.
            choose({**clock_branches, (a, b): way if here_node == a else -way})
            try:
                outgoing = rates(at, probe)[i]
            finally:
                choose(clock_branches)
            if outgoing * way < 0:
                reversal(here_node.name)
            low, high = (limit - float(band), beyond) if way > 0 else (beyond, limit + float(band))
            switches.append((i, low, high, beyond))
    departure = y.copy()
    for i, low, high, beyond in switches:
        if low <= departure[i] <= high:
            departure[i] = beyond
    reached = set(contacted) | clock_branches.keys()
    if switches:
        # Retain physical contacts at the unperturbed state when a fixed-stock probe
        # moves its coordinate to the neighbouring float.
        _, initial = branch_sides(surfaces, side, comparisons)
        reached.update(pair for pair, (left, right) in initial.items() if left == right)
    # A jump across an enclosing min/max/if changes its winning operand without
    # crossing its incoming root. Read each layer with all inner departures installed.
    signs = dict(clock_branches)
    for layer in layers:
        found = departing_branches(layer, at, departure, side_at, rates, place, moving, reached, comparisons)
        if band_edges:
            edges = [pair for pair in band_edges if found.get(pair) == 0]
            if edges:
                physical_motion = physical(at, y)
                for pair in edges:
                    i, gap, order = band_edges[pair]
                    if physical_motion[i] * gap > 0:
                        found[pair] = order if gap > 0 else -order
        signs = {**signs, **found, **clock_branches}
        choose(signs)
    return tuple(switches), clock, signs, watched


def exits_of_held_comparisons(edges, factor, solution, start, end):
    """First representable time on the far side of a held stock's comparison band.
    This ends the numerical piece without placing the stock on its authored threshold."""
    if not edges:
        return
    initial, final = solution(start), solution(end)
    for row, target, floor in edges:

        def outside(value, target=target, floor=floor):
            return abs(value - target) > band_from_floor_width(factor, floor, value, target)

        if initial[row] == final[row] or outside(initial[row]) or not outside(final[row]):
            continue
        yield first_outside(lambda at: outside(solution(at)[row]), start, end), row


def departing_ledgers(system, run, field, at_switch, env):
    """Nondecreasing ledgers that leave their lower bound at the segment start, where a surface at
    its switch compares the ledger itself with that bound.

    The ledger's rate is positive on its bound and just above it, so the ledger is above the bound
    at every time after the start, and it never falls. The comparison therefore holds its value
    from just above the bound on the whole open segment; at the start itself it still holds the
    other value. The segment's field is the limit from the right, so the ledger is evaluated just
    above its bound, as a stock that departs its zero face is. This changes the field only at the
    start and at trial states below the bound, which a nondecreasing ledger cannot reach.
    """
    s, y = system, run.y
    dynamic_names = s.evolving | {'t'}
    candidates = set()
    for a, b in at_switch:
        for coordinate, target_expr in ((a, b), (b, a)):
            if not isinstance(coordinate, nodes.Ref) or coordinate.name not in s.index:
                continue
            if s.expanded_names(target_expr) & dynamic_names:
                continue
            i = s.index[coordinate.name]
            if not s.monotone[i] or y[i] != s.lower[i] or i in run.right_faces:
                continue
            if float(evaluate(target_expr, env, s.units)) == s.lower[i]:
                candidates.add(i)
    if not candidates:
        return set()
    on_bound = field.rates(run.time, y)
    probe = y.copy()
    for i in candidates:
        probe[i] = math.nextafter(s.lower[i], math.inf)
    above = field.rates(run.time, probe)
    return {i for i in candidates if on_bound[i] > 0 and above[i] > 0}


def hidden_excursion(system, run, environment, start, solution, descriptors):
    """Check watched thresholds on the capped grid after integrating the segment."""
    s = system
    if not any(kind == 'event' for kind, _ in descriptors):
        return None
    end_time = float(solution.t[-1])
    grid = np.arange(start + s.max_step, end_time, s.max_step)
    if len(grid) == 0:
        return None
    values = solution.sol(grid)
    env = environment(start, solution.y[:, 0])
    for kind, desc in descriptors:
        if kind != 'event':
            continue
        cond = run.guards[desc]
        if s.expanded_names(cond['value']) & (s.evolving | {'t'}):
            continue
        threshold = float(evaluate(cond['value'], env, s.units))
        i = s.index[cond['var']]
        series = np.concatenate(([solution.y[i, 0]], values[i], [solution.y[i, -1]])) - threshold
        crossed = (
            (series[0] < 0 and np.any(series[1:] >= 0))
            if cond['op'] == '>='
            else (series[0] > 0 and np.any(series[1:] <= 0))
        )
        if crossed and not (solution.t_events and any(len(te) for te in solution.t_events)):
            hits = np.nonzero((series[1:-1] >= 0) if cond['op'] == '>=' else (series[1:-1] <= 0))[0]
            return float(grid[hits[0]]) if len(hits) else float(grid[-1])
    return None


def chattering(system, field, solution, diagnostics, failed=None):
    """The SimulationError of a numerical segment that stalled (`STALLED`), or whose solver failed
    with the message `failed`: the time span of its short steps, and the switching surfaces that
    are at their switch in its last state (within the tolerance of the solver and of the quantities
    that they read), with the quantities that move that they read. Each branch of such a surface
    takes the state back across it, so the steps of the solver get shorter and shorter there."""
    s = system
    first, last = solution.short
    state = solution.y[:, -1]
    side = field.operands(last, state)
    dynamic = s.evolving | {'t'}
    near, read = [], set()
    for a, b in switching_surfaces(s):
        try:
            left, right = side(a), side(b)
        except (ExpressionError, TypeError, ValueError):
            continue
        moving = (s.expanded_names(a) | s.expanded_names(b)) & s.evolving
        slack = max((float(s.atol[s.index[name]]) for name in moving if name in s.index), default=0.0)
        if abs(left - right) <= s.cfg.rtol * (abs(left) + abs(right)) + slack:
            near.append(f'{nodes.notation(a)} against {nodes.notation(b)}')
            read |= (s.expanded_names(a) | s.expanded_names(b)) & dynamic
    where = '; '.join(near) if near else 'a condition of the rates'
    steps = (
        f'the solver failed ({failed})'
        if failed is not None
        else f'the steps of the solver stayed shorter than {s.cfg.crossing:g} h for '
        f'{STALLED_STEPS} steps in a row, from t = {first:g} h'
    )
    message = (
        f'The run stops at t = {last:g} h: {steps}. The rates switch back and forth at {where}: '
        'each branch takes the state back across the switch. '
        'A condition that turns the outflows of a stock off when it is empty does this when they ask '
        'for more than comes in: remove the condition, as the engine gives the outflows of an empty '
        'stock what comes in.'
    )
    item = {
        'severity': 'error',
        'code': 'chattering',
        'from_h': first,
        'at_h': last,
        'surfaces': near,
        'quantities': sorted(read - {'t'}),
    }
    return SimulationError(message, [*diagnostics, item])


def _outside_held_face(system, active, solution):
    """A truncated collocation step can carry its trial field across a later switch.
    Check its accepted prefix against the same physical limits as the published state."""
    if len(solution.t) < 2:
        return False
    step = solution.sol.interpolants[-1]
    end = solution.t[-1]
    if end >= step.t:
        return False
    low, high = state_limits(system)
    rows, levels, directions = [], [], []
    for row, face in active:
        rows.append(row)
        lower = face == 'min'
        directions.append(-1 if lower else 1)
        levels.append(math.nextafter(low[row], -math.inf) if lower else math.nextafter(high[row], math.inf))
    return bool(dense.bound_crossings(step, solution.t[-2], end, rows, levels, directions))


def numerical_segment(system, run, field, context, roots, descriptors, end, repayment_surfaces):
    """Integrate one segment with Radau, up to `end` or its first terminal root.

    Returns the solver solution, the bound targets that it reaches at its end and the watched level
    rules whose root ends it.
    """
    s = system
    time, y, lower = run.time, run.y, s.lower
    # Certified material rows have constant velocity on the current stock
    # face. Their first depletion clock also bounds a numerical segment
    # when unrelated clinical compartments require numerical integration.
    # Keeping the smooth field inside that physical interval prevents a
    # dense interpolation from crossing and recrossing a stock face.
    depletion_crossings = []
    face_rate = field.rates(time, y)
    for name in s.proven_faces:
        i = s.index[name]
        if y[i] > lower[i] and face_rate[i] < 0:
            crossing = s.faces.contact(i, y[i], face_rate[i], time, name)
            if time < crossing <= end:
                depletion_crossings.append((crossing, i))
    if depletion_crossings:
        end = min(end, *(at for at, _ in depletion_crossings))
    depletion_targets = {i: lower[i] for at, i in depletion_crossings if at == end}
    # Rejected solver stages use the current smooth material face. A trial
    # overshoot cannot activate the zero-stock service branch before the
    # certified depletion boundary ends this segment.
    run.right_faces.update(
        s.index[name] for name in s.proven_faces if y[s.index[name]] > lower[s.index[name]]
    )
    start = time
    switches, at_switch = switching_roots(
        s,
        field.operands(time, y),
        repayment_surfaces,
        time,
        y,
        field.branches,
        run.contacted,
        run.contact_clocks,
    )
    run.right_faces.update(departing_ledgers(s, run, field, at_switch, field.environment(time, y)))
    # The certified first-depletion clock already locates these physical
    # faces exactly. A second numerical root search at the same endpoint
    # can disagree with accepted solver values by interpolation roundoff
    # and lose its bracket. Settle those faces conservatively at the clock;
    # every other event, bound and switching surface remains armed.
    if depletion_targets:

        def settled_by_depletion_clock(root):
            return root.target is not None and depletion_targets.get(root.target[0]) == root.target[1]

        retained = [
            (root, descriptor)
            for root, descriptor in zip(roots, descriptors)
            if not settled_by_depletion_clock(root)
        ]
        roots = [root for root, _ in retained]
        descriptors = [descriptor for _, descriptor in retained]
        switches = [root for root in switches if not settled_by_depletion_clock(root)]
    # Every numerical field observes declared physical resolution. An evolving
    # clock state can create the same forcing as literal time. The exact affine
    # and compartment kernels supply structurally proved fast paths.
    context.settings['resolution_policy'] = 'physical_resolution_cap'
    context.settings['actual_max_step_h'] = s.max_step

    def integrate(until=end):
        # Physical resolution complements adaptive error control.
        armed = roots + [
            root._replace(data=tuple(field.expression(node) for node in root.data))
            if root.kind in ('surface', 'band-exit')
            else root
            for root in switches
        ]

        return radau(
            lambda at, state: field.rates(at, state, trial=True),
            (time, until),
            y,
            roots=Roots(s, field.branch_environment, armed, field.values_program) if armed else None,
            leg_rates=field.leg_rates,
            held_comparisons=run.held_comparisons,
            comparison_factor=s.faces.factor,
            check=s.max_step,
            moment=s.cfg.crossing,
            rtol=s.cfg.rtol,
            atol=getattr(s, 'integration_atol', s.atol),
            jac_sparsity=field.jacobian_pattern(),
            max_step=s.solver_step,
        )

    try:
        solution = integrate()
        # The first root can truncate a much longer trial. If its collocation
        # stages crossed the change of regime and polluted an already-held
        # stock, solve up to the located time before posting any leg integrals.
        while run.active_bounds and solution.success and _outside_held_face(s, run.active_bounds, solution):
            solution = integrate(solution.t[-1])
    except ValueError as exc:
        raise SimulationError(
            f'Numerical event location failed at {time:g} h: {exc}', context.diagnostics
        ) from exc
    # A departing root that rounds to the exact start has already been consumed there.
    while solution.success and switches and solution.t[-1] == start:
        fired = {
            k
            for k, hits in enumerate(solution.t_events[len(roots) :])
            if len(hits) and switches[k].start == start
        }
        if not fired:
            break
        switches = [root for k, root in enumerate(switches) if k not in fired]
        solution = integrate()
    if solution.status == STALLED:
        raise chattering(s, field, solution, context.diagnostics)
    if not solution.success:
        # A solver whose steps fall below the spacing of the doubles at a switch chatters too.
        if solution.short is not None:
            stopped = chattering(s, field, solution, context.diagnostics, solution.message)
            if stopped.diagnostics[-1]['surfaces']:
                raise stopped
        raise SimulationError(f'Integrator failed: {solution.message}')
    flagged = hidden_excursion(s, run, field.environment, start, solution, descriptors)
    if flagged is not None:
        raise SimulationError(
            f'A hidden excursion inside one solver step at {flagged:g} h crosses a threshold '
            'and back; declare a shorter physical time scale',
            context.diagnostics,
        )
    reached = float(solution.t[-1])
    context.settings['integration_segments'].append(
        {
            'start_h': start,
            'end_h': reached,
            'max_step_h': s.max_step,
            'resolution_policy': 'physical_resolution_cap',
        }
    )
    armed = roots + switches
    solution.contacts = [(at, armed[k]) for at, k in solution.root_candidates]
    located = {}
    if reached == end:
        located.update(depletion_targets)
    for root, hits in zip(roots + switches, solution.t_events or []):
        if root.target is not None and len(hits) and abs(float(hits[-1]) - reached) <= s.cfg.crossing:
            located[root.target[0]] = root.target[1]
    due = [
        descriptor[1]
        for descriptor, hits in zip(descriptors, solution.t_events or [])
        if descriptor[0] == 'event' and len(hits)
    ]
    return solution, located, due
