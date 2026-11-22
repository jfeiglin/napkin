"""Physical objectives, flow rates and diagnostics of small, ranked mixed-column solvers."""

from decimal import Decimal
from fractions import Fraction
from math import isclose
from random import Random

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.errors import Infeasible
from tests.reference.from_program import run_of, scale_at, value_at

UNITS = {
    'h': {'time': 1},
    'L': {'volume': 1},
    'mL': ({'volume': 1}, Fraction(1, 1000)),
    'kL': ({'volume': 1}, 1000),
}
PER_L = {'L': Decimal(1), 'mL': Decimal(1000), 'kL': Decimal('0.001')}
SHAPES = ('box', 'ranked', 'unbounded-feed', 'unbounded-spare', 'infeasible', 'fair', 'nonunique')
KEYS = {
    'f': Key('tank', ('inlet', 'actual_rate')),
    'g': Key('tank', ('second', 'actual_rate')),
    's': Key('planner', ('dispatch', 'spare')),
    'v': Key('planner', ('dispatch', 'other')),
}


def flow_source(size, shape, unit, scale):
    """The stored limit and each declaration use equivalent physical quantities in the chosen unit."""
    rate = unit + '/h'

    def amount(number):
        return f'{Decimal(number) * PER_L[unit]:f} {rate}'

    primary = 'maximize(feed.actual_rate + spare)'
    extra = []
    constraints = []
    objectives = [primary, 'minimize(spare)']
    bound = 'cap'
    if shape == 'ranked':
        # Rank 1 fixes the total to cap. Rank 2 picks the largest admissible spare, cap / 2.
        bound = '0.5 * cap'
        constraints = ['feed.actual_rate + spare <= cap']
        objectives = [primary, 'maximize(spare)']
    elif shape == 'unbounded-feed':
        objectives = [primary]
    elif shape == 'unbounded-spare':
        bound = ''
        objectives = ['maximize(feed.actual_rate)', primary]
    elif shape == 'infeasible':
        constraints = ['feed.actual_rate + spare <= cap', 'feed.actual_rate + spare >= 2 * cap']
    elif shape == 'fair':
        # Once spare reaches cap, share cap in the ratio of the flow requests, two to three.
        constraints = ['feed.actual_rate + second.actual_rate <= cap']
        objectives = ['maximize(spare)']
    elif shape == 'nonunique':
        # Only the sum of the two nonflows is determined at the optimum.
        extra = [f'other: {rate} in [0 {rate}, cap]']
        constraints = ['spare + other == cap']
        objectives = ['maximize(feed.actual_rate + spare + other)']
    setup = [
        'tank:',
        '    water: L = 0 L',
        f'    limit: {rate} = {amount(size)}',
        '    flow inlet: SOURCE -> this.water',
    ]
    if shape != 'unbounded-feed':
        setup.append('        capacity = formula(this.limit)')
    inputs = ['feed = tank.inlet', 'cap = tank.limit']
    solving = ['feed.actual_rate']
    if shape == 'fair':
        setup += [
            '        request = formula(2 * this.limit)',
            '    flow second: SOURCE -> this.water',
            '        capacity = formula(this.limit)',
            '        request = formula(3 * this.limit)',
        ]
        inputs += ['second = tank.second']
        solving += ['second.actual_rate']
    suffix = '' if scale is None else f' scale {amount(scale)}'
    solving += [f'spare: {rate} in [0 {rate}, {bound}]{suffix}', *extra]
    lines = [
        'scenario "Mixed solver scales"',
        '    horizon 0 h',
        *setup,
        'planner:',
        '    dispatch = solver:',
    ]
    for section, entries in (
        ('inputs', inputs),
        ('solve_for', solving),
        ('constraints', constraints),
        ('objective', objectives),
    ):
        if entries:
            lines += [f'        {section}:', *('            ' + entry for entry in entries)]
    return '\n'.join(lines) + '\n'


def expected(size, shape):
    """The value at each authored rank, and each determined flow, in L/h."""
    if shape.startswith('unbounded'):
        return 'unbounded', {}
    if shape == 'infeasible':
        return 'infeasible', {}
    if shape == 'box':
        return 'optimal', {'f': size, 'f+s': 2 * size, 's': size}
    if shape == 'ranked':
        return 'optimal', {'f': Fraction(size, 2), 'f+s': size, 's': Fraction(size, 2)}
    if shape == 'fair':
        return 'optimal', {'s': size, 'f': Fraction(2 * size, 5), 'g': Fraction(3 * size, 5)}
    return 'optimal', {'f': size, 's+v': size, 'f+s+v': 2 * size}


def _observation(compiled, shape, names, reference):
    program, config = compiled.program, compiled.configuration
    if reference:
        oracle, failure = run_of(program, config)
        if failure is not None:
            if isinstance(failure, Infeasible):
                return 'infeasible', str(failure)
            return ('unbounded' if 'unbounded' in str(failure) else 'stopped'), str(failure)
        readings = [value_at(oracle, program, KEYS[name], Fraction(0)) for name in names]
    else:
        record = run(program, config)
        if record.failure is not None:
            detail = record.failure.detail('message')
            if record.failure.t == 0 and 'planner.dispatch' in detail:
                rank = 2 if shape == 'unbounded-spare' else 1
                if f'unbounded in objective {rank}' in detail:
                    return 'unbounded', detail
                if 'infeasible in the hard constraints' in detail:
                    return 'infeasible', detail
            return 'stopped', detail
        readings = [item.values[0] for item in read(record, program, [KEYS[name] for name in names], [0])]
    physical = {
        name: value * scale_at(program, KEYS[name]) for name, value in zip(names, readings, strict=True)
    }
    return 'optimal', physical


def _check_one(source, size, shape):
    compiled = compile_text(source, UNITS)
    status, wanted = expected(size, shape)
    names = tuple(dict.fromkeys(name for label in wanted for name in label.split('+'))) or ('f', 's')
    differences = []
    for reader, reference in (('engine', False), ('reference', True)):
        try:
            actual, result = _observation(compiled, shape, names, reference)
        except Exception as error:
            differences.append(f'{reader} raised {type(error).__name__}: {error}')
            continue
        if actual != status:
            differences.append(f'{reader} expected {status}, got {actual}: {result}')
        elif actual == 'optimal':
            for label, optimum in wanted.items():
                observed = sum(result[name] for name in label.split('+'))
                matches = (
                    observed == optimum
                    if reference
                    else isclose(observed, optimum, rel_tol=1e-9, abs_tol=1e-8)
                )
                if not matches:
                    differences.append(f'{reader} {label} expected {optimum}, got {observed} L/h')
            if shape == 'nonunique' and min(result['s'], result['v']) < -1e-8:
                differences.append(f'{reader} expected both nonflows nonnegative, got {result}')
    return differences


def spellings(seed):
    rng = Random(seed)
    size = 10**9 if seed == 0 else rng.randrange(1, 10) * 10 ** rng.choice((2, 5, 8, 9))
    shapes = SHAPES if seed == 0 else (SHAPES[seed % len(SHAPES)],)
    scale = rng.choice(('1', '0.000000001', '1000000000000'))
    other = rng.choice(('mL', 'kL'))
    forms = [('L', None), ('L', scale), (other, scale)]
    if seed == 0:
        forms = [
            ('L', None),
            ('L', '1'),
            ('L', '0.000000001'),
            ('L', '1000000000000'),
            ('mL', '1'),
            ('kL', '0.000000001'),
        ]
    for shape in shapes:
        for unit, mark in forms:
            yield size, shape, unit, mark


def check_solver_flow_scale(seed):
    failures = []
    for size, shape, unit, mark in spellings(seed):
        source = flow_source(size, shape, unit, mark)
        try:
            differences = _check_one(source, size, shape)
        except Exception as error:
            differences = [f'{type(error).__name__}: {error}']
        if differences:
            label = f'{shape}, {unit}/h, scale {mark} L/h'
            failures.append(f'{label}\n' + '\n'.join(differences) + '\n' + source)
    assert not failures, f'mixed solver scales seed {seed}\n' + '\n'.join(failures)
