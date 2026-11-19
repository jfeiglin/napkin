"""Small programs with closed-form equilibria and bifurcations, for the analysis of dynamics.

A flow never asks a negative rate, so each normal form (`tank`) writes a signed rate g into a level as
two flows: an inflow `offset + g` and an outflow `offset`, with an offset larger than any |g| near the
centre c. The net rate is g, so the equilibria, derivatives and bifurcations are those of g. A level
also has a lower bound of zero, so each normal form shifts its state by the centre to keep it inside.
The queue, the mixed tank, the pond, the drain and the schedule ask rates that are never negative.
Each level is in people and each rate in people an hour, so the expressions keep their units: y =
(x - c) / 1 person is a plain number. Each model gives its program and the configuration of a median
run to its horizon.
"""

from __future__ import annotations

from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    call,
    flow,
    fmax,
    fmin,
    formula,
    ifelse,
    input_,
    q,
    t,
    this,
    value,
)
from napkin.program.config import Configuration, Request

UNITS = {'people': {'people': 1}, 'h': {'time': 1}}
CENTRE = 10.0
OFFSET = 500.0
PERSON, PER_HOUR, HOUR = q(1, 'people'), q(1, 'people/h'), q(1, 'h')


def run_of(program, horizon):
    """A program with the configuration of a median run to its horizon (h)."""
    return program, Configuration(Request(horizon))


def tank(*parts, horizon=10):
    """The tank of one model: the centre and the offset of its rates, and its parts."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        input_('c', 'people', CENTRE, lower=1, upper=100),
        input_('offset', 'people/h', OFFSET, lower=100, upper=5000),
        *parts,
    )
    return run_of(b.finish(), horizon)


def level(name, start):
    """A level in people from `start`, with a lower bound of zero and a size of 10 people."""
    return value(name, 'people', start, lower=0, scale=q(10, 'people'))


def plain(name, expression):
    """A formula with no unit."""
    return value(name, '', formula(expression))


def signed(name, target, rate):
    """The two flows of a signed rate `rate` (in people/h) into `target`."""
    return (
        flow(f'{name}_in', SOURCE, target, request=formula(this.offset + rate)),
        flow(f'{name}_out', target, SINK, request=formula(this.offset)),
    )


def offset_of(name):
    """y = (level - c) / 1 person, as a handle."""
    return (getattr(this, name) - this.c) / PERSON


def fold(mu=1.0, *, horizon=10):
    """x' = mu - y^2 people/h: equilibria c +- sqrt(mu) for mu > 0, a fold at mu = 0."""
    return tank(
        input_('mu', 'people/h', mu, lower=-5, upper=5),
        level('x', CENTRE + 1),
        *signed('change', this.x, this.mu - offset_of('x') ** 2 * PER_HOUR),
        horizon=horizon,
    )


def fold_in_time(mu0=-2.0, slope=0.5, *, horizon=10):
    """The fold with mu = mu0 + slope t / 1 h, a formula of the time: a fold at t = -mu0 / slope."""
    return tank(
        input_('mu0', 'people/h', mu0, lower=-5, upper=5),
        input_('slope', 'people/h', slope, lower=0.01, upper=5),
        value('mu', 'people/h', formula(this.mu0 + this.slope * t / HOUR)),
        level('x', CENTRE + 1),
        *signed('change', this.x, this.mu - offset_of('x') ** 2 * PER_HOUR),
        horizon=horizon,
    )


def cusp(mu=0.0, lam=3.0, *, start=CENTRE - 2, horizon=60):
    """x' = (mu + lam y - y^3) people/h: for lam > 0, folds at mu = +-2 (lam / 3)^(3/2), and two
    stable equilibria between them."""
    return tank(
        input_('mu', 'people/h', mu, lower=-10, upper=10),
        input_('lam', '', lam, lower=0, upper=10),
        input_('x0', 'people', start, lower=0, upper=100),
        plain('y', offset_of('x')),
        level('x', this.x0),
        *signed('change', this.x, this.mu + (this.lam * this.y - this.y**3) * PER_HOUR),
        horizon=horizon,
    )


def linear(a, *, horizon=10):
    """x' = A (x - c) per hour for two levels x and w: the derivative is A, with its eigenvalues."""
    (a11, a12), (a21, a22) = a
    return tank(
        input_('a11', '', a11, lower=-10, upper=10),
        input_('a12', '', a12, lower=-10, upper=10),
        input_('a21', '', a21, lower=-10, upper=10),
        input_('a22', '', a22, lower=-10, upper=10),
        level('x', CENTRE + 1),
        level('w', CENTRE - 1),
        *signed('change_x', this.x, (this.a11 * offset_of('x') + this.a12 * offset_of('w')) * PER_HOUR),
        *signed('change_w', this.w, (this.a21 * offset_of('x') + this.a22 * offset_of('w')) * PER_HOUR),
        horizon=horizon,
    )


def hopf(mu=-0.5, omega=2.0, *, horizon=10):
    """The normal form of a Hopf bifurcation: u' = mu u - omega v - u (u^2 + v^2) and v' = omega u +
    mu v - v (u^2 + v^2), per hour, with u = (x - c) / 1 person and v = (w - c) / 1 person. The centre
    has the eigenvalues mu +- i omega: a Hopf point at mu = 0 with the frequency omega."""
    square = this.u**2 + this.v**2
    return tank(
        input_('mu', '', mu, lower=-5, upper=5),
        input_('omega', '', omega, lower=0.1, upper=10),
        plain('u', offset_of('x')),
        plain('v', offset_of('w')),
        level('x', CENTRE + 0.5),
        level('w', CENTRE),
        *signed('change_x', this.x, (this.mu * this.u - this.omega * this.v - this.u * square) * PER_HOUR),
        *signed('change_w', this.w, (this.omega * this.u + this.mu * this.v - this.v * square) * PER_HOUR),
        horizon=horizon,
    )


def kinked_stall(*, start=CENTRE + 1, horizon=10):
    """x' = max(-1/2 - |y|, -3 - 2 y) people/h. For y > -5/6 the first term is the larger, so x' <= -1/2
    there, and the one rest is y = -3/2, on the second term: stable, with the eigenvalue -2. |x'| has
    a local minimum of 1/2 at the kink y = 0, where the central difference is 0."""
    return tank(
        input_('x0', 'people', start, lower=0, upper=100),
        plain('y', offset_of('x')),
        level('x', this.x0),
        *signed('change', this.x, fmax(-0.5 - call('abs', this.y), -3 - 2 * this.y) * PER_HOUR),
        horizon=horizon,
    )


def cubic(*, start=CENTRE + 1, horizon=10):
    """x' = -(y^3 - 2 y + 2) people/h: one rest, at the real root of y^3 - 2 y + 2 = 0, where the
    derivative -(3 y^2 - 2) is negative: stable. x' < 0 above the root, and |x'| has a local minimum at
    y = sqrt(2/3), where x' is not zero."""
    return tank(
        input_('x0', 'people', start, lower=0, upper=100),
        plain('y', offset_of('x')),
        level('x', this.x0),
        *signed('change', this.x, -(this.y**3 - 2 * this.y + 2) * PER_HOUR),
        horizon=horizon,
    )


def ridge(mu=1.0, *, horizon=10):
    """x' = mu - s^2 and w' = 2 (mu - s^2) people/h, with s = ((x + w) / 2 - c) / 1 person. For mu > 0
    the rests make two lines, s = +-sqrt(mu); none exist for mu < 0. The derivative is -s [[1, 1],
    [2, 2]] per hour: the eigenvalue 0 with the direction (1, -1) along the line, and -3 s on the
    other direction."""
    return tank(
        input_('mu', 'people/h', mu, lower=-5, upper=5),
        plain('s', ((this.x + this.w) / 2 - this.c) / PERSON),
        level('x', CENTRE + 1),
        level('w', CENTRE + 1),
        *signed('change_x', this.x, this.mu - this.s**2 * PER_HOUR),
        *signed('change_w', this.w, 2 * (this.mu - this.s**2 * PER_HOUR)),
        horizon=horizon,
    )


def fold_and_decay(mu=0.0, *, horizon=10):
    """x' = mu - y^2 people/h and w' = -(w - c) per hour. At mu = 0 the rest (c, c) is a fold point:
    the derivative diag(0, -1) has the null direction (1, 0), but x' = -(x - c)^2 vanishes nowhere
    next to it, so no rest lies next to it along that direction."""
    return tank(
        input_('mu', 'people/h', mu, lower=-5, upper=5),
        level('x', CENTRE),
        level('w', CENTRE),
        *signed('change_x', this.x, this.mu - offset_of('x') ** 2 * PER_HOUR),
        *signed('change_w', this.w, -offset_of('w') * PER_HOUR),
        horizon=horizon,
    )


def semistable(a=0.5, b=2.0, *, decay=None, horizon=10):
    """x' = min(a y, -b y) people/h, for a, b > 0: the rest y = 0 sits on the kink. Above it x' = -b y,
    so x falls back to it; below it x' = a y, so x runs away from it. The central difference gives
    (a - b) / 2. With `decay`, a second level w' = -decay (w - c) per hour."""
    second = ()
    if decay is not None:
        second = (
            input_('k', '', decay, lower=0.01, upper=10),
            level('w', CENTRE),
            *signed('change_w', this.w, -this.k * offset_of('w') * PER_HOUR),
        )
    return tank(
        input_('a', '', a, lower=0.01, upper=10),
        input_('b', '', b, lower=0.01, upper=10),
        plain('y', offset_of('x')),
        level('x', CENTRE),
        *signed('change', this.x, fmin(this.a * this.y, -this.b * this.y) * PER_HOUR),
        *second,
        horizon=horizon,
    )


def fold_with_empty_stock(mu=1.0, *, horizon=10):
    """The fold x' = mu - y^2 + e / 1 h, and a level e that only drains, at k e. e starts empty and
    stays empty, on its lower bound 0, along every branch: the equilibria are those of the fold."""
    return tank(
        input_('mu', 'people/h', mu, lower=-5, upper=5),
        input_('k', '1/h', 0.5, lower=0.01, upper=1),
        level('x', CENTRE + 1),
        level('e', 0),
        *signed('change', this.x, this.mu - offset_of('x') ** 2 * PER_HOUR + this.e / HOUR),
        flow('drain_e', this.e, SINK, request=formula(this.k * this.e)),
        horizon=horizon,
    )


def queue(arrivals=1.5, *, start=2.2, horizon=10):
    """A queue with arrivals min(C, mu) and departures min(B / T, C), with the capacity C = 1 person/h
    and the time in the queue T = 2 h. For mu < C its one rest is B = mu T, stable with the
    eigenvalue -1 / T. For mu > C every B >= C T is a rest: the departures run at capacity, so B is
    neutral. Coming down in mu, the branch meets a corner at mu = C, where the queue stops filling."""
    b = Builder(UNITS)
    b.entity(
        'queue',
        input_('arrivals', 'people/h', arrivals, lower=0, upper=5),
        input_('capacity', 'people/h', 1, lower=0.1, upper=10),
        input_('delay', 'h', 2, lower=0.1, upper=10),
        input_('start', 'people', start, lower=0, upper=100),
        level('waiting', this.start),
        flow('arrive', SOURCE, this.waiting, request=formula(fmin(this.capacity, this.arrivals))),
        flow('leave', this.waiting, SINK, request=formula(fmin(this.waiting / this.delay, this.capacity))),
    )
    return run_of(b.finish(), horizon)


def mixed(*, horizon=10):
    """A level x that drains into a tally that counts what it drains (passive), and two stored
    values that no flow meets (held at their start): a number that the inflow reads and a gate that
    the drain reads, which runs only while the gate is open. The rest is (supply + boost / 1 h) / k."""
    b = Builder(UNITS)
    gate = b.enum('Gate', 'OPEN', 'SHUT')
    b.entity(
        'tank',
        input_('k', '1/h', 0.5, lower=0.01, upper=1),
        input_('supply', 'people/h', 4, lower=0, upper=10),
        value('gate', gate, gate.OPEN),
        value('boost', 'people', 2, scale=q(10, 'people')),
        level('x', CENTRE),
        value('drained', 'people', 0, lower=0, scale=q(100, 'people')),
        flow('fill', SOURCE, this.x, request=formula(this.supply + this.boost / HOUR)),
        flow(
            'drain',
            this.x,
            this.drained,
            request=formula(ifelse(this.gate == gate.OPEN, this.k * this.x, q(0, 'people/h'))),
        ),
    )
    return run_of(b.finish(), horizon)


def pond(*, horizon=10):
    """A pond that rain (r) and a spring (k (top - x)) fill and a drain (d x) empties, below its upper
    bound `top`. Two flows meet the pond on one side, so the engine runs it on the sparse integrator.
    Its rest is x = (r + k top) / (k + d), stable with the eigenvalue -(k + d)."""
    b = Builder(UNITS)
    b.entity(
        'pond',
        input_('rain', 'people/h', 2, lower=0, upper=10),
        input_('k', '1/h', 0.5, lower=0, upper=5),
        input_('top', 'people', 20, lower=1, upper=100),
        input_('d', '1/h', 0.25, lower=0, upper=5),
        value('x', 'people', 4, lower=0, upper=this.top, scale=q(10, 'people')),
        flow('rainfall', SOURCE, this.x, request=formula(this.rain)),
        flow('spring', SOURCE, this.x, request=formula(this.k * (this.top - this.x))),
        flow('drain', this.x, SINK, request=formula(this.d * this.x)),
    )
    return run_of(b.finish(), horizon)


def drain(k=0.1, *, start=10.0, horizon=10):
    """A tank that drains at k x from x0: x(T) = x0 exp(-k T). The engine solves its segment in
    closed form, so a run costs a few milliseconds."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        input_('k', '1/h', k, lower=0, upper=1),
        level('x', start),
        flow('drain', this.x, SINK, request=formula(this.k * this.x)),
    )
    return run_of(b.finish(), horizon)


def scheduled(*, horizon=10):
    """A tank filled by a schedule, readings of 2 people/h from 0 h and 6 people/h from 4 h, that
    drains at k x with k = 1/2 per hour: x' = schedule(t) - k x. Its rest is 4 people before 4 h and
    12 people after."""
    b = Builder(UNITS)
    reading = b.template('Reading', input_('hour', 'h', 0), input_('rate', 'people/h', 0))
    for name, hour, rate in (('early', 0, 2), ('late', 4, 6)):
        b.member(reading, name, hour=q(hour, 'h'), rate=q(rate, 'people/h'))
    b.entity(
        'tank',
        input_('k', '1/h', 0.5, lower=0, upper=1),
        level('x', 4),
        flow('fill', SOURCE, this.x, request=formula(reading.instances.by('hour').at(t).rate)),
        flow('drain', this.x, SINK, request=formula(this.k * this.x)),
    )
    return run_of(b.finish(), horizon)
