"""Independent acceptance outcomes and the access of each run.

The consequence fixtures keep their literal inputs and independent formulas. Supply acceptance uses fixed
qualification work, explicit resource rates and a physical receipt lag.
"""


def keeps_access(model, run):
    """Whether a run's attacker keeps hidden access after its first strike: the run names the one
    option of the file that sets a start state, the attacker's access."""
    (access,) = model.start_options
    return access in model.runs[run]['options']
