"""Rounds at one time (decision D5). Stages due together commit one after another, the
earliest-started occurrence first, and a later stage sees what an earlier one committed. Each
affected solve settles once per round. A read of a computed result whose inputs changed before it
settles is an error, also through a formula: a stale answer is a wrong one."""

from fractions import Fraction as F

import pytest

from tests.reference.errors import RunFailed
from tests.reference.model import (
    SINK,
    Model,
    N,
    add,
    after,
    calc,
    event,
    flow,
    lit,
    set_,
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


def test_a_delay_finishes_with_the_settled_result():
    """Staff hours fall to 80 h: a next delay of `this.staffing.care` uses 56 h."""
    go = event('go', steps=[after(1, [set_(this.staff_hours, 80)]), after(this.staffing.care, [])])
    r = Run(clinic([go], ['go']), horizon=100).run()
    assert r.times('done') == [57]


def stale(read, later=False):
    """`cut` sets the staff hours to 80 at 1 h; `look` reads `read` at 1 h, in the same round or in
    the next round of that time."""
    steps = (
        [after(1, []), after(0, [set_(this.seen, read)])] if later else [after(1, [set_(this.seen, read)])]
    )
    cut = event('cut', steps=[after(1, [set_(this.staff_hours, 80)])])
    return Run(clinic([cut, event('look', steps=steps)], ['cut', 'look']), horizon=2)


def test_a_stale_solver_result_is_an_error():
    with pytest.raises(
        RunFailed, match=r'clinic\.staffing\.care is read before its solve settles: clinic\.staff_hours'
    ):
        stale(this.staffing.care).run()


def test_a_stale_result_read_through_a_formula_is_an_error():
    with pytest.raises(RunFailed, match=r'clinic\.staffing\.care is read before its solve settles'):
        stale(this.care_now).run()


def test_the_result_can_be_read_once_it_settles():
    """The same read in the next round of that time sees the settled 56 h."""
    assert stale(this.staffing.care, later=True).run().read(N.clinic.seen) == 56


def test_a_read_after_a_write_in_the_same_stage_is_an_error():
    go = event('go', steps=[after(1, [set_(this.staff_hours, 80), set_(this.seen, this.staffing.care)])])
    with pytest.raises(RunFailed, match='before its solve settles'):
        Run(clinic([go], ['go']), horizon=2).run()


def test_a_stage_guard_reads_no_stale_result():
    cut = event('cut', steps=[after(1, [set_(this.staff_hours, 80)])])
    look = event('look', steps=[after(1, [set_(this.seen, 1)], this.staffing.care > 60)])
    with pytest.raises(RunFailed, match='before its solve settles'):
        Run(clinic([cut, look], ['cut', 'look']), horizon=2).run()


def tank(look_at, start_a_flow=False):
    m = Model()
    deliver = event('deliver', locals=[flow('pipe', this.water, SINK, request=2)], steps=[after(5, [])])
    opener = event('opener', steps=[after(look_at, [start(this.deliver)] if start_a_flow else [])])
    look = event('look', steps=[after(look_at, [set_(this.seen, this.water.outflow.actual_rate)])])
    m.entity('tank', fields=[value('water', 8, 0, 20), value('seen', -1)], events=[deliver, opener, look])
    m.entity('clinic', flows=[flow('delivery', N.tank.water, SINK, request=3)])
    m.setup = [start(N.tank.opener), start(N.tank.look)]
    return Run(m, horizon=4)


def test_a_flow_that_joins_in_the_round_makes_the_rates_stale():
    """A stage of the round starts an occurrence whose flow joins the tank: a later stage of that
    round cannot read the tank's outflow before the network settles."""
    assert tank(1).run().read(N.tank.seen) == 3
    with pytest.raises(RunFailed, match=r'before its (first )?solve'):
        tank(1, start_a_flow=True).run()


def test_a_store_that_meets_its_bound_makes_its_rates_stale():
    """8 L at 3 L/h empties at 8/3 h. A stage due then cannot read the rate that the empty tank
    changes until the network settles."""
    with pytest.raises(RunFailed, match=r'tank\.water'):
        tank(F(8, 3)).run()
