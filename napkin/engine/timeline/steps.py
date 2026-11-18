"""One step of a rule: its trigger, the outcome that it takes, and its firing.

Moved from `run.py` with no change (step B0-6). `Steps` is a part of `run.Run`: its methods
read the run as `self`.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from ...distributions import central as central_value
from ...distributions import problems, quantile
from ...model.ir import COUNT, ENTERED, TIME
from ..errors import SimulationError
from ..sampling import draws
from .state import CHANCE_TOLERANCE, Env, Past, _one


def shares(chances):
    """The chance with which a sample takes each outcome of a firing, from the chances as the
    model gives them (they add up to 1 within the tolerance of the chances). A sample takes the
    first outcome whose running total is above its uniform number, and the last outcome that has
    a chance where no total is (`Run.chosen`): so each outcome has its chance, the running total
    stops at 1, and the last one takes what is missing to 1."""
    found, total, last = [0.0] * len(chances), 0.0, None
    for place, chance in enumerate(chances):
        if chance <= 0:
            continue
        found[place] = min(1.0, total + chance) - min(1.0, total)
        total, last = total + chance, place
    if last is not None and total < 1.0:
        found[last] += 1.0 - total
    return found


class Steps:
    """See the module."""

    def extras(self, rule, j, env, t, stage):
        """Give the environment of a firing the values that the rule reads at this stage: each value
        that it draws (the central value, or with luck the next number of the stream of its event),
        and each value of the past."""
        for item in rule.extras:
            if item.stage != stage:
                continue
            name = self.rule_name(rule, j)
            if item.kind == 'delayed':
                delay = float(_one(self.value(item.delay, env)))
                if not math.isfinite(delay) or delay < 0:
                    raise SimulationError(f'{name}: delayed() goes back a finite time from 0, not {delay} h')
                past = env if delay == 0 else Past(self, rule.space, np.array([j]), max(0.0, t - delay))
                env.memo[item.name] = _one(self.value(item.expr, past))
                continue
            args = {arg: float(_one(self.value(node, env))) for arg, node in item.args}
            wrong = problems(item.family, args)
            if wrong:
                raise SimulationError(f'{name}: {item.family}{tuple(args.values())}: {"; ".join(wrong)}')
            if not self.luck:
                env.memo[item.name] = central_value(item.family, args)
                continue
            key = (name, 'draw')
            if key not in self.streams:
                self.streams[key] = draws(self.luck['seed'], f'{name}/draw/{self.luck["sample"]}')
            env.memo[item.name] = float(quantile(item.family, args, self.streams[key]()))

    def count_step(self, t, rule, j):
        # The budget is for the steps of one thing at one moment: the rows of a table can each take
        # their steps at the same moment, so the limit is that number times the rows of the largest
        # table, as the limit of the events of a run is.
        limit = self.cfg.max_steps * max(space.count for space in self.plan.spaces)
        if self.steps >= limit:
            name = self.rule_name(rule, j)
            raise SimulationError(
                f'The moment t={t:g} h does not settle within {limit} steps; next: {name}',
                [{'code': 'step_budget', 'severity': 'error', 't': t, 'next': [name]}],
            )
        self.steps += 1
        self.counts['steps'] += 1

    def emitted(self, events, space, j, t, writes):
        for event in events:
            if event in self.plan.events:
                place = self.place(space, j, event)
                count = int(self.v[event + COUNT][place]) + 1
                writes.append((event + COUNT, place, count))
                writes.append((event + TIME, place, t))

    def trigger(self, rule, j, t):
        """A rule triggers for the instance j at the time t."""
        state = self.rules[rule.index]
        self.count_step(t, rule, j)
        state.armed[j] = False
        state.triggered[j] += 1
        # The crossing that brought the rule to this moment has had its trigger: from here the rule
        # holds only while its quantity is at or past its value.
        state.reached[j] = 0
        self.mark(rule.index, {j})
        env = Env(self, rule.space, np.array([j]), t)
        if rule.each:
            state.window[j] = self.window(rule, env, 1)[0]
        if rule.delay is None:
            self.fire(rule, j, t, counted=True, own=True)
            return
        self.extras(rule, j, env, t, 'trigger')
        delay = float(_one(self.value(rule.delay, env)))
        if not math.isfinite(delay) or delay < 0:
            name = self.rule_name(rule, j)
            path = rule.delay_path if rule.delay_path is not None else rule.path
            raise SimulationError(
                f'{name}: a delay is a finite time from 0, not {delay} h',
                [{'code': 'delay', 'severity': 'error', 'rule': name, 'path': path}],
            )
        state.pending[j] = t + delay
        writes = []
        self.emitted(rule.emits, rule.space, j, t, writes)
        self.trace.append((float(t), rule.index, j, None))
        self.entry(rule, j, None, t, {}, {}, [], {})
        self.apply(writes, t)
        self.snapshot(t, step=True)

    def chosen(self, rule, env, j, t):
        """The place of the outcome that a firing takes. Each chance is from 0 to 1, the chances add
        up to 1, and an outcome that cannot happen now (its condition fails) has no chance; else the
        run stops. The central run takes the likeliest outcome, the first in the file on a tie."""
        outcomes = rule.outcomes
        if len(outcomes) == 1 and outcomes[0].chance in (None, 'else'):
            return 0
        name = self.rule_name(rule, j)

        def stop(message):
            return SimulationError(
                message, [{'code': 'chances', 'severity': 'error', 'rule': name, 't': float(t)}]
            )

        chances, rest = [], None
        for place, item in enumerate(outcomes):
            if item.chance is None:
                chances.append(1.0)
            elif item.chance == 'else':
                chances.append(0.0)
                rest = place
            else:
                value = float(_one(self.value(item.chance, env)))
                if not math.isfinite(value) or value < -CHANCE_TOLERANCE or value > 1 + CHANCE_TOLERANCE:
                    raise stop(f'{name}.{item.name}: a chance is from 0 to 1, not {value:g}, at t={t:g} h')
                chances.append(min(max(value, 0.0), 1.0))
        if rest is not None:
            chances[rest] = max(0.0, 1.0 - sum(chances))
        total = sum(chances)
        if abs(total - 1.0) > CHANCE_TOLERANCE:
            raise stop(f'{name}: the chances of its outcomes add up to {total:g} at t={t:g} h, not 1')
        possible = []
        for place, item in enumerate(outcomes):
            can = item.available is None or bool(_one(self.value(item.available, env)))
            possible.append(can)
            if not can and chances[place] > CHANCE_TOLERANCE:
                raise stop(
                    f'{name}.{item.name}: an outcome that cannot happen now has the chance '
                    f'{chances[place]:g} at t={t:g} h'
                )
        controller = self.controller(rule, j)
        if controller is not None:
            # A chance is the model's estimate of what the actor does, which a pick replaces; the
            # condition under which an outcome can happen is not.
            return self.pick(rule, j, chances, possible, t, env, controller)
        if self.outcomes is not None:
            return self.taken(name, chances)
        if not self.luck:
            return max(range(len(chances)), key=lambda place: (chances[place], -place))
        # A sample of a study: one uniform number for each firing, from the stream of the event.
        if name not in self.streams:
            self.streams[name] = draws(self.luck['seed'], f'{name}/{self.luck["sample"]}')
        u, total, last = self.streams[name](), 0.0, None
        for place, chance in enumerate(chances):
            if chance <= 0:
                continue
            total, last = total + chance, place
            if u < total:
                return place
        return last

    def taken(self, name, chances):
        """The outcome of a firing of a run with given outcomes (`outcomes`): the given place, or
        the likeliest outcome after the last given place (the first in the file on a tie). The run
        keeps the firing as (the name of the rule, the chance with which a sample takes each
        outcome, the place taken). A given place is one that a sample can take."""
        found, at = shares(chances), len(self.firings)
        if at < len(self.outcomes):
            place = self.outcomes[at]
            if not 0 <= place < len(found) or found[place] <= 0:
                raise ValueError(f'{name}: no sample takes the outcome {place} of its firing number {at}')
        else:
            place = max(range(len(found)), key=lambda other: (found[other], -other))
        self.firings.append((name, tuple(found), place))
        return place

    def fire(self, rule, j, t, counted=False, own=False):
        """One step of a rule: the firing of the instance j at the time t."""
        plan = self.plan
        if not counted:
            self.count_step(t, rule, j)
        self.mark(rule.index, {j})
        env = Env(self, rule.space, np.array([j]), t)
        self.extras(rule, j, env, t, 'fire')
        outcomes = rule.outcomes
        outcome = outcomes[self.chosen(rule, env, j, t)]
        # Every value of the step is read before the step.
        writes = []

        def now(name, place):
            """The value of a quantity for one instance at the moment."""
            inner = Env(self, plan.space_of(name), np.array([place]), t)
            return float(_one(inner[name]))

        held = {}  # (quantity, place) -> its value in the step so far
        sets, modes, before, moved = {}, {}, {}, []  # what the entry of the trace says of the step

        def bounds(name, place):
            quantity = plan.quantities[name]
            return (
                quantity.lower,
                quantity.upper,
                float(self.slack[name][place]),
                float(self.atol[name][place]),
            )

        for target, node, mode in outcome.sets:
            place = self.place(rule.space, j, target)
            if node is None or target in plan.modes:
                value = mode if node is None else _one(self.value(node, env))
                if node is not None and value not in plan.modes[target]:
                    raise SimulationError(
                        f'{self.rule_name(rule, j)}: {target} cannot take the value {value!r}'
                    )
                modes[(target, place)], before[(target, place)] = value, self.v[target][place]
                if value != self.v[target][place]:
                    writes.append((target + ENTERED, place, t))
                writes.append((target, place, value))
                continue
            value = float(_one(self.value(node, env)))
            if not math.isfinite(value):
                raise SimulationError(f'{self.rule_name(rule, j)}: nonfinite value for {target}')
            if target in plan.quantities:
                # A value that misses a bound by less than the solver can resolve is on the bound, so
                # the next segment starts inside the domain.
                lower, upper, slack, atol = bounds(target, place)
                if lower - slack <= value < lower:
                    value = float(lower)
                elif upper < value <= upper + atol:
                    value = float(upper)
                held[(target, place)] = value
            else:
                writes.append((target, place, value))
            sets[(target, place)] = value
        moves = []
        for source, target, node in outcome.moves:
            amount = float(_one(self.value(node, env)))
            if not math.isfinite(amount) or amount < 0:
                raise SimulationError(
                    f'{self.rule_name(rule, j)}: a move takes a finite amount from 0, not {amount}'
                )
            moves.append(
                (
                    (source, self.place(rule.space, j, source)),
                    (target, self.place(rule.space, j, target)),
                    amount,
                )
            )
        if moves:
            # Every move must fit together with the values that the step sets: each quantity of a
            # move, and each that the step sets, stays inside its bounds.
            trial = dict(held)
            for source, target, amount in moves:
                for key, sign in ((source, -1.0), (target, 1.0)):
                    if key not in trial:
                        trial[key] = now(*key)
                    trial[key] += sign * amount
            for (name, place), value in trial.items():
                lower, upper, slack, atol = bounds(name, place)
                if not lower - slack <= value <= upper + atol:
                    raise SimulationError(
                        f'{self.rule_name(rule, j)}: a move does not fit: the stock holds less than the amount',
                        [
                            {
                                'code': 'transaction_failed',
                                'severity': 'error',
                                'rule': self.rule_name(rule, j),
                                'path': rule.path,
                            }
                        ],
                    )
        for source, target, asked in moves:
            for key in (source, target):
                if key not in held:
                    held[key] = now(*key)
            value, lower = held[source], bounds(*source)[0]
            amount = asked
            left = value - amount
            # A move that would leave less than the solver can resolve behind moves everything. A
            # stock that already sits below its bound by such an amount has nothing to move.
            if left != lower and abs(left - lower) <= bounds(*source)[3]:
                amount = amount + (left - lower)
                if amount >= 0:
                    left = lower
                else:
                    amount, left = 0.0, value
            held[source] = left
            value = held[target]
            held[target] = value + amount
            moved.append((source, target, amount))
        for (name, place), value in held.items():
            # The structure lets no step lower a tally; the run checks it all the same.
            if plan.quantities[name].monotone and value < now(name, place):
                raise SimulationError(f'A step decreases the nondecreasing quantity {name}')
        writes += [(name, place, value) for (name, place), value in held.items()]
        for name, place, value in writes:
            quantity = plan.quantities.get(name)
            if quantity is not None and not (
                quantity.lower - self.slack[name][place] <= value <= quantity.upper + self.atol[name][place]
            ):
                raise SimulationError(
                    f'{self.rule_name(rule, j)} at t={t:g} h leaves {name} outside its bounds',
                    [
                        {
                            'code': 'joint_feasibility',
                            'severity': 'error',
                            't': t,
                            'rules': [self.rule_name(rule, j)],
                        }
                    ],
                )
        self.emitted([*(rule.emits if own else ()), *outcome.emits], rule.space, j, t, writes)
        self.trace.append((float(t), rule.index, j, outcome.name))
        self.entry(rule, j, outcome, t, sets, modes, moved, before)
        self.apply(writes, t)
        self.snapshot(t, step=True)
        named = [(plan.rule_index[target], target) for target in outcome.fires if target in plan.rule_index]
        for at, (index, _) in enumerate(named):
            other = plan.rules[index]
            place = self.place(rule.space, j, other.name)
            if not self.can_trigger(index, place):
                continue
            if self.settled and self.controlled(index, place) and other.delay is None:
                # A decision that an event names waits until the independent work of the moment is
                # done; the events that the same line names after it wait behind it.
                self.continuations.append(
                    deque((k, self.place(rule.space, j, name)) for k, name in named[at:])
                )
                break
            waiting = len(self.continuations)
            self.trigger(other, place, t)
            if self.settled and len(self.continuations) > waiting:
                self.continuations[-1].extend(
                    (k, self.place(rule.space, j, name)) for k, name in named[at + 1 :]
                )
                break
