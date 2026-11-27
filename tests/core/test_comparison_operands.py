"""The comparison walk shares expression structure across evaluations."""

import sys
from fractions import Fraction

from napkin.core import comparisons, expr
from napkin.core.comparisons import Binding, Comparisons, SelectedScale


def test_shared_operands_read_the_current_choice_and_binding_in_order():
    flag, x, y, alias = map(expr.ref, ('flag', 'x', 'y', 'alias'))
    choice = expr.if_else(flag, x, y)
    roots = (expr.binary('sub', choice, choice), expr.binary('add', alias, choice))
    picked = SelectedScale(lambda read: choice if read('first') else y, {'first'}, ('x', 'y'))
    bindings = {'x': Fraction(1, 3), 'y': 5, 'alias': picked}
    values = {'flag': True, 'first': True}
    calls = []

    def bind(name):
        calls.append(name)
        return Binding(1, bindings[name])

    def read(node):
        if isinstance(node, SelectedScale):
            return node.choose(lambda name: read(expr.ref(name)))
        calls.append(node.name)
        return values[node.name]

    policy = Comparisons(None, named=bind)
    cancelled, combined = policy.operands(roots, read)
    assert calls == ['flag', 'x', 'alias', 'first']
    assert cancelled.terms == {x: 0} and combined.terms == {x: 2 * float(Fraction(1, 3))}

    calls.clear()
    values.update(flag=False, first=False)
    bindings['y'] = 7
    cancelled, combined = policy.operands(roots, read)
    assert calls == ['flag', 'y', 'alias', 'first']
    assert cancelled.floor == 0 and combined.terms == {y: 14}

    calls.clear()
    bindings['alias'] = x
    _, combined = policy.operands(roots, read)
    assert calls == ['flag', 'y', 'alias', 'x']
    assert combined.terms == {x: float(Fraction(1, 3)), y: 7}


def test_deep_inline_operations_and_named_scale_definitions_use_an_explicit_stack():
    depth = sys.getrecursionlimit() + 20
    leaf = expr.ref('leaf')
    body = leaf
    for _ in range(depth):
        body = expr.unary('pos', body)
    bindings = {f'n{i}': expr.ref(f'n{i + 1}') for i in range(depth)}
    bindings[f'n{depth}'] = body
    bindings['leaf'] = Fraction(1, 3)
    policy = Comparisons(None, named=lambda name: Binding(1, bindings[name]))
    (scale,) = policy.operands((expr.ref('n0'),), None)
    assert scale.terms == {leaf: Fraction(1, 3)} and scale.floor == Fraction(1, 3)


def test_row_views_reuse_the_walk_and_read_their_own_bindings(monkeypatch):
    quantity = expr.ref('amount')
    root = expr.binary('add', quantity, quantity)
    compiled = []
    operands = comparisons._scale_operands

    def observe(node):
        compiled.append(node)
        return operands(node)

    monkeypatch.setattr(comparisons, '_scale_operands', observe)
    sizes = {'small.amount': 2, 'large.amount': 7}
    policy = Comparisons(None, named=lambda name: Binding(1, sizes[name]))
    for row, expected in [('small', 4), ('large', 14)]:
        view = policy.for_row(None, lambda name: f'{row}.{name}')
        (scale,) = view.operands((root,), None)
        assert scale.terms == {quantity: expected}
    assert compiled == [root]


def test_a_floor_that_reads_the_state_walks_again_only_when_a_value_that_it_read_changes(monkeypatch):
    flag, x, y = map(expr.ref, ('flag', 'x', 'y'))
    left, right = expr.if_else(flag, x, y), expr.const(0)
    policy = Comparisons(None, named=lambda name: Binding(1, {'x': Fraction(1, 3), 'y': 5}[name]))
    values = {'flag': True}
    walks = []
    operands = Comparisons.operands

    def walked(self, roots, read):
        walks.append(roots)
        return operands(self, roots, read)

    monkeypatch.setattr(Comparisons, 'operands', walked)

    def floor():
        return policy.floor(left, right, lambda node: values[node.name])

    assert floor() == Fraction(1, 3) and len(walks) == 1
    assert floor() == Fraction(1, 3) and len(walks) == 1  # the same value read: the same walk
    values['flag'] = False
    assert floor() == 5 and len(walks) == 2
    policy.floors.clear()  # what clears the floors clears the memo with them
    assert floor() == 5 and len(walks) == 3


def test_a_row_keeps_its_policy_and_what_it_learned_until_the_floors_are_cleared():
    from types import SimpleNamespace

    from napkin.core.arrays import _Pass

    policy = Comparisons(None, named=lambda name: Binding(1, 1))
    registry = SimpleNamespace(comparisons=policy)
    run = _Pass({}, registry, 2, {'this.x': ('a.x', 'b.x')}, None)
    key = (expr.ref('this.x'), expr.const(0), (('this.x', ('a.x', 'b.x')),))
    first = run.row_policy(0, key)
    assert run.row_policy(0, key) is first and run.row_policy(1, key) is not first
    assert run.row_policy(0) is not first  # without a key, a row's policy is made for that read only
    policy.floors.clear()
    assert run.row_policy(0, key) is not first
