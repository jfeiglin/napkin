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

**A rate read in a round** (D5; PLAN, change 27): in a moment the stages commit
first and the flows are shared again after, so while the stages of a round run, and its conditions
once a firing has changed something, every rate and result that the settling decides (of local
sharing as of a declared solver, a flow from SOURCE to SINK too) is the one of the last settling.
Each affected set publishes its numeric answers after the sharing. An untouched component or sparse
set samples its installed segment at the moment's time when its answer is read. A flow that joins
reads zero and a flow that leaves keeps its opening rate until the settling retires it.
"""

from __future__ import annotations

import math
from dataclasses import replace

from ..continuous.walk import walked
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
        self.sampled = {}  # component or sparse instance's first set id -> time of its published answers
        self.moving_solvers = {}  # set ids of solvers whose incoming record needs its prepared prefix
        self.followers = set()  # ids of sets that sample another instance's incoming segment
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
        time. The installed way gives the rate until the next settling, including for a flow
        whose occurrence finished in this round. A flow with no installed way reads zero."""
        instance = self.instance_of(name.rsplit('.', 1)[0])
        return 0.0 if instance is None else instance.rate_at(name, t)

    def held_rate(self, name):
        """Whether the active expression for a rate holds through the present segment."""
        way = self.instance_of(name.rsplit('.', 1)[0])
        return isinstance(way, Family | Lines) or (isinstance(way, Sparse) and name in way.held_rates)

    def publish(self, instance, t, incoming=False, flows=None):
        """Publish the numeric answer of an installed set. Moving rates use the modes of their
        segment at t. A connection's carried rate supplies its leg and both incident endpoints."""
        whole = flows is None
        if whole:
            flows = instance.flows
        if isinstance(instance, Sparse):
            pending = instance.pending
            y = instance.y if pending is None else pending[2](t)
            evaluations = instance.evaluations
            try:
                if not incoming:
                    instance._start()
                primary, carried = instance.values(t, y)
            finally:
                instance.evaluations = evaluations
            answers = dict(zip(instance.recorded, map(float, primary)))
            if not instance.net.plain:
                answers.update(
                    (f'{name}.actual_rate', float(number))
                    for name, number in zip(instance.net.connections, carried)
                )
        elif isinstance(instance, ComponentWay):
            if not incoming:
                instance._settle()
            component, segment = instance.component, instance.pending
            y = component.state.y if segment is None or segment.solution is None else segment.solution(t)
            evaluations = component.state.evaluations
            try:
                component.field.rates(t, component.context.project(y))
                answers = dict(zip(instance.rates, map(float, component.field.delivered)))
            finally:
                component.state.evaluations = evaluations
        elif isinstance(instance, DeclaredWay):
            answers = instance.publish_at(t, incoming)
        else:
            answers = {}
            for flow in flows:
                row = instance.row[flow]
                if isinstance(instance, Family):
                    answers[f'{flow}.actual_rate'] = float(instance.rate[row])
                else:
                    answers[instance.recorded[row]] = float(instance.value[row])
                    if not instance.net.plain:
                        for c in instance.net.conns.of(row):
                            answers[f'{instance.net.connections[c]}.actual_rate'] = float(instance.rate[c])
        run = self.run
        run.published.update(answers)
        ends = {}
        for flow in flows:
            for connection in self.plan.flows[flow].connections:
                amount = run.published.get(f'{connection.name}.actual_rate', 0.0)
                for store, side in ((connection.source, 'outflow'), (connection.sink, 'inflow')):
                    if store is not None:
                        ends[store, side] = ends.get((store, side), 0.0) + amount
        for (store, side), installed in ends.items():
            # The installed connections still carry the round's opening answer after a stage
            # changes membership. A partial refresh of fixed rows needs their unchanged neighbours.
            total = (
                installed
                if whole
                else sum(run.published.get(f'{c}.actual_rate', 0.0) for c in self.plan.incident(store, side))
            )
            run.published[f'{store}.{side}.actual_rate'] = total
        if isinstance(instance, Sparse | ComponentWay):
            self.sampled[instance.key] = t

    def shared_value(self, name):
        """A numeric answer of the last sharing. An installed moving set samples just once at this
        time, from its held inputs, branch choices and membership, even after a stage has written."""
        if self.sampled and name.endswith(('.actual_rate', '.served_fraction')):
            owner = name.rsplit('.', 1)[0]
            instance = self.instance_of(owner)
            if instance is None and name in self.plan.shared:  # a leg or the side of a store
                instance = self.instance_of(owner.rsplit('.', 1)[0])
            if isinstance(instance, Sparse | ComponentWay) and self.sampled[instance.key] != self.run.now:
                self.publish(instance, self.run.now, incoming=True)
        return self.run.published.get(name, 0.0)

    def opening(self, t):
        """A moving solver samples before stages write inputs used to fit its incoming record."""
        for key in self.moving_solvers:
            self.publish(self.sets[key][1], t, incoming=True)

    def sample_at_stop(self, t):
        """Keep numeric answers at a breakpoint, including unread sets whose dense output ends here."""
        for key, at in self.sampled.items():
            if at != t:
                self.publish(self.sets[key][1], t, incoming=True)

    def result(self, name, t):
        """A result of a declared solver that is no rate: a stored number that it determines or an
        unknown of its own."""
        return self.sets[self.result_of[name]][1].level_at(name, t)

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

    def cut_order(self):
        """A set records its rates before a supplier discards the segment those rates read."""
        if not self.followers:
            return self.instances
        readers = [self.sets[key][1] for key in sorted(self.followers, key=self.levels.get, reverse=True)]
        first = set(readers)
        return [*readers, *(way for way in self.instances if way not in first)]

    def peek(self):
        """(the time of the next event of an instance, the instance), or (inf, None)."""
        found = (math.inf, None)
        for instance in self.cut_order():
            at = instance.peek()
            if at < found[0]:
                found = (at, instance)
        return found

    def cut(self, t):
        """Every instance stands at time t. Give the stores brought to a bound by the cut."""
        met = set()
        for instance in self.cut_order():
            met.update(instance.cut(t) or ())
        return met

    def switched(self, t):
        """The switches of rates that the states of the ways reached at time t, where every instance
        stands (`cut`): the flows that must rebuild at the settling. Each
        way whose rates move between moments says which of its switches its window reached at its
        end (`switched_at(t)`); a way whose rates hold between moments reaches none."""
        found = set()
        for instance in self.instances:
            reached = getattr(instance, 'switched_at', None)
            if reached is not None:
                found |= reached(t)
        return found

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
            if name in self.result_of:
                found.add(self.result_of[name])
            found |= self.readers.get(name, set())
        return found

    def moving_sources(self, sets):
        """The ids of the sets now whose rates move between moments and that the settings of the
        connected sets `sets` read: they integrate with them (`build`)."""
        found = set()
        for connected in sets:
            if not connected.stores and connected.solver is None:
                continue  # an empty state follows its producer's installed trajectory
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
        return found + list(connected.results) + list(connected.stores)

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
            self.sampled.pop(key, None)
            self.moving_solvers.pop(key, None)
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
            self.followers.discard(key)
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
                if not connected.stores and connected.solver is None:
                    producer = rate_sets.get(name)
                    moves = (
                        moving[owner] if owner is not None else producer is not None and self.moving(producer)
                    )
                    if moves:
                        made[index] = replace(connected, way=SPARSE, moves=True)
                        moving[index] = True
                    continue
                if owner is None:
                    if name in rate_sets and self.moving(rate_sets[name]):
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
        if isinstance(instance, Sparse) and instance.following:
            self.followers.add(instance.key)
        if isinstance(instance, MovingDeclared):
            self.moving_solvers[instance.key] = None
        instance.begin()
        self.publish(instance, self.run.now)
