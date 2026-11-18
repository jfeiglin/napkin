"""The reductions over the instances of a family, and how one member is brought up to date.

Moved from `run.py` with no change (step B0-6). `Lists` is a part of `run.Run`: its methods
read the run as `self`.
"""

from __future__ import annotations

import numpy as np

from .state import Env, _spread
from .trees import Pairwise


class Lists:
    """See the module."""

    # ---- the lists ------------------------------------------------------------------------------

    def aggregate(self, name, t, trial):
        found = self.plan.aggregates[name]
        trial = trial if trial is not None and trial.whole else None
        parts = []
        for place, term in enumerate(found.terms):
            kept = None if found.moving else self.terms.get((name, place))
            if kept is None:
                env = Env(self, term.space, None, t, trial)
                kept = self.reduced(found.function, _spread(self.value(term.node, env), env.count))
                if not found.moving:
                    self.terms[(name, place)] = kept
            parts.append(kept)
        return self.combined(found.function, parts)

    @staticmethod
    def combined(function, parts):
        """The value of a list from what it keeps of each member (`reduced`)."""
        if function == 'sum':
            total = 0.0
            for kept in parts:
                total = total + kept.total
            return total
        if function == 'any':
            return any(count > 0 for count, _ in parts)
        if function == 'all':
            return all(count == size for count, size in ((np.count_nonzero(k[1]), len(k[1])) for k in parts))
        extreme = min if function == 'min' else max
        return extreme(float(extreme(kept)) for kept in parts)

    @staticmethod
    def reduced(function, values):
        """What a list keeps of the values of one member: a tree for a sum, the values for the others."""
        if function == 'sum':
            return Pairwise(values)
        if function in ('any', 'all'):
            values = values.astype(bool)
            return [np.count_nonzero(values), values]
        return np.array(values, dtype=float)

    def update_term(self, name, place, J, t):
        """Bring the member `place` of a list up to date for the instances J (None: all)."""
        found = self.plan.aggregates[name]
        term = found.terms[place]
        kept = self.terms.get((name, place))
        count = self.plan.spaces[term.space].count
        if kept is None or J is None or count == 1:
            self.terms.pop((name, place), None)
            self.aggregate(name, t, None)
            return
        J = np.fromiter(J, dtype=int, count=len(J))
        env = Env(self, term.space, J, t)
        values = _spread(self.value(term.node, env), len(J))
        if found.function == 'sum':
            kept.set_many(J, values)
        elif found.function in ('any', 'all'):
            kept[1][J] = values.astype(bool)
            kept[0] = np.count_nonzero(kept[1])
        else:
            kept[J] = values
