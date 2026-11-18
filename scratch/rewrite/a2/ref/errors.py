"""The ways a run stops, each with a message that names what it met."""


class RunFailed(Exception):
    """An execution error: the run stops and reports the expression, the invocation and the time."""


class Diagnostic(RunFailed):
    """A model that the language refuses. A compiler would report it before the run."""


class Infeasible(RunFailed):
    """The hard conditions of a solve have no answer."""


class NotCovered(Exception):
    """The reference interpreter does not cover this model. The text says what it met."""


class Paused(Exception):
    """The run needs a choice that nobody has given yet."""

    def __init__(self, decision):
        super().__init__(f'the run waits for the choice {decision["key"]}')
        self.decision = decision
