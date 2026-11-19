"""An expression with many operations one inside the other: a long sum that an author writes by hand,
a deep nest of calls, choices or brackets, a chain of formulas, and a sum over many members.

The model has the value that the arithmetic gives, or the front end refuses it with a problem at a
line: there is no third case, and no length gives an error of Python. Each part that holds an
expression (a flow's request and capacity, an endpoint's setting, a trigger's condition, a stage's
assignment, an assertion) has the value of an expression of 100 terms.

The first model has an input rate of 3 people an hour and formulas of it. The second has n cells whose
level starts at 1 and rises by 0.5 an hour, and a pool that gathers a tenth of the sum of the levels
each hour: after 4 hours the sum is `n (1 + 0.5 × 4) = 3 n`, and the pool holds the integral of
`n (1 + 0.5 t) / 10`, `0.8 n`. A reduction is one read of the program (`refs.Reduce`), so it is no
deeper with more members.
"""

from __future__ import annotations

import sys

import pytest

from napkin.core.expr import DEEPEST
from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

HEAD = """\
scenario "Deep"
    horizon 4 h

s:
    input rate: person/h = 3 person/h in [0 person/h, 10 person/h]
    served: person = 0 person
    level: person = 0 person
"""

# Each form: the text of an expression with n operations one inside the other, and its value in
# people an hour when the rate is 3.
FORMS = {
    'a sum from the left': (lambda n: ' + '.join(['this.rate'] * (n + 1)), lambda n: 3 * (n + 1)),
    'a sum from the right': (lambda n: 'this.rate + (' * n + 'this.rate' + ')' * n, lambda n: 3 * (n + 1)),
    'signs': (lambda n: ' '.join(['-'] * (2 * (n // 2))) + ' this.rate', lambda n: 3),
    'calls': (lambda n: 'min(' * n + 'this.rate' + ', this.rate)' * n, lambda n: 3),
    'choices': (
        lambda n: '(this.rate if this.rate > 0 person/h else ' * n + 'this.rate' + ')' * n,
        lambda n: 3,
    ),
    'brackets': (lambda n: '(' * n + 'this.rate' + ')' * n, lambda n: 3),
}


class Recursed(AssertionError):
    """The front end ended in a RecursionError: raised in its place, so that the report is short."""


# The parser reads a bracket, a call or a choice with about eleven calls of Python for each level, and
# the declared model a sum or a sign with two for each term: past about 90 levels of the first and 450
# terms of the second, the stack of Python ends before the front end does.
RECURSION = pytest.mark.xfail(
    strict=True,
    raises=Recursed,
    reason='bug: napkin/model/language/parse.py and semantic.py recurse once or more for each level of an '
    'expression, so a deep expression ends in a RecursionError, not in a value or a problem at its line',
)
NESTED = ('a sum from the right', 'calls', 'choices', 'brackets')


def depths(form):
    """The depths of a form that the test reads: a few levels, 60, and past the deepest tree, up to
    the first depth at which the front end ends in a RecursionError, so that each form shows the bug
    once."""
    return (3, 60, DEEPEST + 1) if form in NESTED else (3, 60, DEEPEST + 1, 2 * DEEPEST, 700)


def broken(form, levels):
    return (form in NESTED and levels > 90) or levels >= 450


def value_of(expression, name='s.total', time=4):
    """The value of `name` at `time` in the model with `total = formula(expression)`."""
    try:
        model = compile_text(HEAD + f'    total = formula({expression})\n', UNITS)
    except RecursionError:
        raise Recursed('the front end ended in a RecursionError') from None
    record = run(model.program, model.configuration)
    assert record.failure is None, record.failure.detail('message')
    (found,) = read(record, model.program, [name], [time])
    return found.values[0]


@pytest.mark.parametrize('terms', [2, 40, 100, DEEPEST, 2 * DEEPEST])
def test_a_sum_of_many_terms_is_an_expression_like_any_other(terms):
    assert value_of(' + '.join(['this.rate'] * terms)) == 3 * terms


@pytest.mark.parametrize(
    ('form', 'levels'),
    [
        pytest.param(form, levels, marks=[RECURSION] if broken(form, levels) else [])
        for form in sorted(FORMS)
        for levels in depths(form)
    ],
)
def test_an_expression_of_any_depth_has_its_value_or_a_problem_at_its_line(form, levels):
    """Each form with a few levels, near the deepest tree of `napkin/core/expr.py`, and far past it.
    With 60 levels and fewer it has the value."""
    source, value = FORMS[form]
    try:
        found = value_of(source(levels))
    except LanguageError as refused:
        assert levels > 60 and all(problem.code and problem.line for problem in refused.problems)
    else:
        assert found == value(levels)


@pytest.mark.parametrize(
    'form',
    [
        'a sum from the left',
        pytest.param('a sum from the right', marks=RECURSION),
        'signs',
    ],
)
def test_an_expression_at_the_deepest_tree_leaves_room_on_the_stack(form):
    """A caller can be deep itself (a test runner, a notebook, a server): with 250 calls fewer than
    Python gives, an expression one level below the deepest tree still has its value."""
    source, value = FORMS[form]
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(limit - 250)
    try:
        found = value_of(source(DEEPEST - 1))
    finally:
        sys.setrecursionlimit(limit)
    assert found == value(DEEPEST - 1)


def cells(n):
    """The cells and the pool of the module's docstring, the cells as the rows of a table."""
    text = """\
scenario "Cells"
    horizon 4 h

Cell:
    level: work_unit = 1 work_unit in [0 work_unit,]
    flow fill: SOURCE -> this.level
        request = 0.5 work_unit/h

cells: Cell from "cells.csv"

pool:
    held: work_unit = 0 work_unit
    flow gather: SOURCE -> this.held
        request = formula(sum(Cell.instances.level) / 10 h)

total = formula(sum(Cell.instances.level))
"""
    return compile_text(text, UNITS, tables={'cells.csv': 'id\n' + ''.join(f'c{k}\n' for k in range(n))})


@pytest.mark.parametrize('n', [3, 45, 140, DEEPEST + 1, 2000])
def test_a_sum_over_many_members_has_its_value(n):
    model = cells(n)
    record = run(model.program, model.configuration)
    total, held = read(record, model.program, ['total', 'pool.held'], [4])
    assert total.values == pytest.approx((3 * n,), rel=1e-12)
    assert held.values == pytest.approx((0.8 * n,), rel=1e-9)


@pytest.mark.parametrize(('count', 'terms'), [(3, 40), (2, 75), (2, 76), (10, 100)])
def test_a_chain_of_formulas_has_its_value_however_deep_it_is_written_out(count, terms):
    """`count` formulas, each of `terms` terms: the first adds the rate `terms` times, and each next
    one adds the rate `terms - 1` times to the one before it. Written out, the last is
    `terms + (count - 1) (terms - 1)` deep, past the deepest tree for the last three; each formula is
    read by its path, so none is written out. With the rate of 3 people an hour the last is
    `3 (terms + (count - 1) (terms - 1))`."""
    rows = ['    f1 = formula(' + ' + '.join(['this.rate'] * terms) + ')']
    for k in range(2, count + 1):
        rows.append(
            f'    f{k} = formula(' + ' + '.join([f'this.f{k - 1}', *['this.rate'] * (terms - 1)]) + ')'
        )
    model = compile_text(HEAD + '\n'.join(rows) + '\n', UNITS)
    (found,) = read(run(model.program, model.configuration), model.program, [f's.f{count}'], [4])
    assert found.values == (3 * (terms + (count - 1) * (terms - 1)),)


def deep(n):
    """A sum of n rates: n - 1 operations one inside the other."""
    return ' + '.join(['this.rate'] * n)


# Each kind of part with an expression of n terms in it, the value that it reads and that value at
# 4 h when the rate is 3: the flows fill a store at 300 people an hour; the trigger fires at once and
# sets the level to 1 person; the stage at 1 h sets it to 300 people.
PARTS = {
    'a flow request': (
        lambda n: f'    flow extra: SOURCE -> this.served\n        request = formula({deep(n)})\n',
        's.served',
        1200,
    ),
    'a flow capacity': (
        lambda n: (
            '    flow extra: SOURCE -> this.served\n'
            '        request = 1000 person/h\n'
            f'        capacity = formula({deep(n)})\n'
        ),
        's.served',
        1200,
    ),
    'an endpoint setting': (
        lambda n: (
            f'    got: person = 0 person\n        inflow.capacity = formula({deep(n)})\n'
            '    flow extra: SOURCE -> this.got\n        request = 1000 person/h\n'
        ),
        's.got',
        1200,
    ),
    'a trigger condition': (
        lambda n: (
            '    seen = event():\n'
            f'        when {deep(n)} >= 300 person/h:\n'
            '            this.seen.start()\n'
            '            reset when false\n'
            '        after 0 h:\n'
            '            this.level = 1 person\n'
        ),
        's.level',
        1,
    ),
    'a stage assignment': (
        lambda n: (
            '    refill = event():\n'
            '        after 1 h:\n'
            f'            this.level = ({deep(n)}) * 1 h\n'
            's.refill.start()\n'
        ),
        's.level',
        300,
    ),
    'an assertion': (lambda n: f'assert {deep(n).replace("this.", "s.")} >= 0 person/h\n', 's.served', 0),
}


@pytest.mark.parametrize('part', sorted(PARTS))
def test_each_kind_of_part_holds_an_expression_of_a_hundred_terms(part):
    make, name, expected = PARTS[part]
    model = compile_text(HEAD + make(100), UNITS)
    record = run(model.program, model.configuration)
    assert record.failure is None, record.failure.detail('message')
    (found,) = read(record, model.program, [name], [4])
    assert found.values == pytest.approx((expected,), rel=1e-12)
