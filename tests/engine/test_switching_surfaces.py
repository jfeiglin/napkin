"""The switching surfaces of a run of the general tier (`continuous/integrate.py`,
`switching_surfaces`, `switching_roots`).

A rate with `min`, `max`, `clip`, `abs` or a comparison is smooth on each side of a surface and
has a kink or a jump on it. A numerical segment ends on such a surface, so that no step of the
solver has both sides in it. The surfaces are stated here by the rule, for one rate that has each
form; and a run whose rate has a kink at a time with a closed form ends a segment there.
"""

import math

import pytest

from napkin.core import expr
from napkin.engine.continuous.integrate import switching_surfaces
from napkin.engine.continuous.system import System
from napkin.engine.runtime import NumericalSettings, simulate
from tests import build as b


def system_of(*members, horizon=5):
    rs = b.resolved(b.system(*members, horizon=horizon))
    return rs, System(rs, b.library(), NumericalSettings.parse(None))


def test_the_surfaces_of_a_run_are_those_of_each_form_with_a_side_that_moves():
    """One rate with each form. By the rule: `min` and `max` have a surface for each pair of their
    values; `clip` has one at each end; `abs` has one where its value is zero; a comparison of order
    has one where its sides are equal, and a comparison of equality has none (`level + mid is not
    mark`). A pair with no side that moves between moments is no surface: the two inputs of the
    last `min` never change."""
    rate = (
        'min(level, cap) / 1 h + clip(level, low, high) / 1 h + abs(level - mid) / 1 h'
        ' + (gain if level > mark else 0 people/h) + (gain if level + mid is not mark else 0 people/h)'
        ' + max(low, mid, level) / 1 h + min(cap, high) / 1 h'
    )
    _, s = system_of(
        *(b.parameter(name, value, 'people') for name, value in (('cap', 9), ('low', 1), ('high', 8))),
        b.parameter('mid', 4, 'people'),
        b.parameter('mark', 6, 'people'),
        b.parameter('gain', 2, 'people/h'),
        b.stock('level', 0, kind='tally', size=None, rate=rate),
    )
    found = [(expr.text(a), expr.text(b_)) for a, b_ in switching_surfaces(s)]
    assert len(found) == len(set(found))
    assert set(found) == {
        ('s.level', 's.cap'),
        ('s.level', 's.low'),
        ('s.level', 's.high'),
        ('s.level - s.mid', '0'),
        ('s.level', 's.mark'),
        # `max` of three values: each pair with the level; the pair of the two inputs does not move.
        ('s.low', 's.level'),
        ('s.mid', 's.level'),
    }


def test_a_segment_ends_where_the_rate_changes_its_branch():
    """The level rises at `max(0.2, 1 - level)` an hour from 0. It is `1 - exp(-t)` until its rate
    falls to 0.2, at `t = ln 5`, and it rises at 0.2 an hour after that. The run has the end of a
    segment at that time, and the level at the horizon of 5 h is `0.8 + 0.2 (5 - ln 5)`."""
    rs, _ = system_of(
        b.stock('level', 0, kind='tally', size=None, rate='max(0.2 people/h, (1 people - level) / 1 h)'),
    )
    trajectory = simulate(rs, b.library())
    switch = math.log(5)
    ends = [segment.end for segment in trajectory._segments]
    assert min(abs(end - switch) for end in ends) < 1e-6, ends
    assert trajectory.env_at(5.0)['s.level'] == pytest.approx(0.8 + 0.2 * (5 - switch), rel=1e-6)
