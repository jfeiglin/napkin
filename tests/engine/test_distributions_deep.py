"""Deep checks of distribution quantiles and a catalogue spread."""

from dataclasses import replace

import numpy as np
import pytest

from napkin import distributions
from napkin.engine import SamplingSettings, configurations, monte_carlo
from napkin.engine.sampling import stream
from napkin.engine.timeline.record import key_of
from napkin.model import load_json
from napkin.program.config import Request
from tests.engine import distribution_oracles as oracle
from tests.engine.test_distributions import CASES
from tests.helpers import catalogue_model
from tools.publish.brief import brief_of, spread_document

pytestmark = pytest.mark.deep


@pytest.mark.parametrize('case', list(CASES))
def test_a_million_draws_follow_the_family_s_cdf(case):
    """The empirical cdf of 10^6 draws stays within the DKW bound (failure probability 1e-9) of the
    family's own cdf at 200 points spread over the draws."""
    family, args = CASES[case]
    n = 1_000_000
    # A study takes at most 100,000 samples; the stream itself gives as many numbers as it is asked.
    draws = np.sort(distributions.quantile(family, args, stream(12, 'x').random(n)))
    points = draws[np.linspace(0, n - 1, 200).astype(int)]
    eps = oracle.dkw_epsilon(n)
    for x in points:
        empirical = np.searchsorted(draws, x, side='right') / n
        assert abs(empirical - float(oracle.tails(family, args, x)[0])) <= eps, (case, x)


def test_a_catalogue_spread_samples_and_summarizes_the_declared_input():
    # This recovery spread draws the fraction of water production available under manual
    # operation at startup. We can check both sampled records and their summary at that time.
    model = catalogue_model('water_controls_wipe:washington_dc')
    spec = next(spread for spread in brief_of(model).spreads if spread.id == 'uncertainty')
    run = spec.runs[0]
    edits = load_json(spread_document(model, spec), exact_numbers=True)
    configuration = configurations(model, [run], edits)[run]
    path = 'wssc_water.manual_share'
    request = Request(0, everything=False, keys=(key_of(model.program, path),))
    result = monte_carlo(
        model.program,
        replace(configuration, request=request),
        [path],
        [0],
        SamplingSettings(2, seed=1),
        model=model.table,
    )
    assert result.refused is None, result.refused
    assert len(result.samples) == 2
    draws = [sample.values[0][0] for sample in result.samples]
    assert draws[0] != draws[1] and all(0.3 <= share <= 0.9 for share in draws)
    summary = result.spread(path, 0).summary
    assert summary.central == pytest.approx(0.6)
    assert summary.mean.value == pytest.approx(sum(draws) / len(draws))
