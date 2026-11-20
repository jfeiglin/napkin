"""What the continuous engine reads of a run besides its system, and the state that changes as it
proceeds.

A system (`timeline/component.Network`) is the fixed description of one connected set of stores and
flows. The continuous engine also reads three things of the run that holds it, and this module has
them:

- the numerical settings: the step cap of a numerical segment (`step_cap`), the longest step of its
  solver (`solver_step`) and the settings as the record of the run gives them (`run_settings`);
- a `Context`: the formulas at a time and a state (`environment`, in their order), the projection
  of a dense state onto the bounds that its accuracy admits, the diagnostics, and the settings. A
  formula is evaluated by one generated program of them all; where that fails, each is evaluated
  where a rate reads it (`Formulas`), so a formula or a value of the run on a side that the rate does
  not take fails nothing (spec: a conditional evaluates only its selected side);
- the `Run`: the time, the state, the store of the values that do not move, and the bounds and
  faces that hold the state in the present segment.

The time between two moments that the engine tells apart, to which it locates a crossing, is the
run's own: `Numerics.crossing` of its configuration, which a system holds as `cfg.crossing`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from ...core.errors import ExpressionError
from ...expressions import compile_program, evaluate


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
    `values` are the inputs and the other values that do not move; `missing` are those that have no
    value, with the reason, which a rate that reads one fails with."""

    def __init__(self, states, values, formulas, units, bounds, settings, missing=None):
        self.states = tuple(states)
        self.values = dict(values)
        self.missing = dict(missing or {})
        self.order = list(formulas)
        self._formulas = dict(self.order)
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
        each formula, all of them from the generated program, or else each when it is read."""
        env = {**self.values, **dict(zip(self.states, map(float, y))), **store, 't': float(t)}
        if self._program is None:
            self._program = self._compile(store)
        if self._program:
            try:
                self._program(env, self.units)
                return env
            except (ArithmeticError, ValueError, TypeError, KeyError):
                # A formula on a side that no rate takes may fail: each is evaluated where it is read.
                env = {**self.values, **dict(zip(self.states, map(float, y))), **store, 't': float(t)}
        return Formulas(env, self._formulas, self.missing, self.units)

    def project(self, state):
        """A dense state with its roundoff at a bound put on the bound: within the lower slack below
        a lower bound (a receive-only store has the accuracy of its own size there) and within the
        absolute tolerance above an upper bound. A larger excursion stays, and the checks see it."""
        lower, upper, lower_slack, upper_slack = self.bounds
        state = np.array(state, dtype=float)
        state = np.where((state < lower) & (state >= lower - lower_slack), lower, state)
        return np.where((state > upper) & (state <= upper + upper_slack), upper, state)


class Formulas(Mapping):
    """The values that a rate reads (`env`), with each formula evaluated when it is first read and
    then kept; a value that the run has none of (`missing`) raises its reason where it is read."""

    def __init__(self, env, formulas, missing, units):
        self.env, self.formulas, self.missing, self.units = env, formulas, missing, units

    def __getitem__(self, name):
        if name in self.env:
            return self.env[name]
        if name in self.formulas:
            found = self.env[name] = evaluate(self.formulas[name], self, self.units)
            return found
        if name in self.missing:
            raise ExpressionError(self.missing[name])
        raise KeyError(name)

    def __contains__(self, name):
        return name in self.env or name in self.formulas or name in self.missing

    def __iter__(self):
        # The names that have values: a value that has none is no name that a proof may take.
        return iter({*self.env, *self.formulas})

    def __len__(self):
        return len({*self.env, *self.formulas})


@dataclass
class Run:
    """What changes as a run proceeds: the time, the state and the discrete store, the bounds the
    state rests on, the stock faces of the current segment, the sides of the switches at which it
    starts (`integrate.starting_sides`) and the level rules it watches."""

    time: float
    y: np.ndarray
    store: dict
    active_bounds: set = field(default_factory=set)  # (quantity index, 'min' | 'max')
    zero_faces: set = field(default_factory=set)  # stocks held on their zero face
    right_faces: set = field(default_factory=set)  # stocks evaluated just above zero
    # (quantity index, low, high, number): a quantity in [low, high] reads as the number, the first on
    # the far side of a switch that the segment's state crosses at its start; (low, high, time) the
    # same for the time.
    switches: tuple = ()
    clock: tuple | None = None
    guards: dict = field(default_factory=dict)  # the segment's armed level rules, by rule
    evaluations: int = 0
