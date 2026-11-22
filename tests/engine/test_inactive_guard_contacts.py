"""Only a reachable comparison can propose a numerical contact."""

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.program.record import Key
from tests.engine.test_threshold_transfer_placement import use_method
from tests.reference.from_program import run_of, value_at


@pytest.mark.parametrize('method', ['lines', 'component', 'sparse', 'moving_declared'])
@pytest.mark.parametrize(
    ('condition', 'expected'),
    [
        ('this.mode == OPEN and this.stock >= 1 L', [3]),
        ('this.mode != OPEN or this.stock <= 1 L', [0]),
        ('t >= 2 h and this.stock >= 1 L', [2]),
    ],
)
def test_a_held_deciding_operand_suppresses_the_unreachable_contact(method, condition, expected, monkeypatch):
    text = f"""scenario "A counter enabled by a switch"
    horizon 4 h
yard:
    mode: enum[OPEN, CLOSED] = CLOSED
    stock: L = 0
    count: number = 0
    flow fill: SOURCE -> this.stock
        request = 1 L/h
        capacity = 1 L/h
    enable = event():
        after 3 h:
            this.mode = OPEN
    watch = event():
        when {condition}:
            this.watch.start()
            reset when false
        after 0 h:
            this.count += 1
yard.enable.start()
"""
    model = use_method(text, method, monkeypatch, 'fill')
    machine = Run(Plan.of(model.program, model.configuration))
    moments = []
    next_moment = machine.next_moment

    def advance():
        result = next_moment()
        moments.append(result[0])
        assert len(moments) < 30, moments
        return result

    monkeypatch.setattr(machine, 'next_moment', advance)
    record = machine.run()
    assert record.failure is None
    assert [e.t for e in record.entries('fire', 'yard.watch.when[0]')] == expected
    if 'mode' in condition:
        assert all(abs(t - 1) > 1e-7 for t in moments), moments
    oracle, error = run_of(model.program, model.configuration)
    assert error is None and value_at(oracle, model.program, Key('yard', ('count',)), 4) == 1
