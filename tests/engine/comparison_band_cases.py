"""A scaled formula retains its exact operands, and every authoring form uses the same interval."""

from decimal import Decimal
from fractions import Fraction
from random import Random
from traceback import format_exc

from napkin.engine.timeline import read, run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.build import Builder, after, event, param, q, start, value
from napkin.program.check import ProgramError
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, values_at

UNITS = {'h': {'time': 1}, 'min': ({'time': 1}, Fraction(1, 60)), 'L': {'volume': 1}}
CONFIG = Configuration(Request(0))
BAND = Decimal('0.000000001')
FAMILIES = ('gap', 'range')


def quantity(hours, unit):
    number = hours * (60 if unit == 'min' else 1)
    return f'{number:f} {unit}'


def gap_case(seed, placement):
    rng = Random(seed)
    floor = Decimal(1 if seed == 0 else rng.choice((1, 2, 4, 10)))
    if placement == 'inside':
        origin = Decimal(1 if seed == 0 else rng.randint(1, 20))
        delta = floor * BAND * (1 if seed == 0 else Decimal(rng.randint(1, 10)) / 10)
        other = floor * BAND * 2
    else:
        origin = Decimal(1_000_000_000 if seed == 0 else rng.randint(1, 15) * 1_000_000_000)
        delta = floor * BAND * (50 if seed == 0 else rng.randint(2, 50))
        other = Decimal(0)
    sign = -1 if seed % 2 else 1
    return origin, sign * delta, sign * other, floor


def gap_source(seed, placement, unit, section='full'):
    origin, delta, other, floor = gap_case(seed, placement)
    op = '<' if seed % 2 else '>'
    threshold = quantity(origin, unit)
    gate = f'this.a - {threshold} {op} {quantity(Decimal(0), unit)}'
    definition = f'formula({quantity(origin + delta, unit)}) scale {quantity(floor, unit)}'
    fields = f"""Box:
    a = {definition}
    guard = formula({gate})
    choice = 7 if {gate} else 1
"""
    flow = f"""    water: L = 0 L
    flow use: SOURCE -> this.water
        request = formula(7 L/h if {gate} else 1 L/h)
"""
    rows = f"""first: Box
second: Box
    a = formula({quantity(origin + other, unit)})
"""
    solver = f"""solver_host:
    a = {definition}
    guard = formula({gate})
    choice = 7 if {gate} else 1
    water: L = 0 L
    flow use: SOURCE -> this.water
        request = 10 L/h
    dispatch = solver:
        inputs:
            pipe = this.use
            amount = this.a
        solve_for:
            pipe.actual_rate
        constraints:
            pipe.actual_rate <= (7 L/h if {gate.replace('this.a', 'amount')} else 1 L/h)
        objective:
            maximize(pipe.actual_rate)
"""
    if section == 'fields':
        return fields + rows
    if section == 'rates':
        return fields + flow + rows
    if section == 'solver':
        return solver
    return fields + flow + rows + '\n' + solver


def gap_differences(seed):
    differences = {}
    for placement in ('inside', 'outside'):
        _, delta, other, floor = gap_case(seed, placement)
        groups = {'fields': {}, 'rates': {}, 'solver': {}}
        for host, amount in (('first', delta), ('second', other), ('solver_host', delta)):
            holds = abs(amount) > BAND * floor
            values = groups['solver' if host == 'solver_host' else 'fields']
            values[Key(host, ('guard',))] = holds
            values[Key(host, ('choice',))] = 7 if holds else 1
            rates = groups['solver' if host == 'solver_host' else 'rates']
            rates[Key(host, ('use', 'actual_rate'))] = 7 if holds else 1
        for unit in ('h', 'min'):
            for section, paths in groups.items():
                program = compile_text(gap_source(seed, placement, unit, section), UNITS).program
                oracle, error = run_of(program, CONFIG)
                assert error is None, (seed, placement, unit, section, 'reference', error)
                exact = values_at(oracle, program, paths, [0])
                for key, wanted in paths.items():
                    if exact[key][0] != wanted:
                        label = '.'.join((placement, unit, 'reference', key.owner, *key.steps))
                        differences[label] = exact[key][0], wanted
                try:
                    record = run(program, CONFIG)
                    if record.failure is not None:
                        raise AssertionError(record.failure.detail('message'))
                    result = read(record, program, list(paths), [0])
                except Exception as error:
                    differences[f'{placement}.{unit}.engine.{section}.run'] = (
                        {'error': type(error).__name__, 'message': str(error), 'traceback': format_exc()},
                        'completed',
                    )
                    continue
                for (key, wanted), series in zip(paths.items(), result, strict=True):
                    if series.values[0] != wanted:
                        label = '.'.join((placement, unit, 'engine', key.owner, *key.steps))
                        differences[label] = series.values[0], wanted
    return differences


def interval_limits(seed):
    rng = Random(seed)
    inside = Decimal('0.5') if seed == 0 else Decimal(rng.randint(1, 10)) / 10
    outside = 2 if seed == 0 else rng.randint(2, 12)
    return {'inside': BAND * inside, 'outside': BAND * outside}


def range_source(kind, lower, unit):
    lo, hi = quantity(lower, unit), quantity(Decimal(0), unit)
    if kind == 'field':
        return f'box:\n    duration: h = {hi} in [{lo}, {hi}]\n'
    return f'box:\n    take = event(duration: h in [{lo}, {hi}]):\n        after 1 h\nbox.take.start({hi})\n'


def range_program(kind, lower, unit):
    number = Fraction(lower) * (60 if unit == 'min' else 1)
    lo, hi = q(number, unit), q(0, unit)
    b = Builder(UNITS)
    if kind == 'field':
        b.entity('box', value('duration', 'h', hi, lower=lo, upper=hi))
    else:
        box = b.entity('box', event('take', param('duration', 'h', lower=lo, upper=hi), after(q(1, 'h'))))
        b.setup(start(box.take, hi))
    return b.finish()


def range_differences(seed):
    differences = {}
    for placement, lower in interval_limits(seed).items():
        should_accept = placement == 'inside'
        for unit in ('h', 'min'):
            for kind in ('field', 'parameter'):
                for author in ('text', 'builder'):
                    prefix = '.'.join((placement, unit, kind, author))
                    try:
                        if author == 'text':
                            program = compile_text(range_source(kind, lower, unit), UNITS).program
                        else:
                            program = range_program(kind, lower, unit)
                    except (LanguageError, ProgramError) as error:
                        if should_accept or 'range' not in str(error).lower():
                            differences[prefix + '.authoring'] = str(error), should_accept
                        continue
                    if not should_accept:
                        differences[prefix + '.authoring'] = True, should_accept
                    record = run(program, CONFIG)
                    accepted = record.failure is None
                    if accepted != should_accept or (
                        record.failure is not None and 'range' not in record.failure.detail('message').lower()
                    ):
                        outcome = True if accepted else record.failure.detail('message')
                        differences[prefix + '.runtime'] = outcome, should_accept
    return differences


def initializer_ranges(seed):
    """A stored branch result must fit exactly one of two singleton ranges at its first read."""
    differences = {}
    for placement in ('inside', 'outside'):
        origin, delta, _, floor = gap_case(seed, placement)
        target = 7 if abs(delta) > BAND * floor else 1
        op = '<' if seed % 2 else '>'
        for unit in ('h', 'min'):
            for end in (1, 7):
                source = (
                    f'box:\n    a = formula({quantity(origin + delta, unit)}) scale {quantity(floor, unit)}\n'
                    f'    choice = 7 if this.a - {quantity(origin, unit)} {op} 0 h else 1 in [{end}, {end}]\n'
                )
                try:
                    program = compile_text(source, UNITS).program
                except LanguageError as error:
                    accepted = False
                    detail = str(error)
                    assert 'range' in detail.lower(), (seed, placement, unit, detail)
                else:
                    record = run(program, CONFIG)
                    accepted = record.failure is None
                    detail = True if accepted else record.failure.detail('message')
                if accepted != (end == target):
                    differences[f'{placement}.{unit}.choice.in[{end},{end}]'] = detail, end == target
    return differences


def check_comparison_band(seed, family):
    if family == 'gap':
        differences = gap_differences(seed)
    elif family == 'range':
        differences = range_differences(seed) | initializer_ranges(seed)
    else:
        raise ValueError(f'unknown comparison-band family {family!r}')
    assert not differences, (seed, family, differences)
