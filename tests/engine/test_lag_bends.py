"""The raw history and uniform-lag report keep a bend between their ordinary sampling points."""

from tests.engine.lag_bend_cases import check_lag_bends


def test_a_narrow_bend_contributes_its_area_to_a_uniform_lag():
    check_lag_bends(0)
