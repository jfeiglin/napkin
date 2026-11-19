"""The ways of a run: the instances that run its connected sets between moments, and what a moment
does to them.

A connected set runs on one of five ways (`plan.Connected.way`): the family of one-flow sets on
arrays (`family.py`), lines (`lines.py`), one component of the continuous engine (`component.py`),
the sparse integrator (`sparse.py`), or the way of a declared solver (`declared.py`). `Ways` holds
the instances of a run, each of one or more sets, and gives every engine of the run the same few
operations:

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
- **a component**, **a sparse set** and **a declared solver's set** are one set each: the instance
  goes, and a new one starts. A declared solver keeps its `solve.Solver` for the whole run (`kept`),
  with its last problem and answer (`last`), and the references of its stored numbers.

**Levels.** A set whose requests or capacities, or whose solver's problem, read the actual rates or
the results of another set settles after it: its level is one more than the levels of the sets that
it reads. Instances are made level by level, so a setting reads rates that are settled, and each
affected solver is solved once, in dependency order. A rate or a result that another set reads
changes at a moment or at an event of its instance; the sets that read it are touched then. A set
whose settings read a rate that moves between moments (of a component or of a sparse set, or of a
set that follows one) integrates with that set (D3): the sets run in one instance of the sparse
integrator, level by level, each reading the rates that the levels before it give at the same time
and state, and a moment that builds one of them again builds them all. A set of a declared solver
whose problem moves runs alone: a set that would follow it, or that it would follow, stops the run
by name.

**A result read before it settles** (D5): while the stages of a round run, a rate or a result of a
declared solver's set whose inputs changed in the round (a write of a commit or of the stage, a store
that met a bound, a flow that joined or left one of its stores) fails, naming the result and what
changed (`fresh`), and so does one that has never been solved.
"""

from __future__ import annotations

import math

from ..errors import SimulationError
from .component import ComponentWay
from .declared import DeclaredWay, MovingDeclared
from .family import Family
from .lines import Lines
from .plan import COMPONENT, DECLARED, FAMILY, LINES, ROUTE, SPARSE
from .sparse import Sparse


def _moves(connected):
    """Whether the rates of a connected set move between moments."""
    return connected.way in (COMPONENT, SPARSE) or (connected.way == DECLARED and connected.moves)


class Ways:
    """The instances of the ways of one run (see the module)."""

    def __init__(self, run):
        self.run, self.plan = run, run.plan
        self.sets = {}  # set id -> (Connected, its instance)
        self.set_of = {}  # store or flow -> the id of its set
        self.levels = {}  # set id -> its level
        self.readers = {}  # engine name -> the ids of the sets whose settings read it
        self.result_of = {}  # a result of a declared solver that is no rate -> the id of its set
        self.kept, self.last = {}, {}  # solver id -> its `solve.Solver`; -> (last problem, answer)
        self.references = {}  # a stored number that a solver determines -> its reference
        self.instances = []
        self.grouped = set()  # the ids of the sets that integrate with others in one instance
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

    def result(self, name, t):
        """A result of a declared solver that is no rate: a stored number that it determines or an
        unknown of its own."""
        return self.sets[self.result_of[name]][1].level_at(name, t)

    def fresh(self, name, tx):
        """A rate or a result read while the stages of a round run: it fails when it belongs to a
        declared solver's set whose inputs changed in the round, or that has never been solved
        (D5: a stale answer is a wrong one)."""
        plan, run = self.plan, self.run
        key = self.result_of.get(name)
        if key is None:
            key = self.set_of.get(name.rsplit('.', 1)[0])
        connected = self.sets[key][0] if key is not None else None
        if connected is None or connected.way != DECLARED:
            sid = plan.results.get(name) or plan.solved_flows.get(name.rsplit('.', 1)[0])
            if sid is not None or (connected is None and name in run.waiting_names):
                raise SimulationError(
                    f'{name} is read before its first solve: it settles after the stages of the round commit'
                )
            return
        changed = run.changed_names() | set(run.written)
        if tx is not None:
            changed |= set(tx.writes)
        found = sorted(changed & (connected.reads | set(connected.stores)))
        moved = [
            flow
            for flow in (*run.joined, *run.left)
            for connection in plan.flows[flow].connections
            if connection.source in connected.stores or connection.sink in connected.stores
        ]
        if found or moved:
            raise SimulationError(
                f'{name} is read before its solve settles: {", ".join(found + moved[:1])} changed in this '
                f'round (the solver {connected.solver}). Read it after the stage commits and the solve '
                'settles.'
            )

    def linear(self, store):
        """(value, rate, since) of a store whose line holds until its instance's next event, or
        None for a store that moves on a curve."""
        return self.instance_of(store).linear(store)

    def monotone(self, store):
        """Whether a store of a set only supplies or only receives the connections of its set, so
        that it only falls or only rises between moments."""
        connected = self.sets[self.set_of[store]][0]
        sides = set()
        for flow in connected.flows:
            found = self.plan.flows[flow]
            if found.kind == ROUTE and store in (found.source, found.sink):
                return False  # a signed rate moves it either way
            for connection in found.connections:
                if connection.source == store:
                    sides.add('out')
                if connection.sink == store:
                    sides.add('in')
        return len(sides) <= 1

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

    def finish(self, t):
        """At the horizon: each instance stands there, and the lines settle what left a bound."""
        self.cut(t)
        for instance in self.instances:
            if isinstance(instance, Lines):
                instance.finish(t)

    def touched_by(self, names):
        """The ids of the sets that hold or read any of `names`."""
        found = set()
        for name in names:
            if name in self.set_of:
                found.add(self.set_of[name])
            found |= self.readers.get(name, set())
        return found

    def moving_sources(self, sets):
        """The ids of the sets now whose rates move between moments and that the settings of the
        connected sets `sets` read: they integrate with them (`build`)."""
        found = set()
        for connected in sets:
            for name in connected.rates:
                key = self.result_of.get(name)
                if key is None:
                    key = self.set_of.get(name.rsplit('.', 1)[0])
                if key is not None and self.moving(key):
                    found.add(key)
        return found

    def moving(self, key):
        """Whether the rates of a set now move between moments: by its way, or because it integrates
        with a set whose rates move."""
        return _moves(self.sets[key][0]) or key in self.grouped

    def touched_outside(self, names, instance):
        """The ids of the sets that hold or read any of `names`, outside an instance: the sets that
        integrate in one instance read one another's rates there, at each state, with no moment."""
        return {key for key in self.touched_by(names) if self.sets[key][1] is not instance}

    def readers_of_rates(self, ids):
        """The ids of the sets that read an actual rate, a served fraction or a result of the sets
        `ids`."""
        found = set()
        for key in ids:
            connected = self.sets[key][0]
            for name in self._given(connected):
                found |= self.readers.get(name, set())
        return found - set(ids)

    def _given(self, connected):
        """What a set gives that other sets may read: the rates of its flows and of its endpoints,
        and the results of its solver."""
        found = [name for flow in connected.flows for name in self.plan.rates_of_flow(flow)]
        return found + list(connected.results)

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
            for name in connected.results:
                if self.result_of.get(name) == key:
                    del self.result_of[name]
            for name in connected.reads:
                found = self.readers.get(name)
                if found is not None:
                    found.discard(key)
            self.levels.pop(key, None)
            self.grouped.discard(key)
        self.instances = [instance for instance in self.instances if instance.alive]
        return values

    def build(self, sets, values, t):
        """New instances for connected sets at time t, from `values`, the value of each of their
        stores there: level by level, the family's sets and the lines' sets of one level in one
        instance each, every component and sparse set alone."""
        if not sets:
            return []
        rate_sets = {}  # the rates and results of the sets that stay, by the set that gives each
        if any(connected.rates for connected in sets):
            for key, (connected, _) in self.sets.items():
                for name in self._given(connected):
                    rate_sets[name] = key
        made = list(sets)
        new_rates = {}
        for index, connected in enumerate(made):
            for name in self._given(connected):
                new_rates[name] = index
        level = [None] * len(made)

        def level_of(index, path):
            if level[index] is not None:
                return level[index]
            if index in path:
                raise SimulationError(
                    f'{(made[index].flows or (made[index].solver,))[0]}: requests or capacities of '
                    "connected sets that read one another's actual rates or results: a relation between "
                    'the rates of two calculations needs one declared solver that owns them both, '
                    'which states it as a constraint'
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
        # A set whose settings read a rate of another set that moves between moments integrates
        # with it, on the sparse integrator, level by level (`Sparse`): they are one instance.
        together = list(range(len(made)))

        def root(index):
            while together[index] != index:
                together[index] = together[together[index]]
                index = together[index]
            return index

        moving = [False] * len(made)  # whether the rates of each new set move between moments
        for index in sorted(range(len(made)), key=lambda index: level[index]):
            connected = made[index]
            moving[index] = _moves(connected)
            for name in connected.rates:
                owner = new_rates.get(name)
                if owner is None:
                    if self.moving(rate_sets[name]):
                        raise SimulationError(
                            f'{name}: a rate that moves, read by a set built again without its own set'
                        )
                    continue
                if not moving[owner]:
                    continue
                moving[index] = True
                found = made[owner]
                if DECLARED in (found.way, connected.way):
                    raise SimulationError(
                        f'{(connected.flows or (connected.solver,))[0]}: a request, a capacity or a '
                        f'problem that reads {name}, a rate or a result of another connected set that '
                        "moves between moments, where one of the two is a declared solver's: the engine "
                        'integrates the set of a moving solver alone, so it does not run one that follows '
                        'it or that it follows'
                    )
                together[root(index)] = root(owner)
        joined = {}
        for index in range(len(made)):
            joined.setdefault(root(index), []).append(index)
        created = []
        for members in joined.values():
            if len(members) < 2:
                continue
            members.sort(key=lambda index: level[index])
            keys = [self._register(made[index], level[index]) for index in members]
            self.grouped.update(keys)
            low = level[members[0]]
            instance = Sparse(
                self.run,
                [made[index] for index in members],
                values,
                t,
                keys[0],
                [level[index] - low for index in members],
            )
            self._hold(instance, keys)
            created.append(instance)
        alone = {members[0] for members in joined.values() if len(members) == 1}
        for depth in sorted(set(level)):
            here = [index for index in range(len(made)) if level[index] == depth and index in alone]
            groups = {}
            for index in here:
                groups.setdefault(made[index].way, []).append(index)
            for way in (FAMILY, LINES, COMPONENT, SPARSE, DECLARED):
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
                    elif way == DECLARED:
                        kind = MovingDeclared if made[index].moves else DeclaredWay
                        instance = kind(self.run, made[index], values, t, key)
                    else:
                        instance = Sparse(self.run, [made[index]], values, t, key)
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
        for name in connected.results:
            self.result_of[name] = key
        for name in connected.reads:
            self.readers.setdefault(name, set()).add(key)
        return key

    def _hold(self, instance, keys):
        """An instance holds its sets, and starts."""
        for key in keys:
            self.sets[key] = (self.sets[key][0], instance)
        self.instances.append(instance)
        instance.begin()
