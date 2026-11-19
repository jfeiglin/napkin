"""Reachability (D16): what the runs of one effective configuration can reach, kept as proof metadata.

`reach(program, configuration)` finds, as a fixed point, which events can start and which values each
named state can take, each conclusion with its reason. A named state is a stored value of an enum or a
yes/no: a value of a template (one state for all its members, the union of what each can take), of the
root, or a local of an event (one state for all its occurrences). The analysis is conservative: a
condition that it cannot settle (on a number, a time, a rate) counts as one that can go either way, so
"cannot start" and "never takes this value" are proved, while "can start" says only that nothing rules
it out. It answers "this event cannot fire with the plant closed"; "it could have fired and did not"
is what a trace shows (D16). Nothing prunes a run by it. Ported from `napkin/model/lower/starts.py` of
commit 81b367b (`Acting`), on the parts of a program.

- **Start values.** A state starts at its initializer, and each member at its own value, or at the
  configuration's value of an input: a member written in place or a yes/no is that value; a draw of
  a categorical is each outcome of positive weight; a choice, each member of its enum; a read of
  another state, what that state can take; anything else, any value of its type.
- **Events.** An event can start when the setup starts it, when one of its triggers can fire (its
  condition can hold: a trigger exists once for each receiver, also before its event has started),
  or when a statement that can run starts it. A statement can run when the setup holds it, or when
  its event can start, its stage's guard can hold and its branches can lead to it: an `if` whose test
  can hold (or fail, for `else`), a case whose guard can hold and whose member the selector can give.
- **Values.** An assignment that can run gives its target what its value can be; the locals of an
  event that can start take their start values.
- **Conditions** are read as the set of the values that they can take: a member, a yes/no constant
  and a state by what they can be, a comparison of such sets member by member, the count of the
  occurrences of an event that cannot start as zero, `not`, `and`, `or` and `if` by their parts, and
  anything else as either value.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass

from ..core import expr as nodes
from . import parts as p
from .check import ROOT_OWNER, Resolver, Scope, owner_key
from .refs import Distribution, Draw, EnumValue, Formula, Path, Reduce

_COMPARE = {
    'eq': operator.eq,
    'ne': operator.ne,
    'lt': operator.lt,
    'le': operator.le,
    'gt': operator.gt,
    'ge': operator.ge,
}
EITHER = frozenset({False, True})


@dataclass(frozen=True)
class Reach:
    """What the runs of a configuration can reach. `events` maps each event's origin to (whether it
    can start, the reason); `states` maps each named state (`Valve.state`, `grinder.refill.status`,
    `mode` of the root) to {value: (whether it can take it, the reason)}, in the order of its type."""

    events: dict
    states: dict


def reach(program, configuration=None):
    """The reachability of a program under a configuration (its inputs; None for the program's own)."""
    return _Reach(program, configuration).run()


def _domain(value_type, program):
    """The values of a named state's type, or None for a type that is no named state."""
    if isinstance(value_type, p.EnumType):
        return program.enum(value_type.enum).members
    if isinstance(value_type, p.Bool):
        return (False, True)
    return None


class _Reach:
    def __init__(self, program, configuration):
        self.program = program
        self.resolver = Resolver(program)
        self.domains, self.found, self.started = {}, {}, {}
        self.changed = False
        overrides = {(item.member, item.name): item.value for item in getattr(configuration, 'inputs', ())}
        self.owners = []  # (scope, owner of the values, values, the members' own values)
        for template in program.templates:
            members = [
                {name: overrides.get((member.id, name), init) for name, init in member.values}
                | {name: value for (who, name), value in overrides.items() if who == member.id}
                for member in template.members
            ]
            self.owners.append((Scope(template), template.name, template.values, members))
            for event in template.events:
                values = [part for part in event.locals if isinstance(part, p.Value)]
                self.owners.append((Scope(template, event), event.origin, values, None))
        root = [{name: value for (who, name), value in overrides.items() if who == ''}]
        self.owners.append((Scope(), ROOT_OWNER, program.root, root))
        for _, owner, values, _ in self.owners:
            for value in values:
                domain = _domain(value.type, program)
                if domain is not None and value.kind in (p.STATE, p.INPUT):
                    self.domains[_key(owner, value.name)] = domain
                    self.found[_key(owner, value.name)] = {}

    # ---- the fixed point ---------------------------------------------------------------------------

    def run(self):
        """Start values, then the setup, the triggers and the stages of the events that can start,
        again until nothing more can be reached."""
        self.changed = True
        while self.changed:
            self.changed = False
            for scope, owner, values, members in self.owners:
                if scope.event is not None and scope.event.origin not in self.started:
                    continue
                for value in values:
                    key = _key(owner, value.name)
                    if key not in self.domains:
                        continue
                    inits = (
                        [value.init] if members is None else [m.get(value.name, value.init) for m in members]
                    )
                    for init in inits or [value.init]:
                        if init is not None:
                            self.add(key, self.values(init, scope), 'its start value')
            for statement in self.program.setup:
                self.statement(statement, Scope())
            for template in self.program.templates:
                for event in template.events:
                    for trigger in event.triggers:
                        if True in self.condition(trigger.test, Scope(template, trigger=trigger)):
                            self.start(event.origin, f'its trigger {trigger.origin} can fire')
                    if event.origin not in self.started:
                        continue
                    for step in event.steps:
                        scope = Scope(template, event)
                        if isinstance(step, p.After) and (
                            step.guard is None or True in self.condition(step.guard, scope)
                        ):
                            for statement in step.body:
                                self.statement(statement, scope)
        events = {
            event.origin: (True, self.started[event.origin])
            if event.origin in self.started
            else (
                False,
                'nothing that can happen starts it: no start of the setup, no trigger whose condition can hold, no statement that can run',
            )
            for template in self.program.templates
            for event in template.events
        }
        states = {
            key: {
                value: (True, self.found[key][value])
                if value in self.found[key]
                else (False, 'no start value and no assignment that can run gives it this value')
                for value in domain
            }
            for key, domain in self.domains.items()
        }
        return Reach(events, states)

    def start(self, event, reason):
        if event not in self.started:
            self.started[event] = reason
            self.changed = True

    def add(self, key, values, reason):
        for value in self.domains[key] if values is None else values:
            if value in self.domains[key] and value not in self.found[key]:
                self.found[key][value] = reason
                self.changed = True

    def statement(self, statement, scope):
        """What a statement that can run reaches: the values that it assigns, the events that it
        starts, and the statements of the branches that can be taken."""
        if isinstance(statement, p.Assign):
            key = self.state_of(statement.target, scope)
            if key is not None and not isinstance(statement.value, (Formula, Distribution, Path)):
                self.add(key, self.values(statement.value, scope), f'{statement.origin} sets it')
        elif isinstance(statement, p.Start):
            found = self.resolver.resolve(statement.event, scope, '')
            if found is not None and found.kind == 'event':
                self.start(found.part.origin, f'{statement.origin} starts it')
        elif isinstance(statement, p.If):
            test = self.condition(statement.test, scope)
            for body, taken in ((statement.then, True), (statement.orelse, False)):
                if taken in test:
                    for inner in body:
                        self.statement(inner, scope)
        elif isinstance(statement, p.Switch):
            selected = self.values(statement.selector, scope)
            fallback = selected is None or bool(set(selected) - {case.member for case in statement.cases})
            for case in statement.cases:
                guard = EITHER if case.guard is None else self.condition(case.guard, scope)
                fallback = fallback or False in guard
                if (selected is None or case.member in selected) and True in guard:
                    for inner in case.body:
                        self.statement(inner, scope)
            if fallback:
                for inner in statement.orelse:
                    self.statement(inner, scope)

    # ---- what an expression can be -----------------------------------------------------------------

    def state_of(self, path, scope):
        """The named state that a path names, or None."""
        found = self.resolver.resolve(path, scope, '')
        if found is None or found.kind != 'value' or found.many:
            return None
        key = _key(owner_key(found.owner), found.part.name)
        return key if key in self.domains else None

    def condition(self, expression, scope):
        """The yes/no values that a condition can take."""
        found = self.values(expression, scope)
        return EITHER if found is None else frozenset(found) & EITHER or EITHER

    def values(self, init, scope):
        """The values that an expression can take (a frozenset), or None for any value."""
        if isinstance(init, EnumValue):
            return frozenset({init.member})
        if isinstance(init, bool):
            return frozenset({init})
        if not hasattr(init, 'node'):
            return None
        return self.node(init.node, dict(init.reads), scope)

    def node(self, node, reads, scope):
        if isinstance(node, nodes.Const):
            return frozenset({node.value})
        if isinstance(node, nodes.Ref):
            return self.read(reads.get(node.name), scope)
        if isinstance(node, nodes.Compare) and len(node.ops) == 1:
            left, right = (self.node(side, reads, scope) for side in node.operands)
            if left is None or right is None:
                return None
            compare = _COMPARE[node.ops[0]]
            try:
                return frozenset(compare(a, b) for a in left for b in right)
            except TypeError:
                return None
        if isinstance(node, nodes.Unary) and node.op == 'not':
            found = self.node(node.operand, reads, scope)
            return None if found is None else frozenset(not value for value in found)
        if isinstance(node, nodes.BoolOp):
            found = [self.node(value, reads, scope) or EITHER for value in node.values]
            if node.op == 'and':
                true, false = all(True in each for each in found), any(False in each for each in found)
            else:
                true, false = any(True in each for each in found), all(False in each for each in found)
            return frozenset(value for value, can in ((True, true), (False, false)) if can)
        if isinstance(node, nodes.IfElse):
            test = self.node(node.test, reads, scope) or EITHER
            sides = [
                self.node(side, reads, scope)
                for side, taken in ((node.body, True), (node.orelse, False))
                if taken in test
            ]
            return None if any(side is None for side in sides) else frozenset().union(*sides)
        return None

    def read(self, read, scope):
        """What one read can be: a member of an enum, a named state, the count of the occurrences of
        an event that cannot start, a draw of a categorical; anything else (a choice among them) may
        be any value."""
        if isinstance(read, EnumValue):
            return frozenset({read.member})
        if isinstance(read, Path):
            key = self.state_of(read, scope)
            return None if key is None else frozenset(self.found[key])
        if isinstance(read, Reduce) and read.op in ('count', 'any'):
            found = self.resolver.resolve(read.source, scope, '')
            while found is not None and found.kind != 'occurrence':
                found = found.of
            if found is not None and found.part.origin not in self.started:
                return frozenset({0 if read.op == 'count' else False})
            return None
        if isinstance(read, Draw):
            source = read.source
            if isinstance(source, Path):
                found = self.resolver.resolve(source, scope, '')
                source = getattr(found.part, 'init', None) if found is not None else None
            if isinstance(source, Distribution) and source.family == 'categorical':
                return frozenset(name for name, weight in zip(source.outcomes, source.params) if weight > 0)
        return None


def _key(owner, name):
    return f'{owner}.{name}' if owner else name
