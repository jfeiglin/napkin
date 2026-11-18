"""The measured table of FINDINGS.md. Run alone: python measure.py [SECTION ...] [--share S] [--repeat R]

Sections: ranked, fair, distance, join, units, again, small. With none, all of them at the sizes of the
table (full scale for most; the fair section stops a run at 600 s and says so).
Each timing is the best of R runs (default 3; the fair runs at 30,000 places once).
"""
import os
import sys
import time
import numpy as np
import scipy.sparse as sp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from network import network, program, damaged
from solve.form import Problem, FLOW, OTHER, INTERNAL, Work
from solve.lp import Kept
from solve import ranked, fair, distance
from solve.select import Selector

LIMIT = 600.0


def load():
    return os.getloadavg()[0]


def scenario(share, name):
    net = network(int(30000 * share), int(35000 * share), int(15000 * share))
    mult = {'shortage': 1.45, 'global': 1.7}.get(name, 1.0)
    up = damaged(net, int(1000 * share)) if name == 'damaged' else None
    return net, net['need'] * mult, up


def network_problem(net, need, up, objectives=1):
    """The route-and-level program as a Problem: objective `min sum(short)`; with 2, a second objective
    `min sum(supply)` (no surplus draw); one claim per place on its use."""
    A, rl, ru, lo, hi, at = program(net, need=need, up=up, shortfall=True)
    n = A.shape[1]
    kind = np.full(n, FLOW, dtype=np.int8)
    kind[at['level']] = OTHER
    kind[at['short']] = INTERNAL
    target = np.zeros(n)
    target[at['use']] = need
    p = Problem(lo, hi, target=target, kind=kind)
    p.rows(A, rl, ru)
    c = np.zeros(n); c[at['short']] = 1.0
    p.minimize(c)
    if objectives > 1:
        c = np.zeros(n); c[at['supply']] = 1.0
        p.minimize(c)
    for j, q in zip(at['use'].tolist(), need.tolist()):
        p.claim(j, q)
    return p, at


def best(fn, repeat):
    times, out = [], None
    for _ in range(repeat):
        t = time.perf_counter(); out = fn(); times.append(time.perf_counter() - t)
    return min(times), out


# -- sections ------------------------------------------------------------------------------------
def sec_ranked(share, repeat):
    """Two ranked objectives, pin against row: time, kept optima, and how far the answers differ."""
    for name in ('normal', 'shortage'):
        net, need, up = scenario(share, name)
        p, at = network_problem(net, need, up, objectives=2)
        w = Work(p)
        res = {}
        for method in ('pin', 'row'):
            def run():
                k = Kept(w.A, w.row_lower, w.row_upper, w.lower, w.upper)
                face = ranked.Face(w.lower, w.upper, w.row_lower, w.row_upper)
                x, optima, st = ranked.optimize(k, face, w.costs, method)
                return x, optima, st, k.iterations
            t, (x, optima, st, its) = best(run, repeat)
            lost = ranked.check(w.costs, optima, x, tol=1e-7)
            res[method] = x
            print(f'ranked {share:g} {name:9s} {method}: {t:6.2f} s, {its} iterations, optima '
                  f'{[round(v * s, 6) for v, s in zip(optima, w.cost_norms)]}, fixed {st}, optimum lost: {bool(lost)} '
                  f'[load {load():.1f}]', flush=True)


def sec_fair(share, repeat, names=('normal', 'shortage', 'damaged', 'global')):
    for name in names:
        net, need, up = scenario(share, name)
        p, at = network_problem(net, need, up)
        sel = Selector(p)
        reps = repeat if share <= 0.1 else 1
        t, ans = best(lambda: sel_fresh(p).solve(fair_limit=LIMIT), reps)
        s = ans.stats['fair0']
        stopped = ' STOPPED at the limit' if s.get('stopped') else ''
        lv = ans.levels[0][1]
        print(f'fair {share:g} {name:9s}: whole solve {t:6.2f} s (ranked {ans.stats["t_ranked"]:.2f}, fair '
              f'{ans.stats["t_fair"]:.2f}, distance {ans.stats["t_distance"]:.2f}); {s["programs"]} programs, '
              f'{s["iterations"]} iterations, {s["distinct"]} distinct levels, {int((lv < 1 - 1e-7).sum())} claims below 100%'
              f'{stopped} [load {load():.1f}]', flush=True)


def sel_fresh(p):
    return Selector(p)


def sec_distance(share, repeat):
    """The distance step at scale after objective 1, with no fair rank before it (its own cost)."""
    for name in ('normal', 'shortage', 'damaged'):
        net, need, up = scenario(share, name)
        p, at = network_problem(net, need, up)
        w = Work(p)
        k = Kept(w.A, w.row_lower, w.row_upper, w.lower, w.upper)
        face = ranked.Face(w.lower, w.upper, w.row_lower, w.row_upper)
        ranked.optimize(k, face, w.costs)

        def run():
            lo, hi = face.lower.copy(), face.upper.copy()
            x, s1 = distance.nearest(w.A, face.row_lower, face.row_upper, lo, hi, w.target, (w.kind == FLOW).astype(float))
            flows = w.kind == FLOW
            lo[flows] = hi[flows] = x[flows]
            x, s2 = distance.nearest(w.A, face.row_lower, face.row_upper, lo, hi, w.target, (w.kind == OTHER).astype(float))
            return x, s1, s2
        t, (x, s1, s2) = best(run, repeat)
        viol = np.abs(w.A @ x - np.clip(w.A @ x, face.row_lower, face.row_upper)).max()
        print(f'distance {share:g} {name:9s}: {t:6.2f} s; flows {s1.outer} outer / {s1.newton} Newton / {s1.factorizations} '
              f'factorizations, others {s2.outer} / {s2.newton} / {s2.factorizations}; largest row violation {viol:.1e} '
              f'[load {load():.1f}]', flush=True)


def sec_join(share, repeat, joined=300):
    """Risk 3 at scale: `joined` new claimed flows at random places join a kept instance (objective 1 only),
    then leave. Warm on the kept instance against a problem formed fresh."""
    net, need, up = scenario(share, 'shortage')
    A, rl, ru, lo, hi, at = program(net, need=need, up=up, shortfall=True)
    n = A.shape[1]
    cost = np.zeros(n); cost[at['short']] = 1.0
    rng = np.random.default_rng(5)
    where = rng.integers(0, net['places'], joined)
    # a new flow out of the balance row of its place, with capacity 1 and cost -0.5 (a served value)
    newA = sp.csc_array((-np.ones(joined), (where, np.arange(joined))), shape=(A.shape[0], joined))
    k = Kept(A, rl, ru, lo, hi, cost)
    k.solve()
    t0 = time.perf_counter(); k.add_cols(np.full(joined, -0.5), np.zeros(joined), np.ones(joined), newA)
    x1, *_ , v1 = k.solve(); warm_join = time.perf_counter() - t0; it_join = k.last_iterations
    t0 = time.perf_counter(); k.delete_cols(np.arange(n, n + joined))
    x2, *_, v2 = k.solve(); warm_leave = time.perf_counter() - t0; it_leave = k.last_iterations
    A2 = sp.hstack([A, newA]).tocsr()

    def fresh():
        f = Kept(A2, rl, ru, np.r_[lo, np.zeros(joined)], np.r_[hi, np.ones(joined)], np.r_[cost, np.full(joined, -0.5)])
        return f.solve()[-1]
    tf, vf = best(fresh, repeat)
    k0 = Kept(A, rl, ru, lo, hi, cost)
    tf0, v0 = best(lambda: Kept(A, rl, ru, lo, hi, cost).solve()[-1], 1)
    print(f'join {share:g}: {joined} flows join: warm {warm_join:.2f} s ({it_join} iterations), fresh {tf:.2f} s; '
          f'optimum {v1:.6f} against fresh {vf:.6f}; they leave: warm {warm_leave:.2f} s ({it_leave} iterations), '
          f'optimum {v2:.6f} against fresh {v0:.6f} [load {load():.1f}]', flush=True)


def sec_small(share, repeat, count=2000):
    """Solves of about ten unknowns: the provider case through the whole order, and one LP alone."""
    import cases
    p = cases.provider(6.0, 6.0).problem()
    t, _ = best(lambda: [Selector(p).solve() for _ in range(200)], repeat)
    sel = Selector(p)
    tk, _ = best(lambda: [sel.solve() for _ in range(200)], repeat)
    w = Work(p)
    k = Kept(w.A, w.row_lower, w.row_upper, w.lower, w.upper, w.costs[0])
    tl, _ = best(lambda: [k.run() for _ in range(count)], repeat)
    print(f'small: whole order, formed each time {t / 200 * 1e3:.2f} ms ({200 / t:.0f}/s); on a kept instance '
          f'{tk / 200 * 1e3:.2f} ms ({200 / tk:.0f}/s); one LP run on a kept instance {tl / count * 1e6:.0f} us '
          f'({count / tl:.0f}/s) [load {load():.1f}]', flush=True)


def sec_again(share, repeat):
    """The same problem cold, warm after another problem on the same instance, and inside a batch."""
    net, need, up = scenario(share, 'shortage')
    p, at = network_problem(net, need, up)
    cold = Selector(p).solve(fair_limit=LIMIT).x
    other, _ = network_problem(*scenario(share, 'normal'))
    sel = Selector(other)
    sel.solve(fair_limit=LIMIT)
    w = Work(p)
    sel.kept.set_bounds(np.arange(w.n), w.lower, w.upper)
    sel.kept.set_row_bounds(np.arange(w.m), w.row_lower, w.row_upper)
    sel.problem, sel.work = p, w
    warm = sel.solve(fair_limit=LIMIT).x
    # batch: the problem as the second block of a block-diagonal program with another one
    print(f'again {share:g}: cold against warm, largest difference {np.abs(cold - warm).max():.2e} '
          f'(flows {np.abs(cold - warm)[w.kind == FLOW].max():.2e}, levels {np.abs(cold - warm)[w.kind == OTHER].max():.2e})',
          flush=True)


def sec_units(share, repeat):
    """The worked network in W and in kW, and the network at scale with use and supply written in kW."""
    import cases
    a = cases.worked().solve(); b = cases.worked(unit=1e3).solve()
    d = max(abs(a[k] - b[k] * (1e3 if not k.startswith('level') and not k.startswith('short') else 1.0)) for k in a if not k.startswith('short'))
    print(f'units: worked network W against kW, largest difference in W {d:.1e}; kW use {b["use_clinic"]:.9f}', flush=True)


SECTIONS = dict(ranked=sec_ranked, fair=sec_fair, distance=sec_distance, join=sec_join, small=sec_small,
                again=sec_again, units=sec_units)

if __name__ == '__main__':
    args = sys.argv[1:]
    share, repeat = 1.0, 3
    if '--share' in args:
        i = args.index('--share'); share = float(args[i + 1]); del args[i:i + 2]
    if '--repeat' in args:
        i = args.index('--repeat'); repeat = int(args[i + 1]); del args[i:i + 2]
    names = args or ['units', 'small', 'ranked', 'distance', 'join', 'fair']
    print(f'measure.py {names} share {share} repeat {repeat}; load {load():.1f}; 4 cores', flush=True)
    for name in names:
        if name == 'fair' and not args:
            sec_fair(0.1, repeat)
            sec_fair(1.0 / 3, 1)
            sec_fair(1.0, 1)
        else:
            SECTIONS[name](share, repeat)
