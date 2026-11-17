"""The expressions of a structure, as typed nodes with the flat names of the structure.

Two steps, with no text between them.

- `Typing` reads an expression whose names the front end resolved (`resolved`) and gives a
  typed node (`napkin/core/expr.py`) with the structure's names. It checks each part: a bool reads as
  the engine's 0/1 number, a test of a named input as a test of its code, a formula that is written
  in line as its expression, and a sum over a list as the sum of its members.
- `desugared` gives the engine's form of such a node. The structure keeps one meaning for each name:
  `count(e)` becomes `e__count`, a comparison with `since(e)` becomes
  `(e__count > 0 and t - e__time OP x)`, and `elapsed(s)` becomes `(t - s__entered)`.

Each form of the language that is no operation of the engine has one function here:

| The file writes | The function | What the structure holds |
| --- | --- | --- |
| `count(e)` | `count_form` | a read of `e__count` |
| `since(e) OP x` | `since_form` | `(e__count > 0 and t - e__time OP x)` |
| `elapsed(s)` | `elapsed_form` | `t - s__entered` |
| `sum`, `count`, `any`, `all`, `min`, `max` of a list | `Typing.reduction`, `Typing.call` | the members, one by one |
| `delayed(x, D)` in an event | `Firing.delayed` | a name of the event, with `x` and `D` among its `extras` |
| a distribution in an event | `Firing.draw` | a name of the event, with the family and its arguments among its `extras` |
| a bare number in a typed field | `typed` | a quantity of the field's unit |

An event with a window (`each W`) and a waiting condition (`while`) are parts of a rule, which the
builder writes (`Builder.event_part`).
"""

from __future__ import annotations

import ast
import re

from ...core import expr as nodes
from .. import resolved
from ..ir import COUNT, DRAWN, ENTERED, FIRING_VALUE, RESERVED, TIME, diagnostic, thaw
from ..semantic import AnalysisError, split_key


class RewriteError(Exception):
    def __init__(self, path, message, code='reference'):
        self.diagnostic = diagnostic(code, path, message)
        super().__init__(f'{path}: {message}')


def expression_text(value):
    if isinstance(value, bool):
        return 'True' if value else 'False'
    if isinstance(value, (int, float)):
        return repr(value)
    return value


_NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?')


def typed(value, unit):
    """A typed value field: a bare number (or a copy value that is one) is in the field's unit;
    other text is an expression."""
    if isinstance(value, str) and _NUMBER.fullmatch(value.strip()):
        value = float(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return f'q({value!r}, {unit!r})' if value != 0 else '0'


# The functions of an expression before `desugared`: those of the engine, and the three that it
# turns into reads of names.
WRITTEN = nodes.FUNCTIONS | {'count', 'since', 'elapsed'}


def source_node(value, path):
    """The node of a source that the builder gives: a node, a number, a yes/no or an expression text."""
    if isinstance(value, nodes.Node):
        if not nodes.outside(value):
            return value
        # A part outside the language is read again from its text, as it always was.
        value = nodes.text(value)
    text = expression_text(value)
    if not isinstance(text, str) or not text.strip():
        raise RewriteError(path, 'an expression must be a nonempty string or a number', 'expression')
    try:
        return nodes.parse(text, WRITTEN)
    except SyntaxError as exc:
        raise RewriteError(path, f'invalid expression: {exc.msg}', 'expression') from exc


def _reserved(symbol, path):
    """A name that holds `__` is the structure's own, but for the time and for a value that a firing
    event reads (`Firing`)."""
    if symbol != 't' and not FIRING_VALUE.search(symbol) and RESERVED in symbol:
        raise RewriteError(path, f'names may not contain {RESERVED!r}: {symbol}')


def _one_name(call, message, path):
    """The name that is the one argument of a call."""
    if len(call.args) != 1 or not isinstance(call.args[0], nodes.Ref):
        raise RewriteError(path, message)
    return call.args[0].name


def count_form(call, path):
    """`count(e)`: how many times the event has happened. The structure keeps that number under the
    name `e__count`."""
    return nodes.ref(_one_name(call, 'count() takes one event name', path) + COUNT)


def elapsed_form(call, path):
    """`elapsed(s)`: the time since the named state took its present value. The structure keeps the
    time of that moment under the name `s__entered`, so the form is `t - s__entered`."""
    state = _one_name(call, 'elapsed() takes one named state', path)
    return nodes.binary('sub', nodes.ref('t'), nodes.ref(state + ENTERED))


def since_form(comparison, visit, path):
    """`since(e) OP x`, or `x OP since(e)`: the time since the event last happened, compared with one
    value. It holds only after the event has happened: `(e__count > 0 and t - e__time OP x)`, with the
    time of the last happening under the name `e__time`. `visit` gives the form of the other side."""
    sides = comparison.operands
    since = [i for i, side in enumerate(sides) if isinstance(side, nodes.Call) and side.function == 'since']
    if len(sides) != 2 or len(since) != 1:
        raise RewriteError(path, 'since() compares with one value at a time')
    event = _one_name(sides[since[0]], 'since() takes one event name', path)
    other = visit(sides[1 - since[0]])
    elapsed = nodes.binary('sub', nodes.ref('t'), nodes.ref(event + TIME))
    ordered = (elapsed, other) if since[0] == 0 else (other, elapsed)
    happened = nodes.compare(['gt'], [nodes.ref(event + COUNT), nodes.const(0)])
    return nodes.boolean('and', [happened, nodes.compare(comparison.ops, ordered)])


def desugared(node, path):
    """The engine's form of a typed expression (the top of this module): `count` (`count_form`),
    `since` (`since_form`) and `elapsed` (`elapsed_form`) become reads of the names that the structure
    keeps for an event and for a named state. A name that holds `__` and is no value of a firing event
    is an error."""

    def visit(n):
        if isinstance(n, nodes.Ref):
            _reserved(n.name, path)
            return n
        if isinstance(n, nodes.Const):
            return n
        if isinstance(n, nodes.Call):
            if n.function == 'count':
                return count_form(n, path)
            if n.function == 'since':
                raise RewriteError(path, 'since() must be one side of a comparison, e.g. since(e) >= d')
            if n.function == 'elapsed':
                return elapsed_form(n, path)
            return nodes.call(n.function, [visit(arg) for arg in n.args])
        if isinstance(n, nodes.Compare):
            if any(isinstance(side, nodes.Call) and side.function == 'since' for side in n.operands):
                return since_form(n, visit, path)
            return nodes.compare(n.ops, [visit(side) for side in n.operands])
        if isinstance(n, nodes.Unary):
            return nodes.unary(n.op, visit(n.operand))
        if isinstance(n, nodes.Binary):
            return nodes.binary(n.op, visit(n.left), visit(n.right))
        if isinstance(n, nodes.BoolOp):
            return nodes.boolean(n.op, [visit(value) for value in n.values])
        if isinstance(n, nodes.IfElse):
            return nodes.if_else(visit(n.test), visit(n.body), visit(n.orelse))
        # A part outside the language, which the checks of the structure reject: its names are checked.
        for symbol in nodes.names(n):
            _reserved(symbol, path)
        return n

    return visit(node)


# ---- the typing of an expression ------------------------------------------------------------------
#
# `Typing` reads an expression whose names the front end resolved (`semantic.Ref`, ...) and gives its
# typed node with the structure's names, in a context (`Context`); `Reads` collects what it reads of
# other entities. Its `analysis` is the builder, which answers what each name reads.


# The functions of the engine: one list, the typed core's.
FUNCTIONS = nodes.FUNCTIONS


class Firing:
    """The values that one event reads when it fires, or, for its delay, when it triggers (`stage`):
    a draw of a distribution written in the event, and a value of the run's past (`delayed`). Each is a
    placeholder name of the event, which the engine sets before it reads the event's expressions. The
    expressions of an item are typed nodes."""

    def __init__(self, rid):
        self.rid, self.items, self.stage = rid, [], None

    def add(self, typing, name, args, keywords=()):
        """The name of the value that a call `name(args)` of the event reads. `args` are resolved
        nodes, and `keywords` pairs of a name and a resolved node."""
        if name == 'delayed':
            item = self.delayed(typing, args, keywords)
        else:
            item = self.draw(typing, name, args, keywords)
        item['name'] = f'{self.rid}__{item["kind"]}{len(self.items)}'
        item['stage'] = self.stage
        self.items.append(item)
        return nodes.ref(item['name'])

    def delayed(self, typing, args, keywords):
        """`delayed(x, D)`: the value that `x` had the time `D` earlier. The engine reads it from the
        run's own past when the event fires or triggers, and sets it under a name of the event."""
        if len(args) != 2 or keywords:
            typing.fail('delayed(x, D) takes a value and a time: the value D earlier')
        value, delay = (typing.visit(arg) for arg in args)
        return {'kind': 'delayed', 'expr': value, 'delay': delay}

    def draw(self, typing, name, args, keywords):
        """A distribution written in an event, `uniform(a, b)`: a number that the engine draws each
        time the event fires or triggers, and sets under a name of the event. The parameters come by
        position or by name, each once (`DRAWN`)."""
        parameters = DRAWN[name]
        if len(args) > len(parameters):
            typing.fail(f'{name} takes {", ".join(parameters)}')
        given = dict(zip(parameters, args))
        for key, value in keywords:
            if key not in parameters or key in given:
                typing.fail(f'{name} takes {", ".join(parameters)}, each once')
            given[key] = value
        missing = [p for p in parameters if p not in given]
        if missing:
            typing.fail(f'{name} needs {", ".join(missing)}')
        return {'kind': 'draw', 'family': name, 'args': {p: typing.visit(given[p]) for p in parameters}}


class Context:
    """The entity whose expression is read (None: the top level), and whether it is an output's."""

    def __init__(self, entity, outcome=False):
        self.entity, self.outcome = entity, outcome


class Reads:
    """The names that the expressions of one entity (`host`, or None for the main) read. Every name
    is the structure's; a read of another entity's member is one of the entity's links."""

    def __init__(self, analysis, host):
        self.analysis, self.host = analysis, host
        self.reads = set()

    def value(self, symbol):
        if (
            self.host is not None
            and symbol not in self.analysis.parameter_ids
            and split_key(symbol)[0] != self.host
        ):
            self.reads.add(symbol)
        return symbol

    def event(self, event):
        if self.host is not None and self.analysis.event_owner(event) != self.host:
            self.reads.add(event)
        return event


def _text_constant(node):
    return isinstance(node, nodes.Const) and isinstance(node.value, str)


def _is(node, number):
    """Whether a node is the written number `number`."""
    return isinstance(node, nodes.Const) and type(node.value) in (int, float) and node.value == number


class Typing:
    """One expression whose names the front end has read (`resolved`), as a typed node with the
    structure's names, in a context (`reads` collects what it reads of other entities): a bool reads
    as the engine's 0/1 number, a test of a named input as a test of its code, and a formula as its
    expression.

    `visit(node)` reads a resolved node and gives its node. It reads the parts in the order in which
    they are written, so the values that a firing event reads are numbered in that order."""

    def __init__(self, analysis, ctx, reads, path):
        self.analysis, self.ctx, self.reads, self.path = analysis, ctx, reads, path

    def fail(self, message):
        raise AnalysisError(self.path, message)

    def visit(self, node):
        if isinstance(node, resolved.Ref):
            return self.node_of(self.read(node), node.written)
        if isinstance(node, nodes.Const):
            if isinstance(node.value, bool):
                self.fail(f'write {str(node.value).lower()}, not {node.value}: a bool is true or false')
            return nodes.written(node.value)
        if isinstance(node, nodes.Ref):
            return node  # the time, t: the front end reads every other name
        if isinstance(node, nodes.Binary):
            left = self.visit(node.left)
            return nodes.binary(node.op, left, self.visit(node.right))
        if isinstance(node, nodes.Call):
            return self.call(node)
        if isinstance(node, nodes.Compare):
            return self.comparison(node)
        if isinstance(node, nodes.IfElse):
            # `1 if flag else 0` is the engine's 0/1 input itself.
            pid = self.flag(node.test)
            if pid is not None and _is(node.body, 1) and _is(node.orelse, 0):
                return nodes.ref(pid)
            test = self.visit(node.test)
            body = self.visit(node.body)
            return nodes.if_else(test, body, self.visit(node.orelse))
        if isinstance(node, nodes.Unary):
            pid = self.flag(node.operand) if node.op == 'not' else None
            if pid is not None:
                return nodes.compare(['eq'], [nodes.ref(pid), nodes.const(0)])
            return nodes.unary(node.op, self.visit(node.operand))
        if isinstance(node, nodes.BoolOp):
            return nodes.boolean(node.op, [self.visit(value) for value in node.values])
        if isinstance(node, resolved.Word):
            return nodes.const(node.value)
        if isinstance(node, resolved.Problem):
            self.fail(node.message)
        if isinstance(node, resolved.Named):
            # Arguments by name: only a distribution takes them, and `delayed` says what it takes.
            if node.function in DRAWN or node.function == 'delayed':
                return self.fired(node.function, node.args, node.named)
            self.fail('only the listed functions can be called')
        if isinstance(node, nodes.Foreign):
            return self.outside(node.tree)
        # An event, or the terms of a list, where a value is read. The front end gives these only as
        # the argument of the functions that take them.
        self.fail('an event or a list is not a value')

    def outside(self, tree):
        """A part that the language does not have, as the front end's tree of it: a call of something
        that is no name is an error here; of anything else (values in brackets) the parts are typed,
        and the checks of the structure reject it where it stands."""
        if isinstance(tree, ast.Call):
            self.fail('only the listed functions can be called')

        def typed_part(part):
            if isinstance(part, ast.expr):
                return ast.parse(nodes.text(self.visit(resolved.of_tree(part))), mode='eval').body
            return part

        made = type(tree)()
        for name, value in ast.iter_fields(tree):
            found = [typed_part(item) for item in value] if isinstance(value, list) else typed_part(value)
            setattr(made, name, found)
        return nodes.of_tree(ast.fix_missing_locations(made))

    def read(self, node):
        """What a name of a value reads (`Analysis.value`), or None when `node` is not one."""
        if isinstance(node, resolved.Problem):
            self.fail(node.message)
        if isinstance(node, resolved.Ref):
            return self.analysis.value(node.entity, node.member, self.ctx, self.path)
        return None

    def flag(self, node):
        """The engine's 0/1 number of a bool input or a bool state that `node` names, else None."""
        ref = self.read(node)
        if ref is None:
            return None
        if ref[0] == 'parameter' and ref[1] in self.analysis.flags:
            return ref[1]
        if ref[0] == 'quantity' and ref[1] in self.analysis.bool_states:
            return self.reads.value(ref[1])
        return None

    def choice(self, node):
        """(parameter, its named values) of a named input that `node` names, else None."""
        ref = self.read(node)
        if ref is not None and ref[0] == 'parameter' and ref[1] in self.analysis.choices:
            return ref[1], self.analysis.choices[ref[1]]
        return None

    def comparison(self, node):
        # A test of a named input is a test of the code of its value: `self.curve == 'bobb'` reads
        # `curve == 1`. The value is one of its values.
        sides = node.operands
        if len(node.ops) == 1 and node.ops[0] in ('eq', 'ne'):
            for named, other in ((sides[0], sides[1]), (sides[1], sides[0])):
                found = self.choice(named)
                if found and _text_constant(other):
                    pid, values = found
                    if other.value not in values:
                        self.fail(
                            f'{other.value!r} is not a value of the named input {named.written}: {list(values)}'
                        )
                    return nodes.compare(node.ops, [nodes.ref(pid), nodes.const(values.index(other.value))])
        # A test of a named state names one of its values: a misspelt value would make the test
        # always false (or always true with `!=`), and the parts that it guards could never act.
        for op, left, right in zip(node.ops, sides, sides[1:]):
            if op not in ('eq', 'ne'):
                continue
            for state, other in ((left, right), (right, left)):
                if _text_constant(other):
                    values = self.state_values(state)
                    if values is not None and other.value not in values:
                        self.fail(
                            f'{other.value!r} is not a value of the named state {state.written}: {values}'
                        )
        return nodes.compare(node.ops, [self.visit(side) for side in sides])

    def state_values(self, node):
        """The values of the named state that `node` names, or None when it names something else."""
        if isinstance(node, resolved.Problem):
            self.fail(node.message)
        if isinstance(node, resolved.Word) and node.problem is not None:
            self.fail(node.problem)
        if not isinstance(node, resolved.Ref) or node.entity is None:
            return None
        if self.analysis.field_kind.get(f'{node.entity}.{node.member}') != 'mode':
            return None
        return thaw(self.analysis.entity_named[node.entity].value(node.member).type)

    def node_of(self, ref, symbol):
        kind = ref[0]
        if kind == 'number':
            return nodes.written(ref[1])
        if kind == 'parameter' and ref[1] in self.analysis.choices:
            self.fail(f'{symbol} is a named input: read it in a test of one of its values, {symbol} is "a"')
        if kind == 'parameter' and ref[1] in self.analysis.flags:
            # A bool input is the engine's 0/1 input: as a condition it reads `x == 1`.
            return nodes.compare(['eq'], [nodes.ref(ref[1]), nodes.const(1)])
        if kind == 'quantity' and ref[1] in self.analysis.bool_states:
            # So is a bool state: the engine's 0/1 quantity.
            return nodes.compare(['eq'], [nodes.ref(self.reads.value(ref[1])), nodes.const(1)])
        if kind == 'parameter':
            return nodes.ref(ref[1])
        if kind in ('quantity', 'mode', 'computed'):
            return nodes.ref(self.reads.value(ref[1]))
        if kind == 'outcome':
            if not self.ctx.outcome:
                self.fail(f'{symbol} is an output; outputs never feed back into the model')
            return nodes.ref(ref[1])
        if kind == 'inline':
            owner, formula = ref[1], ref[2]
            if (owner, formula.where) in self.analysis.inlining:
                self.fail(f'{symbol} is defined through itself')
            self.analysis.inlining.add((owner, formula.where))
            try:
                typing = Typing(
                    self.analysis, Context(owner, outcome=self.ctx.outcome), self.reads, formula.where
                )
                return typing.visit(formula.node)
            finally:
                self.analysis.inlining.discard((owner, formula.where))
        self.fail(f'{symbol} is not a value')

    def fired(self, name, args, keywords=()):
        """A draw of a distribution, or a value of the run's past, that an event reads as it fires."""
        firing = getattr(self.analysis, 'firing', None)
        if firing is None or firing.stage is None:
            if name == 'delayed':
                self.fail(
                    'delayed() is read by an event, in its lines, chances or delay: not in a condition, a rate, a formula or an output'
                )
            self.fail(
                'a distribution is drawn by a thing, as an input or a let of its own, or by an event, in its '
                'lines, chances or delay: not inside a condition, a rate, a formula or an output'
            )
        return firing.add(self, name, args, keywords)

    def call(self, node):
        name, args = node.function, node.args
        if name in DRAWN or name == 'delayed':
            return self.fired(name, args)
        if name == 'count' and args and isinstance(args[0], resolved.Terms):
            return self.reduction(node, name)
        if name in ('since', 'count'):
            found = self.argument(node, resolved.EventRef)
            if found is None:
                self.fail(f'{name}() takes one event')
            event = self.analysis.event_name(found.kind, found.key, found.ending)
            return nodes.call(name, [nodes.ref(self.reads.event(event))])
        if name == 'elapsed':
            # Any named state: the entity's own, a linked entity's or the main's. Its entry time is
            # a read of the state.
            ref = self.read(args[0]) if len(args) == 1 else None
            if ref is None or ref[0] != 'mode':
                self.fail('elapsed() measures a named state: elapsed(state)')
            return nodes.call(name, [nodes.ref(self.reads.value(ref[1]))])
        if name in ('sum', 'any', 'all'):
            return self.reduction(node, name)
        if name in ('min', 'max') and any(isinstance(arg, resolved.Terms) for arg in args):
            members = []
            for arg in args:
                members += (
                    [self.member(ref) for ref in arg.refs]
                    if isinstance(arg, resolved.Terms)
                    else [self.visit(arg)]
                )
            if not members:
                self.fail(f'{name}() of a list with no members has no value')
            return nodes.call(name, members)
        if name not in FUNCTIONS:
            self.fail(f'unknown function {name}')
        return nodes.call(name, [self.visit(arg) for arg in args])

    def reduction(self, node, name):
        """`sum`, `count`, `any` or `all` of a value of each member of a list."""
        terms = self.argument(node, resolved.Terms)
        if terms is None:
            self.fail(f'{name}() takes one value of a list link or of a set of copies: {name}(list.value)')
        members = [self.member(ref) for ref in terms.refs]
        if self.analysis.listed and members:
            # The form of the hybrid core: one node for the list, whatever the number of its members.
            if name == 'count':
                members = [nodes.if_else(item, nodes.const(1), nodes.const(0)) for item in members]
            return nodes.call('sum' if name == 'count' else name, members)
        if name in ('any', 'all'):
            if not members:
                return nodes.const(name == 'all')  # no member: none holds, and all do
            if len(members) == 1:
                return members[0]
            return nodes.boolean('or' if name == 'any' else 'and', members)
        if name == 'count':
            # The members where a yes/no holds: 1 for each.
            members = [nodes.if_else(item, nodes.const(1), nodes.const(0)) for item in members]
        if not members:
            return nodes.const(0)  # a list with no members adds to nothing
        total = members[0]
        for term in members[1:]:
            total = nodes.binary('add', total, term)
        return total

    def member(self, ref):
        """The value that one member of a list gives to a reduction over it."""
        return self.node_of(self.analysis.value_of(ref.entity, ref.member, self.ctx, self.path), ref.written)

    def argument(self, call, kind):
        """The resolved argument of `since()`, `count()` or `sum()`, or None when the call is not
        written as one; an argument that does not resolve fails."""
        args = call.args
        if len(args) == 1 and isinstance(args[0], resolved.Problem):
            self.fail(args[0].message)
        return args[0] if len(args) == 1 and isinstance(args[0], kind) else None
