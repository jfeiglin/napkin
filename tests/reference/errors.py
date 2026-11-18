"""The ways a run of the oracle stops, each with a message that names what it met.

A model error and an execution error both stop the run (`RunFailed`); a `Diagnostic` is one that a
compiler would report before the run. `NotCovered` is the oracle's own limit: it does not guess an
answer for a model that it cannot run exactly. `Paused` is no failure: the run waits for a choice.
"""


class RunFailed(Exception):
    """An execution error: the run stops, and the message names the expression, the invocation and
    the time."""


class Diagnostic(RunFailed):
    """A model that the language refuses. A compiler would report it before the run."""


class Infeasible(RunFailed):
    """The hard conditions of a solve have no answer."""


class NotCovered(Exception):
    """The oracle does not cover this model. The message says what it met."""


class Paused(Exception):
    """The run waits for a choice that nobody has given yet. `decision` describes it."""

    def __init__(self, decision):
        super().__init__(f'the run waits for the choice {decision["key"]}')
        self.decision = decision
