"""The selection order of the spec on one small problem, by brute force.

The answer of a solve is chosen in four ranks:

1. the hard conditions: every row `lin <= 0` or `lin == 0`;
2. each written objective, minimised in written order and then kept at its optimum;
3. inherited sharing: tier by tier, the smallest served fraction is made as large as it can be,
   then the next smallest; then the preferred routes of each aggregate request;
4. the least squared distance to the targets: the flows first, then the other unknowns.

Ranks 2 and 3 are linear programs (`scipy.optimize.linprog`, HiGHS). Their optimum values come
back as floats and are turned into exact fractions (`_snap`). Rank 4 cannot be a linear program:
it is computed here in fractions, by trying sets of active inequality rows. Which claims share a
tier is the caller's affair (`network.assemble`): it is how local sharing differs from the fair
sharing of a declared solver.
"""

from fractions import Fraction
from itertools import combinations

from scipy.optimize import linprog

from .errors import Diagnostic, Infeasible, NotCovered
from .exact import least_squares_on, simplest_between, solve_affine

SNAP = Fraction(1, 10**9)  # an optimum is the simplest fraction this near to the float answer
TIGHT = 1e-9  # a row whose slack is never above this is an equality
LOOSE = 1e-7  # a row whose slack is never below this binds nowhere
LIMIT = 50_000  # the most sets of active rows that the least-distance rank will try


class Lin:
    """k + sum(c[v] * v) + sum(max(0, part)): affine in the unknowns, plus positive parts.

    A value with positive parts is convex. It may be minimised, and it may stand on the small side
    of `<=`. Anything else that would need it is refused."""

    __slots__ = ('c', 'k', 'parts')

    def __init__(self, c=None, k=0, parts=()):
        self.c = {v: x for v, x in (c or {}).items() if x != 0}
        self.k = Fraction(k)
        self.parts = tuple(parts)

    @staticmethod
    def var(v):
        """One unknown, with coefficient one."""
        return Lin({v: Fraction(1)})

    @property
    def known(self):
        """True when no unknown and no positive part remains."""
        return not self.c and not self.parts

    def __repr__(self):
        terms = [f'{x}*{v}' for v, x in self.c.items()] + [f'pos({p})' for p in self.parts]
        return ' + '.join([str(self.k), *terms])

    def __add__(self, other):
        o = lin(other)
        c = dict(self.c)
        for v, x in o.c.items():
            c[v] = c.get(v, 0) + x
        return Lin(c, self.k + o.k, self.parts + o.parts)

    __radd__ = __add__

    def __neg__(self):
        if self.parts:
            raise Diagnostic('unsupported in a solver: the negative of a positive part (not convex)')
        return Lin({v: -x for v, x in self.c.items()}, -self.k)

    def __sub__(self, other):
        return self + (-lin(other))

    def __rsub__(self, other):
        return lin(other) + (-self)

    def __mul__(self, other):
        o = lin(other)
        if not o.known:
            if not self.known:
                raise Diagnostic('unsupported in a solver: a product of two unknowns')
            return o * self.k
        f = o.k
        if self.parts and f < 0:
            raise Diagnostic('unsupported in a solver: a positive part with a negative factor (not convex)')
        return Lin(
            {v: x * f for v, x in self.c.items()}, self.k * f, [p * f for p in self.parts] if f else ()
        )

    __rmul__ = __mul__

    def __truediv__(self, other):
        o = lin(other)
        if not o.known:
            raise Diagnostic('unsupported in a solver: a division by an unknown')
        return self * (1 / o.k)

    def positive(self):
        """max(0, self)."""
        if self.parts:
            raise NotCovered('a positive part of a positive part')
        return Lin(k=max(self.k, 0)) if self.known else Lin(parts=(self,))

    def at(self, x):
        """The value at the point x (a mapping from each unknown to its value)."""
        return self.k + sum(c * x[v] for v, c in self.c.items()) + sum(max(p.at(x), 0) for p in self.parts)


def lin(x):
    """A number as a constant `Lin`; a `Lin` unchanged."""
    return x if isinstance(x, Lin) else Lin(k=x)


class Rel:
    """A relation `lin <= 0` or `lin == 0`."""

    __slots__ = ('lin', 'op')

    def __init__(self, lin_, op):
        self.lin, self.op = lin_, op

    def __repr__(self):
        return f'{self.lin} {self.op} 0'

    def holds(self, x):
        """Whether the relation holds at the point x."""
        v = self.lin.at(x)
        return v == 0 if self.op == '==' else v <= 0


def relation(a, op, b):
    """`a op b` between values of which one at least holds an unknown."""
    a, b = lin(a), lin(b)
    if op in ('<', '>', '!='):
        raise Diagnostic(f'unsupported in a solver: the relation {op} (use <=, >= or ==)')
    if op == '>=':
        a, b = b, a
    if b.parts or (op == '==' and a.parts):
        raise Diagnostic(
            'unsupported in a solver: a positive part on the large side of a relation (not convex)'
        )
    return Rel(a - b, '<=' if op != '==' else '==')


def expand(rel):
    """The plain rows of one relation: a row with k positive parts is 2**k rows without any."""
    if not rel.lin.parts:
        return [rel]
    base = Lin(rel.lin.c, rel.lin.k)
    parts = rel.lin.parts
    if len(parts) > 12:
        raise NotCovered('a relation with more than 12 positive parts')
    return [
        Rel(sum(chosen, base), '<=') for size in range(len(parts) + 1) for chosen in combinations(parts, size)
    ]


# --- ranks 1 to 3: linear programs -----------------------------------------------------------------


def _lp(variables, rows, cost):
    """Minimise the affine `cost` over the rows. Returns (status, value, point as floats)."""
    names = list(variables)
    for r in rows:
        for v in r.lin.c:
            if v not in names:
                names.append(v)  # an auxiliary unknown of this program only
    index = {v: i for i, v in enumerate(names)}
    ub, bub, eq, beq = [], [], [], []
    for r in rows:
        row = [0.0] * len(names)
        for v, x in r.lin.c.items():
            row[index[v]] = float(x)
        (eq if r.op == '==' else ub).append(row)
        (beq if r.op == '==' else bub).append(-float(r.lin.k))
    c = [0.0] * len(names)
    for v, x in cost.c.items():
        c[index[v]] = float(x)
    res = linprog(
        c,
        A_ub=ub or None,
        b_ub=bub or None,
        A_eq=eq or None,
        b_eq=beq or None,
        bounds=[(None, None)] * len(names),
        method='highs',
    )
    if res.status == 0:
        return 'optimal', res.fun + float(cost.k), res.x
    if res.status == 2:
        return 'infeasible', None, None
    if res.status == 3:
        return 'unbounded', None, None
    raise NotCovered(f'the linear program did not finish: {res.message}')


def _snap(value):
    """The exact number that a float optimum stands for."""
    return simplest_between(Fraction(value) - SNAP, Fraction(value) + SNAP)


def _minimise(variables, rows, objective, text):
    """Rank 2: one written objective. Returns the rows that keep its optimum."""
    extra, cost = [], Lin(objective.c, objective.k)
    for i, part in enumerate(objective.parts):
        u = Lin.var(('aux', i))
        extra += [Rel(part - u, '<='), Rel(-u, '<=')]
        cost = cost + u
    status, value, _ = _lp(variables, rows + extra, cost)
    if status == 'unbounded':
        raise Diagnostic(f'the objective {text} is unbounded')
    best = _snap(value)
    return expand(Rel(objective - best, '<=')), best


def _maxmin(variables, rows, claims):
    """Rank 3, one tier: make the smallest served fraction as large as it can be, then the next.

    A claim is (lin, request): its served fraction is lin / request, counted from zero up to one
    (spec, "Selection order": "A positive request measures its fulfilled fraction up to 100%"). The
    lin of a route's claim is its signed rate in the direction of its request, which is below zero
    where the route carries against it: its fraction is then zero, the rate of its leg in that
    direction (spec: "the backward leg exposes the positive part of its negation"). So where the
    smallest fraction is zero, a claim that no answer serves is held at zero and nothing more, and a
    route may carry against its request to make room for another one ("An edge may carry more than
    its own request to meet another request"); where every claim left can be served, but not all of
    them together, none is served against another: each is held at zero or above, as before."""
    rows = list(rows)
    open_ = list(claims)
    levels = []
    t = Lin.var(('aux', 't'))
    while open_:
        floor = [Rel(t * r - served, '<=') for served, r in open_] + [Rel(t - 1, '<=')]
        _, value, _ = _lp(variables, rows + floor, -t)
        level = _snap(-value)
        if level >= 1:
            rows += [Rel(Lin(k=r) - served, '<=') for served, r in open_]
            levels += [Fraction(1)] * len(open_)
            break
        if level <= 0:
            # The smallest fraction is zero: the claims that no answer serves are held there.
            unserved, still = [], []
            for served, r in open_:
                status, value, _ = _lp(variables, rows, -served)
                if status != 'unbounded' and -value <= TIGHT * max(1.0, float(r)):
                    unserved.append((served, r))
                else:
                    still.append((served, r))
            if unserved:
                rows += [Rel(served, '<=') for served, _ in unserved]
                levels += [Fraction(0)] * len(unserved)
                open_ = still
                continue
            level = Fraction(0)
        hold = [Rel(Lin(k=level * r) - served, '<=') for served, r in open_]
        still = []
        for served, r in open_:  # can this claim alone rise above the level while the others keep it?
            status, value, _ = _lp(variables, rows + hold, -served)
            if status == 'unbounded' or -value > float(level * r) + TIGHT * max(1.0, float(level * r)):
                still.append((served, r))
            else:
                rows.append(Rel(served - level * r, '=='))
                levels.append(level)
        if len(still) == len(open_):
            raise NotCovered(
                'fair sharing made no progress: the float tolerance is too coarse for this problem'
            )
        open_ = still
    return rows, levels


# --- rank 4: the least squared distance, in fractions ------------------------------------------------


def least_distance(variables, rows, groups):
    """The point of the rows that is nearest to the targets, group by group.

    `groups` is a list of mappings unknown -> (target, scale). The first group is minimised first
    (the flows), and the next groups choose among its minimisers (the other unknowns). The distance
    of a group is sum(((x - target) / scale) ** 2).

    Method. A float linear program sorts the inequality rows: a row that is tight at every feasible
    point becomes an equality, and a row that is tight at none is dropped. Then, in fractions: for a
    set of rows taken as active (as equalities), the nearest point of that affine set is the answer
    of a linear system. Each such point that satisfies every row is a feasible point, and the
    nearest point of the whole set is among them (its own active rows give it). So the feasible
    candidate with the least distance is the answer. The empty set is tried first: when its point
    is feasible it is the answer at once."""
    variables = list(variables)
    n = len(variables)

    def vector(row):
        return [row.c.get(v, Fraction(0)) for v in variables], -row.k

    equal = [r.lin for r in rows if r.op == '==']
    unequal = [r.lin for r in rows if r.op == '<=']
    facets = []
    for row in unequal:
        status, low, _ = _lp(variables, rows, row)
        if status == 'optimal' and low >= -TIGHT:
            equal.append(row)
            continue
        status, high, _ = _lp(variables, rows, -row)
        if status == 'optimal' and high >= LOOSE:
            continue
        facets.append(row)
    weights = [
        (
            [1 / Fraction(group[v][1]) ** 2 if v in group else Fraction(0) for v in variables],
            [Fraction(group[v][0]) if v in group else Fraction(0) for v in variables],
        )
        for group in groups
    ]

    def candidate(active):
        found = solve_affine([vector(row) for row in equal + list(active)], n)
        if found is None:
            return None
        x0, basis = found
        for weight, target in weights:
            x0, basis = least_squares_on(x0, basis, weight, target)
        if basis:
            raise NotCovered('an unknown without a target in the least-distance rank')
        point = dict(zip(variables, x0))
        if any(row.at(point) > 0 for row in unequal):
            return None
        cost = tuple(
            sum(w * (x - g) ** 2 for w, x, g in zip(weight, x0, target)) for weight, target in weights
        )
        return cost, x0

    best = candidate(())
    if best is None:
        hull = solve_affine([vector(row) for row in equal], n)
        if hull is None:
            raise Infeasible('the hard conditions have no exact answer')
        free = len(hull[1])
        tried = 0
        for size in range(1, free + 1):
            for active in combinations(facets, size):
                tried += 1
                if tried > LIMIT:
                    raise NotCovered('the least-distance rank is too large for the reference interpreter')
                found = candidate(active)
                if found is not None and (best is None or found[0] < best[0]):
                    best = found
    if best is None:
        raise Infeasible('the least-distance rank found no exact answer (a float optimum did not snap)')
    return dict(zip(variables, best[1]))


# --- the whole order ---------------------------------------------------------------------------------


def select(variables, rows, objectives=(), tiers=(), prefs=(), groups=()):
    """The answer of one solve: a mapping from each unknown to its exact value.

    rows        relations (`Rel`), positive parts allowed on the small side of `<=`
    objectives  (lin, text) pairs to minimise, in written order
    tiers       lists of claims (lin, request), first tier first
    prefs       (lin, amount) pairs: carry as much of `amount` on `lin` as can be, in order
    groups      the targets of the least-distance rank"""
    rows = [plain for r in rows for plain in expand(r)]
    for r in rows:
        if r.lin.known and not r.holds({}):
            raise Infeasible(f'a hard condition fails with no unknown in it: {r}')
    if not variables:
        return {}
    if _lp(variables, rows, Lin())[0] == 'infeasible':
        raise Infeasible('the hard conditions of the solve have no answer')
    for objective, text in objectives:
        kept, _ = _minimise(variables, rows, lin(objective), text)
        rows += kept
    for claims in tiers:
        rows, _ = _maxmin(variables, rows, claims)
    for carried, amount in prefs:
        u = Lin.var(('aux', 'u'))
        _, value, _ = _lp(variables, [*rows, Rel(u - carried, '<='), Rel(u - amount, '<=')], -u)
        rows.append(Rel(Lin(k=_snap(-value)) - carried, '<='))
    return least_distance(variables, rows, groups)
