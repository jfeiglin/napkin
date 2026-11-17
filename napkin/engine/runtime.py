"""Deterministic hybrid integration over canonical model definitions (docs/engine.md).

`simulate` gives the run of the timeline engine (`engine/timeline`) as a `Trajectory`: the timeline
takes the steps of every moment, and between moments each part of the model moves by its own
segments (`engine/continuous` for the parts that one solver moves together). Reporting is a
read-only view of the stored dense segments: neither report requests nor plotting resolution take
part in event detection or integration.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields

import numpy as np

from ..expressions import compile_program, evaluate, names_in
from ..model import structure as typed
from ..model.ir import ModelError
from .errors import SimulationError

__all__ = ['NumericalSettings', 'SimulationError', 'Trajectory', 'simulate']


@dataclass(frozen=True)
class NumericalSettings:
    rtol: float = 1e-9
    atol_factor: float = 1e-10
    max_step: float = 1.0
    max_evaluations: int = 2_000_000
    max_events: int = 10_000
    max_steps: int = 1_000

    def __post_init__(self):
        for name in ('rtol', 'atol_factor', 'max_step'):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f'{name} must be finite and positive')
        for name in ('max_evaluations', 'max_events', 'max_steps'):
            if (
                isinstance(getattr(self, name), bool)
                or not isinstance(getattr(self, name), int)
                or getattr(self, name) <= 0
            ):
                raise ValueError(f'{name} must be a positive integer')

    @classmethod
    def parse(cls, settings):
        """Validated settings from a caller mapping; invalid settings reject the study as a model error."""
        if isinstance(settings, cls):
            return settings
        values = dict(settings or {})
        unknown = sorted(values.keys() - {item.name for item in fields(cls)})
        try:
            if unknown:
                raise ValueError(f'Unknown numerical settings {unknown}')
            return cls(**values)
        except ValueError as exc:
            raise ModelError(
                [
                    {
                        'code': 'numerical_settings',
                        'path': 'numerical_settings',
                        'message': str(exc),
                        'severity': 'error',
                    }
                ]
            ) from exc


@dataclass
class Trajectory:
    horizon: float
    trace: list
    diagnostics: list
    settings: dict
    _states: tuple
    _values: dict
    _computed: dict  # computed values and labels, as expressions
    _units: dict
    _bounds: tuple  # (lower, upper, lower_slack, upper_slack)
    _segments: list = field(default_factory=list)
    _snapshots: list = field(default_factory=list)  # (t, state, store) before and after each step
    _steps: list = field(default_factory=list)  # (t, state, store) after each step, by step number
    layers: list = field(default_factory=list)  # global step number of each trace entry, increasing
    moved: set = field(default_factory=set)  # the flows that delivered material in some segment
    evaluations: int = 0
    _order: list | None = None
    # A played run's first decision that waits for a pick (docs/engine.md, "Play"), or None.
    decision: dict | None = None
    paused: bool = False
    end_time: float | None = None

    def __post_init__(self):
        if self.end_time is None:
            self.end_time = self.horizon

    # Caches that a trajectory keeps for its own use and that its pickle leaves out: the index of
    # `env_at` (`_times`) and the generated program of `_environment` (`_compile`).
    TRANSIENT = ('_lookup', '_program')

    def __getstate__(self):
        return {key: value for key, value in self.__dict__.items() if key not in Trajectory.TRANSIENT}

    def _compile(self, store):
        """The generated program that assigns the computed values of an environment in their order,
        with each input that no other name hides as a literal; False when it cannot be made, and the
        interpreter evaluates each value."""
        hidden = set(self._states) | set(store) | set(self._computed) | {'t'}
        constants = {name: value for name, value in self._values.items() if name not in hidden}
        try:
            return compile_program(self._order, [], constants=constants, units=self._units)
        except (SyntaxError, RecursionError, ValueError):
            return False

    def _environment(self, t, y, store):
        env = {**self._values, **dict(zip(self._states, map(float, y))), **store, 't': float(t)}
        if self._order is not None:
            # The available names are fixed for a trajectory, so the resolution order is too.
            program = self.__dict__.get('_program')
            if program is None:
                program = self.__dict__['_program'] = self._compile(store)
            if program:
                try:
                    program(env, self._units)
                    return env
                except (ArithmeticError, ValueError, TypeError, KeyError):
                    # The interpreter names the value that fails.
                    env = {**self._values, **dict(zip(self._states, map(float, y))), **store, 't': float(t)}
            for name, expr in self._order:
                env[name] = evaluate(expr, env, self._units)
            return env
        order = []
        pending = dict(self._computed)
        while pending:
            ready = [
                name for name, definition in pending.items() if names_in(definition['expr']) <= env.keys()
            ]
            if not ready:
                raise SimulationError(f'Unresolved computed values: {sorted(pending)}')
            for name in ready:
                expr = pending.pop(name)['expr']
                env[name] = evaluate(expr, env, self._units)
                order.append((name, expr))
        self._order = order
        return env

    def _project(self, state):
        """Project dense roundoff using the integrator's admitted bound accuracy.

        Nondecreasing ledgers use their established ledger-scale lower accuracy;
        other lower bounds and every upper bound use absolute accuracy. Larger
        excursions remain visible to reporting validation.
        """
        lower, upper, lower_slack, upper_slack = self._bounds
        state = np.array(state, dtype=float)
        state = np.where((state < lower) & (state >= lower - lower_slack), lower, state)
        return np.where((state > upper) & (state <= upper + upper_slack), upper, state)

    def env_after_step(self, layer: int) -> dict:
        """The state just after one step; a trace entry's step number is in `layers`."""
        t, state, store = self._steps[layer]
        return self._environment(t, state, store)

    def _times(self):
        """The times of the snapshots and the ends of the segments, for `env_at`. Both lists grow in
        time order, so a lookup is a binary search. They are kept, with the counts that they were
        made from, in an attribute that is not a field: a digest of the trajectory reads its fields."""
        counts = (len(self._snapshots), len(self._segments))
        found = self.__dict__.get('_lookup')
        if found is None or found[0] != counts:
            found = self.__dict__['_lookup'] = (
                counts,
                [snap[0] for snap in self._snapshots],
                [segment.end for segment in self._segments],
            )
        return found[1], found[2]

    def env_at(self, t: float, side: str = 'right') -> dict:
        t = float(t)
        if side not in {'left', 'right'}:
            raise ValueError('side must be left or right')
        end = self.horizon if self.end_time is None else self.end_time
        if not math.isfinite(t) or t < 0 or t > end:
            raise ValueError(f'Sampling time {t} lies outside [0, {end}]')
        times, ends = self._times()
        # Exact timestamp snapshots distinguish impulse pre/post states: the first and the last
        # snapshot at t.
        first = bisect.bisect_left(times, t)
        if first < len(times) and times[first] == t:
            snap = self._snapshots[first if side == 'left' else bisect.bisect_right(times, t) - 1]
            return self._environment(t, self._project(snap[1]), snap[2])
        # The first segment that holds t: no earlier one ends at or after t.
        k = bisect.bisect_left(ends, t)
        if k < len(ends) and self._segments[k].start <= t:
            segment = self._segments[k]
            return self._environment(t, self._project(segment.solution(t)), segment.store)
        raise SimulationError(f'No stored solution covers time {t}')


def simulate(
    rs: typed.Resolved,
    library: Mapping,
    settings: Mapping | NumericalSettings | None = None,
    *,
    play: Mapping | None = None,
    pause_at_decision: bool = False,
    decision_events=None,
    settled_decisions: bool = False,
    decision_resolver=None,
) -> Trajectory:
    """Run to the horizon, or stop before the first unanswered controlled decision.

    ``play`` is what a played run asks (docs/engine.md, "Play"): ``{'control': {thing: 'reader' |
    'agent' | 'chance'}, 'picks': [{'event': …, 'outcome': …}, …]}``. With no ``play`` the model
    takes every decision.
    ``decision_events`` optionally limits control to the named rules. Other rules retain their
    normal seeded policy. A paused trajectory retains the original horizon but only stores history
    through ``end_time``; continuing a played run replays it with the extended pick log.
    ``settled_decisions`` resolves independent already-due work at the same timestamp before a
    controlled outcome. It neither advances time nor previews any unanswered outcome.
    ``decision_resolver(decision, env, trace)`` may authorize an unanswered choice at its exact
    boundary. It returns a pick mapping or None to pause. It requires ``pause_at_decision=True``;
    callers must durably record an authorized pick before returning it.
    """
    if decision_resolver is not None and not pause_at_decision:
        raise ValueError('decision_resolver requires pause_at_decision=True')
    from . import timeline

    return timeline.trajectory(
        rs,
        library,
        settings,
        play=play,
        pause_at_decision=pause_at_decision,
        decision_events=decision_events,
        settled_decisions=settled_decisions,
        decision_resolver=decision_resolver,
    )
