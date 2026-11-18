"""The run configuration (`napkin/program/config.py`).

The limits start at the defaults of D6; a median run has no seed and a sampled run needs one; an
input, a controller and a pick are each given once; a limit, a budget and a numerical setting are
positive; the horizon is a number of hours.
"""

import pytest

from napkin.program.config import (
    MEDIAN,
    PLAYER,
    SAMPLED,
    Budgets,
    Configuration,
    ConfigurationError,
    Controller,
    InputValue,
    Limits,
    Numerics,
    Pick,
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
        {'controllers': (Controller('dispatcher', 'oracle'),)},
        {'controllers': (Controller('dispatcher', PLAYER),) * 2},
        {'picks': (Pick('depot.ask.step[0].do[0].choice[0]', 'depot.ask#0', 'SEND'),) * 2},
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
