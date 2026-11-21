"""State checks, numerical face projection, the bounds a state rests on and stock faces."""

from __future__ import annotations

import math

import numpy as np

from ...expressions import compile_program, evaluate, names_in
from ..errors import SimulationError

# The failures of a generated program that the expressions, evaluated one by one, report.
PROGRAM_FAILURES = (ArithmeticError, ValueError, TypeError, KeyError)


def state_limits(system):
    """The lowest and the highest value of each quantity that a state check admits: its bounds with
    their slack. They are fixed for a run."""
    s = system
    if 'limits' not in s.analysis:
        s.analysis['limits'] = (s.lower - s.ledger_slack, s.upper + s.atol)
    return s.analysis['limits']


def check_values(system, env):
    """`value(expression)` of each state check, partition total and tolerance of a run in one
    environment.

    One generated program of the run computes them all. When it fails, each expression is evaluated
    on its own, in the order of `check_conditions`, so that the first one that fails names itself.
    """
    s = system
    program = s.analysis.get('checks')
    if program is None:
        sources = [check.expr for check in s.resolved.state_checks.values()]
        for partition in s.resolved.partitions.values():
            sources += [partition.total] + ([partition.tolerance] if partition.tolerance else [])
        index = {source: k for k, source in enumerate(dict.fromkeys(sources))}
        try:
            program = (index, compile_program([], list(index), constants=s.known, units=s.units))
        except (SyntaxError, RecursionError, ValueError):
            program = False  # a program too deep for Python: each expression on its own
        s.analysis['checks'] = program
    if program:
        index, run = program
        try:
            values = run(env, s.units)
        except PROGRAM_FAILURES:
            pass
        else:
            return lambda source: values[index[source]]
    return lambda source: evaluate(source, env, s.units)


def check_bounds(system, state):
    """Every quantity of a state is a number inside its bounds, with their slack."""
    s = system
    if np.any(~np.isfinite(state)):
        raise SimulationError('Nonfinite continuous state')
    low, high = state_limits(s)
    outside = (state < low) | (state > high)
    if outside.any():
        violations = [s.state_ids[i] for i in np.flatnonzero(outside)]
        raise SimulationError(f'State bounds violated: {violations}')


def check_conditions(system, env, at):
    """Every check on the state and every partition of a system holds in one environment."""
    s = system
    value = check_values(s, env)
    for name, check in s.resolved.state_checks.items():
        if not bool(value(check.expr)):
            diagnostic = {
                'code': 'check_failed',
                'severity': 'error',
                't': float(at),
                'check': name,
                'path': check.path,
                'expression': check.expr,
                'values': {key: env[key] for key in sorted(names_in(check.expr)) if key in env},
            }
            # The builder writes the message of each check, or None: the key is always there.
            raise SimulationError(f'Check {name}: {check.message}', [diagnostic])
    for name, partition in s.resolved.partitions.items():
        total = float(value(partition.total))
        parts = sum(float(env[part]) for part in partition.parts)
        limit = float(value(partition.tolerance)) if partition.tolerance else 1e-9 * max(1.0, abs(total))
        if abs(parts - total) > limit:
            raise SimulationError(
                f'Partition {name}: its parts add up to {parts}, not {total}',
                [
                    {
                        'code': 'partition_failed',
                        'severity': 'error',
                        't': float(at),
                        'partition': name,
                        'path': partition.path,
                        'parts': {part: float(env[part]) for part in partition.parts},
                    }
                ],
            )


def project_bound_roundoff(system, at, state, exact_targets=None, solution=None):
    """Put trial coordinates on their located faces after checking the size of the correction."""
    s = system
    lower, upper, atol = s.lower, s.upper, s.atol
    for i, name in enumerate(s.state_ids):
        target = (exact_targets or {}).get(i)
        if target is None:
            target = lower[i] if state[i] < lower[i] else upper[i] if state[i] > upper[i] else None
        if target is None:
            continue
        delta = float(target - state[i])
        if delta == 0:
            continue
        limit = s.ledger_slack[i] if target == lower[i] else atol[i]
        if abs(delta) > limit:
            # A proved crossing can fall between two adjacent floating-point timestamps.
            # The same incoming curve must bracket both the bound and this reported level.
            if solution is None or i not in (exact_targets or {}):
                raise SimulationError(f'Material state-bound violation for {name}')
            low, high = sorted(float(solution(np.nextafter(at, side))[i]) for side in (-np.inf, np.inf))
            if not (low <= state[i] <= high and low <= target <= high):
                raise SimulationError(f'Material state-bound violation for {name}')
        # This is a numerical trial coordinate. Only the timeline knows the accepted
        # cutoff and the physical incidence of all the faces reaching it together.
        state[i] = target
    return state


def refresh_bounds(system, run, field):
    """The bounds the state rests on after a moment; an inward rate releases its bound at once."""
    s = system
    run.active_bounds.clear()
    for i in range(len(run.y)):
        # A store that still has room can take material. A located physical contact puts
        # it on the bound; the error allowance on its state cannot advance that time.
        if run.y[i] <= s.lower[i]:
            run.active_bounds.add((i, 'min'))
        if run.y[i] >= s.upper[i]:
            run.active_bounds.add((i, 'max'))
    if run.active_bounds:
        derivative = field.rates(run.time, run.y)
        for i, bound in list(run.active_bounds):
            if (bound == 'min' and derivative[i] > 1e-14) or (bound == 'max' and derivative[i] < -1e-14):
                run.active_bounds.remove((i, bound))


def rounded_faces(system, run, derivative):
    """Proven stock faces whose remaining positive coordinate depletes within the timestamp's ulp.

    A constant-rate stock face can keep such a representational remainder. It is settled with its
    conservative balancing leg before any numerical stages, including unrelated nonlinear fields.
    """
    s, y = system, run.y
    found = {}
    for name in s.proven_faces:
        i = s.index[name]
        if s.lower[i] < y[i] <= s.lower[i] + s.ledger_slack[i] and derivative[i] < 0:
            remaining_h = (s.lower[i] - y[i]) / derivative[i]
            if remaining_h <= math.ulp(run.time):
                found[i] = s.lower[i]
    return found


def depart_faces(system, run, field, derivative):
    """Proven stock faces that an inward supply lifts off zero, with the field just above them.

    A stock on its zero face whose rate there is positive departs; each departure is probed one
    ulp above zero with its bound released, and a stock that the departure itself feeds departs
    with it. The field above must keep pointing up, or the face would chatter.
    """
    s, y, lower = system, run.y, system.lower
    departures = {
        s.index[name]
        for name in s.proven_faces
        if y[s.index[name]] == lower[s.index[name]] and derivative[s.index[name]] > 0
    }
    if not departures:
        return departures, derivative
    saved_bounds = run.active_bounds.copy()
    probe = y.copy()
    try:
        while True:
            for i in departures:
                probe[i] = math.nextafter(lower[i], math.inf)
                run.active_bounds.discard((i, 'min'))
            right_derivative = field.rates(run.time, probe)
            downstream = {
                s.index[name]
                for name in s.proven_faces
                if probe[s.index[name]] == lower[s.index[name]] and right_derivative[s.index[name]] > 0
            }
            if not downstream - departures:
                break
            departures.update(downstream)
    finally:
        run.active_bounds.clear()
        run.active_bounds.update(saved_bounds)
    if any(right_derivative[i] <= 0 for i in departures):
        details = {
            s.state_ids[i]: {'face_rate': float(derivative[i]), 'right_rate': float(right_derivative[i])}
            for i in departures
            if right_derivative[i] <= 0
        }
        raise SimulationError(f'Stock-zero field has an inward chattering switch at {run.time}: {details}')
    run.right_faces.update(departures)
    return departures, right_derivative


def hold_zero_faces(system, run, velocity):
    """A proven zero face with zero allocated velocity stays on that face under the constant
    material rates until the next physical or discrete boundary; numerical trial evaluations
    keep it there, including segments with unrelated evolving compartments."""
    s, y = system, run.y
    run.zero_faces.update(
        s.index[name]
        for name in s.proven_faces
        if y[s.index[name]] == s.lower[s.index[name]] and velocity[s.index[name]] == 0
    )
