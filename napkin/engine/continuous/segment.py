"""One segment of the continuous part of a run: the step that an engine takes between two moments.

`advance` is that step. The timeline engine (`engine/timeline/component.py`) takes it for one
connected set of stores and flows. It gives the step a system, the state that changes, a field, the
level rules that are watched and the context of the run (`system.Context`); the step reads nothing
else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core.errors import ExpressionError
from .bounds import depart_faces, hold_zero_faces, rounded_faces
from .integrate import numerical_segment, release_root, segment_roots
from .kernels import Classifier, affine_segment, compartment_solution


@dataclass
class Advance:
    """What `advance` found from the present time and state of a run.

    - `rounded`: the stock faces that the state reaches within the roundoff of the time ({quantity
      index: bound}). No segment was made: the caller settles them and asks again.
    - else `end` and `solution`: the segment, as a function of the time that gives the state. `exact`
      says that a closed form gives it; else `numerical` is the result of the solver, whose accepted
      steps the caller checks. `targets` are the bounds that the state reaches at the end ({quantity
      index: bound}), and `due` the watched level rules whose crossing is at the end.
    """

    rounded: dict | None = None
    end: float | None = None
    solution: Any = None
    targets: dict | None = None
    due: tuple = ()
    exact: bool = False
    numerical: Any = None


def advance(system, run, field, watcher, context, end):
    """The segment from `run.time` and `run.y` as far as `end`: a closed form where the structure of
    the segment proves one (`kernels`), else the solver (`integrate.numerical_segment`). The caller
    has cleared the faces of the segment before (`run.right_faces`, `run.zero_faces`). `watcher`
    gives the level rules that are watched (`guards(environment)`)."""
    s, environment = system, field.environment
    roots, descriptors = segment_roots(s, run, watcher, environment)
    derivative = field.rates(run.time, run.y)
    initial_rates = field.delivered
    rounded = rounded_faces(s, run, derivative)
    if rounded:
        return Advance(rounded=rounded)
    departures, velocity = depart_faces(s, run, field, derivative)
    for i in departures:
        # A departing stock whose bound is still active has its release root already.
        if ('release', (i, 'min')) not in descriptors:
            roots.append(release_root(run, i, 'min'))
            descriptors.append(('release', (i, 'min')))
    hold_zero_faces(s, run, velocity)
    classifier = Classifier(s, run, environment)
    try:
        exact = affine_segment(s, run, classifier, departures, derivative, descriptors, end, environment)
        if exact is not None:
            exact[1].leg_rates = initial_rates
        else:
            exact, repayment_surfaces = compartment_solution(
                s, run, field, classifier, departures, end, descriptors
            )
    except ExpressionError:
        # A closed form reads a fixed part that has no value now, on a side that the rates do not
        # take (spec: a conditional evaluates only its selected side): the solver integrates the
        # segment, and its rates read only what they take.
        exact, repayment_surfaces = None, []
    if exact is not None:
        reached, solution, targets, due = exact
        return Advance(end=reached, solution=solution, targets=targets, due=tuple(due), exact=True)
    solution, located, due = numerical_segment(
        s, run, field, context, roots, descriptors, end, repayment_surfaces
    )
    return Advance(
        end=float(solution.t[-1]), solution=solution.sol, targets=located, due=tuple(due), numerical=solution
    )
