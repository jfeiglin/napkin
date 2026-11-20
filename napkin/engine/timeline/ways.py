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

**A rate read before it settles** (D5; PLAN, change 25): in a moment the stages commit first and
the flows are shared again after, so while the stages of a round run, every rate and result that
the settling decides (of local sharing as of a declared solver, a flow from SOURCE to SINK too) is
the one of the last settling. One that something it depends on changed since then fails, naming it,
what changed and the advice (`fresh`): a value that its settings or its problem read and that a
commit, the stage itself or an edit set, a store of its set that was set or met its bound at this
moment, the allocation of an endpoint of its set, a flow that joined or left one of its stores, and
so on through the sets whose rates or results its settings read (`stale`). So does one read in the
setup, before the flows first settle, and the rate of a flow that joined since they last settled. A
flow that left since reads zero, as a finished flow does. A store meets its bound at a moment where
an event of its instance brings it there at the moment's time (each way's `snap` names it); the
other names that the ways change there (`Run.moved`: every store and rate of a moving set whose
segment ends at the moment) are what the settling builds again, and no change of what a rate
depends on. What a check holds against is known statically (`Connected.reads`), so a write to a
value that a branch of a setting reads, which the present state does not take, counts too.
"""

from __future__ import annotations

import math
from collections import deque

from ..continuous.walk import walked
from ..errors import SimulationError
from .component import ComponentWay
from .declared import DeclaredWay, MovingDeclared
from .family import Family
from .lines import Lines
from .plan import COMPONENT, DECLARED, FAMILY, LINES, RATE, RESULT, ROUTE, SPARSE
from .sparse import Sparse

# The advice of a stale read (PLAN, change 25).
ADVICE = (
    'In a moment the stages commit first and the flows are shared again after: read it in a later '
    'stage or after a wait.'
)


def _listed(items):
    """What changed, for a message: the first three, and how many more."""
    shown = ', '.join(items[:3])
    return shown if len(items) <= 3 else f'{shown} and {len(items) - 3} more'


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
        time; a flow that is in no set now (it has not joined), or that left since the flows last
        settled, moves nothing."""
        flow = name.rsplit('.', 1)[0]
        instance = self.instance_of(flow)
        return 0.0 if instance is None or flow in self.run.left else instance.rate_at(name, t)

    def result(self, name, t):
        """A result of a declared solver that is no rate: a stored number that it determines or an
        unknown of its own."""
        return self.sets[self.result_of[name]][1].level_at(name, t)

    def giver(self, name):
        """The id of the set that gives a rate, a served fraction, a result or an endpoint's rate over
        its present flows (a dynamic read), or None for one that no set gives now."""
        key = self.result_of.get(name)
        if key is None:
            key = self.set_of.get(name.rsplit('.', 1)[0])
        dynamic = self.plan.dynamic.get(name) if key is None else None
        if dynamic is not None and dynamic.source[0] == 'flows':
            key = self.set_of.get(dynamic.source[1])
        return key

    def fresh(self, name, tx):
        """A rate or a result that the settling decides, read while the stages of a round run (see the
        module; spec, "Reading a result": a stale answer is a wrong one): it fails in the setup, for a
        flow that joined since the flows last settled, and where what it depends on changed since
        (`stale`). A flow that left since reads zero (`rate`)."""
        plan, run = self.plan, self.run
        flow = name.rsplit('.', 1)[0]
        if flow in run.left:
            return
        solver = plan.results.get(name) or plan.solved_flows.get(flow)
        if run.moment.round == 0 and solver is None:
            raise SimulationError(
                f'{name} is read before the flows first settle: the setup reads it, and they settle once '
                f'it commits. {ADVICE}'
            )
        if flow in run.joined or ('joined', name) in run.changed:
            raise SimulationError(
                f'{name} is read before its flow first settles: {flow} joined since the flows last '
                f'settled. {ADVICE}'
            )
        key = self.giver(name)
        if run.moment.round == 0 or (key is None and solver is not None):
            raise SimulationError(
                f'{name} is read before its first solve: it settles after the stages of the round '
                f'commit. {ADVICE}'
            )
        if key is None and name not in plan.outside:
            return  # a flow in no set moves nothing
        found = self.stale(name if key is None else key, tx)
        if found is None:
            return
        via, changes = found
        follows = f'it follows {via}, and ' if via is not None else ''
        connected = self.sets[key][0] if key is not None else None
        if connected is not None and connected.way == DECLARED:
            raise SimulationError(
                f'{name} is read before its solve settles: {follows}since it last settled, '
                f'{_listed(changes)} (the solver {connected.solver}). {ADVICE}'
            )
        raise SimulationError(
            f'{name} is read before the flows settle again: {follows}since they last settled, '
            f'{_listed(changes)}. {ADVICE}'
        )

    def stale(self, item, tx):
        """What changed since the flows last settled that the rates or results of a set (its id) or
        of a flow from SOURCE to SINK (its rate's name) depend on: (the rate on the way to it, or
        None, and what changed), or None. A set depends on what its settings and its problem read
        (`Connected.reads`), its stores, the allocations of their endpoints and the flows that join
        or leave them, and on the sets whose rates and results its settings read
        (`Connected.rates`), as far as they go; the first set on that way at which something
        changed is the one named. Each set costs what changed, not its size."""
        run, plan = self.run, self.plan
        names, marks = run.unsettled(tx)
        joined, left = set(run.joined), set(run.left)
        ends = {}  # a store -> what joined or left it since the flows last settled
        for flow in (*run.joined, *run.left):
            how = 'joined' if flow in joined else 'left'
            for connection in plan.flows[flow].connections:
                for end in (connection.source, connection.sink):
                    if end is not None:
                        ends.setdefault(end, []).append(f'{flow} {how} {end}')
        pending, seen = deque([(item, None)]), {item}
        while pending:
            item, via = pending.popleft()
            reads, rates = self._depends(item)

            def mine(store, item=item):
                return self.set_of.get(store) == item  # a store of the set (none of a flow outside)

            changes = [f'{name} changed' for name in sorted(names) if name in reads or mine(name)]
            for mark in sorted(marks):
                if mark[0] == 'bound' and mine(mark[1]):
                    changes.append(f'{mark[1]} met its bound')
                elif mark[0] == 'allocation' and mine(mark[1]):
                    changes.append(f'the allocation of {mark[1]}.{mark[2]} changed')
            for store in sorted(ends):
                if mine(store):
                    changes += ends[store]
            for rate in sorted(rates):
                flow = rate.rsplit('.', 1)[0]
                if flow in joined or flow in left:
                    changes.append(f'{flow} {"joined" if flow in joined else "left"}')
            if changes:
                return via, list(dict.fromkeys(changes))
            for rate in sorted(rates):
                key = self.giver(rate)
                if key is not None and key not in seen:
                    seen.add(key)
                    pending.append((key, via or rate))
        return None

    def _depends(self, item):
        """(what it reads, the rates and results of other sets that it reads) of a set by its id, or
        of a flow from SOURCE to SINK by its rate's name, as its settings read them."""
        if item in self.sets:
            connected = self.sets[item][0]
            return connected.reads, connected.rates
        plan = self.plan
        found = plan.settings_reads(plan.outside[item])
        rates = set()
        for name in found.leaves:
            value, dynamic = plan.values.get(name), plan.dynamic.get(name)
            if (value is not None and value.kind in (RATE, RESULT)) or (
                dynamic is not None and dynamic.steps[-1:] in (('actual_rate',), ('served_fraction',))
            ):
                rates.add(name)
        return found.leaves | found.formulas | found.stepped, rates

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

    def renew(self):
        """A round's stages begin: each declared solver's next solve starts on a fresh instance with
        its basis (`solve.Solver.renew`)."""
        for solver in self.kept.values():
            solver.renew()

    def finish(self, t, moment=True):
        """At the horizon: each instance stands there and the lines settle what left a bound. Where
        the horizon is a moment that a run that goes on has too (`moment`: a stage, a timer, a key
        time or a contact is due there), a set whose rates move that was built there records its state
        there, with the rates that its first segment would start with; at a horizon that is no other
        moment, the sets whose segments merely end there hold their values in their pieces, as a
        longer run's segments through it do. So a value at the horizon reads the same in a run that
        ends there as in one that goes on."""
        self.cut(t)
        for instance in self.instances:
            if isinstance(instance, Lines) or (moment and isinstance(instance, ComponentWay | Sparse)):
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
        """The sets `ids` leave their instances at time t; gives the values of their stores there, in
        the order of the sets' ids (a set of ids has no order of its own)."""
        values = {}
        for key in sorted(ids):
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
            """The level of a new set, as a computation of `walk.walked`, so that a chain of sets that
            read the rates of the next is no limit: each new set whose rates it reads is one that it
            yields. `path` holds the sets on the way to it, which the driver walks depth first."""
            if level[index] is not None:
                return level[index]
            if index in path:
                raise SimulationError(
                    f'{(made[index].flows or (made[index].solver,))[0]}: requests or capacities of '
                    "connected sets that read one another's actual rates or results: a relation between "
                    'the rates of two calculations needs one declared solver that owns them both, '
                    'which states it as a constraint'
                )
            path.add(index)
            found = 0
            for name in made[index].rates:
                if name in new_rates:
                    found = max(found, (yield level_of(new_rates[name], path)) + 1)
                elif name in rate_sets:
                    found = max(found, self.levels[rate_sets[name]] + 1)
            path.discard(index)
            level[index] = found
            return found

        for index in range(len(made)):
            walked(level_of(index, set()))
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

    def _register(self, connected, depth, key=None):
        """A new set: its id, its level and what it reads; a restored set keeps its own id
        (`saved.py`)."""
        if key is None:
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
