"""The shared fixtures of the package's tests. The root conftest.py rewrites the assertions of every
module of the catalogue's tests."""

import pytest

from tests.result_cache import result_cache


@result_cache(maxsize=8)
def _run_trajectory(run):
    from napkin.engine import evaluate_study
    from tests.helpers import catalogue_model

    study = evaluate_study(catalogue_model('cyber_learning_loop'), runs=[run])
    assert study.admissible, study.diagnostics
    return study.runs[run]['trajectory']


@pytest.fixture(scope='session')
def trajectory_of():
    """`trajectory_of(run)`: the trajectory of one standard run of the scenario, simulated alone (the run store keeps
    it). A study without edits (`catalogue_study`) simulates every standard run, so a test of one run would
    wait for all of them and fail with any of them."""
    return _run_trajectory
