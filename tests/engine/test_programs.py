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
# (S1); endpoints, local sharing, junctions and flows across members (S2); reversible routes and flows
# with legs (S3); events, occurrences, stages, triggers, gates, moves and retirement (the first part
# of S4); draws, choices and inputs that are distributions (the second part of S4). The other
# examples need solvers (S5).
SUBSET = {
    'median_categorical',
    'median_categorical_guarded',
    'dispatcher_forecast',
    'dispatcher_player_sends',
    'dispatcher_player_no_spare',
    'dispatcher_forecast_no_spare',
    'distribution_input',
    'scalar_input_override',
    'scalar_input_default',
    'grinder_refill',
    'grinder_trigger_and_manual',
    'deliveries_current_flows',
    'deliveries_separate_batches',
    'deliveries_shared_supply',
    'deliveries_late_start',
    'shared_limit',
    'same_round_writes',
    'stage_sees_writes',
    'inspect_guard_read_once',
    'inspect_guard_false',
    'clock_trigger',
    'alarm_cooldown',
    'crossing_drain',
    'crossing_rejoin',
    'retirement_failure',
    'rising_ramp',
    'falling_ramp',
    'move_within_bounds',
    'move_over_bound',
    'frozen_formula',
    'lookup_below_first_key',
    'water_service_returns',
    'reversible_route',
    'legs_half_service',
    'legs_zero_leg',
    'legs_all_zero',
    'tank_delivery',
    'unit_division',
    'unit_product',
    'keyed_lookup',
    'reservoir_priority',
    'reservoir_proportional',
    'common_sink',
    'one_pipe',
    'one_pipe_capped_at_source',
    'one_pipe_capped_at_pipe',
    'one_pipe_capped_at_sink',
    'two_junctions',
}
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
    """A yes/no or a text is the same; a number is within 1e-8 of it, relatively: a set whose rates
    move is integrated to the run's tolerance of 1e-9 at each step (the falling ramp's kink at 2.5 h
    costs it 2e-9)."""
    if isinstance(expected, bool | str):
        return found == expected and type(found) is type(expected)
    return found == pytest.approx(float(expected), rel=1e-8, abs=1e-12)


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
    """Each value that the example states, at its own times and at the quarters of the horizon, up
    to the time of a failure, which both runs meet at the same time. A value that the oracle cannot
    read (a keyed read below its first key) is unavailable; a value of an occurrence before its
    start is no value of either."""
    example, record = outcome(name)
    oracle, failed = run_of(example.program, example.configuration)
    assert (failed is None) == (record.failure is None), (failed, record.failure)
    horizon = Fraction(example.configuration.request.horizon)
    if failed is not None:
        assert record.failure.t == pytest.approx(float(oracle.view.t))
        horizon = oracle.view.t
    keys = {item.key for item in example.expected if isinstance(item, At)}
    times = {Fraction(item.t) for item in example.expected if isinstance(item, At) and item.t <= horizon}
    times |= {horizon * k / 4 for k in range(5)}
    for key in sorted(keys, key=str):
        for t in sorted(times):
            if failed is not None and t >= horizon:
                continue  # the oracle's state at its failure is not the record's
            try:
                found = value(record, example.program, key, t)
            except LookupError:
                with pytest.raises(RunFailed):
                    value_at(oracle, example.program, key, t)
                continue
            try:
                expected = value_at(oracle, example.program, key, t)
            except RunFailed:
                assert isinstance(found, Unavailable), (key, t)
                continue
            assert same(found, expected), (key, t)
