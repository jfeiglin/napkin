"""The engine sizes each value (docs/engine.md, "Sizes and tolerances").

A quantity's absolute tolerance is `atol_factor` times its size: the `size` that the file writes,
else the largest of one of its unit, its start value, its finite bounds, the largest start value of
the quantities that flows connect it to, and the capacity of a rationed flow over the horizon. The
expectations are that rule, applied by hand to small models, and closed forms of their runs.
"""

import math

import pytest

from napkin.engine.continuous.system import System
from napkin.engine.runtime import NumericalSettings, SimulationError
from tests.build import compiled, flow, library, q, run, stock, system

START = 1e8  # people
RATE = 1e6  # people an hour: the stock is empty at 100 h
HORIZON = 150


def drained(*members):
    """A stock of 1e8 people that drains into a tally at 1e6 people an hour until it is empty, at
    100 h, in a run of 150 h. Neither writes a size."""
    return system(
        stock('stock', START, size=None),
        stock('drained', 0, size=None, kind='tally'),
        *members,
        flow('drain', 'stock -> drained', q(RATE, 'people/h')),
        horizon=HORIZON,
    )


def sizes(source):
    """{quantity: its size} in the whole structure of run `a`, which keeps every part."""
    model = compiled(source)
    numbers, errors = model.numbers(model.run_values('a'))
    assert not errors
    rs = model.resolve_in(model.whole[model.runs['a']['starts']], numbers, 'whole a')
    found = System(rs, library(), NumericalSettings.parse(None))
    return dict(zip(found.state_ids, found.sizes))


def test_each_value_takes_the_size_of_its_rule():
    found = sizes(
        drained(
            # A tally that only its own rate fills, from outside: nothing but its unit sizes it.
            stock('clock', 0, 'h', size=None, minimum=None, kind='state', rate='1'),
            # A var with a size of its own, which the engine takes as written.
            stock('kept', 0, size=500),
        )
    )
    assert found['s.stock'] == START  # its start value
    assert found['s.drained'] == START  # the start value of the stock that its flow drains
    assert found['s.clock'] == 1  # one of its unit
    assert found['s.kept'] == 500


def draining(size):
    """A stock of 1e8 people drains into a tally at 2e6 people an hour times t / (t + 1 h), which the
    solver integrates: S(t) = 1e8 - 2e6 (t - ln(1 + t)) until it is empty, at about 54 h. `size` is
    the size that both write (None: the engine sizes them)."""
    return system(
        stock('stock', START, size=size),
        stock('drained', 0, size=size, kind='tally'),
        stock('clock', 0, 'h', size=None, minimum=0, kind='state', rate='1'),
        flow('drain', 'stock -> drained', f'{q(2 * RATE, "people/h")} * clock / (clock + 1 h)'),
        horizon=HORIZON,
    )


def test_a_large_stock_that_the_solver_drains_takes_its_own_size():
    """Sized by its start value, the stock follows its closed form to zero. With a size of one person
    (the size of a value with none before the engine sized values) its roundoff at zero exceeds its
    tolerance, and the run stops."""
    _, trajectory = run(draining(None))
    for t in (10.0, 30.0, 50.0, HORIZON):
        left = max(0.0, START - 2 * RATE * (t - math.log1p(t)))
        env = trajectory.env_at(t)
        assert env['s.stock'] == pytest.approx(left, rel=1e-9, abs=1e-9 * START)
        assert env['s.drained'] == pytest.approx(START - left, rel=1e-9)
    with pytest.raises(SimulationError, match='Material state-bound violation'):
        run(draining(1))
