"""F10. A declared solver whose input is a store that a flow drains to its lower bound makes the whole
run fail at 0 h: the store `staff_hours: h = 100 h in [0 h,]` drains at 10 h/h and empties at 10 h,
where the staffing problem is feasible (care = outreach = 0 h). With a horizon of 10 h the engine
reports "cannot answer at t = 10 h: ... upper bound -2.66e-15" (a roundoff), with a horizon past it
"cannot answer at t = 10.0044 h: ... upper bound -0.0443" (a trial state past the store's bound);
in both the failure entry is at 0 h and every value after 0 h is unavailable. With a horizon of 9.99 h
the same model finishes. Without the solver the store drains to 0 h and stays there.

Rule: D0 / spec.md:19 ("Every supported feasible problem with finite ranked optima has one selected
answer, or the run stops with a diagnostic that names the step"); spec.md:252 (a store's interval is
an inventory bound: at its lower bound withdrawals stop); spec.md:279 (a rate may follow a moving
quantity in a model of any size); spec.md:542 (continuous integration can evaluate a solver at trial
states, separately from the once-per-round rule); spec.md:658 (an execution error names its time);
PLAN change 10 (bounds are kept exactly; a near-tie is detected and reported).

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f10_solver_input_drains_to_bound.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import compiled, read, run  # noqa: E402

MODEL = '''scenario "A solver whose input drains"
    horizon {HORIZON}

clinic:
    staff_hours: h = 100 h in [0 h,]
    flow attrition: this.staff_hours -> SINK
        request = 10 h/h
    outreach_minimum = formula(0.30 * this.staff_hours)
{SOLVER}'''
SOLVER = '''    staffing = solver:
        inputs:
            available = this.staff_hours
            minimum_outreach = this.outreach_minimum
        solve_for:
            care: h in [0 h, available]
            outreach: h in [minimum_outreach, available]
        constraints:
            care + outreach == available
        objective:
            maximize(care)
'''
for horizon, solver in (('9.99 h', SOLVER), ('10 h', SOLVER), ('12 h', SOLVER), ('12 h', '')):
    c = compiled(MODEL.format(HORIZON=horizon, SOLVER=solver))
    r = run(c.program, c.configuration)
    f = r.failure
    what = 'finished' if f is None else f'failure entry at {float(f.t):g} h: {f.detail("message")}'
    water = read(r, c.program, ['clinic.staff_hours'], [5])[0].values[0]
    print(f'horizon {horizon:7s} {"with" if solver else "without"} the solver: {what}')
    print(f'   staff_hours at 5 h: {water}')
print('What the rule gives: with the solver, every horizon finishes; staff_hours is 50 h at 5 h and 0 h from')
print('10 h, and the solver answers care = 70 % of it, 0 h from 10 h.')
# The second part: a solve that is truly infeasible later (outreach of at least 30 h once fewer than
# 30 h remain, at 7 h) is also put at 0 h, with the time of a trial state past it.
LATER = MODEL.format(HORIZON='12 h', SOLVER=SOLVER).replace('[minimum_outreach, available]', '[30 h, available]')
c = compiled(LATER)
r = run(c.program, c.configuration)
print('A solve that is infeasible from 7 h on: failure entry at', float(r.failure.t), 'h:', r.failure.detail('message'))
print('   staff_hours at 5 h:', read(r, c.program, ['clinic.staff_hours'], [5])[0].values[0])
print('What the rule gives: the run fails at 7 h, naming that time, and its record holds the values to 7 h.')
