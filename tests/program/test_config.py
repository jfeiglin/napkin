"""The run configuration (`napkin/program/config.py`).

The limits start at the defaults of D6; a median run has no seed and a sampled run needs one; an
input is given once; a limit, a budget and a numerical setting are positive; the horizon is a
number of hours.
"""

import pytest

from napkin.program.config import (
    MEDIAN,
    SAMPLED,
    Budgets,
    Configuration,
    ConfigurationError,
    InputValue,
    Limits,
    Numerics,
    Quantity,
    Request,
)


def test_the_limits_start_at_the_defaults_of_d6():
    assert (Limits().max_occurrences, Limits().max_active, Limits().max_rounds) == (1_000_000, 100_000, 1_000)


def test_a_run_is_median_by_default_and_records_everything():
    configuration = Configuration(Request(2))
    assert configuration.mode == MEDIAN and configuration.seed is None
    assert configuration.request.everything and configuration.request.pieces == 10_000_000


@pytest.mark.parametrize(
    'settings',
    [
        {'mode': MEDIAN, 'seed': 3},
        {'mode': SAMPLED},
        {'mode': SAMPLED, 'seed': True},
        {'mode': 'mean'},
        {'inputs': (InputValue('tank', 'water', Quantity(9, 'L')),) * 2},
    ],
)
def test_a_configuration_that_no_run_can_take_is_refused(settings):
    with pytest.raises(ConfigurationError):
        Configuration(Request(1), **settings)


@pytest.mark.parametrize(
    'make',
    [
        lambda: Limits(max_rounds=0),
        lambda: Limits(max_active=-1),
        lambda: Budgets(fair_programs=0),
        lambda: Numerics(rtol=0.0),
        lambda: Request(-1),
        lambda: Request('2 h'),
    ],
)
def test_a_setting_out_of_its_range_is_refused(make):
    with pytest.raises(ConfigurationError):
        make()


def test_a_sampled_run_has_its_seed():
    assert Configuration(Request(1), mode=SAMPLED, seed=7).seed == 7


def test_a_requests_horizon_is_held_as_the_run_holds_a_time():
    """A horizon is a time as the run holds every time (`engine.timeline.moment.Clock`): its exact
    value rounded once to a float, whoever made the request. So the exact 36/5 h of `0.3 days` is the
    float 7.2, the time that a caller writes as `7.2 h`, and the record of the run, whose manifest
    takes the request's horizon, holds a value at it."""
    from fractions import Fraction

    from napkin.program.config import Request

    for given, held in ((Fraction(36, 5), 7.2), (10, 10.0), (7.2, 7.2), (Fraction(1, 3), 1 / 3)):
        horizon = Request(given).horizon
        assert type(horizon) is float and horizon == held
