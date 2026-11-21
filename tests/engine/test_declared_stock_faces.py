"""The declared solver decides which stock faces its allocated rates hold or release."""

from collections import Counter
from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.declared import DeclaredWay
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, dumps, loads
from napkin.program.config import Configuration, Request
from tests.engine.test_random_solvers import program
from tests.reference.from_program import run_of, value_at


@pytest.fixture(params=[False, True], ids=['held', 'moving'])
def moving(request, monkeypatch):
    connect = Plan.connect

    def use_declared(plan, *args, **kwargs):
        groups = connect(plan, *args, **kwargs)
        return [replace(group, moves=request.param) if group.way == 'declared' else group for group in groups]

    monkeypatch.setattr(Plan, 'connect', use_declared)
    return request.param


def test_a_declared_face_with_balanced_through_flow_keeps_its_stock(moving):
    # Immediately after 3 h, 31/24 + 1 L/h enters t0 and 55/24 leaves it. Summing
    # the rounded rates gives a positive drift. Only t1 leaves its trajectory to hit zero.
    model, keys = program(875)
    config = Configuration(Request(6))
    oracle, failed = run_of(model, config)
    assert failed is None
    machine = Run(Plan.of(model, config), (Breakpoint('t2.change1.step[0]'),))
    stopped = machine.run()
    restored = Run.restored(Plan.of(model, config), loads(dumps(stopped)))
    times = [Fraction(3), Fraction(14471, 4550), Fraction(6)]
    for run in (machine, restored):
        record = run.resume()
        assert record.failure is None
        assert run.stock_balance('t0.water', 6) == 0
        residue = run.stock_balance('t1.water', 6)
        if moving:
            # Taking the last fraction through the capped outlet would exceed its
            # integrated capacity. The accepted stock stays in its own comparison band.
            (placement,) = [entry for entry in record.entries('settle') if entry.detail('placements')]
            assert 't1.f0.capacity' in placement.detail('reason')
            (_, observed, target) = next(p for p in placement.detail('placements') if p[0] == 't1.water')
            assert target == 0 and 0 < float(residue) == observed <= run.comparison_band(
                't1.water', observed, 0
            )
        else:
            assert residue == 0
        for key, row in zip(keys, read(record, model, keys, list(map(float, times))), strict=True):
            # A located rate can change on either side of its rounded crossing clock.
            for i in (0, 2) if 'actual_rate' in key.steps else range(3):
                expected = float(value_at(oracle, model, key, times[i]))
                assert row.values[i] == pytest.approx(expected, abs=1e-10)


def test_a_genuine_inward_allocation_leaves_the_face_again_after_a_reset(moving, monkeypatch):
    model = compile_text(
        """scenario "Repeat a release from an empty store"
    horizon 2 h
yard:
    water: L = 0 L in [0,]
    mark = 0
    flow fill: SOURCE -> this.water
        request = formula(1.2 L/h + this.mark * (0 L/h))
    flow drain: this.water -> SINK
        request = 0.2 L/h
    change = event():
        after 1 h:
            this.water = 0 L
            this.mark = 1
        after 0.5 h:
            this.mark = 2
owner:
    share = solver:
        inputs:
            pipe = yard.fill
        solve_for:
            pipe.actual_rate
yard.change.start()
""",
        {'L': {'volume': 1}, 'h': {'time': 1}},
    )
    solved = DeclaredWay._solved
    calls = Counter()

    def count(self, t, *args):
        calls[t] += 1
        return solved(self, t, *args)

    monkeypatch.setattr(DeclaredWay, '_solved', count)
    run = Run(Plan.of(model.program, model.configuration))
    record = run.run()
    assert record.failure is None
    assert read(record, model.program, ['yard.water'], [0.5, 1, 1.5, 2])[0].values == pytest.approx(
        (0.5, 0, 0.5, 1)
    )
    assert calls[0] and calls[1.5] == 0
    if not moving:
        assert calls[1] == 0  # the held solver can reuse its released problem at the empty face


def test_an_unresolved_numerical_departure_is_refined_and_reported_once(moving, monkeypatch):
    source = """scenario "A ranked answer on the edge of physical departure"
    horizon 1 h
yard:
    a: L = 0 L in [0, 5 L]
    flow fill: SOURCE -> this.a
        request = 0.75 L/h
    flow drain: this.a -> SINK
        request = 0.75 L/h
    owner = solver:
        inputs:
            inlet = this.fill
            outlet = this.drain
        solve_for:
            inlet.actual_rate
            outlet.actual_rate
        constraints:
            3 * inlet.actual_rate <= 1.5000000000015 L/h
            7 * outlet.actual_rate <= 3.4999999999965 L/h
"""
    checked = []
    refine = DeclaredWay._refined_answer

    def measured(self, arrays, requests):
        rates = refine(self, arrays, requests)
        checked.append(tuple(rates))
        return rates

    monkeypatch.setattr(DeclaredWay, '_refined_answer', measured)
    model = compile_text(source, {'L': {'volume': 1}, 'h': {'time': 1}})
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    assert record.failure is None, record.failure
    assert checked
    way = machine.ways.instance_of('yard.a')
    assert way.resting_value('yard.a', 1) is not None
    assert machine.stock_balance('yard.a', 1) == (
        way.transferred('yard.fill', 1) - way.transferred('yard.drain', 1)
    )
    ((entry, detail),) = record.near_ties()
    assert (entry.t, entry.kind, entry.part) == (0, 'settle', 'yard.a')
    assert detail[:2] == ('yard.a', 'stock departure')
    net, gross, threshold, uncertainty = entry.detail('departure')
    assert gross == pytest.approx(1, abs=1e-12)
    assert threshold == 1e-12 * gross
    assert 0 < abs(net - threshold) <= uncertainty
    assert machine.recorder.record(record.end).near_ties() == record.near_ties()
