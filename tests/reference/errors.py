"""The ways a run of the oracle stops, each with a message that names what it met.

A model error and an execution error both stop the run (`RunFailed`); a `Diagnostic` is one that a
compiler would report before the run. `NotCovered` is the oracle's own limit: it does not guess an
answer for a model that it cannot run exactly. `Paused` is no failure: the run stops at a breakpoint.
"""


class RunFailed(Exception):
    """An execution error: the run stops, and the message names the expression, the invocation and
    the time."""


class FrozenTransfer(RunFailed):
    """All the directed legs contributing to the first group of frozen allowance violations."""

    def __init__(self, time, violations):
        self.violations = tuple(violations)
        messages = []
        for store, side, connection in self.violations[:5]:
            way = 'into' if side == 'inflow' else 'out of'
            owner = store.rsplit('.', 1)[0]
            messages.append(
                f'the flow {connection} carries a rate {way} {store} at t = {time} h: '
                f'{store} belongs to the finished occurrence {owner}, which is frozen'
            )
        if len(self.violations) > 5:
            messages.append(f'{len(self.violations) - 5} more')
        super().__init__('. '.join(messages))


class Diagnostic(RunFailed):
    """A model that the language refuses. A compiler would report it before the run."""


class Infeasible(RunFailed):
    """The hard conditions of a solve have no answer."""


class NotCovered(Exception):
    """The oracle does not cover this model. The message says what it met."""


class Paused(Exception):
    """The run stops at a breakpoint. `decision` describes the stop (`Run._stop`)."""

    def __init__(self, decision):
        super().__init__(f'the run stops at {decision["key"]}')
        self.decision = decision
