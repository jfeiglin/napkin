"""F05. A record of only some values (a `Request` with `keys`: what `napkin sample` asks of each sample,
and what the run store serves to such a request, cold or warm) does not keep the key field of a keyed
read `.by(field).at(x)`. A formula that reads one, such as the worked network's
`need = formula(this.base_need * Reading.instances.by(hour).at(t).factor)`, reads `Unavailable`
("the record keeps no history of readings[0].hour"), and `napkin sample` gives it no spread. A
`where` filter on a fixed field, a link, a literal and an occurrence's `.at(t)` are kept.

Rule: spec.md:99 and spec.md:328 (a keyed read); program/record.py, "What a record holds": a record
of some values holds "what their values need", one function of the request for a run and for a cut
(`engine/timeline/record.requested`); D10 (a caller selects paths). Cause:
`engine/timeline/record.needed` walks `Plan.reads` of a LOOKUP, which leaves out the members' key
field.

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f05_selective_record_keyed_read.py
"""

import sys
import tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import cli, compiled, package, read, run  # noqa: E402

from napkin import store  # noqa: E402
from napkin.engine.timeline.record import key_of  # noqa: E402
from napkin.program.config import Request  # noqa: E402

MODEL = '''scenario "Keyed need"
    horizon 4 h

Reading:
    input hour: h = 0  @fixture
    input factor = 1  @fixture

r0: Reading
r1: Reading
    hour = 1 h  @fixture
    factor = 0.5  @fixture

Place:
    input rank = 0  @fixture
    input base_need: W = uniform(5 W, 7 W).draw()  @fixture
    need = formula(this.base_need * Reading.instances.by(hour).at(t).factor)

clinic: Place
garden: Place
    rank = 1  @fixture

first = formula(Place.instances.by(rank).at(1).base_need)

record fixture: assumption "A fixture."
'''
c = compiled(MODEL)
times = [0, 1, 2]
for path in ('clinic.need', 'first'):
    full = run(c.program, c.configuration)
    only = replace(c.configuration, request=Request(4, everything=False, keys=(key_of(c.program, path),)))
    print(path)
    print('   a record of every value:', read(full, c.program, [path], times)[0].values)
    print('   a record of this value :', read(run(c.program, only), c.program, [path], times)[0].values)
    with tempfile.TemporaryDirectory() as d:
        with store.use(Path(d)):
            store.run(c.program, c.configuration)
            warm = store.run(c.program, only)
    print('   the store, warm        :', read(warm, c.program, [path], times)[0].values)
with tempfile.TemporaryDirectory() as d:
    units = '{"W": {"dimensions": {"energy": 1, "time": -1}, "scale": 1, "description": "A watt."}}'
    folder = package(Path(d) / 'keyed', {'model.scn': MODEL, 'units.json': units})
    code, out, err = cli('sample', folder, '--samples', '4', '--jobs', '1', '--value', 'clinic.need,clinic.base_need', '--at', '1h')
    print('napkin sample: exit', code)
    print('\n'.join('   ' + line for line in out.strip().splitlines()))
print('What the rule gives: clinic.need is 6, 3, 3 W in the median run in every record; first is 6 W;')
print('napkin sample gives clinic.need a spread (half of base_need at 1 h).')
