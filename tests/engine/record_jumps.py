"""Recognize corresponding discontinuities when comparing two recorded histories."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby
from math import inf, nextafter, ulp
from numbers import Real


def _number(value):
    return isinstance(value, (Real, Decimal)) and not isinstance(value, bool)


@dataclass(frozen=True)
class Jump:
    time: float
    left: object
    right: object

    def transition(self, scale):
        if _number(self.left) and _number(self.right):
            a, b = float(self.left), float(self.right)
            # A continuous fit can have last-bit roundoff at a seam.
            if abs(a - b) <= 8 * ulp(max(scale, abs(a), abs(b))):
                return None
            return ('increase',) if b > a else ('decrease',)
        if self.left != self.right:
            return ('change', self.left, self.right)
        return None


@dataclass(frozen=True)
class MovedJump:
    first: Jump
    second: Jump
    crossing: float

    @property
    def low(self):
        return min(self.first.time, self.second.time) - self.crossing

    @property
    def high(self):
        return max(self.first.time, self.second.time) + self.crossing


def _jumps(history, scale):
    previous = None
    for time, pieces in groupby(history.pieces, key=lambda piece: piece.t):
        landed = list(pieces)[-1]
        if previous is not None:
            jump = Jump(float(time), previous.at(time), landed.at(time))
            if jump.transition(scale) is not None:
                yield jump
        previous = landed


def moved_jumps(first_history, second_history, *, crossing, scale, event_times=None):
    """Match isolated transitions with the same direction or the same categorical change.

    The two times must lie within the crossing tolerance or be the times of the same
    trace decision. Both runs must have exactly one jump in the closed window.
    The caller checks the values of both histories at both outer edges of the window.
    """
    events = event_times or {}
    a = list(_jumps(first_history, scale))
    b = list(_jumps(second_history, scale))
    ta, tb = [j.time for j in a], [j.time for j in b]
    pairs = []
    for first in a:
        t = first.time
        # An unchanged discontinuity needs no special handling.
        at = bisect_left(tb, t)
        if at < len(b) and tb[at] == t:
            continue
        candidates = set(range(bisect_left(tb, t - crossing), bisect_right(tb, t + crossing)))
        linked = events.get(t)
        if linked is not None:
            j = bisect_left(tb, linked)
            if j < len(b) and tb[j] == linked:
                candidates.add(j)
        candidates = [j for j in candidates if first.transition(scale) == b[j].transition(scale)]
        if len(candidates) != 1:
            continue
        second = b[candidates[0]]
        match = MovedJump(first, second, crossing)
        # No intervening discontinuity can be hidden by alignment. A second
        # matching jump in the other direction makes the pairing ambiguous.
        if any(bisect_right(times, match.high) - bisect_left(times, match.low) != 1 for times in (ta, tb)):
            continue
        near = a[bisect_left(ta, second.time - crossing) : bisect_right(ta, second.time + crossing)]
        if any(j.time != t and j.transition(scale) == first.transition(scale) for j in near):
            continue
        pairs.append(match)
    return tuple(pairs)


def public_jump(window, read_first, read_second, scale):
    """Use a stored jump window for public reads only if both public readers jump there."""

    def read(stored, reader):
        t = stored.time
        return Jump(t, reader(nextafter(t, -inf)), reader(t))

    first = read(window.first, read_first)
    second = read(window.second, read_second)
    shape = first.transition(scale)
    if shape is not None and shape == second.transition(scale) == window.first.transition(scale):
        return MovedJump(first, second, window.crossing)
    return None


def short_piece_windows(first_history, second_history, *, crossing, through):
    """Open interiors of short continuous numeric pieces, with no jump in either history.

    Compare the shared edge values before using a window. A lasting change, an
    authored posting, or a categorical transition cannot be excused by this rule.
    """
    candidates, jumps = set(), set()
    for history in (first_history, second_history):
        previous = None
        for t, group in groupby(history.pieces, key=lambda piece: piece.t):
            landed = list(group)[-1]
            if previous is not None:
                if not _number(landed.value) or not _number(previous.value) or previous.at(t) != landed.at(t):
                    jumps.add(t)
                if 0 < t - previous.t < crossing and _number(previous.value):
                    candidates.add((float(previous.t), float(t)))
            previous = landed
        if previous is not None and _number(previous.value) and 0 < through - previous.t < crossing:
            candidates.add((float(previous.t), float(through)))
    transitions = sorted(jumps)
    return tuple(
        (lo, hi)
        for lo, hi in sorted(candidates)
        if bisect_right(transitions, hi) == bisect_left(transitions, lo)
    )


def projection_point(history, time):
    """True only for the physical balance added by the stock projection at an inclusive cutoff."""
    from napkin.program.record import BalancePoint

    return bool(
        history.pieces and history.pieces[-1].t == time and isinstance(history.pieces[-1], BalancePoint)
    )
