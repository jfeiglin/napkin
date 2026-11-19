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
values can change its answer (`predict`). Where a comparison is affine in what it reads and each
read is a line (the time; a store on its line; a rate of the family or of the lines, which holds
between their events), that is the root of its line: of a comparison whose only moving read is the
time (`t`, `since(e)`, the time less the newest start, or `elapsed(x)`), the time at which it
changes in exact arithmetic, as the clock builds a time (`moment.Clock`); of one store on its line,
its start plus its distance over its rate (their closed forms). So a condition on sets whose rates
hold between moments is exact.

**Values that turn** (PLAN, change 20). Where a read moves on a curve, the comparison is certified
step by step (`_contact`). Its difference d, the left side less the right, is a sum of what moves
with weights that hold between moments (`_weights`, which reads the still parts now), and its
answer, read within its band b, can change only where d crosses -b (for `>=`, `<`, `==`, `!=`) or b
(for `<=`, `>`, `==`, `!=`). The window is cut at the ends of the steps of the sets that it reads
(`breaks`), and each piece is read from the form of their solutions (`motion`,
`continuous/dense.py`: the cubic of a step of Radau's dense output, the closed form of compartments,
or a line). The form gives the rate of d at the start of the piece, how far that rate can move over
the piece, and the most that d can move over it (the bound on its rate over the piece, integrated
over the piece), so:

- an edge farther from d than the most that d can move over the piece, with the margins of what the
  run reads and of roundoff, is not reached there: d at the start of the piece is the form's sum
  and the parts that hold, read once at now, so a far piece costs no read;
- where the rate of d keeps its sign over the piece, its ends decide, and a crossing is found by
  bisection on the dense output to the crossing tolerance;
- elsewhere d may turn near an edge: the piece is halved, and each half is read again from the same
  output (no step of the integrator, no evaluation of a rate), until each piece is certain or
  shorter than the crossing tolerance, whose end then decides.

So an excursion inside one step is found, though the step's ends do not show it. A value that comes
within b of its threshold without crossing it enters the band, and the moment there reads the
condition within tolerance: a trigger fires there marked as a near-tie (below), or misses within
tolerance. The run stops with a diagnostic that names what it cannot certify: a side that is no such
sum (a product of moving values, a branch on one), a rate of a set that moves, a store of a set
whose way gives no form (a declared solver whose problem moves: unless it alone is read and only
rises or only falls, when the ends of the window decide), and a value that stays within roundoff of
an edge for more than `_HALVINGS` halvings of one step. `any` and `all` of yes/no values are read
through their members' comparisons; a sum is affine where its members are, and a count, a least or
a greatest value of what moves is not. A keyed read whose key or members move changes by steps that
the engine does not locate: a watched condition that reads one stops the run with a diagnostic.

That time is a moment, and so is an event of a way that changes what a watched condition reads (a
rate that jumps). The prediction holds within the window of the ways that it reads and is made again
after it. A strict comparison whose difference moves has no first instant: the run stops with a
diagnostic when such a condition is watched, never polling.

**Near-ties** (change 10). A tiny difference can flip a discrete outcome; the engine does not
compute it more precisely, it marks it. A condition whose answer was decided by a numeric comparison
with sides that differ by no more than the tolerance of what they read (the largest tolerance of the
stores and the rates that they read, through formulas, and the crossing tolerance for the time), now
and an instant later (`AFTER`), was decided within tolerance of its threshold: its trace entry has the
detail `near`, one (origin, comparison, difference, tolerance) for each such comparison that decides
its answer (`moment.near_ties`), the difference and the tolerance in canonical units. Sides that move
through the boundary, as at a crossing, differ by more an instant later: the answer then follows from
when they cross, and is no near-tie. So are marked:

- a firing, in its entry `fire`;
- an armed trigger whose condition is false, in an entry `miss` ("came within tolerance of its
  threshold and did not fire"). A trigger is read in every round, so a near-tie that holds from
  moment to moment would repeat: a `miss` is written when its near-ties differ from those of the
  trigger's last `miss` since it last fired. That memory is what the trace says (`_missed`), so a
  run restored from a checkpoint has it too. A comparison whose sides differ by more than the widest
  tolerance of the run has no near-tie, so a condition far from its threshold costs no more;
- a gate's release, in an entry `release` of the occurrence at the gate.

A stage's guard, an `if` and the guard of a case are marked the same way in the entry of their commit,
and a false guard in an entry `skip` of the stage that ran nothing (`moment.py`), with no instant
later: a stage reads its test once. A gate that stays shut is read again in every round, and is not
marked.
"""

from __future__ import annotations

import heapq
import math
import sys
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...program.record import Unavailable
from ..continuous import dense
from ..continuous.dense import Motion
from ..errors import SimulationError
from .family import Family
from .lines import Lines
from .moment import Tx, near_ties
from .plan import FORMULA, LOOKUP, RATE, REDUCE, walked
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
# The edges of the band at which the answer of each comparison can change: `low` where the difference
# crosses -band (the answer of `d >= -band`), `high` where it crosses band (of `d <= band`).
_EDGES = {
    'ge': ('low',),
    'lt': ('low',),
    'le': ('high',),
    'gt': ('high',),
    'eq': ('low', 'high'),
    'ne': ('low', 'high'),
}
_ROUNDOFF = 64 * sys.float_info.epsilon  # the roundoff of a difference, relative to its terms
_HALVINGS = 4096  # the most halvings of one step that the prediction of a comparison reads
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
        # (origin, member) of a trigger -> the near-ties of its last `miss` since it last fired, made
        # from the trace when first needed, so that a restored run has it as the trace gives it.
        self.missed = None
        self._widest = (-1, 0.0)  # (the count of the record's tolerances, the largest of them)

    # ---- reading --------------------------------------------------------------------------------

    def holds(self, node, t=None, band=True):
        """The truth of a condition now (or at time t inside the window of the ways)."""
        return bool(self._truth(node, self.run.now if t is None else t, band))

    def _truth(self, node, t, band, close=None):
        """The truth of a condition at time t; a comparison read on the way whose sides differ by no
        more than the widest tolerance of the run is added to `close`, when it is given, so that a
        condition with none has no near-tie to look for. It is read through boolean formulas with no
        recursion (`plan.walked`)."""
        return walked(self._truth_of(node, t, band, close))

    def _truth_of(self, node, t, band, close):
        """The computation of `_truth`: each part through a boolean formula is one that it yields."""
        plan, run = self.plan, self.run
        if isinstance(node, nodes.Const):
            return node.value
        if isinstance(node, nodes.Ref):
            found = plan.values.get(node.name)
            if found is not None and found.kind == FORMULA and found.boolean and node.name not in run.frozen:
                return (yield self._truth_of(found.node, t, band, close))
            return _known(run.value(node.name, t))
        if isinstance(node, nodes.BoolOp):
            decides = node.op == 'or'  # the answer of a term that decides the whole
            for part in node.values:
                if bool((yield self._truth_of(part, t, band, close))) == decides:
                    return decides
            return not decides
        if isinstance(node, nodes.Unary) and node.op == 'not':
            return not (yield self._truth_of(node.operand, t, band, close))
        if isinstance(node, nodes.IfElse):
            test = yield self._truth_of(node.test, t, band, close)
            return (yield self._truth_of(node.body if test else node.orelse, t, band, close))
        if isinstance(node, nodes.Compare):
            for left, op, right in zip(node.operands, node.ops, node.operands[1:]):
                a, b = self.side(left, t), self.side(right, t)
                if isinstance(a, bool | str) or isinstance(b, bool | str):
                    found = (a == b) if op == 'eq' else (a != b) if op == 'ne' else None
                    if found is None:
                        raise ExpressionError(f'{nodes.text(node)}: only == and != compare these values')
                else:
                    difference = float(a) - float(b)
                    if close is not None and abs(difference) <= self.widest():
                        close.append(node)
                    tolerance = self.band(left, right) if band else 0.0
                    found = _COMPARE[op](difference, tolerance)
                if not found:
                    return False
            return True
        return self.side(node, t)

    def widest(self):
        """The largest tolerance of what a comparison can read: of the values that the record keeps,
        and the crossing tolerance for the time."""
        tolerance = self.run.recorder.tolerance
        if self._widest[0] != len(tolerance):
            found = max(tolerance.values(), default=0.0)
            self._widest = (len(tolerance), max(found, self.plan.numerics.crossing))
        return self._widest[1]

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
                elif state.rearm_at is not None and run.clock.due(state.rearm_at, t, run.moment.round == 1):
                    state.armed = True  # its time has come, by the clock (`moment.Clock`)
            if state.armed and state.blocked_at != t:
                close = []
                if self._truth(trigger.test, t, True, close):
                    fires.append(state)
                elif close:
                    self.miss(trigger)
        releases = []
        for live in run.occurrences.waiting():
            step = live.plan.event.steps[live.step]
            node = run.occurrences.node(step.test, live.plan.scope, step.origin)
            if self.holds(node):
                releases.append((live, step.origin, self.near(node, step.origin, t)))
        for state in fires:
            self.fire(state)
        for live, origin, near in releases:
            if live.waiting:
                if near:
                    run.recorder.entry(t, 'release', origin, live.id, near=near)
                run.occurrences.reach(live, live.step + 1)

    def miss(self, trigger):
        """An armed trigger whose condition is false: an entry `miss` when it came within tolerance of
        its threshold (`near`, now and an instant later), unless the trigger's last `miss` since it
        last fired has the same near-ties, so that a near-tie that holds from moment to moment is in
        the trace once."""
        run = self.run
        near = self.near(trigger.test, trigger.origin, run.now)
        if not near:
            return
        missed = self._missed()
        if missed.get((trigger.origin, trigger.member)) != near:
            missed[(trigger.origin, trigger.member)] = near
            run.recorder.entry(run.now, 'miss', trigger.origin, trigger.member, near=near)

    def _missed(self):
        """The near-ties of the last `miss` of each trigger since it last fired, as the trace has them."""
        if self.missed is None:
            self.missed = {}
            for entry in self.run.recorder.trace:
                if entry.kind == 'fire':
                    self.missed.pop((entry.part, entry.owner), None)
                elif entry.kind == 'miss':
                    self.missed[(entry.part, entry.owner)] = entry.detail('near')
        return self.missed

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
            # The time at which it rearms is the clock's: exact from the duration (`moment.Clock`).
            duration = run.clock.value(trigger.reset[1], run.value, run.now)
            if isinstance(duration, bool) or not isinstance(duration, int | float | Fraction) or duration < 0:
                shown = float(duration) if isinstance(duration, Fraction) else duration
                raise SimulationError(f'{trigger.origin}: reset after {shown!r}, which is no duration')
            state.rearm_at = run.clock.later(run.now, duration)
        del run.chance.firing[trigger.key]
        run.recorder.entry(run.now, 'fire', trigger.origin, trigger.member, **tx.details())
        self._missed().pop((trigger.origin, trigger.member), None)
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
        (whether `not` turns it over), found with no recursion (`plan.walked`)."""
        return walked(self._atoms_of(node, positive))

    def _atoms_of(self, node, positive):
        """The computation of `_atoms`: each part through a boolean formula is one that it yields."""
        found = self.plan.values
        if isinstance(node, nodes.Ref):
            value = found.get(node.name)
            if (
                value is not None
                and value.kind == FORMULA
                and value.boolean
                and node.name not in self.run.frozen
            ):
                return (yield self._atoms_of(value.node, positive))
            if value is not None and value.kind == REDUCE and value.boolean:
                # `any` or `all` of yes/no values changes only where one of its members does.
                reduction = self.plan.reductions[node.name]
                atoms = []
                for k in self.run.kept_of(node.name) if reduction.names else ():
                    atoms += yield self._atoms_of(nodes.ref(reduction.names[k]), positive)
                return atoms
            return []
        if isinstance(node, nodes.Unary) and node.op == 'not':
            return (yield self._atoms_of(node.operand, not positive))
        if isinstance(node, nodes.Compare):
            return [
                (left, op, right, positive)
                for left, op, right in zip(node.operands, node.ops, node.operands[1:])
            ]
        atoms = []
        for child in node.children:
            atoms += yield self._atoms_of(child, positive)
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
                linear = (
                    self._linear(moving)
                    and _affine(left, moving, self.plan)
                    and _affine(right, moving, self.plan)
                )
                end = self.side(left, until) - self.side(right, until) if linear else None
            except (TypeError, ValueError):
                continue  # sides that are no numbers
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
            root = self._contact(left, op, right, moving, now, until, float(start))
            if root is not None:
                earliest = min(earliest, root)
        return earliest, window

    def _contact(self, left, op, right, moving, now, until, start):
        """The first time in (now, until] at which a comparison of values on curves can change its
        answer, read within its band, or None: step by step, each piece of a step skipped, decided by
        its ends, or halved (see the module). `start` is its difference now."""
        spelled = f'{nodes.text(left)} {_SPELLING[op]} {nodes.text(right)}'
        band, crossing = self.band(left, right), self.plan.numerics.crossing
        read = {now: start}

        def difference(t):
            # The difference as the run reads it at time t, on the dense output of its sets.
            found = read.get(t)
            if found is None:
                found = read[t] = float(self.side(left, t)) - float(self.side(right, t))
            return found

        edges = _EDGES[op]
        before = {edge: _side(edge, start, band) for edge in edges}
        motion, breaks = self._forms(left, right, moving, now, until, spelled)
        halvings, offset = [0], None

        def first(s, e):
            """The first change in (s, e], a piece inside one form of each read, where the answer has
            not changed before s."""
            piece = motion(s, e)
            # The difference at s is the form's sum and the parts that hold, which the read now gives:
            # within twice the margin of what the run reads, and the roundoff of each.
            at = piece.value + offset
            roundoff = _ROUNDOFF * (piece.size + abs(at) + abs(offset) + band)
            reach = piece.change * (1 + _ROUNDOFF) + 2 * piece.margin + roundoff
            near = [edge for edge in edges if abs(at - _EDGE[edge] * band) <= reach]
            if not near:
                return None  # every edge is farther than the difference can move here
            if piece.spread == 0 or abs(piece.rate) > piece.spread or e - s <= crossing:
                # Its rate keeps its sign (or the piece is within the crossing tolerance): its ends decide.
                changed = [edge for edge in near if _side(edge, difference(e), band) != before[edge]]
                if not changed or e - s <= crossing:
                    return e if changed else None
                return min(self._bisect(difference, edge, band, before[edge], s, e) for edge in changed)
            halvings[0] += 1
            if halvings[0] > _HALVINGS:
                raise SimulationError(
                    f'the first contact of {spelled} cannot be certified: its difference stays within '
                    f'the roundoff of its threshold through {_HALVINGS} halvings of a step from '
                    f't = {s:g} h; compare a value that moves away from its threshold, or use an '
                    'inspection schedule'
                )
            middle = 0.5 * (s + e)
            found = first(s, middle)
            return found if found is not None else first(middle, e)

        found = None
        if motion is None:
            # One store that only rises or only falls, whose way gives no form: the ends decide.
            changed = [edge for edge in edges if _side(edge, difference(until), band) != before[edge]]
            found = min(
                (self._bisect(difference, edge, band, before[edge], now, until) for edge in changed),
                default=None,
            )
        else:
            points = [now, *breaks, until]
            offset = start - motion(now, points[1]).value
            for s, e in pairwise(points):
                halvings[0] = 0
                found = first(s, e)
                if found is not None:
                    break
        # A change just after now is read at the first instant that the engine tells apart from now:
        # what is due before it is due at now (`moment.Clock`).
        return None if found is None else min(max(found, self.run.clock.apart(now)), until)

    def _forms(self, left, right, moving, now, until, spelled):
        """How the difference of a comparison's sides moves through the window (see the module): a
        function (s, e) -> its `Motion` over a piece inside one form of each read, and the times
        inside the window at which a form changes; (None, ()) for one store that only rises or only
        falls, of a way that gives no form. What the engine cannot bound stops the run by name."""
        plan, ways = self.plan, self.run.ways
        if not (_affine(left, moving, plan) and _affine(right, moving, plan)):
            raise SimulationError(
                f'the first contact of {spelled} cannot be certified: a side is no sum of what moves '
                'between moments with weights that hold between them (it multiplies, divides by or '
                'branches on such a value), so the engine has no bound on how far it moves in a step; '
                'compare such a sum, or use an inspection schedule'
            )
        weights = self._weights(left, moving, now)
        for name, weight in self._weights(right, moving, now).items():
            weights[name] = weights.get(name, 0.0) - weight
        live = [name for name, weight in weights.items() if weight != 0]
        lines, curved, formless = [], {}, []  # lines: (weight, value, rate, since)
        for name in live:
            weight = weights[name]
            if name == 't':
                lines.append((weight, 0.0, 1.0, 0.0))
                continue
            if name in ways.set_of:
                line = ways.linear(name)
                instance = ways.instance_of(name)
                if line is not None:
                    lines.append((weight, *line))
                elif hasattr(instance, 'motion'):
                    curved.setdefault(instance, {})[name] = weight
                else:
                    formless.append(name)
                continue
            value = plan.values.get(name)
            instance = ways.instance_of(name.rsplit('.', 1)[0])
            held = (
                instance is None or isinstance(instance, Family | Lines) or getattr(instance, 'lines', False)
            )
            if value is not None and value.kind == RATE and held:
                continue  # a rate of the family or of the lines holds through the window
            raise SimulationError(
                f'the first contact of {spelled} cannot be certified: it reads {name}, which moves on a '
                'curve that the engine does not bound between moments (a rate of a set whose rates move, '
                'or a result of a solver whose problem moves); compare the stores that it moves, or use '
                'an inspection schedule'
            )
        if formless:
            if live == formless[:1] and ways.monotone(formless[0]):
                return None, ()
            raise SimulationError(
                f'the first contact of {spelled} cannot be certified: it reads {formless[0]}, a store of a '
                'set whose way gives the engine no form of its steps (a declared solver whose problem '
                'moves), and is not one store that only rises or only falls; compare such a store, or use '
                'an inspection schedule'
            )
        breaks = sorted({at for instance in curved for at in instance.breaks(now, until)})

        def motion(s, e):
            found = Motion()
            for weight, value, rate, since in lines:
                found += dense.line(weight * (value + rate * (s - since)), weight * rate, e - s)
            for instance, part in curved.items():
                found += instance.motion(part, s, e)
            return found

        return motion, breaks

    def _weights(self, node, moving, t):
        """The weight of each moving name in an affine node (`_affine`), through formulas and the sums
        of their kept entries: {name: weight}, with what holds between moments read at time t, found
        with no recursion (`plan.walked`)."""
        found = {}
        walked(self._weights_of(node, moving, t, 1.0, found))
        return found

    def _weights_of(self, node, moving, t, scale, found):
        """The computation of `_weights`: each part through a formula or a sum is one that it yields."""
        plan = self.plan
        if not (_reads(node, plan) & (moving | {'t'})):
            return
        if isinstance(node, nodes.Ref):
            value = plan.values.get(node.name)
            if node.name in moving or node.name == 't':
                found[node.name] = found.get(node.name, 0.0) + scale
            elif value is not None and value.kind == FORMULA and node.name not in self.run.frozen:
                yield self._weights_of(value.node, moving, t, scale, found)
            elif value is not None and value.kind == REDUCE:
                names = plan.reductions[node.name].names  # a sum, which `_affine` admits
                for k in self.run.kept_of(node.name):
                    yield self._weights_of(nodes.ref(names[k]), moving, t, scale, found)
        elif isinstance(node, nodes.Unary):
            yield self._weights_of(node.operand, moving, t, -scale if node.op == 'neg' else scale, found)
        elif node.op in ('add', 'sub'):
            yield self._weights_of(node.left, moving, t, scale, found)
            yield self._weights_of(node.right, moving, t, -scale if node.op == 'sub' else scale, found)
        elif node.op == 'div':
            yield self._weights_of(node.left, moving, t, scale / float(self.side(node.right, t)), found)
        elif _reads(node.left, plan) & (moving | {'t'}):  # a product with one side that holds
            yield self._weights_of(node.left, moving, t, scale * float(self.side(node.right, t)), found)
        else:
            yield self._weights_of(node.right, moving, t, scale * float(self.side(node.left, t)), found)

    def _bisect(self, difference, edge, band, before, low, high):
        """The first time in (low, high] at which a difference that moves one way leaves the side
        `before` of an edge, to within the crossing tolerance: bisection, which keeps the change
        between its ends (the side at `low` is `before`, at `high` the other)."""
        crossing = self.plan.numerics.crossing
        while high - low > crossing:
            middle = 0.5 * (low + high)
            if _side(edge, difference(middle), band) == before:
                low = middle
            else:
                high = middle
        return high

    def _exact_root(self, left, right, moving, now):
        """The root of a comparison whose only moving read is the time (`t`, `since(e)` or
        `elapsed(x)` against what holds), which the clock gives exactly (`moment.Clock`): the sides
        are affine in the time, so their difference at now and an hour later, in exact arithmetic,
        gives the time at which it is zero; so `since(e) >= 0.2 h` after a start at 0.1 h changes at
        0.3 h, as `t >= 0.3 h` does. Or the root of one store on its line against what holds, the
        line's start plus its distance over its rate. None for any other comparison."""
        run, ways = self.run, self.run.ways
        if moving == {'t'}:
            clock = run.clock

            def difference(t):
                read = lambda name: run.value(name, now)  # noqa: E731 (what holds, now)
                return clock.value(left, read, t) - clock.value(right, read, t)

            try:
                begin = clock.exact(now)
                start = difference(begin)
                slope = difference(begin + 1) - start
                return None if slope == 0 else float(begin - start / slope)
            except (ExpressionError, ArithmeticError, TypeError, ValueError, LookupError):
                return None  # sides that exact arithmetic does not read: the line's root
        for side, other in ((left, right), (right, left)):
            if not isinstance(side, nodes.Ref) or moving != {side.name}:
                continue
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


_SPELLING = {'le': '<=', 'ge': '>=', 'lt': '<', 'gt': '>', 'eq': '==', 'ne': '!='}
_EDGE = {'low': -1.0, 'high': 1.0}  # the place of each edge of a band, in bands


def _side(edge, difference, band):
    """The side of an edge of the band on which a difference lies: whether `difference >= -band` for
    the low edge, and whether `difference <= band` for the high one (`_COMPARE`)."""
    return difference >= -band if edge == 'low' else difference <= band


def _affine(node, moving, plan):
    """Whether a node is affine in the moving names that it reads, through formulas, found with no
    recursion (`plan.walked`)."""
    return walked(_affine_of(node, moving, plan))


def _affine_of(node, moving, plan):
    """The computation of `_affine`: each part through a formula or a sum is one that it yields."""
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
                for name in reduction.names:
                    if not (yield _affine_of(nodes.ref(name), moving, plan)):
                        return False
                return True
            return not (_reads(node, plan) & (moving | {'t'}))
        if node.name in moving or node.name == 't' or value is None or value.kind != FORMULA:
            return True
        return (yield _affine_of(value.node, moving, plan))
    if isinstance(node, nodes.Unary) and node.op in ('neg', 'pos'):
        return (yield _affine_of(node.operand, moving, plan))
    if isinstance(node, nodes.Binary):
        if node.op in ('add', 'sub'):
            return bool((yield _affine_of(node.left, moving, plan))) and bool(
                (yield _affine_of(node.right, moving, plan))
            )
        still = [not (_reads(part, plan) & (moving | {'t'})) for part in (node.left, node.right)]
        if node.op == 'mul':
            if not (still[0] or still[1]):
                return False
            for part in (node.left, node.right):
                if not (yield _affine_of(part, moving, plan)):
                    return False
            return True
        if node.op == 'div':
            return still[1] and bool((yield _affine_of(node.left, moving, plan)))
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
