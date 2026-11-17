"""Windows and waiting conditions of events (docs/language.md, §2.6): `each W` fires an event at most
once for each value of W, and `while K` cancels a firing that waits once K fails. The expected times
follow from the fixture's clock and alarm, not from a trace."""

from __future__ import annotations

import pytest

from napkin.model import ModelError
from tests.build import block, document, entity, library, named, run, stock


def world(*lines):
    """A clock whose `beat` steps at 1, 2 and 3 h, and an alarm on from 1.5 h to 2.5 h and from 4 h."""
    return entity(
        'world',
        stock('beat', 0, 'fraction', minimum=None, maximum=10, size=None, kind='state'),
        named('alarm', 'off', 'on'),
        block('event tick_1 once when t >= 1 h:  @fixture', 'beat = 1'),
        block('event tick_2 once when t >= 2 h:  @fixture', 'beat = 2'),
        block('event tick_3 once when t >= 3 h:  @fixture', 'beat = 3'),
        block('event ring once when t >= 1.5 h:  @fixture', 'alarm = "on"'),
        block('event hush once when t >= 2.5 h:  @fixture', 'alarm = "off"'),
        block('event ring_again once when t >= 4 h:  @fixture', 'alarm = "on"'),
        *lines,
    )


def times(*lines, rule='world.watch'):
    _, trajectory = run(document('Windows fixture', world(*lines), horizon=12))
    return [
        entry['t'] for entry in trajectory.trace if entry['rule'] == rule and entry.get('outcome') is not None
    ]


def fires(head):
    return block(head, '"It happens."', 'beat = beat')


def test_an_event_with_a_window_fires_once_in_each_window_while_its_condition_holds():
    # The alarm is on in beats 1 and 2, off in beat 3, and on again in beat 3 from 4 h.
    assert times(fires('event watch each beat when alarm is "on":  @fixture')) == [1.5, 2.0, 4.0]


def test_without_a_window_the_same_condition_fires_each_time_it_becomes_true():
    assert times(fires('event watch when alarm is "on":  @fixture')) == [1.5, 4.0]


def test_a_window_alone_fires_once_in_each_window():
    assert times(fires('event watch each beat:  @fixture')) == [0.0, 1.0, 2.0, 3.0]


def test_a_window_of_two_values_fires_in_each_new_combination():
    assert times(fires('event watch each beat, alarm:  @fixture')) == [0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]


def test_a_waiting_firing_is_cancelled_when_its_condition_fails():
    # Triggered at 1.5 h, due at 4.5 h; the alarm goes off at 2.5 h, so that firing never happens. The
    # alarm comes on again at 4 h: a new firing is due at 7 h.
    head = 'event watch after 3 h when alarm is "on" while alarm is "on":  @fixture'
    assert times(fires(head)) == [7.0]
    # Without `while`, the first firing happens anyway, and an event that waits does not trigger again:
    # the alarm is still on after it fires, so nothing new triggers.
    assert times(fires('event watch after 3 h when alarm is "on":  @fixture')) == [4.5]


def test_a_cancelled_firing_was_still_a_trigger_that_count_and_since_read():
    # The watch triggers at 1.5 h (cancelled at 2.5 h) and at 4 h (it fires at 7 h). Each trigger
    # counts as it happens: count(watch) is 1 from 1.5 h, before the cancellation, and 2 from 4 h,
    # before the firing; since(watch) runs from the cancelled trigger, so 2 h after it is 3.5 h.
    head = 'event watch after 3 h when alarm is "on" while alarm is "on":  @fixture'
    first = block('event first once when count(watch) >= 1:  @fixture', '"One trigger."', 'beat = beat')
    second = block('event second once when count(watch) >= 2:  @fixture', '"Two triggers."', 'beat = beat')
    later = block(
        'event later once when count(watch) >= 1 and since(watch) >= 2 h:  @fixture',
        '"Two hours after the first trigger."',
        'beat = beat',
    )
    lines = (fires(head), first, second, later)
    assert times(*lines) == [7.0]
    assert times(*lines, rule='world.first') == [1.5]
    assert times(*lines, rule='world.second') == [4.0]
    assert times(*lines, rule='world.later') == [3.5]


def test_a_cancelled_event_that_fires_once_stays_spent():
    head = 'event watch once after 3 h when alarm is "on" while alarm is "on":  @fixture'
    assert times(fires(head)) == []


@pytest.mark.parametrize(
    'head',
    [
        'event watch once each beat:  @fixture',  # once and a window
        'event watch when alarm is "on" while alarm is "on":  @fixture',  # nothing waits
        'event watch each t:  @fixture',  # a window on a value that moves between moments
    ],
    ids=['once and each', 'while without after', 'a moving window'],
)
def test_a_window_or_a_waiting_condition_that_cannot_hold_is_refused(head):
    with pytest.raises(ModelError):
        run(document('Windows fixture', world(fires(head)), horizon=12), lib=library())


def test_a_window_opens_again_when_its_value_returns():
    # The alarm is on from 1.5 h to 2.5 h and again from 4 h: two windows of the value "on", with an
    # "off" window between them in which the condition never holds.
    assert times(fires('event watch each alarm when alarm is "on":  @fixture')) == [1.5, 4.0]


def test_without_a_condition_each_return_of_a_value_is_a_new_window():
    assert times(fires('event watch each alarm:  @fixture')) == [0.0, 1.5, 2.5, 4.0]
