"""Finite electricity damage endpoints checked against independently authored mathematics."""

from tests.helpers import catalogue_default, catalogue_model

TIMES = (0, 6, 12, 24, 48, 84, 120, 168)

OUTPUTS = {
    'deaths': 'deaths',
    'casualties': 'casualties',
    'exposure': 'supply.people_followed',
    'economic': 'economic_loss',
    'accounts': ('interruption_cost', 'crews.restoration_cost', 'support_cost', 'clinical_cost'),
}


def model(scenario_id):
    return catalogue_model(scenario_id)


def default_run(scenario_id):
    return catalogue_default(scenario_id)
