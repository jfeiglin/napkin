"""F09. A trigger whose condition reads a declared solver's result that moves between moments (the
solver's input is a store that a flow drains) fires only at the next moment, here the horizon, and
says nothing: `when this.staffing.care <= 60 h` fires at 4 h, while care reaches 60 h at 10/7 h. The
same condition written over the same quantity as a formula (`0.7 * this.staff_hours`) or over the
store fires at 10/7 h.

Rule: spec.md:674 ("A trigger fires when its condition first becomes true ... between any scheduled
events. The same holds for a supported condition that reads a solved value, such as a rate that a
solver publishes ... It never falls back to polling in silence, because that would move the time of
the event"); G0, "Fire triggers when their condition first becomes true" ("For a supported continuous
condition, including one that reads a solved value, find the first qualifying crossing even between
scheduled events. If the engine cannot certify the first crossing, diagnose it").

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f09_trigger_on_moving_solved_value.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import compiled, read, run  # noqa: E402

MODEL = '''scenario "A trigger on a solved value"
    horizon 4 h

clinic:
    staff_hours: h = 100 h in [0 h,]
    flow attrition: this.staff_hours -> SINK
        request = 10 h/h
    outreach_minimum = formula(0.30 * this.staff_hours)
    care_by_formula = formula(0.7 * this.staff_hours)
    staffing = solver:
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
    fired_at: h = 0 h
    alarm = event():
        when {CONDITION}:
            this.alarm.start()
            reset when false
        after 0 h:
            this.fired_at = t
'''
for condition in ('this.staffing.care <= 60 h', 'this.care_by_formula <= 60 h', 'this.staff_hours <= 85.7142857 h'):
    c = compiled(MODEL.format(CONDITION=condition))
    r = run(c.program, c.configuration)
    fires = [round(float(e.t), 6) for e in r.entries('fire')]
    care = read(r, c.program, ['clinic.staffing.care'], [1.5])[0].values[0]
    print(f'when {condition:34s}: fires at {fires}; failure {r.failure}; care at 1.5 h reads {care}')
print('What the rule gives: each condition first holds at 10/7 h = 1.428571 h, so each fires there.')
