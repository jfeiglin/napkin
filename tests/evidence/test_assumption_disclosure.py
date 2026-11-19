"""The disclosure of an assumption follows its canonical review status in the library, on a synthetic
model: the stop of the service rests on the assumption A-STOP, and the stop starts in the run."""

import pytest

from napkin.engine.report import report
from napkin.engine.timeline import run
from napkin.model.compile import load_scenario
from tests.evidence.support import SERVICE, evidence_library, write_package
from tools.evidence.trail import disclosures, evidence


@pytest.mark.parametrize('status', ['unreviewed', 'confirmed', 'replaced'])
def test_assumption_disclosure_respects_canonical_review_status(tmp_path, status):
    library = evidence_library()
    library['assumptions'].append(
        {
            'id': 'A-STOP',
            'statement': 'The service stops at its end.',
            'rationale': 'Selected analytic input, subject to independent review.',
            'review': {'status': status},
        }
    )
    text = SERVICE.replace(
        '            assumption RT-FIXTURE\n        when', '            assumption A-STOP\n        when'
    )
    model = load_scenario(write_package(tmp_path, {'model.scn': text}, library))
    record = run(model.program, model.configuration)
    found = report(record, model.program, model.configuration, ['service.served'], [10], model=model.declared)
    (traced,) = evidence(found, model.declared, library)
    assert traced.reached.assumptions == {'A-STOP': status}
    stop = [line for line in disclosures(traced) if 'A-STOP' in line]
    assert stop == ([] if status == 'confirmed' else [f'the assumption A-STOP is {status}'])
