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
from .plan import FORMULA, name_of


class Stocks:
    def __init__(self, run):
        self.run = run
        self.balances = {}  # name -> (exact balance, signed incidence already posted, time)
        self.ends = {}  # incoming generation membership during a stage's membership edits

    def point(self, store, t):
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
                gross += sign * way.transferred(name, t)
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
        residuals = {
            name: rational(bound) - self.stock_balance(name, t)
            for name, bound in levels.items()
            if name not in run.written and name in run.ways.set_of
        }
        if not any(residuals.values()):
            return
        # Each face suggests a distribution on its incident physical legs. If both ends of one
        # leg reach a face together, solve their incidence equations before applying either
        # correction. Otherwise one rounded contact could reopen the face just closed.
        columns, equations, effects = {}, {}, {}
        todo = [name for name, delta in residuals.items() if delta]
        while todo:
            name = todo.pop()
            if name in columns:
                continue
            shares = columns[name] = self.face_shares(name, levels[name], t)
            for connection, weight in shares:
                leg = run.plan.connections[connection]
                for end, sign in ((leg.source, -1), (leg.sink, 1)):
                    if end not in residuals:
                        continue
                    row = equations.setdefault(end, {})
                    row[name] = row.get(name, 0) + sign * weight
                    if end not in columns:
                        todo.append(end)
        factors = _contact_factors(equations, residuals)
        for name, factor in factors.items():
            for connection, weight in columns[name]:
                effects[connection] = effects.get(connection, 0) + factor * weight
        for connection, delta in effects.items():
            if delta:
                leg = run.plan.connections[connection]
                self.adjust(run.ways.instance_of(leg.source or leg.sink), connection, delta, t)

    def face_shares(self, name, bound, t):
        run = self.run
        side = 'outflow' if bound == run.bounds[name][0] else 'inflow'
        sign = -1 if side == 'outflow' else 1
        incidence = self.ends.get((name, side))
        if incidence is None:
            incidence = run.plan.incident(name, side)
        if not incidence:
            return ()
        if len(incidence) == 1:
            return ((incidence[0], sign),)
        # Read the incoming allocation before this instant publishes its outgoing branches.
        earlier = math.nextafter(t, -math.inf) if t else t
        rates = [rational(max(0, run.value(f'{c}.actual_rate', earlier))) for c in incidence]
        total = sum(rates)
        if total:
            return [(c, sign * weight / total) for c, weight in zip(incidence, rates) if weight]
        return ((incidence[0], sign),)

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
        corrected = {}
        for history in record.histories:
            name = name_of(history.key)
            if history.pieces and name in run.ways.set_of:
                actual = float(self.stock_balance(name, end))
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
