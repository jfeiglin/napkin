"""The trigger of each row of a table fires at the time of its closed form, on a curve.

The model is a cell whose level rises at a pace that grows with the time: the level at t hours is
`5 + pace / 24 * (t + t^2 / 200)` for a pace in a day, so it reaches 5.2 at
`t = -100 + sqrt(10000 + 960 / pace)`. A level that only receives its flow only rises, whatever the
pace of its row, so the first contact of each row's trigger is certain and found on the curve of its
set (`timeline/triggers.py`); the crossing tolerance of a run, 1e-8 h, is well inside this test's
1e-6 h.
"""

from __future__ import annotations

import math

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    SOURCE,
    Builder,
    after,
    assign,
    event,
    flow,
    formula,
    fsum,
    input_,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request

PACES = (0.3, 0.4, 0.25)


def test_each_row_fires_at_the_time_of_its_closed_form():
    b = Builder({'h': {'time': 1}, 'day': ({'time': 1}, 24)})
    cell = b.template(
        'Cell',
        input_('pace', '1/day', 0.3),
        value('level', '', 5, lower=0, upper=10, scale=1),
        value('seen', '', 0, scale=1),
        flow('gain', SOURCE, this.level, request=formula(this.pace * (1 + t / q(100, 'h')))),
        event(
            'high',
            when(this.level >= 5.2, start(this.high), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.seen, 1)),
        ),
    )
    b.table('cells', cell, [{'pace': pace} for pace in PACES])
    b.root(value('seen', '', formula(fsum(cell.instances.seen))))
    program = b.finish()
    record = run(program, Configuration(Request(240)))
    assert record.failure is None, record.failure
    times = sorted(entry.t for entry in record.entries('fire', 'Cell.high.when[0]'))
    exact = sorted(-100 + math.sqrt(10000 + 960 / pace) for pace in PACES)
    assert times == pytest.approx(exact, abs=1e-6)
    assert read(record, program, ['seen'], [240.0])[0].values == (3.0,)
