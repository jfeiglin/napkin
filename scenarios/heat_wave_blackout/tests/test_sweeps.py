"""Published sweeps vary public protection and heat assumptions under the same observed outage."""

from scenarios.heat_wave_blackout.tests.support import model
from tools.publish.brief import brief_of


def test_sweeps_hold_the_observed_incident_and_population_fixed():
    sweeps = brief_of(model()).sweeps
    assert sweeps
    for sweep in sweeps:
        assert all(not key.startswith(('incident.', 'extra.')) for key, _ in sweep.values), sweep.id
        assert not {'supply.people_served', 'compound.held'} & dict(sweep.values).keys(), sweep.id
