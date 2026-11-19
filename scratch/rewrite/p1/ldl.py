"""Prototype P1: the library's distance method with its Newton systems factorized by LDL' (qdldl).

Not a test and not linted. The augmented system of a Newton step of `distance._Dual` keeps one
pattern over a whole stage (only its diagonal changes), and it is quasi-definite: [[D, E'], [E, -delta]]
with D > 0. So it has an LDL' factorization in any symmetric order; qdldl (Apache-2.0, the
factorization of OSQP) takes an AMD order and its symbolic analysis once, and each new diagonal is a
numeric refactorization (`update`). SuperLU, which the library uses, orders and pivots afresh each
time. A solve is refined by `REFINE` steps on the residual, since LDL' does not pivot. Everything else
is the library's method, unchanged (its steps, stop rules, tolerances).

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/ldl.py TAG [--repeat R]
"""

import copy
import json
import sys
import time

import lab
import numpy as np
import qdldl
import scipy.sparse as sp

from napkin.engine.solve import Budget, distance
from napkin.engine.solve.solver import Work

REFINE = 2  # steps of iterative refinement of each solve


class _Factor:
    """A qdldl factorization of K that the next K of the same pattern updates in place."""

    cache = {}

    def __init__(self, K):
        K = sp.csc_array(K)
        key = (K.shape, K.nnz, id(K.indices))
        self.K = K
        solver = _Factor.cache.get(key)
        if solver is None:
            solver = qdldl.Solver(sp.csc_matrix(K))
            _Factor.cache = {key: solver}  # one pattern at a time: the stage that runs
        else:
            solver.update(sp.csc_matrix(K))
        self.solver = solver

    def solve(self, rhs):
        x = self.solver.solve(rhs)
        for _ in range(REFINE):
            x = x + self.solver.solve(rhs - self.K @ x)
        if not np.all(np.isfinite(x)):
            raise RuntimeError('a singular Newton system')
        return x


def use():
    """Make the library's method factorize by qdldl (the name `splu` that `distance` calls)."""
    distance.splu = lambda K, permc_spec=None: _Factor(K)


def run(tag, repeat):
    use()
    state = lab.read(tag)
    times, answers, work = [], [], None
    for _ in range(repeat):
        work = Work()
        clock = time.perf_counter()
        xi = distance.select(copy.deepcopy(state['face']), state['w'], Budget(), work)
        times.append(time.perf_counter() - clock)
        answers.append(xi)
    same = all(np.array_equal(a, answers[0]) for a in answers[1:]) if repeat > 1 else None
    try:
        reference = np.load(f'{lab.DATA}/{tag}-library.npy')
    except FileNotFoundError:
        reference = None
    found = lab.measures(state, answers[0], reference)
    infos = dict(newton=work.newton, methods=work.methods, factorizations=work.factorizations, qp=work.qp)
    record = dict(tag=tag, method='library-ldl', seconds=min(times), all=times, repeat=repeat, bitwise=same,
                  infos=infos, measures=found, load=lab.load(), version=lab.library_version())  # fmt: skip
    with open(f'{lab.DATA}/distance.jsonl', 'a') as f:
        f.write(json.dumps(record, default=str) + '\n')
    print(f'{tag} library-ldl: {min(times):.2f} s (of {repeat}: {", ".join(f"{t:.2f}" for t in times)}), '
          f'bitwise {same}; {infos}; {lab.fmt(found)} [load {lab.load()}]', flush=True)  # fmt: skip


if __name__ == '__main__':
    args = sys.argv[1:]
    repeat = 1
    if '--repeat' in args:
        i = args.index('--repeat')
        repeat = int(args[i + 1])
        del args[i : i + 2]
    run(args[0], repeat)
