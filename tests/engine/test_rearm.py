"""A trigger fires each time its condition first becomes true (spec, "A trigger belongs to its event").

Without a reset, a trigger rearms when its condition becomes false, so a level that rises again to
its threshold fires it again; with `reset when C`, it rearms when C holds, whatever its own condition
does. The level rises at 1 L/h, and each firing starts a drain that takes 2 L at once, so the
threshold of 2 L is reached at 2, 4, 6 and 8 h (worked by hand).
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    BOOL,
    SOURCE,
    Builder,
    after,
    assign,
    event,
    flow,
    q,
    reset_when,
    start,
    subtract,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request


def tank(reset=None, *parts):
    """A level that rises at 1 L/h, with a drain that a trigger on 2 L starts."""
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    b.entity(
        'tank',
        value('level', 'L', 0, lower=0, upper=10),
        value('high', BOOL, False),
        flow('fill', SOURCE, this.level, request=q(1, 'L/h')),
        event(
            'drain',
            when(this.level >= q(2, 'L'), start(this.drain), reset=reset),
            after(q(0, 'h'), subtract(this.level, q(2, 'L')), assign(this.high, True)),
        ),
        *parts,
    )
    program = b.finish()
    return program, run(program, Configuration(Request(9)))


def test_a_crossing_fires_again_each_time_the_level_rises_to_it_again():
    program, record = tank()
    assert [entry.t for entry in record.entries('fire', 'tank.drain.when[0]')] == pytest.approx([2, 4, 6, 8])
    # 9 h at 1 L/h, less four drains of 2 L.
    assert read(record, program, ['tank.level'], [9.0])[0].values == pytest.approx((1.0,))


def test_a_reset_when_a_state_is_set_back_rearms_a_crossing():
    # The drain marks the tank high; a reset event marks it low again an hour later, which rearms the
    # trigger: the level, 0 L after each drain, reaches 2 L one hour after that. The horizon is
    # inclusive, so the last calm, due at 9 h, finishes.
    _, record = tank(
        reset_when(~this.high),
        event(
            'calm',
            when(this.high, start(this.calm), reset=reset_when(~this.high)),
            after(q(1, 'h'), assign(this.high, False)),
        ),
    )
    drains = [entry.t for entry in record.entries('fire', 'tank.drain.when[0]')]
    calms = [entry.t for entry in record.entries('finish', 'tank.calm')]
    assert drains == pytest.approx([2, 4, 6, 8])
    assert calms == pytest.approx([3, 5, 7, 9])
