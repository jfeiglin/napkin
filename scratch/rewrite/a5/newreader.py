"""A simple reader of the new notation, for `check.py`. It is no compiler: it reads the lines of a
translated file into the facts that the check compares (`Facts`), and it reads only the forms that
the translations of A5 write. A line that it does not know is kept in `Facts.unread`, and the check
reports it.

The forms it reads (the specification gives most of them; `PROPOSED` marks those of A5):

    scenario "Title" / variant "Title", with summary, horizon, scope, library, timescales, resolution
    use NAME
    name: / Name: / name: Template [from "file.csv"]       a thing, a template, an instance
    [readonly] [input] name[: type] = value [in [lo, hi]] [scale S]  @record
    name: Template / name: <Template>                       a link that each instance binds
    flow name: A -> B   with request = ..., capacity = ... or legs (`flow leg: A -> B`) under it
    outflow.capacity = ... / outflow.allocation = ...        under a store
    name = event(params):   with locals, `when C:` triggers, `after D [when C]:` stages, `until C`
    switch VALUE:  with `MEMBER:` cases                      in a stage
    status rating [when C]
    assert C
    options "Group": / "Option": / path = value  @record
    runs: / name = "Option" + "Option"
    report: / path [cumulative] [lag D]                      PROPOSED
    notes: (any keys)
    record name: kind "explanation", with `assumption ID` / `convention ID` and `claims:` under it
    @name, and @kind "explanation" in place
    title, role, sees, about, category, scope               kept lines
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field

import exprs
from exprs import NewSyntax, parse_new, tokens_of

INDENT = 4
RATINGS = ('ok', 'degraded', 'failed', 'inactive')
RECORD_KINDS = ('source', 'source_transfer', 'assumption', 'identity', 'convention')


@dataclass
class Line:
    number: int
    depth: int
    text: str
    tokens: list = field(default_factory=list)
    under: list = field(default_factory=list)


def logical_lines(text):
    """The logical lines of a file in the new notation: a line goes on while a bracket or a text is
    open. A comment starts with `#` outside a text. Each level of nesting is four spaces."""
    rows = text.split('\n')
    out = []
    k = 0
    while k < len(rows):
        row = rows[k]
        stripped = row.strip()
        if not stripped or stripped.startswith('#'):
            k += 1
            continue
        spaces = len(row) - len(row.lstrip(' '))
        number = k + 1
        pieces = []
        depth, quoted = 0, False
        while True:
            row = rows[k]
            piece = []
            i = 0
            while i < len(row):
                ch = row[i]
                if quoted:
                    piece.append(ch)
                    if ch == '\\' and i + 1 < len(row):
                        piece.append(row[i + 1])
                        i += 2
                        continue
                    if ch == '"':
                        quoted = False
                elif ch == '"':
                    quoted = True
                    piece.append(ch)
                elif ch == '#':
                    break
                else:
                    if ch in '([':
                        depth += 1
                    elif ch in ')]':
                        depth -= 1
                    piece.append(ch)
                i += 1
            pieces.append(''.join(piece).strip())
            k += 1
            if (depth > 0 or quoted) and k < len(rows):
                continue
            break
        out.append(Line(number, spaces // INDENT, ' '.join(piece for piece in pieces if piece)))
    return out


def tree(lines):
    top, stack = [], []
    for line in lines:
        while stack and stack[-1].depth >= line.depth:
            stack.pop()
        (stack[-1].under if stack else top).append(line)
        stack.append(line)
    return top


# ---- the facts of a model -------------------------------------------------------------------------------


@dataclass
class Value:
    """A declared value of a thing, or of the top level (thing None)."""

    thing: str | None
    name: str
    kind: str  # input.number, input.bool, input.text, input.named, let.fixed, let.formula, var.named,
    # var.bool, var.number, link, none
    unit: str | None = None  # the unit of its type, as written
    members: tuple = ()  # the members of an enum
    expr: object = None  # its value, default or start
    range: tuple | None = None
    scale: object = None
    line: int = 0
    records: tuple = ()  # the names that it cites
    text: str | None = None
    target: object = None  # of a link: the template or the things


@dataclass
class Flow:
    thing: str
    name: str
    legs: list = field(default_factory=list)  # (leg name or None, source path, sink path, request tree)
    line: int = 0


@dataclass
class Event:
    thing: str
    name: str
    when: object = None
    once: bool = False
    stages: list = field(default_factory=list)  # (delay tree, guard tree or None, [statements])
    locals: dict = field(default_factory=dict)
    cases: list = field(default_factory=list)  # (label, [statements]) of each case of each switch
    selectors: list = field(default_factory=list)  # the value of each switch
    line: int = 0


@dataclass
class Facts:
    """What the check compares, of an old file or of a new one. Every expression is a tree of the
    new notation (`exprs`)."""

    things: dict = field(default_factory=dict)  # name -> {'template': name or None, 'line': n}
    values: dict = field(default_factory=dict)  # (thing, name) -> Value
    flows: dict = field(default_factory=dict)  # (thing, name) -> Flow
    capacities: dict = field(default_factory=dict)  # (thing, store) -> tree
    allocations: dict = field(default_factory=dict)  # (thing, store) -> tree
    events: dict = field(default_factory=dict)  # (thing, name) -> Event
    statuses: dict = field(default_factory=dict)  # thing -> [(rating, condition tree or None)]
    asserts: dict = field(default_factory=dict)  # thing or None -> [tree]
    sees: dict = field(default_factory=dict)  # thing -> [path]
    instance_lines: dict = field(default_factory=dict)  # (thing, member) -> tree
    options: dict = field(default_factory=dict)  # (group, option) -> {target path: tree}
    runs: dict = field(default_factory=dict)  # name -> [options]
    report: dict = field(default_factory=dict)  # path -> {'cumulative': bool, 'lag': tree or None}
    records: dict = field(default_factory=dict)  # name -> (kind, id, text, [(claim, datum)])
    numbers: collections.Counter = field(default_factory=collections.Counter)  # (value, unit)
    texts: collections.Counter = field(default_factory=collections.Counter)
    notes: list = field(default_factory=list)  # the keys of the notes, in order, with their depth
    scenario: dict = field(default_factory=dict)
    uses: list = field(default_factory=list)
    unread: list = field(default_factory=list)  # (line, why)

    def count(self, tree_, unit=None):
        for value, given in exprs.numbers_of(tree_, unit):
            self.numbers[(value, given)] += 1

    def say(self, text):
        self.texts[normal_text(text)] += 1


BRACED = re.compile(r'\{this\.')


def normal_text(text):
    """A text as the check compares it: its words with one space between them, and a name in braces
    without `this.`."""
    return BRACED.sub('{', ' '.join(text.split()))


# ---- the reader -----------------------------------------------------------------------------------------


def split_top(tokens, test):
    """The index of the first token outside brackets for which `test(tokens, k)` holds, or None."""
    depth = 0
    for k, token in enumerate(tokens):
        if token[0] == 'op' and token[1] in '([':
            depth += 1
        elif token[0] == 'op' and token[1] in ')]':
            depth -= 1
        elif depth == 0 and test(tokens, k):
            return k
    return None


def strip_cites(tokens):
    """(the tokens before the citations that end a line, the names cited)."""
    cut = split_top(tokens, lambda ts, k: ts[k] == ('op', '@'))
    if cut is None:
        return tokens, []
    names = [t[1] for t in tokens[cut:] if t[0] == 'name']
    return tokens[:cut], names


def type_text(tokens):
    out = []
    for token in tokens:
        out.append(token[1] if token[0] != 'num' else token[1] + (' ' + token[2] if token[2] else ''))
    return ''.join(out)


def path_of(tokens):
    """A dotted path of names: `this.water`, `tank.water`, `SOURCE`."""
    parts = []
    for k, token in enumerate(tokens):
        if k % 2 == 0:
            if token[0] != 'name':
                raise NewSyntax(f'{token!r} is no part of a path')
            parts.append(token[1])
        elif token != ('op', '.'):
            raise NewSyntax(f'{token!r} is no part of a path')
    if not parts:
        raise NewSyntax('a path is missing')
    return '.'.join(parts)


class Reader:
    def __init__(self, text, origin='<new>'):
        self.origin = origin
        self.facts = Facts()
        self.lines = logical_lines(text)
        for line in self.lines:
            try:
                line.tokens = tokens_of(line.text)
            except NewSyntax as exc:
                self.facts.unread.append((line.number, str(exc)))
                line.tokens = []
        self.top = tree(self.lines)

    def unread(self, line, why):
        self.facts.unread.append((line.number, f'{why}: {line.text[:80]}'))

    def read(self):
        for line in self.top:
            try:
                self.top_line(line)
            except NewSyntax as exc:
                self.unread(line, str(exc))
        return self.facts

    # ---- the top level ---------------------------------------------------------------------------------

    def top_line(self, line):
        tokens = line.tokens
        if not tokens:
            return
        first = tokens[0]
        word = first[1] if first[0] == 'name' else None
        second = tokens[1] if len(tokens) > 1 else None
        f = self.facts
        if word in ('scenario', 'variant') and second is not None and second[0] == 'text':
            f.scenario['role'] = word
            f.scenario['title'] = second[1]
            f.say(second[1])
            for child in line.under:
                self.scenario_line(child)
        elif word == 'use' and second is not None and second[0] == 'name':
            f.uses.append(path_of(tokens[1:]))
        elif word == 'record' and second is not None and second[0] == 'name':
            self.record(line)
        elif word == 'notes' and second == ('op', ':'):
            self.notes(line.under, 1)
        elif word == 'options' and second is not None and second[0] == 'text':
            self.options(line)
        elif word == 'runs' and second == ('op', ':'):
            self.runs(line)
        elif word == 'report' and second == ('op', ':'):
            self.report(line)
        elif word == 'assert':
            self.assert_(line, None)
        elif word == 'change' and second is not None and second[0] == 'name':
            self.thing(line, tokens[1:])
        elif word is not None and second == ('op', ':') and self.is_thing(line):
            self.thing(line, tokens)
        elif word is not None:
            self.declaration(line, None)
        else:
            self.unread(line, 'a line at the top level')

    def is_thing(self, line):
        """Whether `name: …` at the top level opens a thing: nothing after the colon but a template, a
        table and citations. A declaration has `=`."""
        tokens, _ = strip_cites(line.tokens)
        rest = tokens[2:]
        if split_top(rest, lambda ts, k: ts[k] == ('op', '=')) is not None:
            return False
        if not rest:
            return True
        return rest[0][0] == 'name' and rest[0][1][:1].isupper() and (
            len(rest) == 1 or rest[1] == ('name', 'from')
        )

    def scenario_line(self, line):
        tokens = line.tokens
        key = tokens[0][1]
        f = self.facts
        if key in ('summary', 'scope', 'library') and len(tokens) == 2 and tokens[1][0] == 'text':
            f.scenario[key] = tokens[1][1]
            f.say(tokens[1][1])
        elif key in ('horizon', 'resolution'):
            f.scenario[key] = parse_new(tokens[1:])
            f.count(f.scenario[key])
        elif key == 'timescales':
            parts, current, depth = [], [], 0
            for token in tokens[1:]:
                if token[0] == 'op' and token[1] in '([':
                    depth += 1
                elif token[0] == 'op' and token[1] in ')]':
                    depth -= 1
                if depth == 0 and token == ('op', ','):
                    parts.append(current)
                    current = []
                else:
                    current.append(token)
            parts.append(current)
            f.scenario[key] = [parse_new(part) for part in parts if part]
            for item in f.scenario[key]:
                f.count(item)
        else:
            self.unread(line, 'a line of the scenario line')

    # ---- evidence and texts ----------------------------------------------------------------------------

    def evidence(self, line, holder=None):
        """A line that starts with `@`: citations, or a record in place with its lines."""
        tokens = line.tokens
        f = self.facts
        if len(tokens) >= 3 and tokens[1][0] == 'name' and tokens[1][1] in RECORD_KINDS and tokens[2][0] == 'text':
            f.say(tokens[2][1])
            claims = self.record_lines(line)
            if holder is not None:
                holder.setdefault('in_place', []).append((tokens[1][1], claims[0], tokens[2][1], claims[1]))
            return
        names = [t[1] for t in tokens if t[0] == 'name']
        if holder is not None:
            holder.setdefault('cites', []).extend(names)

    def record_lines(self, line):
        """(the ID, [(claim, datum)]) of the lines under a record."""
        identifier, claims = None, []
        for child in line.under:
            tokens = child.tokens
            word = tokens[0][1] if tokens and tokens[0][0] == 'name' else None
            if word in ('assumption', 'convention') and len(tokens) > 1 and tokens[1] != ('op', ':'):
                identifier = type_text(tokens[1:])
            elif word == 'claims':
                for item in child.under:
                    datum = None
                    for sub in item.under:
                        if sub.tokens and sub.tokens[0] == ('name', 'datum'):
                            datum = type_text(sub.tokens[2:])
                    claims.append((type_text(item.tokens), datum))
            else:
                self.unread(child, 'a line under a record')
        return identifier, claims

    def record(self, line):
        tokens = line.tokens
        if len(tokens) < 5 or tokens[2] != ('op', ':') or tokens[3][0] != 'name' or tokens[-1][0] != 'text':
            self.unread(line, 'a record')
            return
        name, kind, text = tokens[1][1], tokens[3][1], tokens[-1][1]
        identifier = type_text(tokens[4:-1]) or None
        self.facts.say(text)
        under_id, claims = self.record_lines(line)
        self.facts.records[name] = (kind, identifier or under_id, normal_text(text), claims)

    def common(self, line, holder):
        """A line that can stand under any declaration: its text, its evidence, or a kept line
        (`about`, `category`, `scope`, `title`, `role`). True when the line is read."""
        tokens = line.tokens
        if not tokens:
            return True
        first = tokens[0]
        f = self.facts
        if first[0] == 'text' and len(tokens) == 1:
            f.say(first[1])
            holder.setdefault('texts', []).append(first[1])
            return True
        if first == ('op', '['):
            # A list of texts: one for each time.
            for token in tokens:
                if token[0] == 'text':
                    f.say(token[1])
            return True
        if first == ('op', '@'):
            self.evidence(line, holder)
            return True
        word = first[1] if first[0] == 'name' else None
        if word in ('about', 'scope', 'title') and len(tokens) == 2 and tokens[1][0] == 'text':
            f.say(tokens[1][1])
            holder[word] = tokens[1][1]
            return True
        if word in ('category', 'role') and len(tokens) == 2 and tokens[1][0] == 'name':
            holder[word] = tokens[1][1]
            return True
        return False

    # ---- things -----------------------------------------------------------------------------------------

    def thing(self, line, tokens):
        tokens, cites = strip_cites(tokens)
        name = tokens[0][1]
        rest = tokens[2:]
        template = rest[0][1] if rest else None
        if len(rest) >= 3 and rest[1] == ('name', 'from') and rest[2][0] == 'text':
            self.facts.say(rest[2][1])
        info = self.facts.things.setdefault(name, {'template': template, 'line': line.number, 'cites': cites})
        for child in line.under:
            try:
                self.member(child, name, info)
            except NewSyntax as exc:
                self.unread(child, str(exc))

    def member(self, line, thing, info):
        tokens = line.tokens
        if not tokens:
            return
        first = tokens[0]
        word = first[1] if first[0] == 'name' else None
        f = self.facts
        if self.common(line, info):
            return
        if word == 'sees':
            parts, current = [], []
            for token in tokens[1:]:
                if token == ('op', ','):
                    parts.append(current)
                    current = []
                else:
                    current.append(token)
            parts.append(current)
            f.sees[thing] = [path_of(part) for part in parts if part]
        elif word == 'status' and len(tokens) > 1 and tokens[1][0] == 'name' and tokens[1][1] in RATINGS:
            body, cites = strip_cites(tokens[2:])
            condition = None
            if body:
                if body[0] != ('name', 'when'):
                    raise NewSyntax('status rating [when C]')
                condition = parse_new(body[1:])
                f.count(condition)
            f.statuses.setdefault(thing, []).append((tokens[1][1], condition))
            holder = {}
            for child in line.under:
                if not self.common(child, holder):
                    self.unread(child, 'a line under a status')
        elif word == 'flow':
            self.flow(line, thing)
        elif word == 'assert':
            self.assert_(line, thing)
        else:
            self.declaration(line, thing)

    def assert_(self, line, thing):
        body, _ = strip_cites(line.tokens[1:])
        condition = parse_new(body)
        self.facts.count(condition)
        self.facts.asserts.setdefault(thing, []).append(condition)
        holder = {}
        for child in line.under:
            if not self.common(child, holder):
                self.unread(child, 'a line under an assert')

    # ---- declarations ----------------------------------------------------------------------------------

    def declaration(self, line, thing):
        tokens, cites = strip_cites(line.tokens)
        f = self.facts
        k = 0
        readonly = is_input = False
        while k < len(tokens) and tokens[k][0] == 'name' and tokens[k][1] in ('readonly', 'input'):
            readonly = readonly or tokens[k][1] == 'readonly'
            is_input = is_input or tokens[k][1] == 'input'
            k += 1
        if k >= len(tokens) or tokens[k][0] != 'name':
            raise NewSyntax('a declaration starts with a name')
        name = tokens[k][1]
        rest = tokens[k + 1 :]
        equals = split_top(rest, lambda ts, i: ts[i] == ('op', '='))
        head = rest if equals is None else rest[:equals]
        body = [] if equals is None else rest[equals + 1 :]
        written = None
        if head:
            if head[0] != ('op', ':'):
                raise NewSyntax(f'{name}: a declaration is `name[: type] = value`')
            written = type_text(head[1:])
        # An event: `name = event(params):`.
        if body and body[0] == ('name', 'event') and body[-1] == ('op', ':'):
            self.event(line, thing, name, body)
            return
        if body and body[0] == ('name', 'solver'):
            self.unread(line, 'a solver (the check of A5 reads none)')
            return
        # The value, then `in [lo, hi]`, then `scale S`.
        cut_scale = split_top(body, lambda ts, i: ts[i] == ('name', 'scale'))
        scale = None
        if cut_scale is not None:
            scale = parse_new(body[cut_scale + 1 :])
            body = body[:cut_scale]
        cut_in = split_top(body, lambda ts, i: ts[i] == ('name', 'in') and i + 1 < len(ts) and ts[i + 1] == ('op', '['))
        bounds = None
        if cut_in is not None:
            bounds = self.bounds(body[cut_in:])
            body = body[:cut_in]
        expr = parse_new(body) if body else None
        value = Value(thing, name, '?', line=line.number, records=tuple(cites), expr=expr, scale=scale)
        holder = {}
        props = {}
        for child in line.under:
            ctoks = child.tokens
            if self.common(child, holder):
                continue
            if ctoks and ctoks[0] == ('name', 'in') and len(ctoks) > 1 and ctoks[1] == ('op', '['):
                inner, _ = strip_cites(ctoks)
                bounds = self.bounds(inner)
                for sub in child.under:
                    self.common(sub, holder)
                continue
            if ctoks and ctoks[0][0] == 'name' and ctoks[0][1] in ('outflow', 'inflow'):
                inner, _ = strip_cites(ctoks)
                eq = split_top(inner, lambda ts, i: ts[i] == ('op', '='))
                if eq is None:
                    raise NewSyntax('an endpoint property is `outflow.capacity = value`')
                key = path_of(inner[:eq])
                props[key] = parse_new(inner[eq + 1 :])
                f.count(props[key])
                sub_holder = {}
                for sub in child.under:
                    if not self.common(sub, sub_holder):
                        self.unread(sub, 'a line under an endpoint property')
                continue
            if ctoks and ctoks[0] == ('name', 'unestimated') and len(ctoks) == 2 and ctoks[1][0] == 'text':
                f.say(ctoks[1][1])
                continue
            self.unread(child, f'a line under the declaration of {name}')
        value.range = bounds
        value.text = (holder.get('texts') or [None])[0]
        value.records = tuple(cites) + tuple(holder.get('cites', ()))
        self.classify(value, written, readonly, is_input, body, equals is not None)
        if expr is not None and expr[0] == 'text':
            f.say(expr[1])
        # An instance line: `m = v` in an instance of a template sets a member, and declares none.
        template = f.things.get(thing, {}).get('template') if thing is not None else None
        if template is not None and written is None and not readonly and not is_input:
            f.instance_lines[(thing, name)] = expr
            if expr is not None:
                f.count(expr)
            for key, tree_ in props.items():
                self.endpoint(thing, name, key, tree_)
            return
        if template is not None and equals is None and written is None:
            return  # `m:` with new text or records
        f.values[(thing, name)] = value
        unit = value.unit
        if expr is not None:
            f.count(expr, unit)
        if bounds is not None:
            f.count(bounds[0], unit)
            f.count(bounds[1], unit)
        if scale is not None:
            f.count(scale, unit)
        for key, tree_ in props.items():
            self.endpoint(thing, name, key, tree_)

    def endpoint(self, thing, name, key, tree_):
        if key == 'outflow.capacity':
            self.facts.capacities[(thing, name)] = tree_
        elif key == 'outflow.allocation':
            self.facts.allocations[(thing, name)] = tree_
        else:
            self.facts.unread.append((0, f'the endpoint property {key} of {thing}.{name}'))

    def bounds(self, tokens):
        if len(tokens) < 5 or tokens[0] != ('name', 'in') or tokens[1] != ('op', '[') or tokens[-1] != ('op', ']'):
            raise NewSyntax('a range is `in [low, high]`')
        inner = tokens[2:-1]
        comma = split_top(inner, lambda ts, i: ts[i] == ('op', ','))
        if comma is None:
            raise NewSyntax('a range is `in [low, high]`')
        return parse_new(inner[:comma]), parse_new(inner[comma + 1 :])

    def classify(self, value, written, readonly, is_input, body, has_value):
        """The kind of a declaration, in the words of the old language, so that the check can compare
        the two."""
        expr = value.expr
        formula_type = None
        if written is not None and written.startswith('formula(') and written.endswith(')'):
            formula_type = written[len('formula(') : -1]
        is_formula = expr is not None and expr[0] == 'call' and expr[1] == 'formula'
        if is_formula:
            value.expr = expr[2][0]
        enum = written is not None and written.startswith('enum[')
        if enum:
            value.members = tuple(part.strip() for part in written[len('enum[') : -1].split(','))
        is_text = expr is not None and expr[0] == 'text'
        is_bool = written == 'bool' or formula_type == 'bool' or (
            expr is not None and expr[0] == 'name' and expr[1] in ('true', 'false')
        )
        collection = written is not None and written.startswith('<')
        template_type = written is not None and written[:1].isupper() and written.isidentifier()
        if not has_value and (collection or template_type):
            value.kind = 'link'
            value.target = written
            return
        if expr is not None and (
            expr[0] == 'coll'
            or (expr[0] == 'name' and expr[1].endswith('.instances'))
            or (expr[0] == 'method' and expr[2] in ('where', 'by'))
        ):
            value.kind = 'link'
            value.target = expr
            return
        if expr is not None and expr[0] == 'none':
            value.kind = 'none'
            value.unit = written
            return
        if is_input:
            if is_text:
                value.kind = 'input.text'
            elif enum:
                value.kind = 'input.named'
            elif is_bool:
                value.kind = 'input.bool'
            else:
                value.kind = 'input.number'
                value.unit = written
            return
        if is_formula or formula_type is not None:
            value.kind = 'let.formula'
            value.unit = formula_type
            return
        if readonly:
            value.kind = 'let.fixed'
            value.unit = written
            return
        if enum:
            value.kind = 'var.named'
        elif is_bool:
            value.kind = 'var.bool'
        elif is_text:
            value.kind = 'input.text'
        elif has_value and value.thing is not None and written is None and expr is not None and expr[0] == 'name' and '.' not in expr[1]:
            # `x = other`: a link that an entity binds to one thing.
            value.kind = 'link'
            value.target = expr
        else:
            value.kind = 'var.number'
            value.unit = written

    # ---- flows -----------------------------------------------------------------------------------------

    def flow(self, line, thing, parent=None):
        tokens, cites = strip_cites(line.tokens)
        name = tokens[1][1]
        if tokens[2] != ('op', ':'):
            raise NewSyntax('a flow is `flow name: A -> B`')
        rest = tokens[3:]
        f = self.facts
        flow = parent if parent is not None else Flow(thing, name, line=line.number)
        holder = {}
        if not rest:
            # A flow with legs.
            for child in line.under:
                if self.common(child, holder):
                    continue
                if child.tokens and child.tokens[0] == ('name', 'flow'):
                    self.flow(child, thing, flow)
                else:
                    self.unread(child, 'a line under a flow with legs')
            f.flows[(thing, name)] = flow
            return
        arrow = split_top(rest, lambda ts, i: ts[i][0] == 'op' and ts[i][1] in ('->', '<->'))
        if arrow is None:
            raise NewSyntax('a flow is `flow name: A -> B`')
        source, sink = path_of(rest[:arrow]), path_of(rest[arrow + 1 :])
        request = capacity = None
        for child in line.under:
            if self.common(child, holder):
                continue
            ctoks, _ = strip_cites(child.tokens)
            if len(ctoks) > 2 and ctoks[0][0] == 'name' and ctoks[0][1] in ('request', 'capacity') and ctoks[1] == ('op', '='):
                tree_ = parse_new(ctoks[2:])
                f.count(tree_)
                if tree_[0] == 'call' and tree_[1] == 'formula':
                    tree_ = tree_[2][0]
                if ctoks[0][1] == 'request':
                    request = tree_
                else:
                    capacity = tree_
            else:
                self.unread(child, 'a line under a flow')
        flow.legs.append((name if parent is not None else None, source, sink, request, capacity))
        if parent is None:
            f.flows[(thing, name)] = flow

    # ---- events -----------------------------------------------------------------------------------------

    def event(self, line, thing, name, body):
        f = self.facts
        event = Event(thing, name, line=line.number)
        holder = {}
        for child in line.under:
            tokens = child.tokens
            if self.common(child, holder):
                continue
            word = tokens[0][1] if tokens and tokens[0][0] == 'name' else None
            if word == 'when' and tokens[-1] == ('op', ':'):
                condition = parse_new(strip_cites(tokens[1:])[0][:-1] if tokens[-1] == ('op', ':') else tokens[1:-1])
                f.count(condition)
                event.when = condition if event.when is None else ('bool', 'or', [event.when, condition])
                for sub in child.under:
                    stoks = sub.tokens
                    if stoks[:2] == [('name', 'reset'), ('name', 'when')]:
                        reset = parse_new(stoks[2:])
                        if reset == ('name', 'false'):
                            event.once = True
                        else:
                            event.locals.setdefault('__reset__', []).append(reset)
                    elif stoks[:2] == [('name', 'reset'), ('name', 'after')]:
                        tree_ = parse_new(stoks[2:])
                        f.count(tree_)
                        event.locals.setdefault('__reset__', []).append(('call', 'after', [tree_]))
                    else:
                        self.statement(sub, event, None)
            elif word == 'after' and tokens[-1] == ('op', ':'):
                inner = tokens[1:-1]
                guard = None
                cut = split_top(inner, lambda ts, i: ts[i] == ('name', 'when'))
                if cut is not None:
                    guard = parse_new(inner[cut + 1 :])
                    f.count(guard)
                    inner = inner[:cut]
                delay = parse_new(inner)
                f.count(delay)
                statements = []
                for sub in child.under:
                    self.statement(sub, event, statements)
                event.stages.append((delay, guard, statements))
            elif word == 'until':
                tree_ = parse_new(tokens[1:])
                f.count(tree_)
                event.stages.append((('call', 'until', [tree_]), None, []))
            elif word == 'flow':
                self.flow(child, thing)
            elif word is not None and len(tokens) > 1 and tokens[1] in (('op', ':'), ('op', '=')):
                # A local of the occurrence.
                toks, _ = strip_cites(tokens)
                eq = split_top(toks, lambda ts, i: ts[i] == ('op', '='))
                event.locals[word] = type_text(toks[2:eq]) if toks[1] == ('op', ':') else None
                if eq is not None:
                    tree_ = parse_new(toks[eq + 1 :])
                    f.count(tree_)
            else:
                self.unread(child, f'a line of the event {name}')
        f.events[(thing, name)] = event

    def statement(self, line, event, out):
        """A line of a stage or of a trigger: an assignment, a move, a start, or a `switch`."""
        tokens = line.tokens
        f = self.facts
        if not tokens:
            return
        word = tokens[0][1] if tokens[0][0] == 'name' else None
        if word == 'switch' and tokens[-1] == ('op', ':'):
            selector = parse_new(tokens[1:-1])
            f.count(selector)
            event.selectors.append(selector)
            for case in line.under:
                ctoks, _ = strip_cites(case.tokens)
                if len(ctoks) < 2 or ctoks[-1] != ('op', ':') or ctoks[0][0] != 'name':
                    self.unread(case, 'a case of a switch')
                    continue
                statements = []
                holder = {}
                for sub in case.under:
                    if self.common(sub, holder):
                        continue
                    self.statement(sub, event, statements)
                event.cases.append((ctoks[0][1], statements))
            return
        if word == 'move':
            cut_from = split_top(tokens, lambda ts, i: ts[i] == ('name', 'from'))
            cut_to = split_top(tokens, lambda ts, i: ts[i] == ('name', 'to'))
            if cut_from is None or cut_to is None:
                raise NewSyntax('move A from S to D')
            amount = parse_new(tokens[1:cut_from])
            f.count(amount)
            statement = ('move', amount, path_of(tokens[cut_from + 1 : cut_to]), path_of(tokens[cut_to + 1 :]))
        else:
            assign = split_top(tokens, lambda ts, i: ts[i][0] == 'op' and ts[i][1] in ('=', '+=', '-='))
            if assign is not None:
                value = parse_new(tokens[assign + 1 :])
                f.count(value)
                if value[0] == 'text':
                    f.say(value[1])
                statement = ('set', tokens[assign][1], path_of(tokens[:assign]), value)
            else:
                call = parse_new(tokens)
                f.count(call)
                if call[0] == 'method' and call[2] == 'start':
                    statement = ('start', exprs.show(call[1]), call[3])
                else:
                    raise NewSyntax('a line of a stage sets a value, moves an amount or starts an event')
        if out is not None:
            out.append(statement)
        else:
            event.locals.setdefault('__trigger__', []).append(statement)

    # ---- options, runs, report, notes -------------------------------------------------------------------

    def options(self, line):
        f = self.facts
        group = line.tokens[1][1]
        f.say(group)
        for option in line.under:
            if not option.tokens or option.tokens[0][0] != 'text':
                self.unread(option, 'an option')
                continue
            name = option.tokens[0][1]
            f.say(name)
            settings = f.options.setdefault((group, name), {})
            holder = {}
            for child in option.under:
                if self.common(child, holder):
                    continue
                tokens, _ = strip_cites(child.tokens)
                eq = split_top(tokens, lambda ts, i: ts[i] == ('op', '='))
                if eq is None:
                    self.unread(child, 'a line of an option')
                    continue
                value = parse_new(tokens[eq + 1 :])
                f.count(value)
                if value[0] == 'text':
                    f.say(value[1])
                settings[path_of(tokens[:eq])] = value
                sub_holder = {}
                for sub in child.under:
                    if not self.common(sub, sub_holder):
                        self.unread(sub, 'a line under a line of an option')

    def runs(self, line):
        f = self.facts
        for run in line.under:
            tokens = run.tokens
            if len(tokens) < 3 or tokens[1] != ('op', '='):
                self.unread(run, 'a run')
                continue
            names = [t[1] for t in tokens[2:] if t[0] == 'text']
            extra = [t for t in tokens[2:] if t[0] != 'text' and t != ('op', '+')]
            if extra:
                self.unread(run, 'a run names its options, joined by +')
            for name in names:
                f.say(name)
            f.runs[tokens[0][1]] = names
            for child in run.under:
                if child.tokens and child.tokens[0][0] == 'text':
                    f.say(child.tokens[0][1])

    def report(self, line):
        f = self.facts
        for entry in line.under:
            tokens = entry.tokens
            cut = split_top(tokens, lambda ts, i: ts[i][0] == 'name' and ts[i][1] in ('cumulative', 'lag') and i > 0 and ts[i - 1] != ('op', '.'))
            path = path_of(tokens if cut is None else tokens[:cut])
            flags = {'cumulative': False, 'lag': None, 'line': entry.number}
            rest = [] if cut is None else tokens[cut:]
            k = 0
            while k < len(rest):
                if rest[k] == ('name', 'cumulative'):
                    flags['cumulative'] = True
                    k += 1
                elif rest[k] == ('name', 'lag'):
                    flags['lag'] = parse_new(rest[k + 1 :])
                    f.count(flags['lag'])
                    k = len(rest)
                else:
                    raise NewSyntax('an entry of report: is `path [cumulative] [lag D]`')
            f.report[path] = flags

    def notes(self, lines, depth):
        f = self.facts
        for line in lines:
            tokens = line.tokens
            if not tokens:
                continue
            if tokens[0] == ('op', '@'):
                self.evidence(line)
                continue
            colon = split_top(tokens, lambda ts, i: ts[i] == ('op', ':'))
            if colon is None:
                self.unread(line, 'a note is `key: value`')
                continue
            f.notes.append((depth, type_text(tokens[:colon])))
            for token in tokens[colon + 1 :]:
                if token[0] == 'text':
                    f.say(token[1])
                elif token[0] == 'num':
                    f.count(token)
            self.notes(line.under, depth + 1)


def read_new(text, origin='<new>'):
    """The facts of a file in the new notation."""
    return Reader(text, origin).read()
