"""A later producer or definition cannot change a closed interval's stored representation."""

from dataclasses import replace

from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.record import requested
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.record import Key

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


def recorded(model, names, *, budget=None, horizon=None, stop=()):
    request = model.configuration.request
    keys = tuple(Key('yard', (name,)) for name in names)
    request = replace(
        request,
        everything=False,
        keys=keys,
        horizon=request.horizon if horizon is None else horizon,
        pieces=request.pieces if budget is None else budget,
    )
    run = Run(Plan.of(model.program, replace(model.configuration, request=request)), stop)
    return run, run.run()


def test_a_later_curved_member_keeps_the_closed_sum_of_straight_lines():
    model = compile_text(
        """scenario "A sum changes representation"
    horizon 4 h
Tank:
    water: L = 2 L
    flow fill: SOURCE -> this.water
        request = 1 L/h
    extra = event():
        flow pump: SOURCE -> this.water
            request = formula(t * 1 L/h/h)
        after 3 h
one: Tank
two: Tank
yard:
    total = formula(sum(Tank.instances.water))
    marks = 0
    tick = event():
        after 0.5 h:
            this.marks += 1
        after 0.5 h:
            this.marks += 1
        after 0.5 h:
            this.marks += 1
        after 0.5 h:
            one.extra.start()
yard.tick.start()
""",
        UNITS,
    )
    names = ('total', 'marks')
    _, whole = recorded(model, names)
    assert whole.failure is None
    key = Key('yard', ('total',))
    total = whole.history(key)
    assert [(p.t, p.value, p.rate, p.curve) for p in total.pieces if p.t < 2] == [(0, 4, 2, None)]
    assert any(p.t >= 2 and p.curve is not None for p in total.pieces)
    for budget in (3, 4, 5):
        _, limited = recorded(model, names, budget=budget)
        assert limited == requested(whole.within(budget), model.program)

    _, unlimited = recorded(model, ('total',))
    run, checkpoint = recorded(model, ('total',), budget=1, stop=(Breakpoint('yard.tick.step[2]'),))
    assert isinstance(checkpoint, Checkpoint) and checkpoint.stop.t == 1.5
    assert checkpoint.record.history(key).pieces == total.pieces[:1]
    assert run.resume() == requested(unlimited.within(1), model.program)


def test_a_later_time_definition_keeps_the_early_alias_and_its_readers():
    model = compile_text(
        """scenario "An alias changes definition"
    horizon 4 h
yard:
    level: L = 2 L
    flow fill: SOURCE -> this.level
        request = 1 L/h
    alias: formula(L) = formula(this.level)
    copy: formula(L) = formula(this.alias)
    tick = event():
        after 1 h
        after 1 h:
            this.alias = formula((t / (1 h)) ** 2 * 1 L)
yard.tick.start()
""",
        UNITS,
    )
    names = ('alias', 'copy')
    _, whole = recorded(model, names)
    _, before = recorded(model, names, horizon=1)
    assert whole.failure is None and before.failure is None
    for name in names:
        key = Key('yard', (name,))
        history = whole.history(key)
        assert [p for p in history.pieces if p.t < 2] == list(before.history(key).pieces)
        assert [(p.rate, p.curve) for p in history.pieces if p.t == 0] == [(0, None), (1, None)]
        assert abs(history.at(3) - 9) < 1e-9
    for budget in (4, 5):
        _, limited = recorded(model, names, budget=budget)
        assert limited == requested(whole.within(budget), model.program)
