"""A played run (spec, "Actor decisions and observations"; D1; `chance.py`): the configuration names
who controls each actor, and a player's picks answer its choices, each keyed by the choice's site and
the occurrence that makes it. A choice of a played actor shows what the actor sees, in the declared
units of the observations; `sees` permits nothing. The expected values are the fixture's constant
rates and the spec's rules.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import paused
from napkin.program.build import (
    BOOL,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    case,
    categorical,
    choose,
    dist_of,
    event,
    flow,
    named,
    q,
    sees,
    start,
    switch,
    this,
    value,
)
from napkin.program.config import (
    FORECAST,
    PLAYER,
    Configuration,
    ConfigurationError,
    Controller,
    Pick,
    Request,
)

UNITS = {'h': {'time': 1}, 'day': ({'time': 1}, 24), 'L': {'volume': 1}}
FIRST = 'guard.first.step[0].do[0].choice[0]'
SECOND = 'guard.second.step[0].do[0].choice[0]'


def world(alarm=True):
    """A world whose alarm is on (unless `alarm` is false), whose level rises at 0.1 L an hour from
    0, and whose delay is 2 days; a guard that decides at 3 h, and again at 5 h, to shut or to wait.
    The guard sees the alarm, the level and the delay, and nothing of the hum."""
    b = Builder(UNITS)
    action = b.enum('enum[SHUT, WAIT]', 'SHUT', 'WAIT')
    w = named('world')
    b.entity(
        'world',
        value('alarm', BOOL, alarm),
        value('level', 'L', 0, lower=0),
        value('delay', 'day', 2),
        value('hum', 'L', 9),
        flow('rise', SOURCE, this.level, request=q(0.1, 'L/h')),
    )
    decision = (
        switch(
            choose(this, this.forecast),
            case(action.SHUT, add(this.shut, 1), when=w.alarm),
            case(action.WAIT, add(this.waited, 1)),
        ),
    )
    b.entity(
        'guard',
        sees(w.alarm),
        sees(w.level),
        sees(w.delay),
        value('forecast', dist_of(action), categorical(action, SHUT=0.25, WAIT=0.75)),
        value('shut', '', 0),
        value('waited', '', 0),
        event('first', after(q(3, 'h'), *decision)),
        event('second', after(q(5, 'h'), *decision)),
    )
    g = named('guard')
    b.setup(start(g.first), start(g.second))
    return b.finish()


def played(*picks, by=PLAYER):
    return Configuration(Request(6), controllers=(Controller('guard', by),), picks=picks)


def counts(record, program):
    found = read(record, program, ['guard.shut', 'guard.waited'], [6])
    return tuple(reading.values[0] for reading in found)


def test_the_first_choice_with_no_pick_shows_exactly_what_its_actor_sees():
    program = world()
    entry = paused(run(program, played()))
    assert (entry.t, entry.owner, entry.detail('site'), entry.detail('actor')) == (
        3,
        'guard.first#0',
        FIRST,
        'guard',
    )
    # The level rises at 0.1 L an hour from 0: 0.3 L at 3 h. The delay shows in its own unit, days.
    assert entry.detail('sees') == (
        ('world.alarm', True),
        ('world.level', pytest.approx(0.3, rel=1e-9)),
        ('world.delay', pytest.approx(2)),
    )
    assert entry.detail('options') == ('SHUT', 'WAIT')


def test_each_pick_answers_its_own_site_and_occurrence():
    program = world()
    first = run(program, played(Pick(FIRST, 'guard.first#0', 'SHUT')))
    entry = paused(first)
    assert (entry.t, entry.detail('site')) == (5, SECOND)
    both = run(program, played(Pick(FIRST, 'guard.first#0', 'SHUT'), Pick(SECOND, 'guard.second#0', 'SHUT')))
    assert paused(both) is None and counts(both, program) == (2, 0)
    choices = [(entry.t, entry.detail('by'), entry.detail('value')) for entry in both.entries('choice')]
    assert choices == [(3, 'player', 'SHUT'), (5, 'player', 'SHUT')]
    (seen,) = {entry.detail('sees')[1][1] for entry in both.entries('choice')[1:]}
    assert seen == pytest.approx(0.5)  # the level at 5 h


def test_a_forecast_controller_is_the_model_alone():
    """With the forecast in control the guard waits twice, as with no controller; its picks are not
    read."""
    program = world()
    forecast = run(program, played(Pick(FIRST, 'guard.first#0', 'SHUT'), by=FORECAST))
    alone = run(program, Configuration(Request(6)))
    assert counts(forecast, program) == counts(alone, program) == (0, 2)
    assert [entry.detail('by') for entry in alone.entries('choice')] == ['forecast', 'forecast']


def test_a_pick_replaces_the_forecast_but_not_a_guard():
    """SHUT needs the alarm: with it off, a pick of SHUT fails the run; WAIT is always available."""
    picks = (Pick(FIRST, 'guard.first#0', 'WAIT'), Pick(SECOND, 'guard.second#0', 'SHUT'))
    record = run(world(alarm=False), played(*picks))
    assert record.failure.t == 5
    assert 'the pick SHUT of guard.second#0 is not available (available: WAIT)' in record.failure.detail(
        'message'
    )
    program = world()
    waited = run(
        program, played(Pick(FIRST, 'guard.first#0', 'WAIT'), Pick(SECOND, 'guard.second#0', 'WAIT'))
    )
    assert counts(waited, program) == (0, 2)


def test_a_pick_at_a_site_that_no_choice_has_is_refused():
    with pytest.raises(ConfigurationError, match='no choice has this site'):
        run(world(), played(Pick('guard.first.step[0].do[0].draw[0]', 'guard.first#0', 'SHUT')))


def test_only_a_member_can_be_played():
    with pytest.raises(ConfigurationError, match='a controller decides for an actor'):
        run(world(), Configuration(Request(6), controllers=(Controller('nobody', PLAYER),)))


def test_sees_permits_nothing():
    """The guard sees the level only, and a stage of it writes the hum all the same."""
    b = Builder(UNITS)
    w = b.entity('world', value('hum', 'L', 9), value('level', 'L', 1))
    b.entity('guard', sees(w.level), event('listen', after(q(1, 'h'), assign(w.hum, q(1, 'L')))))
    b.setup(start(named('guard').listen))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert read(record, program, ['world.hum'], [2])[0].values == (1,)
