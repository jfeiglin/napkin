"""Cross-set flow rates in a switch reader belong to its time and inventory."""

import pytest

from napkin.core import expr as nodes
from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text

SOURCE = """scenario "Meter"
    horizon 1 h
yard:
    meter: L = 1 L
    water: L = 0 L
    flow tap: SOURCE -> this.meter
        request = formula(this.meter / (1 h) + 1 L/h * (t / (1 h)))
    flow other: SOURCE -> this.meter
        request = formula(2 * this.meter / (1 h) + 3 L/h * (t / (1 h)))
    flow pipe: SOURCE -> this.water
        request = 2 L/h
        capacity = formula(0.25 L/h if this.tap.actual_rate > 2 L/h else 2 L/h)
"""


def installed():
    model = compile_text(SOURCE, {'L': {'volume': 1}, 'h': {'time': 1}})
    run = Run(Plan.of(model.program, model.configuration))
    run.prepare(now=False)
    run.moment.setup()
    (way,) = run.ways.instances
    assert isinstance(way, Sparse) and len(way.levels) == 2
    return way


@pytest.mark.parametrize('second', [(0.75, 1), (0.25, 5)], ids=['time-changes', 'inventory-changes'])
def test_delayed_sparse_readers_keep_their_own_producer_rates(second):
    way = installed()
    readers = []
    for time, volume in ((0.25, 1), second):
        state = way.y.copy()
        state[way.place['yard.meter']] = volume
        readers.append((time, volume, way._side(time, state)))
    # Root location and the numerical Jacobian can probe other times and inventories
    # between creating these readers and evaluating a comparison or its scale.
    different = way.y.copy()
    different[way.place['yard.meter']] = 7
    way.values(0.5, different)
    for time, volume, reader in reversed(readers):
        # Only tap is an explicit operand. A lazy read of the sibling rate gets the
        # same state as the eager operand, even after another reader has been used.
        assert reader(nodes.ref('yard.other.actual_rate')) == 2 * volume + 3 * time
        assert reader(nodes.ref('yard.tap.actual_rate')) == volume + time


def test_sparse_requests_for_a_jacobian_use_the_rates_of_the_supplied_state():
    way = installed()
    way.choose({})  # evaluate the authored capacity before the branch has been held
    state = way.y.copy()
    state[way.place['yard.meter']] = 3
    k = way.net.connections.index('yard.pipe')
    assert way.asked(0.25, state).capacity[k] == 0.25
    way.values(0.25, state)
    state[way.place['yard.meter']] = 1
    assert way.asked(0.25, state).capacity[k] == 2
