"""What the picture reads of a compiled model (`napkin.model.compile.Compiled`): its things, the kind
of each of their values, and what each part of a thing reads, changes, starts and moves of the
others. Every module of the picture reads a model through one `Things`, so that one place knows the
declared model (`napkin/model/semantic.py`) and the program.

- **Cards** (`Card`). A card is a thing of the picture: an entity written once (its path, `tank`), a
  member of a template written by hand (its id, `north`), or a table, whose rows share one card (its
  name, `places`; `members` are its rows). A template has no card of its own: its members stand for
  it. The top level has no card: its values are on no card, and nothing points to them. The cards
  stand in the order of the model's lines; a table stands at its own line.
- **Kinds by use** (`kind`, change 14 of the plan). A stored number at an end of a flow, a leg, a
  route or a `move` is a `stock`, and a `tally` when nothing takes from it: it is the source of no
  flow, of no `move`, and at the end of no route (a route takes from both of its ends). Any other
  stored value is a `state` when a statement assigns it or a solver solves for it, and `fixed` when
  nothing does; a text is a `text`. An input is an `input`, a formula a `formula`, a distribution
  that is no input is `fixed`. The kinds are those of the declared value, the same for every member
  of a template.
- **Reads** (`reached`). A read of the typed form (`semantic.Read`) from the members of a card
  reaches parts of members: a value, a flow (its rates, its legs, its ends), an event (its
  occurrences and the time since it started), or a solver (its results). A link takes the read to
  the member that it names for each member, a collection to its members; `Template.instances` is
  every member of the template; `where`, `by` and `.at` keep every member of their source, since
  which of them a filter keeps is known only in a run; a parameter that passes an entity is any
  member of its template. `reads(expression)` gives each read of an expression, those inside the
  tests and keys of its keyed reads too, each with the members that an item of a `where` stands for.
- **Runs** (`runs`, `startable`). The runs of a model are its named runs, else its default run.
  Which events can start in a run is the reachability of the program under the run's configuration
  (`napkin.program.reach`, D16): an event that cannot start is proved so.
- **The library** of the model's package (`library`), for the references, and the **texts as the
  file writes them** (`written`): a condition of a trigger, from the parsed tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from ..model import semantic as s
from ..model.language import format as formatter
from ..model.views import instances
from ..program.reach import reach
from .text import in_words

ENTITY, MEMBER, TABLE = 'entity', 'member', 'table'
# The kinds of a value (`Things.kind`).
KINDS = ('input', 'fixed', 'state', 'stock', 'tally', 'formula', 'text', 'link', 'collection', 'unknown')
STOCK_KINDS = ('stock', 'tally')
FLOWS = (s.DeclaredFlow, s.DeclaredLegs)


@dataclass(frozen=True)
class Card:
    """A thing of the picture: `id`, `title` (its title, else its name in words), `role` (its
    template's for a member or a table), `template` (the path of the declared entity or template whose
    parts its members have), `members` (their ids), `line`, `text` and `kind` (`entity`, `member` or
    `table`). `shown_template` is the template's name for a member or a table, else None."""

    id: str
    title: str
    role: str | None
    template: str
    members: tuple
    line: int
    text: str | None
    kind: str

    @property
    def shown_template(self):
        return None if self.kind == ENTITY else self.template


@dataclass(frozen=True)
class Reached:
    """What a read reaches: `what` is `value`, `local`, `flow`, `event`, `solver` or `member` (an
    entity, read for its fields elsewhere); `members` the ids of the members that own it; `name` its
    path below their template (`water`, `restore.labor`, `refill`), or None for a member; `steps` the
    steps after it (`actual_rate`, `outflow`, `occurrences`)."""

    what: str
    members: tuple
    name: str | None
    steps: tuple = ()


def walk_expression(expression, item=()):
    """Each read of a typed expression with the members that an item of a `where` stands for in it:
    (read, item). The reads inside the test of a `where` and the key of a lookup come after the read
    whose start they are; a constant reads nothing."""
    if isinstance(expression, s.Read):
        yield expression, item
        yield from _start_reads(expression.start, item)
    elif isinstance(expression, s.Reduced):
        yield from walk_expression(expression.source, item)
    elif isinstance(expression, s.Apply):
        for arg in expression.args:
            yield from walk_expression(arg, item)
    elif isinstance(expression, s.Retain):
        yield from walk_expression(expression.body, item)
    elif isinstance(expression, (s.Drawn, s.Chosen)):
        if isinstance(expression, s.Chosen):
            yield from walk_expression(expression.actor, item)
        if isinstance(expression.source, s.Read):
            yield from walk_expression(expression.source, item)
    elif isinstance(expression, s.History):
        yield from walk_expression(expression.source, item)
        if expression.delay is not None:
            yield from walk_expression(expression.delay, item)
    elif isinstance(expression, tuple):
        for part in expression:
            yield from walk_expression(part, item)


def _start_reads(start, item):
    kind = start[0]
    if kind == 'literal':
        for read in start[1]:
            yield from walk_expression(read, item)
    elif kind in ('where', 'by', 'lookup'):
        yield from walk_expression(start[1], item)
        if kind == 'where':
            # The item of the test is a member of the source: the test reads its fields.
            yield from walk_expression(start[2], ('of', start[1]))
        elif kind == 'lookup':
            yield from walk_expression(start[2], item)


class Things:
    """The things of one compiled model (see the module's text)."""

    def __init__(self, compiled):
        self.compiled = compiled
        self.declared = declared = compiled.declared
        self.program = compiled.program
        self.entities = {entity.path: entity for entity in declared.entities}
        self.cards = {card.id: card for card in self._cards()}
        self.card_of = {member: card.id for card in self.cards.values() for member in card.members}
        self.template_of = {member: card.template for card in self.cards.values() for member in card.members}
        self.ends, self.written_values = self._uses()

    # ---- the cards and their members

    def _cards(self):
        declared, found = self.declared, []
        for entity in declared.entities:
            if not isinstance(entity, s.DeclaredTemplate):
                title = entity.title or in_words(entity.path)
                found.append(
                    Card(entity.path, title, entity.role, entity.path, (entity.path,), entity.line, entity.text, ENTITY)
                )
        for member in declared.members:
            if member.table is None:
                role = self.entities[member.template].role
                found.append(
                    Card(
                        member.path,
                        in_words(member.path),
                        role,
                        member.template,
                        (member.path,),
                        member.line,
                        member.text,
                        MEMBER,
                    )
                )
        for table in declared.tables:
            role = self.entities[table.template].role
            found.append(
                Card(
                    table.path, in_words(table.path), role, table.template, table.members, table.line, table.text, TABLE
                )
            )
        return sorted(found, key=lambda card: card.line)

    def members_of(self, template):
        """The ids of the members of a template (an entity written once is its own), in creation
        order."""
        if template in self.entities and not isinstance(self.entities[template], s.DeclaredTemplate):
            return (template,)
        return self._members.get(template, ())

    @cached_property
    def _members(self):
        out = {}
        for template in self.program.templates:
            out[template.name] = tuple(member.id for member in template.members)
        return out

    @cached_property
    def links(self):
        """{member id: {link: the id of the member that it names}} of every member with a link."""
        out = {}
        for entity in self.declared.entities:
            if any(isinstance(part, s.DeclaredValue) and part.kind == s.LINK for part in entity.parts):
                for found in instances(self.compiled, entity.path):
                    out[found['name']] = found['links']
        return out

    def parts(self, card):
        """The declared parts of a card's template, in written order."""
        return self.entities[self.cards[card].template].parts

    def part(self, template, name):
        """The declared part `name` (a path below the template, `water`, `restore.labor`) of a
        template, or None."""
        return self.declared.part(f'{template}.{name}')

    def title_of(self, member):
        """The words of a member: its card's title, and for a row its card's title and its id."""
        card = self.cards.get(self.card_of.get(member))
        if card is None:
            return in_words(member)
        if card.kind != TABLE:
            return card.title
        return f'{card.title} {member.rpartition(".")[2]}'

    # ---- the kinds of the values

    def _uses(self):
        """({value path: {'in', 'out'}} of each stored number at an end of a flow, a leg, a route or a
        move; the paths of the values that a statement assigns or a solver solves for)."""
        ends, written = {}, set()

        def end(read, side):
            if isinstance(read, s.Read) and read.part:
                ends.setdefault(read.part, set()).add(side)

        def flow(part):
            for leg in part.legs if isinstance(part, s.DeclaredLegs) else (part,):
                both = isinstance(leg, s.DeclaredRoute)
                end(leg.source, 'out')
                end(leg.sink, 'in')
                if both:
                    end(leg.source, 'in')
                    end(leg.sink, 'out')

        for entity in self.declared.entities:
            for part in entity.parts:
                if isinstance(part, FLOWS):
                    flow(part)
                elif isinstance(part, s.DeclaredEvent):
                    for local in part.locals:
                        if isinstance(local, FLOWS):
                            flow(local)
                    for statement in event_statements(part):
                        if isinstance(statement, s.DeclaredMove):
                            end(statement.source, 'out')
                            end(statement.destination, 'in')
                        elif isinstance(statement, s.DeclaredAssign) and statement.target.part:
                            written.add(statement.target.part)
                elif isinstance(part, s.DeclaredSolver):
                    written.update(read.part for read in part.solve_for if read.part)
        return ends, written

    def kind(self, value):
        """The kind of a declared value (see the module's text)."""
        if value.kind == s.INPUT:
            return 'input'
        if value.kind == s.FORMULA:
            return 'formula'
        if value.kind == s.DISTRIBUTION:
            return 'fixed'
        if value.kind in (s.LINK, s.COLLECTION, s.UNKNOWN):
            return value.kind
        if value.type == s.TEXT:
            return 'text'
        use = self.ends.get(value.path)
        if use is not None and isinstance(value.type, s.Num):
            return 'stock' if 'out' in use else 'tally'
        return 'state' if value.path in self.written_values else 'fixed'

    def values(self, card):
        """The declared values of a card's template, in written order."""
        return [part for part in self.parts(card) if isinstance(part, s.DeclaredValue)]

    def stocks(self, card):
        """The stocks and tallies of a card, in written order."""
        return [value for value in self.values(card) if self.kind(value) in STOCK_KINDS]

    def machines(self, card):
        """The stored values of named states of a card (a stored enum), in written order."""
        return [
            value for value in self.values(card) if value.kind == s.STATE and isinstance(value.type, s.EnumOf)
        ]

    def events(self, card):
        """The events of a card, in written order."""
        return [part for part in self.parts(card) if isinstance(part, s.DeclaredEvent)]

    # ---- reads

    def reached(self, read, members, item=()):
        """What a read reaches from the members `members` of `this` (`Reached`), or None for a read
        of the time, of the top level, or of a local of the occurrence that reads it. `item` is the
        context of a read in the test of a `where` (`walk_expression`)."""
        kind = read.start[0]
        if kind in ('time', 'root'):
            return None
        if kind == 'local':
            if not read.steps:
                return Reached('local', tuple(members), read.start[1]) if read.part else None
            # A parameter that passes an entity: any member of the template of what it reads.
            template = read.part.rpartition('.')[0] if read.part else None
            if template is None or template not in self.entities:
                return None
            return self._walk(self.members_of(template), read.steps)
        start = self.start_members(read.start, members, item)
        return self._walk(start, read.steps)

    def start_members(self, start, members, item=()):
        """The members that the start of a read stands for."""
        kind = start[0]
        if kind == 'this':
            return tuple(members)
        if kind == 'named':
            return (start[1],)
        if kind == 'item':
            return self.member_set(item[1], members) if item else ()
        if kind == 'instances':
            return self.members_of(start[1])
        if kind == 'literal':
            return tuple(dict.fromkeys(m for read in start[1] for m in self.member_set(read, members, item)))
        if kind in ('where', 'by', 'lookup'):
            return self.member_set(start[1], members, item)
        return ()

    def member_set(self, read, members, item=()):
        """The members that a read of a member or a collection stands for."""
        found = self.reached(read, members, item)
        return () if found is None or found.what != 'member' else found.members

    def _walk(self, current, steps):
        for k, step in enumerate(steps):
            if not current:
                return Reached('member', (), None)
            template = self.template_of.get(current[0])
            if template is None:
                return None
            part = self.part(template, step)
            if isinstance(part, s.DeclaredValue) and part.kind == s.LINK:
                current = tuple(dict.fromkeys(self.links.get(m, {}).get(step) for m in current) - {None})
                continue
            if isinstance(part, s.DeclaredValue) and part.kind == s.COLLECTION:
                current = tuple(dict.fromkeys(m for owner in current for m in self.member_set(part.init, (owner,))))
                continue
            rest = tuple(steps[k + 1 :])
            if isinstance(part, s.DeclaredValue):
                return Reached('value', current, step, rest)
            if isinstance(part, (s.DeclaredFlow, s.DeclaredLegs)):
                return Reached('flow', current, step, rest)
            if isinstance(part, s.DeclaredEvent):
                return Reached('event', current, step, rest)
            if isinstance(part, s.DeclaredSolver):
                return Reached('solver', current, step, rest)
            return None
        return Reached('member', tuple(current), None)

    # ---- runs

    @cached_property
    def runs(self):
        """The runs of the model: the names of its named runs, else (None,) for its default run."""
        return tuple(run.name for run in self.declared.runs) or (None,)

    def configuration(self, run):
        """The configuration of a run (None for the default run), or None for a model with no
        horizon."""
        return self.compiled.base if run is None else self.compiled.configure(run)

    def startable(self, run):
        """{event origin: whether it can start} under a run's configuration (`reach`)."""
        key = ('startable', run)
        if key not in self._cache:
            found = reach(self.program, self.configuration(run))
            self._cache[key] = {origin: can for origin, (can, _) in found.events.items()}
        return self._cache[key]

    @cached_property
    def _cache(self):
        return {}

    # ---- the files

    @cached_property
    def origin(self):
        """The entry file of the model, or None for a model of one text."""
        files = self.declared.files
        return Path(files[-1][0]) if files else None

    def file_of(self, card):
        """The file that writes a card's line, as the model names it, or None for a model of one
        text."""
        name, _ = self.declared.place(self.cards[card].line)
        return name or None

    @cached_property
    def library(self):
        """The library of the model's package (`napkin.model.library.load_library`), or the empty
        library of a model of one text."""
        from ..model.language.evidence import document
        from ..model.library import empty_library, load_library

        if self.origin is None or not self.origin.is_file():
            return empty_library()
        return load_library(self.origin, document=document(self.declared.tree))

    @cached_property
    def _lines(self):
        """{(the class of a node of the tree, its line): the node}, of every line of the tree."""
        found = {}

        def visit(node):
            if isinstance(node, tuple):
                for item in node:
                    visit(item)
                return
            if not hasattr(node, '__dataclass_fields__'):
                return
            line = getattr(node, 'line', None)
            if line is not None:
                found.setdefault((type(node).__name__, line), node)
            for name in node.__dataclass_fields__:
                if name not in ('lead', 'tail', 'cites', 'evidence'):
                    value = getattr(node, name)
                    if isinstance(value, tuple) or hasattr(value, '__dataclass_fields__'):
                        visit(value)

        tree = self.declared.tree
        visit(tree.items if tree is not None else ())
        return found

    def written(self, kind, line, field):
        """The text of the expression `field` of the line of class `kind` (`Trigger`, `Stage`) at
        `line`, as the file writes it, or None."""
        node = self._lines.get((kind, line))
        value = getattr(node, field, None) if node is not None else None
        return None if value is None else formatter.expression(value)


def event_statements(event):
    """Each statement of the stages of an event, and of the branches inside them, outermost first."""
    for step in event.steps:
        if isinstance(step, s.DeclaredStage):
            yield from s.statements_of(step.body)
