"""Reread a saved physical record with its own numerical settings in a new interpreter."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory

from napkin import store
from napkin.engine import read
from napkin.engine.report import report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text
from napkin.program.artifact import load, value_of
from napkin.program.canonical import value_bytes

UNITS = {
    'h': {'time': 1},
    'L': {'volume': 1},
    'mL': ({'volume': 1}, Fraction(1, 1000)),
    'kL': ({'volume': 1}, 1000),
}
PER_L = {'L': Decimal(1), 'mL': Decimal(1000), 'kL': Decimal('0.001')}
PATHS = ['meter.near', 'meter.filtered', 'meter.outside', 'meter.equal', 'meter.seen']
ROOT = Path(__file__).resolve().parents[2]


def case_values(seed):
    if seed == 0:
        return 1, Decimal('0.0000004'), 1, 2, 9
    rng = Random(seed)
    bound = rng.randint(1, 20)
    gap = Decimal(rng.randint(2, 8)) * Decimal('1e-7') * bound
    return bound, gap, rng.randint(1, 6), rng.randint(1, 7), rng.randint(9, 40)


def record_source(seed, unit):
    bound, gap, start, old, new = case_values(seed)

    def amount(litres):
        return f'{litres * PER_L[unit]:f} {unit}'

    limit, above = amount(bound), amount(bound + gap)
    # well below the later occurrence's gate, including under the wider band
    outside = amount(Decimal(bound) * Decimal('0.9999'))
    return f"""scenario "Stored occurrence lookups"
    horizon {start + 2} h
meter:
    level: {unit} = {above} scale {amount(1)}
    seen: L = 0 L
    near = formula(this.batch.occurrences.at({start} h if this.level <= {limit} else 0 h).amount)
    filtered = formula(this.batch.occurrences.where(gate <= {limit}).at(t).amount)
    outside = formula(this.batch.occurrences.at({start} h if this.level <= {outside} else 0 h).amount)
    equal = formula(this.batch.occurrences.at({start} h if this.level <= {above} else 0 h).amount)
    batch = event(amount: L, gate: L):
        after {start + 3} h
    launch = event():
        after {start} h:
            this.batch.start({new} L, {above})
        after 1 h:
            this.seen = this.near
meter.batch.start({old} L, {limit})
meter.launch.start()
"""


def _observations(record, program, configuration, times, table):
    result = {}
    for name, rows in (
        ('read', lambda: read(record, program, PATHS, times)),
        ('report', lambda: report(record, program, configuration, PATHS, times, table=table).values),
    ):
        try:
            values = rows()
            result[name] = {
                path: [v if isinstance(v, (int, float)) else repr(v) for v in row.values]
                for path, row in zip(PATHS, values, strict=True)
            }
        except Exception as error:
            result[name] = f'{type(error).__name__}: {error}'
    return result


def _fresh_results(directory):
    directory = Path(directory)
    results = {}
    for settings in sorted(directory.glob('*.config')):
        label = settings.stem
        cfg = value_of(settings.read_bytes())
        times = json.loads((directory / f'{label}.times').read_text())
        for source in ('saved', 'cache'):
            # Each lookup starts from just the artifact, the configuration and the persisted record.
            artifact = load(directory / f'{label}.program')
            try:
                if source == 'saved':
                    record = value_of((directory / f'{label}.record').read_bytes())
                else:
                    previous = store.counts['hits']
                    with store.use(directory / 'cache'):
                        record = store.run(artifact.program, cfg)
                    results[label, 'cache_hits'] = store.counts['hits'] - previous
                results[label, source] = _observations(record, artifact.program, cfg, times, artifact.table)
            except Exception as error:
                results[label, source] = f'{type(error).__name__}: {error}'
    return [[label, name, rows] for (label, name), rows in results.items()]


def check_record_numerics(seed):
    bound, gap, start, old, new = case_values(seed)
    times = [start - 0.5, start + 0.5, start + 1.5]
    differences, expectations, sources = [], {}, {}
    with TemporaryDirectory(prefix='napkin-record-') as directory:
        folder = Path(directory)
        for unit in ('L', 'mL' if seed % 2 == 0 else 'kL'):
            source = sources[unit] = record_source(seed, unit)
            model = compile_text(source, UNITS)
            for custom in (False, True):
                rtol = 1e-6 if custom else 1e-9
                selected = new if custom else old
                series = [old, selected, selected]
                expected = dict(
                    zip(PATHS, [series, series, [old] * 3, [old, new, new], [0, 0, selected]], strict=True)
                )
                modes = (False, True) if seed == 0 else (seed % 2 == 0,)
                for selective in modes:
                    label = f'{unit}-rtol={rtol:g}-{"selective" if selective else "full"}'
                    expectations[label] = expected
                    base = model.configuration
                    request = base.request
                    if selective:
                        request = replace(
                            request, everything=False, keys=tuple(key_of(model.program, p) for p in PATHS)
                        )
                    cfg = replace(base, request=request, numerics=replace(base.numerics, rtol=rtol))
                    model.artifact().save(folder / f'{label}.program')
                    (folder / f'{label}.times').write_text(json.dumps(times))
                    (folder / f'{label}.config').write_bytes(value_bytes(cfg))
                    try:
                        with store.use(folder / 'cache'):
                            result = store.run(model.program, cfg)
                        (folder / f'{label}.record').write_bytes(value_bytes(result))
                        if result.failure is not None:
                            differences.append(f'{label} initial run stopped: {result.failure}')
                        _compare(
                            differences,
                            label,
                            'initial',
                            _observations(result, model.program, cfg, times, model.table),
                            expected,
                        )
                    except Exception as error:
                        differences.append(f'{label} initial run raised {type(error).__name__}: {error}')
        # One interpreter reads all physical spellings and controls of this seed without any preceding simulation.
        fresh = subprocess.run(
            [
                sys.executable,
                '-B',
                '-m',
                'tests.engine.record_numerics_cases',
                str(folder),
            ],
            cwd=folder,
            env={**os.environ, 'PYTHONPATH': str(ROOT)},
            timeout=35,
            capture_output=True,
            text=True,
            check=False,
        )
        if fresh.returncode:
            differences.append(f'fresh reader exited {fresh.returncode}: {fresh.stderr}')
        else:
            for label, source, observations in json.loads(fresh.stdout):
                if source == 'cache_hits':
                    if observations != 1:
                        differences.append(f'{label} expected a warm cache hit, got {observations}')
                else:
                    _compare(differences, label, source, observations, expectations[label])
    if differences:
        models = '\n'.join(sources.values())
        raise AssertionError(
            f'record numerics seed {seed}, limit {bound} L, gap {gap} L\n'
            + '\n'.join(differences)
            + '\n'
            + models
        )


def _compare(differences, label, source, observations, expected):
    if not isinstance(observations, dict):
        differences.append(f'{label} {source}: {observations}')
        return
    for api, actual in observations.items():
        if not isinstance(actual, dict):
            differences.append(f'{label} {source}/{api} expected values, got {actual}')
            continue
        for path in PATHS:
            if actual.get(path) != expected[path]:
                differences.append(
                    f'{label} {source}/{api} {path} expected {expected[path]}, got {actual.get(path)}'
                )


if __name__ == '__main__':
    print(json.dumps(_fresh_results(sys.argv[1])))
