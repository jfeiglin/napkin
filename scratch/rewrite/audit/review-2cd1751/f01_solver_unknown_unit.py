"""F01. A solver's own unknown is read with no unit and in canonical units, not in its declared unit.

Rule: spec.md:448 ("`clinic.staffing.care` is 70 h"), spec.md:540 ("A new staffing unknown lives on
the solver"); the reader's contract (`napkin.engine.read`: "each in its declared unit") and the
reference interpreter (`tests/reference/from_program.scale_at`: "of a solver's unknown its type's
unit"). Cause: `engine/timeline/record.declared` resolves the key `clinic.plan.x` to the part `plan`
(the solver), which has no type, so the unit is '' and the scale 1.

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f01_solver_unknown_unit.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LITRE, cli, compiled, oracle, oracle_value, package, read, run  # noqa: E402

from napkin.engine.report import report  # noqa: E402

MODEL = '''scenario "Staff in days"
    horizon 1 h

clinic:
    total: day = 11 h
    plan = solver:
        inputs:
            available = this.total
        solve_for:
            x: day in [0 h, 10 h]
            y: day in [0 h, 100 h]
            z: day in [0 h,]
        constraints:
            x + y + z == available
    xs = formula(this.plan.x + this.plan.y + this.plan.z)
'''

paths = ['clinic.total', 'clinic.plan.x', 'clinic.plan.y', 'clinic.plan.z', 'clinic.xs']
c = compiled(MODEL)
r = run(c.program, c.configuration)
print('napkin.engine.read at 0 h, (unit, value):')
for x in read(r, c.program, paths, [0]):
    print(f'   {x.path:15s} unit {x.unit!r:6s} value {x.values[0]:.6g}')
o, _ = oracle(c)
print('the reference interpreter, in the declared unit:', {p: round(oracle_value(c, o, p, 0), 6) for p in paths})
value = report(r, c.program, c.configuration, ['clinic.plan.x'], [0], model=c.declared).values[0]
print('report: unit', repr(value.unit), 'value', value.values)
with tempfile.TemporaryDirectory() as d:
    folder = package(Path(d) / 'pkg', {'model.scn': MODEL, 'units.json': LITRE})
    code, out, err = cli('run', folder, '--value', ','.join(paths), '--at', '0h')
    print('napkin run (exit %d):' % code)
    print(out)
print('What happens: x + y + z read 11 (no unit) while their sum xs reads 0.458333 day; the CLI shows no')
print('unit for each unknown. What the rule gives: each unknown in day: 0.0045375, 0.45375, 4.5375e-05.')
print('With hours (the staffing example) the number happens to agree but the unit column is empty.')
