"""Polynomials in the time since a moment, with exact coefficients.

Between two moments a level or a rate is a polynomial in tau, the time since the last moment. The
interpreter needs four things from one: its value at a time, its integral, its sign just after
tau = 0, and its first root after tau = 0."""

from fractions import Fraction
from math import isqrt

from .errors import NotCovered


class Poly:
    __slots__ = ('c',)

    def __init__(self, coefficients):
        c = [Fraction(x) for x in coefficients]
        while len(c) > 1 and c[-1] == 0:
            c.pop()
        self.c = tuple(c) or (Fraction(0),)

    def __repr__(self):
        return 'Poly(' + ', '.join(str(x) for x in self.c) + ')'

    @property
    def constant(self):
        return len(self.c) == 1

    def __call__(self, tau):
        total = Fraction(0)
        for x in reversed(self.c):
            total = total * tau + x
        return total

    def __add__(self, other):
        o = poly(other).c
        n = max(len(self.c), len(o))
        return Poly([(self.c[i] if i < len(self.c) else 0) + (o[i] if i < len(o) else 0) for i in range(n)])

    __radd__ = __add__

    def __neg__(self):
        return Poly([-x for x in self.c])

    def __sub__(self, other):
        return self + (-poly(other))

    def __rsub__(self, other):
        return poly(other) - self

    def __mul__(self, other):
        o = poly(other).c
        out = [Fraction(0)] * (len(self.c) + len(o) - 1)
        for i, a in enumerate(self.c):
            for j, b in enumerate(o):
                out[i + j] += a * b
        return Poly(out)

    __rmul__ = __mul__

    def __truediv__(self, other):
        o = poly(other)
        if not o.constant:
            raise NotCovered('a division by a value that moves between two moments')
        return Poly([x / o.c[0] for x in self.c])

    def __rtruediv__(self, other):
        if not self.constant:
            raise NotCovered('a division by a value that moves between two moments')
        return Poly([Fraction(other) / self.c[0]])

    def integral(self):
        """The polynomial whose derivative is this one, zero at tau = 0."""
        return Poly([0] + [x / (i + 1) for i, x in enumerate(self.c)])

    def sign_after(self):
        """The sign just after tau = 0: that of the first coefficient that is not zero."""
        for x in self.c:
            if x != 0:
                return 1 if x > 0 else -1
        return 0

    def sign_now(self):
        return (self.c[0] > 0) - (self.c[0] < 0)

    def first_root(self):
        """The smallest tau > 0 at which the polynomial is zero, or None. Exact, or not covered."""
        c = self.c
        if len(c) == 1:
            return None
        if c[0] == 0:  # a root at zero: divide it out and look at the rest
            return Poly(c[1:]).first_root()
        if len(c) == 2:
            root = -c[0] / c[1]
            return root if root > 0 else None
        if len(c) == 3:
            disc = c[1] * c[1] - 4 * c[2] * c[0]
            if disc < 0:
                return None
            root = _sqrt(disc)
            if root is None:  # kept as a float: only an error if it turns out to be the next moment
                d = float(disc) ** 0.5
                later = [r for r in ((-float(c[1]) - d) / (2 * float(c[2])), (-float(c[1]) + d) / (2 * float(c[2]))) if r > 0]
                return Irrational(min(later)) if later else None
            roots = [(-c[1] - root) / (2 * c[2]), (-c[1] + root) / (2 * c[2])]
            later = [r for r in roots if r > 0]
            return min(later) if later else None
        raise NotCovered('a level that is a polynomial of degree three or more in time')


def poly(x):
    return x if isinstance(x, Poly) else Poly([x])


def plain(x):
    """A constant polynomial as its number; anything else unchanged."""
    return x.c[0] if isinstance(x, Poly) and x.constant else x


def _sqrt(q):
    """The exact square root of a nonnegative fraction, or None when it is not rational."""
    n, d = isqrt(q.numerator), isqrt(q.denominator)
    return Fraction(n, d) if n * n == q.numerator and d * d == q.denominator else None


class Irrational:
    """A contact time that is not a rational number. It may stand among the stops; if it is the
    earliest, the run cannot go on exactly (`Run._next_time` says so)."""

    def __init__(self, x):
        self.x = x

    def __repr__(self):
        return f'irrational({self.x})'

    def __float__(self):
        return self.x

    def __lt__(self, o):
        return self.x < float(o)

    def __gt__(self, o):
        return self.x > float(o)

    def __le__(self, o):
        return self.x <= float(o)

    def __ge__(self, o):
        return self.x >= float(o)

    def __add__(self, o):
        return Irrational(self.x + float(o))

    __radd__ = __add__
