"""A one-piece request admits the median counter and stops samples that change it."""

import pytest

from napkin.engine.sampling import sample_seed
from tests.engine.study_request_cases import study_case


@pytest.mark.parametrize('selection', ['other', 'full', 'selected'])
def test_the_central_run_records_the_requested_counter(selection):
    _, outcomes = study_case(0, 1, selection, 1)
    expected, actual = outcomes['central']
    assert actual == expected


@pytest.fixture(scope='module')
def ten_samples():
    _, outcomes = study_case(0, 1, 'selected', 10)
    return outcomes


@pytest.mark.parametrize('index', range(10))
def test_a_one_piece_sample_agrees_with_a_standalone_run(ten_samples, index):
    expected, actual = ten_samples[sample_seed(0, index)]
    assert actual == expected


def test_the_study_refuses_when_any_standalone_sample_exhausts_its_budget(ten_samples):
    assert ten_samples['refusal'] == (True, True)


def test_two_pieces_fit_every_sample():
    _, outcomes = study_case(0, 2, 'selected', 10)
    assert outcomes['refusal'] == (False, False)
    assert all(actual == expected for expected, actual in outcomes.values())
