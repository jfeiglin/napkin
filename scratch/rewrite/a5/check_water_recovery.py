"""Reproduce the civilian service observations in the checked-in water recovery fixture."""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = Path('scenarios/water_controls_wipe')
FIXTURE = ROOT / PACKAGE / 'tests' / 'recovery-readings.json'
REVISION = '8488047dbb7eafee1f5582cf59839c6bea0cf8cd'


def legacy_values(place, corpus):
    import napkin
    from napkin.engine.report import outputs_until
    from napkin.model.ir import thaw

    assert Path(napkin.__file__).resolve().is_relative_to(Path.cwd())
    model = napkin.load_scenario(PACKAGE / 'variants' / place / 'model.scn')
    study = napkin.evaluate_study(model, runs=[corpus['run']])
    assert study.admissible, study.diagnostics
    run = study.runs[corpus['run']]
    trajectory = run['trajectory']
    assert not trajectory.paused and trajectory.end_time == corpus['hours'][-1]
    samples = outputs_until(run, thaw(model.library), corpus['hours'])
    return {key: [row['values'][model.outputs[key]] for row in samples] for key in corpus['places'][place]}


def main():
    corpus = json.loads(FIXTURE.read_text())
    if sys.argv[1:2] == ['--worker']:
        print(json.dumps(legacy_values(sys.argv[2], corpus)))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('legacy', type=Path, help='checkout of the pinned historical revision')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    base = args.legacy.resolve()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=base, text=True).strip()
    if revision != REVISION or not revision.startswith(corpus['revision']):
        parser.error(f'expected legacy revision {REVISION}, found {revision}')
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    env = {
        **os.environ,
        'PYTHONPATH': str(base),
        'NAPKIN_STORE': 'off',
        'OMP_NUM_THREADS': '1',
        'OPENBLAS_NUM_THREADS': '1',
        'VECLIB_MAXIMUM_THREADS': '1',
    }

    def check(place):
        result = subprocess.check_output(
            [sys.executable, '-B', str(Path(__file__).resolve()), '--worker', place], cwd=base, env=env
        )
        values = json.loads(result)
        for key, expected in corpus['places'][place].items():
            for hour, got, wanted in zip(corpus['hours'], values[key], expected, strict=True):
                if got != wanted:
                    raise ValueError(f'{place} {key} at {hour} h: expected {wanted}, got {got}')
        return sum(map(len, values.values()))

    with ThreadPoolExecutor(args.jobs) as pool:
        count = sum(pool.map(check, sorted(corpus['places'])))
    print(f'{count} historical readings reproduced in {len(corpus["places"])} variants at {revision}')


if __name__ == '__main__':
    main()
