"""The bound values reached by the contacts of an installed segment."""

import heapq


class Placements(dict):
    """Located stock targets, retaining distinct simultaneous targets of the same stock."""

    def __init__(self, levels=()):
        super().__init__(levels)
        self.others = {}
        self.located = {}

    def add(self, name, target, *, at=None):
        if at is not None:
            self.located.setdefault(name, set()).add(at)
        if name not in self:
            self[name] = target
        elif self[name] != target:
            others = self.others.setdefault(name, [])
            if target not in others:
                others.append(target)

    def include(self, levels):
        for name, times in levels.located.items():
            self.located.setdefault(name, set()).update(times)
        for name, target in levels.items():
            self.add(name, target)
            for other in levels.others.get(name, ()):
                self.add(name, other)

    @classmethod
    def from_bounds(cls, bounds, events):
        levels = cls()
        for at, name, kind in events:
            if kind in ('lower bound', 'upper bound'):
                levels.add(name, bounds[name][kind == 'upper bound'], at=at)
        return levels


def bound_values(bounds, events):
    """The exact faces of stores whose located contacts are due at this instant."""
    return {
        name: bounds[name][kind == 'upper bound']
        for _, name, kind in events
        if kind in ('lower bound', 'upper bound')
    }


def put_bounds(way, state, events):
    """Snap just the due stores and return their names for the sharing that follows."""
    return way.run.stock_state.install(way, state, bound_values(way.run.bounds, events))


def continued_lines(way, levels, t):
    """Restart just the held lines whose grouped placement kept the incoming level."""
    rows = []
    for name in levels:
        if name in way.place:
            row = way.place[name]
            way.y[row], way.since[row] = levels[name], t
            rows.append(row)
    return rows


def put_lines(way, t=None, through=None, invalidate=True):
    """Anchor each due line on its face and retire its old prediction. With no cutoff,
    take one row, so a Lines step can re-share before the next row is consumed."""
    events = []
    while way.due and (through is None or way.peek() <= through):
        at, row, _ = heapq.heappop(way.due)
        kind = 'lower bound' if way.slope[row] < 0 else 'upper bound'
        events.append((at, way.stores[row], kind))
        way.since[row], way.slope[row] = at if t is None else t, 0.0
        if invalidate:
            way.version[row] += 1
        if through is None:
            break
    return put_bounds(way, way.y, events)
