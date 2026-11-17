"""The scenario's finite damage endpoints follow independent accounting."""

import math

import pytest

from napkin.engine import sample_result
from scenarios.heat_wave_blackout.tests.electricity_damage_support import OUTPUTS as OUTPUTS
from scenarios.heat_wave_blackout.tests.electricity_damage_support import TIMES as TIMES
from scenarios.heat_wave_blackout.tests.electricity_damage_support import default_run as default_run

pytestmark = pytest.mark.deep


def test_every_electricity_path_reports_all_damage_endpoints():
    sid = 'heat_wave_blackout'
    report = sample_result(default_run(sid), TIMES)
    names = OUTPUTS
    for item in report['runs'].values():
        for sample in item['samples']:
            values, statuses = (sample['values'], sample['statuses'])
            for key in (names['deaths'], names['casualties'], names['economic']):
                assert statuses[key] == 'estimated'
                assert math.isfinite(values[key]) and values[key] >= -1e-08
            assert values[names['casualties']] >= values[names['deaths']]
            assert values[names['casualties']] <= values[names['exposure']] + 0.01
            assert values[names['economic']] == pytest.approx(
                sum(values[k] for k in names['accounts']), abs=1e-09
            )
