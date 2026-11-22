"""Read aggregate historical workforce and AI-adoption equations from the pinned interpreter.

python scratch/rewrite/a5/compare_strategic_workforce.py /path/to/8488047 > reference.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REVISION = '8488047dbb7eafee1f5582cf59839c6bea0cf8cd'
YEARS = (0, 1, 4, 10, 12, 15, 25)
STAFF = (
    'leadership.experts',
    'researchers.people',
    'operators.people',
    'collection_specialists.people',
    'analysts.people',
    'analysts.capacity',
)
OUTPUTS = ('ai_tools.progress', 'ai_tools.payload_progress', 'defenders.hardening', 'defenders.closing')


def read_reference():
    import napkin
    from napkin.core import expr
    from napkin.dynamics import vector_field

    assert Path(napkin.__file__).resolve().parent.parent == Path.cwd()
    model = napkin.load_scenario('scenarios/cyber_learning_loop/model.scn')
    runs = {}
    payrolls = {}
    for name in model.runs:
        field = vector_field(model, name)
        # Each reported time function depends only on time and its named configuration.
        # Payroll groups are read at initialization; no historical trajectory is advanced.
        outputs = field.field.values_program([expr.ref(key) for key in OUTPUTS])
        runs[name] = [list(map(float, outputs(t * 8760, field.base))) for t in YEARS]
        payroll = field.field.values_program([expr.ref(key) for key in STAFF])
        counts = dict(zip(STAFF, map(float, payroll(0, field.base)), strict=True))
        payrolls[name] = counts
    brief = Path('scenarios/cyber_learning_loop/results/brief.md').read_text()
    table = brief.split('| Pathway | Attacks made since the start |', 1)[1].split('\n\n', 1)[0]
    totals = {
        label: int(count.replace(',', ''))
        for label, count in re.findall(r'^\| ([^|]+?) \| ([0-9,]+) operations \|', table, re.MULTILINE)
    }
    assert len(totals) == len(model.runs)
    published = {name: totals[info['name']] for name, info in model.runs.items()}
    return {
        'revision': REVISION,
        'years': YEARS,
        'payroll_at_zero': payrolls,
        'outputs': OUTPUTS,
        'published_total_operations': published,
        'runs': runs,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('legacy', type=Path)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    base = args.legacy.resolve()
    if args.worker:
        print(json.dumps(read_reference(), indent=2))
    else:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=base, text=True).strip()
        if (
            revision != REVISION
            or subprocess.run(['git', 'diff', '--quiet', 'HEAD'], cwd=base, check=False).returncode
        ):
            parser.error(f'expected a clean historical checkout at {REVISION}')
        subprocess.run(
            [sys.executable, '-B', Path(__file__).resolve(), base, '--worker'],
            cwd=base,
            env={**os.environ, 'PYTHONPATH': str(base), 'NAPKIN_STORE': 'off'},
            check=True,
        )
