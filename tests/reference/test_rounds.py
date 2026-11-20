"""Rounds at one time (decision D5). Stages due together commit one after another, the
earliest-started occurrence first, and a later stage sees what an earlier one committed. Each
affected solve settles once per round. Reads in stages, also through a formula, give the values
of the previous settlement at the moment's time (PLAN, change 27)."""

from fractions import Fraction as F

import pytest

from tests.reference.errors import RunFailed
from tests.reference.model import (
    SINK,
    SOURCE,
    Model,
    N,
    add,
    after,
    calc,
    event,
    flow,
    formula,
    if_,
    leg,
    legs,
    lit,
    set_,
    solver,
    start,
    sub,
    this,
    trigger,
    value,
)
from tests.reference.run import Run
from tests.reference.test_solvers import staffing


def beans(two_stages):
    refill = event(
        'refill',
        triggers=[trigger(this.low_on_beans, [start(this.refill)], reset=('when', this.beans >= 30))],
    )
    if two_stages:
        extra = [
            event('use', steps=[after(1, [set_(this.beans, 8)])]),
            event('top', steps=[after(1, [add(this.beans, 4)])]),
        ]
    else:
        extra = [event('use', steps=[after(1, [set_(this.beans, 8), add(this.beans, 4)])])]
    m = Model()
    m.entity(
        'grinder',
        fields=[value('beans', 20), calc('low_on_beans', this.beans <= 10)],
        events=[refill, *extra],
    )
    m.setup = [start(getattr(N.grinder, e.name)) for e in extra]
    return Run(m, horizon=2).run()


def test_stages_of_one_round_commit_in_turn():
    """20 g; one stage sets 8 g and a later stage of the same round adds 4 g: 12 g. The trigger on
    `beans <= 10 g` reads the committed 12 g after the stages, and does not fire."""
    r = beans(two_stages=True)
    assert r.read(N.grinder.beans, 1) == 12
    assert r.times('fire') == []
    assert beans(two_stages=False).times('fire') == []


def test_a_stage_reads_its_own_earlier_writes():
    """Inside a stage `x = 2` then `y = x` gives 2."""
    m = Model()
    m.entity(
        'box',
        fields=[value('x', 0), value('y', 0)],
        events=[event('go', steps=[after(1, [set_(this.x, 2), set_(this.y, this.x)])])],
    )
    m.setup = [start(N.box.go)]
    assert Run(m, horizon=2).run().read(N.box.y, 2) == 2


def clinic(events, setup):
    m = Model()
    m.entity(
        'clinic',
        fields=[
            value('staff_hours', 100),
            calc('outreach_minimum', F(3, 10) * this.staff_hours),
            calc('care_now', this.staffing.care),
            value('seen', 0),
        ],
        events=events,
        solvers=[staffing()],
    )
    m.setup = [start(getattr(N.clinic, name)) for name in setup]
    return m


def solves_at(r, at):
    return sum(1 for e in r.trace if e[0] == 'solve' and e[1] == at)


def test_two_writes_one_solve_and_a_reaction():
    """Two writes in one round make one solve. A trigger that reacts to the result makes a second
    round, with a second solve, at the same time: 100 - 10 - 10 + 5 = 85 h, care 0.7 * 85."""
    cut = event('cut', steps=[after(1, [sub(this.staff_hours, 10)])])
    react = trigger(this.staffing.care <= 60, [start(this.top_up)], reset=('when', lit(False)))
    quiet = Run(
        clinic([cut, event('top_up', steps=[after(0, [add(this.staff_hours, 5)])])], ['cut', 'cut']),
        horizon=2,
    ).run()
    assert solves_at(quiet, 1) == 1
    assert quiet.read(N.clinic.staffing.care, 1) == 56
    top_up = event('top_up', steps=[after(0, [add(this.staff_hours, 5)])], triggers=[react])
    r = Run(clinic([cut, top_up], ['cut', 'cut']), horizon=2).run()
    assert solves_at(r, 1) == 2
    assert r.times('fire') == [1]
    assert (r.read(N.clinic.staff_hours, 1), r.read(N.clinic.staffing.care, 1)) == (85, F(119, 2))


@pytest.mark.parametrize(
    ('result', 'path'),
    [
        (N.clinic.staffing.care, 'clinic.staffing.care'),
        (N.clinic.hours, 'clinic.hours'),
    ],
)
def test_setup_cannot_read_a_declared_result_before_its_first_solve(result, path):
    m = clinic([], [])
    m.templates['clinic'].fields.append(value('hours', 100))
    m.templates['clinic'].solvers.append(solver('hours_solver', solve_for=[this.hours]))
    m.setup = [set_(N.clinic.seen, result)]
    r = Run(m, horizon=0)
    with pytest.raises(RunFailed) as failure:
        r.run()
    assert f'{path} is read before its first solve' in str(failure.value)


def test_a_delay_finishes_with_the_settled_result():
    """Staff hours fall to 80 h: a next delay of `this.staffing.care` uses 56 h."""
    go = event('go', steps=[after(1, [set_(this.staff_hours, 80)]), after(this.staffing.care, [])])
    r = Run(clinic([go], ['go']), horizon=100).run()
    assert r.times('done') == [57]


def staffing_read(read, later=False):
    """`cut` sets the staff hours to 80 at 1 h; `look` reads `read` at 1 h, in the same round or in
    the next round of that time."""
    steps = (
        [after(1, []), after(0, [set_(this.seen, read)])] if later else [after(1, [set_(this.seen, read)])]
    )
    cut = event('cut', steps=[after(1, [set_(this.staff_hours, 80)])])
    return Run(clinic([cut, event('look', steps=steps)], ['cut', 'look']), horizon=2)


def test_a_stage_reads_the_result_of_the_last_solve():
    assert staffing_read(this.staffing.care).run().read(N.clinic.seen) == 70


def test_a_formula_reads_the_result_of_the_last_solve():
    assert staffing_read(this.care_now).run().read(N.clinic.seen) == 70


def test_the_result_can_be_read_once_it_settles():
    """The same read in the next round of that time sees the settled 56 h."""
    assert staffing_read(this.staffing.care, later=True).run().read(N.clinic.seen) == 56


def test_a_read_after_a_write_in_the_same_stage_uses_the_last_solve():
    go = event('go', steps=[after(1, [set_(this.staff_hours, 80), set_(this.seen, this.staffing.care)])])
    assert Run(clinic([go], ['go']), horizon=2).run().read(N.clinic.seen) == 70


def test_a_stage_guard_reads_the_result_of_the_last_solve():
    cut = event('cut', steps=[after(1, [set_(this.staff_hours, 80)])])
    look = event('look', steps=[after(1, [set_(this.seen, 1)], this.staffing.care > 60)])
    assert Run(clinic([cut, look], ['cut', 'look']), horizon=2).run().read(N.clinic.seen) == 1


def tank(look_at, start_a_flow=False):
    m = Model()
    deliver = event('deliver', locals=[flow('pipe', this.water, SINK, request=2)], steps=[after(5, [])])
    opener = event('opener', steps=[after(look_at, [start(this.deliver)] if start_a_flow else [])])
    look = event('look', steps=[after(look_at, [set_(this.seen, this.water.outflow.actual_rate)])])
    m.entity('tank', fields=[value('water', 8, 0, 20), value('seen', -1)], events=[deliver, opener, look])
    m.entity('clinic', flows=[flow('delivery', N.tank.water, SINK, request=3)])
    m.setup = [start(N.tank.opener), start(N.tank.look)]
    return Run(m, horizon=4)


def test_a_flow_that_joins_in_the_round_is_counted_at_the_settlement():
    """The clinic takes 3 L/h. The pipe adds 2 L/h when the round settles."""
    assert tank(1).run().read(N.tank.seen) == 3
    r = tank(1, start_a_flow=True).run()
    assert r.read(N.tank.seen) == 3
    assert r.read(N.tank.water.outflow.actual_rate, 1) == 5


def test_a_store_that_meets_its_bound_keeps_its_rate_until_the_settlement():
    """8 L at 3 L/h empties at 8/3 h. The stage reads 3 L/h and the record gives zero."""
    at = F(8, 3)
    r = tank(at).run()
    assert r.read(N.tank.seen, at) == 3
    assert r.read(N.tank.water.outflow.actual_rate, at) == 0


def test_a_leg_reads_its_carried_rate_at_a_switch_of_its_request():
    """The tank fills from 2 L at 1 L/h. The leg asks 1 L/h while the tank holds at most 3 L.
    At 1 h the stage sees 1 L/h. The settlement gives the leg its new 2 L/h from 1 h."""
    m = Model()
    work = legs('work', leg('delivery', SOURCE, SINK, request=formula(if_(this.water <= 3, 1, 2))))
    look = event('look', steps=[after(1, [set_(this.seen, this.work.delivery.actual_rate)])])
    m.entity(
        'tank',
        fields=[value('water', 2, 0, 20), value('seen', 0)],
        flows=[flow('fill', SOURCE, this.water, request=1), work],
        events=[look],
    )
    m.setup = [start(N.tank.look)]
    r = Run(m, horizon=2).run()
    assert r.read(N.tank.seen, 1) == 1
    assert r.read(N.tank.work.delivery.actual_rate, 1) == 2
