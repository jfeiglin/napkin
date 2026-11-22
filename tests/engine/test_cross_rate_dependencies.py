"""A downstream flow must see the upstream rate on the trajectory it is testing."""

from fractions import Fraction

import pytest

from napkin.model.compile import compile_text
from tests.engine.cross_rate_cases import UNITS, WATER, case_for, engine_rows, source_of
from tests.reference.from_program import run_of, value_at


@pytest.mark.parametrize('setting', ['request', 'capacity'])
@pytest.mark.parametrize('selector', ['guard', 'key'])
@pytest.mark.parametrize('event', [False, True], ids=['uninterrupted', 'empty-event'])
def test_seed_zero_cross_rate_switch_delivers_eleven_eighths_of_a_litre(setting, selector, event):
    case = case_for(0)
    model = compile_text(source_of(case, f'{selector}-{setting}', event), UNITS)
    path, stop, rows = engine_rows(model, (WATER,), (2,))
    assert path == ('Sparse', {'yard.tap': 0, 'yard.pipe': 1}) and not stop
    # Tap = 2t. It reaches 1 L/h after half an hour. Pipe delivers 2 L/h for
    # that half-hour and 1/4 L/h for the remaining hour and a half.
    reference, failure = run_of(model.program, model.configuration)
    assert failure is None
    assert value_at(reference, model.program, WATER, Fraction(2)) == Fraction(11, 8)
    assert rows[WATER] == pytest.approx((1.375,), rel=0, abs=3e-8)
