"""A way decides where a step starts once for each start state, and the step pays for that decision."""

import numpy as np
import pytest

from napkin.engine.continuous import integrate
from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.component import Component, ComponentWay
from napkin.engine.timeline.sparse import Sparse
from tests.engine.test_threshold_transfer_placement import use_method

SOURCE = """scenario "A switch read again after a move"
    horizon 2 h
yard:
    stock: L = 1 L in [0,]
    drained: L = 0 L
    flow drain: this.stock -> this.drained
        request = formula(1 L/h if this.stock > 0.5 L else 0.25 L/h)
    take = event():
        after 0.25 h:
            move 0.1 L from this.stock to this.drained
yard.take.start()
"""


def _run(method, monkeypatch, *, again):
    model = use_method(SOURCE, method, monkeypatch, 'drain')
    calls, ways = [], []
    far_sides = integrate.far_sides

    def counted(surfaces, layers, t, y, *args, **kwargs):
        calls.append((float(t), np.asarray(y, dtype=float).tobytes(), tuple(map(str, surfaces))))
        return far_sides(surfaces, layers, t, y, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(integrate, 'far_sides', counted)
        for kind in (Sparse, ComponentWay):
            built = kind.__init__

            def remember(way, *args, built=built, **kwargs):
                built(way, *args, **kwargs)
                ways.append(way)

            patch.setattr(kind, '__init__', remember)
        if again:
            # The rule before: the first step decides again, and pays for its own decision.
            start, settle = Sparse._start, Component.next

            def decide(way):
                way._undecide()
                return start(way)

            def segment(component, horizon):
                component.decided, component.decision_cost = False, 0
                return settle(component, horizon)

            patch.setattr(Sparse, '_start', decide)
            patch.setattr(Component, 'next', segment)
        record = Run(Plan.of(model.program, model.configuration)).run()
    spent = sum(
        way.evaluations if isinstance(way, Sparse) else way.component.state.evaluations for way in ways
    )
    return record, calls, spent


@pytest.mark.parametrize('method', ['component', 'sparse'])
def test_a_step_pays_once_for_the_start_that_an_observation_decided(method, monkeypatch):
    record, calls, spent = _run(method, monkeypatch, again=False)
    before, repeated, paid = _run(method, monkeypatch, again=True)
    assert record.failure is None and before.failure is None
    assert len(set(calls)) == len(calls) < len(repeated)
    assert set(calls) == set(repeated)
    assert spent == paid
