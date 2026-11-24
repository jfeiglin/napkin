"""An independently watched inventory reaches its threshold where a clock switches a pipe."""

from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.record import Key
from tests.engine.resume_parity import assert_resume_parity
from tests.engine.test_threshold_transfer_placement import use_method
from tests.reference.from_program import run_of, value_at


@pytest.mark.parametrize(
    'method,route',
    [
        ('component', False),
        ('sparse', False),
        ('moving_declared', False),
        ('sparse', True),
        ('moving_declared', True),
    ],
)
@pytest.mark.parametrize('time', ['0.9999999999', '1.0000000001'])
def test_a_clock_switch_and_a_watch_place_the_tank_using_the_incoming_rates(method, route, time, monkeypatch):
    ends = '<->' if route else '->'
    later = '-0.3' if route else '0.2'
    source = f"""scenario "A clock switch and a tank watch"
    horizon 1.1 h
yard:
    tank: L = 0 L
    first: L = 8 L
    second: L = 7 L
    flow link: this.first {ends} this.tank
        request = formula(2 L/h if t < 1 h else {later} L/h)
    flow steady: this.second -> this.tank
        request = 1 L/h
    watch = event():
        when this.tank >= 3 L:
            this.watch.start()
        after 0 h
    clock = event():
        after {time} h
yard.clock.start()
"""
    model = use_method(source, method, monkeypatch, 'steady')
    oracle, error = run_of(model.program, model.configuration)
    assert error is None, error
    run = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.clock.step[0]'),))
    checkpoint = run.run()
    assert isinstance(checkpoint, Checkpoint)
    way = run.ways.instance_of('yard.link')
    assert (
        type(way).__name__
        == {'component': 'ComponentWay', 'sparse': 'Sparse', 'moving_declared': 'MovingDeclared'}[method]
    )
    for name, expected in [('tank', 3), ('first', 6), ('second', 6)]:
        assert value_at(oracle, model.program, Key('yard', (name,)), Fraction(time)) == expected
        assert float(run.stock_balance('yard.' + name, run.now)) == pytest.approx(expected, rel=0, abs=1e-13)
    assert float(way.transferred('yard.link.forward' if route else 'yard.link', run.now)) == pytest.approx(
        2, abs=1e-13, rel=0
    )
    assert float(way.transferred('yard.steady', run.now)) == pytest.approx(1, rel=0, abs=1e-13)
    if route:
        assert way.transferred('yard.link.backward', run.now) == 0
    again = Run.restored(Plan.of(model.program, model.configuration), loads(dumps(checkpoint)))
    assert_resume_parity(model.program, model.configuration, run.resume(), again.resume())
