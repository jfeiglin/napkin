"""F02. A named value that the model itself does not read is not in the run: a store's
`outflow.actual_rate` (or `inflow`, or `.request`), a distribution's `.mean` and `.std`, a flow's
`.capacity` when it declares none. A caller's read gives `Unavailable` whose reason is the bare path in
quotes (the text of a KeyError); at a stop the reason says the run stopped; `napkin run --value` calls
it "no named value of the model" (exit 2). The same paths read normally as soon as some formula of
the model reads them.

Rule: spec.md:223-224 (a source `Y.outflow` has the read-only `.actual_rate` summed over its outgoing
flows), spec.md:227 (`sum(water.outflow.flows.actual_rate)` equals `water.outflow.actual_rate`),
spec.md:131 and D10 ("Any named value can be reported. The caller selects paths"), spec.md:163
(`.mean` and `.std` describe the distribution), spec.md:235 (the table of deliveries reads
`tank.water.outflow.actual_rate`). Cause: `engine/timeline/plan.py` makes an endpoint (`End`) or a
moment only for what the model names, and `Reader.value` turns the KeyError of an unknown engine name
into an `Unavailable` (KeyError is a LookupError).

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f02_unmade_named_values.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LITRE, cli, compiled, package, read, run  # noqa: E402

from napkin.program.checkpoint import Breakpoint  # noqa: E402
from napkin.session import Session  # noqa: E402

MODEL = '''scenario "Endpoint rate"
    horizon 4 h

tank:
    water: L = 8 L in [0,]
    spread = uniform(1 h, 3 h)
    tick = event():
        after 1 h:
            this.water += 1 L

clinic:
    flow delivery: tank.water -> SINK
        request = 3 L/h

tank.tick.start()
'''
READS = MODEL.replace(
    "    spread = uniform(1 h, 3 h)\n",
    "    spread = uniform(1 h, 3 h)\n    seen = formula(this.water.outflow.actual_rate)\n    m = formula(this.spread.mean)\n",
)
paths = ['tank.water.outflow.actual_rate', 'tank.water.outflow.request', 'tank.spread.mean', 'clinic.delivery.capacity']
for name, text in (('as written', MODEL), ('with formulas that read the endpoint and the mean', READS)):
    c = compiled(text)
    r = run(c.program, c.configuration)
    print(f'napkin.engine.read at 0.5 h, {name}:')
    for x in read(r, c.program, paths, [0.5]):
        print(f'   {x.path:32s} {x.values[0]!r}')
c = compiled(MODEL)
s = Session(c.program, c.configuration, (Breakpoint('tank.tick.step[0]'),))
s.advance()
print('Session.view at the stop of 1 h:', s.view(['tank.water.outflow.actual_rate']).values[0].value)
with tempfile.TemporaryDirectory() as d:
    folder = package(Path(d) / 'pkg', {'model.scn': MODEL, 'units.json': LITRE})
    code, out, err = cli('run', folder, '--value', 'tank.water.outflow.actual_rate', '--at', '0.5h')
    print('napkin run --value tank.water.outflow.actual_rate: exit', code, err.strip().splitlines()[-1])
print('What the rule gives: tank.water.outflow.actual_rate 3 L/h, its request 0 L/h, tank.spread.mean 2 h;')
print('a flow without a capacity has no ceiling, so at least a reason that says so, not a bare path.')
