"""Each methods page of the catalogue states each limit of its results once."""

import pytest

from tests.helpers import SCENARIO_IDS, catalogue_model
from tools.publish.methods import scenario_methods
from tools.publish.pages import review_of


def one_line(text):
    return ' '.join(text.split())


@pytest.mark.parametrize('sid', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_a_methods_page_states_each_limit_of_its_results_once(sid):
    model = catalogue_model(sid)
    page = one_line(scenario_methods(model, link=lambda target: target))
    for item in review_of(model.scenario.notes).get('limitations', []):
        assert page.count(one_line(item['statement'])) == 1, item['id']
