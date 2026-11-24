"""The first frozen write is selected by gross direction across joined and departed pipes."""

import math

import pytest

from napkin.engine.timeline import Plan, Run, plan
from napkin.engine.timeline.component import ComponentWay
from napkin.engine.timeline.lines import Lines
from napkin.engine.timeline.sparse import Sparse
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, dumps, loads
from tests.engine.resume_parity import assert_resume_parity

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


@pytest.mark.parametrize('kind', ['held', 'component', 'sparse'])
def test_frozen_failure_tracks_each_direction_after_a_join_and_departure(kind, monkeypatch):
    # An initial pulse spends 0.025 L of a retired occurrence's incoming allowance.
    # Its pipe then departs and a pair of opposing legs join. Net transport is zero,
    # but the incoming direction uses its remaining 0.075 L before the outgoing direction.
    monkeypatch.setattr(plan, 'LIMIT', 0 if kind == 'sparse' else 150)
    moving = kind != 'held'
    failure_time = 1.5 + (math.sqrt(2.5) - 1 if moving else 0.75)
    request = 'formula(0.1 L/h * (1 + (t - 1.5 h) / (1 h)))' if moving else '0.1 L/h'
    model = compile_text(
        f"""scenario "Frozen gross amount"
    horizon 3 h
plant:
    water: L = 10 L in [0,]
    retire = event():
        batch: L = 0 L in [0,] scale 1000000000 L
        after 1 h
    prime = event():
        job = this.retire.occurrences.at(t)
        flow pulse: this.water -> job.batch
            request = 0 L/h
        after 1 h:
            pulse.request = 0.05 L/h
        after 0.5 h
    relay = event():
        job = this.retire.occurrences.at(t)
        flow there: this.water -> job.batch
            request = {request}
        flow back: job.batch -> this.water
            request = {request}
        after 2 h
    open = event():
        after 1.5 h:
            this.relay.start()
    pause = event():
        after {failure_time - 1e-5} h
plant.retire.start()
plant.prime.start()
plant.open.start()
plant.pause.start()
""",
        UNITS,
    )
    machine = Run(Plan.of(model.program, model.configuration))
    direct = machine.run()
    assert isinstance(
        machine.ways.instance_of('plant.relay#0.there'),
        {'held': Lines, 'component': ComponentWay, 'sparse': Sparse}[kind],
    )
    assert direct.failure is not None
    assert direct.failure.t == pytest.approx(failure_time, abs=5e-9, rel=0)
    details = ' '.join(str(item) for item in direct.failure.details)
    assert 'plant.relay#0.there' in details and 'into plant.retire#0.batch' in details
    stopped = Run(Plan.of(model.program, model.configuration), (Breakpoint('plant.pause.step[0]'),))
    checkpoint = stopped.run()
    restored = Run.restored(Plan.of(model.program, model.configuration), loads(dumps(checkpoint)))
    assert_resume_parity(model.program, model.configuration, direct, restored.resume())
    assert_resume_parity(model.program, model.configuration, direct, stopped.resume())
