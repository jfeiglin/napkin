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

    def __init__(self, time, violations, attempts=()):
        self.violations = tuple(violations)
        self.attempts = tuple(attempts)
        amounts = {row[:3]: row[3:] for row in attempts}
        messages = []
        for store, side, connection in self.violations[:5]:
            way = 'into' if side == 'inflow' else 'out of'
            owner = store.rsplit('.', 1)[0]
            if (store, side, connection) in amounts:
                quantity, allowance = amounts[store, side, connection]
                messages.append(
                    f'{connection} would correct {store} {side} by {quantity} at t = {time} h '
                    f'with a frozen allowance of {allowance}'
                )
                continue
            messages.append(
                f'the flow {connection} carries a rate {way} {store} at t = {time} h: '
                f'{store} belongs to the finished occurrence {owner}, which is frozen'
            )
        if len(self.violations) > 5:
            messages.append(f'{len(self.violations) - 5} more')
        super().__init__('. '.join(messages))


class PlacementConflict(RunFailed):
    """The accepted trajectory misses a target of an incompatible placement group."""

    def __init__(self, time, placements, reasons=()):
        self.placements = placements
        self.reasons = reasons
        details = ', '.join(f'{name} at {actual} with target {target}' for name, actual, target in placements)
        names = ', '.join(dict.fromkeys(name for name, _, _ in placements))
        super().__init__(
            '. '.join((f'incompatible crossing levels of {names} at {time} h: {details}', *reasons))
        )


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
