"""A captured request and capacity keep their separate upstream measurements."""

from dataclasses import replace

import pytest

from napkin.engine import run
from napkin.engine.report import report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text


@pytest.mark.parametrize('full', [True, False])
def test_each_flow_setting_reads_its_own_source(full):
    model = compile_text(
        """scenario "Independent settings"
    horizon 1 h
w:
    input meter: L/h = 4 L/h @meter
    input limit: L/h = 5 L/h @limit
    stock: L = 20 L
    flow tap: this.stock -> SINK @calibration
        request = this.meter
        capacity = this.limit
    reading = formula(this.tap.request)
record calibration: source "Flow calibration."
record meter: source "Request meter."
record limit: source "Maximum."
""",
        {'h': {'time': 1}, 'L': {'volume': 1}},
    )
    expected = {
        'w.tap.request': {'meter', 'calibration'},
        'w.reading': {'meter', 'calibration'},
        'w.tap.capacity': {'limit', 'calibration'},
        'w.tap.actual_rate': {'meter', 'limit', 'calibration'},
    }
    program, cfg = model.program, model.configuration
    if not full:
        keys = tuple(key_of(program, path) for path in expected)
        cfg = replace(cfg, request=replace(cfg.request, everything=False, keys=keys))
    record = run(program, cfg)
    assert record.failure is None
    rows = report(record, program, cfg, expected, [1], table=model.artifact().table).values
    assert {
        row.path: {cite for part in row.trail if part.exercised for cite in part.records} for row in rows
    } == expected
