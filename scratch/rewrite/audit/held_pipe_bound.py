"""Lower-bound the full held-pipe clock with one interrupted baseline run (under 3 minutes)."""

import argparse
import json
import math
import os
import platform
import runpy
import signal
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from port_benchmark import THREAD_ENV, check_held_sample, file_digest, identity, workload

BASELINE = '6202824d6d567c34ac46da7b018e66a9c28588b3'
HARNESS = '0f0fcb2a933fdf71a0458a101a4377e1ccb0f44a'
SOURCE = '23c9f60eb10400f078d42fae6bc69e496dfc917cfb2acf3eea05fdd904da7b6d'
CUTOFF = 75


class Cutoff(BaseException):
    """Stop the measured invocation without letting the engine turn the cutoff into a run failure."""


def measure(root, harness):
    if identity(root) != BASELINE or identity(harness) != HARNESS:
        raise ValueError('use the pinned baseline and frozen timing harness')
    name, argv = workload('held-pipes', 'guard')
    script = harness / 'scratch/rewrite/b1' / name
    if file_digest(script) != SOURCE or argv != ['30000', '--full-record-only']:
        raise ValueError('the 30,000-pipe full-record benchmark changed')
    if any(os.environ.get(k) != v for k, v in THREAD_ENV.items()):
        raise ValueError('single-thread BLAS settings are required')
    sys.path.insert(0, str(root))
    import napkin
    from napkin.engine.timeline import Run

    if Path(napkin.__file__).resolve().parent != root / 'napkin':
        raise ValueError('loaded the wrong engine')
    original = Run.run
    elapsed = None
    began = None

    def interrupt(_signal, frame):
        nonlocal elapsed
        observed = time.perf_counter()
        while frame is not None and frame.f_code is not original.__code__:
            frame = frame.f_back
        if frame is None:
            raise RuntimeError('deadline expired outside the original Run.run')
        elapsed = observed - began
        raise Cutoff

    def bounded(machine):
        nonlocal began
        signal.signal(signal.SIGALRM, interrupt)
        signal.setitimer(signal.ITIMER_REAL, CUTOFF)
        began = time.perf_counter()
        try:
            return original(machine)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    sys.argv = [str(script), *argv]
    with patch.object(Run, 'run', bounded), suppress(Cutoff):
        runpy.run_path(str(script), run_name='__main__')
    if elapsed is None or elapsed < CUTOFF - 1:
        raise ValueError('no qualifying in-run elapsed-time lower bound was observed')
    # Round down beyond timestamp/interrupt overhead. Run construction also counts on the official clock.
    lower = math.floor(elapsed - 0.001)
    return {
        'phase': 'guard',
        'row': 'held-pipes',
        'status': 'censored_inside_Run.run',
        'sha': BASELINE,
        'harness_commit': HARNESS,
        'harness_sha256': SOURCE,
        'argv': argv,
        'root': str(root),
        'napkin': napkin.__file__,
        'source': str(script),
        'measurement_sha256': file_digest(Path(__file__)),
        'host': platform.node(),
        'python': sys.version,
        'blas_env': THREAD_ENV,
        'cache': os.environ['NAPKIN_STORE'],
        'time_utc': datetime.now(UTC).isoformat(),
        'inner_timer_seconds': CUTOFF,
        'observed_inside_run_seconds': elapsed,
        'certified_run_record_lower_seconds': lower,
        'completed_run_record_seconds': None,
        'observations': None,
        'warmup_runs': 0,
        'outer_timeout_seconds': 175,
    }


def compare(bound, candidate):
    """Return a strict upper bound using a completed candidate on the same workload and machine."""
    check_held_sample(candidate, 'guard')
    lower = bound['certified_run_record_lower_seconds']
    observed = bound['observed_inside_run_seconds']
    if (
        bound['status'] != 'censored_inside_Run.run'
        or bound['sha'] != BASELINE
        or bound['harness_commit'] != HARNESS
        or bound['harness_sha256'] != SOURCE
        or bound['blas_env'] != THREAD_ENV
        or bound['completed_run_record_seconds'] is not None
        or bound['observations'] is not None
        or bound['warmup_runs'] != 0
        or not 0 < lower < observed
        or lower > math.floor(observed - 0.001)
        or candidate['revision'] != 'F'
        or not math.isfinite(candidate['run_record_seconds'])
        or candidate['run_record_seconds'] <= 0
    ):
        raise ValueError('expected a genuine baseline lower bound and a completed candidate')
    for field in ('phase', 'row', 'argv', 'harness_sha256', 'blas_env', 'host', 'python'):
        if bound[field] != candidate[field]:
            raise ValueError(f'baseline/candidate mismatch in {field}')
    return math.nextafter(candidate['run_record_seconds'] / lower, math.inf)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--harness', type=Path)
    parser.add_argument('--compare', nargs=2, type=Path, metavar=('BOUND_JSON', 'CANDIDATE_JSON'))
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.compare:
        if args.baseline or args.harness or args.worker:
            parser.error('--compare reads already measured samples')
        bound, candidate = (json.loads(path.read_text()) for path in args.compare)
        limit = compare(bound, candidate)
        print(
            f'{candidate["sha"]}: F {candidate["run_record_seconds"]:.9f} s; B > {bound["certified_run_record_lower_seconds"]} s; F/B < {math.ceil(limit * 1e6) / 1e6:.6f}; exact ratio unavailable'
        )
        if limit > 1.05:
            raise SystemExit('the bound is inconclusive for 1.05')
        return
    if not args.baseline or not args.harness:
        parser.error('measurement requires --baseline and --harness')
    root, harness = args.baseline.resolve(), args.harness.resolve()
    if args.worker:
        print(json.dumps(measure(root, harness), indent=2))
        return
    cmd = [
        sys.executable,
        '-B',
        str(Path(__file__).resolve()),
        '--baseline',
        str(root),
        '--harness',
        str(harness),
        '--worker',
    ]
    env = {
        **os.environ,
        **THREAD_ENV,
        'NAPKIN_STORE': 'off',
        'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONPATH': str(root),
    }
    result = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=175, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    print(result.stdout, end='')


if __name__ == '__main__':
    main()
