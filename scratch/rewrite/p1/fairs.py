"""Prototype P1, fair sharing: the library's sequential method against variants on `highspy`.

Not a test and not linted. Every variant computes the spec's levels (the lexicographic max-min of
the served fractions, tier by tier) by the library's exact rule: in the program `max t` over the
pending claims, a claim whose row has a dual above TAU is at t* in every optimal answer and is held
there by a floor t* - FIX. The variants change how the programs are run, never that rule:

- `highs-primal`: the library's method on HiGHS 1.16 through `highspy` (its own instance, the basis
  of the objective's program, its vectorized model edits), the primal simplex after the first
  program, as the library runs it on SciPy's HiGHS 1.12;
- `highs-dual`: the same with the dual simplex after each fixing;
- `pieces`: the face split into its connected parts (columns joined by the rows and claims that read
  them, the fixed columns left out): one column t_p for each part with pending claims, and one
  program `max sum_p t_p` advances every part at once, since the parts share no row. The duals of
  each part's claims sum to one; each part holds its own claims. Exact for parts that share no row.

Tolerances: `--tol` sets the primal feasibility tolerance of the programs (the library's 1e-10),
`--fix` the slack of a held floor (FIX, 1e-7). An answer is checked against its program (A x on our
own copy of the matrix) as `kept.Kept.run` does, and a miss above MISS x tol renews the instance.

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/fairs.py TAG VARIANT [--tol T] [--fix F]
        [--repeat R] [--distance clarabel|library]

Prints the time, programs, levels, iterations, tight runs and renewals, and the levels against the
library's (`lab.export`): the largest difference and each claim held at another level by more than
1e-6 (a near-tie, with its size). `--distance` runs that distance step on the variant's face and
measures the answer (`lab.measures`). Appends a record to /home/user/p1-data/fair.jsonl.
"""

import copy
import json
import sys
import time

import lab
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components

import highspy
from napkin.engine.solve import Budget, ranked
from napkin.engine.solve.failures import FAIR_BUDGET, NUMERICAL, SolveFailure
from napkin.engine.solve.scaled import row_max

INF = highspy.kHighsInf
TAU = 1e-9
FULL = 1e-9
MISS = 10.0
UPDATES = 100
TIGHT = 1e-10
OPTIMAL = highspy.HighsModelStatus.kOptimal
STATED = (
    OPTIMAL,
    highspy.HighsModelStatus.kModelEmpty,
    highspy.HighsModelStatus.kInfeasible,
    highspy.HighsModelStatus.kUnbounded,
    highspy.HighsModelStatus.kUnboundedOrInfeasible,
)
BASIC = highspy.HighsBasisStatus.kBasic
AT_UPPER = highspy.HighsBasisStatus.kUpper
STATUS = {int(s): s for s in highspy.HighsBasisStatus.__members__.values()}


def _i32(v):
    return np.ascontiguousarray(v, dtype=np.int32)


def _f64(v):
    return np.ascontiguousarray(v, dtype=np.float64)


class Instance:
    """One highspy instance of a program min c.x over rows and bounds, with our own copy of its
    matrix for the check of each answer, and the renewal of `kept.Kept.run`."""

    def __init__(self, A, row_lower, row_upper, lower, upper, cost, options):
        self.A = sp.csr_array(A)
        self.row_lower, self.row_upper = _f64(row_lower).copy(), _f64(row_upper).copy()
        self.lower, self.upper = _f64(lower).copy(), _f64(upper).copy()
        self.cost = _f64(cost).copy()
        self.options = dict(options)
        self.renewals = 0
        self.iterations = 0
        self.h = self._fresh()

    def _fresh(self, basis=None):
        h = highspy.Highs()
        h.setOptionValue('output_flag', False)
        for name, value in self.options.items():
            h.setOptionValue(name, value)
        A = sp.csc_array(self.A)
        A.sort_indices()
        lp = highspy.HighsLp()
        lp.num_col_, lp.num_row_ = A.shape[1], A.shape[0]
        lp.col_cost_ = self.cost
        lp.col_lower_, lp.col_upper_ = self.lower, self.upper
        lp.row_lower_, lp.row_upper_ = self.row_lower, self.row_upper
        lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
        lp.a_matrix_.start_ = _i32(A.indptr)
        lp.a_matrix_.index_ = _i32(A.indices)
        lp.a_matrix_.value_ = _f64(A.data)
        lp.a_matrix_.num_col_, lp.a_matrix_.num_row_ = A.shape[1], A.shape[0]
        h.passModel(lp)
        if basis is not None:
            h.setBasis(basis)
        return h

    @property
    def n(self):
        return self.A.shape[1]

    @property
    def m(self):
        return self.A.shape[0]

    def option(self, name, value):
        self.options[name] = value
        self.h.setOptionValue(name, value)

    def set_basis(self, cols, rows):
        basis = highspy.HighsBasis()
        basis.col_status = [STATUS[int(s)] for s in cols]
        basis.row_status = [STATUS[int(s)] for s in rows]
        basis.valid = True
        basis.alien = True
        self.h.setBasis(basis)

    def set_cost(self, index, cost):
        index = _i32(index)
        self.cost[index] = cost
        if len(index):
            self.h.changeColsCost(len(index), index, _f64(self.cost[index]))

    def set_bounds(self, index, lower, upper):
        index = _i32(index)
        if len(index):
            self.lower[index], self.upper[index] = lower, upper
            self.h.changeColsBounds(len(index), index, _f64(self.lower[index]), _f64(self.upper[index]))

    def set_row_bounds(self, index, lower, upper):
        index = _i32(index)
        if len(index):
            self.row_lower[index], self.row_upper[index] = lower, upper
            self.h.changeRowsBounds(
                len(index), index, _f64(self.row_lower[index]), _f64(self.row_upper[index])
            )

    def add_cols(self, cost, lower, upper, columns):
        columns = sp.csc_array(columns)
        columns.sort_indices()
        k = len(lower)
        self.h.addCols(
            k, _f64(cost), _f64(lower), _f64(upper), columns.nnz, _i32(columns.indptr[:-1]),
            _i32(columns.indices), _f64(columns.data),
        )  # fmt: skip
        first = self.n
        self.A = sp.csr_array(sp.hstack([self.A, columns]))
        self.lower, self.upper = np.r_[self.lower, lower], np.r_[self.upper, upper]
        self.cost = np.r_[self.cost, cost]
        return np.arange(first, self.n)

    def add_rows(self, lower, upper, rows):
        rows = sp.csr_array(rows)
        rows.sort_indices()
        k = rows.shape[0]
        self.h.addRows(
            k, _f64(lower), _f64(upper), rows.nnz, _i32(rows.indptr[:-1]), _i32(rows.indices),
            _f64(rows.data),
        )  # fmt: skip
        first = self.m
        self.A = sp.csr_array(sp.vstack([self.A, rows]))
        self.row_lower, self.row_upper = np.r_[self.row_lower, lower], np.r_[self.row_upper, upper]
        return np.arange(first, self.m)

    def run(self):
        """One run, checked; a run that is no answer is made again on a fresh instance with the
        basis, then on one with none by the dual simplex (`kept.Kept.run`)."""
        result = self._checked(self._once())
        if not result['answered']:
            self.h = self._fresh(self.h.getBasis())
            self.renewals += 1
            result = self._checked(self._once())
        if not result['answered']:
            self.h = self._fresh()
            self.renewals += 1
            saved = self.options.get('simplex_strategy')
            self.h.setOptionValue('simplex_strategy', 1)
            result = self._checked(self._once())
            if saved is not None:
                self.h.setOptionValue('simplex_strategy', saved)
        return result

    def _once(self):
        h = self.h
        h.run()
        status = h.getModelStatus()
        info = h.getInfo()
        iterations = max(0, info.simplex_iteration_count)
        self.iterations += iterations
        if status != OPTIMAL:
            return dict(status=status, iterations=iterations)
        solution = h.getSolution()
        return dict(
            status=status,
            x=np.array(solution.col_value),
            d=np.array(solution.col_dual),
            row_value=np.array(solution.row_value),
            y=np.array(solution.row_dual),
            iterations=iterations,
        )

    def _checked(self, result):
        result['answered'] = result['status'] in STATED
        if result['status'] == OPTIMAL:
            x = result['x']
            value = self.A @ x
            size = 1.0 + abs(self.A) @ np.abs(x)
            rows = np.maximum(self.row_lower - value, value - self.row_upper) / size
            columns = np.maximum(self.lower - x, x - self.upper) / (1.0 + np.abs(x))
            result['missed'] = float(max(rows.max(initial=0.0), columns.max(initial=0.0)))
            tol = self.options['primal_feasibility_tolerance']
            result['answered'] = result['missed'] <= MISS * tol
        return result

    def wrong_sign(self, result):
        """The largest dual of the wrong sign for the side its column or row rests on (`ranked`)."""
        return max(
            ranked._wrong(result['x'], result['d'], self.lower, self.upper),
            ranked._wrong(result['row_value'], result['y'], self.row_lower, self.row_upper),
        )


def pieces(face, w, columns):
    """The connected part of each column of `columns`' claims: columns joined by a row of the face or
    a claim that reads them, the fixed columns left out. Gives (labels of the claims, count)."""
    A, _, _ = face.arrays(w.A)
    A = sp.csr_array(A)
    free = (face.lower < face.upper).astype(float)
    n = len(free)
    M = sp.vstack([A, w.F]).tocsr() @ sp.diags_array(free)
    M = sp.csr_array(M)
    M.eliminate_zeros()
    rows = M.shape[0]
    graph = sp.bmat([[None, M], [M.T, None]]).tocsr()  # rows first, then columns
    count, label = connected_components(graph, directed=False)
    claims = label[A.shape[0] : A.shape[0] + w.F.shape[0]]
    return claims, count, label[rows:], n


def share(face, w, budget, work, variant, tol, fix, basis=None, report=None):
    """The levels of every tier by `variant`, holding each claim on `face` as the library does."""
    options = {'primal_feasibility_tolerance': tol, 'simplex_update_limit': UPDATES, 'threads': 1}
    A, row_lower, row_upper = face.arrays(w.A)
    inst = Instance(A, row_lower, row_upper, face.lower, face.upper, np.zeros(w.n), options)
    if basis is not None and A.shape[0] == len(basis[1]):
        inst.set_basis(basis[0], basis[1])
    levels = np.full(len(w.request), np.nan)
    for tier in np.unique(w.tier).tolist():
        chosen = np.flatnonzero(w.tier == tier)
        levels[chosen] = _tier(inst, face, w, chosen, tier, budget, work, variant, fix, report)
    work.iterations += inst.iterations
    work.renewals += inst.renewals
    return levels


def _tier(inst, face, w, chosen, tier, budget, work, variant, fix, report):
    F = sp.csr_array(w.F[chosen])
    K, width = F.shape
    levels = np.full(K, np.nan)
    fixed = face.lower == face.upper
    constant = np.diff(F.indptr) == np.diff(sp.csr_array(F[:, fixed]).indptr)
    if constant.any():
        levels[constant] = np.minimum(1.0, F[constant] @ np.where(fixed, face.lower, 0.0))
    pending = ~constant
    if not pending.any():
        return levels
    step = f'fair sharing, tier {tier}'
    if variant == 'pieces':
        label, count, _, _ = pieces(face, w, None)
        label = label[chosen]
        names, part = np.unique(label[pending], return_inverse=True)
        piece = np.full(K, -1)
        piece[pending] = part
        if report is not None:
            sizes = np.bincount(part)
            report.update(parts=int(len(names)), largest=int(sizes.max()), components=int(count))
    else:
        piece = np.where(pending, 0, -1)
    P = int(piece.max()) + 1
    scale = 1.0 / np.maximum(1.0, row_max(F))
    single = np.diff(F.indptr) == 1
    t = inst.add_cols(np.full(P, -1.0), np.full(P, -INF), np.ones(P), sp.csc_array((inst.m, P)))
    T = sp.csr_array(
        (-scale[pending], (np.flatnonzero(pending), piece[pending])), shape=(K, P)
    )
    rows = sp.hstack([sp.diags_array(scale) @ F, sp.csr_array((K, inst.n - width - P)), T]).tocsr()
    first = inst.add_rows(np.where(pending, 0.0, -INF), np.full(K, INF), rows)
    # each t starts at its upper bound, the new rows basic
    basis = inst.h.getBasis()
    if basis.valid:
        cols = list(basis.col_status)
        for j in t.tolist():
            if cols[j] != BASIC:
                cols[j] = AT_UPPER
        inst.set_basis(cols, list(basis.row_status))
    reached = []
    programs = 0
    try:
        inst.option('simplex_strategy', 1)  # HiGHS's default, the dual simplex, as the library's first program
        while pending.any():
            if work.fair_programs >= budget.fair_programs:
                raise SolveFailure(FAIR_BUDGET, step, f'{programs} programs', {'programs': programs})
            result = inst.run()
            work.programs += 1
            work.fair_programs += 1
            programs += 1
            if result['status'] != OPTIMAL or not result['answered']:
                raise SolveFailure(NUMERICAL, step, f'status {result["status"]}', {'programs': programs})
            if inst.wrong_sign(result) > TAU:
                work.tight += 1
                saved = inst.options['primal_feasibility_tolerance']
                inst.option('dual_feasibility_tolerance', TIGHT)
                inst.option('primal_feasibility_tolerance', TIGHT)
                result = inst.run()
                inst.option('dual_feasibility_tolerance', 1e-7)
                inst.option('primal_feasibility_tolerance', saved)
                if result['status'] != OPTIMAL:
                    raise SolveFailure(NUMERICAL, step, 'tight run', {'programs': programs})
            if programs == 1:
                inst.option('simplex_strategy', 1 if variant == 'highs-dual' else 4)
            x, y = result['x'], result['y']
            level_of = x[t]
            held = np.zeros(K, bool)
            level = np.full(K, np.nan)
            for p in np.unique(piece[pending]).tolist():
                mine = pending & (piece == p)
                if level_of[p] >= 1.0 - FULL:
                    held |= mine
                    level[mine] = 1.0
                else:
                    stuck = mine & (y[first] > TAU)
                    if not stuck.any():
                        raise SolveFailure(NUMERICAL, step, 'no claim has a dual', {'programs': programs})
                    held |= stuck
                    level[stuck] = level_of[p]
            for p in np.unique(piece[held]).tolist():
                reached.append(float(level[held & (piece == p)][0]))
            index = np.flatnonzero(held)
            levels[index] = level[index]
            pending[index] = False
            _hold(inst, face, F, scale, first, index, single, level[index], width, fix)
            # a part with no pending claim leaves the objective
            done = [p for p in range(P) if not (pending & (piece == p)).any() and inst.cost[t[p]] != 0]
            if done:
                inst.set_cost(t[done], 0.0)
                inst.set_bounds(t[done], np.full(len(done), -INF), np.full(len(done), INF))
    finally:
        work.levels += len({round(v / fix) for v in reached})
        _remove(inst, first, t)
    return levels


def _hold(inst, face, F, scale, first, index, single, level, width, fix):
    inst.set_row_bounds(first[index], np.full(len(index), -INF), np.full(len(index), INF))
    floor = np.minimum(level, 1.0) - fix
    one = single[index]
    if one.any():
        claims = index[one]
        columns = F.indices[F.indptr[claims]]
        a = F.data[F.indptr[claims]]
        rising = a > 0
        np.maximum.at(face.lower, columns[rising], floor[one][rising] / a[rising])
        np.minimum.at(face.upper, columns[~rising], floor[one][~rising] / a[~rising])
        inst.set_bounds(columns, face.lower[columns], face.upper[columns])
    many = index[~single[index]]
    if len(many):
        rows = sp.csr_array(sp.diags_array(scale[many]) @ F[many])
        lower = scale[many] * floor[~one]
        inst.add_rows(lower, np.full(len(many), INF), sp.hstack([rows, sp.csr_array((len(many), inst.n - width))]))
        face.add(rows, lower, np.full(len(many), INF))


def _remove(inst, first, t):
    """Free the tier's claim rows and its t columns (their cost to zero): the next tier adds its own."""
    inst.set_row_bounds(first, np.full(len(first), -INF), np.full(len(first), INF))
    inst.set_cost(t, 0.0)
    inst.set_bounds(t, np.full(len(t), -INF), np.full(len(t), INF))


def library_share(variant, tol=1e-10, fix=1e-7):
    """A `fair.share` replacement for the library's Solver (the correctness runs)."""

    def replacement(kept, face, w, budget, work):
        basis = kept.s.getBasis()
        statuses = None
        if basis.valid and len(basis.row_status) == len(face.row_lower) and not face.extra:
            statuses = ([int(s) for s in basis.col_status], [int(s) for s in basis.row_status])
        return share(face, w, budget, work, variant, tol, fix, statuses)

    return replacement


def run(tag, variant, tol, fix, repeat, after_distance):
    from napkin.engine.solve.solver import Work

    state = lab.read(tag)
    w, after = state['w'], state['after']
    times, results = [], []
    for _ in range(repeat):
        face = copy.deepcopy(after['face'])
        work = Work()
        report = {}
        clock = time.perf_counter()
        try:
            if variant == 'library':
                from napkin.engine.solve import fair

                fair.TIGHT, fair.FIX = tol, fix
                problem = lab.scenario_problem(*_scenario(tag)) if tag.startswith('bench') else lab.engine_problem(int(tag.split('-')[1]))
                done = lab.prefix(problem)
                levels, face, work = done['levels'], done['face'], done['work']
                seconds = done['times']['fair']
            else:
                levels = share(
                    face, w, Budget(fair_programs=5000), work, variant, tol, fix,
                    (after['col_status'], after['row_status']), report,
                )  # fmt: skip
                seconds = time.perf_counter() - clock
            failure = None
        except SolveFailure as stopped:
            levels, seconds, failure = None, time.perf_counter() - clock, str(stopped)
        times.append(seconds)
        results.append((levels, face, work, report, failure))
    levels, face, work, report, failure = results[0]
    same = (
        all(r[0] is not None and np.array_equal(r[0], levels) for r in results[1:]) if repeat > 1 else None
    )
    record = dict(
        tag=tag, variant=variant, tol=tol, fix=fix, seconds=min(times), all=times, repeat=repeat,
        bitwise=same, failure=failure, programs=work.fair_programs, levels=work.levels,
        iterations=work.iterations, tight=work.tight, renewals=work.renewals, report=report,
        load=lab.load(), version=lab.library_version(),
    )  # fmt: skip
    if levels is not None:
        base = state['levels']
        delta = levels - base
        record['level diff'] = float(np.abs(delta).max(initial=0.0))
        flips = np.flatnonzero(np.abs(delta) > 1e-6)
        record['near ties'] = [(int(i), float(base[i]), float(levels[i])) for i in flips[:20]]
        record['near tie count'] = int(len(flips))
        if after_distance:
            sub = dict(state, face=face, levels=levels)
            if after_distance == 'clarabel':
                import qp

                qp._clarabel_iterations()
                clock = time.perf_counter()
                xi, infos = qp.candidate('clarabel', sub)
                record['distance'] = dict(method='clarabel', seconds=time.perf_counter() - clock, infos=infos)
            else:
                xi, dwork, dseconds = lab.library_distance(sub)
                record['distance'] = dict(method='library', seconds=dseconds, newton=dwork.newton)
            try:
                reference = np.load(f'{lab.DATA}/{tag}-library.npy')
            except FileNotFoundError:
                reference = None
            record['measures'] = lab.measures(sub, xi, reference)
    with open(f'{lab.DATA}/fair.jsonl', 'a') as f:
        f.write(json.dumps(record, default=str) + '\n')
    shown = {k: v for k, v in record.items() if k not in ('all', 'version', 'near ties')}
    print(f'{tag} {variant} tol {tol:g} fix {fix:g}: {shown}', flush=True)
    if record.get('near ties'):
        print(f'  near ties (claim, library level, variant level): {record["near ties"][:8]}', flush=True)


def _scenario(tag):
    _, places, name = tag.split('-')
    return int(places) / 30000, name


if __name__ == '__main__':
    args = sys.argv[1:]

    def option(name, default, kind):
        if name in args:
            i = args.index(name)
            value = kind(args[i + 1])
            del args[i : i + 2]
            return value
        return default

    tol = option('--tol', 1e-10, float)
    fix = option('--fix', 1e-7, float)
    repeat = option('--repeat', 1, int)
    after_distance = option('--distance', None, str)
    run(args[0], args[1], tol, fix, repeat, after_distance)
