"""A located bound can be crossed between adjacent floating-point instants."""

from types import SimpleNamespace

import numpy as np
import pytest

from napkin.engine.continuous.bounds import check_bounds
from napkin.engine.errors import SimulationError


@pytest.mark.parametrize(
    ('values', 'before', 'after', 'error'),
    [
        ((-2e-8, 1), 4e-8, -3e-8, None),
        ((-2e-8, 1), -1e-8, -3e-8, 'stock'),
        ((-2e-8, -2e-8), 4e-8, -3e-8, 'other'),
        ((float('nan'), 1), 4e-8, -3e-8, 'Nonfinite'),
    ],
)
def test_only_the_located_coordinate_can_use_its_time_bracket(values, before, after, error):
    system = SimpleNamespace(
        state_ids=['stock', 'other'],
        lower=np.zeros(2),
        upper=np.full(2, np.inf),
        ledger_slack=np.full(2, 1e-10),
        atol=np.full(2, 1e-10),
        analysis={},
    )
    state = np.array(values)

    def dense(time):
        return [before if time < 1 else after, 1]

    if error is None:
        check_bounds(system, state, at=1, targets={0: 0}, solution=dense)
        np.testing.assert_array_equal(state, values)
    else:
        with pytest.raises(SimulationError, match=error):
            check_bounds(system, state, at=1, targets={0: 0}, solution=dense)
