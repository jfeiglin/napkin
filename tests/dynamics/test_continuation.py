"""Branches of equilibria, folds and Hopf points (napkin/dynamics/continuation.py).

Each expectation is a closed form of a normal form: the fold X' = mu - (X - c)^2 turns at mu = 0; with
mu = mu0 + slope t it turns at t = -mu0 / slope; the cusp X' = mu + lam y - y^3 turns at
mu = +-2 (lam / 3)^(3/2) and has no fold for lam = 0; and the Hopf normal form loses the stability of
its centre at mu = 0, with the frequency omega. A stock that stays empty on its bound leaves the fold's
branch as it is, and the lines of rests s = +-sqrt(mu) of the ridge turn at mu = 0 like the fold, with one
neutral mode at every point. A queue's branch has a corner where the queue stops filling, and below it
the one rest is the queue of Little's law."""

from __future__ import annotations

import math

import numpy as np
import pytest

from napkin.dynamics import STABLE, UNSTABLE, continue_equilibrium, fold_curve
from tests.build import compiled
from tests.dynamics.models import CENTRE, cusp, fold, fold_in_time, fold_with_empty_stock, hopf, queue, ridge


def test_a_branch_turns_at_the_fold_and_returns_on_the_unstable_side():
    branch = continue_equilibrium(compiled(fold(1.0)), 'a', 's.mu', (1.0, -1.0), start=np.array([CENTRE + 1]))
    (turn,) = branch.folds
    assert turn.parameter == pytest.approx(0.0, abs=1e-7)
    assert turn.state[0] == pytest.approx(CENTRE, abs=1e-3)
    assert branch.stop == 'span'
    above = [p for p in branch.points if p.state[0] > CENTRE + 0.05]
    below = [p for p in branch.points if p.state[0] < CENTRE - 0.05]
    assert above and all(p.stability == STABLE for p in above)
    assert below and all(p.stability == UNSTABLE for p in below)
    # Every point of the branch is an equilibrium: mu = (X - c)^2.
    for point in branch.points:
        assert point.parameter == pytest.approx((point.state[0] - CENTRE) ** 2, abs=1e-8)


def test_a_branch_in_time_turns_where_the_driver_reaches_the_fold():
    mu0, slope = -2.0, 0.5
    model = compiled(fold_in_time(mu0, slope))
    # At t = 8 h, mu = 2: start on the stable branch and follow it back in time.
    branch = continue_equilibrium(model, 'a', 't', (8.0, 0.0), start=np.array([CENTRE + 1.5]))
    (turn,) = branch.folds
    assert turn.parameter == pytest.approx(-mu0 / slope, abs=1e-6)


@pytest.mark.parametrize('lam', [1.0, 3.0, 4.5])
def test_the_cusp_has_two_folds_at_the_closed_form(lam):
    edge = 2 * (lam / 3) ** 1.5
    model = compiled(cusp(-2 * edge, lam))
    roots = np.roots([-1, 0, lam, -2 * edge])  # mu + lam y - y^3 = 0 at mu = -2 edge: one real root
    lower = CENTRE + min(r.real for r in roots if abs(r.imag) < 1e-9)
    branch = continue_equilibrium(
        model, 'a', 's.mu', (-2 * edge, 2 * edge), start=np.array([lower]), max_step=0.02
    )
    turns = [fold.parameter for fold in branch.folds]
    assert turns == pytest.approx([edge, -edge], abs=1e-6)
    assert branch.stop == 'span'


def test_the_cusp_without_lambda_has_no_fold():
    model = compiled(cusp(-2.0, 0.0))
    branch = continue_equilibrium(model, 'a', 's.mu', (-2.0, 2.0), start=np.array([CENTRE - 2 ** (1 / 3)]))
    assert branch.folds == []
    assert all(p.stability in (STABLE, 'nonhyperbolic') for p in branch.points)


def test_the_fold_curve_follows_the_edges_of_the_bistable_region():
    model = compiled(cusp(-6.0, 3.0))
    grid = [1.5, 3.0, 4.5]
    rows = fold_curve(model, 'a', 's.mu', (-6.0, 6.0), 's.lam', grid, max_step=0.02)
    for lam, turns in rows:
        edge = 2 * (lam / 3) ** 1.5
        assert sorted(turns) == pytest.approx([-edge, edge], abs=1e-6)


def test_the_hopf_point_is_where_the_centre_loses_its_stability():
    omega = 2.0
    model = compiled(hopf(-0.5, omega))
    branch = continue_equilibrium(model, 'a', 's.mu', (-0.5, 0.5), start=np.array([CENTRE, CENTRE]))
    (point,) = branch.hopfs
    assert point.parameter == pytest.approx(0.0, abs=1e-7)
    assert point.frequency == pytest.approx(omega, rel=1e-5)
    assert branch.folds == []
    assert branch.points[0].stability == STABLE
    assert branch.points[-1].stability == UNSTABLE
    assert math.isclose(branch.points[-1].parameter, 0.5, abs_tol=0.06)


def test_a_stock_that_stays_empty_does_not_stop_a_branch():
    # E starts on its bound 0 and drains at k E, so it stays there: the branch is the fold's.
    model = compiled(fold_with_empty_stock(1.0))
    branch = continue_equilibrium(model, 'a', 's.mu', (1.0, -1.0), start=np.array([CENTRE + 1, 0.0]))
    assert branch.stop == 'span'
    (turn,) = branch.folds
    assert turn.parameter == pytest.approx(0.0, abs=1e-7)
    for point in branch.points:
        x, e = point.state
        assert abs(e) <= 1e-9
        assert point.parameter == pytest.approx((x - CENTRE) ** 2, abs=1e-8)


def test_a_branch_of_lines_of_rests_turns_at_its_fold():
    # Each point lies on a line of rests s = +-sqrt(mu): one neutral mode, and the eigenvalue -3 s on the
    # other direction, so the branch is stable above the fold and unstable below it.
    branch = continue_equilibrium(
        compiled(ridge(1.0)), 'a', 's.mu', (1.0, -1.0), start=np.array([CENTRE + 1, CENTRE + 1])
    )
    assert branch.stop == 'span'
    (turn,) = branch.folds
    assert turn.parameter == pytest.approx(0.0, abs=1e-7)
    assert turn.state.sum() / 2 == pytest.approx(CENTRE, abs=1e-3)
    for point in branch.points:
        s = point.state.sum() / 2 - CENTRE
        assert point.parameter == pytest.approx(s**2, abs=1e-8)
        assert point.neutral == 1
    above = [p for p in branch.points if p.state.sum() / 2 > CENTRE + 0.05]
    below = [p for p in branch.points if p.state.sum() / 2 < CENTRE - 0.05]
    assert above and all(p.stability == STABLE for p in above)
    assert below and all(p.stability == UNSTABLE for p in below)


def test_a_branch_steps_over_the_corner_where_a_queue_stops_filling():
    # Above mu = 1 the departures run at capacity and every queue of 2 people or more is a rest, so the
    # queue keeps its start. At mu = 1 the branch has a corner: no direction of rests moves mu. Below it
    # the one rest is the queue of Little's law, B = mu T, with T = 2 h and the eigenvalue -1 / T.
    branch = continue_equilibrium(
        compiled(queue(1.5, start=2.2)), 'a', 's.mu', (1.5, 0.5), start=np.array([2.2])
    )
    assert branch.stop == 'span'
    assert branch.folds == [] and branch.hopfs == []
    above = [p for p in branch.points if p.parameter > 1 + 1e-6]
    below = [p for p in branch.points if p.parameter < 1 - 1e-6]
    assert above and below
    for point in above:
        assert point.state[0] == pytest.approx(2.2, abs=1e-9)
        assert point.neutral == 1
    for point in below:
        assert point.state[0] == pytest.approx(2 * point.parameter, abs=1e-8)
        assert (point.neutral, point.stability) == (0, STABLE)
        assert point.eigenvalues == pytest.approx([-0.5], rel=1e-6)
    assert min(p.parameter for p in below) <= 0.5
