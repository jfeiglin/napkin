"""Prototype P1: the same method twice, in two processes, on the same problem: equal bit for bit?

Not a test and not linted. `run` solves one problem by one method and saves the answer (the distance
step's xi, or fair sharing's levels); `compare` reads two saved answers.

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/same.py run TAG METHOD OUT
    /home/user/venvs/p1/bin/python scratch/rewrite/p1/same.py compare A B
"""

import copy
import sys

import lab
import numpy as np

from napkin.engine.solve import Budget, distance
from napkin.engine.solve.solver import Work

if __name__ == '__main__':
    if sys.argv[1] == 'compare':
        a, b = np.load(sys.argv[2]), np.load(sys.argv[3])
        same = np.array_equal(a, b)
        print(f'{sys.argv[2].split("/")[-1]}: bitwise {same}, largest difference {np.abs(a - b).max():.1e}')
        sys.exit(0)
    _, _, tag, method, out = sys.argv
    state = lab.read(tag)
    if method.startswith('fair:'):
        import fairs

        variant = method[5:]
        if variant == 'library':
            problem = lab.scenario_problem(int(tag.split('-')[1]) / 30000, tag.split('-')[2])
            answer = lab.prefix(problem)['levels']
        else:
            after = state['after']
            answer = fairs.share(
                copy.deepcopy(after['face']), state['w'], Budget(fair_programs=5000), Work(), variant,
                1e-10, 1e-7, (after['col_status'], after['row_status']),
            )  # fmt: skip
    elif method == 'library':
        answer = distance.select(copy.deepcopy(state['face']), state['w'], Budget(), Work())
    else:
        import qp

        answer, _ = qp.candidate(method, state)
    np.save(out, answer)
