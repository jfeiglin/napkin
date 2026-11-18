"""The worked models of the spec (`tests/program/examples.py`) on the engine.

Each example either runs and gives the results that the spec states, and the oracle's results
(`tests/reference/from_program.py`) at the same times and at times between them, or the engine
refuses it with the slice of the rewrite that brings what it lacks (`Outside`). The expected values
are the examples' own; none comes from a run of the engine.
"""

from __future__ import annotations

import re
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Outside
from napkin.program.record import Unavailable
from tests.program.examples import EXAMPLES, At, Fails, Traced
from tests.reference.errors import RunFailed
from tests.reference.from_program import run_of, value_at

# The examples of the subsets of the slices so far: inputs, stored values with bounds, formulas and
# directed flows with a request and a capacity (S0); templates, tables, collections and keyed reads
# (S1). The other examples with collections also need a later slice: events, sharing, legs, solvers.
SUBSET = {'tank_delivery', 'unit_division', 'unit_product', 'keyed_lookup'}
SLICE = re.compile(r'\((S[0-6]|C)(, S[0-6])*\)$')


def outcome(name):
    """(the example, its record), or (the example, the refusal)."""
    example = EXAMPLES[name]()
    try:
        return example, run(example.program, example.configuration)
    except Outside as refusal:
        return example, refusal


def value(record, program, key, t):
    (reading,) = read(record, program, [key], [float(t)])
    return reading.values[0]


def same(found, expected):
    if isinstance(expected, bool):
        return found is expected
    return found == pytest.approx(float(expected), rel=1e-9, abs=1e-12)


def test_the_subset_of_this_slice_runs():
    ran = {name for name in EXAMPLES if not isinstance(outcome(name)[1], Outside)}
    assert ran >= SUBSET


@pytest.mark.parametrize('name', sorted(EXAMPLES))
def test_an_example_gives_its_results_or_is_refused_by_its_slice(name):
    example, found = outcome(name)
    if isinstance(found, Outside):
        assert name not in SUBSET, found
        assert SLICE.search(str(found)), f'the refusal names no slice: {found}'
        return
    record = found
    failure = next((item for item in example.expected if isinstance(item, Fails)), None)
    if failure is None:
        assert record.failure is None, record.failure
    else:
        assert failure.message in record.failure.detail('message')
        if failure.t is not None:
            assert record.failure.t == pytest.approx(float(failure.t))
    for item in example.expected:
        if isinstance(item, At):
            assert same(value(record, example.program, item.key, item.t), item.value), item
        elif isinstance(item, Traced):
            entries = record.entries(item.kind, item.part)
            assert [entry.t for entry in entries] == pytest.approx([float(t) for t in item.times]), item
            if item.rounds is not None:
                assert [entry.round for entry in entries] == list(item.rounds), item


@pytest.mark.parametrize('name', sorted(SUBSET))
def test_an_example_of_the_subset_agrees_with_the_oracle(name):
    """Each value that the example states, at its own times and at the quarters of the horizon. A
    value that the oracle cannot read (a keyed read below its first key) is unavailable."""
    example, record = outcome(name)
    oracle, failed = run_of(example.program, example.configuration)
    assert failed is None
    horizon = Fraction(example.configuration.request.horizon)
    keys = {item.key for item in example.expected if isinstance(item, At)}
    times = {Fraction(item.t) for item in example.expected if isinstance(item, At)}
    times |= {horizon * k / 4 for k in range(5)}
    for key in sorted(keys, key=str):
        for t in sorted(times):
            found = value(record, example.program, key, t)
            try:
                expected = value_at(oracle, example.program, key, t)
            except RunFailed:
                assert isinstance(found, Unavailable), (key, t)
                continue
            assert same(found, expected), (key, t)
