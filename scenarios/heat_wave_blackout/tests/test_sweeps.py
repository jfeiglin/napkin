"""The scenario's sweeps (`[[sweep]]` in its brief settings, the rows of its run table) vary the defenders
and the exposure, never the AI operation or the setting."""

from tests.helpers import catalogue_model
from tools.publish.brief import brief_of

# The AI operation and the setting stay as selected in every sweep.
FIXED = (
    'ai.obeys',
    'ai.reaction_time',
    'ai.rework_share',
    'job.run_time',
    'supply.people_served',
    'compound.held',
)


def test_no_sweep_edits_the_ai_operation_or_the_setting():
    sweeps = brief_of(catalogue_model('heat_wave_blackout')).sweeps
    assert sweeps
    for sweep in sweeps:
        assert not {name for name, _ in sweep.values} & set(FIXED), sweep.id
