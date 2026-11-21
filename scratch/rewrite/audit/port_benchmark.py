"""Paired engine benchmarks. See port-benchmark.md for sample invocations and counter definitions."""

import argparse
import ast
from collections import Counter
from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import resource
import runpy
import statistics
import subprocess
import sys
import time
from unittest.mock import patch


THREAD_ENV = dict.fromkeys(
    (
        'OPENBLAS_NUM_THREADS',
        'OMP_NUM_THREADS',
        'MKL_NUM_THREADS',
        'VECLIB_MAXIMUM_THREADS',
        'NUMEXPR_NUM_THREADS',
        'BLIS_NUM_THREADS',
    ),
    '1',
)


def workload(row, phase):
    places, routes = (3000, 3500) if phase == 'prototype' else (30000, 35000)
    if row in ('component-tanks', 'sparse-tanks'):
        return 's1-engine/bench_moving_tanks.py', [
            '--tanks',
            '12',
            '--hours',
            '12',
            '--method',
            row.split('-')[0],
        ]
    if row in ('held-network', 'moving-network'):
        return 's2-engine/bench.py', [row.split('-')[0], str(places), str(routes), '48']
    if row == 'events':
        return 's4a-engine/bench.py', [
            '30000' if phase == 'guard' else '1200',
            '48',
            '12',
        ]
    if row == 'held-pipes':
        return 's1-engine/bench.py', ['30000']
    if row == 'declared':
        return 's5-engine/bench.py', ['3000', '3500', '1500']
    raise ValueError(f'unknown workload {row}')


PHASES = {
    'prototype': [
        'component-tanks',
        'sparse-tanks',
        'held-network',
        'moving-network',
        'events',
    ]
}
PHASES['final'] = [*PHASES['prototype'], 'held-pipes', 'declared']
PHASES['guard'] = ['events']


def git(root, *args):
    return subprocess.check_output(['git', '-C', root, *args], text=True).strip()


def identity(root):
    dirty = git(root, 'status', '--porcelain=v1', '--untracked-files=all', '--', 'napkin')
    if dirty:
        raise RuntimeError(f'benchmark requires pinned engine sources: {root}\n{dirty}')
    return git(root, 'rev-parse', 'HEAD')


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_method():
    frame = sys._getframe(1)
    while frame:
        module = frame.f_globals['__name__']
        if module.startswith('napkin.engine.timeline.'):
            family = module.rsplit('.', 1)[1]
            if family in ('sparse', 'component', 'declared', 'family', 'lines'):
                return family
        frame = frame.f_back
    return 'other'


def primitives(machine, row):
    """A sampled accepted leg and its dedicated sink measure the same transfer independently."""
    if row not in ('component-tanks', 'sparse-tanks', 'moving-network'):
        return {}
    if row.endswith('tanks'):
        selected = [(f'tank{i}.fill', f'tank{i}.water') for i in range(12)]
    else:
        flows = sorted(f for f in machine.plan.flows if f.startswith('places.') and f.endswith('.use'))
        selected = [(f, f.rsplit('.', 1)[0] + '.used') for f in (flows[0], flows[len(flows) // 2], flows[-1])]
    readings = {}
    for flow, store in selected:
        way = machine.ways.sets[machine.ways.set_of[flow]][1]
        if not hasattr(way, 'transferred'):
            continue
        amount, observed = (
            float(way.transferred(flow, machine.now)),
            float(machine.value(store)),
        )
        if not math.isclose(amount, observed, rel_tol=1e-8, abs_tol=1e-10):
            raise AssertionError(f'{flow} accepted {amount}, {store} holds {observed}')
        readings[flow] = [amount, observed]
    return readings


def instrument(stack, row):
    import scipy.integrate._ivp.radau as radau
    from napkin.engine.allocation import Allocation
    from napkin.engine.timeline.network import Instant
    from napkin.engine.timeline import Run

    result = {'by_method': {}, 'primitives': {}, 'solver': 'SciPy Radau'}
    active, current, sizes = False, None, None

    def counts(method):
        return result['by_method'].setdefault(method, Counter())

    def count(owner, name):
        original = getattr(owner, name)

        def wrapped(*args, **kw):
            if active:
                counts(engine_method())[f'{owner.__name__}.{name}'] += 1
            return original(*args, **kw)

        stack.enter_context(patch.object(owner, name, wrapped))

    count(Allocation, 'allocated')
    count(Instant, 'values')
    count(Instant, 'settle')
    try:
        from napkin.engine.continuous.transfers import MovingAmounts
    except ImportError:
        pass
    else:
        original_accept = MovingAmounts.accept

        def accepted(amounts, start, end, amount):
            if active:
                work = counts(engine_method())
                work['accepted_primitive_batches'] += 1
                work['accepted_leg_amounts'] += getattr(amount, 'size', 1)
            return original_accept(amounts, start, end, amount)

        stack.enter_context(patch.object(MovingAmounts, 'accept', accepted))

    original_step = radau.Radau.step

    def step(solver):
        nonlocal current, sizes
        if not active:
            return original_step(solver)
        current, sizes = engine_method(), []
        old = solver.t
        try:
            message = original_step(solver)
            success = int(solver.t > old)
            work = counts(current)
            work['step_attempts'] += len(sizes)
            work['accepted_steps'] += success
            if success and not sizes:
                raise AssertionError('Radau advanced without a recorded trial')
            work['rejected_steps'] += len(sizes) - success
            return message
        finally:
            current, sizes = None, None

    stack.enter_context(patch.object(radau.Radau, 'step', step))
    original_solve = radau.solve_collocation_system

    def collocate(fun, t, y, h, *args, **kw):
        if sizes is not None and (not sizes or sizes[-1] != h):
            sizes.append(h)
        return original_solve(fun, t, y, h, *args, **kw)

    stack.enter_context(patch.object(radau, 'solve_collocation_system', collocate))

    original_init = Run.__init__
    original_run = Run.run
    finished = False

    def construction(machine, *args, **kwargs):
        nonlocal active
        active = not finished
        return original_init(machine, *args, **kwargs)

    stack.enter_context(patch.object(Run, '__init__', construction))

    def measured(machine, *args, **kw):
        nonlocal active, finished
        if finished:
            return original_run(machine, *args, **kw)  # s1 also runs a narrow record, outside its benchmark
        active = True
        try:
            rec = original_run(machine, *args, **kw)
        finally:
            active = False
        if rec.failure:
            raise AssertionError(rec.failure)
        result['primitives'] = primitives(machine, row)
        finished = True
        return rec

    stack.enter_context(patch.object(Run, 'run', measured))
    return result


def worker(args):
    root = Path(args.root).resolve()
    if identity(root) != args.sha:
        raise RuntimeError(f'engine moved from {args.sha}')
    sys.path.insert(0, str(root))
    import napkin
    import scipy
    import numpy

    module = Path(napkin.__file__).resolve()
    if module.parent != root / 'napkin':
        raise RuntimeError(f'loaded {module} instead of {root}/napkin')
    name, argv = workload(args.row, args.phase)
    path = Path(args.harness) / 'scratch/rewrite/b1' / name
    sys.argv = [str(path), *argv]
    if args.row.endswith('tanks'):
        sys.argv.extend(['--repeat', str(args.repeat)])
    if any(os.environ.get(k) != v for k, v in THREAD_ENV.items()):
        raise RuntimeError('single-thread BLAS environment not set')
    started = time.monotonic()
    with ExitStack() as stack:
        counters = instrument(stack, args.row) if args.diagnostic else None
        run_only = []
        if args.phase == 'guard':
            from napkin.engine.timeline import Run

            original = Run.run

            def guard_clock(machine):
                began = time.perf_counter()
                record = original(machine)
                run_only.append(time.perf_counter() - began)
                return record

            stack.enter_context(patch.object(Run, 'run', guard_clock))
        output = io.StringIO()
        with redirect_stdout(output):
            runpy.run_path(str(path), run_name='__main__')
    log = output.getvalue()

    def seconds(expression, required=True):
        match = re.search(expression + r' (\d+(?:\.\d+)?) s', log)
        if not match and required:
            raise ValueError(f'missing {expression} in {log}')
        return float(match[1]) if match else None

    elapsed = seconds(r'(?:run\+record|run with its record|run and record)')
    if args.row == 'declared' and not all(
        token in log
        for token in (
            'failure: None',
            '3163.7587 W',
            '3083.5128 W',
            '[(0.0, 0), (24.0, 1)]',
        )
    ):
        raise AssertionError(log)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    samples = {}
    if args.row.endswith('-network'):
        for path_name, numbers in re.findall(r'^\s+(places\.\S+) (\[[^\]]+\])$', log, re.MULTILINE):
            samples[path_name] = ast.literal_eval(numbers)
        if len(samples) != 3:
            raise ValueError(f'missing network observations: {log}')
    if args.row == 'events':
        expected_starts = 482500 if args.phase == 'guard' else 19300
        if f'{expected_starts} starts; p0 stock 84 L' not in log:
            raise AssertionError(log)
    result = {
        'observations': samples,
        'sha': args.sha,
        'root': str(root),
        'napkin': str(module),
        'row': args.row,
        'phase': args.phase,
        'source': str(path),
        'harness_sha256': file_digest(path),
        'argv': sys.argv[1:],
        'repeat': args.repeat,
        'batch_seconds': elapsed,
        'run_record_seconds': elapsed / args.repeat,
        'build_seconds': seconds('build', False),
        'plan_seconds': seconds('plan', False),
        'peak_rss_bytes': peak,
        'wall_seconds': time.monotonic() - started,
        'counters': counters,
        'guard_run_only_seconds': run_only,
        'output': log,
        'host': platform.node(),
        'python': sys.version,
        'numpy': numpy.__version__,
        'scipy': scipy.__version__,
        'time_utc': datetime.now(timezone.utc).isoformat(),
        'blas_env': THREAD_ENV,
    }
    print(json.dumps(result))


def save(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def read(path):
    return json.loads(path.read_text())


def take(path, args, row, tag, root, sha, repeat, diagnostic=False):
    source = Path(args.harness) / 'scratch/rewrite/b1' / workload(row, args.phase)[0]
    if path.exists():
        existing = read(path)
        if (
            existing['sha'],
            existing['row'],
            existing['repeat'],
            existing['harness_sha256'],
            existing['phase'],
            existing['counters'] is not None,
        ) != (sha, row, repeat, file_digest(source), args.phase, diagnostic):
            raise RuntimeError(f'different identity/options for persisted sample: {path}')
        return existing
    print(
        f'{datetime.now().isoformat(timespec="seconds")} {path.name}: {tag} {sha[:8]} {row}, repeat {repeat}',
        flush=True,
    )
    cmd = [
        sys.executable,
        '-B',
        __file__,
        'worker',
        '--root',
        str(root),
        '--sha',
        sha,
        '--row',
        row,
        '--phase',
        args.phase,
        '--repeat',
        str(repeat),
        '--harness',
        args.harness,
    ]
    if diagnostic:
        cmd.append('--diagnostic')
    environment = {
        **os.environ,
        **THREAD_ENV,
        'NAPKIN_STORE': 'off',
        'PYTHONPATH': str(root),
        'PYTHONDONTWRITEBYTECODE': '1',
    }
    process = subprocess.run(cmd, cwd=root, env=environment, text=True, capture_output=True)
    if process.returncode:
        path.with_suffix('.failure.txt').write_text(process.stdout + process.stderr)
        raise RuntimeError(f'{path.name}: worker exited {process.returncode}: {process.stderr[-900:]}')
    data = json.loads(process.stdout)
    data['revision'] = tag
    save(path, data)
    print(
        f'  {data["run_record_seconds"]:.6f} s, RSS {data["peak_rss_bytes"] / 2**20:.1f} MiB',
        flush=True,
    )
    return data


def campaign(args):
    revisions = {}
    for entry in args.revision:
        tag, raw = entry.split('=', 1)
        root = Path(raw).resolve()
        if tag not in ('B', 'A', 'P', 'F') or tag in revisions:
            raise ValueError(f'invalid/duplicate revision {tag}')
        revisions[tag] = root, identity(root)
    names = [tag for tag in ('B', 'A', 'P', 'F') if tag in revisions]
    rows = args.rows or PHASES[args.phase]
    if any(r not in PHASES[args.phase] for r in rows):
        raise ValueError(f'{rows} do not belong to {args.phase}')
    if args.phase == 'guard' and args.mode == 'diagnostics':
        raise ValueError('do not repeat the full event workload for counters')
    folder = Path(args.out).resolve() / args.phase
    folder.mkdir(parents=True, exist_ok=True)
    args.harness = str(Path(args.harness).resolve())
    with (folder / 'campaign.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for row in rows:
            if args.mode == 'timing' and args.phase != 'guard':
                path = folder / f'{row}.schedule.json'
                schedule = {
                    'revisions': {tag: revisions[tag][1] for tag in names},
                    'alternating_order': names,
                    'driver_sha256': file_digest(Path(__file__)),
                    'source_sha256': file_digest(
                        Path(args.harness) / 'scratch/rewrite/b1' / workload(row, args.phase)[0]
                    ),
                    'host': platform.node(),
                    'python': sys.version,
                    'blas_env': THREAD_ENV,
                }
                if path.exists() and read(path) != schedule:
                    raise ValueError(f'schedule or harness changed; use another output folder for {row}')
                if not path.exists():
                    save(path, schedule)
            if args.mode == 'diagnostics':
                for tag in names:
                    take(
                        folder / f'{row}.{tag}.diagnostic.json',
                        args,
                        row,
                        tag,
                        *revisions[tag],
                        1,
                        True,
                    )
                continue
            repeat = 1
            if row.endswith('tanks'):
                if 'B' not in revisions:
                    raise ValueError('calibrated tank batches require pinned B')
                pilot = take(
                    folder / f'{row}.B.calibration.json',
                    args,
                    row,
                    'B',
                    *revisions['B'],
                    1,
                )
                repeat = max(1, math.ceil(1.5 / pilot['batch_seconds']))
            for pair in range(1, (1 if args.phase == 'guard' else 3) + 1):
                for tag in names if pair % 2 else reversed(names):
                    take(
                        folder / f'{row}.{pair}.{tag}.json',
                        args,
                        row,
                        tag,
                        *revisions[tag],
                        repeat,
                    )


def summary(args):
    folder = Path(args.out).resolve() / args.phase
    pairs = 1 if args.phase == 'guard' else 3
    failed = False
    for row in args.rows or PHASES[args.phase]:
        tagged = {}
        for file in sorted(folder.glob(f'{row}.*.*.json')):
            _, n, tag, _ = file.name.split('.')
            if n.isdigit():
                tagged.setdefault(tag, {})[int(n)] = read(file)
        required = [('A', 'B'), ('P', 'B'), ('P', 'A')] if args.phase == 'prototype' else [('F', 'B')]
        for numerator, denominator in required:
            if numerator not in tagged or denominator not in tagged:
                raise ValueError(f'missing {row}: {numerator}/{denominator}')
            left, right = tagged[numerator], tagged[denominator]
            if set(left) != set(range(1, pairs + 1)) or set(right) != set(left):
                raise ValueError(f'incomplete {row} {numerator}/{denominator}')
            for i, candidate in left.items():
                lhs, rhs = candidate.get('observations', {}), right[i].get('observations', {})
                if lhs.keys() != rhs.keys() or any(
                    not math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-6)
                    for path in lhs
                    for a, b in zip(lhs[path], rhs[path], strict=True)
                ):
                    raise ValueError(f'{row} pair {i} changed sampled results: {lhs} vs {rhs}')
            for sample in [*left.values(), *right.values()]:
                if sample['batch_seconds'] < 1:
                    raise ValueError(f'batch below 1 s for {row}, {sample["sha"]}; recalibrate and rerun')
            for key in (
                ('run_record_seconds', 'total_seconds') if row == 'declared' else ('run_record_seconds',)
            ):

                def metric(sample):
                    return (
                        sample[key]
                        if key != 'total_seconds'
                        else sum(
                            sample[k]
                            for k in (
                                'build_seconds',
                                'plan_seconds',
                                'run_record_seconds',
                            )
                        )
                    )

                ratio = statistics.median(metric(left[i]) / metric(right[i]) for i in left)
                limit = 1.10 if args.phase == 'guard' else 1.05
                status = 'diagnostic' if denominator == 'A' else 'pass' if ratio <= limit else 'FAIL'
                failed |= status == 'FAIL'
                print(
                    row,
                    key,
                    numerator + '/' + denominator,
                    f'{ratio:.6f}',
                    status,
                    'pairs',
                    [(round(metric(right[i]), 6), round(metric(left[i]), 6)) for i in sorted(left)],
                    'peak MiB denominator/numerator',
                    round(max(d['peak_rss_bytes'] for d in right.values()) / 2**20, 1),
                    round(max(d['peak_rss_bytes'] for d in left.values()) / 2**20, 1),
                )
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    for action in ('campaign', 'summary', 'worker'):
        cmd = actions.add_parser(action)
        cmd.add_argument('--phase', choices=PHASES, required=True)
        if action != 'summary':
            cmd.add_argument('--harness', default=str(Path(__file__).resolve().parents[3]))
        if action == 'worker':
            cmd.add_argument('--root', required=True)
            cmd.add_argument('--sha', required=True)
            cmd.add_argument('--row', required=True)
            cmd.add_argument('--repeat', type=int, default=1)
            cmd.add_argument('--diagnostic', action='store_true')
        else:
            cmd.add_argument('--out', required=True)
            cmd.add_argument('--rows', nargs='+')
        if action == 'campaign':
            cmd.add_argument('--revision', action='append', required=True, metavar='B=PATH')
            cmd.add_argument('--mode', choices=('timing', 'diagnostics'), default='timing')
    args = parser.parse_args()
    return {'worker': worker, 'summary': summary, 'campaign': campaign}[args.action](args)


if __name__ == '__main__':
    sys.exit(main())
