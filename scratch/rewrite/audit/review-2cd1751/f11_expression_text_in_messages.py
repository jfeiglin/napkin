"""F11. A diagnostic that quotes an expression writes each quantity as the program's internal call
`q(2, 'L')` instead of the model's `2 L`, and an arithmetic error as Python's text ("float division by
zero"): the `max_active` message, a crossing that cannot be certified, a formula that a finished
occurrence could not keep, a division by zero.

Rule: spec.md:664 (the `max_active` diagnostic quotes the gate as the model writes it: "waits at
`until this.cleared`"), spec.md:658 ("Execution errors fail the run with the expression, invocation
and simulation time"), spec.md:52 and 64 (a quantity is a number followed by a unit). Cause:
`napkin/core/expr.text` writes the node as Python (`ast.unparse`), and the engine's messages use it.

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f11_expression_text_in_messages.py
"""

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import compiled, run  # noqa: E402

from napkin.program.config import Limits  # noqa: E402

ACTIVE = '''scenario "Active"
    horizon 10 h

plant:
    water: L = 0 L
    inspect = event():
        when t >= 1 h:
            this.inspect.start()
            reset after 1 h
        until this.water >= 2 L
'''
DIVIDE = '''scenario "Divide"
    horizon 2 h

plant:
    water: L = 2 L
    x = 0
    look = event():
        after 0.5 h:
            this.x = this.water / (this.water - 2 L)

plant.look.start()
'''
RATE = '''scenario "Rate"
    horizon 4 h

tank:
    water: L = 8 L in [0,]
    flow drain: this.water -> SINK
        request = formula(this.water / (2 h))
    alarm = event():
        when this.drain.actual_rate <= 2 L/h:
            this.alarm.start()
            reset when false
'''
c = compiled(ACTIVE)
print('max_active:', run(c.program, replace(c.configuration, limits=Limits(max_active=3))).failure.detail('message'))
c = compiled(DIVIDE)
print('a division by zero:', run(c.program, c.configuration).failure.detail('message'))
c = compiled(RATE)
print('a crossing:', run(c.program, c.configuration).failure.detail('message'))
print("What the rule gives: the model's notation, `until this.water >= 2 L`, `this.water / (this.water - 2 L)`,")
print('`this.drain.actual_rate <= 2 L/h`, and an error that names the division by zero in its words.')
