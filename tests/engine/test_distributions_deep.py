"""Deep checks of distributions and Monte Carlo studies (`pytest -m deep`): a million draws of every
family against its cdf, Latin samples against random ones, and one small study of a catalogue
scenario. The scenario is the smallest one that the catalogue discovers, by the size of its
structures; the test names none."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from napkin import distributions
from napkin.engine import SamplingSettings, edits_for, evaluate_uncertainty
from napkin.engine.sampling import _open, stream, uniforms
from napkin.engine.uncertainty import uncertainty_report
from napkin.model.model import input_name
from napkin.model.runs import Runs
from napkin.schema import FOLDER as SCHEMAS
from tests.engine import distribution_oracles as oracle
from tests.engine.test_distributions import CASES
from tests.helpers import ALL_SCENARIO_IDS, catalogue_model

pytestmark = pytest.mark.deep


@pytest.mark.parametrize('case', list(CASES))
def test_a_million_draws_follow_the_family_s_cdf(case):
    """The empirical cdf of 10^6 draws stays within the DKW bound (failure probability 1e-9) of the
    family's own cdf at 200 points spread over the draws."""
    family, args = CASES[case]
    n = 1_000_000
    # A study takes at most 100,000 samples; the stream itself gives as many numbers as it is asked.
    draws = np.sort(distributions.quantile(family, args, _open(stream(12, 'x'), n)))
    points = draws[np.linspace(0, n - 1, 200).astype(int)]
    eps = oracle.dkw_epsilon(n)
    for x in points:
        empirical = np.searchsorted(draws, x, side='right') / n
        assert abs(empirical - float(oracle.tails(family, args, x)[0])) <= eps, (case, x)


def test_latin_means_are_within_one_stratum_and_random_means_within_hoeffding():
    """For a monotone image of one draw, the mean of N Latin samples is within (max - min) / N of the
    true mean for every seed; the mean of N random samples is within Hoeffding's bound."""
    family, args = CASES['pert']
    mean, _ = (float(v) for v in oracle.moments(family, args))
    width = args['max'] - args['min']
    for n in (100, 1000, 10_000):
        for seed in range(5):
            latin = distributions.quantile(
                family, args, uniforms(['x'], SamplingSettings(n, seed=seed, method='latin'))['x']
            )
            randomly = distributions.quantile(
                family, args, uniforms(['x'], SamplingSettings(n, seed=seed))['x']
            )
            assert abs(latin.mean() - mean) <= width / n
            assert abs(randomly.mean() - mean) <= width * oracle.hoeffding_epsilon(n, 1e-9 / 15)


def smallest_scenario():
    def size(scenario_id):
        structures = catalogue_model(scenario_id).structures.values()
        return sum(len(json.dumps(structure.plain(), default=str)) for structure in structures)

    return min(ALL_SCENARIO_IDS, key=size)


def test_a_small_study_of_the_smallest_scenario_runs_two_samples():
    """The first input of a number with a range takes a narrow uniform distribution around its own
    value, through an edit; the study runs its central run and two samples of its first default run,
    and the report keeps the schema."""
    model = catalogue_model(smallest_scenario())
    table = Runs.from_table(model.run_table)
    name, item = next(
        (name, item)
        for name, item in table.inputs.items()
        if not item.fixed
        and item.range is not None
        and model.inputs[input_name(name)]['distribution'] is None
    )
    low, high = item.range
    value = model.inputs[input_name(name)]['value']
    spread = (high - low) / 1000
    lower, upper = max(low, value - spread), min(high, value + spread)
    written = f'uniform({lower!r} {item.unit}, {upper!r} {item.unit})'
    run = next(iter(model.runs))
    result = evaluate_uncertainty(
        model, edits_for(model, {'set': {name: written}}), SamplingSettings(2, seed=1), runs=[run]
    )
    assert result.admissible, [d for d in result.diagnostics if d.get('severity', 'error') == 'error']
    assert len(result.samples[run]['runs']) == 2
    for values in result.samples[run]['values']:
        assert lower <= values[input_name(name)] <= upper
    report = uncertainty_report(result)
    schema = json.loads((SCHEMAS / 'report.schema.json').read_text(encoding='utf-8'))
    assert not list(Draft202012Validator(schema).iter_errors(report))
    summaries = report['uncertainty']['runs'][run]['outcomes']
    assert all(
        point['estimated'] is False or math.isfinite(point['mean'])
        for outcome in summaries.values()
        for point in outcome['points'].values()
    )
