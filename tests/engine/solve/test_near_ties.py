"""Two rows of a declared solver that nearly tie (agent E's finding: a moving solver whose two bounds
meet failed "numerical in fair sharing, tier 0: no answer on the face that the earlier ranks left").

An objective's optimum is kept by pinning (`ranked.pin`): a row whose dual is not zero becomes an
equality on the side that it rests on. HiGHS holds a row to its feasibility tolerance (1e-7), so where
two rows of one unknown nearly tie, `u <= 2` and `u <= 2 - d` with d below that tolerance, it could
answer u = 2, the second row missed by d, and pin the first: the face was u = 2 against u <= 2 - d,
empty for the ranks after it, which hold their rows to the tightest tolerance. The rule: whatever the
gap between two rows, the answer is that of the tighter, and each later rank has a face to work on.

1. By hand: one flow that asks 10 L/h, `u <= 2` and `u <= 2 - d`, maximized: u = min(2, 2 - d), served
   the fraction u / 10, for gaps from zero to 1e-3 on either side, several a decade, the rows in either
   order, in any unit of the flow.
2. In a run: a provider's solver serves a pipe of a tank up to `want` and up to the tank's water over
   an hour, a moving solver. From 2 L both bounds meet at the start; the rate is then the water over
   an hour, so the tank holds 2 e^-t L. From 3 L the pipe carries 2 L/h to 0.5 h, where the bounds
   meet, then the water, 2 e^-(t - 0.5) L, until `want` falls to 1 L/h at 1 h: 1 L/h until the water
   is 1 L, at 1 + 2 e^-0.5 - 1 h, where they meet again, then e^-(t - that) L.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from napkin.engine.solve import FLOW, Problem, Solver
from napkin.engine.timeline import Plan, Run, read
from napkin.program.build import (
    SINK,
    Builder,
    after,
    assign,
    constraint,
    event,
    flow,
    given,
    local,
    maximize,
    named,
    q,
    solve_for,
    solver,
    start,
    this,
    value,
)
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
# Several gaps a decade from 1e-12 to 1e-6, and at the tight tolerance of HiGHS (1e-10). Gaps of 1.5
# to 2.5e-10 once passed the guard (`ranked.exact`), which measured the miss relative to the size of
# its row (3 here), and left the next rank an empty face; 1e-10 and 3e-9, the nearest gaps tested
# then, are either side of that window.
GAPS = sorted(
    {0.0, 0.9e-10, 1.1e-10, 1.2e-10, 1e-3}
    | {m * 10.0**e for e in range(-12, -5) for m in (1, 1.5, 2, 2.5, 3, 5, 7)}
)


def tie(gap, swapped=False, scale=1.0):
    """The problem by hand: a flow of target 10 (in units of `scale`), at most 2 and at most 2 - gap,
    maximized, with its claim."""
    problem = Problem()
    u = problem.unknown(('flow', 'pipe'), 0.0, np.inf, FLOW, 10.0 * scale, scale)
    rows = [('wanted', 2.0 * scale), ('left', (2.0 - gap) * scale)]
    for name, limit in reversed(rows) if swapped else rows:
        problem.at_most(name, {u: 1.0}, limit)
    problem.minimize({u: -1.0})
    problem.claim({u: 1.0}, 10.0 * scale, 0)
    return problem


@pytest.mark.parametrize('scale', [1.0, 1e-7, 1e4])
@pytest.mark.parametrize('swapped', [False, True], ids=['in order', 'swapped'])
@pytest.mark.parametrize('gap', [*GAPS, *(-gap for gap in GAPS[1:])])
def test_two_rows_that_nearly_tie_give_the_answer_of_the_tighter(gap, swapped, scale):
    answer = Solver().solve(tie(gap, swapped, scale))
    best = min(2.0, 2.0 - gap)
    assert answer.x[0] == pytest.approx(best * scale, rel=1e-9)
    assert answer.levels[0] == pytest.approx(best / 10, rel=1e-8)


def tank(water):
    """The plant of the module: a tank of `water` L whose pipe a moving solver serves."""
    b = Builder(UNITS)
    member = b.entity(
        'plant',
        value('w0', 'L', water, lower=0),
        value('want', 'L/h', 2),
        event('tick', after(q(1, 'h'), assign(this.want, q(1, 'L/h')))),
        flow('pipe', this.w0, SINK, request=q(10, 'L/h')),
    )
    b.entity(
        'provider',
        solver(
            'share',
            given('use', member.pipe),
            given('cap', member.want),
            given('left', member.w0),
            solve_for(local.use.actual_rate),
            constraint(local.use.actual_rate <= local.cap),
            constraint(local.use.actual_rate <= local.left / q(1, 'h')),
            maximize(local.use.actual_rate),
        ),
    )
    b.setup(start(named('plant').tick))
    return b.finish()


def by_hand(water, t):
    """The tank's water at t, worked by hand (see the module)."""
    if water == 2:
        return 2 * math.exp(-t)
    if t <= 0.5:
        return 3 - 2 * t
    at_one = 2 * math.exp(-0.5)
    if t <= 1:
        return 2 * math.exp(-(t - 0.5))
    meet = 1 + at_one - 1
    if t <= meet:
        return at_one - (t - 1)
    return math.exp(-(t - meet))


@pytest.mark.parametrize('water', [2, pytest.param(3, marks=pytest.mark.deep)])
def test_a_moving_solver_whose_two_bounds_meet_goes_on_with_the_tighter(water):
    """To 1 h from 2 L, and to 1.3 h from 3 L, past both meetings (a solve at each trial state of a
    curve is slow: the second takes about ten seconds)."""
    program = tank(water)
    horizon = {2: 1, 3: 1.3}[water]
    record = Run(Plan.of(program, Configuration(Request(horizon)))).run()
    assert record.failure is None, record.failure.detail('message')
    times = [t for t in (0.25, 0.5, 0.75, 1, 1.1, 1.25, 1.3) if t <= horizon]
    found = read(record, program, ['plant.w0'], times)[0].values
    for t, value_ in zip(times, found, strict=True):
        assert value_ == pytest.approx(by_hand(water, t), rel=1e-5, abs=1e-7), (t, value_)
