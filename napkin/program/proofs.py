"""Proofs over a program and a configuration (D10, D16): that a value never falls over a run, and the
parts that a value reads. Each conclusion has its reason. A report reads both: a reporting lag is valid
only when its value never falls, and its evidence trail lists what a value read.

**Never falls** (`never_falls(program, configuration, key)`). A proof covers every way that the value
can change (spec, "What a proof establishes"). It is conservative: what it cannot settle counts as a
fall, so "never falls" is proved, while "can fall" says only that nothing proved otherwise. The rules
are the cumulative rules of the old `napkin/model/analysis/values.py` (`quantity_claims`), on the
parts of a program, member by member.

- An input, a link and a constant are fixed for the run.
- A formula is written as a linear form, where its arithmetic allows it. The terms are stored numbers,
  each of one member (`this.water` of the member that reads it, `sum(Utility.instances.unserved)` of
  every member), the time, and the counts of the occurrences of an event (all of them, or those done).
  The form admits sums, differences, products and quotients by fixed numbers, a conditional on what is
  fixed, and the formulas that it reads, each in its own member. A member that a `where`, a lookup on
  a fixed key or an entity parameter names may be any member of its collection, or none of them: its
  coefficient may be its own or zero.
- Every writer of each stored number of the form must leave the form from falling. A directed flow
  moves `rate * (coefficient of its sink - coefficient of its source)` at a rate that is never
  negative, so its sink's coefficient must be at least its source's (`SOURCE` and `SINK` count zero).
  A route moves either way, so its ends need one coefficient. A move takes an amount from zero, as a
  flow does. `+=` and `-=` need the sign of what they add, and `=` or a declared solver that
  determines the value can set anything. So a flow from one counted store to another cancels:
  `infected + recovered` never falls while people recover. A tally, a store that nothing drains, is
  known by its use (change 14). The time and a count of occurrences need a coefficient from zero.
- The writers are every flow of every member, every flow of every event on every receiver, every
  statement of every stage, and every solver, so a shared store that another occurrence can drain is
  covered by the flow or the move that drains it. An event that cannot start under the configuration
  (`reach`) writes nothing, and the reason says so. The setup writes at time 0, in round zero, before
  any read of the run (a read at a time takes the last value at that time), so it is no writer.
- What the linear form does not cover is proved by its parts: `min`, `max` and a sum of what never
  falls, a product by a fixed number from zero and a quotient by a fixed positive number.
- A formula that a stage or the setup can give a new definition can fall, and so can a rate of a flow,
  a solver's unknown, `since`, `elapsed`, a keyed read whose key moves, and any other read.

**What a value reads** (`reads(program, configuration, key)`): the parts that the value can depend
on, each as one member runs it (`Part`), with the parts that each of them reads. It starts at a named
value, at the flow of a field of a flow, or at a member's status display, which reads what its
cases read. A stored value reads
its starting value, its bounds and its writers; a formula, what its expression reads; a flow, its
request and its capacity, its ends, the settings of the endpoints at its ends, and the other flows
there, which share them; a stage, its guard, its statements and the stores of its moves, and its
event; an event, its triggers
and the stages that start it; a trigger, its condition; a solver, its inputs, its constraints and its
objectives. An event that cannot start under the configuration is `blocked`, with the reason (D16:
"this event cannot fire with the plant closed"); what a run exercised is the record's to say.

`Proofs(program, configuration)` finds the writers and the reachability of a program once, for each
key that a caller asks about (`never_falls`, `reads`); the functions of the same names make one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core import expr as nodes
from ..core.errors import ExpressionError
from ..core.evaluation import checked_value
from ..core.units import UnitSystem
from . import parts as p
from .reach import reach
from .refs import (
    By,
    Choice,
    Distribution,
    Draw,
    Elapsed,
    EnumValue,
    Formula,
    Instances,
    Literal,
    Local,
    Lookup,
    Named,
    Path,
    Reduce,
    Root,
    Since,
    This,
    Time,
    Where,
    spelled,
)

TIME_TERM = ('t',)  # the term of the time in a linear form


@dataclass(frozen=True)
class Proof:
    """A conclusion of a proof: whether it holds, and why."""

    holds: bool
    reason: str


@dataclass(frozen=True)
class Part:
    """A part of a program as one member runs it: its kind (`value`, `flow`, `stage`, `event`,
    `trigger`, `solver` or `status`), its origin, and its owner: the member that runs it, `''` for the root, or
    for a value of an event's occurrences the receiver and the event (`tank.receive#`)."""

    kind: str
    origin: str
    owner: str = ''


@dataclass(frozen=True)
class Reads:
    """What a value reads: from `start`, each part with the parts that it reads (`edges`), and each
    event that cannot start under the configuration, with the reason (`blocked`)."""

    start: Part
    edges: dict = field(default_factory=dict)
    blocked: dict = field(default_factory=dict)


def never_falls(program, configuration, key):
    """Whether the value of a record key (`record.Key`) never falls over a run of the program under the
    configuration (None for the program's own inputs), with the reason (see the module)."""
    return Proofs(program, configuration).never_falls(key)


def reads(program, configuration, key):
    """What the value of a record key reads (`Reads`, see the module)."""
    return Proofs(program, configuration).reads(key)


class _Fall(Exception):
    """What can make a value fall, or what the proof cannot settle: the reason."""


class _Nonlinear(Exception):
    """A part of an expression that a linear form does not write."""


@dataclass(frozen=True, eq=False)
class _At:
    """Where an expression is read: its template and member (none for the root), and the event,
    trigger or solver whose bare names it reads."""

    template: p.Template | None = None
    member: p.Member | None = None
    event: p.Event | None = None
    trigger: p.Trigger | None = None
    solver: p.Solver | None = None

    @property
    def owner(self):
        """The owner of the values of the scope: the member, the root, or the event's occurrences on
        the member."""
        if self.member is None:
            return ''
        return f'{self.member.id}.{self.event.name}#' if self.event is not None else self.member.id


@dataclass(eq=False)
class _Writer:
    """A part that changes stored numbers: a directed `flow`, a `route`, an `assign`ment, a `move` or
    a `solver`; the keys of what it takes from (`sources`) and gives to (`sinks`), each with whether
    it is the one (True) or one of several (False); the event that it belongs to, and the part of
    the evidence trail that it is (`part`)."""

    kind: str
    origin: str
    part: Part
    sources: tuple = ()
    sinks: tuple = ()
    op: str = ''
    value: object = None
    at: _At | None = None
    event: str | None = None


def _added(left, right):
    found = dict(left)
    for term, (lo, hi) in right.items():
        low, high = found.get(term, (0.0, 0.0))
        found[term] = (low + lo, high + hi)
    return {term: bounds for term, bounds in found.items() if bounds != (0.0, 0.0)}


def _scaled(form, factor):
    factor = float(factor)
    return {
        term: (min(lo * factor, hi * factor), max(lo * factor, hi * factor))
        for term, (lo, hi) in form.items()
        if factor != 0
    }


def _widened(form):
    """A form of a member that may not be counted: each coefficient its own or zero."""
    return {term: (min(lo, 0.0), max(hi, 0.0)) for term, (lo, hi) in form.items()}


def _sign_of(number):
    return 1 if number > 0 else -1 if number < 0 else 0


class Proofs:
    """The proofs of one program under one configuration (see the module), which find the writers and
    the reachability of the program once for every key that they are asked about."""

    def __init__(self, program, configuration):
        self.program = program
        self.rows = {
            member.id: (template, member) for template in program.templates for member in template.members
        }
        self.given = {(item.member, item.name): item.value for item in getattr(configuration, 'inputs', ())}
        self.units = UnitSystem(
            {
                unit.name: {'dimensions': dict(unit.dimension), 'scale': float(unit.scale)}
                for unit in program.units
            }
        )
        self.events = reach(program, configuration).events
        self._index = None

    # ---- paths, member by member ----------------------------------------------------------------------

    def points(self, path, at, moving=False):
        """What a path names, member by member: [(point, whether it is the one)]. A point is a tuple
        whose first item is its kind: `member`, `root`, `value` (owner, part, scope), `flow` (owner,
        flow, scope), `leg` of a route, `rate` (a property of a flow), `event`, `occurrences`,
        `occurrence`, `solver` or `other` (a description). A lookup whose key moves is `other`, but
        with `moving`, which a writer's target takes, its members."""
        found = self._start(path.start, at, moving)
        for step in path.steps:
            found = [(after, one and also) for point, one in found for after, also in self._step(point, step)]
        return found

    def _start(self, start, at, moving):
        if isinstance(start, This):
            return [(('member', at.template, at.member), True)]
        if isinstance(start, Root):
            return [(('root',), True)]
        if isinstance(start, Named):
            template, member = self.rows[start.id]
            return [(('member', template, member), True)]
        if isinstance(start, Local):
            return self._local(start.name, at)
        if isinstance(start, Instances):
            template = self.program.template(start.template)
            return [(('member', template, member), True) for member in template.members]
        if isinstance(start, Literal):
            return [found for item in start.items for found in self.points(item, at, moving)]
        if isinstance(start, By):
            return self.points(start.source, at, moving)
        if isinstance(start, Where):
            return [(point, False) for point, _ in self.points(start.source, at, moving)]
        if isinstance(start, Lookup):
            if not moving and not self.fixed(start.key.node, dict(start.key.reads), at):
                return [(('other', 'a keyed read whose key moves, which can select a smaller value'), True)]
            # One member of the collection, or the newest occurrence of an event.
            return [
                (
                    ('occurrence', *point[1:4]) if point[0] == 'occurrences' and point[4] is None else point,
                    False,
                )
                for point, _ in self.points(start.source, at, moving)
            ]
        return [(('other', 'the member of a where'), True)]

    def _local(self, name, at):
        """A bare name: an input or an unknown of a solver, a capture of a trigger, or a parameter, a
        local or a flow of an event."""
        if at.solver is not None:
            for binding in at.solver.inputs:
                if binding.name == name:
                    return self.points(binding.source, _At(at.template, at.member))
            if any(unknown.name == name for unknown in at.solver.unknowns):
                return [(('other', f'{name}, an unknown of {at.solver.origin}'), True)]
        if at.trigger is not None and any(capture.name == name for capture in at.trigger.captures):
            return [(('other', f'{name}, a capture of {at.trigger.origin}'), True)]
        if at.event is not None:
            for part in (*at.event.params, *at.event.locals):
                if part.name != name:
                    continue
                if isinstance(part, p.Value) and isinstance(part.type, p.EntityType):
                    # An entity parameter can pass any member of its template (D13).
                    template = self.program.template(part.type.template)
                    return [(('member', template, member), False) for member in template.members]
                kind = 'value' if isinstance(part, p.Value) else 'flow'
                return [((kind, at.owner, part, at), True)]
        return [(('other', f'the bare name {name}'), True)]

    def _step(self, point, name):
        kind = point[0]
        if kind == 'root':
            part = self.program.root_value(name)
            return [(('value', '', part, _At()), True)] if part is not None else [(('other', name), True)]
        if kind == 'member':
            _, template, member = point
            part = template.part(name) if template is not None else None
            at = _At(template, member)
            if isinstance(part, p.Value):
                if part.kind == p.LINK:
                    target = self.program.template(part.type.template)
                    return [(('member', target, target.members[member.link(name)]), True)]
                if part.kind == p.COLLECTION:
                    return self.points(member.value(name) or part.init, at, True)
                return [(('value', member.id, part, at), True)]
            if isinstance(part, p.Flow):
                return [(('flow', member.id, part, at), True)]
            if isinstance(part, p.Event):
                return [(('event', template, member, part), True)]
            if isinstance(part, p.Solver):
                return [(('solver', template, member, part), True)]
            return [(('other', name), True)]
        if kind == 'flow':
            _, owner, flow, at = point
            if name in ('source', 'sink'):
                end = getattr(flow, name)
                return [] if isinstance(end, p.Outside) else self.points(end, at, True)
            if name in ('forward', 'backward'):
                return [(('leg', owner, flow, at, name), True)]
            for leg in flow.legs:
                if leg.name == name:
                    return [(('flow', owner, leg, at), True)]
            return [(('rate', owner, flow, name, at), True)]
        if kind == 'leg':
            _, owner, flow, at, side = point
            if name in ('source', 'sink'):
                end = flow.source if (side == 'forward') == (name == 'source') else flow.sink
                return self.points(end, at, True)
            return [(('rate', owner, flow, name, at), True)]
        if kind == 'event':
            return (
                [(('occurrences', *point[1:], None), True)]
                if name == 'occurrences'
                else [(('other', name), True)]
            )
        if kind == 'occurrences' and point[4] is None:
            return [(('occurrences', *point[1:4], name), True)]
        if kind == 'occurrence':
            _, template, member, event = point
            for part in (*event.params, *event.locals):
                if part.name == name:
                    at = _At(template, member, event)
                    return [(('value' if isinstance(part, p.Value) else 'flow', at.owner, part, at), True)]
        if kind == 'value':
            return [(('other', f'{point[2].origin}.{name}, a setting or a property of a value'), True)]
        if kind == 'other':
            return [(point, True)]  # what follows a part that the proof does not follow
        return [(('other', f'{name} of {kind}'), True)]

    def fixed(self, node, reads, at):
        """Whether an expression reads only what is fixed for the run: constants, inputs and links."""
        for name in nodes.names(node):
            read = reads.get(name)
            if isinstance(read, EnumValue):
                continue
            if not isinstance(read, Path):
                return False
            found = self.points(read, at)
            if len(found) != 1 or found[0][0][0] not in ('value', 'member'):
                return False
            if found[0][0][0] == 'value' and found[0][0][2].kind not in (p.INPUT, p.LINK):
                return False
        return True

    # ---- fixed values and signs -----------------------------------------------------------------------

    def constant(self, node, reads, at, depth=0):
        """The value of an expression that reads only what is fixed for the run, in canonical units, or
        None: an input that is drawn has no value known before the run."""
        environment = {}
        for name in nodes.names(node):
            read = reads.get(name)
            if isinstance(read, EnumValue):
                environment[name] = read.member
                continue
            if not isinstance(read, Path) or depth > 50:
                return None
            found = self.points(read, at)
            if len(found) != 1 or found[0][0][0] != 'value' or found[0][0][2].kind != p.INPUT:
                return None
            value = self.input_value(found[0][0], depth + 1)
            if value is None:
                return None
            environment[name] = value
        try:
            return checked_value(node, environment, self.units)
        except (ExpressionError, ArithmeticError, ValueError, TypeError, KeyError):
            return None

    def input_value(self, point, depth=0):
        """The value of an input: the configuration's, or its default when that is fixed."""
        _, owner, part, at = point
        given = self.given.get((owner, part.name))
        if given is not None:
            if isinstance(given, (bool, str)):
                return given
            if isinstance(given, EnumValue):
                return given.member
            if isinstance(given, Distribution):
                return None
            unit = given.unit if isinstance(given.unit, p.Unit) else self.program.unit(given.unit)
            return float(given.number) * float(unit.scale)
        init = at.member.value(part.name) if at.member is not None and at.event is None else None
        init = init if init is not None else part.init
        if init is None or not hasattr(init, 'node'):
            return None
        return self.constant(init.node, dict(init.reads), at, depth)

    def sign(self, node, reads, at):
        """1 for a value that is never negative, -1 for one never positive, 0 for zero, None when the
        proof does not know: from a fixed value, a bound of a stored number (the run keeps a store in
        its bounds; it checks an input's range only when the configuration sets it, and then its value
        is fixed), and the signs of the parts of the arithmetic."""
        found = self.constant(node, reads, at)
        if isinstance(found, (int, float)) and not isinstance(found, bool):
            return _sign_of(found)
        if isinstance(node, nodes.Ref):
            read = reads.get(node.name)
            points = self.points(read, at) if isinstance(read, Path) else ()
            if len(points) == 1 and points[0][0][0] == 'value' and points[0][0][2].kind == p.STATE:
                _, _, part, place = points[0][0]
                for bound, sign in ((part.lower, 1), (part.upper, -1)):
                    limit = None if bound is None else self.constant(bound.node, dict(bound.reads), place)
                    if isinstance(limit, (int, float)) and sign * limit >= 0:
                        return sign
            return None
        if isinstance(node, nodes.Unary) and node.op in ('neg', 'pos'):
            inner = self.sign(node.operand, reads, at)
            return None if inner is None else -inner if node.op == 'neg' else inner
        if isinstance(node, nodes.Binary) and node.op in ('add', 'sub', 'mul', 'div'):
            left, right = self.sign(node.left, reads, at), self.sign(node.right, reads, at)
            if node.op == 'sub':
                right = None if right is None else -right
            if node.op in ('mul', 'div'):
                if left == 0 or (right == 0 and node.op == 'mul'):
                    return 0
                return None if left is None or right is None else left * right
            if left == 0 or right == 0:
                return right if left == 0 else left
            return left if left == right else None
        if isinstance(node, nodes.Call) and node.function in ('max', 'min', 'abs', 'sum'):
            signs = [self.sign(arg, reads, at) for arg in node.args]
            if node.function == 'abs':
                return 1
            if node.function == 'max' and any(sign in (0, 1) for sign in signs):
                return 1
            if node.function == 'min' and any(sign in (0, -1) for sign in signs):
                return -1
            known = set(signs)
            return known.pop() if len(known) == 1 and None not in known else None
        return None

    # ---- the writers of the program ----------------------------------------------------------------------

    def index(self):
        """The writers of each stored number by its key, the definitions that stages give each
        formula, the parts that start each event on each receiver, and each flow, stage and trigger
        by its part (`_Index`), found once."""
        if self._index is not None:
            return self._index
        found = _Index()
        for template in self.program.templates:
            for member in template.members:
                at = _At(template, member)
                for flow in template.flows:
                    self._flow(flow, at, None, found)
                for event in template.events:
                    inner = _At(template, member, event)
                    for local in event.locals:
                        if isinstance(local, p.Flow):
                            self._flow(local, inner, event.origin, found)
                    for step in event.steps:
                        if isinstance(step, p.After):
                            stage = Part('stage', step.origin, member.id)
                            found.stages[stage] = (step, inner)
                            self._statements(step.body, inner, stage, event.origin, found)
                    for trigger in event.triggers:
                        fired = Part('trigger', trigger.origin, member.id)
                        found.triggers[fired] = (trigger, _At(template, member, trigger=trigger))
                        found.starters.setdefault(Part('event', event.origin, member.id), []).append(fired)
                for solver in template.solvers:
                    part = Part('solver', solver.origin, member.id)
                    targets = tuple(each for target in solver.solve_for for each in self._ends(target, at))
                    writer = _Writer(
                        'solver', solver.origin, part, sinks=targets, at=_At(template, member, solver=solver)
                    )
                    found.solvers[part] = solver
                    for key, _ in targets:
                        found.writers.setdefault(key, []).append(writer)
        self._statements(self.program.setup, _At(), Part('stage', 'setup'), None, found, setup=True)
        self._index = found
        return found

    def _ends(self, end, at):
        """The keys of the stored numbers that a flow's end, a move's end or a target names."""
        if isinstance(end, p.Outside):
            return []
        return [
            ((point[1], point[2].name), one)
            for point, one in self.points(end, at, True)
            if point[0] == 'value'
        ]

    def _flow(self, flow, at, event, found):
        """The writer of a flow of a member or of an event on a receiver; a flow with legs is its legs."""
        if flow.kind == p.LEGS:
            for leg in flow.legs:
                self._flow(leg, at, event, found)
            return
        part = Part('flow', flow.origin, at.member.id)
        kind = 'route' if flow.kind == p.REVERSIBLE else 'flow'
        writer = _Writer(
            kind, flow.origin, part, tuple(self._ends(flow.source, at)), tuple(self._ends(flow.sink, at))
        )
        writer.value, writer.at, writer.event = flow, at, event
        found.flows[part] = writer
        for key, _ in (*writer.sources, *writer.sinks):
            found.writers.setdefault(key, []).append(writer)

    def _statements(self, statements, at, stage, event, found, setup=False):
        """The writers, the definitions and the starts of the statements of a stage. The setup writes
        at time 0, before any read of the run, so only its definitions and starts count."""
        for statement in statements:
            if isinstance(statement, p.Assign):
                if isinstance(statement.value, Formula):
                    for key, _ in self._ends(statement.target, at):
                        found.defines.setdefault(key, []).append((statement.origin, event))
                elif not setup and not isinstance(
                    statement.value, (p.Priority, p.Proportional, Distribution, Path)
                ):
                    targets = tuple(self._ends(statement.target, at))
                    writer = _Writer('assign', statement.origin, stage, sinks=targets, op=statement.op)
                    writer.value, writer.at, writer.event = statement.value, at, event
                    for key, _ in targets:
                        found.writers.setdefault(key, []).append(writer)
            elif isinstance(statement, p.Move) and not setup:
                source, destination = self._ends(statement.source, at), self._ends(statement.destination, at)
                writer = _Writer('move', statement.origin, stage, tuple(source), tuple(destination))
                writer.at, writer.event = at, event
                for key, _ in (*writer.sources, *writer.sinks):
                    found.writers.setdefault(key, []).append(writer)
            elif isinstance(statement, p.Start):
                for point, _ in self.points(statement.event, at, True):
                    if point[0] == 'event':
                        found.starters.setdefault(Part('event', point[3].origin, point[2].id), []).append(
                            stage
                        )
            elif isinstance(statement, p.If):
                for body in (statement.then, statement.orelse):
                    self._statements(body, at, stage, event, found, setup)
            elif isinstance(statement, p.Switch):
                for body in (*(case.body for case in statement.cases), statement.orelse):
                    self._statements(body, at, stage, event, found, setup)

    def blocked(self, event):
        """The reason why an event cannot start under the configuration, or None."""
        if event is None:
            return None
        can, reason = self.events.get(event, (True, ''))
        return None if can else reason

    # ---- never falls ------------------------------------------------------------------------------------

    def point_of(self, key):
        """The value point of a record key, or _Fall."""
        point = self.value_point(key.owner, key.steps[0]) if len(key.steps) == 1 else None
        if point is None:
            name = '.'.join((key.owner, *key.steps)) if key.owner else '.'.join(key.steps)
            raise _Fall(
                f'{name} is no named number: a rate, a setting or a field of a flow follows its sharing, '
                'which can fall'
            )
        return point

    def value_point(self, owner, name):
        """The point of a value of an owner: a member, the root (`''`), or the occurrences of an event
        on a receiver (`tank.receive#`, `tank.receive#0`); None when it has no such value."""
        if '#' in owner:
            receiver, event_name = owner.rsplit('#', 1)[0].rsplit('.', 1)
            template, member = self.rows[receiver]
            event = template.part(event_name)
            at = _At(template, member, event)
            part = next((each for each in (*event.params, *event.locals) if each.name == name), None)
        elif owner:
            template, member = self.rows[owner]
            part, at = template.part(name), _At(template, member)
        else:
            part, at = self.program.root_value(name), _At()
        return ('value', at.owner, part, at) if isinstance(part, p.Value) else None

    def never_falls(self, key):
        """Whether the value of a record key never falls over a run, with the reason (`Proof`)."""
        try:
            return Proof(True, self.value(key))
        except _Fall as fall:
            return Proof(False, str(fall))

    def value(self, key):
        """Why the value of a key never falls, or _Fall."""
        point = self.point_of(key)
        part = point[2]
        if part.kind in (p.INPUT, p.LINK):
            return 'it is fixed for the run'
        if not isinstance(part.type, p.Number):
            raise _Fall(f'{part.origin} is no number: only a number is averaged over a window')
        return self.rises([(point, True)], frozenset())

    def rises(self, points, seen):
        """Why what some points name never falls (their linear form, else their parts), or _Fall."""
        try:
            form = self.points_form(points, seen)
        except _Nonlinear:
            pass
        else:
            return self.check(form)
        reasons = []
        for point, _ in points:
            if point[0] == 'value' and point[2].kind == p.FORMULA:
                init = self.formula_init(point, seen)
                inner = seen | {(point[1], point[2].name)}
                reasons.append(self.parts_rise(init.node, dict(init.reads), point[3], inner))
            else:
                reasons.append(self.check(self.point_form(point, seen)))
        return '; '.join(dict.fromkeys(reasons))

    def parts_rise(self, node, reads, at, seen):
        """Why an expression that no linear form writes never falls, by its parts, or _Fall."""
        try:
            return self.check(self.linear(node, reads, at, seen))
        except _Nonlinear:
            pass
        parts = None
        if isinstance(node, nodes.Call) and node.function in ('min', 'max', 'sum'):
            parts = node.args
        elif isinstance(node, nodes.Binary) and node.op == 'add':
            parts = (node.left, node.right)
        elif isinstance(node, nodes.Binary) and node.op == 'sub' and self.fixed(node.right, reads, at):
            parts = (node.left,)
        elif isinstance(node, nodes.Binary) and node.op in ('mul', 'div'):
            sides = (
                [(node.right, node.left)]
                if node.op == 'div'
                else [(node.left, node.right), (node.right, node.left)]
            )
            for factor, operand in sides:
                value = self.constant(factor, reads, at)
                if _number(value) and (value > 0 or (value == 0 and node.op == 'mul')):
                    parts = (operand,)
                    break
        elif isinstance(node, nodes.IfElse) and self.fixed(node.test, reads, at):
            test = self.constant(node.test, reads, at)
            if isinstance(test, bool):
                parts = (node.body if test else node.orelse,)
        elif isinstance(node, nodes.Ref):
            read = reads.get(node.name)
            if isinstance(read, Reduce) and read.op in ('min', 'max', 'sum'):
                return self.rises(self.points(read.source, at), seen)
            if isinstance(read, Path):
                return self.rises(self.points(read, at), seen)
        if parts is None:
            raise _Fall(
                f'{nodes.text(node)} can fall: the proof covers sums, differences, min, max, and products '
                'and quotients by fixed numbers of what never falls'
            )
        return '; '.join(dict.fromkeys(self.parts_rise(part, reads, at, seen) for part in parts))

    def formula_init(self, point, seen):
        """The expression of a formula of one member, or _Fall when a stage can give it another."""
        _, owner, part, at = point
        key = (owner, part.name)
        if key in seen:
            raise _Fall(f'{part.origin} reads itself')
        for origin, event in self.index().defines.get(key, ()):
            if self.blocked(event) is None:
                raise _Fall(f'{origin} can give {part.origin} a new definition')
        own = at.member.value(part.name) if at.member is not None and at.event is None else None
        init = own if own is not None else part.init
        return init.expr if isinstance(init, Formula) else init

    def points_form(self, points, seen):
        """The linear form of what some points name, added: a point that may not be counted adds its
        form widened to zero."""
        form = {}
        for point, one in points:
            found = self.point_form(point, seen)
            form = _added(form, found if one else _widened(found))
        return form

    def point_form(self, point, seen):
        """The linear form of one point: a stored number is a term, a formula its expression's form."""
        kind = point[0]
        if kind == 'value':
            _, owner, part, at = point
            if part.kind in (p.INPUT, p.LINK):
                return {}
            if part.kind == p.STATE and isinstance(part.type, p.Number):
                return {(owner, part.name): (1.0, 1.0)}
            if part.kind == p.FORMULA:
                init = self.formula_init(point, seen)
                return self.linear(init.node, dict(init.reads), at, seen | {(owner, part.name)})
            raise _Fall(f'{part.origin} is no number that the proof can follow')
        if kind == 'occurrences' and point[4] in (None, 'done'):
            # An occurrence joins its event's collection at its start and stays; one done stays done.
            return {('count', point[2].id, point[3].name, point[4] or ''): (1.0, 1.0)}
        if kind == 'rate':
            raise _Fall(f'{point[1]}.{point[2].name}.{point[3]} is a rate of a flow, which can fall')
        if kind == 'other':
            raise _Fall(f'it reads {point[1]}')
        if kind == 'occurrences':
            raise _Fall(
                f'{point[3].origin}.occurrences.{point[4]} takes the value of each occurrence that starts, '
                'and the proof does not know its sign'
            )
        raise _Fall(f'it reads a {kind}, which is no number')

    def linear(self, node, reads, at, seen):
        """The linear form of an expression: {term: (least, greatest coefficient)}, or _Nonlinear."""
        if self.fixed(node, reads, at):
            return {}
        if isinstance(node, nodes.Ref):
            return self.read_form(reads[node.name], at, seen)
        if isinstance(node, nodes.Unary) and node.op in ('neg', 'pos'):
            inner = self.linear(node.operand, reads, at, seen)
            return _scaled(inner, -1) if node.op == 'neg' else inner
        if isinstance(node, nodes.Binary) and node.op in ('add', 'sub'):
            right = self.linear(node.right, reads, at, seen)
            return _added(
                self.linear(node.left, reads, at, seen), right if node.op == 'add' else _scaled(right, -1)
            )
        if isinstance(node, nodes.Binary) and node.op == 'mul':
            for factor, operand in ((node.left, node.right), (node.right, node.left)):
                value = self.constant(factor, reads, at)
                if _number(value):
                    return _scaled(self.linear(operand, reads, at, seen), value)
        if isinstance(node, nodes.Binary) and node.op == 'div':
            value = self.constant(node.right, reads, at)
            if _number(value) and value != 0:
                return _scaled(self.linear(node.left, reads, at, seen), 1 / value)
        if isinstance(node, nodes.IfElse) and self.fixed(node.test, reads, at):
            test = self.constant(node.test, reads, at)
            if isinstance(test, bool):
                return self.linear(node.body if test else node.orelse, reads, at, seen)
        if isinstance(node, nodes.Call) and node.function == 'sum':
            form = {}
            for arg in node.args:
                form = _added(form, self.linear(arg, reads, at, seen))
            return form
        raise _Nonlinear(nodes.text(node))

    def read_form(self, read, at, seen):
        """The linear form of one read of an expression."""
        if isinstance(read, Time):
            return {TIME_TERM: (1.0, 1.0)}
        if isinstance(read, Path):
            return self.points_form(self.points(read, at), seen)
        if isinstance(read, Reduce) and read.op in ('sum', 'count'):
            points = self.points(read.source, at)
            if read.op == 'count' and all(point[0] == 'member' and one for point, one in points):
                return {}  # the members of a fixed collection are fixed for the run
            if read.op == 'count' and not all(point[0] == 'occurrences' for point, _ in points):
                raise _Fall(f'{spelled(read.source)} has yes/no members, which can turn false')
            return self.points_form(points, seen)
        if isinstance(read, (Since, Elapsed)):
            raise _Fall(f'{spelled(read)} falls to zero when what it follows starts or changes again')
        raise _Nonlinear(type(read).__name__)

    def check(self, form):
        """Why a linear form never falls, from each writer of each stored number that it counts, or
        _Fall (see the module)."""
        writers = self.index().writers
        if form.get(TIME_TERM, (0.0, 0.0))[0] < 0:
            raise _Fall('it falls as the time goes on')
        for term, (lo, _) in form.items():
            if term[0] == 'count' and lo < 0:
                raise _Fall(f'it falls as {term[1]}.{term[2]} starts again')
        adds, idle, done = [], [], set()
        for term in form:
            for writer in writers.get(term, ()):
                if id(writer) in done:
                    continue
                done.add(id(writer))
                why = self.blocked(writer.event)
                if why is not None:
                    idle.append(f'{writer.event} cannot start: {why}')
                    continue
                self.writer(writer, form)
                adds.append(_named(writer))
        reasons = []
        if adds:
            reasons.append('what changes it adds to what it counts or moves within it: ' + ', '.join(adds))
        elif any(term[0] not in ('t', 'count') for term in form):
            reasons.append('nothing changes what it counts during the run')
        if form.get(TIME_TERM):
            reasons.append('it rises with the time')
        counts = sorted({f'{term[1]}.{term[2]}' for term in form if term[0] == 'count'})
        if counts:
            reasons.append(f'the occurrences of {", ".join(counts)} only add to their count')
        if not form:
            reasons.append('it reads only what is fixed for the run')
        return '; '.join([*reasons, *dict.fromkeys(idle)])

    @staticmethod
    def _coefficients(ends, form):
        """The least and the greatest coefficient of an end, which is one of its candidates (an
        entity parameter or a lookup can name any of them): zero for SOURCE and SINK."""
        if not ends:
            return 0.0, 0.0
        found = [form.get(key, (0.0, 0.0)) for key, _ in ends]
        return min(lo for lo, _ in found), max(hi for _, hi in found)

    def writer(self, writer, form):
        """_Fall when a writer can make a linear form fall."""
        name = _named(writer)
        if writer.kind in ('flow', 'move', 'route'):
            if writer.sources == writer.sinks and len(writer.sources) == 1 and writer.sources[0][1]:
                return  # a flow from a store to itself moves nothing
            sink_low, sink_high = self._coefficients(writer.sinks, form)
            source_low, source_high = self._coefficients(writer.sources, form)
            if sink_low - source_high < 0 or (writer.kind == 'route' and source_low - sink_high < 0):
                taken = 'moves either way between' if writer.kind == 'route' else 'takes from'
                raise _Fall(f'{name} {taken} what it counts')
            return
        if writer.kind == 'solver':
            raise _Fall(f'{name} determines what it counts')
        delta = None
        if writer.op != '=':
            delta = self.sign(writer.value.node, dict(writer.value.reads), writer.at)
            delta = None if delta is None else delta if writer.op == '+=' else -delta
        for key, _ in writer.sinks:
            lo, hi = form.get(key, (0.0, 0.0))
            if (lo, hi) == (0.0, 0.0) or delta == 0:
                continue
            if delta is None:
                change = (
                    'sets what it counts'
                    if writer.op == '='
                    else f'changes what it counts ({writer.op}) by an amount of no known sign'
                )
                raise _Fall(f'{name} {change}')
            if (delta > 0 and lo < 0) or (delta < 0 and hi > 0):
                raise _Fall(f'{name} takes from what it counts')

    # ---- what a value reads -------------------------------------------------------------------------------

    def reads(self, key):
        """What the value of a key reads (`Reads`): a named value, a field of a flow or of a leg (the
        flow), a field of an endpoint (its store), or a member's status display (what its cases read)."""
        index = self.index()
        start, places = self.start_of(key)
        found, blocked = {}, {}
        pending = [start]
        while pending:
            part = pending.pop()
            if part in found:
                continue
            if part.kind == 'event':
                why = self.blocked(part.origin)
                if why is not None:
                    blocked[part] = why
            found[part] = tuple(dict.fromkeys(self._edges(part, index, places)))
            pending.extend(each for each in found[part] if each not in found)
        return Reads(start, found, blocked)

    def start_of(self, key):
        """The part of a record key where what it reads starts, and the places of the parts found."""
        owner, steps = key.owner, key.steps
        if owner and '#' not in owner and len(steps) == 1:
            template, member = self.rows[owner]
            if steps == ('status',) and template.status is not None and template.part('status') is None:
                part = Part('status', template.status.origin, owner)
                return part, {part: (template.status, _At(template, member))}
        point = self.value_point(owner, steps[0])
        if point is not None:
            part = Part('value', point[2].origin, point[1])
            return part, {part: point}
        places = {}
        if '#' in owner:
            receiver, event_name = owner.rsplit('#', 1)[0].rsplit('.', 1)
            template, member = self.rows[receiver]
            event = template.part(event_name)
            at = _At(template, member, event)
            flow = next((each for each in event.locals if each.name == steps[0]), None)
            points = [(('flow', at.owner, flow, at), True)] if isinstance(flow, p.Flow) else []
        else:
            path = Path(Named(owner), steps[:1]) if owner else Path(Root(), steps[:1])
            points = self.points(path, _At(), True)
            if len(steps) > 1 and points and points[0][0][0] == 'flow':
                points = [(after, True) for after, _ in self._step(points[0][0], steps[1])]
        parts = [part for point, _ in points for part in self._point_parts(point, places)]
        if not parts:
            raise KeyError(f'{key}: no value of the program')
        return parts[0], places

    def _edges(self, part, index, places):
        """The parts that one part reads; `places` keeps the point of each value that they name."""
        edges = []

        def expression(expr, at):
            expr = expr.expr if isinstance(expr, Formula) else expr
            for _, read in getattr(expr, 'reads', ()):
                edges.extend(self._read_parts(read, at, places))

        if part.kind == 'status':
            display, at = places[part]
            for case in display.cases:
                expression(case.test, at)
        elif part.kind == 'value':
            _, owner, value, at = places[part]
            own = at.member.value(value.name) if at.member is not None and at.event is None else None
            if value.kind != p.INPUT or (owner, value.name) not in self.given:
                expression(own if own is not None else value.init, at)
            expression(value.lower, at)
            expression(value.upper, at)
            edges.extend(writer.part for writer in index.writers.get((owner, value.name), ()))
        elif part.kind == 'flow' and part in index.flows:
            writer = index.flows[part]
            expression(writer.value.request, writer.at)
            expression(writer.value.capacity, writer.at)
            for key, _ in (*writer.sources, *writer.sinks):
                point = self.value_point(*key)
                edges.extend(self._point_parts(point, places))
                for side in (point[2].outflow, point[2].inflow):
                    if side is not None:
                        expression(side.capacity, point[3])
                        expression(side.request, point[3])
                # The other flows at an end share it with this one.
                edges.extend(
                    other.part for other in index.writers.get(key, ()) if other.kind in ('flow', 'route')
                )
            if writer.event is not None:
                edges.append(Part('event', writer.event, part.owner))
        elif part.kind == 'stage' and part in index.stages:
            step, at = index.stages[part]
            expression(step.guard, at)
            for statement in _flat(step.body):
                for expr in _statement_exprs(statement):
                    expression(expr, at)
                if isinstance(statement, p.Move):  # a move fits its stores, or fails whole
                    for end in (statement.source, statement.destination):
                        for point, _ in self.points(end, at, True):
                            edges.extend(self._point_parts(point, places))
            edges.append(Part('event', at.event.origin, part.owner))
        elif part.kind == 'event':
            edges.extend(index.starters.get(part, ()))
        elif part.kind == 'trigger' and part in index.triggers:
            trigger, at = index.triggers[part]
            expression(trigger.test, at)
        elif part.kind == 'solver' and part in index.solvers:
            solver = index.solvers[part]
            template, member = self.rows[part.owner]
            for binding in solver.inputs:
                for point, _ in self.points(binding.source, _At(template, member), True):
                    edges.extend(self._point_parts(point, places))
            at = _At(template, member, solver=solver)
            for item in solver.constraints:
                expression(item.test, at)
            for item in solver.objective:
                expression(item.expr, at)
        return [edge for edge in edges if edge != part]

    def _read_parts(self, read, at, places):
        """The parts that one read of an expression names."""
        if isinstance(read, Path):
            return [
                found
                for point, _ in self.points(read, at, True)
                for found in self._point_parts(point, places)
            ]
        if isinstance(read, Reduce):
            return self._read_parts(read.source, at, places)
        if isinstance(read, Since):
            return self._read_parts(read.event, at, places)
        if isinstance(read, Elapsed):
            return self._read_parts(read.value, at, places)
        if isinstance(read, (Draw, Choice)) and isinstance(read.source, Path):
            return self._read_parts(read.source, at, places)
        return []

    def _point_parts(self, point, places):
        """The parts that a point names: a value, a flow (each leg of a flow with legs), an event or
        a solver."""
        kind = point[0]
        if kind == 'value':
            part = Part('value', point[2].origin, point[1])
            places.setdefault(part, point)
            return [part]
        if kind in ('flow', 'rate', 'leg'):
            flow, at = point[2], point[4] if kind in ('rate', 'leg') else point[3]
            owner = at.member.id if at.member is not None else ''
            return [Part('flow', each.origin, owner) for each in (flow.legs or (flow,))]
        if kind in ('event', 'occurrences', 'occurrence'):
            return [Part('event', point[3].origin, point[2].id)]
        if kind == 'solver':
            return [Part('solver', point[3].origin, point[2].id)]
        return []


@dataclass(eq=False)
class _Index:
    """What the proofs find once in a program: the writers of each stored number by its key; the
    definitions that stages and the setup give each formula, as (origin, event); the parts that
    start each event on each receiver; and each flow, stage, trigger and solver by its part."""

    writers: dict = field(default_factory=dict)
    defines: dict = field(default_factory=dict)
    starters: dict = field(default_factory=dict)
    flows: dict = field(default_factory=dict)
    stages: dict = field(default_factory=dict)
    triggers: dict = field(default_factory=dict)
    solvers: dict = field(default_factory=dict)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _named(writer):
    """A writer as a reason names it: its origin, and the member that runs it."""
    return f'{writer.origin} of {writer.part.owner}' if writer.part.owner else writer.origin


def _flat(statements):
    """The statements of a body, with those of its branches."""
    for statement in statements:
        yield statement
        if isinstance(statement, p.If):
            yield from _flat((*statement.then, *statement.orelse))
        elif isinstance(statement, p.Switch):
            yield from _flat((*(each for case in statement.cases for each in case.body), *statement.orelse))


def _statement_exprs(statement):
    """The expressions that a statement reads."""
    if isinstance(statement, p.Assign):
        return (statement.value,)
    if isinstance(statement, p.Move):
        return (statement.amount,)
    if isinstance(statement, p.Start):
        return statement.args
    if isinstance(statement, p.If):
        return (statement.test,)
    if isinstance(statement, p.Switch):
        return (statement.selector, *(case.guard for case in statement.cases if case.guard is not None))
    return ()
