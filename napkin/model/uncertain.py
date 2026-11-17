"""A distribution as a file or an edit writes it, read with its units (docs/language.md, §2.3).

A distribution is one call of a family: `pert(24 h, 72 h, 336 h)`. Its arguments are positional, in
the order of the family's parameters, or keywords: `normal(mean=10 h, sd=2 h, min=4 h, max=16 h)`.
A categorical gives each named value its probability: `categorical(low=0.7, high=0.3)`. A number
argument has its unit, a unit of the dimension of the value, and the reader converts it to the unit
of the value; `gsd`, the shapes `a` and `b` of a beta and the probabilities are plain numbers. An
argument can also read inputs and fixed values, `median=1.5 * self.detection_time`: the reader keeps
its source, and the analysis reads it in the entity of the value.

A read distribution is a record, `{'family', 'args', 'text'}`: each argument is a number in the unit
of its parameter, or `{'reads': source}`; `text` is the distribution as it was written. The source
of an argument that reads other values is the argument as the author wrote it: the resolver reads
it as it reads an expression of the file.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping

from ..core import expr as nodes
from ..core.evaluation import checked_value
from ..core.units import same, unit_of
from ..distributions import FAMILIES, central, problems, support
from ..expressions import NUMBER, ExpressionError, evaluate, names_in
from .types import UnitProblem, family_of, family_type, literal_quantities, number_in

# What the values of each kind of type are, for the messages.
KINDS = {'unit': 'numbers', 'bool': 'true or false', 'names': 'named values'}


class DistributionProblem(ValueError):
    """A distribution that its field cannot take, with the reason, and the name of the value when it
    is known."""

    def __init__(self, message, name=None):
        super().__init__(message)
        self.name = name


def is_distribution(value):
    """A read distribution (a record), not a point value."""
    return isinstance(value, Mapping) and 'family' in value


def reads(record):
    """{parameter: source} of the arguments of a distribution that read other values."""
    return {name: arg['reads'] for name, arg in record['args'].items() if isinstance(arg, Mapping)}


def plain(parameter, family):
    """A parameter that is a plain number, not in the unit of the value."""
    return family in ('categorical', 'bernoulli', 'beta') or parameter in FAMILIES[family].dimensionless


def _reads_a_name(node):
    return bool(nodes.names(node))


def _signed(node):
    """(the sign, the node that it stands before) of a node with one sign, or (1, the node)."""
    if isinstance(node, nodes.Unary) and node.op in ('neg', 'pos'):
        return (-1 if node.op == 'neg' else 1), node.operand
    return 1, node


def _literal(node):
    """The number of a bare literal (`3`, `-0.5`), or None."""
    sign, node = _signed(node)
    if isinstance(node, nodes.Const) and type(node.value) in (int, float):
        return sign * node.value
    return None


def _quantity(node):
    """(number, unit) of a written quantity, `24 h` (read as `q(24, 'h')`) or `-24 h`, or None."""
    sign, node = _signed(node)
    if (
        isinstance(node, nodes.Call)
        and node.function == 'q'
        and len(node.args) == 2
        and _literal(node.args[0]) is not None
        and isinstance(node.args[1], nodes.Const)
        and isinstance(node.args[1].value, str)
    ):
        return sign * _literal(node.args[0]), node.args[1].value
    return None


def _number(node, parameter, family, unit, units):
    """The number of one argument that reads no name, in the unit of its parameter."""
    found = _quantity(node)
    if found is not None and not plain(parameter, family):
        number, given = found
        try:
            # A number in the unit of the value keeps its value bit for bit.
            return number_in(f'{number!r} {given}', unit, units)
        except UnitProblem as exc:
            raise DistributionProblem(f'{parameter}: {exc}') from None
    literal = _literal(node)
    if literal is not None:
        # A bare number is 0, a plain number, or a number of a dimensionless unit, as elsewhere.
        if plain(parameter, family) or literal == 0 or not units.parse_unit(unit).dimensions:
            return literal
        raise DistributionProblem(f'{parameter}: write the unit of the number: {literal!r} {unit}')
    expected = NUMBER if plain(parameter, family) else units.parse_unit(unit).canonical()
    if any(isinstance(part, nodes.Call) and part.function in nodes.LISTED for part in nodes.walk(node)):
        # A function over the members of a list is the lowering's, for a list of the model: an author
        # does not call it with values, here as in a formula.
        raise DistributionProblem(f'{parameter}: Unsupported function or keyword arguments')
    try:
        value = _constant(node, units, expected)
    except ExpressionError as exc:
        raise DistributionProblem(f'{parameter}: {exc}') from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DistributionProblem(f'{parameter} is a number')
    return value if plain(parameter, family) else value / units.parse_unit(unit).scale


def _constant(node, units, expected):
    """The value of an expression that reads no name, in execution units. The checks are those of an
    expression of a formula, made on the node: the limits of its size (`expr.limited`), its unit,
    which is `expected`, and its value. Raises ExpressionError."""
    nodes.limited(node)
    found, _ = unit_of(node, {}, units)
    same(found, expected.canonical())
    return checked_value(node, {}, units)


# The name of an argument that is given by name: `median=`, and not the `==` of another language.
_NAMED = re.compile(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)')


def written_arguments(written):
    """The arguments of a written call, each as the author wrote it: [(the name of an argument that
    is given by name, or None; its text)], in their order. An argument ends at a comma that is
    outside brackets and outside a text."""
    start, end = written.index('('), written.rindex(')')
    parts, depth, quoted, begin = [], 0, False, start + 1
    for at in range(start + 1, end):
        char = written[at]
        if char == '"':
            quoted = not quoted
        elif quoted:
            continue
        elif char in '([':
            depth += 1
        elif char in ')]':
            depth -= 1
        elif char == ',' and depth == 0:
            parts.append(written[begin:at])
            begin = at + 1
    if parts or written[begin:end].strip():
        parts.append(written[begin:end])
    found = []
    for part in parts:
        named = _NAMED.match(part)
        found.append((named.group(1), part[named.end() :].strip()) if named else (None, part.strip()))
    return found


def read_distribution(written, kind, unit, units, names=None, filled=None):
    """The record of a written distribution of a value of `kind` (`unit`, `bool` or `names`): in
    `unit`, a library unit, or with the named values `names`. `filled` is the text with the braces of
    its units filled (`{item}/h`), when they differ. Raises DistributionProblem."""
    family = family_of(written)
    if family is None:
        raise DistributionProblem(f'a distribution is a call of one family: {", ".join(FAMILIES)}')
    if family_type(family) != kind:
        raise DistributionProblem(
            f'{family} gives {KINDS[family_type(family)]}, and this field takes {KINDS[kind]}'
        )
    if family == 'beta' and units.parse_unit(unit).dimensions:
        raise DistributionProblem(
            f'beta gives values from 0 to 1, for a dimensionless value, not one in {unit}'
        )
    source = (filled or written).strip()
    try:
        call = ast.parse(literal_quantities(source, units), mode='eval').body
    except SyntaxError:
        raise DistributionProblem(
            f'{written!r} is not one call of {family} with numbers and the units of the library'
        ) from None
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != family:
        raise DistributionProblem(f'a distribution is one call of {family}')
    if family == 'categorical':
        parameters = list(names or ())
        if call.args:
            raise DistributionProblem(
                'a categorical names each value with its probability: categorical(a=0.7, b=0.3)'
            )
    else:
        parameters = list(FAMILIES[family].parameters)
        if len(call.args) > len(parameters):
            raise DistributionProblem(f'{family} takes {", ".join(parameters)}')
    given = dict(zip(parameters, call.args))
    # Each argument as the author wrote it, by its parameter: Python has the arguments with no name
    # first, in their order, and so has the text.
    texts = written_arguments(source)
    by_name = {name: text for name, text in texts if name is not None}
    text_of = dict(zip(parameters, (text for name, text in texts if name is None)))
    for keyword in call.keywords:
        if keyword.arg not in parameters:
            what = 'value' if family == 'categorical' else 'parameter'
            raise DistributionProblem(
                f'{family} has no {what} {keyword.arg!r}: it takes {", ".join(parameters)}'
            )
        if keyword.arg in given:
            raise DistributionProblem(f'{keyword.arg} is given twice')
        given[keyword.arg] = keyword.value
        text_of[keyword.arg] = by_name.get(keyword.arg)
    if family == 'categorical' and not given:
        raise DistributionProblem('a categorical names one or more values with their probabilities')
    missing = [p for p in parameters if p not in given and family != 'categorical']
    if missing:
        raise DistributionProblem(f'{family} needs {", ".join(missing)}')
    args = {}
    for parameter in parameters:
        tree = given.get(parameter)
        # The call is read as Python reads it, because it names its arguments; each argument is an
        # expression of the language, read as typed nodes.
        node = None if tree is None else nodes.of_tree(tree)
        if node is None:
            args[parameter] = 0.0  # a named value that a categorical leaves out has no probability
            continue
        text = text_of.get(parameter)
        # The text of the argument is the argument: read by itself, it is the node of the call.
        if text is None or _alone(text, units) is not node:
            raise DistributionProblem(f'{written!r} is not one call of {family} with its arguments')
        if _reads_a_name(node):
            # As the language writes it, with a space where a unit ends inside a word (`2 h/x`).
            args[parameter] = {'reads': literal_quantities(text, units, spaced=True)}
        else:
            args[parameter] = _number(node, parameter, family, unit, units)
    return {'family': family, 'args': args, 'text': written}


def _alone(text, units):
    """The node of the text of one argument, read by itself; None when it does not read."""
    try:
        return nodes.of_tree(ast.parse(literal_quantities(text, units), mode='eval').body)
    except SyntaxError:
        return None


# ---- the values of a run ----------------------------------------------------------------------------


def engine_value(value, parameter, units):
    """The value of an input (`parameter`, its `structure.Parameter`) in execution units, as an
    expression reads it: a bool is 1 or 0 and a named value its code (`metadata.values`)."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, str):
        return list(parameter.metadata['values']).index(value)
    return value * units.parse_unit(parameter.unit).scale


def order(uncertain, arguments):
    """The uncertain values in the order that their reads need: a distribution that reads another
    uncertain value comes after it, and the others keep their order. Raises DistributionProblem when
    some read each other, or one reads itself."""
    needs = {
        name: {
            symbol
            for source in (arguments.get(name, {}).get(record['text']) or {}).values()
            for symbol in names_in(source)
            if symbol in uncertain
        }
        for name, record in uncertain.items()
    }
    done, out = set(), []
    while len(out) < len(uncertain):
        ready = [name for name in uncertain if name not in done and needs[name] <= done]
        if not ready:
            left = sorted(name for name in uncertain if name not in done)
            raise DistributionProblem(f'the distributions of {", ".join(left)} read each other', left[0])
        out += ready
        done.update(ready)
    return out


def arguments_of(name, record, arguments, env, parameters, units):
    """The numbers of the arguments of one distribution, in the units of its parameters: each number
    as it is, and each argument that reads other values evaluated with their values (`env`, in
    execution units). `parameters` holds the inputs' records (`structure.Parameter`)."""
    unit = parameters[name].unit
    compiled = arguments.get(name, {}).get(record['text']) or {}
    out = {}
    for parameter, arg in record['args'].items():
        if not isinstance(arg, Mapping):
            out[parameter] = arg
            continue
        value = evaluate(compiled[parameter], env, units)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DistributionProblem(f'{parameter} is a number')
        out[parameter] = value if plain(parameter, record['family']) else value / units.parse_unit(unit).scale
    return out


def checked(name, record, args, parameters):
    """The problems of the arguments of one distribution and of its support, which lies inside the
    range of its input (`parameters[name].adjust`): a list of texts."""
    found = problems(record['family'], args)
    if found:
        return found
    adjust = parameters[name].adjust
    if FAMILIES[record['family']].kind == 'number' and adjust.mode == 'range':
        low, high = support(record['family'], args)
        if low < adjust.minimum or high > adjust.maximum:
            return [
                f'it takes values from {low} to {high}, outside the range [{adjust.minimum}, {adjust.maximum}]'
            ]
    return []


def central_value(record, args, parameter):
    """The central value of one distribution: the median of a number, the more likely bool, or the most
    likely named value (the first one on a tie). `parameter` is the record of its input."""
    value = central(record['family'], args)
    if record['family'] == 'categorical':
        return list(parameter.metadata['values'])[value]
    return value


def point_values(values, arguments, parameters, units, pick=None):
    """{name: point value} of the values of a run, `{name: value or distribution}`: each distribution
    replaced by `pick(name, record, args)`, its central value by default, in the order that the
    distributions that read other values need. `arguments` holds the compiled arguments that read
    other values, `{name: {text: {parameter: expression}}}`, and `parameters` the records of the
    inputs, `{name: structure.Parameter}`. Raises DistributionProblem, with the name of the value,
    for a distribution whose arguments or support are invalid."""
    uncertain = {name: value for name, value in values.items() if is_distribution(value)}
    if not uncertain:
        return dict(values)
    out = dict(values)
    env = {
        name: engine_value(value, parameters[name], units)
        for name, value in values.items()
        if name not in uncertain
    }
    for name in order(uncertain, arguments):
        record = uncertain[name]
        try:
            args = arguments_of(name, record, arguments, env, parameters, units)
        except (ExpressionError, DistributionProblem) as exc:
            raise DistributionProblem(f'{name}: {record["text"]}: {exc}', name) from None
        found = checked(name, record, args, parameters)
        if found:
            raise DistributionProblem(f'{name}: {record["text"]}: {"; ".join(found)}', name)
        value = (pick or (lambda n, r, a: central_value(r, a, parameters[n])))(name, record, args)
        out[name] = value
        env[name] = engine_value(value, parameters[name], units)
    return out
