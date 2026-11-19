"""The library's whole order on A3's network, one scenario a process, each step printed as it ends,
after the adoption of P1's three speedups (not a test, not linted).

    NAPKIN_STORE=off OPENBLAS_NUM_THREADS=1 .venv/bin/python scratch/rewrite/p1/adopted.py SHARE SCENARIO

It is `b1/solve/bench.py after` for one scenario, with the fair-sharing budget of 5,000 programs, but
it prints the objective and fair sharing before the distance step starts, so that a run stopped at
15 minutes still gives them.
"""

import os
import sys
import time

sys.path.insert(0, '/home/user/napkin/scratch/rewrite/b1/solve')
import bench  # noqa: E402

from napkin.engine.solve import Budget, SolveFailure, distance, fair, ranked  # noqa: E402
from napkin.engine.solve.scaled import Scaled  # noqa: E402
from napkin.engine.solve.solver import Solver, Work, _answer, _check_hard  # noqa: E402


def main(share, name):
    net, need, up = bench.scenario(share, name)
    problem = bench.network_problem(net, need, up)
    solver = Solver(Budget(fair_programs=5000))
    arrays = problem.arrays()
    _check_hard(arrays)
    w = solver._follow(Scaled(arrays))
    kept, work = solver._kept, Work()
    face = ranked.Face(w)
    clock = time.perf_counter()
    optima = ranked.optimize(kept, face, w, work)
    objective = time.perf_counter() - clock
    clock = time.perf_counter()
    levels = fair.share(kept, face, w, solver.budget, work)
    shared = time.perf_counter() - clock
    print(
        f'{name} {int(30000 * share)}: objective {objective:.1f} s, fair {shared:.1f} s, {work.fair_programs} '
        f'programs, {work.levels} levels, {kept.iterations} iterations, {work.tight} tight, {kept.renewals} '
        f'renewals [load {os.getloadavg()[0]:.1f}]',
        flush=True,
    )
    clock = time.perf_counter()
    try:
        xi = distance.select(face, w, solver.budget, work)
        _answer(arrays, w, xi, optima, levels, work)
        outcome = 'answered'
    except SolveFailure as stopped:
        outcome = f'stopped: {stopped}'
    print(
        f'{name} {int(30000 * share)}: distance {time.perf_counter() - clock:.1f} s, {outcome}; Newton steps '
        f'{work.newton}, SuperLU runs {work.superlu}, factorizations {work.factorizations}, QP {work.qp} '
        f'[load {os.getloadavg()[0]:.1f}]',
        flush=True,
    )


if __name__ == '__main__':
    main(float(sys.argv[1]), sys.argv[2])
