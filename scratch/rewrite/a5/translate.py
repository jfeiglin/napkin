#!/usr/bin/env python
"""Task 4 of brief A5: translate the mechanical lines of an old model file into the new language.

The old file is read with the old parser. Each logical line of the old file is either translated,
or left for a person: its old text is then written as a comment under a `# TODO(hand): reason` line.
Nothing is read with a text pattern over the source, and every name is resolved with the names of
the model (`oldmodel.Symbols`).

Run:

    PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python translate.py            # every file
    PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python translate.py FILE.scn   # one file

With no file it translates every `.scn` file of `examples/` and `scenarios/` at the base commit into
`translated/auto/`, and prints the share of the lines that it translated, for each file. With
`--stdout` and one file it prints the translation. `--no-events` leaves every event for a person.

What it translates: the scenario line, `use`, things and instances, links, inputs, fixed values,
formulas, named states and number vars with their ranges and sizes, flows of one pair, status lines,
asserts (a sum check becomes an interval), outputs (a named formula and an entry of `report:`),
options, runs, notes, records and their claims, and the events that have one trigger and one set of
lines (a share becomes `outflow.capacity` and `outflow.allocation`). What it leaves: flows with several
pairs, events with outcomes, `versus`,
and whatever needs a decision (`exprs.Hand`).
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

import exprs
import oldmodel
from exprs import Hand, Scope, show
from oldmodel import BASE, lex, nodes

HERE = Path(__file__).resolve().parent
WIDTH = 110
INDENT = '    '


BREAK_BEFORE = (' + ', ' - ', ' * ', ' / ', ' and ', ' or ', ' if ', ' else ', ' == ', ' != ', ' <= ', ' >= ')


def breaks(text):
    """The places where a line can break: (index of the space, rank). Inside a text, any single space
    (rank 1). Inside a bracket, the space after a comma (rank 3) or before an operator (rank 2). A
    number never parts from its unit."""
    found = []
    depth, quoted = 0, False
    k = 0
    while k < len(text):
        ch = text[k]
        if quoted:
            if ch == '\\':
                k += 2
                continue
            if ch == '"':
                quoted = False
            elif ch == ' ' and text[k - 1] != ' ' and k + 1 < len(text) and text[k + 1] != ' ':
                found.append((k, 1))
        elif ch == '"':
            quoted = True
        elif ch in '([':
            depth += 1
        elif ch in ')]':
            depth = max(0, depth - 1)
        elif ch == ' ' and depth > 0:
            if text[k - 1] == ',':
                found.append((k, 3))
            elif any(text.startswith(word, k) for word in BREAK_BEFORE):
                found.append((k, 2))
        k += 1
    return found


def wrap(depth, text, width=WIDTH):
    """One line of the new file at a depth, broken inside its brackets or inside a text when it is
    longer than the width. A continuation is one level deeper."""
    prefix = INDENT * depth
    if len(prefix) + len(text) <= width:
        return [prefix + text]
    deeper = INDENT * (depth + 1)
    places = breaks(text)
    out, start = [], 0
    while True:
        room = width - len(prefix)
        if len(text) - start <= room:
            out.append(prefix + text[start:])
            return out
        limit = start + room
        usable = [item for item in places if start < item[0] <= limit]
        if usable:
            # The last place of the best rank in the last third of the row, else the last place.
            late = [item for item in usable if item[0] - start >= room * 2 // 3]
            cut = max(late, key=lambda item: (item[1], item[0]))[0] if late else usable[-1][0]
        else:
            later = [item for item in places if item[0] > limit]
            if not later:
                out.append(prefix + text[start:])
                return out
            cut = later[0][0]
        out.append(prefix + text[start:cut].rstrip())
        start = cut + 1
        prefix = deeper


class Translator:
    def __init__(self, path, events=True):
        self.path = Path(path)
        self.text = self.path.read_text(encoding='utf-8')
        self.rows = self.text.split('\n')
        self.file, self.files, self.symbols, self.kinds = oldmodel.model_of(self.path)
        flat = lex.lines(self.text)
        self.flat = flat
        lex.tree(flat)
        self.logical = {line.number: line for line in flat if line.kind == 'line'}
        self.state = {}  # logical line number -> 'done' or 'todo'
        self.why = collections.Counter()  # reason -> lines left for a person
        self.proposed = collections.Counter()  # proposed spelling -> lines that use it
        self.out = []  # (old line, sequence, text)
        self.sequence = 0
        self.anchor = None  # where the next lines go, when they move under another declaration
        self.events = events
        self.report = []  # (old line, text of the entry)
        self.comparisons = []
        self.output_names = {o.name for file in self.files for o in file.outputs}
        self.formula_overrides = self._formula_overrides()

    # ---- bookkeeping ---------------------------------------------------------------------------------

    def emit(self, line, depth, text, raw=False):
        rows = [INDENT * depth + text] if raw else wrap(depth, text)
        where = self.anchor if self.anchor is not None else line
        for row in rows:
            self.sequence += 1
            self.out.append((where, self.sequence, row))

    def end_of(self, number):
        """The last line of the old file that the declaration at `number` holds."""
        return self.logical[self.block(number)[-1]].end

    def emit_after(self, number, depth, text):
        """A line that comes after every line under the declaration at `number`."""
        where = self.anchor if self.anchor is not None else self.end_of(number) + 0.25
        for row in wrap(depth, text):
            self.sequence += 1
            self.out.append((where, self.sequence, row))

    def verbatim(self, number, depth=None):
        """Copy one logical line of the old file as it is written (its syntax does not change). With
        `depth`, the line moves to that depth: a line that goes under another declaration."""
        line = self.logical[number]
        where = self.anchor if self.anchor is not None else line.number
        shift = None if depth is None else (depth - line.depth) * len(INDENT)
        for k in range(line.number, line.end + 1):
            row = self.rows[k - 1].rstrip()
            if shift and row.strip():
                row = (' ' * shift + row) if shift > 0 else row[-shift:]
            self.sequence += 1
            self.out.append((where, self.sequence, row))
        self.state[number] = 'done'

    def block(self, number):
        """The numbers of a logical line and of every logical line under it."""
        line = self.logical[number]
        found = [number]
        for child in line.under:
            found += self.block(child.number)
        return found

    def done(self, number):
        self.state[number] = 'done'

    def done_block(self, number):
        for k in self.block(number):
            self.state[k] = 'done'

    def hand(self, number, depth, reason, draft=None):
        """Leave the block of a logical line for a person: a `# TODO(hand)` line, the old text as
        comments, and a draft when the script has one."""
        numbers = self.block(number)
        for k in numbers:
            self.state[k] = 'todo'
        self.why[reason.split(':')[0]] += len(numbers)
        self.emit(number, depth, f'# TODO(hand): {reason}', raw=True)
        last = self.logical[numbers[-1]].end
        for k in range(number, last + 1):
            row = self.rows[k - 1]
            self.emit(number, depth, ('# | ' + row[len(INDENT) * depth :]) if row.strip() else '# |', raw=True)
        for row in draft or ():
            self.emit(number, depth, '# draft: ' + row, raw=True)

    def children(self, number):
        return self.logical[number].under

    # ---- small parts ---------------------------------------------------------------------------------

    def cites(self, support):
        """The citations that end a line: `  @a @b`."""
        names = [item.name for item in support if isinstance(item, nodes.Cite) and self.on_line(item)]
        return ('  ' + ' '.join('@' + name for name in names)) if names else ''

    def on_line(self, cite):
        """Whether a citation ends its line: its place is the place of the line, with no `@` part."""
        return oldmodel_evidence_place(cite.place) is None

    def under(self, number, depth, support=(), text=None, braces_thing=None, extra=None):
        """The lines under a declaration that keep their form: its text, its citations on lines of
        their own and its records in place. `extra(child)` translates another line and returns True."""
        placed = {}
        for item in support:
            where = oldmodel_evidence_place(item.place)
            if where is not None:
                placed.setdefault(item.line, []).append(item)
        for child in self.children(number):
            if child.number in self.state:
                continue
            first = child.first
            if first.kind == 'text' or (first.is_op('[') and text is not None and child.number == text.line):
                self.text_line(child.number, depth, braces_thing)
            elif first.kind == 'at':
                items = placed.get(child.number, [])
                records = [item for item in items if isinstance(item, nodes.Record)]
                if records:
                    self.record_in_place(child.number, depth, records[0])
                else:
                    self.verbatim(child.number, depth if depth != child.depth else None)
            elif extra is not None and extra(child):
                continue
            else:
                self.hand(child.number, depth, 'a line that this script does not place')

    def text_line(self, number, depth, thing=None):
        """A text keeps its words. A name in braces is written as an expression writes it."""
        line = self.logical[number]
        token = line.first
        if thing is not None and token.kind == 'text' and '{' in token.value:
            from napkin.model.language.resolve import BRACES

            scope = Scope(self.symbols, thing)

            def named(match):
                try:
                    return '{' + scope.path(match.group(1))[0] + '}'
                except Hand:
                    return match.group(0)

            new = BRACES.sub(named, token.value)
            self.emit(number, depth, '"' + new + '"')
            self.proposed['braces in a text name a path'] += 1
            self.done(number)
            return
        self.verbatim(number, depth if depth != line.depth else None)

    def record_in_place(self, number, depth, record):
        """`@kind [ID] "explanation"` with its claims. The ID moves to a line of its own, which says what
        it names (the candidate of the specification)."""
        moved = depth - self.logical[number].depth
        if record.id is None:
            for k in self.block(number):
                self.verbatim(k, self.logical[k].depth + moved if moved else None)
            return
        self.emit(number, depth, f'@{record.kind} "{record.text}"')
        self.done(number)
        self.emit(number, depth + 1, f'{id_label(record.kind)} {record.id}')
        for child in self.children(number):
            for k in self.block(child.number):
                self.verbatim(k, self.logical[k].depth + moved if moved else None)

    def expr(self, expr, thing, draws=True, own='this.'):
        scope = Scope(self.symbols, thing, self.output_names, own=own)
        return show(exprs.rewrite_old(expr, scope, draws))

    # ---- the file ---------------------------------------------------------------------------------------

    def translate(self):
        file = self.file
        if file.scenario is not None:
            self.scenario(file.scenario)
        for use in file.uses:
            self.verbatim(use.line)
        top = []
        top += [('thing', item) for item in file.things]
        top += [('change', item) for item in file.changes]
        top += [('check', item) for item in file.checks]
        top += [('output', item) for item in file.outputs]
        top += [('options', item) for item in file.profiles]
        top += [('record', item) for item in file.records]
        top.sort(key=lambda pair: pair[1].line)
        for kind, item in top:
            getattr(self, kind)(item)
        if file.runs_place is not None:
            self.runs()
        if file.notes is not None:
            self.notes()
        self.report_block()
        return self.result()

    def scenario(self, block):
        number = block.line
        self.verbatim(number)
        for child in self.children(number):
            key = child.first.value
            if key in ('summary', 'scope', 'library', 'horizon'):
                self.verbatim(child.number)
            elif key == 'timescales':
                parts = [self.expr(item, None, draws=False) for item in block.timescales]
                self.emit(child.number, 1, 'timescales ' + ', '.join(parts))
                self.done_block(child.number)
                self.proposed['timescales kept as a hint'] += 1
            elif key == 'resolution':
                self.verbatim(child.number)
                self.proposed['resolution kept as a hint'] += 1
            else:
                self.hand(child.number, 1, 'a line of the scenario line')

    # ---- things -----------------------------------------------------------------------------------------

    def thing(self, thing, change=False):
        number = thing.line
        name = thing.name
        instance = thing.template is not None or change
        if thing.copies is not None:
            self.hand(number, 0, 'copies: `name: Template * k` has no form in the first version')
            return
        self.verbatim(number)
        members = {getattr(m, 'line', None): m for m in thing.members}
        handled = set()

        def member_line(child):
            first = child.first
            word = first.value if first.kind == 'name' else None
            member = members.get(child.number)
            if word in ('title', 'role') and member is None:
                self.verbatim(child.number)
                if word == 'role':
                    self.proposed['`role` kept as a line'] += 1
                return True
            if word == 'sees' and member is None:
                facts = []
                scope = Scope(self.symbols, name)
                for fact, _ in thing.sees:
                    facts.append(scope.path(fact)[0])
                self.emit(child.number, 1, 'sees ' + ', '.join(facts))
                self.done_block(child.number)
                return True
            if word == 'status':
                status = next((m for m in thing.members if isinstance(m, nodes.Status)), None)
                if status is not None and id(status) not in handled:
                    handled.add(id(status))
                    self.status(status, name)
                return child.number in self.state
            if word == 'output' and member is None:
                # `output x` gave its lines to the field `x`: the field translated them.
                return child.number in self.state
            if member is None:
                return False
            try:
                self.member(member, name, instance)
            except Hand as reason:
                self.hand(child.number, 1, str(reason))
            return True

        # A field's `output x` line stands apart from the field: read the fields first.
        self.pending_outputs = {}
        for member in thing.members:
            value = member.lines if isinstance(member, nodes.Change) else member
            if isinstance(value, nodes.Value) and value.output is not None:
                self.pending_outputs[value.output.line] = (member, value)
        self.under(number, 1, thing.support, thing.text, extra=member_line)

    def change(self, thing):
        self.thing(thing, change=True)

    def member(self, member, thing, instance):
        if isinstance(member, nodes.Value):
            self.field(member, thing)
        elif isinstance(member, nodes.LinkDecl):
            kind = f'<{member.target}>' if member.many else member.target
            self.emit(member.line, 1, f'{member.name}: {kind}')
            self.done(member.line)
        elif isinstance(member, nodes.LinkBind):
            self.link(member, thing, instance)
        elif isinstance(member, nodes.Change):
            self.instance_line(member, thing)
        elif isinstance(member, nodes.Flow):
            self.flow(member, thing)
        elif isinstance(member, nodes.Allocate):
            self.share(member, thing)
        elif isinstance(member, nodes.Event):
            self.event(member, thing)
        elif isinstance(member, nodes.Check):
            self.check(member, thing)
        elif isinstance(member, nodes.Output):
            self.output(member, thing)
        elif isinstance(member, nodes.Status):
            self.status(member, thing)
        else:
            raise Hand(f'a {type(member).__name__}')

    def link(self, member, thing, instance):
        targets = member.targets
        if member.many:
            value = '<' + ', '.join(targets) + '>'
        elif targets in self.symbols.templates:
            value = f'{targets}.instances'
        else:
            value = targets
        self.emit(member.line, 1, f'{member.name} = {value}')
        self.done(member.line)

    # ---- fields -----------------------------------------------------------------------------------------

    def range_of(self, value, thing):
        if value.min is None:
            return ''
        low = self.expr(value.min.expr, thing, draws=False)
        high = self.expr(value.max.expr, thing, draws=False)
        return f' in [{low}, {high}]'

    def scale_of(self, value, thing):
        if value.size is None:
            return ''
        self.proposed['`scale S` for `size S`'] += 1
        return f' scale {self.expr(value.size.expr, thing, draws=False)}'

    def field(self, value, thing):
        kind = oldmodel.field_kind(value)
        number = value.line
        name = value.name
        typed = f': {value.type}' if isinstance(value.type, str) else ''
        cites = self.cites(value.support)
        if kind == 'input.text':
            head = f'input {name} = "{value.value.tokens[0].value}"'
        elif kind in ('input.number', 'input.bool'):
            head = f'input {name}{typed} = {self.expr(value.value, thing)}{self.range_of(value, thing)}'
        elif kind == 'input.named':
            members = ', '.join(exprs.member_of(v) for v in value.type) if isinstance(value.type, list) else None
            if members is None:
                raise Hand('an input with named values and no list of them')
            head = f'input {name}: enum[{members}] = {self.expr(value.value, thing)}'
        elif kind == 'let.fixed':
            if (thing, name) in self.formula_overrides:
                # An instance gives this member a formula, so the template declares a formula.
                written = typed[2:] if typed else None
                if written is None:
                    raise Hand('a fixed value that an instance replaces with a formula needs its type')
                head = f'readonly {name}: formula({written}) = formula({self.expr(value.value, thing)})'
                self.proposed['an instance replaces a formula of its template'] += 1
            else:
                head = f'readonly {name}{typed} = {self.expr(value.value, thing)}{self.range_of(value, thing)}'
        elif kind == 'let.formula':
            if not typed:
                raise Hand('a formula with no type')
            head = f'readonly {name}: formula({value.type}) = formula({self.expr(value.value, thing)})'
        elif kind == 'var.named':
            if not isinstance(value.type, list):
                raise Hand('a named state with no list of its values')
            members = ', '.join(exprs.member_of(v) for v in value.type)
            head = f'{name}: enum[{members}] = {self.expr(value.value, thing)}'
        elif kind == 'var.bool':
            head = f'{name}: bool = {self.expr(value.value, thing)}'
        elif kind == 'var.number':
            start = self.expr(value.value, thing, draws=True)
            bounds = self.range_of(value, thing)
            sort = self.kinds.get((self.symbols.declarer(thing), name))
            if not bounds and sort == 'stock':
                # A stock of the old language never goes below zero; the new one writes the bound.
                bounds = ' in [0, none]'
                self.proposed['`in [0, none]`: a store with a floor and no ceiling'] += 1
            head = f'{name}{typed} = {start}{bounds}{self.scale_of(value, thing)}'
        else:
            raise Hand(f'a field of kind {kind}')
        self.emit(number, 1, head + cites)
        self.done(number)

        def output_line(child):
            return self.field_output(child, value, thing)

        self.under(number, 2, value.support, value.text, extra=output_line)
        if value.output is not None and value.output.line not in self.state:
            self.field_output(self.logical[value.output.line], value, thing)

    def field_output(self, child, value, thing):
        """`output x` under a thing: an entry of `report:`. Its `scope`, `category` and `about` lines
        go under the field."""
        lines = value.output
        if lines is None or child.number != lines.line:
            return False
        self.report_entry(lines, self.report_path(thing, value.name), child.number, thing)
        self.done(child.number)
        for sub in child.under:
            key = sub.first.value if sub.first.kind == 'name' else None
            if key in ('scope', 'category', 'about'):
                self.emit(value.line, 2, written_row(self, sub.number).strip())
                self.done(sub.number)
                self.proposed[f'`{key}` kept as a line under a declaration'] += 1
            elif key in ('level', 'signed', 'lag'):
                self.done_block(sub.number)
            else:
                self.hand(sub.number, 2, 'a line of an output')
        return True

    def report_path(self, thing, name):
        if thing is None:
            return name
        if thing in self.symbols.templates:
            return f'{thing}.instances.{name}'
        return f'{thing}.{name}'

    def report_entry(self, lines, path, number, thing=None):
        flags = []
        if lines.measure != 'level' and lines.unestimated is None:
            flags.append('cumulative')
        if lines.lag is not None:
            if thing is not None and thing in self.symbols.templates:
                raise Hand('lag: the delay of an output of a template is read in each instance')
            own = f'{thing}.' if thing is not None else ''
            delays = [self.expr(d, thing, draws=False, own=own) for d in lines.lag.delays]
            if lines.lag.kind == 'fixed':
                flags.append(f'lag {delays[0]}')
            elif lines.lag.kind == 'uniform':
                flags.append(f'lag uniform({", ".join(delays)})')
            else:
                raise Hand('a lag that is a mixture')
        self.report.append((number, path + ''.join(' ' + flag for flag in flags)))

    def instance_line(self, change, thing):
        lines = change.lines
        number = change.line
        cites = self.cites(lines.support)
        found = self.symbols.read(change.name, thing)
        kind = found[1] if found is not None and found[0] == 'value' else None
        if change.kind is not None:
            new = oldmodel.field_kind(lines)
            if new == 'let.formula':
                head = f'{change.name} = formula({self.expr(lines.value, thing)})'
            elif new == 'let.fixed':
                head = f'{change.name} = formula({self.expr(lines.value, thing)})'
            else:
                raise Hand(f'an instance makes the member {change.name} a {new}')
            self.proposed['an instance replaces a formula of its template'] += 1
            self.emit(number, 1, head + cites + '  # PROPOSED: an instance replaces a formula')
        elif lines.value is not None:
            if kind == 'input.text':
                value = f'"{lines.value.tokens[0].value}"'
            else:
                value = self.expr(lines.value, thing)
            self.emit(number, 1, f'{change.name} = {value}{self.range_of(lines, thing)}{cites}')
        elif lines.output is not None and lines.text is None and not lines.support:
            raise Hand('new lines of the output of a member of an instance')
        else:
            self.emit(number, 1, f'{change.name}:{cites}')
        self.done(number)
        self.under(number, 2, lines.support, lines.text)

    def _formula_overrides(self):
        """{(template, member)} of the fixed values that some instance replaces with a formula."""
        found = set()
        for file in self.files:
            for thing in file.things:
                if thing.template is None:
                    continue
                for member in thing.members:
                    if isinstance(member, nodes.Change) and member.kind is not None:
                        found.add((thing.template, member.name))
        return found

    # ---- flows and shares -----------------------------------------------------------------------------

    def end(self, name, thing):
        return Scope(self.symbols, thing).path(name)[0]

    def flow(self, flow, thing):
        number = flow.line
        if flow.together is not None:
            try:
                draft = self.legs_draft(flow, thing)
            except Hand:
                draft = None
            self.hand(number, 1, 'a flow with several pairs: name each leg', draft)
            return
        pair = flow.pair
        source = 'SOURCE' if pair.source == 'outside' else self.end(pair.source, thing)
        target = 'SINK' if pair.target == 'outside' else self.end(pair.target, thing)
        rate = exprs.rewrite_old(flow.rate.expr, Scope(self.symbols, thing, self.output_names))
        literal = rate[0] == 'num'
        if flow.keep is not None:
            keep = exprs.rewrite_old(flow.keep.expr, Scope(self.symbols, thing, self.output_names))
            rate = ('if', keep, rate, ('num', '0', None))
            literal = False
        request = show(rate) if literal else f'formula({show(rate)})'
        self.emit(number, 1, f'flow {flow.name}: {source} -> {target}{self.cites(flow.support)}')
        self.done(number)
        self.under(number, 2, flow.support, flow.text)
        self.emit_after(number, 2, f'request = {request}')

    def share(self, share, thing):
        """`share VAR limit RATE [order f, g]`: the limit is the `outflow.capacity` of the store, and the
        order its `outflow.allocation`. The lines go under the declaration of the store."""
        found = self.symbols.read(share.stock, thing)
        info = self.symbols.things[thing]
        store = None
        if found is not None and found[0] == 'value' and found[2] == thing and '.' not in share.stock:
            node = self.symbols.nodes[thing]
            store = next(
                (m for m in node.members if isinstance(m, nodes.Value) and m.name == share.stock), None
            )
        if store is None or store.line not in self.state:
            raise Hand('share: the store is declared in another thing or after its share')
        declared = self.symbols.nodes[self.symbols.declarer(thing)]
        flows = {m.name: m for m in declared.members if isinstance(m, nodes.Flow)}
        for name, _ in share.serve or ():
            if name not in flows:
                raise Hand('share: its order names something that is no flow of the thing')
            if flows[name].together is not None:
                raise Hand('share: its order names a flow with several pairs, so it names the leg at this store')
        limit = self.expr(share.limit.expr, thing, draws=False)
        literal = oldmodel_literal(share.limit.expr.tokens)
        self.anchor = self.end_of(store.line) + 0.3
        try:
            capacity = limit if literal else f'formula({limit})'
            self.emit(share.line, 2, f'outflow.capacity = {capacity}{self.cites(share.support)}')
            self.done(share.line)
            self.under(share.line, 3, share.support, share.text)
            if share.serve is not None:
                names = ', '.join(self.end(name, thing) for name, _ in share.serve)
                self.emit(share.line, 2, f'outflow.allocation = priority({names})')
        finally:
            self.anchor = None
        self.proposed['the text and the records of a share go under `outflow.capacity`'] += 1

    def legs_draft(self, flow, thing):
        """A draft of a flow with several pairs: its legs need names, which a person gives."""
        scope = Scope(self.symbols, thing, self.output_names)
        rate = exprs.rewrite_old(flow.rate.expr, scope)
        keep = exprs.rewrite_old(flow.keep.expr, scope) if flow.keep is not None else None
        rows = [f'flow {flow.name}:{self.cites(flow.support)}']
        for k, pair in enumerate(flow.together, 1):
            source = 'SOURCE' if pair.source == 'outside' else self.end(pair.source, thing)
            target = 'SINK' if pair.target == 'outside' else self.end(pair.target, thing)
            own = exprs.rewrite_old(pair.rate.expr, scope) if pair.rate is not None else rate
            if keep is not None:
                own = ('if', keep, own, ('num', '0', None))
            rows.append(f'    flow leg_{k}: {source} -> {target}{self.cites(pair.support)}')
            rows.append(f'        request = formula({show(own)})')
        return rows

    # ---- events -----------------------------------------------------------------------------------------

    def event(self, event, thing):
        number = event.line
        if not self.events:
            raise Hand('an event')
        if len(event.outcomes) > 1:
            raise Hand('an event with several outcomes: a `switch` in a stage')
        if event.each or event.keep is not None:
            raise Hand('an event with a window or a `while`')
        only = event.outcomes[0] if event.outcomes else None
        if only is not None and (only.chance is not None or only.is_else or only.when is not None):
            raise Hand('an event whose one outcome has a chance or a condition: a guard on its stage')
        scope = Scope(self.symbols, thing, self.output_names)
        rows = []
        when = None
        if event.when is not None:
            when = show(exprs.rewrite_old(event.when, scope))
        delay = '0 h'
        if event.after is not None:
            delay = show(exprs.rewrite_old(event.after, scope))
        if event.after is not None and not event.once:
            raise Hand(
                'an event that waits and can trigger again: the old language keeps one firing that waits, '
                'and the new one starts an occurrence at each trigger'
            )
        body = []
        written = set()
        for line in only.lines if only is not None else ():
            # The old language reads every value of an outcome from before the outcome. A stage of the
            # new one reads what its earlier lines wrote.
            value = line.value if isinstance(line, nodes.Assign) else getattr(line, 'amount', None)
            if value is not None:
                for name in exprs.names_of(old_names(value)):
                    found = self.symbols.read(name, thing)
                    if found is not None and found[0] == 'value' and (found[2], found[3]) in written:
                        raise Hand(
                            f'a line of the event reads {name}, which an earlier line of the same event sets: '
                            'the old language reads the value from before the event'
                        )
            body.append(self.statement(line, thing, scope))
            if isinstance(line, nodes.Assign):
                found = self.symbols.read(line.target, thing)
                if found is not None and found[0] == 'value':
                    written.add((found[2], found[3]))
            elif isinstance(line, nodes.Move):
                for end in (line.source, line.target):
                    found = self.symbols.read(end, thing)
                    if found is not None and found[0] == 'value':
                        written.add((found[2], found[3]))
        # An outcome's text and records, when the one outcome is written by its name.
        # The records of the old event stay on the event. A person can move the record that says how
        # the thing knows what the `when` reads to the trigger, where the specification puts it.
        self.emit(number, 1, f'{event.name} = event():{self.cites(event.support)}')
        self.done(number)

        def inner(child):
            first = child.first
            if first.is_name('role') and len(child.tokens) == 2:
                self.verbatim(child.number)
                return True
            if only is not None and child.number == only.line and child.number != number:
                # `done:` written by its name: its text and records go under the event.
                self.done(child.number)
                self.under(child.number, 2, only.support, only.text, braces_thing=thing, extra=statement_line)
                return True
            return statement_line(child)

        def statement_line(child):
            if only is not None and any(child.number == line.line for line in only.lines):
                self.done_block(child.number)
                return True
            return False

        self.under(number, 2, event.support, event.text, braces_thing=thing, extra=inner)
        if when is not None:
            self.emit_after(number, 2, fit(2, 'when ', when, ':'))
            self.emit_after(number, 3, f'this.{event.name}.start()')
            if event.once:
                self.emit_after(number, 3, 'reset when false')
        if body or event.after is not None:
            self.emit_after(number, 2, f'after {delay}:')
            for row in body:
                self.emit_after(number, 3, row)
            if not body:
                self.emit_after(number, 3, '# Nothing changes: the event marks the moment.')
        if event.name == 'start':
            self.proposed['an event named `start`'] += 1

    def statement(self, line, thing, scope):
        if isinstance(line, nodes.Assign):
            target, found = scope.path(line.target)
            kind = found[1] if found[0] == 'value' else None
            if kind == 'input.text':
                value = f'"{line.value.tokens[0].value}"'
            else:
                value = show(exprs.rewrite_old(line.value, scope))
            return f'{target} {line.op} {value}'
        if isinstance(line, nodes.Move):
            amount = show(exprs.rewrite_old(line.amount, scope))
            return f'move {amount} from {scope.path(line.source)[0]} to {scope.path(line.target)[0]}'
        if isinstance(line, nodes.Fire):
            path, found = scope.path(line.target)
            if found[0] != 'event':
                raise Hand(f'the line {line.target} names no event')
            return f'{path}.start()'
        raise Hand(f'a line of an event of kind {type(line).__name__}')

    # ---- status, asserts, outputs -------------------------------------------------------------------

    def status(self, status, thing):
        for case in status.lines:
            number = case.line
            head = f'status {case.status}'
            on_line = [s for s in status.support if s.line == number and self.on_line(s)]
            if case.condition is not None:
                head = fit(1, head + ' when ', self.expr(case.condition, thing), self.cites(on_line))
            else:
                head += self.cites(on_line)
            self.emit(number, 1, head)
            self.done(number)
            under = [s for s in status.support if oldmodel_evidence_place(s.place) is not None]
            self.under(number, 2, under, case.text, braces_thing=thing)

    def check(self, check, thing=None):
        number = check.line
        depth = 0 if thing is None else 1
        scope = Scope(self.symbols, thing, self.output_names)
        if check.kind == 'conserve':
            terms = []
            for term, _ in check.terms:
                path, found = scope.path(term)
                terms.append(('call', 'sum', [('name', path)]) if found[0] == 'value' and found[4] else ('name', path))
            total = exprs.rewrite_old(check.total, scope)
            within = exprs.rewrite_old(check.within.expr, scope)
            left = terms[0]
            for term in terms[1:]:
                left = ('bin', '+', left, term)
            tree = ('in', left, ('bin', '-', total, within), ('bin', '+', total, within))
            head = f'assert {show(tree)}'
        else:
            if check.within is not None:
                raise Hand('`assert C within TOL` that is no sum: write the interval by hand')
            head = fit(depth, 'assert ', self.expr(check.expr, thing), self.cites(check.support))
            head = head.removesuffix(self.cites(check.support)) if self.cites(check.support) else head
        self.emit(number, depth, head + self.cites(check.support))
        self.done(number)
        self.under(number, depth + 1, check.support, check.text)

    def output(self, output, thing=None):
        number = output.line
        depth = 0 if thing is None else 1
        lines = output.lines
        cites = self.cites(lines.support)
        name = output.name
        if thing is not None and name in self.symbols.things[thing].values and self.symbols.things[thing].values[name] != 'output':
            raise Hand(f'an output named as the field {name} of its thing')
        if lines.unestimated is not None:
            head = f'{name}: {output.type} = none'
        else:
            if output.type is None:
                raise Hand('an output with no unit')
            bounds = '' if lines.signed else ' in [0, none]'
            if bounds:
                self.proposed['`in [0, none]` on a reported formula: it is never negative'] += 1
            readonly = 'readonly ' if thing is not None else ''
            head = f'{readonly}{name}: formula({output.type}) = formula({self.expr(output.expr, thing)}){bounds}'
        self.report_entry(lines, self.report_path(thing, name), number, thing)
        self.emit(number, depth, head + cites)
        self.done(number)

        def line_of(child):
            key = child.first.value if child.first.kind == 'name' else None
            if key in ('about', 'scope', 'category'):
                self.verbatim(child.number)
                self.proposed[f'`{key}` kept as a line under a declaration'] += 1
                return True
            if key in ('level', 'signed'):
                self.done_block(child.number)
                return True
            if key == 'lag':
                self.done_block(child.number)
                return True
            if key == 'distinct':
                # Its records stay on the formula: they say why the groups that it adds are disjoint.
                cited = self.cites(lines.distinct.support)
                if cited:
                    self.emit(child.number, depth + 1, cited.strip())
                self.done(child.number)
                self.under(child.number, depth + 1, lines.distinct.support)
                return True
            if key == 'unestimated':
                self.emit(child.number, depth + 1, f'@identity "{lines.unestimated.value}"')
                self.done_block(child.number)
                self.proposed['the reason of a `none` is a record in place'] += 1
                return True
            return False

        self.under(number, depth + 1, lines.support, lines.text, extra=line_of)

    def report_block(self):
        if not self.report:
            return
        # After the last thing, check or output of the file, and before its options, runs and notes.
        tops = [item.line for item in [*self.file.things, *self.file.checks, *self.file.outputs]]
        anchor = max(tops)
        where = self.logical[self.block(anchor)[-1]].end + 0.5
        self.out.append((where, self.sequence + 1, ''))
        self.out.append((where, self.sequence + 2, '# PROPOSED: the default selection of the package.'))
        self.out.append((where, self.sequence + 3, 'report:'))
        self.sequence += 3
        for _, entry in sorted(self.report):
            self.sequence += 1
            self.out.append((where, self.sequence, INDENT + entry))
        self.proposed['a `report:` block'] += 1

    # ---- options, runs, notes, records ----------------------------------------------------------------

    def options(self, group):
        self.verbatim(group.line)
        for option in group.profiles:
            self.verbatim(option.line)
            settings = {setting.line: setting for setting in option.settings}

            def setting_line(child):
                setting = settings.get(child.number)
                if setting is None:
                    return False
                try:
                    self.setting(setting)
                except Hand as reason:
                    self.hand(child.number, 2, str(reason))
                return True

            self.under(option.line, 2, (), option.text, extra=setting_line)

    def setting(self, setting):
        head, _, member = setting.target.rpartition('.')
        found = self.symbols.read(setting.target, None)
        kind = found[1] if found is not None and found[0] == 'value' else None
        if kind is None:
            raise Hand(f'the line of an option sets {setting.target}, which this script does not resolve')
        if head in self.symbols.templates:
            target = f'{head}.instances.{member}'
            owner = head
            self.proposed['`Template.instances.x = v` in an option'] += 1
        else:
            target, owner = setting.target, head
        if kind == 'input.text':
            value = f'"{setting.value.tokens[0].value}"'
        else:
            # The names of the value are read in the thing that the line sets, as the old language does.
            own = '' if head in self.symbols.templates else f'{owner}.'
            if head in self.symbols.templates and not oldmodel_literal(setting.value.tokens):
                raise Hand('an option gives every instance of a template a value that is an expression')
            value = self.expr(setting.value, owner, own=own)
        self.emit(setting.line, 2, f'{target} = {value}{self.cites(setting.support)}')
        self.done(setting.line)
        self.under(setting.line, 3, setting.support)

    def runs(self):
        number = self.file.lines[self.file.runs_place]
        self.verbatim(number)
        for run in self.file.runs:
            names = ' + '.join(f'"{name}"' for name in run.profiles)
            if run.versus is not None:
                self.comparisons.append((run.name, run.versus))
                self.emit(run.line, 1, f'{run.name} = {names}')
                self.state[run.line] = 'todo'
                self.why['`versus`'] += 1
                self.emit(
                    run.line,
                    1,
                    f'# TODO(hand): `versus {run.versus}` leaves the language. Name the pair where the '
                    'comparison is made (R-A5-06).',
                    raw=True,
                )
            else:
                self.emit(run.line, 1, f'{run.name} = {names}')
                self.done(run.line)
            if run.text is not None:
                self.verbatim(run.text.line)

    def notes(self):
        """Notes keep their form. A record in place with an ID moves its ID to a line of its own."""
        number = self.file.notes[0].line if self.file.notes else None
        start = self.file.lines[('notes:',)]
        self.verbatim(start)

        def walk(items, depth):
            for note in items:
                self.verbatim(note.line)
                placed = {
                    item.line: item for item in note.support if isinstance(item, nodes.Record)
                }
                for child in self.children(note.line):
                    if child.number in self.state:
                        continue
                    if child.first.kind == 'at':
                        record = placed.get(child.number)
                        if record is not None:
                            self.record_in_place(child.number, depth + 1, record)
                        else:
                            self.verbatim(child.number)
                walk(note.under, depth + 1)

        walk(self.file.notes, 1)

    def record(self, record):
        number = record.line
        if record.id is None:
            for k in self.block(number):
                self.verbatim(k)
            return
        self.emit(number, 0, f'record {record.name}: {record.kind} "{record.text}"')
        self.done(number)
        self.emit(number, 1, f'{id_label(record.kind)} {record.id}')
        for child in self.children(number):
            for k in self.block(child.number):
                self.verbatim(k)

    # ---- the result -------------------------------------------------------------------------------------

    def result(self):
        """(the text of the new file, the counts of its lines)."""
        items = sorted(self.out, key=lambda item: (item[0], item[1]))
        # Comments and empty lines keep their place: each goes before the first line that comes from a
        # later line of the old file.
        extras = [line for line in self.flat if line.kind != 'line']
        rows, k = [], 0
        for where, _, text in items:
            while k < len(extras) and extras[k].number < where:
                rows.append(self.rows[extras[k].number - 1].rstrip() if extras[k].kind == 'comment' else '')
                k += 1
            rows.append(text)
        while k < len(extras):
            rows.append(self.rows[extras[k].number - 1].rstrip() if extras[k].kind == 'comment' else '')
            k += 1
        while rows and not rows[-1]:
            rows.pop()
        counts = collections.Counter(self.state.values())
        missing = sorted(set(self.logical) - set(self.state))
        physical = collections.Counter()
        for number, line in self.logical.items():
            physical[self.state.get(number, 'missed')] += line.end - line.number + 1
        return '\n'.join(rows) + '\n', {
            'logical': len(self.logical),
            'done': counts['done'],
            'todo': counts['todo'],
            'missed': missing,
            'physical': dict(physical),
            'why': dict(self.why),
            'proposed': dict(self.proposed),
            'comparisons': self.comparisons,
        }


def old_names(expr):
    """The tree of an old expression with each old name as a path of its own words, for a reader of
    the names alone."""
    tree = exprs.old_tree(expr)

    def visit(node):
        if node[0] == 'old':
            return ('name', node[1])
        if node[0] == 'call':
            return ('call', node[1], [visit(arg) for arg in node[2]])
        if node[0] == 'un':
            return ('un', node[1], visit(node[2]))
        if node[0] in ('bin', 'cmp'):
            return (node[0], node[1], visit(node[2]), visit(node[3]))
        if node[0] == 'bool':
            return ('bool', node[1], [visit(value) for value in node[2]])
        if node[0] == 'if':
            return ('if', visit(node[1]), visit(node[2]), visit(node[3]))
        if node[0] == 'pair':
            return ('pair', node[1], visit(node[2]))
        return node

    return visit(tree)


def oldmodel_evidence_place(place):
    """The number of the evidence line that a place is on (`(..., '@', k)`), or None for evidence that
    ends the line of its declaration."""
    for k, part in enumerate(place):
        if part == '@' and k + 1 < len(place) and isinstance(place[k + 1], int):
            return place[k + 1]
    return None


def fit(depth, before, expression, after):
    """`before expression after` on one line. An expression that makes the line too long, and has no
    bracket around it, takes one: an expression continues on the next row only inside a bracket."""
    line = f'{before}{expression}{after}'
    if len(INDENT) * depth + len(line) <= WIDTH or expression.startswith('('):
        return line
    return f'{before}({expression}){after}'


def oldmodel_literal(tokens):
    from napkin.model.language.parse import Parser

    return Parser.literal(tokens)


def id_label(kind):
    """What the ID of a record names (docs/language.md, 2.10): a convention of the library for a
    `convention` record, an assumption for a record of any other kind."""
    return 'convention' if kind == 'convention' else 'assumption'


def written_row(translator, number):
    line = translator.logical[number]
    return ' '.join(translator.rows[k - 1].strip() for k in range(line.number, line.end + 1))


def main(argv):
    events = '--no-events' not in argv
    to_stdout = '--stdout' in argv
    paths = [Path(arg) for arg in argv if not arg.startswith('--')]
    every = not paths
    if every:
        paths = oldmodel.model_files()
    out = HERE / 'translated' / 'auto'
    total = collections.Counter()
    why = collections.Counter()
    proposed = collections.Counter()
    rows = []
    for path in paths:
        path = path if path.is_absolute() else Path.cwd() / path
        translator = Translator(path, events=events)
        text, counts = translator.translate()
        try:
            relative = path.resolve().relative_to(BASE.resolve())
        except ValueError:
            relative = Path(path.name)
        if to_stdout:
            sys.stdout.write(text)
        else:
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
        share = counts['done'] / counts['logical'] if counts['logical'] else 1.0
        rows.append((relative.as_posix(), counts['logical'], counts['done'], counts['todo'], len(counts['missed']), share))
        total.update({'logical': counts['logical'], 'done': counts['done'], 'todo': counts['todo'], 'missed': len(counts['missed'])})
        why.update(counts['why'])
        proposed.update(counts['proposed'])
        if counts['missed']:
            print(f'  {relative}: lines that the script lost: {counts["missed"][:8]}', file=sys.stderr)
    if to_stdout:
        return
    width = max(len(row[0]) for row in rows)
    print(f'{"file":{width}}  lines  translated  left  share')
    for name, logical, done, todo, missed, share in rows:
        print(f'{name:{width}}  {logical:5d}  {done:10d}  {todo:4d}  {share:5.1%}' + (f'  ({missed} lost)' if missed else ''))
    if every or len(rows) > 1:
        share = total['done'] / total['logical']
        print(f'{"all":{width}}  {total["logical"]:5d}  {total["done"]:10d}  {total["todo"]:4d}  {share:5.1%}')
        print()
        print('lines left for a person, by reason:')
        for reason, n in why.most_common():
            print(f'  {n:5d}  {reason}')
        print()
        print('translated lines that use a proposed spelling:')
        for reason, n in proposed.most_common():
            print(f'  {n:5d}  {reason}')
        print()
        print(f'wrote {out}')


if __name__ == '__main__':
    main(sys.argv[1:])
