"""The state of a run as data, and the run made again from it (docs/design/decisions.md, change 15).

A checkpoint (`napkin/program/checkpoint.py`) holds, beside the logical state that a caller reads,
the state of the engine at the stop (`save`). A fresh process makes the run again from it
(`restore`) and goes on from there: nothing before the stop runs twice. Everything that the future
of a run reads is here, or is made again from what is here by the same code:

- **the plan**: the program's plan, made again (`Plan.of`), then each change that the run made to it,
  in order (`Plan.log`): the occurrences, the first reads of expressions that named values (so the
  values are named in the same order), the definitions and allocations of commits, the flows that
  joined and left, and the stores that started to move. An expression is named by its place in a
  walk of the program's setup and events (`_expressions`).
- **the run**: the values that it holds, their bounds, sizes and scales, the frozen formulas, the
  times of the changes that `elapsed` reads, what the round in progress wrote and changed, the next
  moment that it knows and the time; the record so far as the recorder holds it (the pieces of
  each value and the trace); the draws of the stage that stopped, and the hits and edits of the
  breakpoints. A stop in the opening stages also keeps the published numeric rates and results and
  the direct store levels at the moment. Its recorder includes the incoming prefix. The saved
  changes to the ways' physical states install that prefix after the held stages commit;
- **the occurrences** (where each waits, the steps due, the delays that wait for the round's
  settling), **the triggers** (armed, rearm, firings) and **the moment** (its round, the stages held);
- **the ways**: each connected set by its id and level, each instance with its live sets in their
  order, and in each the line of each store (the time at which it starts, the value there, its
  rate), the rate of each flow and what it asks, the flags of the bounds, the times at which a line
  meets a bound, what the instance captured when it was built (a component's parameters, rigid flows
  and missing values, the sparse integrator's constants), the bounds that a component's state rests
  on as it found them, the faces of its stocks and the sides of the switches at which it stands,
  and each declared solver's program and basis
  (`solve.Solver`) with its last problem (a digest) and answer.

An unaffected live Radau solver can continue its step across a moment. At a restart the live
solver can reuse its last step size. A restored solver selects its first step. Both runs make the same
decisions in the same order. The values agree closely. Inside a long step, the relative
difference can exceed `rtol`. The engine also starts a new moving-solver segment
(`declared.MovingDeclared.cut`), renews the HiGHS instance with its basis (`solve.Solver.renew`),
and calculates trigger predictions again. After a restore, the engine processes the sets in the
same order (`moment.Moment.settle`). The instances of the family and of the lines hold the rows of sets that
left them; a restored instance holds the live ones, in their order, which changes no row's numbers
and no order of events. Caches are made again as the run reads.

The data of each part is a tuple of (name, value) fields: numbers, texts, tuples, and the records of
`napkin/program/checkpoint.py`. An array is a tuple of its numbers; a sparse matrix is (its shape,
`indptr`, `indices`, `data`).
"""

from __future__ import annotations

import heapq
import math
from copy import copy, deepcopy
from dataclasses import fields, is_dataclass

import numpy as np
import scipy.sparse as sp
from scipy.optimize._highspy import _core as highs

from ...core import expr as nodes
from ...core.errors import ExpressionError
from ...program.refs import Expr, Path
from ..continuous.transfers import ClockLeg
from ..errors import SimulationError
from ..solve.kept import Kept
from ..solve.solver import Budget, Solver
from .component import ComponentWay
from .declared import DeclaredWay, MovingDeclared
from .family import Family
from .lines import Lines
from .network import Asked, Instant
from .occurrences import Live
from .plan import Connected
from .sparse import Sparse
from .stocks import RestingAmounts, RestingRates

_ERRORS = {
    kind.__name__: kind
    for kind in (
        ExpressionError,
        SimulationError,
        ArithmeticError,
        ZeroDivisionError,
        ValueError,
        LookupError,
    )
}


# ---- the program's expressions ------------------------------------------------------------------


def _expressions(program):
    """The expressions and paths of the program's setup and events, in the order of a walk of their
    records: a run names an expression of a log entry by its place here."""
    found, seen = [], set()

    def walk(value):
        if isinstance(value, Expr | Path) and id(value) not in seen:
            seen.add(id(value))
            found.append(value)
        if isinstance(value, tuple | list):
            for item in value:
                walk(item)
        elif is_dataclass(value) and not isinstance(value, type):
            for item in fields(value):
                walk(getattr(value, item.name))

    walk(program.setup)
    for template in program.templates:
        walk(template.events)
    return found


# ---- data of engine records -----------------------------------------------------------------------


def _array(values):
    return tuple(np.asarray(values).tolist())


def _matrix(matrix):
    matrix = sp.csr_array(matrix)
    return (tuple(matrix.shape), _array(matrix.indptr), _array(matrix.indices), _array(matrix.data))


def _csr(data):
    shape, indptr, indices, values = data
    return sp.csr_array(
        (np.array(values, dtype=float), np.array(indices, dtype=np.int32), np.array(indptr, dtype=np.int32)),
        shape=tuple(shape),
    )


def _set(connected):
    """A connected set as data."""
    return (
        connected.stores,
        connected.flows,
        connected.formulas,
        connected.stepped,
        connected.way,
        tuple(sorted(connected.rates)),
        tuple(sorted(connected.reads)),
        connected.solver,
        connected.results,
        connected.moves,
    )


def _connected(data):
    stores, flows, formulas, stepped, way, rates, reads, solver, results, moves = data
    return Connected(
        tuple(stores),
        tuple(flows),
        tuple(formulas),
        tuple(stepped),
        way,
        frozenset(rates),
        frozenset(reads),
        solver,
        tuple(results),
        moves,
    )


def _pairs(mapping):
    return tuple(mapping.items())


def _captured(found):
    """A value that a delay captured, or the error that reading it raised, as data."""
    if isinstance(found, Exception):
        return ('error', type(found).__name__, str(found))
    return ('value', found)


def _uncaptured(data):
    if data[0] == 'error':
        return _ERRORS.get(data[1], SimulationError)(data[2])
    return data[1]


# ---- save ---------------------------------------------------------------------------------------------


def at_stop(run):
    """Project the incoming record and physical end states into checkpoint data. The checkpoint
    records from a projection of the recorder, so a pause leaves the run's own histories as they
    were, and the live ways keep their pending segments. A restored run installs the end states
    after its held stages."""
    run.ways.sample_at_stop(run.now)
    if run.saved_arrival is not None:
        return run.recorder.projection(), run.saved_arrival
    # A later round can stop after the transfers were booked but before the
    # corresponding histories were requested. Only the checkpoint needs those pieces.
    if not run.arriving and not any(
        isinstance(way, Sparse) and way.pending is not None and way.t < run.now for way in run.ways.instances
    ):
        recorder = run.recorder.projection()
        run.ways.project(recorder, run.now)
        return recorder, None
    projected = copy(run)
    projected.stock_state = copy(run.stock_state)
    projected.stock_state.run = projected
    projected.stock_state.balances = dict(run.stock_state.balances)
    projected.stock_state.ranges = dict(run.stock_state.ranges)
    projected.stock_state.ends = dict(run.stock_state.ends)
    projected.recorder = recorder = run.recorder.projection(projected)
    projected.moved = set(run.moved)
    memo = {
        id(run): projected,
        id(run.plan): run.plan,
        id(run.plan.units): run.plan.units,
        id(run.recorder): recorder,
    }
    for solver in run.ways.kept.values():
        memo[id(solver)] = solver  # the cut uses the prepared prefix; no solve is committed
    ways = projected.ways = copy(run.ways)
    ways.run = projected
    for way in run.ways.instances:
        if isinstance(way, Sparse) and way.solver is not None:
            memo[id(way.solver)] = way.solver  # pending dense output is read; Radau takes no step
        if not isinstance(way, Sparse | ComponentWay | MovingDeclared) and not any(
            way.timing_events(run.clock.apart(run.now))
        ):
            memo[id(way)] = way  # a line with no due bound has no cut
    ways.instances = [deepcopy(way, memo) for way in run.ways.instances]
    ways.sets = {key: (connected, memo[id(way)]) for key, (connected, way) in run.ways.sets.items()}
    projected.arrival_limits = {memo[id(way)]: end for way, end in run.arrival_limits.items()}
    projected.finish_arrival()
    for way in ways.instances:
        if isinstance(way, Sparse):
            way.cut(run.now)
    deltas = []
    levels = {}
    for k, (live, preview) in enumerate(zip(run.ways.instances, projected.ways.instances, strict=True)):
        if live is preview:
            continue
        before = dict(_instance(live)[2])
        if before['arrival_rates'] is not None:
            end, left = before['arrival_rates']
            preview.arrival_rates = end, dict(left)
        delta = tuple((name, value) for name, value in _instance(preview)[2] if before[name] != value)
        if delta:
            deltas.append((k, delta))
        if isinstance(live, Sparse | ComponentWay | MovingDeclared):
            levels.update((name, live.accepted_level(name, run.now)) for name in live.stores)
    return recorder, (tuple(deltas), tuple(sorted(projected.moved - run.moved)), _pairs(levels))


def save(run, recorder, arrival):
    """The state of a run that a breakpoint stopped, as data (see the module)."""
    plan = run.plan
    index = {id(found): k for k, found in enumerate(_expressions(plan.program))}
    log = []
    for entry in plan.log:
        if entry[0] in ('node', 'resolve'):
            log.append((entry[0], index[id(entry[1])], entry[2], entry[3]))
        elif entry[0] == 'define':
            _, name, source, t, start = entry
            source = None if source is None else (index[id(source[0])], source[1], source[2])
            log.append(('define', name, source, t, start))
        else:
            log.append(entry)
    occurrences, moment, breaks = run.occurrences, run.moment, run.breaks
    held = moment.held
    if isinstance(held, tuple):
        held = (tuple(live.id for live in held[0]), held[1])
    return (
        ('log', tuple(log)),
        (
            'run',
            (
                ('now', run.now),
                ('limit', run.limit),
                ('env', tuple((name, value) for name, value in run.env.items() if name != 't')),
                ('bounds', _pairs(run.bounds)),
                ('scales', _pairs(run.scales)),
                ('sizes', _pairs(run.sizes)),
                ('frozen', _pairs(run.frozen)),
                ('changes', tuple((name, tuple(times)) for name, times in run.changes.items())),
                ('written', _pairs(run.written)),
                ('stocks', _pairs(run.stock_state.balances)),
                ('stock_ranges', _pairs(run.stock_state.ranges)),
                ('incoming_ends', _pairs(run.stock_state.ends)),
                ('published', _pairs(run.published)),
                ('arrival', arrival),
                ('contacts', run.contacts),
                ('consumed', _pairs(run.consumed)),
                ('separate', run.clock.separate),
                ('bounds_at_arrival', _pairs(run.bound_at)),
                ('changed', tuple(sorted(run.changed, key=repr))),  # a set, in one order
                # The rate settings outside the explicit-time check, which the record's note counts: the
                # run's own, as its record can end before the stop.
                ('unchecked_time_rates', _pairs(run.unchecked_time_rates)),
                ('moved', tuple(sorted(run.moved))),
                ('joined', tuple(run.joined)),
                ('left', tuple(run.left)),
                ('waiting', tuple(_set(connected) for connected in run.waiting)),
            ),
        ),
        (
            'recorder',
            (
                ('pieces', tuple(recorder.saved_pieces(run.now))),
                ('trace', tuple(recorder.trace)),
                ('constants', _pairs(recorder.constants)),
                ('tolerance', _pairs(recorder.tolerance)),
                ('formulas', tuple(sorted(recorder.formulas))),
                ('round', recorder.round),
                ('fit_ends', tuple(recorder.fits.ends)),
                ('wanted', None if recorder._wanted is None else tuple(sorted(recorder._wanted))),
                (
                    'transfers',
                    tuple((name, start, tuple(moved)) for name, (start, moved) in recorder.transfers.items()),
                ),
            ),
        ),
        ('draws', (('kept', tuple(sorted(run.chance.kept))),)),
        (
            'breaks',
            (
                ('hits', breaks.hits),
                ('edits', tuple(breaks.edits)),
                ('done', tuple(sorted(breaks.done))),
                ('start', breaks.start),
                ('next', breaks.next),
            ),
        ),
        (
            'occurrences',
            (
                ('made', occurrences.made),
                ('transferred', _pairs(occurrences.transferred)),
                (
                    'live',
                    tuple(
                        (
                            live.id,
                            live.number,
                            live.started,
                            live.step,
                            live.due,
                            live.version,
                            live.waiting,
                            live.active,
                            tuple(sorted(live.met)),
                        )
                        for live in occurrences.live.values()
                    ),
                ),
                ('schedule', tuple(occurrences.schedule)),
                (
                    'of_event',
                    tuple(
                        (key, tuple(live.id for live in found)) for key, found in occurrences.of_event.items()
                    ),
                ),
                ('gates', tuple(occurrences.gates)),
                (
                    'awaiting',
                    tuple(
                        (
                            live.id,
                            version,
                            next(k for k, each in enumerate(live.plan.event.steps) if each is step),
                            tuple((leaf, _captured(found)) for leaf, found in captured.items()),
                        )
                        for live, version, _, step, captured in occurrences.awaiting
                    ),
                ),
            ),
        ),
        (
            'triggers',
            tuple(
                (state.armed, state.rearm_at, state.blocked_at, state.firings)
                for state in run.triggers.states
            ),
        ),
        (
            'moment',
            (('phase', moment.phase), ('again', moment.again), ('round', moment.round), ('held', held)),
        ),
        ('ways', _ways(run.ways)),
    )


def _ways(ways):
    """The sets, the instances and the solvers of the ways (see the module)."""
    return (
        ('next', ways._next),
        ('grouped', tuple(sorted(ways.grouped))),
        (
            'sets',
            tuple((key, ways.levels[key], _set(connected)) for key, (connected, _) in ways.sets.items()),
        ),
        ('instances', tuple(_instance(instance) for instance in ways.instances)),
        ('references', _pairs(ways.references)),
        ('last', tuple((solver, digest, _array(x)) for solver, (digest, x) in ways.last.items())),
        ('kept', tuple((solver, _solver(found)) for solver, found in ways.kept.items())),
    )


def _solver(solver):
    """A declared solver's program and basis between two solves (`solve.Solver.renew`)."""
    kept = solver._kept
    instance = None
    if kept is not None:
        basis = kept.s.getBasis()
        instance = (
            _matrix(kept.A),
            _array(kept.row_lower),
            _array(kept.row_upper),
            _array(kept.lower),
            _array(kept.upper),
            (tuple(int(each) for each in basis.col_status), tuple(int(each) for each in basis.row_status))
            if basis.valid
            else None,
        )
    return (
        ('columns', tuple(solver._columns)),
        ('rows', tuple(solver._rows)),
        ('scale', _array(solver._scale)),
        ('A', _matrix(solver._A)),
        ('instance', instance),
    )


def _lines_of(instance, stores):
    """The line of each store of an instance, by name: (the value at its start, its start, its rate)."""
    return tuple(
        (name, float(instance.y[s]), float(instance.since[s]), float(instance.slope[s]))
        for s, name in enumerate(stores)
    )


def _instance(instance):
    """Include the accepted physical transfers of the live rows in the checkpoint."""
    kind, keys, fields = _instance_fields(instance)
    if kind in ('lines', 'family'):
        names = instance.flows if kind == 'family' else instance.net.connections
        closed = tuple(
            (names[row], t, amount)
            for row, t, amount in instance.amounts.closed()
            if not (instance.dead[row] if kind == 'family' else instance.dead_flows[instance.net.of[row]])
        )
        fields += (('closed_amounts', closed),)
    elif kind == 'declared':
        fields += (
            (
                'closed_amounts',
                tuple(
                    (instance.net.connections[row], t, amount) for row, t, amount in instance.amounts.closed()
                ),
            ),
        )
    elif kind in ('sparse', 'component', 'moving'):
        amounts = instance.amounts
        segment = instance.component.state if kind == 'component' else instance
        if segment.held_comparisons:
            fields += (('held_comparisons', tuple(sorted(segment.held_comparisons))),)
        fields += (
            ('amount_origin', amounts.start),
            (
                'clock_amounts',
                tuple(
                    (
                        row,
                        leg.mode,
                        leg.start,
                        leg.closed,
                        leg.origin,
                        leg.polynomial,
                        leg.source,
                        leg.sink,
                        leg.feeds_source,
                        leg.drains_sink,
                    )
                    for row, leg in amounts.clocks.items()
                ),
            ),
            (
                'accepted_amounts',
                (
                    amounts.through,
                    np.asarray(amounts.total).tolist()
                    if amounts.single is not None
                    else _array(amounts.total),
                    np.asarray(amounts.remainder).tolist()
                    if amounts.single is not None
                    else _array(amounts.remainder),
                ),
            ),
        )
    incoming = getattr(instance, 'arrival_rates', None)
    if instance.resting is not None and getattr(instance, 'pending', None) is not None:
        end = instance.run.now
        if instance.holds_incoming(end):
            left = instance.incoming_rates(math.nextafter(end, -math.inf))
            incoming = end, {name: left(name) for name in instance.resting.incident}
    fields += (
        ('arrival_rates', None if incoming is None else (incoming[0], _pairs(incoming[1]))),
        (
            'resting_rates',
            None
            if instance.resting_rates is None
            else (
                tuple((instance.stores[i], side) for i, side in instance.resting_rates.sides.items()),
                _pairs(instance.resting_rates.offsets),
            ),
        ),
        ('resting', _pairs(instance.resting.rows) if instance.resting is not None else ()),
        ('donor', getattr(instance, 'donor', None)),
        ('certified', _pairs(getattr(instance, 'certified', {}))),
        ('adjustments', _pairs(getattr(instance, 'adjustments', {}))),
    )
    return kind, keys, fields


def _instance_fields(instance):
    """An instance of a way as data: its kind, its live sets' ids, and its fields."""
    if isinstance(instance, Family):
        rows = [k for k in range(len(instance.flows)) if not instance.dead[k]]
        keys = [key for key, k in sorted(instance.keys.items(), key=lambda item: item[1])]
        live = set(rows)
        due = [entry for entry in instance.due if entry[1] in live and entry[2] == instance.version[entry[1]]]
        return (
            'family',
            tuple(keys[k] for k in rows),
            (
                ('sets', tuple(_set(instance.sets[k]) for k in rows)),
                ('t0', instance.t0),
                ('lines', _lines_of(instance, instance.stores)),
                (
                    'rows',
                    tuple(
                        (
                            instance.flows[k],
                            float(instance.rate[k]),
                            float(instance.asked[k]),
                            float(instance.wanted[k]),
                            int(instance.version[k]),
                        )
                        for k in rows
                    ),
                ),
                (
                    'due',
                    tuple(
                        (reach, instance.flows[k], version, tuple(instance.stores[s] for s in bounded))
                        for reach, k, version, bounded in due
                    ),
                ),
                ('settings', _pairs(instance.settings)),
            ),
        )
    if isinstance(instance, Lines):
        live_keys = [key for key in instance.keys if key in instance.members]
        stores = [s for key in live_keys for s in instance.members[key]]
        flows = [f for key in live_keys for f in instance.flows_of[key]]
        valid = [
            entry
            for entry in instance.due
            if entry[1] in set(stores) and entry[2] == instance.version[entry[1]]
        ]
        asked = instance.asked
        net = instance.net
        conns = [int(c) for f in flows for c in (net.conns.of(f).tolist() if not net.plain else [f])]
        return (
            'lines',
            tuple(live_keys),
            (
                ('sets', tuple(_set(instance.sets[instance.keys.index(key)]) for key in live_keys)),
                ('t0', instance.t0),
                (
                    'lines',
                    tuple(
                        (
                            instance.stores[s],
                            float(instance.y[s]),
                            float(instance.since[s]),
                            float(instance.slope[s]),
                            int(instance.version[s]),
                            bool(instance.instant.lower[s]),
                            bool(instance.instant.upper[s]),
                            float(asked.end_request[0][s]),
                            float(asked.end_request[1][s]),
                            float(asked.end_capacity[0][s]),
                            float(asked.end_capacity[1][s]),
                        )
                        for s in stores
                    ),
                ),
                ('flows', tuple((instance.flows[f], float(instance.value[f])) for f in flows)),
                (
                    'connections',
                    tuple(
                        (float(instance.rate[c]), float(asked.request[c]), float(asked.capacity[c]))
                        for c in conns
                    ),
                ),
                ('due', tuple((reach, instance.stores[s], version) for reach, s, version in valid)),
                ('stale', tuple(sorted(instance.stores[s] for s in instance.stale))),
                ('selected', instance.selected),
                ('solved', instance.instant.selected),
                ('closed', instance.closed),
            ),
        )
    if isinstance(instance, ComponentWay):
        state = instance.component.state
        known, missing, rigid = instance.captured
        return (
            'component',
            (instance.key,),
            (
                ('set', _set(instance.connected)),
                ('time', float(state.time)),
                ('y', _array(state.y)),
                ('store', _pairs(state.store)),
                ('evaluations', state.evaluations),
                ('still', instance.still),
                # The bounds that the state rests on, as the component found them, the faces of its
                # stocks and the sides of the switches at which it stands: a restored one holds them,
                # and does not find them again (`_settle`).
                ('bounded', instance.bounded),
                ('bounds', tuple(sorted(state.active_bounds))),
                ('zero_faces', tuple(sorted(state.zero_faces))),
                ('right_faces', tuple(sorted(state.right_faces))),
                ('switches', tuple(state.switches)),
                ('clock', state.clock),
                ('known', _pairs(known)),
                ('missing', _pairs(missing)),
                ('rigid', tuple(rigid)),
            ),
        )
    if isinstance(instance, Sparse):
        return (
            'sparse',
            tuple(sorted(key for key, (_, found) in instance.run.ways.sets.items() if found is instance)),
            (
                ('sets', tuple(_set(connected) for connected in instance.sets)),
                ('levels', tuple(instance.set_levels)),
                ('t', instance.t),
                ('y', _array(instance.y)),
                ('brief', instance.brief),
                ('brief_from', instance.brief_from),
                ('evaluations', instance.evaluations),
                ('constants', _pairs(instance.vector.constants)),
                ('switches', tuple((store, tuple(flows)) for store, flows in instance.switches.items())),
                ('selected', instance.selected),
                (
                    'signs',
                    tuple((nodes.text(a), nodes.text(b), sign) for (a, b), sign in instance.signs.items()),
                ),
                ('selection', _pairs(instance.selection)),
                ('held_rates', tuple(sorted(instance.held_rates))),
                # A failed trial past the calendar turns them off for good: the same decisions after a
                # restore need it (`Sparse._local_trial`).
                ('local_steps', instance.local_steps),
            ),
        )
    if isinstance(instance, DeclaredWay):
        found = [
            ('set', _set(instance.connected)),
            ('t0', instance.t0),
            ('y', _array(instance.y)),
            ('since', _array(instance.since)),
            ('slope', _array(instance.slope)),
            ('value', _array(instance.value)),
            ('results', _pairs(instance.results)),
            ('requests', _array(instance.former.requests)),
            ('version', _array(instance.version)),
            ('due', tuple(instance.due)),
            ('alive', instance.alive),
        ]
        kind = 'declared'
        if isinstance(instance, MovingDeclared):
            kind = 'moving'
            found += [
                ('time', instance.time),
                ('low', _array(instance.low)),
                ('high', _array(instance.high)),
                (
                    'signs',
                    tuple(
                        (nodes.text(a), nodes.text(b), sign) for (a, b), sign in instance.region.signs.items()
                    ),
                ),
                ('rows', _pairs(instance.region.rows)),
            ]
        return (kind, (instance.key,), tuple(found))
    raise TypeError(f'no state of an instance of {type(instance).__name__}')


# ---- restore ------------------------------------------------------------------------------------------


def _scope(plan, owner):
    """The scope of an owner of a log entry: the root's, a member's or an occurrence's."""
    if not owner:
        return None
    if '#' in owner:
        return plan.frames[owner]
    template, row = plan.program.member(owner)
    return (template, row, template.members[row])


def restore(run, data):
    """Make a fresh run of a plan (`run`, not started) the run whose state `data` holds (`save`)."""
    plan, parts = run.plan, dict(data)
    expressions = _expressions(plan.program)
    plan.started = run.started = True
    made, log = {}, []
    for saved in parts['log']:
        kind, entry = saved[0], saved
        if kind == 'occurrence':
            _, member, event, number, args, started, references = entry
            found = plan.occurrence(member, event, number, tuple(args), started, references)
            made[found.id] = found
        elif kind in ('node', 'resolve'):
            _, k, owner, origin = entry
            read = run.occurrences.node if kind == 'node' else run.moment.resolved
            read(expressions[k], _scope(plan, owner), origin)
            entry = (kind, expressions[k], owner, origin)
        elif kind == 'define':
            _, name, source, t, start = entry
            node = None
            if source is not None:
                source = (expressions[source[0]], source[1], source[2])
                node = run.occurrences.node(source[0], _scope(plan, source[1]), source[2])
            plan.define(name, node, t, start)
            entry = ('define', name, source, t, start)
        elif kind == 'allocate':
            _, store, side, ranking = entry
            plan.allocate(store, side, ranking)
        elif kind == 'present':
            run._present(entry[1], entry[2])
        elif kind == 'moving':
            plan.moving.add(entry[1])
        log.append(entry)
    # The log of the restored plan, which a later checkpoint holds again; the reads above logged
    # some of its entries a second time.
    plan.log = log
    _run(run, dict(parts['run']))
    _recorder(run.recorder, dict(parts['recorder']))
    for entry in run.recorder.trace:
        if entry.kind == 'finish':
            plan.frozen_scales.update(entry.detail('scales') or ())
    run.chance.kept = set(dict(parts['draws'])['kept'])
    found = dict(parts['breaks'])
    breaks = run.breaks
    breaks.hits, breaks.edits, breaks.done = found['hits'], list(found['edits']), set(found['done'])
    breaks.start, breaks.next = found['start'], found['next']
    _occurrences(run, dict(parts['occurrences']), made)
    for state, (armed, rearm_at, blocked_at, firings) in zip(
        run.triggers.states, parts['triggers'], strict=True
    ):
        state.armed, state.rearm_at, state.blocked_at, state.firings = armed, rearm_at, blocked_at, firings
    found = dict(parts['moment'])
    moment = run.moment
    moment.phase, moment.again, moment.round = found['phase'], found['again'], found['round']
    held = found['held']
    if isinstance(held, tuple):
        held = ([run.occurrences.live[name] for name in held[0]], held[1])
    moment.held = held
    _restore_ways(run, dict(parts['ways']))
    run.stock_state.restore_missing()


def _run(run, found):
    run.now, run.limit = found['now'], found['limit']
    run.accepted = run.now
    run.env = {'t': run.now, **dict(found['env'])}
    run.bounds = {name: tuple(bounds) for name, bounds in found['bounds']}
    run.scales, run.sizes = dict(found['scales']), dict(found['sizes'])
    run.plan.comparison_scales.update(
        (name, abs(value)) for name, value in run.scales.items() if value is not None
    )
    run.frozen = dict(found['frozen'])
    run.changes = {name: list(times) for name, times in found['changes']}
    run.written = dict(found['written'])
    run.stock_state.balances = dict(found['stocks'])
    run.stock_state.ranges = dict(found['stock_ranges'])
    run.stock_state.ends = dict(found['incoming_ends'])
    run.published = dict(found['published'])
    run.saved_arrival = found['arrival']
    if run.saved_arrival is not None:
        run.arriving = True
        run.opening_levels = dict(run.saved_arrival[2])
    run.contacts, run.bound_at = tuple(found['contacts']), dict(found['bounds_at_arrival'])
    run.consumed = dict(found['consumed'])
    run.clock.separate = found['separate']
    run.changed, run.moved = set(found['changed']), set(found['moved'])
    run.unchecked_time_rates = dict(found['unchecked_time_rates'])
    run.joined, run.left = list(found['joined']), list(found['left'])
    run.waiting = [_connected(data) for data in found['waiting']]


def _recorder(recorder, found):
    recorder.pieces = {name: list(pieces) for name, pieces in found['pieces']}
    recorder.trace = list(found['trace'])
    recorder.constants = dict(found['constants'])
    recorder.tolerance = dict(found['tolerance'])
    recorder.formulas = set(found['formulas'])
    recorder.round = found['round']
    recorder.fits.ends = list(found['fit_ends'])
    # A full record retains every value (None); a selected one, the values that it saved.
    recorder._wanted = None if found['wanted'] is None else set(found['wanted'])
    recorder.transfers = {name: (start, list(moved)) for name, start, moved in found['transfers']}


def _occurrences(run, found, made):
    occurrences = run.occurrences
    occurrences.made = found['made']
    occurrences.transferred = dict(found['transferred'])
    occurrences.live = {}
    for name, number, started, step, due, version, waiting, active, met in found['live']:
        occurrences.live[name] = Live(
            made[name], number, started, step, due, version, waiting, active, set(met) & run.plan.stocks
        )
    occurrences.schedule = [tuple(entry) for entry in found['schedule']]
    heapq.heapify(occurrences.schedule)
    occurrences.of_event = {
        tuple(key): [occurrences.live[name] for name in names] for key, names in found['of_event']
    }
    occurrences.gates = {name: occurrences.live[name] for name in found['gates']}
    occurrences.awaiting = []
    for name, version, k, captured in found['awaiting']:
        live = occurrences.live[name]
        step = live.plan.event.steps[k]
        node = occurrences.node(step.delay, live.plan.scope, step.origin)
        values = {leaf: _uncaptured(value) for leaf, value in captured}
        occurrences.awaiting.append((live, version, node, step, values))


def _restore_ways(run, found):
    ways = run.ways
    ways._next, ways.grouped = found['next'], set(found['grouped'])
    for key, level, data in found['sets']:
        ways._register(_connected(data), level, key)
    deltas = {} if run.saved_arrival is None else dict(run.saved_arrival[0])
    for k, (kind, keys, data) in enumerate(found['instances']):
        instance = _made(run, kind, keys, dict(data), observe=True)
        for key in keys:
            ways.sets[key] = (ways.sets[key][0], instance)
        ways.instances.append(instance)
        if isinstance(instance, Sparse) and instance.following:
            ways.followers.add(instance.key)
        if instance.sample_on_read:
            ways.sampled[instance.key] = run.now
        elif isinstance(instance, MovingDeclared):
            ways.moving_solvers[instance.key] = None
        if k in deltas:
            projected = _made(run, kind, keys, dict((*data, *deltas[k])), observe=False)
            if isinstance(instance, Sparse | ComponentWay | MovingDeclared):
                instance.arrival_amounts = projected.amounts
            run.cut_at_resume.append((k, keys, projected))
    ways.references = dict(found['references'])
    ways.last = {solver: (digest, np.array(x, dtype=float)) for solver, digest, x in found['last']}
    budgets = run.plan.configuration.budgets
    for solver, saved in found['kept']:
        made = ways.kept[solver] = Solver(
            Budget(budgets.fair_programs, budgets.newton_steps, budgets.qp_iterations)
        )
        data = dict(saved)
        made._columns, made._rows = list(data['columns']), list(data['rows'])
        made._scale, made._A = np.array(data['scale'], dtype=float), _csr(data['A'])
        if data['instance'] is not None:
            A, row_lower, row_upper, lower, upper, basis = data['instance']
            if basis is not None:
                basis = (
                    [highs.HighsBasisStatus(each) for each in basis[0]],
                    [highs.HighsBasisStatus(each) for each in basis[1]],
                )
            made._kept = Kept.of(
                _csr(A),
                np.array(row_lower, dtype=float),
                np.array(row_upper, dtype=float),
                np.array(lower, dtype=float),
                np.array(upper, dtype=float),
                basis,
            )


def _made(run, kind, keys, data, *, observe):
    instance = _made_fields(run, kind, keys, data)
    instance.prepare_clock_rates(observe=observe)
    instance.donor = data.get('donor')
    if data.get('arrival_rates') is not None:
        t, rates = data['arrival_rates']
        instance.arrival_rates = t, dict(rates)
    if data.get('resting'):
        rests = instance.resting = RestingAmounts()
        rests.rows = dict(data['resting'])
        for store, (_, _, row) in rests.rows.items():
            for name, _ in row:
                rests.incident.setdefault(name, set()).add(store)
    if data.get('resting_rates') is not None:
        sides, offsets = data['resting_rates']
        instance.resting_rates = RestingRates()
        instance.resting_rates.sides = {instance.place[n]: side for n, side in sides if n in instance.place}
        instance.resting_rates.offsets = {n: value for n, value in offsets if n in instance.leg_rows}
    if data.get('adjustments'):
        instance.adjustments = dict(data['adjustments'])
    if data.get('certified'):
        instance.certified = dict(data['certified'])
    if 'closed_amounts' in data:
        rows = instance.row if kind == 'family' else instance.leg_rows
        for name, t, amount in data['closed_amounts']:
            if name in rows:
                instance.amounts.restore(rows[name], t, amount)
    if 'accepted_amounts' in data:
        segment = instance.component.state if kind == 'component' else instance
        segment.held_comparisons = (
            set(map(tuple, data['held_comparisons'])) if data.get('held_comparisons') else None
        )
        amounts = instance.amounts
        amounts.clocks = {}
        for row, mode, start, closed, origin, polynomial, *ends in data['clock_amounts']:
            leg = amounts.clocks[row] = ClockLeg(tuple(polynomial), start, *ends)
            leg.mode, leg.start, leg.closed, leg.origin = mode, start, closed, origin
        amounts.all_clock = bool(amounts.clocks) and len(amounts.clocks) == len(instance.leg_rows)
        amounts.start = data.get('amount_origin', amounts.start)
        amounts.through, total, remainder = data['accepted_amounts']
        if amounts.single is not None:
            amounts.total, amounts.remainder = total, remainder
        else:
            amounts.total, amounts.remainder = np.array(total), np.array(remainder)
    return instance


def _made_fields(run, kind, keys, data):
    """An instance of a way made again from its data (`_instance`), without its begin."""
    if kind == 'family':
        sets = [_connected(each) for each in data['sets']]
        lines = {name: (y, since, slope) for name, y, since, slope in data['lines']}
        instance = Family(run, sets, {name: y for name, (y, _, _) in lines.items()}, data['t0'], list(keys))
        for s, name in enumerate(instance.stores):
            instance.y[s], instance.since[s], instance.slope[s] = lines[name]
        for k, (_, rate, asked, wanted, version) in enumerate(data['rows']):
            instance.rate[k], instance.asked[k], instance.wanted[k], instance.version[k] = (
                rate,
                asked,
                wanted,
                version,
            )
        row = {name: k for k, name in enumerate(instance.flows)}
        place = instance.place
        instance.due = [
            (reach, row[flow], version, tuple(place[name] for name in bounded))
            for reach, flow, version, bounded in data['due']
        ]
        heapq.heapify(instance.due)
        instance.settings = dict(data['settings'])
        return instance
    if kind == 'lines':
        sets = [_connected(each) for each in data['sets']]
        lines = {entry[0]: entry[1:] for entry in data['lines']}
        instance = Lines(run, sets, {name: entry[0] for name, entry in lines.items()}, data['t0'], list(keys))
        count = len(instance.stores)
        lower, upper = np.zeros(count, dtype=bool), np.zeros(count, dtype=bool)
        end_request, end_capacity = np.zeros((2, count)), np.full((2, count), np.inf)
        for s, name in enumerate(instance.stores):
            y, since, slope, version, low, high, out_request, in_request, out_capacity, in_capacity = lines[
                name
            ]
            instance.y[s], instance.since[s], instance.slope[s], instance.version[s] = (
                y,
                since,
                slope,
                version,
            )
            lower[s], upper[s] = low, high
            end_request[:, s] = (out_request, in_request)
            end_capacity[:, s] = (out_capacity, in_capacity)
        for f, (_, value) in enumerate(data['flows']):
            instance.value[f] = value
        connections = data['connections']
        request = np.array([entry[1] for entry in connections], dtype=float)
        capacity = np.array([entry[2] for entry in connections], dtype=float)
        instance.rate = np.array([entry[0] for entry in connections], dtype=float)
        instance.asked = Asked(request, capacity, end_request, end_capacity)
        instance.instant = Instant(instance.net, instance.asked, lower, upper)
        instance.instant.selected = data['solved']
        place = instance.place
        instance.due = [(reach, place[name], version) for reach, name, version in data['due']]
        heapq.heapify(instance.due)
        instance.stale = {place[name] for name in data['stale']}
        instance.selected, instance.closed = data['selected'], data['closed']
        return instance
    if kind == 'component':
        connected = _connected(data['set'])
        y = np.array(data['y'], dtype=float)
        values = dict(zip(connected.stores, y.tolist(), strict=True))
        captured = (dict(data['known']), dict(data['missing']), tuple(data['rigid']))
        instance = ComponentWay(run, connected, values, data['time'], keys[0], captured)
        state = instance.component.state
        state.time, state.y = data['time'], y
        state.store.clear()
        state.store.update(dict(data['store']))
        state.evaluations, instance.still = data['evaluations'], data['still']
        instance.bounded = data['bounded']
        for held, found in (
            (state.active_bounds, data['bounds']),
            (state.zero_faces, data['zero_faces']),
            (state.right_faces, data['right_faces']),
        ):
            held.clear()
            held.update(tuple(each) if isinstance(each, tuple | list) else each for each in found)
        state.switches = tuple(tuple(each) for each in data['switches'])
        state.clock = None if data['clock'] is None else tuple(data['clock'])
        return instance
    if kind == 'sparse':
        sets = [_connected(each) for each in data['sets']]
        stores = [store for connected in sets for store in connected.stores]
        y = np.array(data['y'], dtype=float)
        given = {name: tuple(found) for name, found in data['constants']}
        instance = Sparse(
            run,
            sets,
            dict(zip(stores, y.tolist(), strict=True)),
            data['t'],
            keys[0],
            list(data['levels']),
            given,
        )
        instance.t, instance.y = data['t'], y
        instance.brief, instance.brief_from, instance.evaluations = (
            data['brief'],
            data['brief_from'],
            data['evaluations'],
        )
        instance.switches = {store: list(flows) for store, flows in data['switches']}
        instance.local_steps = data['local_steps']
        if data['selected']:
            signs = {(a, b): sign for a, b, sign in data['signs']}
            instance.signs = {
                (a, b): signs[key]
                for a, b in instance.surfaces
                if (key := (nodes.text(a), nodes.text(b))) in signs
            }
            instance.choose(instance.signs)
            instance.selection.update(data['selection'])
            instance.held_rates = set(data['held_rates'])
            instance.selected = True
        return instance
    if kind in ('declared', 'moving'):
        connected = _connected(data['set'])
        values = dict(zip(connected.stores, data['y'], strict=True))
        way = MovingDeclared if kind == 'moving' else DeclaredWay
        instance = way(run, connected, values, data['t0'], keys[0])
        instance.y = np.array(data['y'], dtype=float)
        instance.since, instance.slope = (
            np.array(data['since'], dtype=float),
            np.array(data['slope'], dtype=float),
        )
        instance.value = np.array(data['value'], dtype=float)
        instance.results = dict(data['results'])
        instance.former.requests = np.array(data['requests'], dtype=float)
        instance.version = np.array(data['version'], dtype=np.int64)
        instance.due = [tuple(entry) for entry in data['due']]
        heapq.heapify(instance.due)
        instance.alive = data['alive']
        if kind == 'declared':
            instance.carried = instance.physical_rates(instance.value)
        if kind == 'moving':
            instance.time = data['time']
            signs = {(a, b): sign for a, b, sign in data['signs']}
            region = instance.region
            region.set(
                {
                    (a, b): signs[key]
                    for a, b in region.surfaces
                    if (key := (nodes.text(a), nodes.text(b))) in signs
                },
                dict(data['rows']),
            )
            instance.former.region = region
            instance.low, instance.high = (
                np.array(data['low'], dtype=bool),
                np.array(data['high'], dtype=bool),
            )
        return instance
    raise TypeError(f'no instance of a way of kind {kind}')
