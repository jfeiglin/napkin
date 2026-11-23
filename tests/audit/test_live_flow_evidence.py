"""A sum of live incident requests credits the measurements behind exactly those requests."""

from dataclasses import replace

import pytest

from napkin.engine import run
from napkin.engine.report import report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text

SOURCE = """scenario "Incident requests"
    horizon 3 h
w:
    input slow: L/h = 1 L/h @slow
    input fast: L/h = 2 L/h @fast
    water: L = 100 L
    drain = event(quick: bool):
        wish = formula(this.fast if quick else this.slow)
        flow pipe: this.water -> SINK
            request = formula(wish)
        after 1.5 h
    again = event():
        after 1 h:
            this.drain.start(true)
    all_wish = formula(sum(this.water.outflow.flows.request))
w.drain.start(false)
w.again.start()
record slow: source "Slow pump measurement."
record fast: source "Fast pump measurement."
"""


@pytest.mark.parametrize('full', [True, False], ids=['full', 'selected'])
def test_sources_follow_only_pipes_incident_at_the_report_time(full):
    c = compile_text(SOURCE, {'h': {'time': 1}, 'L': {'volume': 1}})
    config = c.configuration
    path = 'w.all_wish'
    if not full:
        config = replace(
            config, request=replace(config.request, everything=False, keys=(key_of(c.program, path),))
        )
    r = run(c.program, config)
    assert r.failure is None
    observed = []
    for t in (1.25, 2.75, 0.5, 1.75):
        (row,) = report(r, c.program, config, [path], [t], model=c.declared).values
        observed.append(
            (row.values[0], {source for part in row.trail if part.exercised for source in part.records})
        )
    assert observed == [(3, {'fast', 'slow'}), (0, set()), (1, {'slow'}), (2, {'fast'})]
