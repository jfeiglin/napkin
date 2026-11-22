"""The branches and keyed rows of a smooth segment. The arithmetic on them still moves."""

from ...core import expr as nodes
from ..continuous.integrate import branch_expression, comparison_side, departing_branches


class Region:
    """A segment's comparisons and selected key rows, shared by its trial evaluations."""

    def __init__(self, surfaces=(), lookups=None, defined=()):
        self.defined = defined  # rates whose arithmetic is part of this trial field
        self.lookups = lookups or {}
        keys = (pair for rows in self.lookups.values() for pair in rows)
        self.surfaces = tuple(dict.fromkeys((*surfaces, *keys)))
        self.set({}, {})

    def _winners(self, run, signs, compare):
        """Select the greatest eligible key in creation order. The later entry wins a tie."""
        rows = {}
        for name, pairs in self.lookups.items():
            eligible = (k for k in run.kept_of(name) if signs.get(pairs[k], -1) >= 0)
            winner = next(eligible, None)
            if winner is None:
                continue
            for challenger in eligible:
                pair = pairs[winner][1], pairs[challenger][1]
                direction = compare(name, pair)
                if direction is not None and direction <= 0:
                    winner = challenger
            rows[name] = run.plan.keyed[name].names[winner]
        return rows

    def selected_rows(self, run, signs, operand):
        return self._winners(
            run, signs, lambda _, pair: comparison_side(pair, operand, run.plan.units.comparisons)
        )

    def rank_members(self, run, signs, t, y, side_at, rates, places, moving, contacted):
        """Certify the selected row until its eligibility or its rank changes on this trajectory."""
        operand = side_at(t, y)
        ranks = {}
        self.rank_owners = {}

        def compare(name, pair):
            a, b = pair
            if a == b or not (moving(a) or moving(b)):
                return comparison_side(pair, operand, run.plan.units.comparisons)
            direction = departing_branches(
                (pair,),
                t,
                y,
                side_at,
                rates,
                places,
                moving,
                (pair,) if pair in contacted or run.consumed_in((pair,), t) else (),
                run.plan.units.comparisons,
            ).get(pair)
            if direction is not None:
                ranks[pair] = direction
                self.rank_owners.setdefault(pair, []).append(name)
            return direction

        return self._winners(run, signs, compare), ranks

    def set(self, signs, rows):
        """Install the active branches and invalidate expressions selected for the previous segment."""
        self.signs, self.rows = signs, rows
        self._expressions = {}

    def expression(self, node):
        """The expression on this segment, evaluated at the trial time and physical state."""
        if node not in self._expressions:
            self._expressions[node] = branch_expression(node, self.signs)
        return self._expressions[node]

    def keyed(self, name):
        """The engine name selected by a moving lookup on this segment, if it has one."""
        return self.rows.get(name)


def key_surfaces(plan, names, moving):
    """The operands whose crossing can select a different row between moments."""
    return {
        name: [(keyed.key, nodes.ref(k) if isinstance(k, str) else nodes.const(k)) for k in keyed.keys]
        for name in names
        if (keyed := plan.keyed.get(name)) is not None
        and (moving(keyed.key) or any(isinstance(k, str) and moving(nodes.ref(k)) for k in keyed.keys))
    }
