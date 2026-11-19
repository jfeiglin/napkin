"""Triggers, resets and gates: the conditions that a run reads at each round, and the moments between
which their answers can change.

**A trigger** belongs to its event on one receiver (`plan.Trigger`) and exists for the whole run,
before the event ever starts. The conditions of each round (`conditions`) read every trigger, reset
and gate on the settled state:

- a trigger that is not armed rearms: with no reset, when its condition is false, or false just
  after now (it is then armed for a later visit, but not at this time); with `reset when C`, when
  C holds; with `reset after D`, once the time that its firing captured has come;
- an armed trigger whose condition holds fires: its captures take their values in written order,
  its body starts its event, it is disarmed, and a `reset after D` captures D;
- a gate (`until C`) releases its occurrence when C holds.

Then the firings act, by receiver and declaration, and the released gates go on, in the order in
which their occurrences were made. A manual start of the event consumes nothing of its trigger. A
draw of a firing (in a capture, in the start's arguments, in `reset after D`) is keyed by the
firing's number (`chance.py`).

**An assertion over state** (spec, "Assertions and their timing"; R-A2-15) must hold after every
round, within the tolerance of what it reads, and just after every moment (`check`): a value that
leaves its asserted interval at a moment fails there. Between moments it is watched as a condition
is, so a contact with its boundary is a moment, just after which it fails; a strict comparison is
watched too, since the first instant at which an assertion fails exists for either form.

**Reading a condition.** A comparison whose sides read what moves between moments (a store of a set,
an actual rate, the time) holds within the tolerance of what it reads (spec: a crossing counts as
reached within the numerical tolerance of the quantity that it reads): `x <= c` holds while
`x - c` is at most that tolerance. A comparison of what holds between moments is exact. A boolean
formula is read through its expression, so its comparisons are read the same way. `and` and `or`
read their terms left to right up to the one that decides, a conditional its selected side, and a
side its names as its evaluation asks for them (`reads.py`): a read with no value on a side that is
not taken (`since(e)` before the first start) fails nothing, and a comparison on such a side has no
contact to predict until it can be read.

**When an answer can change.** What holds between moments changes at the commits and settlings of
the moments, and every condition is read in every round. Between moments, each watched condition
(the condition of every trigger, the reset of a disarmed trigger, the gate of a waiting occurrence,
each assertion over state) gives the first time after now at which one of its comparisons on moving
values can change its answer (`predict`): on lines, where a comparison is affine in what it reads,
the root of a line (of a clock, the time that its other side gives; of one store on its line, its
start plus its distance over its rate: their closed forms; `since(e)` is the time less the newest
start, so it moves as the time does); else,
where the comparison is affine in one store that only rises or only falls through the window
(it only supplies or only receives the flows of its set) against what holds between moments, the
first change of sign along its trajectory, found by sampling and bisection to the crossing
tolerance; any other comparison on a curve has no first contact that the engine can certify, and the
run stops with a diagnostic. `any` and `all` of yes/no values are read through their members'
comparisons; a sum is affine where its members are, and a count, a least or a greatest value of what
moves is not. A keyed read whose key or members move changes by steps that the engine does not
locate: a watched condition that reads one stops the run with a diagnostic. That time is a moment, and so is an event of a way that changes what a
watched condition reads (a rate that jumps). The prediction holds within the window of the ways that
it reads and is made again after it. A strict comparison whose difference moves has no first
instant: the run stops with a diagnostic when such a condition is watched, never polling.

**Near-ties** (change 10). A tiny difference can flip a discrete outcome; the engine does not
compute it more precisely, it marks it. A firing whose condition read a numeric comparison with sides
that differ by no more than the tolerance of what they read (the largest tolerance of the stores and
the rates that they read, through formulas, and the crossing tolerance for the time), now and an
instant later (`AFTER`), was decided within tolerance of its threshold: its trace entry has the
detail `near`, one (origin, comparison, difference, tolerance) for each such comparison on the path
of its answer (`moment.near_ties`), the difference and the tolerance in canonical units. Sides that move
through the boundary, as at a crossing, differ by more an instant later: the firing then follows
from when they cross, and is no near-tie. A stage's guard, an `if` and the guard of a case are marked
the same way in the entry of their commit (`moment.py`), with no instant later: a stage reads its
test once. A gate's release, and a decision that makes no entry (a trigger that does not fire, a
guard that is false), carry no mark.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...program.record import Unavailable
from ..errors import SimulationError
from .family import Family
from .lines import Lines
from .moment import Tx, near_ties
from .plan import FORMULA, LOOKUP, RATE, REDUCE
from .reads import lazily

# The comparisons of `napkin/core/expr`, as functions of the difference of their sides and of the
# tolerance of what they read.
_COMPARE = {
    'le': lambda d, band: d <= band,
    'ge': lambda d, band: d >= -band,
    'lt': lambda d, band: d < -band,
    'gt': lambda d, band: d > band,
    'eq': lambda d, band: abs(d) <= band,
    'ne': lambda d, band: abs(d) > band,
}
_CLOSED = {'le', 'ge', 'eq'}
_SAMPLES = 32  # the points at which a curved difference is read in its window
AFTER = 1e-6  # hours after now at which a condition is read "just after"


@dataclass(eq=False)
class State:
    """A trigger of one receiver in a run: whether it is armed, when it rearms after a `reset after`,
    the time at which a visit cannot fire it, and how often it fired."""

    plan: object
    armed: bool = True
    rearm_at: float | None = None
    blocked_at: float | None = None
    firings: int = 0


class Triggers:
    """The triggers and the watched conditions of one run (see the module)."""

    def __init__(self, run):
        self.run, self.plan = run, run.plan
        self.states = [State(trigger) for trigger in run.plan.triggers]
        self.contacts = []  # (time, watched key, version)
        self.windows = []  # (time, watched key, version): the end of the window of a prediction
        self.version = {}  # watched key -> the version of its prediction
        self.readers = {}  # engine name -> the watched keys that read it

    # ---- reading --------------------------------------------------------------------------------

    def holds(self, node, t=None, band=True):
        """The truth of a condition now (or at time t inside the window of the ways)."""
        return bool(self._truth(node, self.run.now if t is None else t, band))

    def _truth(self, node, t, band):
        plan, run = self.plan, self.run
        if isinstance(node, nodes.Const):
            return node.value
        if isinstance(node, nodes.Ref):
            found = plan.values.get(node.name)
            if found is not None and found.kind == FORMULA and found.boolean and node.name not in run.frozen:
                return self._truth(found.node, t, band)
            return _known(run.value(node.name, t))
        if isinstance(node, nodes.BoolOp):
            if node.op == 'and':
                return all(self._truth(part, t, band) for part in node.values)
            return any(self._truth(part, t, band) for part in node.values)
        if isinstance(node, nodes.Unary) and node.op == 'not':
            return not self._truth(node.operand, t, band)
        if isinstance(node, nodes.IfElse):
            return self._truth(node.body if self._truth(node.test, t, band) else node.orelse, t, band)
        if isinstance(node, nodes.Compare):
            for left, op, right in zip(node.operands, node.ops, node.operands[1:]):
                a, b = self.side(left, t), self.side(right, t)
                if isinstance(a, bool | str) or isinstance(b, bool | str):
                    found = (a == b) if op == 'eq' else (a != b) if op == 'ne' else None
                    if found is None:
                        raise ExpressionError(f'{nodes.text(node)}: only == and != compare these values')
                else:
                    tolerance = self.band(left, right) if band else 0.0
                    found = _COMPARE[op](float(a) - float(b), tolerance)
                if not found:
                    return False
            return True
        return self.side(node, t)

    def side(self, node, t):
        """The value of a side of a comparison at time t, which reads only what its evaluation takes
        (`reads.py`)."""
        return lazily(node, lambda name: self.run.value(name, t), self.plan.units, t)

    def near(self, node, origin, t):
        """The near-ties of a condition that holds at time t (see the module): sides within the
        tolerance of what they read, now and an instant later."""

        def later(left, right):
            # A side that cannot be read an instant later is not shown to move through: it stays marked.
            try:
                a, b = self.side(left, t + AFTER), self.side(right, t + AFTER)
            except (ExpressionError, ArithmeticError, LookupError):
                return 0.0
            return float(a) - float(b)

        return near_ties(
            node,
            origin,
            self.plan,
            self.run.frozen,
            lambda side: self.side(side, t),
            lambda op, difference, left, right: _COMPARE[op](difference, self.band(left, right)),
            self.tolerance,
            later,
        )

    def tolerance(self, *parts):
        """The tolerance of what the sides of a comparison read: the largest of the tolerances of the
        stores and the rates that they read, through formulas, and the crossing tolerance for the
        time; zero for sides that read neither."""
        found = 0.0
        tolerance = self.run.recorder.tolerance
        for part in parts:
            expanded = self.plan.reads_now(self.plan.expansion(part))
            if expanded.time:
                found = max(found, self.plan.numerics.crossing)
            for name in expanded.leaves:
                found = max(found, tolerance.get(name, 0.0))
        return found

    def band(self, *parts):
        """The tolerance of what the sides of a comparison read that moves between moments: the
        largest of their stores' and rates' tolerances, and of the crossing tolerance for the time."""
        found = 0.0
        tolerance = self.run.recorder.tolerance
        for name in self.moving_reads(*parts):
            if name == 't' or name in self.plan.dynamic:
                found = max(found, self.plan.numerics.crossing)
            else:
                found = max(found, tolerance.get(name, 0.0))
        return found

    def moving_reads(self, *parts):
        """The engine names that the nodes read, through formulas, that move between moments: the
        time, the stores of the sets, and the rates of flows."""
        run, plan = self.run, self.plan
        found = set()
        for part in parts:
            expanded = plan.reads_now(plan.expansion(part))
            if expanded.time:
                found.add('t')
            for name in expanded.leaves:
                value = plan.values.get(name)
                if name in run.ways.set_of or (value is not None and value.kind == RATE):
                    found.add(name)
                elif name in run.ways.result_of and run.ways.sets[run.ways.result_of[name]][0].moves:
                    found.add(name)  # a result of a solver whose problem moves between moments
        return found

    # ---- the conditions of a round ------------------------------------------------------------------

    def conditions(self):
        """Read every trigger, reset and gate on the settled state, then act (see the module)."""
        run = self.run
        t = run.now
        fires = []
        for state in self.states:
            trigger = state.plan
            if not state.armed:
                reset = trigger.reset
                if reset is None:
                    if not self.holds(trigger.test):
                        state.armed = True
                    elif not self.holds(trigger.test, t + AFTER, band=False):
                        state.armed, state.blocked_at = True, t
                elif reset[0] == 'when':
                    state.armed = self.holds(reset[1])
                elif state.rearm_at is not None and t >= state.rearm_at:
                    state.armed = True
            if state.armed and state.blocked_at != t and self.holds(trigger.test):
                fires.append(state)
        releases = []
        for live in run.occurrences.waiting():
            step = live.plan.event.steps[live.step]
            if self.holds(run.occurrences.node(step.test, live.plan.scope, step.origin)):
                releases.append(live)
        for state in fires:
            self.fire(state)
        for live in releases:
            if live.waiting:
                run.occurrences.reach(live, live.step + 1)

    def fire(self, state):
        """A firing: the captures in written order, the start of the event, the reset. A draw of the
        firing is keyed by its number (`chance.py`)."""
        run, moment = self.run, self.run.moment
        trigger = state.plan
        run.chance.firing[trigger.key] = state.firings + 1
        for name, node in trigger.captures:
            run.env[name] = run.truth(node)
        tx = Tx(trigger.member, stage=False)
        tx.near = self.near(trigger.test, trigger.origin, run.now)
        moment.execute(trigger.body, tx, trigger.scope)
        state.armed, state.firings = False, state.firings + 1
        if trigger.reset is not None and trigger.reset[0] == 'after':
            duration = run.truth(trigger.reset[1])
            if isinstance(duration, bool) or not isinstance(duration, int | float) or duration < 0:
                raise SimulationError(f'{trigger.origin}: reset after {duration!r}, which is no duration')
            state.rearm_at = run.now + float(duration)
        del run.chance.firing[trigger.key]
        run.recorder.entry(run.now, 'fire', trigger.origin, trigger.member, **tx.details())
        moment.again = True
        moment.commit(tx)

    def check(self, after=False):
        """The assertions over state on the settled state (spec, "Assertions and their timing"):
        after a round, each must hold within the tolerance of what it reads; just after a moment,
        each must hold an instant later (as a trigger is read just after, with no band), so a value
        that leaves its asserted interval at a moment fails there."""
        t = self.run.now
        for origin, member, node in self.plan.checks:
            if after:
                holds, when = self.holds(node, t + AFTER, band=False), f'just after t = {t:g} h'
            else:
                holds, when = self.holds(node), f'at t = {t:g} h'
            if not holds:
                owner = f' for {member}' if member else ''
                raise SimulationError(f'{origin}: the assertion does not hold{owner} {when}')

    def next_timer(self):
        """The earliest time after now at which a disarmed trigger rearms, or None."""
        found = [
            state.rearm_at
            for state in self.states
            if not state.armed and state.rearm_at is not None and state.rearm_at > self.run.now
        ]
        return min(found, default=None)

    # ---- watching -------------------------------------------------------------------------------------

    def watched(self):
        """Each watched condition: (key, node)."""
        run = self.run
        found = []
        for index, state in enumerate(self.states):
            found.append((('when', index), state.plan.test))
            if not state.armed and state.plan.reset is not None and state.plan.reset[0] == 'when':
                found.append((('reset', index), state.plan.reset[1]))
        for live in run.occurrences.waiting():
            step = live.plan.event.steps[live.step]
            found.append((('gate', live.id), run.occurrences.node(step.test, live.plan.scope, step.origin)))
        for index, (_, _, node) in enumerate(self.plan.checks):
            found.append((('assert', index), node))
        return found

    def reads_any(self, names):
        """Whether a watched condition reads any of `names`."""
        return any(name in self.readers for name in names)

    def predict_all(self):
        """The next contact of every watched condition, from now."""
        self.contacts, self.windows, self.version, self.readers = [], [], {}, {}
        for key, node in self.watched():
            self._watch(key, node)

    def predict(self, names):
        """The next contact again of the watched conditions that read `names`, and of those whose
        window has ended."""
        keys = {key for name in names for key in self.readers.get(name, ())}
        windows, now = self.windows, self.run.now
        while windows and windows[0][0] <= now:
            _, key, version = heapq.heappop(windows)
            if self.version.get(key) == version:
                keys.add(key)
        if keys:
            for key, node in self.watched():
                if key in keys:
                    self._watch(key, node)

    def next_contact(self):
        """The time of the earliest predicted contact, or inf."""
        contacts = self.contacts
        while contacts and contacts[0][2] != self.version.get(contacts[0][1]):
            heapq.heappop(contacts)
        return contacts[0][0] if contacts else math.inf

    def _watch(self, key, node):
        version = self.version[key] = self.version.get(key, 0) + 1
        reads = self.plan.reads_now(self.plan.expansion(node))
        for name in set(reads.leaves) | set(reads.formulas):
            self.readers.setdefault(name, set()).add(key)
        at, until = self._next(node, strict=key[0] != 'assert')
        if math.isfinite(at):
            heapq.heappush(self.contacts, (at, key, version))
        elif math.isfinite(until):
            heapq.heappush(self.windows, (until, key, version))

    def _atoms(self, node, positive=True):
        """The comparisons of a condition, through its boolean formulas, each with its polarity
        (whether `not` turns it over)."""
        found = self.plan.values
        if isinstance(node, nodes.Ref):
            value = found.get(node.name)
            if (
                value is not None
                and value.kind == FORMULA
                and value.boolean
                and node.name not in self.run.frozen
            ):
                return self._atoms(value.node, positive)
            if value is not None and value.kind == REDUCE and value.boolean:
                # `any` or `all` of yes/no values changes only where one of its members does.
                reduction = self.plan.reductions[node.name]
                atoms = []
                for k in self.run.kept_of(node.name) if reduction.names else ():
                    atoms += self._atoms(nodes.ref(reduction.names[k]), positive)
                return atoms
            return []
        if isinstance(node, nodes.Unary) and node.op == 'not':
            return self._atoms(node.operand, not positive)
        if isinstance(node, nodes.Compare):
            return [
                (left, op, right, positive)
                for left, op, right in zip(node.operands, node.ops, node.operands[1:])
            ]
        atoms = []
        for child in node.children:
            atoms += self._atoms(child, positive)
        return atoms

    def _next(self, node, strict=True):
        """The first time after now at which a comparison of the condition on moving values can change
        its answer (inf for none), and the end of the window in which that holds. A strict threshold
        on a moving value has no first instant at which it holds (`strict`); an assertion fails at the
        first instant at which it does not, which either form has."""
        run = self.run
        now, earliest, window = run.now, math.inf, math.inf
        stepping = self._moving_lookups(node)
        if stepping:
            raise SimulationError(
                f'the first contact of {nodes.text(node)} cannot be certified: it reads {stepping[0]}, a '
                'keyed read whose key or members move between moments, which changes by steps that the '
                'engine does not locate; compare what it is keyed by with the keys, or use an inspection '
                'schedule'
            )
        for left, op, right, positive in self._atoms(node):
            moving = self.moving_reads(left, right)
            if not moving:
                continue
            until = self._window(moving)
            window = min(window, until)
            if until <= now:
                continue
            try:
                start = self.side(left, now) - self.side(right, now)
                end = self.side(left, until) - self.side(right, until)
            except (TypeError, ValueError):
                continue  # sides that are no numbers
            linear = (
                self._linear(moving)
                and _affine(left, moving, self.plan)
                and _affine(right, moving, self.plan)
            )
            if linear and start == end:
                continue
            if strict and (op in _CLOSED) != positive:
                raise SimulationError(
                    f'a strict threshold on a value that changes continuously: '
                    f'{nodes.text(left)} {_SPELLING[op]} {nodes.text(right)} has no first instant; use an '
                    'inclusive threshold'
                )
            if linear:
                # A comparison on its boundary now changes its answer just after now, which this
                # moment reads (`holds` just after); else the root of its line, however near.
                root = self._exact_root(left, right, moving, now)
                if root is None:
                    root = now + start / (start - end) * (until - now)
                if abs(start) > self.band(left, right) and now < root <= until:
                    earliest = min(earliest, root)
                continue
            if not self._certified(left, right, moving):
                raise SimulationError(
                    f'the first contact of {nodes.text(left)} {_SPELLING[op]} {nodes.text(right)} cannot be '
                    'certified: it reads a value that moves on a curve and does not compare one store '
                    'that only rises or only falls with what holds between moments; use such a '
                    'threshold or an inspection schedule'
                )
            root = self._search(left, right, now, until, self.band(left, right))
            if root is not None:
                earliest = min(earliest, root)
        return earliest, window

    def _exact_root(self, left, right, moving, now):
        """The root of a clock (`t` against what holds between moments), which is the time that the
        other side gives, or of one store on its line against what holds, which is the line's start
        plus its distance over its rate; None for any other comparison."""
        ways = self.run.ways
        for side, other in ((left, right), (right, left)):
            if not isinstance(side, nodes.Ref) or moving != {side.name}:
                continue
            if side.name == 't':
                return float(self.side(other, now))
            line = ways.linear(side.name) if side.name in ways.set_of else None
            if line is not None and line[1] != 0:
                value, slope, since = line
                return since + (float(self.side(other, now)) - value) / slope
        return None

    def _moving_lookups(self, *parts):
        """The keyed reads that the nodes read, through formulas, that move between moments."""
        plan, ways = self.plan, self.run.ways
        found = set()
        for part in parts:
            leaves = plan.reads_now(plan.expansion(part)).leaves | plan.expansion(part).stepped
            found |= {leaf for leaf in leaves if leaf in plan.keyed and plan.lookup_moves(leaf, ways.set_of)}
        return sorted(found)

    def _certified(self, left, right, moving):
        """Whether the first contact of a comparison on a curve is certain to be found: one side is
        affine in a single store that only rises or only falls through the window, the other holds
        between moments, so the difference changes its sign once at most."""
        plan, ways = self.plan, self.run.ways
        if len(moving) != 1:
            return False
        (store,) = moving
        if store not in ways.set_of:
            return False
        sides = [part for part in (left, right) if store in _reads(part, plan)]
        return len(sides) == 1 and _affine(sides[0], moving, plan) and ways.monotone(store)

    def _window(self, moving):
        """The time until which the trajectories of the moving reads hold: the next moment that the
        run knows, or the next event of an instance that holds one of them."""
        run, ways = self.run, self.run.ways
        until = run.limit
        for name in moving:
            if name == 't':
                continue
            store = name if name in ways.set_of else name.rsplit('.', 1)[0]
            instance = ways.instance_of(store)
            if instance is not None:
                until = min(until, instance.peek())
        return until

    def _linear(self, moving):
        """Whether each moving read is a line through the window: the time, a store on a line, or a
        rate of the family or of the lines, which holds between their events."""
        ways = self.run.ways
        for name in moving:
            if name == 't':
                continue
            if name in ways.set_of:
                if ways.linear(name) is None:
                    return False
                continue
            instance = ways.instance_of(name.rsplit('.', 1)[0])
            if instance is not None and not (
                isinstance(instance, Family | Lines) or getattr(instance, 'lines', False)
            ):
                return False
        return True

    def _search(self, left, right, now, until, band):
        """The first change of sign of a curved difference in (now, until]: sampled, then bisected to
        the crossing tolerance; None when none is found."""
        crossing = self.plan.numerics.crossing

        def sign(t):
            d = float(self.side(left, t)) - float(self.side(right, t))
            return 0 if abs(d) <= band else (1 if d > 0 else -1)

        times = [now + (until - now) * k / _SAMPLES for k in range(1, _SAMPLES + 1)]
        first = sign(now)
        if first == 0:
            first = sign(times[0])
        before = now
        for at in times:
            if sign(at) != first:
                low, high = before, at
                while high - low > crossing:
                    middle = 0.5 * (low + high)
                    if sign(middle) == first:
                        low = middle
                    else:
                        high = middle
                return high if high > now else None
            before = at
        return None


_SPELLING = {'le': '<=', 'ge': '>=', 'lt': '<', 'gt': '>', 'eq': '==', 'ne': '!='}


def _affine(node, moving, plan):
    """Whether a node is affine in the moving names that it reads, through formulas."""
    if isinstance(node, nodes.Const):
        return True
    if isinstance(node, nodes.Ref):
        value = plan.values.get(node.name)
        if value is not None and value.kind == LOOKUP:
            # A keyed read is a step in what it reads: affine only where nothing that it reads moves.
            return not (_reads(node, plan) & (moving | {'t'}))
        if value is not None and value.kind == REDUCE:
            # A sum of affine values is affine; a count, a least or a greatest value steps or bends.
            reduction = plan.reductions[node.name]
            if reduction.op == 'sum' and reduction.names is not None:
                return all(_affine(nodes.ref(name), moving, plan) for name in reduction.names)
            return not (_reads(node, plan) & (moving | {'t'}))
        if node.name in moving or node.name == 't' or value is None or value.kind != FORMULA:
            return True
        return _affine(value.node, moving, plan)
    if isinstance(node, nodes.Unary) and node.op in ('neg', 'pos'):
        return _affine(node.operand, moving, plan)
    if isinstance(node, nodes.Binary):
        if node.op in ('add', 'sub'):
            return _affine(node.left, moving, plan) and _affine(node.right, moving, plan)
        still = [not (_reads(part, plan) & (moving | {'t'})) for part in (node.left, node.right)]
        if node.op == 'mul':
            return (still[0] or still[1]) and all(
                _affine(part, moving, plan) for part in (node.left, node.right)
            )
        if node.op == 'div':
            return still[1] and _affine(node.left, moving, plan)
    return not (_reads(node, plan) & (moving | {'t'}))


def _reads(node, plan):
    """The names that a node reads, through formulas, with the time."""
    expanded = plan.expansion(node)
    return set(expanded.leaves) | ({'t'} if expanded.time else set())


def _known(value):
    """A value that a condition can read: an `Unavailable` one raises its reason (D7)."""
    if isinstance(value, Unavailable):
        raise ExpressionError(value.reason)
    return value
