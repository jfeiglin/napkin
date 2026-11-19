"""What the three scripts of A5 share: where the old models are, and how the old compiler reads them.

Everything here reads a model with the old compiler at the base commit (`napkin.model.language`), and
never with a text pattern over the source. Run each script with the old package on the path:

    PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python <script>.py

`symbols(context)` gives a small table of the names of one model, which the census and the check use to
say what a dotted name reads: a value of a kind, an event, an outcome, a list, a thing. `facts(entry)`
gives what `check.py` compares of an old model; run alone, this module prints them as JSON:

    PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python oldmodel.py ENTRY.scn
"""

from __future__ import annotations

import ast
import collections
import dataclasses
import json
import os
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

BASE = Path(os.environ.get('NAPKIN_BASE', '/home/user/napkin-base'))

try:
    from napkin.model.language import expressions, lex, modules, nodes, parse
except ImportError as exc:  # pragma: no cover - a message for the reader of the script
    raise SystemExit(
        'the old compiler is not on the path: run with PYTHONPATH=/home/user/napkin-base\n' + str(exc)
    ) from None

if not str(Path(parse.__file__).resolve()).startswith(str(BASE.resolve())):
    raise SystemExit(
        f'napkin is imported from {parse.__file__}, not from the base commit {BASE}: '
        'run with PYTHONPATH=/home/user/napkin-base'
    )


def model_files():
    """Each `.scn` file of `examples/` and `scenarios/` at the base commit, in a fixed order."""
    found = sorted(BASE.glob('examples/**/*.scn')) + sorted(BASE.glob('scenarios/**/*.scn'))
    return [path for path in found if 'tests' not in path.relative_to(BASE).parts]


def entry_files():
    """The entry files: each `model.scn`, of a package or of a variant."""
    return [path for path in model_files() if path.name == 'model.scn']


def home_entry(path):
    """The entry file whose model gives a file its names: its own for an entry file, and the main
    file of its package for a module."""
    path = Path(path)
    if path.name == 'model.scn':
        return path
    folder = path.parent
    while folder != folder.parent:
        if (folder / 'model.scn').is_file():
            return folder / 'model.scn'
        folder = folder.parent
    return path


def parse_file(path):
    """The `nodes.File` of one file alone, as the old parser reads it."""
    return parse.parse(Path(path).read_text(encoding='utf-8'))


def context_files(path):
    """[(path, File)] of the files of the model that gives `path` its names (`home_entry`), each parsed
    alone, in the order of the model: dependencies first."""
    entry = home_entry(path)
    return [(Path(p), parse_file(p)) for p in modules.paths(entry)]


def relink(file, names):
    """Read the lets of `file` that name things of the whole model as links (`parse.links`): the
    parser alone knows only the things of the file itself."""
    parse.links(file, set(names))
    return file


# ---- a small table of names ---------------------------------------------------------------------------


@dataclass
class ThingInfo:
    """What a thing declares, with its template's members under its own."""

    name: str
    kind: str  # entity, template, instance
    template: str | None
    values: dict = field(default_factory=dict)  # name -> field kind (see `field_kind`)
    types: dict = field(default_factory=dict)  # name -> type as written, or None
    events: dict = field(default_factory=dict)  # name -> [outcome names]
    flows: set = field(default_factory=set)
    # name -> (target: a template, a thing or a list of things; many; declared as a slot)
    links: dict = field(default_factory=dict)
    shares: dict = field(default_factory=dict)  # stock name -> Allocate


def field_kind(value):
    """The kind of a field as the migration reads it: `input.number`, `input.bool`, `input.text`,
    `input.named`, `let.fixed`, `let.formula`, `var.named`, `var.bool`, `var.number`."""
    tokens = value.value.tokens if value.value is not None else []
    one = len(tokens) == 1
    if value.kind == 'text':
        return 'input.text'
    if value.kind == 'input':
        if isinstance(value.type, list):
            return 'input.named'
        if value.type == 'bool' or (one and tokens[0].is_name('true', 'false')):
            return 'input.bool'
        if one and tokens[0].kind == 'text':
            return 'input.named'
        return 'input.number'
    if value.kind == 'fixed':
        return 'let.fixed'
    if value.kind == 'formula':
        return 'let.formula'
    if value.kind == 'state':
        if isinstance(value.type, list) or (one and tokens[0].kind == 'text'):
            return 'var.named'
        return 'var.bool'
    if value.kind == 'var':
        return 'var.number'
    return f'?{value.kind}'


class Symbols:
    """The names of one model: its things, and what a dotted name reads in a thing."""

    def __init__(self, files):
        self.things = {}
        self.nodes = {}
        self.templates = set()
        for file in files:
            for thing in file.things:
                self.nodes.setdefault(thing.name, thing)
        for file in files:
            for thing in file.things:
                if thing.kind == 'template':
                    self.templates.add(thing.name)
        for name in self.nodes:
            self.things[name] = self._info(name)
        self.instances = {}
        for name, thing in self.nodes.items():
            if thing.template is not None:
                self.instances.setdefault(thing.template, []).append(name)

    def _info(self, name):
        thing = self.nodes[name]
        kind = 'instance' if thing.template is not None else thing.kind
        info = ThingInfo(name, kind, thing.template)
        sources = []
        if thing.template is not None and thing.template in self.nodes:
            sources.append(self.nodes[thing.template])
        sources.append(thing)
        for source in sources:
            for member in source.members:
                if isinstance(member, nodes.Value):
                    info.values[member.name] = field_kind(member)
                    info.types[member.name] = member.type
                elif isinstance(member, nodes.Change):
                    if member.kind is not None and member.lines is not None:
                        info.values[member.name] = field_kind(member.lines)
                        if member.lines.type is not None:
                            info.types[member.name] = member.lines.type
                elif isinstance(member, nodes.Event):
                    info.events[member.name] = [o.name for o in member.outcomes] or ['done']
                elif isinstance(member, nodes.Flow):
                    info.flows.add(member.name)
                elif isinstance(member, nodes.LinkDecl):
                    info.links[member.name] = (member.target, member.many, True)
                elif isinstance(member, nodes.LinkBind):
                    info.links[member.name] = (member.targets, member.many, False)
                elif isinstance(member, nodes.Allocate):
                    info.shares[member.stock] = member
                elif isinstance(member, nodes.Output) and member.expr is not None:
                    info.values[member.name] = 'output'
        return info

    def declarer(self, thing):
        """The thing that declares the members of `thing`: its template for an instance, else itself."""
        node = self.nodes.get(thing)
        return node.template if node is not None and node.template is not None else thing

    def link_owner(self, info, part):
        """What a link of a thing reads: ('thing', name) for one thing (a slot of a template reads the
        template's members) or ('list', template) for a list of things."""
        target, many, declared = info.links[part]
        if declared:
            # `let x: T` is a slot for one thing of T; `let xs: [T]` a slot for a list of them.
            return ('list', target) if many else ('thing', target)
        if many:
            return ('list', self._common(target))
        # `let zones = Zone` binds the list of the template's instances (docs/language.md, 2.3).
        return ('list', target) if target in self.templates else ('thing', target)

    def owner_of(self, parts, thing):
        """What the head of a dotted name reads, from the thing `thing` (None: the top level):
        ('thing', name), ('list', template or None) or None."""
        current = ('thing', thing) if thing is not None else None
        for k, part in enumerate(parts):
            if current is not None and current[0] == 'list':
                return None  # a member of a list has no further head in the old language
            found = None
            if current is not None and current[1] in self.things:
                info = self.things[current[1]]
                if part in info.links:
                    found = self.link_owner(info, part)
            if found is None and k == 0:
                if part in self.templates:
                    found = ('list', part)
                elif part in self.things:
                    found = ('thing', part)
            if found is None:
                return None
            current = found
        return current

    def _common(self, targets):
        """The template that the things of a list link share, or None."""
        if not isinstance(targets, list):
            return None
        found = {self.nodes[name].template for name in targets if name in self.nodes}
        return found.pop() if len(found) == 1 else None

    def member_thing(self, owner):
        """The thing whose members a ('thing', name) or ('list', template) owner reads."""
        if owner is None:
            return None
        kind, name = owner
        if kind == 'list':
            return self.things.get(name) if name is not None else None
        info = self.things.get(name)
        if info is None:
            return None
        return info

    def read(self, symbol, thing):
        """What a dotted name reads in the thing `thing`:
        ('value', kind, owner thing, member, through_list),
        ('event', owner thing, event, outcome or None, through_list),
        ('flow', owner thing, flow), ('thing', name), ('list', template), or None."""
        parts = symbol.split('.')
        # A copy's number after the name of its set joins the name: `waves.2.x`.
        for cut in range(len(parts), 0, -1):
            head, rest = parts[: cut - 1], parts[cut - 1 :]
            owner = self.owner_of(head, thing) if head else (('thing', thing) if thing is not None else None)
            if owner is None:
                continue
            through_list = owner[0] == 'list'
            info = self.member_thing(owner)
            if info is None:
                continue
            name = rest[0]
            if len(rest) == 1:
                if name in info.values:
                    return ('value', info.values[name], info.name, name, through_list)
                if name in info.events:
                    return ('event', info.name, name, None, through_list)
                if name in info.flows:
                    return ('flow', info.name, name)
                if name in info.links:
                    return self.link_owner(info, name)
            elif len(rest) == 2 and name in info.events and rest[1] in info.events[name]:
                return ('event', info.name, name, rest[1], through_list)
        if len(parts) == 1:
            if symbol in self.templates:
                return ('list', symbol)
            if symbol in self.things:
                return ('thing', symbol)
        return None


def quantity_kinds(files, symbols):
    """{(thing, member): `stock`, `tally` or `state`} of each number var of the files of one model,
    by the old compiler's own rule (`napkin/model/language/resolve.py`, `var_kinds`): a stock when a
    flow or a move joins it and something takes from it (a flow, a move, `-=` or `=`), a tally when a
    flow or a move joins it and nothing takes from it, and a number state when no flow or move joins
    it. The thing is the template or the thing that declares the var: an instance has its
    template's kinds."""
    ends, drained = set(), set()

    def key(symbol, thing):
        found = symbols.read(symbol, thing)
        if found is None or found[0] != 'value':
            return None
        # A flow of one thing can name a var of an instance (`controls_crew.hours`): the kind is the
        # template's, so that one declaration has one kind. It is the widest kind of its instances.
        return (symbols.declarer(found[2]), found[3])

    for file in files:
        for thing in [*file.things, *file.changes]:
            for member in thing.members:
                if isinstance(member, nodes.Flow):
                    pairs = member.together if member.together is not None else [member.pair]
                    for pair in pairs:
                        if pair.source != 'outside':
                            ends.add(key(pair.source, thing.name))
                            drained.add(key(pair.source, thing.name))
                        if pair.target != 'outside':
                            ends.add(key(pair.target, thing.name))
                elif isinstance(member, nodes.Event):
                    for outcome in member.outcomes:
                        for line in outcome.lines:
                            if isinstance(line, nodes.Move):
                                ends.update({key(line.source, thing.name), key(line.target, thing.name)})
                                drained.add(key(line.source, thing.name))
                            elif isinstance(line, nodes.Assign) and line.op != '+=':
                                drained.add(key(line.target, thing.name))
    kinds = {}
    for name, info in symbols.things.items():
        if info.kind == 'instance':
            continue
        for member, kind in info.values.items():
            if kind != 'var.number':
                continue
            found = (name, member)
            if found not in ends:
                kinds[found] = 'state'
            else:
                kinds[found] = 'stock' if found in drained else 'tally'
    return kinds


def model_of(path):
    """(the `File` of `path`, relinked; the files of its model; its `Symbols`; the kinds of its
    number vars)."""
    path = Path(path).resolve()
    parts = context_files(path)
    names = {thing.name for _, file in parts for thing in file.things}
    own = None
    for current, file in parts:
        relink(file, names)
        if current.resolve() == path:
            own = file
    if own is None:
        own = relink(parse_file(path), names)
        parts.append((path, own))
    files = [file for _, file in parts]
    symbols = Symbols(files)
    return own, files, symbols, quantity_kinds(files, symbols)


def symbols_for(path):
    """(the `File` of `path`, relinked over its model; the `Symbols` of that model)."""
    path = Path(path).resolve()
    parts = context_files(path)
    names = {thing.name for _, file in parts for thing in file.things}
    own = None
    for current, file in parts:
        relink(file, names)
        if current.resolve() == path:
            own = file
    if own is None:
        own = relink(parse_file(path), names)
        parts.append((path, own))
    return own, Symbols([file for _, file in parts])


# ---- expressions ----------------------------------------------------------------------------------------


def tree_of(expr):
    """(the Python tree of an expression of the old language, {placeholder: name}), or (None, {})
    for one that is not an expression (a list of links)."""
    try:
        return expressions.tree(expr.tokens)
    except lex.SyntaxProblem:
        return None, {}


def written(tokens):
    """The tokens of a line as the file writes them, with one space where the file has one."""
    out = []
    for token in tokens:
        text = token.source or str(token.value)
        if token.kind == 'text':
            text = '"' + str(token.value) + '"'
        if out and token.space:
            out.append(' ')
        out.append(text)
    return ''.join(out)


# ---- what check.py compares of an old model ----------------------------------------------------------------

# The kinds of the old language as `check.py` compares them with the kinds of now (`newmodel.kinds`).
KINDS = {
    'input.number': 'input.number',
    'input.bool': 'input.bool',
    'input.text': 'input.text',
    'input.named': 'input.enum',
    'let.fixed': 'fixed',
    'let.formula': 'formula',
    'var.named': 'state.enum',
    'var.bool': 'state.bool',
    'output': 'formula',
}


def number_key(value, scale, dimension):
    """A number as the check compares it: its value in base units with 12 significant digits and its
    dimension, so that `12 h` and `0.5 day` are one number; a zero has no dimension (`newmodel`)."""
    base = float(Fraction(str(value)) * Fraction(scale))
    dims = [] if base == 0 else sorted([str(k), float(v)] for k, v in dimension)
    return f'{base:.12g}', json.dumps(dims)


def facts(entry):
    """What `check.py` compares of an old model (an entry file with the files that it reads):

    - `numbers`: [value in base units, dimension, count] of each number of every file of the model,
      a bare number in the unit that its declaration gives it (`exprs.numbers_of`); the delays of a
      reporting lag are left out, because a caller selects a lag now (D10);
    - `texts`: {text: count} of every text, record explanation, name of an option or of its group,
      and text value;
    - `kinds`: {path: [kind, type]} of each thing, value, flow and event, by the path of the thing that
      declares it (a template for its instances), with a stored number's kind by its use (`stock`,
      `tally`, `state`), as `quantity_kinds` gives it;
    - `flows`: {path of a flow: its pairs as [source, sink], sorted}, each end the path of a store;
    - `unestimated`: the outputs that have no estimate, which have no declaration now (D4);
    - `proven`: {run: the paths of the outputs that the old compiler proved cumulative in it}, with
      `''` for a model that has no runs (the old `base` run)."""
    from napkin.core.units import UnitSystem
    from napkin.model.library import load_library
    from napkin.model.model import build_model

    entry = Path(entry).resolve()
    _, files, symbols, kinds_ = model_of(entry)
    units = UnitSystem(load_library(entry)['units'])
    numbers, texts = collections.Counter(), collections.Counter()

    def say(text):
        if isinstance(text, str) and text:
            texts[' '.join(text.split())] += 1

    def count(tree, unit=None):
        from exprs import numbers_of

        for value, spelled in numbers_of(tree, unit):
            try:
                found = units.parse_unit(spelled) if spelled else None
            except Exception:  # a unit that names a text value in braces: compared by its spelling
                numbers[(str(value), json.dumps(spelled))] += 1
                continue
            scale, dims = (found.scale, found.dims) if found is not None else (1, ())
            numbers[number_key(value, scale, dims)] += 1

    for file in files:
        _numbers_and_texts(file, symbols, say, count)
    found_kinds, flows, unestimated = {}, {}, []
    for name, thing in symbols.nodes.items():
        info = symbols.things[name]
        if info.kind == 'instance':
            found_kinds[name] = [f'member of {thing.template}', '']
            continue
        found_kinds[name] = [info.kind, '']
        for member in thing.members:
            if isinstance(member, nodes.Value):
                kind = field_kind(member)
                sort = kinds_.get((name, member.name)) if kind == 'var.number' else KINDS.get(kind, kind)
                if kind == 'let.fixed' and any(
                    isinstance(m, nodes.Change) and m.kind is not None and m.name == member.name
                    for other in symbols.nodes.values()
                    if other.template == name
                    for m in other.members
                ):
                    sort = 'formula'  # an instance gives it a formula, so its template declares one
                found_kinds[f'{name}.{member.name}'] = [sort, _type_of(member, units)]
            elif isinstance(member, (nodes.LinkDecl, nodes.LinkBind)):
                found_kinds[f'{name}.{member.name}'] = ['collection' if member.many else 'link', '']
            elif isinstance(member, nodes.Flow):
                found_kinds[f'{name}.{member.name}'] = ['flow', '']
                pairs = member.together if member.together is not None else [member.pair]
                ends = []
                for pair in pairs:
                    ends.append([_end(pair.source, name, symbols), _end(pair.target, name, symbols, 'SINK')])
                flows[f'{name}.{member.name}'] = sorted(ends)
            elif isinstance(member, nodes.Event):
                found_kinds[f'{name}.{member.name}'] = ['event', '']
            elif isinstance(member, nodes.Output):
                path = f'{name}.{member.name}'
                if member.lines.unestimated is not None:
                    unestimated.append(path)
                else:
                    found_kinds[path] = ['formula', _unit(member.type, units)]
    for file in files:
        for output in file.outputs:
            if output.lines.unestimated is not None:
                unestimated.append(output.name)
            else:
                found_kinds[output.name] = ['formula', _unit(output.type, units)]
    model = build_model(entry)
    proven = {}
    for run in model.runs:
        paths = []
        for name in sorted(model.resolve(run).proven_cumulative_outcomes):
            head, _, member = name.removesuffix('.output').rpartition('.')
            if not head:
                paths.append(member)
            else:
                declarer = symbols.declarer(head)
                paths.append(f'{declarer}.instances.{member}' if declarer != head else f'{head}.{member}')
        proven['' if run == 'base' and len(model.runs) == 1 else run] = sorted(set(paths))
    return {
        'numbers': [[*key, n] for key, n in numbers.items()],
        'texts': dict(texts),
        'kinds': found_kinds,
        'flows': flows,
        'unestimated': sorted(unestimated),
        'proven': proven,
    }


def _unit(spelled, units):
    """The dimension of a unit as the check compares it, or the word of a type that is no unit."""
    if not isinstance(spelled, str):
        return ''
    if spelled == 'bool':
        return 'bool'
    try:
        dims = units.parse_unit(spelled).dims
    except Exception:
        return spelled
    return json.dumps(sorted([str(k), float(v)] for k, v in dims))


def _type_of(value, units):
    """The type of a value as the check compares it: the dimension of its unit, `bool`, `text`, or
    `enum[A, B]` of a named state."""
    kind = field_kind(value)
    if kind in ('input.text',):
        return 'text'
    if kind in ('input.bool', 'var.bool'):
        return 'bool'
    if kind in ('input.named', 'var.named') and isinstance(value.type, list):
        return 'enum[' + ', '.join(v.upper() for v in value.type) + ']'
    return _unit(value.type, units)


def _end(name, thing, symbols, outside='SOURCE'):
    """The path of the store at an end of a flow: the thing that declares it and the member."""
    if name == 'outside':
        return outside
    found = symbols.read(name, thing)
    if found is None or found[0] != 'value':
        return '?' + name
    return f'{symbols.declarer(found[2])}.{found[3]}'


def _numbers_and_texts(file, symbols, say, count):
    """Give every text of a file to `say` and every number, with the unit of its place, to `count`."""
    from exprs import Hand, old_tree

    units = {}  # id of an expression -> the unit that its declaration gives a bare number
    text_values = set()  # ids of the expressions whose one token is a text value, not a named value

    def declare(value):
        unit = value.type if isinstance(value.type, str) and value.type != 'bool' else None
        for part in (
            value.value,
            value.min and value.min.expr,
            value.max and value.max.expr,
            value.size and value.size.expr,
        ):
            if part is not None:
                units[id(part)] = unit

    for thing in [*file.things, *file.changes]:
        for member in thing.members:
            if isinstance(member, nodes.Value):
                declare(member)
                if field_kind(member) == 'input.text':
                    text_values.add(id(member.value))
            elif (
                isinstance(member, nodes.Change)
                and member.lines is not None
                and member.lines.value is not None
            ):
                found = symbols.read(member.name, thing.name)
                if found is not None and found[0] == 'value' and found[1] == 'input.text':
                    text_values.add(id(member.lines.value))
            elif isinstance(member, nodes.Event):
                for outcome in member.outcomes:
                    for line in outcome.lines:
                        if isinstance(line, nodes.Assign):
                            found = symbols.read(line.target, thing.name)
                            if found is not None and found[0] == 'value' and found[1] == 'input.text':
                                text_values.add(id(line.value))
            elif isinstance(member, nodes.Output) and member.expr is not None:
                units[id(member.expr)] = member.type
    for output in file.outputs:
        if output.expr is not None:
            units[id(output.expr)] = output.type
    for group in file.profiles:
        say(group.name)
        for option in group.profiles:
            say(option.name)
            for setting in option.settings:
                found = symbols.read(setting.target, None)
                if found is not None and found[0] == 'value' and found[1] == 'input.text':
                    text_values.add(id(setting.value))
    for run in file.runs:
        for name in run.profiles:
            say(name)
    seen = set()

    def walk(node):
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, nodes.Text):
            for value in node.value if isinstance(node.value, list) else [node.value]:
                say(value)
            return
        if isinstance(node, nodes.Lag):
            return  # a caller selects a lag now (D10)
        if isinstance(node, nodes.Record):
            say(node.text)
        if isinstance(node, nodes.Expr):
            if id(node) in text_values:
                say(node.tokens[0].value)
                return
            try:
                tree = old_tree(node)
            except Hand:
                return
            count(tree, units.get(id(node)))
            return
        if isinstance(node, nodes.Note) and isinstance(node.value, lex.Token) and node.value.kind == 'number':
            count(('num', str(node.value.value), None))
        if dataclasses.is_dataclass(node) and not isinstance(node, type):
            for item in dataclasses.fields(node):
                value = getattr(node, item.name)
                if item.name != 'place' and not isinstance(value, dict):
                    walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(file)


__all__ = [
    'BASE',
    'Symbols',
    'ast',
    'context_files',
    'entry_files',
    'expressions',
    'field_kind',
    'home_entry',
    'lex',
    'model_files',
    'model_of',
    'modules',
    'nodes',
    'parse',
    'parse_file',
    'quantity_kinds',
    'relink',
    'symbols_for',
    'tree_of',
    'written',
]


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    json.dump(facts(sys.argv[1]), sys.stdout)
