"""What the continuous engine reads of a run besides its system, and the state that changes as it
proceeds.

A system (`timeline/component.Network`) is the fixed description of one connected set of stores and
flows. The continuous engine also reads three things of the run that holds it, and this module has
them:

- the numerical settings: the step cap of a numerical segment (`step_cap`), the longest step of its
  solver (`solver_step`) and the settings as the record of the run gives them (`run_settings`);
- a `Context`: the formulas at a time and a state (`environment`, in their order), the projection
  of a dense state onto the bounds that its accuracy admits, the diagnostics, and the settings;
- the `Run`: the time, the state, the store of the values that do not move, and the bounds and
  faces that hold the state in the present segment.

`EVENT_TIME_TOLERANCE_H` is the time between two moments that the engine tells apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ...expressions import compile_program, evaluate

# Two moments closer than this, in hours, are one moment; a crossing is located to within it.
EVENT_TIME_TOLERANCE_H = 1e-8


def step_cap(numerics):
    """The step cap of a numerical segment, in hours: the interval at which the engine reads the
    roots, the field and the hidden excursions of the segment (`numerics.max_step`)."""
    cap = float(numerics.max_step)
    if not math.isfinite(cap) or cap <= 0:
        raise ValueError('the step cap must be a finite and positive time')
    return cap


def solver_step(numerics):
    """The longest step that the solver of a numerical segment takes, in hours. A program declares
    no physical timescale, so the solver's own control of the error decides its steps."""
    return math.inf


def run_settings(numerics, cap):
    """The numerical settings of a run as its record gives them, with the list of its numerical
    segments, which the solver fills."""
    return {
        'rtol': numerics.rtol,
        'atol_factor': numerics.atol_factor,
        'max_evaluations': numerics.max_evaluations,
        'max_step': cap,
        'integration_segments': [],
        'resolution_policy': 'structural_exact',
        'actual_max_step_h': None,
    }


class Context:
    """What the continuous engine reads of a run beside its system: the formulas that the rates
    read, evaluated at a time and a state; the projection of a dense state onto its bounds; the
    diagnostics of the run and its numerical settings.

    `formulas` are (name, node) in an order in which each formula comes after those that it reads.
    `values` are the inputs and the other values that do not move."""

    def __init__(self, states, values, formulas, units, bounds, settings):
        self.states = tuple(states)
        self.values = dict(values)
        self.order = list(formulas)
        self.units = units
        self.bounds = bounds  # (lower, upper, lower slack, upper slack)
        self.settings = settings
        self.diagnostics = []
        self._program = None

    def _compile(self, store):
        """The generated program that assigns the formulas in their order, with each input that no
        other name hides as a literal; False when it cannot be made, and the interpreter evaluates
        each formula."""
        hidden = set(self.states) | set(store) | {name for name, _ in self.order} | {'t'}
        constants = {name: value for name, value in self.values.items() if name not in hidden}
        try:
            return compile_program(self.order, [], constants=constants, units=self.units)
        except (SyntaxError, RecursionError, ValueError):
            return False

    def environment(self, t, y, store):
        """The values that a rate reads at time t and state y: the inputs, the store, the state and
        each formula."""
        env = {**self.values, **dict(zip(self.states, map(float, y))), **store, 't': float(t)}
        if self._program is None:
            self._program = self._compile(store)
        if self._program:
            try:
                self._program(env, self.units)
                return env
            except (ArithmeticError, ValueError, TypeError, KeyError):
                # The interpreter names the formula that fails.
                env = {**self.values, **dict(zip(self.states, map(float, y))), **store, 't': float(t)}
        for name, node in self.order:
            env[name] = evaluate(node, env, self.units)
        return env

    def project(self, state):
        """A dense state with its roundoff at a bound put on the bound: within the lower slack below
        a lower bound (a receive-only store has the accuracy of its own size there) and within the
        absolute tolerance above an upper bound. A larger excursion stays, and the checks see it."""
        lower, upper, lower_slack, upper_slack = self.bounds
        state = np.array(state, dtype=float)
        state = np.where((state < lower) & (state >= lower - lower_slack), lower, state)
        return np.where((state > upper) & (state <= upper + upper_slack), upper, state)


@dataclass
class Run:
    """What changes as a run proceeds: the time, the state and the discrete store, the bounds the
    state rests on, the stock faces of the current segment and the level rules it watches."""

    time: float
    y: np.ndarray
    store: dict
    active_bounds: set = field(default_factory=set)  # (quantity index, 'min' | 'max')
    zero_faces: set = field(default_factory=set)  # stocks held on their zero face
    right_faces: set = field(default_factory=set)  # stocks evaluated just above zero
    guards: dict = field(default_factory=dict)  # the segment's armed level rules, by rule
    evaluations: int = 0
