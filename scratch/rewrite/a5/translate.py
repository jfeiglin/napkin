#!/usr/bin/env python
"""The mechanical translator of stage M: the lines of an old model file in the language of now.

It reads the old file with the old parser (at the base commit 8488047), so it runs with the old
compiler on the path:

    PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python translate.py [--compile] [PATH...]

A PATH is an old model file, or the folder of an old package (each of its `.scn` files); a relative
one is read from the base commit. With no PATH it translates every model file of `examples/` and
`scenarios/` there. Each translation goes to `translated/now/`, at the path that it has at the base
commit, with the files of its package that the compiler reads (`units.json`, `evidence/`) and the
catalogue's library, so that it compiles where it stands. It never writes over a model of the
checkout. It prints the share of the logical lines that it translated, for each file, and why it
left the others. `--stdout` prints one translation instead.

With `--compile` it compiles each entry file that it wrote (a package's main file when the package
has no variant, else each variant) with the compiler of now (`newmodel.py`, in a process without the
old compiler), and prints the problems that stop the compile by their code, and the warnings of the
evidence rule (`no_record`, change 16).

A line that it cannot translate is left for a person: a `# TODO(hand): reason` line, then its old
text as comments, then a draft when it has one. Nothing is read with a text pattern over the source:
every name is resolved with the names of the model (`oldmodel.Symbols`). What it writes:

- the scenario line, `use`, things, templates and instances, links (`<a, b>`, `Template.instances`),
  inputs, fixed values (`readonly`), formulas, named states (`enum[...]`) and numbers that change,
  with their ranges (`in [lo, hi]`; a stock with none gets `in [0,]`) and scales (`scale`, for `size`);
  units spelled with `*` and `/` (D12: `tunings/tuner/year` for `tunings/tuner-year`);
- a flow of one pair with `request` and `capacity` both, the old fixed rate (D15, D-8 of S0); a flow
  of several pairs with one leg for each, named by the target store (R-A5-12: a person may rename
  them), each with its `request`; a share as the `outflow.capacity` and `outflow.allocation` of its
  store;
- an event as `e = event():` with its trigger (`when C:`, `this.e.start()`, `reset when false` for
  `once`) and one stage (`after D:`). Outcomes by condition are a local `outcome` and a `switch` on it;
  outcomes by chance a `switch` on `categorical(...).draw()`; an actor's choice a field `forecast`
  holding the chances, a local `order` drawn from it and a `switch` on it, which a caller edits at a
  breakpoint (change 15). A case whose outcome has no line cannot be written (a case has an action),
  so it is left for a person with its text;
- status cases, asserts (a sum check is an interval), options, runs, notes and records (an ID goes on
  a line of its own under its record: R-A5-02);
- an output as a named formula with its text and records, `in [0,]` unless it was `signed` (D10). What
  the language has no place for goes into the notes, with its words: the `about`, `scope`,
  `category` and `lag` of each output under `reporting:`, an output with no estimate (D4) with its
  label and reason under `not_estimated:`, and each `versus` pair under `comparisons:` (D9).

What leaves the language with no trace in the model: `sees` (change 15), the `role` of an event or an
outcome (written as a comment), `level`, `signed`, `cumulative`. Braces in a text stay as written.
"""

from __future__ import annotations

import collections
import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import exprs
import oldmodel
from exprs import Hand, Scope, new_unit, show, with_new_units
from oldmodel import BASE, lex, nodes

HERE = Path(__file__).resolve().parent
OUT = HERE / 'translated' / 'now'
WIDTH = 110
INDENT = '    '
# The interpreter of the checkout, which loads the compiler of now when no PYTHONPATH names the old one.
PYTHON = '/home/user/napkin/.venv/bin/python'
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


def quoted(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def unit_of(declared):
    """The type of a value as the language of now writes a unit (`new_unit`), or `bool`."""
    return declared if declared == 'bool' else new_unit(declared)


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
        self.dropped = collections.Counter()  # what the language of now has no place for
        self.defaults = collections.Counter()  # names and forms that the script chose
        self.out = []  # (old line, sequence, text)
        self.sequence = 0
        self.anchor = None  # where the next lines go, when they move under another declaration
        self.events = events
        # The notes that the script adds: {top key: [(path of keys, value text, cites)]}.
        self.extra = collections.defaultdict(list)
        self.output_names = {o.name for file in self.files for o in file.outputs}
        self.formula_overrides = self._formula_overrides()
        self.renames = self._renames()
        self.started = self._started()

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

    def emit_after(self, number, depth, text, raw=False):
        """A line that comes after every line under the declaration at `number`."""
        where = self.anchor if self.anchor is not None else self.end_of(number) + 0.25
        for row in [INDENT * depth + text] if raw else wrap(depth, text):
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
        old_depth = self.logical[number].depth
        for k in range(number, last + 1):
            row = self.rows[k - 1]
            self.emit(
                number, depth, ('# | ' + row[len(INDENT) * old_depth :]) if row.strip() else '# |', raw=True
            )
        for row in draft or ():
            self.emit(number, depth, '# draft: ' + row, raw=True)

    def children(self, number):
        return self.logical[number].under

    def note(self, top, keys, value, cites='', rows=()):
        """A note that the script adds under `notes:`: `top:` / each key / the last key with its value
        (a text, or a word), the records that it cites, and `rows` under it: (depth under the key,
        text) of its records in place."""
        self.extra[top].append((tuple(keys), value, cites, tuple(rows)))

    # ---- small parts ---------------------------------------------------------------------------------

    def cites(self, support):
        """The citations that end a line: `  @a @b`."""
        names = [item.name for item in support if isinstance(item, nodes.Cite) and self.on_line(item)]
        return ('  ' + ' '.join('@' + name for name in names)) if names else ''

    def all_cites(self, support):
        """Every citation of a declaration, on its line or on a row of its own: `  @a @b`."""
        names = [item.name for item in support if isinstance(item, nodes.Cite)]
        return ('  ' + ' '.join('@' + name for name in names)) if names else ''

    def on_line(self, cite):
        """Whether a citation ends its line: its place is the place of the line, with no `@` part."""
        return evidence_place(cite.place) is None

    def under(self, number, depth, support=(), text=None, extra=None):
        """The lines under a declaration that keep their form: its text, its citations on lines of
        their own and its records in place. `extra(child)` translates another line and returns True."""
        placed = {}
        for item in support:
            where = evidence_place(item.place)
            if where is not None:
                placed.setdefault(item.line, []).append(item)
        for child in self.children(number):
            if child.number in self.state:
                continue
            first = child.first
            if first.kind == 'text' or (first.is_op('[') and text is not None and child.number == text.line):
                self.verbatim(child.number, depth if depth != child.depth else None)
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

    def record_in_place(self, number, depth, record):
        """`@kind [ID] "explanation"` with its claims. The ID moves to a line of its own, which says what
        it names (R-A5-02)."""
        moved = depth - self.logical[number].depth
        if record.id is None:
            for k in self.block(number):
                self.verbatim(k, self.logical[k].depth + moved if moved else None)
            return
        self.emit(number, depth, f'@{record.kind} {quoted(record.text)}')
        self.done(number)
        self.emit(number, depth + 1, f'{id_label(record.kind)} {record.id}')
        for child in self.children(number):
            for k in self.block(child.number):
                self.verbatim(k, self.logical[k].depth + moved if moved else None)

    def tree(self, expr, thing, draws=True, own='this.'):
        """The tree of an old expression in the language of now, with its units spelled anew."""
        return with_new_units(exprs.rewrite_old(expr, self.scope(thing, own), draws))

    def expr(self, expr, thing, draws=True, own='this.'):
        return show(self.tree(expr, thing, draws, own))

    def scope(self, thing, own='this.'):
        return Scope(self.symbols, thing, self.output_names, own=own, renames=self.renames)

    def renamed(self, thing, name):
        """The name of a member in the language of now (`renames`)."""
        return self.renames.get((self.symbols.declarer(thing), name), name) if thing is not None else name

    def _started(self):
        """{(thing, member)} of the states whose start an option sets."""
        found = set()
        for file in self.files:
            for group in file.profiles:
                for option in group.profiles:
                    for setting in option.settings:
                        read = self.symbols.read(setting.target, None)
                        if read is not None and read[0] == 'value' and read[1].startswith('var.'):
                            found.add((self.symbols.declarer(read[2]), read[3]))
        return found

    def _renames(self):
        """{(thing, member): new name}: a value named `status` of a thing that has status lines is
        `state` now, since the display is the thing's `status` (`semantic.STATUS_NAME`)."""
        found = {}
        for name, node in self.symbols.nodes.items():
            values = {m.name for m in node.members if isinstance(m, nodes.Value)}
            if 'status' in values and any(isinstance(m, nodes.Status) for m in node.members):
                found[(name, 'status')] = 'state' if 'state' not in values else 'status_value'
        return found

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
        self.extra_notes()
        return self.result()

    def scenario(self, block):
        number = block.line
        self.verbatim(number)
        for child in self.children(number):
            key = child.first.value
            if key in ('summary', 'scope', 'library', 'horizon', 'resolution'):
                self.verbatim(child.number)
            elif key == 'timescales':
                parts = [self.expr(item, None, draws=False) for item in block.timescales]
                self.emit(child.number, 1, 'timescales ' + ', '.join(parts))
                self.done_block(child.number)
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
                if thing.template is None:
                    self.verbatim(child.number)
                    return True
                # A member written by hand has no title or role in the language of now: its words
                # go into the notes (`titles`, `roles`), for the drawings and the briefs.
                words = child.tokens[1]
                said = quoted(words.value) if words.kind == 'text' else words.value
                self.note(word + 's', [name], said)
                self.done_block(child.number)
                self.dropped[f'the {word} of a member: into the notes'] += 1
                return True
            if word == 'sees' and member is None:
                # Change 15: `sees` left the language; a wrapper shows any value at a breakpoint.
                self.done_block(child.number)
                self.dropped['sees (change 15)'] += 1
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
            self.link(member)
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

    def link(self, member):
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
        return f' scale {self.expr(value.size.expr, thing, draws=False)}'

    def field(self, value, thing):
        kind = oldmodel.field_kind(value)
        number = value.line
        name = self.renamed(thing, value.name)
        if name != value.name:
            self.defaults['a value named `status` beside status lines is `state`'] += 1
        typed = f': {unit_of(value.type)}' if isinstance(value.type, str) else ''
        cites = self.cites(value.support)
        if kind == 'input.text':
            head = f'input {name} = {quoted(value.value.tokens[0].value)}'
        elif kind in ('input.number', 'input.bool'):
            head = f'input {name}{typed} = {self.expr(value.value, thing)}{self.range_of(value, thing)}'
        elif kind == 'input.named':
            if not isinstance(value.type, list):
                raise Hand('an input with named values and no list of them')
            members = ', '.join(exprs.member_of(v) for v in value.type)
            head = f'input {name}: enum[{members}] = {self.expr(value.value, thing)}'
        elif kind == 'let.fixed':
            if (thing, name) in self.formula_overrides:
                # An instance gives this member a formula, so the template declares a formula (R-A5-07).
                if not typed:
                    raise Hand('a fixed value that an instance replaces with a formula needs its type')
                head = f'readonly {name}: formula({typed[2:]}) = formula({self.expr(value.value, thing)})'
            else:
                head = (
                    f'readonly {name}{typed} = {self.expr(value.value, thing)}{self.range_of(value, thing)}'
                )
        elif kind == 'let.formula':
            if not typed:
                raise Hand('a formula with no type')
            head = f'readonly {name}: formula({typed[2:]}) = formula({self.expr(value.value, thing)})'
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
            if not bounds and self.kinds.get((self.symbols.declarer(thing), value.name)) == 'stock':
                # A stock of the old language never goes below zero; the new one writes its floor (D8).
                bounds = ' in [0,]'
                self.defaults['`in [0,]` on a stock'] += 1
            head = f'{name}{typed} = {start}{bounds}{self.scale_of(value, thing)}'
        else:
            raise Hand(f'a field of kind {kind}')
        if kind.startswith('var.') and (self.symbols.declarer(thing), value.name) in self.started:
            # An option sets only an input (R-A5-04): the start of a state that an option sets is an
            # input of its own, which the option sets, and the state starts from it. An input's
            # default is a value written out, so a start that is a calculation is left for a person.
            if not oldmodel_literal(value.value.tokens):
                raise Hand(
                    'an option sets the start of a state that starts from a calculation: an input of its own'
                )
            declared, _, start = head.partition(' = ')
            start, bounds = (
                start.partition(' in [')[0],
                start.partition(' in [')[1] + start.partition(' in [')[2],
            )
            self.emit(number, 1, f'input {name}_start{declared[len(name) :]} = {start}{cites}')
            head = f'{declared} = this.{name}_start' + (f' {bounds}' if bounds else '')
            self.defaults['a state that an option sets starts from an input `x_start`'] += 1
        self.emit(number, 1, head + cites)
        self.done(number)

        def output_line(child):
            return self.field_output(child, value, thing)

        self.under(number, 2, value.support, value.text, extra=output_line)
        if value.output is not None and value.output.line not in self.state:
            self.field_output(self.logical[value.output.line], value, thing)

    def field_output(self, child, value, thing):
        """`output x` under a thing: the field is the value that a caller reports (D10). Its `about`,
        `scope`, `category` and `lag` go into the notes (`reporting`)."""
        lines = value.output
        if lines is None or child.number != lines.line:
            return False
        self.done(child.number)
        self.reporting(lines, [*self.owner_keys(thing), self.renamed(thing, value.name)], child.number, thing)
        return True

    def owner_keys(self, thing):
        """The keys of the notes under which the reporting lines of a thing's value go: the thing that
        declares it (a template for its instances), or none at the top level."""
        return [] if thing is None else [self.symbols.declarer(thing)]

    def reporting(self, lines, keys, number, thing):
        """The lines under an output that the language of now has no place for, as notes under
        `reporting:`: `about`, `scope` and `category` with their words, and `lag` as the text of its
        delay, which a caller now selects (D10). `level`, `signed` and `cumulative` say nothing now:
        a range says whether a value can be negative, and a proof whether it never falls."""
        if lines.about is not None:
            self.note('reporting', [*keys, 'about'], quoted(text_of(lines.about)))
        if lines.scope is not None:
            self.note('reporting', [*keys, 'scope'], quoted(text_of(lines.scope)))
        if lines.category is not None:
            self.note('reporting', [*keys, 'category'], lines.category)
        if lines.lag is not None:
            own = f'{thing}.' if thing is not None else ''
            delays = [show(self.tree(d, thing, draws=False, own=own)) for d in lines.lag.delays]
            if lines.lag.kind == 'fixed':
                said = delays[0]
            elif lines.lag.kind == 'uniform':
                said = f'uniform({", ".join(delays)})'
            else:
                raise Hand('a lag that is a mixture')
            self.note('reporting', [*keys, 'lag'], quoted(said))
        for sub in self.children(number):
            key = sub.first.value if sub.first.kind == 'name' else None
            if key in ('scope', 'category', 'about', 'level', 'signed', 'lag'):
                self.done_block(sub.number)

    def instance_line(self, change, thing):
        lines = change.lines
        number = change.line
        cites = self.cites(lines.support)
        found = self.symbols.read(change.name, thing)
        kind = found[1] if found is not None and found[0] == 'value' else None
        if change.kind is not None:
            new = oldmodel.field_kind(lines)
            if new not in ('let.formula', 'let.fixed'):
                raise Hand(f'an instance makes the member {change.name} a {new}')
            head = f'{self.renamed(thing, change.name)} = formula({self.expr(lines.value, thing)})'
            self.emit(number, 1, head + cites)
        elif lines.value is not None:
            if kind == 'input.text':
                value = quoted(lines.value.tokens[0].value)
            else:
                value = self.expr(lines.value, thing)
            self.emit(
                number, 1, f'{self.renamed(thing, change.name)} = {value}{self.range_of(lines, thing)}{cites}'
            )
        else:
            raise Hand('an instance line with no value: its text and records belong to the template')
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
        if name == 'outside':
            return None
        return self.scope(thing).path(name)[0]

    def rate(self, flow, own_rate, thing):
        """The request of a flow or a leg: its rate under its `while`, and whether it is a number."""
        scope = self.scope(thing)
        rate = with_new_units(exprs.rewrite_old(own_rate, scope))
        literal = rate[0] == 'num'
        if flow.keep is not None:
            keep = with_new_units(exprs.rewrite_old(flow.keep.expr, scope))
            rate = ('if', keep, rate, ('num', '0', None))
            literal = False
        return show(rate) if literal else f'formula({show(rate)})'

    def flow(self, flow, thing):
        number = flow.line
        if flow.together is not None:
            self.legs(flow, thing)
            return
        pair = flow.pair
        source = self.end(pair.source, thing) or 'SOURCE'
        target = self.end(pair.target, thing) or 'SINK'
        request = self.rate(flow, flow.rate.expr, thing)
        self.emit(number, 1, f'flow {flow.name}: {source} -> {target}{self.cites(flow.support)}')
        self.done(number)
        self.under(number, 2, flow.support, flow.text)
        # The old `at R` is a fixed rate: the request, and the capacity too, so that no claim at an
        # endpoint can carry more (D15; D-8 of S0 for the piano tuners).
        self.emit_after(number, 2, f'request = {request}')
        self.emit_after(number, 2, f'capacity = {request}')

    def leg_names(self, flow, thing):
        """The names of the legs of a flow of several pairs: the name of each target store, with its
        owner when it is another thing's, or the source's for a pair to outside (R-A5-12). The author
        may rename them."""
        out = []
        for pair in flow.together:
            target = pair.target if pair.target != 'outside' else pair.source
            parts = target.split('.')
            # A store of another thing is named with its owner: `field_crew_used`, `parts_used`.
            name = '_'.join(parts[-2:]) if len(parts) > 1 else parts[0]
            while name in out or name in RESERVED:
                name += '_leg'
            out.append(name)
        return out

    def legs(self, flow, thing):
        """A flow of several pairs: `flow f:` with a leg for each pair, which moves at the flow's rate
        (or its own) under the flow's `while`; the legs move together at one fraction."""
        number = flow.line
        names = self.leg_names(flow, thing)
        self.emit(number, 1, f'flow {flow.name}:{self.cites(flow.support)}')
        self.done(number)
        pairs = {pair.line: (pair, name) for pair, name in zip(flow.together, names, strict=True)}

        def leg(child):
            found = pairs.get(child.number)
            if found is None:
                return False
            pair, name = found
            source = self.end(pair.source, thing) or 'SOURCE'
            target = self.end(pair.target, thing) or 'SINK'
            own = pair.rate.expr if pair.rate is not None else flow.rate.expr
            self.emit(child.number, 2, f'flow {name}: {source} -> {target}{self.cites(pair.support)}')
            self.done(child.number)
            self.under(child.number, 3, pair.support)
            self.emit_after(child.number, 3, f'request = {self.rate(flow, own, thing)}')
            return True

        self.under(number, 2, flow.support, flow.text, extra=leg)
        missing = [pair for pair in flow.together if pair.line not in self.state]
        if missing:
            raise Hand('a pair of a flow that stands on the flow line')
        self.defaults['a leg named by its target store (R-A5-12)'] += len(flow.together)

    def share(self, share, thing):
        """`share VAR limit RATE [order f, g]`: the limit is the `outflow.capacity` of the store, and the
        order its `outflow.allocation`; for a flow of several pairs the order names the leg that leaves
        the store. The lines go under the declaration of the store."""
        found = self.symbols.read(share.stock, thing)
        store = None
        if found is not None and found[0] == 'value' and found[2] == thing and '.' not in share.stock:
            node = self.symbols.nodes[thing]
            store = next(
                (m for m in node.members if isinstance(m, nodes.Value) and m.name == share.stock), None
            )
        if store is None or self.state.get(store.line) != 'done':
            raise Hand('share: the store is declared in another thing, after its share, or by hand')
        declared = self.symbols.nodes[self.symbols.declarer(thing)]
        flows = {m.name: m for m in declared.members if isinstance(m, nodes.Flow)}
        names = []
        for name, _ in share.serve or ():
            if name not in flows:
                raise Hand('share: its order names something that is no flow of the thing')
            path = self.end(name, thing)
            if flows[name].together is not None:
                legs = [
                    leg
                    for pair, leg in zip(
                        flows[name].together, self.leg_names(flows[name], thing), strict=True
                    )
                    if pair.source == share.stock
                ]
                if len(legs) != 1:
                    raise Hand(
                        'share: its order names a flow of several pairs with no one leg from the store'
                    )
                path = f'{path}.{legs[0]}'
            names.append(path)
        limit = self.expr(share.limit.expr, thing, draws=False)
        literal = oldmodel_literal(share.limit.expr.tokens)
        self.anchor = self.end_of(store.line) + 0.3
        try:
            capacity = limit if literal else f'formula({limit})'
            self.emit(share.line, 2, f'outflow.capacity = {capacity}{self.cites(share.support)}')
            self.done(share.line)
            self.under(share.line, 3, share.support, share.text)
            if names:
                self.emit(share.line, 2, f'outflow.allocation = priority({", ".join(names)})')
        finally:
            self.anchor = None

    # ---- events -----------------------------------------------------------------------------------------

    def event(self, event, thing):
        number = event.line
        if not self.events:
            raise Hand('an event')
        if event.each or event.keep is not None:
            raise Hand('an event with a window or a `while`')
        if event.after is not None and not event.once:
            raise Hand(
                'an event that waits and can trigger again: the old language keeps one firing that waits, '
                'and the new one starts an occurrence at each trigger'
            )
        outcomes = event.outcomes
        several = len(outcomes) > 1 or event.choice
        scope = self.scope(thing)
        when = show(self.tree(event.when, thing)) if event.when is not None else None
        delay = show(self.tree(event.after, thing)) if event.after is not None else '0 h'
        guard = None
        if not several and outcomes:
            only = outcomes[0]
            if only.chance is not None and not only.is_else:
                # One outcome whose chance is a condition happens only when it holds: a guard on the
                # stage. Its old reading failed the run when it did not hold.
                guard = show(self.tree(only.chance, thing))
            elif only.is_else or only.when is not None:
                raise Hand('an event whose one outcome has a condition of when it can happen')
        selector = self.selector(event, thing) if several else None
        bodies = {}
        for outcome in outcomes:
            bodies[outcome.name] = self.body(outcome, thing, scope)
        if selector is not None and selector[0] == 'choice':
            self.emit(number - 0.5, 1, f'{selector[1]} = {selector[2]}')
            self.defaults['a choice: a field `forecast`, a local `order` and a switch (change 15)'] += 1
        self.emit(number, 1, f'{event.name} = event():{self.cites(event.support)}')
        self.done(number)
        outcome_lines = {outcome.line: outcome for outcome in outcomes if outcome.line != number}

        def inner(child):
            first = child.first
            if first.is_name('role') and len(child.tokens) == 2:
                # An event has no role in the language of now.
                self.emit(
                    child.number, 2, f'# role {child.tokens[1].value}: an event has no role now', raw=True
                )
                self.done(child.number)
                self.dropped['the role of an event'] += 1
                return True
            if first.is_name('choice') and len(child.tokens) == 1:
                self.done(child.number)
                return True
            if child.number in outcome_lines:
                return True  # written with the stage
            return any(child.number == line.line for outcome in outcomes for line in outcome.lines)

        self.under(number, 2, event.support, event.text, extra=inner)
        self.anchor = self.end_of(number) + 0.25
        try:
            if selector is not None and selector[3]:
                self.emit(number, 2, selector[3])
            if when is not None:
                self.emit(number, 2, fit(2, 'when ', when, ':'))
                self.emit(number, 3, f'this.{event.name}.start()')
                if event.once:
                    self.emit(number, 3, 'reset when false')
            if selector is not None:
                self.emit(number, 2, f'after {delay}:')
                if selector[4]:
                    target, _, value = selector[4].partition(' = ')
                    self.emit(number, 3, fit(3, f'{target} = ', value, ''))
                self.emit(number, 3, f'switch {selector[5]}:')
                for outcome in outcomes:
                    self.case(outcome, bodies[outcome.name], selector[6][outcome.name], thing)
            elif outcomes and (bodies[outcomes[0].name] or guard is not None):
                only = outcomes[0]
                self.emit(number, 2, f'after {delay}' + (f' when {guard}' if guard else '') + ':')
                if only.line != number:
                    self.outcome_lines(only, 3, cites_row=True)
                for row in bodies[only.name]:
                    self.emit(number, 3, row)
            elif event.after is not None:
                # A delay with no line: the occurrence waits, and marks the moment when it ends.
                self.emit(number, 2, f'after {delay}')
            for outcome in outcomes:
                for line in outcome.lines:
                    self.done_block(line.line)
        finally:
            self.anchor = None

    def selector(self, event, thing):
        """How the outcome of an event with several is chosen: ('choice' | 'chance' | 'condition', the
        name of the forecast field, its value, the local of the occurrence, the line that sets it, the
        selector of the switch, {outcome: case member})."""
        outcomes = event.outcomes
        members = {outcome.name: exprs.member_of(outcome.name) for outcome in outcomes}
        listed = ', '.join(members[outcome.name] for outcome in outcomes)
        if any(outcome.when is not None for outcome in outcomes):
            raise Hand('an outcome that can happen only under a condition: a guard on its case')
        numbers = [
            outcome
            for outcome in outcomes
            if outcome.chance is not None and oldmodel_literal(outcome.chance.tokens)
        ]
        if event.choice or len(numbers) == len([o for o in outcomes if not o.is_else]):
            weights = chances(outcomes)
            spelled = ', '.join(f'{members[name]}: {weight}' for name, weight in weights)
            if event.choice:
                info = self.symbols.things[self.symbols.declarer(thing)]
                field = 'forecast' if 'forecast' not in info.values else f'{event.name}_forecast'
                first = members[outcomes[0].name]
                return (
                    'choice',
                    field,
                    f'categorical({spelled})',
                    f'order: enum[{listed}] = {first}',
                    f'order = this.{field}.draw()',
                    'order',
                    members,
                )
            return ('chance', None, None, None, None, f'categorical({spelled}).draw()', members)
        # By condition: the outcome whose condition holds, the `else` one, or the last one.
        rest = [outcome for outcome in outcomes if not outcome.is_else]
        last = next((outcome for outcome in outcomes if outcome.is_else), rest[-1])
        conditional = members[last.name]
        for outcome in reversed([outcome for outcome in rest if outcome is not last]):
            if outcome.chance is None:
                raise Hand('an outcome with no chance beside others: two outcomes that always happen')
            tree = self.tree(outcome.chance, thing)
            if not self.condition(tree, thing):
                raise Hand(
                    'an outcome whose chance is an expression: categorical() takes numbers written in place'
                )
            test = show(tree, 1)
            conditional = f'{members[outcome.name]} if {test} else {conditional}'
        first = members[outcomes[0].name]
        return (
            'condition',
            None,
            None,
            f'outcome: enum[{listed}] = {first}',
            f'outcome = {conditional}',
            'outcome',
            members,
        )

    def condition(self, tree, thing):
        """Whether a chance is a condition (1 when it holds, else 0) and no number."""
        if tree[0] in ('cmp', 'bool') or (tree[0] == 'un' and tree[1] == 'not') or tree[0] == 'in':
            return True
        if tree[0] == 'name' and tree[1] in ('true', 'false'):
            return True
        if tree[0] == 'name':
            found = self.symbols.read(tree[1].removeprefix('this.'), thing)
            return found is not None and found[0] == 'value' and found[1] in ('var.bool', 'input.bool')
        return False

    def body(self, outcome, thing, scope):
        """The translated lines of an outcome. The old language reads every value of an outcome from
        before the outcome; a stage of the new one reads what its earlier lines wrote, so a line that
        reads what an earlier line of the outcome wrote is left for a person."""
        rows, written = [], set()
        for line in outcome.lines:
            value = line.value if isinstance(line, nodes.Assign) else getattr(line, 'amount', None)
            if value is not None:
                for name in exprs.names_of(old_names(value)):
                    found = self.symbols.read(name, thing)
                    if found is not None and found[0] == 'value' and (found[2], found[3]) in written:
                        raise Hand(
                            f'a line of the event reads {name}, which an earlier line of the same outcome sets: '
                            'the old language reads the value from before the outcome'
                        )
            rows.append(self.statement(line, thing, scope))
            targets = [line.target] if isinstance(line, nodes.Assign) else []
            targets += [line.source, line.target] if isinstance(line, nodes.Move) else []
            for target in targets:
                found = self.symbols.read(target, thing)
                if found is not None and found[0] == 'value':
                    written.add((found[2], found[3]))
        return rows

    def outcome_lines(self, outcome, depth, cites_row=False):
        """The text, records and role of an outcome written by its name, under its case or its stage.
        With `cites_row`, the records that its line cites go on a row of their own: a stage's line
        takes none."""
        self.done(outcome.line)
        if cites_row and self.cites(outcome.support):
            self.emit(outcome.line, depth, self.cites(outcome.support).strip())
        for child in self.children(outcome.line):
            if child.number in self.state:
                continue
            first = child.first
            if first.is_name('role') and len(child.tokens) == 2:
                self.emit(
                    child.number, depth, f'# role {child.tokens[1].value}: a case has no role now', raw=True
                )
                self.done(child.number)
                self.dropped['the role of an outcome'] += 1
            elif first.kind == 'text':
                self.verbatim(child.number, depth)
            elif first.kind == 'at':
                records = [
                    item
                    for item in outcome.support
                    if isinstance(item, nodes.Record)
                    and evidence_place(item.place) is not None
                    and item.line == child.number
                ]
                if records:
                    self.record_in_place(child.number, depth, records[0])
                else:
                    self.verbatim(child.number, depth)

    def case(self, outcome, rows, member, thing):
        """One case of the switch of an event with outcomes: its member, then the outcome's text, records
        and lines. A case needs an action, so an outcome with no line is left for a person."""
        if not rows:
            self.hand(outcome.line, 4, f'the case {member} has no action, and a case of a switch needs one')
            return
        cites = self.cites(outcome.support)
        self.emit(outcome.line, 4, f'{member}:{cites}')
        self.outcome_lines(outcome, 5)
        for row in rows:
            self.emit(outcome.line, 5, row)

    def statement(self, line, thing, scope):
        if isinstance(line, nodes.Assign):
            target, found = scope.path(line.target)
            kind = found[1] if found[0] == 'value' else None
            if kind == 'input.text':
                value = quoted(line.value.tokens[0].value)
            else:
                value = show(with_new_units(exprs.rewrite_old(line.value, scope)))
            return f'{target} {line.op} {value}'
        if isinstance(line, nodes.Move):
            amount = show(with_new_units(exprs.rewrite_old(line.amount, scope)))
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
            under = [s for s in status.support if evidence_place(s.place) is not None]
            self.under(number, 2, under, case.text)

    def check(self, check, thing=None):
        number = check.line
        depth = 0 if thing is None else 1
        scope = self.scope(thing)
        if check.kind == 'conserve':
            terms = []
            for term, _ in check.terms:
                path, found = scope.path(term)
                terms.append(
                    ('call', 'sum', [('name', path)]) if found[0] == 'value' and found[4] else ('name', path)
                )
            total = with_new_units(exprs.rewrite_old(check.total, scope))
            within = with_new_units(exprs.rewrite_old(check.within.expr, scope))
            left = terms[0]
            for term in terms[1:]:
                left = ('bin', '+', left, term)
            head = f'assert {show(("in", left, ("bin", "-", total, within), ("bin", "+", total, within)))}'
        else:
            if check.within is not None:
                raise Hand('`assert C within TOL` that is no sum: write the interval by hand')
            head = fit(depth, 'assert ', self.expr(check.expr, thing), self.cites(check.support))
            head = head.removesuffix(self.cites(check.support)) if self.cites(check.support) else head
        self.emit(number, depth, head + self.cites(check.support))
        self.done(number)
        self.under(number, depth + 1, check.support, check.text)

    def output(self, output, thing=None):
        """An output is a named formula (D10), never negative unless it was `signed`. An output with no
        estimate has no declaration (D4): its label, reason and lines go into the notes."""
        number = output.line
        depth = 0 if thing is None else 1
        lines = output.lines
        name = output.name
        if thing is not None and self.symbols.things[thing].values.get(name, 'output') != 'output':
            raise Hand(f'an output named as the field {name} of its thing')
        keys = [*self.owner_keys(thing), name]
        if lines.unestimated is not None:
            cites = self.all_cites(lines.support)
            if lines.text is not None:
                self.note('not_estimated', [*keys, 'label'], quoted(text_of(lines.text)))
            records = [item for item in lines.support if isinstance(item, nodes.Record)]
            self.note(
                'not_estimated',
                [*keys, 'reason'],
                quoted(text_of(lines.unestimated)),
                cites,
                record_rows(records),
            )
            self.reporting(lines, keys, number, thing)
            for k in self.block(number):
                self.state.setdefault(k, 'done')
            self.dropped['an output with no estimate: into the notes (D4)'] += 1
            return
        if output.type is None:
            raise Hand('an output with no unit')
        bounds = '' if lines.signed else ' in [0,]'
        distinct = self.cites(lines.distinct.support) if lines.distinct is not None else ''
        head = f'{name}: formula({unit_of(output.type)}) = formula({self.expr(output.expr, thing)}){bounds}'
        self.emit(number, depth, head + self.cites(lines.support) + distinct)
        self.done(number)
        self.reporting(lines, keys, number, thing)
        if lines.distinct is not None:
            # Its records stay on the formula: they say why the groups that it adds are disjoint.
            self.done(lines.distinct.line)
            self.under(lines.distinct.line, depth + 1, lines.distinct.support)
        self.under(number, depth + 1, lines.support, lines.text)

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
        member = self.renamed(head, member)
        if (self.symbols.declarer(head), setting.target.rpartition('.')[2]) in self.started:
            member += '_start'
        target = f'{head}.instances.{member}' if head in self.symbols.templates else f'{head}.{member}'
        if kind == 'input.text':
            value = quoted(setting.value.tokens[0].value)
        else:
            if not oldmodel_literal(setting.value.tokens):
                # An option gives an input a constant of its type (D2, `semantic.constant`).
                raise Hand('an option sets a value that is a calculation: an option gives a constant now')
            value = self.expr(setting.value, head, own='' if head in self.symbols.templates else f'{head}.')
        self.emit(setting.line, 2, f'{target} = {value}{self.cites(setting.support)}')
        self.done(setting.line)
        self.under(setting.line, 3, setting.support)

    def runs(self):
        number = self.file.lines[self.file.runs_place]
        self.verbatim(number)
        for run in self.file.runs:
            names = ' + '.join(quoted(name) for name in run.profiles)
            self.emit(run.line, 1, f'{run.name} = {names}')
            self.done(run.line)
            if run.versus is not None:
                # D9: a comparison is the scenario's own, outside the model; the pair stays in the notes.
                self.note('comparisons', [run.name], run.versus)
                self.dropped['versus: into the notes (D9)'] += 1
            if run.text is not None:
                self.verbatim(run.text.line)

    def notes(self):
        """Notes keep their form. A record in place with an ID moves its ID to a line of its own."""
        start = self.file.lines[('notes:',)]
        self.verbatim(start)

        def walk(items, depth):
            for note in items:
                self.verbatim(note.line)
                placed = {item.line: item for item in note.support if isinstance(item, nodes.Record)}
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

    def extra_notes(self):
        """The notes that the script adds (`note`), after the file's own notes, or in a `notes:` block of
        their own at the end of the file."""
        if not self.extra:
            return
        if self.file.notes is not None:
            where = self.logical[self.block(self.file.lines[('notes:',)])[-1]].end + 0.5
        else:
            where = len(self.rows) + 1
        self.anchor = where
        try:
            if self.file.notes is None:
                self.emit(where, 0, '')
                self.emit(where, 0, 'notes:')
            for top in ('reporting', 'not_estimated', 'comparisons', 'titles', 'roles'):
                items = self.extra.get(top)
                if not items:
                    continue
                self.emit(where, 1, f'{top}:')
                written = set()
                for keys, value, cites, rows in items:
                    for k in range(len(keys) - 1):
                        if keys[: k + 1] not in written:
                            written.add(keys[: k + 1])
                            self.emit(where, 2 + k, f'{keys[k]}:')
                    self.emit(where, 1 + len(keys), f'{keys[-1]}: {value}{cites}')
                    for depth, row in rows:
                        self.emit(where, 2 + len(keys) + depth, row)
        finally:
            self.anchor = None

    def record(self, record):
        number = record.line
        if record.id is None:
            for k in self.block(number):
                self.verbatim(k)
            return
        self.emit(number, 0, f'record {record.name}: {record.kind} {quoted(record.text)}')
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
        return '\n'.join(rows) + '\n', {
            'logical': len(self.logical),
            'done': counts['done'],
            'todo': counts['todo'],
            'missed': missing,
            'why': dict(self.why),
            'dropped': dict(self.dropped),
            'defaults': dict(self.defaults),
        }


# Words that a leg cannot be named by (`napkin/model/language/parse.py`, RESERVED).
RESERVED = frozenset(
    [
        'true',
        'false',
        'this',
        't',
        'none',
        'and',
        'or',
        'not',
        'if',
        'else',
        'in',
        'is',
        'from',
        'to',
        'when',
        'after',
        'until',
        'reset',
        'switch',
        'move',
        'assert',
        'flow',
        'record',
        'readonly',
        'input',
        'formula',
        'event',
        'solver',
        'enum',
        'bool',
        'scale',
    ]
)


def chances(outcomes):
    """[(outcome, weight)] of outcomes whose chances are numbers, with `else` as 1 less the others,
    each a number written in place (a categorical's weights are, in the language of now)."""
    given = {
        outcome.name: Decimal(literal_text(outcome.chance))
        for outcome in outcomes
        if not outcome.is_else and outcome.chance is not None
    }
    rest = Decimal(1) - sum(given.values(), Decimal(0))
    out = []
    for outcome in outcomes:
        weight = rest if outcome.is_else else given.get(outcome.name, Decimal(1))
        out.append((outcome.name, format(weight.normalize(), 'f')))
    return out


def record_rows(records):
    """[(depth, text)] of records in place: `@kind "explanation"`, the ID that it names on a line of its
    own (R-A5-02), and its claims with their data."""
    rows = []
    for record in records:
        rows.append((0, f'@{record.kind} {quoted(record.text)}'))
        if record.id is not None:
            rows.append((1, f'{id_label(record.kind)} {record.id}'))
        if record.claims:
            rows.append((1, 'claims:'))
            for claim in record.claims:
                rows.append((2, claim.id))
                if claim.datum:
                    rows.append((3, f'datum: {claim.datum}'))
    return rows


def literal_text(expr):
    tree = exprs.old_tree(expr)
    if tree[0] != 'num':
        raise Hand('a chance that is no number')
    return tree[1]


def text_of(node):
    """The words of an old text node."""
    value = node.value
    return ' '.join(value) if isinstance(value, list) else value


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


def evidence_place(place):
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
    """What the ID of a record names (docs/language.md, 2.10, at 8488047): a convention of the
    library for a `convention` record, an assumption for a record of any other kind."""
    return 'convention' if kind == 'convention' else 'assumption'


# ---- the files of a package, and the compile ------------------------------------------------------------


def package_of(path):
    """The folder of the package (or of the example) that holds a model file at the base commit."""
    relative = Path(path).resolve().relative_to(BASE.resolve())
    return BASE / Path(*relative.parts[:2])


def copy_support(package):
    """Copy what the compiler reads beside the model files of a package into `translated/now/`: each
    `units.json` and `evidence/` of the package and of its variants, and the catalogue's library."""
    relative = package.relative_to(BASE)
    for folder in [package, *sorted((package / 'variants').glob('*'))]:
        target = OUT / relative / folder.relative_to(package)
        if (folder / 'units.json').is_file():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(folder / 'units.json', target / 'units.json')
        if (folder / 'evidence').is_dir():
            shutil.copytree(folder / 'evidence', target / 'evidence', dirs_exist_ok=True)
    library = BASE / 'scenarios' / 'library'
    if relative.parts[0] == 'scenarios' and library.is_dir():
        shutil.copytree(library, OUT / 'scenarios' / 'library', dirs_exist_ok=True)


def entries(written):
    """The entry files among the translated files: each variant, and a package's main file when the
    package has no variant (its main file then builds no model of its own)."""
    found = []
    for path in written:
        if path.name != 'model.scn':
            continue
        if path.parent.parent.name == 'variants' or not (path.parent / 'variants').is_dir():
            found.append(path)
    return sorted(found)


def unspellable_units(packages):
    """[(file, unit, its spelling now, its parts that are no unit)] of the units that the prelude, the
    catalogue's library and the `units.json` of `packages` declare under a composed name: the
    language of now composes a unit of its parts (D12), so each part must be a unit too."""
    files = [BASE / 'napkin' / 'std' / 'units.json', BASE / 'scenarios' / 'library' / 'vocabulary.json']
    for package in sorted(packages):
        files += sorted(package.rglob('units.json'))
    declared = {}
    for file in files:
        if file.is_file():
            found = json.loads(file.read_text(encoding='utf-8'))
            for name in found.get('units', found):
                declared.setdefault(name, file.relative_to(BASE).as_posix())
    out = []
    for name, file in declared.items():
        spelled = new_unit(name)
        parts = [part.strip() for piece in spelled.split('/') for part in piece.split('*')]
        missing = [part for part in parts if part not in declared and part != '1']
        if missing:
            out.append((file, name, spelled, missing))
    return out


def compile_all(paths):
    """The compile of each entry file by the compiler of now, in a process without the old compiler
    (`newmodel.py --compile`): {entry: result}."""
    environment = {key: value for key, value in __import__('os').environ.items() if key != 'PYTHONPATH'}
    done = subprocess.run(
        [PYTHON, str(HERE / 'newmodel.py'), '--compile', *map(str, paths)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
        cwd=HERE,
    )
    if done.returncode != 0:
        raise SystemExit(f'newmodel.py --compile failed:\n{done.stderr}')
    return json.loads(done.stdout)


def main(argv):
    events = '--no-events' not in argv
    to_stdout = '--stdout' in argv
    do_compile = '--compile' in argv
    paths = []
    for arg in argv:
        if arg.startswith('--'):
            continue
        path = Path(arg)
        path = path if path.is_absolute() else BASE / path
        paths += sorted(p for p in path.rglob('*.scn') if 'tests' not in p.parts) if path.is_dir() else [path]
    every = not paths
    if every:
        paths = oldmodel.model_files()
    total, why, dropped, defaults = (
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
    )
    rows, written, packages = [], [], set()
    for path in paths:
        translator = Translator(path, events=events)
        text, counts = translator.translate()
        relative = path.resolve().relative_to(BASE.resolve())
        if to_stdout:
            sys.stdout.write(text)
            continue
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
        written.append(target)
        packages.add(package_of(path))
        share = counts['done'] / counts['logical'] if counts['logical'] else 1.0
        rows.append(
            (
                relative.as_posix(),
                counts['logical'],
                counts['done'],
                counts['todo'],
                len(counts['missed']),
                share,
            )
        )
        total.update({key: counts[key] for key in ('logical', 'done', 'todo')})
        why.update(counts['why'])
        dropped.update(counts['dropped'])
        defaults.update(counts['defaults'])
        if counts['missed']:
            print(f'  {relative}: lines that the script lost: {counts["missed"][:8]}', file=sys.stderr)
    if to_stdout:
        return 0
    for package in sorted(packages):
        copy_support(package)
    width = max(len(row[0]) for row in rows)
    print(f'{"file":{width}}  lines  translated  left  share')
    for name, logical, done, todo, missed, share in rows:
        print(
            f'{name:{width}}  {logical:5d}  {done:10d}  {todo:4d}  {share:5.1%}'
            + (f'  ({missed} lost)' if missed else '')
        )
    if len(rows) > 1:
        print(
            f'{"all":{width}}  {total["logical"]:5d}  {total["done"]:10d}  {total["todo"]:4d}  {total["done"] / total["logical"]:5.1%}'
        )
    for title, counter in (
        ('lines left for a person, by reason', why),
        ('what the language of now has no place for', dropped),
        ('names and forms that the script chose', defaults),
    ):
        if counter:
            print(f'\n{title}:')
            for reason, n in counter.most_common():
                print(f'  {n:5d}  {reason}')
    print(f'\nwrote {OUT}')
    missing = unspellable_units(packages)
    if missing:
        print(f'\nunits declared under a composed name whose parts are no unit ({len(missing)}):')
        for file, name, spelled, parts in missing:
            print(
                f'  {file}: {name} is {spelled} now, and {", ".join(parts)} {"is" if len(parts) == 1 else "are"} no unit'
            )
    if not do_compile:
        return 0
    status = 0
    print('\nthe compile of each entry file by the compiler of now:')
    for entry, found in compile_all(entries(written)).items():
        name = Path(entry).relative_to(OUT).as_posix()
        warnings = collections.Counter(item['code'] for item in found['reports'])
        if found['ok']:
            print(f'  {name}: compiles; warnings {dict(warnings) or "none"}')
            continue
        status = 1
        codes = collections.Counter(item['code'] for item in found['problems'])
        print(f'  {name}: refused, {len(found["problems"])} problems: {dict(codes.most_common())}')
        for item in found['problems'][:12]:
            print(f'      {item["code"]:14s} {item["file"]}:{item["line"]}  {item["message"][:150]}')
    return status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
