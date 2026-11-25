"""A budget poll cannot change the physical solution or the record of a run that fits."""

from fractions import Fraction

import pytest

from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.record import Recorder
from napkin.model.compile import compile_text
from napkin.program.record import Key


@pytest.mark.parametrize('internal_only', [True, False], ids=['internal-poll', 'all-polls'])
def test_record_is_independent_of_budget_polls(monkeypatch, internal_only):
    model = compile_text(
        """scenario "Independent budget observation"
    horizon 2 h
tank:
    water: L = 0 L in [0 L, 1.25 L]
    flow fill: SOURCE -> this.water
        request = 1 L/h
    reading = formula(exp(this.water / (1 L)))
    clock = formula(exp(t / (1 h)))
    total = formula(this.reading ** 2 + this.clock)
    tick = event():
        after 0.8 h
tank.tick.start()
""",
        {'h': {'time': 1}, 'L': {'volume': 1}},
    )

    def simulate():
        live = Run(Plan.of(model.program, model.configuration))
        record = live.run()
        assert record.failure is None
        # The 1 L/h inflow stops at the 1.25 L bound. Read the physical balance
        # and the cumulative transfer directly from the book for this stock.
        assert live.stock_state.point('tank.water', record.end) == (Fraction(5, 4), Fraction(5, 4))
        return record

    expected = simulate()
    skipped = []
    check = Recorder.check_budget

    def skip(recorder, end, **options):
        # The stock reaches its bound on an internal step. The event has its
        # own moment at 0.8 h and does not change the flow.
        if internal_only and end != 1.25:
            return check(recorder, end, **options)
        skipped.append(end)

    monkeypatch.setattr(Recorder, 'check_budget', skip)
    actual = simulate()
    assert 1.25 in skipped
    if not internal_only:
        assert 0.8 in skipped
    assert actual.trace == expected.trace
    assert actual.history(Key('tank', ('total',))) == expected.history(Key('tank', ('total',)))
    assert actual == expected
