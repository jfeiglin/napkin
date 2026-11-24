"""Moving clocks and keyed stocks swap raw order, either within the band or on a genuine crossing."""

from decimal import Decimal
from fractions import Fraction
from math import isclose
from random import Random

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.comparison_bands import band_samples
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def _settings(seed):
    rng = Random(seed)
    base = rng.randrange(4, 12)
    slope = Decimal(rng.randrange(1, 9)) / 4
    cross = Decimal(rng.randrange(2, 7)) / 8
    prices = rng.sample(range(1, 10), 2)
    return base, slope, cross, prices


def selection_drift(base, leaves):
    if leaves:
        return Decimal('0.5')
    (fraction,) = band_samples(Configuration(Request(1)), 1, multiples=(0.5,))
    return base * Decimal(str(fraction))


def switch_selection_source(seed, mode, leaves):
    base, slope, cross, (older, later) = _settings(seed)
    # The older key overtakes the later one at exactly cross hours. The small
    # drift is half the band at the initial base, and acts for less than an hour.
    drift = selection_drift(base, leaves)
    trajectory = '    rank = formula(this.origin + this.slope * t)'
    if mode == 'rank':
        trajectory = """    rank: L = this.origin
    flow measure: SOURCE -> this.rank
        request = this.slope
        capacity = this.slope"""
    source = f"""scenario "Two moving keys"
    horizon 1 h
Meter:
    input origin = {base} L
    input slope = {slope} L/h
    input price = {later} L/h
{trajectory}
older: Meter
    origin = {base - drift * cross} L
    slope = {slope + drift} L/h
    price = {older} L/h
later: Meter
yard:
"""
    if mode == 'trigger':
        return (
            source
            + """    counts = 0
    fired: h = -1 h
    alarm = event():
        when older.rank >= later.rank:
            this.alarm.start()
            reset when false
        after 0 h:
            this.counts += 1
            this.fired = t
"""
        )
    if mode == 'clock':
        request = 'older.price if older.rank > later.rank else later.price'
    elif mode == 'rank':
        request = 'Meter.instances.by(rank).at(30 L).price'
    else:
        raise ValueError(mode)
    return (
        source
        + f"""    total: L = 0 L
    flow meter: SOURCE -> this.total
        request = formula({request})
"""
    )


def _expected(seed, mode, leaves):
    _, _, at, (older, later) = _settings(seed)
    crossing = Fraction(at)
    times = (crossing / 2, (1 + crossing) / 2, Fraction(1))
    if mode == 'trigger':
        fired = crossing if leaves else 0
        return times, {
            'counts': tuple(int(t >= fired) for t in times),
            'fired': tuple(fired if t >= fired else -1 for t in times),
        }
    return times, {
        'total': tuple(later * t + (older - later) * max(t - crossing, 0) * leaves for t in times),
        'meter.actual_rate': tuple(older if leaves and t > crossing else later for t in times),
    }


def _read(model, reader, keys, times):
    if reader == 'reference':
        record, failure = run_of(model.program, model.configuration)
        if failure is None:
            return [tuple(value_at(record, model.program, key, t) for t in times) for key in keys]
    else:
        record = run(model.program, model.configuration)
        failure = record.failure
        if failure is None:
            return [row.values for row in read(record, model.program, keys, list(map(float, times)))]
    raise ValueError(str(failure))


def check_switch_selection(seed):
    differences = {}
    for mode in ('clock', 'trigger', 'rank'):
        for leaves in (False, True):
            name = f'{mode}.{"crossing" if leaves else "tie"}'
            model = compile_text(switch_selection_source(seed, mode, leaves), UNITS)
            times, expected = _expected(seed, mode, leaves)
            keys = [Key('yard', tuple(path.split('.'))) for path in expected]
            for reader in ('reference', 'engine'):
                label = f'{name}.{reader}'
                try:
                    actual = _read(model, reader, keys, times)
                except Exception as error:
                    differences[label] = {
                        'actual': f'{type(error).__name__}: {error}',
                        'expected': 'complete at 1 h',
                    }
                    continue
                for (path, wanted), got in zip(expected.items(), actual, strict=True):
                    tolerance = 0 if path in ('counts', 'meter.actual_rate') else 1e-7
                    if any(
                        not isclose(a, b, abs_tol=tolerance, rel_tol=0)
                        for a, b in zip(got, wanted, strict=True)
                    ):
                        differences[f'{label}.{path}'] = {
                            'times': list(map(float, times)),
                            'actual': list(map(float, got)),
                            'expected': list(map(float, wanted)),
                        }
    assert not differences, (seed, differences)
