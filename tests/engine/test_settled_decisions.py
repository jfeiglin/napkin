"""What a pause settles (R-A2-14; spec, "A prompt pauses one atomic stage"; `chance.py`).

The stages of a moment commit one after another (D5). A pause stops the run in its stage: the stages
of its round before it have committed and are kept; the stage itself and the stages after it, in its
round and in the rounds after, wait for the answer, and nothing of the future happens. A run with the
picks, and a chain of runs that each answer one more choice, replay the same trajectory from the same
keyed draws. The expected values are worked by hand from these rules.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run, paused
from napkin.program.build import (
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
    named,
    q,
    start,
    switch,
    t,
    this,
    uniform,
    value,
    when,
)
from napkin.program.config import PLAYER, SAMPLED, Configuration, Controller, Pick, Request

UNITS = {'h': {'time': 1}}
DECIDE = 'actor.decide.step[0].do[0].choice[0]'
NEXT = 'actor.next_choice.step[0].do[0].choice[0]'


def cascade():
    """At 1 h an actor draws a number, reports twice, asks the player twice: `decide` and then
    `next_choice` start in the commit of `outer`, and each answer starts a report of its own."""
    b = Builder(UNITS)
    plan = b.enum('enum[YES, NO]', 'YES', 'NO')
    decision = (
        choose(this, this.forecast),
        case(plan.YES, add(this.chosen, 1), start(this.answered)),
        case(plan.NO, add(this.chosen, 10), start(this.answered)),
    )
    b.entity(
        'actor',
        value('forecast', dist_of(plan), categorical(plan, YES=0.5, NO=0.5)),
        value('random', '', 0),
        value('report', '', 0),
        value('chosen', '', 0),
        value('answers', '', 0),
        event('roll', after(q(1, 'h'), assign(this.random, draw(uniform(1, 2))))),
        event('report_once', after(q(1, 'h'), add(this.report, 1))),
        event(
            'outer', after(q(1, 'h'), start(this.decide), start(this.next_choice), start(this.report_late))
        ),
        event('decide', after(q(0, 'h'), switch(*decision))),
        event('next_choice', after(q(0, 'h'), switch(*decision))),
        event('report_late', after(q(0, 'h'), add(this.report, 1))),
        event('answered', after(q(0, 'h'), add(this.answers, 1))),
    )
    actor = named('actor')
    b.setup(start(actor.roll), start(actor.report_once), start(actor.outer))
    return b.finish()


def played(*picks, seed=None):
    mode = {'mode': SAMPLED, 'seed': seed} if seed is not None else {}
    return Configuration(Request(2), controllers=(Controller('actor', PLAYER),), picks=picks, **mode)


def state(record, program, at=1):
    names = ['random', 'report', 'chosen', 'answers']
    return dict(zip(names, (r.values[0] for r in read(record, program, [f'actor.{n}' for n in names], [at]))))


def test_the_stages_before_a_pause_commit_and_those_after_it_wait():
    """At 1 h: `roll`, `report_once` and `outer` commit in round 1; in round 2 `decide` asks first, so
    `next_choice` and `report_late`, after it in the round, wait with it."""
    program = cascade()
    record = run(program, played())
    entry = paused(record)
    assert (entry.t, entry.round, entry.owner) == (1, 2, 'actor.decide#0')
    found = state(record, program)
    assert (found['report'], found['chosen'], found['answers']) == (1, 0, 0)
    assert 1 <= found['random'] <= 2
    assert [e.part for e in record.entries('commit')] == [
        'actor.roll.step[0]',
        'actor.report_once.step[0]',
        'actor.outer.step[0]',
    ]


def test_each_answer_goes_on_to_the_next_choice_of_the_same_moment():
    program = cascade()
    first = run(program, played(Pick(DECIDE, 'actor.decide#0', 'YES')))
    entry = paused(first)
    assert (entry.t, entry.owner, entry.detail('site')) == (1, 'actor.next_choice#0', NEXT)
    assert state(first, program)['chosen'] == 1
    both = run(
        program, played(Pick(DECIDE, 'actor.decide#0', 'YES'), Pick(NEXT, 'actor.next_choice#0', 'NO'))
    )
    assert paused(both) is None
    found = state(both, program, 2)
    assert (found['report'], found['chosen'], found['answers']) == (2, 11, 2)


@pytest.mark.parametrize('seed', [2, 17, 91])
def test_a_chain_of_answers_replays_the_run_with_every_pick(seed):
    """The draw at 1 h is the same in each record of the chain; the last record of the chain, answered
    in place, is the record of a run with both picks."""
    program = cascade()
    picks = (Pick(DECIDE, 'actor.decide#0', 'YES'), Pick(NEXT, 'actor.next_choice#0', 'NO'))
    running = Run(Plan.of(program, played(seed=seed)))
    records = [running.run()]
    for pick in picks:
        records.append(running.resume(pick))
    full = run(program, played(*picks, seed=seed))
    assert records[-1] == full
    assert [paused(record) is None for record in records] == [False, False, True]
    assert len({state(record, program)['random'] for record in records}) == 1
    assert [state(record, program)['random'] for record in records[:2]] == [
        state(full, program, 2)['random']
    ] * 2


def test_a_trigger_and_a_manual_start_of_a_decision_are_two_choices():
    """A decision that a trigger starts and a manual start starts at the same time is two occurrences,
    each with its own pick."""
    b = Builder(UNITS)
    plan = b.enum('enum[YES, NO]', 'YES', 'NO')
    b.entity(
        'actor',
        value('forecast', dist_of(plan), categorical(plan, YES=0.5, NO=0.5)),
        value('chosen', '', 0),
        event(
            'decide',
            after(q(0, 'h'), switch(choose(this, this.forecast), case(plan.YES, add(this.chosen, 1)))),
            when(t >= q(1, 'h'), start(this.decide)),
        ),
        event('ask', after(q(1, 'h'), start(this.decide))),
    )
    b.setup(start(named('actor').ask))
    program = b.finish()
    site = 'actor.decide.step[0].do[0].choice[0]'
    first = paused(run(program, played()))
    assert (first.t, first.owner) == (1, 'actor.decide#0')
    second = paused(run(program, played(Pick(site, 'actor.decide#0', 'YES'))))
    assert (second.t, second.owner) == (1, 'actor.decide#1')
    both = run(program, played(Pick(site, 'actor.decide#0', 'YES'), Pick(site, 'actor.decide#1', 'YES')))
    assert read(both, program, ['actor.chosen'], [2])[0].values == (2,)
