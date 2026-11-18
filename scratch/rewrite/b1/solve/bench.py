"""A3's measured table again at 3,000 places, on the solve library `napkin/engine/solve`. Not a test.

Run from /home/user/napkin:

    NAPKIN_STORE=off .venv/bin/python scratch/rewrite/b1/solve/bench.py [SECTION ...] [--share S] [--repeat R]

Sections: fair, objective, after, join, again, small, verify (default: all but `after` and `verify`,
which solve the whole order on every scenario). `--share 0.1` (the default) is 3,000 places of A3's
network (`scratch/rewrite/a3/network.py`: 3,000 places, 3,500 routes, 1,500 sources); `verify` is
meant for a share where the QP of HiGHS finishes (0.01). Each timing is the best of R runs (default 1)
and gives the load of the machine (4 cores, shared).
"""

import os
import sys
import time

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, '/home/user/napkin/scratch/rewrite/a3')
from network import damaged, network  # A3's synthetic network

from napkin.engine.solve import FLOW, OTHER, Budget, Problem, Solver, distance, fair, ranked
from napkin.engine.solve.scaled import Scaled
from napkin.engine.solve.solver import Work, _answer, _check_hard

INF = np.inf


def load():
    return os.getloadavg()[0]


def scenario(share, name):
    """A3's scenarios: normal, shortage (need x1.45), damaged (1,000 x share routes down), global
    (need x1.7)."""
    net = network(int(30000 * share), int(35000 * share), int(15000 * share))
    mult = {'shortage': 1.45, 'global': 1.7}.get(name, 1.0)
    up = damaged(net, int(1000 * share)) if name == 'damaged' else None
    return net, net['need'] * mult, up


def network_problem(net, need, up=None, claims=True, extra=0):
    """A3's route-and-level program as a Problem: levels (OTHER, [-30, 30], reference 0), sources,
    uses (target and claim: the need; no cap), signed routes; balance and route-law rows; the
    objective min sum(max(0, need - use)). `extra` flows of capacity 1 and request 0.5 join at
    random places (the join section), and their unmet requests join the objective."""
    P, S, R = net['places'], net['sources'], net['routes']
    up = np.ones(R) if up is None else up
    p = Problem()
    level = p.unknowns([('level', i) for i in range(P)], -30.0, 30.0, OTHER)
    supply = p.unknowns([('supply', i) for i in range(S)], 0.0, net['pmax'], FLOW)
    use = p.unknowns([('use', i) for i in range(P)], 0.0, INF, FLOW, need)
    carried = p.unknowns([('carried', i) for i in range(R)], -net['cap'] * up, net['cap'] * up, FLOW)
    where = np.random.default_rng(5).integers(0, P, extra)
    joined = p.unknowns([('joined', i) for i in range(extra)], 0.0, 1.0, FLOW, 0.5)
    n = len(p.keys)
    r = np.arange(R)
    rows = np.r_[net['at'], np.arange(P), net['frm'], net['to'], where]
    cols = np.r_[supply, use, carried, carried, joined]
    vals = np.r_[np.ones(S), -np.ones(P), -np.ones(R), np.ones(R), -np.ones(extra)]
    p.rows([('balance', i) for i in range(P)], sp.coo_array((vals, (rows, cols)), shape=(P, n)), 0.0, 0.0)
    pull = net['b'] * up
    law = sp.coo_array(
        (
            np.r_[np.ones(R), -pull, pull],
            (np.r_[r, r, r], np.r_[carried, level[net['frm']], level[net['to']]]),
        ),
        shape=(R, n),
    )
    p.rows([('law', i) for i in range(R)], law, 0.0, 0.0)
    short = p.positive_parts(
        [('short', i) for i in range(P)], sp.coo_array((-np.ones(P), (np.arange(P), use)), shape=(P, n)), need
    )
    unserved = p.positive_parts(
        [('unserved', i) for i in range(extra)],
        sp.coo_array((-np.ones(extra), (np.arange(extra), joined)), shape=(extra, len(p.keys))),
        0.5,
    )
    cost = np.zeros(len(p.keys))
    cost[short] = 1.0
    cost[unserved] = 1.0
    p.minimize(cost)
    if claims:
        p.claims(use, need)
        if extra:
            p.claims(joined, 0.5)
    return p


class Timed:
    """`Solver.solve` with a clock on each step (the library itself counts work, never seconds)."""

    def __init__(self, budget=None):
        self.solver = Solver(budget)
        self.budget = self.solver.budget

    def solve(self, problem, until='distance'):
        solver, times = self.solver, {}
        start = time.perf_counter()
        arrays = problem.arrays()
        _check_hard(arrays)
        w = solver._follow(Scaled(arrays))
        kept, work = solver._kept, Work()
        first = kept.iterations
        face = ranked.Face(w)
        times['form'] = time.perf_counter() - start
        answer = None
        try:
            clock = time.perf_counter()
            optima = ranked.optimize(kept, face, w, work)
            times['objective'] = time.perf_counter() - clock
            if until in ('fair', 'distance'):
                clock = time.perf_counter()
                levels = fair.share(kept, face, w, self.budget, work)
                times['fair'] = time.perf_counter() - clock
            else:
                levels = np.full(len(w.request), np.nan)
            if until == 'distance':
                clock = time.perf_counter()
                xi = distance.select(face, w, self.budget, work)
                times['distance'] = time.perf_counter() - clock
                answer = _answer(arrays, w, xi, optima, levels, work)
        finally:
            solver._restore(w)
            work.iterations = kept.iterations - first
        times['total'] = time.perf_counter() - start
        return answer, optima, levels, work, times


def best(fn, repeat):
    times, out = [], None
    for _ in range(repeat):
        clock = time.perf_counter()
        out = fn()
        times.append(time.perf_counter() - clock)
    return min(times), out


# -- sections -------------------------------------------------------------------------------------
def sec_fair(share, repeat):
    """The objective and the fair rank of one tier, on one kept instance; the distance step apart."""
    for name in ('normal', 'shortage', 'damaged', 'global'):
        net, need, up = scenario(share, name)
        p = network_problem(net, need, up)
        _, (_, _, levels, work, times) = best(lambda: Timed().solve(p, until='fair'), repeat)
        below = int((levels < 1 - 1e-7).sum())
        print(
            f'fair {share:g} {name:8s}: objective {times["objective"]:.2f} s, fair {times["fair"]:.2f} s; '
            f'{work.fair_programs} programs, {work.levels} distinct levels, {below} claims below 100%, '
            f'{work.iterations} iterations, {work.tight} tight runs [load {load():.1f}]',
            flush=True,
        )


def sec_objective(share, repeat):
    """The whole order with no claims: the distance steps on the face of the objective."""
    for name in ('normal', 'shortage', 'damaged'):
        net, need, up = scenario(share, name)
        p = network_problem(net, need, up, claims=False)
        _, (_, _, _, work, times) = best(lambda: Timed().solve(p), repeat)
        print(
            f'objective face {share:g} {name:8s}: distance {times["distance"]:.2f} s, methods {work.methods}, '
            f'Newton steps {work.newton}, factorizations {work.factorizations}, QP iterations {work.qp} '
            f'[load {load():.1f}]',
            flush=True,
        )


def sec_after(share, repeat, names=('normal',)):
    """The whole order: the distance steps on the face that fair sharing leaves."""
    for name in names:
        net, need, up = scenario(share, name)
        p = network_problem(net, need, up)
        _, (_, optima, _, work, times) = best(lambda: Timed().solve(p), repeat)
        print(
            f'after fair {share:g} {name:8s}: objective {times["objective"]:.2f} s, fair {times["fair"]:.2f} s, '
            f'distance {times["distance"]:.2f} s; methods {work.methods}, Newton steps {work.newton}, '
            f'factorizations {work.factorizations}, QP iterations {work.qp}; optimum {optima[0] if optima else None} '
            f'[load {load():.1f}]',
            flush=True,
        )


def sec_join(share, repeat, joined=300):
    """`joined` claimed flows join a kept instance and leave it again (the objective's program),
    against the problem formed fresh."""
    net, need, up = scenario(share, 'shortage')
    before = network_problem(net, need, up, claims=False)
    after = network_problem(net, need, up, claims=False, extra=joined)
    kept = Timed()
    kept.solve(before, until='objective')
    _, (_, o_join, _, work_join, t_join) = best(lambda: _round_trip(kept, after, before), 1)
    t_fresh, (_, o_fresh, *_) = best(lambda: Timed().solve(after, until='objective'), repeat)
    _, o_leave, _, work_leave, t_leave = kept.solve(before, until='objective')
    _, o_before, *_ = Timed().solve(before, until='objective')
    print(
        f'join {share:g}: {joined} flows join: warm {t_join["total"]:.2f} s ({work_join.iterations} iterations), '
        f'fresh {t_fresh:.2f} s; optimum {o_join[0]:.9f} against fresh {o_fresh[0]:.9f}; they leave: warm '
        f'{t_leave["total"]:.2f} s ({work_leave.iterations} iterations), optimum {o_leave[0]:.9f} against fresh '
        f'{o_before[0]:.9f} [load {load():.1f}]',
        flush=True,
    )


def _round_trip(kept, after, before):
    return kept.solve(after, until='objective')


def sec_again(share, repeat):
    """The same problem (shortage) cold, and warm on an instance that first solved another (normal):
    the optimum and the fair levels; and two fresh solvers, which must agree bit for bit."""
    net, need, up = scenario(share, 'shortage')
    shortage = network_problem(net, need, up)
    normal = network_problem(*scenario(share, 'normal'))
    _, o_cold, l_cold, *_ = Timed().solve(shortage, until='fair')
    warm = Timed()
    warm.solve(normal, until='fair')
    _, o_warm, l_warm, *_ = warm.solve(shortage, until='fair')
    _, o_again, l_again, *_ = Timed().solve(shortage, until='fair')
    print(
        f'again {share:g}: optimum cold {o_cold[0]:.9f}, warm {o_warm[0]:.9f}; fair levels: warm differs from cold '
        f'by {np.abs(l_warm - l_cold).max():.1e}; a second fresh solver: optimum and levels bit for bit '
        f'{o_again == o_cold and np.array_equal(l_again, l_cold)} [load {load():.1f}]',
        flush=True,
    )


def provider(east_request=6.0, west_request=6.0, limit=8.0):
    p = Problem()
    east = p.unknown('east', 0.0, 6.0, FLOW, east_request)
    west = p.unknown('west', 0.0, 6.0, FLOW, west_request)
    p.at_most('contract', {east: 1.0, west: 1.0}, limit)
    p.claim({east: 1.0}, east_request)
    p.claim({west: 1.0}, west_request)
    p.minimize({p.positive_part('east unmet', {east: -1.0}, east_request): 1.0})
    p.minimize({p.positive_part('west unmet', {west: -1.0}, west_request): 1.0})
    p.minimize({east: 1.0, west: 1.0})
    return p


def sec_small(share, repeat, count=200):
    """Solves of about ten unknowns: the provider case through the whole order."""
    problems = [provider(6.0, 6.0), provider(2.0, 6.0)]
    t_fresh, _ = best(lambda: [Solver().solve(problems[k % 2]) for k in range(count)], repeat)
    solver = Solver()
    t_kept, _ = best(lambda: [solver.solve(problems[k % 2]) for k in range(count)], repeat)
    print(
        f'small: whole order, formed each time {t_fresh / count * 1e3:.2f} ms ({count / t_fresh:.0f}/s); '
        f'on a kept instance {t_kept / count * 1e3:.2f} ms ({count / t_kept:.0f}/s) [load {load():.1f}]',
        flush=True,
    )


def sec_verify(share, repeat, names=('normal', 'shortage')):
    """The method against the QP of HiGHS (the method given no Newton step) on the whole order, at a
    size where that QP finishes: the largest difference of the flows and of the levels."""
    for name in names:
        net, need, up = scenario(share, name)
        problem = network_problem(net, need, up)
        clock = time.perf_counter()
        newton = Solver().solve(problem)
        t_newton = time.perf_counter() - clock
        clock = time.perf_counter()
        try:
            qp = Solver(Budget(newton_steps=0)).solve(problem)
        except Exception as stopped:  # the fallback's own failure is the measurement here
            print(f'verify {share:g} {name:8s}: the QP failed: {stopped} [load {load():.1f}]', flush=True)
            continue
        t_qp = time.perf_counter() - clock
        kinds = np.array([key[0] for key in problem.keys])
        flows = np.isin(kinds, ('supply', 'use', 'carried'))
        print(
            f'verify {share:g} {name:8s}: Newton {t_newton:.2f} s {newton.work.methods}, QP {t_qp:.2f} s '
            f'{qp.work.qp}; flows differ by {np.abs(newton.x - qp.x)[flows].max():.1e}, levels by '
            f'{np.abs(newton.x - qp.x)[kinds == "level"].max():.1e} [load {load():.1f}]',
            flush=True,
        )


SECTIONS = dict(
    fair=sec_fair,
    objective=sec_objective,
    after=sec_after,
    join=sec_join,
    again=sec_again,
    small=sec_small,
    verify=sec_verify,
)

if __name__ == '__main__':
    args = sys.argv[1:]
    share, repeat = 0.1, 1
    if '--share' in args:
        i = args.index('--share')
        share = float(args[i + 1])
        del args[i : i + 2]
    if '--repeat' in args:
        i = args.index('--repeat')
        repeat = int(args[i + 1])
        del args[i : i + 2]
    names = args or ['small', 'fair', 'objective', 'join', 'again']
    print(f'bench {names} share {share} repeat {repeat}; budget {Budget()}; load {load():.1f}', flush=True)
    for name in names:
        SECTIONS[name](share, repeat)
