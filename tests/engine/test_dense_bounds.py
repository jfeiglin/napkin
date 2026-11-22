"""Direct boundary cases for the signed coordinates of a Radau collocation step."""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from napkin.engine.continuous.dense import bound_crossings


def step(initial, coefficients):
    return SimpleNamespace(t_old=2.0, h=4.0, y_old=np.array(initial), Q=np.array(coefficients))


@pytest.mark.parametrize('scale', [2.0**-800, 1.0, 2.0**800])
@pytest.mark.parametrize('sign', [-1, 1])
def test_exact_tangency_and_adjacent_strict_miss(scale, sign):
    # -(3x - 1)² touches from below at 1/3; its time is not representable.
    output = step([-scale * sign], [[6 * scale * sign, -9 * scale * sign, 0]])
    got = bound_crossings(output, 2, 6, [0], [0], [sign])
    assert len(got) == 1 and got[0][1] == 0
    assert got[0][0] == pytest.approx(2 + 4 / 3, abs=1e-14)
    output.y_old[0] = math.nextafter(output.y_old[0], -sign * math.inf)
    assert bound_crossings(output, 2, 6, [0], [0], [sign]) == []


@pytest.mark.parametrize('sign', [-1, 0, 1])
def test_small_cubic_term_controls_whether_a_quadratic_reaches_its_face(sign):
    # The finite extremum is near 1/2, and a nonzero cubic creates a second
    # extremum very far outside the step. It still determines the sign at 1/2.
    output = step([-0.25], [[1, -1, sign * 2.0**-800]])
    got = bound_crossings(output, 2, 6, [0], [0], [1])
    if sign < 0:
        assert got == []
    else:
        assert len(got) == 1 and got[0][0] == pytest.approx(4.0, abs=1e-14)


def test_repeated_stock_faces_sort_by_time_and_only_count_arrivals_inside_the_interval():
    output = step([0, 0], [[1, -1, 0], [1, 0, 0]])
    faces = ([0, 0, 1], [1 / 8, 3 / 16, 1 / 8], [-1, 1, 1])
    got = bound_crossings(output, 2, 6, *faces)
    assert [k for _, k in got] == [2, 1, 0]
    times = [2.5, 3.0, 2 + 2 * (1 + math.sqrt(0.5))]
    assert [t for t, _ in got] == pytest.approx(times, abs=1e-14)
    assert bound_crossings(output, 3.5, 6, *faces) == [got[-1]]
    assert bound_crossings(output, 2, 2.25, *faces) == []


def test_accepted_state_supplies_the_endpoint_sign_in_both_directions():
    output = step([-1.0, -1.0], [[math.nextafter(1, 0), 0, 0], [1, 0, 0]])
    faces = ([0, 1], [0, 0], [1, 1])
    assert bound_crossings(output, 2, 6, *faces) == [(6, 1)]
    assert bound_crossings(output, 2, 6, *faces, accepted_end=[0, -(2.0**-53)]) == [(6, 0)]


def test_initially_stationary_and_inward_faces_remain_free_until_an_actual_return():
    output = step([0, 0, 0, 0], [[0, 0, 0], [-1, 0, 0], [-1, 2, 0], [1, 0, 0]])
    assert bound_crossings(output, 2, 6, range(4), [0] * 4, [1] * 4) == [(2, 3), (4, 2)]


def test_a_small_nonzero_bound_survives_subtraction_from_a_much_larger_initial_level():
    # (1-2x)² reaches a small positive lower bound before its minimum and
    # never reaches the matching negative bound. Both rounded initial gaps are 1.
    face = 2.0**-58
    output = step([1.0], [[-4, 4, 0]])
    got = bound_crossings(output, 2, 6, [0, 0], [face, -face], [-1, -1])
    assert len(got) == 1 and got[0][1] == 0
    assert got[0][0] == pytest.approx(2 + 2 * (1 - math.sqrt(face)), abs=1e-14)


def test_a_positive_arrival_too_close_to_represent_advances_from_a_late_start():
    output = step([-1e-9], [[1, 0, 0]])
    start, end = 2.0**30, 2.0**30 + 1
    output.t_old, output.h = start, end - start
    assert bound_crossings(output, start, end, [0], [0], [1]) == [(math.nextafter(start, end), 0)]


def test_touching_from_the_exterior_does_not_arm_a_new_outward_contact():
    # (2x-1)² touches from above then keeps rising on the exterior side.
    output = step([1.0], [[-4, 4, 0]])
    assert bound_crossings(output, 2, 6, [0], [0], [1]) == []


@pytest.mark.parametrize('direction', [-1, 1])
@pytest.mark.parametrize('accepted', [None, [0.0]])
def test_subnormal_departure_must_reach_a_distinct_coordinate(direction, accepted):
    # x²(1-x) peaks at 4/27. Three minimum subnormals give a peak below half
    # a representable value, while four give a distinguishable excursion.
    quantum = math.ulp(0.0)
    for n, expected in ((3, []), (4, [(2, 0)])):
        amplitude = n * quantum * direction
        output = step([0.0], [[0.0, amplitude, -amplitude]])
        assert bound_crossings(output, 2, 6, [0], [0], [direction], accepted_end=accepted) == expected
        # The opposite face sees the representable inward departure return at the endpoint.
        assert bound_crossings(output, 2, 6, [0], [0], [-direction], accepted_end=accepted) == (
            [(6, 0)] if n == 4 else []
        )


@pytest.mark.parametrize('sign', [-1, 1])
def test_inward_release_has_a_distinct_level_when_allowance_rounds_away(sign):
    from napkin.engine.allocation import StockFaces

    level = np.array([1230980.1235242249])
    low, high = np.array([sign > 0]), np.array([sign < 0])
    faces = StockFaces(level - 1, level + 1, [1.0], 1e-9)
    armed = faces.armed(low, high, releases=(level, 1e-12))
    assert armed.kinds == ('release',)
    assert armed.levels[0] == math.nextafter(level[0], sign * math.inf)


def test_monotone_departure_without_a_separate_endpoint_requires_a_distinct_coordinate():
    for coordinate, delta in ((1.5, math.ulp(1.5)), (0.0, math.ulp(0.0))):
        output = step([coordinate], [[delta, 0.0, 0.0]])
        assert bound_crossings(output, 2, 3, [0], [coordinate], [1]) == []
        assert bound_crossings(output, 2, 6, [0], [coordinate], [1]) == [(2, 0)]
