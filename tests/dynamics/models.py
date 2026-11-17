"""Small models with closed-form equilibria and bifurcations, for the analysis of dynamics.

A flow never moves a negative amount, and a var that flows join never falls below zero. So each model
shifts its state by a centre c, to keep it positive, and writes each signed rate g as two flows: an
inflow `offset + g` and an outflow `offset`, with an offset larger than any |g| near the centre. The net
rate is g, so the equilibria, derivatives and bifurcations are those of g. Each state is in people,
`unit_count` is one person and `unit_rate` one person an hour, so the expressions keep their units.
"""

from __future__ import annotations

from tests.build import flow, formula, named, output, parameter, stock, system

CENTRE = 10.0
OFFSET = 500.0


def units():
    return (
        parameter('c', CENTRE, 'people', 1, 100, doc='Centre'),
        parameter('offset', OFFSET, 'people/h', 100, 5000, doc='Offset of the rates'),
        parameter('unit_count', 1, 'people', 1, 2, doc='One person'),
        parameter('unit_rate', 1, 'people/h', 1, 2, doc='One person an hour'),
    )


def signed(name, target, rate):
    """The two flows of a signed rate `rate` (in people/h) into `target`."""
    return (
        flow(f'{name}_in', f'-> {target}', f'offset + {rate}'),
        flow(f'{name}_out', f'{target} ->', 'offset'),
    )


def fold(mu=1.0, *, horizon=10):
    """X' = mu - ((X - c) / 1 person)^2 people/h: equilibria c +- sqrt(mu) for mu > 0, a fold at mu = 0."""
    return system(
        *units(),
        parameter('mu', mu, 'people/h', -5, 5, doc='Mu'),
        stock('x', CENTRE + 1, 'people', size=10, doc='X'),
        *signed('change', 'x', 'mu - ((x - c) / unit_count) ** 2 * unit_rate'),
        horizon=horizon,
    )


def fold_in_time(mu0=-2.0, slope=0.5, *, horizon=10):
    """The fold with mu = mu0 + slope t / 1 h, a formula of the time: a fold at t = -mu0 / slope."""
    return system(
        *units(),
        parameter('mu0', mu0, 'people/h', -5, 5, doc='Mu at the start'),
        parameter('slope', slope, 'people/h', 0.01, 5, doc='Growth of mu in an hour'),
        parameter('hour', 1, 'h', 1, 2, doc='One hour'),
        formula('mu', 'mu0 + slope * t / hour', 'people/h'),
        stock('x', CENTRE + 1, 'people', size=10, doc='X'),
        *signed('change', 'x', 'mu - ((x - c) / unit_count) ** 2 * unit_rate'),
        horizon=horizon,
    )


def cusp(mu=0.0, lam=3.0, *, start=CENTRE - 2, horizon=60):
    """X' = (mu + lam y - y^3) people/h with y = (X - c) / 1 person: for lam > 0, folds at
    mu = +-2 (lam / 3)^(3/2), and two stable equilibria between them."""
    return system(
        *units(),
        parameter('mu', mu, 'people/h', -10, 10, doc='Mu'),
        parameter('lam', lam, 'fraction', 0, 10, doc='Lambda'),
        parameter('x0', start, 'people', 0, 100, doc='Start value'),
        formula('y', '(x - c) / unit_count', 'fraction'),
        stock('x', 'x0', 'people', size=10, doc='X'),
        *signed('change', 'x', 'mu + (lam * y - y ** 3) * unit_rate'),
        horizon=horizon,
    )


def linear(a, *, horizon=10):
    """X' = A (X - c) per hour for two quantities: the derivative is A, with its eigenvalues."""
    (a11, a12), (a21, a22) = a
    return system(
        *units(),
        parameter('a11', a11, 'fraction', -10, 10, doc='A11'),
        parameter('a12', a12, 'fraction', -10, 10, doc='A12'),
        parameter('a21', a21, 'fraction', -10, 10, doc='A21'),
        parameter('a22', a22, 'fraction', -10, 10, doc='A22'),
        stock('x', CENTRE + 1, 'people', size=10, doc='X'),
        stock('w', CENTRE - 1, 'people', size=10, doc='W'),
        *signed('change_x', 'x', '(a11 * (x - c) + a12 * (w - c)) / unit_count * unit_rate'),
        *signed('change_w', 'w', '(a21 * (x - c) + a22 * (w - c)) / unit_count * unit_rate'),
        horizon=horizon,
    )


def hopf(mu=-0.5, omega=2.0, *, horizon=10):
    """The normal form of a Hopf bifurcation: u' = mu u - omega v - u (u^2 + v^2) and v' = omega u +
    mu v - v (u^2 + v^2), per hour, with u = (X - c) / 1 person and v = (W - c) / 1 person. The centre
    has the eigenvalues mu +- i omega: a Hopf point at mu = 0 with frequency omega."""
    return system(
        *units(),
        parameter('mu', mu, 'fraction', -5, 5, doc='Mu'),
        parameter('omega', omega, 'fraction', 0.1, 10, doc='Omega'),
        formula('u', '(x - c) / unit_count', 'fraction'),
        formula('v', '(w - c) / unit_count', 'fraction'),
        stock('x', CENTRE + 0.5, 'people', size=10, doc='X'),
        stock('w', CENTRE, 'people', size=10, doc='W'),
        *signed('change_x', 'x', '(mu * u - omega * v - u * (u ** 2 + v ** 2)) * unit_rate'),
        *signed('change_w', 'w', '(omega * u + mu * v - v * (u ** 2 + v ** 2)) * unit_rate'),
        horizon=horizon,
    )


def kinked_stall(*, start=CENTRE + 1, horizon=10):
    """X' = max(-1/2 - |y|, -3 - 2 y) people/h with y = (X - c) / 1 person. For y > -5/6 the first term
    is the larger, so X' <= -1/2 there, and the one rest is y = -3/2, on the second term: stable, with
    eigenvalue -2. |X'| has a local minimum of 1/2 at the kink y = 0, where the central difference is 0."""
    return system(
        *units(),
        parameter('x0', start, 'people', 0, 100, doc='Start value'),
        formula('y', '(x - c) / unit_count', 'fraction'),
        stock('x', 'x0', 'people', size=10, doc='X'),
        *signed('change', 'x', 'max(-0.5 - abs(y), -3 - 2 * y) * unit_rate'),
        horizon=horizon,
    )


def cubic(*, start=CENTRE + 1, horizon=10):
    """X' = -(y^3 - 2 y + 2) people/h with y = (X - c) / 1 person: one rest, at the real root of
    y^3 - 2 y + 2 = 0, where the derivative -(3 y^2 - 2) is negative: stable. X' < 0 above the root, and
    |X'| has a local minimum at y = sqrt(2/3), where X' is not zero."""
    return system(
        *units(),
        parameter('x0', start, 'people', 0, 100, doc='Start value'),
        formula('y', '(x - c) / unit_count', 'fraction'),
        stock('x', 'x0', 'people', size=10, doc='X'),
        *signed('change', 'x', '-(y ** 3 - 2 * y + 2) * unit_rate'),
        horizon=horizon,
    )


def ridge(mu=1.0, *, horizon=10):
    """X' = mu - s^2 and W' = 2 (mu - s^2) people/h, with s = ((X + W) / 2 - c) / 1 person. For mu > 0 the
    rests make two lines, s = +-sqrt(mu); none exist for mu < 0. The derivative is -s [[1, 1], [2, 2]] per
    hour: the eigenvalue 0 with the direction (1, -1) along the line, and -3 s on the other direction."""
    return system(
        *units(),
        parameter('mu', mu, 'people/h', -5, 5, doc='Mu'),
        formula('s', '((x + w) / 2 - c) / unit_count', 'fraction'),
        stock('x', CENTRE + 1, 'people', size=10, doc='X'),
        stock('w', CENTRE + 1, 'people', size=10, doc='W'),
        *signed('change_x', 'x', 'mu - s ** 2 * unit_rate'),
        *signed('change_w', 'w', '2 * (mu - s ** 2 * unit_rate)'),
        horizon=horizon,
    )


def fold_and_decay(mu=0.0, *, horizon=10):
    """X' = mu - ((X - c) / 1 person)^2 people/h and W' = -(W - c) per hour. At mu = 0 the rest (c, c) is a
    fold point: the derivative diag(0, -1) has the null direction (1, 0), but X' = -(X - c)^2 vanishes
    nowhere next to it, so no rest lies next to it along that direction."""
    return system(
        *units(),
        parameter('mu', mu, 'people/h', -5, 5, doc='Mu'),
        stock('x', CENTRE, 'people', size=10, doc='X'),
        stock('w', CENTRE, 'people', size=10, doc='W'),
        *signed('change_x', 'x', 'mu - ((x - c) / unit_count) ** 2 * unit_rate'),
        *signed('change_w', 'w', '-(w - c) / unit_count * unit_rate'),
        horizon=horizon,
    )


def semistable(a=0.5, b=2.0, *, decay=None, horizon=10):
    """X' = min(a y, -b y) people/h with y = (X - c) / 1 person, for a, b > 0: the rest y = 0 sits on the
    kink. Above it X' = -b y, so X falls back to it; below it X' = a y, so X runs away from it. The
    central difference gives (a - b) / 2. With `decay`, a second quantity W' = -decay (W - c) per hour."""
    second = ()
    if decay is not None:
        second = (
            parameter('k', decay, 'fraction', 0.01, 10, doc='Decay'),
            stock('w', CENTRE, 'people', size=10, doc='W'),
            *signed('change_w', 'w', '-k * (w - c) / unit_count * unit_rate'),
        )
    return system(
        *units(),
        parameter('a', a, 'fraction', 0.01, 10, doc='Slope below the rest'),
        parameter('b', b, 'fraction', 0.01, 10, doc='Slope above the rest'),
        formula('y', '(x - c) / unit_count', 'fraction'),
        stock('x', CENTRE, 'people', size=10, doc='X'),
        *signed('change', 'x', 'min(a * y, -b * y) * unit_rate'),
        *second,
        horizon=horizon,
    )


def fold_with_empty_stock(mu=1.0, *, horizon=10):
    """The fold X' = mu - ((X - c) / 1 person)^2 + E / 1 h, and a stock E that only drains, at k E. E starts
    empty and stays empty, on its lower bound 0, along every branch: the equilibria are those of the fold."""
    return system(
        *units(),
        parameter('mu', mu, 'people/h', -5, 5, doc='Mu'),
        parameter('k', 0.5, 'per_h', 0.01, 1, doc='Drain rate'),
        parameter('hour', 1, 'h', 1, 2, doc='One hour'),
        stock('x', CENTRE + 1, 'people', size=10, doc='X'),
        stock('e', 0, 'people', size=10, doc='E'),
        *signed('change', 'x', 'mu - ((x - c) / unit_count) ** 2 * unit_rate + e / hour'),
        flow('drain_e', 'e ->', 'k * e'),
        horizon=horizon,
    )


def queue(mu=1.5, *, start=2.2, horizon=10):
    """A queue B with arrivals min(C, mu) and departures min(B / T, C), with C = 1 person/h and T = 2 h.
    For mu < C its one rest is B = mu T, stable with the eigenvalue -1 / T. For mu > C every B >= C T is a
    rest: the departures run at capacity, so B is neutral. Coming down in mu, the branch meets a corner
    at mu = C, where the queue stops filling."""
    return system(
        parameter('mu', mu, 'people/h', 0, 5, doc='Arrivals'),
        parameter('capacity', 1, 'people/h', 0.1, 10, doc='Capacity'),
        parameter('delay', 2, 'h', 0.1, 10, doc='Time in the queue'),
        parameter('b0', start, 'people', 0, 100, doc='Start value'),
        stock('b', 'b0', 'people', size=10, doc='Queue'),
        flow('arrive', '-> b', 'min(capacity, mu)'),
        flow('leave', 'b ->', 'min(b / delay, capacity)'),
        horizon=horizon,
    )


def mixed(*, horizon=10):
    """An active stock that decays to an inflow, a tally that counts what it drains (passive), a
    number state that the inflow reads and a named state that the drain reads (both frozen): the drain
    runs only while the gate is open. Its equilibrium is (supply + boost / 1 h) / k."""
    return system(
        *units(),
        parameter('k', 0.5, 'per_h', 0.01, 1, doc='Drain rate'),
        parameter('supply', 4, 'people/h', 0, 10, doc='Supply'),
        parameter('hour', 1, 'h', 1, 2, doc='One hour'),
        named('gate', 'open', 'shut'),
        stock('boost', 2, 'people', kind='state', size=10, doc='Boost'),
        stock('x', CENTRE, 'people', size=10, doc='X'),
        stock('drained', 0, 'people', kind='tally', size=100, doc='Drained'),
        flow('fill', '-> x', 'supply + boost / hour'),
        flow('drain', 'x -> drained', 'k * x if gate is "open" else 0 people/h'),
        horizon=horizon,
        outputs=(output('drained_out', 's.drained', 'people', doc='Drained'),),
    )
