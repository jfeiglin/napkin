"""The engine's form of a typed expression (`rewrite.desugared`), and a constant as a text writes it.

`count(e)`, `since(e)` and `elapsed(s)` become reads of the names that a structure keeps for an event
and for a named state. Their meaning is checked by values: the form is evaluated beside the meaning
that docs/language.md gives, on random states of an event.
"""

import random

import pytest

from napkin.core import evaluation, expr
from napkin.model.lower.expressions import RewriteError, desugared, source_node
from tests.core.reference import UNITS

ORDER = {
    '>=': lambda a, b: a >= b,
    '>': lambda a, b: a > b,
    '<': lambda a, b: a < b,
    '<=': lambda a, b: a <= b,
}


def form(text):
    """The engine's form of an expression that the typing would give for `text`."""
    return desugared(source_node(text, 'here'), 'here')


def test_since_holds_when_the_event_happened_and_the_time_since_then_compares():
    rng = random.Random(20261112)
    seen = set()
    for _ in range(400):
        op, limit = rng.choice(sorted(ORDER)), rng.choice((0.0, 1.5, 4.0))
        # Either side of the comparison: since(e) OP d, and d OP since(e).
        first = rng.random() < 0.5
        text = f's.fire.done {op} {limit}'.replace('s.fire.done', 'since(s.fire.done)')
        if not first:
            text = f'{limit} {op} since(s.fire.done)'
        count, at, now = rng.choice((0, 1, 3)), rng.choice((0.0, 2.0, 5.0)), rng.choice((2.0, 5.0, 9.5))
        env = {'s.fire.done__count': count, 's.fire.done__time': at, 't': now}
        elapsed = now - at
        want = count > 0 and (ORDER[op](elapsed, limit) if first else ORDER[op](limit, elapsed))
        assert evaluation.value(form(text), env, UNITS) is want, (text, env)
        seen.add((count > 0, want))
    assert seen == {(False, False), (True, False), (True, True)}


def test_count_and_elapsed_read_the_names_that_the_structure_keeps():
    env = {'s.fire__count': 3, 's.state__entered': 2.5, 't': 7.0, 'x': 2}
    assert evaluation.value(form('count(s.fire) * x'), env, UNITS) == 6
    assert evaluation.value(form('elapsed(s.state) + 1'), env, UNITS) == 5.5
    assert expr.names(form('count(s.fire) > 0 and elapsed(s.state) > x')) == {
        's.fire__count',
        's.state__entered',
        't',
        'x',
    }
    # Everything else is the expression itself, the same node.
    plain = expr.read("min(x, q(2, 'h')) if x > 1 else -x ** 2")
    assert desugared(plain, 'here') is plain


@pytest.mark.parametrize(
    'text, message',
    [
        ('since(s.fire)', r'since\(\) must be one side of a comparison'),
        ('since(s.fire) + 1 > 2', r'since\(\) must be one side of a comparison'),
        ('1 < since(s.fire) < 2', r'since\(\) compares with one value at a time'),
        ('since(s.fire) > since(s.stop)', r'since\(\) compares with one value at a time'),
        ('since(x + 1) > 2', r'since\(\) takes one event name'),
        ('count(x, y)', r'count\(\) takes one event name'),
        ('elapsed(x + 1)', r'elapsed\(\) takes one named state'),
        ('x + s.fire__count', "names may not contain '__'"),
        ('', 'an expression must be a nonempty string or a number'),
        ('x +', 'invalid expression'),
    ],
)
def test_a_form_that_has_no_meaning_is_an_error_at_its_place(text, message):
    with pytest.raises(RewriteError, match=message) as raised:
        form(text)
    assert raised.value.diagnostic['path'] == 'here'


def test_a_value_that_a_firing_event_reads_keeps_its_name():
    # The names of a draw and of a value of the past hold `__`, and are the event's own.
    kept = form('s.fire__draw0 + s.fire__delayed1 * 2')
    assert expr.names(kept) == {'s.fire__draw0', 's.fire__delayed1'}


def test_a_constant_is_the_node_that_its_text_reads_back_to():
    for value in (0, 1, 2.5, -1, -2.5, -0.0, 1e-05, 1e22, 'on', True, False):
        node = expr.written(value)
        assert expr.read(expr.text(node)) is node, value
    assert expr.written(-1) is expr.unary('neg', expr.const(1)) and expr.written(0.0) is expr.const(0.0)
    assert expr.text(expr.written(-0.0)) == '-0.0'
    # A part of an expression that is outside the language is known to be there.
    assert expr.outside(expr.read('x + [y]')) and not expr.outside(expr.read('x + y'))
