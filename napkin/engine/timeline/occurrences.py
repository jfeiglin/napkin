"""Occurrences: the starts of events in a run, what each holds, and how it goes through its steps.

An occurrence is made when a start registers: at the commit of the stage or of the setup that queued
it, or at a firing of a trigger (`moment.py`). The plan gives it its values and flows under its id,
`receiver.event#n`, the n-th start of that event on that receiver from 0 (`plan.Plan.occurrence`).
Its entry gives them values in written order (D14): its parameters take the arguments, which the
caller evaluated (each within its parameter's entry bounds), `started` the time, `done` false and
`active` true, then each local and each plain setting of its flows its initializer, which reads what
is above it; a draw there is the occurrence's (`chance.py`), and a local distribution is its own. A
stored number of an occurrence takes its size there, and its bounds. Its flows join the network at
the settling of the round (`ways.py`).

Then it goes through its steps in order (spec, "Time, waiting and completion"):

- `after D` captures D when the step is reached, a finite duration from zero, and is due D later:
  its stage commits then (`moment.py`). D and the time at which it is due are the clock's
  (`moment.Clock`): D is evaluated in exact arithmetic and added to the time exactly, so 0.1 h and
  then 0.2 h is due at 0.3 h exactly, and the first round of a moment takes each step due within the
  time tolerance after it, as due at it; a step reached during the moment with a delay above zero
  is due later, at its own moment. Stages due together commit in the order in which their
  occurrences were made (D5). A D that a stage or the conditions of a round reach (a start of a
  firing, a release) and that reads a rate or a result takes them after the next settling, so a
  solve that the round affects gives its settled answer and no read of it comes before (PLAN, change
  26); what else it reads is captured when the step is reached (`delays`);
- `until C` is a gate: the occurrence waits there until the conditions of a round find C true
  (`triggers.py`), and goes on in that round.

At the end of its steps it finishes normally (`complete`). Each of its stores that a flow or a move
met, its own or another occurrence's, must be empty, within its tolerance, or the run fails and
names the occurrence, the store, the amount and its unit, and the time (retirement). Each of its
formulas, the settings of its flows included, keeps the value that it has then, or the reason why it
has none (D7). Its flows leave the network at the settling of the round, and read zero from then on.
`done` becomes true and `active` false: the occurrence is a stable record.

**A finished occurrence is frozen** (PLAN, change 24 b, amended at change 29). An assignment
and an authored move of any nonzero amount fail by name (`writable`). For each physical store of
a finished occurrence, `carried` counts the inventory through each side after retirement. The sum
over all its present connections and all elapsed segments has one conservation allowance in that
store's unit. A settled rate over no time transfers nothing. A flow joining or leaving cannot reset
the sum. The first excess ends the run with the responsible connection, direction and occurrence.

The limits of a runaway run (D6) are checked before each start: `max_occurrences` starts of one
event, and `max_active` occurrences of one event alive at once, whose message names the oldest
and the step at which it waits.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import pairwise

from scipy.integrate import quad
from scipy.optimize import brentq

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...program import parts as p
from ...program.record import Unavailable
from ..errors import SimulationError
from .moment import in_unit, quantity, span
from .plan import DESCRIBED, FORMULA, RATE, RESULT, SIDES
from .reads import lazily


def _flow_of(plan, connection):
    """The flow of a connection: a directed flow is its own, a leg of a route or of a flow with legs
    is named after its flow."""
    return connection if connection in plan.flows else connection.rsplit('.', 1)[0]


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
        self.sources = {}  # the id of such a node -> (its expression, owner, origin), for `saved.py`
        self.awaiting = []  # delays that wait for the round's settling (`delays`)
        self._delays = {}  # a delay's node -> the rates and results that it reads
        # The stores of finished occurrences that a present connection may meet (`carried`), found
        # when first asked from the occurrences that the run holds (`watched`).
        self._watched = None
        self.transferred = {}  # (retired store, direction) -> amounts booked since retirement

    def node(self, expression, scope, origin):
        """The node of an expression of a scope over engine names, made once."""
        plan = self.plan
        owner = plan.owner_of(scope)
        key = (id(expression), owner)
        found = self._nodes.get(key)
        if found is None:
            size = plan.size()
            # The expression is kept with its node, so that its id names it while the run lasts.
            found = self._nodes[key] = (plan.node(expression, scope, origin), expression)
            self.sources[id(found[0])] = (expression, owner, origin)
            if plan.size() != size:
                plan.log.append(('node', expression, owner, origin))  # it named values (`saved.py`)
        return found[0]

    # ---- starts -----------------------------------------------------------------------------------

    def register(self, member, event, args):
        """A start becomes an occurrence (see the module); gives it."""
        run, plan = self.run, self.plan
        t = run.now
        found = self.of_event.setdefault((member, event), [])
        self._limits(member, event, found)
        made = plan.occurrence(member, event, len(found), args, t)
        plan.log.append(('occurrence', member, event, len(found), tuple(args), t))
        self.made += 1
        live = Live(made, self.made, t)
        self.live[made.id] = live
        found.append(live)
        for name in made.initial:
            self._enter(name, made)
        for flow in made.flows:
            for connection in plan.flows[flow].connections:
                for end in (connection.source, connection.sink):
                    if end is not None:
                        # A store of an occurrence that it meets is retired as met (`complete`); one
                        # of a finished occurrence is watched from its settling on (`carried`).
                        self.met(end)
                        if self.frozen(end) is not None:
                            self.watched().add(end)
            run.flow_joins(flow)
        run.recorder.entry(t, 'start', made.event.origin, made.id, args=tuple(args))
        run.changed.add(('occurrences', member, event))
        if run.moment.phase == 'conditions':
            run.moment.again = True
        self.reach(live, 0)
        return live

    def _enter(self, name, made):
        """One value of an occurrence takes its value at the entry, in written order: each of its
        initial values (`plan.Occurrence.initial`), which hold no `formula(...)` local, a retained
        calculation that is read where something reads it after the entry, so that it may name a local
        below it or a value that has none yet (spec.md:634, D14), and that freezes when its occurrence
        finishes (`complete`)."""
        run, plan = self.run, self.plan
        if name in plan.distributions:
            run.env[name] = plan.distributions[name]  # a distribution of the occurrence, to draw from
            return
        value = plan.values[name]
        if value.kind == DESCRIBED:  # the `.mean` or the `.std` of a distribution of the occurrence
            run.recorder.add(name, run.now, run.chance.described(name), 0.0)
            return
        number = run.truth(value.node)
        if not value.boolean and isinstance(number, int | float) and not isinstance(number, bool):
            number = float(number)
        if value.scale is not None:
            run.scales[name] = float(run.truth(value.scale))
            plan.comparison_scales[name] = abs(run.scales[name])
            plan.units.comparisons.floors.clear()
        bounds = [None, None]
        for k, bound in enumerate((value.lower, value.upper)):
            if bound is not None:
                bounds[k] = float(run.truth(bound))
        if bounds != [None, None] or name in made.stores:
            low, high, number = run.initial_range(name, *bounds, number)
            run.bounds[name] = low, high
            parameter = value.key.steps[0] in (each.name for each in made.event.params)
            if not low <= number <= high and not (parameter and run.admitted(name, low, high, number)):
                raise SimulationError(
                    f'{name} = {quantity(plan, name, number)} is outside its range '
                    f'{span(plan, name, low, high)} at t = {run.now:g} h'
                )
        if name in made.stores:
            unit = plan.units.scale(value.unit) if value.unit else 1.0
            size = max([unit, abs(number)] + [abs(b) for b in bounds if b is not None and math.isfinite(b)])
            run.sizes[name] = size
            run.recorder.tolerance[name] = run.amount_tolerance(name)
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
            return f'`until {nodes.notation(step.test.node)}` (step {live.step + 1})'
        due = f', due at {live.due:g} h' if live.due is not None else ''
        return f'`after {nodes.notation(step.delay.node)}` (step {live.step + 1}{due})'

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
        node = self.node(step.delay, live.plan.scope, step.origin)
        computed = self._computed(node)
        if computed and run.moment.phase in ('stages', 'conditions'):
            # The rates and results that it reads settle after the stages of the round (D5), and
            # after the firings and releases of its conditions, at the next round's settling.
            self.awaiting.append((live, live.version, node, step, self._captured(node, computed)))
            return
        self._schedule(live, run.clock.value(node, run.value, run.now), step)

    def _schedule(self, live, delay, step):
        """A step is due `delay` after now, by the clock (`moment.Clock`)."""
        run = self.run
        if (
            isinstance(delay, bool)
            or not isinstance(delay, int | float | Fraction)
            or not math.isfinite(delay)
            or delay < 0
        ):
            shown = in_unit(self.plan.units, float(delay) if isinstance(delay, Fraction) else delay, 'h')
            raise SimulationError(
                f'the delay {nodes.notation(step.delay.node)} of {live.id} must be a duration that is not '
                f'negative, and is {shown} at t = {run.now:g} h'
            )
        live.due = run.clock.later(run.now, delay)
        heapq.heappush(self.schedule, (live.due, live.number, live.id, live.version))

    def _computed(self, node):
        """The rates and results that a delay reads, through formulas, reductions and dynamic reads."""
        plan = self.plan
        key = (node, plan.version)  # a definition that a commit gives changes what a node reads
        found = self._delays.get(key)
        if found is None:
            expanded = plan.reads_now(plan.expansion(node))
            leaves = expanded.leaves
            found = frozenset(
                leaf for leaf in leaves if leaf in plan.values and plan.values[leaf].kind in (RATE, RESULT)
            ) | (plan.shared & (leaves | expanded.formulas))
            self._delays[key] = found
        return found

    def _captured(self, node, computed):
        """The values now of what a delay reads other than rates and results: each value that it
        reads, or the error that reading it raises. A dynamic read of the rates of an endpoint's
        flows is read with them, after the settling (`delays`)."""
        run, plan = self.run, self.plan
        found = {}
        for leaf in plan.reads_now(plan.expansion(node)).leaves - computed:
            dynamic = plan.dynamic.get(leaf)
            if dynamic is not None and dynamic.steps[-1:] in (('actual_rate',), ('served_fraction',)):
                continue
            try:
                found[leaf] = run.value(leaf)
            except (ExpressionError, ArithmeticError, ValueError, LookupError, SimulationError) as problem:
                found[leaf] = problem
        return found

    def delays(self):
        """After the settling of a round: each delay that waits for rates and results takes its
        value, from what it captured and what settled, and its stage is due that much later."""
        run, plan = self.run, self.plan
        waiting, self.awaiting = self.awaiting, []
        for live, version, node, step, captured in waiting:
            if live.version != version:
                continue

            def read(name, captured=captured):
                if name in captured:
                    found = captured[name]
                    if isinstance(found, Exception):
                        raise found
                    return found
                if name in run.published:
                    return run.ways.shared_value(name)
                value = plan.values.get(name)
                if (
                    value is not None
                    and value.kind == FORMULA
                    and name not in run.frozen
                    and name not in plan.shared
                ):
                    return lazily(value.node, read, plan.units, run.now)
                return run.value(name)

            self._schedule(live, run.clock.value(node, read, run.now), step)

    def next_due(self):
        """The time of the next step that waits for its time, or None."""
        schedule = self.schedule
        while schedule and schedule[0][3] != self.live[schedule[0][2]].version:
            heapq.heappop(schedule)
        return schedule[0][0] if schedule else None

    def due(self, t, opening):
        """The occurrences whose steps are due at the moment of time t, in the order in which they
        were made (D5): by the clock (`moment.Clock`), as the moment begins (`opening`, its first
        round) or within it."""
        found, clock = [], self.run.clock
        while self.next_due() is not None and clock.due(self.schedule[0][0], t, opening):
            _, _, occ, _ = heapq.heappop(self.schedule)
            found.append(self.live[occ])
        return sorted(found, key=lambda live: live.number)

    def met(self, store):
        """A move or a flow meets a store: one of an occurrence must be empty when it finishes."""
        found = self.plan.values.get(store)
        owner = found.key.owner if found is not None and found.key is not None else ''
        if owner in self.live:
            self.live[owner].met.add(store)

    def frozen(self, name):
        """The finished occurrence that owns an engine name, or None: its values are frozen."""
        owner = self.plan.occurrence_of(name)
        live = self.live.get(owner) if owner is not None else None
        return owner if live is not None and not live.active else None

    def writable(self, name, writer, amount=None):
        """The one check of a write or a transfer that lands on an engine name (see the module): an
        assignment (`amount` None) always writes, and an authored move writes for any nonzero amount.
        A write to a value of a finished occurrence fails the run, naming the value, its occurrence
        and the writer."""
        owner = self.frozen(name)
        if owner is None:
            return
        if amount == 0:
            return
        raise SimulationError(f'{writer}: {name} belongs to the finished occurrence {owner}, which is frozen')

    def watched(self):
        """The stores of finished occurrences that a present connection may meet: kept as stores
        finish and flows join (`complete`, `register`), and found once from the finished occurrences
        by a run that a checkpoint restored, which keeps no more than its occurrences (`saved.py`)."""
        if self._watched is None:
            self._watched = {
                store for live in self.live.values() if not live.active for store in live.plan.stores
            }
        return self._watched

    def carried(self, start, end):
        """Book each direction's inventory since retirement over the accepted segment. An amount
        allowance belongs to the store and covers all segments and all its connections."""
        if end <= start or not self.watched():
            return
        run = self.run
        first = None
        updates = {}
        for store in sorted(self.watched()):
            present = False
            allowance = run.amount_tolerance(store)
            for side in SIDES:
                connections = self.plan.incident(store, side)
                if not connections:
                    continue
                present = True
                key = store, side
                # Keep the running sum exact over the measured segment contributions, so tiny
                # transfers cannot disappear when joined to a much larger accumulated amount.
                previous = self.transferred.get(key, Fraction(0))
                rates, breaks = [], {start, end}
                moving = False
                for connection in connections:
                    name = f'{connection}.actual_rate'
                    parent = _flow_of(self.plan, connection)
                    way = run.ways.instance_of(parent)
                    if way is None:
                        continue
                    rates.append(name)
                    if run.ways.moving(run.ways.set_of[parent]):
                        moving = True
                        breaks.update(getattr(way, 'breaks', lambda a, b: ())(start, end))
                if not rates:
                    continue

                def rate(t):
                    return math.fsum(abs(run.value(name, t)) for name in rates)

                def volume(a, b):
                    if not moving:
                        return rate(a) * (b - a)
                    answer = quad(rate, a, b, epsabs=allowance * 1e-6, epsrel=1e-10, full_output=True)
                    if len(answer) > 3:
                        raise SimulationError(
                            f'{store}: cannot certify the frozen {side} amount: {answer[3]}'
                        )
                    return answer[0]

                for a, b in pairwise(sorted(breaks)):
                    moved = Fraction(volume(a, b))
                    if previous + moved > allowance:
                        remaining = float(Fraction(allowance) - previous)
                        at = (
                            brentq(lambda t: volume(a, t) - remaining, a, b, xtol=1e-14)
                            if moving
                            else a + (b - a) * remaining / float(moved)
                        )
                        largest = max(rates, key=lambda name: abs(run.value(name, at)))
                        if first is None or at < first[0]:
                            first = (at, store, side, largest, run.value(largest, at))
                        break
                    previous += moved
                updates[key] = previous
            if not present:
                self.watched().discard(store)
        if first is None:
            self.transferred.update(updates)
            return
        at, store, side, name, amount = first
        run.ways.cut(at)
        run.now = at
        connection = name.rsplit('.', 1)[0]
        unit = self.plan.values[name].unit
        shown = in_unit(self.plan.units, amount, unit)
        way = 'out of' if side == 'outflow' else 'into'
        self.writable(store, f'the flow {connection} carries {shown} {way} {store} at t = {at:g} h')

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
            if abs(left) > run.amount_tolerance(store, left):
                raise SimulationError(
                    f'{made.id} cannot finish at t = {t:g} h: its store {store} still holds '
                    f'{quantity(plan, store, left)}. Wait for it to drain, move the rest to a named stock, '
                    'or send it to SINK.'
                )
        # What is a formula at the finish freezes: a stage may have given a request or a capacity a
        # formula, or a number in place of one.
        observations = {}
        for name in dict.fromkeys((*made.formulas, *made.initial)):
            found = plan.values.get(name)  # none for a distribution-valued local
            if found is None or found.kind != FORMULA:
                continue
            try:
                frozen = run.value(name, observations=observations)
            except (ExpressionError, ArithmeticError, ValueError, LookupError, SimulationError) as problem:
                frozen = Unavailable(
                    f'{name} was not available when {made.id} finished at t = {t:g} h: {problem}'
                )
            run.frozen[name] = frozen
            run.recorder.add(name, t, frozen, 0.0)
        for flow in made.flows:
            run.flow_leaves(flow)
        live.active = False
        # A flow of another occurrence that still meets one of its stores writes it where it carries
        # a rate, from the settling of this round on (`carried`).
        self.watched().update(
            store for store in made.stores if any(plan.incident(store, side) for side in SIDES)
        )
        for name, value in ((f'{made.id}.done', True), (f'{made.id}.active', False)):
            run.env[name] = value
            run.recorder.add(name, t, value, 0.0)
            run.changed.add(name)
        run.changed.add(('occurrences', made.member, made.event.name))
        details = (
            {'reads': tuple((name, tuple(reads)) for name, reads in observations.items())}
            if observations
            else {}
        )
        run.recorder.entry(t, 'finish', made.event.origin, made.id, **details)
        if run.moment.phase == 'conditions':
            run.moment.again = True
