"""The hybrid core: each thing that no table makes by itself, and one family for each class of the
rows of a table that have one shape (docs/compiler.md).

A table makes one instance of a template for each of its rows (docs/language.md, §2.3). The flat
structure writes each of them out. The hybrid core does not: the rows whose lowered parts are equal
but for the values that the cells give, and for the instances that the links name, are one **class**,
and the compiler lowers one of them, its **representative**.

`classes` finds the classes from the parsed file, before any lowering, by the **signature** of each
row: the facts of the row that can change the shape of what the lowering writes.

- Which cells of the row are empty. An empty cell leaves the value of the template, which has other
  records and another place.
- The start state that the row gives a named state, and the yes or no that it gives a yes/no var.
  The lowering reads the start states to find the parts that cannot act.
- Whether the number that the row gives a number var is zero. A stock that starts at zero and that
  nothing fills is left out.
- For a link: the entity that the cell names, when no table makes it; else the class of the instance
  that it names.
- Whether a line of the file names this one instance (`tanks.3.held`, an option that sets one of its
  values, a link that binds it). Such an instance is a class of one.

What is not in the signature is a value: the number of an input or of a constant, a number var's
start that is not zero, a text and a title. `Family.columns` holds those for each row.

Two forms of rows are classes of one for now, because one representative cannot say which link a
reference came through: a row with two links into one class, and a row that links into its own class.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ..core import expr as nodes
from ..expressions import UnitSystem, evaluate
from . import resolved
from .analysis import structure as structure_analysis
from .analysis.values import value_facts
from .compile import check_parameters
from .ir import ModelError, diagnostic, rule_events, thaw
from .language import expressions as grammar
from .language import front
from .language.lex import SyntaxProblem, Token
from .language.nodes import Expr, LinkDecl, Table
from .language.nodes import Value as ValueNode
from .language.resolve import Kept, Resolver, cell_tokens, written_of
from .lower.builder import flat_node
from .lower.expressions import WRITTEN, Context, Typing
from .lower.starts import read_events
from .semantic import flat_entity, in_words, value_label
from .structure import Resolved, Structure
from .types import engine_number, is_number, number_in


@dataclass(frozen=True)
class Class:
    """The rows of one table that have one signature: the thing of the table (`set`), the numbers of
    the rows in their order, from 1, and the signature. The first row is the representative."""

    set: str
    rows: tuple
    signature: tuple

    @property
    def representative(self):
        return self.rows[0]

    def name(self, row):
        """The name of the instance of a row: `set.row`."""
        return f'{self.set}.{row}'


def _strings(value, skip=(Table,)):
    """Each text of a part of a parsed file, as the file writes it: the tokens of an expression joined,
    and each name that a node holds. The tables are left out."""
    if isinstance(value, skip):
        return
    if isinstance(value, Expr):
        yield ''.join(token.source or str(token.value) for token in value.tokens)
    elif isinstance(value, Token):
        yield value.source or str(value.value)
    elif isinstance(value, str):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item, skip)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item, skip)
    elif dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            if field.name not in ('place', 'line'):
                yield from _strings(getattr(value, field.name), skip)


def named_alone(file, sets):
    """{set: the numbers of its instances that a line of the file names one by one}, for the sets of
    `sets`. A name of the set alone (`tanks.held`, a list) names no one instance."""
    found = {name: set() for name in sets}
    if not sets:
        return found
    one = re.compile(
        r'(?<![A-Za-z0-9_.])(' + '|'.join(map(re.escape, sorted(sets))) + r')\.([0-9]+)(?![0-9])'
    )
    parts = [file.scenario, file.things, file.checks, file.outputs, file.profiles, file.runs, file.notes]
    for text in _strings(parts):
        for name, number in one.findall(text):
            found[name].add(int(number))
    return found


def lists_in_templates(file):
    """The templates whose instances a table makes and whose own lines read a list over the rows of a
    table (`sum(Cell.level)` in a line of `Cell`), as (template, the name that the line reads).

    The hybrid core cannot stand for such a model. In a part of a representative, its own name reads
    as the name of each instance of its family, and a member of a list has the same name. So the
    parts of the other instances would have a list over themselves. The flat structure of the file
    has no such limit."""
    templates = {thing.name: thing for thing in file.things if thing.kind == 'template'}
    tabled = [thing for thing in file.things if thing.table is not None and thing.template in templates]
    names = {thing.name for thing in tabled} | {thing.template for thing in tabled}
    if not names:
        return []
    listed = re.compile(
        r'(?<![A-Za-z0-9_.])(' + '|'.join(map(re.escape, sorted(names))) + r')\.(?=[A-Za-z_])'
    )
    found = []
    for name in sorted({thing.template for thing in tabled}):
        for text in _strings(templates.get(name)):
            for read in listed.findall(text):
                if (name, read) not in found:
                    found.append((name, read))
    return found


def kinds_changed(model, listed):
    """The events whose condition has one kind in the model of the representatives and another with
    its lists as they are, as (event, the kind in the model, the kind with the lists). `listed` has
    the typed parts of each structure with its lists as they are (`Hybrid.listed`).

    A list over the rows of one class has one member in the model of the representatives, and a
    condition on one value that moves is a crossing. With the list of every row it is a condition on
    many values that move, which the compiler does not take as a crossing. So the checks of the model
    of the representatives would pass a model that the checks of the whole model refuse."""
    found = []
    for starts, s in listed.items():
        checked = model.structures[starts].rules if starts in model.structures else {}
        discrete = structure_analysis.discrete_names(s)
        moving = structure_analysis.evolving_parts(s) | {'t'}
        for name, rule in s.rules.items():
            if name not in checked:
                continue
            try:
                kind = structure_analysis.classify(rule, s, discrete, moving).kind
            except ValueError:
                kind = 'refused'
            before = checked[name].trigger.kind
            if before is not None and kind != before and (name, before, kind) not in found:
                found.append((name, before, kind))
    return found


def _number_is_zero(cell):
    try:
        return float(cell) == 0
    except ValueError:
        # No number: the resolver refuses the cell, and the row needs no class.
        return None


def classes(file):
    """{the thing of each table of the parsed file: its classes, in the order of their first rows}."""
    templates = {thing.name: thing for thing in file.things if thing.kind == 'template'}
    tabled = {
        thing.name: thing
        for thing in file.things
        if thing.table is not None and thing.table.rows and thing.template in templates
    }
    alone = named_alone(file, tabled)
    base, links = {}, {}  # {(set, row): the signature without the links into tables}, and those links
    for name, thing in tabled.items():
        template = templates[thing.template]
        values = {m.name: m for m in template.members if isinstance(m, ValueNode)}
        slots = {m.name for m in template.members if isinstance(m, LinkDecl) and not m.many}
        for row in thing.table.rows:
            k = row.place[-1]
            facts, into = [], []
            for column, cell in zip(thing.table.columns, row.cells):
                member = values.get(column.name)
                if member is not None:
                    fact = bool(cell)
                    state = isinstance(member.type, list) or (member.kind == 'var' and member.type == 'bool')
                    if cell and state:
                        fact = cell
                    elif cell and member.kind == 'var':
                        fact = ('zero', _number_is_zero(cell))
                    facts.append((column.name, fact))
                elif column.name in slots:
                    head, _, number = cell.rpartition('.')
                    if head in tabled and number.isdigit():
                        into.append((column.name, head, int(number)))
                        facts.append((column.name, 'table', head))
                    else:
                        facts.append((column.name, 'thing', cell))
            if k in alone[name]:
                facts.append(('alone', k))
            base[name, k], links[name, k] = tuple(facts), tuple(into)
    # The class of a row follows the classes of the rows that it links to: refine until none splits.
    ids = _ids(base)
    while True:
        refined = {
            key: (
                base[key],
                tuple((column, ids.get((head, number))) for column, head, number in links[key]),
            )
            for key in base
        }
        again = _ids(refined)
        if len(set(again.values())) == len(set(ids.values())):
            signatures = refined
            ids = again
            break
        ids = again
    # One representative cannot say which link a reference came through: a row with two links into
    # one class, or with a link into its own class, is a class of one.
    for key, into in links.items():
        targets = [ids.get((head, number)) for _, head, number in into]
        if len(set(targets)) < len(targets) or ids[key] in targets:
            signatures[key] = (*signatures[key], ('alone', key[1]))
    ids = _ids(signatures)
    out = {}
    for name, thing in tabled.items():
        grouped = {}
        for row in thing.table.rows:
            k = row.place[-1]
            grouped.setdefault(ids[name, k], []).append(k)
        out[name] = [Class(name, tuple(rows), signatures[name, rows[0]]) for rows in grouped.values()]
    return out


def _ids(signatures):
    """{key: the number of its signature among the signatures of its set}, a number for each distinct
    signature in the order of the keys."""
    numbers, out = {}, {}
    for key, signature in signatures.items():
        out[key] = numbers.setdefault((key[0], signature), len(numbers))
    return out


# ---- the families ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Family:
    """One class of the rows of a table, with what each of its instances has of its own.

    The parts of the family are the parts of its representative in the model of the representatives:
    each part whose thing is `host`. For the instance at place j of `hosts`, the name `host` in a part
    reads as `hosts[j]`; the value of the parameter `host.p` is `values[p][j]`; the start of the
    quantity `host.q` is `starts[q][j]`; the entity that the link `l` names is `links[l][j]`; its title
    is `titles[j]` and its text `x` is `texts[x][j]`; its number in its set is `rows[j]`. `labels` has
    the text of each value of the template: the label of the value `v` of an instance is that text
    after the title of the instance (`semantic.value_label`)."""

    of: Class
    template: str
    host: str
    hosts: tuple
    rows: tuple
    values: MappingProxyType
    starts: MappingProxyType
    links: MappingProxyType
    titles: tuple
    texts: MappingProxyType
    labels: MappingProxyType

    def __len__(self):
        return len(self.rows)


@dataclass(frozen=True)
class Hybrid:
    """The hybrid core of a model: the model of the representatives (`model`: every thing that no
    table makes, and one instance for each class of rows), its structures with each list as one node
    (`listed`, {start-state options: the structure}), and the family of each class.

    `model` is checked and proved as every model is; its structures write a reduction over a list as
    the chain of the flat structure, which every check reads. `listed` holds the same structures with
    a reduction over a list as one node (`sum(a, b)`): the form in which the name of a representative,
    outside its own parts, stands for each instance of its family at its place in the list. Each one
    is its typed parts (`structure.Structure`), with the place and the class of each trigger
    (`classified`): each run that is given values reads them for its proofs. A model with no table
    has no family, and `model` is the whole model.

    The model of the representatives is checked for one row of each class. `facts` has, for each
    declared run, what the checks of the values proved for every row (`row_facts`); it is empty when
    no class has more than one row."""

    model: object
    listed: MappingProxyType
    families: tuple
    path: str
    facts: MappingProxyType = MappingProxyType({})

    def proved(self, run, resolved=None, given=None):
        """What the checks of the values proved of a run for every row of each table (the stocks with
        a proved zero face, the crossings of a quantity that moves one way, the cumulative outcomes),
        or None when no class has more than one row. With `resolved`, the run with other values than
        the declared ones, the checks are made for those values: a failure is a ModelError. `given`
        has the values that a run was given: {input: (least, greatest) over the instances of its
        thing, in the unit of the input}, in the place of the values of `resolved` and of the
        columns."""
        if resolved is None:
            return self.facts.get(run)
        errors, facts = row_facts(self, run, resolved, given)
        if errors:
            raise ModelError(errors)
        return facts

    def family_of(self, host):
        """The family whose representative has the flat name `host`, or None."""
        return next((family for family in self.families if family.host == host), None)

    def positions(self):
        """{the flat name of each thing of the whole model: its number in the order of the model}
        (`positions`): what an engine that reads the core asks of it."""
        return positions(self)


def _host(name):
    return flat_entity(name)


def _literal_start(tokens, unit, place):
    """The node that a structure holds of the start that a cell gives a number var, by the functions
    that the builder uses for it (`Builder.quantity_part`): a number is read as a number, and any
    other literal as its typed node."""
    written = written_of(tokens)
    if isinstance(written, bool):
        source = engine_number(written)
    elif is_number(written):
        source = written
    else:
        tree, _ = grammar.tree(tokens)
        source = Typing(None, Context(None), None, place).visit(resolved.of_tree(tree))
    return flat_node(source, place, unit)


def _family(of, thing, template, structure, units):
    """The family of one class, with the columns of its values from the cells of its rows.
    `structure` is a whole structure of the model of the representatives (`structure.Structure`)."""
    table = thing.table
    members = {m.name: m for m in template.members if isinstance(m, ValueNode)}
    slots = {m.name for m in template.members if isinstance(m, LinkDecl)}
    host = _host(of.name(of.representative))
    values, starts, links, texts, titles = {}, {}, {}, {}, []
    # The text of each value of the template, which the label of the value of an instance starts from.
    labels = {name: member.text.value for name, member in members.items() if member.text is not None}
    at = {column.name: k for k, column in enumerate(table.columns)}
    for row_number in of.rows:
        row = table.rows[row_number - 1]
        cell = row.cells[at['title']] if 'title' in at and 'title' not in members else ''
        # The title of an instance with none of its own, as the resolver gives it (`Resolver.title`).
        given = thing.title.value if thing.title is not None else None
        titles.append(cell or given or f'{in_words(thing.name)} {row_number}')
    for column in table.columns:
        name = column.name
        cells = [table.rows[k - 1].cells[at[name]] for k in of.rows]
        if name in slots:
            links[name] = tuple(_host(cell) for cell in cells)
            continue
        member = members.get(name)
        if member is None or not any(cells):
            continue
        key = f'{host}.{name}'
        textual = Resolver.is_text(member)
        column_values = []
        for row_number, cell in zip(of.rows, cells):
            row = table.rows[row_number - 1]
            place = (*row.place, name)
            tokens = cell_tokens(cell, column.type, textual, row.line)
            written = written_of(tokens)
            if key in structure.parameters:
                parameter = structure.parameters[key]
                control = (parameter.metadata or {}).get('control')
                if control == 'binary':
                    column_values.append(engine_number(written))
                elif control == 'choice':
                    column_values.append(parameter.metadata['values'].index(written))
                else:
                    column_values.append(number_in(written, parameter.unit, units))
            elif key in structure.quantities:
                column_values.append(_literal_start(tokens, structure.quantities[key].unit, place))
            else:
                column_values.append(written)
        if key in structure.parameters:
            values[name] = tuple(column_values)
        elif key in structure.quantities:
            starts[name] = tuple(column_values)
        elif key not in structure.modes:
            texts[name] = tuple(column_values)
    return Family(
        of=of,
        template=template.name,
        host=host,
        hosts=tuple(_host(of.name(k)) for k in of.rows),
        rows=of.rows,
        values=MappingProxyType(values),
        starts=MappingProxyType(starts),
        links=MappingProxyType(links),
        titles=tuple(titles),
        texts=MappingProxyType(texts),
        labels=MappingProxyType(labels),
    )


def compile(path, library=None):
    """The hybrid core of the model of the file `path`. The model of the representatives is checked
    and proved as every model is (`front.compile_file`); the cost of it does not grow with the rows of
    a table. Raises ModelError."""
    from .library import load_library

    path = Path(path)
    file, files = front.load(path)
    if library is None:
        library = load_library(path, document=front.projection(file))
    limits = [
        diagnostic(
            'hybrid',
            f'{template}',
            f'The template {template} reads a list over the rows of a table ({read}) in a line of its '
            'own. The hybrid core does not hold such a model; its flat structure does.',
        )
        for template, read in lists_in_templates(file)
    ]
    if limits:
        raise ModelError(limits)
    found = classes(file)
    kept = Kept(
        rows={name: [of.representative for of in group] for name, group in found.items()},
        stands={
            of.name(k): of.name(of.representative)
            for group in found.values()
            for of in group
            for k in of.rows
        },
    )
    model = front.compile_file(file, path.as_posix(), thaw(library), files=files, only=kept)
    listed = front.listed_structures(file, path.as_posix(), thaw(library), files=files, only=kept)
    # Each listed structure with the place and the class of each trigger, made once: the core keeps it.
    listed = {starts: classified(structure) for starts, structure in listed.items()}
    changed = [
        diagnostic(
            'hybrid',
            f'{name}/when:',
            f'The condition of {name} reads a list over the rows of a table of values that move between '
            f'moments: with one row of each class it is a {before}, and with every row it is not '
            f'({kind}). The hybrid core does not hold such a model.',
        )
        for name, before, kind in kinds_changed(model, listed)
    ]
    if changed:
        raise ModelError(changed)
    units = UnitSystem(model.library['units'])
    whole = next(iter(model.whole.values()))
    things = {thing.name: thing for thing in file.things}
    families = []
    try:
        for name, group in found.items():
            for of in group:
                families.append(_family(of, things[name], things[things[name].template], whole, units))
    except (SyntaxProblem, ValueError, LookupError) as exc:
        # A cell of a row that is no representative, which the model of the representatives did not read.
        message = getattr(exc, 'message', None) or str(exc)
        raise ModelError([diagnostic('table', '', f'a table of the model: {message}')]) from None
    drawn = drawn_from_columns(model, families)
    if drawn:
        raise ModelError(drawn)
    core = Hybrid(model, MappingProxyType(listed), tuple(families), path.as_posix())
    # The model of the representatives is checked and proved for one row of each class. The checks
    # of the values are made once more for each declared run, over the range of the rows of each
    # class (`row_facts`).
    facts, errors = {}, []
    for run in model.runs:
        found, proved = row_facts(core, run)
        errors += found
        if proved is not None:
            facts[run] = MappingProxyType(proved)
    if errors:
        raise ModelError(errors)
    return dataclasses.replace(core, facts=MappingProxyType(facts))


def drawn_from_columns(model, families):
    """The diagnostics of each input of a class of more than one row whose distribution reads a
    column of the table: the model of the representatives has the value of such an input from the
    cells of one row, and the hybrid core holds that one value for every row of the class, where
    the flat structure has one for each row. The hybrid core does not hold such a model."""
    found = []
    for family in families:
        if len(family) < 2:
            continue
        columns = {f'{family.host}.{member}' for member in family.values}
        for name, by_text in model.arguments.items():
            if name.split('.', 1)[0] != family.host:
                continue
            read = {
                symbol
                for arguments in by_text.values()
                for source in arguments.values()
                if isinstance(source, nodes.Node)
                for symbol in nodes.names(source)
            }
            for column in sorted(read & columns):
                found.append(
                    diagnostic(
                        'hybrid',
                        name,
                        f'The input {name} is drawn from a distribution that reads {column}, a column '
                        'of the table. The hybrid core holds one value of such an input for each class '
                        'of rows; its flat structure holds one for each row.',
                    )
                )
    return found


class Weights:
    """How many values the instance of a name stands for in a list: the rows of the class of its
    thing (`core.intervals.prover`, `weights`)."""

    def __init__(self, hosts):
        self.hosts = dict(hosts)

    def get(self, name, default=1):
        return self.hosts.get(name.split('.', 1)[0], default)

    def __bool__(self):
        return bool(self.hosts)


def rows_of(core, structure, units):
    """What the checks of the values read of the rows of the tables (`analysis.values.value_facts`,
    `rows`): the range of each input and of each start that a column gives, over the rows of its
    class and in execution units, and the number of the rows of each class. `structure` is the
    typed parts of the structure."""
    ranges, starts, hosts, written = {}, {}, {}, {}
    for family in core.families:
        if len(family) > 1:
            hosts[family.host] = len(family)
        for member, column in family.values.items():
            name = f'{family.host}.{member}'
            scale = units.scale(structure.parameters[name].unit)
            numbers = [float(value) * scale for value in column]
            ranges[name] = (min(numbers), max(numbers))
            # The same in the unit of the input, as the cells write the values.
            written[name] = (min(column), max(column))
        for member, column in family.starts.items():
            # A start is a number or the node of a literal: each one is computed once.
            numbers = [
                float(start) if isinstance(start, (int, float)) else float(evaluate(start, {}, units))
                for start in set(column)
            ]
            starts[f'{family.host}.{member}'] = (min(numbers), max(numbers))
    return {'ranges': ranges, 'starts': starts, 'weights': Weights(hosts), 'written': written}


def classified(structure):
    """A structure with each list as one node (`Hybrid.listed`), with the class of each trigger. The
    checks of a structure have not read it (`front.listed_structures`), so each trigger has its
    condition and no class. The classifier of those checks gives each one its class
    (`analysis.structure.classify`: a crossing, a timer, a face or a discrete condition) and its
    place: its own, or that of its rule for an event with no condition. The proofs of the values of
    a run read the class: they prove a crossing and a zero face only for a trigger that has one
    (`analysis.values`), so without it the proofs over the rows of a table would prove neither. A
    condition that the classifier refuses keeps no class: the hybrid core refuses the model by the
    name of its event (`kinds_changed`)."""
    discrete = structure_analysis.discrete_names(structure)
    moving = structure_analysis.evolving_parts(structure) | {'t'}
    triggers = {}
    for name, rule in structure.rules.items():
        if rule.trigger.kind is not None:
            continue
        try:
            triggers[name] = structure_analysis.classify(rule, structure, discrete, moving)
        except ValueError:
            continue
    return structure.with_facts({'computed_order': structure.computed_order, 'triggers': triggers})


def row_facts(core, run, resolved=None, given=None):
    """(the diagnostics, the proved facts) of the checks of the values of one run for every row of
    each table. The structure is the one with each list as one node, in
    which a representative stands for each row of its class: every proof is over the range of the
    values of the rows, and a sum over a list counts a member once for each row. So a proof of it
    holds for every row; it can fail where the proof of each row by itself holds, and the model is
    then refused, with the class named.

    ([], None) when no class has more than one row: the model of the representatives is the whole
    model then. `resolved` is the run with its values (default: the declared run); `given` is that
    of `Hybrid.proved`.

    The value of each row is first checked against the range of its input, as the compiler checks
    the value of each instance of a flat model (`compile.check_parameters`): the model of the
    representatives has the values of one row of each class."""
    if not any(len(family) > 1 for family in core.families):
        return [], None
    model = core.model
    resolved = resolved if resolved is not None else model.resolve(run)
    key = next((k for k in core.listed if tuple(k) == tuple(resolved.starts)), None)
    if key is None:
        key = next(iter(core.listed))
    library = thaw(model.library)
    units = UnitSystem(library['units'])
    # The structure with what the run has of its own that the checks read: its values and its time.
    own = {
        name: value
        for name, value in resolved.own().items()
        if name in ('values', 'parameter_values', 'time')
    }
    rs = Resolved.over(core.listed[key], own)
    rows = rows_of(core, rs, units)
    written = {**rows.pop('written'), **(given or {})}
    outside = []
    for name, ends in written.items():
        for end in dict.fromkeys(ends):
            check_parameters(rs.parameters, {name: end}, f'runs/{run}/values', outside)
    if outside:
        return [{**item, 'context': f'runs/{run}'} for item in outside], None
    for name, (least, most) in (given or {}).items():
        scale = units.scale(rs.parameters[name].unit)
        rows['ranges'][name] = (float(least) * scale, float(most) * scale)
    errors, facts = value_facts(rs, library, rows)
    hosts = {family.host: family for family in core.families if len(family) > 1}
    found = []
    for item in errors:
        path = str(item.get('path', ''))
        text = f'{path} {item.get("message", "")}'
        # The class that the part is of: its path starts with the template, or its text names the
        # representative.
        named = [
            f'the {len(family)} rows of {family.of.set} that row {family.of.representative} stands for'
            for host, family in hosts.items()
            if path.split('/')[0] == family.template
            or re.search(rf'(?<![A-Za-z0-9_]){re.escape(host)}(?![A-Za-z0-9_])', text)
        ]
        over = ' and '.join(named) if named else 'the rows of each table'
        found.append(
            {
                **item,
                'context': f'runs/{run}',
                'message': f'{item.get("message", "")} (the proof is over the range of {over})',
            }
        )
    return found, {key: value for key, value in facts.items() if key != 'bounds'}


# ---- the checking mode: every family written out ------------------------------------------------------
#
# `written_out` gives the flat structures that the model of the representatives stands for: each part
# of a representative once for each instance of its family, and each list outside the family with every
# member. `problems` compares them with the flat lowering of the whole file. It is for small models:
# it costs what the flat lowering costs.

# The sections whose parts the builder writes thing by thing, in the order of the names of the things.
BY_THING = ('entities', 'quantities', 'modes', 'computed', 'labels', 'rates', 'coupling', 'rules', 'links')
# The sections of the checks, whose parts the builder names by the template of their thing.
CHECKS = ('state_checks', 'input_checks', 'partitions')
LISTED_CALLS = (*nodes.LISTED, 'min', 'max')
# A text that can hold a reduction over a list as one node.
LISTED_TEXT = re.compile(r'\b(?:' + '|'.join(sorted(nodes.LISTED)) + r')\(')


def _named(host):
    """The pattern of the flat name of a thing as a whole name: `tanks_1`, not `tanks_10`."""
    return re.compile(rf'(?<![A-Za-z0-9_]){re.escape(host)}(?![A-Za-z0-9_])')


class _Writer:
    """The parts of the structures of a hybrid core, written out for every instance."""

    def __init__(self, families, entities):
        """`families` are the families of a hybrid core, and `entities` the flat names of the things
        of its model of the representatives, in the order of the model."""
        # Every family, a class of one too: the instances of one table go together, in the order of its rows.
        self.families = {family.host: family for family in families}
        self.patterns = {host: _named(host) for host in self.families}
        self.any = (
            re.compile('|'.join(pattern.pattern for pattern in self.patterns.values()))
            if self.patterns
            else None
        )
        self.of_instance = {host: family for family in families for host in family.hosts}
        # The number of each thing in the order of the whole model, from 0: the things of the model
        # of the representatives in their order, with every instance of a table in the place of its
        # representatives. The rank of an event holds it.
        sizes = {}
        for family in families:
            sizes[family.of.set] = sizes.get(family.of.set, 0) + len(family)
        sets = {family.host: family.of.set for family in families}
        self.position, starts, count = {}, {}, 0
        for host in entities:
            name = sets.get(host)
            if name is None:
                self.position[host] = count
                count += 1
            elif name not in starts:
                starts[name] = count
                count += sizes[name]
        for family in families:
            for host, row in zip(family.hosts, family.rows):
                self.position[host] = starts[family.of.set] + row - 1

    def owner(self, key, value=None, section=None):
        """The family whose representative has the part `key`, or None."""
        if section in CHECKS:
            return self.check_owner(key)
        host = key
        if isinstance(value, dict) and isinstance(value.get('entity'), str):
            host = value['entity']
        elif key not in self.families:
            host = key.rpartition('.')[0]
        return self.families.get(host)

    def check_owner(self, key):
        """The family whose representative has the check `key`, or None. The builder names a check by
        the template of its thing and the number of the check, `Tank.0`, and, when the template has
        more than one instance in the model, by the thing too: `Tank.0.tanks_3`."""
        template, _, rest = key.partition('.')
        _, _, host = rest.partition('.')
        if host:
            return self.families.get(host)
        found = [family for family in self.families.values() if family.template == template]
        return found[0] if len(found) == 1 else None

    def check_name(self, key, family, j):
        """The name of the check `key` of a representative for the instance at place j: with the name
        of the thing when the whole model has more than one instance of the template."""
        template, _, rest = key.partition('.')
        number, _, host = rest.partition('.')
        if host or len(family) > 1:
            return f'{template}.{number}.{family.hosts[j]}'
        return key

    # -- a part of a representative, for one instance

    def instance(self, value, family, j):
        """A part of the representative of `family` as the part of its instance at place j."""
        if isinstance(value, dict):
            return {self.instance(k, family, j): self.instance(v, family, j) for k, v in value.items()}
        if isinstance(value, list):
            return [self.instance(item, family, j) for item in value]
        if isinstance(value, str):
            value = self.patterns[family.host].sub(family.hosts[j], value)
            for targets in family.links.values():
                # A link into a table: in the parts of the representative, the representative of the
                # class that it links to stands for the instance that this instance links to.
                linked = self.of_instance.get(targets[j])
                if linked is not None and linked.host != targets[j]:
                    value = self.patterns[linked.host].sub(targets[j], value)
        return value

    def part(self, section, key, value, family, j):
        made = self.instance(value, family, j)
        name = key[len(family.host) + 1 :]
        if section == 'parameters' and name in family.values:
            made['value'] = family.values[name][j]
        if section == 'quantities' and name in family.starts:
            # The plain data of a structure writes an expression as its text.
            made['initial'] = nodes.text(family.starts[name][j])
        if section == 'entities':
            made['copy'] = family.rows[j]
            made['label'] = family.titles[j]
        elif name in family.labels and isinstance(made.get('label'), str):
            # The label of a value: its text after the title of its instance, when the label of the
            # representative is made so.
            text = family.labels[name]
            if made['label'] == value_label(
                text, family.titles[family.rows.index(family.of.representative)], True
            ):
                made['label'] = value_label(text, family.titles[j], True)
        if section == 'rules':
            made['rank'] = self.rank(made, family.rows[j])
        return made

    def rank(self, rule, copy=None):
        """The rank of a rule in the whole model: its line, the number of its thing in the order of the
        model, and its number in its set. The start has a rank of its own."""
        rank = rule.get('rank')
        if not isinstance(rank, list) or len(rank) != 3:
            return rank
        return [rank[0], self.position.get(rule['entity'], rank[1]), rank[2] if copy is None else copy]

    # -- a part outside the families, with every member of each list

    def members(self, text):
        """The families whose representatives a text names."""
        return [self.families[host] for host, pattern in self.patterns.items() if pattern.search(text)]

    def spread(self, items, text_of=lambda item: item, by_name=False):
        """A list of items in which the item of a representative stands for each instance of its
        family: every instance, in the order of the rows of its table, or with `by_name` in the order
        of their names (the links of a thing, which the builder writes in the order of the names that
        an expression reads)."""
        out, position = [], {}
        for index, item in enumerate(items):
            text = text_of(item)
            found = self.members(text) if isinstance(text, str) else []
            if len(found) != 1:
                out.append(((index, 0), item))
                continue
            family = found[0]
            # The instances of one table stay together, at the place of its first representative.
            at = position.setdefault(family.of.set, index)
            for j, row in enumerate(family.rows):
                made = self.instance(item, family, j)
                out.append(((at, text_of(made) if by_name else row), made))
        return [item for _, item in sorted(out, key=lambda pair: pair[0])]

    def expression(self, text):
        """An expression of a part outside the families, with each list as the flat structure writes
        it: every member, and a sum as its chain."""
        try:
            node = nodes.parse(text, WRITTEN)
        except SyntaxError:
            return text
        return nodes.text(self.listed(node))

    def listed(self, node):
        if isinstance(node, nodes.Call) and node.function in LISTED_CALLS:
            # The members as texts, in which the name of a representative is the name of an instance;
            # then each as its node again.
            members = self.spread([nodes.text(self.listed(arg)) for arg in node.args])
            return _flat(node.function, [nodes.parse(member, WRITTEN) for member in members])
        if isinstance(node, nodes.Unary):
            return nodes.unary(node.op, self.listed(node.operand))
        if isinstance(node, nodes.Binary):
            return nodes.binary(node.op, self.listed(node.left), self.listed(node.right))
        if isinstance(node, nodes.Compare):
            return nodes.compare(node.ops, [self.listed(item) for item in node.operands])
        if isinstance(node, nodes.BoolOp):
            return nodes.boolean(node.op, [self.listed(item) for item in node.values])
        if isinstance(node, nodes.IfElse):
            return nodes.if_else(self.listed(node.test), self.listed(node.body), self.listed(node.orelse))
        if isinstance(node, nodes.Call):
            return nodes.call(node.function, [self.listed(arg) for arg in node.args])
        return node

    def outside(self, value, by_name=False):
        if isinstance(value, dict):
            keys = self.spread(list(value), lambda key: key if isinstance(key, str) else None, by_name)
            if keys == list(value):
                return {key: self.outside(item) for key, item in value.items()}
            # A mapping by the names of parts: the entry of a representative is the entry of each
            # instance.
            out = {}
            for key, item in value.items():
                found = self.members(key) if isinstance(key, str) else []
                if len(found) != 1:
                    out[key] = self.outside(item)
                    continue
                for j in range(len(found[0])):
                    out[self.instance(key, found[0], j)] = self.instance(item, found[0], j)
            return {key: out[key] for key in keys}
        if isinstance(value, list):
            if any(isinstance(item, str) and self.names(item) for item in value):
                return self.spread(value)
            return [self.outside(item) for item in value]
        if isinstance(value, str) and (self.names(value) or LISTED_TEXT.search(value)):
            return self.expression(value)
        return value

    def names(self, text):
        """Whether a text names a representative."""
        return self.any is not None and self.any.search(text) is not None

    # -- a structure

    def structure(self, s):
        out = {}
        for section, parts in s.items():
            if section == 'events' or not isinstance(parts, dict):
                out[section] = parts
                continue
            made, first = [], {}
            for index, (key, value) in enumerate(parts.items()):
                family = self.owner(key, value, section)
                if family is None:
                    part = self.outside(value, by_name=section == 'links')
                    if section == 'rules':
                        part = {**part, 'rank': self.rank(part)}
                    made.append(((index, 0, index), key, part))
                    continue
                at = first.setdefault(family.of.set, index)
                for j, row in enumerate(family.rows):
                    name = (
                        self.check_name(key, family, j)
                        if section in CHECKS
                        else self.instance(key, family, j)
                    )
                    made.append(((at, row, index), name, self.part(section, key, value, family, j)))
            if section in BY_THING:
                made.sort(key=lambda item: (_thing(item[1], item[2]), item[0][2]))
            elif section == 'flows':
                made.sort(key=lambda item: item[1])
            else:
                made.sort(key=lambda item: item[0])
            out[section] = {key: value for _, key, value in made}
        out['events'] = _events(out)
        return out


def positions(core):
    """{the flat name of each thing of the whole model: its number in the order of the model, from
    0}: the things of the model of the representatives in their order, with every instance of a table
    in the place of its representatives. The rank of an event holds this number."""
    return _Writer(core.families, list(core.model.entities)).position


def _thing(key, value):
    if isinstance(value, dict) and isinstance(value.get('entity'), str):
        return value['entity']
    return key.rpartition('.')[0] or key


def _flat(name, members):
    """A reduction over the members of a list as the flat structure writes it
    (`lower.expressions.Typing.reduction`)."""
    if name in ('min', 'max'):
        return nodes.call(name, members)
    if len(members) == 1:
        return members[0]
    if name in ('any', 'all'):
        return nodes.boolean('or' if name == 'any' else 'and', members)
    total = members[0]
    for term in members[1:]:
        total = nodes.binary('add', total, term)
    return total


def _events(s):
    """The events of a structure, as the builder registers them (`Builder.finish_events`)."""
    events = {}
    for rid, rule in s['rules'].items():
        for event in rule_events(rule):
            events.setdefault(event, {'sources': []})['sources'].append(rid)
    # The writer writes plain data, in which each expression is its text; the helpers of the builder
    # read nodes, so they read the typed parts of the structure as the builder's mappings hold them.
    for event in sorted(read_events(Structure.of(s).plain(written=False))):
        events.setdefault(event, {'sources': []})
    return events


def written_out(core):
    """{start-state options: the flat structure, as plain data} that a hybrid core stands for: its
    structures with one node for each list, written out, with the facts that the checks of a structure
    write into it."""
    writer = _Writer(core.families, core.model.entities)
    library = thaw(core.model.library)
    units = UnitSystem(library['units'])
    out = {}
    for starts, structure in core.listed.items():
        made = writer.structure(unchecked(structure))
        # The facts that the checks of a structure give it (the order of the formulas, the class of
        # each trigger), by the checks themselves.
        _, typed = structure_analysis.checked(Structure.of(made), library, units)
        out[starts] = typed.plain()
    return out


def unchecked(structure):
    """The plain data of a listed structure (`Hybrid.listed`) as the lowering writes it, before the
    checks of a structure: no order of the formulas, and each trigger with its condition and the
    place of its condition, with no class. The checks of a structure give both again."""
    out = structure.plain()
    out['computed_order'] = []
    for rule in out['rules'].values():
        trigger = rule['trigger']
        rule['trigger'] = {'path': trigger['path'], 'when': trigger['when']}
    return out


def problems(core, flat=None):
    """The checking mode: the differences between the flat structures that a hybrid core stands for
    (`written_out`) and the flat lowering of the whole file, each as (kind, place, the one, the
    other); none when the two agree. `flat` is the model of the whole file, built when it is not given.
    The cost is that of the flat lowering, so this is for small models.

    One thing is not compared: the label of a part of an instance that is no representative. The
    hybrid core has the title and the texts of each instance and the labels of the representative; it
    does not write the label of each part of each instance."""
    from .model import build_model

    flat = build_model(core.path) if flat is None else flat
    silent = {host for family in core.families for host in family.hosts if host != family.host}
    found = []
    written = written_out(core)
    if list(written) != list(flat.structures):
        return [('start sets', '', list(written), list(flat.structures))]
    for starts, structure in flat.structures.items():
        _compare(written[starts], structure.plain(), f'{list(starts)}', found, silent)
    return found


def _compare(one, other, place, found, silent, part=None):
    if type(one) is not type(other):
        found.append(('kind', place, one, other))
    elif isinstance(one, dict):
        if list(one) != list(other):
            kind = 'order' if set(one) == set(other) else 'names'
            found.append((kind, place, list(one), list(other)))
        for key, value in one.items():
            if key in other:
                if key == 'label' and part in silent:
                    continue
                inner = part
                if isinstance(value, dict):
                    inner = _thing(key, value) if place.count('/') == 1 else part
                _compare(value, other[key], f'{place}/{key}', found, silent, inner)
    elif isinstance(one, list):
        if len(one) != len(other):
            found.append(('length', place, one, other))
        else:
            for k, (a, b) in enumerate(zip(one, other)):
                _compare(a, b, f'{place}[{k}]', found, silent, part)
    elif one != other:
        found.append(('value', place, one, other))


# ---- the checking mode for a model of any size: a second representative -----------------------------


def _turned(family):
    """A family with its last instance in the first place: the same instances with the same values,
    and another representative."""

    def last_first(column):
        return (column[-1], *column[:-1])

    rows = last_first(family.rows)
    return dataclasses.replace(
        family,
        of=Class(family.of.set, rows, family.of.signature),
        host=family.hosts[-1],
        hosts=last_first(family.hosts),
        rows=rows,
        values=MappingProxyType({name: last_first(column) for name, column in family.values.items()}),
        starts=MappingProxyType({name: last_first(column) for name, column in family.starts.items()}),
        links=MappingProxyType({name: last_first(column) for name, column in family.links.items()}),
        titles=last_first(family.titles),
        texts=MappingProxyType({name: last_first(column) for name, column in family.texts.items()}),
    )


def _without_labels(value):
    if isinstance(value, dict):
        return {key: _without_labels(item) for key, item in value.items() if key != 'label'}
    if isinstance(value, list):
        return [_without_labels(item) for item in value]
    return value


def second_problems(core, library=None):
    """The checking mode for a model of any size. The compiler lowers a second time, with the last
    instance of each class as its representative. Each part that the first representative gives that
    instance (its name in the place of the representative's, the values of its row, its links, its
    rank) must be the part that the lowering itself gives it. The differences, as `problems` gives
    them; none when the two agree.

    The cost is one more lowering of one instance for each class, with no check. It compares the
    parts of the families; a part outside them, and every instance, is what `problems` compares for a
    small model. The label of a part that is no value is not compared (a text of an event that a
    text of the instance fills)."""
    from .library import load_library

    path = Path(core.path)
    file, files = front.load(path)
    if library is None:
        library = load_library(path, document=front.projection(file))
    by_set = {}
    for family in core.families:
        by_set.setdefault(family.of.set, []).append(family)
    kept = Kept(
        rows={name: sorted(family.rows[-1] for family in group) for name, group in by_set.items()},
        stands={
            f'{family.of.set}.{row}': f'{family.of.set}.{family.rows[-1]}'
            for family in core.families
            for row in family.rows
        },
    )
    second = {
        starts: classified(structure)
        for starts, structure in front.listed_structures(
            file, path.as_posix(), thaw(library), files=files, only=kept
        ).items()
    }
    turned = {family.host: _turned(family) for family in core.families}
    first_writer = _Writer(core.families, core.model.entities)
    second_writer = _Writer(
        tuple(turned.values()),
        [turned[host].host if host in turned else host for host in core.model.entities],
    )
    found = []
    if list(second) != list(core.listed):
        return [('start sets', '', list(core.listed), list(second))]
    for starts, structure in core.listed.items():
        ours, theirs = unchecked(structure), unchecked(second[starts])
        for family in core.families:
            if len(family) < 2:
                continue
            j, other = len(family) - 1, turned[family.host]
            for section, parts in ours.items():
                if section == 'events' or not isinstance(parts, dict):
                    continue
                for key, value in parts.items():
                    if first_writer.owner(key, value, section) is not family:
                        continue
                    if section in CHECKS:
                        # The second lowering names the check by its own representative, or by the
                        # template alone when that is its only instance of the template.
                        name = first_writer.check_name(key, family, j)
                        template, _, rest = key.partition('.')
                        number, _, host = rest.partition('.')
                        lowered_name = f'{template}.{number}.{other.host}' if host else key
                    else:
                        name = lowered_name = first_writer.instance(key, family, j)
                    place = f'{list(starts)}/{section}/{name}'
                    if lowered_name not in theirs[section]:
                        found.append(('names', place, name, None))
                        continue
                    one = first_writer.part(section, key, value, family, j)
                    # What the second lowering gives the instance, as it gives it: only the names of
                    # the things that it links to, and its rank in the whole model, are written out.
                    lowered = second_writer.instance(theirs[section][lowered_name], other, 0)
                    if section == 'rules':
                        lowered['rank'] = second_writer.rank(lowered)
                    if section != 'entities' and key[len(family.host) + 1 :] not in family.labels:
                        one, lowered = _without_labels(one), _without_labels(lowered)
                    _compare(one, lowered, place, found, set())
    return found
