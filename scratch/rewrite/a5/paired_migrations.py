"""Compare the pinned piano draws and reservoir sweep. Run from any Napkin checkout.

    .venv/bin/python scratch/rewrite/a5/paired_migrations.py --candidate HEAD

Each engine runs in its own process from a Git archive. This script does not write either model.
"""

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import replace
from fractions import Fraction as F
from itertools import product
from pathlib import Path

LEGACY = '8488047dbb7eafee1f5582cf59839c6bea0cf8cd'
HERE = Path(__file__).resolve()
PIANO = Path('examples/piano_tuners/model.scn')
RESERVOIR = Path('examples/reservoir/model.scn')
A5 = Path('scratch/rewrite/a5')
PIANO_TIMES = (0, 4380, 8760)
RESERVOIR_TIMES = (0, 24, 40, 60, 80, 96, 120)
SWEEP = tuple(product(('0.03', '0.06'), ('0.06', '0.15'), ('0.6', '0.7', '0.8')))
PIANO_UNITS = {
    'tuners.rate': 'tunings/tuner/year',
    'tuners.due': 'tunings',
    'tuners.done': 'tunings',
    'tunings_done': 'tunings',
}
RESERVOIR_UNITS = {'reservoir.water': 'fraction', 'reservoir.spilled': 'fraction', 'reservoir.risk_time': 'h'}


def reservoir_inputs(conditions):
    return dict(
        zip(('reservoir.inflow', 'reservoir.spillway', 'reservoir.risk'), map(float, conditions), strict=True)
    )


def old_data(root):
    from napkin import evaluate_study, evaluate_uncertainty
    from napkin.engine import SamplingSettings, edits_for
    from napkin.engine.report import outputs_until
    from napkin.model import load_scenario
    from napkin.model.ir import thaw

    def state(model, completed, times, units):
        trajectory = completed['trajectory']
        assert not trajectory.paused and trajectory.end_time == times[-1], trajectory.trace
        outputs = outputs_until(completed, thaw(model.library), times)
        assert [row['t'] for row in outputs] == list(times)
        values = {}
        (structure,) = model.structures.values()
        for name, unit in units.items():
            if name in model.outputs:
                key = model.outputs[name]
                assert structure.outcomes[key].unit == unit
                assert all(row['statuses'][key] == 'estimated' for row in outputs), (name, outputs)
                values[name] = [row['values'][key] for row in outputs]
            else:
                # env_at is in canonical hours. The legacy model's written piano rate is per tuner-year.
                if name == 'tuners.rate':
                    scale = 8760
                else:
                    assert structure.quantities[name].unit == unit
                    scale = 1
                values[name] = [trajectory.env_at(t)[name] * scale for t in times]
        return values

    piano = load_scenario(root / PIANO)
    assert piano.inputs['tuners.rate']['unit'] == 'tunings/tuner-year'
    result = {'piano': [], 'reservoir': []}
    for seed in range(12):
        study = evaluate_uncertainty(piano, None, SamplingSettings(1, seed=seed))
        assert study.admissible, study.diagnostics
        sample = study.samples['base']
        draw = sample['values'][0]['tuners.rate']
        result['piano'].append([draw, state(piano, sample['runs'][0], PIANO_TIMES, PIANO_UNITS)])
    reservoir = load_scenario(root / RESERVOIR)
    assert [reservoir.inputs['reservoir.' + name]['unit'] for name in ('inflow', 'spillway', 'risk')] == [
        'fraction/day',
        'fraction/day',
        'fraction',
    ]
    for conditions in SWEEP:
        edits = edits_for(reservoir, {'set': reservoir_inputs(conditions)})
        study = evaluate_study(reservoir, edits)
        assert study.admissible, (conditions, study.diagnostics)
        result['reservoir'].append(state(reservoir, study.runs['base'], RESERVOIR_TIMES, RESERVOIR_UNITS))
    return result


def compare_new(root, old):
    from check import agree

    import napkin

    maxima = {}

    def equal(key, case, name, unit, at, actual, expected):
        assert agree(float(actual), float(expected)), (key, case, name, unit, at, actual, expected)
        label = f'{key} {name} [{unit}]'
        maxima[label] = max(maxima.get(label, 0.0), abs(actual - float(expected)))

    def readings(model, edits, paths, times, seed=None):
        configuration = model.configure(
            edits={'schema_version': napkin.SCHEMA_VERSION, 'model_hash': model.model_hash, 'set': edits}
        )
        if seed is not None:
            configuration = replace(configuration, mode='sampled', seed=seed)
        record = napkin.run(model.program, configuration)
        assert record.failure is None and record.end == times[-1], (edits, record.failure, record.end)
        rows = napkin.read(record, model.program, list(paths), times)
        for row in rows:
            assert row.unit == paths[row.path], (edits, row.path, row.unit)
        return {row.path: row.values for row in rows}

    piano = napkin.load_scenario(root / PIANO)
    assert len(set(draw for draw, _ in old['piano'])) == 12
    for seed, (draw, previous) in enumerate(old['piano']):
        assert 600 <= draw <= 1200, (seed, draw)
        paths = {**PIANO_UNITS, 'tuners.tune.actual_rate': 'tunings/h'}
        found = readings(piano, {'tuners.rate': draw}, paths, PIANO_TIMES, seed)
        for i, at in enumerate(PIANO_TIMES):
            done = 3 * draw * at / 8760
            exact = {
                'tuners.rate': draw,
                'tuners.due': 5000 - done,
                'tuners.done': done,
                'tunings_done': done,
            }
            for name, unit in PIANO_UNITS.items():
                equal('old/new', seed, name, unit, at, found[name][i], previous[name][i])
                equal('old/analytic', seed, name, unit, at, previous[name][i], exact[name])
                equal('new/analytic', seed, name, unit, at, found[name][i], exact[name])
            equal(
                'new/analytic',
                seed,
                'tuners.tune.actual_rate',
                'tunings/h',
                at,
                found['tuners.tune.actual_rate'][i],
                3 * draw / 8760,
            )
            if i:
                # The old public trajectory retains balances. For this continuously working pipe
                # either interval's change in completed tunings gives its realized constant rate.
                interval_rate = (previous['tuners.done'][i] - previous['tuners.done'][i - 1]) / (
                    at - PIANO_TIMES[i - 1]
                )
                equal(
                    'old/new',
                    seed,
                    'tuners.tune.actual_rate',
                    'tunings/h',
                    at,
                    found['tuners.tune.actual_rate'][i],
                    interval_rate,
                )

    reservoir = napkin.load_scenario(root / RESERVOIR)
    for conditions, previous in zip(SWEEP, old['reservoir'], strict=True):
        inflow, spillway, risk = map(F, conditions)
        incoming, outgoing = inflow / 24, spillway / 24
        initial, level = F('0.6'), F('0.7')
        opening = (level - initial) / incoming
        found = readings(reservoir, reservoir_inputs(conditions), RESERVOIR_UNITS, RESERVOIR_TIMES)
        for i, at in enumerate(RESERVOIR_TIMES):
            shut, open_ = min(at, opening), max(0, at - opening)
            water = initial + incoming * shut + (incoming - outgoing) * open_
            # Duration above threshold on each linear segment, including an exactly flat segment.
            hours = max(0, shut - max(0, (risk - initial) / incoming))
            fall = outgoing - incoming
            if fall:
                hours += max(0, min(open_, (level - risk) / fall))
            elif level >= risk:
                hours += open_
            exact = {
                'reservoir.water': water,
                'reservoir.spilled': outgoing * open_,
                'reservoir.risk_time': hours,
            }
            for name, unit in RESERVOIR_UNITS.items():
                equal('old/new', conditions, name, unit, at, found[name][i], previous[name][i])
                equal('old/analytic', conditions, name, unit, at, previous[name][i], exact[name])
                equal('new/analytic', conditions, name, unit, at, found[name][i], exact[name])
    return maxima


def archive(repo, commit, path, paths):
    path.mkdir()
    with tempfile.TemporaryFile() as file:
        subprocess.run(['git', '-C', repo, 'archive', commit, *paths], stdout=file, check=True)
        file.seek(0)
        with tarfile.open(fileobj=file) as tree:
            tree.extractall(path, filter='data')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, help='candidate Git commit to archive')
    args = parser.parse_args()
    repo = HERE.parents[3]
    commit = subprocess.check_output(
        ['git', '-C', repo, 'rev-parse', '--verify', args.candidate + '^{commit}'], text=True
    ).strip()
    with tempfile.TemporaryDirectory(prefix='napkin-migration-') as folder:
        old, new = (Path(folder) / side for side in ('legacy', 'candidate'))
        archive(repo, LEGACY, old, ['napkin', 'examples/piano_tuners', 'examples/reservoir'])
        archive(repo, commit, new, ['napkin', 'examples/piano_tuners', 'examples/reservoir', A5, 'pyproject.toml'])

        def invoke(root, *command, payload=None, expected_code=0):
            env = {**os.environ, 'PYTHONPATH': str(root), 'NAPKIN_BASE': str(old), 'NAPKIN_STORE': 'off'}
            result = subprocess.run(
                [sys.executable, *command],
                cwd=root,
                env=env,
                input=payload,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != expected_code:
                raise RuntimeError(result.stdout + result.stderr)
            return result.stdout

        previous = invoke(old, HERE, '--worker-old')
        maxima = json.loads(invoke(new, HERE, '--worker-new', payload=previous))
        piano = old / PIANO
        for source, target, times in [
            (piano, new / PIANO, [4380]),
            (old / RESERVOIR, new / RESERVOIR, RESERVOIR_TIMES[1:-1]),
        ]:
            invoke(new, new / A5 / 'check.py', source, target, *(v for t in times for v in ('--at', str(t))))
        for suffix, message in [
            ('run', 'FAIL [run] tunings_done at 8760 h'),
            ('outcome', 'FAIL [run] outcome: old finished at 8760 h, new failed at 8760 h'),
        ]:
            target = new / A5 / 'translated/wrong' / f'piano_tuners_{suffix}/model.scn'
            rejected = invoke(new, new / A5 / 'check.py', piano, target, expected_code=1)
            assert message in rejected, rejected
        analytic = invoke(
            new, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', new / A5 / 'test_port_readiness.py'
        )
        print(
            f'legacy {LEGACY}\ncandidate {commit}\n12 paired piano draws at {PIANO_TIMES} h\n12 paired reservoir configurations at {RESERVOIR_TIMES} h'
        )
        print('Both median checks passed. Both negative controls failed for the expected reason.')
        print(analytic.strip().splitlines()[-1])
        print(json.dumps(maxima, indent=2, sort_keys=True))


if __name__ == '__main__':
    if sys.argv[1:] in (['--worker-old'], ['--worker-new']):
        import napkin

        root = Path.cwd()
        assert Path(napkin.__file__).resolve().is_relative_to(root), napkin.__file__
        if sys.argv[1] == '--worker-old':
            print(json.dumps(old_data(root)))
        else:
            # Use the pinned candidate's own migration tolerance and reporting helpers.
            sys.path.insert(0, str(root / A5))
            print(json.dumps(compare_new(root, json.load(sys.stdin))))
    else:
        main()
