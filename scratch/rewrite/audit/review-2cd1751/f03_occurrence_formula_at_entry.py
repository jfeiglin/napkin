"""F03. An occurrence evaluates each of its `formula(...)` locals at its entry. A formula local that
names a later local, or one that cannot be evaluated yet (`since` of an event that has not started),
fails the run at the start, although nothing reads it then. The compiler accepts both (its own refusal
of a plain initializer says "a formula(...) is read later"), the reference interpreter runs both, and
the case of the spec's own text, a flow's `request = formula(left / (2 h))`, does run: the rule was
fixed for a flow's property and its cause left for a local.

Rule: spec.md:634 ("Creating a `formula(...)` retains a calculation for later reads ... A retained
`formula(left / (2 h))` may name a later local, because it is evaluated when it is read, after entry
is complete"), D14; spec.md:727 and D7 (a formula that could not be evaluated keeps its reason; the
occurrence finishes normally; a model read of it raises the reason). Cause: `Occurrences._enter`
(`engine/timeline/occurrences.py`) runs `run.truth(value.node)` for every name of `made.initial`,
formulas included.

Run from /home/user/napkin-R:
    PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/f03_occurrence_formula_at_entry.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import compiled, oracle, oracle_value, read, run  # noqa: E402

LATER = '''scenario "A formula names a later local"
    horizon 3 h

plant:
    seen: L = 0 L
    job = event():
        f = formula(x * 2)
        x: L = 3 L
        after 1 h:
            plant.seen = f

plant.job.start()
'''
SINCE = '''scenario "A formula that cannot be read yet"
    horizon 3 h

plant:
    job = event():
        g = formula(since(this.other))
        after 1 h
    other = event():
        after 0 h
'''
FLOW = '''scenario "The spec's own case: a flow's request"
    horizon 3 h

plant:
    water: L = 0 L in [0,]
    job = event():
        flow pipe: SOURCE -> plant.water
            request = formula(left / (2 h))
        left: L = 4 L
        after 1 h

plant.job.start()
'''
for text, path, expected in (
    (LATER, 'plant.seen', 'the run finishes; plant.seen is 6 L from 1 h'),
    (SINCE + '\nplant.job.start()\n', 'plant.job#0.g', 'the run finishes; plant.job#0.g is unavailable with its reason'),
    (FLOW, 'plant.water', 'the run finishes; plant.water is 2 L at 1 h'),
):
    c = compiled(text)
    r = run(c.program, c.configuration)
    title = text.splitlines()[0]
    print(title)
    print('   engine failure:', r.failure and (float(r.failure.t), r.failure.detail('message')))
    print('   engine', path, 'at 1 h and 2 h:', read(r, c.program, [path], [1, 2])[0].values)
    o, failed = oracle(c)
    shown = None
    if failed is None:
        try:
            shown = [oracle_value(c, o, path, t) for t in (1, 2)]
        except Exception as error:  # noqa: BLE001
            shown = f'{type(error).__name__}: {error}'
    print('   reference interpreter failure:', failed, '| values:', shown)
    print('   the rule gives:', expected)
