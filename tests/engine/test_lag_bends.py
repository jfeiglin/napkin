"""The raw history and uniform-lag report keep a bend between their ordinary sampling points."""

import pytest

from napkin.engine import run
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text
from tests.engine.lag_bend_cases import check_lag_bends


def test_a_narrow_bend_contributes_its_area_to_a_uniform_lag():
    check_lag_bends(0)


def test_a_single_smooth_operand_can_cross_the_same_branch_twice_between_fit_points():
    model = compile_text(
        """scenario "Short curved pulse"
    horizon 1 h
yard:
    peak = formula(max(0 L, 1 L - ((t - 0.52 h) / (0.001 h)) ** 2 * (1 L)))
""",
        {'h': {'time': 1}, 'L': {'volume': 1}},
    )
    record = run(model.program, model.configuration)
    assert record.failure is None
    pulse = record.history(key_of(model.program, 'yard.peak'))
    assert [pulse.at(t) for t in (0.51, 0.5195, 0.52, 0.5205, 0.53)] == pytest.approx(
        (0, 0.75, 1, 0.75, 0), abs=1e-8
    )


def test_undefined_candidate_on_an_inactive_arm_leaves_a_straight_record():
    model = compile_text(
        """scenario "Dormant branch"
    horizon 1 h
yard:
    input gate: bool = false
    input zero = 0
    flow fill: SOURCE -> this.water
        request = 1 L/h
    water: L = 0 L
    selected = formula(max(this.water, this.water / this.zero) if this.gate else this.water)
""",
        {'h': {'time': 1}, 'L': {'volume': 1}},
    )
    record = run(model.program, model.configuration)
    assert record.failure is None
    history = record.history(key_of(model.program, 'yard.selected'))
    assert [history.at(t) for t in (0, 0.25, 0.5, 0.75, 1)] == pytest.approx([0, 0.25, 0.5, 0.75, 1])
    assert all(piece.t in (0, 1) for piece in history.pieces)
