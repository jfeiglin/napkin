"""Independent clinical, toxic-load and resource accounting for restored clinical and industrial damage.

Expected values use fixed reference mathematics and math.erf, independently of
production expressions, source adapters, trajectories and presentation builders.
"""

from napkin.engine import edits_for, evaluate_study
from scenarios.tests.sources import response_of
from tests.helpers import catalogue_model


def model(sid):
    return catalogue_model(sid)


def run(sid, name='subpar', **edits):
    """The study under an edit body (`set`, `options`, ...) and the trajectory of one run."""
    compiled = model(sid)
    result = evaluate_study(compiled, edits_for(compiled, edits))
    assert result.admissible, [d for d in result.diagnostics if d.get('severity') == 'error']
    return result, result.runs[name]['trajectory']


def subpar_response(sid):
    """The defender response of the run `subpar`."""
    return response_of(model(sid), 'subpar')
