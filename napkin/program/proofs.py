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
  coefficient may be its own or zero. A named collection, of a member, of the root or a local of an
  event, is the collection that it names, so a read over it proves as the read written in its place.
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
- Only a number is averaged over a window: a yes/no, a text, an enum member, a link or a distribution
  is refused by name before anything else, also when it is fixed for the run.
- A formula's linear form, and its proof by parts, are found once for each formula of a member, each
  after the formulas that it reads, depth first on a stack of its own (`Proofs._find`): a chain of
  formulas, of child links or of links between members of any length needs no recursion of Python, and
  so is the value of an input whose default reads other inputs (`Proofs.input_value`). A formula that
  reads itself can fall: the proof cannot settle it.

**An edited run** (`Proofs(program, configuration, changes)`): each change from outside (`Change`, an
edit at a stop, PLAN change 15) is one more writer of the run that it changed, at its time, from its
old value to its new one, and every proof of that run follows from this one premise, as it follows
from the program's own writers: none is computed for the unedited run and then patched by kind of
edit. A change of a stored number is a writer of known sign: one that lowers what a form counts, or
raises what it subtracts, makes the form fall, so the proof is withdrawn for that run, for the edited
value and for every formula that rests on it, with the change's reason; one that does not break it
keeps it (PLAN 15). A change of a named state (a yes/no or an enum member) lets the state take its new
value, so reachability is derived again (`reach`): an event that it lets start writes, and is no
longer "cannot start", and a stage that it lets run can give a formula a new definition.

**What a value reads** (`reads(program, configuration, key)`): the parts that the value can depend
on, each as one member runs it (`Part`), with the parts that each of them reads. It starts at a named
value, at the flow of a field of a flow, or at a member's status display, which reads its cases, each
a part (`case`) that reads what its condition reads, each after the first only when those before it
do not hold. A read through a reference to an occurrence (`parts.OccurrenceType`) reads that field of
an occurrence of its event, as `.at(t)` does. A stored value reads its starting value, its
bounds and its writers; a formula, what its expression reads; a flow, its request and its capacity,
its ends, the settings of the endpoints at its ends, and the other flows there, which share them; a
stage, its guard, its statements and the stores of its moves, and its event; an event, its triggers
and the stages that start it; a trigger, its condition; a solver, its inputs, its constraints and its
objectives. A part that an expression reads only on a branch (a side of a choice, a later term of
`and` or `or`: `always`) is in `sometimes` of the part that reads it, unless another of its
expressions reads it on every evaluation. An event that cannot start under the configuration is
`blocked`, with the reason (D16: "this event cannot fire with the plant closed"); what a run
exercised is the record's to say.

`Proofs(program, configuration, changes)` finds the writers and the reachability of a program once,
for each key that a caller asks about (`never_falls`, `reads`); the functions of the same names make
one.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field, replace
from fractions import Fraction

from ..core import expr as nodes
from ..core.comparisons import Comparisons
from ..core.errors import ExpressionError
from ..core.evaluation import checked_value
from ..core.units import UnitSystem, rational
from . import parts as p
from .reach import _Reach, reach
from .record import Key
from .refs import (
    ITEM,
    By,
    Distribution,
    Draw,
    Elapsed,
    EnumValue,
    Formula,
    Instances,
    Item,
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
    renamed,
    spelled,
)

TIME_TERM = ('t',)  # the term of the time in a linear form


@dataclass(frozen=True)
class Proof:
    """A conclusion of a proof: whether it holds, and why."""

    holds: bool
    reason: str


@dataclass(frozen=True)
class Change:
    """A change from outside of a stored value in one run (an edit at a stop): the record key of the
    value (`record.Key`), its value before and after, in canonical units (a number, a yes/no, an enum
    member's name, a text), and what it did, which a proof that it withdraws gives as its reason."""

    key: Key
    old: object
    new: object
    why: str

    @property
    def amount(self):
        """What a change of a number added (below zero for one that lowered it), or None."""
        if all(_number(value) for value in (self.old, self.new)):
            return float(self.new) - float(self.old)
        return None


@dataclass(frozen=True)
class Part:
    """A declaration or a computed field in the evidence graph. The origin names the declaration
    and, for a network field or solved rate, its field. The owner is its receiver, the root (''),
    or the scope of an occurrence value (`tank.receive#`)."""

    kind: str
    origin: str
    owner: str = ''


@dataclass(frozen=True)
class Reads:
    """What a value reads: from `start`, each part with the parts that it reads (`edges`), of those the
    parts that it reads only on a branch (`sometimes`), and each event that cannot start under the
    configuration, with the reason (`blocked`)."""

    start: Part
    edges: dict = field(default_factory=dict)
    blocked: dict = field(default_factory=dict)
    sometimes: dict = field(default_factory=dict)


def never_falls(program, configuration, key, changes=()):
    """Whether the value of a record key (`record.Key`) never falls over a run of the program under the
    configuration (None for the program's own inputs), with the reason; with `changes`, over the run
    that they changed (see the module)."""
    return Proofs(program, configuration, changes).never_falls(key)


def always(node):
    """The names that every evaluation of a node reads (that does not fail first): all of them but
    those on a side of a choice that the other side does not read too, in a term of `and` or `or`
    after the first, and in a comparison of a chain after the first (`a < b < c` reads `c` only when
    `a < b`)."""
    if isinstance(node, nodes.Ref):
        return frozenset((node.name,))
    if isinstance(node, nodes.IfElse):
        return always(node.test) | (always(node.body) & always(node.orelse))
    if isinstance(node, nodes.BoolOp):
        return always(node.values[0])
    if isinstance(node, nodes.Compare):
        return always(node.operands[0]) | always(node.operands[1])
    if isinstance(node, nodes.Call) and node.function in ('any', 'all') and len(node.args) > 1:
        return always(node.args[0])  # the `or` or the `and` of its members
    if isinstance(node, nodes.Foreign):
        return frozenset()
    return frozenset().union(*map(always, node.children))


def reads(program, configuration, key):
    """What the value of a record key reads (`Reads`, see the module)."""
    return Proofs(program, configuration).reads(key)


class _Fall(Exception):
    """What can make a value fall, or what the proof cannot settle: the reason."""


class _Nonlinear(Exception):
    """A part of an expression that a linear form does not write."""


class _Pending(Exception):
    """Jobs that a proof needs before it has them: each (`form` or `rise`, a formula point), the
    linear form or the proof by parts of a formula. The search (`Proofs._find`) does them first and
    tries again, so a chain of formulas needs no recursion."""

    def __init__(self, jobs):
        super().__init__(len(jobs))
        self.jobs = jobs


def _walked(computation):
    """The result of a computation on a stack of its own, with no recursion of Python (re-audit 15):
    a computation is a generator that yields each computation that it needs and is sent its result,
    and returns its own; an exception that a needed one raises is thrown into the one that waits for
    it, where a call would have raised it. It is the driver of the engine's walks
    (`napkin/engine/continuous/walk.py`) for the program, which the engine imports."""
    stack, sent, thrown = [computation], None, None
    while True:
        top = stack[-1]
        try:
            asked = top.send(sent) if thrown is None else top.throw(thrown)
        except StopIteration as done:
            stack.pop()
            if not stack:
                return done.value
            sent, thrown = done.value, None
            continue
        except Exception as problem:
            stack.pop()
            if not stack:
                raise
            sent, thrown = None, problem
            continue
        stack.append(asked)
        sent, thrown = None, None


def _formula(point):
    """The key of a formula of a member (owner, name) that a point names, or None."""
    if point[0] == 'value' and point[2].kind == p.FORMULA:
        return (point[1], point[2].name)
    return None


@dataclass(frozen=True, eq=False)
class _At:
    """Where an expression is read: its template and member (none for the root), and the event,
    trigger or solver whose bare names it reads. In a predicate, item is its collection entry."""

    template: p.Template | None = None
    member: p.Member | None = None
    event: p.Event | None = None
    trigger: p.Trigger | None = None
    solver: p.Solver | None = None
    item: tuple | None = None

    @property
    def owner(self):
        """The owner of the values of the scope: the member, the root, or the event's occurrences on
        the member."""
        if self.member is None:
            return ''
        return f'{self.member.id}.{self.event.name}#' if self.event is not None else self.member.id


@dataclass(frozen=True)
class _Selection:
    """Reads that decide which collection entries to use, in their own scopes. A lookup needs
    the source's keys; an ordinary projection uses only its membership."""

    reads: list
    keys: bool = False

    def expression(self, expr, at, certain=True):
        every = always(expr.node)
        self.reads.extend((read, at, certain and name in every) for name, read in expr.reads)


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

    def __init__(self, program, configuration, changes=()):
        self.program = program
        self.rows = {
            member.id: (template, member) for template in program.templates for member in template.members
        }
        self.given = {(item.member, item.name): item.value for item in getattr(configuration, 'inputs', ())}
        self.units = UnitSystem(
            {unit.name: {'dimensions': dict(unit.dimension), 'scale': unit.scale} for unit in program.units}
        )
        if configuration is not None:
            self.units.comparisons.factor = max(
                configuration.numerics.rtol, configuration.numerics.atol_factor
            )
        # The changes from outside of the run (see the module): every proof follows from them.
        self.changes = tuple(changes)
        self.declared = reach(program, configuration).events  # what the configuration alone reaches
        states = [found for change in self.changes if (found := self._state(change)) is not None]
        self.events = self.declared if not states else _reached(program, configuration, states).events
        self._index = None
        # Found once, by formula or input (owner, name): a formula's linear form and its proof by
        # parts, each a value or the failure that it raised (`_find`), and an input's value.
        self._tables = {'form': {}, 'rise': {}}
        self._inputs = {}
        self._searching = 0

    def _state(self, change):
        """The named state that a change gives a value (reach's key, its new value, the reason), or
        None for a change of a number or a text, which reachability reads as any value."""
        point = (
            self.value_point(change.key.owner, change.key.steps[0]) if len(change.key.steps) == 1 else None
        )
        if point is None or not isinstance(point[2].type, (p.Bool, p.EnumType)):
            return None
        _, _, part, at = point
        # A state is one for all the members of a template, or for all the occurrences of an event.
        scope = at.event.origin if at.event is not None else at.template.name if at.template else ''
        return (f'{scope}.{part.name}' if scope else part.name, frozenset({change.new}), change.why)

    def withdrawn(self, event):
        """Why the configuration alone proves that an event cannot start, when the changes of the run
        let it start (see the module), with the changes of named states that do; else None."""
        can, reason = self.declared.get(event, (True, ''))
        if can or self.blocked(event) is not None:
            return None
        edits = [change.why for change in self.changes if self._state(change) is not None]
        return f'{"; ".join(edits)}: this withdrew for this run the proof that it cannot start: {reason}'

    # ---- paths, member by member ----------------------------------------------------------------------

    def points(self, path, at, moving=False):
        """What a path names, member by member: [(point, whether it is the one)]. A point is a tuple
        whose first item is its kind: `member`, `root`, `value` (owner, part, scope), `flow` (owner,
        flow, scope), `leg` of a route, `rate` (a property of a flow), `event`, `occurrences`,
        `occurrence`, `solver` or `other` (a description). A lookup whose key moves is `other`, but
        with `moving`, which a writer's target takes, its members. A named collection is the
        collection that it names (spec, "Collections, keys and projections"), of a member, of the root
        or a local of an event: a path that steps into it reads its init, so a read over it is the
        read over the collection written in its place. The walk goes on a stack of its own
        (`_walked`): a chain of named collections, each read through the one before, of any length
        needs no recursion of Python."""
        return _walked(self._points(path, at, moving))

    def _points(self, path, at, moving, selection=None):
        """The computation of `points` (`_walked`). When building an evidence trail, keep the
        reads that select these points as well as the projected fields."""
        found = yield self._start(path.start, at, moving, selection)
        for step in path.steps:
            after = []
            for point, one in found:
                stepped = yield self._step(point, step, selection)
                after += [(each, one and also) for each, also in stepped]
            found = after
        return found

    def _start(self, start, at, moving, selection):
        if isinstance(start, This):
            return [(('member', at.template, at.member), True)]
        if isinstance(start, Item) and at.item is not None:
            return [(at.item, True)]
        if isinstance(start, Root):
            return [(('root',), True)]
        if isinstance(start, Named):
            template, member = self.rows[start.id]
            return [(('member', template, member), True)]
        if isinstance(start, Local):
            return (yield self._local(start.name, at, selection))
        if isinstance(start, Instances):
            template = self.program.template(start.template)
            return [(('member', template, member), True) for member in template.members]
        if isinstance(start, Literal):
            found = []
            for item in start.items:
                found += yield self._points(item, at, moving, selection)
            return found
        if isinstance(start, By):
            source = replace(selection, keys=False) if selection is not None and selection.keys else selection
            found = yield self._points(start.source, at, moving, source)
            if selection is not None and selection.keys:
                for point, one in found:
                    selection.reads.append((Path(ITEM, (start.key,)), replace(at, item=point), one))
            return found
        if isinstance(start, Where):
            found = yield self._points(start.source, at, moving, selection)
            if selection is not None:
                for point, one in found:
                    selection.expression(start.test, replace(at, item=point), one)
            return [(point, False) for point, _ in found]
        if isinstance(start, Lookup):
            if not moving and not (yield self._fixed(start.key.node, dict(start.key.reads), at)):
                return [(('other', 'a keyed read whose key moves, which can select a smaller value'), True)]
            # One member of the collection, or the newest occurrence of an event.
            source = selection
            if selection is not None:
                selection.expression(start.key, at)
                source = replace(selection, keys=True)
            found = yield self._points(start.source, at, moving, source)
            return [
                (
                    ('occurrence', *point[1:4]) if point[0] == 'occurrences' and point[4] is None else point,
                    False,
                )
                for point, _ in found
            ]
        return [(('other', 'the member of a where'), True)]

    def _local(self, name, at, selection):
        """A bare name: an input or an unknown of a solver, a capture of a trigger, or a parameter, a
        local (a named collection: its members) or a flow of an event."""
        if at.solver is not None:
            for binding in at.solver.inputs:
                if binding.name == name:
                    return (yield self._points(binding.source, _At(at.template, at.member), False, selection))
            if any(unknown.name == name for unknown in at.solver.unknowns):
                return [(('other', f'{name}, an unknown of {at.solver.origin}'), True)]
        if at.trigger is not None:
            for capture in at.trigger.captures:
                if capture.name == name:
                    if selection is not None:
                        selection.expression(capture.init, at)
                    return [(('other', f'{name}, a capture of {at.trigger.origin}'), True)]
        if at.event is not None:
            for part in (*at.event.params, *at.event.locals):
                if part.name != name:
                    continue
                if isinstance(part, p.Value) and part.kind == p.COLLECTION:
                    return (yield self._points(part.init, at, True, selection))
                if isinstance(part, p.Value) and isinstance(part.type, p.EntityType):
                    # An entity parameter can pass any member of its template (D13).
                    template = self.program.template(part.type.template)
                    return [(('member', template, member), False) for member in template.members]
                if isinstance(part, p.Value) and isinstance(part.type, p.OccurrenceType):
                    # A reference names one occurrence of its event, of any member of the template:
                    # a read through it reads that occurrence's field, as `.at(t)` does.
                    template = self.program.template(part.type.template)
                    event = template.part(part.type.event)
                    return [(('occurrence', template, member, event), False) for member in template.members]
                kind = 'value' if isinstance(part, p.Value) else 'flow'
                return [((kind, at.owner, part, at), True)]
        return [(('other', f'the bare name {name}'), True)]

    def _step(self, point, name, selection=None):
        """The points of one step of a path from a point (`_points`)."""
        kind = point[0]
        if kind == 'root':
            part = self.program.root_value(name)
            if part is None:
                return [(('other', name), True)]
            if part.kind == p.COLLECTION:
                return (yield self._points(part.init, _At(), True, selection))
            return [(('value', '', part, _At()), True)]
        if kind == 'member':
            _, template, member = point
            part = template.part(name) if template is not None else None
            at = _At(template, member)
            if isinstance(part, p.Value):
                if part.kind == p.LINK:
                    target = self.program.template(part.type.template)
                    return [(('member', target, target.members[member.link(name)]), True)]
                if part.kind == p.COLLECTION:
                    return (yield self._points(member.value(name) or part.init, at, True, selection))
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
                return [] if isinstance(end, p.Outside) else (yield self._points(end, at, True, selection))
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
                return [] if isinstance(end, p.Outside) else (yield self._points(end, at, True, selection))
            return [(('network field', owner, flow, at, (side, name)), True)]
        if kind == 'event':
            if selection is not None and name == 'occurrences':
                selection.reads.append((Path(Named(point[2].id), (point[3].name,)), _At(), True))
            return (
                [(('occurrences', *point[1:], None), True)]
                if name == 'occurrences'
                else [(('other', name), True)]
            )
        if kind == 'occurrences' and point[4] is None:
            if selection is not None and name not in p.OCCURRENCE_PROPERTIES:
                fields = yield self._step(('occurrence', *point[1:4]), name, selection)
                return [(field, False) for field, _ in fields]
            return [(('occurrences', *point[1:4], name), True)]
        if kind == 'occurrence':
            _, template, member, event = point
            for part in (*event.params, *event.locals):
                if part.name == name:
                    at = _At(template, member, event)
                    return [(('value' if isinstance(part, p.Value) else 'flow', at.owner, part, at), True)]
        if kind == 'value':
            if selection is not None and name in ('outflow', 'inflow'):
                return [(('endpoint', point, name), True)]
            return [(('other', f'{point[2].origin}.{name}, a setting or a property of a value'), True)]
        if kind == 'endpoint':
            _, value, side = point
            if name == 'flows':
                return self._incident(value, side)
            return [(('network field', *value[1:], (side, name)), True)]
        if kind == 'solver' and any(u.name == name for u in point[3].unknowns):
            return [(point, True)]  # a read of a declared result reads its solver
        if kind == 'other':
            return [(point, True)]  # what follows a part that the proof does not follow
        return [(('other', f'{name} of {kind}'), True)]

    def _incident(self, value, side):
        """The connections on one side of a store, including the appropriate leg of each route."""
        key = value[1], value[2].name
        found = []
        for writer in dict.fromkeys(self.index().writers.get(key, ())):
            if writer.kind not in ('flow', 'route'):
                continue
            connection = writer.at.owner, writer.value, writer.at
            for ends, forward in ((writer.sources, side == 'outflow'), (writer.sinks, side == 'inflow')):
                for end, one in ends:
                    if end != key:
                        continue
                    definite = one and writer.event is None
                    if writer.kind == 'route':
                        direction = 'forward' if forward else 'backward'
                        found.append((('leg', *connection, direction), definite))
                    elif forward:
                        found.append((('flow', *connection), definite))
        return found

    def fixed(self, node, reads, at):
        """Whether an expression reads only what is fixed for the run: constants, inputs and links."""
        return _walked(self._fixed(node, reads, at))

    def _fixed(self, node, reads, at):
        """The computation of `fixed` (`_walked`): the points of each read are found on the stack."""
        for name in nodes.names(node):
            read = reads.get(name)
            if isinstance(read, EnumValue):
                continue
            if not isinstance(read, Path):
                return False
            found = yield self._points(read, at, False)
            if len(found) != 1 or found[0][0][0] not in ('value', 'member'):
                return False
            if found[0][0][0] == 'value' and found[0][0][2].kind not in (p.INPUT, p.LINK):
                return False
        return True

    # ---- fixed values and signs -----------------------------------------------------------------------

    def constant(self, node, reads, at):
        """The value of an expression that reads only what is fixed for the run, in canonical units, or
        None: an input that is drawn has no value known before the run."""
        environment, points, identities, aliases = {}, {}, {}, {}
        for name in nodes.names(node):
            read = reads.get(name)
            if isinstance(read, EnumValue):
                environment[name] = read.member
                continue
            point = self._input_point(read, at)
            value = None if point is None else self.input_value(point)
            if value is None:
                return None
            # One input can be reached by several paths. Its repeated contributions share
            # a comparison scale, including inside a product or another compound expression.
            owner, part = point[1:3]
            bound = identities.setdefault((owner, part.name), name)
            if name != bound:
                aliases[name] = bound
            environment[bound] = value
            points[bound] = point

        def operand(name):
            point = points.get(name)
            if point is None:
                return 1.0, 1.0
            _, _, part, place = point
            size = (
                self.units.scale(part.type.unit)
                if isinstance(part.type, p.Number) and part.type.unit
                else 1.0
            )
            if part.scale is None:
                return size, size
            scale = self.constant(part.scale.node, dict(part.scale.reads), place)
            if scale is None:
                raise ExpressionError('the comparison scale is not fixed')
            return size, abs(scale)

        units = self.units
        if points:
            units = copy(units)
            units.comparisons = Comparisons(units, self.units.comparisons.factor, operand)
        try:
            return checked_value(renamed(node, aliases) if aliases else node, environment, units)
        except (ExpressionError, ArithmeticError, ValueError, TypeError, KeyError):
            return None

    def _input_point(self, read, at):
        """The point of the one input that a read of an expression names, or None."""
        if not isinstance(read, Path):
            return None
        found = self.points(read, at)
        if len(found) != 1 or found[0][0][0] != 'value' or found[0][0][2].kind != p.INPUT:
            return None
        return found[0][0]

    def input_value(self, point):
        """The value of an input: the configuration's, or its default when that is fixed; None when
        it has none known before the run. Found once for each input of a member, each after the
        inputs that its default reads, on a stack: a chain of defaults of any length needs no
        recursion. A default that reads itself has no value known before the run."""
        key = (point[1], point[2].name)
        if key not in self._inputs:
            stack, waiting = [(point, False)], set()
            while stack:
                place, ready = stack.pop()
                name = (place[1], place[2].name)
                if name in self._inputs:
                    continue
                if ready:
                    self._inputs[name] = self._input(place)
                    continue
                if name in waiting:
                    self._inputs[name] = None  # it reads itself
                    continue
                waiting.add(name)
                stack.append((place, True))
                init = self._default(place)
                for _, read in () if init is None else init.reads:
                    other = self._input_point(read, place[3])
                    if other is not None and (other[1], other[2].name) not in self._inputs:
                        stack.append((other, False))
        return self._inputs[key]

    def _default(self, point):
        """The default of an input that the configuration does not set (its member's own line, or
        its declaration's), or None."""
        _, owner, part, at = point
        if (owner, part.name) in self.given:
            return None
        init = at.member.value(part.name) if at.member is not None and at.event is None else None
        init = init if init is not None else part.init
        return init if init is not None and hasattr(init, 'node') else None

    def _input(self, point):
        """The value of one input once the inputs that its default reads are known (`input_value`)."""
        _, owner, part, at = point
        given = self.given.get((owner, part.name))
        if given is not None:
            if isinstance(given, (bool, str)):
                return given
            if isinstance(given, EnumValue):
                return given.member
            if isinstance(given, Distribution):
                return None
            # The decimal that a configuration writes times the unit's exact scale, rounded once.
            unit = given.unit if isinstance(given.unit, p.Unit) else self.program.unit(given.unit)
            return float(rational(given.number) * Fraction(unit.scale))
        init = self._default(point)
        return None if init is None else self.constant(init.node, dict(init.reads), at)

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
        statements = []
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
                            statements.append((step.body, inner, stage, event.origin))
                    for trigger in event.triggers:
                        fired = Part('trigger', trigger.origin, member.id)
                        found.triggers[fired] = (trigger, _At(template, member, trigger=trigger))
                        statements.append((trigger.body, found.triggers[fired][1], fired, None))
                for solver in template.solvers:
                    part = Part('solver', solver.origin, member.id)
                    scope = _At(template, member, solver=solver)
                    targets = []
                    for target in solver.solve_for:
                        for point, certain in self.points(target, scope, True):
                            if point[0] == 'value':
                                targets.append(((point[1], point[2].name), certain))
                            elif point[0] == 'rate':
                                found.rate_solvers[point[1], point[2].origin] = part
                    writer = _Writer('solver', solver.origin, part, sinks=tuple(targets), at=scope)
                    found.solvers[part] = solver
                    for key, _ in targets:
                        found.writers.setdefault(key, []).append(writer)
        # A setting assignment can select a flow of an endpoint whose connections appear later.
        # Resolve these targets after every member's flows have entered the index.
        self._index = found
        for body, at, stage, event in statements:
            self._statements(body, at, stage, event, found)
        self._statements(self.program.setup, _At(), Part('stage', 'setup'), None, found, setup=True)
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
                found.groups[at.owner, leg.origin] = flow
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
            if isinstance(statement, p.Assign) and statement.target.steps[-1:] in (
                ('request',),
                ('capacity',),
            ):
                # Keep the assigned setting distinct from the other setting of the same connection.
                for point, _ in _walked(self._points(statement.target, at, True, _Selection([]))):
                    if point[0] in ('rate', 'network field'):
                        for setting in self._point_parts(point, {}):
                            found.settings.setdefault(setting, []).append(stage)
            if isinstance(statement, p.Assign):
                if isinstance(statement.value, Formula):
                    for point, _ in self.points(statement.target, at, True):
                        if point[0] == 'value':
                            key = (point[1], point[2].name)
                            found.defines.setdefault(key, []).append((statement.origin, event, stage))
                        if setup:
                            # Each setup definition can read different inputs, even at the same time.
                            for part in self._point_parts(point, {}):
                                found.setup_definitions.setdefault(part, []).append(statement.value)
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
                        target, receiver = point[3], point[2]
                        found.starters.setdefault(Part('event', target.origin, receiver.id), []).append(stage)
                        for param, arg in zip(target.params, statement.args, strict=True):
                            key = (f'{receiver.id}.{target.name}#', param.name)
                            found.arguments.setdefault(key, []).append((arg, at))
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
            if key.store is not None:
                raise _Fall(f'{key} is the ledger of a store, what edits brought into it: no named number')
            raise _Fall(
                f'{key} is no named number: a rate, a setting or a field of a flow follows its sharing, '
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
        """Whether the value of a record key never falls over the run (edited by the changes, if any),
        with the reason (`Proof`)."""
        try:
            return Proof(True, self.value(key))
        except _Fall as fall:
            return Proof(False, str(fall))

    def value(self, key):
        """Why the value of a key never falls, or _Fall: only a number is averaged over a window, so the
        type comes first, also for what is fixed for the run."""
        point = self.point_of(key)
        part = point[2]
        if not isinstance(part.type, p.Number):
            raise _Fall(f'{part.origin} is {kind_of(part.type)}, and only a number is averaged over a window')
        if part.kind in (p.INPUT, p.LINK):
            return 'it is fixed for the run'
        return self.rises([(point, True)])

    def rises(self, points):
        """Why what some points name never falls (their linear form, else their parts), or _Fall."""
        try:
            form = self.points_form(points)
        except _Nonlinear:
            pass
        else:
            return self.check(form)
        self._ensure('rise', [point for point, _ in points])
        reasons = []
        for point, _ in points:
            if _formula(point) is not None:
                reasons.append(self._entry('rise', point))
            else:
                reasons.append(self.check(self.point_form(point)))
        return '; '.join(dict.fromkeys(reasons))

    def parts_rise(self, node, reads, at):
        """Why an expression that no linear form writes never falls, by its parts, or _Fall."""
        try:
            return self.check(self.linear(node, reads, at))
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
                return self.rises(self.points(read.source, at))
            if isinstance(read, Path):
                return self.rises(self.points(read, at))
        if parts is None:
            raise _Fall(
                f'{nodes.notation(node)} can fall: the proof covers sums, differences, min, max, and products '
                'and quotients by fixed numbers of what never falls'
            )
        return '; '.join(dict.fromkeys(self.parts_rise(part, reads, at) for part in parts))

    def formula_init(self, point):
        """The expression of a formula of one member, or _Fall when a stage can give it another."""
        _, owner, part, at = point
        for origin, event, _ in self.index().defines.get((owner, part.name), ()):
            if self.blocked(event) is None:
                raise _Fall(f'{origin} can give {part.origin} a new definition')
        own = at.member.value(part.name) if at.member is not None and at.event is None else None
        init = own if own is not None else part.init
        return init.expr if isinstance(init, Formula) else init

    # ---- each formula once, each after what it reads -----------------------------------------------------

    def _ensure(self, which, points):
        """Find the entry of `which` (`form` or `rise`) of each formula among `points` where it is
        missing: within a search, the search does it first (`_Pending`); else a search of its own."""
        table = self._tables[which]
        missing = [
            (which, point) for point in points if (key := _formula(point)) is not None and key not in table
        ]
        if not missing:
            return
        if self._searching:
            raise _Pending(missing)
        self._find(missing)

    def _entry(self, which, point):
        """The entry of `which` of a formula point once it is found: its value, or the failure that it
        raised, raised again."""
        self._ensure(which, [point])
        found = self._tables[which][_formula(point)]
        if isinstance(found, Exception):
            raise type(found)(*found.args)
        return found

    def _find(self, jobs):
        """Do each job (`form` or `rise`, a formula point) and those that it needs, depth first on a
        stack, with no recursion: a job goes after the linear forms of the formulas that its
        expression reads, and one that needs a job that is not done yet (`_Pending`) waits while it is
        done. A job that its own needs reach again is a formula that reads itself: it can fall."""
        stack, waiting = [(job, False) for job in jobs], set()
        self._searching += 1
        try:
            while stack:
                (which, point), ready = stack.pop()
                key, table = _formula(point), self._tables[which]
                if key in table:
                    continue
                if not ready:
                    if (which, key) in waiting:
                        table[key] = _Fall(f'{point[2].origin} reads itself')
                        continue
                    waiting.add((which, key))
                    stack.append(((which, point), True))
                    stack += [(('form', other), False) for other in self._formulas_read(point)]
                    continue
                try:
                    table[key] = self._job(which, point)
                except _Pending as pending:
                    stack.append(((which, point), True))  # again, once what it needs is done
                    stack += [(job, False) for job in pending.jobs]
                except (_Fall, _Nonlinear) as problem:
                    table[key] = problem
        finally:
            self._searching -= 1

    def _job(self, which, point):
        """The linear form of a formula point's expression (`form`), or why it never falls by its
        parts (`rise`), once what it needs is found."""
        init = self.formula_init(point)
        if which == 'form':
            return self.linear(init.node, dict(init.reads), point[3])
        return self.parts_rise(init.node, dict(init.reads), point[3])

    def _formulas_read(self, point):
        """The formula points whose linear forms are not found yet that the expression of a formula
        point reads, on any branch."""
        try:
            init = self.formula_init(point)
        except _Fall:
            return []
        found = []
        for _, read in init.reads:
            source = read.source if isinstance(read, Reduce) else read
            if isinstance(source, Path):
                found += [
                    other
                    for other, _ in self.points(source, point[3])
                    if (key := _formula(other)) is not None and key not in self._tables['form']
                ]
        return found

    def points_form(self, points):
        """The linear form of what some points name, added: a point that may not be counted adds its
        form widened to zero."""
        self._ensure('form', [point for point, _ in points])
        form = {}
        for point, one in points:
            found = self.point_form(point)
            form = _added(form, found if one else _widened(found))
        return form

    def point_form(self, point):
        """The linear form of one point: a stored number is a term, a formula its expression's form."""
        kind = point[0]
        if kind == 'value':
            _, owner, part, _ = point
            if part.kind in (p.INPUT, p.LINK):
                return {}
            if part.kind == p.STATE and isinstance(part.type, p.Number):
                return {(owner, part.name): (1.0, 1.0)}
            if part.kind == p.FORMULA:
                return self._entry('form', point)
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

    def linear(self, node, reads, at):
        """The linear form of an expression: {term: (least, greatest coefficient)}, or _Nonlinear."""
        if self.fixed(node, reads, at):
            return {}
        if isinstance(node, nodes.Ref):
            return self.read_form(reads[node.name], at)
        if isinstance(node, nodes.Unary) and node.op in ('neg', 'pos'):
            inner = self.linear(node.operand, reads, at)
            return _scaled(inner, -1) if node.op == 'neg' else inner
        if isinstance(node, nodes.Binary) and node.op in ('add', 'sub'):
            right = self.linear(node.right, reads, at)
            return _added(
                self.linear(node.left, reads, at), right if node.op == 'add' else _scaled(right, -1)
            )
        if isinstance(node, nodes.Binary) and node.op == 'mul':
            for factor, operand in ((node.left, node.right), (node.right, node.left)):
                value = self.constant(factor, reads, at)
                if _number(value):
                    return _scaled(self.linear(operand, reads, at), value)
        if isinstance(node, nodes.Binary) and node.op == 'div':
            value = self.constant(node.right, reads, at)
            if _number(value) and value != 0:
                return _scaled(self.linear(node.left, reads, at), 1 / value)
        if isinstance(node, nodes.IfElse) and self.fixed(node.test, reads, at):
            test = self.constant(node.test, reads, at)
            if isinstance(test, bool):
                return self.linear(node.body if test else node.orelse, reads, at)
        if isinstance(node, nodes.Call) and node.function == 'sum':
            form = {}
            for arg in node.args:
                form = _added(form, self.linear(arg, reads, at))
            return form
        raise _Nonlinear(nodes.notation(node))

    def read_form(self, read, at):
        """The linear form of one read of an expression."""
        if isinstance(read, Time):
            return {TIME_TERM: (1.0, 1.0)}
        if isinstance(read, Path):
            return self.points_form(self.points(read, at))
        if isinstance(read, Reduce) and read.op in ('sum', 'count'):
            points = self.points(read.source, at)
            if read.op == 'count' and all(point[0] == 'member' and one for point, one in points):
                return {}  # the members of a fixed collection are fixed for the run
            if read.op == 'count' and not all(point[0] == 'occurrences' for point, _ in points):
                raise _Fall(f'{spelled(read.source)} has yes/no members, which can turn false')
            return self.points_form(points)
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
                try:
                    self.writer(writer, form)
                except _Fall as fall:
                    # A writer that only the changes of the run let run says which change did.
                    withdrawn = self.withdrawn(writer.event) if writer.event is not None else None
                    raise _Fall(f'{fall} ({withdrawn})' if withdrawn else str(fall)) from None
                adds.append(_named(writer))
        for change in self.changes:
            amount = change.amount  # a change of a named state writes no number; it reaches (`events`)
            lo, hi = form.get(_term(change.key), (0.0, 0.0))
            if amount is not None and ((amount < 0 and hi > 0) or (amount > 0 and lo < 0)):
                raise _Fall(change.why)
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
        flow), a field of an endpoint (its store), or a member's status display (its cases, each of
        which reads what its condition reads)."""
        index = self.index()
        start, places = self.start_of(key)
        found, blocked, sometimes = {}, {}, {}
        pending = [start]
        while pending:
            part = pending.pop()
            if part in found:
                continue
            if part.kind == 'event':
                why = self.blocked(part.origin)
                if why is not None:
                    blocked[part] = why
            edges, maybe = self._edges(part, index, places)
            found[part] = tuple(dict.fromkeys(edges))
            if maybe:
                sometimes[part] = frozenset(maybe)
            pending.extend(each for each in found[part] if each not in found)
        return Reads(start, found, blocked, sometimes)

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
            if len(steps) == 3 and steps[1] in ('inflow', 'outflow'):
                places = {}
                network = ('network field', *point[1:], steps[1:])
                return self._point_parts(network, places)[0], places
            part = Part('value', point[2].origin, point[1])
            return part, {part: point}
        places = {}
        if '#' in owner:
            receiver, event_name = owner.rsplit('#', 1)[0].rsplit('.', 1)
            template, member = self.rows[receiver]
            event = template.part(event_name)
            if len(steps) == 1 and steps[0] in p.OCCURRENCE_PROPERTIES:
                return Part('event', event.origin, receiver), {}
            at = _At(template, member, event)
            flow = next((each for each in event.locals if each.name == steps[0]), None)
            points = [(('flow', at.owner, flow, at), True)] if isinstance(flow, p.Flow) else []
        else:
            path = Path(Named(owner), steps[:1]) if owner else Path(Root(), steps[:1])
            points = self.points(path, _At(), True)
        if points and points[0][0][0] == 'flow':
            for step in steps[1:]:
                points = [entry for point, _ in points for entry in _walked(self._step(point, step))]
        parts = [part for point, _ in points for part in self._point_parts(point, places)]
        if not parts:
            raise KeyError(f'{key}: no value of the program')
        return parts[0], places

    def _edges(self, part, index, places):
        """The parts that one part reads, and those of them that it reads only on a branch of each
        expression that reads them (`always`); `places` keeps the point of each value that they name."""
        edges, surely = [], set()

        def expression(expr, at, branch=False):
            # On a branch of a stage (an `if`, a case), even what its expression always reads is read
            # only when the branch runs.
            expr = expr.expr if isinstance(expr, Formula) else expr
            node = getattr(expr, 'node', None)
            every = always(node) if node is not None and not branch else frozenset()
            for name, read in getattr(expr, 'reads', ()):
                for found, certain in self._read_parts(read, at, places):
                    edges.append(found)
                    if certain and name in every:
                        surely.add(found)

        def certain(found):
            found = list(found)
            edges.extend(found)
            surely.update(found)

        if part.kind == 'status':
            # Its cases in order: each after the first is read only when those before it do not hold.
            display, at = places[part]
            for k, case in enumerate(display.cases):
                made = Part('case', case.origin, part.owner)
                places.setdefault(made, (case, at))
                edges.append(made)
                if k == 0:
                    surely.add(made)
        elif part.kind == 'case':
            case, at = places[part]
            if case.test is not None:
                expression(case.test, at)
        elif part.kind == 'value':
            _, owner, value, at = places[part]
            own = at.member.value(value.name) if at.member is not None and at.event is None else None
            if value.kind != p.INPUT or (owner, value.name) not in self.given:
                expression(own if own is not None else value.init, at)
            for argument, caller in index.arguments.get((owner, value.name), ()):
                # The program admits every such start. Its record identifies which argument
                # evaluation produced the value of a particular occurrence.
                expression(argument, caller, branch=True)
            expression(value.lower, at)
            expression(value.upper, at)
            certain(writer.part for writer in index.writers.get((owner, value.name), ()))
            certain(stage for _, _, stage in index.defines.get((owner, value.name), ()))
        elif part.kind == 'network field':
            _, owner, declared, at, fields = places[part]
            name = fields[-1]
            if isinstance(declared, p.Value):
                side = fields[0]
                if name == 'actual_rate':
                    value = ('value', owner, declared, at)
                    for incident, definite in self._incident(value, side):
                        for rate, _ in _walked(self._step(incident, name)):
                            parts = self._point_parts(rate, places)
                            edges.extend(parts)
                            if definite:
                                surely.update(parts)
                else:
                    expression(getattr(getattr(declared, side), name, None), at)
            elif len(fields) == 2:
                # Each directional view is computed from the route's signed setting or answer.
                certain(self._point_parts(('rate', owner, declared, name, at), places))
            elif name == 'served_fraction':
                certain(self._point_parts(('flow', owner, declared, at), places))
            elif name in ('request', 'capacity'):
                expression(getattr(declared, name), at)
            else:
                # A named leg delivers its request times the fraction served for all its siblings.
                group = index.groups[owner, declared.origin]
                certain(self._point_parts(('rate', owner, group, 'served_fraction', at), places))
                certain(self._point_parts(('rate', owner, declared, 'request', at), places))
            certain(index.settings.get(part, ()))
        elif part.kind == 'rate':
            flow, solver = places[part]
            certain(self._point_parts(flow, places))
            certain([solver])
        elif part.kind == 'flow' and part in index.flows:
            writer = index.flows[part]
            expression(writer.value.request, writer.at)
            expression(writer.value.capacity, writer.at)
            for key, _ in (*writer.sources, *writer.sinks):
                point = self.value_point(*key)
                certain(self._point_parts(point, places))
                for side in (point[2].outflow, point[2].inflow):
                    if side is not None:
                        expression(side.capacity, point[3])
                        expression(side.request, point[3])
                # The other flows at an end share it with this one.
                certain(other.part for other in index.writers.get(key, ()) if other.kind in ('flow', 'route'))
            for name in ('request', 'capacity'):
                setting = Part('network field', f'{part.origin}.{name}', part.owner)
                certain(index.settings.get(setting, ()))
            if writer.event is not None:
                certain([Part('event', writer.event, part.owner)])
        elif part.kind == 'stage' and part in index.stages:
            step, at = index.stages[part]
            expression(step.guard, at)
            for statement, branch in _flat(step.body):
                for expr in _statement_exprs(statement):
                    expression(expr, at, branch)
                if isinstance(statement, p.Move):  # a move fits its stores, or fails whole
                    for end in (statement.source, statement.destination):
                        for point, _ in self.points(end, at, True):
                            found = self._point_parts(point, places)
                            edges.extend(found)
                            if not branch:
                                surely.update(found)
            certain([Part('event', at.event.origin, part.owner)])
        elif part.kind == 'event':
            certain(index.starters.get(part, ()))
        elif part.kind == 'trigger' and part in index.triggers:
            trigger, at = index.triggers[part]
            expression(trigger.test, at)
        elif part.kind == 'solver' and part in index.solvers:
            solver = index.solvers[part]
            template, member = self.rows[part.owner]
            at = _At(template, member, solver=solver)
            for unknown in solver.unknowns:
                for operand in (unknown.init, unknown.lower, unknown.upper, unknown.scale):
                    expression(operand, at)
            # A target supplies the solve's reference and bounds. Input aliases are names;
            # the target, constraint and objective expressions decide which ones are read.
            for target in solver.solve_for:
                for point, _ in self.points(target, at, True):
                    certain(self._point_parts(point, places))
            for item in solver.constraints:
                expression(item.test, at)
            for item in solver.objective:
                expression(item.expr, at)
        for definition in index.setup_definitions.get(part, ()):
            expression(definition, _At(), branch=True)
        edges = [edge for edge in edges if edge != part]
        return edges, {edge for edge in edges if edge not in surely}

    def _read_parts(self, read, at, places):
        """The fields a read can return and the fields that select them. Follow selectors in their
        own scopes: a predicate reads its row, a lookup reads its cutoff in its enclosing scope."""
        pending = [(read, at, True)]
        while pending:
            read, scope, certain = pending.pop()
            if isinstance(read, Reduce | Draw):
                read = read.source
            elif isinstance(read, Since):
                read = read.event
            elif isinstance(read, Elapsed):
                read = read.value
            if isinstance(read, Path):
                selection = _Selection([])
                for point, one in _walked(self._points(read, scope, True, selection)):
                    for part in self._point_parts(point, places):
                        yield part, certain and one
                pending.extend(
                    (selector, place, certain and sure) for selector, place, sure in selection.reads
                )

    def _point_parts(self, point, places):
        """The parts that a point names: a value, a flow (each leg of a flow with legs), an event or
        a solver."""
        kind = point[0]
        if kind == 'rate' and point[3] in ('actual_rate', 'served_fraction'):
            _, owner, flow, field, at = point
            solver = self.index().rate_solvers.get((owner, flow.origin))
            if solver is not None:
                part = Part('rate', f'{flow.origin}.{field}', at.member.id)
                places[part] = (('flow', owner, flow, at), solver)
                return [part]
        if kind == 'value':
            part = Part('value', point[2].origin, point[1])
            places.setdefault(part, point)
            return [part]
        if kind == 'rate':
            _, owner, flow, name, at = point
            if name in ('request', 'capacity', 'served_fraction') or (
                name == 'actual_rate' and (owner, flow.origin) in self.index().groups
            ):
                point = ('network field', owner, flow, at, (name,))
                kind = point[0]
        if kind == 'network field':
            _, _, declared, at, fields = point
            part = Part(kind, '.'.join((declared.origin, *fields)), at.member.id if at.member else '')
            places.setdefault(part, point)
            return [part]
        if kind in ('flow', 'rate', 'leg'):
            # A rate's point is (kind, owner, flow, name, at); a flow's and a leg's keep `at` fourth.
            flow, at = point[2], point[4] if kind == 'rate' else point[3]
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
    definitions that stages and the setup give each formula, as (origin, event, stage); the parts that
    start each event on each receiver; the stages that assign a setting of each flow (its request or
    its capacity); and each flow, stage, trigger and solver by its part."""

    writers: dict = field(default_factory=dict)
    defines: dict = field(default_factory=dict)
    setup_definitions: dict = field(default_factory=dict)
    starters: dict = field(default_factory=dict)
    arguments: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    flows: dict = field(default_factory=dict)
    groups: dict = field(default_factory=dict)
    stages: dict = field(default_factory=dict)
    triggers: dict = field(default_factory=dict)
    solvers: dict = field(default_factory=dict)
    rate_solvers: dict = field(default_factory=dict)


def _term(key):
    """The term of a linear form that a record key of a stored number names: its owner (the
    occurrences of an event on a receiver share one, `tank.receive#`) and its name."""
    owner = key.owner.rsplit('#', 1)[0] + '#' if '#' in key.owner else key.owner
    return (owner, key.steps[0]) if len(key.steps) == 1 else None


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _named(writer):
    """A writer as a reason names it: its origin, and the member that runs it."""
    return f'{writer.origin} of {writer.part.owner}' if writer.part.owner else writer.origin


def kind_of(value_type):
    """A type in words, as a refusal names it: `a number`, `a yes/no`, `a text`, `a member of the enum
    Mode`, `a link to a Tank`, `a collection`, `a distribution`, `a reference to an occurrence of
    crew.repair`."""
    if isinstance(value_type, p.Number):
        return 'a number'
    if isinstance(value_type, p.Bool):
        return 'a yes/no'
    if isinstance(value_type, p.Text):
        return 'a text'
    if isinstance(value_type, p.EnumType):
        return f'a member of the enum {value_type.enum}'
    if isinstance(value_type, p.EntityType):
        return f'a link to a {value_type.template}'
    if isinstance(value_type, p.DistributionType):
        return 'a distribution'
    if isinstance(value_type, p.OccurrenceType):
        return f'a reference to an occurrence of {value_type.template}.{value_type.event}'
    return 'a collection'


def _reached(program, configuration, states):
    """The reachability of a program under a configuration (`reach`) when some named states can also
    take the values that the changes of a run give them, from the start: (state, values, reason)."""
    found = _Reach(program, configuration)
    for state, values, reason in states:
        if state in found.domains:
            found.add(state, values, reason)
    return found.run()


def _flat(statements, branch=False):
    """The statements of a body, with those of its branches: (statement, whether it is on a branch, a
    side of an `if` or the body of a case, which runs only when the branch is taken)."""
    for statement in statements:
        yield statement, branch
        if isinstance(statement, p.If):
            yield from _flat((*statement.then, *statement.orelse), True)
        elif isinstance(statement, p.Switch):
            yield from _flat(
                (*(each for case in statement.cases for each in case.body), *statement.orelse), True
            )


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
