"""Exact linear algebra on fractions, for the least-distance rank of the selection order.

Three helpers: the solutions of a linear system, the least-squares points of an affine set, and
the simplest fraction in an interval (which turns the optimum of a float linear program back into
an exact number)."""

from fractions import Fraction


def solve_affine(rows, n):
    """Every solution of the rows `(coefficients, rhs)` in n unknowns.

    Returns (x0, basis): each solution is x0 plus a combination of the basis vectors. Returns None
    when the rows contradict each other."""
    m = [[*c, r] for c, r in rows]
    pivots = []
    r = 0
    for col in range(n):
        p = next((i for i in range(r, len(m)) if m[i][col] != 0), None)
        if p is None:
            continue
        m[r], m[p] = m[p], m[r]
        lead = m[r][col]
        m[r] = [x / lead for x in m[r]]
        for i in range(len(m)):
            if i != r and m[i][col] != 0:
                f = m[i][col]
                m[i] = [a - f * b for a, b in zip(m[i], m[r])]
        pivots.append(col)
        r += 1
    if any(row[n] != 0 for row in m[r:]):
        return None
    x0 = [Fraction(0)] * n
    for i, col in enumerate(pivots):
        x0[col] = m[i][n]
    basis = []
    for free in (c for c in range(n) if c not in pivots):
        v = [Fraction(0)] * n
        v[free] = Fraction(1)
        for i, col in enumerate(pivots):
            v[col] = -m[i][free]
        basis.append(v)
    return x0, basis


def project_minimum(rows, dimensions, limit):
    """Eliminate all but the final coordinate from rational inequalities, then minimize it.

    Each row gives coefficients followed by a right-hand side. Pair upper and lower
    bounds on an eliminated coordinate (Fourier–Motzkin). Parallel rows keep only
    the tightest bound. The caller limits the work to the small oracle domain.
    """

    def compact(inequalities):
        tightest = {}
        for *coeffs, rhs in inequalities:
            scale = next((abs(x) for x in coeffs if x), None)
            if scale is None:
                if rhs < 0:
                    return None
                continue
            direction = tuple(x / scale for x in coeffs)
            bound = rhs / scale
            if direction not in tightest or bound < tightest[direction]:
                tightest[direction] = bound
        return [(*key, rhs) for key, rhs in tightest.items()]

    rows = compact(rows)
    for width in range(dimensions, 1, -1):
        if not rows:
            break

        def pair_count(i):
            return sum(r[i] > 0 for r in rows) * sum(r[i] < 0 for r in rows)

        i = min(range(width - 1), key=pair_count)
        if pair_count(i) > limit:
            raise OverflowError('exact linear projection exceeds the reference work limit')
        positive, negative, kept = [], [], []
        for row in rows:
            a = row[i]
            rest = row[:i] + row[i + 1 :]
            if a:
                (positive if a > 0 else negative).append(tuple(x / abs(a) for x in rest))
            else:
                kept.append(rest)
        rows = compact([*kept, *(tuple(x + y for x, y in zip(p, n)) for p in positive for n in negative)])
    if rows is None:
        return 'infeasible', None
    lower = max((rhs / a for a, rhs in rows if a < 0), default=None)
    upper = min((rhs / a for a, rhs in rows if a > 0), default=None)
    if lower is not None and upper is not None and lower > upper:
        return 'infeasible', None
    if lower is None:
        return 'unbounded', None
    return 'optimal', lower


def least_squares_on(x0, basis, weight, target):
    """The points of the affine set x0 + span(basis) that minimise sum(weight[j] * (x[j] - target[j])**2).

    Returns that set again as (x0, basis). A coordinate with weight zero costs nothing, so the set
    can keep some freedom; the next group of the selection order then takes it."""
    if not basis:
        return x0, basis
    k = len(basis)
    rows = []
    for a in range(k):
        coefficients = [
            sum(w * basis[a][j] * basis[b][j] for j, w in enumerate(weight) if w) for b in range(k)
        ]
        rhs = sum(w * basis[a][j] * (target[j] - x0[j]) for j, w in enumerate(weight) if w)
        rows.append((coefficients, rhs))
    z0, zbasis = solve_affine(rows, k)  # the normal equations always have a solution
    point = [x0[j] + sum(z0[a] * basis[a][j] for a in range(k)) for j in range(len(x0))]
    rest = [[sum(z[a] * basis[a][j] for a in range(k)) for j in range(len(x0))] for z in zbasis]
    return point, rest


def simplest_between(lo, hi):
    """The fraction with the smallest denominator in the closed interval [lo, hi]."""
    lo, hi = Fraction(lo), Fraction(hi)
    if lo > hi:
        lo, hi = hi, lo
    if lo <= 0 <= hi:
        return Fraction(0)
    if hi < 0:
        return -simplest_between(-hi, -lo)
    whole = lo.numerator // lo.denominator
    if whole == lo:
        return Fraction(whole)
    if whole + 1 <= hi:
        return Fraction(whole + 1)
    rest = simplest_between(1 / (hi - whole), 1 / (lo - whole))
    return whole + 1 / rest
