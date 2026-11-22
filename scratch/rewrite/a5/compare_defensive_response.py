"""Replay the retained defensive equations with the isolated legacy interpreter at 8488047.

From the current checkout, run:
    python scratch/rewrite/a5/compare_defensive_response.py /path/to/8488047

The generated JSON is the historical side of the package's regression test. The legacy interpreter
only loads the small temporary model built here from the selected defensive declarations.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve()
PACKAGE = Path('scenarios/cyber_learning_loop')
BASE = '8488047'
YEAR = 8760
YEARS = [0, 0.25, 0.75, 1, 1.5, 2, 3, 5, 12, 25]
PATHS = [
    'defenders.threat',
    'defenders.attention_target',
    'defenders.alertness',
    'defenders.hardening',
    'defenders.closing',
]
CASES = {
    'reference': {},
    'quiet': {'observations.initial': 0, 'observations.during': 0, 'observations.later': 0},
    'response': {
        'observations.initial': 4,
        'observations.during': 4,
        'observations.later': 4,
        'defenders.hardening_rate': 0.05,
        'defenders.ai_hardening': 0.5,
        'observations.uptake': 0.6,
    },
    'pulse': {'observations.during': 5, 'observations.later': 0.5, 'defenders.calm_rate': 3},
}


def declaration(source, prefix):
    """One selected historical declaration, retaining its expression and replacing its citation."""
    lines = source.splitlines()
    matches = [i for i, line in enumerate(lines) if line.startswith('    ' + prefix)]
    assert len(matches) == 1, prefix
    start = matches[0]
    end = next(i for i in range(start, len(lines)) if '@' in lines[i])
    return '\n'.join([*lines[start:end], lines[end].split('@', 1)[0].rstrip() + '  @fixture'])


def historical_text(source):
    inputs = ['alert_now', 'calm_rate', 'attention_cap', 'hardening_rate', 'ai_hardening', 'close_gain']
    retained = [
        *(declaration(source, f'input {name}:') for name in inputs),
        '    let threat: ratio = observations.pressure  @fixture',
        declaration(source, 'let attention_target:'),
        declaration(source, 'let hardening:').replace('ai_tools.progress', 'observations.uptake'),
        declaration(source, 'let closing:').replace('ai_tools.progress', 'observations.uptake'),
        declaration(source, 'var alertness:'),
        declaration(source, 'flow alert:'),
        declaration(source, 'flow calm:'),
    ]
    return (
        """scenario "Defensive observation replay"
    horizon 25 years
    timescales 1 / defenders.calm_rate
    resolution 7 days
    scope "Aggregate observations of defensive workload."

observations:
    input initial: ratio = 1 in 0 to 20  @fixture
    input during: ratio = 1 in 0 to 20  @fixture
    input later: ratio = 1 in 0 to 20  @fixture
    input uptake: fraction = 0 in 0 to 1  @fixture
    let pressure: ratio = initial if t < 1 years else (during if t < 2 years else later)  @fixture

defenders:
"""
        + '\n'.join(retained)
        + '\n\nrecord fixture: assumption "The historical equation replay."\n'
    )


def legacy(base):
    import napkin
    from napkin.engine import edits_for, evaluate_study
    from napkin.model import load_scenario

    assert Path(napkin.__file__).resolve().parent.parent == base
    sha = subprocess.check_output(['git', '-C', base, 'rev-parse', 'HEAD'], text=True).strip()
    assert sha.startswith(BASE)
    entry = base / PACKAGE / 'model.scn'
    committed = subprocess.check_output(['git', '-C', base, 'show', f'{sha}:{PACKAGE}/model.scn'])
    assert entry.read_bytes() == committed
    block = committed.decode().split('\ndefenders:')[1].split('\n\n')[0]
    text = historical_text(block)
    with TemporaryDirectory() as temporary:
        folder = Path(temporary)
        path = folder / 'model.scn'
        path.write_text(text)
        vocabulary = json.loads((base / 'scenarios/library/vocabulary.json').read_text())['units']
        (folder / 'units.json').write_text(json.dumps({'per_year': vocabulary['per_year']}))
        model = load_scenario(path)
        cases = {}
        for label, edits in CASES.items():
            study = evaluate_study(model, edits_for(model, {'set': edits}))
            assert study.admissible, study.diagnostics
            trajectory = study.runs['base']['trajectory']
            assert not trajectory.paused and trajectory.end_time == 25 * YEAR
            rows = []
            for year in YEARS:
                env = trajectory.env_at(year * YEAR)
                rows.append([float(env[key]) for key in PATHS])
            cases[label] = {'edits': edits, 'rows': rows}
    return {
        'legacy_commit': sha,
        'source_sha256': hashlib.sha256(committed).hexdigest(),
        'retained_fixture_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'years': YEARS,
        'paths': PATHS,
        'cases': cases,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    base = args.base.resolve()
    if args.worker:
        print(json.dumps(legacy(base), indent=2))
    else:
        subprocess.run(
            [sys.executable, '-B', HERE, base, '--worker'],
            cwd=base,
            check=True,
            env={**os.environ, 'PYTHONPATH': str(base), 'NAPKIN_STORE': 'off'},
        )
