#!/usr/bin/env python
"""Task 1 of brief A5: a census of every construct of every `.scn` file of `examples/` and
`scenarios/` at the base commit.

Every count comes from the old parser (`napkin.model.language.parse`) and, for the compiled facts,
from the old compiler (`napkin.model.model.build_model`). No count comes from a text pattern over the
source. Braces in a text are counted with the old compiler's own reader of them (`resolve.BRACES`),
over the value of a parsed text.

Run:

    PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python census.py

It writes `census.json` and `census.md` beside itself. `--no-compile` leaves out the compiled part.
"""

from __future__ import annotations

import ast
import collections
import dataclasses
import json
import sys
import time
from pathlib import Path

import oldmodel
from oldmodel import BASE, lex, nodes, parse

HERE = Path(__file__).resolve().parent
DISTRIBUTIONS = set(parse.DISTRIBUTIONS)
MATH = {'clip', 'abs', 'exp', 'expm1', 'ln', 'log1p', 'sqrt', 'erf'}

# Each key of the census: what it counts. The migration table has one row for each key group (the
# part of the key before the first dot, and often the second).
DESCRIPTIONS = {}


def describe(key, text):
    DESCRIPTIONS.setdefault(key, text)


class Census:
    """The counts of one file, and the first places where each key is seen."""

    def __init__(self, relative):
        self.relative = relative
        self.counts = collections.Counter()
        self.where = {}

    def bump(self, key, line=None, n=1, text=None):
        if text is not None:
            describe(key, text)
        if n:
            self.counts[key] += n
            if line is not None:
                seen = self.where.setdefault(key, [])
                if len(seen) < 3:
                    seen.append(line)


# ---- expressions ----------------------------------------------------------------------------------------


def is_literal(tokens):
    return parse.Parser.literal(tokens)


def distribution_of(tokens):
    """The family of an expression that is one distribution, or None."""
    if (
        len(tokens) >= 3
        and tokens[0].is_name(*DISTRIBUTIONS)
        and tokens[1].is_op('(')
        and parse.closing(tokens[1:]) == len(tokens) - 2
    ):
        return tokens[0].value
    return None


# The places of an expression that an event reads while the model runs.
RUNTIME = {'when', 'after', 'each', 'event while', 'chance', 'outcome when', 'set', 'move'}
REACH_TEXT = {
    'own': 'A name of a member of the thing itself, written bare (`demand`)',
    'via_link': 'A name read through a link of the thing (`utility.service`, `buys.rate`)',
    'thing_by_name': 'A member of another thing, read by that thing\'s name (`relief.status`)',
    'template_list': 'A member of every instance of a template, by its name (`Utility.unserved`)',
    'top_level': 'A name read at the top level of the file',
    'unresolved': 'A name that this census did not resolve',
}


class Reader:
    """Reads the expressions of one file, with the names of its model."""

    def __init__(self, census, symbols):
        self.c = census
        self.symbols = symbols

    def units(self, expr):
        for token in expr.tokens:
            if token.kind != 'unit':
                continue
            word = token.value
            self.c.bump('expr.unit', expr.line, text='A number with its unit, `12 h`')
            if '^' in word:
                self.c.bump('expr.unit.power', expr.line, text='A unit with a power, `m^2`')
            if '-' in word:
                self.c.bump('expr.unit.product', expr.line, text='A unit that is a product, `tuner-year`')
            if '/' in word:
                self.c.bump('expr.unit.quotient', expr.line, text='A unit that is a quotient, `L/h`')

    def read(self, expr, thing, context):
        """Count what one expression holds. `thing` is the thing that it is read in (None: the top
        level); `context` says where it stands (`when`, `rate`, `value`, `set`, ...)."""
        if expr is None or not expr.tokens:
            return None
        c = self.c
        line = expr.line
        self.units(expr)
        tree, names = oldmodel.tree_of(expr)
        if tree is None:
            c.bump('expr.unreadable', line, text='An expression that the old reader does not read alone')
            return None
        c.bump('expr', line, text='Expressions, of every place')
        units = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'q':
                units.update(id(arg) for arg in node.args)
        for node in ast.walk(tree):
            if id(node) in units:
                continue
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.call(node, names, thing, context, line)
            elif isinstance(node, ast.Compare):
                for op in node.ops:
                    if isinstance(op, ast.Eq):
                        c.bump('expr.is', line, text='Equality, `a is b`')
                    elif isinstance(op, ast.NotEq):
                        c.bump('expr.is_not', line, text='Inequality, `a is not b`')
                if len(node.ops) > 1:
                    c.bump('expr.chained_comparison', line, text='A chain of comparisons, `a <= b <= c`')
            elif isinstance(node, ast.IfExp):
                c.bump('expr.if_else', line, text='A conditional value, `a if C else b`')
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                c.bump('expr.power', line, text='A power, `a ** b`')
            elif isinstance(node, ast.BoolOp):
                c.bump('expr.and_or', line, text='`and` / `or`')
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                c.bump('expr.not', line, text='`not`')
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                c.bump('expr.named_value', line, text='A named value or a text in quotes, `"open"`')
            elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                c.bump('expr.bare_number', line, text='A number with no unit, `0.3`')
            elif isinstance(node, ast.Name):
                if node.id == 't':
                    c.bump('expr.t', line, text='The time, `t`')
                elif node.id in ('true', 'false'):
                    c.bump('expr.true_false', line, text='`true` or `false`')
                elif names.get(node.id) == 'copy':
                    c.bump('expr.copy', line, text='The number of a copy, `copy`')
        runtime = context in RUNTIME
        for name in names.values():
            found = self.symbols.read(name, thing)
            if found is None and thing is None and '.' not in name:
                # A top-level expression can read an output of the scenario by its name.
                c.bump('expr.reads_output', line, text='An output that reads another output by its name')
                continue
            how = self.reach(name, thing, found)
            c.bump(f'name.read.{how}', line, text=REACH_TEXT[how])
            if runtime and how in ('thing_by_name', 'template_list'):
                c.bump(
                    f'name.read.{how}.in_event',
                    line,
                    text=REACH_TEXT[how] + ', in a trigger or a line of an event',
                )
        return tree, names

    def reach(self, name, thing, found):
        """How an expression reaches a name: `own` (a member of the thing itself), `via_link` (through a
        link of the thing), `thing_by_name` (a member of another thing, by that thing's name),
        `template_list` (over the instances of a template, by its name), `top_level` (read at the top
        level of the file), or `unresolved`."""
        if found is None:
            return 'unresolved'
        parts = name.split('.')
        if len(parts) == 1:
            return 'own' if thing is not None else 'top_level'
        head = parts[0]
        info = self.symbols.things.get(thing) if thing is not None else None
        if info is not None and head in info.links:
            return 'via_link'
        if head in self.symbols.templates:
            return 'template_list'
        if head in self.symbols.things:
            return 'thing_by_name'
        return 'unresolved'

    def call(self, node, names, thing, context, line):
        c = self.c
        name = node.func.id
        args = node.args
        symbol = names.get(args[0].id) if len(args) == 1 and isinstance(args[0], ast.Name) else None
        found = self.symbols.read(symbol, thing) if symbol is not None else None
        if name == 'q':
            return
        if name in ('since', 'count'):
            if found is not None and found[0] == 'event':
                kind = 'outcome' if found[3] is not None else 'event'
                c.bump(
                    f'fn.{name}.{kind}',
                    line,
                    text=f'`{name}(e)` of an event'
                    if kind == 'event'
                    else f'`{name}(e.o)` of one outcome of an event',
                )
                c.bump(f'fn.{name}.in.{context}', line, text=f'`{name}()` read in a {context}')
            elif name == 'count' and found is not None and found[0] == 'value' and found[4]:
                c.bump('fn.count.list', line, text='`count(list.flag)`: the members where a yes/no holds')
            elif name == 'since' and found is not None and found[0] == 'value' and found[1] == 'var.named':
                c.bump(
                    'fn.since.state', line, text='`since(state)`: the old compiler reads it as `elapsed(state)`'
                )
            else:
                c.bump(f'fn.{name}.unresolved', line, text=f'`{name}()` whose argument this census did not resolve')
            return
        if name == 'elapsed':
            c.bump('fn.elapsed', line, text='`elapsed(state)`: the time since a named state last changed')
            c.bump(f'fn.elapsed.in.{context}', line, text=f'`elapsed()` read in a {context}')
            return
        if name == 'delayed':
            c.bump('fn.delayed', line, text='`delayed(x, D)`: the value of x at D before the firing')
            return
        if name in ('sum', 'any', 'all'):
            listed = found is not None and found[0] == 'value' and found[4]
            if listed:
                c.bump(f'fn.{name}.list', line, text=f'`{name}(list.x)` over a list link or a template')
                head = symbol.rpartition('.')[0]
                if head in self.symbols.templates:
                    c.bump(
                        f'fn.{name}.list.template',
                        line,
                        text=f'`{name}(Template.x)`: over every instance of a template',
                    )
                else:
                    c.bump(f'fn.{name}.list.link', line, text=f'`{name}(link.x)`: over a list link')
            else:
                c.bump(f'fn.{name}.other', line, text=f'`{name}()` of something that is no list')
            return
        if name in ('min', 'max'):
            lists = 0
            for arg in args:
                if isinstance(arg, ast.Name) and arg.id in names:
                    read = self.symbols.read(names[arg.id], thing)
                    if read is not None and read[0] == 'value' and read[4]:
                        lists += 1
            if lists and len(args) > lists:
                c.bump(
                    f'fn.{name}.list_with_extra',
                    line,
                    text=f'`{name}(list.x, v)`: a list and a further argument',
                )
            elif lists:
                c.bump(f'fn.{name}.list', line, text=f'`{name}(list.x)` over a list')
            else:
                c.bump(f'fn.{name}.scalar', line, text=f'`{name}(a, b, ...)` of scalars')
                c.bump(f'fn.{name}.scalar.args{min(len(args), 4)}', line, text=f'`{name}` with that many arguments (4: four or more)')
            return
        if name in MATH:
            c.bump(f'fn.math.{name}', line, text=f'`{name}()`')
            return
        if name in DISTRIBUTIONS:
            place = 'event' if context in ('set', 'after', 'chance', 'move') else 'declaration'
            c.bump(
                f'dist.{place}.{name}',
                line,
                text=f'`{name}(...)` written in a declaration'
                if place == 'declaration'
                else f'`{name}(...)` written in an event: drawn at each firing',
            )
            if len(args) > {'uniform': 2, 'loguniform': 2, 'normal': 2, 'lognormal': 2, 'beta': 2}.get(name, 9):
                c.bump(
                    f'dist.{name}.truncated',
                    line,
                    text=f'`{name}` with bounds: four arguments',
                )
            if node.keywords:
                c.bump('dist.keyword_arguments', line, text='A distribution with arguments by name')
            return
        c.bump(f'fn.other.{name}', line, text=f'A call of `{name}`')


# ---- the walk of a file ----------------------------------------------------------------------------------


def braces(text):
    """The names in braces of a text, read with the old compiler's own reader of braces."""
    from napkin.model.language.resolve import BRACES

    values = text.value if isinstance(text.value, list) else [text.value]
    return [m.group(1) for value in values for m in BRACES.finditer(value or '')]


def evidence(c, support, owner):
    """The records and the citations of one line."""
    for item in support:
        if isinstance(item, nodes.Cite):
            c.bump('evidence.cite', item.line, text='`@name`: a named record cited at a line')
            c.bump(f'evidence.cite.on.{owner}', item.line, text=f'`@name` on a {owner}')
        elif isinstance(item, nodes.Record):
            c.bump('evidence.record.in_place', item.line, text='`@kind [ID] "explanation"` under a line')
            c.bump(
                f'evidence.record.in_place.kind.{item.kind}', item.line, text=f'A record in place of kind `{item.kind}`'
            )
            c.bump(f'evidence.record.in_place.on.{owner}', item.line, text=f'A record in place on a {owner}')
            if item.id is not None:
                c.bump('evidence.record.in_place.id', item.line, text='A record in place with an ID')
            claims(c, item)
    if len(support) > 1:
        c.bump(
            f'evidence.several.on.{owner}',
            support[0].line,
            text=f'A {owner} with two records or more (cited or in place)',
        )


def claims(c, record):
    if record.claims:
        c.bump('evidence.claims_block', record.line, text='`claims:` under a record')
    for claim in record.claims:
        c.bump('evidence.claim', claim.line, text='A claim listed under a record')
        if claim.datum is not None:
            c.bump('evidence.claim.datum', claim.line, text='`datum: key` under a claim')


def text_of(c, text, owner):
    if text is None:
        return
    c.bump(f'text.{owner}', text.line, text=f'The text of a {owner}')
    if isinstance(text.value, list):
        c.bump(f'text.{owner}.list', text.line, text=f'A list of texts on a {owner}: one for each time')
    found = braces(text)
    if found:
        c.bump(f'text.{owner}.braces', text.line, text=f'A text of a {owner} with a name in braces')
        for name in found:
            if '.' in name:
                c.bump(
                    'text.braces.other_thing', text.line, text='Braces that name a text value of another thing'
                )


# Words that the specification of the new language uses for itself: its keywords, the built-in
# properties of a flow, an endpoint, an event and an occurrence, and its functions. A member of an
# old model that has one of these names may need a new name; A1 rules on which words are kept.
NEW_WORDS = frozenset(
    """this formula readonly input flow event solver inputs solve_for constraints objective switch after
    until when reset move from to none SOURCE SINK where by at instances occurrences flows request
    capacity actual_rate inflow outflow allocation priority proportional status start draw mean std
    done active started served_fraction forward backward source sink enum bool record assert minimize
    maximize sum count any all min max clip sqrt since elapsed delayed t in and or not if else true
    false sampled median ok degraded failed inactive origin destination id sees use variant change
    options runs notes report scale claims size resolution""".split()
)


def declared(c, name, what, line):
    """A name that a model declares, when the new language uses the word itself."""
    if name in NEW_WORDS:
        c.bump(
            f'name.declared.{name}',
            line,
            text=f'A member or a thing named `{name}`, a word that the new language uses itself',
        )
        c.bump(f'name.declared.as.{what}', line, text=f'A {what} whose name is a word of the new language')


def type_units(c, written, line):
    if not isinstance(written, str) or written == 'bool':
        return
    c.bump('type.unit', line, text='A type written as a unit, `name: L/h = …`')
    if '^' in written:
        c.bump('type.unit.power', line, text='A type whose unit has a power')
    if '-' in written:
        c.bump('type.unit.product', line, text='A type whose unit is a product, `person-days`')
    if '/' in written:
        c.bump('type.unit.quotient', line, text='A type whose unit is a quotient')


def field(c, r, value, thing, owner='field'):
    """A field of a thing or a template."""
    kind = oldmodel.field_kind(value)
    line = value.line
    declared(c, value.name, 'field', line)
    type_units(c, value.type, line)
    c.bump(f'field.{kind}', line, text=FIELD_TEXT.get(kind, kind))
    tokens = value.value.tokens if value.value is not None else []
    family = distribution_of(tokens)
    literal = is_literal(tokens)
    if family is not None:
        c.bump(f'field.{kind}.distribution', line, text=f'A {FIELD_TEXT.get(kind, kind)} whose value is a distribution')
    if value.type is not None and not isinstance(value.type, list):
        c.bump(f'field.{kind}.typed', line, text=f'… with its type written (`name: unit = …`)')
    elif value.type is None and kind in ('input.number', 'let.fixed', 'var.number'):
        c.bump(f'field.{kind}.type_from_value', line, text='… with no type: the unit of its value gives it')
    if value.min is not None:
        c.bump(f'field.{kind}.range', line, text='… with a range, `in low to high`')
        low = value.min.expr.tokens
        high = value.max.expr.tokens
        if not (is_literal(low) and is_literal(high)):
            c.bump('field.range.expression', line, text='A range with an end that is an expression')
    elif kind == 'input.number':
        c.bump('field.input.number.no_range', line, text='A number input with no range')
    if value.size is not None:
        c.bump(f'field.{kind}.size', line, text='… with a `size` hint')
    if kind == 'var.number':
        if not literal:
            c.bump(
                'field.var.number.start_expression',
                line,
                text='A number var whose start value is an expression of other values',
            )
        if value.min is None and value.size is None:
            c.bump('field.var.number.no_range_no_size', line, text='A number var with no range and no size')
    if value.output is not None:
        c.bump('output.field', value.output.line, text='`output x` under a thing: its field `x` is an output')
        output_lines(c, value.output, 'field')
    r.read(value.value, thing, 'value')
    if value.min is not None:
        r.read(value.min.expr, thing, 'range')
        r.read(value.max.expr, thing, 'range')
    if value.size is not None:
        r.read(value.size.expr, thing, 'size')
    text_of(c, value.text, 'field')
    evidence(c, value.support, 'field')
    if not value.support and kind not in ('input.text', 'var.named'):
        c.bump(f'field.{kind}.no_record', line, text='… with no record on its own line')


FIELD_TEXT = {
    'input.number': '`input x = 6 h in 1 h to 24 h`: a number input',
    'input.bool': '`input flag = true`: a yes/no input',
    'input.text': '`input actor = "The AI"`: a text value',
    'input.named': 'An input with named values',
    'let.fixed': '`let k = 2 h`: a value that never changes',
    'let.formula': '`let f: unit = a * b`: a formula',
    'var.named': '`var s: "a" | "b" = "a"`: a named state',
    'var.bool': '`var found = false`: a yes/no state',
    'var.number': '`var n: unit = 0 …`: a number that changes (a stock, a tally or a number state)',
}


def output_lines(c, lines, where):
    line = lines.line
    if lines.about is not None:
        c.bump('output.set.about', lines.about.line, text='`about "…"` under an output')
    if lines.category is not None:
        c.bump('output.set.category', line, text='`category word` under an output')
        c.bump(f'output.set.category.{lines.category}', line, text=f'`category {lines.category}`')
    if lines.scope is not None:
        c.bump('output.set.scope', lines.scope.line, text='`scope "…"` under an output')
    if lines.measure == 'level':
        c.bump('output.set.level', line, text='`level`: the output can fall')
    if lines.signed:
        c.bump('output.set.signed', line, text='`signed`: the output can be below zero')
    if lines.distinct is not None:
        c.bump('output.set.distinct', lines.distinct.line, text='`distinct  @r`: the people that it adds are different people')
        evidence(c, lines.distinct.support, 'distinct')
        if not lines.distinct.support:
            c.bump('output.set.distinct.no_record', lines.distinct.line, text='`distinct` with no record')
    if lines.lag is not None:
        c.bump(f'output.set.lag.{lines.lag.kind}', lines.lag.line, text=f'`lag` of kind {lines.lag.kind}')
    if lines.unestimated is not None:
        c.bump('output.set.unestimated', lines.unestimated.line, text='`unestimated "Reason"`: an output with no estimate')
    if lines.measure != 'level' and lines.unestimated is None:
        c.bump('output.cumulative', line, text='An estimated output with no `level`: the file says it is cumulative')
    if lines.measure != 'level' and lines.unestimated is not None:
        c.bump('output.unestimated.no_level', line, text='An unestimated output with no `level`')
    if lines.measure == 'level' and lines.unestimated is not None:
        c.bump('output.unestimated.level', line, text='An unestimated output with `level`')
    if where != 'field':
        text_of(c, lines.text, 'output')
    evidence(c, lines.support, 'output')


def output(c, r, node, thing, where):
    c.bump(f'output.{where}', node.line, text=OUTPUT_TEXT[where])
    declared(c, node.name, 'output', node.line)
    type_units(c, node.type, node.line)
    if node.expr is not None:
        r.read(node.expr, thing, 'output')
    if node.type is not None:
        c.bump('output.typed', node.line, text='An output with its unit written')
    output_lines(c, node.lines, where)


OUTPUT_TEXT = {
    'top': '`output name: unit = E` at the top level',
    'thing': '`output name: unit = E` under a thing',
    'field': '`output x` under a thing: its field `x` is an output',
}


def flow(c, r, node, thing, symbols):
    line = node.line
    declared(c, node.name, 'flow', line)
    c.bump('flow', line, text='Flows, of every form')
    pairs = [node.pair] if node.pair is not None else list(node.together)
    if node.together is None:
        c.bump('flow.plain', line, text='`flow name: a -> b at RATE`: one pair')
        pair = node.pair
        if pair.source == 'outside':
            c.bump('flow.plain.from_outside', line, text='`flow name: -> b at RATE`: from outside the model')
        elif pair.target == 'outside':
            c.bump('flow.plain.to_outside', line, text='`flow name: a -> at RATE`: out of the model')
        else:
            c.bump('flow.plain.store_to_store', line, text='`flow name: a -> b at RATE`: between two vars')
    else:
        c.bump('flow.legs', line, text='`flow name at RATE:` with its pairs under it: pairs that move by one fraction')
        c.bump(f'flow.legs.pairs{len(node.together)}', line, text='… with that many pairs')
        evidence(c, node.together_support, 'flow')
        for pair in node.together:
            c.bump('flow.leg', pair.line, text='A pair of a flow with several pairs')
            if pair.rate is not None:
                c.bump('flow.leg.own_rate', pair.line, text='A pair with a rate of its own, `c -> d at other_rate`')
                r.read(pair.rate.expr, thing, 'rate')
            if pair.source == 'outside' or pair.target == 'outside':
                c.bump('flow.leg.outside', pair.line, text='A pair with one end outside the model')
            evidence(c, pair.support, 'flow pair')
    if node.keep is not None:
        c.bump('flow.while', line, text='`… while C`: a flow that moves only while a condition holds')
        r.read(node.keep.expr, thing, 'flow while')
    r.read(node.rate.expr, thing, 'rate')
    if is_literal(node.rate.expr.tokens):
        c.bump('flow.rate.literal', line, text='A flow whose rate is one number')
    shared = False
    for pair in pairs:
        for end in (pair.source, pair.target):
            if end != 'outside' and '.' in end:
                c.bump('flow.end.other_thing', pair.line, text='An end of a flow in another thing, `relief.supply -> received`')
        if pair.source != 'outside' and in_share(symbols, pair.source, thing):
            shared = True
            if node.together is not None:
                c.bump('flow.leg.in_share', pair.line, text='A pair of a flow with several pairs that drains a var with a `share`')
    if shared:
        c.bump('flow.in_share', line, text='A flow that drains a var with a `share`')
        if node.together is None:
            c.bump('flow.plain.in_share', line, text='A flow of one pair that drains a var with a `share`')
        else:
            c.bump('flow.legs.in_share', line, text='A flow with several pairs, one of which drains a var with a `share`')
    text_of(c, node.text, 'flow')
    evidence(c, node.support, 'flow')


def in_share(symbols, source, thing):
    """Whether a var that a flow drains has a `share` line in its thing."""
    found = symbols.read(source, thing)
    if found is None or found[0] != 'value':
        return False
    owner, member = found[2], found[3]
    info = symbols.things.get(owner)
    return info is not None and member in info.shares


def share(c, r, node, thing):
    line = node.line
    c.bump('share', line, text='`share VAR limit RATE [order f, g]`')
    if node.serve is None:
        c.bump('share.proportional', line, text='A share with no `order`: in proportion to what each flow asks')
    else:
        c.bump('share.order', line, text='A share with `order f, g`: the named flows first, in order')
        c.bump(f'share.order.flows{len(node.serve)}', line, text='… that names that many flows')
    if '.' in node.stock:
        c.bump('share.other_thing', line, text='A share of a var of another thing')
    r.read(node.limit.expr, thing, 'share limit')
    text_of(c, node.text, 'share')
    evidence(c, node.support, 'share')


def chance_kind(expr, thing, symbols):
    """`number`, `condition` or `expression` of the chance of an outcome."""
    tokens = expr.tokens
    if is_literal(tokens):
        return 'number'
    tree, names = oldmodel.tree_of(expr)
    if isinstance(tree, (ast.Compare, ast.BoolOp)) or (
        isinstance(tree, ast.UnaryOp) and isinstance(tree.op, ast.Not)
    ):
        return 'condition'
    if isinstance(tree, ast.Name):
        if tree.id in ('true', 'false'):
            return 'condition'
        found = symbols.read(names.get(tree.id, ''), thing)
        if found is not None and found[0] == 'value' and found[1] in ('input.bool', 'var.bool'):
            return 'condition'
    return 'expression'


def crossings(c, tree, names, thing, symbols, line):
    """The comparisons of a number var in a `when`: what a trigger watches between moments."""
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        sides = [node.left, node.comparators[0]]
        watched = False
        for side in sides:
            if isinstance(side, ast.Name) and side.id in names:
                found = symbols.read(names[side.id], thing)
                if found is not None and found[0] == 'value' and found[1] == 'var.number':
                    watched = True
        if not watched:
            continue
        op = node.ops[0]
        if isinstance(op, (ast.LtE, ast.GtE)):
            c.bump('event.when.var_comparison.inclusive', line, text='A `when` that compares a number var by `<=` or `>=`')
        elif isinstance(op, (ast.Lt, ast.Gt)):
            c.bump('event.when.var_comparison.strict', line, text='A `when` that compares a number var by `<` or `>`')
        else:
            c.bump('event.when.var_comparison.equal', line, text='A `when` that compares a number var by `is`')


def event(c, r, node, thing, symbols):
    line = node.line
    declared(c, node.name, 'event', line)
    c.bump('event', line, text='Events, of every form')
    parts = []
    if node.after is not None:
        parts.append('after')
    if node.each:
        parts.append('each')
    if node.when is not None:
        parts.append('when')
    form = '_'.join(parts) or 'named_only'
    c.bump(f'event.trigger.{form}', line, text=TRIGGER_TEXT.get(form, f'An event with {form}'))
    if node.once:
        c.bump('event.once', line, text='`once`: the event triggers at most once in a run')
        c.bump(f'event.once.{form}', line, text=f'`once` with the trigger form {form}')
    if node.keep is not None:
        c.bump('event.while', line, text='`while K` on the header: a firing that waits is cancelled when K fails')
        r.read(node.keep, thing, 'event while')
    if node.each:
        c.bump('event.each', line, text='`each W`: at most one trigger in each window')
        c.bump(f'event.each.values{len(node.each)}', line, text='… with that many window values')
        for item in node.each:
            r.read(item, thing, 'each')
    if node.name == 'start':
        c.bump('event.start', line, text='`event start when t >= 0 h:`: the start of the model')
    if node.after is not None:
        family = distribution_of(node.after.tokens)
        if is_literal(node.after.tokens) and family is None:
            c.bump('event.after.literal', line, text='`after 2 h`: a delay that is one number')
        elif family is not None:
            c.bump('event.after.distribution', line, text='`after pert(...)`: a delay that is drawn')
        else:
            c.bump('event.after.expression', line, text='`after D`: a delay that reads a value')
        r.read(node.after, thing, 'after')
    if node.when is not None:
        read = r.read(node.when, thing, 'when')
        if read is not None:
            tree, names = read
            crossings(c, tree, names, thing, symbols, line)
            called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            reads_t = any(isinstance(n, ast.Name) and n.id == 't' for n in ast.walk(tree))
            if reads_t:
                c.bump('event.when.reads_t', line, text='A `when` that reads the time `t`')
            for name in ('since', 'elapsed', 'count'):
                if name in called:
                    c.bump(f'event.when.reads_{name}', line, text=f'A `when` that reads `{name}()`')
    if node.choice:
        c.bump('event.choice', line, text='`choice` under an event: an actor chooses its outcome')
    if node.role is not None:
        c.bump('event.role', line, text='`role R` under an event')
    text_of(c, node.text, 'event')
    evidence(c, node.support, 'event')
    if not node.support:
        c.bump(f'event.no_record.{form}', line, text=f'An event of the form {form} with no record on its line')
    outcomes = node.outcomes
    if not outcomes:
        c.bump('event.no_lines', line, text='An event with no line under it: it changes nothing, and others read it')
    elif len(outcomes) == 1:
        only = outcomes[0]
        written = only.chance is not None or only.is_else or only.when is not None or only.text is not None
        if written or only.support or only.role is not None:
            c.bump('event.outcomes.one_written', line, text='An event with one outcome written by its name, `done C:`')
        else:
            c.bump('event.outcomes.lines', line, text='An event with its lines under it: the one outcome `done`')
    else:
        c.bump('event.outcomes.several', line, text='An event with two outcomes or more')
        c.bump(f'event.outcomes.several.n{len(outcomes)}', line, text='… with that many outcomes')
        kinds = set()
        for item in outcomes:
            if item.is_else:
                kinds.add('else')
            elif item.chance is None:
                kinds.add('none')
            else:
                kinds.add(chance_kind(item.chance, thing, symbols))
        if kinds <= {'condition', 'else'}:
            c.bump('event.outcomes.several.by_condition', line, text='… whose chances are all conditions (and `else`): the model decides')
        else:
            c.bump('event.outcomes.several.by_chance', line, text='… with a chance that is a number or an expression')
    explicit = len(outcomes) > 1 or (
        len(outcomes) == 1
        and (
            outcomes[0].chance is not None
            or outcomes[0].is_else
            or outcomes[0].when is not None
            or outcomes[0].text is not None
            or outcomes[0].support
            or outcomes[0].role is not None
        )
    )
    for item in outcomes:
        if explicit:
            c.bump('outcome', item.line, text='Outcomes written by their name')
            if item.is_else:
                c.bump('outcome.chance.else', item.line, text='`name else:`: 1 less the other chances')
            elif item.chance is None:
                c.bump('outcome.chance.none', item.line, text='An outcome with no chance: the chance 1')
            else:
                kind = chance_kind(item.chance, thing, symbols)
                c.bump(f'outcome.chance.{kind}', item.line, text=CHANCE_TEXT[kind])
                r.read(item.chance, thing, 'chance')
            if item.when is not None:
                c.bump('outcome.when', item.line, text='`name chance when C:`: when the outcome can happen')
                r.read(item.when, thing, 'outcome when')
            if item.role is not None:
                c.bump('outcome.role', item.line, text='`role R` under an outcome')
            text_of(c, item.text, 'outcome')
            evidence(c, item.support, 'outcome')
            if not item.lines:
                c.bump('outcome.no_lines', item.line, text='An outcome with no line: it changes nothing')
        for statement in item.lines:
            statement_of(c, r, statement, thing, symbols)


TRIGGER_TEXT = {
    'when': '`event e when C:`: it triggers each time C becomes true',
    'after_when': '`event e after D when C:`: it fires D after it triggers',
    'after': '`event e after D:` with no `when`',
    'named_only': '`event e:` with no `when`: it triggers only when a line names it',
    'each': '`event e each W:` with no `when`',
    'each_when': '`event e each W when C:`',
    'after_each_when': '`event e after D each W when C:`',
}
CHANCE_TEXT = {
    'number': 'An outcome whose chance is a number, `open 1:`',
    'condition': 'An outcome whose chance is a condition, `done mode is "x" and ready:`',
    'expression': 'An outcome whose chance is an expression, `manual 1 - shut_odds:`',
}


def statement_of(c, r, node, thing, symbols):
    line = node.line
    if isinstance(node, nodes.Assign):
        key = {'=': 'set', '+=': 'add', '-=': 'subtract'}[node.op]
        c.bump(f'stmt.{key}', line, text=STMT_TEXT[key])
        found = symbols.read(node.target, thing)
        kind = found[1] if found is not None and found[0] == 'value' else 'unresolved'
        c.bump(f'stmt.{key}.target.{kind}', line, text=f'… whose target is a {kind}')
        if '.' in node.target:
            c.bump(f'stmt.{key}.other_thing', line, text='… whose target is a value of another thing')
        tokens = node.value.tokens
        tree, _ = oldmodel.tree_of(node.value)
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)} if tree is not None else set()
        if calls & DISTRIBUTIONS:
            c.bump('stmt.draws', line, text='A line of an event that draws from a distribution')
        if 'delayed' in calls:
            c.bump('stmt.reads_delayed', line, text='A line of an event that reads `delayed(x, D)`')
        if not is_literal(tokens):
            c.bump(f'stmt.{key}.expression', line, text='… whose value is an expression (it reads the values from before the outcome)')
        r.read(node.value, thing, 'set')
    elif isinstance(node, nodes.Move):
        c.bump('stmt.move', line, text='`move A from S to D`')
        if '.' in node.source or '.' in node.target:
            c.bump('stmt.move.other_thing', line, text='A move with an end in another thing')
        if node.source == 'outside' or node.target == 'outside':
            c.bump('stmt.move.outside', line, text='A move with one end outside (an error in the old language)')
        r.read(node.amount, thing, 'move')
    elif isinstance(node, nodes.Fire):
        found = symbols.read(node.target, thing)
        if found is not None and found[0] == 'event' and found[4]:
            c.bump('stmt.fire.list', line, text='`list.e`: a line that fires the event of each member of a list')
        elif '.' in node.target:
            c.bump('stmt.fire.other_thing', line, text='`thing.e`: a line that fires an event of another thing')
        else:
            c.bump('stmt.fire.own', line, text='`e`: a line that fires an event of the same thing')
        if found is None or found[0] != 'event':
            c.bump('stmt.fire.unresolved', line, text='A line that names an event this census did not resolve')


STMT_TEXT = {
    'set': '`x = v` in an event',
    'add': '`x += v` in an event',
    'subtract': '`x -= v` in an event',
}


def status(c, r, node, thing):
    c.bump('status.block', node.line, text='Things with `status` lines')
    ratings = collections.Counter()
    for case in node.lines:
        c.bump('status.case', case.line, text='`status rating [when C]` lines')
        c.bump(f'status.case.rating.{case.status}', case.line, text=f'`status {case.status} …`')
        ratings[case.status] += 1
        if case.condition is None:
            c.bump('status.case.fallback', case.line, text='A status line with no condition')
        else:
            c.bump('status.case.when', case.line, text='A status line with `when C`')
            r.read(case.condition, thing, 'status when')
        text_of(c, case.text, 'status')
        if case.text is None:
            c.bump('status.case.no_text', case.line, text='A status line with no text')
    if node.lines and node.lines[-1].condition is not None:
        c.bump('status.block.no_fallback', node.line, text='A status whose last line has a condition')
    if any(n > 1 for n in ratings.values()):
        c.bump('status.block.repeated_rating', node.line, text='A status with two cases of one rating and different texts')
    evidence(c, node.support, 'status')


def check(c, r, node, thing, where):
    line = node.line
    c.bump('assert', line, text='`assert` lines')
    c.bump(f'assert.{where}', line, text=f'`assert` {"at the top level" if where == "top" else "under a thing"}')
    if node.kind == 'conserve':
        c.bump('assert.sum', line, text='`assert a + b is T within TOL`: a sum of number vars')
        c.bump(f'assert.sum.terms{min(len(node.terms), 5)}', line, text='… with that many terms (5: five or more)')
        for term, _ in node.terms:
            head = term.split('.')[0]
            if head[:1].isupper():
                c.bump('assert.sum.list_term', line, text='A term of a sum that names a list, `Zone.held`')
        r.read(node.total, thing, 'assert')
        r.read(node.within.expr, thing, 'within')
    else:
        c.bump('assert.condition', line, text='`assert C`: a condition')
        r.read(node.expr, thing, 'assert')
        if node.within is not None:
            c.bump('assert.condition.within', line, text='`assert C within TOL` that is no sum')
            r.read(node.within.expr, thing, 'within')
    if node.within is not None:
        c.bump('assert.within', line, text='`assert … within TOL`')
    else:
        c.bump('assert.no_within', line, text='`assert` with no `within`')
    text_of(c, node.text, 'assert')
    evidence(c, node.support, 'assert')


def change(c, r, node, thing, where):
    """A line of an instance or of a change block."""
    line = node.line
    lines = node.lines
    if node.kind is not None:
        kind = oldmodel.field_kind(lines)
        c.bump(f'{where}.line.new_kind', line, text='`input m = v` / `let m: u = E` in an instance: a new kind of value for a member')
        c.bump(f'{where}.line.new_kind.{kind}', line, text=f'… that makes the member a {kind}')
    elif lines.value is not None:
        c.bump(f'{where}.line.value', line, text='`m = v  @r` in an instance: a new value for a member')
        found = r.symbols.read(node.name, thing)
        kind = found[1] if found is not None and found[0] == 'value' else 'unresolved'
        c.bump(f'{where}.line.value.sets.{kind}', line, text=f'… of a member that is a {kind}')
        if lines.min is not None:
            c.bump(f'{where}.line.value.range', line, text='… with a new range')
        if not lines.support:
            c.bump(f'{where}.line.value.no_record', line, text='… with no record of its own (a text value needs none)')
        tokens = lines.value.tokens
        if not is_literal(tokens):
            c.bump(f'{where}.line.value.expression', line, text='… whose value is an expression')
    elif lines.output is None:
        c.bump(f'{where}.line.member_block', line, text='`m:` with lines under it: a new text or new records for a member')
    if lines.output is not None:
        c.bump(f'{where}.line.output', line, text='`output m` in an instance: new lines of the output of a member')
        output_lines(c, lines.output, 'field')
    if lines.text is not None:
        c.bump(f'{where}.line.text', line, text='A new text for a member of an instance')
        text_of(c, lines.text, 'field')
    r.read(lines.value, thing, 'value')
    if lines.min is not None:
        r.read(lines.min.expr, thing, 'range')
        r.read(lines.max.expr, thing, 'range')
    evidence(c, lines.support, 'instance line')


def thing_of(c, r, thing, symbols, block='thing'):
    line = thing.line
    name = thing.name
    if block != 'change':
        declared(c, name, 'thing', line)
    if block == 'change':
        c.bump('change', line, text='`change name:`: a block that gives a thing of an earlier file the lines of an instance')
        where = 'change'
    elif thing.copies is not None:
        c.bump('thing.copies', line, text='`name: Template * k`: k copies')
        where = 'instance'
    elif thing.table is not None:
        c.bump('thing.table', line, text='`name: Template from "file.csv"`: one instance for each row of a table')
        where = 'instance'
    elif thing.template is not None:
        c.bump('thing.instance', line, text='`name: Template`: an instance of a template')
        where = 'instance'
        if not thing.members and thing.text is None and thing.title is None:
            c.bump('thing.instance.bare', line, text='… with no line under it')
    elif thing.kind == 'template':
        c.bump('thing.template', line, text='`Template:`: a template')
        where = 'thing'
    else:
        c.bump('thing.entity', line, text='`name:`: a thing made without a template')
        where = 'thing'
    text_of(c, thing.text, 'thing')
    if thing.title is not None:
        c.bump('thing.title', thing.title.line, text='`title "…"` under a thing')
    if thing.role is not None:
        c.bump('thing.role', line, text='`role R` under a thing')
        c.bump(f'thing.role.{thing.role}', line, text=f'`role {thing.role}`')
    if thing.sees is not None:
        c.bump('thing.sees', line, text='`sees a, b.c`: the thing is an actor')
        for fact, _ in thing.sees:
            found = symbols.read(fact, name)
            kind = found[0] if found is not None else 'unresolved'
            c.bump(f'thing.sees.fact.{kind}', line, text=f'A fact that an actor sees: a {kind}')
    evidence(c, thing.support, 'thing')
    for member in thing.members:
        if isinstance(member, nodes.Value):
            field(c, r, member, name)
        elif isinstance(member, nodes.LinkDecl):
            key = 'many' if member.many else 'one'
            c.bump(f'link.declare.{key}', member.line, text=LINK_TEXT[f'declare.{key}'])
        elif isinstance(member, nodes.LinkBind):
            if member.many and not member.targets:
                key = 'empty_list'
            elif member.many:
                key = 'list'
            elif member.targets in symbols.templates:
                key = 'template'
            else:
                key = 'one'
            c.bump(f'link.bind.{key}', member.line, text=LINK_TEXT[f'bind.{key}'])
            if where != 'thing':
                c.bump(f'link.bind.in_instance', member.line, text='A link bound in an instance (or a change block)')
            else:
                c.bump(f'link.bind.in_thing', member.line, text='A link bound in a thing made without a template, or in a template')
        elif isinstance(member, nodes.Change):
            change(c, r, member, name, where if where != 'thing' else 'instance')
        elif isinstance(member, nodes.Event):
            event(c, r, member, name, symbols)
        elif isinstance(member, nodes.Flow):
            flow(c, r, member, name, symbols)
        elif isinstance(member, nodes.Allocate):
            share(c, r, member, name)
        elif isinstance(member, nodes.Check):
            check(c, r, member, name, 'in_thing')
        elif isinstance(member, nodes.Output):
            output(c, r, member, name, 'thing')
        elif isinstance(member, nodes.Status):
            status(c, r, member, name)
            if where != 'thing':
                c.bump(f'{where}.status', member.line, text='`status` lines in an instance or a change block')
        else:
            c.bump(f'thing.member.unknown.{type(member).__name__}', getattr(member, 'line', None))


LINK_TEXT = {
    'declare.one': '`let region: Region`: a slot for one thing, which each instance binds',
    'declare.many': '`let regions: [Region]`: a slot for a list of things',
    'bind.one': '`let region = inland`: a link to one thing',
    'bind.list': '`let zones = [near, middle]`: a link to a list of things',
    'bind.empty_list': '`let regions = []`: a list of no things',
    'bind.template': '`let zones = Zone`: the list of the instances of a template',
}


def notes(c, items, depth=1):
    deepest = depth if items else depth - 1
    for note in items:
        c.bump('note', note.line, text='Notes: `key: value` lines under `notes:`')
        if depth == 1:
            c.bump(f'note.top.{note.key}', note.line, text=f'The top-level note `{note.key}:`')
        value = note.value
        if value is None:
            kind = 'none'
        elif isinstance(value, nodes.Text):
            kind = 'text'
        elif isinstance(value, list):
            kind = 'list'
        elif isinstance(value, lex.Token):
            kind = 'number'
        else:
            kind = 'word'
        c.bump(f'note.value.{kind}', note.line, text=f'A note whose value is {"nothing: it holds notes" if kind == "none" else "a " + kind}')
        if note.support:
            c.bump('note.with_evidence', note.line, text='A note that cites or holds a record')
        evidence(c, note.support, 'note')
        deepest = max(deepest, notes(c, note.under, depth + 1))
    return deepest


def census_of(path):
    relative = path.relative_to(BASE).as_posix()
    c = Census(relative)
    text = path.read_text(encoding='utf-8')
    file, symbols = oldmodel.symbols_for(path)
    r = Reader(c, symbols)
    flat = lex.lines(text)
    physical = text.count('\n') + (0 if text.endswith('\n') else 1)
    c.bump('lines.physical', n=physical, text='Lines of the file')
    c.bump('lines.logical', n=sum(1 for row in flat if row.kind == 'line'), text='Logical lines: a line with what its brackets and texts carry on')
    c.bump('lines.comment', n=sum(1 for row in flat if row.kind == 'comment'), text='Comment lines')
    c.bump('lines.blank', n=sum(1 for row in flat if row.kind == 'blank'), text='Empty lines')
    c.bump(f'file.role.{file.role}', 1, text=f'Files whose first declaration makes them a {file.role}')
    block = file.scenario
    if block is not None:
        key = 'scenario' if block.role == 'main' else 'variant'
        c.bump(f'{key}.line', block.line, text='`scenario "Title"`' if key == 'scenario' else '`variant "Title"`')
        for part in ('summary', 'horizon', 'resolution', 'scope', 'library'):
            if getattr(block, part) is not None:
                c.bump(f'{key}.{part}', getattr(block, part).line, text=f'`{part} …` under the {key} line')
        if block.timescales is not None:
            c.bump(f'{key}.timescales', block.timescales[0].line, text=f'`timescales a, b` under the {key} line')
            c.bump(f'{key}.timescales.values', block.timescales[0].line, n=len(block.timescales), text='The values that `timescales` lists')
            for item in block.timescales:
                r.read(item, None, 'timescales')
                if not is_literal(item.tokens) and len(item.tokens) > 1 and '.' not in ''.join(t.source for t in item.tokens[1:2]):
                    pass
        if block.horizon is not None:
            r.read(block.horizon, None, 'horizon')
        if block.resolution is not None:
            r.read(block.resolution, None, 'resolution')
    for use in file.uses:
        c.bump('use', use.line, text='`use NAME`: a module of the package')
    for thing in file.things:
        thing_of(c, r, thing, symbols)
    for item in file.changes:
        thing_of(c, r, item, symbols, block='change')
    for item in file.checks:
        check(c, r, item, None, 'top')
    for item in file.outputs:
        output(c, r, item, None, 'top')
    for group in file.profiles:
        c.bump('options.group', group.line, text='`options "Group":`')
        for option in group.profiles:
            c.bump('options.option', option.line, text='`"Option":` under a group')
            if option.text is None:
                c.bump('options.option.no_text', option.line, text='An option with no text')
            if not option.settings:
                c.bump('options.option.no_setting', option.line, text='An option that sets nothing: the values as the file writes them')
            for setting in option.settings:
                c.bump('options.setting', setting.line, text='`thing.field = v` in an option')
                head, _, member = setting.target.rpartition('.')
                if head in symbols.templates:
                    c.bump('options.setting.template', setting.line, text='`Template.field = v`: every instance of a template')
                else:
                    c.bump('options.setting.thing', setting.line, text='`thing.field = v`: one thing')
                found = symbols.read(setting.target, None)
                kind = found[1] if found is not None and found[0] == 'value' else 'unresolved'
                c.bump(f'options.setting.sets.{kind}', setting.line, text=f'… that sets a {kind}')
                if setting.support:
                    c.bump('options.setting.with_record', setting.line, text='… with a record')
                else:
                    c.bump('options.setting.no_record', setting.line, text='… with no record (the old compiler asks for none)')
                    c.bump(f'options.setting.no_record.{kind}', setting.line, text=f'… with no record, on a {kind}')
                if not is_literal(setting.value.tokens):
                    c.bump('options.setting.expression', setting.line, text='… whose value is an expression')
                r.read(setting.value, None, 'option')
                evidence(c, setting.support, 'option line')
    if file.runs_place is not None:
        c.bump('runs.block', file.lines.get(file.runs_place), text='`runs:` blocks')
    baselines = set()
    for run in file.runs:
        c.bump('run', run.line, text='`name = "Option" + "Option"` lines of `runs:`')
        c.bump(f'run.options{min(len(run.profiles), 8)}', run.line, text='A run that names that many options (8: eight or more)')
        if run.versus is not None:
            c.bump('run.versus', run.line, text='A run with `versus other`: a comparison')
            baselines.add(run.versus)
        else:
            c.bump('run.no_versus', run.line, text='A run with no `versus`')
        if run.text is not None:
            c.bump('run.text', run.line, text='A run with its text under it')
    if baselines:
        c.bump('run.versus.baselines', n=len(baselines), text='Distinct runs that a `versus` names')
    if file.notes is not None:
        c.bump('notes.block', file.notes[0].line if file.notes else None, text='`notes:` blocks')
        deepest = notes(c, file.notes)
        c.counts['note.depth.max'] = deepest
        describe('note.depth.max', 'The deepest nesting of notes (a maximum, not a sum)')
    for record in file.records:
        c.bump('evidence.record.named', record.line, text='`record name: kind [ID] "explanation"`')
        c.bump(f'evidence.record.named.kind.{record.kind}', record.line, text=f'A named record of kind `{record.kind}`')
        if record.id is not None:
            c.bump('evidence.record.named.id', record.line, text='A named record with an ID')
        claims(c, record)
    for thing in file.things:
        if thing.table is not None and thing.table.columns:
            c.bump('table.column', thing.line, n=len(thing.table.columns), text='Columns of tables')
    return c, file


# ---- the compiled models -----------------------------------------------------------------------------------


def compiled(path):
    """What the old compiler says of one entry model: the kinds of its parts and what it proved."""
    from napkin.model.model import build_model

    started = time.time()
    model = build_model(path)
    out = {'seconds_to_build': round(time.time() - started, 2)}
    out['runs'] = {
        name: {'options': list(run['options']), 'versus': run['comparison_of']} for name, run in model.runs.items()
    }
    out['start_options'] = list(model.start_options)
    out['structures'] = len(model.structures)
    key = next(iter(model.structures))
    structure = model.structures[key]
    whole = model.whole[key]
    counts = collections.Counter()
    for q in whole.quantities.values():
        counts[f'quantity.{q.kind}'] += 1
        if q.maximum is not None:
            counts['quantity.with_maximum'] += 1
        if q.size is not None:
            counts['quantity.with_size'] += 1
    counts['parameter'] = len(whole.parameters)
    counts['mode'] = len(whole.modes)
    counts['computed'] = len(whole.computed)
    counts['label'] = len(whole.labels)
    counts['entity'] = len(whole.entities)
    counts['entity.actor'] = sum(1 for e in whole.entities.values() if e.sees is not None)
    for f in whole.flows.values():
        counts['flow'] += 1
        counts['flow.in_allocation'] += f.allocation is not None
        ends = ('outside' if f.source is None else 'store', 'outside' if f.target is None else 'store')
        counts[f'flow.{ends[0]}_to_{ends[1]}'] += 1
    for a in whole.allocation.values():
        counts[f'allocation.{a.policy}'] += 1
    counts['coupling'] = len(whole.coupling)
    counts['coupling.flows'] = sum(len(x.flows) for x in whole.coupling.values())
    for rule in whole.rules.values():
        counts['rule'] += 1
        counts[f'rule.trigger.{rule.trigger.kind}'] += 1
        if rule.trigger.kind in ('crossing', 'face'):
            counts[f'rule.trigger.{rule.trigger.kind}.op.{rule.trigger.op}'] += 1
        counts['rule.once'] += bool(rule.once)
        counts['rule.delay'] += rule.delay is not None
        counts['rule.each'] += bool(rule.each)
        counts['rule.keep'] += rule.keep is not None
        counts['rule.choice'] += bool(rule.choice)
        counts['rule.extras'] += bool(rule.extras)
        counts['rule.named'] += bool(rule.named)
        counts[f'rule.outcomes{min(len(rule.outcomes), 3)}'] += 1
    # The whole structure keeps no check: the structure that acts has them.
    counts['check.input'] = len(structure.input_checks)
    counts['check.state'] = len(structure.state_checks)
    counts['partition'] = len(whole.partitions)
    proved = {}
    for name in model.runs:
        resolved = model.resolve(name)
        proved[name] = list(resolved.proven_cumulative_outcomes)
    outcomes = {}
    for name, o in whole.outcomes.items():
        counts[f'outcome.{o.kind}'] += 1
        counts[f'outcome.status.{o.status}'] += 1
        counts['outcome.lag'] += o.lag is not None
        counts['outcome.nonnegative'] += bool(o.nonnegative)
        outcomes[name] = {'kind': o.kind, 'status': o.status, 'nonnegative': o.nonnegative, 'lag': o.lag is not None}
    runs = list(proved.values())
    same = all(set(x) == set(runs[0]) for x in runs) if runs else True
    out['proven_cumulative_outcomes'] = sorted(set().union(*map(set, runs))) if runs else []
    out['proven_cumulative_same_in_every_run'] = same
    counts['outcome.proven_cumulative'] = len(out['proven_cumulative_outcomes'])
    out['counts'] = dict(sorted(counts.items()))
    out['outcomes'] = outcomes
    return out


# ---- the report ---------------------------------------------------------------------------------------------

GROUPS = [
    ('examples', lambda p: p.startswith('examples/')),
    ('cyber', lambda p: p.startswith('scenarios/cyber_learning_loop/')),
    ('heat', lambda p: p.startswith('scenarios/heat_wave_blackout/')),
    ('iv', lambda p: p.startswith('scenarios/iv_fluid_shortage/')),
    ('water.scn', lambda p: p == 'scenarios/water_controls_wipe/water.scn'),
    ('water main', lambda p: p == 'scenarios/water_controls_wipe/model.scn'),
    ('16 variants', lambda p: '/variants/' in p),
]
MAXIMA = {'note.depth.max'}


def grouped(files):
    totals = collections.Counter()
    by_group = {name: collections.Counter() for name, _ in GROUPS}
    where = {}
    for relative, item in files.items():
        for key, n in item['counts'].items():
            if key in MAXIMA:
                totals[key] = max(totals[key], n)
            else:
                totals[key] += n
            for name, test in GROUPS:
                if test(relative):
                    if key in MAXIMA:
                        by_group[name][key] = max(by_group[name][key], n)
                    else:
                        by_group[name][key] += n
        for key, lines in item['where'].items():
            seen = where.setdefault(key, [])
            for line in lines:
                if len(seen) < 3:
                    seen.append(f'{relative}:{line}')
    return totals, by_group, where


SECTIONS = [
    ('Files and lines', ('lines.', 'file.')),
    ('The scenario line, variants, modules', ('scenario.', 'variant.', 'use', 'change')),
    ('Things', ('thing.', 'instance.', 'link.', 'table.')),
    ('Fields', ('field.',)),
    ('Flows and shares', ('flow', 'share')),
    ('Events', ('event', 'outcome', 'stmt.')),
    ('Status, asserts, outputs', ('status.', 'assert', 'output.')),
    ('Options and runs', ('options.', 'runs.', 'run')),
    ('Notes', ('notes.', 'note')),
    ('Evidence', ('evidence.',)),
    ('Texts', ('text.',)),
    ('Functions and expressions', ('fn.', 'dist.', 'expr', 'type.')),
    ('Names', ('name.',)),
]


def section_of(key):
    for title, prefixes in SECTIONS:
        for prefix in prefixes:
            if key == prefix or key.startswith(prefix if prefix.endswith('.') else prefix + '.') or key == prefix.rstrip('.'):
                return title
    return 'Other'


def markdown(data):
    files = data['files']
    totals, by_group, where = grouped(files)
    out = []
    out.append('# Census of the catalogue at the base commit')
    out.append('')
    out.append(
        f'Made by `census.py` with the old parser at `{data["base"]}` (commit {data["commit"]}). '
        'Every count is of parsed nodes. No count comes from a text pattern.'
    )
    out.append('')
    out.append(f'Files: {len(files)}. Lines: {totals["lines.physical"]}. Keys counted: {len(totals)}.')
    out.append('')
    out.append('Columns: the two `examples/` models; `cyber_learning_loop`; `heat_wave_blackout`; ')
    out.append('`iv_fluid_shortage`; `water_controls_wipe/water.scn`; its main `model.scn`; its 16 variants together.')
    out.append('"Where" gives up to three places, as `file:line`.')
    out.append('')
    out.append('## Forms that the language has and the catalogue never uses')
    out.append('')
    absent = [key for key in EXPECTED if totals.get(key, 0) == 0]
    for key in absent:
        out.append(f'- `{key}`: {EXPECTED[key]}')
    out.append('')
    keys_by_section = collections.defaultdict(list)
    for key in sorted(totals):
        keys_by_section[section_of(key)].append(key)
    names = [name for name, _ in GROUPS]
    for title, _ in [*SECTIONS, ('Other', ())]:
        keys = keys_by_section.get(title)
        if not keys:
            continue
        out.append(f'## {title}')
        out.append('')
        out.append('| Key | What it counts | Total | ' + ' | '.join(names) + ' | Where |')
        out.append('| --- | --- | ---: | ' + ' | '.join('---:' for _ in names) + ' | --- |')
        for key in keys:
            cells = [str(by_group[name].get(key, 0) or '') for name in names]
            first = ', '.join(short(w) for w in where.get(key, [])[:2])
            text = data['keys'].get(key, '').replace('|', '\\|')
            out.append(f'| `{key}` | {text} | {totals[key]} | ' + ' | '.join(cells) + f' | {first} |')
        out.append('')
    if data.get('models'):
        out.append('## What the old compiler makes of each model')
        out.append('')
        out.append(
            'One row for each entry file, from `build_model`. The counts are of the compiled model, with each '
            'instance of a template written out. "Stock", "tally" and "number state" are what the compiler '
            'found for each number var (`Quantity.kind`: `stock`, `cumulative`, `variable`). The trigger '
            'kinds are those of `Trigger.kind`.'
        )
        out.append('')
        head = ['Model', 'Things', 'Inputs', 'Stocks', 'Tallies', 'Number states', 'Named states', 'Formulas', 'Flows', 'in a share', 'Shares (order / proportional)', 'Flows with legs', 'Rules', 'discrete / timer / crossing / face', 'Outputs', 'cumulative / level', 'Proved cumulative', 'Unestimated', 'Sum checks', 'Runs']
        out.append('| ' + ' | '.join(head) + ' |')
        out.append('| ' + ' | '.join(['---'] + ['---:'] * (len(head) - 1)) + ' |')
        for relative, model in data['models'].items():
            if 'error' in model:
                out.append(f'| `{short(relative)}` | does not build alone: {model["error"]} |' + ' |' * (len(head) - 2))
                continue
            n = collections.Counter(model['counts'])
            row = [
                f'`{short(relative)}`',
                n['entity'],
                n['parameter'],
                n['quantity.stock'],
                n['quantity.cumulative'],
                n['quantity.variable'],
                n['mode'],
                n['computed'],
                n['flow'],
                n['flow.in_allocation'],
                f'{n["allocation.priority"]} / {n["allocation.proportional"]}',
                n['coupling'],
                n['rule'],
                f'{n["rule.trigger.discrete"]} / {n["rule.trigger.timer"]} / {n["rule.trigger.crossing"]} / {n["rule.trigger.face"]}',
                sum(v for k, v in n.items() if k.startswith('outcome.status.')),
                f'{n["outcome.cumulative"]} / {n["outcome.stock"]}',
                n['outcome.proven_cumulative'],
                n['outcome.status.unestimated'],
                n['partition'],
                len(model['runs']),
            ]
            out.append('| ' + ' | '.join(map(str, row)) + ' |')
        out.append('')
        out.append('### The outputs that the old compiler proved cumulative')
        out.append('')
        out.append('`check.py` lists these for a translation. The new compiler must prove that each of them never falls.')
        out.append('')
        seen = {}
        for relative, model in data['models'].items():
            if 'error' in model:
                continue
            key = tuple(model['proven_cumulative_outcomes'])
            seen.setdefault(key, []).append(short(relative))
        for key, models in seen.items():
            listed = ', '.join(f'`{name}`' for name in key) or 'none'
            shown = ', '.join(models) if len(models) <= 4 else f'{models[0]} and {len(models) - 1} more'
            out.append(f'- {shown}: {listed}')
        out.append('')
        out.append('### Other keys of the compiled models, summed over the entry files')
        out.append('')
        summed = collections.Counter()
        for model in data['models'].values():
            if 'error' not in model:
                summed.update(model['counts'])
        out.append('| Key | Sum |')
        out.append('| --- | ---: |')
        for key in sorted(summed):
            out.append(f'| `{key}` | {summed[key]} |')
        out.append('')
    return '\n'.join(out) + '\n'


def short(relative):
    return (
        relative.replace('scenarios/water_controls_wipe/variants/', 'water/variants/')
        .replace('scenarios/water_controls_wipe/', 'water/')
        .replace('scenarios/', '')
        .replace('/model.scn', '')
    )


# Forms of docs/language.md that the report names when the catalogue has none of them.
EXPECTED = {
    'thing.copies': '`name: Template * k`, and so `copy` in an expression',
    'thing.table': '`name: Template from "file.csv"`',
    'change': '`change name:` blocks',
    'event.each': '`each W` windows',
    'event.while': '`while K` on the header of an event',
    'event.after.distribution': 'a drawn delay, `after pert(...)`',
    'event.trigger.after': '`after D` with no `when`',
    'event.when.var_comparison.strict': 'a `when` that compares a number var by `<` or `>`',
    'fn.delayed': '`delayed(x, D)`',
    'fn.count.list': '`count(list.flag)`',
    'fn.any.list': '`any(list.flag)`',
    'fn.all.list': '`all(list.flag)`',
    'fn.min.list': '`min(list.x)`',
    'fn.max.list': '`max(list.x)`',
    'fn.min.list_with_extra': '`min(list.x, v)`',
    'fn.max.list_with_extra': '`max(list.x, v)`',
    'fn.since.outcome': '`since(e.o)` of one outcome',
    'fn.since.state': '`since(state)` of a named state',
    'fn.elapsed': '`elapsed(state)`',
    'name.read.unresolved': 'a name that this census did not resolve',
    'fn.since.unresolved': '`since()` whose argument this census did not resolve',
    'fn.count.unresolved': '`count()` whose argument this census did not resolve',
    'stmt.fire.unresolved': 'a line that names an event this census did not resolve',
    'expr.unreadable': 'an expression that the old reader does not read alone',
    'fn.count.outcome': '`count(e.o)` of one outcome',
    'output.set.lag.fixed': '`lag 2 h`',
    'output.set.lag.uniform': '`lag uniform(a, b)`',
    'output.set.lag.mixture': '`lag mixture(...)`',
    'field.input.named': 'an input with named values',
    'field.var.bool': 'a yes/no state, `var found = false`',
    'expr.copy': '`copy`',
    'expr.power': '`a ** b`',
    'expr.unit.power': 'a unit with a power, `m^2`',
    'dist.declaration.bernoulli': '`bernoulli(p)`',
    'dist.declaration.categorical': '`categorical(...)`',
    'dist.keyword_arguments': 'a distribution with arguments by name, `normal(a, b, min=c)`',
    'stmt.subtract': '`x -= v`',
    'stmt.move': '`move A from S to D`',
    'stmt.fire.list': '`list.e`',
    'stmt.reads_delayed': 'a line that reads `delayed`',
    'stmt.draws': 'a line of an event that draws',
    'text.event.list': 'a list of texts on an event',
    'assert.condition.within': '`assert C within TOL` that is no sum',
    'assert.sum.list_term': 'a term of a sum check that names a list',
    'instance.line.new_kind': 'a new kind of value for a member of an instance',
    'instance.line.member_block': '`m:` with new text or records in an instance',
    'instance.line.output': '`output m` in an instance',
    'instance.status': '`status` lines in an instance',
    'link.bind.empty_list': '`let xs = []`',
    'thing.sees': '`sees`',
    'event.choice': '`choice`',
    'scenario.resolution': '`resolution`',
    'scenario.timescales': '`timescales`',
    'variant.horizon': 'a variant with a `horizon` of its own',
    'variant.resolution': 'a variant with a `resolution` of its own',
    'variant.timescales': 'a variant with `timescales` of its own',
    'options.setting.sets.var.named': 'an option that sets the start of a named state',
    'options.setting.sets.var.number': 'an option that sets the start of a number var',
    'options.setting.sets.input.text': 'an option that sets a text value',
    'options.setting.sets.let.fixed': 'an option that sets a `let`',
    'options.setting.expression': 'an option whose value is an expression',
    'note.value.list': 'a note whose value is a list',
    'note.value.number': 'a note whose value is a number',
    'flow.leg.own_rate': 'a pair with a rate of its own',
    'flow.while': 'a flow with `while`',
    'share.order': 'a share with `order`',
    'status.block.no_fallback': 'a status whose last line has a condition',
}


def main(argv):
    do_compile = '--no-compile' not in argv
    files = {}
    for path in oldmodel.model_files():
        c, _ = census_of(path)
        files[c.relative] = {'counts': dict(sorted(c.counts.items())), 'where': c.where}
    import subprocess

    commit = subprocess.run(
        ['git', '-C', str(BASE), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, check=False
    ).stdout.strip()
    data = {'base': str(BASE), 'commit': commit, 'files': files, 'keys': dict(sorted(DESCRIPTIONS.items()))}
    totals, by_group, where = grouped(files)
    data['totals'] = dict(sorted(totals.items()))
    data['groups'] = {name: dict(sorted(counter.items())) for name, counter in by_group.items()}
    data['where'] = where
    data['absent'] = {key: text for key, text in EXPECTED.items() if totals.get(key, 0) == 0}
    if do_compile:
        models = {}
        for path in oldmodel.entry_files():
            relative = path.relative_to(BASE).as_posix()
            try:
                models[relative] = compiled(path)
            except Exception as exc:  # the main file of the water package has no instance
                message = str(exc).splitlines()[0][:200]
                models[relative] = {'error': f'{type(exc).__name__}: {message}'}
        data['models'] = models
    (HERE / 'census.json').write_text(json.dumps(data, indent=1, sort_keys=False) + '\n', encoding='utf-8')
    (HERE / 'census.md').write_text(markdown(data), encoding='utf-8')
    print(f'{len(files)} files, {totals["lines.physical"]} lines, {len(totals)} keys')
    print(f'wrote {HERE / "census.json"} and {HERE / "census.md"}')


if __name__ == '__main__':
    main(sys.argv[1:])
