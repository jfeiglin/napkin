"""Recorded recovery observations from 8488047, including edited responses and the prehistory boundary."""

import gzip
import json
from pathlib import Path

import pytest

from napkin.engine import edits_for
from napkin.engine.report import Lag, report
from napkin.program.record import Unavailable
from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import model, readings, record

FIXTURE = json.loads(gzip.decompress(Path(__file__).with_name('legacy-recovery.json.gz').read_bytes()))
pytestmark = pytest.mark.deep


@pytest.mark.parametrize('label', FIXTURE['cases'])
def test_legacy_stocks_recovery_events_and_reported_outcomes(label):
    case = FIXTURE['cases'][label]
    hours = FIXTURE['hours']
    name = case['run']
    edits = case['edits']
    r = record(name, **edits)
    assert r.end == 1440 and r.failure is None
    expected = case['physical_readings']
    measured = readings(r, [*expected, *case['unmodeled_hold_stocks']], hours)
    for path, values in expected.items():
        assert measured[path] == pytest.approx(values, abs=1e-6, rel=1e-8), path
    for path in case['unmodeled_hold_stocks']:
        assert not any(measured[path]), path
    for event, times in case['recovery_times_h'].items():
        starts = [e.t for e in r.entries('start') if e.owner.split('#')[0] == event]
        assert starts == pytest.approx(times, abs=1e-6), event
    m = model()
    config = m.configure(name, edits_for(m, {'runs': {name: edits}}))
    lag = {path: Lag(h, h) for path, h in FIXTURE['lags_h'].items()}
    observed = report(r, m.program, config, list(case['reported_outcomes']), hours, lag)
    for result in observed.values:
        for t, was, now in zip(hours, case['reported_outcomes'][result.path], result.values, strict=True):
            if result.path in lag and t < FIXTURE['lags_h'][result.path]:
                assert was == 0 and isinstance(now, Unavailable), (result.path, t)
            else:
                assert now == pytest.approx(was, abs=1e-6, rel=1e-8), (result.path, t)
