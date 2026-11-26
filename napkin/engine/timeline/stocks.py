"""Physical stock balances and their accepted directed-connection cursors.

A generation starts when a connected set is installed. The numerical method
supplies cumulative physical amounts from its start; each endpoint consumes
them independently when a stage or a change of generation touches that stock.
A query computes the same balance without advancing a cursor.
"""

import math
from dataclasses import replace
from fractions import Fraction
from functools import cached_property

from ...core import expr as nodes
from ...core.literals import Literals, node_parts
from ...core.units import rational
from ...expressions import evaluate
from ...program.record import BalancePoint
from ..continuous.transfers import (
    ZERO_AMOUNT,
    certified_amount,
    clock_primitive,
    held_elapsed,
    polynomial_amount,
)
from ..errors import SimulationError
from .moment import quantity, span
from .plan import DIRECT, FORMULA, INPUT, LEG, name_of
from .reads import Reads

# Test-only: a whole number of units in the last place added to a ledger balance where a
# decision reads it (`Run.value`) and where a rebuilt method starts from it (`release_stock`).
# The ledger and a method's trajectory agree only to the last places, and platforms round those
# differently, so a decision that changes under this probe depends on the platform
# (tests/engine/test_ledger_roundoff.py). Zero in every real run.
LEDGER_PROBE = 0


def exact_posting(point, t, value):
    """The exact balance of a stock's posting `point` (balance, cursor, time) in place of `value`, a
    value of the stock at t, when the posting is at t and its float is `value`: the posting keeps the
    remainder that the float loses. Else `value`."""
    if point is not None and point[2] == t and point[0] != value and float(point[0]) == value:
        return point[0]
    return value


def probed(balance):
    """A ledger balance as a decision or a new trajectory reads it: itself, unless a test moves
    its last places (`LEDGER_PROBE`)."""
    return balance + LEDGER_PROBE * math.ulp(balance) if LEDGER_PROBE else balance


class ContactInterval:
    """The incoming part of a time-shifted contact on which an earlier physical
    moment would also admit all its stock targets. Earlier distinct moments keep
    their prefixes. Compute the suffix only if a hard rate needs checking."""

    def __init__(self, run, t, targets):
        self.run, self.end, self.targets = run, t, targets

    @cached_property
    def start(self):
        start = 0.0
        for name, target, times in self.targets:
            way = self.run.ways.instance_of(name)
            # Held rows keep their last rate change. Moving rows can prove a
            # suffix only from their available incoming solution.
            line = way.linear(name)
            origin = line[2] if line is not None else way.amounts.through
            left = max(start, max(times) - self.run.clock.crossing, origin)
            start = self._since(way, name, target, left, line is not None)
        return start

    def _since(self, way, name, target, left, linear):
        right = self.end
        if left >= right:
            return right

        def admitted(at):
            value = way.incoming_level(name, at)
            return abs(target - value) <= self.run.comparison_band(name, value, target)

        smallest_band = self.run.comparison_band(name, target, target)

        def whole(a, b):
            if not admitted(a) or not admitted(b):
                return False
            if linear:
                return True
            piece = way.motion({name: 1.0}, a, b)
            if piece.spread == 0 or abs(piece.rate) > piece.spread:
                return True  # monotone on this smooth piece
            return abs(piece.value - target) + piece.change <= smallest_band

        knots = () if linear else way.breaks(left, right)
        for a in reversed([left, *knots]):
            if whole(a, right):
                right = a
                continue
            # The endpoints alone cannot rule out a trip outside the band.
            # Keep only a terminal interval whose entire dense form is admitted.
            lo, hi = a, right
            while True:
                middle = lo + (hi - lo) / 2
                if middle in (lo, hi):
                    return hi
                if whole(middle, right):
                    hi = middle
                else:
                    lo = middle
        return left


class Stocks:
    def __init__(self, run):
        self.run = run
        self.balances = {}  # name -> (exact balance, signed incidence already posted, time)
        self.ranges = {}  # exact captured bounds when their float snapshots lose a written digit
        self.ends = {}  # incoming generation membership during a stage's membership edits

    def amount(self, node, units, read, balance_of):
        """Evaluate one authored amount. Keep exact arithmetic and the usual branch/draw selection."""
        reads = Reads(nodes.names(node), read, self.run.now)

        def parts(part):
            op, args, data = node_parts(part)
            if isinstance(part, nodes.Ref):
                value = balance_of(part.name)
                if isinstance(value, nodes.Node):
                    return 'pos', (value,), None
                if value is None:
                    value = units.comparisons.literal_value(part)
                if isinstance(value, Fraction):
                    return 'number', (), (value, '')
            if isinstance(part, nodes.Ref) or op in ('compare', 'within', 'not', 'and', 'or'):
                value = evaluate(part, reads.for_scale(part), units)
                if isinstance(value, int | float | Fraction) and not isinstance(value, bool):
                    return 'number', (), (value, '')
                return 'literal', (), value
            return op, args, data

        exact = Literals(parts, units.exact_scale, units.comparisons.factor).value(node)
        return evaluate(node, reads, units) if exact is None else exact

    def _opening_operand(self, name):
        run = self.run
        if name in self.balances:
            return self.stock_balance(name, run.now)
        value = run.plan.values.get(name)
        if name in run.frozen:
            return None
        if value is not None and (name in run.plan.stocks or value.kind in (FORMULA, INPUT)):
            return value.node
        return None

    def _bounds(self, store, read, *, historical=False):
        run = self.run
        value = run.plan.values[store]
        snapshot = run.bounds.get(store, (-math.inf, math.inf))
        limits = []
        for source, rounded in zip((value.lower, value.upper), snapshot, strict=True):
            if source is None or not math.isfinite(rounded):
                limits.append(rounded)
            elif historical and nodes.names(source):
                limits.append(rational(rounded))
            else:
                limits.append(rational(self.amount(source, run.plan.units, read, self._opening_operand)))
        if limits[0] > limits[1]:
            # Setup already gave a slightly inverted interval its accepted common point.
            limits = [rational(edge) for edge in snapshot]
        return tuple(limits)

    def bounds(self, store):
        retained = self.ranges.get(store)
        if retained is not None:
            return retained
        return tuple(
            rational(edge) if math.isfinite(edge) else edge
            for edge in self.run.bounds.get(store, (-math.inf, math.inf))
        )

    def open(self, store, rounded, *, node=None):
        """Open the exact posting cursor when this concrete stock comes into existence."""
        if store in self.balances:
            return
        run = self.run
        units = run.plan.units
        read = run.value_of
        limits = self._bounds(store, read)
        if limits != self.bounds(store):
            self.ranges[store] = limits
        value = rounded
        if node is not None and not (nodes.names(node) & run.plan.draws.keys()):
            value = self.amount(node, units, read, self._opening_operand)
        balance = rational(value)
        if limits[0] == limits[1] and float(limits[0]) == rounded:
            balance = limits[0]
        self.balances[store] = balance, 0, run.now
        # Numerical trajectories and ordinary reads start from the once-rounded opening.
        run.env[store] = float(balance)

    def restore_missing(self):
        """Older checkpoints posted some stocks lazily. Preserve each saved cursor and its prefix."""
        run = self.run
        for store in sorted(run.plan.stocks):
            if store not in run.env:
                continue
            if store not in self.ranges:
                limits = self._bounds(store, run.value_of, historical=True)
                if limits != self.bounds(store):
                    self.ranges[store] = limits
            if store in self.balances:
                continue
            opening = run.env[store]
            node = run.plan.values[store].node
            # Recover a known written opening when the old checkpoint still contains it.
            # Other snapshots carry their saved value, including changes made before this version.
            if node is not None and not nodes.names(node) and not run.changes.get(store):
                exact = run.plan.units.comparisons.literal_value(node)
                if isinstance(exact, Fraction) and float(exact) == opening:
                    opening = exact
            self.balances[store] = rational(opening), 0, run.changed_start(store)

    def incident(self, store, side):
        """The concrete legs of the incoming installation until its last stock is released."""
        names = self.ends.get((store, side))
        return self.run.plan.incident(store, side) if names is None else names

    def point(self, store, t, amounts=None):
        """The physical balance and cumulative signed incidence of its installed generation.
        Read both directions from that generation even if a stage already changed membership."""
        balance, cursor, at = self.balances[store]
        if t == at:
            return balance, cursor
        way = self.run.ways.instance_of(store)
        if way is None:
            return balance, cursor
        gross = 0
        for side, sign in (('inflow', 1), ('outflow', -1)):
            for name in self.incident(store, side):
                if amounts is None:
                    amount = way.transferred(name, t)
                else:
                    if name not in amounts:
                        amounts[name] = way.transferred(name, t)
                    amount = amounts[name]
                if amount:
                    gross = gross + amount if sign > 0 else gross - amount
        change = gross - cursor if cursor else gross
        return (balance + change if change else balance), gross

    def stock_balance(self, store, t):
        """Read the accepted physical balance without advancing a posting cursor."""
        return self.point(store, t)[0]

    def post_stock(self, store, t, amounts=None):
        """Materialize an accepted balance once at t. Return whether its cursor advanced."""
        point = self.balances.get(store)
        if point is not None and point[2] == t:
            return False
        balance, cursor = self.point(store, t, amounts)
        self.balances[store] = balance, cursor, t
        return True

    def place(self, levels, t):
        """The sole decision on located targets, shared by the timeline and all methods."""
        retained = self.faces(levels, t)
        decided = {name: retained.get(name, value) for name, value in levels.items()}
        self.coordinates = t, decided
        self.changed = levels.keys() - retained.keys()
        return decided

    def install(self, way, state, names):
        """Rebase a numerical trajectory on the stock ledger's accepted placement."""
        now = self.run.now
        at, coordinates = getattr(self, 'coordinates', (None, {}))
        levels = coordinates if now == at else self.run.bound_at
        for name in names:
            if name in levels:
                state[way.place[name]] = levels[name]
        return list(names)

    def faces(self, levels, t):
        """Apply a roundoff correction at a located physical face through an incident leg.
        The same correction reaches the other endpoint when that endpoint consumes this prefix."""
        run = self.run
        # A single draining source can use its numerical level as the best-conditioned
        # primitive. A placement changes that level discontinuously. Preserve its incoming
        # amount and continue from the ordinary integral before applying the placement once.
        for name in levels:
            way = run.ways.instance_of(name)
            donor = getattr(way, 'donor', None)
            if donor is not None and donor[1] == name:
                connection = donor[0]
                before = way.raw_transferred(connection, t)
                way.donor = None
                difference = before - way.raw_transferred(connection, t)
                if difference:
                    way.correct(connection, difference)
        residuals = {
            name: rational(bound) - self.stock_balance(name, t)
            for name, bound in levels.items()
            if name not in run.written and name in run.ways.set_of
        }
        others = getattr(levels, 'others', {})
        located = getattr(levels, 'located', {})
        if not any(residuals.values()) and not others:
            return {}
        # Each face suggests a distribution on its incident physical legs. If both ends of one
        # leg reach a face together, solve their incidence equations before applying either
        # correction. Otherwise one rounded contact could reopen the face just closed.
        levels = dict(levels)
        resting = set()
        columns = {}
        todo = [name for name, delta in residuals.items() if delta or name in others]
        while todo:
            name = todo.pop()
            if name in columns:
                continue
            shares = columns[name] = self.face_shares(name, levels[name], t, name in resting)
            for connection, _ in shares:
                leg = run.plan.connections[connection]
                for end in (leg.source, leg.sink):
                    if end is None or end in run.written:
                        continue
                    if end not in residuals:
                        way = run.ways.instance_of(end)
                        if way is None or way.resting_value(end, t) is None:
                            continue
                        before = self.stock_balance(end, t)
                        # This neighbor has no placement of its own. Even an exactly
                        # bound-looking float can hide a remainder on its physical books.
                        levels[end] = before
                        residuals[end] = ZERO_AMOUNT
                        resting.add(end)
                    if end not in columns:
                        todo.append(end)
        retained, accepted, gross = {}, {}, {}
        groups = (tuple(columns),) if len(columns) == 1 else _connected_placements(run, columns)
        refusals = []
        for group in groups:
            local = {name: columns[name] for name in group}
            effects = _incidence_effects(run.plan, local, {n: residuals[n] for n in group})
            achieved = dict.fromkeys(group, 0)
            for name, amount in effects.items():
                leg = run.plan.connections[name]
                if leg.source in achieved:
                    achieved[leg.source] -= amount
                if leg.sink in achieved:
                    achieved[leg.sink] += amount
            compatible = all(n not in others and achieved[n] == residuals[n] for n in group)
            problem = None
            if compatible:
                targets = [(name, levels[name], located[name]) for name in group if name in located]
                interval = (
                    ContactInterval(run, t, targets) if any(times != {t} for _, _, times in targets) else None
                )
                problem = self._feasibility(effects, t, levels, residuals, interval)
                if problem is None:
                    updates, problem = run.occurrences.placement(effects, t)
                    if problem is None:
                        accepted.update(effects)
                        gross.update(updates)
                        continue
            entries, near = [], []
            outside = False
            for name in sorted(group):
                actual = retained[name] = float(rational(levels[name]) - residuals[name])
                for level in (levels[name], *others.get(name, ())):
                    target = float(level)
                    band = run.comparison_band(name, actual, target)
                    gap = actual - target
                    entries.append((name, actual, target))
                    near.append((name, f'{name} == {target:.17g}', gap, band))
                    outside |= abs(gap) > band
            details = dict(near=tuple(near), placements=tuple(entries))
            if problem is not None:
                details['reason'] = str(problem)
                for key in ('attempts', 'violations', 'refinement'):
                    if hasattr(problem, key):
                        details[key] = getattr(problem, key)
            refusals.append((tuple(entries), details, problem, outside))
        refusals.sort(key=lambda item: item[0])
        for _, details, _, _ in refusals:
            run.recorder.entry(t, 'settle', 'stock placement', **details)
        if any(outside for _, _, _, outside in refusals):
            readings = tuple(sorted(row for entries, *_ in refusals for row in entries))
            reasons = sorted({str(problem) for _, _, problem, _ in refusals if problem})
            targets = ', '.join(f'{n} targets {v:.17g} from {a:.17g}' for n, a, v in readings)
            names = ', '.join(sorted({name for name, _, _ in readings}))
            problem = SimulationError(
                f'incompatible crossing levels of {names} at {t:g} h: {targets}'
                + ('. ' + '. '.join(reasons) if reasons else '')
            )
            problem.placements = readings
            attempts = [entry for _, details, _, _ in refusals for entry in details.get('attempts', ())]
            if attempts:
                problem.attempts = tuple(
                    sorted(attempts, key=lambda v: (v[0], v[1] == 'inflow', run.plan.number(v[2])))
                )
                problem.violations = tuple(v[:3] for v in problem.attempts)
            raise problem
        run.occurrences.transferred.update(gross)
        for connection, delta in accepted.items():
            if delta:
                leg = run.plan.connections[connection]
                self.adjust(run.ways.instance_of(leg.source or leg.sink), connection, delta, t)
        return retained

    def _feasibility(self, effects, t, levels, residuals, interval):
        run = self.run
        # Both ends of each proposed transfer share the same amount. Check the
        # combined change at each finite bound before any physical or gross post.
        net = {}
        for connection, delta in effects.items():
            if delta:
                leg = run.plan.connections[connection]
                for end, change in ((leg.source, -delta), (leg.sink, delta)):
                    if end is not None:
                        net[end] = net.get(end, 0) + change
        for store, change in net.items():
            lower, upper = run.bounds[store]
            if not change or not math.isfinite(lower if change < 0 else upper):
                continue
            before = (
                rational(levels[store]) - residuals[store]
                if store in residuals
                else self.stock_balance(store, t)
            )
            after = before + change
            if (change < 0 and after < rational(lower)) or (change > 0 and after > rational(upper)):
                available = before - rational(lower) if change < 0 else rational(upper) - before
                affected = [
                    name
                    for name, delta in effects.items()
                    if delta and store in (run.plan.connections[name].source, run.plan.connections[name].sink)
                ]
                problem = SimulationError(
                    f'the placement on {", ".join(affected)} at {t:g} h would change {store} '
                    f'by {quantity(run.plan, store, float(change))} to {quantity(run.plan, store, float(after))}, '
                    f'outside its range {span(run.plan, store, lower, upper)}; '
                    f'{quantity(run.plan, store, float(available))} available'
                )
                problem.placements = ((store, float(before), float(after)),)
                return problem
        problem = self._flow_limits(effects, t, interval=interval)
        if problem is not None and interval is not None:
            # A correction that reproduces the incoming physical rates restores a
            # numerical integral. It requires no additional service near the root.
            try:
                if self._corrects_integral(effects, t):
                    return self._flow_limits(effects, t)
            except SimulationError as uncertainty:
                problem.refinement = str(uncertainty)
        return problem

    def _corrects_integral(self, effects, t):
        for name, change in effects.items():
            if not change:
                continue
            flow = self.run.plan.connections[name]
            way = self.run.ways.instance_of(flow.source or flow.sink)
            start = getattr(way.amounts, 'through', t)
            if start >= t:
                return False
            actual = way.raw_transferred(name, t) - way.raw_transferred(name, start)
            fixed, measured = way.watch_leg(
                name, start, label=f'{name}: cannot certify the incoming transfer'
            )(start, t)
            if actual + change != fixed + measured:
                return False
        return True

    def physical_face_net(self, way, row, rates):
        """A face flag can keep its allocation while hard transfers move its balance.
        Test the proportional correction of the incident rates before treating it as stationary."""
        store = way.stores[row]
        incoming = self.incident(store, 'inflow')
        outgoing = self.incident(store, 'outflow')

        if (
            len(incoming) == len(outgoing) == 1
            and rates[way.leg_rows[incoming[0]]] == rates[way.leg_rows[outgoing[0]]]
        ):
            return 0.0

        def value(name):
            return rational(rates[way.leg_rows[name]])

        inward, outward = sum(map(value, incoming)), sum(map(value, outgoing))
        delta = inward - outward
        if not delta:
            return 0.0
        # The release threshold describes allocation, never a physical loss of
        # traffic. Only rounding of an actually balanced allocation can be leveled.
        if abs(delta) > (inward + outward) * 32 * math.ulp(1.0):
            return float(delta)
        faces = getattr(way, 'faces', None)
        if faces is None:
            faces, level = way.component.system.faces, way.component.state.y[row]
        else:
            level = way.y[row]
        low = faces.at_lower(row, level)
        active = outgoing if low else incoming
        speeds = {name: value(name) for name in active if rates[way.leg_rows[name]] > 0}
        total = sum(speeds.values())
        if not total:
            return float(delta)
        adjustments = {name: (delta if low else -delta) * speed / total for name, speed in speeds.items()}
        return float(delta) if not self.admits_rates(way, adjustments, rates) else 0.0

    def admits_rates(self, way, changes, rates):
        return self._flow_limits(changes, self.run.now, installed=way, rates=rates) is None

    def _flow_limits(self, effects, t, *, installed=None, rates=None, interval=None):
        """Use the same hard rows for an incidence-rate refinement and a located
        physical posting. A rate uses one unit of time; a posting uses accepted amounts."""
        run, plan = self.run, self.run.plan
        ends, solvers, groups, capped = {}, {}, {}, {}
        for name, delta in effects.items():
            if not delta:
                continue
            c = plan.connections[name]
            way = installed or run.ways.instance_of(c.source or c.sink)
            if getattr(way, 'declared', None) is not None and way.declared.constraints:
                solvers.setdefault(way, {})[name] = delta
            if c.role == LEG:
                groups[name.rsplit('.', 1)[0]] = way
            if c.capacity is not None:
                capped.setdefault((way, c.capacity), []).append((name, delta))
            if delta < 0:
                before = (
                    rational(rates[way.leg_rows[name]]) if rates is not None else way.raw_transferred(name, t)
                )
                if before < -delta:
                    return SimulationError(f'the placement on {name} at {t:g} h exceeds its accepted amount')
            for store, side in ((c.source, 'outflow'), (c.sink, 'inflow')):
                endpoint = plan.ends.get((store, side))
                if endpoint is not None and endpoint.capacity is not None:
                    ends[store, side] = ends.get((store, side), 0) + delta
        for flow in groups:
            fraction = None
            for leg in plan.flows[flow].connections:
                change = effects.get(leg.name, 0)
                request = run.value(leg.request, t)
                if not request:
                    if change:
                        return SimulationError(f'the placement at {t:g} h would change closed leg {leg.name}')
                    continue
                part = change / rational(request)
                if fraction is not None and part != fraction:
                    return SimulationError(
                        f'the placement at {t:g} h would split the served fraction of {flow}'
                    )
                fraction = part
        for (way, capacity), changes in capped.items():
            names = [n for n, _ in changes]
            first = plan.connections[names[0]]
            if first.role not in (DIRECT, LEG):
                names = [leg.name for leg in plan.flows[first.name.rsplit('.', 1)[0]].connections]
            if self._over_capacity(way, names, capacity, sum(v for _, v in changes), t, rates, interval):
                return SimulationError(f'the placement on {", ".join(names)} at {t:g} h exceeds {capacity}')
        for (store, side), change in ends.items():
            capacity = plan.ends[store, side].capacity
            if self._over_capacity(
                installed or run.ways.instance_of(store),
                self.incident(store, side),
                capacity,
                change,
                t,
                rates,
                interval,
            ):
                return SimulationError(f'the placement at {t:g} h exceeds {capacity}')
        for way, changes in solvers.items():
            conflict = way.placement_relation(changes, t, rates=rates is not None, interval=interval)
            if conflict is not None:
                return SimulationError(f'the placement at {t:g} h would violate {conflict}')
        return None

    def _over_capacity(self, way, names, capacity, change, t, rates, interval):
        if change <= 0:
            return False
        if rates is not None:
            limit = self.run.value(capacity, t)
            return math.isfinite(limit) and sum(
                rational(rates[way.leg_rows[n]]) for n in names
            ) + change > rational(limit)
        moving = self.run.triggers.moving_reads(nodes.ref(capacity))
        primitive = clock_primitive(nodes.ref(capacity), self.run.plan) if moving else None
        limit = None if moving else self.run.value(capacity, t)
        if limit is not None and not math.isfinite(limit):
            return False
        start = way.amounts.through if moving else way.amounts.start
        if moving and start >= t:
            return True  # at a purely observational stop placement precedes closure
        starts = [start]
        if interval is not None and interval.start > start:
            starts.append(interval.start)
        for since in starts:
            if limit is not None:
                allowed = rational(limit) * held_elapsed(since, t)
            elif primitive is not None:
                allowed = polynomial_amount(primitive, since, t)
            else:
                # The window [through, t] is the present segment's: read the capacity on the
                # branches that the segment ran on (`Way.held_value`), never a comparison
                # decided again at each time, which can flip inside its band before the switch.
                allowed = certified_amount(
                    lambda at: way.held_value(capacity, min(at, math.nextafter(t, since))),
                    since,
                    t,
                    f'{capacity}: cannot certify the accepted capacity',
                )
            if since == way.amounts.start:
                carried = sum(way.raw_transferred(n, t) for n in names)
            else:
                carried = sum(way.raw_transferred(n, t) - way.raw_transferred(n, since) for n in names)
            if carried + change > allowed:
                return True
        return False

    def face_shares(self, name, bound, t, resting=False):
        run = self.run
        lower, upper = run.bounds[name]
        earlier = math.nextafter(t, -math.inf) if t else t
        rates = None

        def speed(connection):
            nonlocal rates
            if rates is None:
                way = run.ways.instance_of(name)
                kept = getattr(way, 'arrival_rates', None)
                rates = (
                    kept[1].__getitem__
                    if resting and kept is not None and kept[0] == t
                    else way.incoming_rates(earlier)
                )
            return max(0, rates(connection))

        def incidence(side):
            connections = self.incident(name, side)
            return [
                leg
                for leg in connections
                if run.plan.connections[leg].source != run.plan.connections[leg].sink
            ]

        if bound == lower or (
            resting
            and math.isfinite(lower)
            and bound - lower <= run.comparison_band(name, float(bound), lower)
        ):
            side = 'outflow'
        elif bound == upper or (
            resting
            and math.isfinite(upper)
            and upper - bound <= run.comparison_band(name, float(bound), upper)
        ):
            side = 'inflow'
        else:
            # The direction comes from the incoming trajectory, even when the moment
            # coalesces with a crossing just before or after its mathematical root.
            inflow, outflow = incidence('inflow'), incidence('outflow')
            net = sum(map(speed, inflow)) - sum(map(speed, outflow))
            if net == 0:
                return ()
            side = 'inflow' if net > 0 else 'outflow'
        sign = -1 if side == 'outflow' else 1
        legs = incidence(side)
        if len(legs) == 1:
            return ((legs[0], sign),) if speed(legs[0]) > 0 else ()
        weights = [rational(speed(leg)) for leg in legs]
        total = sum(weights)
        return [(c, sign * w / total) for c, w in zip(legs, weights) if w] if total else ()

    def adjust(self, way, connection, adjustment, t):
        """Post one physical correction through its two endpoints, including any open cursor."""
        way.correct(connection, adjustment)
        leg = self.run.plan.connections[connection]
        for end, direction in ((leg.source, -1), (leg.sink, 1)):
            entry = self.balances.get(end)
            if entry is not None and entry[2] == t:
                balance, cursor, _ = entry
                self.balances[end] = balance + direction * adjustment, cursor + direction * adjustment, t

    def release_stock(self, store, t, amounts=None):
        """Close the retired generation and carry its exact balance into its successor."""
        self.run.post_stock(store, t, amounts)
        balance = self.balances[store][0]
        self.balances[store] = balance, 0, t
        return probed(float(balance))

    def replace(self, store, value, balance):
        """Apply the stage or edit and report whether it changed the physical balance."""
        self.run.post_stock(store, self.run.now)
        old, cursor, at = self.balances[store]
        new = rational(value) if balance is None else balance
        self.balances[store] = new, cursor, at
        return new != old

    def external(self, name, value, tx):
        run = self.run
        if isinstance(value, bool) or not isinstance(value, int | float | Fraction):
            return 0
        if name not in run.plan.stocks:
            return 0
        previous = run.moment.stage_balance(name, tx) if tx is not None else self.stock_balance(name, run.now)
        return rational(value) - previous

    def _failure_balance_time(self, name, end):
        """Use the accepted transfer ledger. A failed trial can report a later diagnostic time."""
        run = self.run
        accepted = min(end, run.accepted)
        way = run.ways.instance_of(name)
        # A numerical way commits the integral of a step at through. A held rate
        # gives its integral directly up to the accepted timeline time.
        through = getattr(getattr(way, 'amounts', None), 'through', accepted)
        # The stock can also have a newer exact posting from an accepted stage.
        return max(self.balances[name][2], min(accepted, through))

    def project(self, record, recorder=None):
        """Show the exact balance of each moving stock and its direct aliases at an inclusive cutoff.
        An added balance point is exempt from the budget. An actual posting at the cutoff still counts."""
        end = record.end
        if record.after(end) is not None:
            return record
        run = self.run
        recorder = run.recorder if recorder is None else recorder
        histories = {name_of(h.key): h for h in record.histories}
        projected, amounts = {}, {}
        for name in recorder._order:
            history = histories.get(name)
            if history is None or not history.pieces:
                continue
            if name in self.balances:
                at = end if record.failure is None else self._failure_balance_time(name, end)
                actual = float(self.point(name, at, amounts)[0])
                last = history.pieces[-1]
                if last.curve is None and last.rate == 0 and last.at(end) == actual:
                    continue
                endpoint = BalancePoint(end, actual)
            else:
                value = run.plan.values[name]
                if value.kind != FORMULA or not isinstance(value.node, nodes.Ref) or name in run.frozen:
                    continue
                source = value.node.name
                if source not in projected:
                    continue
                raw = recorder.supplied_binding(name, value)
                if raw and raw[0][0] <= end:
                    continue
                # The binding already owns its native prefix, including earlier definitions.
                # Its last reading comes from the source's final history.
                endpoint = projected[source].pieces[-1]
            pieces = history.pieces
            if pieces[-1].t == end:
                # Keep the charge on a real landing, including the start of an alias binding.
                last = pieces[-1]
                actual = endpoint.at(end)
                if last.at(end) != actual:
                    last = replace(last, value=actual, rate=0.0, curve=None)
                pieces = (*pieces[:-1], last)
            else:
                pieces = (*pieces, endpoint)
            projected[name] = replace(history, pieces=pieces)
        if not projected:
            return record
        return replace(record, histories=tuple(projected.get(name, h) for name, h in histories.items()))


def _contact_factors(equations, residuals):
    """Solve the exact incidence equations. Dependent rows are usual when both ends of a
    closed network arrive together; an unconstrained coefficient can then remain zero."""
    pivots = {}
    for store, coefficients in equations.items():
        row = dict(coefficients)
        target = residuals[store]
        while (pivot := next((k for k, weight in row.items() if weight and k in pivots), None)) is not None:
            multiplier = row.pop(pivot)
            previous, value = pivots[pivot]
            target -= multiplier * value
            for key, weight in previous.items():
                row[key] = row.get(key, 0) - multiplier * weight
        pivot = next((key for key, weight in row.items() if weight), None)
        if pivot is None:
            continue
        first = row.pop(pivot)
        row = {key: weight for key, weight in row.items() if weight}
        if first != 1:
            row = {key: rational(weight) / first for key, weight in row.items()}
            target /= first
        pivots[pivot] = row, target
    result = {}
    for pivot, (row, target) in reversed(pivots.items()):
        result[pivot] = target - sum(weight * result.get(key, 0) for key, weight in row.items())
    return result


class RestingRates:
    """Exact incidence at stores whose held allocation keeps them on a face.

    Only stores with positive pass-through have a constraint. A rate change
    revisits the adjacent constrained component. Its small rate corrections
    accrue as ordinary rectangles until the next change of that allocation.
    """

    def __init__(self):
        self.sides = {}
        self.offsets = {}

    def update(self, way, changed, rate, t):
        net = way.net
        previous = {s for s in changed if s in self.sides}
        for store, side in changed.items():
            if side is None:
                self.sides.pop(store, None)
            else:
                self.sides[store] = side
        todo = list(previous | {s for s in changed if s in self.sides})
        visited, connections, rows = set(), set(), {}
        while todo:
            s = todo.pop()
            if s in visited:
                continue
            visited.add(s)
            signed = {}
            for side, sign in ((0, -1), (1, 1)):
                for c in net.ends[side].of(s).tolist():
                    name = net.connections[c]
                    if not rate[c] and name not in self.offsets:
                        continue
                    connections.add(name)
                    signed[name] = signed.get(name, 0) + sign
                    neighbor = int(net.source[c] if sign > 0 else net.sink[c])
                    if neighbor in self.sides and neighbor not in visited:
                        todo.append(neighbor)
            if s in self.sides:
                rows[s] = {name: sign for name, sign in signed.items() if sign}
        if not connections:
            return
        speeds = {name: rational(rate[way.leg_rows[name]]) for name in connections}
        residuals = {s: -sum(sign * speeds[n] for n, sign in row.items()) for s, row in rows.items()}
        updated = {}
        if any(residuals.values()):
            columns = {}
            for s, row in rows.items():
                sign = -1 if self.sides[s] == 0 else 1
                group = [n for n, direction in row.items() if direction == sign and speeds[n]]
                total = sum(speeds[n] for n in group)
                columns[way.stores[s]] = [(n, sign * speeds[n] / total) for n in group]
            updated = _incidence_effects(
                way.run.plan, columns, {way.stores[s]: r for s, r in residuals.items()}
            )
        if any(
            abs(delta) > 32 * math.ulp(1.0) * sum(speeds[n] for n in rows[s])
            for s, delta in residuals.items()
        ):
            updated.clear()
        if updated and not way.run.stock_state.admits_rates(way, updated, rate):
            updated.clear()
        for n in connections:
            old = self.offsets.get(n)
            new = updated.get(n, 0)
            if (old is None and not new) or (old is not None and old[1] == new):
                continue
            if old is not None:
                start, adjustment = self.offsets.pop(n)
                if t != start:
                    way.correct(n, adjustment * held_elapsed(start, t))
            if new:
                self.offsets[n] = t, new


class RestingAmounts:
    """Conserve each resting store's signed prefix on demand during a moving regime.

    A query follows only the connected resting stores incident to its leg. A mode
    change closes the old constraint; an empty event does not settle other stores.
    """

    def __init__(self):
        self.rows = {}  # store -> (physical face, signed gross prefix at entry, incidence)
        self.incident = {}  # connection -> the resting stores it touches
        self.time = None
        self.cache = {}

    def invalidate(self):
        self.time = None
        self.cache.clear()

    def update(self, way, levels, at):
        changed = {
            s
            for s in self.rows.keys() | levels.keys()
            if s not in levels or s not in self.rows or self.rows[s][0] != levels[s]
        }
        if not changed:
            return
        new_rows = {
            store: tuple(
                (name, sign)
                for side, sign in (('outflow', -1), ('inflow', 1))
                for name in way.run.plan.incident(store, side)
                if way.run.plan.connections[name].source != way.run.plan.connections[name].sink
            )
            for store in changed & levels.keys()
        }
        # A new or departing constraint can touch an old one. Close only their
        # affected components, regardless of which other stores were previously read.
        self.invalidate()
        for store in changed & self.rows.keys():
            _, _, row = self.rows[store]
            if row:
                self.amount(way, row[0][0], at)
        for row in new_rows.values():
            for name, _ in row:
                if name in self.incident:
                    self.amount(way, name, at)
        for name, delta in list(self.cache.items()) if self.time == at else ():
            if delta:
                way.correct(name, delta)
        self.invalidate()
        for store in changed & self.rows.keys():
            _, _, row = self.rows.pop(store)
            for name, _ in row:
                self.incident[name].remove(store)
                if not self.incident[name]:
                    del self.incident[name]
        for store, row in new_rows.items():
            if not row:
                continue
            target = sum(sign * way.raw_transferred(n, at) for n, sign in row)
            self.rows[store] = levels[store], target, row
            for name, _ in row:
                self.incident.setdefault(name, set()).add(store)

    def amount(self, way, name, t):
        if name not in self.incident:
            return 0
        if t != self.time:
            self.cache.clear()
            self.time = t
        if name in self.cache:
            return self.cache[name]
        todo, rows, raw, checked = list(self.incident[name]), {}, {}, set()
        while todo:
            s = todo.pop()
            if s in checked:
                continue
            checked.add(s)
            # An exact smooth solution can leave a face with zero initial slope:
            # the next compartment of a filling chain starts with zero inflow.
            # Its actual trajectory decides whether this prefix still rests.
            if way.accepted_level(s, t) != self.rows[s][0]:
                continue
            rows[s] = self.rows[s]
            for leg, _ in self.rows[s][2]:
                if leg not in raw:
                    raw[leg] = way.raw_transferred(leg, t)
                    todo.extend(self.incident[leg])
        self.cache.update(dict.fromkeys(raw, 0))
        residuals = {
            s: target - sum(sign * raw[n] for n, sign in row) for s, (_, target, row) in rows.items()
        }
        if any(residuals.values()):
            columns = {
                s: way.run.stock_state.face_shares(s, bound, t, resting=True)
                for s, (bound, _, _) in rows.items()
            }
            adjustments = _incidence_effects(way.run.plan, columns, residuals)
            if not way.run.stock_state._flow_limits(adjustments, t, installed=way):
                for n, delta in adjustments.items():
                    self.cache[n] += delta
        return self.cache.get(name, 0)


def _incidence_effects(plan, columns, residuals):
    if len(columns) == 1:
        store, shares = next(iter(columns.items()))
        return {name: residuals[store] * weight for name, weight in shares}
    equations, effects = {}, {}
    for store, shares in columns.items():
        for name, weight in shares:
            leg = plan.connections[name]
            for end, sign in ((leg.source, -1), (leg.sink, 1)):
                if end in residuals:
                    row = equations.setdefault(end, {})
                    previous = row.get(store, 0)
                    row[store] = previous + weight if sign > 0 else previous - weight
    for store, factor in _contact_factors(equations, residuals).items():
        for name, weight in columns[store]:
            effects[name] = effects.get(name, 0) + factor * weight
    return effects


def _connected_placements(run, columns):
    """Targets are coupled by a leg, a finite stock, a capped endpoint, a
    common served fraction or a shared hard relation in their incoming solve."""
    plan = run.plan
    neighbors = {stock: set() for stock in columns}
    first = {}
    for stock, shares in columns.items():
        for name, _ in shares:
            leg = plan.connections[name]
            way = run.ways.instance_of(stock)
            groups = [('leg', name)]
            for other, side in ((leg.source, 'outflow'), (leg.sink, 'inflow')):
                if other in columns and other != stock:
                    neighbors[stock].add(other)
                    neighbors[other].add(stock)
                if other is None:
                    continue
                if other in run.occurrences.watched() or any(map(math.isfinite, run.bounds[other])):
                    groups.append(('stock', other))
                endpoint = plan.ends.get((other, side))
                if endpoint is not None and endpoint.capacity is not None:
                    groups.append(('capacity', endpoint.capacity))
            if leg.role != DIRECT:
                groups.append(('flow', name.rsplit('.', 1)[0]))
            if getattr(way, 'declared', None) is not None and way.declared.constraints:
                groups.extend(way.placement_rows(name))
            for key in groups:
                neighbor = first.setdefault(key, stock)
                if stock != neighbor:
                    neighbors[neighbor].add(stock)
                    neighbors[stock].add(neighbor)
    seen = set()
    for start in columns:
        if start in seen:
            continue
        group, pending = [], [start]
        while pending:
            stock = pending.pop()
            if stock not in seen:
                seen.add(stock)
                group.append(stock)
                pending.extend(neighbors[stock])
        yield group
