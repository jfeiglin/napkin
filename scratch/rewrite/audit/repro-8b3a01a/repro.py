"""The main session's reproductions of the readiness audit of 8b3a01a (`../readiness-8b3a01a.csv`),
each written independently of the auditor's. Run: NAPKIN_STORE=off .venv/bin/python
scratch/rewrite/audit/repro-8b3a01a/repro.py [NAME...]. Each prints what the code gives and what the
spec asks; on 8b3a01a each one shows the defect (row 16 needs a property test: see the brief)."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import numpy as np

from napkin.engine import read, run
from napkin.engine.report import Lag, report
from napkin.model.compile import compile_text, load_scenario
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS


def row06():
    """Every rank, the last included: the solver's answer is (1, 0); a candidate (0, 1), which moves
    all of it onto the idle pipe (target 0), passes `admits`. Spec: the final distance step is a rank
    of the selection order ("Final targets", spec.md:548-556)."""
    from napkin.engine.solve.problem import Problem
    from napkin.engine.solve.solver import Solver

    problem = Problem()
    a = problem.unknown('a', 0, 2, target=1.0)
    b = problem.unknown('b', 0, 2, target=0.0)
    problem.equal('books', {a: 1.0, b: 1.0}, 1.0)
    answer = Solver().solve(problem)
    print('06 solver answer', answer.x, '| admits (0, 1):', answer.admits(np.array([0.0, 1.0])), '(must be False)')


def row12():
    """A reversed interval made at run time: `ok` reads false and the run finishes. Spec.md:80: reversed
    bounds are an error."""
    text = '''scenario "Interval"
    horizon 4 h

plant:
    lo: h = 1 h
    hi: h = 3 h
    x: h = 2.5 h
    ok = formula(this.x in [this.lo, this.hi])
    swap = event():
        after 1 h:
            this.lo = 3 h
            this.hi = 2 h

plant.swap.start()
'''
    compiled = compile_text(text, UNITS)
    record = run(compiled.program, compiled.configuration)
    print('12 failure:', record.failure, '| ok at 0, 2 h:', read(record, compiled.program, ['plant.ok'], [0, 2])[0].values, '(must fail by name when read reversed)')


def row14():
    """(a) A write through a saved reference to an occurrence that finished at 5 h succeeds; spec.md:632:
    a finished occurrence is frozen, and a write to it is an error. (b) A formula installed through an
    event's parameter on a member captures the occurrence's parameter and is read after it ends;
    spec.md:640: reject a live formula installed in a longer-lived entity if reading it would require a
    retired local."""
    frozen = '''scenario "Frozen"
    horizon 10 h

crew:
    seen: L = 0 L
    repair = event(amount: L):
        size: L = amount * 2
        after 1 h:
            this.watch.start()
        after 4 h
    watch = event():
        job = this.repair.occurrences.at(t)
        after 6 h:
            job.size = 1 L
            this.seen = job.size

crew.repair.start(3 L)
'''
    compiled = compile_text(frozen, UNITS)
    record = run(compiled.program, compiled.configuration)
    print('14a failure:', record.failure, '(must fail by name at 7 h)')
    captured = '''scenario "Captured"
    horizon 10 h

Crew:
    rate: formula(L/h) = formula(0 L/h)

north: Crew

boss:
    order = event(target: Crew, amount: L):
        after 1 h:
            target.rate = formula(amount / (2 h))

boss.order.start(north, 3 L)
'''
    try:
        compiled = compile_text(captured, UNITS)
        record = run(compiled.program, compiled.configuration)
        print('14b compiled; north.rate at 9 h:', read(record, compiled.program, ['north.rate'], [9])[0].values, '(must be refused: lifetime)')
    except LanguageError as error:
        print('14b refused:', [problem.code for problem in error.problems])


def row15():
    """(a) A reduction over a named top-level collection is refused by the engine. (b) A chain of 300
    top-level formulas fails to compile (RecursionError in the front end's resolution), before any
    lag or trail is asked."""
    top = '''scenario "Top"
    horizon 2 h

Tank:
    water: L = 4 L

east: Tank
west: Tank
    water = 6 L

tanks = Tank.instances
total = formula(sum(tanks.water))
'''
    try:
        compiled = compile_text(top, UNITS)
        record = run(compiled.program, compiled.configuration)
        print('15a total:', read(record, compiled.program, ['total'], [1])[0].values, '(must be 10)')
    except Exception as error:  # noqa: BLE001 - a reproduction prints what it meets
        print('15a', type(error).__name__, str(error)[:160])
    rows = ['scenario "Chain"', '    horizon 2 h', '', 'store:', '    water: L = 0 L in [0,]',
            '    flow fill: SOURCE -> this.water', '        request = 1 L/h', '']
    n = 300
    rows += [f'v{k} = formula(v{k + 1} + 0 L)' for k in range(n - 1)] + [f'v{n - 1} = formula(store.water)']
    try:
        compiled = compile_text('\n'.join(rows) + '\n', UNITS)
        record = run(compiled.program, compiled.configuration)
        found = report(record, compiled.program, compiled.configuration, ['v0'], [2], {'v0': Lag(0.5, 1)})
        print('15b lagged v0:', found.values[0].values)
    except RecursionError as error:
        import traceback

        frames = traceback.extract_tb(error.__traceback__)
        print('15b RecursionError in', sorted({f'{f.filename.split("napkin/")[-1]}:{f.name}' for f in frames[-30:]}))


def row17():
    """A value fixed when the model compiles, citing a datum of 34 h: only plain arithmetic is compared.
    A true conditional and a square root of the same 99 h pass, and a decimal longer than a float keeps
    is rounded to the datum."""
    from napkin.model.support import DATUM
    from tests.evidence.support import datum_package

    root = Path(tempfile.mkdtemp())
    for k, end in enumerate(('99 h', '(99 h if true else 34 h)', 'sqrt(99 h * 99 h)', '34.000000000000000001 h')):
        path = datum_package(root / str(k), end=end)
        warned = [item.message for item in load_scenario(path).reports if item.code == DATUM]
        print(f'17 {end}: {"warns" if warned else "no warning (must warn)"}')


ROWS = {'06': row06, '12': row12, '14': row14, '15': row15, '17': row17}

if __name__ == '__main__':
    for name in sys.argv[1:] or ROWS:
        ROWS[name]()
