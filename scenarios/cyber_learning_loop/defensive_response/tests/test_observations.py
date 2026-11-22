"""Defensive attention and recovery under observed pressure, independent of its source."""

import json
from dataclasses import replace
from math import exp
from pathlib import Path

import pytest

from napkin.engine import edits_for, read, run
from napkin.model import load_scenario
from tools import catalogue
from tools.publish.brief import brief_of
from tools.publish.readings import render

FOLDER = Path(__file__).resolve().parents[1]
BASELINE = json.loads((FOLDER / 'tests/legacy-readings.json').read_text())
YEAR = 8760


@pytest.fixture(scope='module')
def model():
    compiled = load_scenario(FOLDER / 'model.scn')
    assert not compiled.reports
    return compiled


def replay(model, changes, max_step=None):
    config = model.configure(edits=edits_for(model, {'set': changes}))
    if max_step is not None:
        config = replace(config, numerics=replace(config.numerics, max_step=max_step))
    record = run(model.program, config)
    assert record.stop is None and record.end == 25 * YEAR
    return record


@pytest.mark.parametrize('case', BASELINE['cases'])
def test_retained_defensive_readings_match_the_historical_interpreter(model, case):
    historical = BASELINE['cases'][case]
    record = replay(model, historical['edits'])
    paths = ['observations.pressure', *BASELINE['paths'][1:]]
    actual = read(record, model.program, paths, [year * YEAR for year in BASELINE['years']])
    for index, year in enumerate(BASELINE['years']):
        for previous, current in zip(historical['rows'][index], actual, strict=True):
            assert current.values[index] == pytest.approx(previous, rel=1e-7, abs=1e-8), (
                case,
                year,
                current.path,
                previous,
                current.values[index],
            )


def test_attention_follows_the_pulse_and_recovers_on_both_step_limits(model):
    changes = BASELINE['cases']['pulse']['edits']
    years = [0, 1 - 1e-4, 1, 1.25, 1.75, 2, 2.25, 3, 6, 25]
    high = 0.05 * 6 * 5 / (5 + 6 - 1)
    low = 0.05 * 6 * 0.5 / (0.5 + 6 - 1)
    end_of_pulse = high + (0.05 - high) * exp(-3)
    for step in (7 * 24, 24):
        record = replay(model, changes, step)
        pressure, attention = read(
            record, model.program, ['observations.pressure', 'defender_attention'], [t * YEAR for t in years]
        )
        assert pressure.values == tuple(1 if t < 1 else 5 if t < 2 else 0.5 for t in years)
        for t, observed in zip(years, attention.values, strict=True):
            if t <= 1:
                expected = 0.05
            elif t <= 2:
                expected = high + (0.05 - high) * exp(-3 * (t - 1))
            else:
                expected = low + (end_of_pulse - low) * exp(-3 * (t - 2))
            assert observed == pytest.approx(expected, abs=2e-9), (step, t, observed, expected)


def test_brief_reports_the_defensive_observations_and_the_two_distinct_indices(model):
    assert brief_of(model).show == (
        'observations.pressure',
        'defenders.attention_target',
        'defender_attention',
        'defenders.hardening',
        'defenders.closing',
    )
    record = replay(model, BASELINE['cases']['response']['edits'])
    attention, hardening, remediation = read(
        record,
        model.program,
        ['defender_attention', 'defenders.hardening', 'defenders.closing'],
        [0, 5 * YEAR, 25 * YEAR],
    )
    assert attention.values[0] < attention.values[1] < attention.values[2]
    assert hardening.values == pytest.approx([0.3, 0.55, 1.55])
    assert remediation.values == pytest.approx([2.2] * 3)


def test_catalogue_entry_and_leaf_share_the_defensive_equations(model):
    entry = catalogue.entries()['cyber_learning_loop']
    assert entry.parent == FOLDER.parent
    canonical = load_scenario(entry)
    assert not canonical.reports
    strategic = run(canonical.program, canonical.configure('no_ai'))
    leaf = replay(model, {})
    times = [year * YEAR for year in BASELINE['years']]
    paths = brief_of(model).show
    for left, right in zip(
        read(strategic, canonical.program, paths, times), read(leaf, model.program, paths, times), strict=True
    ):
        assert left.path == right.path and left.values == pytest.approx(right.values)
    assert render(model) == (FOLDER / 'results/readings.md').read_text()
