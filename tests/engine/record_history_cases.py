"""Historical stock postings and elapsed clocks, compared to the authored sequence of commits."""

from dataclasses import dataclass, replace
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from random import Random

from napkin.engine import read, run
from napkin.engine.report import report
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.engine.stock_balance_cases import LOWER, _model, _move
from tests.reference.from_program import run_of, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}, 'pL': ({'volume': 1}, Fraction(1, 10**12))}


@dataclass(frozen=True)
class History:
    name: str
    source: str
    times: tuple
    fields: dict
    failure: bool = False


def postings(seed, returns):
    rng = Random(seed)
    multiple = 1 if not seed else rng.randrange(1, 300)
    initial = Decimal(4_000_000 * multiple)
    # Scale the small posting along with the principal to exercise different representable neighbors.
    step = Decimal('3e-10') * multiple
    fields = (
        ('stock', initial, f' in [0 L, {initial} L]'),
        ('supply', 4 * step, LOWER),
        ('receipt', 0, LOWER),
    )
    if returns:
        second = (_move(step, 'receipt', 'stock'),)
    else:
        second = (_move(step, 'supply', 'receipt'), _move(2 * step, 'supply', 'stock'))
    source = _model(fields, ((_move(step, 'stock', 'receipt'),), second))
    return History(
        'posting.return' if returns else 'posting.failed-cutoff',
        source,
        (0, 1, Fraction(3, 2), 2),
        {
            'stock': (initial, initial - step, initial - step, initial if returns else initial - step),
            'receipt': (0, step, step, 0 if returns else step),
            'supply': (4 * step,) * 4,
        },
        not returns,
    )


def elapsed(seed, mode):
    rng = Random(seed)
    first = Fraction(1) if not seed else Fraction(rng.randrange(3, 11), 8)
    interval = Fraction(1, 2) if not seed else Fraction(rng.randrange(1, 6), 8)
    tiny = Decimal('0.5') if not seed else Decimal(rng.randrange(1, 10)) / 10
    small = mode != 'visible'
    value = tiny if small else Decimal(rng.randrange(1, 20))
    unit = 'pL' if small else 'L'
    second = value if mode == 'repeat' else value * 2
    # All observation and change times are dyadic, so every public clock has one exact float.
    at1, at2, at3, at4 = (first + k * interval for k in range(4))
    source = f"""scenario "A record of elapsed time"
    horizon {float(at4)} h
yard:
    amount: L = 0 L
    first_seen: h = 0 h
    last_seen: h = 0 h
    age = formula(elapsed(this.amount))
    work = event():
        after {float(first)} h:
            this.amount = {value} {unit}
        after {float(interval)} h:
            this.first_seen = elapsed(this.amount)
        after {float(interval)} h:
            this.amount = {second} {unit}
        after {float(interval)} h:
            this.last_seen = elapsed(this.amount)
yard.work.start()
"""
    changed = mode != 'repeat'
    last_age = interval if changed else 3 * interval
    divisor = 10**12 if small else 1
    value_l, second_l = Fraction(value) / divisor, Fraction(second) / divisor
    return History(
        f'elapsed.{mode}',
        source,
        (0, at1, at2, at3, at4),
        {
            'amount': (0, value_l, value_l, second_l, second_l),
            'age': (0, 0, interval, 0 if changed else 2 * interval, last_age),
            'first_seen': (0, 0, interval, interval, interval),
            'last_seen': (0, 0, 0, 0, last_age),
        },
    )


def same_time(seed, separate):
    rng = Random(seed)
    first = Fraction(1) if not seed else Fraction(rng.randrange(3, 11), 8)
    interval = Fraction(1, 2) if not seed else Fraction(rng.randrange(1, 6), 8)
    amount = '0.5 pL' if seed % 2 else f'{1 if not seed else rng.randrange(1, 12)} L'
    later = first + interval
    second = 'this.restore.start()' if separate else 'this.amount = 0 L'
    restore = (
        """    restore = event():
        after 0 h:
            this.amount = 0 L
"""
        if separate
        else ''
    )
    source = f"""scenario "Round trip at one time"
    horizon {float(later)} h
yard:
    amount: L = 0 L
    seen: h = 0 h
    age = formula(elapsed(this.amount))
{restore}    work = event():
        after {float(first)} h:
            this.amount = {amount}
            {second}
        after {float(interval)} h:
            this.seen = elapsed(this.amount)
yard.work.start()
"""
    # The public amount is always zero. Only two separate commits restart elapsed.
    seen = interval if separate else later
    return History(
        'elapsed.two-commits' if separate else 'elapsed.one-commit',
        source,
        (0, first, later),
        {'amount': (0, 0, 0), 'age': (0, 0 if separate else first, seen), 'seen': (0, 0, seen)},
    )


def cases(seed):
    yield postings(seed, False)
    yield postings(seed, True)
    for mode in ('tiny', 'repeat', 'visible'):
        yield elapsed(seed, mode)
    yield same_time(seed, True)
    yield same_time(seed, False)


def _status(case, when, failure, differences, label):
    actual = 'refused' if 'nothing is moved' in failure else failure or 'finished'
    expected = 'refused' if case.failure else 'finished'
    if actual != expected or when != case.times[-1]:
        differences[label] = {'observed': (str(when), actual), 'expected': (str(case.times[-1]), expected)}


def _rows(case, order, rows, differences, label, exact=False):
    convert = Fraction if exact else float
    for name, row in zip(case.fields, rows, strict=True):
        wanted = tuple(convert(value) for value in case.fields[name][::order])
        if tuple(row) != wanted:
            differences[f'{label}.{name}'] = {
                'observed': list(map(str, row)),
                'expected': list(map(str, wanted)),
            }


def _check(case, program, config, keys, differences, label):
    paths = [f'yard.{name}' for name in case.fields]
    result = run(program, config)
    message = result.failure.detail('message') if result.failure else ''
    _status(case, result.end, message, differences, label + '.outcome')
    for order, direction in ((1, 'forward'), (-1, 'backward')):
        times = tuple(map(float, case.times[::order]))
        for access in ('read', 'report'):
            point = f'{label}.{direction}.{access}'
            try:
                rows = (
                    read(result, program, keys, times)
                    if access == 'read'
                    else report(result, program, config, paths, times).values
                )
                _rows(case, order, [row.values for row in rows], differences, point)
            except Exception as error:
                differences[point] = f'{type(error).__name__}: {error}'


def check_record_history(seed):
    failures = {}
    for case in cases(seed):
        differences = {}
        try:
            compiled = compile_text(case.source, UNITS)
        except Exception as error:
            differences['compile'] = f'{type(error).__name__}: {error}'
        else:
            program, config = compiled.program, compiled.configuration
            keys = tuple(Key('yard', (name,)) for name in case.fields)
            for label in ('full', 'selective'):
                recording = (
                    config
                    if label == 'full'
                    else replace(config, request=replace(config.request, everything=False, keys=keys))
                )
                try:
                    _check(case, program, recording, keys, differences, label)
                except Exception as error:
                    differences[label] = f'{type(error).__name__}: {error}'
            try:
                oracle, failure = run_of(program, config)
                _status(
                    case, oracle.view.t, str(failure) if failure else '', differences, 'reference.outcome'
                )
                for order, direction in ((1, 'forward'), (-1, 'backward')):
                    readings = values_at(oracle, program, keys, case.times[::order])
                    _rows(
                        case,
                        order,
                        [readings[key] for key in keys],
                        differences,
                        'reference.' + direction,
                        exact=True,
                    )
            except Exception as error:
                differences['reference'] = f'{type(error).__name__}: {error}'
        if differences:
            failures[case.name] = {
                'source_sha256': sha256(case.source.encode()).hexdigest(),
                'source': case.source,
                'times': list(map(str, case.times)),
                'expected': {name: list(map(str, values)) for name, values in case.fields.items()},
                **differences,
            }
    assert not failures, (seed, 'record-history', failures)
