"""Published run orderings computed from the public IV program's terminal readings."""

import json
from itertools import pairwise
from pathlib import Path

import pytest

from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import readings, record


def orders():
    return json.loads(Path(__file__).with_name('expected-orders.json').read_text())


def ordered(values):
    return all(x is not None for x in values) and all(a <= b + 1e-8 for a, b in pairwise(values))


@pytest.mark.parametrize(('runs', 'outputs'), orders())
def test_completed_runs_preserve_the_expected_order(runs, outputs):
    totals = [readings(record(run), outputs, [1440]) for run in runs]
    for key in outputs:
        assert ordered([row[key][0] for row in totals]), (runs, key)


def test_the_order_control_rejects_both_an_unestimated_value_and_a_fall():
    assert ordered([1.0, 1.0, 1.0])
    assert not ordered([1.0, 1.0, 0.5])
    assert not ordered([1.0, 1.0, None])
