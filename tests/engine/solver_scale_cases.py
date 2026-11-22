"""Declared unknowns measured in volume. Objective ranks and physical answers have exact solutions."""

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from math import isclose, ulp
from random import Random

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, values_at

UNITS = {
    'h': {'time': 1},
    'L': {'volume': 1},
    'mL': ({'volume': 1}, Fraction(1, 1000)),
}


@dataclass(frozen=True)
class Case:
    name: str
    source: str
    answers: tuple
    unbounded: int
    objective: str


def _case(seed, name, x_max, y_max, scale, *, small_unit=False, reverse=False):
    unit = 'mL' if small_unit else 'L'
    x, y = ('spare', 'stock') if reverse else ('x', 'y')

    def volume(value):
        return f'{value * (1000 if small_unit else 1)} {unit}'

    ranked = name.startswith('ranked')
    open_y = 'unbounded' in name
    x_row = f'{x}: {unit} in [0 {unit}, {volume(x_max)}]'
    y_row = f'{y}: {unit} in [0 {unit}, {"" if open_y else volume(y_max)}]'
    if scale is not None:
        y_row += f' scale {volume(scale)}'
    rows = [y_row, x_row] if reverse else [x_row, y_row]
    lines = [
        'scenario "Stock decisions"',
        '    horizon 1 h',
        'yard:',
        '    choose = solver:',
        '        solve_for:',
        *(f'            {row}' for row in rows),
    ]
    total = f'{x} + {y}'
    if ranked and not open_y:
        # The primary-optimal face has x+y=budget. Either endpoint that the second
        # rank selects can be worked out from the corresponding box bound.
        budget = max(x_max, y_max) + min(x_max, y_max) // 2
        lines += ['        constraints:', f'            {total} <= {volume(budget)}']
        maximum_y = not seed % 2
        expected_y = y_max if maximum_y else budget - x_max
        expected_x = budget - expected_y
        objectives = [('maximize', total), ('maximize' if maximum_y else 'minimize', y)]
        answers = expected_x, expected_y, budget, expected_y
    elif ranked:
        objectives = [('maximize', x), ('maximize', y)]
        answers = ()
    else:
        objectives = [('maximize', total)]
        answers = (x_max, y_max, x_max + y_max) if not open_y else ()
    lines += ['        objective:', *(f'            {op}({expr})' for op, expr in objectives)]
    # Report every unknown and written objective explicitly in litres for both spellings.
    for title, expression in [
        ('chosen_x', x),
        ('chosen_y', y),
        *[(f'rank{i}', e) for i, (_, e) in enumerate(objectives, 1)],
    ]:
        physical = ' + '.join('yard.choose.' + part for part in expression.split(' + '))
        lines.append(f'{title}: formula(L) = formula({physical})')
    rank = len(objectives) if open_y else 0
    return Case(name, '\n'.join(lines) + '\n', answers, rank, objectives[-1][1])


def cases(seed):
    rng = Random(seed)
    if seed == 0:
        x_max, y_max, scale = 10**9, 10**9, 1
    else:
        magnitude = 10 ** rng.choice((0, 1, 3, 6, 8, 9, 10))
        x_max = magnitude * rng.randint(2, 9)
        y_max = magnitude * rng.randint(2, 9)
        scale = rng.choice((1, 2, 4, max(1, y_max // 2)))
    order = bool(seed % 2)
    small = bool(seed % 3)
    for domain in ('bounded', 'unbounded'):
        for label, declared in (('implicit', None), ('explicit', scale)):
            yield _case(seed, f'{domain}.{label}', x_max, y_max, declared, small_unit=small, reverse=order)
    yield _case(seed, 'bounded.rewritten', x_max, y_max, scale, small_unit=not small, reverse=not order)
    yield _case(seed, 'ranked.bounded', x_max, y_max, scale, small_unit=not small, reverse=order)
    yield _case(seed, 'ranked.unbounded', x_max, y_max, scale, small_unit=small, reverse=not order)


def _probe(case, program, configuration, reference):
    nkeys = 2 + case.unbounded if case.unbounded else len(case.answers)
    keys = [Key('', (name,)) for name in ('chosen_x', 'chosen_y', 'rank1', 'rank2')[:nkeys]]
    if reference:
        try:
            result, failure = run_of(program, configuration)
        except NotCovered:
            return  # The exact physical optimum or unbounded rank is supplied independently above.
        message = str(failure)
        at = result.view.t if result is not None else 0
    else:
        result = run(program, configuration)
        failure = result.failure
        message = failure.detail('message') if failure else ''
        at = failure.t if failure else None
    if failure:
        if not case.unbounded:
            return {'expected': case.answers, 'failure': message}
        rank = case.objective if reference else f'objective {case.unbounded}'
        if at != 0 or 'unbounded' not in message or 'yard.choose' not in message or rank not in message:
            return {'expected_unbounded_rank': case.unbounded, 'at': str(at), 'observed': message}
        return
    if reference:
        readings = values_at(result, program, keys, [0])
        values = tuple(readings[key][0] for key in keys)
    else:
        values = tuple(row.values[0] for row in read(result, program, keys, [0]))
    if case.unbounded:
        return {'expected_unbounded_rank': case.unbounded, 'finite_answer': list(map(str, values))}
    if reference:
        valid = values == case.answers
    else:
        valid = all(
            isclose(value, answer, rel_tol=0, abs_tol=max(2e-9, 32 * ulp(answer)))
            for value, answer in zip(values, case.answers, strict=True)
        )
    if not valid:
        return {'expected': case.answers, 'observed': list(map(str, values))}


def check_solver_scale(seed):
    differences = {}
    for case in cases(seed):
        problems = {}
        try:
            found = compile_text(case.source, UNITS)
        except Exception as error:
            problems['compile'] = f'{type(error).__name__}: {error}'
        else:
            for label in ('engine', 'reference'):
                try:
                    outcome = _probe(case, found.program, found.configuration, label == 'reference')
                except Exception as error:
                    outcome = f'{type(error).__name__}: {error}'
                if outcome:
                    problems[label] = outcome
        if problems:
            differences[case.name] = {
                'source_sha256': sha256(case.source.encode()).hexdigest(),
                'source': case.source,
                **problems,
            }
    assert not differences, (seed, 'solver-scale', differences)
