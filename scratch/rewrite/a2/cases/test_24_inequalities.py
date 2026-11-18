"""Case 24: inequalities in the distance step. 4 <= x + y <= 6: targets (0, 0) give (2, 2); targets (5, 5)
give (3, 3). x + y == 1 with targets zero gives (1/2, 1/2), where a linear program may give (1, 0)."""
from fractions import Fraction as F

import pytest

from ref import Model, N, solver, unknown
from ref.run import Run


def build(target, rows):
    m = Model()
    m.entity('box', solvers=[solver('pick', solve_for=[unknown('x', init=target), unknown('y', init=target)], constraints=rows)])
    return m


@pytest.mark.parametrize('target, expected', [(0, (2, 2)), (5, (3, 3))])
def test_band(target, expected):
    r = Run(build(target, [N.x + N.y >= 4, N.x + N.y <= 6]), horizon=0).run()
    assert (r.read(N.box.pick.x), r.read(N.box.pick.y)) == expected


def test_half_half():
    r = Run(build(0, [N.x + N.y == 1]), horizon=0).run()
    assert (r.read(N.box.pick.x), r.read(N.box.pick.y)) == (F(1, 2), F(1, 2))
