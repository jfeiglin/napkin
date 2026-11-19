"""Branches in a stage: `if` and `else` (decision D11), `switch` on a value, on a drawn categorical
value with guards on its cases, and on an actor's choice (decision D1). A person's choice pauses one
atomic stage, and resuming commits it once. The weights of a categorical are scaled by their sum."""

from fractions import Fraction as F

import pytest

from tests.reference.errors import RunFailed
from tests.reference.evaluate import Ev, Scope
from tests.reference.model import (
    Config,
    Model,
    N,
    add,
    after,
    branch,
    case,
    categorical,
    count,
    event,
    move,
    set_,
    start,
    sub,
    switch,
    t,
    this,
    uniform,
    value,
)
from tests.reference.run import Run
from tests.reference.test_rulings import keyed_uniform


def now(r, e):
    """A value of the live state where a run stopped or paused."""
    return Ev(r, r.view, Scope()).val(e)


def test_if_and_else_in_a_stage():
    """The stage runs the selected body, then continues after the branch."""

    def run(passes):
        stage = after(
            0,
            [
                branch(
                    this.passes_test,
                    [set_(this.operational, True), start(this.service_restored)],
                    [add(this.failed_tests, 1)],
                ),
                add(this.inspections, 1),
            ],
        )
        m = Model()
        fields = [
            value('passes_test', passes),
            value('operational', False),
            value('failed_tests', 0),
            value('inspections', 0),
        ]
        m.entity('pump', fields=fields, events=[event('inspect', steps=[stage]), event('service_restored')])
        m.setup = [start(N.pump.inspect)]
        r = Run(m, horizon=1).run()
        p = N.pump
        return (
            r.read(p.operational),
            r.read(p.failed_tests),
            r.read(p.inspections),
            r.read(count(p.service_restored.occurrences)),
        )

    assert run(True) == (True, 0, 1, 1)
    assert run(False) == (False, 1, 1, 0)


@pytest.mark.parametrize(
    'action, expected', [('REPAIR', (1, 0, 1)), ('RESUME', (0, 1, 1)), ('OTHER', (0, 0, 1))]
)
def test_switch_on_an_enum_value(action, expected):
    """The selector is read once and its case runs; with no matching case and no `else`, the stage
    continues directly."""
    stage = after(
        0,
        [
            switch(this.action, case('REPAIR', [start(this.repair)]), case('RESUME', [start(this.resume)])),
            add(this.inspections, 1),
        ],
    )
    m = Model()
    m.entity(
        'pump',
        fields=[value('action', action), value('inspections', 0)],
        events=[event('check', steps=[stage]), event('repair'), event('resume')],
    )
    m.setup = [start(N.pump.check)]
    r = Run(m, horizon=1).run()
    p = N.pump
    assert (
        r.read(count(p.repair.occurrences)),
        r.read(count(p.resume.occurrences)),
        r.read(p.inspections),
    ) == expected


def outcome(parts=1, mode='median', seed=0, guards=('parts', None), default=None):
    """`switch categorical(FIXED: 0.7, FAILED: 0.3).draw():` after 2 h, with optional guards."""

    def guard(g):
        return None if g is None else this.parts >= (1 if g == 'parts' else 5)

    selector = categorical(FIXED=F(7, 10), FAILED=F(3, 10)).draw()
    cases = [
        case('FIXED', [set_(this.operational, True)], when=guard(guards[0])),
        case('FAILED', [start(this.repair)], when=guard(guards[1])),
    ]
    m = Model()
    m.entity(
        'machine',
        fields=[value('parts', parts), value('operational', False), value('idle', False)],
        events=[
            event('test', steps=[after(2, [switch(selector, *cases, default=default)])]),
            event('repair'),
        ],
    )
    m.setup = [start(N.machine.test)]
    r = Run(m, Config(horizon=3, mode=mode, seed=seed)).run()
    fixed = r.read(N.machine.operational)
    if r.draws:  # exactly one case ran
        assert fixed != (r.read(count(N.machine.repair.occurrences)) == 1)
    return r, ('FIXED' if fixed else 'FAILED')


def test_a_median_run_takes_the_most_likely_outcome():
    """`categorical(FIXED: 0.7, FAILED: 0.3).draw()` in a median run: FIXED."""
    r, got = outcome()
    assert got == 'FIXED'
    assert [value for _, value in r.draws] == ['FIXED']


def test_a_sampled_run_draws_fixed_seven_times_in_ten():
    """Over 400 seeds the share of FIXED is 0.7 within 0.08 (more than three standard deviations)."""
    share = sum(outcome(mode='sampled', seed=s)[1] == 'FIXED' for s in range(400)) / 400
    assert abs(share - 0.7) < 0.08


def test_a_guard_makes_a_case_ineligible():
    """With no parts the FIXED case is not eligible: both modes take FAILED, the only eligible one."""
    assert outcome(parts=0)[1] == 'FAILED'
    assert {outcome(parts=0, mode='sampled', seed=s)[1] for s in range(20)} == {'FAILED'}


def test_no_eligible_case_runs_else_and_draws_nothing():
    r, _ = outcome(parts=0, guards=('parts', 'many'), default=[set_(this.idle, True)])
    assert r.read(N.machine.idle) is True
    assert r.draws == []


def test_a_skipped_branch_or_a_described_distribution_draws_nothing():
    stage = after(
        1, [branch(this.flag, [set_(this.x, this.speeds.draw())]), set_(this.mean, this.speeds.mean)]
    )
    m = Model()
    m.entity(
        'pump',
        fields=[value('flag', False), value('speeds', uniform(0, 10)), value('x', 0), value('mean', 0)],
        events=[event('go', steps=[stage])],
    )
    m.setup = [start(N.pump.go)]
    r = Run(m, Config(horizon=2, mode='sampled', seed=3)).run()
    assert (r.read(N.pump.x), r.read(N.pump.mean), r.draws) == (0, 5, [])


def dispatch(spares, controlled=False, mode='median', seed=0, forecast=None):
    """The dispatcher of `spec.md`, whose forecast always waits, unless another is given."""
    cases = [case('SEND', [start(this.send_pump)], when=this.spares >= 1), case('WAIT', [add(this.waits, 1)])]
    request = event(
        'request_pump', steps=[after(0, [switch(N.dispatcher.choose(N.dispatcher.forecast), *cases)])]
    )
    send = event('send_pump', steps=[after(0, [sub(this.spares, 1), add(this.sent, 1)])])
    if forecast is None:
        forecast = categorical(SEND=0, WAIT=1)
    m = Model()
    m.entity('dispatcher', fields=[value('forecast', forecast)], sees=[N.depot.spares])
    m.entity(
        'depot',
        fields=[value('spares', spares, 0), value('waits', 0), value('sent', 0)],
        events=[request, send],
    )
    m.setup = [start(N.depot.request_pump)]
    return Run(
        m, Config(horizon=1, mode=mode, seed=seed, controllers={'dispatcher'} if controlled else set())
    ).run()


def outcome_of(r):
    return r.read(N.depot.sent), r.read(N.depot.waits)


def test_an_automated_dispatcher_always_waits():
    """With no controller the value is the forecast's draw: WAIT, with or without a spare."""
    assert outcome_of(dispatch(1)) == (0, 1)
    assert outcome_of(dispatch(0)) == (0, 1)
    assert {outcome_of(dispatch(1, mode='sampled', seed=s)) for s in range(20)} == {(0, 1)}


def test_a_person_can_send_the_spare_pump():
    """A human can send the pump although its forecast probability is zero: eligibility and
    probability are independent. The prompt shows the alternatives and what the actor sees."""
    r = dispatch(1, controlled=True)
    assert r.paused['options'] == ['SEND', 'WAIT']
    assert r.paused['probabilities'] == {'SEND': 0, 'WAIT': 1}
    assert r.paused['sees'] == {'depot.spares': 1}
    r.resume('SEND')
    assert outcome_of(r) == (1, 0) and r.read(N.depot.spares) == 0


def test_with_no_spare_neither_the_person_nor_the_forecast_can_send():
    r = dispatch(0, controlled=True)
    assert r.paused['options'] == ['WAIT']
    with pytest.raises(RunFailed, match='SEND is not available'):
        r.resume('SEND')
    r = dispatch(0, controlled=True)
    r.resume('WAIT')
    assert outcome_of(r) == (0, 1)


def verdict(weights, mode='median', seed=0):
    """A stage at 1 h that sets `state` to a draw of `categorical(**weights)`, whose site is `verdict`."""
    selector = categorical(**weights).draw()
    m = Model()
    m.entity(
        'machine',
        fields=[value('state', 'UNTESTED')],
        events=[event('test', steps=[after(1, [set_(this.state, selector)])])],
    )
    m.sites[id(selector)] = 'verdict'
    m.setup = [start(N.machine.test)]
    return Run(m, Config(horizon=2, mode=mode, seed=seed)).run()


def test_weights_are_scaled_by_their_sum():
    """`categorical(FIXED: 1, FAILED: 3)` is FIXED with probability 1/4: a median run takes FAILED,
    a sampled run takes FIXED where the number of its key `verdict|machine.test#0` is below 1/4,
    and a person who decides is shown the probabilities 1/4 and 3/4."""
    weights = {'FIXED': 1, 'FAILED': 3}
    assert verdict(weights).read(N.machine.state) == 'FAILED'
    expected = [
        'FIXED' if keyed_uniform(seed, 'verdict|machine.test#0') < F(1, 4) else 'FAILED' for seed in range(20)
    ]
    assert set(expected) == {'FIXED', 'FAILED'}  # these seeds tell the two scalings apart
    assert [verdict(weights, 'sampled', seed).read(N.machine.state) for seed in range(20)] == expected
    r = dispatch(1, controlled=True, forecast=categorical(SEND=1, WAIT=3))
    assert r.paused['probabilities'] == {'SEND': F(1, 4), 'WAIT': F(3, 4)}


@pytest.mark.parametrize('mode', ['median', 'sampled'])
def test_weights_that_are_all_zero_give_no_draw(mode):
    """With every weight zero there is nothing to draw in either mode, as for eligible outcomes
    whose total is zero (D1); a person still picks any eligible outcome."""
    with pytest.raises(RunFailed, match='no eligible outcome has a probability to draw'):
        verdict({'FIXED': 0, 'FAILED': 0}, mode)
    with pytest.raises(RunFailed, match='no eligible outcome has a probability to draw'):
        dispatch(1, mode=mode, forecast=categorical(SEND=0, WAIT=0))
    r = dispatch(1, controlled=True, mode=mode, forecast=categorical(SEND=0, WAIT=0))
    assert r.paused['options'] == ['SEND', 'WAIT']
    r.resume('SEND')
    assert outcome_of(r) == (1, 0)


def shift(choices=None):
    """A stage that draws a value, queues a child, moves 3 L and then asks the crew to choose."""
    stage = after(
        1,
        [
            set_(N.drawn, this.speeds.draw()),
            start(this.child),
            move(3, this.a, this.b),
            switch(
                N.crew.choose(N.crew.plan), case('REPAIR', [set_(this.x, 1)]), case('WAIT', [set_(this.x, 2)])
            ),
        ],
    )
    m = Model()
    m.entity('crew', fields=[value('plan', categorical(REPAIR=F(1, 2), WAIT=F(1, 2)))])
    m.entity(
        'site',
        fields=[value('speeds', uniform(0, 10)), value('a', 8, 0, 20), value('b', 0, 0, 4), value('x', 0)],
        events=[
            event('child', steps=[after(5, [])]),
            event('work', locals=[value('drawn', 0)], steps=[stage]),
        ],
    )
    m.setup = [start(N.site.work)]
    config = Config(horizon=3, mode='sampled', seed=7, controllers={'crew'}, choices=choices or {})
    return Run(m, config).run()


def record(r):
    """The values, the moves, the draws, and the value drawn in the stage."""
    s = N.site
    moves = [e[4] for e in r.ledger if e[0] == 'move']
    values = (r.read(s.x), r.read(s.a), r.read(s.b), r.read(count(s.child.occurrences)))
    return values, moves, list(r.draws), r.read(s.work.occurrences.at(t).drawn)


def test_a_prompt_pauses_one_atomic_stage():
    """The run pauses with the draw and the queued start kept, and nothing of the stage visible."""
    r = shift()
    assert r.paused['time'] == 1
    assert r.paused['queued_starts'] == ['site.child']
    assert list(r.paused['kept_draws'].values()) == [v for _, v in r.draws] and len(r.draws) == 1
    assert (
        now(r, N.site.x),
        now(r, N.site.a),
        now(r, N.site.b),
        now(r, count(N.site.child.occurrences)),
    ) == (0, 8, 0, 0)


def test_resuming_commits_the_stage_once():
    """One draw, one child, one transfer: the same record as a replay with the answer."""
    r = shift()
    kept = list(r.draws)
    key = r.paused['key']
    r.resume('REPAIR')
    assert r.draws == kept
    replay = shift(choices={key: 'REPAIR'})
    assert record(r) == record(replay) == ((1, 5, 3, 1), [3], kept, kept[0][1])
    assert [d['value'] for d in r.decisions] == [d['value'] for d in replay.decisions] == ['REPAIR']
