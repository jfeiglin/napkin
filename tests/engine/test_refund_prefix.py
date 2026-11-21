"""A refund can spend both halves of a transfer into a large physical stock."""

import pytest

from napkin.engine import read
from napkin.engine.report import report
from napkin.engine.timeline import Plan, Run, plan
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, dumps, loads

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


@pytest.mark.parametrize('method', [ComponentWay, Sparse])
@pytest.mark.parametrize('pause', ['none', 'empty', 'serialized'])
def test_refund_from_large_stock_uses_the_accepted_transfer(method, pause, monkeypatch):
    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    source = """scenario "Refund"
    horizon 1 h
plant:
    donor: L = 1 L in [0,]
    pool: L = 10000000 L in [0,]
    bulk: L = 0 L in [0,]
    paid: L = 0 L in [0,]
    pace = formula(0.1 L/h * (t / (1 h)))
    flow delivery: this.donor -> this.pool
        request = formula(this.pace)
    pay = event():
        after 1 h:
            this.delivery.request = 0 L/h
            move 10000000 L from this.pool to this.bulk
        after 0 h:
            move (1 L - this.donor) from this.pool to this.paid
"""
    if pause != 'none':
        source += '    idle = event():\n        after 0.5 h\nplant.idle.start()\n'
    model = compile_text(source + 'plant.pay.start()\n', UNITS)
    stops = (Breakpoint('plant.idle.step[0]'),) if pause == 'serialized' else ()
    machine = Run(Plan.of(model.program, model.configuration), stops)
    # A rate assignment at the horizon can replace the method that integrated the ramp.
    ramp_methods = []
    finish = machine.finish_arrival

    def finish_ramp():
        if machine.arriving:
            ramp_methods.append(type(machine.ways.instance_of('plant.delivery')))
        return finish()

    machine.finish_arrival = finish_ramp
    record = machine.run()
    if stops:
        # Inspect the incoming half-hour cut in both query orders while the live
        # machine is stopped. The saved cursor and its physical prefix must survive.
        checkpoint = dumps(record)
        way = machine.ways.instance_of('plant.delivery')
        prefix = way.transferred('plant.delivery', 0.5)
        assert float(prefix) == pytest.approx(0.0125, abs=1e-10, rel=0)
        for paths in (['plant.pool', 'plant.donor'], ['plant.donor', 'plant.pool']):
            inspected = report(
                record.record, model.program, model.configuration, paths, [0.5], table=model.table
            )
            assert dict((row.path, row.values) for row in inspected.values)['plant.donor'] == pytest.approx(
                (0.9875,), abs=1e-10, rel=0
            )
            assert dumps(record) == checkpoint
            assert way.transferred('plant.delivery', 0.5) == prefix
        machine = Run.restored(Plan.of(model.program, model.configuration), loads(checkpoint))
        record = machine.resume()
    assert method in ramp_methods
    assert record.failure is None, record.failure
    donor, pool, paid = read(record, model.program, ['plant.donor', 'plant.pool', 'plant.paid'], [0.5, 1])
    assert 1 - donor.values[0] == pytest.approx(0.0125, abs=1e-10, rel=0)
    assert donor.values[0] - donor.values[1] == pytest.approx(0.0375, abs=1e-10, rel=0)
    assert (donor.values[1], pool.values[1], paid.values[1]) == pytest.approx(
        (0.95, 0, 0.05), abs=1e-10, rel=0
    )
