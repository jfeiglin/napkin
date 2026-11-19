"""The ways of a run: the instances that run its connected sets between moments, and what a moment
does to them.

A connected set runs on one of four ways (`plan.Connected.way`): the family of one-flow sets on
arrays (`family.py`), lines (`lines.py`), one component of the continuous engine (`component.py`)
or the sparse integrator (`sparse.py`). `Ways` holds the instances of a run, each of one or more
sets, and gives every engine of the run the same few operations:

- the value of a store and the rate of a flow at a time inside the present window of its instance;
- `peek()`, the time of the next event inside an instance (a store that reaches or leaves a bound,
  the end of a segment or of a step of the solver), and `step()`, which commits it;
- `cut(t)`: an instance whose next segment or step was made past a moment commits it up to there;
- `build(sets, values, t)` and `retire(ids)`.

**Moments change sets by rebuilding them.** An occurrence's flows join and leave the network at
moments, a stage writes a store or a value that a rate reads, and a rate that another set reads
changes. The sets that such a change touches are retired from their instances at the moment, the
connected sets of what they held (with the flows that joined, without those that left) are found
again (`plan.connect`), and new instances start from the state there; every other set goes on in its
instance. So a connected set gains and loses members at moments, and each way takes it as it is:

- **the family** and **lines** hold many sets in one instance: a retired set's rows are dead in
  it (no event, no refresh), and the touched sets of one moment form one new instance of each of
  those ways for each level (below);
- **a component** and **a sparse set** are one set each: the instance goes, and a new one starts.

**Levels.** A set whose requests or capacities read the actual rates of another set settles after
it: its level is one more than the levels of the sets that it reads. Instances are made level by
level, so a setting reads rates that are settled. A rate that another set reads changes at a
moment or at an event of its instance; the sets that read it are touched then. A set whose settings
read a rate that moves between moments (of a component or of a sparse set) has no closed answer
here and is refused (`Outside`).
"""

from __future__ import annotations

import math

from .component import ComponentWay
from .family import Family
from .lines import Lines
from .plan import COMPONENT, FAMILY, LINES, SPARSE, Outside
from .sparse import Sparse


class Ways:
    """The instances of the ways of one run (see the module)."""

    def __init__(self, run):
        self.run, self.plan = run, run.plan
        self.sets = {}  # set id -> (Connected, its instance)
        self.set_of = {}  # store or flow -> the id of its set
        self.levels = {}  # set id -> its level
        self.readers = {}  # engine name -> the ids of the sets whose settings read it
        self.instances = []
        self._next = 0

    # ---- what the ways hold now ----------------------------------------------------------------

    def instance_of(self, name):
        """The instance that holds a store or a flow, or None."""
        found = self.set_of.get(name)
        return None if found is None else self.sets[found][1]

    def value(self, store, t):
        """The value of a store of a set at a time inside its present window."""
        return self.instance_of(store).level_at(store, t)

    def rate(self, name, t):
        """An actual rate or a served fraction (`flow.actual_rate`, `flow.served_fraction`) at a
        time; a flow that is in no set now (it has left, or not joined) moves nothing."""
        flow = name.rsplit('.', 1)[0]
        instance = self.instance_of(flow)
        return 0.0 if instance is None else instance.rate_at(name, t)

    def linear(self, store):
        """(value, rate, since) of a store whose line holds until its instance's next event, or
        None for a store that moves on a curve."""
        return self.instance_of(store).linear(store)

    def peek(self):
        """(the time of the next event of an instance, the instance), or (inf, None)."""
        found = (math.inf, None)
        for instance in self.instances:
            at = instance.peek()
            if at < found[0]:
                found = (at, instance)
        return found

    def cut(self, t):
        """Every instance stands at time t."""
        for instance in self.instances:
            instance.cut(t)

    def touched_by(self, names):
        """The ids of the sets that hold or read any of `names`."""
        found = set()
        for name in names:
            if name in self.set_of:
                found.add(self.set_of[name])
            found |= self.readers.get(name, set())
        return found

    def readers_of_rates(self, ids):
        """The ids of the sets that read an actual rate or a served fraction of the sets `ids`."""
        found = set()
        for key in ids:
            connected = self.sets[key][0]
            for flow in connected.flows:
                for name in self.plan.rates_of_flow(flow):
                    found |= self.readers.get(name, set())
        return found - set(ids)

    # ---- rebuilding sets -------------------------------------------------------------------------

    def retire(self, ids, t):
        """The sets `ids` leave their instances at time t; gives the values of their stores there."""
        values = {}
        for key in ids:
            connected, instance = self.sets.pop(key)
            for store in connected.stores:
                values[store] = instance.level_at(store, t)
            instance.retire(key)
            for name in (*connected.stores, *connected.flows):
                if self.set_of.get(name) == key:
                    del self.set_of[name]
            for name in connected.reads:
                found = self.readers.get(name)
                if found is not None:
                    found.discard(key)
            self.levels.pop(key, None)
        self.instances = [instance for instance in self.instances if instance.alive]
        return values

    def build(self, sets, values, t):
        """New instances for connected sets at time t, from `values`, the value of each of their
        stores there: level by level, the family's sets and the lines' sets of one level in one
        instance each, every component and sparse set alone."""
        if not sets:
            return []
        rate_sets = {}
        for key, (connected, _) in self.sets.items():
            for flow in connected.flows:
                for name in self.plan.rates_of_flow(flow):
                    rate_sets[name] = key
        made = list(sets)
        new_rates = {}
        for index, connected in enumerate(made):
            for flow in connected.flows:
                for name in self.plan.rates_of_flow(flow):
                    new_rates[name] = index
        level = [None] * len(made)

        def level_of(index, path):
            if level[index] is not None:
                return level[index]
            if index in path:
                raise Outside(
                    f'{made[index].flows[0]}: requests or capacities of connected sets that read one '
                    "another's actual rates, which local sharing settles at once (S5: a solver)"
                )
            found = 0
            for name in made[index].rates:
                if name in new_rates:
                    found = max(found, level_of(new_rates[name], path | {index}) + 1)
                elif name in rate_sets:
                    found = max(found, self.levels[rate_sets[name]] + 1)
            level[index] = found
            return found

        for index in range(len(made)):
            level_of(index, frozenset())
        for connected in made:
            for name in connected.rates:
                owner = new_rates.get(name)
                way = made[owner].way if owner is not None else self.sets[rate_sets[name]][0].way
                if way in (COMPONENT, SPARSE):
                    raise Outside(
                        f'{connected.flows[0]}: a request or a capacity that reads the rate of a flow '
                        'that moves between moments (S5: a solver)'
                    )
        created = []
        for depth in sorted(set(level)):
            here = [index for index in range(len(made)) if level[index] == depth]
            groups = {}
            for index in here:
                groups.setdefault(made[index].way, []).append(index)
            for way in (FAMILY, LINES, COMPONENT, SPARSE):
                members = groups.get(way, [])
                if not members:
                    continue
                if way in (FAMILY, LINES):
                    keys = [self._register(made[index], depth) for index in members]
                    kind = Family if way == FAMILY else Lines
                    instance = kind(self.run, [made[index] for index in members], values, t, keys)
                    self._hold(instance, keys)
                    created.append(instance)
                    continue
                for index in members:
                    key = self._register(made[index], depth)
                    if way == COMPONENT:
                        instance = ComponentWay(self.run, made[index], values, t, key)
                    else:
                        instance = Sparse(self.run, made[index], values, t, key)
                    self._hold(instance, [key])
                    created.append(instance)
        return created

    def _register(self, connected, depth):
        """A new set: its id, its level and what it reads."""
        key = self._next
        self._next += 1
        self.sets[key] = (connected, None)
        self.levels[key] = depth
        for name in (*connected.stores, *connected.flows):
            self.set_of[name] = key
        for name in connected.reads:
            self.readers.setdefault(name, set()).add(key)
        return key

    def _hold(self, instance, keys):
        """An instance holds its sets, and starts."""
        for key in keys:
            self.sets[key] = (self.sets[key][0], instance)
        self.instances.append(instance)
        instance.begin()
