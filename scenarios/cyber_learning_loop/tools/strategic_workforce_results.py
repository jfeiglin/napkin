"""Measure named aggregate outputs and their matched no-AI controls; check the legacy readings.

From the repository root, use `python scenarios/cyber_learning_loop/tools/strategic_workforce_results.py OUTDIR`.
"""

import argparse
import csv
import json
from math import isclose
from pathlib import Path

import napkin
from napkin import store
from napkin.engine import edits_for

FOLDER = Path(__file__).resolve().parents[1]
OUTPUTS = {
    'surveillance_program.completed': 'staff_years',
    'effects_program.completed': 'staff_years',
    'attacks_per_year': 'operations/year',
    'total_attacks': 'operations',
}


def values(record, model, paths, times):
    return {v.path: v.values for v in napkin.read(record, model.program, paths, times)}


def complete(model, name, edits=None):
    config = model.configure(name, edits=edits)
    result = store.run(model.program, config)
    if result.stop is not None or result.end != config.request.horizon:
        raise ValueError(f'{name} stopped at {result.end}: {result.stop}')
    return result


def compare(folder):
    baseline = json.loads((FOLDER / 'tests/strategic-reference.json').read_bytes())
    hours = [year * 8760 for year in baseline['years']]
    model = napkin.load_scenario(FOLDER)
    paths = [
        'ai_tools.review_progress' if p == 'ai_tools.payload_progress' else p for p in baseline['outputs']
    ]
    assert set(baseline['runs']) == {run.name for run in model.declared.runs}
    differences, comparisons, results = [], 0, []
    national_counts = []
    for name, rows in baseline['runs'].items():
        candidate = complete(model, name)
        expected = baseline['payroll_at_zero'][name]
        initial = values(candidate, model, list(expected), [0])
        observations = [(0, path, old, initial[path][0]) for path, old in expected.items()]
        read = values(candidate, model, paths, hours)
        for index, (year, historical) in enumerate(zip(baseline['years'], rows, strict=True)):
            for path, old in zip(paths, historical, strict=True):
                observations.append((year, path, old, read[path][index]))
        for year, path, old, current in observations:
            comparisons += 1
            if old != current:
                reason = (
                    'within floating-point tolerance'
                    if isclose(old, current, rel_tol=1e-10, abs_tol=1e-12)
                    else 'outside tolerance'
                )
                differences.append((name, year, path, old, current, reason))
        changes = edits_for(model, {'runs': {name: {'ai_tools.pace': 0}}})
        control = complete(model, name, changes)
        measured = values(candidate, model, OUTPUTS, [candidate.end])
        matched = values(control, model, OUTPUTS, [control.end])
        old = baseline['published_total_operations'][name]
        (count,) = measured['total_attacks']
        national_counts.append(
            (
                name,
                old,
                count,
                count - old,
                old / baseline['years'][-1],
                count / baseline['years'][-1],
                measured['attacks_per_year'][0],
                'Current count uses fixed average labor per case, availability and annual demand. See the case mapping in README.md.',
            )
        )
        for path in OUTPUTS:
            (actual,), (no_ai,) = measured[path], matched[path]
            results.append(
                (name, path, OUTPUTS[path], actual, no_ai, actual - no_ai, (actual / no_ai - 1) * 100)
            )
    with (folder / 'matched-uptake.csv').open('w', newline='') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(
            [
                'run',
                'quantity',
                'unit',
                'case_value',
                'matched_no_ai_value',
                'difference',
                'difference_percent',
            ]
        )
        writer.writerows(results)
    with (folder / 'historical-operations.csv').open('w', newline='') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(
            [
                'run',
                'legacy_published_operations',
                'current_operations',
                'difference_operations',
                'legacy_mean_operations_per_year',
                'current_mean_operations_per_year',
                'current_endpoint_operations_per_year',
                'reason',
            ]
        )
        writer.writerows(national_counts)
    with (folder / 'workforce-legacy-differences.csv').open('w', newline='') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['run', 'year', 'quantity', 'legacy', 'current', 'reason'])
        writer.writerows(differences)
    print(f'{comparisons} historical comparisons, {len(differences)} changed readings')
    return all(d[-1] != 'outside tolerance' for d in differences)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with store.use(store.default_directory()):
        raise SystemExit(0 if compare(args.output) else 1)
