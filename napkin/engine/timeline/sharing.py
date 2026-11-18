"""What a flow of the fast tier delivers: a group with a limit, flows that move by one
fraction, and a source that rests on its bound.

Moved from `run.py` with no change (step B0-6). `Sharing` is a part of `run.Run`: its methods
read the run as `self`.
"""

from __future__ import annotations

import numpy as np

from ..errors import SimulationError
from .plan import Outside
from .state import NEGATIVE, POSITIVE, Env, _spread


class Sharing:
    """See the module."""

    # ---- the rates ------------------------------------------------------------------------------

    def rate_of(self, name, env, trial=False):
        """The rate of a quantity. At a state of the run, a flow of it with a rate below zero is
        outside the fast tier. At a state that a solver tries (`trial`) it is no error: a trial can
        be past a bound, where the rate of a flow has no meaning. The environment keeps the name
        (`NEGATIVE`), for the case that the solver accepts that state (`Solution.advance`)."""
        total = 0.0
        plan = self.plan
        for (sign, node, is_flow), key in zip(plan.parts[name], plan.part_flows[name]):
            part = self.delivered(key, env) if key is not None else self.value(node, env)
            if is_flow and np.any(np.asarray(part) < 0):
                if not trial:
                    raise self.negative_flow(name)
                env.memo.setdefault(NEGATIVE, name)
            if key is not None and key not in self.flowing and np.any(np.asarray(part) > 0):
                # The flow delivers material at this state: at a state of the run it has moved; at
                # a state that a solver tries, it has when the solver accepts the state.
                if trial:
                    env.memo.setdefault(POSITIVE, set()).add(key)
                else:
                    self.flowing.add(key)
            total = total + sign * part
        return _spread(total, env.count).astype(float)

    def see_flows(self, names, env):
        """Mark the flows of some quantities that deliver material at the state of an environment
        (a state of the run): for a segment whose rates the engine does not read at its start."""
        plan = self.plan
        for name in names:
            for key in plan.part_flows[name]:
                if key is None or key in self.flowing:
                    continue
                if np.any(np.asarray(self.delivered(key, env)) > 0):
                    self.flowing.add(key)

    def flows_at_end(self):
        """Mark the flows that deliver material at the end of the run. With the states at which the
        engine reads the rates (the start of each segment, each state that a solver accepts), this
        is where the fast tier looks: a flow that is at zero at all of them counts as not moved."""
        plan = self.plan
        for name in plan.quantities:
            keys = [key for key in plan.part_flows[name] if key is not None and key not in self.flowing]
            if keys:
                self.see_flows([name], Env(self, plan.space_of(name), None, self.horizon))

    def negative_flow(self, name):
        """A flow cannot ask a rate below zero: the general tier gives the error of the run."""
        return Outside(f'a flow of {name} with a rate below zero', space=self.plan.space_of(name))

    def delivered(self, key, env):
        """The rate that a flow delivers for the instances of `env`: what it asks, or its share of
        the limit of its group when the flows of the group ask more than the limit together."""
        plan = self.plan
        members = plan.coupled.get(key)
        if members is not None:
            # Flows that move by one fraction: each gets its request times the smallest share that
            # any of them can have of its own request.
            found = env.memo.get(('coupled', members))
            if found is None:
                found = env.memo[('coupled', members)] = self.fraction(members, env)
            return _spread(self.value(plan.flows[key], env), env.count).astype(float) * found
        return self.alone(key, env)

    def alone(self, key, env):
        """What a flow delivers by itself: with the limit of its group and the bound of its source,
        and without the flows that move by one fraction with it."""
        plan = self.plan
        group = plan.groups.get(plan.flow_group.get(key))
        floor = plan.floors.get(plan.flow_source.get(key))
        if group is not None and (group.capacity is not None or floor is not None):
            found = env.memo.get(('group', group.name))
            if found is None:
                found = env.memo[('group', group.name)] = self.rationed(group, env)
            return found[key]
        asked = self.value(plan.flows[key], env)
        if floor is None:
            return asked
        # The one flow out of a quantity that rests on its bound gets no more than what comes in.
        rests = _spread(env[floor.flag], env.count).astype(bool)
        if not rests.any():
            return asked
        asked = _spread(asked, env.count).astype(float)
        return np.where(rests, np.minimum(asked, self.supply(floor, env)), asked)

    def fraction(self, members, env, but=None):
        """The fraction of their requests that flows that move by one fraction get: the smallest of
        what each can have of its own request (`but`: without that one). A flow that asks nothing
        while another asks something stops the run."""
        plan, count = self.plan, env.count
        asked = {key: _spread(self.value(plan.flows[key], env), count).astype(float) for key in members}
        some = np.zeros(count, dtype=bool)
        none = np.zeros(count, dtype=bool)
        for values in asked.values():
            some |= values > 0
            none |= values <= 0
        if (some & none).any():
            raise SimulationError('A coupled transaction must request every material flow together')
        found = np.ones(count)
        for key in members:
            if key == but:
                continue
            can = _spread(self.alone(key, env), count).astype(float)
            with np.errstate(divide='ignore', invalid='ignore'):
                found = np.minimum(found, np.where(asked[key] > 0, can / asked[key], 1.0))
        return found

    def supply(self, floor, env):
        """What comes into a quantity that can rest on its bound, for the instances of `env`: what
        the flows into it deliver, and the parts of its rate that are no flow."""
        found = env.memo.get(('supply', floor.name))
        if found is None:
            total = np.zeros(env.count)
            for node in floor.base:
                total = total + _spread(self.value(node, env), env.count)
            if np.any(total < 0):
                raise Outside(
                    f'{floor.name}, which can rest on its bound, with a rate below zero',
                    space=self.plan.space_of(floor.name),
                )
            for key in floor.inflows:
                total = total + _spread(self.delivered(key, env), env.count)
            found = env.memo[('supply', floor.name)] = total
        return found

    def rationed(self, group, env, resting=True):
        """{flow: the rate that it delivers} of the flows of a group with a limit. While they ask no
        more than the limit together, each delivers what it asks. Else a proportional group gives each
        the same fraction of what it asks, the limit over the sum of what they ask; and a priority
        group serves the flows of its order one after the other, each in full while the limit lasts.
        The arithmetic is that of the continuous engine (`Field._ration`), for each instance."""
        plan, count = self.plan, env.count
        asked = {key: _spread(self.value(plan.flows[key], env), count).astype(float) for key in group.flows}
        if group.capacity is None:
            capacity = np.full(count, np.inf)
        else:
            capacity = _spread(self.value(group.capacity, env), count).astype(float)
        if np.any(capacity < 0):
            raise SimulationError(f'Negative capacity for {group.name}')
        floor = plan.floor_of_group.get(group.name)
        if resting and floor is not None:
            # While the quantity that the flows drain rests on its bound, they share what comes in.
            rests = _spread(env[floor.flag], count).astype(bool)
            if rests.any():
                capacity = np.where(rests, np.minimum(capacity, self.supply(floor, env)), capacity)
        total = np.zeros(count)
        for key in group.flows:
            total = total + asked[key]
        over = total > capacity
        if not over.any():
            return asked
        if group.policy == 'proportional':
            with np.errstate(divide='ignore', invalid='ignore'):
                fraction = capacity / total
            return {key: np.where(over, asked[key] * fraction, asked[key]) for key in group.flows}
        found, remaining = dict(asked), capacity.copy()
        for key in group.order:
            cut = np.minimum(asked[key], remaining)
            remaining = remaining - cut
            found[key] = np.where(over, cut, asked[key])
        return found
