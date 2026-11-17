"""The disclosure of an assumption follows its canonical review status, on synthetic models."""

import pytest

from napkin.engine import evaluate_study
from tests.build import compiled, in_place, library, scenario
from tests.evidence.support import resting


@pytest.mark.parametrize('status', ['unreviewed', 'confirmed', 'replaced'])
def test_assumption_disclosure_respects_canonical_review_status(status):
    lib = library()
    lib['assumptions'] = [
        {
            'id': 'selected-population',
            'statement': 'Ten people in this fixture.',
            'rationale': 'Selected analytic input, subject to independent review.',
            'review': {'status': status},
        }
    ]
    record = in_place(
        'assumption', 'Selected population for the analytic fixture.', assumption='selected-population'
    )
    result = evaluate_study(compiled(resting(scenario(), 'service/n', record), lib))
    assert result.admissible, result.diagnostics
    warnings = [d for d in result.diagnostics if d.get('code') == 'assumption:selected-population']
    if status == 'confirmed':
        assert not warnings
    elif status == 'replaced':
        assert len(warnings) == 1 and 'replaced' in warnings[0]['message']
        assert 'unreviewed' not in warnings[0]['message']
    else:
        assert len(warnings) == 1 and 'unreviewed' in warnings[0]['message']
