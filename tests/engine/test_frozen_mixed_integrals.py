"""A curved neighbor cannot spend any of the exact frozen leg's allowance."""

import math
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, plan, read
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.declared import DeclaredWay, MovingDeclared
from napkin.engine.timeline.lines import Lines
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text
from napkin.program.record import Key

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}
ALLOWANCE = Fraction(1, 10)
MEANS = (repr(math.nextafter(0.1, 0)), '0.1', repr(math.nextafter(0.1, math.inf)))


@pytest.mark.parametrize('method', [Lines, DeclaredWay, ComponentWay, Sparse, MovingDeclared])
@pytest.mark.parametrize('mean', MEANS, ids=['just-below', 'equal', 'just-above'])
def test_frozen_limit_uses_only_the_accepted_amount_of_its_physical_leg(method, mean, monkeypatch):
    # At t=1 h the occurrence freezes and its one incoming leg opens. The buffer
    # remains interior, so the leg carries its full local request. The source
    # filling that buffer is *in the same calculation* and never touches batch.
    # In moving cases its reciprocal rate has no polynomial clock primitive.
    # Held controls use the equivalent fixed-input reciprocal and a constant leak.
    held = method in (Lines, DeclaredWay)
    clock = 'this.duration' if held else 't'
    leak = f'{mean} L/h' if held else f'formula(2 * {mean} L/h * (t - 1 h) / (1 h))'
    source = f"""scenario "A physical leg at a frozen threshold"
    horizon 2 h
plant:
    input duration: h = 1 h
    water: L = 10 L in [0,]
    flow supply: SOURCE -> this.water
        request = formula(1 L/h / (1 + {clock} / (1 h)))
    retire = event():
        batch: L = 0 L in [0,] scale 1000000000 L
        after 1 h
    watch = event():
        job = this.retire.occurrences.at(t)
        flow leak: this.water -> job.batch
            request = 0 L/h
        after 1 h:
            leak.request = {leak}
        after 2 h
"""
    if method in (DeclaredWay, MovingDeclared):
        # The solver determines supply. It leaves leak to local allocation.
        source += """provider:
    share = solver:
        inputs:
            supply = plant.supply
        solve_for:
            supply.actual_rate
"""
    source += 'plant.retire.start()\nplant.watch.start()\n'
    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    model = compile_text(source, UNITS)
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    connection = 'plant.watch#0.leak'
    way = run.ways.instance_of(connection)
    assert type(way) is method
    assert run.ways.instance_of('plant.supply') is way

    gross = Fraction(mean)  # held rectangle, or the ramp's triangular area over one hour
    if gross <= ALLOWANCE:
        assert record.failure is None
        (batch,) = read(record, model.program, [Key('plant.retire#0', ('batch',))], [1, 2])
        assert batch.values == pytest.approx((0, float(gross)), abs=5e-10, rel=0)
    else:
        duration = float(ALLOWANCE / gross)
        threshold = 1 + (duration if held else math.sqrt(duration))
        assert record.failure is not None
        assert record.failure.t == pytest.approx(threshold, abs=5e-9, rel=0)
        message = record.failure.detail('message')
        assert f'the flow {connection} carries' in message
        assert 'into plant.retire#0.batch' in message
        assert 'belongs to the finished occurrence plant.retire#0, which is frozen' in message
