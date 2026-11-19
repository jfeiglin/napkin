"""Thresholds between outcomes of real runs (docs/python-api.md, "Dynamics").

Where a run has two stable equilibria, the set of start states and inputs from which it reaches each
one is its basin. `threshold` finds, by bisection, the value of one number at which the class of a run's
end changes: the smallest surge that tips a run into the other basin, or the start value on the
boundary between the basins. Each evaluation is a run of the engine (`napkin.engine.run`), with every
check of its start, so a threshold rests on the dynamics as they run, not on the linear part at an
equilibrium. A run that fails stops the search with its failure: no class is guessed for it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..engine.timeline import run
from .field import configured, started


@dataclass(frozen=True)
class Threshold:
    """The class of the end changes between `low` and `high`, from `below` to `above`."""

    low: float
    high: float
    below: object
    above: object
    evaluations: int

    @property
    def value(self):
        return (self.low + self.high) / 2


def threshold(evaluate, classify, low, high, *, tol, max_iterations=200):
    """The value between `low` and `high` where `classify(evaluate(value))` changes, to within `tol`.
    The two ends must give two classes."""
    low, high = float(low), float(high)
    below, above = classify(evaluate(low)), classify(evaluate(high))
    if below == above:
        raise ValueError(f'Both ends give the class {below!r}: no threshold lies between them')
    count = 2
    while high - low > tol and count < max_iterations:
        middle = (low + high) / 2
        found = classify(evaluate(middle))
        count += 1
        if found == below:
            low = middle
        elif found == above:
            high = middle
        else:
            raise ValueError(f'A third class {found!r} lies between the ends')
    return Threshold(low, high, below, above, count)


def _record(program, configuration, what):
    """The record of a run that reaches its horizon; a run that fails raises its failure."""
    record = run(program, configuration)
    if record.failure is not None:
        raise ValueError(f'The run with {what} fails: {record.failure.detail("message")}')
    return record


def input_threshold(program, configuration, name, low, high, classify, *, tol):
    """The value of the input `name` (in its declared unit) where the class of the run's end changes.
    `classify` reads the record of the run (`napkin.engine.read` gives its values)."""

    def evaluate(value):
        return _record(program, configured(program, configuration, {name: value}), f'{name} = {value}')

    return threshold(evaluate, classify, low, high, tol=tol)


def state_threshold(program, configuration, path, low, high, classify, *, tol):
    """The start value of the stored value `path` (in its declared unit) where the class of the run's
    end changes. `classify` reads the record of the run. The start value replaces the store's
    initializer (`started`), and the engine checks its bounds at the start."""

    def evaluate(value):
        return _record(started(program, {path: value}), configuration, f'{path} starting at {value}')

    return threshold(evaluate, classify, low, high, tol=tol)
