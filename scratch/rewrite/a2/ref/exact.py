"""Exact linear algebra on fractions, for the least-distance rank of the selection order.

Three helpers: the solutions of a linear system, the least-squares points of an affine set, and
the simplest fraction in an interval (which turns the optimum of a float linear program back into
an exact number)."""

from fractions import Fraction


def solve_affine(rows, n):
    """Every solution of the rows `(coefficients, rhs)` in n unknowns.

    Returns (x0, basis): each solution is x0 plus a combination of the basis vectors. Returns None
    when the rows contradict each other."""
    m = [list(c) + [r] for c, r in rows]
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


def least_squares_on(x0, basis, weight, target):
    """The points of the affine set x0 + span(basis) that minimise sum(weight[j] * (x[j] - target[j])**2).

    Returns that set again as (x0, basis). A coordinate with weight zero costs nothing, so the set
    can keep some freedom; the next group of the selection order then takes it."""
    if not basis:
        return x0, basis
    k = len(basis)
    rows = []
    for a in range(k):
        coefficients = [sum(w * basis[a][j] * basis[b][j] for j, w in enumerate(weight) if w) for b in range(k)]
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
