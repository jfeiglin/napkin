"""The generated programs of the engine (`expressions.compile_program`).

A program has the semantics of evaluating each of its expressions in turn (`expressions.evaluate`):
the same value of the same type, bit for bit, and a failure where an evaluation fails. A part of an
expression that reads only known inputs is computed once, when the program is made, by Python's own
operations; a part that fails stays code, so it fails only when a run reaches it. A program that
checks a value only where it could be hidden (`lean`) gives the same values and fails where an
evaluation fails.
"""

import dis
import math
import random

import pytest

from napkin.core import expr
from napkin.expressions import ExpressionError, UnitSystem, compile_program, evaluate
from tests.units import UNITS

REGISTRY = UnitSystem(UNITS)
FAILURES = (ArithmeticError, ValueError, TypeError, KeyError)


def outcome(compute):
    """('fails',) when `compute` fails as an evaluation fails, else the type and the exact value."""
    try:
        value = compute()
    except FAILURES:
        return ('fails',)
    return type(value), value.hex() if isinstance(value, float) else value


def test_a_known_input_is_written_into_the_program():
    program = compile_program(
        [('c.twice', expr.read('p.a * 2'))], [expr.read('c.twice + x')], constants={'p.a': 3}, units=REGISTRY
    )
    env = {'x': 1.0}
    assert program(env, REGISTRY) == (7.0,)
    # 3 * 2 is the int 6, as the evaluation gives it, and the program writes it into the environment.
    assert outcome(lambda: env['c.twice']) == (int, 6)
    # The program does not read the input when it runs.
    assert program({'x': 1.0, 'p.a': 100}, REGISTRY) == (7.0,)


def test_an_assignment_that_reads_only_known_values_is_known_and_the_next_one_reads_it():
    program = compile_program(
        [('c.a', expr.read('p.a + 1')), ('c.b', expr.read('c.a * x'))],
        [expr.read('c.b')],
        constants={'p.a': 1},
        units=REGISTRY,
    )
    env = {'x': 1.5}
    assert program(env, REGISTRY) == (3.0,)
    assert env == {'x': 1.5, 'c.a': 2, 'c.b': 3.0}


def test_an_assignment_hides_a_known_input_of_the_same_name():
    program = compile_program(
        [('p.a', expr.read('x + 1'))], [expr.read('p.a * 2')], constants={'p.a': 5}, units=REGISTRY
    )
    env = {'x': 1.0}
    assert program(env, REGISTRY) == (4.0,)
    assert env['p.a'] == 2.0


def test_a_branch_that_a_known_test_leaves_out_never_runs():
    known = compile_program(
        [],
        [expr.read('x if p.flag else 1 / p.zero')],
        constants={'p.flag': True, 'p.zero': 0},
        units=REGISTRY,
    )
    assert known({'x': 2.5}, REGISTRY) == (2.5,)
    # With a test that the program reads, each branch runs only when the test takes it.
    read = compile_program(
        [], [expr.read('x if flag else 1 / p.zero')], constants={'p.zero': 0}, units=REGISTRY
    )
    assert read({'x': 2.5, 'flag': True}, REGISTRY) == (2.5,)
    with pytest.raises(ZeroDivisionError):
        read({'x': 2.5, 'flag': False}, REGISTRY)


def test_a_known_term_of_and_or_or_decides_only_when_no_term_that_runs_comes_first():
    constants = {'p.no': False, 'p.yes': True}
    for source, env, expected in [
        ('p.no and missing.name > 0', {}, False),
        ('p.yes or missing.name > 0', {}, True),
        ('p.yes and x > 0', {'x': 1.0}, True),
        ('p.no or x > 0', {'x': -1.0}, False),
    ]:
        program = compile_program([], [expr.read(source)], constants=constants, units=REGISTRY)
        assert program(env, REGISTRY) == (expected,), source
    # A term that comes first still runs, and a name that it reads and that no one gives fails.
    program = compile_program(
        [], [expr.read('missing.name > 0 and p.no')], constants=constants, units=REGISTRY
    )
    with pytest.raises(ExpressionError):
        program({}, REGISTRY)


@pytest.mark.parametrize(
    'source',
    [
        '1 / p.zero',
        'ln(p.zero)',
        'sqrt(-p.one)',
        'exp(p.big)',
        'p.huge * 10',
        'p.one ** 2000',
        "q(p.huge, 'days')",
        'clip(p.one, 2, 1)',
        'missing.name',
    ],
)
def test_a_known_part_that_fails_stays_code_and_fails_when_a_run_reaches_it(source):
    constants = {'p.zero': 0, 'p.one': 1.0, 'p.big': 1000.0, 'p.huge': 1e308}
    with pytest.raises(FAILURES):
        evaluate(expr.read(source), constants, REGISTRY)
    # Making the program does not fail: only the run that reaches the part does.
    program = compile_program(
        [], [expr.read(f'0 if x > 0 else {source}')], constants=constants, units=REGISTRY
    )
    assert program({'x': 1.0}, REGISTRY) == (0,)
    with pytest.raises(FAILURES):
        program({'x': -1.0}, REGISTRY)


def test_the_sign_of_zero_and_the_type_of_each_value_are_kept():
    constants = {'p.zero': 0.0, 'p.one': 1, 'p.yes': True, 'p.half': 0.5}
    sources = [
        '-p.zero',
        'p.zero * -1',
        '-(p.one - p.one)',
        'p.one + p.yes',
        'p.one / 2',
        'min(p.one, p.zero)',
        'max(p.yes, p.zero)',
        'abs(-p.one)',
        'p.one > 0',
        'not p.zero',
        '+p.half',
        'p.half ** 2',
        "q(p.one, 'days')",
        'clip(p.half, p.zero, p.one)',
        "'on' if p.yes else 'off'",
    ]
    for source in sources:
        node = expr.read(source)
        (got,) = compile_program([], [node], constants=constants, units=REGISTRY)({}, REGISTRY)
        assert outcome(lambda: got) == outcome(lambda: evaluate(node, constants, REGISTRY)), source
    (negative,) = compile_program([], [expr.read('-p.zero')], constants=constants, units=REGISTRY)(
        {}, REGISTRY
    )
    assert math.copysign(1.0, negative) == -1.0


def test_a_reader_gives_the_code_of_each_name_and_its_values_are_checked():
    def read(name):
        places = {'t': 'T', 'x': 'Y[0]', 'm': "S['m']", 'p.v': "V['p.v']"}
        return (places[name], False) if name in places else (f'_missing({name!r})', True)

    program = compile_program(
        [('c.r', expr.read('x * t'))],
        [expr.read("c.r + p.v if m == 'on' else -c.r")],
        units=REGISTRY,
        read=read,
        arguments=('Y', 'T', 'S', 'V', 'R'),
        write=False,
    )
    assert program([2.0], 3.0, {'m': 'on'}, {'p.v': 0.5}, REGISTRY) == (6.5,)
    assert program([2.0], 3.0, {'m': 'off'}, {'p.v': 0.5}, REGISTRY) == (-6.0,)
    # A value that a reader gives passes the same check as a value of an environment.
    with pytest.raises(ExpressionError):
        program([math.inf], 3.0, {'m': 'on'}, {'p.v': 0.5}, REGISTRY)


# ---- the program against each evaluation, on random expressions ---------------------------------

PARAMETERS = ('p.a', 'p.b', 'p.c', 'p.zero', 'p.flag')
STATES = ('x.s', 'x.t', 'x.u')
NUMBERS = (0, 1, 2, 3, 0.5, -1, 10, 1e-300, 1e300, 1e308, 7.25, 1000, 0.0, -0.0, 4.5)


def leaf(rng):
    r = rng.random()
    if r < 0.3:
        return rng.choice(PARAMETERS)
    if r < 0.55:
        return rng.choice(STATES)
    if r < 0.6:
        return 't'
    if r < 0.65:
        return 'c.one'  # the formula that the program assigns first
    if r < 0.68:
        return 'nowhere.name'
    return repr(rng.choice(NUMBERS))


def expression(rng, depth):
    if depth == 0 or rng.random() < 0.2:
        return leaf(rng)
    k = rng.randrange(20)
    a, b, c = expression(rng, depth - 1), expression(rng, depth - 1), expression(rng, depth - 1)
    if k < 4:
        return f'({a} {rng.choice("+-*/")} {b})'
    if k == 4:
        return f'({a} ** {rng.choice(["2", "0.5", "-1", "3", "2000", b])})'
    if k == 5:
        return f'-({a})'
    if k == 6:
        return f'+({a})'
    if k == 7:
        return f'{rng.choice(["exp", "ln", "sqrt", "abs", "expm1", "log1p", "erf"])}({a})'
    if k == 8:
        return f'{rng.choice(["min", "max"])}({a}, {b})'
    if k == 9:
        return f'clip({a}, {b}, {c})'
    if k == 10:
        return f"q({a}, '{rng.choice(['h', 'days'])}')"
    test = rng.choice(
        [
            f'{a} > {b}',
            f'{a} <= {b} < {c}',
            f'{a} == {b}',
            f'{a} != 0',
            f"m.mode == '{rng.choice(['open', 'shut'])}'",
            'p.flag',
            f'not ({a} > 0)',
            f'{a} > 0 and {b} > 0',
            f'{a} > 0 or {b} < 0',
            f'{a} > 0 and {b} > 0 and {c} != 1',
        ]
    )
    if k < 16:
        return f'({a} if {test} else {b})'
    if k < 18:
        return f'({test})'
    return f'(1 if ({test}) else 0)'


def direct_read(name):
    """Where a program with direct reads, `program(Y, T, S, V, R)`, finds a name that it reads."""
    if name == 't':
        return 'T', False
    if name == 'm.mode':
        return "S['m.mode']", False
    if name in STATES:
        return f'Y[{STATES.index(name)}]', False
    if name in PARAMETERS:
        return f'V[{name!r}]', False
    return f'_missing({name!r})', True


# A part that is not finite for x = 1e200 (its product leaves the range of a float, or it is the
# difference of two such products), inside each reader that could hide it: the value of the whole
# is then a finite number, or a yes/no.
BIG = ('x.s * x.s', '-(x.s * x.s)', 'x.s * x.s - x.s * x.s', 'abs(x.s * x.s)', 'x.s * x.s + 1')
HIDERS = (
    '1 / ({})',
    'min({}, 5)',
    'max({}, 5)',
    'clip({}, 0, 5)',
    'clip(1, 0, {})',
    'exp(-abs({}))',
    'expm1(-abs({}))',
    'erf({})',
    '({}) ** 0',
    '(1 if {} > 5 else 0)',
    '(1 if 5 < {} else 0)',
    '(2 if not ({} > 5) else 3)',
    '({} > 0 and x.s > 0)',
    '({} > 0 or x.s > 0)',
    # A number that is read as a yes/no: a value that is not finite reads as yes.
    '(1 if {} else 0)',
    '(1 if ({} and x.s > 0) else 0)',
    '(1 if ({} or x.s < -5) else 0)',
    '(7 if ({} if x.s > 0 else 1) < 5 else 8)',
    "q(1, 'h') / q({}, 'h')",
    '{}',
)


@pytest.mark.parametrize('big', BIG)
@pytest.mark.parametrize('hider', HIDERS)
def test_a_lean_program_fails_where_a_reader_could_hide_a_value_that_is_not_finite(big, hider):
    """The evaluation fails at the part that is not finite. The lean program has no check at that
    part: it fails at the reader, at the assignment or at the output. Where the evaluation has a
    value (a small x; a branch that does not read the part), the two give the same value. The part
    is in an output, and also in a formula that the output reads."""

    def evaluated(assignments, output, x):
        env = {'x.s': x}
        for name, formula in assignments:
            env[name] = evaluate(formula, env, REGISTRY)
        return evaluate(output, env, REGISTRY)

    cases = (
        ([], expr.read(hider.format(big))),
        ([('c.one', expr.read(big))], expr.read(hider.format('c.one'))),
    )
    for assignments, output in cases:
        lean = compile_program(
            assignments,
            [output],
            units=REGISTRY,
            read=direct_read,
            arguments=('Y', 'T', 'S', 'V', 'R'),
            write=False,
            lean=True,
        )
        for x in (1e200, -1e200, 2.0):
            want = outcome(lambda x=x, case=(assignments, output): evaluated(*case, x))
            if x == 1e200:
                assert want == ('fails',), output
            got = outcome(lambda x=x, lean=lean: lean([x, 0.0, 0.0], 0.0, {}, {}, REGISTRY)[0])
            assert got == want, (output, x)


def count_checks(program):
    """The number of checks of a value in the code of a program: each check calls `_finite` when its
    value fails."""
    return program.__code__.co_names.count('_finite') and sum(
        1 for instruction in dis.get_instructions(program) if instruction.argval == '_finite'
    )


def test_a_program_gives_what_each_evaluation_gives_on_random_expressions():
    rng = random.Random(20261025)
    seen = {'fails': 0, 'values': 0}
    checks = {'every': 0, 'lean': 0}
    for _ in range(1500):
        inputs = {name: rng.choice((*NUMBERS, math.inf, math.nan)) for name in PARAMETERS}
        inputs['p.zero'], inputs['p.flag'] = 0, rng.choice([0, 1])
        # The program knows some inputs and reads the others, as a run reads what the state hides.
        constants = {name: value for name, value in inputs.items() if rng.random() < 0.7}
        states = {name: rng.choice([0.0, 1.0, -2.0, 3.5, 1e-310, 2.0]) for name in STATES}
        env = {**inputs, **states, 'm.mode': rng.choice(['open', 'shut']), 't': rng.choice([0.0, 5.0])}
        formula, source = expr.read(expression(rng, 2)), expr.read(expression(rng, rng.randrange(1, 5)))
        reference = dict(env)
        first = outcome(lambda: evaluate(formula, reference, REGISTRY))
        if first == ('fails',):
            continue  # the interpreter reports a formula that fails before any program runs
        reference['c.one'] = evaluate(formula, reference, REGISTRY)
        want = outcome(lambda: evaluate(source, reference, REGISTRY))
        seen['fails' if want == ('fails',) else 'values'] += 1

        program = compile_program([('c.one', formula)], [source], constants=constants, units=REGISTRY)
        written = dict(env)
        assert outcome(lambda: program(written, REGISTRY)[0]) == want, (formula, source, constants)
        assert outcome(lambda: written['c.one']) == first, (formula, constants)

        direct = compile_program(
            [('c.one', formula)],
            [source],
            constants=constants,
            units=REGISTRY,
            read=direct_read,
            arguments=('Y', 'T', 'S', 'V', 'R'),
            write=False,
        )
        y = [states[name] for name in STATES]
        got = outcome(lambda: direct(y, env['t'], {'m.mode': env['m.mode']}, inputs, REGISTRY)[0])
        assert got == want, (formula, source, constants)

        # The program that checks a value only where it could be hidden (`lean`): the same value, and
        # a failure where an evaluation fails.
        lean = compile_program(
            [('c.one', formula)],
            [source],
            constants=constants,
            units=REGISTRY,
            read=direct_read,
            arguments=('Y', 'T', 'S', 'V', 'R'),
            write=False,
            lean=True,
        )
        got = outcome(lambda: lean(y, env['t'], {'m.mode': env['m.mode']}, inputs, REGISTRY)[0])
        assert got == want, (formula, source, constants)
        checks['every'] += count_checks(direct)
        checks['lean'] += count_checks(lean)
    # Both kinds of result are common enough to check.
    assert min(seen.values()) > 200, seen
    # The lean programs have far fewer checks, and still some: this test is of a program that leaves
    # checks out.
    assert 0 < checks['lean'] < 0.7 * checks['every'], checks
