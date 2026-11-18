#!/usr/bin/env python
"""Task 5 of brief A5: `check.py OLD NEW` compares a translation with its old file, by meaning.

    PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python check.py OLD.scn NEW.scn

OLD is read with the old parser and, for what the old compiler proved, with the old compiler. NEW is
read with a simple reader of the new notation (`newreader.py`). The check fails (exit 1) when:

1. a number with its unit, or a text, of the old file is not in the new one;
2. a name changes its kind: an input, a fixed value, a formula, a named state, a store (a stock), an
   accumulated tally (a stock that flows only fill), a number state, a link, an output; or its unit;
3. an expression of the old file is not the expression that the new file writes at the same place,
   once each name is written as the new language writes it (formulas, start values, defaults, ranges,
   rates, conditions, the lines of events, options, checks);
4. an output that the old compiler proved cumulative is not marked `cumulative` in `report:`, or is
   built from accumulated tallies in the old file and from something that can fall in the new one.

It lists each output that the old compiler proved cumulative: the new compiler must prove that each
of them never falls.

Options: `--model ENTRY.scn` names the entry file whose compiled model gives the proofs (default: the
entry file of OLD, or for a module the main file of its package, or else its first variant).
`--no-compile` leaves the old compiler out. `--quiet` prints the verdict only.
"""

from __future__ import annotations

import collections
import dataclasses
import sys
from pathlib import Path

import exprs
import newreader
import oldmodel
from exprs import Hand, Scope, canonical, show
from newreader import Event, Facts, Flow, Value, normal_text
from oldmodel import BASE, lex, nodes

ZERO = ('num', '0', None)
NONE = ('none',)


# ---- the facts of the old file ---------------------------------------------------------------------------


class Old:
    """The facts of an old file, with each expression as the new language writes it."""

    def __init__(self, path):
        self.source = Path(path)
        self.file, self.files, self.symbols, self.kinds = oldmodel.model_of(self.source)
        self.facts = Facts()
        self.problems = []  # what the old file holds that the mechanical rules do not translate
        self.outputs = {o.name for file in self.files for o in file.outputs}
        self.overrides = set()
        for file in self.files:
            for thing in file.things:
                if thing.template is not None:
                    for member in thing.members:
                        if isinstance(member, nodes.Change) and member.kind is not None:
                            self.overrides.add((thing.template, member.name))
        self.proven_paths = {}

    def scope(self, thing, own='this.'):
        return Scope(self.symbols, thing, self.outputs, own=own)

    def tree(self, expr, thing, draws=True, own='this.'):
        try:
            return exprs.rewrite_old(expr, self.scope(thing, own), draws)
        except Hand as reason:
            self.problems.append((expr.line, str(reason)))
            return ('name', f'<by hand: line {expr.line}>')

    def path(self, name, thing):
        try:
            return self.scope(thing).path(name)[0]
        except Hand as reason:
            self.problems.append((0, str(reason)))
            return name

    def build(self):
        f = self.facts
        file = self.file
        block = file.scenario
        if block is not None:
            f.scenario['role'] = 'scenario' if block.role == 'main' else 'variant'
            if block.horizon is not None:
                f.scenario['horizon'] = self.tree(block.horizon, None, draws=False)
            if block.resolution is not None:
                f.scenario['resolution'] = self.tree(block.resolution, None, draws=False)
            if block.timescales is not None:
                f.scenario['timescales'] = [self.tree(item, None, draws=False) for item in block.timescales]
        f.uses = [use.name for use in file.uses]
        for thing in [*file.things, *file.changes]:
            self.thing(thing)
        for check in file.checks:
            f.asserts.setdefault(None, []).append(self.check(check, None))
        for output in file.outputs:
            self.output(output, None)
        for group in file.profiles:
            for option in group.profiles:
                settings = f.options.setdefault((group.name, option.name), {})
                for setting in option.settings:
                    target, tree = self.setting(setting)
                    settings[target] = tree
        for run in file.runs:
            f.runs[run.name] = list(run.profiles)
        for record in file.records:
            claims = [(claim.id, claim.datum) for claim in record.claims]
            f.records[record.name] = (record.kind, record.id, normal_text(record.text), claims)
        self.notes(file.notes or [], 1)
        self.texts_and_numbers()
        return f

    def notes(self, items, depth):
        for note in items:
            self.facts.notes.append((depth, note.key))
            self.notes(note.under, depth + 1)

    # ---- things -----------------------------------------------------------------------------------------

    def thing(self, thing):
        f = self.facts
        name = thing.name
        f.things.setdefault(name, {'template': thing.template, 'line': thing.line})
        if thing.sees is not None:
            f.sees[name] = [self.path(fact, name) for fact, _ in thing.sees]
        for member in thing.members:
            if isinstance(member, nodes.Value):
                self.value(member, name)
            elif isinstance(member, nodes.LinkDecl):
                target = f'<{member.target}>' if member.many else member.target
                f.values[(name, member.name)] = Value(name, member.name, 'link', line=member.line, target=target)
            elif isinstance(member, nodes.LinkBind):
                if thing.template is not None or thing.kind == 'change':
                    f.instance_lines[(name, member.name)] = self.link(member)
                else:
                    f.values[(name, member.name)] = Value(
                        name, member.name, 'link', line=member.line, target=self.link(member)
                    )
            elif isinstance(member, nodes.Change):
                self.instance_line(member, name)
            elif isinstance(member, nodes.Flow):
                self.flow(member, name)
            elif isinstance(member, nodes.Allocate):
                f.capacities[(name, member.stock)] = self.tree(member.limit.expr, name, draws=False)
                if member.serve is not None:
                    f.allocations[(name, member.stock)] = (
                        'call',
                        'priority',
                        [('name', self.path(flow, name)) for flow, _ in member.serve],
                    )
            elif isinstance(member, nodes.Event):
                self.event(member, name)
            elif isinstance(member, nodes.Check):
                f.asserts.setdefault(name, []).append(self.check(member, name))
            elif isinstance(member, nodes.Output):
                self.output(member, name)
            elif isinstance(member, nodes.Status):
                f.statuses[name] = [
                    (case.status, self.tree(case.condition, name) if case.condition is not None else None)
                    for case in member.lines
                ]

    def link(self, member):
        if member.many:
            return ('coll', [('name', target) for target in member.targets])
        if member.targets in self.symbols.templates:
            return ('name', f'{member.targets}.instances')
        return ('name', member.targets)

    def value(self, value, thing):
        f = self.facts
        kind = oldmodel.field_kind(value)
        unit = value.type if isinstance(value.type, str) and value.type != 'bool' else None
        made = Value(thing, value.name, kind, unit=unit, line=value.line)
        if kind == 'input.text':
            made.expr = ('text', value.value.tokens[0].value)
        else:
            made.expr = self.tree(value.value, thing)
        if isinstance(value.type, list):
            try:
                made.members = tuple(exprs.member_of(v) for v in value.type)
            except Hand as reason:
                self.problems.append((value.line, str(reason)))
        if value.min is not None:
            made.range = (
                self.tree(value.min.expr, thing, draws=False),
                self.tree(value.max.expr, thing, draws=False),
            )
        elif kind == 'var.number' and self.kinds.get((self.symbols.declarer(thing), value.name)) == 'stock':
            # A stock of the old language never goes below zero: the new file writes the bound.
            made.range = (ZERO, NONE)
        if value.size is not None:
            made.scale = self.tree(value.size.expr, thing, draws=False)
        if kind == 'let.fixed' and (thing, value.name) in self.overrides:
            made.kind = 'let.formula'  # an instance gives it a formula, so the template declares one
        f.values[(thing, value.name)] = made
        if value.output is not None:
            self.report(value.output, self.report_path(thing, value.name), thing)

    def report_path(self, thing, name):
        if thing is None:
            return name
        if thing in self.symbols.templates:
            return f'{thing}.instances.{name}'
        return f'{thing}.{name}'

    def report(self, lines, path, thing):
        flags = {'cumulative': lines.measure != 'level' and lines.unestimated is None, 'lag': None}
        if lines.lag is not None:
            own = f'{thing}.' if thing is not None else ''
            delays = [self.tree(d, thing, draws=False, own=own) for d in lines.lag.delays]
            flags['lag'] = delays[0] if lines.lag.kind == 'fixed' else ('call', lines.lag.kind, delays)
        self.facts.report[path] = flags

    def instance_line(self, change, thing):
        lines = change.lines
        if lines.value is None:
            return
        found = self.symbols.read(change.name, thing)
        kind = found[1] if found is not None and found[0] == 'value' else None
        if kind == 'input.text':
            tree = ('text', lines.value.tokens[0].value)
        else:
            tree = self.tree(lines.value, thing)
        if change.kind is not None:
            tree = ('call', 'formula', [tree])
        self.facts.instance_lines[(thing, change.name)] = tree

    # ---- flows and events -------------------------------------------------------------------------------

    def end(self, name, thing):
        return 'SOURCE/SINK' if name == 'outside' else self.path(name, thing)

    def flow(self, flow, thing):
        rate = self.tree(flow.rate.expr, thing)
        keep = self.tree(flow.keep.expr, thing) if flow.keep is not None else None
        made = Flow(thing, flow.name, line=flow.line)
        pairs = [flow.pair] if flow.together is None else flow.together
        for pair in pairs:
            own = self.tree(pair.rate.expr, thing) if pair.rate is not None else rate
            if keep is not None:
                own = ('if', keep, own, ZERO)
            source = 'SOURCE' if pair.source == 'outside' else self.path(pair.source, thing)
            sink = 'SINK' if pair.target == 'outside' else self.path(pair.target, thing)
            made.legs.append((None, source, sink, own, None))
        self.facts.flows[(thing, flow.name)] = made

    def statement(self, line, thing):
        scope = self.scope(thing)
        try:
            if isinstance(line, nodes.Assign):
                target, found = scope.path(line.target)
                if found[0] == 'value' and found[1] == 'input.text':
                    value = ('text', line.value.tokens[0].value)
                else:
                    value = exprs.rewrite_old(line.value, scope)
                return ('set', line.op, target, value)
            if isinstance(line, nodes.Move):
                return (
                    'move',
                    exprs.rewrite_old(line.amount, scope),
                    scope.path(line.source)[0],
                    scope.path(line.target)[0],
                )
            if isinstance(line, nodes.Fire):
                return ('start', scope.path(line.target)[0], [])
        except Hand as reason:
            self.problems.append((line.line, str(reason)))
        return ('unknown', line.line)

    def event(self, event, thing):
        made = Event(thing, event.name, line=event.line, once=event.once)
        if event.when is not None:
            made.when = self.tree(event.when, thing)
        delay = self.tree(event.after, thing) if event.after is not None else ('num', '0', 'h')
        outcomes = event.outcomes
        simple = len(outcomes) <= 1 and not (
            outcomes and (outcomes[0].chance is not None or outcomes[0].is_else or outcomes[0].when is not None)
        )
        if simple:
            statements = [self.statement(line, thing) for line in (outcomes[0].lines if outcomes else ())]
            if statements or event.after is not None:
                made.stages.append((delay, None, statements))
        else:
            made.stages.append((delay, None, []))
            for outcome in outcomes:
                made.cases.append((outcome.name.upper(), [self.statement(line, thing) for line in outcome.lines]))
                if outcome.chance is not None:
                    made.selectors.append(self.tree(outcome.chance, thing))
                if outcome.when is not None:
                    made.selectors.append(self.tree(outcome.when, thing))
            made.locals['__choice__'] = event.choice
        self.facts.events[(thing, event.name)] = made

    # ---- checks, outputs, options -----------------------------------------------------------------------

    def check(self, check, thing):
        if check.kind != 'conserve':
            return self.tree(check.expr, thing)
        scope = self.scope(thing)
        terms = []
        for term, _ in check.terms:
            try:
                path, found = scope.path(term)
            except Hand as reason:
                self.problems.append((check.line, str(reason)))
                continue
            listed = found[0] == 'value' and found[4]
            terms.append(('call', 'sum', [('name', path)]) if listed else ('name', path))
        total = self.tree(check.total, thing)
        within = self.tree(check.within.expr, thing)
        left = terms[0]
        for term in terms[1:]:
            left = ('bin', '+', left, term)
        return ('in', left, ('bin', '-', total, within), ('bin', '+', total, within))

    def output(self, output, thing):
        lines = output.lines
        name = output.name
        if lines.unestimated is not None:
            made = Value(thing, name, 'none', unit=output.type, line=output.line, expr=NONE)
        else:
            made = Value(thing, name, 'let.formula', unit=output.type, line=output.line)
            made.expr = self.tree(output.expr, thing)
            if not lines.signed:
                made.range = (ZERO, NONE)
        self.facts.values[(thing, name)] = made
        self.report(lines, self.report_path(thing, name), thing)

    def setting(self, setting):
        head, _, member = setting.target.rpartition('.')
        found = self.symbols.read(setting.target, None)
        kind = found[1] if found is not None and found[0] == 'value' else None
        if head in self.symbols.templates:
            target, own = f'{head}.instances.{member}', ''
        else:
            target, own = setting.target, f'{head}.'
        if kind == 'input.text':
            return target, ('text', setting.value.tokens[0].value)
        return target, self.tree(setting.value, head, own=own)

    # ---- the texts and the numbers of the old file, as the file writes them ------------------------------

    def texts_and_numbers(self):
        f = self.facts
        file = self.file
        units = {}  # id of an expression -> the unit that its declaration gives a bare number
        text_values = set()  # ids of the expressions whose one token is a text value, not a named value

        def declare(value, thing):
            if value is None:
                return
            unit = value.type if isinstance(value.type, str) and value.type != 'bool' else None
            for part in (value.value, value.min and value.min.expr, value.max and value.max.expr, value.size and value.size.expr):
                if part is not None:
                    units[id(part)] = unit

        for thing in [*file.things, *file.changes]:
            for member in thing.members:
                if isinstance(member, nodes.Value):
                    declare(member, thing.name)
                    if oldmodel.field_kind(member) == 'input.text':
                        text_values.add(id(member.value))
                elif isinstance(member, nodes.Change) and member.lines is not None:
                    found = self.symbols.read(member.name, thing.name)
                    if found is not None and found[0] == 'value' and found[1] == 'input.text' and member.lines.value is not None:
                        text_values.add(id(member.lines.value))
                elif isinstance(member, nodes.Event):
                    for outcome in member.outcomes:
                        for line in outcome.lines:
                            if isinstance(line, nodes.Assign):
                                found = self.symbols.read(line.target, thing.name)
                                if found is not None and found[0] == 'value' and found[1] == 'input.text':
                                    text_values.add(id(line.value))
            for member in thing.members:
                if isinstance(member, nodes.Output):
                    units[id(member.expr)] = member.type
        for output in file.outputs:
            if output.expr is not None:
                units[id(output.expr)] = output.type
        for group in file.profiles:
            f.say(group.name)
            for option in group.profiles:
                f.say(option.name)
                for setting in option.settings:
                    found = self.symbols.read(setting.target, None)
                    if found is not None and found[0] == 'value' and found[1] == 'input.text':
                        text_values.add(id(setting.value))
        for run in file.runs:
            for name in run.profiles:
                f.say(name)
        seen = set()

        def walk(node):
            if isinstance(node, nodes.Text):
                values = node.value if isinstance(node.value, list) else [node.value]
                for value in values:
                    if isinstance(value, str):
                        f.say(value)
                return
            if isinstance(node, nodes.Record):
                f.say(node.text)
            if isinstance(node, nodes.Expr):
                if id(node) in seen:
                    return
                seen.add(id(node))
                if id(node) in text_values:
                    f.say(node.tokens[0].value)
                    return
                try:
                    tree = exprs.old_tree(node)
                except Hand:
                    return
                f.count(tree, units.get(id(node)))
                return
            if isinstance(node, nodes.Note) and isinstance(node.value, lex.Token) and node.value.kind == 'number':
                f.count(('num', node.value.value, None))
            if isinstance(node, nodes.Lag):
                for share in node.shares:
                    f.count(('num', share, None))
            if isinstance(node, nodes.Table):
                f.say(node.file)
            if dataclasses.is_dataclass(node) and not isinstance(node, type):
                for item in dataclasses.fields(node):
                    if item.name in ('lines', 'columns', 'place', 'keys'):
                        continue
                    walk(getattr(node, item.name))
            elif isinstance(node, (list, tuple)):
                for item in node:
                    walk(item)

        walk(file)
        # The lines of an instance and of an option give a bare number no unit, on both sides.

    # ---- what the old compiler proved ----------------------------------------------------------------------

    def proven(self, model_path=None):
        """({report path: the old compiler's name} of the outputs that the old compiler proved
        cumulative, the entry file that it built, or the reason that none was built)."""
        from napkin.model.model import build_model

        candidates = [Path(model_path)] if model_path else []
        if not candidates:
            entry = oldmodel.home_entry(self.source)
            candidates.append(entry)
            variants = sorted((entry.parent / 'variants').glob('*/model.scn')) if entry.parent.is_dir() else []
            candidates += variants
        reason = None
        for entry in candidates:
            try:
                model = build_model(entry)
            except Exception as exc:  # the main file of a package of templates builds no model
                reason = f'{type(exc).__name__}: {str(exc).splitlines()[0][:120]}'
                continue
            _, _, symbols, _ = oldmodel.model_of(entry)
            proved = set()
            for run in model.runs:
                proved |= set(model.resolve(run).proven_cumulative_outcomes)
            found = {}
            for name in sorted(proved):
                written = name.removesuffix('.output')
                head, _, member = written.rpartition('.')
                if not head:
                    path = member
                else:
                    declarer = symbols.declarer(head)
                    path = f'{declarer}.instances.{member}' if declarer != head else f'{head}.{member}'
                found.setdefault(path, []).append(name)
            # The kinds that the old compiler gives each number var, for a check of this script's own rule.
            whole = next(iter(model.whole.values()))
            compiled = {}
            rank = {'variable': 0, 'cumulative': 1, 'stock': 2}
            word = {'variable': 'state', 'cumulative': 'tally', 'stock': 'stock'}
            for name, q in whole.quantities.items():
                key = (symbols.declarer(q.entity), name[len(q.entity) + 1 :])
                if key not in compiled or rank[q.kind] > rank[compiled[key][0]]:
                    compiled[key] = (q.kind, word[q.kind])
            return found, entry, {key: value[1] for key, value in compiled.items()}
        return {}, None, reason


# ---- what a set of facts says of each number var --------------------------------------------------------


class Structure:
    """The names of a set of facts, and what its flows and events do to each number var."""

    def __init__(self, facts, declarer=None):
        self.facts = facts
        self.templates = {name for name, info in facts.things.items() if name[:1].isupper()}
        self.declarer_of = declarer or (lambda thing: facts.things.get(thing, {}).get('template') or thing)
        self.ends, self.drained = set(), set()
        self.adds = collections.defaultdict(list)  # (thing, member) -> the trees that events add to it
        self.sets = collections.defaultdict(list)  # (thing, member) -> the trees that events set or subtract
        for (thing, _), flow in facts.flows.items():
            for _, source, sink, _, _ in flow.legs:
                if source != 'SOURCE':
                    key = self.member(source, thing)
                    self.ends.add(key)
                    self.drained.add(key)
                if sink != 'SINK':
                    self.ends.add(self.member(sink, thing))
        for (thing, _), event in facts.events.items():
            statements = [s for _, _, body in event.stages for s in body]
            statements += [s for _, body in event.cases for s in body]
            for statement in statements:
                if statement[0] == 'move':
                    source, sink = self.member(statement[2], thing), self.member(statement[3], thing)
                    self.ends.update({source, sink})
                    self.drained.add(source)
                elif statement[0] == 'set':
                    key = self.member(statement[2], thing)
                    if statement[1] == '+=':
                        self.adds[key].append((statement[3], thing))
                    else:
                        self.drained.add(key)
                        self.sets[key].append((statement[3], thing))

    def member(self, path, thing):
        """(the thing that declares it, the member) of a path: `this.x`, `this.link.x`, `thing.x`,
        `Template.instances.x`."""
        parts = path.split('.')
        if parts[0] == 'this':
            owner, rest = thing, parts[1:]
        elif len(parts) >= 3 and parts[1] == 'instances':
            owner, rest = parts[0], parts[2:]
        elif len(parts) >= 2 and parts[0] in self.facts.things:
            owner, rest = parts[0], parts[1:]
        else:
            owner, rest = thing, parts
        owner = self.declarer_of(owner) if owner is not None else None
        while len(rest) > 1:
            link = self.facts.values.get((owner, rest[0]))
            target = self.link_target(link, owner, rest[0])
            if target is None:
                return (owner, '.'.join(rest))
            owner, rest = target, rest[1:]
        return (owner, rest[0] if rest else '')

    def link_target(self, link, owner, name):
        """The thing that declares the members that a link of `owner` reaches."""
        if link is None or link.kind != 'link':
            return None
        target = link.target
        if isinstance(target, str):
            return target.strip('<>')
        if isinstance(target, tuple):
            if target[0] == 'name':
                name_ = target[1].removesuffix('.instances')
                return self.declarer_of(name_)
            if target[0] == 'coll' and target[1]:
                return self.declarer_of(target[1][0][1]) if target[1][0][0] == 'name' else None
            if target[0] == 'method':
                inner = target[1]
                while inner[0] == 'method':
                    inner = inner[1]
                if inner[0] == 'name':
                    return inner[1].split('.')[0]
        return None

    def kind(self, key):
        """`stock`, `tally` or `state` of a number var, by the old compiler's rule."""
        if key not in self.ends:
            return 'state'
        return 'stock' if key in self.drained else 'tally'

    def value(self, path, thing):
        key = self.member(path, thing)
        return key, self.facts.values.get(key)

    # ---- signs and what never falls ---------------------------------------------------------------------

    def nonnegative(self, tree, thing, seen=frozenset()):
        """Whether this simple rule can say that a tree is never below zero."""
        tree = canonical(tree)
        kind = tree[0]
        if kind == 'num':
            value = exprs.number_value(tree[1])
            return value is not None and value >= 0
        if kind == 'name':
            if tree[1] in ('true', 'false', 't'):
                return True
            key, value = self.value(tree[1], thing)
            if value is None or key in seen:
                return False
            if value.kind == 'input.number':
                return value.range is not None and self.nonnegative(value.range[0], key[0], seen | {key})
            if value.kind == 'var.number':
                return self.kind(key) in ('stock', 'tally') or (
                    value.range is not None and self.nonnegative(value.range[0], key[0], seen | {key})
                )
            if value.kind in ('let.fixed', 'let.formula') and value.expr is not None:
                return self.nonnegative(value.expr, key[0], seen | {key})
            return False
        if kind == 'bin':
            if tree[1] in ('+', '*', '/'):
                return self.nonnegative(tree[2], thing, seen) and self.nonnegative(tree[3], thing, seen)
            if tree[1] == '-' and tree[2][0] == 'num' and tree[2][1] == '1':
                return self.share(tree[3], thing)
            return False
        if kind == 'call':
            name, args = tree[1], tree[2]
            if name == 'max':
                return any(self.nonnegative(arg, thing, seen) for arg in args)
            if name in ('min', 'sum'):
                return all(self.nonnegative(arg, thing, seen) for arg in args)
            if name == 'clip':
                return len(args) == 3 and self.nonnegative(args[1], thing, seen)
            return name in ('abs', 'exp', 'sqrt', 'count')
        if kind == 'if':
            return self.nonnegative(tree[2], thing, seen) and self.nonnegative(tree[3], thing, seen)
        if kind == 'method' and tree[2] == 'draw':
            return False
        return False

    def share(self, tree, thing):
        """Whether a tree is an input whose range lies in [0, 1], so that `1 - it` is never negative."""
        if tree[0] != 'name':
            return False
        key, value = self.value(tree[1], thing)
        if value is None or value.kind != 'input.number' or value.range is None:
            return False
        low, high = canonical(value.range[0]), canonical(value.range[1])
        if low[0] != 'num' or high[0] != 'num':
            return False
        return exprs.number_value(low[1]) >= 0 and exprs.number_value(high[1]) <= 1

    def fixed(self, tree, thing, seen=frozenset()):
        """Whether a tree reads only what a run never changes: inputs, fixed values, and formulas of
        them."""
        for name in exprs.names_of(tree):
            if name in ('true', 'false') or name.isupper():
                continue
            if name == 't':
                return False
            key, value = self.value(name, thing)
            if value is None or key in seen:
                return False
            if value.kind.startswith('input') or value.kind == 'let.fixed':
                continue
            if value.kind == 'let.formula' and value.expr is not None and self.fixed(value.expr, key[0], seen | {key}):
                continue
            return False
        return True

    def never_falls(self, tree, thing, seen=frozenset()):
        """(whether this simple rule can say that a tree never falls during a run, the reason when it
        cannot). The rule: an accumulated tally, or a number state that events only add to, never
        falls; neither does a sum of such values, their product with a fixed value that is never
        negative, or the largest or the smallest of them."""
        tree = canonical(tree)
        kind = tree[0]
        if kind == 'num':
            return True, None
        if kind == 'name':
            key, value = self.value(tree[1], thing)
            if value is None:
                return False, f'{tree[1]} names nothing that this script reads'
            if key in seen:
                return False, f'{tree[1]} reads itself'
            if value.kind.startswith('input') or value.kind == 'let.fixed':
                return True, None
            if value.kind == 'let.formula':
                if value.expr is None:
                    return False, f'{tree[1]} has no formula'
                ok, why = self.never_falls(value.expr, key[0], seen | {key})
                return ok, (None if ok else f'{tree[1]} is a formula: {why}')
            if value.kind == 'var.number':
                sort = self.kind(key)
                if sort == 'stock' or self.sets.get(key):
                    return False, f'{tree[1]} is a store that flows or events take from'
                for amount, where in self.adds.get(key, ()):
                    if not self.nonnegative(amount, where):
                        return False, f'an event adds {show(amount)} to {tree[1]}, which this rule cannot sign'
                return True, None
            return False, f'{tree[1]} is a {value.kind}'
        if kind == 'call':
            name, args = tree[1], tree[2]
            if name in ('sum', 'max', 'min'):
                for arg in args:
                    ok, why = self.never_falls(arg, thing, seen)
                    if not ok:
                        return False, why
                return True, None
            return False, f'{name}() of values that change'
        if kind == 'bin':
            left, right = tree[2], tree[3]
            if tree[1] == '+':
                for side in (left, right):
                    ok, why = self.never_falls(side, thing, seen)
                    if not ok:
                        return False, why
                return True, None
            if tree[1] == '*':
                for side in (left, right):
                    ok, why = self.never_falls(side, thing, seen)
                    if not ok:
                        return False, why
                    if not self.nonnegative(side, thing):
                        return False, f'{show(side)} may be negative'
                return True, None
            if tree[1] == '/':
                ok, why = self.never_falls(left, thing, seen)
                if not ok:
                    return False, why
                if not (self.fixed(right, thing) and self.nonnegative(right, thing) and self.nonnegative(left, thing)):
                    return False, f'a division by {show(right)}, which may change'
                return True, None
            return False, f'a difference: {show(tree)}'
        if self.fixed(tree, thing):
            return True, None
        return False, f'{show(tree)} reads values that can fall'


# ---- the comparison ------------------------------------------------------------------------------------------


class Report:
    def __init__(self):
        self.errors = []
        self.notes = []
        self.counts = collections.Counter()

    def error(self, group, message):
        self.errors.append((group, message))
        self.counts[group] += 1

    def note(self, group, message):
        self.notes.append((group, message))


def same(a, b):
    if a is None or b is None:
        return a is b
    return canonical(a) == canonical(b)


def text(tree):
    return 'nothing' if tree is None else show(tree)


def statements_text(statements):
    out = []
    for statement in statements:
        if statement[0] == 'set':
            out.append(f'{statement[2]} {statement[1]} {show(statement[3])}')
        elif statement[0] == 'move':
            out.append(f'move {show(statement[1])} from {statement[2]} to {statement[3]}')
        elif statement[0] == 'start':
            out.append(f'{statement[1]}.start()')
        else:
            out.append(str(statement))
    return out


def canonical_statement(statement):
    if statement[0] == 'set':
        return ('set', statement[1], statement[2], canonical(statement[3]))
    if statement[0] == 'move':
        return ('move', canonical(statement[1]), statement[2], statement[3])
    if statement[0] == 'start':
        return ('start', statement[1], tuple(canonical(arg) for arg in statement[2]))
    return statement


def compare(old, new, old_structure, new_structure, report):
    """Every difference of meaning between the facts of the old file and those of the new one."""
    # 1. Numbers with their units, and texts.
    for (value, unit), n in sorted(old.numbers.items(), key=str):
        have = new.numbers.get((value, unit), 0)
        if have < n:
            shown = f'{value} {unit}' if unit else str(value)
            report.error('number', f'{shown}: {n} in the old file, {have} in the new one')
    for words, n in old.texts.items():
        have = new.texts.get(words, 0)
        if have < n:
            report.error('text', f'{n} in the old file, {have} in the new one: "{words[:90]}"')
    extra = sum((new.numbers - old.numbers).values())
    if extra:
        added = collections.Counter()
        for (value, unit), n in (new.numbers - old.numbers).items():
            added[f'{value} {unit}' if unit else str(value)] += n
        most = ', '.join(f'{key} ({n})' for key, n in added.most_common(6))
        report.note('number', f'{extra} numbers of the new file are not in the old one: {most}')

    # 2. Things.
    for name, info in old.things.items():
        if name not in new.things:
            report.error('thing', f'{name} is missing')
        elif new.things[name]['template'] != info['template']:
            report.error('thing', f'{name}: of the template {info["template"]}, and now of {new.things[name]["template"]}')
    for name in new.things:
        if name not in old.things:
            report.error('thing', f'{name} is new')

    # 3. Values: their kind, their unit, their expression, their range and their scale.
    for key, value in old.values.items():
        where = f'{key[0]}.{key[1]}' if key[0] else key[1]
        other = new.values.get(key)
        if other is None:
            report.error('kind', f'{where} ({value.kind}) is missing')
            continue
        if value.kind != other.kind:
            report.error('kind', f'{where}: a {KIND.get(value.kind, value.kind)} in the old file, a {KIND.get(other.kind, other.kind)} in the new one')
            continue
        if value.kind == 'link':
            continue
        if (value.unit or None) != (other.unit or None):
            report.error('unit', f'{where}: {value.unit} in the old file, {other.unit} in the new one')
        if value.members and tuple(value.members) != tuple(other.members):
            report.error('kind', f'{where}: the states {value.members} are now {other.members}')
        if not same(value.expr, other.expr):
            report.error('expression', f'{where}: expected {text(value.expr)}; the new file has {text(other.expr)}')
        if (value.range is None) != (other.range is None) or (
            value.range is not None and not (same(value.range[0], other.range[0]) and same(value.range[1], other.range[1]))
        ):
            shown = lambda r: 'no range' if r is None else f'[{show(r[0])}, {show(r[1])}]'  # noqa: E731
            report.error('range', f'{where}: expected {shown(value.range)}; the new file has {shown(other.range)}')
        if not same(value.scale, other.scale):
            report.error('scale', f'{where}: expected scale {text(value.scale)}; the new file has {text(other.scale)}')
        if value.kind == 'var.number':
            mine, theirs = old_structure.kind(old_structure.member(f'this.{key[1]}', key[0])), new_structure.kind(new_structure.member(f'this.{key[1]}', key[0]))
            if mine != theirs:
                report.error('kind', f'{where}: {SORT[mine]} in the old file, {SORT[theirs]} in the new one')
    for key, other in new.values.items():
        if key not in old.values and not (key[0] is not None and (key[0], key[1]) in new.events):
            where = f'{key[0]}.{key[1]}' if key[0] else key[1]
            report.error('kind', f'{where} ({other.kind}) is new')

    # 4. Flows, and what a store gives out.
    for key, flow in old.flows.items():
        where = f'{key[0]}.{key[1]}'
        other = new.flows.get(key)
        if other is None:
            report.error('flow', f'the flow {where} is missing')
            continue
        mine = sorted((leg[1], leg[2], show(canonical_tree(leg[3]))) for leg in flow.legs)
        theirs = sorted((leg[1], leg[2], show(canonical_tree(leg[3])) if leg[3] is not None else 'no request') for leg in other.legs)
        if mine != theirs:
            for leg in mine:
                if leg not in theirs:
                    report.error('flow', f'{where}: expected {leg[0]} -> {leg[1]} with the request {leg[2]}')
            for leg in theirs:
                if leg not in mine:
                    report.error('flow', f'{where}: the new file has {leg[0]} -> {leg[1]} with the request {leg[2]}')
    for key in new.flows:
        if key not in old.flows:
            report.error('flow', f'the flow {key[0]}.{key[1]} is new')
    for name, table in (('capacity', 'capacities'), ('allocation', 'allocations')):
        mine, theirs = getattr(old, table), getattr(new, table)
        for key in sorted(set(mine) | set(theirs)):
            if not same(mine.get(key), theirs.get(key)):
                report.error(
                    'share',
                    f'{key[0]}.{key[1]}: expected outflow.{name} {text(mine.get(key))}; the new file has {text(theirs.get(key))}',
                )

    # 5. Events.
    for key, event in old.events.items():
        where = f'{key[0]}.{key[1]}'
        other = new.events.get(key)
        if other is None:
            report.error('event', f'the event {where} is missing')
            continue
        if not same(event.when, other.when):
            report.error('event', f'{where}: expected the trigger {text(event.when)}; the new file has {text(other.when)}')
        if event.once != other.once and event.when is not None:
            report.error('event', f'{where}: `once` in the old file is `reset when false`: {"missing" if event.once else "added"}')
        if not event.cases:
            mine = [(show(canonical_tree(d)), [canonical_statement(s) for s in body]) for d, _, body in event.stages]
            theirs = [(show(canonical_tree(d)), [canonical_statement(s) for s in body]) for d, g, body in other.stages]
            if other.cases:
                report.error('event', f'{where}: one set of lines in the old file, a switch in the new one')
            elif mine != theirs:
                want = '; '.join(f'after {d}: ' + ', '.join(statements_text(body)) for d, _, body in event.stages) or 'no stage'
                have = '; '.join(f'after {show(d)}: ' + ', '.join(statements_text(body)) for d, _, body in other.stages) or 'no stage'
                report.error('event', f'{where}: expected {want}; the new file has {have}')
        else:
            mine = {label: sorted(map(repr, map(canonical_statement, body))) for label, body in event.cases}
            theirs = {label: sorted(map(repr, map(canonical_statement, body))) for label, body in other.cases}
            for label in mine:
                if label not in theirs:
                    report.error('event', f'{where}: the outcome {label} is missing')
                elif mine[label] != theirs[label]:
                    old_body = next(body for name, body in event.cases if name == label)
                    new_body = next(body for name, body in other.cases if name == label)
                    report.error('event', f'{where}: the outcome {label}: expected {statements_text(old_body)}; the new file has {statements_text(new_body)}')
            for label in theirs:
                if label not in mine:
                    report.error('event', f'{where}: the outcome {label} is new')
            want = {name for tree in event.selectors for name in exprs.names_of(tree) if not name.isupper()}
            have = {name for tree in other.selectors for name in exprs.names_of(tree) if not name.isupper()}
            have |= {name for d, g, _ in other.stages for tree in (d, g) if tree is not None for name in exprs.names_of(tree)}
            if not want <= have:
                report.error('event', f'{where}: its outcomes read {sorted(want - have)}, which the new switch does not read')
            if event.stages and other.stages and not same(event.stages[0][0], other.stages[0][0]):
                report.error('event', f'{where}: expected the delay {text(event.stages[0][0])}; the new file has {text(other.stages[0][0])}')
            report.note('event', f'{where}: an event with outcomes; the check compares the lines of each outcome and the names that its conditions read, not the conditions')
    for key in new.events:
        if key not in old.events:
            report.note('event', f'the event {key[0]}.{key[1]} is new (an event that keeps the history of an outcome is new)')

    # 6. Status cases, checks, what an actor sees.
    for thing in sorted(set(old.statuses) | set(new.statuses), key=str):
        mine, theirs = old.statuses.get(thing, []), new.statuses.get(thing, [])
        if len(mine) != len(theirs):
            report.error('status', f'{thing}: {len(mine)} status cases in the old file, {len(theirs)} in the new one')
            continue
        for k, (a, b) in enumerate(zip(mine, theirs, strict=True)):
            if a[0] != b[0] or not same(a[1], b[1]):
                report.error('status', f'{thing}, case {k + 1}: expected {a[0]} when {text(a[1])}; the new file has {b[0]} when {text(b[1])}')
    for thing in sorted(set(old.asserts) | set(new.asserts), key=str):
        mine, theirs = old.asserts.get(thing, []), new.asserts.get(thing, [])
        want = sorted(show(canonical_tree(tree)) for tree in mine)
        have = sorted(show(canonical_tree(tree)) for tree in theirs)
        for item in want:
            if item not in have:
                report.error('assert', f'{thing or "top level"}: expected assert {item}')
        for item in have:
            if item not in want:
                report.error('assert', f'{thing or "top level"}: the new file has assert {item}')
    if old.sees != new.sees:
        report.error('sees', f'expected {old.sees}; the new file has {new.sees}')

    # 7. The lines of instances, options and runs.
    for key in sorted(set(old.instance_lines) | set(new.instance_lines)):
        a, b = old.instance_lines.get(key), new.instance_lines.get(key)
        if not same(a, b):
            report.error('instance', f'{key[0]}.{key[1]}: expected {text(a)}; the new file has {text(b)}')
    for key in sorted(set(old.options) | set(new.options)):
        a, b = old.options.get(key), new.options.get(key)
        if a is None or b is None:
            report.error('option', f'the option "{key[1]}" of "{key[0]}" is {"missing" if b is None else "new"}')
            continue
        for target in sorted(set(a) | set(b)):
            if not same(a.get(target), b.get(target)):
                report.error('option', f'"{key[1]}": expected {target} = {text(a.get(target))}; the new file has {text(b.get(target))}')
    if old.runs != new.runs:
        for name in sorted(set(old.runs) | set(new.runs)):
            if old.runs.get(name) != new.runs.get(name):
                report.error('run', f'{name}: expected {old.runs.get(name)}; the new file has {new.runs.get(name)}')
    if list(old.runs) != list(new.runs) and set(old.runs) == set(new.runs):
        report.error('run', 'the runs are in another order: the order is the order of the menu')

    # 8. Records, notes, uses, the scenario line.
    for name in sorted(set(old.records) | set(new.records)):
        a, b = old.records.get(name), new.records.get(name)
        if a != b:
            what = 'is missing' if b is None else 'is new' if a is None else 'differs'
            detail = ''
            if a is not None and b is not None:
                parts = ('kind', 'ID', 'explanation', 'claims')
                detail = ': ' + ', '.join(part for part, x, y in zip(parts, a, b, strict=True) if x != y)
            report.error('record', f'the record {name} {what}{detail}')
    if old.notes != new.notes:
        report.error('note', f'the keys of the notes differ: {len(old.notes)} in the old file, {len(new.notes)} in the new one')
    if old.uses != new.uses:
        report.error('use', f'expected use {old.uses}; the new file has {new.uses}')
    for key in ('role', 'horizon', 'resolution'):
        a, b = old.scenario.get(key), new.scenario.get(key)
        if key == 'role':
            if a != b:
                report.error('scenario', f'expected a {a} line; the new file has {b}')
        elif not same(a, b):
            report.error('scenario', f'{key}: expected {text(a)}; the new file has {text(b)}')
    a, b = old.scenario.get('timescales') or [], new.scenario.get('timescales') or []
    if [show(canonical_tree(x)) for x in a] != [show(canonical_tree(x)) for x in b]:
        report.error('scenario', 'the timescales differ')

    # 9. The report: what is selected, and what is said to be cumulative.
    for path, flags in old.report.items():
        other = new.report.get(path)
        if other is None:
            report.error('report', f'{path} is an output of the old file and no entry of `report:`')
            continue
        if flags['cumulative'] != other['cumulative']:
            want = 'cumulative' if flags['cumulative'] else 'a level (it can fall)'
            report.error('report', f'{path}: {want} in the old file; the new entry says {"cumulative" if other["cumulative"] else "nothing"}')
        if not same(flags['lag'], other['lag']):
            report.error('report', f'{path}: expected lag {text(flags["lag"])}; the new entry has {text(other["lag"])}')
    for path in new.report:
        if path not in old.report:
            report.note('report', f'{path} is a new entry of `report:`')


def canonical_tree(tree):
    return canonical(tree) if tree is not None else ('name', 'nothing')


KIND = {
    'input.number': 'number input',
    'input.bool': 'yes/no input',
    'input.text': 'text value',
    'input.named': 'input with named values',
    'let.fixed': 'fixed value',
    'let.formula': 'formula',
    'var.named': 'named state',
    'var.bool': 'yes/no state',
    'var.number': 'number that changes',
    'link': 'link',
    'none': 'value with no estimate',
}
SORT = {'stock': 'a store (flows or events take from it)', 'tally': 'an accumulated tally (flows only fill it)', 'state': 'a number state (no flow joins it)'}


def cumulative(old_builder, new, old_structure, new_structure, report, model_path, quiet):
    """The outputs that the old compiler proved cumulative: listed, and checked with this script's own
    simple rule on both sides."""
    proved, entry, compiled = old_builder.proven(model_path)
    old = old_builder.facts
    lines = []
    if entry is None:
        report.note('cumulative', f'the old compiler built no model for this file ({compiled}); no proof is listed')
        return lines
    # This script's rule for the kind of a number var, against the old compiler's.
    differ = 0
    for key, kind in compiled.items():
        if (key in old.values or (key[0], key[1]) in old.values) and old_structure.kind(key) != kind:
            differ += 1
    checked = sum(1 for key in compiled if key in old.values)
    report.note(
        'kind',
        f'the kinds of {checked} number vars of this file, by this script\'s rule, against the old compiler\'s '
        f'({short(entry)}): {differ} differ',
    )
    if differ:
        report.error('kind', f'this script\'s rule for stock, tally and state differs from the old compiler\'s on {differ} vars')
    mine = {path: names for path, names in proved.items() if path in old.report}
    lines.append(f'outputs that the old compiler proved cumulative ({short(entry)}): {len(mine)} of this file')
    for path, names in sorted(mine.items()):
        thing, _, member = path.rpartition('.')
        owner = thing.removesuffix('.instances') or None
        key = (owner, member)
        old_value, new_value = old.values.get(key), new.values.get(key)
        flags = new.report.get(path)
        verdicts = []
        if flags is None or not flags['cumulative']:
            report.error('cumulative', f'{path}: the old compiler proved it cumulative, and `report:` does not say `cumulative`')
            verdicts.append('NOT MARKED')
        if old_value is None or new_value is None:
            verdicts.append('not found')
        else:
            ok_old, why_old = old_structure.never_falls(('name', f'this.{member}') if owner else ('name', member), owner)
            ok_new, why_new = new_structure.never_falls(('name', f'this.{member}') if owner else ('name', member), owner)
            if ok_old and not ok_new:
                report.error(
                    'cumulative',
                    f'{path}: the old file adds up values that never fall; the new definition can fall: {why_new}',
                )
                verdicts.append('CAN FALL IN THE NEW FILE')
            elif ok_old and ok_new:
                verdicts.append('never falls by the simple rule, in both files')
            elif not ok_old:
                verdicts.append(f'the simple rule does not decide ({why_old}); the new compiler must prove it')
        lines.append(f'  {path}: ' + '; '.join(verdicts))
    return lines


def short(path):
    try:
        return Path(path).resolve().relative_to(BASE.resolve()).as_posix()
    except ValueError:
        return str(path)


def run(old_path, new_path, model_path=None, do_compile=True, quiet=False, out=sys.stdout):
    builder = Old(old_path)
    old = builder.build()
    new = newreader.read_new(Path(new_path).read_text(encoding='utf-8'), str(new_path))
    report = Report()
    old_structure = Structure(old, declarer=builder.symbols.declarer)
    new_structure = Structure(new, declarer=builder.symbols.declarer)
    for line, why in new.unread:
        report.error('unread', f'line {line} of the new file: {why}')
    todo = Path(new_path).read_text(encoding='utf-8').count('# TODO(hand)')
    if todo:
        report.note('todo', f'the new file has {todo} `# TODO(hand)` marks: what they stand for is missing below')
    compare(old, new, old_structure, new_structure, report)
    lines = []
    if do_compile:
        lines = cumulative(builder, new, old_structure, new_structure, report, model_path, quiet)
    for line, why in builder.problems:
        report.note('by hand', f'old line {line}: {why}')
    print(f'check {short(old_path)} -> {new_path}', file=out)
    print(
        f'  old file: {sum(old.numbers.values())} numbers, {sum(old.texts.values())} texts, {len(old.values)} values, '
        f'{len(old.flows)} flows, {len(old.events)} events, {len(old.records)} records',
        file=out,
    )
    for line in lines:
        print('  ' + line, file=out)
    if not quiet:
        for group, message in report.notes:
            print(f'  note [{group}] {message}', file=out)
        shown = collections.Counter()
        for group, message in report.errors:
            shown[group] += 1
            if shown[group] <= 12:
                print(f'  FAIL [{group}] {message}', file=out)
        for group, n in shown.items():
            if n > 12:
                print(f'  FAIL [{group}] ... and {n - 12} more', file=out)
    if report.errors:
        summary = ', '.join(f'{n} {group}' for group, n in sorted(report.counts.items()))
        print(f'  FAILED: {len(report.errors)} differences ({summary})', file=out)
    else:
        print('  PASSED: every number with its unit and every text is there, every name keeps its kind, and every expression is the expected one', file=out)
    return report


def main(argv):
    args = [arg for arg in argv if not arg.startswith('--')]
    model = None
    if '--model' in argv:
        model = argv[argv.index('--model') + 1]
        args = [arg for arg in args if arg != model]
    if len(args) != 2:
        print(__doc__)
        return 2
    report = run(args[0], args[1], model, '--no-compile' not in argv, '--quiet' in argv)
    return 1 if report.errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
