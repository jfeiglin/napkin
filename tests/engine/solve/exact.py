"""An exact reference of the selection order for tiny problems, in rational arithmetic.

Nothing here comes from the library. A problem is a list of unknowns with finite boxes, and
constraints `(a, sense, b)` meaning a.x <= b, a.x == b or a.x >= b over `Fraction`s:

- a linear program is solved by a two-phase simplex method with Bland's rule (`linear`);
- each written objective adds the equality c.x == its optimum: the optimal face, exactly;
- fair sharing is the sequential definition, by brute force: `max t` over the pending claims of a
  tier, then for each pending claim `max f.x` with every pending claim at t* or more; a claim that
  cannot rise is held at t*;
- a distance stage first projects out the coordinates that it does not weigh (Fourier-Motzkin
  elimination), then finds the nearest point by enumerating the sets of active constraints.
"""

from fractions import Fraction
from itertools import combinations

LE, EQ, GE = '<=', '==', '>='


class Infeasible(Exception):
    pass


def linear(cost, constraints, n, maximize=False):
    """The optimum of cost.x over the constraints, with x free; gives (value, x)."""
    # x = y - shift with y >= 0, where `shift` keeps every coordinate of a bounded problem positive
    shift = Fraction(1000)
    rows = []
    for a, sense, b in constraints:
        moved = b + sum(a) * shift  # a.(y - shift) <op> b
        if sense in (LE, EQ):
            rows.append((list(a), moved, sense))
        if sense == GE:
            rows.append(([-v for v in a], -moved, LE))
    sign = -1 if maximize else 1
    value, y = _simplex([sign * v for v in cost], rows, n)
    return sign * value - sum(cost) * shift, [v - shift for v in y]


def _simplex(cost, rows, n):
    """min cost.y, y >= 0, over rows (a, b, '<=' or '=='): two phases, Bland's rule."""
    slacks = [i for i, (_, _, sense) in enumerate(rows) if sense == LE]
    width = n + len(slacks) + len(rows)  # y, slacks, one artificial for each row
    table, basis = [], []
    for i, (a, b, _) in enumerate(rows):
        line = [Fraction(v) for v in a] + [Fraction(0)] * (width - n) + [Fraction(b)]
        if i in slacks:
            line[n + slacks.index(i)] = Fraction(1)
        if line[-1] < 0:
            line = [-v for v in line]
        line[n + len(slacks) + i] = Fraction(1)
        table.append(line)
        basis.append(n + len(slacks) + i)
    artificial = set(range(n + len(slacks), width))
    _phase(table, basis, [Fraction(int(j in artificial)) for j in range(width)], set())
    if sum(table[i][-1] for i, j in enumerate(basis) if j in artificial) != 0:
        raise Infeasible
    for i, j in enumerate(basis):
        if j in artificial:  # an artificial at zero leaves the basis where any other column can enter
            entering = next((k for k in range(width) if k not in artificial and table[i][k] != 0), None)
            if entering is not None:
                _pivot(table, basis, i, entering)
    full = [Fraction(v) for v in cost] + [Fraction(0)] * (width - n)
    _phase(table, basis, full, artificial)
    y = [Fraction(0)] * width
    for i, j in enumerate(basis):
        y[j] = table[i][-1]
    return sum(c * v for c, v in zip(full, y)), y[:n]


def _phase(table, basis, cost, barred):
    while True:
        reduced = [
            cost[k] - sum(cost[j] * table[i][k] for i, j in enumerate(basis)) for k in range(len(cost))
        ]
        entering = next((k for k in range(len(cost)) if k not in barred and reduced[k] < 0), None)
        if entering is None:
            return
        ratios = [
            (table[i][-1] / table[i][entering], basis[i], i)
            for i in range(len(table))
            if table[i][entering] > 0
        ]
        if not ratios:
            raise ValueError('unbounded')
        _pivot(table, basis, min(ratios)[2], entering)


def _pivot(table, basis, row, column):
    pivot = table[row][column]
    table[row] = [v / pivot for v in table[row]]
    for i in range(len(table)):
        if i != row and table[i][column] != 0:
            factor = table[i][column]
            table[i] = [v - factor * w for v, w in zip(table[i], table[row])]
    basis[row] = column


def eliminate(constraints, j):
    """The constraints with x_j projected out: by an equality that holds x_j where there is one,
    else by Fourier-Motzkin elimination."""
    for a, sense, b in constraints:
        if sense == EQ and a[j] != 0:
            # x_j = (b - sum of the others) / a_j, put into every other constraint
            out = []
            for c, s, d in constraints:
                if (c, s, d) == (a, sense, b):
                    continue
                k = c[j] / a[j]
                out.append(([ci - k * ai for ci, ai in zip(c, a)], s, d - k * b))
            return _clean(out, j)
    upper = [_as_le(c) for c in constraints if _as_le(c)[0][j] > 0]
    lower = [_as_le(c) for c in constraints if _as_le(c)[0][j] < 0]
    kept = [c for c in constraints if c[0][j] == 0]
    for a, b in upper:
        for c, d in lower:
            p, q = a[j], -c[j]
            kept.append(([q * ai + p * ci for ai, ci in zip(a, c)], LE, q * b + p * d))
    return _clean(kept, j)


def _as_le(constraint):
    a, sense, b = constraint
    if sense == GE:
        return [-v for v in a], -b
    return list(a), b


def _clean(constraints, j):
    """The constraints with x_j gone, as a.x <= b or a.x == b, each once; an empty one must hold."""
    out, seen = [], set()
    for a, sense, b in constraints:
        row = [Fraction(0) if k == j else v for k, v in enumerate(a)]
        if all(v == 0 for v in row):
            if not {LE: b >= 0, GE: b <= 0, EQ: b == 0}[sense]:
                raise Infeasible
            continue
        side, bound = (LE, b) if sense != GE else (LE, -b)
        if sense == GE:
            row = [-v for v in row]
        elif sense == EQ:
            side = EQ
        scale = max(abs(v) for v in row)
        key = (tuple(v / scale for v in row), side, bound / scale)
        if key not in seen:
            seen.add(key)
            out.append((list(key[0]), side, key[2]))
    return out


def nearest(constraints, weighed, target, weight, n):
    """The point of the constraints nearest the target in the coordinates `weighed`, with the other
    coordinates projected out; gives {coordinate: value}."""
    for j in range(n):
        if j not in weighed:
            constraints = eliminate(constraints, j)
    equal = _independent([(a, b) for a, sense, b in constraints if sense == EQ])
    loose = [_as_le(c) for c in constraints if c[1] != EQ]
    best, value = None, None
    for size in range(len(weighed) + 1):
        for chosen in combinations(range(len(loose)), size):
            active = equal + [loose[i] for i in chosen]
            x = _projection(active, weighed, target, weight, n)
            if x is None or not all(_holds(c, x) for c in constraints):
                continue
            distance = sum(weight[j] * (x[j] - target[j]) ** 2 for j in weighed)
            if value is None or distance < value:
                best, value = x, distance
    if best is None:
        raise Infeasible
    return {j: best[j] for j in weighed}


def _independent(equal):
    """The equalities without those that the others imply (an equality that contradicts them would
    leave the problem infeasible, which the earlier steps rule out)."""
    kept, reduced = [], []
    for a, b in equal:
        row = [*a, b]
        for pivot, base in reduced:
            if row[pivot] != 0:
                factor = row[pivot] / base[pivot]
                row = [v - factor * w for v, w in zip(row, base)]
        pivot = next((k for k, v in enumerate(row[:-1]) if v != 0), None)
        if pivot is None:
            if row[-1] != 0:
                raise Infeasible
            continue
        reduced.append((pivot, row))
        kept.append((a, b))
    return kept


def _projection(active, weighed, target, weight, n):
    """min sum w (x - c)^2 with each active a.x == b: x = c - W^-1 A' v, (A W^-1 A') v = A c - b."""
    if not active:
        return {j: target[j] for j in weighed} | {j: Fraction(0) for j in range(n) if j not in weighed}
    matrix = [[sum(a[j] * c[j] / weight[j] for j in weighed) for c, _ in active] for a, _ in active]
    rhs = [sum(a[j] * target[j] for j in weighed) - b for a, b in active]
    v = _solve(matrix, rhs)
    if v is None:
        return None
    x = {j: target[j] - sum(vi * a[j] for vi, (a, _) in zip(v, active)) / weight[j] for j in weighed}
    return x | {j: Fraction(0) for j in range(n) if j not in weighed}


def _solve(matrix, rhs):
    """Gaussian elimination in fractions; None for a singular matrix."""
    size = len(rhs)
    rows = [[*row, b] for row, b in zip(matrix, rhs)]
    for col in range(size):
        pivot = next((r for r in range(col, size) if rows[r][col] != 0), None)
        if pivot is None:
            return None
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(size):
            if r != col and rows[r][col] != 0:
                factor = rows[r][col] / rows[col][col]
                rows[r] = [v - factor * w for v, w in zip(rows[r], rows[col])]
    return [rows[r][-1] / rows[r][r] for r in range(size)]


def _holds(constraint, x):
    a, sense, b = constraint
    value = sum(a[j] * x.get(j, 0) for j in range(len(a)))
    return {LE: value <= b, GE: value >= b, EQ: value == b}[sense]


def select(n, boxes, constraints, objectives, claims, flows, others, target, scale):
    """The selection order: (flow values, other values, fair level of each claim). `claims` holds
    (terms over the unknowns, request, tier); `flows` and `others` are the columns of each kind."""
    rows = list(constraints)
    for j, (lower, upper) in enumerate(boxes):
        unit = [Fraction(int(k == j)) for k in range(n)]
        rows += [(unit, GE, lower), (unit, LE, upper)]
    for cost in objectives:
        value, _ = linear(cost, rows, n)
        rows.append((list(cost), EQ, value))
    levels = [None] * len(claims)
    for tier in sorted({tier for _, _, tier in claims}):
        pending = [i for i, (_, _, t) in enumerate(claims) if t == tier]
        while pending:
            # max t over (x, t): f_i.x / request_i >= t for each pending claim, t <= 1
            lifted = [([*a, Fraction(0)], sense, b) for a, sense, b in rows]
            for i in pending:
                f, request, _ = claims[i]
                lifted.append(([v / request for v in f] + [Fraction(-1)], GE, Fraction(0)))
            lifted.append(([Fraction(0)] * n + [Fraction(1)], LE, Fraction(1)))
            level, _ = linear([Fraction(0)] * n + [Fraction(1)], lifted, n + 1, maximize=True)
            floors = [([v / claims[i][1] for v in claims[i][0]], GE, level) for i in pending]
            if level == 1:
                held = list(pending)
            else:
                held = [i for i in pending if _highest(rows + floors, claims[i], n) == level]
            for i in pending:
                f, request, _ = claims[i]
                sense = EQ if i in held and level < 1 else GE
                rows.append(([v / request for v in f], sense, level))
            for i in held:
                levels[i] = level
            pending = [i for i in pending if i not in held]
    weight = [1 / Fraction(s) ** 2 for s in scale]
    flow_values = nearest(rows, set(flows), target, weight, n) if flows else {}
    for j, value in flow_values.items():
        rows.append(([Fraction(int(k == j)) for k in range(n)], EQ, value))
    other_values = nearest(rows, set(others), target, weight, n) if others else {}
    return flow_values, other_values, levels


def _highest(rows, claim, n):
    f, request, _ = claim
    value, _ = linear([v / request for v in f], rows, n, maximize=True)
    return value
