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
CHECKED = 1e-10  # a refined solve whose residual is above this, relative to the right side, is
# made again by SuperLU on the same system (`_Factor.solve`); `--checked` turns it on
SUPERLU = []  # the systems that went to SuperLU
REGULAR = None  # `--regular D`: factorize K with its (2, 2) diagonal at most -D, refine against K
MOST = 10  # the refinement steps of a regularized factorization, while the residual halves


class _Factor:
    """A qdldl factorization of K that the next K of the same pattern updates in place."""

    cache = {}

    def __init__(self, K):
        K = sp.csc_array(K)
        key = (K.shape, K.nnz, id(K.indices))
        self.K = K
        solver = _Factor.cache.get(key)
        factored = K
        if REGULAR is not None:
            # the (2, 2) block's diagonal is the negative one: -delta, held at most -REGULAR
            factored = K.copy()
            columns = np.repeat(np.arange(K.shape[1]), np.diff(K.indptr))
            diagonal = np.flatnonzero(K.indices == columns)
            values = factored.data[diagonal]
            factored.data[diagonal] = np.where(values < 0, np.minimum(values, -REGULAR), values)
        if solver is None:
            solver = qdldl.Solver(sp.csc_matrix(factored))
            _Factor.cache = {key: solver}  # one pattern at a time: the stage that runs
        else:
            solver.update(sp.csc_matrix(factored))
        self.solver = solver

    checked = False

    def solve(self, rhs):
        x = self.solver.solve(rhs)
        if REGULAR is not None:
            last = np.inf
            for _ in range(MOST):
                r = rhs - self.K @ x
                size = float(np.abs(r).max(initial=0.0))
                if not size < 0.5 * last:
                    break
                last = size
                x = x + self.solver.solve(r)
        for _ in range(REFINE if REGULAR is None else 0):
            x = x + self.solver.solve(rhs - self.K @ x)
        if _Factor.checked:
            bad = not np.all(np.isfinite(x))
            if not bad:
                scale = float(np.abs(rhs).max(initial=0.0)) or 1.0
                bad = float(np.abs(rhs - self.K @ x).max(initial=0.0)) > CHECKED * scale
            if bad:
                from scipy.sparse.linalg import splu

                SUPERLU.append(1)
                return splu(sp.csc_array(self.K), permc_spec='MMD_AT_PLUS_A').solve(rhs)
        if not np.all(np.isfinite(x)):
            raise RuntimeError('a singular Newton system')
        return x


def use():
    """Make the library's method factorize by qdldl (the name `splu` that `distance` calls)."""
    distance.splu = lambda K, permc_spec=None: _Factor(K)


STEPS = None  # `--steps N`: the Newton budget of each stage (the library's is 500)


def run(tag, repeat, checked=False):
    use()
    _Factor.checked = checked
    state = lab.read(tag)
    times, answers, work = [], [], None
    for _ in range(repeat):
        work = Work()
        clock = time.perf_counter()
        try:
            budget = Budget(newton_steps=STEPS) if STEPS else Budget()
            xi = distance.select(copy.deepcopy(state['face']), state['w'], budget, work)
        except Exception as stopped:  # a named failure is the measurement here
            print(f'{tag} library-ldl: stopped after {time.perf_counter() - clock:.1f} s: {stopped}; '
                  f'Newton {work.newton}, superlu {len(SUPERLU)}', flush=True)
            return
        times.append(time.perf_counter() - clock)
        answers.append(xi)
    same = all(np.array_equal(a, answers[0]) for a in answers[1:]) if repeat > 1 else None
    try:
        reference = np.load(f'{lab.DATA}/{tag}-library.npy')
    except FileNotFoundError:
        reference = None
    found = lab.measures(state, answers[0], reference)
    infos = dict(newton=work.newton, methods=work.methods, factorizations=work.factorizations, qp=work.qp,
                 superlu=len(SUPERLU))
    name = 'library-ldl' + ('-checked' if checked else '') + (f'-regular{REGULAR:g}' if REGULAR else '') + (f'-steps{STEPS}' if STEPS else '')
    record = dict(tag=tag, method=name, seconds=min(times), all=times, repeat=repeat, bitwise=same,
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
    checked = '--checked' in args
    if '--steps' in args:
        i = args.index('--steps')
        STEPS = int(args[i + 1])
        del args[i : i + 2]
    if '--regular' in args:
        i = args.index('--regular')
        REGULAR = float(args[i + 1])
        del args[i : i + 2]
    run([a for a in args if not a.startswith('--')][0], repeat, checked)
