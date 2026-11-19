"""The outcomes of categorical draws and the picks of a run (D1; `chance.py`).

A sampled draw takes the outcome whose share of (0, 1), in declared order, holds its uniform number:
the share of each outcome is the part of the uniform numbers that takes it, which exact fractions
give. A run takes the given picks for the choices that they answer and pauses at the first that none
answers; a pick for a choice that the run never makes changes nothing; a run whose actors nobody plays
is the median run. The expected values are exact fractions and the rules themselves.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import paused
from napkin.engine.timeline.chance import outcome
from napkin.program.build import (
    Builder,
    add,
    after,
    case,
    categorical,
    choose,
    dist_of,
    event,
    named,
    q,
    reset_after,
    start,
    switch,
    t,
    this,
    value,
    when,
)
from napkin.program.config import FORECAST, PLAYER, Configuration, Controller, Pick, Request
from napkin.program.refs import Distribution

UNITS = {'h': {'time': 1}}


@pytest.mark.parametrize(
    'weights',
    [
        {'A': Fraction(1, 2), 'B': Fraction(1, 2)},
        {'A': Fraction(1, 4), 'B': Fraction(1, 2), 'C': Fraction(1, 4)},
        {'A': Fraction(1, 8), 'B': Fraction(5, 8), 'C': Fraction(2, 8)},
    ],
)
def test_the_share_of_each_outcome_is_the_part_of_the_uniform_numbers_that_takes_it(weights):
    """At the midpoints (k + 1/2) / 512 of (0, 1), each outcome takes 512 times its weight of them."""
    names = tuple(weights)
    d = Distribution('categorical', tuple(float(w) for w in weights.values()), enum='E', outcomes=names)
    points = 512
    taken = [outcome(d, None, (k + 0.5) / points) for k in range(points)]
    assert {name: taken.count(name) for name in names} == {name: points * w for name, w in weights.items()}
    # The outcomes come in their declared order along (0, 1).
    assert taken == sorted(taken, key=names.index)


def test_barred_outcomes_give_their_share_to_the_others_in_proportion():
    """With A barred, B and C share (0, 1) as 5 to 2."""
    d = Distribution('categorical', (0.125, 0.625, 0.25), enum='E', outcomes=('A', 'B', 'C'))
    taken = [outcome(d, ('B', 'C'), (k + 0.5) / 700) for k in range(700)]
    assert (taken.count('B'), taken.count('C')) == (500, 200)


def clock():
    """A clock whose trigger starts `decide` each hour from 1 h; each asks the operator whether to
    shut, which the forecast does one time in four."""
    b = Builder(UNITS)
    action = b.enum('enum[SHUT, WAIT]', 'SHUT', 'WAIT')
    b.entity(
        'operator',
        value('forecast', dist_of(action), categorical(action, SHUT=0.25, WAIT=0.75)),
        value('shut', '', 0),
        event(
            'decide',
            after(q(0, 'h'), switch(choose(this, this.forecast), case(action.SHUT, add(this.shut, 1)))),
            when(t >= q(1, 'h'), start(this.decide), reset=reset_after(q(1, 'h'))),
        ),
    )
    return b.finish()


SITE = 'operator.decide.step[0].do[0].choice[0]'


def played(*shut, by=PLAYER, horizon=3):
    picks = tuple(Pick(SITE, f'operator.decide#{k}', 'SHUT' if yes else 'WAIT') for k, yes in enumerate(shut))
    return Configuration(Request(horizon), controllers=(Controller('operator', by),), picks=picks)


def shut(record, program, at=3):
    return read(record, program, ['operator.shut'], [at])[0].values[0]


@pytest.mark.parametrize('answers', [(True,), (True, False), (False, True)])
def test_a_run_takes_the_given_picks_and_pauses_at_the_first_choice_that_none_answers(answers):
    """The clock decides at 1, 2 and 3 h."""
    program = clock()
    record = run(program, played(*answers))
    entry = paused(record)
    assert (entry.t, entry.owner) == (1 + len(answers), f'operator.decide#{len(answers)}')
    assert shut(record, program, len(answers)) == sum(answers)


def test_more_picks_than_choices_change_nothing():
    program = clock()
    exact = run(program, played(True, False, True))
    extra = run(program, played(True, False, True, True, True))
    assert paused(exact) is None and exact == extra and shut(exact, program) == 2


def test_a_run_that_nobody_plays_is_the_median_run():
    program = clock()
    alone = run(program, Configuration(Request(3)))
    forecast = run(program, played(True, True, True, by=FORECAST))
    assert alone == forecast and shut(alone, program) == 0  # the forecast waits: 3/4 against 1/4
    assert [entry.detail('by') for entry in alone.entries('choice')] == ['forecast'] * 3


def test_a_pick_outside_the_enum_stops_the_run():
    program = clock()
    record = run(
        program,
        Configuration(
            Request(3),
            controllers=(Controller('operator', PLAYER),),
            picks=(Pick(SITE, 'operator.decide#0', 'OPEN'),),
        ),
    )
    assert record.failure.t == 1 and 'the pick OPEN of operator.decide#0 is not available' in (
        record.failure.detail('message')
    )


def test_each_member_of_a_template_is_its_own_actor():
    """Two operators of one template decide at 1 h; the player controls the first only, and the
    second takes its forecast."""
    b = Builder(UNITS)
    action = b.enum('enum[SHUT, WAIT]', 'SHUT', 'WAIT')
    b.template(
        'Operator',
        value('forecast', dist_of(action), categorical(action, SHUT=0.25, WAIT=0.75)),
        value('shut', '', 0),
        event(
            'decide',
            after(q(1, 'h'), switch(choose(this, this.forecast), case(action.SHUT, add(this.shut, 1)))),
        ),
    )
    b.member('Operator', 'north')
    b.member('Operator', 'south')
    b.setup(start(named('north').decide), start(named('south').decide))
    program = b.finish()
    site = 'Operator.decide.step[0].do[0].choice[0]'
    configuration = Configuration(
        Request(2),
        controllers=(Controller('north', PLAYER),),
        picks=(Pick(site, 'north.decide#0', 'SHUT'),),
    )
    record = run(program, configuration)
    assert paused(record) is None
    assert [reading.values[0] for reading in read(record, program, ['north.shut', 'south.shut'], [2])] == [
        1,
        0,
    ]
    choices = {entry.owner: entry.detail('by') for entry in record.entries('choice')}
    assert choices == {'north.decide#0': 'player', 'south.decide#0': 'forecast'}
