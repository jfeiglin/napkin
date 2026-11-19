"""The engine's bench (`b1/s5-engine/bench.py`) with each solve of its declared solver printed as it
ends, so that a run stopped at 15 minutes still tells which solves finished (not a test, not linted).

    NAPKIN_STORE=off OPENBLAS_NUM_THREADS=1 .venv/bin/python scratch/rewrite/p1/engine_solves.py [PLACES ROUTES SOURCES]
"""

import importlib.util
import os
import sys
import time

from napkin.engine.solve import Solver

spec = importlib.util.spec_from_file_location('engine_bench', '/home/user/napkin/scratch/rewrite/b1/s5-engine/bench.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

solve = Solver.solve
clock = time.perf_counter()


def timed(self, problem):
    start = time.perf_counter()
    print(f'solve starts at {start - clock:.1f} s of the run [load {os.getloadavg()[0]:.1f}]', flush=True)
    answer = solve(self, problem)
    work = answer.work
    print(
        f'solve: {time.perf_counter() - start:.1f} s; {work.fair_programs} fair programs, {work.renewals} renewals, '
        f'Newton steps {work.newton}, SuperLU runs {work.superlu}, methods {work.methods} [load {os.getloadavg()[0]:.1f}]',
        flush=True,
    )
    return answer


Solver.solve = timed
sys.argv = [sys.argv[0], *sys.argv[1:]]
engine.main()
