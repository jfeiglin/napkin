"""F04. `napkin compile` (with or without `--json`) crashes with a Python traceback on any model that
declares a flow with legs, a model that compiles and runs (`napkin run` gives its values). The
acceptance package `tests/acceptance/test_every_construct.py` crashes it the same way.

Rule: spec.md:746-758 (a flow with several legs is a construct of the language); the command's own
contract (napkin/commands/compile.py, docs/cli.md: "print each diagnostic with its place, or a
summary of the program. Exit 0 ok, 1 diagnostics"). Cause: `commands/compile.summary` reads
`flow.source` and `flow.sink` of every flow of a template, and a flow with legs has neither
(`end_text(None)` raises AttributeError).

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f04_compile_summary_legs.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LITRE, cli, package  # noqa: E402

MODEL = '''scenario "Legs"
    horizon 4 h

site:
    work: L = 100 L in [0 L,]  @fixture
    done: L = 0 L in [0 L,]  @fixture
    parts: L = 10 L in [0 L,]  @fixture
    used: L = 0 L in [0 L,]  @fixture
    flow restore:
        flow labor: this.work -> this.done
            request = 4 L/h
        flow spend: this.parts -> this.used
            request = 8 L/h
            capacity = 4 L/h

record fixture: assumption "A fixture."
'''
with tempfile.TemporaryDirectory() as d:
    folder = package(Path(d) / 'legs', {'model.scn': MODEL, 'units.json': LITRE})
    for args in (('compile', folder), ('compile', folder, '--json'), ('run', folder, '--value', 'site.restore.served_fraction')):
        code, out, err = cli(*args)
        print(f'napkin {" ".join(map(str, args[:1] + args[2:]))}: exit {code}')
        print('   ' + ((err.strip().splitlines() or [''])[-1] if code else out.strip().splitlines()[-1]))
print('What the rule gives: napkin compile prints the summary of the program (its flows, with the legs')
print('of site.restore) and exits 0.')
