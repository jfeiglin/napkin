"""The allocation of the flows of a network: what each flow delivers of what it asks.

The requests of the flows are cut to the capacity of their groups and to the fraction of their
coupled transactions (`ration`), and then to what the active bounds of the stocks allow
(`bound_allocation`): a flow out of a stock that rests on its lower bound gets what comes in, and a
flow into a stock at its upper bound is cut. The answer at the bounds is the optimum of one linear
program, which a closed form gives when the stocks decide one after the other (`closed_form`), and
HiGHS otherwise (`linear_program`). `balance` moves a rounding residual of a stock on its zero face
onto a material leg.

`Allocation(system)` reads a network through these attributes of `system`, and nothing else of a
run: `state_ids`, `index`, `flows` (each with `source`, `target`, `allocation`), `flow_ids`,
`flow_index`, `flow_matrix`, `abs_flow_matrix`, `groups` (each with `policy`, `order`),
`group_indices`, `couplings` (each with `flows`), `coupling_members`, `lower`, `upper`, `atol`,
`zero_floor_stocks`, `proven_faces`, `proven_face_set`, `legs` and `quantities` (each with `kind`).
A `System` of the continuous engine is such a network, and so is the network of one space of the
timeline engine. The active bounds and the zero faces of a state are arguments: a set of (row,
'min' or 'max') and a set of rows.

The plans and the rows of a network are kept by the content of the bounds and by the flows that ask
anything, so an `Allocation` serves every evaluation of the network.
"""

from __future__ import annotations

import math

import numpy as np

from .continuous import highs
from .errors import SimulationError


class StockFaces:
    """Which finite bounds participate in allocation at the stock's own comparison scale.

    Held batches inspect individual touched rows. Moving methods classify their accepted
    state vectors together. Neither operation places a stock or changes its accepted balance.
    """

    @classmethod
    def of(cls, run, stores, lower, upper):
        return cls(lower, upper, [run.own_scale(name) for name in stores], run.plan.units.comparisons.factor)

    def __init__(self, lower, upper, scales, factor):
        self.lower, self.upper, self.factor = lower, upper, factor
        self.low_floor = np.where(np.isfinite(lower), np.maximum(scales, np.abs(lower)), 0.0)
        self.high_floor = np.where(np.isfinite(upper), np.maximum(scales, np.abs(upper)), 0.0)

    def at_lower(self, i, value):
        bound = self.lower[i]
        return value <= bound or (
            math.isfinite(bound) and value - bound <= self.factor * max(self.low_floor[i], abs(value))
        )

    def at_upper(self, i, value):
        bound = self.upper[i]
        return value >= bound or (
            math.isfinite(bound) and bound - value <= self.factor * max(self.high_floor[i], abs(value))
        )

    def trial(self, values):
        """Extend the field to an integrator trial outside its physical domain."""
        return np.clip(values, self.lower, self.upper)

    def contact(self, row, value, slope, at, name):
        """The next physically distinct bound on a held line. A sub-band outward
        residual already at its face can reach a material breach, never that same root again."""
        if slope == 0.0:
            return math.inf
        lower = slope < 0
        target = self.lower[row] if lower else self.upper[row]
        if not math.isfinite(target):
            return math.inf
        distance = (target - value) / slope
        if distance <= 0:
            floor = self.low_floor[row] if lower else self.high_floor[row]
            band = self.factor * max(floor, abs(value))
            if abs(value - target) > band:
                raise SimulationError(f'{name}: the accepted transfers move it past its bound at {at:g} h')
            beyond = math.nextafter(target + (-band if lower else band), -math.inf if lower else math.inf)
            distance = (beyond - value) / slope
        return max(math.nextafter(at, math.inf), at + distance)

    def flags(self, values, rows=slice(None)):
        magnitude = np.abs(values)
        low = np.isfinite(self.lower[rows]) & (
            values - self.lower[rows] <= self.factor * np.maximum(self.low_floor[rows], magnitude)
        )
        high = np.isfinite(self.upper[rows]) & (
            self.upper[rows] - values <= self.factor * np.maximum(self.high_floor[rows], magnitude)
        )
        return low, high


def _quotient(left, right):
    """`left / right` as the arithmetic of doubles gives it: by a zero it is an infinity with its
    sign, or no number (0 / 0), where Python raises."""
    try:
        return left / right
    except ZeroDivisionError:
        if left == 0 or left != left:
            return math.nan
        return math.copysign(math.inf, left) * math.copysign(1.0, right)


class Allocation:
    def __init__(self, system):
        self.system = system
        # The active bounds change only between segments; their arrays, and the boundary rows,
        # adjustable flows and allocation plans built from them, serve every evaluation of a
        # segment. Each is built by the same steps, in the same order, every time.
        self._bounds, self._rows, self._units, self._plans = {}, {}, {}, {}
        self._checked = set()  # the boundary rows and requests whose allocation policies passed
        self._priorities = None  # the priority groups, upstream first
        self._rationed = None  # the flows of each group and of each coupled transaction (`ration`)
        self._asking = {}  # the coupled transactions that ask, for each pattern of signs of the requests
        self._quick = {}  # what `served_in_full` reads, for each set of units of the closed form
        self._low_rows, self._sides = {}, {}  # the faces in order and the active upper bounds (`balance`)
        self._proportional = None  # proportional groups joined by material transactions

    def allocated(self, state, base, requested, capacities, active_bounds, zero_faces, bound_key=None):
        """(the rate of each state, the rate that each flow delivers) at one state: from the rates
        that the flows ask (`requested`), the capacities of the groups in their order, the rates of
        the states that are no flow (`base`), and the active bounds and zero faces of the state.
        `bound_key` is (the active bounds, the zero faces) as frozensets, when the caller has it."""
        s = self.system
        if bound_key is None:
            bound_key = (frozenset(active_bounds), frozenset(zero_faces))
        unconstrained_requests = requested.copy()
        # A flow that a bound holds back cannot use its share of a group's capacity. The bound
        # allocation finds the rate that it can take, and the next pass gives the rest of the
        # capacity to the group's other flows. A held rate only falls, so the passes end.
        held = None  # no flow is held yet: each takes its request into the first pass
        balanced_faces = set()
        for _ in range(len(requested) + 1):
            asked = unconstrained_requests if held is None else np.minimum(unconstrained_requests, held)
            rationed, rationing = self.ration(asked, unconstrained_requests, capacities)
            requested, faces = self.bound_allocation(state, base, rationed, unconstrained_requests, bound_key)
            # A later pass sees requests that no longer overdraw a face; it still has to balance.
            balanced_faces |= faces
            if requested is rationed or not rationing:
                break  # the bounds cut nothing, or no group binds: no flow of a group is short
            members = np.array(rationing)
            rate = rationed[members]
            short = members[requested[members] < rate - 1e-12 * np.maximum(1.0, rate)]
            if not len(short):
                break
            if held is None:
                held = np.full(len(requested), np.inf)
            held[short] = requested[short]
        derivative = base + s.flow_matrix @ requested
        self.balance(
            state, base, requested, derivative, balanced_faces, active_bounds, zero_faces, bound_key[0]
        )
        return derivative, requested

    def ration(self, requested, unconstrained, capacities):
        """(the requests after each group's capacity and each coupled transaction's fraction, the
        flows of the groups whose capacity binds): a priority group serves its flows in order, a
        proportional group scales them alike.

        The arithmetic is on Python floats, read once from the arrays: each sum goes from the left
        in the order of the flows, as the sum of the elements of an array does, so the doubles are
        the same."""
        if self._rationed is None:
            s = self.system
            self._rationed = (
                [
                    (
                        group.policy == 'proportional',
                        [int(j) for j in s.group_indices[gid]],
                        [s.flow_index[name] for name in group.order]
                        if group.policy != 'proportional'
                        else (),
                    )
                    for gid, group in s.groups.items()
                ],
                [[int(j) for j in members] for members in s.coupling_members],
            )
        groups, coupled = self._rationed
        rates, asked = requested.tolist(), unconstrained.tolist()
        rationing = []
        for (proportional, indices, ordered), capacity in zip(groups, map(float, capacities)):
            total = 0
            for j in indices:
                total += rates[j]
            if total <= capacity:
                continue
            rationing += indices
            if proportional:
                # A local material bound caps a member without changing the weight
                # of its original request or scaling its remaining allowance again.
                pending = indices
                remaining = capacity
                while pending:
                    weight = 0
                    for j in pending:
                        weight += asked[j]
                    fraction = _quotient(remaining, weight)
                    held = [j for j in pending if rates[j] <= asked[j] * fraction]
                    if not held:
                        for j in pending:
                            rates[j] = asked[j] * fraction
                        break
                    taken = 0
                    for j in held:
                        taken += rates[j]
                    remaining -= taken
                    pending = [j for j in pending if j not in held]
            else:
                remaining = capacity
                for j in ordered:
                    rates[j] = min(rates[j], remaining)
                    remaining -= rates[j]
        # Capacity restriction of any member constrains its entire production
        # transaction, preserving the authored cross-unit material ratios.
        if coupled:
            # The flows of each transaction that ask anything follow from the signs of the requests
            # alone: they are found once for each pattern of signs. A flow that asks nothing moves
            # nothing at any fraction, so it does not bound the fraction of the others.
            pattern = (unconstrained > 0).tobytes()
            asking = self._asking.get(pattern)
            if asking is None:
                asking = [[j for j in members if asked[j] > 0] for members in coupled]
                asking = [members for members in asking if members]
                self._asking[pattern] = asking
            if rates != asked:
                # A transaction none of whose flows has another rate than it asks keeps its rates:
                # its fraction is x / x, which is 1, and each rate is its request times 1.
                changed = {j for j, (rate, request) in enumerate(zip(rates, asked)) if rate != request}
                for members in asking:
                    if changed.isdisjoint(members):
                        continue
                    fraction = min([rates[j] / asked[j] for j in members])
                    for j in members:
                        rates[j] = asked[j] * fraction
        return np.array(rates, dtype=float), rationing

    def bound_arrays(self, key):
        """The arrays of the active bounds of `key`, (the active bounds, the zero faces), each a
        frozenset: their rows in order, whether each is a lower bound, whether its state is on a zero
        face."""
        found = self._bounds.get(key)
        if found is None:
            active_bounds, zero_faces = key
            ordered = sorted(active_bounds)
            rows = np.array([i for i, _ in ordered], dtype=int)
            is_min = np.array([bound == 'min' for _, bound in ordered], dtype=bool)
            on_zero_face = np.array([i in zero_faces for i, _ in ordered], dtype=bool)
            found = self._bounds[key] = (
                rows,
                is_min,
                on_zero_face,
            )
        return found

    def boundary_rows(self, bounds, effective):
        """The constraint rows of the effective bounds, in sorted order, and their adjustable flows."""
        s = self.system
        key = (id(bounds), effective.tobytes())
        found = self._rows.get(key)
        if found is None:
            rows, is_min = bounds[0][effective], bounds[1][effective]
            signs = np.where(is_min, -1.0, 1.0)
            a = signs[:, None] * s.flow_matrix[rows]
            adjustable = set(np.nonzero((a > 0).any(axis=0))[0].tolist())
            for coupling in s.couplings.values():
                members = {s.flow_index[name] for name in coupling.flows}
                if members & adjustable:
                    adjustable |= members
            faces = rows[is_min & s.zero_floor_stocks[rows]]
            found = self._rows[key] = (rows, is_min, signs, a, adjustable, faces)
        return found

    def bound_allocation(self, state, base, requested, unconstrained, bound_key):
        """(the rates that active state bounds allow, the zero faces to balance): the requests, cut
        where a bound holds a stock."""
        s = self.system
        if not bound_key[0]:
            return requested, s.proven_face_set
        bounds = self.bound_arrays(bound_key)
        bound_rows, bound_is_min, bound_on_zero_face = bounds
        at_lower, at_upper = s.faces.flags(state[bound_rows], bound_rows)
        effective = np.where(bound_is_min, bound_on_zero_face | at_lower, at_upper)
        if not effective.any():
            return requested, s.proven_face_set
        balanced_faces = set(s.proven_faces)
        rows, _, signs, a, adjustable_rows, faces = self.boundary_rows(bounds, effective)
        # A zero-stock availability constraint clips an outward requested
        # transaction to its incoming material supply. Its allocated zero
        # velocity can carry multiplication/cancellation roundoff.
        resting = faces[base[faces] == 0]
        if len(resting):
            before_allocation = base + s.flow_matrix @ requested
            balanced_faces.update(s.state_ids[i] for i in resting[before_allocation[resting] < 0])
        b = -signs * base[rows]
        if len(requested) == 0:
            if np.any(b < -1e-14):
                raise SimulationError('Derivative points outside an active state bound')
            return requested, balanced_faces
        adjustable = ()
        excess = a @ requested - b
        outward = excess > 0
        if np.any(outward) and np.any(
            excess[outward] > 32 * np.finfo(float).eps * (np.abs(a[outward]) @ requested + np.abs(b[outward]))
        ):
            self.check_policies(a, b, requested)
            # Inputs not touching a constrained stock are physical supplies;
            # their rates cannot be reduced to make allocation appear feasible.
            adjustable = adjustable_rows
            separable = self.closed_form(a, b, requested, adjustable)
            if separable is not None:
                requested = separable
                adjustable = ()
        if adjustable:
            requested = self.linear_program(a, b, requested, adjustable, unconstrained)
        return requested, balanced_faces

    def check_policies(self, a, b, requested):
        """Flows that compete for one bound row share one explicit allocation group. The answer
        depends only on the rows and on which flows request anything, so a check that passed is
        not repeated."""
        s = self.system
        active = requested > 0
        supply = (b > 0) | ((a < 0) & active).any(axis=1)
        key = (id(a), active.tobytes(), supply.tobytes())
        if key in self._checked:
            return
        # With no incoming resource, every competing delivery has the unique rate zero.
        for row in a[supply & (((a > 0) & active).sum(axis=1) > 1)]:
            contenders = np.nonzero((row > 0) & (requested > 0))[0]
            if len(contenders) > 1:
                policies = {s.flows[s.flow_ids[j]].allocation for j in contenders}
                if len(policies) != 1 or next(iter(policies)) not in s.groups:
                    raise SimulationError(
                        'Competing boundary flows require one explicit common allocation policy'
                    )
        self._checked.add(key)

    def closed_form(self, a, b, requested, adjustable):
        """The boundary LP's unique optimum when constrained stocks allocate one after another.

        A unit is one flow or the active members of one coupled transaction, which share
        a served fraction. Each adjustable unit must draw on exactly one constrained row;
        it may feed others. Rows are allocated upstream first, so a downstream stock sees
        the allocated inflow; a cycle falls back to the LP. Within a row one unit takes
        min(request, available), a priority group fills in order and a proportional group
        scales equally. Serving upstream maximally also maximises downstream supply, so
        this is exactly the optimum the shared-objective LP defines.
        """
        s = self.system
        # The units and the allocation order depend only on which flows are requested and on the
        # signs of the unit columns; both are fixed through a segment, so each plan is built once.
        key = (id(adjustable), (requested > 0).tobytes())
        units = self._units.get(key)
        if units is None:
            units, placed = [], set()
            for members in s.coupling_members:
                active = [j for j in members if requested[j] > 0]
                if not active or not (set(active) & adjustable):
                    continue
                if any(s.flows[s.flow_ids[j]].allocation for j in active):
                    units = ()
                    break
                units.append(active)
                placed |= set(members)
            else:
                units += [[j] for j in adjustable if j not in placed and requested[j] > 0]
            self._units[key] = units
        if units == ():
            return None
        if self.served_in_full(key, units, a, b, requested):
            return requested
        # Each unit's column: its flows' columns of `a`, scaled by their requests and summed in order
        # (`0 + ...` as `sum` does, so a negative zero reads as zero). One flow's columns are taken
        # together; the products are the same.
        singles = [k for k, unit in enumerate(units) if len(unit) == 1]
        matrix = np.empty((len(b), len(units)))
        if singles:
            flows_of = [units[k][0] for k in singles]
            matrix[:, singles] = 0.0 + a[:, flows_of] * requested[flows_of]
        for k, unit in enumerate(units):
            if len(unit) > 1:
                matrix[:, k] = sum(a[:, j] * requested[j] for j in unit)
        signs = matrix.T
        plan_key = (key, (signs > 0).tobytes(), (signs < 0).tobytes())
        plan = self._plans.get(plan_key)
        if plan is None:
            columns = [matrix[:, k] for k in range(len(units))]
            plan = self._plans[plan_key] = self.schedule(
                units, self.plan(units, columns, len(b), len(requested)), a
            )
        if plan is None:
            return None
        steps, fixed, a_fixed, flat, owner = plan
        # The same arithmetic on the same doubles as NumPy scalars, read once as Python floats.
        columns = signs.tolist()
        requested_fixed = requested[fixed]
        fraction = [None] * len(units)
        for r, drawing, entries, priority in steps:
            inflow = sum(-columns[k][r] * fraction[k] for k in drawing)
            available = max(0.0, float(b[r] - a_fixed[r] @ requested_fixed + inflow))
            if priority:
                for k in entries:
                    need = columns[k][r]
                    fraction[k] = min(1.0, available / need)
                    # A unit that is cut takes all that is available, so nothing remains: by the
                    # definition of a cut, and not by the subtraction `available - fraction * need`,
                    # whose roundoff leaves a few units in the last place, of either sign. A negative
                    # remainder would give the next unit a negative rate, and a positive one a rate
                    # that it must not get. A unit that is served in full leaves the rest, and never
                    # less than nothing.
                    available = max(0.0, available - need) if fraction[k] == 1.0 else 0.0
            else:
                total = sum(columns[k][r] for k in entries)
                for k in entries:
                    fraction[k] = min(1.0, available / total)
        allocated = requested.copy()
        allocated[flat] = requested[flat] * np.array([fraction[k] for k in owner], dtype=float)
        return allocated

    def served_in_full(self, key, units, a, b, requested):
        """Whether the closed form serves every unit in full, so that its answer is the request
        itself, found with less work than the closed form: the same fractions from the same
        doubles, with no matrix of every row and unit. It is for units of one flow each, whose plan
        follows from the signs of `a` alone when no product of a request with a column of `a` is
        zero. In any other case, and when a unit is cut, the answer is False and the closed form
        does all of its work.

        In a quiet part of a run a stock rests at a bound with an inflow that equals its outflows
        but for roundoff. The test of the excess (`bound_allocation`) then comes here at each
        evaluation of the field, and each time every unit is served in full."""
        quick = self._quick.get(key)
        if quick is None:
            quick = self._quick[key] = self.quick_plan(key, units, a, len(b), len(requested))
        if not quick:
            return False
        steps, fixed, a_fixed, flows_of, least = quick
        rates = requested.tolist()
        for j in flows_of:
            if rates[j] < least:
                return False
        requested_fixed = requested[fixed]
        fraction = [None] * len(units)
        # The arithmetic of `closed_form`, on the entries of the matrix that the steps read: each is
        # 0.0 + a[r, j] * requested[j], the product of the same two doubles.
        for r, drawing, entries, priority in steps:
            inflow = sum(-(0.0 + coefficient * rates[j]) * fraction[k] for k, j, coefficient in drawing)
            available = max(0.0, float(b[r] - a_fixed[r] @ requested_fixed + inflow))
            if priority:
                for k, j, coefficient in entries:
                    need = 0.0 + coefficient * rates[j]
                    fraction[k] = min(1.0, available / need)
                    if fraction[k] != 1.0:
                        return False
                    available = max(0.0, available - need)
            else:
                total = sum(0.0 + coefficient * rates[j] for _, j, coefficient in entries)
                for k, _, _ in entries:
                    fraction[k] = min(1.0, available / total)
                    if fraction[k] != 1.0:
                        return False
        return True

    def quick_plan(self, key, units, a, count, flows_count):
        """What `served_in_full` reads for one set of units, or False when it does not apply: the
        steps of the plan with the entries of `a` that they read, the fixed flows and their columns,
        the flow of each unit, and the least request for which no product with an entry of `a` is
        zero."""
        if any(len(unit) != 1 for unit in units):
            return False
        flows_of = [unit[0] for unit in units]
        # The matrix of `closed_form` for requests of 1: it has the signs of the matrix of any
        # requests above `least`, and the plan follows from the signs.
        matrix = 0.0 + a[:, flows_of] * 1.0
        signs = matrix.T
        plan_key = (key, (signs > 0).tobytes(), (signs < 0).tobytes())
        plan = self._plans.get(plan_key)
        if plan is None:
            columns = [matrix[:, k] for k in range(len(units))]
            plan = self._plans[plan_key] = self.schedule(
                units, self.plan(units, columns, count, flows_count), a
            )
        if plan is None:
            return False
        steps, fixed, a_fixed, _, _ = plan
        entries_of = a[:, flows_of]
        present = np.abs(entries_of[entries_of != 0])
        least = 1e-300 / float(present.min()) if len(present) else 0.0

        def read(r, ks):
            return [(k, flows_of[k], float(a[r, flows_of[k]])) for k in ks]

        return (
            [(r, read(r, drawing), read(r, entries), priority) for r, drawing, entries, priority in steps],
            (fixed),
            a_fixed,
            flows_of,
            least,
        )

    def plan(self, units, columns, count, flows_count):
        """The rows each unit draws on and feeds, and the upstream-first order of the rows; None
        when a unit draws on more than one row, a group spans rows or the rows form a cycle."""
        s = self.system
        source, rows = [], {}
        for k, column in enumerate(columns):
            positive = np.nonzero(column > 0)[0]
            if len(positive) != 1:
                return None
            source.append(int(positive[0]))
            rows.setdefault(int(positive[0]), []).append(k)
        for gid in s.groups:
            spread = {
                source[k] for k, unit in enumerate(units) if s.flows[s.flow_ids[unit[0]]].allocation == gid
            }
            if len(spread) > 1:
                return None
        feeds = {
            r: {source[k] for k, column in enumerate(columns) if column[r] < 0 and source[k] != r}
            for r in range(count)
        }
        order, done = [], set()
        while len(done) < count:
            ready = [r for r in range(count) if r not in done and feeds[r] <= done]
            if not ready:
                return None
            order += ready
            done |= set(ready)
        # The units feeding each row, in unit order, so its inflow sums the same terms in turn.
        drawing = {r: [k for k in range(len(units)) if columns[k][r] < 0] for r in range(count)}
        moving = {j for unit in units for j in unit}
        fixed = [j for j in range(flows_count) if j not in moving]
        return rows, order, drawing, fixed

    def schedule(self, units, plan, a):
        """The steps of a plan (`plan`), worked out once: for each row in order, the units that feed
        it, its units (a priority group's in the group's order) and whether it is a priority group; the
        fixed flows, their columns of `a`, and each allocated flow with its unit."""
        if plan is None:
            return None
        s = self.system
        rows, order, drawing, fixed = plan
        steps = []
        for r in order:
            if r not in rows:
                continue
            entries = rows[r]
            gid = s.flows[s.flow_ids[units[entries[0]][0]]].allocation
            priority = len(entries) > 1 and gid in s.groups and s.groups[gid].policy == 'priority'
            if priority:
                rank = [s.flow_index[name] for name in s.groups[gid].order]
                entries = sorted(entries, key=lambda k: rank.index(units[k][0]))
            steps.append((r, drawing[r], entries, priority))
        flat = [j for unit in units for j in unit]
        owner = [k for k, unit in enumerate(units) for _ in unit]
        return steps, fixed, np.ascontiguousarray(a[:, fixed]), flat, owner

    def linear_program(self, a, b, requested, adjustable, unconstrained):
        """Serve priority groups in order, then progressively fill proportional requests.

        Physical constraints solve for u_j = rate_j/request_j, avoiding 1/request
        coefficients from vanishing tails. Fair shares retain the original request
        weights even when a previous capacity or material constraint capped a member.
        """
        s = self.system
        scale = np.where(requested > 0, requested, 1.0)
        limits = [
            (0.0, 1.0) if j in adjustable and r > 0 else (float(r > 0), float(r > 0))
            for j, r in enumerate(requested)
        ]
        a_u = a * scale
        equal_a, equal_b = [], []

        def tie(js):
            for j in js[1:]:
                row = np.zeros(len(requested))
                row[j] = 1
                row[js[0]] = -1
                equal_a.append(row)
                equal_b.append(0.0)

        for coupling in s.couplings.values():
            tie([s.flow_index[name] for name in coupling.flows if requested[s.flow_index[name]] > 0])
        objective_all = -(requested > 0).astype(float)

        def solve(objective):
            return highs.solve(objective, a_u, b, equal_a or None, equal_b or None, limits)

        solved = solve(objective_all)
        if not solved.success:
            raise SimulationError(f'No feasible allocation at state boundary: {solved.message}')
        for gid in self.priority_order():
            for name in s.groups[gid].order:
                j = s.flow_index[name]
                if limits[j][0] == limits[j][1]:
                    continue  # nothing to decide: the flow asks for nothing, or no bound limits it
                objective = np.zeros(len(requested))
                objective[j] = -1
                solved = solve(objective)
                if not solved.success:
                    raise SimulationError('Priority allocation is infeasible')
                limits[j] = (float(solved.x[j]), float(solved.x[j]))
            # A single-flow pass leaves every other flow at an arbitrary
            # vertex; restore the shared objective with the ranks pinned.
            solved = solve(objective_all)
            if not solved.success:
                raise SimulationError('Priority allocation is infeasible')
        for component in self.proportional_order():
            js = [j for j in component if requested[j] > 0 and limits[j][0] != limits[j][1]]
            if len(js) < 2:
                continue
            # A group shares its scarce material, not unrelated local bottlenecks. If no
            # active row is drawn on by two members, each can take its own maximum.
            if not np.any((a[:, js] > 0).sum(axis=1) > 1):
                continue
            # Progressive filling maximises the least served fraction. A member whose
            # own queue, destination or other material runs out stays at that fraction;
            # the others share what remains. Tying all fractions would instead waste the
            # remaining supply, and falsely release a stock from its empty face.
            pending = js
            weights = requested[js] / unconstrained[js]
            weights = dict(zip(js, weights))
            while pending:
                # Normalise this waterline to [0, 1]. A very small capped fraction
                # must not become a tiny coefficient for the member that limits it.
                unit = min(weights[j] * limits[j][1] for j in pending)
                floors = np.zeros((len(pending), len(requested) + 1))
                floors[np.arange(len(pending)), pending] = -1
                floors[:, -1] = [unit / weights[j] for j in pending]
                objective = np.zeros(len(requested) + 1)
                objective[-1] = -1
                filled = highs.solve(
                    objective,
                    np.vstack((np.column_stack((a_u, np.zeros(len(b)))), floors)),
                    np.concatenate((b, np.zeros(len(pending)))),
                    np.column_stack((equal_a, np.zeros(len(equal_a)))) if equal_a else None,
                    equal_b or None,
                    [*limits, (0.0, 1.0)],
                )
                if not filled.success:
                    raise SimulationError('Proportional allocation is infeasible')
                level = float(np.clip(filled.x[-1], 0.0, 1.0)) * unit
                fractions = {j: min(limits[j][1], level / weights[j]) for j in pending}
                for j in pending:
                    limits[j] = (max(limits[j][0], fractions[j]), limits[j][1])
                # One optimum is not enough: it can leave a movable member at the
                # waterline just because the solver selected a vertex. Freeze only
                # members that cannot increase while every other floor is retained.
                saturated = []
                for j in pending:
                    objective = np.zeros(len(requested))
                    objective[j] = -1
                    candidate = solve(objective)
                    if not candidate.success:
                        raise SimulationError('Proportional allocation is infeasible')
                    # A served fraction is free to rise only beyond the solver's own tolerance; a
                    # vertex that sits within it of the waterline is the same allocation.
                    if candidate.x[j] <= fractions[j] + highs.FEASIBILITY:
                        saturated.append(j)
                if not saturated:
                    raise SimulationError('Proportional allocation has no limiting member')
                for j in saturated:
                    fraction = fractions[j]
                    limits[j] = (fraction, fraction)
                pending = [j for j in pending if j not in saturated]
        solved = solve(objective_all)
        if not solved.success:
            raise SimulationError('Boundary allocation is infeasible')
        return np.clip(solved.x, 0.0, 1.0) * np.where(requested > 0, requested, 0.0)

    def priority_order(self):
        """The priority groups, each after every group whose flows feed the stocks it draws on: the
        upstream group decides first, as the material reaches the downstream one only through it.
        Groups that feed each other keep the order of the file."""
        if self._priorities is not None:
            return self._priorities
        s = self.system
        groups = [gid for gid, group in s.groups.items() if group.policy == 'priority']
        members = {gid: [s.flows[s.flow_ids[j]] for j in s.group_indices[gid]] for gid in groups}
        self._priorities = self.group_order(members)
        return self._priorities

    def proportional_order(self):
        """Jointly allocate groups sharing a transaction; separate supplies decide upstream first."""
        if self._proportional is not None:
            return self._proportional
        s = self.system
        components = [{gid} for gid, group in s.groups.items() if group.policy == 'proportional']
        for coupling in s.coupling_members:
            linked = {s.flows[s.flow_ids[j]].allocation for j in coupling}
            merged = set()
            other = []
            for component in components:
                if component & linked:
                    merged |= component
                else:
                    other.append(component)
            components = [*other, merged] if merged else other
        rank = {gid: i for i, gid in enumerate(s.groups)}
        components.sort(key=lambda component: min(rank[gid] for gid in component))
        indices = {
            i: sorted(j for gid in component for j in s.group_indices[gid])
            for i, component in enumerate(components)
        }
        members = {i: [s.flows[s.flow_ids[j]] for j in js] for i, js in indices.items()}
        self._proportional = [indices[i] for i in self.group_order(members)]
        return self._proportional

    def group_order(self, members):
        """Material-connected groups in upstream-first order; cycles keep their supplied order."""
        s = self.system
        groups = list(members)
        edges = {}
        for f in s.flows.values():
            if f.source and f.target:
                edges.setdefault(f.source, set()).add(f.target)

        def downstream(stocks):
            """The stocks that these stocks feed, and the stocks themselves."""
            pending = list(stocks)
            found = set(pending)
            while pending:
                stock = pending.pop()
                for to in edges.get(stock, ()):
                    if to not in found:
                        found.add(to)
                        pending.append(to)
            return found

        reach = {gid: downstream(f.target for f in members[gid] if f.target) for gid in groups}
        sources = {gid: {f.source for f in members[gid] if f.source} for gid in groups}
        after = {g: {u for u in groups if u != g and reach[u] & sources[g]} for g in groups}
        order, done = [], set()
        while len(order) < len(groups):
            ready = [g for g in groups if g not in done and after[g] <= done]
            if not ready:  # a cycle: the rest in the order of the file
                ready = [g for g in groups if g not in done]
            order.append(ready[0])
            done.add(ready[0])
        return order

    def balance(
        self, state, base, requested, derivative, balanced_faces, active_bounds, zero_faces, key=None
    ):
        """Conservative zero-face allocations can leave a sub-ulp residual that would falsely
        release the active availability bound. Balance it against an actual material leg,
        preserving the total and the exact zero face.

        The same holds for a stock that rests on its upper bound. When what comes in equals what
        goes out, the sum of its flows keeps the roundoff of its terms, of either sign. A residual
        above zero would carry the stock past its bound, however small it is, and the run would
        stop. Such a residual is no rate: it is within a few units in the last place of the flows
        that make it, as at a zero face, and it goes to the same kind of leg."""
        s = self.system
        index, definitions, legs = s.index, s.quantities, s.legs
        limit = 32 * np.finfo(float).eps
        # The faces in the order of the states, and the active upper bounds: each is kept, for the
        # set of the faces and for the active bounds (`key`: the active bounds as a frozenset, when
        # the caller has it). Most runs have no active upper bound.
        faces = frozenset(balanced_faces)
        low_in_order = self._low_rows.get(faces)
        if low_in_order is None:
            low_in_order = self._low_rows[faces] = sorted(
                (name for name in faces if name in index), key=index.__getitem__
            )
        key = frozenset(active_bounds) if key is None else key
        max_rows = self._sides.get(key)
        if max_rows is None:
            max_rows = self._sides[key] = sorted(i for i, side in key if side == 'max')
        low, high, balanced_in_order = faces, (), low_in_order
        if max_rows:
            # The stocks that rest on their upper bound, exactly.
            high = {s.state_ids[i] for i in max_rows if s.faces.at_upper(i, state[i])}
            if high:
                balanced_in_order = sorted(high.union(low_in_order), key=index.__getitem__)
        for _ in range(len(balanced_in_order)):
            changed = False
            for name in balanced_in_order:
                i = index[name]
                residual = derivative[i]
                # Most faces balance exactly; the tests that follow read nothing that this one changes.
                if residual == 0:
                    continue
                on_low = (
                    name in low
                    and (i, 'min') in active_bounds
                    and (s.faces.at_lower(i, state[i]) or i in zero_faces)
                )
                if not on_low and name not in high:
                    continue
                scale = abs(base[i]) + float(s.abs_flow_matrix[i] @ requested)
                if abs(residual) > limit * scale:
                    continue
                outs, ins, external = legs[name]
                partner = next(
                    (
                        index[to]
                        for j, to in outs
                        if to
                        and requested[j] > 0
                        and (
                            residual >= 0
                            or definitions[to].kind != 'cumulative'
                            or derivative[index[to]] >= -residual
                        )
                    ),
                    None,
                )
                if partner is None:
                    partner = next(
                        (
                            index[source]
                            for j, source in ins
                            if source
                            and requested[j] > 0
                            and not s.faces.at_lower(index[source], state[index[source]])
                        ),
                        None,
                    )
                external_leg = any(requested[j] > 0 for j in external)
                if partner is None and not external_leg:
                    continue
                derivative[i] = 0.0
                if partner is not None:
                    derivative[partner] += residual
                changed = True
            if not changed:
                break
