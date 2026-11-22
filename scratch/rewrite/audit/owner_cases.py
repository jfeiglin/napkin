"""Run deterministic audit families in batches, preserving every outcome for selective retries."""

import argparse
import gzip
import hashlib
import json
import subprocess
import time
import traceback
from pathlib import Path

from tests.engine import stage_broadcast_cases, stage_read_cases

FAMILIES = {
    's1/scalar': stage_read_cases.check_scalar_stage,
    's1/selection': lambda seed: stage_broadcast_cases.check_broadcast_stage(seed, 'selection'),
    's1/ordering': lambda seed: stage_broadcast_cases.check_broadcast_stage(seed, 'ordering'),
}


def rows(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream]


def write_row(stream, row):
    stream.write(json.dumps(row, sort_keys=True, separators=(',', ':'), default=str) + '\n')
    stream.flush()


def case_ids(families, start, stop):
    if not 0 <= start < stop:
        raise ValueError('expected 0 <= start < stop')
    return [f'{family}/{seed}' for family in families for seed in range(start, stop)]


def run_cases(ids, destination):
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    differences = subprocess.check_output(['git', 'diff', 'HEAD', '--', 'napkin', 'tests/reference'])
    dirty = hashlib.sha256(differences).hexdigest() if differences else None
    generators = {
        module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        for module in (stage_broadcast_cases, stage_read_cases)
    }
    failures = 0
    with destination.open('x', encoding='utf-8') as stream:
        for case in ids:
            family, seed = case.rsplit('/', 1)
            check = FAMILIES[family]
            start = time.perf_counter()
            result = {
                'id': case,
                'revision': revision,
                'engine_reference_diff_sha256': dirty,
                'generators_sha256': generators,
            }
            try:
                check(int(seed))
            except AssertionError as exc:
                failures += 1
                result.update(status='failed', difference=exc.args, traceback=traceback.format_exc())
            except Exception as exc:
                failures += 1
                result.update(status='error', difference=str(exc), traceback=traceback.format_exc())
            else:
                result.update(status='passed')
            result['seconds'] = round(time.perf_counter() - start, 6)
            write_row(stream, result)
    print(f'{destination}: {len(ids)} completed, {failures} unsuccessful')
    return int(bool(failures))


def merge(parts, ids, destination):
    data = {}
    for path in parts:
        for result in rows(path):
            case = result['id']
            if case in data:
                raise ValueError(f'duplicate result for {case}')
            data[case] = result
    missing, extra = set(ids) - data.keys(), data.keys() - set(ids)
    if missing or extra:
        raise ValueError(f'missing IDs {sorted(missing)}, extra IDs {sorted(extra)}')
    if destination.suffix != '.gz':
        raise ValueError('a merged ledger must end in .gz')
    with (
        destination.open('xb') as output,
        gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as archive,
    ):
        for case in ids:
            archive.write((json.dumps(data[case], sort_keys=True, separators=(',', ':')) + '\n').encode())
    print(f'{destination}: {len(ids)} unique outcomes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run')
    run.add_argument('--failed-from', type=Path, help='retry unsuccessful IDs from a raw or merged ledger')
    run.add_argument('--id', dest='ids', nargs='+', help='run only the named family/seed IDs')
    collect = sub.add_parser('merge')
    collect.add_argument('parts', nargs='+', type=Path)
    for command in (run, collect):
        command.add_argument('--family', choices=FAMILIES, nargs='+', default=list(FAMILIES))
        command.add_argument('--start', type=int, default=0)
        command.add_argument('--stop', type=int, default=300)
        command.add_argument('--out', type=Path, required=True)
    opts = parser.parse_args()
    ids = case_ids(opts.family, opts.start, opts.stop)
    if opts.action == 'merge':
        merge(opts.parts, ids, opts.out)
        return 0
    if opts.failed_from and opts.ids:
        parser.error('--failed-from and --id are mutually exclusive')
    if opts.failed_from:
        failed = {row['id'] for row in rows(opts.failed_from) if row['status'] != 'passed'}
        ids = [case for case in ids if case in failed]
    elif opts.ids:
        ids = list(dict.fromkeys(opts.ids))
    return run_cases(ids, opts.out)


if __name__ == '__main__':
    raise SystemExit(main())
