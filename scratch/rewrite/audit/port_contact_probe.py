"""Compare the measured engine and its subsequent stock/clock contact correction."""

import argparse
import ast
import hashlib
import json
import math
import os
import platform
import re
import runpy
import statistics
import subprocess
import sys
import time
from collections import Counter
from contextlib import redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from port_benchmark import THREAD_ENV, file_digest, git, identity, save, workload

MEASURED = 'fc9a9ed7fc9c6086f2ac38b27379f2cd14e71864'
HARNESS = '0f0fcb2a933fdf71a0458a101a4377e1ccb0f44a'
TRIGGERS = 'napkin/engine/timeline/triggers.py'
METHODS = ('anchor', '_continued_root')
ROWS = {
    'component-tanks': (None, 2),
    'sparse-tanks': (None, 1),
    'component-compartment-tanks': (None, 24),
    'sparse-compartment-tanks': (None, 1),
    'held-pipes': (['300', '--full-record-only'], 8),
    'held-network': (['held', '300', '350', '48'], 8),
    'moving-network': (['moving', '300', '350', '48'], 1),
    'events': (['60', '48', '12'], 1),
    'declared': (['300', '350', '150', '--no-phase-times'], 3),
}
MIXED_CONTROL = """scenario "Mixed clock and stock control"
    horizon 1.1 h
yard:
    stock: L = 0 L scale 1 L
    flow fill: SOURCE -> this.stock
        request = 2 L/h
        capacity = 2 L/h
    watch = event():
        when this.stock >= 1.000000005 L + t * (1 L/h):
            this.watch.start()
        after 0 h
    clock = event():
        after 1 h
yard.clock.start()
"""


def fingerprint(data):
    raw = json.dumps(data, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def other_changes(measured, final):
    """Reject any changed runtime code outside these two methods, including top-level code."""
    assert git(final, 'diff', '--name-only', MEASURED, 'HEAD', '--', 'napkin') == TRIGGERS

    def rest(root):
        tree = ast.parse((root / TRIGGERS).read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Triggers')
        cls.body = [n for n in cls.body if getattr(n, 'name', None) not in METHODS]
        return ast.dump(tree)

    assert rest(measured) == rest(final), 'a different part of the trigger implementation changed'


def monitor():
    """Use code-object-local monitoring. Time comparisons run in other processes without probes."""
    from napkin.engine.timeline.triggers import Triggers

    m = sys.monitoring
    m.use_tool_id(3, 'port contact probe')
    methods = {getattr(Triggers, n).__code__: n for n in METHODS if hasattr(Triggers, n)}
    entries = dict.fromkeys(methods.values(), 0)
    lines = {name: Counter() for name in methods.values()}

    def start(code, _offset):
        entries[methods[code]] += 1

    def line(code, number):
        lines[methods[code]][str(number)] += 1

    m.register_callback(3, m.events.PY_START, start)
    m.register_callback(3, m.events.LINE, line)
    for code in methods:
        m.set_local_events(3, code, m.events.PY_START | m.events.LINE)
    return entries, lines


def stock_lines(root, lines):
    source = (root / TRIGGERS).read_text().splitlines()
    conditions = {
        '_continued_root': 'ways = {name: run.ways.instance_of(name) for name in stocks}',
        'anchor': 'target = self.run.ways.instance_of(name).incoming_level(name, located)',
    }
    result = {}
    for method, statement in conditions.items():
        locations = [str(i) for i, text in enumerate(source, 1) if text.strip() == statement]
        if locations:
            assert len(locations) == 1
            number = locations[0]
            result[method] = {'line': int(number), 'visits': lines[method].get(number, 0)}
    return result


def controls():
    from napkin.engine.timeline import Plan, Run
    from napkin.model.compile import compile_text

    sources = {
        'earlier': MIXED_CONTROL.replace('1.000000005', '0.999999995'),
        'continued': MIXED_CONTROL.replace('1.000000005', '1.0000000001').replace(
            '0 L scale', '0 L in [0 L, 2 L] scale'
        ),
    }
    observed = {}
    for name, source in sources.items():
        case = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
        record = Run(Plan.of(case.program, case.configuration)).run()
        assert record.end == 1.1 and record.failure is None
        observed[name] = [entry.t for entry in record.entries('fire', 'yard.watch.when[0]')]
    return observed


def guard_dispatch(args):
    """Exercise every site's actual clock predicate without advancing the 30,000-site simulation."""
    from napkin.engine.timeline import Plan, Run
    from napkin.program.config import Configuration, Request

    script = args.harness / 'scratch/rewrite/b1/s4a-engine/bench.py'
    model = runpy.run_path(str(script))['build'](30000, 12)
    run = Run(Plan.of(model, Configuration(Request(48))))
    watches = [state.plan.test.operands for state in run.triggers.states]
    assert len(watches) == 30000 and all(len(sides) == 2 for sides in watches)
    samples = []
    for _ in range(2):
        start = time.perf_counter()
        for i, (left, right) in enumerate(watches):
            phase = (i % 12) / 4
            assert run.triggers.anchor(None, left, right, phase, phase) is True
        samples.append(time.perf_counter() - start)
    assert all(run.triggers.moving_reads(*sides) == {'t'} for sides in watches)
    return {
        'row': args.row,
        'revision': args.sha,
        'script': str(script.relative_to(args.harness)),
        'script_sha256': file_digest(script),
        'driver_sha256': file_digest(Path(__file__)),
        'argv': ['30000', '48', '12'],
        'predicates': len(watches),
        'cold_and_warm_seconds': samples,
    }


def worker(args):
    assert identity(args.root) == args.sha and identity(args.harness) == HARNESS
    sys.path.insert(0, str(args.root))
    import napkin
    from napkin import engine

    assert Path(napkin.__file__).resolve().parent == args.root / 'napkin'
    assert all(os.environ[k] == v for k, v in THREAD_ENV.items())
    if args.row == 'guard-dispatch':
        return guard_dispatch(args)
    calls, lines = monitor() if args.probe else ({}, {})
    receipt = {
        'row': args.row,
        'revision': args.sha,
        'script': None,
        'driver_sha256': file_digest(Path(__file__)),
        'calls': calls,
        'lines': lines,
    }
    if args.row == 'mixed-control':
        receipt['firings'] = controls()
        receipt['stock_lines'] = stock_lines(args.root, lines)
        assert calls['anchor'] and lines['anchor']
        if args.sha != MEASURED:
            assert all(calls.values())
            assert len(receipt['stock_lines']) == 2 and all(
                x['visits'] for x in receipt['stock_lines'].values()
            )
            assert receipt['firings']['continued'] == [1]
            assert len(receipt['firings']['earlier']) == 1 and math.isclose(
                receipt['firings']['earlier'][0], 0.999999995, abs_tol=3e-12, rel_tol=0
            )
        else:
            assert receipt['firings']['earlier'] == [1]
        return receipt
    script, full = workload(args.row, 'final')
    small, repeat = ROWS[args.row]
    argv = small or full
    script = args.harness / 'scratch/rewrite/b1' / script
    repeat = 1 if args.probe else repeat
    runs = repeat
    if args.row.endswith('tanks'):
        argv = [*argv, '--repeat', str(repeat)]
        runs = 1

    original = engine.read
    samples = []

    def read(record, program, paths, times, *extra, **kwargs):
        rows = original(record, program, paths, times, *extra, **kwargs)
        samples.append([list(map(str, paths)), list(times), [list(value.values) for value in rows]])
        return rows

    clocks = []
    printed = []
    for _ in range(runs):
        sys.argv = [str(script), *argv]
        out = StringIO()
        with redirect_stdout(out):
            if args.probe:
                with patch.object(engine, 'read', read):
                    runpy.run_path(str(script), run_name='__main__')
            else:
                runpy.run_path(str(script), run_name='__main__')
        output = out.getvalue()
        elapsed = re.search(r'(?:run\+record|run with its record|run and record) ([\d.]+) s', output)
        assert elapsed, output
        clocks.append(float(elapsed[1]))
        if args.row == 'events':
            assert '965 starts; p0 stock 84 L (by hand 84 L)' in output
        if args.row == 'declared':
            assert 'failure: None' in output and '[(0.0, 0), (24.0, 1)]' in output
        printed.append(hashlib.sha256(output.encode()).hexdigest())
    if args.probe:
        assert samples, 'no actual history reads observed'
        receipt['stock_lines'] = stock_lines(args.root, lines)
    receipt.update(
        script=str(script.relative_to(args.harness)),
        argv=argv,
        repeats=repeat,
        script_sha256=file_digest(script),
        output_sha256=printed,
        physical_sha256=fingerprint(samples) if args.probe else None,
        readings=sum(len(row) for _, _, group in samples for row in group),
        batch_seconds=sum(clocks),
        seconds_per_run=sum(clocks) / repeat,
    )
    return receipt


def run_worker(root, sha, args, row, probe, path):
    cmd = [
        sys.executable,
        '-B',
        str(Path(__file__).resolve()),
        'worker',
        '--root',
        str(root),
        '--sha',
        sha,
        '--harness',
        str(args.harness),
        '--row',
        row,
    ]
    if probe:
        cmd.append('--probe')
    assert not path.exists(), f'output already exists: {path}'
    proc = subprocess.run(
        cmd,
        cwd=root,
        env={
            **os.environ,
            **THREAD_ENV,
            'PYTHONPATH': str(root),
            'NAPKIN_STORE': 'off',
            'PYTHONDONTWRITEBYTECODE': '1',
        },
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr[-4000:])
    receipt = json.loads(proc.stdout)
    receipt.update(utc=datetime.now(UTC).isoformat(), host=platform.node(), python=sys.version)
    save(path, receipt)
    return receipt


def campaign(args):
    measured, final = args.measured.resolve(), args.final.resolve()
    args.harness = args.harness.resolve()
    assert identity(measured) == MEASURED and identity(args.harness) == HARNESS
    sha = identity(final)
    other_changes(measured, final)
    roots = {'M': (measured, MEASURED), 'F': (final, sha)}
    args.out.mkdir(parents=True, exist_ok=True)
    if args.guard_dispatch:
        assert not args.probe
        for pair, order in enumerate(('MF', 'FM', 'MF'), start=1):
            for tag in order:
                root, version = roots[tag]
                receipt = run_worker(
                    root,
                    version,
                    args,
                    'guard-dispatch',
                    False,
                    args.out / f'guard-dispatch.{pair}.{tag}.json',
                )
                print(pair, tag, receipt['predicates'], receipt['cold_and_warm_seconds'], flush=True)
        return
    for row in ['mixed-control', *ROWS] if args.probe else ROWS:
        if args.probe:
            readings = {
                tag: run_worker(root, version, args, row, True, args.out / f'{row}.{tag}.probe.json')
                for tag, (root, version) in roots.items()
            }
            if row == 'mixed-control':
                print('positive control', {tag: r['firings'] for tag, r in readings.items()}, flush=True)
            else:
                assert readings['M']['physical_sha256'] == readings['F']['physical_sha256']
                assert len(readings['F']['stock_lines']) == 2
                assert not any(x['visits'] for x in readings['F']['stock_lines'].values())
                if row == 'events':
                    assert readings['M']['calls']['anchor'] == readings['F']['calls']['anchor'] > 0
                else:
                    assert all(not any(r['calls'].values()) for r in readings.values()), readings
                print(
                    row,
                    readings['F']['calls'],
                    'no stock admission or continuation',
                    readings['F']['readings'],
                    'physical samples',
                    flush=True,
                )
        else:
            ratios = []
            for pair, order in enumerate(('MF', 'FM', 'MF'), start=1):
                clocks = {}
                for tag in order:
                    root, version = roots[tag]
                    r = run_worker(
                        root, version, args, row, False, args.out / f'{row}.{pair}.{tag}.time.json'
                    )
                    clocks[tag] = r['seconds_per_run']
                ratios.append(clocks['F'] / clocks['M'])
            print(
                row, 'final/measured median', statistics.median(ratios), 'paired ratios', ratios, flush=True
            )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    w = sub.add_parser('worker')
    w.add_argument('--root', type=Path, required=True)
    w.add_argument('--sha', required=True)
    w.add_argument('--row', choices=[*ROWS, 'mixed-control', 'guard-dispatch'], required=True)
    q = sub.add_parser('campaign')
    q.add_argument('--guard-dispatch', action='store_true')
    for name in ('measured', 'final', 'out'):
        q.add_argument('--' + name, type=Path, required=True)
    for cmd in (q, w):
        cmd.add_argument('--harness', type=Path, required=True)
        cmd.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    if args.action == 'worker':
        print(json.dumps(worker(args)))
    else:
        campaign(args)
