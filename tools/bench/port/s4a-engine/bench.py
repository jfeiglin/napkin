"""The benchmark of S4a-E: places, each with an event that a clock starts every few hours and whose
occurrence owns a flow from its place for an hour.

    .venv/bin/python tools/bench/port/s4a-engine/bench.py PLACES HOURS PHASES

Each place holds 100 L. Its clock (`when t >= phase`, `reset after period`) starts `ship`, whose
occurrence owns `out: this.stock -> SINK` at 1 L/h and waits 1 h, so its flow joins at the start and
leaves at the finish. The phases of the places are `PHASES` distinct quarters of an hour (the places
share them in turn), so each moment starts and finishes `PLACES / PHASES` occurrences. It prints the
time to build the program, to plan it, and to run and record it, and checks one place by hand: a
place ships 1 L at each of its starts.
"""

from __future__ import annotations

import sys
import time

from napkin.engine import read
from napkin.engine.timeline import Plan, Run
from napkin.program.build import (
    SINK,
    Builder,
    after,
    event,
    flow,
    input_,
    q,
    reset_after,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request


def build(places, phases):
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    place = b.template(
        'Place',
        input_('phase', 'h', 0),
        input_('period', 'h', 3),
        value('stock', 'L', 100, lower=0),
        event(
            'ship',
            flow('out', this.stock, SINK, request=q(1, 'L/h')),
            after(q(1, 'h')),
            when(t >= this.phase, start(this.ship), reset=reset_after(this.period)),
        ),
    )
    b.table('places', place, [{'id': f'p{k:06d}', 'phase': (k % phases) / 4} for k in range(places)])
    return b.finish()


def main(places=30000, hours=48, phases=12):
    begun = time.perf_counter()
    program = build(places, phases)
    built = time.perf_counter()
    configuration = Configuration(Request(hours))
    plan = Plan.of(program, configuration)
    planned = time.perf_counter()
    record = Run(plan).run()
    ran = time.perf_counter()
    assert record.failure is None, record.failure
    starts = len(record.entries('start'))
    first = read(record, program, ['places.p000000.stock'], [float(hours)])[0].values[0]
    expected = 100 - len([k for k in range(10**6) if 3 * k <= hours - 1])  # phase 0: one litre a start
    assert first == expected, (first, expected)
    print(
        f'{places} places, {phases} phases, {hours} h: build {built - begun:.9f} s, plan {planned - built:.9f} s, '
        f'run+record {ran - planned:.9f} s; {starts} starts; p0 stock {first:g} L (by hand {expected} L)'
    )


if __name__ == '__main__':
    main(*(int(arg) for arg in sys.argv[1:]))
