"""Run deterministic audit families in batches, preserving every outcome for selective retries."""

import argparse
import gzip
import hashlib
import json
import subprocess
import time
import traceback
from pathlib import Path

from tests.engine import (
    authored_number_cases,
    authoring_parity_cases,
    collection_kind_cases,
    collection_scope_cases,
    comparison_band_cases,
    cross_rate_cases,
    lag_monotonicity_cases,
    path_selection_cases,
    proof_event_cases,
    proof_network_cases,
    proof_solver_cases,
    record_history_cases,
    record_identity_cases,
    record_numerics_cases,
    reversible_bound_cases,
    simultaneous_bound_cases,
    solver_flow_scale_cases,
    solver_scale_cases,
    stage_broadcast_cases,
    stage_read_cases,
    stock_balance_cases,
    stock_edit_cases,
    study_request_cases,
    switch_selection_cases,
    switch_side_cases,
)

FAMILIES = {
    'p7/selection': path_selection_cases.check_path_selection,
    'p5/request': study_request_cases.check_study_request,
    's1/scalar': stage_read_cases.check_scalar_stage,
    's1/selection': lambda seed: stage_broadcast_cases.check_broadcast_stage(seed, 'selection'),
    's1/ordering': lambda seed: stage_broadcast_cases.check_broadcast_stage(seed, 'ordering'),
    's2/gap': lambda seed: comparison_band_cases.check_comparison_band(seed, 'gap'),
    's2/range': lambda seed: comparison_band_cases.check_comparison_band(seed, 'range'),
    's6/units': lambda seed: authored_number_cases.check_authored_number(seed, 'units'),
    's6/cells': lambda seed: authored_number_cases.check_authored_number(seed, 'cells'),
    's6/cli': lambda seed: authored_number_cases.check_authored_number(seed, 'cli'),
    's3/component': lambda seed: switch_side_cases.check_switch_side(seed, 'component'),
    's3/sparse': lambda seed: switch_side_cases.check_switch_side(seed, 'sparse'),
    's3/declared': lambda seed: switch_side_cases.check_switch_side(seed, 'declared'),
    's3/selection': switch_selection_cases.check_switch_selection,
    's4/inventory': lambda seed: stock_balance_cases.check_stock_balance(seed, 'inventory'),
    's4/capacity': lambda seed: stock_balance_cases.check_stock_balance(seed, 'capacity'),
    's4/edit': stock_edit_cases.check_stock_edit,
    's9/reversible': reversible_bound_cases.check_reversible_bounds,
    's9/simultaneous': simultaneous_bound_cases.check_simultaneous_bounds,
    'p1/rate': cross_rate_cases.check_cross_rate,
    's5/scope': collection_scope_cases.check_collection_scope,
    's5/authoring': authoring_parity_cases.check_authoring_parity,
    's5/kinds': collection_kind_cases.check_collection_kind,
    's5/filter': collection_kind_cases.check_filter_history,
    's7/objective': solver_scale_cases.check_solver_scale,
    's7/flow': solver_flow_scale_cases.check_solver_flow_scale,
    's8/history': record_history_cases.check_record_history,
    's8/identity': record_identity_cases.check_record_identity,
    's8/numerics': record_numerics_cases.check_record_numerics,
    's10/network': proof_network_cases.check_proof_network,
    's10/solver': proof_solver_cases.check_proof_solver,
    's10/arguments': proof_event_cases.check_proof_arguments,
    's10/reach': proof_event_cases.check_proof_reach,
    'p4/monotonicity': lag_monotonicity_cases.check_lag_monotonicity,
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
        for module in (stage_broadcast_cases, stage_read_cases, comparison_band_cases, authored_number_cases)
    }
    dedicated = {
        'p7/selection': path_selection_cases,
        'p5/request': study_request_cases,
        's3/component': switch_side_cases,
        's3/sparse': switch_side_cases,
        's3/declared': switch_side_cases,
        's3/selection': switch_selection_cases,
        's4/inventory': stock_balance_cases,
        's4/capacity': stock_balance_cases,
        's4/edit': stock_edit_cases,
        's9/reversible': reversible_bound_cases,
        's9/simultaneous': simultaneous_bound_cases,
        'p1/rate': cross_rate_cases,
        's5/scope': collection_scope_cases,
        's5/authoring': authoring_parity_cases,
        's5/kinds': collection_kind_cases,
        's5/filter': collection_kind_cases,
        's7/objective': solver_scale_cases,
        's7/flow': solver_flow_scale_cases,
        's8/history': record_history_cases,
        's8/identity': record_identity_cases,
        's8/numerics': record_numerics_cases,
        's10/network': proof_network_cases,
        's10/solver': proof_solver_cases,
        's10/arguments': proof_event_cases,
        's10/reach': proof_event_cases,
        'p4/monotonicity': lag_monotonicity_cases,
    }
    sources_by_module = {
        module: {module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()}
        for module in set(dedicated.values())
    }
    failures = 0
    with destination.open('x', encoding='utf-8') as stream:
        for case in ids:
            family, seed = case.rsplit('/', 1)
            check = FAMILIES[family]
            sources = sources_by_module[dedicated[family]] if family in dedicated else generators
            start = time.perf_counter()
            result = {
                'id': case,
                'revision': revision,
                'engine_reference_diff_sha256': dirty,
                'generators_sha256': sources,
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
