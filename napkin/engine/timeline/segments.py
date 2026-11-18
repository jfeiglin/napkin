"""What a quantity is between two moments: a line, a numeric block or a closed form, and how
each starts again.

Moved from `run.py` with no change (step B0-6). `Segments` is a part of `run.Run`: its methods
read the run as `self`.
"""

from __future__ import annotations

import copy
import heapq
import math
from bisect import bisect_left
from collections import deque

import numpy as np
from scipy.linalg import expm
from scipy.optimize import brentq

from ...core.derivatives import derivative
from ...core.errors import ExpressionError
from ...core.evaluation import program as compile_program
from ...model.ir import EVENT_TIME_TOLERANCE_H
from .. import solvers
from ..continuous.integrate import STALLED_STEPS, Limit, apart
from ..errors import SimulationError
from .plan import Outside
from .state import (
    BOUND,
    END,
    FLOOR,
    LIMIT,
    NEGATIVE,
    POSITIVE,
    ROOT_TOLERANCE,
    Env,
    Seen,
    Trial,
    _one,
    _spread,
)


def _span(a, c, start, bound):
    """The time that the solution of `y' = a y + c` from `start` takes to reach `bound`, or None when
    it does not reach it. Such a solution moves to one side only."""
    if not math.isfinite(bound):
        return None
    if a == 0:
        return (bound - start) / c if c != 0 and (bound - start) / c > 0 else None
    rest = -c / a
    ratio = (bound - rest) / (start - rest) if start != rest else -1.0
    return math.log(ratio) / a if ratio > 0 and math.log(ratio) / a > 0 else None


class Solution:
    """A numeric block from its last restart: the steps of a solver, made when a reader asks."""

    def __init__(self, run, block, instance):
        plan = run.plan
        self.run, self.block, self.instance = run, block, instance
        self.J = None if block.whole else np.array([instance])
        self.slices, at = {}, 0
        for name in block.names:
            count = plan.spaces[plan.space_of(name)].count if block.whole else 1
            self.slices[name] = slice(at, at + count)
            at += count
        self.size = at
        self.t0, self.y0, self.steps, self.ends, self.runner, self.frontier = 0.0, None, [], [], None, 0.0
        # (time, state, a flow below zero or None, the flows above zero) of each state that the
        # solver tried since its last step.
        self.tried = []
        # (time, state, what the field found there or None) of each state of the solution that is a
        # state of the run when a reader comes to it (`settle`), from `settled` on.
        self.unread, self.settled = deque(), 0.0
        # For each step, the whole caps inside it: the times at which the engine reads it.
        self.cuts = []
        self.mode, self.matrix, self.given, self.last = None, None, None, None

    def start(self, t, y):
        self.t0, self.y0, self.frontier = t, y, t
        self.steps, self.ends, self.cuts, self.runner = [], [], [], None
        self.unread, self.settled = deque(), t
        self.evaluations, self.tried = 0, []
        self.numeric_only, self.given_terms = False, None
        # How the segment is solved is decided when a reader first asks (`Run.decide`).
        self.mode, self.matrix, self.given, self.last = None, None, None, None

    def tolerances(self):
        run = self.run
        return np.concatenate(
            [run.atol[name] if self.J is None else run.atol[name][self.J] for name in self.block.names]
        )

    def advance(self):
        """One more step of the solver that the block uses. The step cap of the run is the interval
        at which the engine reads the block, and no limit of the solver's step (docs/engine.md,
        "Steps"): a step can be longer, and is then read inside, on its own solution.

        - At each half of a cap from the start of the segment, the field is compared with the rate
          of the solution (`integrate.apart`). When the two are too far apart at one of these
          times, the step is not used: the solver takes it again, with a shorter limit
          (`integrate.Limit`).
        - At each whole cap, the state of the solution is a state of the run, as the end of a step
          is: it is within its bounds, and no flow of it asks a rate below zero. A step can end
          far after the time that a reader asks for, and an event before its end starts the block
          again: a state is checked when a reader comes to it (`settle`)."""
        run = self.run
        cap, half = run.max_step, run.max_step / 2
        if self.runner is None:
            # The rates at the start of the segment are those of a state of the run: checked.
            run.field(self, self.t0, self.y0, trial=False)
            # The longest step: what the timescales of the run allow, and then what the steps
            # before allow.
            self.limit = Limit(cap, run.solver_step)
            self.halves = 0  # the halves of a cap before the next step, from the start
            self.runner = run.adapter.start(
                lambda t, y: run.field(self, t, y),
                self.t0,
                self.y0,
                run.horizon,
                rtol=run.cfg.rtol,
                atol=self.tolerances(),
                max_step=self.limit.allowed,
            )
        limit, rtol, atol = self.limit, run.cfg.rtol, None
        while True:
            self.runner.limit(limit.allowed)
            try:
                step = self.runner.step()
            except solvers.SolverFailure as problem:
                raise SimulationError(f'{self.block.names[0]}: {problem}') from problem
            run.counts['solver steps'] += 1
            length = step.t - step.t_old
            if not length > cap:
                # A step of the cap at most is read at its end, as each step was before.
                while self.t0 + (self.halves + 1) * half < step.t:
                    self.halves += 1
                limit.short()
                inside = ()
                break
            atol = self.tolerances() if atol is None else atol
            count, largest, far, inside = self.halves, 0.0, 0.0, []
            while True:
                at = self.t0 + (count + 1) * half
                if not at < step.t:
                    break
                count += 1
                if at <= step.t_old:
                    continue
                state = step.dense(at)
                far = apart(length, run.field(self, at, state), step.rate(at), state, rtol, atol)
                if not far <= 1.0:
                    break
                largest = max(largest, far)
                if count % 2 == 0:
                    inside.append((at, state, self.tried[-1][2:]))
            if far <= 1.0:
                self.halves = count
                limit.used(length, largest)
                break
            # The solution of the step is too far from the field inside the step.
            limit.unused(length, far)
            self.runner.retake(limit.allowed)
            self.tried = []
            run.counts['solver steps not used'] += 1
        if limit.accepted(step.t_old, step.t):
            # The steps of the solver no longer move the block (`integrate.STALLED_STEPS`).
            message = (
                f'The run stops at t = {step.t:g} h: the steps of the solver for {self.block.names[0]} '
                f'stayed shorter than {EVENT_TIME_TOLERANCE_H:g} h for {STALLED_STEPS} steps in a '
                f'row, from t = {limit.brief_from:g} h. A rate of the block switches back and forth '
                'at a condition: each branch takes the state back across the switch. A condition '
                'that turns the outflows of a stock off when it is empty does this when they ask for '
                'more than comes in: remove the condition, as the engine gives the outflows of an '
                'empty stock what comes in.'
            )
            item = {
                'severity': 'error',
                'code': 'chattering',
                'from_h': limit.brief_from,
                'at_h': float(step.t),
                'quantities': list(self.block.names),
            }
            raise SimulationError(message, [item])
        # A solver reads the rates at the state that it accepts, so what the field found there is
        # known; a solver that did not is asked for the rates there (`settle`).
        tried, self.tried = self.tried, []
        found = next(
            (
                (negative, positive)
                for at, state, negative, positive in reversed(tried)
                if at == step.t and np.array_equal(state, step.y)
            ),
            None,
        )
        self.unread += [*inside, (step.t, step.y, found)]
        self.steps.append(step)
        self.ends.append(step.t)
        self.cuts.append(tuple(at for at, _, _ in inside))
        self.frontier = step.t

    def settle(self, t):
        """Each state at which the engine reads the solution (the end of a step; each whole cap
        inside a step that is longer than the cap) is a state of the run when a reader comes to it:
        it is within its bounds, and no flow of it asks a rate below zero. The states up to the
        first of them at or after `t` are checked here. The states after it are those of the block
        only when no event starts the block again before them."""
        run, unread = self.run, self.unread
        while unread and self.settled < t:
            at, state, found = unread.popleft()
            run.within_bounds(self, state, at)
            if found is None:
                run.field(self, at, state, trial=False)
            else:
                negative, positive = found
                if negative is not None:
                    raise run.negative_flow(negative)
                run.flowing |= positive
            self.settled = at

    def at(self, t):
        """The state of the block at a time from its restart on."""
        if t <= self.t0:
            return self.y0
        if self.mode is None:
            self.run.decide(self)
        if self.mode == 'closed':
            if self.last is None or self.last[0] != t:
                extended = np.append(self.y0, 1.0)
                self.last = (t, (expm(self.matrix * (t - self.t0)) @ extended)[:-1])
            return self.last[1]
        while self.frontier < t:
            self.advance()
        if self.settled < t:
            self.settle(t)
        step = self.steps[bisect_left(self.ends, t)]
        return step.y if t == step.t else step.dense(t)

    def first_root(self, place, threshold, rising, after):
        """The first time after `after` at which the value at `place` reaches `threshold` from the
        side that `rising` names, or None when it does not before the horizon."""
        horizon = self.run.horizon
        if after >= horizon:
            return None
        if self.mode is None:
            self.run.decide(self)
        if self.mode == 'closed':
            name = next(name for name, cut in self.slices.items() if cut.start == place)
            if self.run.plan.quantities[name].monotone:
                # A quantity that never falls reaches its value once: the root is between two times
                # at which it is on the two sides.
                before = float(self.at(after)[place]) - threshold
                end = float(self.at(horizon)[place]) - threshold
                if not ((before < 0 <= end) if rising else (before > 0 >= end)):
                    return None
                return brentq(
                    lambda at: float(self.at(at)[place]) - threshold,
                    after,
                    horizon,
                    xtol=ROOT_TOLERANCE,
                    rtol=ROOT_TOLERANCE,
                )
            # No proof that it crosses once: the solver's steps find the first crossing.
            self.mode, self.last = 'numeric', None
        self.at(min(horizon, np.nextafter(after, np.inf)))
        k = bisect_left(self.ends, after)
        if k < len(self.ends) and self.ends[k] == after:
            k += 1
        while True:
            if k >= len(self.steps):
                if self.frontier >= horizon:
                    return None
                self.advance()
            step = self.steps[k]
            start = max(step.t_old, after)
            before = float(self.at(start)[place]) - threshold if start > step.t_old else None
            if before is None:
                before = float((self.y0 if k == 0 else self.steps[k - 1].y)[place]) - threshold
            # The value is read at the end of the step, and inside a step that is longer than the
            # cap at each whole cap from the start of the segment, as the ends of the steps of a
            # solver that the cap limits read it: the first of these parts in which it crosses
            # has the root. The states of the block up to there are states of the run.
            for cut in (*self.cuts[k], step.t):
                if cut <= start:
                    continue
                end = float((step.y if cut == step.t else step.dense(cut))[place]) - threshold
                if (before < 0 <= end) if rising else (before > 0 >= end):
                    root = cut
                    if end != 0:
                        root = brentq(
                            lambda at, step=step: float(step.dense(at)[place]) - threshold,
                            start,
                            cut,
                            xtol=ROOT_TOLERANCE,
                            rtol=ROOT_TOLERANCE,
                        )
                    self.settle(root)
                    return root
                start, before = cut, end
            self.settle(step.t)
            k += 1


class Segments:
    """See the module."""

    def field(self, solution, t, y, trial=True):
        """The rates of a numeric block at a state: at a state that its solver tries, or
        (`trial=False`) at a state of the run, where the rates are checked."""
        plan = self.plan
        state = Trial({name: y[cut] for name, cut in solution.slices.items()}, solution.block.whole)
        out = np.empty_like(y)
        envs = {}
        for name, cut in solution.slices.items():
            space = plan.quantities[name].space
            env = envs.get(space)
            if env is None:
                env = envs[space] = Env(self, space, solution.J, t, state)
            out[cut] = self.rate_of(name, env, trial)
        if trial:
            negative = next((env.memo[NEGATIVE] for env in envs.values() if NEGATIVE in env.memo), None)
            positive = set().union(*(env.memo.get(POSITIVE, ()) for env in envs.values()))
            solution.tried.append((t, y.copy(), negative, positive))
        self.counts['evaluations'] += 1
        solution.evaluations += 1
        if solution.evaluations > self.cfg.max_evaluations:
            raise SimulationError(
                f'{solution.block.names[0]}: more than {self.cfg.max_evaluations} evaluations of its rates '
                f'between two moments (t = {t:g} h)'
            )
        return out

    def matrices(self, block, J, start=None):
        """For the instances J (None: all) of a linear block, the matrix M of each: `y' = A y + c` as
        `[y, 1]' = M [y, 1]`, with A and c in the first rows and a last row of zeros; and, for each
        instance, whether no flow of the block can ask a rate below zero while each quantity is
        within its bounds: what the flow asks is `r + w y`, with r at or above 0 and each factor w
        at or above 0 and, where it is not 0, on a quantity whose lower bound is at or above 0.

        The closed form reads no rate at the start of its segment, so the flows that have not
        moved in the run yet (`flowing`) are looked at here. For one instance, `start` is its state
        there: a flow that delivers material at it has moved. For many, the third result has
        (flow, r, w) of each such flow, for `flows_from`."""
        plan, names = self.plan, block.names
        count = plan.spaces[block.space].count if J is None else len(J)
        size = len(names)
        zero = Trial({name: np.zeros(count) for name in names}, False)
        env = Env(self, block.space, J, 0.0, zero)
        floors = [plan.quantities[name].lower >= 0 for name in names]
        values = self.block_values(block, env) if count == 1 else None
        if values is not None:
            # One instance, from its program: plain numbers, with no array for each of them.
            asked = self.asked_alone(block, values)
            rows = [[0.0] * (size + 1) for _ in range(size + 1)]
            sure, at = True, 0
            for i, name in enumerate(names):
                row = rows[i]
                for (sign, _, is_flow), key in zip(plan.parts[name], plan.part_flows[name]):
                    if key is None or asked.get(key, False):
                        # What the part asks: no limit and no other flow cuts it at this state.
                        part = values[at]
                    else:
                        part = float(_one(self.delivered(key, env)))
                    row[size] += sign * part
                    slopes = values[at + 1 : at + 1 + size]
                    for j in range(size):
                        row[j] += sign * slopes[j]
                    if is_flow:
                        if part < 0:
                            sure = False
                        for j in range(size):
                            if not (slopes[j] == 0 or (slopes[j] > 0 and floors[j])):
                                sure = False
                    looked = start is not None and key is not None and key not in self.flowing
                    if looked and part + sum(slopes[j] * start[j] for j in range(size)) > 0:
                        self.flowing.add(key)
                    at += 1 + size
            return np.array([rows], dtype=float), np.array([sure]), []
        found = np.zeros((count, size + 1, size + 1))
        safe = np.ones(count, dtype=bool)
        at, asks = 0, []
        for i, name in enumerate(names):
            for (sign, node, is_flow), key in zip(plan.parts[name], plan.part_flows[name]):
                part = self.value(node, env) if key is None else self.delivered(key, env)
                part = _spread(part, count)
                found[:, i, size] += sign * part
                if is_flow:
                    safe &= part >= 0
                slopes = np.zeros((count, size)) if key is not None and key not in self.flowing else None
                for j, other in enumerate(names):
                    slope = _spread(self.value(derivative(node, other), env), count)
                    found[:, i, j] += sign * slope
                    if is_flow:
                        safe &= (slope == 0) | ((slope > 0) & floors[j])
                    if slopes is not None:
                        slopes[:, j] = slope
                if slopes is not None:
                    asks.append((key, part, slopes))
                at += 1 + size
        return found, safe, asks

    def flows_from(self, asks, states):
        """Mark the flows of `matrices` that deliver material at the states (one row for each
        instance) at which their segments start."""
        for key, part, slopes in asks:
            if key not in self.flowing and np.any(part + np.einsum('ij,ij->i', slopes, states) > 0):
                self.flowing.add(key)

    def asked_alone(self, block, values):
        """{flow of a part of a linear block: whether it delivers what it asks, from the values of
        `block_program`}: a flow that moves by one fraction with no other, whose source is no
        quantity that can rest on its bound, and whose group has no limit, or asks no more than its
        limit together (the test of `rationed`)."""
        plan, size = self.plan, len(block.names)
        found = {}
        for name in block.names:
            for key in plan.part_flows[name]:
                if key is None or key in found:
                    continue
                group = plan.groups.get(plan.flow_group.get(key))
                found[key] = (
                    key not in plan.coupled
                    and plan.floors.get(plan.flow_source.get(key)) is None
                    and (group is None or group.capacity is None)
                )
        at = sum(len(plan.parts[name]) for name in block.names) * (1 + size)
        for group in plan.block_groups[block.index]:
            total = 0.0
            for k in range(len(group.flows)):
                total = total + values[at + k * (1 + size)]
            capacity = values[at + len(group.flows) * (1 + size)]
            inside = capacity >= 0 and not total > capacity and plan.floor_of_group.get(group.name) is None
            for key in group.flows:
                if key in found:
                    found[key] = (
                        inside
                        and key not in plan.coupled
                        and plan.floors.get(plan.flow_source.get(key)) is None
                    )
            at += len(group.flows) * (1 + size) + 1
        return found

    def block_program(self, block):
        """One generated program for what the closed form of a linear block reads of its
        expressions (`core.evaluation.program`): for each part of each rate, its value and its
        derivative by each quantity of the block, in the order of `matrices`; then, for each flow
        of each group with a limit, the same, and the limit of the group, in the order of
        `group_terms`. False when the program cannot be made."""
        made = self.block_programs.get(block.index)
        if made is None:
            plan, names = self.plan, block.names
            outputs = []
            for name in names:
                for _, node, _ in plan.parts[name]:
                    outputs += [node, *(derivative(node, other) for other in names)]
            for group in plan.block_groups[block.index]:
                for key in group.flows:
                    node = plan.flows[key]
                    outputs += [node, *(derivative(node, name) for name in names)]
                outputs.append(group.capacity)
            try:
                made = compile_program([], outputs, units=self.registry)
            except (SyntaxError, RecursionError, ValueError, ExpressionError):
                made = False
            self.block_programs[block.index] = made
        return made

    def block_values(self, block, env):
        """The values of `block_program` for the one instance of an environment, with each quantity
        of the block at 0; None when there is no program, or when it fails: the caller then reads
        each expression by itself, which names the one that fails."""
        program = self.block_program(block)
        if not program:
            return None
        # The matrix of a block and what its groups ask are read one after the other. They read
        # values that only a step writes, so the values of the first reading serve the second while
        # no value was written between them.
        key = (block.index, 0 if env.J is None else int(env.J[0]), self.wrote)
        if self.block_made[0] == key:
            return self.block_made[1]
        try:
            values = program(Seen(env), self.registry)
        except (ArithmeticError, ValueError, TypeError, KeyError, ExpressionError):
            return None
        self.block_made = (key, values)
        return values

    def group_terms(self, block, J):
        """For each group with a limit of a linear block: what its flows ask together as
        `alpha + beta y` over the quantities y of the block, and its limit, for the instances J
        (None: all): (alpha, beta, the limit), with one row for each instance."""
        plan, names = self.plan, block.names
        count = plan.spaces[block.space].count if J is None else len(J)
        zero = Trial({name: np.zeros(count) for name in names}, False)
        env = Env(self, block.space, J, 0.0, zero)
        found = []
        values = self.block_values(block, env) if count == 1 else None
        # The values of the groups come after those of the parts of the rates (`block_program`).
        at = sum(len(plan.parts[name]) for name in names) * (1 + len(names))
        for group in plan.block_groups[block.index]:
            alpha, beta = np.zeros(count), np.zeros((count, len(names)))
            for key in group.flows:
                node = plan.flows[key]
                alpha += _spread(values[at] if values is not None else self.value(node, env), count)
                for i, name in enumerate(names):
                    slope = (
                        values[at + 1 + i] if values is not None else self.value(derivative(node, name), env)
                    )
                    beta[:, i] += _spread(slope, count)
                at += 1 + len(names)
            capacity = values[at] if values is not None else self.value(group.capacity, env)
            at += 1
            found.append((alpha, beta, _spread(capacity, count).astype(float)))
        return found

    def decide(self, solution):
        """How a segment of a block is solved: by its closed form, or by the solver.

        The closed form is used for a linear block of one instance when each quantity of it is one
        of these, so that no state leaves its bounds without the timeline knowing:

        - it has no bound;
        - its rate reads no other quantity of the block. Then it moves to one side only (the
          solution of `y' = a y + c` rises or falls, and never turns), and the time at which it would
          reach a bound goes on the timeline, as for a line;
        - its lower bound is 0, it has no upper bound, the constant of its rate is 0 or more, and so
          is the factor of each other quantity in its rate, while no quantity of the block can be
          below 0. At the value 0 its rate is then 0 or more, so it stays at or above 0.

        A group with a limit must also stay below its limit, because the closed form is of the rates
        that the flows ask. What its flows ask together is `alpha + beta y` for at most one quantity
        y of the block, whose rate reads no other quantity of the block: it then moves to one side
        only, and the time at which it would reach the limit goes on the timeline. From that time the
        solver integrates the block, with the limit shared out."""
        plan, block = self.plan, solution.block
        solution.mode = 'numeric'
        if solution.numeric_only:
            return
        if not block.linear or block.whole or solution.t0 >= self.horizon:
            return
        if solution.given is not None:
            matrix, safe = solution.given
        else:
            found, sure, asks = self.matrices(block, solution.J, solution.y0)
            matrix, safe = found[0], bool(sure[0])
            self.flows_from(asks, solution.y0[None, : len(block.names)])
        if not safe:
            # A flow of the block could ask a rate below zero inside the segment: the solver reads
            # the rates at each state that it accepts.
            return
        size, j = len(block.names), solution.instance
        floors = [plan.quantities[name].lower >= 0 for name in block.names]
        reach = []
        for i, name in enumerate(block.names):
            quantity = plan.quantities[name]
            lower, upper = quantity.lower, quantity.upper
            others = [matrix[i, k] for k in range(size) if k != i]
            if not math.isfinite(lower) and not math.isfinite(upper):
                continue
            if all(value == 0 for value in others):
                for bound in (lower, upper):
                    span = _span(matrix[i, i], matrix[i, size], float(solution.y0[i]), bound)
                    if span is not None and solution.t0 + span < self.horizon:
                        reach.append((solution.t0 + span, name))
                continue
            stays = lower == 0 and not math.isfinite(upper) and matrix[i, size] >= 0 and all(floors)
            if stays and all(value >= 0 for value in others):
                continue
            return
        limits = []
        terms = solution.given_terms
        if terms is None:
            terms = [(a[0], b[0], c[0]) for a, b, c in self.group_terms(block, solution.J)]
        for alpha, beta, capacity in terms:
            if alpha + float(beta @ solution.y0[:size]) > capacity:
                return
            reads = np.flatnonzero(beta)
            if not len(reads):
                continue
            i = int(reads[0])
            if len(reads) > 1 or any(matrix[i, k] != 0 for k in range(size) if k != i):
                return
            span = _span(matrix[i, i], matrix[i, size], float(solution.y0[i]), (capacity - alpha) / beta[i])
            if span is not None and solution.t0 + span < self.horizon:
                limits.append(solution.t0 + span)
        solution.matrix, solution.mode = matrix, 'closed'
        for at, name in reach:
            self.entries += 1
            heapq.heappush(self.times, (float(at), self.entries, BOUND, name, j, int(self.lversion[name][j])))
        for at in limits:
            self.entries += 1
            version = int(self.lversion[block.names[0]][j])
            heapq.heappush(self.times, (float(at), self.entries, LIMIT, block.index, j, version))

    def within_bounds(self, solution, y, t):
        for name, cut in solution.slices.items():
            quantity = self.plan.quantities[name]
            at = slice(None) if solution.J is None else solution.J
            values = y[cut]
            if np.any(values < quantity.lower - self.slack[name][at]) or np.any(
                values > quantity.upper + self.atol[name][at]
            ):
                raise Outside(f'{name} at a bound (t = {t:g} h)', space=quantity.space)

    # ---- the restarts ---------------------------------------------------------------------------

    def restart_line(self, name, J, t, value=None):
        """The line of a quantity starts again at t for the instances J (None: all): from `value`, or
        from where it is."""
        plan = self.plan
        quantity = plan.quantities[name]
        at = slice(None) if J is None else J
        y0, t0, rate = self.y0[name], self.t0[name], self.rate[name]
        y = y0[at] + rate[at] * (t - t0[at]) if value is None else value
        if self.record and not self.starting_lines:
            self.line_log.setdefault(name, []).append(
                (
                    t,
                    np.arange(len(y0)) if J is None else np.array(J),
                    y0[at].copy(),
                    t0[at].copy(),
                    rate[at].copy(),
                )
            )
        y0[at], t0[at] = y, t
        env = Env(self, quantity.space, J, t)
        new = self.rate_of(name, env)
        floor = plan.floors.get(name)
        if floor is not None:
            new = self.rest(floor, J, t, env, new)
        rate[at] = new
        self.lversion[name][at] += 1
        self.counts['line restarts'] += env.count
        # A line that falls to its lower bound, or rises to its upper bound, before the horizon:
        # the time goes on the timeline, and the run is outside this engine if the line still holds then.
        places = np.arange(len(y0)) if J is None else np.asarray(J)
        now = y0[at]
        for bound, toward in ((quantity.lower, new < 0), (quantity.upper, new > 0)):
            if not math.isfinite(bound) or not toward.any():
                continue
            with np.errstate(divide='ignore', invalid='ignore'):
                reach = t + (bound - now) / new
            # A quantity that can rest on its lower bound rests there from that time (FLOOR).
            kind = FLOOR if floor is not None and bound == quantity.lower else BOUND
            for j in np.flatnonzero(toward & (reach < self.horizon)).tolist():
                place = int(places[j])
                self.entries += 1
                heapq.heappush(
                    self.times,
                    (float(reach[j]), self.entries, kind, name, place, int(self.lversion[name][place])),
                )

    def rest(self, floor, J, t, env, rate):
        """Whether each instance of a quantity that can rest on its lower bound rests there from this
        restart, and its rate. It rests when it is at the bound and the flows out of it ask more than
        what comes in; the flows then get what comes in, and its rate is 0. It leaves the bound when
        the flows ask no more than what comes in. A change of the resting is a change of a value that
        the flows out of it read: `flag_changes` keeps it for the parts that read those flows."""
        plan = self.plan
        quantity = plan.quantities[floor.name]
        at = slice(None) if J is None else J
        flag = self.v[floor.flag]
        rests = flag[at].copy()
        supply = self.supply(floor, env)
        if floor.group is not None:
            alone = self.rationed(plan.groups[floor.group], env, resting=False)
            asked = np.zeros(env.count)
            for key in floor.outflows:
                asked = asked + alone[key]
        else:
            key = floor.outflows[0]
            asked = _spread(self.value(plan.flows[key], env), env.count).astype(float)
            if key in plan.coupled:
                # What the flows that move with it leave of its request.
                asked = asked * self.fraction(plan.coupled[key], env, but=key)
        now = rests.copy()
        now[rests & (asked <= supply)] = False
        now[~rests & (self.y0[floor.name][at] <= quantity.lower) & (asked > supply)] = True
        changed = now != rests
        if changed.any():
            places = np.arange(len(flag))[at][changed]
            if self.record:
                for place in places.tolist():
                    self.undo.setdefault(floor.flag, []).append((t, place, bool(flag[place])))
            flag[places] = now[changed]
            self.flag_changes.append((floor.flag, set(places.tolist())))
            self.wrote += 1
            # The rate again, with the flows as they are now.
            rate = self.rate_of(floor.name, Env(self, quantity.space, J, t))
        if now.any():
            # At rest: on the bound itself, with no rate. What comes in is what goes out.
            self.y0[floor.name][np.arange(len(flag))[at][now]] = quantity.lower
            rate = np.where(now, 0.0, rate)
        return rate

    def cut(self, block, j, t):
        """The solution of one instance of a block starts again at t from where it is."""
        solution = self.single[block.index][j]
        prior = {(block.index, j): np.array(solution.at(t), dtype=float)}
        self.restart_block(block, {j}, t, {}, prior)

    def segment_end(self, at, block, j):
        """A segment of a component ends at a time: that time is a moment of the timeline for the
        rules and the checks that read the component."""
        self.entries += 1
        version = int(self.lversion[self.plan.blocks[block].names[0]][j])
        heapq.heappush(self.times, (float(at), self.entries, END, block, int(j), version))

    def restart_block(self, block, J, t, forced, prior):
        """The solutions of a block start again at t: for the whole block, or for the instances J.
        `prior` has the state of each just before the step."""
        if block.whole:
            solutions = [(None, self.whole[block.index])]
        else:
            made = self.single[block.index]
            solutions = [(j, made[j]) for j in (range(len(made)) if J is None else sorted(J))]
        for j, solution in solutions:
            y = prior[(block.index, j)]
            for name, place, value in forced.get((block.index, j), ()):
                at = solution.slices[name].start + place
                y[at] = value
            if self.record:
                # The segment that ends here, as it is: a reader of the past asks it.
                self.block_log.setdefault((block.index, j), []).append((t, copy.copy(solution)))
            solution.start(t, y)
            for name in block.names:
                self.lversion[name][slice(None) if j is None else j] += 1
            if block.net:
                self.counts['block restarts'] += 1
                continue  # a component finds its bounds and the form of its segments itself
            self.within_bounds(solution, y, t)
            # How the segment is solved is decided now, and not when a reader first asks: the
            # decision puts on the timeline the time at which a bound or a limit would be reached.
            if (block.index, j) not in self.restart_numeric:
                self.decide(solution)
            self.counts['block restarts'] += 1
