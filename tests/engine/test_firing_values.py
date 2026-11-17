"""Values that an event reads when it fires (docs/language.md, §2.6): a distribution written in an event
is drawn each time the event fires, and `delayed(x, D)` reads x as it was D earlier. Expectations come
from the distributions' own medians, supports and moments and from the fixture's constant rates."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from napkin.engine.runtime import simulate
from napkin.model import ModelError
from tests.build import block, compiled, document, entity, library, stock

HOURS = 200  # one firing an hour


def clock(*lines, start=0):
    """A clock that fires `tick` every hour from 1 h, a tally `total`, and a stock `filled` that fills at
    1 person an hour from `start`."""
    return entity(
        'clock',
        stock('next', 1, 'h', minimum=None, maximum=HOURS + 2, size=None, kind='state'),
        stock('total', 0, 'people', size=1000),
        stock('filled', start, 'people', size=1000, rate='1 people/h'),
        stock('seen', 0, 'people', minimum=None, maximum=1000, size=None, kind='state'),
        *lines,
    )


def trajectory(*lines, luck=None, start=0):
    rs = compiled(document('Firing fixture', clock(*lines, start=start), horizon=HOURS)).resolve('a')
    if luck is not None:
        rs = replace(rs, luck=luck)
    return simulate(rs, library())


TICK = block(
    'event tick when t >= next:  @fixture', '"A tick."', 'next += 1 h', 'total += uniform(1 people, 3 people)'
)


def increments(trajectory_):
    """What each firing of `tick` added to the total."""
    totals = [trajectory_.env_at(hour + 0.5)['clock.total'] for hour in range(1, HOURS)]
    return [b - a for a, b in zip([0.0, *totals[:-1]], totals)]


def test_the_central_run_takes_the_median_at_each_firing():
    added = increments(trajectory(TICK))
    assert added == pytest.approx([2.0] * len(added))


def test_a_sample_draws_again_at_each_firing_from_its_stream():
    first = increments(trajectory(TICK, luck={'seed': 11, 'sample': 0}))
    again = increments(trajectory(TICK, luck={'seed': 11, 'sample': 0}))
    other = increments(trajectory(TICK, luck={'seed': 11, 'sample': 1}))
    assert first == again  # the same seed and sample give the same draws
    assert first != other
    assert len(set(first)) == len(first)  # each firing draws again
    assert all(1.0 <= value <= 3.0 for value in first)  # the support
    # The mean of uniform(1, 3) is 2 and its standard deviation 2/sqrt(12); five standard errors.
    bound = 5 * (2 / math.sqrt(12)) / math.sqrt(len(first))
    assert abs(sum(first) / len(first) - 2.0) < bound


def test_a_drawn_delay_is_read_as_the_event_triggers():
    late = block(
        'event late once after uniform(1 h, 3 h) when t >= 1 h:  @fixture', '"Late."', 'seen = 1 people'
    )
    trace = trajectory(late).trace
    assert [entry['t'] for entry in trace if entry['rule'] == 'clock.late' and entry.get('outcome')] == [
        pytest.approx(3.0)
    ]


def test_a_delayed_value_reads_the_run_as_it_was():
    look = block('event look once when t >= 10 h:  @fixture', '"Look."', 'seen = delayed(filled, 4 h)')
    early = block('event look once when t >= 2 h:  @fixture', '"Look."', 'seen = delayed(filled, 4 h)')
    # The stock fills at 1 person an hour from 5; 4 h before 10 h it held 5 + 6.
    assert trajectory(look, start=5).env_at(11)['clock.seen'] == pytest.approx(5 + 6)
    # Before the start, the value at the start.
    assert trajectory(early, start=5).env_at(3)['clock.seen'] == pytest.approx(5)


@pytest.mark.parametrize(
    'line',
    [
        block('event never when t >= uniform(1 h, 2 h):  @fixture', '"No."', 'seen = 1 people'),
        'let odd: people = 2 * uniform(1 people, 3 people)  @fixture\n    "Odd"',
        'flow leak: filled -> at delayed(filled, 1 h) / 10 h  @fixture',
    ],
    ids=['a distribution in a condition', 'a distribution inside a formula', 'delayed in a rate'],
)
def test_a_draw_or_a_delayed_value_outside_an_event_firing_is_refused(line):
    with pytest.raises(ModelError):
        trajectory(line)
