"""Independent sampled/analytic migration controls for the two already-translated examples."""

from dataclasses import replace
from fractions import Fraction as F
from itertools import product
from pathlib import Path

import pytest

import napkin
from napkin.program.config import InputValue, Quantity

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PIANO = ROOT / 'examples' / 'piano_tuners' / 'model.scn'
RESERVOIR = HERE / 'translated' / 'now' / 'examples' / 'reservoir' / 'model.scn'


@pytest.mark.parametrize('seed', range(12))
def test_sampled_piano_balance_and_tuning_rate(seed):
    model = napkin.load_scenario(PIANO)
    record = napkin.run(model.program, replace(model.configuration, mode='sampled', seed=seed))
    assert record.failure is None and record.end == 8760, record.failure
    times = [0, 4380, 8760]
    rate, actual, due, done, visible = napkin.read(record, model.program, [
        'tuners.rate', 'tuners.tune.actual_rate', 'tuners.due', 'tuners.done', 'tunings_done',
    ], times)
    # Each realization uses its own draw, which is constant. The default 5000 tunings cannot
    # be exhausted by three tuners at any permitted PERT draw in one year.
    (draw,) = set(rate.values)
    assert 600 <= draw <= 1200
    per_year = 3 * draw
    unit = actual.unit
    assert unit in ('tunings/year', 'tunings/h'), unit
    assert actual.values == pytest.approx([per_year if unit.endswith('year') else per_year / 8760] * 3)
    expected = [per_year * t / 8760 for t in times]
    assert done.values == pytest.approx(expected)
    assert visible.values == pytest.approx(expected)
    assert due.values == pytest.approx([5000 - x for x in expected])


def duration_above(start, slope, hours, threshold):
    if slope == 0:
        return hours if start >= threshold else 0
    crossing = min(hours, max(0, (threshold - start) / slope))
    return hours - crossing if slope > 0 else crossing


@pytest.mark.parametrize(('inflow', 'spill', 'risk'), list(product(('0.03', '0.06'), ('0.06', '0.15'), ('0.6','0.7','0.8'))))
def test_reservoir_analytic_sweep(inflow, spill, risk):
    model = napkin.load_scenario(RESERVOIR)
    inputs = tuple(InputValue('reservoir', name, Quantity(F(number), unit)) for name, number, unit in (
        ('inflow', inflow, 'fraction/day'), ('spillway', spill, 'fraction/day'), ('risk', risk, 'fraction'),
    ))
    record = napkin.run(model.program, replace(model.configuration, inputs=inputs))
    assert record.failure is None and record.end == 120, record.failure
    incoming, outgoing = F(inflow) / 24, F(spill) / 24
    threshold, initial, opening_level = F(risk), F('0.6'), F('0.7')
    opening = (opening_level - initial) / incoming
    # At all twelve settings water remains positive once the gate has opened.
    times = [0, 24, 40, 60, 96, 120]
    found = napkin.read(record, model.program, ['reservoir.water', 'reservoir.spilled', 'reservoir.risk_time'], times)
    for i, at in enumerate(times):
        closed, opened = min(at, opening), max(0, at - opening)
        water = initial + incoming * closed + (incoming - outgoing) * opened
        spilled = outgoing * opened
        hours = duration_above(initial, incoming, closed, threshold)
        hours += duration_above(opening_level, incoming - outgoing, opened, threshold)
        for row, exact in zip(found, (water, spilled, hours), strict=True):
            # The migration checker's established relative and absolute tolerances, in the output unit.
            assert row.values[i] == pytest.approx(float(exact), rel=1e-6, abs=1e-8), (at, row.path, exact)
