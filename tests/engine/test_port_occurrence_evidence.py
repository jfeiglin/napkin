"""At a handoff, a retired pipe's own evidence freezes as the endpoint switches to its successor."""

from dataclasses import replace

import pytest

from napkin.engine import run
from napkin.engine.report import report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text
from napkin.program.artifact import loads


@pytest.mark.parametrize('handoff_first', [False, True])
def test_live_requests_and_a_frozen_pipe_agree_at_the_handoff(handoff_first):
    source = """scenario "Successive shifts"
    horizon 2.5 h
w:
    input slow: L/h = 1 L/h @slow
    input fast: L/h = 2 L/h @fast
    stock: L = 20 L
    shift = event(quick: bool):
        wish = formula(this.fast if quick else this.slow)
        flow pipe: this.stock -> SINK
            request = formula(wish)
        after 1 h
    handoff = event():
        after 1 h:
            this.shift.start(true)
    demand = formula(sum(this.stock.outflow.flows.request))
record slow: source "First shift meter."
record fast: source "Second shift meter."
"""
    starts = ['w.shift.start(false)', 'w.handoff.start()']
    model = compile_text(
        source + '\n'.join(reversed(starts) if handoff_first else starts),
        {'h': {'time': 1}, 'L': {'volume': 1}},
    )
    artifact = loads(model.artifact().data())
    paths = ['w.demand', 'w.shift#0.wish', 'w.shift#1.wish']
    keys = tuple(key_of(artifact.program, path) for path in paths)
    config = replace(
        model.configuration, request=replace(model.configuration.request, everything=False, keys=keys)
    )
    physical = run(artifact.program, config)
    assert physical.failure is None, physical.failure
    # Query away from the handoff, return to the same instant and change path order. A later
    # finish does not change the first shift's frozen reading or the fields credited at hour one.
    for at, expected in [(2, (0, 1, 2)), (1, (2, 1, 2)), (1.5, (2, 1, 2)), (1, (2, 1, 2))]:
        for asked, evidence in [(paths, {'model': model.declared}), (paths[::-1], {'table': artifact.table})]:
            rows = report(physical, artifact.program, config, asked, [at], **evidence).values
            for row in rows:
                value = expected[paths.index(row.path)]
                assert row.values == (value,)
                citations = {ref for part in row.trail if part.exercised for ref in part.records}
                assert citations == {0: set(), 1: {'slow'}, 2: {'fast'}}[value]
