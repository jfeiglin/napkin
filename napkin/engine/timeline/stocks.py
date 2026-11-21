"""Physical stock balances and their accepted directed-connection cursors.

A generation starts when a connected set is installed. The numerical method
supplies cumulative physical amounts from its start; each endpoint consumes
them independently when a stage or a change of generation touches that stock.
A query computes the same balance without advancing a cursor.
"""

import math
from dataclasses import replace

from ...core import expr as nodes
from ...core.units import rational
from ...program.record import History, Piece
from ..continuous.transfers import held_elapsed
from ..errors import SimulationError
from .moment import quantity, span
from .plan import FORMULA, name_of


class Stocks:
    def __init__(self, run):
        self.run = run
        self.balances = {}  # name -> (exact balance, signed incidence already posted, time)
        self.ends = {}  # incoming generation membership during a stage's membership edits

    def point(self, store, t, amounts=None):
        """The physical balance and cumulative signed incidence of its installed generation.
        Read both directions from that generation even if a stage already changed membership."""
        entry = self.balances.get(store)
        if entry is not None:
            balance, cursor, at = entry
            if t == at:
                return balance, cursor
        else:
            balance, cursor = rational(self.run.env[store]), 0
        way = self.run.ways.instance_of(store)
        if way is None:
            return balance, cursor
        gross = 0
        for side, sign in (('inflow', 1), ('outflow', -1)):
            names = self.ends.get((store, side))
            if names is None:
                names = self.run.plan.incident(store, side)
            for name in names:
                if amounts is None:
                    amount = way.transferred(name, t)
                else:
                    if name not in amounts:
                        amounts[name] = way.transferred(name, t)
                    amount = amounts[name]
                gross = gross + amount if sign > 0 else gross - amount
        return balance + (gross - cursor), gross

    def stock_balance(self, store, t):
        """Read the accepted physical balance without advancing a posting cursor."""
        return self.point(store, t)[0]

    def post_stock(self, store, t):
        """Materialize an accepted balance once at t. Return whether its cursor advanced."""
        point = self.balances.get(store)
        if point is not None and point[2] == t:
            return False
        balance, cursor = self.point(store, t)
        self.balances[store] = balance, cursor, t
        return True

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
        if not any(residuals.values()) and not others:
            return {}
        # Each face suggests a distribution on its incident physical legs. If both ends of one
        # leg reach a face together, solve their incidence equations before applying either
        # correction. Otherwise one rounded contact could reopen the face just closed.
        levels = dict(levels)
        columns = {}
        todo = [name for name, delta in residuals.items() if delta or name in others]
        while todo:
            name = todo.pop()
            if name in columns:
                continue
            shares = columns[name] = self.face_shares(name, levels[name], t)
            for connection, _ in shares:
                leg = run.plan.connections[connection]
                for end in (leg.source, leg.sink):
                    if end is None or end in run.written:
                        continue
                    if end not in residuals:
                        way = run.ways.instance_of(end)
                        if way is None or (rest := way.resting_value(end, t)) is None:
                            continue
                        levels[end] = rest
                        residuals[end] = rational(rest) - self.stock_balance(end, t)
                    if end not in columns:
                        todo.append(end)
        retained = {}
        if len(columns) == 1 and not others and all(columns.values()):
            effects = _incidence_effects(run.plan, columns, residuals)
        else:
            effects = {}
            for group in _connected_placements(run.plan, columns):
                local = {name: columns[name] for name in group}
                changes = _incidence_effects(run.plan, local, {n: residuals[n] for n in group})
                achieved = dict.fromkeys(group, 0)
                for name, amount in changes.items():
                    leg = run.plan.connections[name]
                    if leg.source in achieved:
                        achieved[leg.source] -= amount
                    if leg.sink in achieved:
                        achieved[leg.sink] += amount
                if all(n not in others and achieved[n] == residuals[n] for n in group):
                    effects.update(changes)
                    continue
                entries = []
                near = []
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
                run.recorder.entry(
                    t, 'settle', 'stock placement', near=tuple(near), placements=tuple(entries)
                )
                if outside:
                    targets = ', '.join(f'{n} targets {v:.17g} from {a:.17g}' for n, a, v in entries)
                    failure = SimulationError(
                        f'incompatible crossing levels of {", ".join(sorted(group))} at {t:g} h: {targets}'
                    )
                    failure.placements = tuple(entries)
                    raise failure
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
                raise problem
        run.occurrences.placed(effects, t)
        for connection, delta in effects.items():
            if delta:
                leg = run.plan.connections[connection]
                self.adjust(run.ways.instance_of(leg.source or leg.sink), connection, delta, t)
        return retained

    def face_shares(self, name, bound, t):
        run = self.run
        lower, upper = run.bounds[name]
        earlier = math.nextafter(t, -math.inf) if t else t
        rates = None

        def speed(connection):
            nonlocal rates
            if rates is None:
                rates = run.ways.instance_of(name).incoming_rates(earlier)
            return max(0, rates(connection))

        def incidence(side):
            connections = self.ends.get((name, side))
            if connections is None:
                connections = run.plan.incident(name, side)
            return [
                leg
                for leg in connections
                if run.plan.connections[leg].source != run.plan.connections[leg].sink
            ]

        if bound == lower:
            side = 'outflow'
        elif bound == upper:
            side = 'inflow'
        else:
            # The direction comes from the incoming trajectory, even when the moment
            # coalesces with a crossing just before or after its mathematical root.
            inflow, outflow = incidence('inflow'), incidence('outflow')
            net = sum(map(speed, inflow)) - sum(map(speed, outflow))
            if net == 0:
                ordered = sorted(
                    [(leg, 1) for leg in inflow] + [(leg, -1) for leg in outflow],
                    key=lambda item: run.plan.number(item[0]),
                )
                return ordered[:1]
            side = 'inflow' if net > 0 else 'outflow'
        sign = -1 if side == 'outflow' else 1
        legs = incidence(side)
        if not legs:
            legs = incidence('inflow' if sign < 0 else 'outflow')
            return ((legs[0], -sign),) if legs else ()
        if len(legs) == 1:
            return ((legs[0], sign),)
        weights = [rational(speed(leg)) for leg in legs]
        total = sum(weights)
        if total:
            return [(c, sign * weight / total) for c, weight in zip(legs, weights) if weight]
        return ((legs[0], sign),)

    def adjust(self, way, connection, adjustment, t):
        """Post one physical correction through its two endpoints, including any open cursor."""
        way.correct(connection, adjustment)
        leg = self.run.plan.connections[connection]
        for end, direction in ((leg.source, -1), (leg.sink, 1)):
            entry = self.balances.get(end)
            if entry is not None and entry[2] == t:
                balance, cursor, _ = entry
                self.balances[end] = balance + direction * adjustment, cursor + direction * adjustment, t

    def release_stock(self, store, t):
        """Close the retired generation and carry its exact balance into its successor."""
        self.run.post_stock(store, t)
        balance = self.balances[store][0]
        self.balances[store] = balance, 0, t
        for side in ('inflow', 'outflow'):
            self.ends.pop((store, side), None)
        return float(balance)

    def replace(self, store, value, balance):
        self.run.post_stock(store, self.run.now)
        old, cursor, at = self.balances[store]
        self.balances[store] = rational(value) if balance is None else balance, cursor, at
        return float(old)

    def external(self, name, value, tx):
        run = self.run
        if isinstance(value, bool) or not isinstance(value, int | float):
            return 0
        if name not in run.plan.moving and name not in self.balances:
            return 0
        previous = run.moment.stage_balance(name, tx) if tx is not None else self.stock_balance(name, run.now)
        return rational(value) - previous

    def project(self, record):
        """Project rounded physical balances at the cutoff into the requested stock histories.
        The saved recorder and all posting cursors remain suitable for a continuing run."""
        end = record.end
        run = self.run
        corrected, amounts = {}, {}
        for history in record.histories:
            name = name_of(history.key)
            if history.pieces and name in run.ways.set_of:
                actual = float(self.point(name, end, amounts)[0])
                if history.at(end) != actual:
                    corrected[name] = actual
        if not corrected:
            return record
        pending = list(corrected)
        while pending:
            source = pending.pop()
            for name in run.recorder._readers.get(source, ()):
                value = run.plan.values[name]
                if (
                    name not in corrected
                    and value.kind == FORMULA
                    and name not in run.frozen
                    and isinstance(value.node, nodes.Ref)
                    and value.node.name == source
                ):
                    corrected[name] = corrected[source]
                    pending.append(name)
        histories = []
        for history in record.histories:
            name = name_of(history.key)
            points = history.pieces
            if name in corrected and points:
                if points[-1].t == end:
                    points = points[:-1]
                histories.append(History(history.key, (*points, Piece(end, corrected[name]))))
            else:
                histories.append(history)
        return replace(record, histories=tuple(histories))


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
        pivots[pivot] = (
            {key: rational(weight) / first for key, weight in row.items() if weight},
            target / first,
        )
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
            if way.resting_value(s, t) is None:
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
            columns = {s: way.run.stock_state.face_shares(s, bound, t) for s, (bound, _, _) in rows.items()}
            for n, delta in _incidence_effects(way.run.plan, columns, residuals).items():
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
                    row[store] = row.get(store, 0) + sign * weight
    for store, factor in _contact_factors(equations, residuals).items():
        for name, weight in columns[store]:
            effects[name] = effects.get(name, 0) + factor * weight
    return effects


def _connected_placements(plan, columns):
    """Only targets connected by a proposed physical correction constrain each other."""
    neighbors = {stock: set() for stock in columns}
    for stock, shares in columns.items():
        for name, _ in shares:
            leg = plan.connections[name]
            for other in (leg.source, leg.sink):
                if other in columns and other != stock:
                    neighbors[stock].add(other)
                    neighbors[other].add(stock)
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
