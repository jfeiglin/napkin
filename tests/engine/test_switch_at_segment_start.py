"""A rate that tests a nondecreasing ledger against its lower bound, at the start of a segment in
which the ledger leaves that bound.

A valve opens at t = 2 h. Material escapes at held / (1 h) * exp(-(t - 2 h) / 1 h), so
held(t) = n * exp(-(1 - exp(-(t - 2)))) for t >= 2, and released = n - held. An hour count runs
while anything has escaped: its rate is 1 if released > 0, else 0, so it equals t - 2 after the
opening. Before the fix, the solver used the count's rate from the bound (0) at the segment start
and failed for the sizes 1 and 100 ("required step size is less than spacing between numbers").
"""

import math

import pytest

from tests.build import event, flow, named, run, stock, system

OPEN_H = 2.0


def valve(held=100, size=100):
    return system(
        stock('held', held, size=size),
        stock('hours', 0, 'h', size=10, kind='tally', rate='1 if released > 0 people else 0'),
        stock('released', 0, size=size, kind='tally'),
        named('valve', 'closed', 'open'),
        flow(
            'escape',
            'held -> released',
            'held / 1 h * exp(- (t - 2 h) / 1 h) if valve is "open" else 0 people/h',
        ),
        event('open', 't >= 2 h', once=False, transition='valve "closed" -> "open"', doc='Open'),
        horizon=10,
    )


@pytest.mark.parametrize('size', [1, 100, 70000])
def test_a_ledger_that_leaves_its_bound_switches_the_rate_at_once(size):
    _, trajectory = run(valve(size=size))
    assert trajectory.settings['integration_segments'], 'the decaying rate needs the numerical solver'
    for at in (1.0, OPEN_H, 2.5, 4.0, 10.0):
        env = trajectory.env_at(at)
        expected = 100 * math.exp(-(1 - math.exp(-(at - OPEN_H)))) if at >= OPEN_H else 100
        assert env['s.hours'] == pytest.approx(max(0.0, at - OPEN_H), abs=1e-9)
        assert env['s.held'] == pytest.approx(expected, rel=1e-7)
        assert env['s.held'] + env['s.released'] == pytest.approx(100, abs=1e-9 * size)


def test_a_ledger_that_stays_on_its_bound_keeps_the_rate_off():
    # Nothing is held, so nothing escapes when the valve opens: the count must not start.
    _, trajectory = run(valve(held=0))
    for at in (OPEN_H, 4.0, 10.0):
        env = trajectory.env_at(at)
        assert env['s.released'] == 0
        assert env['s.hours'] == 0
