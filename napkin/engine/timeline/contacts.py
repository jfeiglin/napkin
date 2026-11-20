"""The bound values reached by the contacts of an installed segment."""

import heapq


def bound_values(bounds, events):
    """The exact faces of stores whose located contacts are due at this instant."""
    return {
        name: bounds[name][kind == 'upper bound']
        for _, name, kind in events
        if kind in ('lower bound', 'upper bound')
    }


def put_bounds(way, state, events):
    """Snap just the due stores and return their names for the sharing that follows."""
    found = bound_values(way.run.bounds, events)
    for name, number in found.items():
        state[way.place[name]] = number
    return list(found)


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
