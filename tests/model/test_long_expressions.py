"""An expression with many operations one inside the other: a long sum that an author writes by
hand, a deep nest of calls, a sum over the many copies of a template that a flat structure writes
member by member.

The readers of an expression go down its tree, so there is a deepest tree (`core.expr.DEEPEST`).
Up to it, an output of such an expression compiles, runs and reports, with the value that the
arithmetic gives. Past it, the compiler refuses the model with a diagnostic. The limit also holds
for what the checks and the engine make of an expression (a proof that puts a rule's guard around
it; a formula written in the place of its name), so a part within a few levels of the limit can be
refused too, by the check that made the deeper expression. No length gives an error of Python.

The first model is a tally that rises at a rate of 3 people an hour, with an output that is an
expression of the rate. The second has n copies of a cell whose level starts at 1 and rises by 0.5
an hour, and a pool that gathers a tenth of the sum of the levels each hour: after 4 hours the sum
is `n (1 + 0.5 × 4) = 3 n`, and the pool holds the integral of `n (1 + 0.5 t) / 10`, `0.8 n`.
"""

import sys

import pytest

from napkin.core.expr import DEEPEST
from napkin.engine import evaluate_study, sample_result
from napkin.model.ir import ModelError
from tests import build as b

# Each form: the text of an expression with n operations one inside the other, and its value in
# people an hour when the rate is 3.
FORMS = {
    'a sum from the left': (lambda n: ' + '.join(['s.rate'] * (n + 1)), lambda n: 3 * (n + 1)),
    'a sum from the right': (lambda n: 's.rate + (' * n + 's.rate' + ')' * n, lambda n: 3 * (n + 1)),
    'signs': (lambda n: ' '.join(['-'] * (2 * (n // 2))) + ' s.rate', lambda n: 3),
    'calls': (lambda n: 'min(' * n + 's.rate' + ', s.rate)' * n, lambda n: 3),
    'choices': (lambda n: '(s.rate if s.rate > 0 people/h else ' * n + 's.rate' + ')' * n, lambda n: 3),
    'brackets': (lambda n: '(' * n + 's.rate' + ')' * n, lambda n: 3),
}


def with_output(source):
    return b.system(
        b.parameter('rate', 3, 'people/h', 0, 10),
        b.stock('served', 0, kind='tally', size=None, rate='rate'),
        horizon=4,
        outputs=(b.output('total', source, 'people/h', 'level'),),
    )


def copies(n):
    return b.document(
        'Copies',
        b.template(
            'Cell',
            b.stock('level', 1, 'episodes', size=10),
            b.flow('fill', b.move(None, 'level'), '0.5 episodes/h'),
        ),
        b.entity('cells', template='Cell', copies=n),
        b.entity(
            'pool',
            b.stock('held', 0, 'episodes', kind='tally', size=None),
            b.flow('gather', b.move(None, 'held'), 'sum(Cell.level) / 10 h'),
        ),
        b.output('total', 'sum(Cell.level)', 'episodes', 'level'),
        b.output('held', 'pool.held', 'episodes'),
        horizon=4,
    )


def last_values(text):
    """The values of the outputs at the horizon, from the report of the study of the model."""
    report = sample_result(evaluate_study(b.compiled(text)))
    assert report['admissible'], report['diagnostics']
    (run,) = report['runs'].values()
    return list(run['reporting_points'].values())[-1]['values']


def line_of_the_output(text):
    return 1 + next(k for k, row in enumerate(text.splitlines()) if row.startswith('output total'))


@pytest.mark.parametrize('terms', [2, 40, 100, DEEPEST])
def test_a_sum_of_many_terms_is_an_expression_like_any_other(terms):
    """n times the rate of 3 people an hour. Forty terms and more were past what the code of one
    function could hold: the report of such a model failed."""
    assert last_values(with_output(' + '.join(['s.rate'] * terms)))['total'] == 3 * terms


@pytest.mark.parametrize('terms', [DEEPEST + 1, 180, 420, 600, 1500, 6000])
def test_a_sum_that_is_deeper_than_the_readers_go_is_refused_at_its_line(terms):
    """The compiler refuses the expression with one diagnostic, at the line of the output that
    holds it. Six hundred terms and more were an error of Python."""
    text = with_output(' + '.join(['s.rate'] * terms))
    with pytest.raises(ModelError) as raised:
        b.compiled(text)
    (found,) = raised.value.diagnostics
    assert (found['code'], found['line']) == ('build', line_of_the_output(text))


@pytest.mark.parametrize('form', sorted(FORMS))
@pytest.mark.parametrize('levels', [3, 60, DEEPEST - 2, DEEPEST + 1, 2 * DEEPEST, 3 * DEEPEST + 40, 700])
def test_an_expression_of_any_depth_has_its_value_or_a_diagnostic(form, levels):
    """Each form with a few levels, near the deepest tree, and far past it. The model has the
    value of the expression, or the compiler refuses it with a diagnostic at a place: there is no
    third case. With 60 levels and fewer it has the value."""
    source, value = FORMS[form]
    text = with_output(source(levels))
    try:
        found = last_values(text)['total']
    except ModelError as refused:
        assert levels > 60
        assert refused.diagnostics and all(problem['code'] for problem in refused.diagnostics)
    else:
        assert found == value(levels)


@pytest.mark.parametrize('form', ['a sum from the left', 'a sum from the right', 'signs'])
def test_an_expression_at_the_deepest_tree_leaves_room_on_the_stack(form):
    """The deepest tree is set so that its readers stay well inside the calls that Python has. A
    caller can be deep itself (a test runner, a notebook, a server): with 250 calls fewer than
    Python gives, the model of each form that gets to the deepest tree still compiles, runs and
    reports. (A nest of calls or of choices has more parts for each level: the limit of the
    number of parts refuses it before it is that deep.)"""
    source, value = FORMS[form]
    text = with_output(source(DEEPEST - 1))
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(limit - 250)
    try:
        found = last_values(text)['total']
    finally:
        sys.setrecursionlimit(limit)
    assert found == value(DEEPEST - 1)


@pytest.mark.parametrize('n', [3, 45, 140])
def test_a_sum_over_the_copies_of_a_template_in_a_flat_structure_has_its_value(n):
    """A flat structure writes the sum member by member: a chain as deep as the number of copies.
    A flow reads it and an output gives it. Forty-five copies were past what the code of the
    report could hold."""
    found = last_values(copies(n))
    assert found['total'] == pytest.approx(3 * n, rel=1e-12)
    assert found['held'] == pytest.approx(0.8 * n, rel=1e-9)


@pytest.mark.parametrize('n', [DEEPEST + 1, 200, 330, 640, 2000])
def test_a_sum_over_too_many_copies_for_a_flat_structure_is_refused_at_its_place(n):
    """The sum is deeper than the readers go. The compiler refuses the model with one diagnostic,
    at the line of a part that holds the sum: the flow of the pool or the output. With 640 copies
    it was an error of Python."""
    text = copies(n)
    lines = text.splitlines()
    holders = {1 + k for k, row in enumerate(lines) if 'sum(Cell.level)' in row}
    assert len(holders) == 2
    with pytest.raises(ModelError) as raised:
        b.compiled(text)
    (found,) = raised.value.diagnostics
    assert found['code'] == 'expression' and found['line'] in holders


def chain_of_formulas(count, terms):
    """`count` formulas, each of `terms` terms: the first adds the rate `terms` times, and each next
    one adds the rate `terms - 1` times to the one before it. Each is `terms` operations deep by
    itself; written out, the last is `terms + (count - 1) (terms - 1)` deep, and with the rate of 3
    people an hour it is `3 (terms + (count - 1) (terms - 1))`."""
    members = [b.formula('f1', ' + '.join(['rate'] * terms), 'people/h')]
    for k in range(2, count + 1):
        members.append(b.formula(f'f{k}', ' + '.join([f'f{k - 1}', *['rate'] * (terms - 1)]), 'people/h'))
    return b.system(
        b.parameter('rate', 3, 'people/h', 0, 10),
        b.stock('served', 0, kind='tally', size=None, rate='rate'),
        *members,
        horizon=4,
        outputs=(b.output('total', f's.f{count}', 'people/h', 'level'),),
    )


@pytest.mark.parametrize(('count', 'terms'), [(3, 40), (2, 75)])
def test_a_chain_of_formulas_within_the_deepest_tree_runs_with_its_value(count, terms):
    assert terms + (count - 1) * (terms - 1) <= DEEPEST
    assert last_values(chain_of_formulas(count, terms))['total'] == 3 * (terms + (count - 1) * (terms - 1))


@pytest.mark.parametrize(('count', 'terms'), [(2, 76), (2, 100), (10, 100)])
def test_a_chain_of_formulas_deeper_than_the_deepest_tree_is_refused_at_its_lines(count, terms):
    """The engine writes each formula in the place of its name, so it goes down the written-out
    chain. Each formula is within the deepest tree by itself; written out, the chain is deeper,
    and the compiler refuses it at the line of each formula that is too deep, and of the output
    that reads the last one. Ten formulas of 100 terms ended in an error of Python in a run."""
    assert terms <= DEEPEST < terms + (count - 1) * (terms - 1)
    text = chain_of_formulas(count, terms)
    rows = text.splitlines()
    second = 1 + next(k for k, row in enumerate(rows) if row.lstrip().startswith('let f2'))
    with pytest.raises(ModelError) as raised:
        b.compiled(text)
    found = raised.value.diagnostics
    assert {item['code'] for item in found} == {'expression'}
    assert str(second) in {str(item.get('line')) for item in found}


def deep(n):
    """A sum of n rates: n - 1 operations one inside the other."""
    return ' + '.join(['s.rate'] * n)


# Each kind of part with an expression of n terms in it, and a word of the line that holds it.
PARTS = {
    'a flow rate': (lambda n: b.flow('extra', b.move(None, 'served'), deep(n)), 'flow extra'),
    'a condition of an event': (
        lambda n: b.event('seen', f'{deep(n)} > 1000 people/h', 'level = 1 people'),
        'event seen',
    ),
    'the value of a step': (
        lambda n: b.event('reset', 'served >= 5 people', f'level = ({deep(n)}) * 1 h'),
        'level = (',
    ),
    'a check': (lambda n: b.check(f'{deep(n)} >= 0 people/h', 'The rates are not below zero.'), 'assert'),
    'the limit of a share': (lambda n: b.share('level', deep(n)), 'share level'),
    'an argument of a distribution': (
        lambda n: b.uncertain(
            'cap', 'people/h', 0, 10**6, 'uniform(0 people/h, ' + ' + '.join(['1 people/h'] * n) + ')'
        ),
        'input cap',
    ),
}


def with_part(part, n):
    make, _ = PARTS[part]
    return b.system(
        b.parameter('rate', 3, 'people/h', 0, 10),
        b.stock('served', 0, kind='tally', size=None, rate='rate'),
        b.stock('level', 0, 'people', size=100),
        b.flow('use', b.move('level', None), '0.5 people/h'),
        b.flow('waste', b.move('level', None), '0.25 people/h'),
        make(n),
        # The two flows from the level have one share; the part of the share is its own.
        *(() if part == 'the limit of a share' else (b.share('level', '10 people/h'),)),
        horizon=4,
    )


@pytest.mark.parametrize('part', sorted(PARTS))
def test_the_deepest_tree_holds_in_each_kind_of_part_at_its_line(part):
    """An expression of 100 terms compiles in each kind of part; one of `DEEPEST + 1` terms is
    refused with a diagnostic at the line of that part, and with no error of Python."""
    b.compiled(with_part(part, 100))
    text = with_part(part, DEEPEST + 1)
    word = PARTS[part][1]
    line = 1 + next(k for k, row in enumerate(text.splitlines()) if word in row)
    with pytest.raises(ModelError) as raised:
        b.compiled(text)
    found = raised.value.diagnostics
    assert found and all(item['code'] for item in found)
    assert str(line) in {str(item.get('line')) for item in found}, found
