"""What a step wrote: the parts that read it, by any path, and how they are brought up to date.

Moved from `run.py` with no change (step B0-6). `Readers` is a part of `run.Run`: its methods
read the run as `self`.
"""

from __future__ import annotations

import numpy as np

from .plan import ALL, SAME


class Readers:
    """See the module."""

    # ---- what a step wrote ----------------------------------------------------------------------

    def targets(self, space, name, J, how):
        """The instances of `space` that read the instances J of `name`: a set, or None for all."""
        if J is None or how == ALL:
            return None
        if how == SAME:
            return set(J)
        back = self.plan.spaces[space].linked_from[self.plan.space_of(name)]
        found = set()
        for k in J:
            found.update(back.get(k, ()))
        return found

    @staticmethod
    def merge(found, key, target):
        """Add the instances `target` to those of `key`. Whether that added any."""
        if key not in found:
            found[key] = None if target is None else set(target)
            return True
        kept = found[key]
        if kept is None:
            return False
        if target is None:
            found[key] = None
            return True
        size = len(kept)
        kept |= target
        return len(kept) > size

    def closure(self, written):
        """The parts that read, by any path, the names that a step writes: {rule: instances}, {line:
        instances}, {block: instances}, {(list, member): instances}. Instances: a set, or None for all."""
        plan = self.plan
        rules, lines, blocks, terms, checks = {}, {}, {}, {}, {}
        lists = set()
        queue = list(written)
        while queue:
            name, J = queue.pop()
            for reader in plan.readers.get(name, ()):
                kind, how = reader[0], reader[-1]
                if kind == 'rule':
                    self.merge(rules, reader[1], self.targets(plan.rules[reader[1]].space, name, J, how))
                elif kind == 'line':
                    target = self.targets(plan.quantities[reader[1]].space, name, J, how)
                    if self.merge(lines, reader[1], target):
                        queue.append((reader[1], target))
                elif kind in ('check', 'partition'):
                    part = (plan.checks if kind == 'check' else plan.partitions)[reader[1]]
                    self.merge(checks, (kind, reader[1]), self.targets(part.space, name, J, how))
                elif kind == 'block':
                    block = plan.blocks[reader[1]]
                    target = None if block.whole else self.targets(block.space, name, J, how)
                    if self.merge(blocks, reader[1], target):
                        queue.extend((member, target) for member in block.names)
                else:
                    term = plan.aggregates[reader[1]].terms[reader[2]]
                    self.merge(terms, (reader[1], reader[2]), self.targets(term.space, name, J, how))
                    if reader[1] not in lists:
                        lists.add(reader[1])
                        queue.append((reader[1], None))
        return rules, lines, blocks, terms, checks

    def apply(self, writes, t, restart=(), changed=()):
        """Make the writes of one step, and bring up to date the parts that read them. A write is
        (name, place in the space of the name, value). `restart` names blocks of one instance, as
        (block, instance), that start again at t with the solver: a group of theirs reached its
        limit."""
        plan = self.plan
        written = [(name, {place}) for name, place, _ in writes]
        written.extend(changed)
        for name, place, _ in writes:
            # A step wrote the quantity of a crossing: the time at which the crossing was reached
            # says nothing of the new value, so the rule holds only by that value.
            for index in plan.crossings.get(name, ()):
                reached = self.rules[index].reached
                if plan.rules[index].space == plan.space_of(name):
                    reached[place] = 0
                else:
                    reached[:] = 0
        for index, j in restart:
            written.extend((member, {j}) for member in plan.blocks[index].names)
        forced = {}
        for name, place, value in writes:
            if plan.kind[name] == 'numeric':
                block = plan.blocks[plan.quantities[name].block]
                key = (block.index, None if block.whole else place)
                forced.setdefault(key, []).append((name, place if block.whole else 0, value))
                # The block starts again from the written state, so each quantity of it takes a new
                # path: what reads any of them is read again, not only what reads the written one.
                target = None if block.whole else {place}
                written.extend((member, target) for member in block.names if member != name)
        rules, lines, blocks, terms, checks = self.closure(written)
        for index, j in (*forced, *restart):
            self.merge(blocks, index, None if j is None else {j})
        # The state of each block that starts again, just before the step: a block is integrated only
        # when a reader asks, and the values that it read up to this moment are those before the
        # step.
        prior = {}
        for index, J in blocks.items():
            block = plan.blocks[index]
            if block.whole:
                found = [(None, self.whole[index])]
            else:
                made = self.single[index]
                found = [(j, made[j]) for j in (range(len(made)) if J is None else J)]
            for j, solution in found:
                prior[(index, j)] = np.array(solution.at(t), dtype=float)
        for name, place, value in writes:
            kind = plan.kind[name]
            if kind == 'value':
                if self.record:
                    self.undo.setdefault(name, []).append((t, place, self.v[name][place]))
                self.v[name][place] = value
                self.wrote += 1
            elif kind == 'line':
                self.restart_line(name, np.array([place]), t, value)
        for (name, place), J in sorted(terms.items(), key=lambda item: (int(item[0][0][6:]), item[0][1])):
            self.update_term(name, place, J, t)
        for name, J in lines.items():
            self.restart_line(name, None if J is None else np.fromiter(sorted(J), dtype=int, count=len(J)), t)
        self.restart_numeric = set(restart)
        for index, J in blocks.items():
            self.restart_block(plan.blocks[index], J, t, forced, prior)
        for index, j in restart:
            self.single[index][j].numeric_only = True
            self.single[index][j].mode = 'numeric'
        self.restart_numeric = set()
        # A quantity that came to rest on its bound, or left it, in these restarts: the parts that
        # read the flows out of it are brought up to date in their turn.
        while self.flag_changes:
            flags, self.flag_changes = self.flag_changes, []
            self.apply([], t, changed=flags)
        for (kind, index), J in checks.items():
            places = None if J is None else np.fromiter(sorted(J), dtype=int, count=len(J))
            (self.check if kind == 'check' else self.partition)(index, places, t)
        for index, J in rules.items():
            self.mark(index, J)
        if self.reading == 'every':
            for index in range(len(plan.rules)):
                self.mark(index, None)
