"""The three limits that protect a run (decision D6): `max_occurrences`, `max_active` and
`max_rounds`. Each has the spec's default and can be configured; a run that reaches one fails with a
message that names the limit and the event, and for `max_active` the oldest waiting occurrence and
the step at which it waits."""

import pytest

from tests.reference.errors import RunFailed
from tests.reference.model import (
    Config,
    Model,
    N,
    add,
    after,
    count,
    event,
    lit,
    start,
    t,
    this,
    trigger,
    until,
    value,
)
from tests.reference.run import Run


def test_the_defaults():
    config = Config()
    assert (config.max_occurrences, config.max_active, config.max_rounds) == (1_000_000, 100_000, 1_000)


def desk(steps):
    """A trigger that starts a ticket at 0 h and every hour after."""
    hourly = trigger(t >= 0, [start(this.ticket)], reset=('after', 1))
    m = Model()
    m.entity('desk', fields=[value('open', False)], events=[event('ticket', triggers=[hourly], steps=steps)])
    return m


def test_max_active_names_the_oldest_waiting_occurrence():
    m = desk([until(this.open)])
    with pytest.raises(RunFailed) as e:
        Run(m, Config(horizon=10, max_active=3)).run()
    assert str(e.value) == (
        '3 occurrences of desk.ticket are active at once (max_active = 3) and one more starts at t = 3 h. '
        'The oldest, desk.ticket#1, started at 0 h and waits at `until this.open` (step 1).'
    )
    r = Run(m, Config(horizon=10, max_active=20)).run()
    assert r.read(count(N.desk.ticket.occurrences)) == 11


def test_max_occurrences_counts_every_start_of_one_event():
    m = desk([after(0, [])])
    with pytest.raises(RunFailed) as e:
        Run(m, Config(horizon=10, max_occurrences=5)).run()
    assert (
        str(e.value)
        == 'desk.ticket would start 6 times by t = 5 h: the limit max_occurrences is 5 starts of one event'
    )


def bumps(limit):
    again = trigger(this.n < limit, [start(this.bump)], reset=('when', lit(True)))
    m = Model()
    m.entity(
        'pump',
        fields=[value('n', 0)],
        events=[event('bump', triggers=[again], steps=[after(0, [add(this.n, 1)])])],
    )
    return m


def test_max_rounds_names_the_trigger_that_fires_again_and_again():
    """A finite chain of reactions at one time is legitimate; a cycle reaches the limit."""
    assert Run(bumps(2), horizon=1).run().read(N.pump.n) == 2
    with pytest.raises(RunFailed) as e:
        Run(bumps(10**6), Config(horizon=1, max_rounds=10)).run()
    assert str(e.value).startswith(
        'more than 10 rounds at t = 0 h: the limit max_rounds is 10 rounds at one time. '
    )
    assert 'Triggers that fired again and again: pump.bump.when[0]' in str(e.value)
    assert 'pump.bump (' in str(e.value)
