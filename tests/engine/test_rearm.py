"""An event fires each time its condition becomes true (docs/language.md, §2.6). A repeatable event
that watches a crossing sets a name that its condition reads, so that it can fire again once another
event sets that name back."""

from __future__ import annotations

import pytest

from tests.build import event, named, output, run, stock, system


def test_a_repeatable_crossing_fires_each_time_the_value_crosses_again():
    # The level rises at 1 an hour. Each time it reaches 2, `drain` takes 2 and marks the state "high";
    # `reset` then marks it "low" again, which lets `drain` watch the next crossing: at 2, 4, 6 and 8 h.
    text = system(
        named('s', 'low', 'high'),
        stock('level', 0, 'fraction', maximum=10, size=None, rate='1 per_h'),
        event('drain', 's is "low" and level >= 2', 's = "high"', 'level -= 2', once=False, doc='Drain'),
        event('reset', 's is "high"', 's = "low"', once=False, doc='Reset'),
        horizon=9,
        outputs=(output('level_out', 's.level', 'fraction', 'level', doc='Level'),),
    )
    _, trajectory = run(text)
    drains = [entry['t'] for entry in trajectory.trace if entry['rule'] == 's.drain']
    resets = [entry['t'] for entry in trajectory.trace if entry['rule'] == 's.reset']
    assert drains == pytest.approx([2.0, 4.0, 6.0, 8.0])
    assert resets == pytest.approx(drains)
    end = trajectory.env_at(9)
    # 9 h at 1 an hour, less four drains of 2.
    assert (end['s.level'], end['s.s']) == (pytest.approx(9 - 4 * 2), 'low')
