"""Small, typed expression language. Values execute in canonical units; no eval.

Each entry takes an expression as its node (`core/expr.py`), or a number or a yes/no, which is the
constant that it is. A text is a `TypeError`: a caller that has a text reads it first
(`core.expr.read`)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from .core import evaluation, expr
from .core.errors import ExpressionError
from .core.faces import constant_on_faces
from .core.intervals import prover
from .core.units import BOOLEAN, NUMBER, STRING, ZERO, Unit, UnitRegistry, UnitSystem, same, unit_of

__all__ = [
    'BOOLEAN',
    'NUMBER',
    'STRING',
    'ZERO',
    'Expression',
    'ExpressionError',
    'Unit',
    'UnitRegistry',
    'UnitSystem',
    'compile_expression',
    'compile_program',
    'domain_prover',
    'evaluate',
    'infer',
    'names_in',
    'stock_face_dependencies',
    'validate_domains',
]

# What an entry says of a text.
TEXT = 'an expression is a node or a number: read a text with napkin.core.expr.read'


def _no_text(source):
    """Raise the TypeError of a text."""
    if isinstance(source, str):
        raise TypeError(TEXT)


def _number(source):
    """Whether a source is a number or a yes/no, which is the constant that it is."""
    return isinstance(source, (bool, int, float))


@dataclass(frozen=True)
class Expression:
    source: expr.Node
    unit: Unit
    dependencies: frozenset[str]
    # Only the node is retained, and a node cannot change.
    _registry: UnitRegistry

    def evaluate(self, environment: Mapping):
        return evaluation.checked_value(self.source, environment, self._registry)

    __call__ = evaluate


def compile_expression(
    source: expr.Node | int | float | bool,
    symbol_units: Mapping[str, Unit],
    registry: UnitRegistry,
    expected: Unit | None = None,
) -> Expression:
    """The check of an expression: the limits of size of its text (`expr.limited`), its unit, which
    is `expected` when it is given, and the value of an expression that reads no name. A number is
    its constant as its text writes it (`expr.written`)."""
    _no_text(source)
    if _number(source):
        if not isinstance(source, bool) and not math.isfinite(source):
            raise ExpressionError('Nonfinite literal')
        source = expr.written(source)
    if not isinstance(source, expr.Node):
        raise ExpressionError('Expression must be a node or a number')
    node = expr.limited(source)
    unit, dependencies = unit_of(node, symbol_units, registry)
    if expected is not None:
        same(unit, expected.canonical())
    result = Expression(node, unit, dependencies, registry)
    # Catch unconditional constant-domain errors, while preserving lazy conditionals.
    if not dependencies:
        result.evaluate({})
    return result


def _node(source):
    """The node of a source of a program: a number is the constant that it is."""
    _no_text(source)
    if isinstance(source, expr.Node):
        return source
    if _number(source):
        if not isinstance(source, bool) and not math.isfinite(source):
            raise ExpressionError('Nonfinite literal')
        return expr.const(source)
    raise TypeError(f'{TEXT}, not {type(source).__name__}')


def compile_program(
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
    """`evaluation.program` for sources that are nodes or numbers: a straight-line program
    `program(*arguments)` that assigns each named source of `assignments` in order, then returns the
    tuple of `outputs`, with the semantics of evaluating each source in turn (`evaluate`)."""
    return evaluation.program(
        ((name, _node(source)) for name, source in assignments),
        (_node(source) for source in outputs),
        constants=constants,
        units=units,
        read=read,
        arguments=arguments,
        write=write,
        lean=lean,
    )


def names_in(source):
    """The names that an expression reads: a node, or a number (which reads none)."""
    if isinstance(source, expr.Node):
        return expr.names(source)
    if _number(source):
        return frozenset()
    _no_text(source)
    raise TypeError(f'{TEXT}, not {type(source).__name__}')


def infer(source, symbols, units):
    registry = units if isinstance(units, UnitRegistry) else UnitSystem(units)
    mapped = {
        name: registry.parse_unit(value) if isinstance(value, str) else value
        for name, value in symbols.items()
    }
    return compile_expression(source, mapped, registry).unit


def evaluate(source, environment, units):
    """The value of an expression in an environment: a node, or a number (which is its own value).
    Each failure is an ExpressionError that names the expression."""
    _no_text(source)
    if _number(source):
        if isinstance(source, (float, int)) and not math.isfinite(source):
            raise ExpressionError('Nonfinite literal')
        return source
    if not isinstance(source, expr.Node):
        raise ExpressionError(f'{source!r}: {TEXT}, not {type(source).__name__}')
    registry = units if isinstance(units, UnitRegistry) else UnitSystem(units)
    return evaluation.checked_value(source, environment, registry)


def _formula(source):
    """The node of a formula or of an expression of a proof: a node, or a number, which is the node of
    its text (`expr.written`)."""
    _no_text(source)
    if isinstance(source, expr.Node):
        return source
    if _number(source):
        return expr.written(source)
    raise TypeError(f'{TEXT}, not {type(source).__name__}')


def stock_face_dependencies(source, static_names, zero_stocks, aliases, parameters, units):
    """`faces.constant_on_faces` for an expression and formulas ({name: node}) that are nodes or
    numbers: the stocks whose zero face the expression is constant on, or None."""
    node = _formula(source)
    registry = units if isinstance(units, UnitRegistry) else UnitSystem(units)
    formulas = {name: _formula(value) for name, value in aliases.items()}
    return constant_on_faces(node, static_names, zero_stocks, formulas, parameters, registry)


def validate_domains(source, ranges, units, aliases=None):
    """Prove division/log/sqrt domains using bounds and simple lazy conditions.

    Ranges are canonical closed intervals. This is conservative: unsupported
    correlated proofs fail rather than being certified by sampled evaluations.
    It does not promise an arbitrary nonlinear solution is numerically stable.
    """
    return domain_prover(ranges, units, aliases)(_formula(source))


def domain_prover(ranges, units, aliases=None, weights=None):
    """`intervals.prover` with formulas ({name: node}) that are nodes or numbers: the function of one
    node that gives its interval over `ranges`, or raises its ExpressionError. The function copies the
    ranges and the formulas. `weights` are those of `intervals.prover`."""
    registry = units if isinstance(units, UnitRegistry) else UnitSystem(units)
    formulas = {name: _formula(value) for name, value in (aliases or {}).items()}
    return prover(ranges, registry, formulas, weights)
