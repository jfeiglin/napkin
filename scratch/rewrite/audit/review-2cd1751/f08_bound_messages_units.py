"""F08. A failure or a refusal at a bound states its numbers in canonical units, with no unit: a move
into a store, an event's argument outside its declared range, and an edit at a stop. A model in mL or
in days reads a number 1000 or 24 times off the one it wrote. The retirement of an occurrence's store
does convert ("still holds 8000 mL"): the rule kept on one path and not on the others.

Rule: spec.md:660 (the failure "reports the stock, amount, unit, occurrence and time"), spec.md:572
(entry bounds are checked), spec.md:899 (a move checks both bounds), PLAN change 15 (an edit is in
the value's declared unit; types and bounds hold); `Session.edit`: "`value` is in its declared unit".
Causes: `Occurrences._enter` (engine/timeline/occurrences.py), the move check of
engine/timeline/moment.py, and `Checkpoints.checked` (engine/timeline/checkpoints.py) format the
canonical numbers; `Occurrences.complete` divides by the unit's scale and names the unit.

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f08_bound_messages_units.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import compiled, run  # noqa: E402

from napkin.program.checkpoint import Breakpoint, CheckpointError  # noqa: E402
from napkin.session import Session  # noqa: E402

MODEL = '''scenario "Moves in mL"
    horizon 4 h

left:
    readonly water: mL = 8000 mL in [0 mL,]
right:
    readonly water: mL = 0 mL in [0 mL, 4000 mL]
    level: day = 1 day in [0 day, 2 day]

mover:
    shift = event(amount: mL in [0 mL, 6000 mL]):
        after 1 h:
            move amount from left.water to right.water

mover.shift.start({AMOUNT})
'''
RETIRE = '''scenario "Retirement in mL"
    horizon 6 h

tank:
    water: mL = 0 mL in [0,]
    deliver = event(amount: L):
        batch: mL = amount in [0,]
        flow pipe: batch -> tank.water
            request = 6 L/h
            capacity = formula(6 L/h if t < 2 h else 0 L/h)
        after 3 h

tank.deliver.start(20 L)
'''
for amount, written in (('5000 mL', 'a move of 5000 mL into [0 mL, 4000 mL]'), ('7000 mL', 'an argument of 7000 mL against [0 mL, 6000 mL]')):
    c = compiled(MODEL.format(AMOUNT=amount))
    r = run(c.program, c.configuration)
    print(f'{written}:\n   {r.failure.detail("message")}')
c = compiled(MODEL.format(AMOUNT='1000 mL'))
s = Session(c.program, c.configuration, (Breakpoint('mover.shift.step[0]'),))
s.advance()
for path, value, written in (('right.water', 5000, '5000 (mL)'), ('right.level', 3, '3 (days)')):
    try:
        s.edit(path, value)
    except CheckpointError as error:
        print(f'an edit of {path} to {written}:\n   {error}')
c = compiled(RETIRE)
print('the retirement of a store in mL (converted):\n   ' + run(c.program, c.configuration).failure.detail('message'))
print('What the rule gives: each number in the unit that the model declares, with that unit: "right.water would')
print('hold 5000 mL, outside its range [0 mL, 4000 mL]", "amount = 7000 mL ... [0 mL, 6000 mL]", "right.level = 3 day')
print('is outside its range [0 day, 2 day]".')
