"""Shared compiled model for checks of the current cyber workforce catalogue entry."""

import pytest

from tests.helpers import catalogue_model


@pytest.fixture(scope='session')
def workforce_model():
    return catalogue_model('cyber_learning_loop')
