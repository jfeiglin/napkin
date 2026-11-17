"""Thresholds between outcomes of real runs (docs/python-api.md, "Dynamics").

Where a run has two stable equilibria, the set of start states and inputs from which it reaches each
one is its basin. `threshold` finds, by bisection, the value of one number at which the class of a run's
end changes: the smallest surge that tips a run into the other basin, or the start value on the
boundary between the basins. Each evaluation is a run of the engine, with every check of a study, so a
threshold rests on the dynamics as they run, not on the linear part at an equilibrium.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import expr as nodes
from ..engine.runtime import simulate
from ..engine.study import edits_for, evaluate_study
from ..model.ir import thaw


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


def input_threshold(model, run, name, low, high, classify, *, tol, values=None, numerical_settings=None):
    """The value of the input `name` (in its own unit) where the class of the run's end changes.
    `classify` reads the completed run `{'resolved', 'trajectory'}` of a study."""

    def evaluate(value):
        edits = edits_for(model, {'runs': {run: {**dict(values or {}), name: value}}})
        study = evaluate_study(model, edits, numerical_settings, runs=[run])
        if not study.admissible:
            raise ValueError(f'The study rejects {name} = {value}: {study.diagnostics[:1]}')
        return study.runs[run]

    return threshold(evaluate, classify, low, high, tol=tol)


def state_threshold(model, run, quantity, low, high, classify, *, tol, values=None, numerical_settings=None):
    """The start value of `quantity` (in its own unit) where the class of the run's end changes.
    `classify` reads the trajectory. The start value replaces the quantity's start expression, and the
    engine checks the bounds at t = 0."""
    rs = model.resolve(run, values)
    library = thaw(model.library)
    quantities = rs.quantities
    if quantity not in quantities:
        raise KeyError(f'{quantity} is not a quantity of the run')

    unit = quantities[quantity].unit

    def evaluate(value):
        initial = nodes.call('q', [nodes.written(float(value)), nodes.const(unit)])
        start = quantities[quantity].changed(initial=initial)
        return simulate(rs.with_part('quantities', quantity, start), library, numerical_settings)

    return threshold(evaluate, classify, low, high, tol=tol)
