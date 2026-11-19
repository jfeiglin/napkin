"""Occurrences: the starts of events in a run, what each holds, and how it goes through its steps.

An occurrence is made when a start registers: at the commit of the stage or of the setup that queued
it, or at a firing of a trigger (`moment.py`). The plan gives it its values and flows under its id,
`receiver.event#n`, the n-th start of that event on that receiver from 0 (`plan.Plan.occurrence`).
Its entry gives them values in written order (D14): its parameters take the arguments, which the
caller evaluated (each within its parameter's entry bounds), `started` the time, `done` false and
`active` true, then each local and each plain setting of its flows its initializer, which reads what
is above it. A stored number of an occurrence takes its size there, and its bounds. Its flows join
the network at the settling of the round (`ways.py`).

Then it goes through its steps in order (spec, "Time, waiting and completion"):

- `after D` captures D when the step is reached, a finite duration from zero, and is due D later:
  its stage commits then (`moment.py`). Stages due together commit in the order in which their
  occurrences were made (D5);
- `until C` is a gate: the occurrence waits there until the conditions of a round find C true
  (`triggers.py`), and goes on in that round.

At the end of its steps it finishes normally (`complete`). Each of its stores that a flow or a move
met must be empty, within its tolerance, or the run fails and names the occurrence, the store, the
amount and its unit, and the time (retirement). Each of its formulas, the settings of its flows
included, keeps the value that it has then, or the reason why it has none (D7). Its flows leave the
network at the settling of the round, and read zero from then on. `done` becomes true and `active`
false: the occurrence is a stable record, and a write to it fails.

The limits of a runaway run (D6) are checked before each start: `max_occurrences` starts of one
event, and `max_active` occurrences of one event alive at once, whose message names the oldest
and the step at which it waits.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...program import parts as p
from ...program.record import Unavailable
from ..errors import SimulationError


@dataclass(eq=False)
class Live:
    """An occurrence in a run: its plan, its number of creation, the step that it is at (and the
    time at which that step is due, with a version for the schedule), whether it waits at a gate,
    whether it is active, and the stores of it that a flow or a move met."""

    plan: object
    number: int
    started: float
    step: int = 0
    due: float | None = None
    version: int = 0
    waiting: bool = False
    active: bool = True
    met: set = field(default_factory=set)

    @property
    def id(self):
        return self.plan.id


class Occurrences:
    """The occurrences of one run (see the module)."""

    def __init__(self, run):
        self.run, self.plan = run, run.plan
        self.live = {}  # id -> Live
        self.made = 0
        self.schedule = []  # (due, number, id, version) of the steps that wait for their time
        self.of_event = {}  # (member, event) -> its occurrences, in order
        self.gates = {}  # id -> an occurrence that waits at a gate
        self._nodes = {}  # (id of an expression, owner) -> its node over engine names

    def node(self, expression, scope, origin):
        """The node of an expression of a scope over engine names, made once."""
        owner = self.plan.owner_of(scope)
        key = (id(expression), owner)
        found = self._nodes.get(key)
        if found is None:
            # The expression is kept with its node, so that its id names it while the run lasts.
            found = self._nodes[key] = (self.plan.node(expression, scope, origin), expression)
        return found[0]

    # ---- starts -----------------------------------------------------------------------------------

    def register(self, member, event, args):
        """A start becomes an occurrence (see the module); gives it."""
        run, plan = self.run, self.plan
        t = run.now
        found = self.of_event.setdefault((member, event), [])
        self._limits(member, event, found)
        made = plan.occurrence(member, event, len(found), args, t)
        self.made += 1
        live = Live(made, self.made, t)
        self.live[made.id] = live
        found.append(live)
        for name in made.initial:
            self._enter(name, made)
        for flow in made.flows:
            for connection in plan.flows[flow].connections:
                live.met.update(end for end in (connection.source, connection.sink) if end in made.stores)
            run.flow_joins(flow)
        run.recorder.entry(t, 'start', made.event.origin, made.id, args=tuple(args))
        run.changed.add(('occurrences', member, event))
        if run.moment.phase == 'conditions':
            run.moment.again = True
        self.reach(live, 0)
        return live

    def _enter(self, name, made):
        """One value of an occurrence takes its value at the entry, in written order."""
        run, plan = self.run, self.plan
        value = plan.values[name]
        number = run.truth(value.node)
        if not value.boolean and isinstance(number, int | float) and not isinstance(number, bool):
            number = float(number)
        bounds = [None, None]
        for k, bound in enumerate((value.lower, value.upper)):
            if bound is not None:
                bounds[k] = float(run.truth(bound))
        if bounds != [None, None] or name in made.stores:
            low = -math.inf if bounds[0] is None else bounds[0]
            high = math.inf if bounds[1] is None else bounds[1]
            run.bounds[name] = (low, high)
            if not low <= number <= high:
                raise SimulationError(
                    f'{name} = {number:g} is outside its range [{low:g}, {high:g}] at t = {run.now:g} h'
                )
        if name in made.stores:
            unit = plan.units.scale(value.unit) if value.unit else 1.0
            size = max([unit, abs(number)] + [abs(b) for b in bounds if b is not None and math.isfinite(b)])
            run.sizes[name] = size
            run.recorder.tolerance[name] = plan.numerics.atol_factor * size
        run.env[name] = number
        run.recorder.add(name, run.now, number, 0.0)

    def _limits(self, member, event, found):
        """`max_occurrences` and `max_active` (D6), before one more start."""
        limits, t = self.run.plan.configuration.limits, self.run.now
        name = f'{member}.{event}'
        if len(found) >= limits.max_occurrences:
            raise SimulationError(
                f'{name} would start {len(found) + 1} times by t = {t:g} h: the limit max_occurrences '
                f'is {limits.max_occurrences} starts of one event'
            )
        active = [live for live in found if live.active]
        if len(active) >= limits.max_active:
            oldest = active[0]
            raise SimulationError(
                f'{len(active)} occurrences of {name} are active at once (max_active = '
                f'{limits.max_active}) and one more starts at t = {t:g} h. The oldest, {oldest.id}, '
                f'started at {oldest.started:g} h and waits at {self._where(oldest)}.'
            )

    def _where(self, live):
        """The step at which an occurrence waits, for a message."""
        step = live.plan.event.steps[live.step]
        if isinstance(step, p.Until):
            return f'`until {nodes.text(step.test.node)}` (step {live.step + 1})'
        due = f', due at {live.due:g} h' if live.due is not None else ''
        return f'`after {nodes.text(step.delay.node)}` (step {live.step + 1}{due})'

    # ---- steps ------------------------------------------------------------------------------------

    def reach(self, live, index):
        """An occurrence comes to its step `index`: a delay is captured, a gate waits, or it
        finishes."""
        run = self.run
        live.step, live.waiting, live.due = index, False, None
        live.version += 1
        self.gates.pop(live.id, None)
        steps = live.plan.event.steps
        if index >= len(steps):
            self.complete(live)
            return
        step = steps[index]
        if run.moment.phase == 'conditions':
            run.moment.again = True
        if isinstance(step, p.Until):
            live.waiting = True
            self.gates[live.id] = live  # its condition is watched from the end of the moment
            return
        delay = run.truth(self.node(step.delay, live.plan.scope, step.origin))
        if (
            isinstance(delay, bool)
            or not isinstance(delay, int | float)
            or not math.isfinite(delay)
            or delay < 0
        ):
            raise SimulationError(
                f'the delay {nodes.text(step.delay.node)} of {live.id} must be a duration that is not '
                f'negative, and is {delay!r} at t = {run.now:g} h'
            )
        live.due = run.now + float(delay)
        heapq.heappush(self.schedule, (live.due, live.number, live.id, live.version))

    def next_due(self):
        """The time of the next step that waits for its time, or None."""
        schedule = self.schedule
        while schedule and schedule[0][3] != self.live[schedule[0][2]].version:
            heapq.heappop(schedule)
        return schedule[0][0] if schedule else None

    def due(self, t):
        """The occurrences whose steps are due at time t, in the order in which they were made."""
        found = []
        while self.next_due() is not None and self.schedule[0][0] <= t:
            _, _, occ, _ = heapq.heappop(self.schedule)
            found.append(self.live[occ])
        return found

    def met(self, store):
        """A move meets a store: one of an occurrence must be empty when it finishes."""
        found = self.plan.values.get(store)
        owner = found.key.owner if found is not None and found.key is not None else ''
        if owner in self.live:
            self.live[owner].met.add(store)

    def waiting(self):
        """The occurrences that wait at a gate, in the order in which they were made."""
        return sorted(self.gates.values(), key=lambda live: live.number)

    # ---- the finish ---------------------------------------------------------------------------------

    def complete(self, live):
        """Normal completion (see the module)."""
        run, plan, t = self.run, self.plan, self.run.now
        made = live.plan
        for store in made.stores:
            if store not in live.met:
                continue
            left = float(run.value(store))
            if abs(left) > run.recorder.tolerance.get(store, 0.0):
                unit = plan.values[store].unit
                scale = plan.units.scale(unit) if unit else 1.0
                raise SimulationError(
                    f'{made.id} cannot finish at t = {t:g} h: its store {store} still holds '
                    f'{left / scale:g} {unit}'.rstrip()
                    + '. Wait for it to drain, move the rest to a named stock, or send it to SINK.'
                )
        for name in made.formulas:
            try:
                frozen = run.value(name)
            except (ExpressionError, ArithmeticError, ValueError, LookupError, SimulationError) as problem:
                frozen = Unavailable(
                    f'{name} was not available when {made.id} finished at t = {t:g} h: {problem}'
                )
            run.frozen[name] = frozen
            run.recorder.add(name, t, frozen, 0.0)
        for flow in made.flows:
            run.flow_leaves(flow)
        live.active = False
        for name, value in ((f'{made.id}.done', True), (f'{made.id}.active', False)):
            run.env[name] = value
            run.recorder.add(name, t, value, 0.0)
            run.changed.add(name)
        run.changed.add(('occurrences', made.member, made.event.name))
        run.recorder.entry(t, 'finish', made.event.origin, made.id)
        if run.moment.phase == 'conditions':
            run.moment.again = True
