#!/usr/bin/env python
"""Make every table of FINDINGS.md again.

    /home/user/napkin/.venv/bin/python scratch/rewrite/a4a/measure.py [OUT] [--quick] [--only NAME …] [--tables]

OUT (default: a new folder in the temporary folder of the system) gets three copies of the package
at the base commit, the models of each part, one JSON file for each part and `results.md`, which
holds the tables. Run it alone: the timings are of one process on a machine with four cores.

- It writes nothing outside OUT. The copies of the package are made with `git archive` from the
  base worktree (`/home/user/napkin-base`, or the folder that NAPKIN_BASE names), which reads the
  repository and changes nothing; `01_id_column.patch` and `02_table_path_probe.patch` of this
  folder are applied to two of the copies.
- `--quick` leaves out the cases that take more than about a minute each (the components of 300
  places and more, the network of 300,000 places, the lag of today's table path with 35,000 rows).
- `--only NAME` runs the steps whose name starts with NAME (the names are in `steps`).
- `--tables` only makes `results.md` again from the JSON files that OUT holds.

A whole run takes about an hour, most of it in the components of 300 places. Each timing is the
best of three runs where one run takes less than about a minute, and one run above that; each JSON
file has the load of the machine when its part ran.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('NAPKIN_BASE', '/home/user/napkin-base'))
PYTHON = sys.executable


def copy(out, name, patches=()):
    """A copy of the package at the base commit in OUT/copies/NAME, with some patches of this folder."""
    folder = out / 'copies' / name
    if folder.exists():
        return folder
    folder.mkdir(parents=True)
    archive = subprocess.run(['git', '-C', str(BASE), 'archive', 'HEAD', 'napkin'], check=True, capture_output=True)
    subprocess.run(['tar', '-x', '-C', str(folder)], input=archive.stdout, check=True)
    for patch in patches:
        with open(HERE / patch) as handle:
            subprocess.run(['patch', '-p1', '-s'], cwd=folder, stdin=handle, check=True)
    return folder


def steps(quick):
    """(name, the copy of the package that it imports or None, the script and its arguments, the
    most seconds that it may take)."""
    found = [
        ('t1-tiny', 'ids', ['t1_transfer.py', 'tiny'], 300),
        ('t1-probe-base', 'base', ['t1_transfer.py', 'probe', 'OUT', 'base'], 300),
        ('t1-probe-probe', 'probe', ['t1_transfer.py', 'probe', 'OUT', 'probe'], 300),
        ('t1-agree', 'ids', ['t1_transfer.py', 'agree'], 900),
        ('t1-check', None, ['t1_transfer.py', 'check'], 600),
        ('t1-scale-300', None, ['t1_transfer.py', 'scale', 'OUT', '300', '350'], 300),
        ('t1-scale-3000', None, ['t1_transfer.py', 'scale', 'OUT', '3000', '3500'], 300),
        ('t1-scale-30000', None, ['t1_transfer.py', 'scale', 'OUT', '30000', '35000'], 600),
        ('t1-reorder', None, ['t1_transfer.py', 'reorder', 'OUT', '30000', '35000'], 600),
        ('t2-sets', None, ['t2_sets.py', 'sets', 'OUT', '30000', '35000'], 300),
        ('t2-sparse', 'base', ['t2_sets.py', 'sparse', 'OUT', '30000', '35000'], 1800),
        ('t3-lag', None, ['t3_record.py', 'lag'], 60),
        ('t3-scale', None, ['t3_record.py', 'scale', 'OUT', '30000', '35000'], 900),
        ('t3-today', 'ids', ['t3_record.py', 'today', 'OUT'] + (['quick'] if quick else []), 1800),
    ]
    if not quick:
        found.append(('t1-scale-300000', None, ['t1_transfer.py', 'scale', 'OUT', '300000', '350000', '1'], 900))
    sizes = {'constant': (30, 100, 300, 1000), 'constant rings': (30, 100, 300), 'linear': (3, 10, 30, 100, 300), 'saturating': (3, 10, 30, 100, 300), 'target': (3, 10, 30, 100, 300)}
    for kind, places in sizes.items():
        name, *rings = kind.split()
        for count in places:
            if quick and count >= 300:
                continue
            runs = '3' if count <= 100 and not (rings and count >= 100) else '1'
            found.append(
                (f't2-component-{name}{"-rings" if rings else ""}-{count}', 'ids', ['t2_sets.py', 'component', 'OUT', name, str(count), *rings, runs], 1500)
            )
    return found


def run(out, quick, only):
    copies = {
        'base': copy(out, 'base'),
        'ids': copy(out, 'ids', ['01_id_column.patch']),
        'probe': copy(out, 'probe', ['02_table_path_probe.patch']),
    }
    log = open(out / 'log.txt', 'a')
    for name, needs, command, limit in steps(quick):
        if only and not any(name.startswith(prefix) for prefix in only):
            continue
        arguments = [str(out) if item == 'OUT' else item for item in command]
        if 'OUT' not in command:
            arguments.append(str(out))
        env = {key: value for key, value in os.environ.items() if key != 'PYTHONPATH'}
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        if needs:
            env['PYTHONPATH'] = str(copies[needs])
        print(f'== {name}  (load {[round(x, 2) for x in os.getloadavg()]})', flush=True)
        log.write(f'== {name}\n')
        start = time.perf_counter()
        try:
            done = subprocess.run([PYTHON, str(HERE / arguments[0]), *arguments[1:]], env=env, capture_output=True, text=True, timeout=limit)
            text = done.stdout + (done.stderr[-3000:] if done.returncode else '')
        except subprocess.TimeoutExpired as late:
            text = (late.stdout or b'').decode() if isinstance(late.stdout, bytes) else (late.stdout or '')
            text += f'\nno result in {limit} s\n'
            if name.startswith('t2-component'):
                kind, count = command[3], command[4]
                rings = 'rings' in command
                row = {'kind': kind, 'places': int(count), 'rings': rings, 'stores': 2 * int(count), 'failed': f'no result in {limit} s'}
                (out / f'component_{kind}_{count}_{int(rings)}.json').write_text(json.dumps(row))
        log.write(text + '\n')
        log.flush()
        print(text[-2500:], flush=True)
        print(f'   ({time.perf_counter() - start:.0f} s)', flush=True)


# ---- the tables ---------------------------------------------------------------------------------------


def read(out, name):
    path = out / f'{name}.json'
    return json.loads(path.read_text()) if path.exists() else None


def number(value, digits=3):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, int):
        return f'{value:,}'
    if value == 0:
        return '0'
    if abs(value) >= 1000:
        return f'{value:,.0f}'
    if abs(value) >= 0.01:
        return f'{value:.{digits}g}'
    return f'{value:.2g}'


def table(header, rows):
    lines = ['| ' + ' | '.join(header) + ' |', '| ' + ' | '.join('---' if k == 0 else '--:' for k in range(len(header))) + ' |']
    lines += ['| ' + ' | '.join(str(cell) for cell in row) + ' |' for row in rows]
    return '\n'.join(lines)


def tables(out):
    parts = ['# The tables of A4a', '', 'Made by `measure.py`. Times are in seconds unless a column says otherwise.', '']

    def add(title, text):
        parts.extend([f'## {title}', '', text, ''])

    tiny = read(out, 'tiny')
    if tiny:
        rows = []
        for row in tiny['rows']:
            names = list(row['expected'])
            rows.append([row['order'], number(row['t']), *(number(row['expected'][n]) for n in names), *(number(row['present'][n]) for n in names), *(number(row['layout'][n]) for n in names), 'yes' if row['same'] else 'NO'])
        names = [n.split('.')[1] for n in tiny['rows'][0]['expected']]
        add('T1.1 The tiny transfer: the stock of each place (L)', table(['rows of places.csv', 't (h)', *(f'expected {n}' for n in names), *(f'present engine {n}' for n in names), *(f'layout {n}' for n in names), 'same'], rows))
    probes = [read(out, 'probe_base'), read(out, 'probe_probe')]
    if all(probes):
        rows = []
        for a, b in zip(probes[0]['rows'], probes[1]['rows']):
            rows.append([a['case'], a['expected'], a['flat'], f"{a['verdict']}: {a['table'] if a['table'] else a['said']}", f"{b['verdict']}: {b['table'] if b['table'] else b['said']}"])
        add('T1.2 The table path of the present engine: the stocks of three places at 3 h (L)', table(['case', 'expected', 'rows written out', 'table path, base commit', 'table path, with the probe patch'], rows))
    agree = read(out, 'agree')
    if agree:
        rows = [[r['places'], r['routes'], 'yes' if r['rings'] else 'no', r['depletions'], r['moves'], number(r['largest_difference_L']), number(r['present_engine_s'])] for r in agree['rows']]
        add('T1.3 The layout against the present engine (one component)', table(['places', 'routes', 'rings', 'stocks that empty', 'moves', 'largest difference of a store (L)', 'present engine: build and run'], rows) + f"\n\nLoad: {agree['load']}.")
    check = read(out, 'check')
    if check:
        rows = [[r['places'], r['routes'], r['depletions'], r['moves'], number(r['largest_difference_L'])] for r in check['rows']]
        add('T1.4 The layout against its second implementation, with rings', table(['places', 'routes', 'stocks that empty', 'moves', 'largest difference of a store (L)'], rows))
    scales = [read(out, f'scale_{p}_{r}') for p, r in ((300, 350), (3000, 3500), (30000, 35000), (300000, 350000))]
    scales = [row for row in scales if row]
    if scales:
        keys = [
            ('places', 'places'), ('routes', 'routes'), ('stores', 'stores'), ('flows', 'flows'), ('csv_bytes', 'the two tables (bytes)'),
            ('build_s', 'build: read the tables, links, network'), ('start_s', 'start of the run'), ('run_s', 'run to 48 h'),
            ('moments', 'moments'), ('depletions', 'stocks that empty'), ('moves', 'moves'), ('line_restarts', 'lines that start again'),
            ('microseconds_per_moment', 'microseconds for each moment'), ('conservation_error_L', 'total at 48 h less total at 0 h (L)'),
            ('total_start_L', 'total at 0 h (L)'), ('connected_sets', 'connected sets (plain rule)'), ('largest_set_stores', 'stores of the largest set'),
            ('peak_memory_MB', 'peak memory of the process (MB)'), ('runs', 'runs (the best is given)'), ('load', 'load'),
        ]
        add('T1.5 The cost at scale: the layout, run on lines', table(['', *(f"{row['places']:,} places" for row in scales)], [[label, *(number(row[key]) if not isinstance(row[key], list) else row[key] for row in scales)] for key, label in keys]))
    reorder = read(out, 'reorder_30000_35000')
    if reorder:
        rows = [[key, value['named_values'], value['values_with_other_bits'], number(value['largest_difference_L'])] for key, value in reorder.items() if isinstance(value, dict)]
        add('T1.6 Both tables with their rows in another order, 30,000 places and 35,000 routes', table(['order of the rows in memory', 'named values', 'values with other bits', 'largest difference (L)'], rows))
    sets = read(out, 'sets_30000_35000')
    if sets:
        ways = list(sets['rows'][0]['ways'])
        rows = [[r['case'], r['sets_with_a_store'], r['largest_set_stores'], *(f"{r['ways'][w][0]:,} sets, {r['ways'][w][1]:,} stores" for w in ways), number(r['cut_s'])] for r in sets['rows']]
        add(f"T2.1 The connected sets of the model with 30,000 places and 35,000 routes (a component has at most {sets['component_limit']} stores)", table(['case', 'sets', 'stores of the largest', *ways, 'time of the cut'], rows))
    rows = []
    for kind, rings in (('constant', 0), ('constant', 1), ('linear', 0), ('saturating', 0), ('target', 0)):
        for count in (3, 10, 30, 100, 300, 1000):
            r = read(out, f'component_{kind}_{count}_{rings}')
            if not r:
                continue
            label = kind + (', rings' if rings else '')
            if 'failed' in r:
                rows.append([label, count, r['stores'], r.get('flows', ''), '', '', '', '', '', '', number(r.get('peak_memory_MB')), r['failed'][:90]])
            else:
                rows.append([label, count, r['stores'], r['flows'], number(r['build_s']), number(r['simulate_s']), r['evaluations'], number(r['ms_per_evaluation']), f"{100 * r['share_of_evaluation_in_allocation']:.0f}%", r['linear_programs'], number(r['peak_memory_MB']), f"{r['runs']} run(s), load {r['load'][0]}"])
    if rows:
        add('T2.2 One connected set as one component of the present general tier (horizon 300 h)', table(['request of a route', 'places', 'stores', 'flows', 'build', 'run', 'evaluations of the rates', 'ms for each', 'of it in the allocation', 'linear programs', 'peak memory (MB)', 'note'], rows))
    sparse = read(out, 'sparse_30000_35000')
    if sparse:
        keys = [
            ('stores', 'stores'), ('flows', 'flows'), ('jacobian_nonzeros', 'nonzeros of the Jacobian'), ('dense_jacobian_MB', 'the same matrix, dense (MB)'),
            ('ms_per_evaluation', 'one evaluation of the rates (ms)'), ('integrate_s', 'the integration to 48 h'), ('solver_steps', 'steps of the solver'),
            ('evaluations', 'evaluations of the rates'), ('jacobians', 'Jacobians'), ('factorizations', 'factorizations'),
            ('resting_stores_in_the_state', 'stores at rest in the state of the two next rows'),
            ('stand_in_sharing_ms', 'one sharing at that state, stand-in rule (ms)'), ('linear_program_s', 'one linear program at that state, bundled HiGHS'),
            ('estimate_run_with_the_stand_in_sharing_at_each_evaluation_s', 'estimate: the run with the stand-in sharing at each evaluation'),
            ('estimate_run_with_a_program_at_each_evaluation_h', 'estimate: the run with one program at each evaluation (hours)'),
            ('peak_memory_MB', 'peak memory (MB)'), ('load', 'load'),
        ]
        add('T2.3 A large set whose requests read a stock: 30,000 places and 35,000 routes on sparse arrays', table(['', 'value'], [[label, number(sparse[key]) if not isinstance(sparse[key], list) else sparse[key]] for key, label in keys]))
    lag = read(out, 'lag')
    if lag:
        add('T3.1 Two histories with the same readings', table(['', 'read at 0, 6, 12 h', 'mean from 6 h to 10 h'], [['8 L added at 7 h', lag['readings_early'], number(lag['mean_early'])], ['8 L added at 9 h', lag['readings_late'], number(lag['mean_late'])]]))
    rec = read(out, 'record_30000_35000')
    if rec:
        rows = [[r['record'], number(r['run_s']), number(r.get('added_s')), r.get('pieces', ''), r.get('bytes', ''), r.get('bytes_packed', ''), number(r.get('pack_s'))] for r in rec['rows']]
        text = table(['what the run records', 'run to 48 h', 'added by the record', 'pieces', 'bytes as arrays', 'bytes packed', 'time to pack'], rows)
        text += f"\n\n{rec['places']:,} places, {rec['routes']:,} routes, {rec['rows'][0]['moments']:,} moments. Best of {rec['runs']}; load {rec['load']}.\n\n"
        made = rec['made_from_everything']
        text += table(['', 'value'], [
            ['recording changes the run', number(rec['recording_changes_the_run'])],
            ['largest relative difference of a reduction kept in the run from the same made from every store', number(max(rec['largest_relative_difference_of_each_reduction'].values()))],
            ['pieces of each history kept in the run', rec['pieces_of_each_history']],
            ['passes over the rows for the greatest and the least', rec['passes_over_the_rows']],
            ['a report from the histories kept in the run: ten values at three times and one lag at three times', number(rec['report_s'])],
            ['from the record of everything: the ten reductions at three times', number(made['ten_reductions_at_three_times_s'])],
            ['from the record of everything: the whole history of two sums', number(made['two_sum_histories_s'])],
            ['largest relative difference of those two histories from the ones kept in the run', number(made['largest_relative_difference_from_the_histories_kept_in_the_run'])],
        ])
        add('T3.2 The record with 30,000 rows', text)
    today = read(out, 'today')
    if today:
        rows = [[r['places'], r['quantities'], r['segments'], r['snapshots'] + r['steps'], r['pickle_zlib_bytes'], r['state_copies_bytes']] for r in today['trajectory']]
        text = table(['places', 'quantities', 'segments', 'copies of the state around the steps', 'pickle with zlib (bytes)', 'of it, state by segment and by step (bytes, before zlib)'], rows)
        t = today['table_path']
        text += '\n\n' + table(['the table path of today, its own model', 'value'], [
            ['rows (places and routes)', f"{t['places']:,} and {t['routes']:,}"], ['steps', t['steps']],
            ['compile and plan', number(t.get('compile_s')) + ' and ' + number(t.get('plan_s'))],
            ['run without the record', number(t['run_s'])], ['run with `record=True`', number(t['run_with_record_s'])],
            ['entries of the record (old values, old lines)', f"{t['undo_entries']:,} and {t['line_log_entries']:,}"],
            ['bytes of the record in memory', t['record_bytes']], ['bytes of the trace in memory', t['log_bytes']],
            ['a report of one output at three times, no lag', number(t['report_three_times_s'])],
        ])
        rows = [[f'{int(count):,}', number(r['report_one_time_s']) if r.get('report_one_time_s') is not None else f"no result in {r['stopped_after_s']:.0f} s"] for count, r in today['lag_on_the_table_path'].items()]
        text += '\n\n' + table(['routes', 'a report of one output with a uniform lag, at one time'], rows) + f"\n\nLoad: {today['load']}."
        add('T3.3 What the present engine keeps', text)
    text = '\n'.join(parts)
    (out / 'results.md').write_text(text)
    print(text)


if __name__ == '__main__':
    arguments = sys.argv[1:]
    only = []
    while '--only' in arguments:
        at = arguments.index('--only')
        only.append(arguments[at + 1])
        del arguments[at : at + 2]
    quick = '--quick' in arguments
    only_tables = '--tables' in arguments
    folders = [item for item in arguments if not item.startswith('--')]
    out = Path(folders[0]).resolve() if folders else Path(tempfile.mkdtemp(prefix='a4a-measure-'))
    out.mkdir(parents=True, exist_ok=True)
    print(f'OUT = {out}')
    if not only_tables:
        run(out, quick, only)
    tables(out)
