"""A membership in a declared solver's constraint (spec, "Units, comparisons and layout": `x in [lo,
hi]` holds when `lo <= x <= hi`, and reversed bounds are an error; agent F's suggestion, the
readiness audit of `8b3a01a`, row 12).

A solver enforces `x in [lo, hi]` as the chain of its two relations, `lo <= x <= hi`. Where its ends
are reversed at a solve, the run stopped as an infeasible solve, a failure of another name. The
rule: the membership is evaluated as every evaluation of one is (`expr.membership`), so its ends
that the solve knows are checked first, and a reversed interval stops the run by the one name of the
failure (`ops.REVERSED`) at the time of the solve; ends in order are the two relations. On lines, on
a moving solver, after a stage that reverses the ends, and after an edit at a stop that reverses
them, resumed in place and in a fresh process.

By hand: a clinic asks 10 L/h of a tank, and its provider's solver maximizes the rate within
[lo, hi] = [1 L/h, 3 L/h]: 3 L/h, so the tank of 100 L holds 97 L at 1 h. With [2 L/h, 2 L/h] the
rate is exactly 2 L/h. A stage, or an edit, at 1 h makes [lo, hi] = [4 L/h, 2 L/h].
"""

from __future__ import annotations

import textwrap

import pytest

from napkin.core import ops
from napkin.engine.timeline import Plan, Run, read, run
from napkin.model.compile import compile_text
from napkin.program.build import (
    SINK,
    Builder,
    after,
    assign,
    constraint,
    event,
    flow,
    given,
    local,
    maximize,
    named,
    q,
    solve_for,
    solver,
    start,
    this,
    value,
    within,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_checkpoints import in_a_fresh_process

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def plant(low=1, high=3, swap=False, moving=False):
    """The clinic, its tank and the provider's solver over the interval [lo, hi] in L/h; `swap` adds
    a stage at 1 h that makes it [4 L/h, 2 L/h]; `moving` gives the solver a relation that reads
    the tank, so that its problem moves between moments (`MovingDeclared`)."""
    b = Builder(UNITS)
    tank = b.entity('tank', value('water', 'L', 100, lower=0))
    use = b.entity('clinic', flow('use', tank.water, SINK, request=q(10, 'L/h')))
    parts = [
        given('use', use.use),
        given('lo', this.lo),
        given('hi', this.hi),
        solve_for(local.use.actual_rate),
        constraint(within(local.use.actual_rate, local.lo, local.hi)),
        maximize(local.use.actual_rate),
    ]
    if moving:
        parts.insert(3, given('water', tank.water))
        parts.insert(-1, constraint(local.use.actual_rate <= local.water / q(1, 'h')))
    events = [event('swap', after(q(1, 'h'), assign(this.lo, q(4, 'L/h')), assign(this.hi, q(2, 'L/h'))))]
    events.append(event('tick', after(q(1, 'h'))))
    b.entity(
        'provider',
        value('lo', 'L/h', low),
        value('hi', 'L/h', high),
        *events,
        solver('share', *parts),
    )
    b.setup(*([start(named('provider').swap)] if swap else []), start(named('provider').tick))
    return b.finish()


def failure(record):
    """(the time of the failure, its message), or None for a run that finished."""
    return None if record.failure is None else (float(record.failure.t), record.failure.detail('message'))


@pytest.mark.parametrize('moving', [False, True], ids=['lines', 'moving'])
def test_a_membership_in_order_is_its_two_relations(moving):
    for low, high, rate in ((1, 3, 3), (2, 2, 2)):
        program = plant(low, high, moving=moving)
        record = run(program, Configuration(Request(2)))
        assert failure(record) is None
        found = read(record, program, ['clinic.use.actual_rate', 'tank.water'], [0.5, 1])
        assert found[0].values == (pytest.approx(rate), pytest.approx(rate))
        assert found[1].values[1] == pytest.approx(100 - rate)


@pytest.mark.parametrize('moving', [False, True], ids=['lines', 'moving'])
def test_a_membership_that_a_stage_reverses_stops_the_run_by_name_at_the_solve(moving):
    program = plant(swap=True, moving=moving)
    found = failure(run(program, Configuration(Request(2))))
    assert found is not None and found[0] == pytest.approx(1) and ops.REVERSED in found[1], found
    assert 'the solver provider.share' in found[1]


def test_an_edit_that_reverses_a_membership_stops_the_run_by_name_resumed_in_place_and_fresh(tmp_path):
    program = plant()
    made = Run(Plan.of(program, Configuration(Request(2))), (Breakpoint('provider.tick.step[0]'),))
    stopped = made.run()
    assert isinstance(stopped, Checkpoint) and stopped.stop.t == 1
    made.edit(Key('provider', ('lo',)), 4)
    edited = made.edit(Key('provider', ('hi',)), 2)
    for record in (made.resume(), *in_a_fresh_process(program, [edited], tmp_path)):
        found = failure(record)
        assert found is not None and found[0] == pytest.approx(1) and ops.REVERSED in found[1], found


MODEL = """
    scenario "Interval"
        horizon 2 h

    tank:
        water: L = 100 L in [0,]

    clinic:
        flow use: tank.water -> SINK
            request = 10 L/h

    provider:
        lo: L/h = 1 L/h
        hi: L/h = 3 L/h
        swap = event():
            after 1 h:
                this.lo = 4 L/h
                this.hi = 2 L/h
        share = solver:
            inputs:
                use = clinic.use
                lo = this.lo
                hi = this.hi
            solve_for:
                use.actual_rate
            constraints:
                use.actual_rate in [lo, hi]
            objective:
                maximize(use.actual_rate)

    provider.swap.start()
    """


def test_a_membership_of_a_model_reversed_at_a_solve_stops_the_run_by_name():
    model = compile_text(textwrap.dedent(MODEL), UNITS)
    found = failure(run(model.program, model.configuration))
    assert found is not None and found[0] == pytest.approx(1) and ops.REVERSED in found[1], found
