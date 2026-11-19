"""The pause of one atomic stage (spec, "A prompt pauses one atomic stage"; R-A2-14; `chance.py`).

A player's choice that no pick answers stops the run inside its stage, before the stage commits:
what the moment committed before the stage is kept, nothing of the stage is visible, and the stages
after it in its round do not run. A run with the pick replays the stage and commits it once, and
`Run.resume` goes on in place to the same record: a prompt never makes a second draw, child or
transfer. The expected values are worked by hand from these rules.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run, paused
from napkin.program.build import (
    SOURCE,
    Builder,
    add,
    after,
    assign,
    case,
    categorical,
    choose,
    dist_of,
    draw,
    event,
    flow,
    move,
    named,
    q,
    sees,
    start,
    switch,
    t,
    this,
    uniform,
    value,
    when,
)
from napkin.program.config import PLAYER, SAMPLED, Configuration, Controller, Pick, Request
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
CONTROL = (Controller('actor', PLAYER),)


def boundary(at=2):
    """An actor whose events all come due at `at`: `prior` sets a value, then `decide` asks the player
    and sets `chosen`, then `following` sets `later`; `future` is due an hour after. A tally fills at
    1 h an hour, and the actor sees the value and the tally."""
    b = Builder(UNITS)
    plan = b.enum('enum[YES, NO]', 'YES', 'NO')
    b.entity(
        'actor',
        sees(this.value),
        sees(this.accumulated),
        value('forecast', dist_of(plan), categorical(plan, YES=0.4, NO=0.6)),
        value('value', '', 0),
        value('chosen', '', 0),
        value('later', '', 0),
        value('accumulated', 'h', 0),
        flow('accumulate', SOURCE, this.accumulated, request=q(1, 'h/h')),
        event('prior', after(q(at, 'h'), assign(this.value, 7))),
        event(
            'decide',
            after(
                q(at, 'h'),
                switch(
                    choose(this, this.forecast),
                    case(plan.YES, assign(this.chosen, 1)),
                    case(plan.NO, assign(this.chosen, 2)),
                ),
            ),
        ),
        event('following', after(q(at, 'h'), assign(this.later, 1))),
        event('future', after(q(at + 1, 'h'), assign(this.later, 2))),
    )
    actor = named('actor')
    b.setup(start(actor.prior), start(actor.decide), start(actor.following), start(actor.future))
    return b


SITE = 'actor.decide.step[0].do[0].choice[0]'


def program(at=2):
    b = boundary(at)
    return b.finish()


def played(*picks, horizon=4, **settings):
    return Configuration(Request(horizon), controllers=CONTROL, picks=picks, **settings)


def values(record, program_, names, t_):
    return [reading.values[0] for reading in read(record, program_, [f'actor.{n}' for n in names], [t_])]


@pytest.mark.parametrize('at', [0, 2, 4])
def test_a_pause_keeps_what_its_moment_committed_before_the_stage_and_nothing_of_the_stage(at):
    source = program(at)
    record = run(source, played())
    entry = paused(record)
    assert record.failure is None and entry is not None and record.trace[-1] == entry
    assert (entry.t, entry.part, entry.owner) == (at, 'actor.decide.step[0].do[0]', 'actor.decide#0')
    assert entry.detail('site') == SITE and entry.detail('options') == ('YES', 'NO')
    assert entry.detail('weights') == (('YES', 0.4), ('NO', 0.6))
    # What the actor sees: the value that `prior` committed in this moment, and the tally.
    assert entry.detail('sees') == (('this.value', 7), ('this.accumulated', pytest.approx(at)))
    assert values(record, source, ['value', 'chosen', 'later', 'accumulated'], at) == [
        7,
        0,
        0,
        pytest.approx(at),
    ]
    commits = {e.part for e in record.entries('commit')}
    assert commits == {'actor.prior.step[0]'}  # neither the decision nor the stages after it


def test_a_run_with_the_pick_replays_the_stage_once_and_reaches_the_horizon():
    source = program()
    first = run(source, played())
    answered = run(source, played(Pick(SITE, 'actor.decide#0', 'YES')))
    assert paused(answered) is None and answered.failure is None
    assert values(answered, source, ['value', 'chosen', 'later'], 4) == [7, 1, 2]
    # The paused record is the start of the answered one, up to the pause.
    assert answered.trace[: len(first.trace) - 1] == first.trace[:-1]
    (choice,) = answered.entries('choice')
    assert (choice.t, choice.detail('by'), choice.detail('value')) == (2, 'player', 'YES')


def test_a_run_with_no_controller_never_pauses():
    source = program()
    record = run(source, Configuration(Request(4)))
    assert paused(record) is None and values(record, source, ['chosen'], 4) == [2]  # the forecast: NO


def test_resume_goes_on_in_place_and_gives_the_record_of_the_replay():
    source = program()
    running = Run(Plan.of(source, played()))
    assert paused(running.run()) is not None
    resumed = running.resume(Pick(SITE, 'actor.decide#0', 'NO'))
    assert resumed == run(source, played(Pick(SITE, 'actor.decide#0', 'NO')))
    with pytest.raises(Exception, match='waits for no choice'):
        running.resume(Pick(SITE, 'actor.decide#0', 'NO'))


def atomic(seed=5):
    """A stage that draws, queues a child, moves 3 L and only then asks the player."""
    b = Builder(UNITS)
    plan = b.enum('enum[REPAIR, WAIT]', 'REPAIR', 'WAIT')
    crew = b.entity('crew', value('forecast', dist_of(plan), categorical(plan, REPAIR=0.5, WAIT=0.5)))
    b.entity(
        'site',
        value('level', 'L', 8, lower=0),
        value('spare', 'L', 0, lower=0),
        value('x', '', 0),
        value('duration', 'h', 0),
        event('child', after(q(0, 'h'), add(this.x, 10))),
        event(
            'work',
            after(
                q(1, 'h'),
                assign(this.duration, draw(uniform(1, 3, 'h'))),
                start(this.child),
                move(q(3, 'L'), this.level, this.spare),
                assign(this.x, 1),
                switch(
                    choose(crew, crew.forecast),
                    case(plan.REPAIR, add(this.x, 100)),
                    case(plan.WAIT, add(this.x, 1000)),
                ),
            ),
        ),
    )
    b.setup(start(named('site').work))
    configuration = Configuration(
        Request(3), mode=SAMPLED, seed=seed, controllers=(Controller('crew', PLAYER),)
    )
    return b.finish(), configuration


ATOMIC = 'site.work.step[0].do[4].choice[0]'


def test_a_prompt_never_makes_a_second_draw_child_or_transfer():
    """The paused stage drew its duration, queued a child and moved 3 L: none of it is visible, and
    the draw is kept. With the answer, the stage commits once: one draw, one child, one move, and the
    oracle agrees."""
    source, configuration = atomic()
    running = Run(Plan.of(source, configuration))
    stopped = running.run()
    entry = paused(stopped)
    (drawn,) = stopped.entries('draw')
    assert entry.detail('kept') == ((drawn.part, drawn.detail('value')),)
    assert entry.detail('starts') == ('site.child',)
    assert stopped.entries('start', 'site.child') == stopped.entries('move') == ()
    found = read(stopped, source, ['site.level', 'site.spare', 'site.x', 'site.duration'], [1])
    assert [reading.values[0] for reading in found] == [8, 0, 0, 0]
    pick = Pick(ATOMIC, 'site.work#0', 'REPAIR')
    resumed = running.resume(pick)
    answered = replace(configuration, picks=(pick,))
    assert resumed == run(source, answered)
    assert len(resumed.entries('draw')) == len(resumed.entries('move')) == 1
    assert len(resumed.entries('start', 'site.child')) == 1
    assert resumed.entries('draw')[0].detail('value') == drawn.detail('value')
    found = read(resumed, source, ['site.level', 'site.spare', 'site.x', 'site.duration'], [3])
    assert [reading.values[0] for reading in found] == [5, 3, 111, pytest.approx(drawn.detail('value'))]
    oracle, failed = run_of(source, answered)
    assert failed is None
    for reading in found:
        assert reading.values[0] == pytest.approx(float(value_at(oracle, source, reading.key, 3)))


def test_a_decision_after_a_delay_keeps_the_firing_that_started_it():
    """A trigger at 0 h starts `decide`, whose stage asks 2 h later: the firing is kept, the choice
    waits."""
    b = Builder(UNITS)
    plan = b.enum('enum[YES, NO]', 'YES', 'NO')
    b.entity(
        'actor',
        value('forecast', dist_of(plan), categorical(plan, YES=1, NO=1)),
        value('chosen', '', 0),
        event(
            'decide',
            after(q(2, 'h'), switch(choose(this, this.forecast), case(plan.YES, assign(this.chosen, 1)))),
            when(t >= q(0, 'h'), start(this.decide)),
        ),
    )
    source = b.finish()
    record = run(source, played())
    assert [entry.t for entry in record.entries('fire')] == [0]
    entry = paused(record)
    assert (entry.t, entry.owner) == (2, 'actor.decide#0')
    assert values(record, source, ['chosen'], 2) == [0]


def nested():
    """A parent stage at 1 h sets a value and starts three children in order: the first sets the value,
    the second asks the player, the third would set it again."""
    b = Builder(UNITS)
    plan = b.enum('enum[YES, NO]', 'YES', 'NO')
    b.entity(
        'actor',
        value('forecast', dist_of(plan), categorical(plan, YES=1, NO=1)),
        value('value', '', 0),
        value('chosen', '', 0),
        event(
            'parent',
            after(q(1, 'h'), assign(this.value, 2), start(this.first), start(this.decide), start(this.last)),
        ),
        event('first', after(q(0, 'h'), assign(this.value, 3))),
        event(
            'decide',
            after(
                q(0, 'h'),
                switch(
                    choose(this, this.forecast),
                    case(plan.YES, assign(this.chosen, 1)),
                    case(plan.NO, assign(this.chosen, 2)),
                ),
            ),
        ),
        event('last', after(q(0, 'h'), assign(this.value, 4))),
    )
    b.setup(start(named('actor').parent))
    return b.finish()


def test_a_nested_pause_keeps_the_parent_and_the_earlier_sibling_and_not_the_later():
    source = nested()
    record = run(source, played(horizon=3))
    entry = paused(record)
    assert (entry.t, entry.owner) == (1, 'actor.decide#0')
    commits = [(e.part, e.round) for e in record.entries('commit')]
    assert commits == [('actor.parent.step[0]', 1), ('actor.first.step[0]', 2)]
    assert values(record, source, ['value', 'chosen'], 1) == [3, 0]
    answered = run(
        source, played(Pick('actor.decide.step[0].do[0].choice[0]', 'actor.decide#0', 'YES'), horizon=3)
    )
    assert values(answered, source, ['value', 'chosen'], 3) == [4, 1]


def test_a_pause_in_the_setup_is_answered_by_the_root():
    b = Builder(UNITS)
    plan = b.enum('enum[YES, NO]', 'YES', 'NO')
    actor = b.entity(
        'actor', value('forecast', dist_of(plan), categorical(plan, YES=1, NO=1)), value('x', '', 0)
    )
    b.setup(
        switch(
            choose(actor, actor.forecast),
            case(plan.YES, assign(actor.x, 1)),
            case(plan.NO, assign(actor.x, 2)),
        )
    )
    source = b.finish()
    entry = paused(run(source, played(horizon=1)))
    assert (entry.t, entry.round, entry.owner, entry.part) == (0, 0, '', 'setup[0]')
    answered = run(source, played(Pick('setup[0].choice[0]', '', 'NO'), horizon=1))
    assert read(answered, source, ['actor.x'], [1])[0].values == (2,)


def test_a_players_choice_outside_a_stage_fails_the_run():
    """A trigger's capture belongs to a firing, which a prompt cannot pause."""
    b = Builder(UNITS)
    plan = b.enum('enum[YES, NO]', 'YES', 'NO')
    b.entity(
        'actor',
        value('forecast', dist_of(plan), categorical(plan, YES=1, NO=1)),
        event(
            'act',
            after(q(0, 'h')),
            when(
                t >= q(1, 'h'), start(this.act), captures=(value('plan', plan, choose(this, this.forecast)),)
            ),
        ),
    )
    record = run(b.finish(), played(horizon=2))
    assert record.failure.t == 1 and 'a player chooses in a stage' in record.failure.detail('message')
