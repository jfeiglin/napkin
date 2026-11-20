"""F07. At a stop, `Session.view` of a declared solver's result crashes (AttributeError: 'Solver' object
has no attribute 'kind'), and so does `napkin play --value clinic.staffing.care`. The same cause as F01
on another path: the session's `_declared` resolves `clinic.staffing.care` to the solver part.

Rule: PLAN change 15 (a checkpoint shows "the values that the caller asks for, each in its declared
unit with its label"; `napkin.session.Session.view`: "a path that names no value is a KeyError");
spec.md:448 (`clinic.staffing.care` is a value, 70 h). Cause: `napkin/session.py`, `_declared` and
`_shown` (`part.kind` of a `Solver`).

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f07_view_solver_result.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LITRE, cli, compiled, package  # noqa: E402

from napkin.program.checkpoint import Breakpoint  # noqa: E402
from napkin.session import Session  # noqa: E402

MODEL = '''scenario "Staffing"
    horizon 2 h

clinic:
    staff_hours: h = 100 h  @r
        "Staff hours"
    staffing = solver:
        inputs:
            available = this.staff_hours
        solve_for:
            care: h in [0 h, available]
            outreach: h in [30 h, available]
        constraints:
            care + outreach == available
        objective:
            maximize(care)
    cut = event():  @r
        after 1 h:
            this.staff_hours = 80 h

clinic.cut.start()

record r: assumption "A fixture."
'''
c = compiled(MODEL)
s = Session(c.program, c.configuration, (Breakpoint('clinic.cut.step[0]'),), table=c.table)
s.advance()
try:
    print('view:', s.view(['clinic.staffing.care']).values)
except Exception as error:  # noqa: BLE001
    print('Session.view([clinic.staffing.care]) raises', type(error).__name__ + ':', error)
with tempfile.TemporaryDirectory() as d:
    folder = package(Path(d) / 'staff', {'model.scn': MODEL, 'units.json': LITRE})
    import os
    import subprocess
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[4]), 'NAPKIN_STORE': 'off'}
    done = subprocess.run([sys.executable, '-m', 'napkin', 'play', str(folder), '--break', 'clinic.cut.step[0]',
                           '--value', 'clinic.staffing.care'], input='go\n', capture_output=True, text=True, env=env)
    print('napkin play --value clinic.staffing.care: exit', done.returncode, '|', done.stderr.strip().splitlines()[-1])
print('What the rule gives: the stop shows clinic.staffing.care = 70 h (not editable).')
