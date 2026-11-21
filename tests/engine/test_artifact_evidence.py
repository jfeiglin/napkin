"""An artifact and its source give the same evidence for the same cached physical record."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from napkin import store
from napkin.engine.report import report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text
from napkin.program.artifact import loads

METERS = """scenario "Meters"
    horizon 1 h
Cell:
    input reading: L = 0 L
north: Cell
    reading = 2 L @north_meter
south: Cell
    reading = 3 L @south_meter
total = formula(sum(Cell.instances.reading))
record north_meter: source "Northern meter."
record south_meter: source "Southern meter."
"""
UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def test_only_the_artifact_is_available_in_a_fresh_process(tmp_path):
    model = compile_text(METERS, UNITS)
    (tmp_path / 'meters.program').write_bytes(model.artifact().data())
    reader = """
import json
from napkin.engine import run
from napkin.engine.report import report
from napkin.program.artifact import load
from napkin.program.config import Configuration, Request
artifact = load('meters.program')
config = Configuration(Request(1))
record = run(artifact.program, config)
out = report(record, artifact.program, config, ['total'], [1], table=artifact.table)
print(json.dumps([out.values[0].values, out.records]))
"""
    result = subprocess.run(
        [sys.executable, '-B', '-c', reader],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2]), 'NAPKIN_STORE': 'off'},
    )
    assert json.loads(result.stdout) == [
        [5],
        [['north_meter', 'source', 'Northern meter.'], ['south_meter', 'source', 'Southern meter.']],
    ]


def test_cached_record_uses_the_current_artifacts_citations_in_either_query_order(tmp_path):
    original = compile_text(METERS, UNITS)
    edited = compile_text(METERS.replace('Northern meter.', 'Calibrated northern meter.'), UNITS)
    keys = tuple(key_of(original.program, x) for x in ('total', 'north.reading'))
    config = replace(
        original.configuration, request=replace(original.configuration.request, everything=False, keys=keys)
    )
    before = dict(store.counts)
    with store.use(tmp_path):
        record = store.run(original.program, config)
        changed = loads(edited.artifact().data())
        reordered = replace(config, request=replace(config.request, keys=tuple(reversed(keys))))
        cached = store.run(changed.program, reordered)
    assert store.counts['hits'] - before['hits'] == 1
    assert store.counts['misses'] - before['misses'] == 1
    for paths in (['total', 'north.reading'], ['north.reading', 'total']):
        old = report(record, original.program, config, paths, [1], table=original.table)
        new = report(cached, changed.program, reordered, paths, [1], table=changed.table)
        assert {row.path: row.values for row in old.values} == {row.path: row.values for row in new.values}
        assert dict((n, t) for n, _, t in old.records)['north_meter'] == 'Northern meter.'
        assert dict((n, t) for n, _, t in new.records)['north_meter'] == 'Calibrated northern meter.'
        assert {
            r.path: {c for part in r.trail if part.exercised for c in part.records} for r in new.values
        } == {'total': {'north_meter', 'south_meter'}, 'north.reading': {'north_meter'}}


def test_reloaded_evidence_follows_the_live_pipe_fields_in_query_order():
    from napkin.engine import run

    source = """scenario "Live rates"
    horizon 3 h
w:
    input slow: L/h = 1 L/h @slow
    input fast: L/h = 2 L/h @fast
    water: L = 30 L
    draw = event(late: bool):
        flow pipe: this.water -> SINK
            request = formula(this.fast if late else this.slow)
        after 1.5 h
    delayed = event():
        after 1 h:
            this.draw.start(true)
    demand = formula(sum(this.water.outflow.flows.request))
w.draw.start(false)
w.delayed.start()
record slow: source "Slow reading."
record fast: source "Fast reading."
"""
    model = compile_text(source, UNITS)
    artifact = loads(model.artifact().data())
    path = 'w.demand'
    key = key_of(artifact.program, path)
    request = replace(model.configuration.request, everything=False, keys=(key,))
    config = replace(model.configuration, request=request)
    physical = run(artifact.program, config)
    for t, value, expected in [
        (1.25, 3, {'slow', 'fast'}),
        (2.75, 0, set()),
        (1.75, 2, {'fast'}),
        (0.5, 1, {'slow'}),
    ]:
        evidence = report(physical, artifact.program, config, [path], [t], table=artifact.table).values[0]
        assert evidence.values == (value,)
        assert {name for part in evidence.trail if part.exercised for name in part.records} == expected
