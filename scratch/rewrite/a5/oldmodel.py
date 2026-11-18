"""What the three scripts of A5 share: where the old models are, and how the old compiler reads them.

Everything here reads a model with the old compiler at the base commit (`napkin.model.language`), and
never with a text pattern over the source. Run each script with the old package on the path:

    PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python <script>.py

`symbols(context)` gives a small table of the names of one model, which the census and the check use to
say what a dotted name reads: a value of a kind, an event, an outcome, a list, a thing.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
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
            head, rest = parts[:cut - 1], parts[cut - 1:]
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
    'modules',
    'nodes',
    'parse',
    'parse_file',
    'relink',
    'symbols_for',
    'tree_of',
    'written',
]
