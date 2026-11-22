"""The scenario's finite damage endpoints follow independent accounting."""

import math

import pytest

from scenarios.heat_wave_blackout.tests.electricity_damage_support import OUTPUTS as OUTPUTS
from scenarios.heat_wave_blackout.tests.electricity_damage_support import TIMES as TIMES
from scenarios.heat_wave_blackout.tests.electricity_damage_support import default_run as default_run
from scenarios.heat_wave_blackout.tests.support import readings

pytestmark = pytest.mark.deep


def test_every_electricity_path_reports_all_damage_endpoints():
    sid = 'heat_wave_blackout'
    for record in default_run(sid).values():
        paths = [OUTPUTS[name] for name in ('deaths', 'casualties', 'economic', 'exposure')]
        values = readings(record, [*paths, *OUTPUTS['accounts']], TIMES)
        for i, t in enumerate(TIMES):
            deaths, casualties, economic, people = (values[name][i] for name in paths)
            assert all(math.isfinite(x) and x >= -1e-8 for x in (deaths, casualties, economic)), t
            assert deaths <= casualties <= people + 0.01
            assert economic == pytest.approx(sum(values[k][i] for k in OUTPUTS['accounts']), abs=1e-9)
