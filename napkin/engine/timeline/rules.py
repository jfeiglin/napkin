"""The memory of each rule, the reading of a rule, and the time at which it is read again.

Moved from `run.py` with no change (step B0-6). `Rules` is a part of `run.Run`: its methods
read the run as `self`.
"""

from __future__ import annotations

import heapq

import numpy as np

from .state import FIRE, ONE, ROOT, RULE, TRIGGER, Env, _spread


class RuleState:
    def __init__(self, count):
        self.armed = np.ones(count, dtype=bool)
        self.triggered = np.zeros(count, dtype=np.int64)
        self.pending = np.full(count, np.nan)
        self.version = np.zeros(count, dtype=np.int64)
        self.ready = np.zeros(count, dtype=np.int8)
        self.reached = np.zeros(count, dtype=np.int64)  # the moment at which its crossing came
        self.window = np.empty(count, dtype=object)  # the values of its window when it triggered


class Rules:
    """See the module."""

    def ends(self, block, j, t):
        """A segment of a component ended: the rates of the component can change there (a quantity
        of it reached or left a bound, or a rate changed its branch), and with them the answer of a
        rule that reads it. So the rules and the checks that read a quantity of the component are
        read there.

        A condition on the quantities of the component has one answer inside the segment that ended:
        a stock is at zero through a whole segment or at no time inside it, and a crossing that was
        reached inside it ended it. Where that answer is no, the rule can trigger again, as a rule
        whose condition is false can."""
        plan = self.plan
        middle = self.single[block][j].middle()
        rules, _, _, _, checks = self.closure([(name, {j}) for name in plan.blocks[block].names])
        for index, J in rules.items():
            rule = plan.rules[index]
            if middle is None or rule.each or rule.kind not in ('face', 'crossing'):
                continue
            count = plan.spaces[rule.space].count
            places = np.arange(count) if J is None else np.fromiter(sorted(J), dtype=int, count=len(J))
            inside = self.holds(rule, Env(self, rule.space, places, middle), places, middle, False)
            self.rules[index].armed[places[~inside]] = True
        for (kind, index), J in checks.items():
            places = None if J is None else np.fromiter(sorted(J), dtype=int, count=len(J))
            (self.check if kind == 'check' else self.partition)(index, places, t)
        for index, J in rules.items():
            self.mark(index, J)

    def crossing_due(self, at, index, j):
        """The crossing that a rule watches in a component reaches its value at a time."""
        self.later(at, index, j, ROOT)

    def mark(self, index, J):
        """The rule is read again for the instances J (None: all)."""
        if J is None:
            self.dirty[index] = None
        elif self.dirty.get(index, ()) is not None:
            self.dirty.setdefault(index, set()).update(J)

    # ---- the reading of a rule --------------------------------------------------------------------

    def holds(self, rule, env, J, t, reached):
        """Whether the condition of a rule holds for the instances J. `reached`: the time at which
        the crossing of the instance reaches its value is within the tolerance of a time of this
        moment. Then the crossing holds, as a clock within that tolerance does (D-65). With the reading
        of every rule, a crossing holds inside the tolerance band of its quantity, at any moment."""
        count = len(J)
        if rule.kind in ('discrete', 'face'):
            return _spread(self.value(rule.when, env), count).astype(bool) & ~self.spent(rule, env, J)
        found = _spread(self.value(rule.gate, env), count).astype(bool) & ~self.spent(rule, env, J)
        for node in rule.times:
            found = found & (_spread(self.value(node, env), count) <= t + self.tolerance)
        if rule.kind == 'crossing':
            value = _spread(env[rule.var], count)
            threshold = _spread(self.value(rule.value, env), count)
            if self.reading == 'every':
                band = self.atol[rule.var][J] if len(self.atol[rule.var]) > 1 else self.atol[rule.var][0]
                found = found & ((value >= threshold - band) if rule.rising else (value <= threshold + band))
            else:
                found = found & (reached | ((value >= threshold) if rule.rising else (value <= threshold)))
        return found

    def window(self, rule, env, count):
        """The values of the window (`each`) of a rule, for each instance: a list of tuples."""
        columns = [_spread(self.value(node, env), count).tolist() for node in rule.each]
        return list(zip(*columns))

    def spent(self, rule, env, J):
        """Whether each instance of a rule with a window has triggered in the window of this
        moment. A window lasts while the values of `each` stay the same: when they change, the memory
        of the trigger is spent, and a value seen before opens a new window."""
        found = np.zeros(len(J), dtype=bool)
        if not rule.each:
            return found
        kept = self.rules[rule.index].window
        now = None
        for at, j in enumerate(J.tolist()):
            if kept[j] is None:
                continue
            if now is None:
                now = self.window(rule, env, len(J))
            if kept[j] != now[at]:
                kept[j] = None
            else:
                found[at] = True
        return found

    def later(self, at, index, j, kind=RULE):
        """Put a time of a rule on the timeline: of a clock or of the end of a delay (RULE), or the
        time at which its crossing reaches its value (ROOT)."""
        self.entries += 1
        heapq.heappush(
            self.times, (float(at), self.entries, kind, index, int(j), int(self.rules[index].version[j]))
        )

    def read_rule(self, rule, J, t):
        """Read a rule for the instances J, as one moment reads it, and put on the
        timeline the time at which each instance is read again."""
        state, count = self.rules[rule.index], len(J)
        self.counts['readings'] += count
        state.version[J] += 1
        env = Env(self, rule.space, J, t)
        holds = self.holds(rule, env, J, t, state.reached[J] == self.moment)
        ends = state.pending[J]
        pending = ~np.isnan(ends)
        due = np.zeros(count, dtype=np.int8)
        cancelled = np.zeros(count, dtype=bool)
        if rule.keep is not None and pending.any():
            # The reason to wait has gone: the firing is cancelled, and the rule triggers again once
            # its condition becomes true again.
            cancelled = pending & ~_spread(self.value(rule.keep, env), count).astype(bool)
            if cancelled.any():
                state.pending[J[cancelled]] = np.nan
                state.armed[J[cancelled]] = ~holds[cancelled]
                pending = pending & ~cancelled
        if pending.any():
            fire = pending & (ends <= t + self.tolerance)
            due[fire] = FIRE
            for j, at in zip(J[pending & ~fire].tolist(), ends[pending & ~fire].tolist()):
                self.later(at, rule.index, j)
            state.armed[J[pending & holds]] = False
        free = ~pending & ~cancelled
        can = ~(rule.once & (state.triggered[J] > 0))
        due[free & holds & state.armed[J] & can] = TRIGGER
        quiet = free & ~holds
        if quiet.any():
            state.armed[J[quiet]] = True
        quiet = quiet | (cancelled & ~holds)
        if quiet.any() and not rule.named:
            # An instance whose window is spent waits for a step that changes the window, not for a time.
            self.watch(rule, J[quiet & can & ~self.spent(rule, env, J)], t)
        was = state.ready[J]
        state.ready[J] = due
        new = (due != 0) & (was == 0)
        if new.any():
            positions, copies = self.order[rule.index]
            for j in J[new].tolist():
                heapq.heappush(
                    self.ready, ((rule.line, int(positions[j]), int(copies[j]), rule.index), rule.index, j)
                )

    def watch(self, rule, J, t):
        """Instances of a rule whose condition does not hold: the time at which their clocks, or
        their crossing, can make it hold goes on the timeline."""
        if not len(J) or rule.kind == 'face':
            # A condition on stocks at zero is read where a segment of its block ends (`ends`).
            return
        env = Env(self, rule.space, J, t)
        count = len(J)
        open_ = _spread(self.value(rule.gate, env), count).astype(bool) if rule.kind != 'discrete' else None
        if open_ is None or not open_.any():
            return
        clock = np.full(count, -np.inf)
        for node in rule.times:
            clock = np.maximum(clock, _spread(self.value(node, env), count))
        waits = open_ & (clock > t + self.tolerance)
        for j, at in zip(J[waits].tolist(), clock[waits].tolist()):
            if at <= self.horizon + self.tolerance:
                self.later(at, rule.index, j)
        if rule.kind != 'crossing':
            return
        seek = open_ & ~waits
        if not seek.any():
            return
        threshold = _spread(self.value(rule.value, env), count)
        plan = self.plan
        places = self.index(rule.space, plan.space_of(rule.var), J)
        if plan.kind[rule.var] == 'line':
            y0, t0, rate = self.y0[rule.var], self.t0[rule.var], self.rate[rule.var]
            at = slice(None) if places is ONE or places is None else places
            toward = (rate[at] > 0) if rule.rising else (rate[at] < 0)
            with np.errstate(divide='ignore', invalid='ignore'):
                reach = t0[at] + (threshold - y0[at]) / rate[at]
            for k in np.flatnonzero(seek & toward & (reach <= self.horizon + self.tolerance)).tolist():
                self.later(max(float(reach[k]), t), rule.index, int(J[k]), ROOT)
            return
        block = plan.blocks[plan.quantities[rule.var].block]
        for k in np.flatnonzero(seek).tolist():
            place = 0 if places is ONE else int(places[k]) if places is not None else k
            if block.whole:
                solution = self.whole[block.index]
                at = solution.slices[rule.var].start + place
            else:
                solution = self.single[block.index][place]
                at = solution.slices[rule.var].start
            if block.net:
                # A component watches the crossing in each of its segments, as it makes them.
                solution.watch(rule.index, int(J[k]), at, float(threshold[k]), rule.rising, t)
                continue
            mark = float(threshold[k])
            if rule.index in self.monotone_crossings:
                # A value that only rises or only falls can come near its mark and never pass
                # it. Its crossing is watched half a tolerance before the mark, inside the band in
                # which the rule holds, as the general tier watches it (`integrate.root_value`).
                band = self.atol[rule.var]
                half = 0.5 * float(band[place] if len(band) > 1 else band[0])
                mark = mark - half if rule.rising else mark + half
            root = solution.first_root(at, mark, rule.rising, t)
            if root is not None:
                self.later(root, rule.index, int(J[k]), ROOT)

    # ---- a played run ---------------------------------------------------------------------------

    def can_trigger(self, index, place):
        """A rule triggers unless it is `once` and has triggered, or it waits to fire."""
        state = self.rules[index]
        return not (self.plan.rules[index].once and state.triggered[place]) and bool(
            np.isnan(state.pending[place])
        )
