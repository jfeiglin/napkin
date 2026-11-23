"""One event can adjust the ceiling of a running occurrence, even when it began unrestricted."""

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text


@pytest.mark.parametrize('reference', ['job', 'this.drain.occurrences.at(t)'])
@pytest.mark.parametrize('target', ['pipe', 'stock.outflow'])
@pytest.mark.parametrize('initial_cap', [False, True], ids=['initially-unbounded', 'explicit-ceiling'])
def test_set_capacity_of_another_running_occurrence(reference, target, initial_cap):
    endpoint = '            outflow.capacity = 5 L/h\n' if initial_cap and target == 'stock.outflow' else ''
    pipe = '            capacity = 5 L/h\n' if initial_cap and target == 'pipe' else ''
    source = f"""scenario "Adjust a running discharge"
    horizon 2 h
tank:
    drain = event():
        stock: L = 10 L in [0 L,]
{endpoint}        flow pipe: stock -> SINK
            request = 2 L/h
{pipe}        after 4 h
    tune = event():
        job = this.drain.occurrences.at(t)
        after 1 h:
            {reference}.{target}.capacity = 0.5 L/h
        after 3 h
tank.drain.start()
tank.tune.start()
"""
    compiled = compile_text(source, {'h': {'time': 1}, 'L': {'volume': 1}})
    record = run(compiled.program, compiled.configuration)
    assert record.failure is None, record.failure
    balance, rate, capacity = read(
        record,
        compiled.program,
        ['tank.drain#0.stock', 'tank.drain#0.pipe.actual_rate', f'tank.drain#0.{target}.capacity'],
        [0, 1, 2],
    )
    assert balance.values == (10, 8, 7.5)
    assert rate.values == (2, 0.5, 0.5)
    assert capacity.values[1:] == (0.5, 0.5)
