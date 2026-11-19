"""Prototype P1, correctness first: each method in the library's place on the spec's cases and the
seeded random cases of `tests/engine/solve/`, against their exact references.

Not a test and not linted. The test functions of `test_spec_answers.py` (the spec's answers, worked by
hand) and `test_random.py` (the exact rational reference of `exact.py`, the exact nearest point, and
brute-force fair sharing), with its deep sweep, are called directly with each of their parameters,
while `distance.select` or `fair.share` is replaced by the method under test. Tests of the library's
own QP fallback (they read `work.methods`) are left out of the distance candidates.

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/correct.py METHOD [--tol T] [--fix F] [--quick]

METHOD: `library`, a distance candidate of `qp.METHODS` (e.g. `clarabel`), or `fair:VARIANT` with a
variant of `fairs` (e.g. `fair:highs-primal`), or `loose:TOL` (the library with its fair programs at
the primal tolerance TOL, FIX 10 x TOL, and its distance rows to TOL as well).
"""

import itertools
import sys
import time
import traceback

import lab
import numpy as np

from napkin.engine.solve import FLOW, OTHER, SolveFailure, distance, fair, solver

FALLBACK = ('test_the_distance_cases_by_the_exact_fallback', 'test_the_exact_fallback_gives_the_same_answers')


def qp_select(name):
    """A `distance.select` replacement: the candidate's two stages on the face."""
    import qp

    def select(face, w, budget, work):
        A, row_lower, row_upper = face.arrays(w.A)
        lower, upper = face.lower.copy(), face.upper.copy()
        flows, others = w.kind == FLOW, w.kind == OTHER
        xi = None
        if flows.any():
            xi, info = qp.candidate_stage(name, A, row_lower, row_upper, lower, upper, w.target, flows * 1.0)
            work.methods.append(name if info['found'] else f'{name}:{info["status"]}')
            lower[flows] = upper[flows] = xi[flows]
        if others.any() or xi is None:
            xi, info = qp.candidate_stage(name, A, row_lower, row_upper, lower, upper, w.target, others * 1.0)
            work.methods.append(name if info['found'] else f'{name}:{info["status"]}')
        return xi

    return select


class Recorder:
    """`pytest.approx` that records the error of each comparison against its absolute tolerance, so
    that a run gives the largest error relative to the test's tolerance, not only pass or fail."""

    __array_ufunc__ = None
    __array_priority__ = 100
    worst = [0.0, 0.0]  # (largest error / tolerance, largest error)

    def __init__(self, expected, rel=None, abs=None):
        self.expected = np.asarray(expected, float)
        self.abs = 1e-12 if abs is None else abs

    def __eq__(self, other):
        error = float(np.max(np.abs(np.asarray(other, float) - self.expected), initial=0.0))
        Recorder.worst[0] = max(Recorder.worst[0], error / self.abs)
        Recorder.worst[1] = max(Recorder.worst[1], error)
        return error <= self.abs


def cases(module, deep):
    """(name, function, kwargs) for each test of `module` and each of its parameters."""
    for name, f in list(vars(module).items()):
        if not (name.startswith('test_') and callable(f)):
            continue
        marks = getattr(f, 'pytestmark', [])
        if any(m.name == 'deep' for m in marks):
            continue  # the deep sweep is run seed by seed below
        combos = [{}]
        for m in marks:
            if m.name != 'parametrize':
                continue
            names, values = m.args[0], list(m.args[1])
            names = [n.strip() for n in names.split(',')] if isinstance(names, str) else list(names)
            made = []
            for value in values:
                made.append(dict(zip(names, value)) if len(names) > 1 else {names[0]: value})
            combos = [dict(a, **b) for a, b in itertools.product(combos, made)]
        for kwargs in combos:
            yield name, f, kwargs
        # the deep sweep of test_random (`test_a_wider_sweep`), seed by seed
        wider = {
            'test_the_whole_order_against_the_exact_reference': range(30, 330),
            'test_the_distance_step_against_the_exact_nearest_point': range(60, 400),
            'test_fair_sharing_on_networks_against_brute_force': range(16, 60),
        }
        if deep and name in wider:
            for seed in wider[name]:
                yield name, f, {'seed': seed}


def run(method, tol, fix, deep):
    import tests.engine.solve.test_random as random_tests
    import tests.engine.solve.test_spec_answers as spec_tests

    skip = ()
    if method in ('library',):
        pass
    elif method.startswith('fair:'):
        import fairs

        fair.share = fairs.library_share(method[5:], tol, fix)
    elif method.startswith('hybrid'):
        import hybrid
        import qp

        qp._clarabel_iterations()
        parts = method.split(':')  # hybrid[:ipm[:eps]]
        ipm = parts[1] if len(parts) > 1 else 'clarabel'
        eps_start = float(parts[2]) if len(parts) > 2 else distance.EPS_START
        distance.select = hybrid.replacement(ipm, eps_start)
        skip = FALLBACK
    elif method == 'ldl':
        import ldl

        ldl.use()
    elif method.startswith('polish'):
        import polish
        import qp

        qp._clarabel_iterations()
        ipm = method.split(':')[1] if ':' in method else 'clarabel'
        distance.select = polish.replacement(ipm)
        skip = FALLBACK
    elif method.startswith('loose:'):
        # loose:TOL[:FIX[:DISTANCE TOL]]: the library with its fair programs at the primal tolerance
        # TOL, its held floors' slack FIX (default 10 x TOL) and its distance rows to DISTANCE TOL
        parts = [float(v) for v in method[6:].split(':')]
        loose = parts[0]
        fair.TIGHT = loose
        fair.FIX = parts[1] if len(parts) > 1 else 10 * loose
        distance.TOL = parts[2] if len(parts) > 2 else loose
        solver.CHECK = max(solver.CHECK, 10 * fair.FIX)
    else:
        import qp

        qp._clarabel_iterations()
        distance.select = qp_select(method)
        skip = FALLBACK
    import pytest

    pytest.approx = Recorder
    counts, worst, stopped = {}, {}, {}
    failures = []
    clock = time.perf_counter()
    for module in (spec_tests, random_tests):
        for name, f, kwargs in cases(module, deep):
            if name in skip:
                continue
            Recorder.worst = [0.0, 0.0]
            try:
                f(**kwargs)
                ok = True
            except AssertionError:
                ok = False
            except Exception as error:  # a stop by name, or a solver that raised
                ok = False
                stopped[name] = stopped.get(name, 0) + 1
                failures.append((name, kwargs, type(error).__name__, str(error)[:200]))
            passed, failed = counts.get(name, (0, 0))
            counts[name] = (passed + ok, failed + (not ok))
            ratio, error = worst.get(name, (0.0, 0.0))
            worst[name] = (max(ratio, Recorder.worst[0]), max(error, Recorder.worst[1]))
            if not ok and len(failures) < 40:
                failures.append((name, kwargs, 'error/tolerance', round(Recorder.worst[0], 1)))
    seconds = time.perf_counter() - clock
    total = [sum(p for p, _ in counts.values()), sum(f for _, f in counts.values())]
    print(f'{method} (tol {tol:g}, fix {fix:g}, deep {deep}): passed {total[0]}, failed {total[1]} '
          f'in {seconds:.1f} s [load {lab.load()}]')
    for name, (passed, failed) in counts.items():
        ratio, error = worst[name]
        if failed or ratio > 0.1:
            print(f'   {name}: {passed} passed, {failed} failed, {stopped.get(name, 0)} stopped; '
                  f'largest error {error:.1e} = {ratio:.2g} x its tolerance')
    for failure in failures[:6]:
        print('   e.g.', failure)
    import json

    worst_ratio = max((r for r, _ in worst.values()), default=0.0)
    worst_error = max((e for _, e in worst.values()), default=0.0)
    families = {name: dict(passed=p, failed=f, stopped=stopped.get(name, 0), ratio=worst[name][0], error=worst[name][1])
                for name, (p, f) in counts.items()}  # fmt: skip
    with open(f'{lab.DATA}/correct.jsonl', 'a') as f:
        f.write(json.dumps(dict(method=method, tol=tol, fix=fix, passed=total[0], failed=total[1],
                                stopped=sum(stopped.values()), worst_ratio=worst_ratio, worst_error=worst_error,
                                families=families, seconds=seconds, load=lab.load())) + '\n')  # fmt: skip
    return counts, failures


if __name__ == '__main__':
    args = sys.argv[1:]

    def option(name, default):
        if name in args:
            i = args.index(name)
            value = float(args[i + 1])
            del args[i : i + 2]
            return value
        return default

    tol, fix = option('--tol', 1e-10), option('--fix', 1e-7)
    deep = '--quick' not in args
    args = [a for a in args if not a.startswith('--')]
    run(args[0], tol, fix, deep)
