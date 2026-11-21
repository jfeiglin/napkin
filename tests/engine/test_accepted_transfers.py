"""Each stepper reports gross physical transfers only through the accepted instant."""

from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, plan
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}
PAUSE = """    pause = event():
        after 0.5 h
plant.pause.start()
"""


@pytest.mark.parametrize('method', [ComponentWay, Sparse])
@pytest.mark.parametrize('cycle', [False, True], ids=['named-ramp', 'balanced-cycle'])
def test_event_cut_preserves_each_accepted_leg(method, cycle, monkeypatch):
    monkeypatch.setattr(plan, 'LIMIT', 0 if method is Sparse else 150)
    source = """plant:
    donor: L = 10 L
    pool: L = 4000000 L
    pace = formula(0.1 L/h * t / (1 h))
    flow delivery: this.donor -> this.pool
        request = formula(this.pace)
"""
    names = ['plant.delivery']
    if cycle:
        # Net change at either stock is zero. Each directed physical leg carries the ramp.
        source += """    flow returning: this.pool -> this.donor
        request = formula(this.pace)
"""
        names.append('plant.returning')
    program = compile_text(source + PAUSE, UNITS).program
    machine = Run(Plan.of(program, Configuration(Request(1))))
    finish = machine.finish_arrival
    observed = {}

    def observe():
        if machine.arriving and machine.now in (0.5, 1):
            way = machine.ways.instance_of(names[0])
            assert isinstance(way, method)
            time = machine.now
            end = way.pending[1] if method is Sparse else way.pending.end
            before = [way.transferred(name, time) for name in names]
            finish()
            after = [way.transferred(name, time) for name in names]
            assert before == after
            observed[time] = end, after
        else:
            finish()

    machine.finish_arrival = observe
    record = machine.run()
    assert record.failure is None
    assert observed[0.5][0] > 0.5
    for t, volume in ((0.5, Fraction(1, 80)), (1, Fraction(1, 20))):
        if cycle:
            assert observed[t][1] == pytest.approx([float(volume)] * 2, abs=1e-12, rel=0)
        else:
            assert observed[t][1] == [volume]
