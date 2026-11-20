"""The value of an expression: the function of one node, and the programs of the engine.

Both are Python code that this module writes from the nodes of `expr`, with one meaning.

- A part that gives a value is checked when it is computed: a number must be finite and real. A
  comparison and an `and` / `or` give a yes/no, which is not checked.
- A choice computes only the branch that its test takes, and `and` / `or` stop at the term that
  decides. A name with no value fails when the code reaches it, and not before.
- `+x` is `x`. A call with a wrong number of arguments, and a part that is outside the language, fail
  when the code reaches them.

`function(node)` is the code of one node: it reads each name from an environment. `program` is the code
of many expressions in turn. It can know some values before it runs: a part that reads only known
values is computed once, when the program is made, by the same operations and the same checks, and its
value is written into the code. A part whose computation fails stays code, so it fails only when a run
reaches it.

What this module does with each operation is in `TABLE`, from the name of the operation to its
handler. `ops.handlers` checks the table when the module is read: an operation of the language with no
handler here is an error at import, and not a wrong value in a run.
"""

from __future__ import annotations

import ast
import math
import operator
from collections import OrderedDict
from threading import RLock

from . import expr, ops
from .errors import ExpressionError

# The value of code that a program computes when it runs.
UNKNOWN = object()
# The number of nodes whose functions `function` keeps.
LIMIT = 65536
_FUNCTIONS = OrderedDict()
_LOCK = RLock()


def _finite(result):
    if isinstance(result, complex) or (
        isinstance(result, (float, int)) and not isinstance(result, bool) and not math.isfinite(result)
    ):
        raise ExpressionError('Expression produced a nonfinite or non-real value')
    return result


def _missing(name):
    raise ExpressionError(f'Missing value for {name!r}')


def _raise(message):
    raise ExpressionError(message)


def _power(left, right):
    if abs(right) > 1024:
        raise ExpressionError('Exponent exceeds supported magnitude 1024')
    return float(left) ** right


def _clip(value, low, high):
    if low > high:
        raise ExpressionError('clip lower bound exceeds upper bound')
    return min(max(value, low), high)


def _within(value, low, high):
    """`value in [low, high]`, the closed interval; a reversed one is an error (`ops.REVERSED`)."""
    if low > high:
        raise ExpressionError(f'{ops.REVERSED}: [{low!r}, {high!r}]')
    return low <= value <= high


def _sum(values):
    """The members of a list added from the left in their order: the value of `a + b + c`, bit for
    bit. Each sum of two passes the check that the sum of two values passes."""
    total = values[0]
    for value in values[1:]:
        total = total + value
        if not passes(total):
            _finite(total)
    return total


# The names that the written code reads.
RUNTIME = {
    '_finite': _finite,
    '_missing': _missing,
    '_raise': _raise,
    '_power': _power,
    '_clip': _clip,
    '_within': _within,
    '_sum': _sum,
    'min': min,
    'max': max,
    'abs': abs,
    'exp': math.exp,
    'expm1': math.expm1,
    'ln': math.log,
    'log1p': math.log1p,
    'sqrt': math.sqrt,
    'erf': math.erf,
    '_float': float,
    '_int': int,
    '_bool': bool,
    '_str': str,
    'bool': bool,
    '__builtins__': {},
}


def passes(value):
    """Whether a value passes the check that the code gives every value, and a literal writes it with
    its exact type and value: a finite float, an int, a bool or a text."""
    kind = value.__class__
    if kind is float:
        return value - value == 0
    return kind is int or kind is bool or kind is str


def _known(compute, *values):
    """The value of `compute(*values)` when it passes the check, else UNKNOWN: a computation that
    fails stays code, so it fails when the program reaches it."""
    try:
        value = compute(*values)
    except Exception:  # the program raises the same failure when it runs this code
        return UNKNOWN
    return value if passes(value) else UNKNOWN


def from_environment(name):
    """The code that reads a name from the environment `E`; its value is not checked yet."""
    return f'(E[{name!r}] if {name!r} in E else _missing({name!r}))', False


class _Writer:
    """The code of nodes, for one function or one program.

    `code(node)` gives (the code, the value): the value when every name that the node reads is known,
    else UNKNOWN. A known value is written as its literal. `read(name)` gives the code that reads a
    name that is not known, and whether its value is checked already. With `fold` off nothing is
    known: a constant is code too, as in the function of one node.

    With `lean`, the code checks a value only where a value that is not finite could be hidden. The
    values of the program are the same, and a program that fails with every check fails with these
    (it can fail at a later part, with another failure of the arithmetic). The argument:

    - A value that the code reads (a name, a constant) is checked when it is read, so only an
      operation can make a value that is not finite or of a wrong type.
    - A sum, a difference, a product, a negation, a quotient by a finite divisor, `abs`, `sqrt`, `ln`
      and `log1p` of a value that is not finite are not finite, or they raise. So the result of such
      an operation is not checked where it is made (`result`): the code that reads it checks it, or
      it goes on to the next such operation.
    - Each other reader of a value could hide it (a comparison, a membership, a test, `not`, `and`,
      `or`, `min`, `max`, `clip`, a divisor, a power, `exp`, `expm1`, `erf`, a quantity): it reads the
      value checked (`sure`). So do an assignment and an output of a program.
    - `min`, `max` and `clip` give one of their checked values; `exp`, `expm1` and `erf` of a finite
      value are finite or raise; a comparison, a membership, `not`, `and` and `or` give a yes/no.
      Their results need no check.
    """

    def __init__(self, read, constants, units, fold, lean=False):
        self.read, self.constants, self.units, self.fold, self.lean = read, constants, units, fold, lean
        self.count = 0
        self.loose = set()  # with `lean`: the code whose value is not checked yet
        # The parts of a deep node that have code of their own (`split`): node -> (the code that
        # gives the value of the part, its value when it is known), and the number of such parts.
        self.parts, self.named = {}, 0

    def split(self, node):
        """The lines that come before the code of a node, for a node that is deeper than `SPLIT`.

        Python reads no code with more than 200 brackets one inside the other, and the code of one
        checked operation has some of them: the code of a chain of many operations (a sum that a
        flat structure writes member by member) is deeper than that. So each of `_parts(node)` gets
        a line of its own, `_pN = lambda: <its code>`, and `code` then writes the call `_pN()` where
        it would write the code of the part. The part is computed where it was, when it was, and
        only when the code reaches it (a choice, `and` and `or` leave out what they do not need):
        the values, their order and each failure are those of the code in one piece.

        The lines are for one node: a later node can read other values under the same names (an
        assignment of a program), so its parts are written again."""
        self.parts = {}
        lines = []
        if expr.height(node) <= SPLIT:
            return lines
        for part in _parts(node):
            code, known = self.code(part)
            if known is UNKNOWN:
                self.named += 1
                call = f'_p{self.named}()'
                lines.append(f'_p{self.named} = lambda: {code}')
                if code in self.loose:
                    self.loose.add(call)  # the reader of the part checks its value, as it would
                code = call
            self.parts[part] = (code, known)
        return lines

    def checked(self, code):
        self.count += 1
        v, c = f'_v{self.count}', f'_c{self.count}'
        return (
            f'({v} if (({c} := ({v} := {code}).__class__) is _float and {v} - {v} == 0)'
            f' or {c} is _int or {c} is _bool or {c} is _str else _finite({v}))'
        )

    def result(self, code):
        """The code of the result of an operation that hides no value that is not finite: checked
        here, or, with `lean`, where it is read."""
        if not self.lean:
            return self.checked(code)
        self.loose.add(code)
        return code

    def sure(self, code):
        """The code of a value for a reader that could hide a value that is not finite."""
        return self.checked(code) if code in self.loose else code

    def given(self, code):
        """The code of a result that is finite when the values that it reads are checked: a check
        that `lean` leaves out."""
        return code if self.lean else self.checked(code)

    def code(self, node):
        if self.parts:
            found = self.parts.get(node)
            if found is not None:
                return found
        if isinstance(node, expr.Ref):
            name = node.name
            if name in self.constants and passes(self.constants[name]):
                return _literal(self.constants[name])
            source, ready = self.read(name)
            return (source if ready else self.checked(source)), UNKNOWN
        if isinstance(node, expr.Const):
            if self.fold and passes(node.value):
                return _literal(node.value)
            return self.checked(repr(node.value)), UNKNOWN
        if isinstance(node, expr.Foreign):
            return _foreign(self, node)
        if isinstance(node, expr.Call):
            handler = TABLE.get(node.function)
            if handler is None:
                return "_raise('Unsupported function or keyword arguments')", UNKNOWN
            if not ops.arity_holds(ops.OPERATIONS[node.function], len(node.args)):
                return f'_raise({f"Invalid argument count for {node.function}"!r})', UNKNOWN
            return handler(self, node)
        return TABLE[ops.operation_of(node)](self, node)


def _literal(value):
    return repr(value), value


# ---- the handlers: the code and the known value of each operation ---------------------------------------


# How an operation treats a value that is not finite (`_Writer`, `lean`). CARRIES: its result is then
# not finite, or it raises. HIDES: it can give a finite result, and its own result needs the check.
# HIDES_ONE: as HIDES, and its result is finite, or one of its values, when its values are checked.
CARRIES, HIDES, HIDES_ONE = 'carries', 'hides', 'hides, and its result is checked by its values'


def _on_one(template, compute, kind=CARRIES):
    """The handler of an operation on one value. The code is `template` with the code of the operand."""

    def handler(writer, node):
        operand, value = writer.code(node.operand)
        if value is not UNKNOWN:
            found = _known(compute, value)
            if found is not UNKNOWN:
                return _literal(found)
        if kind is CARRIES:
            return writer.result(template.format(operand)), UNKNOWN
        return writer.given(template.format(writer.sure(operand))), UNKNOWN

    return handler


def _on_two(template, compute, kind=CARRIES):
    """The handler of an operation on two values. `kind`: CARRIES, HIDES, or 'divides' for a quotient,
    which carries its first value and can hide its second."""

    def handler(writer, node):
        (left, known_left), (right, known_right) = writer.code(node.left), writer.code(node.right)
        if known_left is not UNKNOWN and known_right is not UNKNOWN:
            found = _known(compute, known_left, known_right)
            if found is not UNKNOWN:
                return _literal(found)
        if kind is CARRIES:
            return writer.result(template.format(left, right)), UNKNOWN
        if kind == 'divides':
            return writer.result(template.format(left, writer.sure(right))), UNKNOWN
        return writer.checked(template.format(writer.sure(left), writer.sure(right))), UNKNOWN

    return handler


# How each comparison is written, and its value.
COMPARISONS = {
    'eq': ('==', operator.eq),
    'ne': ('!=', operator.ne),
    'lt': ('<', operator.lt),
    'le': ('<=', operator.le),
    'gt': ('>', operator.gt),
    'ge': ('>=', operator.ge),
}


def _chain(writer, node):
    """A chain of comparisons. Its code is not checked: it gives a yes/no."""
    written = [(writer.sure(source), value) for source, value in map(writer.code, node.operands)]
    values = [value for _, value in written]
    if all(value is not UNKNOWN for value in values):

        def chain(*operands):
            for op, left, right in zip(node.ops, operands, operands[1:]):
                result = COMPARISONS[op][1](left, right)
                if not result:
                    return result
            return result

        result = _known(chain, *values)
        if result is not UNKNOWN and result.__class__ is bool:
            return _literal(result)
    parts = [written[0][0]]
    for op, (source, _) in zip(node.ops, written[1:]):
        parts += [COMPARISONS[op][0], source]
    return '(' + ' '.join(parts) + ')', UNKNOWN


def _lazy(conjunction):
    """The handler of `and` (`conjunction`) or of `or`. A known term decides the value only when no
    term that runs comes before it, because a term that runs can fail."""

    def handler(writer, node):
        terms = []
        for item in node.values:
            source, value = writer.code(item)
            if value is not UNKNOWN and not terms:
                if bool(value) != conjunction:
                    return _literal(bool(value))  # a false `and` term, or a true `or` term, decides
                continue  # a true `and` term, or a false `or` term, decides nothing
            terms.append(f'bool({writer.sure(source)})')
        if not terms:
            return _literal(conjunction)
        return '(' + (' and ' if conjunction else ' or ').join(terms) + ')', UNKNOWN

    return handler


def _choice(writer, node):
    if not writer.fold:
        # The function of one node numbers the checks of the body before those of the test.
        body, test, orelse = (writer.code(part)[0] for part in (node.body, node.test, node.orelse))
        return writer.checked(f'({body} if {test} else {orelse})'), UNKNOWN
    test, decided = writer.code(node.test)
    if decided is not UNKNOWN:
        # The branch that the test takes, checked as it is: its code checks its value.
        return writer.code(node.body if decided else node.orelse)
    body, orelse = writer.code(node.body)[0], writer.code(node.orelse)[0]
    if writer.lean:
        # The value of the branch that the test takes, as it is: checked when both branches are.
        chosen = f'({body} if {writer.sure(test)} else {orelse})'
        if body in writer.loose or orelse in writer.loose:
            writer.loose.add(chosen)
        return chosen, UNKNOWN
    return writer.checked(f'({body} if {test} else {orelse})'), UNKNOWN


def _call(code, compute, kind=HIDES):
    """The handler of a function. `code(args)` is the code of the call from the code of its arguments,
    and `compute(writer, values)` its value from known arguments (UNKNOWN when it cannot be known).
    `kind` says how the function treats a value that is not finite (CARRIES, HIDES, HIDES_ONE)."""

    def handler(writer, node):
        written = [writer.code(arg) for arg in node.args]
        values = [value for _, value in written]
        if all(value is not UNKNOWN for value in values):
            found = compute(writer, values)
            if found is not UNKNOWN:
                return _literal(found)
        sources = [source for source, _ in written]
        if kind is CARRIES:
            return writer.result(code(sources)), UNKNOWN
        sources = [writer.sure(source) for source in sources]
        if kind is HIDES_ONE:
            return writer.given(code(sources)), UNKNOWN
        return writer.checked(code(sources)), UNKNOWN

    return handler


# `abs`, `sqrt`, `ln` and `log1p` of a value that is not finite are not finite, or they raise. `exp`
# and `expm1` of minus infinity and `erf` of an infinity are finite; of a finite value they are finite
# or they raise (`math.exp` and `math.expm1` raise where they leave the floating-point range).
OF_ONE = {
    'abs': CARRIES,
    'sqrt': CARRIES,
    'ln': CARRIES,
    'log1p': CARRIES,
    'exp': HIDES_ONE,
    'expm1': HIDES_ONE,
    'erf': HIDES_ONE,
}


def _of_one(name):
    return _call(
        lambda args: f'{name}({args[0]})',
        lambda writer, values: _known(RUNTIME[name], values[0]),
        OF_ONE[name],
    )


def _extreme(name):
    # The least or the greatest of checked values is one of them.
    return _call(
        lambda args: f'{name}(({", ".join(args)},))',
        lambda writer, values: _known(RUNTIME[name], tuple(values)),
        HIDES_ONE,
    )


def _listed(many):
    """The handler of a function over the members of a list: one member is that member, as the
    lowering writes a list of one; more go to `many`."""

    def handler(writer, node):
        if len(node.args) == 1:
            return writer.code(node.args[0])
        return many(writer, node)

    return handler


def _terms(op):
    """`any` or `all` of two members or more: the `or` or the `and` of them."""
    return lambda writer, node: TABLE[op](writer, expr.boolean(op, node.args))


def _converted(writer, values):
    # A quantity is converted when the program is made only if the program has the registry.
    return UNKNOWN if writer.units is None else _known(writer.units.normalize, *values)


def _foreign(writer, node):
    """A part that is outside the language. It fails when the code reaches it; the parts inside it that
    come first are computed first, so a failure of theirs comes first."""
    tree = node.tree
    if isinstance(tree, ast.UnaryOp):  # an operator on one value that the language does not have reads as `+`
        return TABLE['pos'](writer, expr.unary('pos', expr.of_tree(tree.operand)))
    if isinstance(tree, ast.Compare):
        # A comparison that the language does not have is an error when the code is written.
        operands = [expr.of_tree(item) for item in (tree.left, *tree.comparators)]
        unsupported = [type(op) for op in tree.ops if type(op) not in expr.COMPARE]
        if writer.fold:
            for operand in operands:
                writer.code(operand)
            raise KeyError(unsupported[0])
        writer.code(operands[0])
        for op, operand in zip(tree.ops, operands[1:]):
            if type(op) not in expr.COMPARE:
                raise KeyError(type(op))
            writer.code(operand)
    if isinstance(tree, ast.BinOp):
        left, right = writer.code(expr.of_tree(tree.left))[0], writer.code(expr.of_tree(tree.right))[0]
        return f"({left}, {right}, _raise('Unsupported operator'))[2]", UNKNOWN
    if isinstance(tree, ast.Call):
        return "_raise('Unsupported function or keyword arguments')", UNKNOWN
    return "_raise('Unsupported expression')", UNKNOWN


TABLE = ops.handlers(
    'the value of an expression',
    {
        'neg': _on_one('(-{})', operator.neg),
        'pos': _on_one('{}', lambda value: value),
        'not': _on_one('(not {})', operator.not_, HIDES_ONE),
        'and': _lazy(True),
        'or': _lazy(False),
        **dict.fromkeys(COMPARISONS, _chain),
        'if': _choice,
        'add': _on_two('({} + {})', operator.add),
        'sub': _on_two('({} - {})', operator.sub),
        'mul': _on_two('({} * {})', operator.mul),
        'div': _on_two('({} / {})', operator.truediv, 'divides'),
        'pow': _on_two('_power({}, {})', _power, HIDES),
        'min': _extreme('min'),
        'max': _extreme('max'),
        # `_sum` checks each sum of two itself, so no value of it is hidden and its result is checked.
        'sum': _listed(
            _call(
                lambda args: f'_sum(({", ".join(args)},))',
                lambda writer, values: _known(_sum, tuple(values)),
                HIDES_ONE,
            )
        ),
        'any': _listed(_terms('or')),
        'all': _listed(_terms('and')),
        # `_clip` gives one of its three checked values.
        'clip': _call(
            lambda args: f'_clip({args[0]}, {args[1]}, {args[2]})',
            lambda writer, values: _known(_clip, *values),
            HIDES_ONE,
        ),
        # `_within` reads its three checked values once each and gives a yes/no; a reversed interval
        # that the program knows when it is made stays code, so it fails where a run reaches it.
        'within': _call(
            lambda args: f'_within({args[0]}, {args[1]}, {args[2]})',
            lambda writer, values: _known(_within, *values),
            HIDES_ONE,
        ),
        **{name: _of_one(name) for name in OF_ONE},
        'q': _call(lambda args: f'R.normalize({args[0]}, {args[1]})', _converted),
    },
)


# ---- the function of one node, and a program ------------------------------------------------------------


# The number of operations, one inside the other, in the code of one part (`_Writer.split`). The
# code of one operation has at most 6 brackets of its own (a checked `min`), and Python reads 200.
SPLIT = 24


def _parts(node):
    """The parts of a deep node that get code of their own, each after the parts under it. A part
    is cut where the code under it, down to the cuts below, has `SPLIT` operations one inside the
    other: so the code of each part, and that of the node, has no more than `SPLIT`, whatever the
    form of the tree. The node can be the last of them. It goes down with a list and not with
    calls."""
    levels, cut, pending = {}, [], [node]
    while pending:
        part = pending[-1]
        if part in levels:
            pending.pop()
            continue
        if expr.height(part) < SPLIT:
            levels[part] = expr.height(part)  # nothing is cut under it
            continue
        waiting = [child for child in part.children if child not in levels]
        if waiting:
            pending += waiting
            continue
        pending.pop()
        level = 1 + max((levels[child] for child in part.children), default=0)
        if level >= SPLIT:
            cut.append(part)
            level = 0
        levels[part] = level
    return cut


def function_text(node):
    """The Python text of `function(node)`: an expression, or, for a node that is deeper than
    `SPLIT`, the definition of the function `_function` (`_Writer.split`)."""
    writer = _Writer(from_environment, {}, None, fold=False)
    lines = writer.split(node)
    code = writer.code(node)[0]
    if not lines:
        return f'lambda E, R: {code}'
    return '\n'.join(['def _function(E, R):', *(f'    {line}' for line in lines), f'    return {code}'])


def function(node):
    """`f(E, R)`: the value of a node in the environment `E` (name → value), with the registry of units
    `R` for its quantities. The functions of the last `LIMIT` nodes are kept."""
    with _LOCK:
        found = _FUNCTIONS.get(node)
        if found is not None:
            _FUNCTIONS.move_to_end(node)
            return found
        text = function_text(node)
        if text.startswith('lambda'):
            found = eval(compile(text, '<expression>', 'eval'), dict(RUNTIME))
        else:
            scope = dict(RUNTIME)
            exec(compile(text, '<expression>', 'exec'), scope)
            found = scope['_function']
        _FUNCTIONS[node] = found
        while len(_FUNCTIONS) > LIMIT:
            _FUNCTIONS.popitem(last=False)
        return found


def value(node, environment, registry):
    """The value of a node in an environment."""
    return function(node)(environment, registry)


# The failures of Python's arithmetic that the value of an expression can meet.
ARITHMETIC = (ValueError, OverflowError, ZeroDivisionError, TypeError, KeyError)


def failure(exc):
    """A failure of Python's arithmetic in the language's words (spec: "Execution errors fail the run
    with the expression"): a division by zero, a number outside the domain of its function (`ln` of
    zero, `sqrt` of a negative number), a number too large to hold, values of kinds that an
    operation does not take, a name with no value."""
    if isinstance(exc, ZeroDivisionError):
        return 'a division by zero'
    if isinstance(exc, OverflowError):
        return 'a number too large to hold'
    if isinstance(exc, KeyError):
        return f'{exc.args[0] if exc.args else "a name"} has no value'
    if isinstance(exc, TypeError):
        return 'values of kinds that its operation does not take'
    if isinstance(exc, ValueError) and 'math domain' in str(exc):
        return 'a number outside the domain of its function'
    return str(exc)


def checked_value(node, environment, registry):
    """The value of a node in an environment; each failure is an ExpressionError that names the
    expression as the model writes it (`expr.notation`) and the failure in the language's words
    (`failure`)."""
    try:
        return function(node)(environment, registry)
    except ExpressionError:
        raise
    except ARITHMETIC as exc:
        raise ExpressionError(f'`{expr.notation(node)}`: {failure(exc)}') from exc


def program_text(
    assignments,
    outputs,
    *,
    constants=None,
    units=None,
    read=None,
    arguments=('E', 'R'),
    write=True,
    lean=False,
):
    """The Python text of `program(...)`, which defines the function `program`."""
    constants = dict(constants or {})
    read = read or from_environment
    assigned, made = {}, 0

    def reads(name):
        if name in assigned:
            return assigned[name], True  # an assigned value was checked when it was assigned
        return read(name)

    writer = _Writer(reads, constants, units, fold=True, lean=lean)
    lines = [f'def program({", ".join(arguments)}):']
    for name, node in assignments:
        lines += [f'    {line}' for line in writer.split(node)]
        code, known = writer.code(node)
        code = writer.sure(code)  # an assigned value is checked when it is assigned
        if known is not UNKNOWN:
            constants[name] = known
            if write:
                lines.append(f'    E[{name!r}] = {code}')
            continue
        constants.pop(name, None)  # the assignment hides a constant of the same name, as it does in E
        made += 1  # a name of its own for each assignment: a name can be assigned again
        local = assigned[name] = f'_a{made - 1}'
        lines.append(f'    {local} = E[{name!r}] = {code}' if write else f'    {local} = {code}')
    values = []
    for node in outputs:
        lines += [f'    {line}' for line in writer.split(node)]
        values.append(writer.sure(writer.code(node)[0]))
    lines.append(f'    return ({"".join(v + ", " for v in values)})')
    return '\n'.join(lines)


# The code of the last programs, by their text: a run makes the program of a structure again for each
# of its segments, and each sample of a study makes those of its run.
PROGRAMS = 256
_CODE = OrderedDict()


def _compiled(text):
    with _LOCK:
        found = _CODE.get(text)
        if found is not None:
            _CODE.move_to_end(text)
            return found
    found = compile(text, '<model>', 'exec')
    with _LOCK:
        _CODE[text] = found
        while len(_CODE) > PROGRAMS:
            _CODE.popitem(last=False)
    return found


def program(
    assignments,
    outputs,
    *,
    constants=None,
    units=None,
    read=None,
    arguments=('E', 'R'),
    write=True,
    lean=False,
):
    """A straight-line program `program(*arguments)`: assign each named node of `assignments`
    (pairs of a name and a node) in order, then return the tuple of the values of `outputs` (nodes),
    with the meaning of the value of each node in turn. A caller computes the values one by one again
    to report a failure.

    - `constants` {name: value}: the names whose values are known before the program runs. A part of
      an expression that reads only constants and literals is computed once, when the program is
      made, and so is an assignment that reads only constants: it is a constant too.
    - `units`: the registry that `q(number, unit)` converts known numbers with.
    - `read(name)`: the code that reads a name that is not a constant or an assignment, and whether
      its value is checked already. By default the program reads E.
    - `write`: each assignment also goes into E.
    - `lean`: the program checks a value only where a value that is not finite could be hidden
      (`_Writer`). It gives the same values. Where the program with every check fails, it fails too,
      but it can fail at a later part and with another failure of the arithmetic: it is for a caller
      that computes the values one by one again to report a failure.
    """
    text = program_text(
        assignments,
        outputs,
        constants=constants,
        units=units,
        read=read,
        arguments=arguments,
        write=write,
        lean=lean,
    )
    namespace = dict(RUNTIME)
    exec(_compiled(text), namespace)
    return namespace['program']
