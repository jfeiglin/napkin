"""Run from the audited checkout: the value and its source use the exact same named unit."""
import pytest

from napkin.model.compile import load_scenario
from tests.evidence.support import evidence_library, fixture_claim, write_package
from tools import check


@pytest.mark.parametrize('power', [0.5, 0.1])
def test_a_quantity_has_the_dimension_of_its_own_unit(tmp_path, power):
    lib = evidence_library()
    lib['assumptions'] = []
    lib['claims'] = [fixture_claim('C-ACCESS', data={'threshold': {'value': 1, 'unit': 'scaled'}})]
    lib['units']['scaled'] = {'dimensions': {'time': power}, 'scale': 1, 'description': 'Time to a power.'}
    model = '''scenario "Fractional dimensions"
    horizon 1 h
    library "../library"
site:
    input x: scaled = 1 scaled @measured
record measured: source "Measured threshold."
    claims:
        C-ACCESS
            datum: threshold
'''
    entry = write_package(tmp_path, {'model.scn': model}, lib)
    problems = [p.message for p in load_scenario(entry).reports]
    assert (problems, check.evidence(('SC99',), tmp_path)) == ([], 0)
