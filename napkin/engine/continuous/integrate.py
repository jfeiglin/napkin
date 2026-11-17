"""Roots that end a segment, and the numerical (Radau) segment."""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
from scipy.integrate import OdeSolution, Radau
from scipy.optimize import OptimizeResult, brentq

from ...core import expr as nodes
from ...expressions import ExpressionError, compile_program, evaluate, names_in
from ...model import structure as typed
from ...model.ir import EVENT_TIME_TOLERANCE_H
from ..errors import SimulationError
from ..solvers import radau_rate

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

    kind: str  # 'guard', 'release', 'bound', 'repayment' or 'surface'
    direction: int
    data: tuple
    target: tuple | None = None


def root_value(system, environment, root, at, state):
    """The value of one root at a time and state.

    - guard (i, value, offset): the quantity of a crossing rule less its value, plus the offset. A
      crossing of a quantity that only rises or only falls (`proven_monotone_crossings`) is watched half
      a tolerance before its value, inside the band where the rule holds: such a quantity can approach
      its value without reaching it (a stock that drains in proportion to itself), and the rule holds
      from where it comes within its tolerance.
    - release (i, limit, sign): the distance from the bound that the quantity rests on, less twice
      its tolerance.
    - bound (i, limit, start): the distance to a finite bound, less half a tolerance. The surface lies
      half a tolerance beyond the limit: interpolation noise below that cannot bracket it, and the
      located crossing stays inside the balanced roundoff that the boundary correction books. At the
      start of the segment, a quantity within its tolerance of the bound has just left it, and is on
      the side that it left to: the segment does not stop at its start.
    - repayment (cash, debt, floor): the cash less the debt and the floor.
    - surface (a, b): one side of a switching surface less the other.
    """
    s = system
    kind, direction, data, _ = root
    if kind == 'guard':
        i, value, offset = data
        return state[i] - float(evaluate(value, environment(at, state), s.units)) + offset
    if kind == 'release':
        i, limit, sign = data
        return sign * (state[i] - limit) - 2 * s.atol[i]
    if kind == 'bound':
        i, limit, start = data
        val = state[i] - limit
        if at == start and abs(val) <= s.atol[i]:
            return -direction * s.atol[i]
        return val - direction * 0.5 * s.atol[i]
    if kind == 'repayment':
        cash, debt, floor = data
        return state[cash] - state[debt] - floor
    a, b = data
    env = environment(at, state)
    return float(evaluate(a, env, s.units)) - float(evaluate(b, env, s.units))


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
        self.bound_half = self.bound_directions * 0.5 * self.bound_atol
        self.bound_start_value = -self.bound_directions * self.bound_atol
        self.cash_rows, self.debt_rows = column('repayment', 0, int), column('repayment', 1, int)
        self.floors = column('repayment', 2)
        # The expressions that the program computes: the value of each crossing rule, then both sides
        # of each switching surface.
        sources = [roots[k].data[1] for k in kinds.get('guard', [])]
        sources += [side for k in kinds.get('surface', []) for side in roots[k].data]
        index = {source: n for n, source in enumerate(dict.fromkeys(sources))}
        self.guard_values = np.array([index[roots[k].data[1]] for k in kinds.get('guard', [])], dtype=int)
        self.left = np.array([index[roots[k].data[0]] for k in kinds.get('surface', [])], dtype=int)
        self.right = np.array([index[roots[k].data[1]] for k in kinds.get('surface', [])], dtype=int)
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
                out[kinds['surface']] = computed[self.left] - computed[self.right]
        if 'release' in kinds:
            out[kinds['release']] = (
                self.release_signs * (state[self.release_rows] - self.release_limits) - self.release_twice
            )
        if 'bound' in kinds:
            val = state[self.bound_rows] - self.bound_limits
            on_start = (at == self.bound_starts) & (np.abs(val) <= self.bound_atol)
            out[kinds['bound']] = np.where(on_start, self.bound_start_value, val - self.bound_half)
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


def locate(roots, k, solution, t_old, t, before, after):
    """The time of root k between two accepted steps: Brent's method on the dense solution, as
    `solve_event_equation` in scipy.integrate._ivp.ivp. At the two accepted times it takes the root's
    values at the accepted states: the dense solution there can differ from them by roundoff, and
    lose the bracket that they made."""

    def f(at):
        if at == t_old:
            return before
        if at == t:
            return after
        return roots.value(k, at, solution(at))

    return brentq(f, t_old, t, xtol=ROOT_TOLERANCE, rtol=ROOT_TOLERANCE)


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
# time between two moments that the engine tells apart (`EVENT_TIME_TOLERANCE_H`): it has then
# moved less than 1e-5 h in that many steps. This is what a rate that switches back and forth at a
# condition makes the solver do (`Limit.accepted`).
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

    It also counts the accepted steps in a row that are shorter than `EVENT_TIME_TOLERANCE_H`
    (`accepted`): after `STALLED_STEPS` of them, the segment is stalled."""

    def __init__(self, check, ceiling):
        self.check, self.ceiling, self.allowed = check, ceiling, ceiling
        self.wait, self.after = 0, 1
        # The accepted steps in a row that are shorter than the event time tolerance, and the time
        # at which the first of them started.
        self.brief, self.brief_from = 0, None

    def accepted(self, start, end):
        """The solver accepted a step from `start` to `end`. True when the segment is stalled: this
        step and the `STALLED_STEPS - 1` accepted steps before it are each shorter than
        `EVENT_TIME_TOLERANCE_H`. A step that is not used does not change the count; a longer step
        starts it again."""
        if end - start < EVENT_TIME_TOLERANCE_H:
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


def radau(fun, interval, initial, roots=None, check=None, **options):
    """`solve_ivp(fun, interval, initial, method='Radau', dense_output=True, events=...)` for roots
    that each end the integration.

    `roots` (a `Roots`) gives the values of all its roots together (`values`), and the value of one
    root to locate its crossing (`locate`). The first root in time ends the integration. `options`
    go to the Radau solver.

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
    - at each check time, the roots are read. A root that changes sign between two check times, or
      between a check time and an end of the step, is located between those two times.
    """
    t0, tf = map(float, interval)
    solver = Radau(fun, t0, initial, tf, vectorized=False, **options)
    ts, ys, interpolants = [t0], [initial], []
    if roots is not None:
        g = roots.values(t0, initial)
        t_events, y_events = [[] for _ in range(len(g))], [[] for _ in range(len(g))]
    else:
        g = None
        t_events = y_events = None
    status = None
    half = None if check is None else check / 2
    halves = 0  # the halves of a check interval before the step, from the start
    # The longest step that the differences of the steps before allow the solver now.
    limit = None if check is None else Limit(check, solver.max_step)
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
                    active = active_roots(g_before, g_at, roots.direction)
                    if active.size > 0:
                        found = [locate(roots, k, sol, before, at, g_before[k], g_at[k]) for k in active]
                        first = int(np.argmin(found))
                        ended = (found[first], int(active[first]))
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
                active = active_roots(g_before, g_new, roots.direction)
                if active.size > 0:
                    found = np.asarray(
                        [locate(roots, k, sol, before, t, g_before[k], g_new[k]) for k in active]
                    )
                    first = int(np.argmin(found))
                    ended = (float(found[first]), int(active[first]))
                g = g_new
            if ended is not None:
                te, k = ended
                t_events[k].append(te)
                y_events[k].append(sol(te))
                status = 1
                t = te
                y = sol(t)
        elif roots is not None:
            g_new = roots.values(t, y)
            active = active_roots(g, g_new, roots.direction)
            if active.size > 0:
                found = np.asarray([locate(roots, k, sol, t_old, t, g[k], g_new[k]) for k in active])
                order = np.argsort(found) if t > t_old else np.argsort(-found)
                k, te = active[order][0], found[order][0]
                t_events[k].append(te)
                y_events[k].append(sol(te))
                status = 1
                t = te
                y = sol(t)
            g = g_new
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


def release_root(system, i, bound):
    """The root at which a quantity resting on a bound leaves it by twice its tolerance."""
    limit = system.lower[i] if bound == 'min' else system.upper[i]
    return Root('release', 1, (i, limit, 1 if bound == 'min' else -1))


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
        roots.append(release_root(s, i, bound))
        descriptors.append(('release', (i, bound)))
    start = run.time
    for i in range(len(run.y)):
        for bound, limit, direction in (('min', s.lower[i], -1), ('max', s.upper[i], 1)):
            if not math.isfinite(limit) or (i, bound) in run.active_bounds:
                continue
            if bound == 'min' and s.monotone[i] and run.y[i] >= limit:
                continue  # a nondecreasing state cannot fall to its lower bound
            target = (i, limit) if bound == 'min' else None
            roots.append(Root('bound', direction, (i, limit, start), target))
            descriptors.append(('bound', (i, bound)))
    return roots, descriptors


def switching_surfaces(system):
    """Every min/max/clip/abs argument pair and every state-dependent condition in the rate
    expressions, in their first order: the switching surfaces of the run (`switching_roots`).

    They read only the run's expressions and the quantities that move, so a run finds them once.
    """
    s = system
    if 'switching' in s.analysis:
        return s.analysis['switching']
    computed = s.computed
    dynamic_names = s.evolving | {'t'}
    sources, seen, pending = [], set(), [f.rate for f in s.flows.values()]
    pending += [d.expr for d in s.resolved.rates.values()] + [g.capacity for g in s.groups.values()]
    while pending:
        expr = typed.node(pending.pop())
        if expr in seen:
            continue
        seen.add(expr)
        sources.append(expr)
        pending += [computed[n]['expr'] for n in names_in(expr) if n in computed]
    surfaces = {}
    for expr in sources:
        for node in nodes.breadth_first(expr):
            pairs = []
            if isinstance(node, nodes.Call):
                args = list(node.args)
                if node.function in ('min', 'max') and len(args) > 1:
                    pairs = [(a, b) for k, a in enumerate(args) for b in args[k + 1 :]]
                elif node.function == 'clip' and len(args) == 3:
                    pairs = [(args[0], args[1]), (args[0], args[2])]
                elif node.function == 'abs' and len(args) == 1:
                    pairs = [(args[0], ZERO)]
            elif isinstance(node, nodes.Compare):
                pairs = [
                    (left, right)
                    for left, op, right in zip(node.operands, node.ops, node.operands[1:])
                    if op not in ('eq', 'ne')
                ]
            for a, b in pairs:
                if (s.expanded_names(a) | s.expanded_names(b)) & dynamic_names:
                    surfaces[(a, b)] = None
    s.analysis['switching'] = tuple(surfaces)
    return s.analysis['switching']


def switching_roots(system, environment, repayment_surfaces, at, state):
    """End numerical segments where a piecewise rate changes branch.

    Every switching surface of the run (`switching_surfaces`) splits two smooth regimes;
    integrating across one mixes them in a single step, so each surface that is not
    already at its switch at the segment start becomes a terminal root.
    Returns the roots and the surfaces already at their switch.
    """
    s = system
    units, index = s.units, s.index
    env = environment(at, state)
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
            left, right = float(evaluate(a, env, units)), float(evaluate(b, env, units))
        except (ExpressionError, TypeError, ValueError):
            continue  # an untaken branch outside its domain is not a live surface
        gap = left - right
        # A surface already at its switch, to solver tolerance, is not armed.
        if not math.isfinite(gap) or abs(gap) <= s.cfg.rtol * (abs(left) + abs(right)):
            if math.isfinite(gap):
                at_switch.append((a, b))
            continue
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
            value = float(evaluate(target_expr, env, units))
            if value == s.lower[i]:
                target = (i, value)
        roots.append(Root('surface', 0, (a, b), target))
    return roots, at_switch


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
    """Audit the dense solution on the capped grid for a bound or threshold crossed and recrossed inside a step."""
    s = system
    end_time = float(solution.t[-1])
    grid = np.arange(start + s.max_step, end_time, s.max_step)
    if len(grid) == 0:
        return None
    values = solution.sol(grid)
    low = np.where(s.monotone, -np.inf, s.lower)[:, None] - s.atol[:, None]
    high = s.upper[:, None] + s.atol[:, None]
    outside = np.any((values < low) | (values > high), axis=0)
    if np.any(outside):
        return float(grid[np.argmax(outside)])
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
    env = field.environment(last, state)
    dynamic = s.evolving | {'t'}
    near, read = [], set()
    for a, b in switching_surfaces(s):
        try:
            left, right = float(evaluate(a, env, s.units)), float(evaluate(b, env, s.units))
        except (ExpressionError, TypeError, ValueError):
            continue
        moving = (s.expanded_names(a) | s.expanded_names(b)) & s.evolving
        slack = max((float(s.atol[s.index[name]]) for name in moving if name in s.index), default=0.0)
        if abs(left - right) <= s.cfg.rtol * (abs(left) + abs(right)) + slack:
            near.append(f'{nodes.text(a)} against {nodes.text(b)}')
            read |= (s.expanded_names(a) | s.expanded_names(b)) & dynamic
    where = '; '.join(near) if near else 'a condition of the rates'
    steps = (
        f'the solver failed ({failed})'
        if failed is not None
        else f'the steps of the solver stayed shorter than {EVENT_TIME_TOLERANCE_H:g} h for '
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


def numerical_segment(system, run, field, trajectory, roots, descriptors, end, repayment_surfaces):
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
            crossing = time + (lower[i] - y[i]) / face_rate[i]
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
    switches, at_switch = switching_roots(s, field.environment, repayment_surfaces, time, y)
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
    trajectory.settings['resolution_policy'] = 'physical_resolution_cap'
    trajectory.settings['actual_max_step_h'] = s.max_step

    def integrate():
        # Physical resolution complements adaptive error control.
        armed = roots + switches
        return radau(
            field.rates,
            (time, end),
            y,
            roots=Roots(s, field.environment, armed, field.values_program) if armed else None,
            check=s.max_step,
            rtol=s.cfg.rtol,
            atol=s.atol,
            jac_sparsity=field.jacobian_pattern(),
            max_step=s.solver_step,
        )

    try:
        solution = integrate()
    except ValueError as exc:
        raise SimulationError(
            f'Numerical event location failed at {time:g} h: {exc}', trajectory.diagnostics
        ) from exc
    # A switching surface that fires within the event tolerance of the start is
    # already at its switch; it is disarmed for this segment only.
    while solution.success and switches and solution.t[-1] - start <= EVENT_TIME_TOLERANCE_H:
        fired = {k - len(roots) for k, te in enumerate(solution.t_events) if len(te) and k >= len(roots)}
        if not fired:
            break
        switches = [root for k, root in enumerate(switches) if k not in fired]
        solution = integrate()
    if solution.status == STALLED:
        raise chattering(s, field, solution, trajectory.diagnostics)
    if not solution.success:
        # A solver whose steps fall below the spacing of the doubles at a switch chatters too.
        if solution.short is not None:
            stopped = chattering(s, field, solution, trajectory.diagnostics, solution.message)
            if stopped.diagnostics[-1]['surfaces']:
                raise stopped
        raise SimulationError(f'Integrator failed: {solution.message}')
    flagged = hidden_excursion(s, run, field.environment, start, solution, descriptors)
    if flagged is not None:
        raise SimulationError(
            f'A hidden excursion inside one solver step at {flagged:g} h crosses a bound or threshold '
            'and back; declare a shorter physical time scale',
            trajectory.diagnostics,
        )
    reached = float(solution.t[-1])
    trajectory.settings['integration_segments'].append(
        {
            'start_h': start,
            'end_h': reached,
            'max_step_h': s.max_step,
            'resolution_policy': 'physical_resolution_cap',
        }
    )
    located = {}
    if reached == end:
        located.update(depletion_targets)
    for root, hits in zip(roots + switches, solution.t_events or []):
        if root.target is not None and len(hits) and abs(float(hits[-1]) - reached) <= EVENT_TIME_TOLERANCE_H:
            located[root.target[0]] = root.target[1]
    due = [
        descriptor[1]
        for descriptor, hits in zip(descriptors, solution.t_events or [])
        if descriptor[0] == 'event' and len(hits)
    ]
    return solution, located, due
