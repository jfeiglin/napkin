"""Compare current water, heat, IV and defensive-response controls with pinned historical observations.

Run with python -m scratch.rewrite.a5.recovery_parity results.csv.gz. Optionally select one or
more groups with --package water, heat, iv or defensive (repeat the flag). Each observation is written,
including numerical and reporting differences, and unexpected differences make the command fail.
"""

import argparse
import csv
import gzip
import io
import json
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from numbers import Real
from pathlib import Path

import napkin
from napkin import store
from napkin.engine import edits_for
from napkin.engine.report import Lag, report
from napkin.program.record import Unavailable

PACKAGES = Path(__file__).resolve().parents[3] / 'scenarios'
BASE = '8488047dbb7eafee1f5582cf59839c6bea0cf8cd'


class Comparison:
    def __init__(self, writer):
        self.writer = writer
        self.counts = Counter()
        self.failures = 0
        self.model_hash = ''

    def check(self, case, observation, at, old, new, reason=''):
        self.counts[case[0]] += 1
        if old == new:
            reason = 'Matched'
        elif not reason:
            self.failures += 1
            reason = 'Outside the archived contract'
        self.writer.writerow([*case, self.model_hash, observation, at, old, new, reason])

    def number(self, case, path, at, old, new, absolute, relative):
        if not isinstance(new, Real):
            self.check(case, path, at, old, str(new))
            return
        limit = max(absolute, relative * abs(old))
        reason = f'Within absolute tolerance {absolute:g} or relative tolerance {relative:g}'
        self.check(case, path, at, old, new, reason if abs(new - old) <= limit else '')


def finished(model, name=None, edits=None):
    changes = {'runs': {name: edits}} if name else {'set': edits}
    config = model.configure(name, edits_for(model, changes) if edits else None)
    record = store.run(model.program, config)
    if record.stop is not None or record.end != config.request.horizon:
        raise ValueError(f'{name}: stopped at {record.end} of {config.request.horizon} h: {record.stop}')
    return record, config


def water(comparison):
    folder = PACKAGES / 'water_controls_wipe'
    fixture = json.loads((folder / 'tests/recovery-readings.json').read_bytes())
    if fixture['run'] != 'delayed_none' or not BASE.startswith(fixture['revision']):
        raise ValueError('Expected the externally supplied outage reference at 8488047')
    hours = fixture['hours']
    for place, series in fixture['places'].items():
        model = napkin.load_scenario(folder / 'variants' / place)
        comparison.model_hash = model.model_hash
        record, _ = finished(model, fixture['run'])
        assert record.end == hours[-1]
        for row in napkin.read(record, model.program, list(series), hours):
            absolute = 1e-5 if row.path == 'work_remaining' else 1e-8
            for at, old, new in zip(hours, series[row.path], row.values, strict=True):
                comparison.number(
                    ('Water', f'{place}/{fixture["run"]}'), row.path, at, old, new, absolute, 1e-8
                )


def heat(comparison):
    folder = PACKAGES / 'heat_wave_blackout'
    archive = json.loads(
        subprocess.check_output(
            ['git', 'show', f'{BASE}:scenarios/heat_wave_blackout/results/runs.json'], cwd=PACKAGES.parent
        )
    )
    archived = {row['id']: row['outcomes'] for row in archive['rows']}
    original = {
        'standard': 'standard_obeys',
        'early_cooling': 'early_obeys',
        'powered_places': 'early_powered_places',
        'delayed_cooling': 'delayed_human',
    }
    fixture = json.loads((folder / 'tests/legacy-outcomes.json').read_bytes())
    if fixture.keys() != original.keys():
        raise ValueError('Heat fixture and archived run mapping differ')
    model = napkin.load_scenario(folder)
    comparison.model_hash = model.model_hash
    for name, series in fixture.items():
        before = comparison.failures
        record, _ = finished(model, name)
        assert record.end == archive['horizon_h']
        for row in napkin.read(record, model.program, list(series), [record.end]):
            # These historical endpoints are published to six significant figures.
            (value,) = row.values
            archive_row = archived[original[name]][row.path]
            old = archive_row['value']
            if archive_row['status'] != 'estimated' or old != series[row.path]:
                raise ValueError(f'{name} {row.path}: endpoint differs from pinned publication')
            shown = 0.0 if abs(value) < 1e-6 and old == 0 else float(format(value, '.6g'))
            comparison.check(('Heat', f'{original[name]} -> {name}'), row.path, record.end, old, shown)
        print(
            f'{name}: {len(series)} archived endpoints, {comparison.failures - before} unexpected', flush=True
        )


def iv(comparison):
    folder = PACKAGES / 'iv_fluid_shortage'
    fixture = json.loads(gzip.decompress((folder / 'tests/legacy-recovery.json.gz').read_bytes()))
    assert fixture['legacy_sha'] == BASE
    model = napkin.load_scenario(folder)
    comparison.model_hash = model.model_hash
    hours = fixture['hours']
    lags = {path: Lag(h, h) for path, h in fixture['lags_h'].items()}
    for label, case in fixture['cases'].items():
        key = ('IV', label)
        record, config = finished(model, case['run'], case['edits'])
        assert record.end == hours[-1]
        physical = case['physical_readings']
        for row in napkin.read(record, model.program, list(physical), hours):
            for at, old, new in zip(hours, physical[row.path], row.values, strict=True):
                comparison.number(key, row.path, at, old, new, 1e-6, 1e-8)
        for row in napkin.read(record, model.program, case['unmodeled_hold_stocks'], hours):
            for at, new in zip(hours, row.values, strict=True):
                comparison.check(('IV hold controls', label), row.path, at, 0, new)
        for event, old in case['recovery_times_h'].items():
            times = [e.t for e in record.entries('start') if e.owner.split('#')[0] == event]
            comparison.check(('IV event counts', label), event, '', len(old), len(times))
            for index, (before, now) in enumerate(zip(old, times), 1):
                comparison.number(key, event + f' start {index}', '', before, now, 1e-6, 1e-6)
        outcomes = case['reported_outcomes']
        reported = ('IV reported outcomes', label)
        for row in report(record, model.program, config, list(outcomes), hours, lags).values:
            for at, old, new in zip(hours, outcomes[row.path], row.values, strict=True):
                if at < fixture['lags_h'].get(row.path, 0) and old == 0 and isinstance(new, Unavailable):
                    comparison.check(
                        reported, row.path, at, old, 'unavailable', 'Reporting window precedes hour zero'
                    )
                else:
                    comparison.number(reported, row.path, at, old, new, 1e-6, 1e-8)


def defensive(comparison):
    fixture_path = PACKAGES / 'cyber_learning_loop/defensive_response/tests/legacy-readings.json'
    folder = fixture_path.parents[1]
    fixture = json.loads(fixture_path.read_bytes())
    assert fixture['legacy_commit'] == BASE
    model = napkin.load_scenario(folder)
    comparison.model_hash = model.model_hash
    hours = [y * 8760 for y in fixture['years']]
    paths = ['observations.pressure', *fixture['paths'][1:]]
    for name, case in fixture['cases'].items():
        record, _ = finished(model, edits=case['edits'])
        assert record.end == hours[-1]
        for index, row in enumerate(napkin.read(record, model.program, paths, hours)):
            for at, historical, new in zip(hours, case['rows'], row.values, strict=True):
                comparison.number(
                    ('Defensive response', name), row.path, at, historical[index], new, 1e-8, 1e-7
                )


@contextmanager
def output_stream(path):
    if path.suffix == '.gz':
        with (
            path.open('wb') as raw,
            gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed,
            io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream,
        ):
            yield stream
    else:
        with path.open('w', encoding='utf-8', newline='') as stream:
            yield stream


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    packages = {'water': water, 'heat': heat, 'iv': iv, 'defensive': defensive}
    parser.add_argument('--package', action='append', choices=packages)
    args = parser.parse_args()
    with store.use(store.default_directory()), output_stream(args.results) as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(
            ['package', 'case', 'model_hash', 'observation', 'hour', 'legacy', 'current', 'result']
        )
        comparison = Comparison(writer)
        for name in args.package or packages:
            packages[name](comparison)
            output.flush()
            print(f'{name} finished, model {comparison.model_hash}', flush=True)
    for label, count in comparison.counts.items():
        print(f'{label}: {count} comparisons')
    print(f'{comparison.failures} unexpected differences')
    sys.exit(bool(comparison.failures))
