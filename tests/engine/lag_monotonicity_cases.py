"""A granted reporting lag must agree with the direction of the physical readings."""

from dataclasses import replace
from hashlib import sha256
from random import Random
from traceback import format_exc

from napkin.engine import read, run
from napkin.engine.report import Lag, report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text
from napkin.program.proofs import never_falls

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
FAMILIES = ('minimum', 'cutoff', 'overlap')


def lag_model(seed, family):
    rng = Random(seed)
    low, step, delay = (2, 4, 1) if seed == 0 else (rng.randint(1, 14), rng.randint(1, 8), rng.randint(1, 4))
    high = low + 2 * step
    if family == 'minimum':
        source = f"""scenario "Round trip"
    horizon {2 * delay + 1} h
Bin:
    stock: L = {low} L
    receipts: L = 0 L
first: Bin
    stock = {high} L
second: Bin
yard:
    floor = formula(min(Bin.instances.stock))
    ceiling = formula(max(Bin.instances.stock))
    total = formula(sum(Bin.instances.stock))
    least_receipts = formula(min(Bin.instances.receipts))
    exchange = event():
        after {delay} h:
            move {step} L from first.stock to second.stock
            second.receipts += {step} L
        after {delay} h:
            move {step} L from second.stock to first.stock
            first.receipts += {step} L
yard.exchange.start()
"""
        times = [0, delay, 2 * delay]
        expected = {
            'yard.floor': (low, low + step, low),
            'yard.ceiling': (high, high - step, high),
            'yard.total': (high + low,) * 3,
            'yard.least_receipts': (0, 0, step),
        }
        claims = {'yard.floor': False, 'yard.ceiling': False, 'yard.total': True, 'yard.least_receipts': True}
    elif family == 'cutoff':
        cutoff = 2 * delay
        source = f"""scenario "Fixed cutoff"
    horizon {3 * delay + 1} h
yard:
    picked = formula(this.batch.occurrences.at({cutoff} h).amount)
    count_batches = formula(count(this.batch.occurrences))
    batch = event(amount: L):
        after {4 * delay} h
    launch = event():
        after {delay} h:
            this.batch.start({low} L)
        after {2 * delay} h:
            this.batch.start({high + step} L)
yard.batch.start({high} L)
yard.launch.start()
"""
        times = [0, delay, 3 * delay]
        expected = {'yard.picked': (high, low, low), 'yard.count_batches': (1, 2, 3)}
        claims = {'yard.picked': False, 'yard.count_batches': True}
    elif family == 'overlap':
        source = f"""scenario "Overlapping stocks"
    horizon {3 * delay + 1} h
yard:
    batch = event(initial: L):
        stock: L = initial
        after {4 * delay + 1} h
    launch = event():
        after {delay} h:
            this.batch.start({low} L)
        after {delay} h:
            this.transfer.start()
    transfer = event():
        first = this.batch.occurrences.at(0 h)
        second = this.batch.occurrences.at({delay} h)
        after {delay} h:
            move {step} L from first.stock to second.stock
yard.batch.start({high} L)
yard.launch.start()
"""
        times = [delay, 2 * delay, 3 * delay]
        expected = {
            'yard.batch#0.stock': (high, high, high - step),
            'yard.batch#1.stock': (low, low, low + step),
        }
        claims = {'yard.batch#0.stock': False}
    else:
        raise ValueError(f'unknown family {family}')
    return source, times, expected, claims


def check_lag_monotonicity(seed, families=FAMILIES):
    errors = {}
    for family in families:
        source, times, expected, claims = lag_model(seed, family)
        differences = {}
        try:
            model = compile_text(source, UNITS)
            cfg, program = model.configuration, model.program
            if seed % 2:
                cfg = replace(
                    cfg,
                    request=replace(
                        cfg.request, everything=False, keys=tuple(key_of(program, p) for p in expected)
                    ),
                )
            record = run(program, cfg)
            if record.failure is not None:
                differences['run'] = repr(record.failure)
            for row in read(record, program, list(expected), times):
                if row.values != expected[row.path]:
                    differences[row.path + '/record'] = (expected[row.path], row.values)
            for path, holds in claims.items():
                try:
                    proof = never_falls(program, cfg, key_of(program, path))
                    if proof.holds != holds:
                        differences[path + '/never_falls'] = (holds, proof.holds, proof.reason)
                    shown = report(
                        record, program, cfg, [path], times, {path: Lag(0, 0.5)}, table=model.table
                    ).values[0]
                    granted = shown.lag is not None
                    if granted != holds:
                        differences[path + '/lag'] = (holds, granted, shown.note)
                    if granted and any(a > b for a, b in zip(expected[path], expected[path][1:])):
                        differences[path + '/granted_on_fall'] = tuple(
                            zip(times, expected[path], strict=True)
                        )
                except Exception:
                    differences[path + '/exception'] = format_exc()
        except Exception:
            differences['exception'] = format_exc()
        if differences:
            errors[family] = {
                'source': source,
                'sha256': sha256(source.encode()).hexdigest(),
                'differences': differences,
            }
    assert not errors, (seed, errors)
