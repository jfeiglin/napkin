"""F12. `napkin.engine.run` raises SciPy's `ValueError: f(a) and f(b) must have different signs` (no
record, no diagnostic) when a declared solver reads a store that a flow fills to its upper bound
exactly at a moment: the horizon (5 h), or a stage due then with a later horizon. A horizon of 4.5 h
or 6 h with no stage at 5 h finishes, and so does the same model with the solver's answer written as
a formula. The same area as F10 (a declared solver whose input moves to a bound,
`engine/timeline/declared.py`, `_segment`: the root-finding of solve_ivp's events).

Rule: spec.md:19 and D0 (a supported feasible problem has its answer, or the run stops with a
diagnostic that names the step); spec.md:662 (the horizon is an inclusive cutoff: work due at it
settles under the same rules); spec.md:658 (execution errors fail the run with the expression,
invocation and time).

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f12_solver_bound_at_a_moment_crash.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import compiled, read, run  # noqa: E402

MODEL = '''scenario "A solver whose input fills"
    horizon {HORIZON}

clinic:
    staff_hours: h = 0 h in [0 h, 50 h]
    flow hire: SOURCE -> this.staff_hours
        request = 10 h/h
    cap: h = 40 h
    staffing = solver:
        inputs:
            available = this.staff_hours
            cap = this.cap
        solve_for:
            care: h in [0 h, cap]
        constraints:
            care <= available
        objective:
            maximize(care)
{TICK}'''
TICK = '''    tick = event():
        after 5 h:
            this.cap = 40 h

clinic.tick.start()
'''
for horizon, tick in (('4.5 h', ''), ('6 h', ''), ('5 h', ''), ('8 h', TICK)):
    c = compiled(MODEL.format(HORIZON=horizon, TICK=tick))
    label = f'horizon {horizon}' + (' with a stage due at 5 h' if tick else '')
    try:
        r = run(c.program, c.configuration)
        care = read(r, c.program, ['clinic.staffing.care'], [4])[0].values[0]
        print(f'{label:32s} finished: {r.failure is None}; care at 4 h {care}')
    except Exception as error:  # noqa: BLE001
        print(f'{label:32s} raises {type(error).__name__}: {error}')
print('What the rule gives: every run finishes; staff_hours reaches 50 h at 5 h and care is 40 h from 4 h.')
