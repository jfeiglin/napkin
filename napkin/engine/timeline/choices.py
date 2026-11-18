"""A played run: who picks, the picks, the decision that waits, and the pause.

Moved from `run.py` with no change (step B0-6). `Choices` is a part of `run.Run`: its methods
read the run as `self`.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from ...core import expr
from ..errors import SimulationError
from .state import FIRE, SEEN, TRIGGER, Seen, _one


class View(Seen):
    """What the resolver of a decision reads: the inputs, the quantities, the states with the times
    at which they were taken, the counts and the times of the events, and the formulas and the
    statuses of the model by their names, at the time of the decision."""

    def names(self):
        plan = self.env.run.plan
        return [name for name, kind in plan.kind.items() if kind in SEEN and name not in plan.outputs]

    def __getitem__(self, name):
        env = self.env
        plan = env.run.plan
        if name != 't' and (plan.kind.get(name) not in SEEN or name in plan.outputs):
            raise KeyError(name)
        if name != 't' and plan.kind[name] == 'formula':
            # A formula or a status has no value of its own in the run: it is its expression.
            return _one(env.run.value(plan.node(expr.ref(name), env.space, f'the formula {name}'), env))
        return _one(env[name])

    def __contains__(self, name):
        plan = self.env.run.plan
        return name == 't' or (plan.kind.get(name) in SEEN and name not in plan.outputs)

    def __iter__(self):
        return iter(('t', *self.names()))

    def __len__(self):
        return 1 + len(self.names())


class Pause(Exception):
    """A decision of a played run waits for a pick: the run stops before the step of that decision."""


class Choices:
    """See the module."""

    def controller(self, rule, j):
        """Who picks the outcomes of a rule in a played run (`reader` or `agent`), or None when chance
        takes them. The control of the run gives the method of a choice: by the event (`actor.event`,
        or the event of the set of copies of the actor), else by the actor (its name, or the name of
        its set of copies). `chance` is the default."""
        if not self.control or not rule.choice:
            return None
        key = (rule.index, j)
        if key not in self.controllers:
            name = self.rule_name(rule, j)
            found = None
            if self.decision_events is None or name in self.decision_events:
                origin = getattr(self.plan.s.entities.get(rule.entity), 'origin', None)
                event = name.rsplit('.', 1)[1]
                for item in (name, origin and f'{origin}.{event}', self.flat_entity(rule, j), origin):
                    if item and item in self.control:
                        found = None if self.control[item] == 'chance' else self.control[item]
                        break
            self.controllers[key] = found
        return self.controllers[key]

    def controlled(self, index, place):
        return self.controller(self.plan.rules[index], place) is not None

    def pick(self, rule, j, chances, possible, t, env, controller):
        """The outcome of a played decision: the next pick of the log, which must answer this
        decision with an outcome that can happen. With no pick left, the run asks for one (`decision`,
        the first that waits) and stops there, or goes on with the choice of the model."""
        name = self.rule_name(rule, j)
        names = [outcome.name for outcome in rule.outcomes]
        if self.picked >= len(self.picks):
            pending = self.decision or self.ask(rule, j, possible, t, env)
            if self.decision_resolver is not None:
                given = self.decision_resolver(
                    {**pending, 'pick_index': self.picked},
                    View(env),
                    tuple(MappingProxyType(self.entry_at(k)) for k in range(len(self.log))),
                )
                if given is not None:
                    if not isinstance(given, Mapping):
                        raise SimulationError('decision_resolver must return a pick mapping or None')
                    self.picks.append(dict(given))
            if self.picked >= len(self.picks):
                self.decision = pending
                if self.pause_at_decision:
                    raise Pause
                return max(range(len(chances)), key=lambda place: (chances[place], -place))
        given = self.picks[self.picked]
        where = {'code': 'pick', 'severity': 'error', 'rule': name, 't': t, 'pick': self.picked}
        if given.get('event') != name or given.get('outcome') not in names:
            raise SimulationError(
                f'Pick {self.picked + 1} answers {given.get("event")} with {given.get("outcome")}, '
                f'but the run asks {name} ({", ".join(names)}) at t={t:g} h: the picks belong to '
                'another run',
                [where],
            )
        k = names.index(given['outcome'])
        if not possible[k]:
            raise SimulationError(f'{name}: {given["outcome"]} cannot happen at t={t:g} h', [where])
        self.picked += 1
        self.picking = controller
        return k

    def happened(self, k, event):
        """Whether the step k of the trace is a time that `event` happened: the event of a rule (when
        it triggers) or of one of its outcomes. A rule without a delay fires as it triggers: its
        firing is its own event too."""
        entry = self.entry_at(k)
        if entry['event'] == event:
            return True
        waits = self.plan.rules[self.log[k][2]].delay is not None
        return entry['rule'] == event and entry['outcome'] is not None and not waits

    def ask(self, rule, j, possible, t, env):
        """What a decision that waits for a pick shows: its time, thing, event and text, its outcomes
        and which can happen, and what its actor sees: the value of each fact (`view`: of a field, in
        its unit, or how many times an event has happened) and the times its events happened."""
        plan = self.plan
        view, units, seen = {}, {}, set()

        def flat(name):
            space = plan.space_of(name)
            return self.rule_free_name(name, space, j) if space == rule.space else name

        for fact in plan.sees.get(rule.entity, ()):
            name = flat(fact.name)
            if fact.event is not None:
                found = [i for i in range(len(self.log)) if self.happened(i, flat(fact.event))]
                view[name] = len(found)
                seen.update(found)
                continue
            value = _one(self.value(fact.node, env))
            if fact.kind == 'choice':
                value = fact.values[int(value)]
            elif fact.kind == 'bool':
                value = bool(value)
            elif fact.kind == 'number':
                value = float(value) / (self.registry.scale(fact.unit) if fact.unit else 1.0)
                units[name] = fact.unit
            view[name] = value
        return {
            't': float(t),
            'thing': self.flat_entity(rule, j),
            'event': self.rule_name(rule, j),
            'text': rule.label,
            'outcomes': [
                {'name': outcome.name, 'text': outcome.label, 'available': possible[k]}
                for k, outcome in enumerate(rule.outcomes)
            ],
            'view': view,
            'units': units,
            'seen': [
                {
                    key: self.entry_at(i)[name]
                    for key, name in (('t', 't'), ('event', 'event'), ('text', 'label'))
                }
                for i in sorted(seen)
            ],
            'pick': self.picked,
            'by': self.controller(rule, j),
        }

    def next_settled(self):
        """The next step of a moment of a played run that settles the independent work first
        (`settled_decisions`): (whether a line named it, rule, instance), or None. A due rule is
        independent when no actor that the run controls decides its step: a firing of a rule that
        chance takes, or a trigger of such a rule or of a rule with a delay. An event that a line
        named cannot pass the first controlled event of its line; the other independent work of the
        moment goes first, and then the controlled steps in the order of the file."""
        plan = self.plan
        due, seen = [], set()
        for key, index, j in sorted(self.ready):
            if self.rules[index].ready[j] and (index, j) not in seen:
                seen.add((index, j))
                due.append((key, index, j))
        self.ready = list(due)
        independent = None
        for _, index, j in due:
            kind, controlled = int(self.rules[index].ready[j]), self.controlled(index, j)
            waits = plan.rules[index].delay is not None
            if (kind == FIRE and not controlled) or (kind == TRIGGER and (not controlled or waits)):
                independent = (False, index, j)
                break
        waiting = []
        for chain in self.continuations:
            while chain and not self.can_trigger(*chain[0]):
                chain.popleft()
            if chain:
                index, place = chain[0]
                if not self.controlled(index, place) or plan.rules[index].delay is not None:
                    return True, index, place
                rule = plan.rules[index]
                positions, copies = self.order[index]
                key = (rule.line, int(positions[place]), int(copies[place]), index)
                waiting.append((key, 0, True, index, place))
        self.continuations = [chain for chain in self.continuations if chain]
        if independent is not None:
            return independent
        if due:
            # An event that a line named and that is also due by its own condition goes as the
            # line named it, once: the named one is first of the two.
            waiting.append((due[0][0], 1, False, due[0][1], due[0][2]))
        if not waiting:
            return None
        return min(waiting)[2:]
