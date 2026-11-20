"""The run, its reads and its triggers on chains of thousands of links (re-audit 15, `briefs/audit3.md` E).

The front end compiles a chain of 5,000 links with Python's recursion limit lowered to 400 (agent
F's rule test). The engine walks the dependency graph on one driver (`walk.walked`); these are the
paths that it may not cover, each on such a chain, with the limit at 400 while the plan is made, the
run goes and its record is read (the programs are made by the program's builder). Each runs at
1,500 links (keyed reads at 1,000), several frames a link far beyond the limit, and at 5,000
(`deep`):

- a named collection on every link (`kids = <the next node>`, `total = own + sum(this.kids.total)`)
  and named collections of the root and of an event over all the nodes, read by a formula, a stage,
  a trigger and the reader; a store at its end, whose first contact a trigger predicts through every
  link; and a chain of named collections, each a `where` of the one before, at the root and through
  the nodes;
- keyed reads on every link (`v = Node.instances.at(k - 1).v + 1`, a constant key over the natural
  keys), with a keyed read by a key that moves, read by stages, and a trigger on the last link;
- a declared solver's input read through a chain of formulas of known values, and a solver's
  constraint that reads the rate that it determines through a chain (`declared.py`); a rate read
  through a chain of known formulas, on arrays and on lines (`family.py`, `core/arrays.py`);
- a chain of connected sets, each of whose requests reads the actual rate of the set written after
  it, so that each settles after that one (`ways.Ways.build`, the levels of the sets);
- a rate that moves, read through a chain, on a component (the names that a formula reads,
  `component.Network.expanded_names`, and the proofs of `continuous/kernels.py`) and on the sparse
  integrator (its compile and each evaluation of its settings, `sparse.Vector`), the last at 1,000
  links, since each step of its solver evaluates the whole chain.

Each expected value is a closed form: the number of links, or the exponential decay of a tank that
drains at its water over 10 h, 10 e^(-t / 10 h) L.
"""

from __future__ import annotations

import math
import sys
from contextlib import contextmanager

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.plan import COMPONENT, DECLARED, FAMILY, LINES, SPARSE
from napkin.program.build import (
    SINK,
    Builder,
    after,
    assign,
    constraint,
    endpoint,
    event,
    flow,
    fmax,
    formula,
    fsum,
    given,
    group_of,
    input_,
    item,
    literal,
    local,
    maximize,
    named,
    q,
    reset_when,
    root,
    solve_for,
    solver,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
LIMIT = 400  # Python's recursion limit while the plan is made, the run goes and its record is read
DEPTHS = [1500, pytest.param(5000, marks=pytest.mark.deep)]


@contextmanager
def shallow(limit=LIMIT):
    """Python's recursion limit lowered to `limit` frames, so that any walk whose depth grows with a
    chain fails."""
    before = sys.getrecursionlimit()
    sys.setrecursionlimit(limit)
    try:
        yield
    finally:
        sys.setrecursionlimit(before)


def ran(program, horizon):
    """The record of a run and the run itself, made with the limit lowered."""
    with shallow():
        made = Run(Plan.of(program, Configuration(Request(horizon))))
        record = made.run()
    assert record.failure is None, record.failure.detail('message')
    return record, made


def values(record, program, paths, time):
    """The values of paths at a time, read with the limit lowered."""
    with shallow():
        found = read(record, program, paths, [time])
    return [reading.values[0] for reading in found]


@pytest.mark.parametrize('depth', DEPTHS)
def test_a_named_collection_on_every_link_is_read_by_formulas_a_stage_a_trigger_and_the_reader(depth):
    """n0 ... n{depth-1}, each with its own 1 L and the next node as its one kid: n0's total is
    `depth` L. The root's `nodes` and an event's `mine` name every node: their largest total is the
    same, read by a formula and by a stage at 1 h; a stage raises the last node's litre to 2 L at
    2 h, and a trigger on n0's total fires then."""
    b = Builder(UNITS)
    node = b.template(
        'Node',
        value('own', 'L', 1),
        value('kids', group_of('Node'), literal()),
        value('total', 'L', formula(this.own + fsum(this.kids.total))),
    )
    for k in range(depth):
        b.member(node, f'n{k}', **({'kids': literal(named(f'n{k + 1}'))} if k + 1 < depth else {}))
    b.root(
        value('nodes', group_of('Node'), node.instances),
        value('largest', 'L', formula(fmax(root.nodes.total))),
    )
    b.entity(
        'crew',
        value('seen', 'L', 0),
        value('rung', 'h', -1),
        event(
            'look',
            value('mine', group_of('Node'), node.instances),
            after(q(1, 'h'), assign(this.seen, fmax(local.mine.total))),
        ),
        event('bump', after(q(2, 'h'), assign(named(f'n{depth - 1}').own, q(2, 'L')))),
        event(
            'ring',
            when(named('n0').total > q(depth + 0.5, 'L'), start(this.ring), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.rung, t)),
        ),
    )
    b.setup(start(named('crew').look), start(named('crew').bump))
    program = b.finish()
    record, _ = ran(program, 3)
    found = values(record, program, ['n0.total', 'largest', 'crew.seen', 'crew.rung'], 3)
    assert found == [depth + 1, depth + 1, depth, 2]


@pytest.mark.parametrize('depth', DEPTHS)
def test_a_store_read_through_a_named_collection_on_every_link_has_its_contact_predicted(depth):
    """As above, but the last node's own litres are a tank that drains from 10 L at 1 L/h: n0's
    total is depth - 1 + 10 - t L, so a trigger on it at depth + 5 L fires at 4 h, found through
    every link's reduction between moments."""
    b = Builder(UNITS)
    node = b.template(
        'Node',
        value('base', 'L', 1),
        value('own', 'L', formula(this.base)),
        value('kids', group_of('Node'), literal()),
        value('total', 'L', formula(this.own + fsum(this.kids.total))),
    )
    for k in range(depth - 1):
        b.member(node, f'n{k}', kids=literal(named(f'n{k + 1}')))
    b.member(node, f'n{depth - 1}', own=formula(named('tank').water))
    b.entity('tank', value('water', 'L', 10, lower=0), flow('drain', this.water, SINK, request=q(1, 'L/h')))
    b.entity(
        'alarm',
        value('at', 'h', -1),
        event(
            'sound',
            when(named('n0').total <= q(depth + 5, 'L'), start(this.sound), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.at, t)),
        ),
    )
    program = b.finish()
    record, _ = ran(program, 6)
    assert values(record, program, ['alarm.at'], 6) == [pytest.approx(4, abs=1e-7)]


@pytest.mark.parametrize('depth', DEPTHS)
def test_a_chain_of_named_collections_resolves_to_its_members(depth):
    """c0 = Tank.instances, c_k = c_{k-1}.where(rank >= 1) at the root, and through the nodes, each
    node's `kids` the one before's narrowed again: a sum over the last of each is the sum over every
    tank, 1 + 2 + 3 L."""
    b = Builder(UNITS)
    tank = b.template('Tank', input_('rank', '', 1), value('water', 'L', 1))
    for k in range(3):
        b.member(tank, f't{k}', water=k + 1)
    chain = [value('c0', group_of('Tank'), tank.instances)]
    for k in range(1, depth):
        chain.append(value(f'c{k}', group_of('Tank'), getattr(root, f'c{k - 1}').where(item.rank >= 1)))
    b.root(*chain, value('total', 'L', formula(fsum(getattr(root, f'c{depth - 1}').water))))
    node = b.template('Node', value('kids', group_of('Tank'), tank.instances))
    b.member(node, 'n0')
    for k in range(1, depth):
        b.member(node, f'n{k}', kids=named(f'n{k - 1}').kids.where(item.rank >= 1))
    last = named(f'n{depth - 1}').kids.water
    b.entity('crew', value('seen', 'L', 0), event('look', after(q(1, 'h'), assign(this.seen, fsum(last)))))
    b.setup(start(named('crew').look))
    program = b.finish()
    record, _ = ran(program, 2)
    assert values(record, program, ['total', 'crew.seen'], 2) == [6, 6]


@pytest.mark.parametrize('depth', [1000, pytest.param(5000, marks=pytest.mark.deep)])
def test_keyed_reads_on_every_link_and_a_key_that_moves_are_read_by_stages_and_a_trigger(depth):
    """n_k.v = Node.instances.at(k - 1).v + 1 from n0.v = 1, so n_k.v = k + 1. A tank of depth - 0.5 L
    drains at 1 L/h, and `pick` reads the node at its water's key: at 0.5 h the key is depth - 1
    (depth), at 2.5 h depth - 3 (depth - 2). A trigger on the last node's value against a stored
    bar, which a stage lowers at 1 h, fires then."""
    b = Builder(UNITS)
    node = b.template('Node', value('one', '', 1), value('v', '', formula(this.one)))
    b.member(node, 'n0')
    for k in range(1, depth):
        b.member(node, f'n{k}', v=formula(node.instances.at(k - 1).v + 1))
    b.entity(
        'tank',
        value('water', 'L', depth - 0.5, lower=0),
        flow('drain', this.water, SINK, request=q(1, 'L/h')),
    )
    b.root(value('pick', '', formula(node.instances.at(named('tank').water / q(1, 'L')).v)))
    b.entity(
        'crew',
        value('early', '', 0),
        value('late', '', 0),
        value('bar', '', depth + 1),
        value('rung', 'h', -1),
        event(
            'look',
            after(q(0.5, 'h'), assign(this.early, root.pick)),
            after(q(2, 'h'), assign(this.late, root.pick)),
        ),
        event('lower', after(q(1, 'h'), assign(this.bar, depth))),
        event(
            'ring',
            when(named(f'n{depth - 1}').v >= this.bar, start(this.ring), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.rung, t)),
        ),
    )
    b.setup(start(named('crew').look), start(named('crew').lower))
    program = b.finish()
    record, _ = ran(program, 3)
    found = values(record, program, [f'n{depth - 1}.v', 'crew.early', 'crew.late', 'crew.rung'], 3)
    assert found == [depth, depth, depth - 2, 1]


def formula_chain(b, name, first, unit, depth):
    """y0 = first, y_k = y_{k-1} + 0 in `unit`, the values of an entity `name`: y_last is `first`."""
    chain = [value('y0', unit, formula(first))]
    chain += [value(f'y{k}', unit, formula(getattr(this, f'y{k - 1}') + q(0, unit))) for k in range(1, depth)]
    return b.entity(name, *chain)


@pytest.mark.parametrize('depth', DEPTHS)
def test_a_solver_reads_its_input_through_a_chain_of_known_values(depth):
    """A cap of 5 L/h read through the chain is a solver's input: of the 10 L/h asked, it serves 5."""
    b = Builder(UNITS)
    caps = formula_chain(b, 'caps', q(5, 'L/h'), 'L/h', depth)
    tank = b.entity('tank', value('water', 'L', 100, lower=0))
    use = b.entity('clinic', flow('use', tank.water, SINK, request=q(10, 'L/h')))
    b.entity(
        'provider',
        solver(
            'share',
            given('cap', getattr(caps, f'y{depth - 1}')),
            given('use', use.use),
            solve_for(local.use.actual_rate),
            constraint(local.use.actual_rate <= local.cap),
            maximize(local.use.actual_rate),
        ),
    )
    program = b.finish()
    record, made = ran(program, 1)
    assert {connected.way for connected, _ in made.ways.sets.values()} == {DECLARED}
    assert values(record, program, ['clinic.use.actual_rate'], 0.5) == [pytest.approx(5)]


@pytest.mark.parametrize('depth', DEPTHS)
def test_a_solver_reads_the_rate_that_it_determines_through_a_chain_of_formulas(depth):
    """The solver's constraint reads the rate that it determines through the chain: at most 3 L/h."""
    b = Builder(UNITS)
    tank = b.entity('tank', value('water', 'L', 100, lower=0))
    use = b.entity('clinic', flow('use', tank.water, SINK, request=q(10, 'L/h')))
    rates = formula_chain(b, 'rates', use.use.actual_rate, 'L/h', depth)
    b.entity(
        'provider',
        solver(
            'share',
            given('use', use.use),
            given('last', getattr(rates, f'y{depth - 1}')),
            solve_for(local.use.actual_rate),
            constraint(local.last <= q(3, 'L/h')),
            maximize(local.use.actual_rate),
        ),
    )
    program = b.finish()
    record, _ = ran(program, 1)
    assert values(record, program, ['clinic.use.actual_rate'], 0.5) == [pytest.approx(3)]


@pytest.mark.parametrize('depth', DEPTHS)
@pytest.mark.parametrize('way', [FAMILY, LINES])
def test_a_rate_read_through_a_chain_of_known_formulas_is_held_between_moments(way, depth):
    """A tank of 100 L drains at y, a chain from 2 L/h: on arrays, alone, it holds 90 L at 5 h; on
    lines, with a second drain of the same rate, 80 L."""
    b = Builder(UNITS)
    chain = formula_chain(b, 'reading', q(2, 'L/h'), 'L/h', depth)
    tank = b.entity('tank', value('water', 'L', 100, lower=0))
    drains = 2 if way == LINES else 1
    for k in range(drains):
        b.entity(
            f'valve{k}', flow('drain', tank.water, SINK, request=formula(getattr(chain, f'y{depth - 1}')))
        )
    program = b.finish()
    record, made = ran(program, 5)
    assert {connected.way for connected, _ in made.ways.sets.values()} == {way}
    assert values(record, program, ['tank.water'], 5) == [pytest.approx(100 - 10 * drains)]


@pytest.mark.parametrize('depth', DEPTHS)
def test_a_chain_of_sets_that_read_the_rate_of_the_set_after_settles_level_by_level(depth):
    """Tank k drains at the actual rate of the drain of tank k + 1, written after it, and the last at
    1 L/h: each drain carries 1 L/h, so each tank holds 10 - 5 L at 5 h, the first as the last. The
    sets are made in the order in which they are written, and each settles after the one that it
    reads, so the first waits on every other."""
    b = Builder(UNITS)
    for k in range(depth):
        rate = q(1, 'L/h') if k == depth - 1 else formula(named(f'tank{k + 1}').drain.actual_rate)
        b.entity(f'tank{k}', value('water', 'L', 10, lower=0), flow('drain', this.water, SINK, request=rate))
    program = b.finish()
    record, made = ran(program, 5)
    assert max(made.ways.levels.values()) == depth - 1
    assert values(record, program, ['tank0.water', f'tank{depth - 1}.water'], 5) == [5, 5]


@pytest.mark.parametrize(
    ('way', 'depth'),
    [
        (COMPONENT, 1500),
        (SPARSE, 1000),
        pytest.param(COMPONENT, 5000, marks=pytest.mark.deep),
        pytest.param(SPARSE, 5000, marks=pytest.mark.deep),
    ],
)
def test_a_rate_that_moves_through_a_chain_of_formulas_integrates_to_its_closed_form(way, depth):
    """A tank of 10 L drains at y / 10 h, y its water through the chain: 10 e^(-t / 10 h) L. With an
    endpoint setting on the tank, its set runs on the sparse integrator; without, on a component."""
    b = Builder(UNITS)
    settings = {'outflow': endpoint(capacity=q(100, 'L/h'))} if way == SPARSE else {}
    tank = b.entity('tank', value('water', 'L', 10, lower=0, **settings))
    chain = formula_chain(b, 'reading', tank.water, 'L', depth)
    request = formula(getattr(chain, f'y{depth - 1}') / q(10, 'h'))
    b.entity('valve', flow('drain', tank.water, SINK, request=request))
    program = b.finish()
    record, made = ran(program, 5)
    assert {connected.way for connected, _ in made.ways.sets.values()} == {way}
    assert values(record, program, ['tank.water'], 5) == [pytest.approx(10 * math.exp(-0.5), rel=1e-6)]
