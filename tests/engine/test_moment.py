"""One moment (docs/language.md, §2.6, "One moment"): the events due at one moment go in the order of their
lines, and each reads what the events before it wrote."""

from __future__ import annotations

import pytest

from tests.build import event, named, output, run, stock, system


def file_of(*events):
    """Entity `s` with a named state `x` ("a", then "b") and a number `y`, and `events` in this
    order."""
    return system(
        named('x', 'a', 'b'),
        stock('y', 0, 'fraction', maximum=2, size=None),
        *events,
        outputs=(output('y_out', 's.y', 'fraction', 'level', doc='y'),),
    )


def story(text):
    """[(t, event)] of the run's events that read as a story, and y at the end."""
    _, trajectory = run(text)
    return [(e['t'], e['event']) for e in trajectory.trace if e['semantic']], trajectory.env_at(10)['s.y']


FIRST = event('first', 't >= 1 h', 'x = "b"', doc='First')


@pytest.mark.parametrize('first_line_first', [True, False])
def test_a_condition_reads_the_write_of_an_earlier_line(first_line_first):
    # `second` holds at t = 1 only while x is "a": after `first`, it no longer does.
    second = event('second', 't >= 1 h and x is "a"', 'y = 1', doc='Second')
    found = story(file_of(FIRST, second) if first_line_first else file_of(second, FIRST))
    if first_line_first:
        assert found == ([(1.0, 's.first.done')], 0)
    else:
        assert found == ([(1.0, 's.second.done'), (1.0, 's.first.done')], 1)


@pytest.mark.parametrize('first_line_first', [True, False])
def test_a_change_reads_the_write_of_an_earlier_line(first_line_first):
    # `second` sets y from x as it stands when it fires: 1 after `first`, 2 before it.
    second = event('second', 't >= 1 h', 'y = 1 if x is "b" else 2', doc='Second')
    found = story(file_of(FIRST, second) if first_line_first else file_of(second, FIRST))
    order = ['s.first.done', 's.second.done'] if first_line_first else ['s.second.done', 's.first.done']
    assert found == ([(1.0, name) for name in order], 1 if first_line_first else 2)
