"""The branches and keyed rows of a smooth segment. The arithmetic on them still moves."""

from ...core import expr as nodes
from ..continuous.integrate import branch_expression


class Region:
    """A segment's comparisons and selected key rows, shared by its trial evaluations."""

    def __init__(self, surfaces=(), lookups=None, defined=()):
        self.defined = defined  # rates whose arithmetic is part of this trial field
        self.lookups = lookups or {}
        keys = (pair for rows in self.lookups.values() for pair in rows)
        self.surfaces = tuple(dict.fromkeys((*surfaces, *keys)))
        self.set({}, {})

    def selected_rows(self, run, signs, operand):
        """The greatest eligible key of each lookup on this side; the later entry wins a tie."""
        rows = {}
        for name, pairs in self.lookups.items():
            eligible = [k for k in run.kept_of(name) if signs.get(pairs[k], -1) >= 0]
            if eligible:
                chosen = max(eligible, key=lambda k: (operand(pairs[k][1]), k))
                rows[name] = run.plan.keyed[name].names[chosen]
        return rows

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
        if (keyed := plan.keyed.get(name)) is not None and moving(keyed.key)
    }
