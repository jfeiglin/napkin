"""The power outage of the scenario: independent reference mathematics, written from the specification of its equations.

Every time is in hours from the start of the outage (t = 0). `service(t)` is the share of people whose
power is back. Inputs arrive in a plain dict under this module's own short names, in execution units
(hours, degrees Celsius, people, per-hour rates). Costs are in USD billions. The module imports no engine
code and accepts no engine trajectory or expression.

The mathematics, in the order of the specification:

* `Ledger`: the restoration work as an exact piecewise linear timeline (events, no ODE solver).
* `interruption_costs`: closed forms for the power-law cost of an outage.
* `Heat`: the equivalent temperatures, relative risks and hazard multipliers.
* `Blackout`: the people at risk, by group, as pools whose survivors follow from the cumulative hazards.
  The cumulative hazards are quadratures of closed-form integrands (`Cumulative`: Chebyshev
  antiderivatives on pieces where the integrand is analytic, cut at every known kink). Each person counts
  at most `visit_limit` heat emergency visits: with V the expected visits of a person at home so far, the
  visits that count are L * (1 - exp(-V / L)), and the heatstroke hazard is a share of them.
* `closed_form_heat`: the exponential-integral solution for the cases in which the temperature curves are
  in one linear regime and one death term always dominates. It shares no code with `Blackout`.
* `device_admissions_without_heat` and `exposure_without_heat`: the closed forms of the admissions and of
  the person-hours at risk when no heat hazard acts. They share no code with `Blackout` either.
"""

import math
from bisect import bisect_right
from itertools import pairwise

from scipy.integrate import quad
from scipy.optimize import brentq
from scipy.special import expi

# The constants that the specification fixes.
SHORTEST_OUTAGE_H = 2.0
REFERENCE_OUTAGE_H = 24.0
SOURCE_WINDOW_H = 120.0
SOURCE_BLACKOUT_H = 48.0
STUDIES = ('gasparrini', 'bobb', 'nordio', 'schwartz')
BUILDINGS = ('homes', 'compound')
# The age bands, as the suffixes of this module's names, and as the report's entity names.
BANDS = ('under_65', '65_74', '75')
ENTITY_BAND = {'under_65': 'under_65', '65_74': '65_to_74', '75': '75_and_over'}


class Profile:
    """Service as a continuous, piecewise linear function of time.

    `knots` are (time, service) pairs in increasing time that start at time 0. Service stays at the
    last value after the last knot.
    """

    def __init__(self, knots):
        self.knots = [(float(t), float(s)) for t, s in knots]
        assert self.knots[0][0] == 0.0
        assert all(a[0] <= b[0] for a, b in pairwise(self.knots))

    def pieces(self, lo=0.0, hi=math.inf):
        """The linear pieces inside [lo, hi] as (a, b, service at a, service at b).

        The piece after the last knot is flat and runs to infinity.
        """
        spans = list(pairwise(self.knots))
        spans.append((self.knots[-1], (math.inf, self.knots[-1][1])))
        for (t0, s0), (t1, s1) in spans:
            a, b = max(t0, lo), min(t1, hi)
            if b <= a:
                continue
            slope = 0.0 if math.isinf(t1) else (s1 - s0) / (t1 - t0)
            yield a, b, s0 + slope * (a - t0), (s0 + slope * (b - t0) if math.isfinite(b) else s0)

    def service(self, t):
        for a, b, service_a, service_b in self.pieces(0.0, math.inf):
            if a <= t <= b:
                return (
                    service_a + (service_b - service_a) * (t - a) / (b - a) if math.isfinite(b) else service_a
                )
        raise ValueError(f'time {t!r} is outside the profile')

    def deficit(self, a, b):
        """The integral of (1 - service) from a to b: exact on each linear piece."""
        return sum((1.0 - (sa + sb) / 2.0) * (pb - pa) for pa, pb, sa, sb in self.pieces(a, b))

    @property
    def full_time(self):
        """The first time at which everyone has power."""
        return next((t for t, s in self.knots if s >= 1.0), math.inf)


class Ledger:
    """The restoration work ledger (section 1), solved exactly as events on a piecewise linear timeline.

    State: initial work done `c`, the rework left from the attacker's change `a1`, the job rework left
    `a2`, and the amounts of each done. After the switching starts the crews do one hour of work per hour,
    unless they are stopped: first the job rework, then the change rework, then the initial work.
    At equal times a completion goes first, so a job or a change that falls when power is back never acts.
    """

    def __init__(self, p):
        self.p = p
        work, rho = p['work_h'], p['rework_share']
        self.work = work
        self.start = max(p['contain_h'], p['determination_h'] + p['check_h'])
        order = p['review_h'] + p['order_delay_h'] + p['order_transit_h']
        self.stop = order if p['obeys'] else max(p['removal_h'], order)
        self.change_at = self.start + p['react_h']
        self.job_at = p['job_h']
        # What happened, for the tests to check that a case is the case it claims to be.
        self.changed = False
        self.job_phase = 'not listed'
        state = [0.0] * 5  # c, a1, a2, a1 done, a2 done
        pending = []
        idle = (0.0,) * 5
        segments = [(0.0, self.start, tuple(state), idle)]
        if self.job_at < self.stop + p['cleanup_h']:
            self.job_phase = 'power back'
            if self.job_at <= self.start:
                # Nothing is done yet, so the job adds the whole rework when it runs.
                state[2] = rho * work
                segments = [
                    (0.0, self.job_at, (0.0,) * 5, idle),
                    (self.job_at, self.start, tuple(state), idle),
                ]
                self.job_phase = 'before switching'
            else:
                pending.append((self.job_at, 'job'))
        if self.stop > self.change_at:
            pending.append((self.change_at, 'change'))
        pending.sort()
        now, stopped = self.start, False
        while True:
            c, a1, a2, _d1, _d2 = state
            if stopped:
                rates, to_clear = (0.0,) * 5, math.inf
            elif a2 > 0:
                rates, to_clear = (0.0, 0.0, -1.0, 0.0, 1.0), a2
            elif a1 > 0:
                rates, to_clear = (0.0, -1.0, 0.0, 1.0, 0.0), a1
            else:
                rates, to_clear = (1.0, 0.0, 0.0, 0.0, 0.0), work - c
            gap = pending[0][0] - now if pending else math.inf
            if to_clear <= gap:
                end = now + to_clear
                segments.append((now, end, tuple(state), rates))
                state = [s + r * to_clear for s, r in zip(state, rates)]
                if rates[0]:
                    state[0] = work
                    break
                state[2 if rates[2] else 1] = 0.0
                now = end
                continue
            when, kind = pending.pop(0)
            segments.append((now, when, tuple(state), rates))
            state = [s + r * gap for s, r in zip(state, rates)]
            now = when
            if kind == 'job':
                state[2] += rho * (work - state[0])
                self.job_phase = 'while stopped' if stopped else 'while working'
            elif kind == 'change':
                state[1] += rho * (work - state[0])
                stopped, self.changed = True, True
                pending.append((self.stop, 'resume'))
                pending.sort()
            else:
                stopped = False
        self.full = end
        segments.append((end, math.inf, tuple(state), (0.0,) * 5))
        self.segments = segments
        self._starts = [segment[0] for segment in segments]
        self.profile = Profile([(t0, s[0] / work) for t0, _t1, s, _r in segments])

    def state(self, t):
        """(c, a1, a2, a1 done, a2 done) at time t; at a jump, the value after it."""
        k = bisect_right(self._starts, t) - 1
        t0, _t1, state, rates = self.segments[k]
        return [s + r * (t - t0) for s, r in zip(state, rates)]

    def service(self, t):
        return self.state(t)[0] / self.work

    def report(self, t):
        """The ledger's outputs under the report's own keys."""
        p = self.p
        c, a1, a2, d1, d2 = self.state(t)
        price = p['lineworkers'] * p['wage'] * p['cost_multiplier'] / 1e9
        return {
            'supply.resident_hours': p['people'] * self.profile.deficit(0.0, t),
            'outstanding_work': self.work - c + a1 + a2,
            'crews.work_left': self.work - c,
            'job.remaining': a2,
            'crews.restoration_cost': (c + d1 + d2) * price,
        }

    def marks(self):
        """The times at which the timeline changes: the start, every event and the end."""
        return sorted({t for t, _s in self.profile.knots} | {self.job_at, self.change_at, self.stop})


def customer_cost(c24, power, hours):
    """The cost in USD to one customer of an outage of `hours` hours."""
    return c24 * (max(hours, SHORTEST_OUTAGE_H) / REFERENCE_OUTAGE_H) ** power


def customer_cost_total(c24, power, hours):
    """The integral of `customer_cost` over outages of 0 to `hours` hours, in closed form.

    The cost is flat up to the shortest outage and a power law above it.
    """
    assert power != -1.0
    flat = customer_cost(c24, power, SHORTEST_OUTAGE_H)
    if hours <= SHORTEST_OUTAGE_H:
        return flat * hours
    rise = (
        c24
        * (hours ** (power + 1) - SHORTEST_OUTAGE_H ** (power + 1))
        / ((power + 1) * REFERENCE_OUTAGE_H**power)
    )
    return flat * SHORTEST_OUTAGE_H + rise


def interruption_costs(p, profile, t):
    """Interruption cost at time t by customer class and in total, under the report's own keys.

    A customer whose circuit came back at time u pays the cost of an outage of u hours. A customer
    still without power pays the cost of the outage so far. So the cost of a class is its customers
    times the cost integrated over the returns of power plus the cost so far for those still dark.
    """
    costs = {}
    for key, suffix in (('residential.cost', 'res'), ('non_residential.cost', 'non')):
        count, c24, power = p['customers_' + suffix], p['cost24_' + suffix], p['power_' + suffix]
        returned = sum(
            (sb - sa) * (customer_cost_total(c24, power, b) - customer_cost_total(c24, power, a)) / (b - a)
            for a, b, sa, sb in profile.pieces(0.0, t)
        )
        costs[key] = count * (returned + (1.0 - profile.service(t)) * customer_cost(c24, power, t)) / 1e9
    costs['interruption_cost'] = costs['residential.cost'] + costs['non_residential.cost']
    return costs


class Heat:
    """Equivalent temperatures, relative risks and hazard multipliers (section 3), per building."""

    def __init__(self, p):
        self.p = p
        self.outdoor, self.cap, self.length = p['outdoor_c'], p['cap_c'], p['heat_h']
        self.rr0 = self.rr(self.outdoor)
        self.rr_ed0 = self.rr_ed(self.outdoor)
        self.rr_hd0 = self.rr_hd(self.outdoor)
        self.delta = {b: self._delta(b) for b in BUILDINGS}

    def _curve(self, study, temperature):
        p = self.p
        low, top = p['curve_threshold_' + study], p['curve_top_' + study]
        return p['curve_slope_' + study] * min(max(temperature - low, 0.0), top - low) + p[
            'curve_ext_' + study
        ] * max(0.0, temperature - top)

    def rr(self, temperature):
        """The relative risk of death from all causes."""
        return math.exp(sum(self.p['curve_weight_' + s] * self._curve(s, temperature) for s in STUDIES))

    def rr_ed(self, temperature):
        """The relative risk of a heat emergency visit."""
        return math.exp(self.p['ed_slope'] * max(0.0, temperature - self.p['ed_threshold']))

    def rr_hd(self, temperature):
        """The relative risk of a heat-related death."""
        return math.exp(self.p['hdeath_slope'] * max(0.0, temperature - self.p['hdeath_threshold']))

    def _delta(self, b):
        """The rise in felt temperature after a long blackout, scaled so that the felt temperature
        averaged over the source blackout and return equals `iet_off`."""
        p = self.p
        tau = p['warm_' + b + '_h']
        ramp = SOURCE_WINDOW_H - SOURCE_BLACKOUT_H
        weight = (
            SOURCE_BLACKOUT_H
            + ramp / 2.0
            - tau**2 / ramp * -math.expm1(-ramp / tau)
            + tau * math.exp(-SOURCE_WINDOW_H / tau)
        )
        return (p['iet_off_' + b] - p['iet_on_' + b]) * SOURCE_WINDOW_H / weight

    def temperature(self, b, t):
        """The equivalent outdoor temperature in building b: outdoor plus the rise over the slope. No cap."""
        rise = self.delta[b] * -math.expm1(-t / self.p['warm_' + b + '_h'])
        return self.outdoor + rise / self.p['slope_' + b]

    def x(self, b, t):
        return self.rr(self.temperature(b, t)) - self.rr0

    def y(self, b, t):
        return self.rr_ed(self.temperature(b, t)) - self.rr_ed0

    def z(self, b, t):
        """The excess of the heat-related death risk. Only this curve is capped."""
        return self.rr_hd(min(self.cap, self.temperature(b, t))) - self.rr_hd0

    def death_multiplier(self, b, band, t):
        return max(self.p['rate_' + band] * self.x(b, t), self.p['hdeath_rate'] * self.z(b, t))

    def visit_multiplier(self, b, t):
        """The expected heat emergency visits of a person at home without power, per hour."""
        return self.p['ed_rate'] * self.y(b, t)

    def heatstroke_per_visit(self):
        """Heatstroke survivors for each heat emergency visit that counts."""
        p = self.p
        return p['heatstroke_share'] * p['people_per_visit'] * (1.0 - p['heatstroke_fatality'])

    def reach_time(self, b, target):
        """The time at which the uncapped temperature of building b reaches `target`; None if never or at once."""
        full_rise = self.delta[b] / self.p['slope_' + b]
        if full_rise <= 0.0:
            return None
        share = (target - self.outdoor) / full_rise
        if not 0.0 < share < 1.0:
            return None
        return -self.p['warm_' + b + '_h'] * math.log1p(-share)

    def kinks(self, b):
        """The times at which a relative risk bends: the temperature crosses a threshold, top or the cap."""
        p = self.p
        targets = [self.cap, p['ed_threshold'], p['hdeath_threshold']]
        for study in STUDIES:
            targets += [p['curve_threshold_' + study], p['curve_top_' + study]]
        return {t for t in (self.reach_time(b, target) for target in targets) if t is not None}

    def crossings(self, b, band, until):
        """The times in (0, until) at which the all-cause and heat-related death terms are equal."""
        p = self.p

        def gap(t):
            return p['rate_' + band] * self.x(b, t) - p['hdeath_rate'] * self.z(b, t)

        if self.delta[b] <= 0.0:
            return set()
        grid = sorted({k * 0.05 for k in range(481)} | {24.0 + k * 0.5 for k in range(int(until * 2) + 1)})
        grid = [t for t in grid if t <= until]
        found = set()
        previous = None
        for t in grid:
            value = gap(t)
            if previous is not None and previous[1] != 0.0 and previous[1] * value < 0.0:
                found.add(brentq(gap, previous[0], t, xtol=1e-13, rtol=1e-14))
            previous = (t, value)
        return found

    def regime(self, b, band, until):
        """'all-cause' or 'heat-death' if one death term is the larger throughout (0, until); else 'mixed'."""
        p = self.p
        grid = [k * 0.05 for k in range(1, 481)] + [24.0 + k * 0.5 for k in range(1, int(until * 2) + 1)]
        signs = {
            (p['rate_' + band] * self.x(b, t) > p['hdeath_rate'] * self.z(b, t))
            for t in grid
            if t <= until and self.x(b, t) + self.z(b, t) > 0.0
        }
        if len(signs) > 1:
            return 'mixed'
        return 'heat-death' if signs == {False} else 'all-cause'


# --- Chebyshev antiderivatives -----------------------------------------------------------------------------

_NODES = 24
_THETA = [math.pi * (k + 0.5) / _NODES for k in range(_NODES)]
_COS_NODES = [math.cos(theta) for theta in _THETA]
_COS_TABLE = [[math.cos(j * theta) for theta in _THETA] for j in range(_NODES)]
_LONGEST_PIECE_H = 12.0


class _Piece:
    """The integral of an analytic function over [a, b] as a Chebyshev series, exact to rounding."""

    def __init__(self, f, a, b):
        self.a, self.b = a, b
        self.half, self.mid = (b - a) / 2.0, (a + b) / 2.0
        values = [f(self.mid + self.half * x) for x in _COS_NODES]
        c = [(2.0 / _NODES) * sum(v * row[k] for k, v in enumerate(values)) for row in _COS_TABLE]
        c[0] *= 0.5
        # Coefficients of the antiderivative in x: int T0 = T1, int T1 = (T0 + T2) / 4 and
        # int Tj = (T(j+1) / (j + 1) - T(j-1) / (j - 1)) / 2 for j >= 2; the constant makes it 0 at x = -1.
        c += [0.0, 0.0]
        d = [0.0] * (_NODES + 1)
        d[1] = c[0] - c[2] / 2.0
        for j in range(2, _NODES + 1):
            d[j] = (c[j - 1] - c[j + 1]) / (2.0 * j)
        d[0] = -sum(dj * (-1.0) ** j for j, dj in enumerate(d) if j)
        self.d = d
        self.total = self.half * sum(d)

    def to(self, t):
        """The integral from a to t."""
        x = (t - self.mid) / self.half
        b1 = b2 = 0.0
        for dj in reversed(self.d[1:]):
            b1, b2 = dj + 2.0 * x * b1 - b2, b1
        return self.half * (self.d[0] + x * b1 - b2)


class Cumulative:
    """The integral from 0 to t of a function that is analytic between the given break times."""

    def __init__(self, f, breaks):
        edges = []
        for a, b in pairwise(breaks):
            if b - a <= 1e-12:
                continue
            parts = max(1, math.ceil((b - a) / _LONGEST_PIECE_H))
            edges += [(a + (b - a) * k / parts, a + (b - a) * (k + 1) / parts) for k in range(parts)]
        self.pieces = [_Piece(f, a, b) for a, b in edges]
        self._starts = [piece.a for piece in self.pieces]
        self._bases = [0.0]
        for piece in self.pieces:
            self._bases.append(self._bases[-1] + piece.total)
        self.end = edges[-1][1]

    def __call__(self, t):
        if not -1e-12 <= t <= self.end + 1e-9:
            raise ValueError(f'time {t!r} is outside [0, {self.end}]')
        t = min(max(t, 0.0), self.end)
        k = min(bisect_right(self._starts, t) - 1, len(self.pieces) - 1)
        return self._bases[k] + self.pieces[k].to(t)


# --- The people at risk --------------------------------------------------------------------------------------


class _PlainPool:
    """People who stay at home under the heat hazards only: survivors follow from the cumulative hazards."""

    def __init__(self, world, building, band, size):
        self.size = size
        self.world, self.building, self.band = world, building, band
        self.hd = world.death_cum(building, band)
        self.hi = world.illness_cum(building)

    def dead(self, t):
        return -self.size * math.expm1(-self.hd(t))

    def ill(self, t):
        return self.size * math.exp(-self.hd(t)) * -math.expm1(-self.hi(t))

    def exposure(self, t):
        return self.size * self.world.exposure_cum(self.building, self.band)(t)

    def admitted(self, t):
        return 0.0

    def accounted(self, t):
        return self.size * math.exp(-self.hd(t)) + self.dead(t)


class _PrivatePool:
    """The private pool of the residents: it leaves at a constant rate while power is off and the heat goes on.

    Exits do not change the share of the people at home who are ill, since they take ill and not-ill
    people in proportion to their numbers. So the people at home N obey N' = -hd N - rate, which has the
    solution N = exp(-Hd) (size - rate * integral of exp(Hd) from the start of the exits). The exits stop
    at the end of the window, when power is back or the heat ends, or when the pool is empty.
    """

    def __init__(self, world, band, size):
        p = world.p
        self.world, self.size = world, size
        self.hd = world.death_cum('homes', band)
        self.hi = world.illness_cum('homes')
        self.start = p['moves_start_h']
        self.rate = size / (p['moves_end_h'] - self.start)
        window_end = min(p['moves_end_h'], world.ledger.full, p['heat_h'], world.until)
        self.emptied = False
        self._at_exits_end = None
        self.growth = Cumulative(
            lambda u: math.exp(self.hd(u)) if u >= self.start else 0.0,
            world.breaks_with(self.start, window_end),
        )
        if window_end > self.start:
            if size - self.rate * self.growth(window_end) <= 0.0:
                window_end = brentq(
                    lambda u: size - self.rate * self.growth(u),
                    self.start,
                    window_end,
                    xtol=1e-14,
                    rtol=1e-14,
                )
                self.emptied = True
        else:
            window_end = self.start
        self.exits_end = window_end
        extra = (self.start, self.exits_end)
        self._at_exits_end = None if self.emptied else self.alive(self.exits_end)
        breaks = world.breaks_with(*extra)
        self._dead = Cumulative(lambda u: world.death_rate('homes', band, u) * self.alive(u), breaks)
        self._exposure = Cumulative(lambda u: world.weight(u) * self.alive(u), breaks)
        self._ill_out = Cumulative(
            lambda u: self.rate * -math.expm1(-self.hi(u)) if self.start <= u < self.exits_end else 0.0,
            breaks,
        )

    def alive(self, t):
        if t <= self.start or self.exits_end <= self.start:
            return self.size * math.exp(-self.hd(t))
        if t <= self.exits_end:
            return math.exp(-self.hd(t)) * (self.size - self.rate * self.growth(t))
        if self.emptied:
            return 0.0
        if self._at_exits_end is None:
            self._at_exits_end = self.alive(self.exits_end)
        return self._at_exits_end * math.exp(-(self.hd(t) - self.hd(self.exits_end)))

    def exited(self, t):
        return self.rate * max(0.0, min(t, self.exits_end) - self.start)

    def dead(self, t):
        return self._dead(t)

    def ill(self, t):
        """Seriously ill and alive, at home or safe elsewhere."""
        return self.alive(t) * -math.expm1(-self.hi(t)) + self._ill_out(t)

    def exposure(self, t):
        return self._exposure(t)

    def admitted(self, t):
        return 0.0

    def accounted(self, t):
        return self.alive(t) + self.dead(t) + self.exited(t)


class _DarkPool:
    """The device users without their own power. Besides the heat hazards they face the admission hazard
    once the battery is spent, and the outreach move at one moment.

    Admissions and the heat death hazard act on ill and not-ill people alike, so the people at home are
    size * g(t) with g = exp(-Hd - Ha), and only the ill share moves between the two kinds. The outreach
    move takes the share `reach` of the not-ill people at home, if power is not fully back.
    """

    def __init__(self, world, band, size):
        p = world.p
        self.world, self.size = world, size
        self.hd = world.death_cum('homes', band)
        self.hi = world.illness_cum('homes')
        self.ha = world.admission_cum()
        self.at = p['outreach_h']
        self.moves = self.at < world.ledger.full and self.at <= world.until
        self.reach = p['reach']
        self.hi_at_move = self.hi(self.at) if self.moves else 0.0
        self.moved = self.reach * math.exp(-self.hi_at_move) if self.moves else 0.0
        breaks = world.breaks_with(self.at)
        self._dead = Cumulative(lambda u: world.death_rate('homes', band, u) * self.alive(u), breaks)
        self._admitted = Cumulative(lambda u: world.admission_rate(u) * self.alive(u), breaks)
        self._admitted_ill = Cumulative(lambda u: world.admission_rate(u) * self.ill_home(u), breaks)
        self._exposure = Cumulative(lambda u: world.weight(u) * self.alive(u), breaks)

    def _after_move(self, t):
        return self.moves and t >= self.at

    def alive(self, t):
        scale = self.size * math.exp(-self.hd(t) - self.ha(t))
        return scale * (1.0 - self.moved) if self._after_move(t) else scale

    def ill_home(self, t):
        scale = self.size * math.exp(-self.hd(t) - self.ha(t))
        ill_share = -math.expm1(-self.hi(t))
        if not self._after_move(t):
            return scale * ill_share
        later = math.exp(-self.hi_at_move) * -math.expm1(-(self.hi(t) - self.hi_at_move))
        return scale * (ill_share - self.reach * later)

    def dead(self, t):
        return self._dead(t)

    def admitted(self, t):
        return self._admitted(t)

    def ill(self, t):
        """Seriously ill and alive, at home or admitted."""
        return self.ill_home(t) + self._admitted_ill(t)

    def exposure(self, t):
        return self._exposure(t)

    def moved_away(self, t):
        return (
            self.size * math.exp(-self.hd(self.at) - self.ha(self.at)) * self.moved
            if self._after_move(t)
            else 0.0
        )

    def accounted(self, t):
        return self.alive(t) + self.dead(t) + self.admitted(t) + self.moved_away(t)


class Blackout:
    """The outcomes of one run (sections 3 to 5) from its inputs, for times up to `until`."""

    def __init__(self, p, until):
        assert p['powered_share'] == 0.0, 'cooled places are outside the oracle'
        self.p, self.until = p, float(until)
        self.ledger = Ledger(p)
        self.heat = Heat(p)
        self.length = p['heat_h']
        self._memo = {}
        marks = {
            0.0,
            self.until,
            p['heat_h'],
            p['battery_h'],
            p['outreach_h'],
            p['moves_start_h'],
            p['moves_end_h'],
        }
        marks |= set(self.ledger.marks())
        for b in BUILDINGS:
            marks |= self.heat.kinks(b)
            for band in BANDS:
                marks |= self.heat.crossings(b, band, min(p['heat_h'], self.until))
        self.base_breaks = sorted(t for t in marks if 0.0 <= t <= self.until)
        self.pools = self._pools()

    # -- the rates and the cumulative hazards
    def weight(self, t):
        """heat_on(t) * (1 - service(t))."""
        return 1.0 - self.ledger.service(t) if t < self.length else 0.0

    def death_rate(self, b, band, t):
        return self.heat.death_multiplier(b, band, t) * self.weight(t)

    def visit_rate(self, b, t):
        return self.heat.visit_multiplier(b, t) * self.weight(t)

    def illness_rate(self, b, t):
        """The heatstroke hazard: the derivative of `illness_cum`."""
        limit = self.p['visit_limit']
        return (
            self.heat.heatstroke_per_visit()
            * self.visit_rate(b, t)
            * math.exp(-self.visits_cum(b)(t) / limit)
        )

    def admission_rate(self, t):
        p = self.p
        if t < p['battery_h']:
            return 0.0
        rate = p['vent_admission'] * (p['vent_share'] + (1.0 - p['vent_share']) * p['conc_factor'])
        return rate * (1.0 - self.ledger.service(t))

    def breaks_with(self, *extra):
        return sorted({*self.base_breaks, *(t for t in extra if 0.0 <= t <= self.until)})

    def _once(self, key, build):
        if key not in self._memo:
            self._memo[key] = build()
        return self._memo[key]

    def death_cum(self, b, band):
        return self._once(
            ('hd', b, band), lambda: Cumulative(lambda t: self.death_rate(b, band, t), self.base_breaks)
        )

    def visits_cum(self, b):
        return self._once(
            ('visits', b), lambda: Cumulative(lambda t: self.visit_rate(b, t), self.base_breaks)
        )

    def illness_cum(self, b):
        """The cumulative heatstroke hazard, from the visits that count (see the module text)."""
        visits, limit = self.visits_cum(b), self.p['visit_limit']
        per_visit = self.heat.heatstroke_per_visit()
        return self._once(('hi', b), lambda: lambda t: per_visit * limit * -math.expm1(-visits(t) / limit))

    def admission_cum(self):
        return self._once(('ha',), lambda: Cumulative(self.admission_rate, self.base_breaks))

    def exposure_cum(self, b, band):
        hd = self.death_cum(b, band)
        return self._once(
            ('exposure', b, band),
            lambda: Cumulative(lambda t: self.weight(t) * math.exp(-hd(t)), self.base_breaks),
        )

    # -- the groups
    def _pools(self):
        p = self.p
        residents = p['people'] - p['held']
        pools = {}
        for band in BANDS:
            share, device = p['share_' + band], p['devshare_' + band]
            entity = ENTITY_BAND[band]
            home = residents * share * (1.0 - device)
            backup, private = p['backup_res_' + band], p['private_res_' + band]
            at_risk = (1.0 - backup) * home
            resident_pools = []
            if (1.0 - private) * at_risk > 0.0:
                resident_pools.append(_PlainPool(self, 'homes', band, (1.0 - private) * at_risk))
            if private * at_risk > 0.0:
                resident_pools.append(_PrivatePool(self, band, private * at_risk))
            pools['residents_' + entity] = resident_pools
            users = residents * share * device
            device_pools = []
            if p['alt_share'] * users > 0.0:
                device_pools.append(_PlainPool(self, 'homes', band, p['alt_share'] * users))
            if (1.0 - p['alt_share']) * users > 0.0:
                device_pools.append(_DarkPool(self, band, (1.0 - p['alt_share']) * users))
            pools['device_users_' + entity] = device_pools
            confined = (1.0 - p['backup_conf_' + band]) * p['held'] * share
            pools['confined_' + entity] = (
                [_PlainPool(self, 'compound', band, confined)] if confined > 0.0 else []
            )
        return pools

    def outputs(self, t):
        """deaths, <entity>.deaths, heatstroke_survivors, casualties, late_deaths, device_admissions, thermal_exposure."""
        p = self.p
        out = {}
        deaths = survivors = admissions = exposure = 0.0
        for entity, pools in self.pools.items():
            dead = sum(pool.dead(t) for pool in pools)
            out[entity + '.deaths'] = dead
            deaths += dead
            survivors += sum(pool.ill(t) for pool in pools)
            admissions += sum(pool.admitted(t) for pool in pools)
            exposure += sum(pool.exposure(t) for pool in pools)
        out.update(
            {
                'deaths': deaths,
                'heatstroke_survivors': survivors,
                'casualties': deaths + survivors,
                'late_deaths': survivors * p['severe_share'] * p['late_fatality'],
                'device_admissions': admissions,
                'thermal_exposure': exposure,
            }
        )
        return out

    def conservation(self, t):
        """For every pool, the people accounted for (at home, dead, gone) less the pool's size."""
        return {
            (entity, k): pool.accounted(t) - pool.size
            for entity, pools in self.pools.items()
            for k, pool in enumerate(pools)
        }


# --- Closed forms --------------------------------------------------------------------------------------------


def _ramp_integral(kappa, tau, t):
    """The integral over (0, t) of exp(kappa * (1 - exp(-u / tau))) - 1, in closed form.

    With x = -kappa * exp(-u / tau), dx/du = -x / tau and d Ei(x) / du = -exp(x) / tau, so the integral of
    exp(kappa) * exp(x) over u is exp(kappa) * tau * (Ei(x(0)) - Ei(x(t))).
    """
    if kappa == 0.0:
        return 0.0
    return math.exp(kappa) * tau * (expi(-kappa) - expi(-kappa * math.exp(-t / tau))) - t


def closed_form_heat(p, t):
    """Deaths and illness with no power during the heat wave, in closed form, for the linear regime.

    The cases covered are those in which: the outdoor temperature is at or above every curve's top, the
    emergency-visit threshold and the heat-death threshold, so that every relative risk is exponential in
    the temperature; no power returns before the heat wave ends; nobody has a backup, a private move or a
    device; and in each band one death term is the larger throughout. The solution then uses the
    exponential integral. The cap enters only the heat-death term, through the time at which the
    temperature reaches it. Heatstroke comes from the visits that count under the limit of `visit_limit`
    visits for each person. It shares no code with `Blackout`.
    """
    heat = Heat(p)
    length = p['heat_h']
    assert Ledger(p).start >= length, 'power must stay off during the heat wave'
    t0 = p['outdoor_c']
    assert all(t0 >= p['curve_top_' + s] for s in STUDIES if p['curve_weight_' + s] > 0.0)
    assert t0 >= p['ed_threshold'] and t0 >= p['hdeath_threshold']
    assert p['powered_share'] == 0.0
    people = p['people'] - p['held']
    until = min(t, length)
    out = {}
    deaths = survivors = exposure = 0.0
    for kind, size_of in (
        ('residents', lambda band: people * p['share_' + band] * (1 - p['devshare_' + band])),
        ('confined', lambda band: p['held'] * p['share_' + band]),
    ):
        building = 'homes' if kind == 'residents' else 'compound'
        tau, slope = p['warm_' + building + '_h'], p['slope_' + building]
        full_rise = heat.delta[building] / slope
        # exp(E_eff * rise) with E_eff the weighted slope above every top
        e_eff = sum(p['curve_weight_' + s] * p['curve_ext_' + s] for s in STUDIES)
        # The expected visits of a person at home, and the visits that count under the limit.
        visits = p['ed_rate'] * heat.rr_ed0 * _ramp_integral(p['ed_slope'] * full_rise, tau, until)
        limit = p['visit_limit']
        illness = (
            p['heatstroke_share']
            * p['people_per_visit']
            * (1 - p['heatstroke_fatality'])
            * limit
            * -math.expm1(-visits / limit)
        )
        # The heat-death term rises with exp(sH * rise) until the cap, then stays at its capped value.
        cap_time = heat.reach_time(building, heat.cap)
        k_hd = p['hdeath_slope'] * full_rise
        for band in BANDS:
            regime = heat.regime(building, band, until)
            assert regime in ('all-cause', 'heat-death'), (building, band, regime)
            if regime == 'all-cause':
                hd = p['rate_' + band] * heat.rr0 * _ramp_integral(e_eff * full_rise, tau, until)
            else:
                capped = cap_time is not None and cap_time < until
                first = min(until, cap_time) if capped else until
                hd = p['hdeath_rate'] * heat.rr_hd0 * _ramp_integral(k_hd, tau, first)
                if capped:
                    hd += p['hdeath_rate'] * heat.z(building, cap_time) * (until - cap_time)
            if kind == 'residents':
                size = size_of(band) * (1 - p['backup_res_' + band])
                assert p['private_res_' + band] == 0.0 and p['devshare_' + band] == 0.0
            else:
                size = size_of(band) * (1 - p['backup_conf_' + band])
            dead = -size * math.expm1(-hd)
            ill = size * math.exp(-hd) * -math.expm1(-illness)
            out[f'{kind}_{ENTITY_BAND[band]}.deaths'] = dead
            deaths += dead
            survivors += ill
            hazard_integral = _closed_form_hazard(
                p, heat, building, band, regime, e_eff, full_rise, tau, cap_time, k_hd
            )
            exposure += (
                size
                * quad(
                    lambda u: math.exp(-hazard_integral(u)),
                    0.0,
                    until,
                    points=[x for x in (cap_time,) if x is not None and 0.0 < x < until] or None,
                    epsabs=0.0,
                    epsrel=1e-12,
                    limit=200,
                )[0]
            )
    out.update(
        {
            'deaths': deaths,
            'heatstroke_survivors': survivors,
            'casualties': deaths + survivors,
            'late_deaths': survivors * p['severe_share'] * p['late_fatality'],
            'device_admissions': 0.0,
            'thermal_exposure': exposure,
        }
    )
    return out


def _closed_form_hazard(p, heat, building, band, regime, e_eff, full_rise, tau, cap_time, k_hd):
    """The cumulative death hazard as a function of time, in closed form (see `closed_form_heat`)."""

    def hazard(u):
        if regime == 'all-cause':
            return p['rate_' + band] * heat.rr0 * _ramp_integral(e_eff * full_rise, tau, u)
        if cap_time is not None and u > cap_time:
            return p['hdeath_rate'] * (
                heat.rr_hd0 * _ramp_integral(k_hd, tau, cap_time)
                + heat.z(building, cap_time) * (u - cap_time)
            )
        return p['hdeath_rate'] * heat.rr_hd0 * _ramp_integral(k_hd, tau, u)

    return hazard


def device_user_count(p):
    """The residents of the homes who depend on a device, over all age bands."""
    return (p['people'] - p['held']) * sum(p['share_' + band] * p['devshare_' + band] for band in BANDS)


def admission_rate(p):
    """The hourly hazard of admission of a device user without power, before it is scaled by the outage."""
    return p['vent_admission'] * (p['vent_share'] + (1.0 - p['vent_share']) * p['conc_factor'])


def exposure_without_heat(p, profile, t):
    """Person-hours at risk at home up to time t when no heat hazard acts, without `Blackout`.

    Nobody dies or falls ill, so each pool changes only by its own exits: the private pool leaves at a
    constant rate while power is off, the heat goes on and the move window is open; the dark device
    users leave through admissions and the outreach move. The integrand is the share without power times
    the people at home, which is piecewise polynomial or exponential, so `quad` cut at the knots is exact
    to rounding.
    """
    length = p['heat_h']
    until = min(t, length)
    if until <= 0.0:
        return 0.0
    people = p['people'] - p['held']
    knots = [k for k, _s in profile.knots if 0.0 < k < until]
    dark_area = profile.deficit(0.0, until)

    def weighted(at_home, kinks=()):
        points = sorted({*knots, *(x for x in kinks if 0.0 < x < until)})
        return quad(
            lambda u: (1.0 - profile.service(u)) * at_home(u),
            0.0,
            until,
            points=points or None,
            epsabs=0.0,
            epsrel=1e-12,
            limit=200,
        )[0]

    total = 0.0
    for band in BANDS:
        share, device = p['share_' + band], p['devshare_' + band]
        at_risk = (1.0 - p['backup_res_' + band]) * people * share * (1.0 - device)
        private = p['private_res_' + band] * at_risk
        total += ((1.0 - p['private_res_' + band]) * at_risk) * dark_area
        if private > 0.0:
            start = p['moves_start_h']
            rate = private / (p['moves_end_h'] - start)
            stop = min(p['moves_end_h'], profile.full_time, length)
            total += private * dark_area - weighted(
                lambda u: rate * max(0.0, min(u, stop) - start), (start, stop)
            )
        users = people * share * device
        total += p['alt_share'] * users * dark_area
        total += (1.0 - p['backup_conf_' + band]) * p['held'] * share * dark_area
        dark = (1.0 - p['alt_share']) * users
        if dark > 0.0:
            moves = p['outreach_h'] < profile.full_time
            total += dark * weighted(
                lambda u: dark_share_at_home(p, profile, u, moves), (p['battery_h'], p['outreach_h'])
            )
    return total


def dark_share_at_home(p, profile, u, moves):
    """With no heat hazard, the share of the dark device users still at home at time u."""
    hazard = admission_rate(p) * profile.deficit(p['battery_h'], u) if u > p['battery_h'] else 0.0
    return math.exp(-hazard) * ((1.0 - p['reach']) if moves and u >= p['outreach_h'] else 1.0)


def device_admissions_without_heat(p, profile, t):
    """People admitted to hospital by time t among the device users in the homes, with no heat hazard.

    A share `alt_share` has its own power for the device and is never admitted. Each of the others
    ("dark") is admitted at the rate `admission_rate` times the share without power, once the battery
    time `battery_h` has passed. With no heat hazard nobody dies or falls seriously ill, so the dark group
    shrinks only by admissions, which hit everyone alike, and by the outreach move: at `outreach_h`, if
    power is not fully back, the share `reach` of the dark people moves at once to a powered site.
    """
    dark = (1.0 - p['alt_share']) * device_user_count(p)
    rate = admission_rate(p)

    def hazard(until):
        return rate * profile.deficit(p['battery_h'], until) if until > p['battery_h'] else 0.0

    left = math.exp(-hazard(t))
    if t < p['outreach_h'] or profile.service(p['outreach_h']) >= 1.0:
        return dark * (1.0 - left)
    left_at_move = math.exp(-hazard(p['outreach_h']))
    return dark * ((1.0 - left_at_move) + (1.0 - p['reach']) * (left_at_move - left))
