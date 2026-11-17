"""The resolver: the parts of a file (`nodes.File`) as the semantic model that the builder reads
(`semantic.Scenario`), in the order of the file (docs/language.md).

- **Entities** go in the order of the file. A template makes no entity; each instance makes one, or
  one for each copy (`name.1` …). An instance has its template's members in the template's order,
  with its own changes applied.
- **Names.** In an entity, a bare name is a member of the entity, and `a.x` reads member `x` of
  entity `a` or through link `a`; a chain of links reads on (`region.diesel.demand`). At the top
  level, `a.x` is member `x` of entity `a`, and a bare name an output.
- **Fields.** A `var` that a flow or a move takes from, or that a line lowers or sets, is a stock when
  a flow or a move joins it, and a number state otherwise; one that flows and moves only fill is a
  tally. A named or yes/no `var` is a state.
- **Events.** An event has its outcomes: the lines under it are its one outcome, `done`. An event
  orders the events of one moment by the place of its line in the file (`rank`).
- **Evidence** passes from no declaration to another: a line with no records of its own has none,
  except the parts that the builder falls back for (a pair to its flow, a rate to its value, a status
  to its entity).

A problem of the file that the builder would not find is a diagnostic here; the problems of the parts
that the builder reads wait in the semantic model, so that the builder reports them in its own order.
"""

from __future__ import annotations

import ast
import dataclasses
import keyword
import re

from ...core import expr as typed
from ...core.errors import ExpressionError
from ...core.units import UnitSystem
from .. import resolved
from ..ir import DRAWN, close_names, diagnostic, freeze, thaw
from ..semantic import (
    BASE_RUN,
    Allocation,
    Assign,
    Bound,
    Case,
    Check,
    Entity,
    Event,
    EventRef,
    Expression,
    Fault,
    Fire,
    Flow,
    Group,
    Lag,
    Move,
    Outcome,
    Output,
    Pair,
    Problem,
    Profile,
    Range,
    Ref,
    Run,
    Scenario,
    Setting,
    Site,
    Start,
    Status,
    Terms,
    Time,
    Value,
    Word,
    Words,
    first_text,
    in_words,
    value_label,
)
from ..types import family_of, hours, time_units
from ..uncertain import is_distribution, reads
from . import evidence as records
from . import expressions, lex
from .format import one_line
from .lex import RESERVED, SyntaxProblem, Token
from .nodes import Allocate as AllocateNode
from .nodes import Assign as AssignLine
from .nodes import Change as ChangeNode
from .nodes import Check as CheckNode
from .nodes import Event as EventNode
from .nodes import Expr, LinkBind, LinkDecl
from .nodes import Fire as FireLine
from .nodes import Flow as FlowNode
from .nodes import Move as MoveLine
from .nodes import Output as OutputNode
from .nodes import Status as StatusNode
from .nodes import Value as ValueNode

MEASURES = {'cumulative': 'cumulative', 'level': 'stock'}
# An entity as a cell of a table names it: a name, or a copy of a set (`sites.3`).
ENTITY_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[0-9]+)?')
# The tokens of a cell that gives a number, with the unit of its column or without one.
NUMBER_CELLS = (('number',), ('number', 'unit'), ('op', 'number'), ('op', 'number', 'unit'))
BRACES = re.compile(r'\{([A-Za-z_][A-Za-z0-9_.]*)\}')


class Problems(Exception):
    """The diagnostics of a file that the resolver rejects."""

    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__(diagnostics)


@dataclasses.dataclass
class Body:
    """One entity of the file: its declaration, its template, and its members merged."""

    name: str
    entry: str
    copy: int | None
    decl: object
    template: object
    values: dict  # {name: (member, change or None)}, in the template's order
    links: dict  # {name: entity, or a list of entities}
    sequence: list  # the events, flows and shares, in order
    checks: list
    status: object
    support: list


@dataclasses.dataclass(frozen=True)
class Kept:
    """The rows of each table that a model of representatives keeps (`model/hybrid.py`): {the thing of
    a table: the numbers of its rows, in order}, and for each instance that a link cell can name the
    instance that stands for it (`stands`, {name: name})."""

    rows: dict
    stands: dict


class Resolver:
    def __init__(self, file, library, files=None, only=None):
        self.file = file
        self.only = only
        # {place: file} of a model of several files (`modules.read`), and the line of the model where each
        # file starts, so that the lines of the model are in the order of its files (the rank of events).
        self.files = dict(files or {})
        self.offsets, total = {}, 0
        for path in dict.fromkeys(self.files.values()):
            self.offsets[path] = total
            total += max((n for place, n in file.lines.items() if self.files.get(place) == path), default=0)
        self.library = library
        self.time_units = set(time_units(library['units']))
        self.errors = []
        # {(entity, member): whether the formula reads inputs only} (`of_inputs`), which holds once the
        # bodies and the kinds of the vars are made.
        self.inputs_only = {}
        self.evidence = records.Evidence(file)
        self.used_units = set()
        # {set: {column: 'title', 'link' or 'value'}} of the columns that the rows of a table give
        # (`columns`), and the problems of tables that are reported already.
        self.table_reads = {}
        self.table_problems = set()

    def fail(self, place, message):
        item = diagnostic('structure', '/'.join(map(str, place)), message)
        if len(place) > 1 and place[1] == 'table:':
            # Each instance of a table reads the columns of the table: a problem of a column is one
            # problem, not one for each row.
            if (item['path'], item['message']) in self.table_problems:
                return
            self.table_problems.add((item['path'], item['message']))
        self.errors.append(item)

    def stop(self):
        if self.errors:
            raise Problems(self.errors)

    # ---- the index of the file ----------------------------------------------------------------------

    def index(self):
        file = self.file
        if file.scenario is None:
            raise Problems(
                [
                    diagnostic(
                        'version',
                        'scenario:',
                        'A model file starts with its scenario line, scenario "Title", or is a variant, '
                        'variant "Title": a file that starts with another declaration is a module',
                    )
                ]
            )
        self.keyword_names()
        self.form()
        self.stop()
        self.templates = {t.name: t for t in file.things if t.kind == 'template'}
        for template in self.templates.values():
            for member in template.members:
                if isinstance(member, LinkDecl) and member.target not in self.templates:
                    self.fail(
                        member.place,
                        f'{member.target} is not a template: a link of a template names the template of '
                        'the entities that it links to',
                    )
        declared = [t for t in file.things if t.kind == 'entity']
        self.declared = {t.name: t for t in declared}
        for thing in declared:
            if thing.template is not None and thing.template not in self.templates:
                self.fail(thing.place, f'{thing.template} is not a template')
        self.stop()
        # The entities, in the order of the file; copy k of a set is `name.k`.
        self.copy_sets = {}
        names = []
        for thing in declared:
            if thing.copies is not None:
                self.copy_sets[thing.name] = [f'{thing.name}.{k}' for k in range(1, thing.copies + 1)]
                names += [(copy, thing, k) for k, copy in enumerate(self.copy_sets[thing.name], 1)]
            elif thing.table is not None:
                # One instance for each row of the table: a set of copies, each with its row's values.
                self.columns(thing)
                rows = range(1, len(thing.table.rows or ()) + 1)
                if self.only is not None:
                    rows = self.only.rows.get(thing.name, rows)
                self.copy_sets[thing.name] = [f'{thing.name}.{k}' for k in rows]
                names += [(f'{thing.name}.{k}', thing, k) for k in rows]
            else:
                names.append((thing.name, thing, None))
        self.bodies = {}
        for name, thing, k in names:
            self.bodies[name] = self.body(name, thing, k)
        self.instances = {}
        for name, body in self.bodies.items():
            if body.template is not None:
                self.instances.setdefault(body.template.name, []).append(name)
        self.stop()
        self.links()
        self.var_kinds()
        self.kinds()

    def keyword_names(self):
        """A name of the file is never a word that Python keeps for itself (`in`, `for`, `class`): the
        engine reads the names of the structure in Python expressions. Nor is it a reserved word of the
        language (docs/language.md, §2.1)."""
        for thing in self.file.things:
            for name, place in [(thing.name, thing.place)] + [
                (member.name, member.place)
                for member in thing.members
                if getattr(member, 'name', None) and not isinstance(member, ChangeNode)
            ]:
                if keyword.iskeyword(name):
                    self.fail(place, f'{name} cannot be a name: the engine reads names in Python expressions')
                elif name in RESERVED:
                    self.fail(place, f'{name} is not a usable name: the language keeps the word for itself')

    def form(self):
        """The rules that the parts of the file obey by themselves (docs/language.md, §2): the
        times and the scope of the scenario block, roles, named values, sizes, the texts of values, the
        measures of outputs, and the start's change."""
        block = self.file.scenario
        scales = time_units(self.library['units'])
        horizon = None
        if block.horizon is not None:
            horizon = hours(text_of(block.horizon.tokens), scales)
            if horizon is not None and horizon <= 0:
                self.fail(block.horizon.place, 'the horizon is a time after the start: more than 0 h')
                horizon = None
        if block.resolution is not None:
            step = hours(text_of(block.resolution.tokens), scales)
            if step is None:
                self.fail(block.resolution.place, 'the resolution is a time with its unit: resolution 7 days')
            elif step <= 0 or (horizon is not None and step > horizon):
                self.fail(
                    block.resolution.place, 'the resolution is a time from more than 0 h to the horizon'
                )
        if block.scope is not None and not block.scope.value.strip():
            self.fail(
                block.scope.place,
                'the scope of the scenario is nonempty text, for the outputs that give none',
            )
        if block.timescales is not None and not block.timescales:
            self.fail(
                (*block.place, 'timescales:'),
                'timescales lists the inputs that set the shortest physical times',
            )
        for thing in self.file.things:
            if thing.role is not None and not NAME.fullmatch(str(thing.role)):
                self.fail((*thing.place, 'role:'), f'a role is a name, not {thing.role}')
            for member in thing.members:
                if isinstance(member, ValueNode):
                    self.value_form(member)
                    if member.output is not None:
                        self.output_form(member.output, member.place)
                elif isinstance(member, OutputNode):
                    self.output_form(member.lines, member.place)
                elif isinstance(member, ChangeNode) and member.lines is not None:
                    self.value_form(member.lines)
                    if member.lines.output is not None:
                        self.output_form(member.lines.output, member.lines.place)
        for output in self.file.outputs:
            self.output_form(output.lines, output.place)

    def value_form(self, member):
        """A value's named values, size and text."""
        if isinstance(member.type, list):
            for value in member.type:
                if not NAME.fullmatch(value):
                    self.fail(member.place, f'a named value is a name, not "{value}"')
            twice = sorted({value for i, value in enumerate(member.type) if value in member.type[:i]})
            if twice:
                listed = ', '.join(f'"{value}"' for value in twice)
                self.fail(
                    member.place, f'a value with named values lists each value once, not {listed} twice'
                )
        if member.size is not None:
            tokens = member.size.expr.tokens if member.size.expr is not None else []
            number = tokens[0].value if tokens and tokens[0].kind == 'number' else None
            plain = len(tokens) == 1 or (len(tokens) == 2 and tokens[1].kind == 'unit')
            if number is None or not plain or float(number) <= 0:
                self.fail(
                    member.size.place,
                    f'size: is a number above 0 with its unit, the size that the value reaches, not '
                    f'{text_of(tokens)}',
                )
        if member.text is not None and not isinstance(member.text.value, str):
            self.fail(member.text.place, 'the text of a value, its label, is one nonempty text')

    def text_form(self, expr, place):
        """A text value is one text in quotes: the words that braces show."""
        if expr is not None and not (len(expr.tokens) == 1 and expr.tokens[0].kind == 'text'):
            self.fail(place, f'a text value is a text in quotes, not {text_of(expr.tokens)}')

    def output_form(self, lines, place):
        """An output's measure and its scope. Its category is a tag that the language does not read."""
        if lines is None:
            return
        if lines.measure is not None and lines.measure not in MEASURES:
            self.fail(
                lines.keys.get('measure', place),
                f'measure: is one of {", ".join(MEASURES)}, not {lines.measure}',
            )
        if lines.scope is not None and not lines.scope.value.strip():
            self.fail(lines.scope.place, 'the scope of an output is nonempty text: whom it covers')

    def body(self, name, thing, k):
        template = self.templates.get(thing.template) if thing.template else None
        values, sequence, checks = {}, [], []
        status = None
        links = {}
        source = template if template is not None else thing
        for member in source.members:
            if isinstance(member, (ValueNode, OutputNode)):
                values[member.name] = (member, None)
            elif isinstance(member, (EventNode, FlowNode, AllocateNode)):
                sequence.append(member)
            elif isinstance(member, CheckNode):
                checks.append(member)
            elif isinstance(member, StatusNode):
                status = member
            elif isinstance(member, (LinkDecl, LinkBind)):
                links[member.name] = member
        if template is not None:
            members = {m.name for m in template.members if hasattr(m, 'name') and m.name}
            for member in thing.members:
                if isinstance(member, StatusNode):
                    status = member
                elif isinstance(member, CheckNode):
                    checks.append(member)
                elif isinstance(member, LinkBind):
                    if member.name not in links:
                        self.fail(
                            member.place, f'{member.name} is not a link of the template {template.name}'
                        )
                    links[member.name] = member
                elif isinstance(member, ChangeNode):
                    # A change of a value; a change of an event or a flow is read with it.
                    if member.name not in members:
                        self.fail(
                            member.place,
                            f'{member.name} is not a member of the template {template.name}: an instance '
                            'changes the members of its template, and adds none',
                        )
                    elif member.name in values:
                        values[member.name] = (values[member.name][0], member)
                else:
                    self.fail(member.place, 'an instance changes the members of its template, and adds none')
        if thing.table is not None and k is not None:
            self.row(thing, k, values, links)
        support = thing.support if (template is None or thing.support) else template.support
        return Body(
            name,
            thing.name,
            k,
            thing,
            template,
            values,
            links,
            sequence,
            checks,
            status,
            support,
        )

    # ---- the table of a set of instances (docs/language.md, §2.3) ---------------------------------

    @staticmethod
    def is_text(member):
        """Whether a value of a template takes a text: a named state, or a text value."""
        if isinstance(member.type, list):
            return True
        tokens = member.value.tokens if member.value is not None else []
        return len(tokens) == 1 and tokens[0].kind == 'text'

    def columns(self, thing):
        """Check the columns of the table of a set against its template, once for the table: a column
        gives a value of the template, one entity for a link of the template, or the title of each
        instance; and a line under the thing does not give what a column gives."""
        template = self.templates[thing.template]
        members = {m.name: m for m in template.members if isinstance(m, ValueNode)}
        links = {m.name: m for m in template.members if isinstance(m, LinkDecl)}
        given = {m.name for m in thing.members if isinstance(m, (ChangeNode, LinkBind))}
        reads = self.table_reads[thing.name] = {}
        for column in thing.table.columns or ():
            name, at = column.name, column.place
            both = f'a line under {thing.name} and a column of its table both give {name}: one gives it'
            if name in members:
                if name in given:
                    self.fail(at, both)
                elif column.type and (self.is_text(members[name]) or members[name].type == 'bool'):
                    self.fail(at, f'{name} takes no number: its column has no unit')
                elif self.column_unit(column, members[name]) is not None:
                    # One problem for the column, at its header: its rows are not read.
                    self.fail(at, self.column_unit(column, members[name]))
                else:
                    reads[name] = 'value'
            elif name in links:
                if links[name].many:
                    self.fail(
                        at,
                        f'{name} is a list link: a cell names one entity; bind the list in a line under '
                        f'{thing.name}',
                    )
                elif name in given:
                    self.fail(at, both)
                elif column.type or column.support:
                    self.fail(at, f'{name} is a link: its column names entities, with no unit and no record')
                else:
                    reads[name] = 'link'
            elif name == 'title':
                if thing.title is not None:
                    self.fail(at, both)
                elif column.type or column.support:
                    self.fail(at, 'the column title is a text, with no unit and no record')
                else:
                    reads[name] = 'title'
            else:
                self.fail(
                    at,
                    f'{name} is not a value or a link of the template {template.name}: a column gives a '
                    'member of the template, or the title' + close_names(name, [*members, *links, 'title']),
                )

    def column_unit(self, column, member):
        """What is wrong with the unit of a column of numbers, or None: the unit is a unit of the
        library, of the kind of the unit of its member. A unit with a name in braces is read for each
        instance, with the text of that instance."""
        own = member.type
        if not column.type or not isinstance(own, str) or '{' in own or '{' in column.type:
            return None
        if getattr(self, 'units', None) is None:
            self.units = UnitSystem(self.library['units'])
        try:
            given = self.units.parse_unit(column.type)
        except (ExpressionError, ValueError):
            return f'{column.type} is not a unit of the library'
        try:
            needed = self.units.parse_unit(own)
        except (ExpressionError, ValueError):
            return None  # the problem of the template's own line
        if not given.compatible(needed):
            return f'the column {column.name} is in {column.type}, and {column.name} is in {own}'
        return None

    def row(self, thing, k, values, links):
        """Give instance k of the set of a table what its row gives: each cell that is not empty is the
        line `member = cell` of the instance, with the unit and the records of its column."""
        table = thing.table
        row = table.rows[k - 1]
        reads = self.table_reads.get(thing.name, {})
        for column, cell in zip(table.columns, row.cells):
            what = reads.get(column.name)
            if what in (None, 'title') or not cell:
                continue
            place = (*row.place, column.name)
            if what == 'link':
                if ENTITY_NAME.fullmatch(cell):
                    # In a model of representatives, a link names the instance that stands for its
                    # target.
                    target = cell if self.only is None else self.only.stands.get(cell, cell)
                    links[column.name] = LinkBind(place, row.line, column.name, target, False)
                else:
                    self.fail(place, f'the cell {cell!r} names no entity')
                continue
            member = values[column.name][0]
            value = self.cell(member, column, cell, place, row.line)
            if value is None:
                continue
            lines = ValueNode(place, row.line, None, column.name, value=value, support=list(column.support))
            # The records of the value are the header's: one line of the table for all its rows.
            lines.cited_at = column.place
            values[column.name] = (member, ChangeNode(place, row.line, column.name, None, lines))

    def cell(self, member, column, text, place, line):
        """The value that a cell gives, as the tokens of the value of the line `member = cell`
        (`cell_tokens`); a cell that gives no value is a problem at its place."""
        try:
            return Expr(place, line, cell_tokens(text, column.type, self.is_text(member), line))
        except SyntaxProblem as exc:
            self.fail(place, exc.message)
            return None

    def links(self):
        """Each entity's links, bound: {link: entity, or a list of entities}; and the template of the
        members of each list that has one (`list_types`)."""
        entities = set(self.bodies)
        self.list_types = {}
        for body in self.bodies.values():
            types = (
                {m.name: m for m in body.template.members if isinstance(m, LinkDecl)}
                if body.template is not None
                else {}
            )
            bound = {}
            for name, link in body.links.items():
                many_of = None  # the template of a list's members, when the list says it
                if name in entities or name in self.copy_sets or name in self.declared:
                    self.fail(link.place, f'the link {name} has the name of an entity')
                if isinstance(link, LinkDecl):
                    self.fail(
                        (*body.decl.place,),
                        f'{body.entry} binds the link {name} of its template: link {name} = …',
                    )
                    continue
                targets = link.targets
                many = link.many or (
                    isinstance(targets, str) and (targets in self.copy_sets or targets in self.templates)
                )
                if isinstance(targets, str) and targets in self.copy_sets:
                    targets = list(self.copy_sets[targets])
                elif isinstance(targets, str) and targets in self.templates:
                    many_of, targets = targets, list(self.instances.get(targets, ()))
                if name in types and types[name].many:
                    many_of = types[name].target
                if many and not targets and many_of is None:
                    self.fail(
                        link.place,
                        f'let {name} = []: an empty list takes the type of its slot: let {name}: [T] in the template',
                    )
                if many_of is not None:
                    self.list_types[body.name, name] = many_of
                for target in targets if isinstance(targets, list) else [targets]:
                    if target not in self.bodies:
                        self.fail(link.place, f'{target} is not an entity')
                bound[name] = list(targets) if many else targets
                if name in types:
                    self.link_type(types[name], link, bound[name])
            body.links = bound
        self.stop()

    def link_type(self, decl, link, bound):
        """The entities that an instance binds to a link of its template: one, or a list, as the template
        declares, each made with the template that it names."""
        if decl.many != isinstance(bound, list):
            self.fail(
                link.place,
                f'link {decl.name}: [{decl.target}] is a list: link {decl.name} = [a, b]'
                if decl.many
                else f'link {decl.name}: {decl.target} links to one entity: link {decl.name} = e',
            )
            return
        for target in bound if isinstance(bound, list) else [bound]:
            made = self.bodies.get(target)
            if made is not None and (made.template is None or made.template.name != decl.target):
                self.fail(link.place, f'{target} is not a {decl.target}')

    def var_kinds(self):
        """The kind of each number `var` (docs/language.md): a stock when a flow or a move joins it and
        something takes from it (a flow, a move, `-=` or `=`), a tally when a flow or a move joins it
        and nothing takes from it, and a number state when no flow or move joins it."""
        ends, drained = set(), set()

        def key(symbol, e):
            try:
                return self.member_of(symbol, e, ())
            except LookupError:
                return None

        for e, body in self.bodies.items():
            for node in body.sequence:
                if isinstance(node, FlowNode):
                    pairs = node.together if node.together is not None else [node.pair] if node.pair else []
                    for pair in pairs:
                        if pair.source != 'outside':
                            ends.add(key(pair.source, e))
                            drained.add(key(pair.source, e))
                        if pair.target != 'outside':
                            ends.add(key(pair.target, e))
                elif isinstance(node, EventNode):
                    for outcome in node.outcomes:
                        for line in outcome.lines:
                            if isinstance(line, MoveLine):
                                ends.update({key(line.source, e), key(line.target, e)})
                                drained.add(key(line.source, e))
                            elif isinstance(line, AssignLine) and line.op != '+=':
                                drained.add(key(line.target, e))
        self.var_kind = {}
        for e, body in self.bodies.items():
            for name, (member, change) in body.values.items():
                kind = (change.kind if change is not None and change.kind else None) or getattr(
                    member, 'kind', None
                )
                found = (e, name)
                if kind == 'state' and found in ends and not isinstance(getattr(member, 'type', None), list):
                    # A yes/no var that a flow or a move joins holds material: a stock or a tally,
                    # which the checks reject as a yes/no value (`binary_state`).
                    self.var_kind[found] = 'stock' if found in drained else 'tally'
                    continue
                if kind != 'var':
                    continue
                if found not in ends:
                    self.var_kind[found] = 'state'
                else:
                    self.var_kind[found] = 'stock' if found in drained else 'tally'

    def kinds(self):
        """The builder's kind of each value (`field_of`)."""
        self.kind = {}
        for e, body in self.bodies.items():
            for name in body.values:
                info = self.value_info(body, name)
                self.kind[(e, name)] = info['field']

    # ---- the parts of a value ---------------------------------------------------------------------

    def value_info(self, body, name):
        """The parts of a value of an entity: its template's member with the instance's change."""
        member, change = body.values[name]
        lines = change.lines if change is not None else None
        kind = (change.kind if change is not None and change.kind else None) or (
            'output' if isinstance(member, OutputNode) else member.kind if member is not None else None
        )
        if kind == 'var' or (kind == 'state' and (body.name, name) in self.var_kind):
            kind = self.var_kind.get((body.name, name), 'state')
        out = {'member': member, 'change': change, 'kind': kind}
        if isinstance(member, OutputNode):
            out['type'] = member.type
            out['value'] = None
            out['formula'] = member.expr
            text = lines.text if lines is not None and lines.text is not None else member.lines.text
            out['text'] = text.value if text is not None else None
        else:
            written_type = member.type if member is not None else None
            if change is not None and change.kind is not None:
                written_type = lines.type
            out['type'] = written_type
            given = lines.value if lines is not None and lines.value is not None else None
            out['value'] = given if given is not None else (member.value if member is not None else None)
            out['formula'] = out['value'] if kind == 'formula' else None
            text = lines.text if lines is not None and lines.text is not None else None
            if text is None and member is not None:
                text = member.text
            out['text'] = text.value if text is not None else None
        out['field'] = self.field_of(kind, out)
        return out

    def field_of(self, kind, info):
        """The builder's kind of a value (`build.field_kind`)."""
        if kind == 'text':
            return 'text'
        if kind in ('input', 'fixed'):
            return 'parameter'
        if kind in ('state', 'stock', 'tally'):
            return 'mode' if isinstance(info['type'], list) else 'quantity'
        if kind == 'formula':
            return 'inline' if info['type'] == 'bool' else 'computed'
        if kind == 'output':
            return 'output'
        return None

    # ---- names ----------------------------------------------------------------------------------

    def entity_of(self, parts, e, place, last=False):
        """The entity that the parts of a name mean, read in entity `e` (None: the top level)."""
        current = None
        if len(parts) > 1 and parts[0] in self.copy_sets and parts[1].isdigit():
            # One copy of a set, by its number: `waves.2`.
            if f'{parts[0]}.{parts[1]}' not in self.bodies:
                raise LookupError(f'{parts[0]} has no copy {parts[1]}')
            current, parts = f'{parts[0]}.{parts[1]}', parts[2:]
        for i, part in enumerate(parts):
            if current is None:
                if e is not None and part in self.bodies[e].links:
                    current = self.bodies[e].links[part]
                elif part in self.bodies:
                    current = part
                elif part in self.templates:
                    # A template's name is the list of its instances, in the order of the model.
                    current = list(self.instances.get(part, ()))
                else:
                    known = [*self.bodies, *self.templates, *(self.bodies[e].links if e is not None else ())]
                    message = f'{part} is not an entity or a link of {e}' if e else f'{part} is not an entity'
                    raise LookupError(message + close_names(part, known))
            else:
                if isinstance(current, list):
                    raise LookupError(
                        f'{parts[i - 1]} is a list: read it with sum(), or name its event on a line'
                    )
                links = self.bodies[current].links
                if part not in links:
                    raise LookupError(f'{part} is not a link of {current}' + close_names(part, links))
                current = links[part]
        if isinstance(current, list) and not last:
            raise LookupError(f'{".".join(parts)} is a list: read it with sum(), or name its event on a line')
        return current

    def list_template(self, parts, e):
        """The template of the members of the list that `parts` names in entity `e`: a template's own
        name, or a list link's slot or template; None when the list has no template."""
        if len(parts) == 1 and parts[0] in self.templates:
            return parts[0]
        owner = e if len(parts) == 1 else self.entity_of(parts[:-1], e, None)
        return self.list_types.get((owner, parts[-1]))

    def members(self, template):
        """The names of the members of a template."""
        return {m.name for m in self.templates[template].members if getattr(m, 'name', None)}

    def no_member(self, parts, e, member, what='a member'):
        """For a list with no members, the problem of a member that its template does not have, else None:
        the names of an empty list are still checked."""
        template = self.list_template(parts, e)
        if template is not None and member not in self.members(template):
            return f'{member} is not {what} of {template}'
        return None

    def member_of(self, symbol, e, place):
        """(entity, member) of a dotted name read in entity `e` (None: the top level): (None, output)
        for an output of the top level."""
        parts = symbol.split('.')
        if len(parts) == 1:
            if e is None:
                if any(output.name == symbol for output in self.file.outputs):
                    return None, symbol
                outputs = [output.name for output in self.file.outputs]
                message = f'unknown name {symbol}: at the top level, write entity.{symbol}'
                raise LookupError(message + close_names(symbol, outputs))
            return e, symbol
        owner = self.entity_of(parts[:-1], e, place)
        return owner, parts[-1]

    def ref(self, symbol, e, place):
        try:
            owner, member = self.member_of(symbol, e, place)
        except LookupError as exc:
            return Problem(message=str(exc))
        if owner is not None and member != 'copy' and (owner, member) not in self.kind:
            kind = self.member_kind(owner, member)
            if kind is None:
                message = f'{symbol} is not a value of {owner}'
                return Problem(message=message + close_names(member, self.member_names(owner)))
        return Ref(entity=owner, member=member, written=symbol)

    def member_names(self, owner):
        """The names of the values of an entity."""
        body = self.bodies.get(owner)
        return list(body.values) if body is not None else []

    def member_kind(self, owner, member):
        body = self.bodies.get(owner)
        if body is None:
            return None
        if member in body.values:
            return 'value'
        for item in body.sequence:
            if item.name == member:
                return type(item).__name__.lower()
        return None

    def event_ref(self, symbol, e, place):
        """What an event names (`event_target`), or why it names nothing."""
        try:
            kind, key, ending = self.event_target(symbol, e)
        except LookupError as exc:
            return Problem(message=str(exc))
        return EventRef(kind=kind, key=key, ending=ending, written=symbol)

    def event_target(self, symbol, e):
        """(`trigger`, `entity.event`, the outcome or None) of the name of an event, or of one of its
        outcomes (`find.done`, `respond.shut`)."""
        parts = symbol.split('.')
        found = self.event_named(parts, e)
        if found is not None:
            owner, event = found
            return 'trigger', f'{owner}.{event.name}', None
        if len(parts) > 1:
            found = self.event_named(parts[:-1], e)
            if found is not None:
                owner, event = found
                names = [outcome.name for outcome in event.outcomes] or ['done']
                if parts[-1] not in names:
                    raise LookupError(
                        f'{".".join(parts[:-1])} has no outcome {parts[-1]}: its outcomes are {", ".join(names)}'
                    )
                return 'trigger', f'{owner}.{event.name}', parts[-1]
        raise LookupError(f'{symbol} is not an event' + close_names(symbol, self.event_names(parts, e)))

    def event_names(self, parts, e):
        """The names of events that the file could write where `parts` names one in entity `e` (None: the
        top level): the events of `e` for a name of one part; else those of the entity that the name
        reads, or of every entity when it reads none, each after the name of its entity."""
        if len(parts) == 1:
            owners = {e: ''} if e in self.bodies else {}
        else:
            try:
                owner = self.entity_of(parts[:-1], e, ())
            except LookupError:
                owner = None
            if isinstance(owner, str) and owner in self.bodies:
                owners = {owner: '.'.join(parts[:-1]) + '.'}
            else:
                owners = {name: f'{name}.' for name in self.bodies}
        return [
            f'{written}{item.name}'
            for owner, written in owners.items()
            for item in self.bodies[owner].sequence
            if isinstance(item, EventNode)
        ]

    def event_named(self, parts, e):
        """(entity, event node) of the name of an event read in entity `e`, or None."""
        try:
            owner, name = (e, parts[0]) if len(parts) == 1 else (self.entity_of(parts[:-1], e, ()), parts[-1])
        except LookupError:
            return None
        if owner is None or isinstance(owner, list) or owner not in self.bodies:
            return None
        event = self.event_of(owner, name)
        return None if event is None else (owner, event)

    def line_of(self, node):
        """The line of a node in the order of the model: its file's line, after the lines of the files
        before it."""
        return self.offsets.get(self.files.get(node.place), 0) + node.line

    def event_of(self, e, name):
        return next(
            (item for item in self.bodies[e].sequence if isinstance(item, EventNode) and item.name == name),
            None,
        )

    # ---- expressions ----------------------------------------------------------------------------

    def expression(self, expr, e, place=None):
        """An expression of the file read in entity `e` (None: the top level): its typed nodes with its
        names resolved, or a `Problem`, and its written form."""
        place = place if place is not None else expr.place
        written = self.written(expr.tokens)
        try:
            tree, names = expressions.tree(expr.tokens)
        except SyntaxProblem as exc:
            return Expression(freeze(written), resolved.problem(exc.message), place)
        for token in expr.tokens:
            if token.kind == 'unit':
                self.used_units.add(token.value)
        try:
            node = resolved.of_tree(self.resolve_tree(tree, names, e, place))
            deep = typed.height(node) > typed.DEEPEST
        except RecursionError:
            deep = True  # a chain of many hundreds of operations
        if deep:
            # The readers of an expression go down its tree, and no further than this (D-75).
            node = resolved.problem(
                f'the expression has more than {typed.DEEPEST} operations one inside the other: '
                'write it in parts, each as a formula of its own'
            )
        return Expression(freeze(written), node, place)

    def written(self, tokens):
        """An expression as the file writes it (`written_of`)."""
        return written_of(tokens)

    def resolve_tree(self, tree, names, e, place):
        resolver = self

        class Resolve(ast.NodeTransformer):
            def visit_Name(self, node):
                if node.id in names:
                    return resolver.ref(names[node.id], e, place)
                if node.id in ('true', 'false'):
                    return Word(value=node.id == 'true', problem=f'unknown name {node.id}')
                return node

            def visit_Call(self, node):
                if isinstance(node.func, ast.Name) and node.func.id in DRAWN:
                    node.args = [self.visit(arg) for arg in node.args]
                    for keyword in node.keywords:
                        keyword.value = self.visit(keyword.value)
                    return node
                if isinstance(node.func, ast.Name) and node.func.id in names:
                    # A name of the file in the place of a function: the grammar reads a word that is no
                    # function of the language as a name, so the call names nothing that can be called.
                    return Problem(message=f'{names[node.func.id]} is not a function of the language')
                if not isinstance(node.func, ast.Name) or node.keywords:
                    return node
                name = node.func.id
                argument = node.args[0] if len(node.args) == 1 else None
                symbol = names.get(argument.id) if isinstance(argument, ast.Name) else None
                if name == 'count' and symbol is not None and resolver.is_list(symbol, e, place):
                    # `count(list.flag)`: the members of a list where a yes/no holds.
                    node.args = [resolver.terms(symbol, e, place)]
                    return node
                if name in ('since', 'count'):
                    if symbol is not None:
                        found = resolver.event_ref(symbol, e, place)
                        if isinstance(found, Problem) and name == 'since':
                            ref = resolver.ref(symbol, e, place)
                            if isinstance(ref, Ref) and resolver.is_state(ref):
                                node.func = ast.Name(id='elapsed', ctx=ast.Load())
                                node.args = [ref]
                                return node
                            found = Problem(message=f'{symbol} is not an event or a named state')
                        node.args = [found]
                    elif isinstance(argument, ast.Name) and argument.id == 't':
                        node.args = [Problem(message=f'{name}() takes an event')]
                    return node
                if name in ('sum', 'any', 'all'):
                    if symbol is not None:
                        node.args = [resolver.terms(symbol, e, place)]
                    return node
                if name in ('min', 'max'):
                    # An argument that names a list stands for each of its members.
                    node.args = [
                        resolver.terms(names[arg.id], e, place)
                        if isinstance(arg, ast.Name)
                        and arg.id in names
                        and resolver.is_list(names[arg.id], e, place)
                        else self.visit(arg)
                        for arg in node.args
                    ]
                    return node
                node.args = [self.visit(arg) for arg in node.args]
                return node

        return Resolve().visit(tree)

    def is_state(self, ref):
        """Whether a value is a named state, which `since()` times from."""
        body = self.bodies.get(ref.entity)
        if body is None or ref.member not in body.values:
            return False
        info = self.value_info(body, ref.member)
        return info['kind'] == 'state' and isinstance(info['type'], list)

    def is_list(self, symbol, e, place):
        """Whether `list.x` reads a value of each member of a list link, a template's instances or a
        set of copies."""
        head, _, member = symbol.rpartition('.')
        if not head or not member:
            return False
        if head in self.copy_sets:
            return True
        try:
            return isinstance(self.entity_of(head.split('.'), e, place, last=True), list)
        except LookupError:
            return False

    def terms(self, symbol, e, place):
        """`sum(list.x)`: x of each entity of a list link, or of each copy of a set."""
        head, _, member = symbol.rpartition('.')
        if not head:
            return Problem(message='sum() takes one value of a list link or of a set of copies: sum(list.x)')
        try:
            if (e is None and head in self.copy_sets) or (e is not None and head in self.copy_sets):
                owners = list(self.copy_sets[head])
            else:
                found = self.entity_of(head.split('.'), e, place, last=True)
                owners = found if isinstance(found, list) else [found]
            wrong = None if owners else self.no_member(head.split('.'), e, member)
        except LookupError as exc:
            return Problem(message=str(exc))
        if wrong is not None:
            return Problem(message=wrong)
        refs = [Ref(entity=owner, member=member, written=f'{owner}.{member}') for owner in owners]
        return Terms(refs=refs, written=symbol)

    # ---- texts ----------------------------------------------------------------------------------

    def fill(self, e, text, place, status=False):
        """A text with each `{name}` filled with the default of that text value of entity `e`, as
        written; a status names a text that no profile sets, because it reads one text in every run."""

        def replace(match):
            symbol = match.group(1)
            try:
                owner, member = self.member_of(symbol, e, place)
            except LookupError as exc:
                raise ValueError(str(exc)) from None
            info = (
                self.value_info(self.bodies[owner], member)
                if owner in self.bodies and member in self.bodies[owner].values
                else None
            )
            if info is None or info['field'] != 'text':
                raise ValueError(f'braces in a text name a text value: {symbol} is not one')
            settings = self.settings[0].get((owner, member), ())
            if status and settings:
                raise ValueError(
                    f'{symbol} changes with the options, and a status reads one text in every run'
                )
            return str(self.literal(info['value']))

        return BRACES.sub(replace, text)

    def words(self, e, text, place, status=False):
        try:
            return Words(self.fill(e, text, place, status), None, place)
        except ValueError as exc:
            return Words(None, str(exc), place)

    def literal(self, expr):
        """The value of a literal of the file: a number, a bool, a text, or the text of the tokens."""
        if expr is None:
            return None
        return self.written(expr.tokens)

    # ---- the scenario -----------------------------------------------------------------------------

    def scenario(self):
        self.index()
        file = self.file
        block = file.scenario
        groups = tuple(
            Group(
                group.name,
                tuple(
                    Profile(profile.name, freeze(profile.text.value if profile.text else None), profile.place)
                    for profile in group.profiles
                ),
                group.place,
            )
            for group in file.profiles
        )
        runs = tuple(
            Run(
                run.name,
                tuple(run.profiles),
                run.place,
                freeze(run.text.value) if run.text is not None else None,
                run.versus,
                run.versus_place or None,
            )
            for run in file.runs
        )
        if not runs and not groups:
            # A model with no runs and no options has one run, `base`, which takes the values as the
            # file writes them.
            runs = (Run(BASE_RUN, (), ('runs:', BASE_RUN)),)
        self.settings = self.profile_settings()
        entities = tuple(self.entity(name) for name in self.bodies)
        notes = records.notes_of(file.notes, self.evidence)
        start = self.start()
        timescales = None
        if block.timescales is not None:
            timescales = tuple(self.expression(x, None) for x in block.timescales)
        outputs = tuple(self.output(output, None) for output in file.outputs)
        checks = tuple(self.check(check, None) for check in file.checks)
        self.stop()
        title = block.title.value if block.title else None
        if block.variant is not None:
            # The title of a variant's model: its package's title, then its own.
            title = f'{title}: {block.variant.value}' if title else block.variant.value
        scenario = Scenario(
            groups=groups,
            runs=runs,
            entities=entities,
            menu_where=file.profiles[0].place if file.profiles else (),
            templates=tuple(self.templates),
            title=freeze(title),
            summary=freeze(block.summary.value if block.summary else None),
            records=self.evidence.records(),
            sites=(),
            citations=(),
            horizon=Time(
                freeze(self.written(block.horizon.tokens)) if block.horizon else None,
                (*block.place, 'horizon:'),
            ),
            timescales=timescales,
            resolution=(
                Time(freeze(self.written(block.resolution.tokens)), (*block.place, 'resolution:'))
                if block.resolution is not None
                else None
            ),
            scope=freeze(block.scope.value if block.scope is not None else None),
            scope_where=(*block.place, 'scope:'),
            outputs=outputs,
            checks=checks,
            notes=notes,
            start=start,
        )
        sites = self.evidence.semantic_sites()
        citations = self.evidence.citations()
        return dataclasses.replace(scenario, sites=sites, citations=citations)

    # ---- profiles ---------------------------------------------------------------------------------

    def profile_settings(self):
        """{(entity, value): [Setting, in the order of the profiles]}, and each entity's settings in
        order: for each profile, its lines for the entity's template, then its lines for the entity;
        a line for the entity replaces the template's line for the same value."""
        per_value, per_entity = {}, {}
        for group in self.file.profiles:
            for profile in group.profiles:
                found = {}
                for line in profile.settings:
                    head, _, member = line.target.rpartition('.')
                    if not head:
                        self.fail(line.place, 'a line of a profile names entity.value or Template.value')
                        continue
                    if head in self.templates:
                        targets = [(name, 0) for name in self.instances.get(head, ())]
                        if not targets and member not in self.members(head):
                            self.fail(line.place, f'{member} is not a value of {head}')
                    elif head in self.copy_sets:
                        targets = [(name, 1) for name in self.copy_sets[head]]
                    elif head in self.bodies:
                        targets = [(head, 1)]
                    else:
                        self.fail(line.place, f'{head} is not an entity or a template')
                        continue
                    for entity, level in targets:
                        body = self.bodies[entity]
                        if member not in body.values:
                            self.fail(line.place, f'{member} is not a value of {entity}')
                            continue
                        found.setdefault(entity, []).append((level, member, line))
                for entity, items in found.items():
                    ordered = {}
                    for level in (0, 1):
                        for item_level, member, line in items:
                            if item_level == level:
                                ordered[member] = line
                    for member, line in ordered.items():
                        setting = self.setting(profile.name, entity, member, line)
                        per_value.setdefault((entity, member), []).append(setting)
                        per_entity.setdefault(entity, []).append(setting)
        return per_value, per_entity

    def setting(self, profile, e, member, line):
        info = self.value_info(self.bodies[e], member)
        if info['kind'] in ('fixed', 'formula', 'output'):
            # What a profile can set (docs/language.md, §2.9).
            self.fail(
                line.place,
                f'{member} is a {info["kind"]}: a profile sets an input, a text, or the start value of a '
                'state, a stock or a tally',
            )
        if info['kind'] == 'text':
            self.text_form(line.value, line.place)
        value = self.literal(line.value)
        named = info['type'] if isinstance(info['type'], list) else None
        if (
            named is not None
            and info['kind'] in ('input', 'fixed', 'state')
            and isinstance(value, str)
            and value not in named
            and family_of(value) is None
        ):
            what = (
                'a named input takes one of its values'
                if info['kind'] == 'input'
                else 'a named state starts in one of its states'
            )
            self.fail(line.place, f'{what} {named}, not {value!r}')
        basis = self.evidence.resolved(line.support)
        self.evidence.note(line.place, line.support)
        written = {'value': value, 'basis': thaw(basis)} if basis is not None else value
        start = None
        if info['field'] == 'quantity':
            start = self.expression(line.value, e, line.place)
        return Setting(
            profile,
            freeze(written),
            line.place,
            target=member,
            value=freeze(value),
            records=basis,
            start=start,
            value_at=line.place,
            places=(line.place,),
        )

    # ---- entities ---------------------------------------------------------------------------------

    def title(self, body):
        decl = body.decl
        if decl.title is not None:
            return decl.title.value
        if decl.table is not None and self.table_reads.get(decl.name, {}).get('title'):
            # The title that the row of the instance gives; an empty cell gives none.
            at = [column.name for column in decl.table.columns].index('title')
            if decl.table.rows[body.copy - 1].cells[at]:
                return decl.table.rows[body.copy - 1].cells[at]
        if body.copy is not None:
            return f'{in_words(body.entry)} {body.copy}'
        return in_words(body.name)

    def place_of(self, name):
        """The number of an entity in the order of the model, from 0: found once for all of them."""
        if getattr(self, 'places', None) is None or len(self.places) != len(self.bodies):
            self.places = {entity: k for k, entity in enumerate(self.bodies)}
        return self.places[name]

    def entity(self, name):
        body = self.bodies[name]
        decl = body.decl
        template = body.template
        text = (
            decl.text.value
            if decl.text is not None
            else (template.text.value if template and template.text else None)
        )
        role = template.role if template is not None else decl.role
        # The records of the template, at its own line, and the instance's own: a template's records
        # are cited, whether or not an instance gives its own.
        if template is not None:
            self.evidence.note(template.place, template.support)
        self.evidence.note(decl.place, decl.support)
        values = tuple(self.value(body, member) for member in body.values)
        settings = tuple(self.settings[1].get(name, ()))
        status = self.status(body) if body.status is not None else None
        checks = tuple(self.check(check, name) for check in body.checks)
        flows = tuple(self.flow(body, item) for item in body.sequence if isinstance(item, FlowNode))
        allocations = tuple(
            self.allocation(body, item) for item in body.sequence if isinstance(item, AllocateNode)
        )
        index = self.place_of(name)
        events = tuple(
            self.event(
                body, item, (-1,) if item.name == 'start' else (self.line_of(item), index, body.copy or 0)
            )
            for item in body.sequence
            if isinstance(item, EventNode)
        )
        sees = None
        observed = template.sees if template is not None else decl.sees
        if observed is not None:
            sees = tuple(self.fact(symbol, name, where) for symbol, where in observed)
            self.sight(body, events, sees)
        else:
            for event in events:
                if event.choice:
                    self.fail(
                        (*event.where, 'choice:'),
                        f'only an actor makes a choice: {name} has no sees',
                    )
        return Entity(
            name=name,
            entry=body.entry,
            copy=body.copy,
            template=template.name if template is not None else None,
            values=values,
            where=decl.place,
            title=self.title(body),
            text=freeze(text),
            role=freeze(role),
            records=self.evidence.resolved(body.support),
            status=status,
            checks=checks,
            settings=settings,
            flows=flows,
            allocations=allocations,
            events=events,
            places=(decl.place, *((template.place,) if template is not None else ())),
            sees=sees,
            links=freeze(
                {
                    name: list(target) if isinstance(target, list) else target
                    for name, target in body.links.items()
                }
            ),
        )

    def sight(self, body, events, sees):
        """An actor's choices (its events marked `choice`) read, in their `when`, `after`, `each`,
        `while`, chances and the conditions of their outcomes, only what it knows: the facts of `sees`,
        `t`, `copy` and its own inputs (docs/language.md, §2.7). Any other name there is an error
        (`sight`). Its other events are mechanisms: chance takes their outcomes, and they may read
        anything."""
        e = body.name
        fields = {(ref.entity, ref.member) for ref in sees if isinstance(ref, Ref)}
        seen = {ref.key for ref in sees if isinstance(ref, EventRef)}
        for event in events:
            if not event.choice:
                continue
            parts = [event.when, event.after, *event.each, event.keep]
            parts += [outcome.chance for outcome in event.outcomes if outcome.chance not in (None, 'else')]
            parts += [outcome.available for outcome in event.outcomes if outcome.available is not None]
            unseen = []
            for expression in parts:
                read = getattr(expression, 'node', None)
                for node in resolved.breadth_first(read) if read is not None else ():
                    if isinstance(node, resolved.Ref) and node.entity is not None:
                        if (node.entity, node.member) in fields:
                            continue
                        if (
                            node.entity == e
                            and node.member in body.values
                            and self.value_info(body, node.member)['kind'] in ('input', 'text', 'fixed')
                        ):
                            continue
                        unseen.append(f'{node.entity}.{node.member}')
                    elif isinstance(node, resolved.EventRef):
                        if node.key not in seen:
                            unseen.append(node.key)
            for name in dict.fromkeys(unseen):
                self.errors.append(
                    diagnostic(
                        'sight',
                        '/'.join(map(str, event.where)),
                        f'the choice {event.name} of {e} reads {name}, which {e} does not see: add it to '
                        f'sees, read what {e} sees, or make the event a mechanism (no choice line)',
                    )
                )

    def fact(self, symbol, e, place):
        """What a name of `sees` names: an event or an outcome, or a value."""
        found = self.event_ref(symbol, e, place)
        if not isinstance(found, Problem):
            return found
        ref = self.ref(symbol, e, place)
        if isinstance(ref, Problem):
            self.fail(place, f'{symbol} is not a field or an event that the thing can see')
        return ref

    def value(self, body, name):
        e = body.name
        info = self.value_info(body, name)
        member, change = info['member'], info['change']
        lines = change.lines if change is not None else None
        place = (member or lines).place
        kind = info['kind']
        field = info['field']

        def part(attribute):
            """A line under the value: the change's, else the member's. A change that gives a new kind
            keeps none of the member's lines, which belong to its old kind (gap 15)."""
            if lines is not None and getattr(lines, attribute, None) is not None:
                return getattr(lines, attribute)
            if change is not None and change.kind is not None:
                return None
            if member is not None and not isinstance(member, OutputNode):
                return getattr(member, attribute)
            return None

        # Its records: a new value has its own; a member that the change does not give keeps its own.
        if isinstance(member, OutputNode):
            # A change with no records of its own, such as a new label, rests on the template's line.
            if lines is not None and lines.support:
                support, support_place = lines.support, lines.place
            else:
                support, support_place = member.lines.support, member.place
        elif lines is not None and (lines.value is not None or lines.support):
            # A value of a table cites its records in the header of its column (`row`).
            support, support_place = lines.support, getattr(lines, 'cited_at', lines.place)
            if lines.value is not None and not lines.support and field in ('parameter', 'quantity'):
                self.fail(
                    support_place,
                    f"{name} = …: a new value needs a record of its own; the template's record supports its "
                    'own value only'
                    if support_place == lines.place
                    else f'the column {name} gives new values, which need records of their own: '
                    f'{name}: unit @record',
                )
        else:
            support, support_place = (member.support if member is not None else []), place
        self.evidence.note(support_place, support)
        basis = self.evidence.resolved(support)
        value_place = lines.place if lines is not None and lines.value is not None else place
        written_type = self.type_of(info, value_place)
        if basis is None and kind == 'state' and written_type == 'bool':
            # A yes/no state needs no record of its own: its entity's records support it, as they
            # support a status. The engine keeps it as a 0/1 number, which has a basis.
            basis = self.evidence.resolved(body.support)
        if kind == 'text':
            self.text_form(info['value'], value_place)
        value = self.literal(info['value']) if kind not in ('formula', 'output') else None
        text = info['text']
        parts = {}
        minimum, maximum, bounds = part('min'), part('max'), part('bounds')
        if field == 'quantity':
            if info['value'] is not None:
                parts['initial'] = self.initial(info['value'], e, value_place)
            for attribute, key in (('min', 'minimum'), ('max', 'maximum'), ('size', 'size')):
                found = part(attribute)
                if found is not None:
                    parts[key] = Bound(self.expression(found.expr, e), (*found.place, 'unit'))
        elif part('size') is not None:
            self.fail(place, f'{name}: size belongs to a var')
        if info['formula'] is not None:
            parts['formula'] = self.expression(info['formula'], e)
        found_range = None
        if field == 'parameter':
            self.parameter_form(
                name, kind, written_type, info['value'], value_place, minimum, maximum, bounds
            )
            found_range = self.range(minimum, maximum, bounds, place)
        elif minimum is not None and field not in ('quantity',):
            self.fail(minimum.place, f'{name}: min: and max: belong to a number')
        label = value_label(text, self.title(body), self.shared(body, name, text))
        output = None
        if kind == 'output':
            output = self.output(member, e, label=label, change=lines)
        elif part('output') is not None:
            # The template's lines of the output, which a change of kind does not keep, and the change's.
            own = member.output if member is not None and (change is None or change.kind is None) else None
            given = lines.output if lines is not None else None
            output = self.value_output(
                body, name, info, self.merged_output(own, given), label, basis, place, written_type
            )
        settings = tuple(self.settings[0].get((e, name), ()))
        value_kind = {'output': 'output'}.get(kind, kind)
        edges = tuple(item.place for item in (minimum, maximum) if item is not None)
        return Value(
            name=name,
            kind=value_kind,
            type=freeze(written_type),
            text=freeze(text),
            value=freeze(value),
            range=found_range,
            records=basis,
            settings=settings,
            where=place,
            value_where=value_place,
            range_where=minimum.place if minimum is not None else place,
            type_where=value_place,
            label=label,
            output=output,
            value_at=value_place,
            range_at=minimum.place if minimum is not None else place,
            edges_at=edges or (place, place),
            unit_where=value_place,
            records_at=support_place,
            **parts,
        )

    def shared(self, body, name, text):
        """Whether another entity of the template shows the same text for the value."""
        if body.template is None or text is None:
            return False
        if self.only is not None and body.decl.table is not None and len(body.decl.table.rows or ()) > 1:
            # In a model of representatives, the other rows of the table are not there: each shows the
            # text of the template, because a row gives no text.
            return True
        for other in self.instances.get(body.template.name, ()):
            other_body = self.bodies[other]
            if (
                other != body.name
                and name in other_body.values
                and self.value_info(other_body, name)['text'] == text
            ):
                return True
        return False

    def type_of(self, info, place):
        """The type of a value as the semantic model holds it: as written, or else what its value shows.
        A number's unit shows its type, and a unit of time gives the type `duration`; `true` and
        `false` show `bool`."""
        written = info['type']
        kind = info['kind']
        if kind == 'text':
            return 'text'
        if isinstance(written, list):
            return tuple(written)
        if written is not None:
            self.used_units.add(written)
            return written
        expr = info['value']
        tokens = expr.tokens if expr is not None else []
        if len(tokens) == 1 and tokens[0].is_name('true', 'false'):
            return 'bool'
        unit = next((token.value for token in tokens if token.kind == 'unit'), None)
        plain = tokens[1:] if tokens and tokens[0].is_op('-') else tokens
        if unit is not None and (len(plain) == 2 or family_of(text_of(tokens)) is not None):
            self.used_units.add(unit)
            return 'duration' if unit in self.time_units else unit
        if kind in ('input', 'fixed', 'state', 'stock', 'tally', 'formula', 'output'):
            self.fail(place, 'write the type of the value: kind name: type = value')
        return None

    def initial(self, expr, e, place):
        """The start value of a state, stock or tally: an expression, which a bool is not."""
        written = self.written(expr.tokens)
        if isinstance(written, bool):
            problem = resolved.problem('an expression is text or a number')
            return Expression(freeze(written), problem, place)
        return self.expression(expr, e, place)

    def parameter_form(self, name, kind, written_type, value, place, minimum, maximum, bounds):
        """An input or a fixed value as the language writes it (docs/language.md, §2.4 and §2.5): a
        yes/no value is `true` or `false`; only a number input has bounds."""
        written = text_of(value.tokens) if value is not None else None
        # A distribution of a yes/no input draws true or false (`bernoulli(p)`).
        if (
            written_type == 'bool'
            and value is not None
            and not isinstance(self.written(value.tokens), bool)
            and family_of(written) is None
        ):
            self.fail(place, f'{name}: a yes/no value is true or false, not {written}')
        first = next((item for item in (minimum, maximum, bounds) if item is not None), None)
        if first is None:
            return
        if kind == 'fixed':
            self.fail(first.place, f'{name}: a fixed value has no bounds: no min:, max: or bounds:')
        elif written_type == 'bool':
            self.fail(first.place, f'{name}: a yes/no input has no bounds: it is true or false')
        elif isinstance(written_type, tuple):
            self.fail(first.place, f'{name}: a named input has no bounds: it is one of its names')

    def range(self, minimum, maximum, bounds, place):
        """The range of an input or a fixed value: its edges and its support, the range note of
        `bounds:` and its records."""
        if minimum is None and maximum is None and bounds is None:
            return None
        edges = tuple(
            None if item is None else (freeze(self.written(item.expr.tokens)), item.place)
            for item in (minimum, maximum)
        )
        basis = None
        texts = [item for item in (minimum, maximum) if item is not None and item.text is not None]
        if bounds is not None:
            note = {'status': 'declared' if bounds.kind == 'sourced' else 'chosen'}
            for key, item in (('min', minimum), ('max', maximum)):
                if item is not None and item.text is not None:
                    note[key] = item.text.value
            if bounds.text is not None:
                note['rationale'] = bounds.text.value
            self.evidence.note(bounds.place, bounds.support)
            found = self.evidence.resolved(bounds.support)
            items = [
                note,
                *([] if found is None else thaw(found) if isinstance(thaw(found), list) else [thaw(found)]),
            ]
            basis = freeze(items[0] if len(items) == 1 else items)
        elif texts:
            self.fail(texts[0].place, 'the texts of min: and max: go with bounds:, which says who set them')
        return Range(edges, basis, minimum.place if minimum is not None else place)

    # ---- outputs ----------------------------------------------------------------------------------

    def output_fields(self, lines, e, place):
        """The parts of an output that its lines give."""
        scope = lines.scope.value if lines.scope is not None else None
        lag = None
        if lines.lag is not None:
            lag = Lag(
                lines.lag.kind,
                tuple(self.expression(delay, e) for delay in lines.lag.delays),
                tuple(freeze(records.number(share)) for share in lines.lag.shares),
                lines.lag.place,
            )
        distinct = None
        if lines.distinct is not None:
            self.evidence.note(lines.distinct.place, lines.distinct.support)
            distinct = Site(
                lines.distinct.place, lines.distinct.place, self.evidence.resolved(lines.distinct.support)
            )
        return dict(
            measure=freeze(MEASURES.get(lines.measure, lines.measure) if lines.measure else 'cumulative'),
            reports=freeze(lines.category),
            about=freeze(lines.about.value if lines.about else None),
            scope=freeze(scope),
            signed=lines.signed,
            not_estimated=freeze(lines.unestimated.value if lines.unestimated else None),
            lag=lag,
            distinct=distinct,
        )

    def output(self, node, e, label=None, change=None):
        """`output name: unit = E`, at the top level (`e` None) or in an entity. An instance's change
        (`change`) can give a new text, new records, and the lines of the output under `output x`;
        the lines that it does not give stay the template's."""
        lines = node.lines
        support, support_place = lines.support, node.place
        if change is not None:
            if change.value is not None:
                self.fail(change.place, 'an instance changes the lines of an output, not its expression')
            if change.support:
                support, support_place = change.support, change.place
            lines = self.merged_output(lines, change.output)
        self.evidence.note(support_place, support)
        text = lines.text.value if lines.text is not None else None
        if change is not None and change.text is not None:
            text = change.text.value
        formula = self.expression(node.expr, e) if node.expr is not None else None
        if node.expr is not None and lines.unestimated is not None:
            self.fail(
                node.place, 'an output has an estimate or a reason for none: = E, or unestimated:, not both'
            )
        if node.type is not None:
            self.used_units.add(node.type)
        return Output(
            name=node.name,
            entity=e,
            text=freeze(text),
            label=label if e is not None else text,
            type=freeze(node.type),
            unit_where=node.place,
            records=self.evidence.resolved(support),
            formula=formula,
            formula_where=node.place,
            where=node.place,
            places=(node.place,),
            **self.output_fields(lines, e, node.place),
        )

    def output_text(self, lines):
        """The lines under `output x` have no text: the text of the field, or of the change, is the label
        of the output."""
        if lines.text is not None:
            self.fail(
                lines.text.place,
                'the label of the output is the text of its field: write it under the field, not under '
                'output x',
            )

    def merged_output(self, lines, given):
        """The lines of an output that an instance's change gives under `output x` (`given`), with
        the template's lines (`lines`) that it does not give. Its records go on the change's line."""
        if given is None:
            return lines
        self.output_text(given)
        if given.support:
            self.fail(given.place, 'the records of a change go on its line, not under output x')
        if lines is None:
            # Its text and records are reported here, once.
            return dataclasses.replace(given, text=None, support=[])
        return dataclasses.replace(
            lines, **{key: getattr(given, key) for key in given.keys}, keys={**lines.keys, **given.keys}
        )

    def value_output(self, body, name, info, lines, label, basis, place, written_type):
        """The output of a number var with `output x`: the field's text is its label, and the field's
        records support it."""
        self.output_text(lines)
        if lines.support:
            self.fail(lines.place, "the output of a field rests on the field's records")
        if info['kind'] not in ('stock', 'tally', 'state') or isinstance(info['type'], list):
            self.fail(lines.place, 'output x names a number var')
        return Output(
            name=name,
            entity=body.name,
            text=freeze(info['text']),
            label=label,
            type=freeze(written_type),
            unit_where=place,
            records=basis,
            formula=None,
            formula_where=lines.place,
            where=lines.place,
            places=(lines.place,),
            **self.output_fields(lines, body.name, lines.place),
        )

    # ---- statuses and checks ------------------------------------------------------------------------

    def status(self, body):
        node = body.status
        e = body.name
        self.evidence.note(node.place, node.support)
        cases = []
        last = len(node.lines) - 1
        for i, line in enumerate(node.lines):
            if i < last and line.condition is None:
                self.fail(line.place, 'each status line but the last has a condition: status failed when C')
            if i == last and line.condition is not None:
                self.fail(line.place, 'the last status line has no condition: status ok')
            condition = (
                self.expression(line.condition, e) if line.condition is not None and i < last else None
            )
            text = line.text.value if line.text is not None else None
            cases.append(
                Case(
                    condition,
                    line.status,
                    self.words(e, text, line.text.place, status=True)
                    if text is not None
                    else Words(None, 'a status line has its text under it', line.place),
                    None,
                    line.place,
                )
            )
        if not cases:
            self.fail(node.place, 'a thing with a status has its status lines')
        return Status(tuple(cases), node.place, self.evidence.resolved(node.support))

    def check(self, node, e):
        self.evidence.note(node.place, node.support)
        message = node.text.value if node.text is not None else None
        basis = self.evidence.resolved(node.support)
        if node.kind == 'conserve':
            if len(node.terms) < 2:
                self.fail(
                    node.place, 'an assert of a sum adds two or more number vars: assert a + b is T within d'
                )
            terms = []
            for name, place in node.terms:
                head, _, member = name.rpartition('.')
                try:
                    found = self.entity_of(head.split('.'), e, place, last=True) if head else None
                except LookupError:
                    found = None
                if isinstance(found, list):
                    # A list adds the var of each member; an empty list still checks the name.
                    wrong = None if found else self.no_member(head.split('.'), e, member)
                    if wrong is not None:
                        self.fail(place or node.place, wrong)
                    terms += [(f'{owner}.{member}', place) for owner in found]
                else:
                    terms.append((name, place))
            parts = tuple(self.ref(name, e, place) for name, place in terms)
            for (name, place), part in zip(terms, parts):
                body = self.bodies.get(part.entity) if isinstance(part, Ref) else None
                if body is not None and part.member in body.values:
                    info = self.value_info(body, part.member)
                    if info['kind'] not in ('stock', 'tally', 'state') or isinstance(info['type'], list):
                        self.fail(place or node.place, f'{name} is not a number var: the sum adds them')
            within = None if node.within is None else self.expression(node.within.expr, e)
            return Check(
                'sum',
                e,
                parts,
                self.expression(node.total, e),
                within,
                None,
                None,
                freeze(message),
                basis,
                node.place,
                node.place,
            )
        condition = self.expression(node.expr, e)
        kind = 'check' if self.of_inputs(condition.node) else 'always'
        return Check(
            kind,
            e,
            (),
            None,
            None,
            condition,
            'block' if kind == 'check' else None,
            freeze(message),
            basis,
            node.place,
            node.place,
        )

    def of_inputs(self, read, seen=frozenset()):
        """Whether an expression (its typed nodes) reads only inputs, fixed values, named states and
        formulas of them: no time, no event and no number var. Such an `assert` checks a run before it
        starts, with each named state at its start value."""
        for node in resolved.breadth_first(read):
            if isinstance(node, (resolved.EventRef, resolved.Problem)):
                return False
            if isinstance(node, typed.Ref) and node.name == 't':
                return False
            if isinstance(node, resolved.Ref) and node.entity is not None:
                body = self.bodies.get(node.entity)
                if body is None or node.member not in body.values:
                    return False
                info = self.value_info(body, node.member)
                if info['field'] == 'quantity':
                    return False
                if info['field'] in ('computed', 'inline') and info['formula'] is not None:
                    key = (node.entity, node.member)
                    if key in seen:
                        return False
                    # The answer for a formula does not depend on the way to it: a formula on a circle
                    # of formulas reads no inputs only, from whichever formula the walk comes. So each
                    # formula is read once, and not once for each way to it.
                    if key not in self.inputs_only:
                        formula = self.expression(info['formula'], node.entity)
                        self.inputs_only[key] = not isinstance(
                            formula.node, resolved.Problem
                        ) and self.of_inputs(formula.node, seen | {key})
                    if not self.inputs_only[key]:
                        return False
        return True

    # ---- flows and allocations ---------------------------------------------------------------------

    def flow(self, body, node):
        e = body.name
        self.evidence.note(node.place, node.support)
        changes = [change for change in self.instance_changes(body, node.name)]
        # An instance's records for the flow, or for its `together:`, are cited at the instance's line.
        together_support, together_at = node.together_support, node.together_place
        for change in changes:
            if change.together is not None:
                together_support, together_at = change.together, (*change.place, 'together:')
            if change.lines.support:
                self.evidence.note(change.lines.place, change.lines.support)
        if node.together is not None and not together_support:
            together_support = node.support
            if not together_support:
                self.fail(
                    node.place,
                    'a flow of several pairs cites its records on its line: why the pairs move together',
                )
        pairs = []
        written = (
            node.together if node.together is not None else ([node.pair] if node.pair is not None else [])
        )
        if node.pair is not None and node.together is not None:
            self.fail(node.place, 'a flow has one pair, or its pairs under together:, not both')
        if not written:
            self.fail(
                node.place,
                'a flow moves material between a pair: flow name: A -> B, or the pairs of together:',
            )
        for pair in written:
            ends = tuple(
                (end, self.flow_end(ref, e))
                for end, ref in (('from', pair.source), ('to', pair.target))
                if ref != 'outside'
            )
            if pair.source == 'outside' and pair.target == 'outside':
                self.fail(pair.place, 'a pair has at most one end outside the model')
            # A pair with records or a rate of its own is a part of its own: under `together:`, or the
            # pair of one, on a line of its own. The pair on the flow's line has neither.
            own = bool(pair.support) or pair.rate is not None
            self.evidence.note(pair.place, pair.support)
            rate = self.expression(pair.rate.expr, e) if pair.rate is not None else None
            pairs.append(
                Pair(
                    ends,
                    rate,
                    self.evidence.resolved(pair.support) if own and pair.support else None,
                    own,
                    pair.place,
                )
            )
        if node.rate is None:
            self.fail(node.place, 'a flow has its rate: rate: E')
        together = None
        if node.together is not None:
            self.evidence.note(together_at, together_support)
            together = Site(
                node.together_place, node.together_place, self.evidence.resolved(together_support)
            )
        text = node.text.value if node.text is not None else None
        support = node.support
        for change in changes:
            if change.lines.text is not None:
                text = change.lines.text.value
            if change.lines.support:
                support = change.lines.support
        return Flow(
            node.name,
            tuple(pairs),
            self.expression(node.rate.expr, e)
            if node.rate is not None
            else Expression(None, resolved.problem('a flow has its rate'), node.place),
            self.expression(node.keep.expr, e) if node.keep is not None else None,
            freeze(text),
            self.evidence.resolved(support),
            together,
            node.place,
        )

    def instance_changes(self, body, name):
        decl = body.decl
        if body.template is None:
            return []
        return [m for m in decl.members if isinstance(m, ChangeNode) and m.name == name]

    def flow_end(self, ref, e):
        try:
            owner, member = self.member_of(ref, e, ())
        except LookupError as exc:
            return Problem(message=str(exc))
        return Ref(entity=owner, member=member, written=ref)

    def allocation(self, body, node):
        e = body.name
        self.evidence.note(node.place, node.support)
        try:
            owner, member = self.member_of(node.stock, e, node.place)
        except LookupError as exc:
            stock = Problem(message=str(exc))
        else:
            stock = Ref(entity=owner, member=member, written=node.stock)
        serve = None
        if node.serve is not None:
            serve = []
            for flow_ref, where in node.serve:
                head, _, name = flow_ref.rpartition('.')
                try:
                    flow_owner = self.entity_of(head.split('.'), e, where, last=True) if head else e
                    wrong = self.no_member(head.split('.'), e, name, 'a flow') if flow_owner == [] else None
                    if wrong is not None:
                        raise LookupError(wrong)
                except LookupError as exc:
                    flow_owner = Problem(message=str(exc))
                if isinstance(flow_owner, list):
                    # A list serves the flow of each member, in the order of the list.
                    serve += [(f'{owner}.{name}', owner, name, where) for owner in flow_owner]
                else:
                    serve.append((flow_ref, flow_owner, name, where))
            serve = tuple(serve)
        if node.limit is None:
            self.fail(node.place, 'an allocation has its limit: limit: E')
        return Allocation(
            node.name,
            stock,
            self.expression(node.limit.expr, e) if node.limit is not None else None,
            serve,
            self.evidence.resolved(node.support),
            node.place,
            node.stock_place or node.place,
            node.serve_place or node.place,
        )

    # ---- events --------------------------------------------------------------------------------------

    def event(self, body, node, rank):
        e = body.name
        # An instance's line `event:  @records` gives the event new records; a new text replaces its own.
        support, support_at = node.support, node.place
        written = node.text
        for change in self.instance_changes(body, node.name):
            if change.lines.support:
                support, support_at = change.lines.support, change.lines.place
            if change.lines.text is not None:
                written = change.lines.text
        self.evidence.note(support_at, support)
        text = written.value if written is not None else None
        doc_problem = None
        texts = [
            (value, written.place)
            for value in (text if isinstance(text, list) else [text])
            if isinstance(value, str)
        ]
        texts += [
            (outcome.text.value, outcome.text.place) for outcome in node.outcomes if outcome.text is not None
        ]
        for words, where in texts:
            try:
                self.fill(e, words, where)
            except ValueError as exc:
                doc_problem = Fault(str(exc), where)
                break
        names = [outcome.name for outcome in node.outcomes]
        twice = sorted({name for i, name in enumerate(names) if name in names[:i]})
        if twice:
            self.fail(node.place, f'an event names each outcome once, not {", ".join(twice)} twice')
        if sum(outcome.is_else for outcome in node.outcomes) > 1:
            self.fail(node.place, 'one outcome at most has the chance else')
        if len(node.outcomes) < 2 and any(outcome.when is not None for outcome in node.outcomes):
            self.fail(node.place, 'only an event with two outcomes or more says when an outcome can happen')
        if node.each and node.once:
            self.fail(node.place, 'an event that fires once has no window: once, or each W')
        if node.keep is not None and node.after is None:
            self.fail(node.place, 'while K cancels a firing that waits: the event has after D')
        if node.choice and len(node.outcomes) < 2:
            self.fail(node.place, 'a choice has two outcomes or more to choose from')
        if node.name == 'start':
            if body.template is not None or body.copy is not None:
                self.fail(node.place, 'the start is an event of one thing, not of a template')
            if node.after is not None or len(node.outcomes) > 1:
                self.fail(node.place, 'the start fires at once, with one outcome')
        outcomes = tuple(self.outcome(body, outcome) for outcome in node.outcomes)
        return Event(
            name=node.name,
            entity=e,
            when=self.expression(node.when, e) if node.when is not None else None,
            once=bool(node.once),
            after=self.expression(node.after, e) if node.after is not None else None,
            outcomes=outcomes,
            text=freeze(text),
            label=self.words(e, first_text(text), node.text.place)
            if isinstance(first_text(text), str)
            else None,
            role=freeze(node.role),
            records=self.evidence.resolved(support),
            doc_problem=doc_problem,
            rank=rank,
            where=node.place,
            when_where=node.when.place if node.when is not None else node.place,
            each=tuple(self.expression(item, e) for item in node.each),
            keep=self.expression(node.keep, e) if node.keep is not None else None,
            choice=node.choice,
        )

    def outcome(self, body, node):
        e = body.name
        self.evidence.note(node.place, node.support)
        if node.is_else:
            chance = 'else'
        elif node.chance is not None:
            chance = self.expression(node.chance, e)
        else:
            chance = None
        text = node.text.value if node.text is not None else None
        label = (
            self.words(e, first_text(text), node.text.place) if isinstance(first_text(text), str) else None
        )
        return Outcome(
            name=node.name,
            chance=chance,
            text=freeze(text),
            role=freeze(node.role),
            records=self.evidence.resolved(node.support),
            lines=tuple(self.line(line, e) for line in node.lines),
            label=label,
            where=node.place,
            available=self.expression(node.when, e) if node.when is not None else None,
        )

    def line(self, line, e):
        """One line of an outcome, read in entity `e`."""
        if isinstance(line, AssignLine):
            target = self.ref(line.target, e, line.place)
            try:
                value, names = expressions.tree(line.value.tokens)
            except SyntaxProblem as exc:
                value = Problem(message=exc.message)
            else:
                value = self.resolve_tree(value, names, e, line.place)
            augmented = line.op != '='
            operator = None
            if augmented:
                operator = 'Add' if line.op == '+=' else 'Sub'
                op = ast.Add() if line.op == '+=' else ast.Sub()
                value = ast.BinOp(left=self.ref(line.target, e, line.place), op=op, right=value)
            for token in line.value.tokens:
                if token.kind == 'unit':
                    self.used_units.add(token.value)
            return Assign(target, line.target, resolved.of_tree(value), augmented, operator, line.place)
        if isinstance(line, MoveLine):
            try:
                amount, names = expressions.tree(line.amount.tokens)
            except SyntaxProblem as exc:
                amount = Problem(message=exc.message)
            else:
                amount = self.resolve_tree(amount, names, e, line.place)
            ends = tuple(
                (ref, 'outside' if ref == 'outside' else self.flow_end(ref, e))
                for ref in (line.source, line.target)
            )
            return Move(resolved.of_tree(amount), ends, line.place)
        if isinstance(line, FireLine):
            parts = line.target.split('.')
            try:
                if len(parts) == 1:
                    owners, name = [e], parts[0]
                elif '.'.join(parts[:-1]) in self.copy_sets:
                    owners, name = list(self.copy_sets['.'.join(parts[:-1])]), parts[-1]
                else:
                    found = self.entity_of(parts[:-1], e, line.place, last=True)
                    owners, name = (found if isinstance(found, list) else [found]), parts[-1]
                for owner in owners:
                    if self.event_of(owner, name) is None:
                        raise LookupError(f'{name} is not an event of {owner}')
                wrong = None if owners else self.no_member(parts[:-1], e, name, 'an event')
                if wrong is not None:
                    raise LookupError(wrong)
                targets = tuple((owner, name) for owner in owners)
            except LookupError as exc:
                targets = Problem(message=str(exc))
            return Fire(targets, line.target, line.place)
        raise TypeError(line)

    # ---- the start --------------------------------------------------------------------------------

    def start(self):
        """The event `start` of one thing: it fires first, at t = 0."""
        found = [
            (e, node)
            for e, body in self.bodies.items()
            for node in body.sequence
            if isinstance(node, EventNode) and node.name == 'start'
        ]
        if not found:
            return None
        if len(found) > 1:
            self.fail(found[1][1].place, 'a model has one start: the event start of one thing')
        e, node = found[0]
        text = node.text.value if node.text is not None else None
        return Start(
            entity=e,
            text=freeze(text),
            label=self.words(e, first_text(text), node.text.place)
            if isinstance(first_text(text), str)
            else None,
            records=self.evidence.resolved(node.support),
            where=node.place,
        )


def written_of(tokens):
    """An expression as the file writes it: a number, `true` or `false`, a text, or its text."""
    if len(tokens) == 1 and tokens[0].kind == 'number':
        return records.number(tokens[0].value)
    if len(tokens) == 2 and tokens[0].is_op('-') and tokens[1].kind == 'number':
        return -records.number(tokens[1].value)
    if len(tokens) == 1 and tokens[0].is_name('true', 'false'):
        return tokens[0].value == 'true'
    if len(tokens) == 1 and tokens[0].kind == 'text':
        return tokens[0].value
    return text_of(tokens)


def cell_tokens(text, unit, textual, line):
    """The tokens of the value that a cell of a table gives (docs/language.md, §2.3): one text for a
    named state or a text value (`textual`); else a number, with the unit of its column, or `true` or
    `false`. Raises SyntaxProblem for a cell that gives no value: a formula is no cell."""
    if textual:
        return [Token('text', text, line, 1, False, f'"{text}"')]
    # No line of the language starts with a sign, so a cell with one is read without it, and the sign
    # comes before what it gives: `-1.5` is the negation of 1.5, as in a formula.
    bare = text.strip()
    sign = [Token('op', '-', line, 1, False, '-')] if bare.startswith('-') else []
    rest = bare[1:] if sign else text
    try:
        found = lex.lines(f'{rest} {unit}' if unit else rest)
    except SyntaxProblem as exc:
        raise SyntaxProblem(f'the cell {text!r}: {exc.message}', line) from None
    found = [item for item in found if item.kind == 'line']
    tokens = sign + found[0].tokens if len(found) == 1 else []
    kinds = tuple(token.kind for token in tokens)
    number = kinds in NUMBER_CELLS and (kinds[0] != 'op' or tokens[0].is_op('-'))
    if not number and not (len(tokens) == 1 and tokens[0].is_name('true', 'false')):
        raise SyntaxProblem(
            f'the cell {text!r} is not a number, true or false: a cell gives a value, and a formula '
            'goes in the template',
            line,
        )
    for token in tokens:
        token.line = line
    return tokens


def text_of(tokens):
    """The text of an expression's tokens, with the language's spacing on one line."""
    return one_line(tokens)


def resolve(file, library, files=None, only=None):
    """The semantic model of a parsed model file (`nodes.File`), or of the merged file of a model of
    several files with the file of each line (`files`). Raises `Problems`. With `only` (`Kept`), a
    table makes only the instances of the rows that it keeps."""
    resolver = Resolver(file, library, files, only)
    return resolver.scenario(), resolver


# The forms of names.
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]*')


def arguments(scenario, run_table, resolver):
    """The scenario with the arguments of each distribution that read other values, read in the entity
    of their input, in the order of its default and its profiles' values."""
    entities = []
    for entity in scenario.entities:
        values = []
        for value in entity.values:
            item = run_table.data['inputs'].get(f'{entity.name}.{value.name}')
            if item is None:
                values.append(value)
                continue
            places = [(value.value_where, item['value'])] + [
                (
                    setting.where,
                    run_table.data['inputs'][f'{entity.name}.{value.name}']['options'][setting.profile][
                        'value'
                    ],
                )
                for setting in value.settings
                if setting.profile in item['options']
            ]
            found = []
            for where, written in places:
                if is_distribution(written):
                    args = []
                    for name, source in reads(written).items():
                        try:
                            # The source is the argument as the author wrote it.
                            tokens = expressions.tokens_of(source)
                            args.append(
                                (name, resolver.expression(Expr(where, 0, tokens), entity.name, where))
                            )
                        except SyntaxProblem as exc:
                            args.append(
                                (name, Expression(freeze(source), resolved.problem(exc.message), where))
                            )
                    found.append((where, written['text'], tuple(args)))
            values.append(dataclasses.replace(value, arguments=tuple(found)) if found else value)
        entities.append(dataclasses.replace(entity, values=tuple(values)))
    return dataclasses.replace(scenario, entities=tuple(entities))


__all__ = ['Problems', 'Resolver', 'arguments', 'resolve', 'text_of']
