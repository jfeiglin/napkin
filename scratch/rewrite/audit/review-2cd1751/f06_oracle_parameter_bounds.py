"""F06. The reference interpreter does not check an event parameter's declared range: it runs a start
whose argument is outside it to the horizon, while the engine fails the run at the start, as the spec
says. A witness that every test leans on agrees with a model that must fail.

Rule: spec.md:572 ("Check declared parameter types, units and entry bounds"). Cause:
`tests/reference/from_program.py` gives the oracle's event only its parameters' names
(`[each.name for each in event.params]`), and `tests/reference/run.Run._register` copies the
arguments with no range.

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f06_oracle_parameter_bounds.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import compiled, oracle, oracle_value, read, run  # noqa: E402

MODEL = '''scenario "Param"
    horizon 4 h

plant:
    got: L = 0 L
    take = event(amount: L in [0 L, 10 L]):
        after 1 h:
            this.got += amount

plant.take.start(20 L)
'''
c = compiled(MODEL)
r = run(c.program, c.configuration)
print('engine:', r.failure and (float(r.failure.t), r.failure.detail('message')))
o, failed = oracle(c)
print('reference interpreter: failure', failed, '| plant.got at 2 h:', oracle_value(c, o, 'plant.got', 2))
print('What the rule gives: the run fails at 0 h, the argument 20 L being outside [0 L, 10 L].')
