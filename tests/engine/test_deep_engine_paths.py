"""The run, its reads and its triggers on a chain of 5,000 links (re-audit 15, `briefs/audit3.md` E).

The front end compiles a chain of 5,000 links with Python's recursion limit lowered to 400 (agent
F's rule test). The engine walks the dependency graph on one driver (`plan.walked`); these are the
paths that it may not cover, each on such a chain, with the limit at 400 while the run and its
reads go (the programs are made by the program's builder, as the front end gives them):

- a named collection on every link (`kids = <the next node>`, `total = own + sum(this.kids.total)`)
  and named collections of the root and of an event over all the nodes, read by a formula, a stage,
  a trigger and the reader;
- keyed reads on every link (`v = Node.instances.at(k - 1).v + 1`, a constant key over the natural
  keys), and a keyed read by a key that moves, at the end of a chain;
- a trigger's condition, its near-ties and its prediction through each;
- a declared solver's inputs and constraints through a chain of formulas, of known values and of
  the rate that it determines;
- rates that move, read through a chain of formulas, on the continuous engine's component and on
  the sparse integrator: a tank drains at y / 10 h where y is its water read through the chain, so
  it holds 10 e^(-t / 10 h) L.

Each expected value is a closed form: the number of links, or the exponential decay.
"""

from __future__ import annotations

import math
import sys
from contextlib import contextmanager

import pytest

from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.plan import COMPONENT, DECLARED, SPARSE
from napkin.program.build import (
    BOOL,
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
    literal,
    local,
    maximize,
    named,
    q,
    root,
    reset_when,
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
DEPTH = 5000  # links in each chain
LIMIT = 400  # Python's recursion limit while the run and its reads go


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
    """The record of a run and the run itself, made and read with the limit lowered."""
    with shallow():
        made = Run(Plan.of(program, Configuration(Request(horizon))))
        record = made.run()
    assert record.failure is None, record.failure.detail('message')
    return record, made


def values(record, program, paths, time):
    with shallow():
        found = read(record, program, paths, [time])
    return [reading.values[0] for reading in found]


def test_a_named_collection_on_every_link_is_read_by_formulas_a_stage_a_trigger_and_the_reader():
    """n0 ... n4999, each with its own 1 L and the next node as its one kid: n0's total is 5,000 L.
    The root's `nodes` and an event's `mine` name every node: their largest total is the same, read
    by a formula and by a stage at 1 h; a trigger on n0's total and a stored litre of the last node,
    which a stage raises at 2 h, fires then."""
    b = Builder(UNITS)
    node = b.template(
        'Node',
        value('own', 'L', 1),
        value('kids', group_of('Node'), literal()),
        value('total', 'L', formula(this.own + fsum(this.kids.total))),
    )
    for k in range(DEPTH):
        kids = {'kids': literal(named(f'n{k + 1}'))} if k + 1 < DEPTH else {}
        b.member(node, f'n{k}', **kids)
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
        event('bump', after(q(2, 'h'), assign(named(f'n{DEPTH - 1}').own, q(2, 'L')))),
        event(
            'ring',
            when(named('n0').total > q(DEPTH + 0.5, 'L'), start(this.ring), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.rung, t)),
        ),
    )
    b.setup(start(named('crew').look), start(named('crew').bump))
    program = b.finish()
    record, _ = ran(program, 3)
    found = values(record, program, ['n0.total', 'largest', 'crew.seen', 'crew.rung'], 3)
    assert found == [DEPTH + 1, DEPTH + 1, DEPTH, 2]


def keyed_chain(b):
    """n0 ... n4999 of a template whose value reads the node before it by a constant key over the
    natural keys: n_k.v = Node.instances.at(k - 1).v + 1 from n0.v = 1, so n_k.v = k + 1."""
    node = b.template('Node', value('one', '', 1), value('v', '', formula(this.one)))
    b.member(node, 'n0')
    for k in range(1, DEPTH):
        b.member(node, f'n{k}', v=formula(node.instances.at(k - 1).v + 1))
    return node


def test_keyed_reads_on_every_link_and_a_key_that_moves_are_read_by_a_stage_and_a_trigger():
    """The keyed chain; a tank of 4,999.5 L drains at 1 L/h, and `pick` reads the node at its
    water's key: at 0.5 h the key is 4,999 (5,000), at 2.5 h 4,997 (4,998). A trigger on the last
    node's value against a stored bar, which a stage lowers at 1 h, fires then."""
    b = Builder(UNITS)
    node = keyed_chain(b)
    b.entity(
        'tank',
        value('water', 'L', DEPTH - 0.5, lower=0),
        flow('drain', this.water, SINK, request=q(1, 'L/h')),
    )
    b.root(value('pick', '', formula(node.instances.at(named('tank').water / q(1, 'L')).v)))
    b.entity(
        'crew',
        value('early', '', 0),
        value('late', '', 0),
        value('bar', '', DEPTH + 1),
        value('rung', 'h', -1),
        event('look', after(q(0.5, 'h'), assign(this.early, root.pick)), after(q(2, 'h'), assign(this.late, root.pick))),
        event('lower', after(q(1, 'h'), assign(this.bar, DEPTH))),
        event(
            'ring',
            when(named(f'n{DEPTH - 1}').v >= this.bar, start(this.ring), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.rung, t)),
        ),
    )
    b.setup(start(named('crew').look), start(named('crew').lower))
    program = b.finish()
    record, _ = ran(program, 3)
    found = values(record, program, [f'n{DEPTH - 1}.v', 'crew.early', 'crew.late', 'crew.rung'], 3)
    assert found == [DEPTH, DEPTH, DEPTH - 2, 1]


def formula_chain(b, name, first, unit):
    """y0 = first, y_k = y_{k-1} + 0 in `unit`, members of an entity `name`: y_last is `first`."""
    chain = [value('y0', unit, formula(first))]
    chain += [value(f'y{k}', unit, formula(getattr(this, f'y{k - 1}') + q(0, unit))) for k in range(1, DEPTH)]
    return b.entity(name, *chain)


def test_a_solver_reads_its_input_through_a_chain_of_known_values():
    """A cap of 5 L/h read through the chain is a solver's input: of the 10 L/h asked, it serves 5."""
    b = Builder(UNITS)
    caps = formula_chain(b, 'caps', q(5, 'L/h'), 'L/h')
    tank = b.entity('tank', value('water', 'L', 100, lower=0))
    use = b.entity('clinic', flow('use', tank.water, SINK, request=q(10, 'L/h')))
    b.entity(
        'provider',
        solver(
            'share',
            given('cap', getattr(caps, f'y{DEPTH - 1}')),
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


def test_a_solver_reads_the_rate_that_it_determines_through_a_chain_of_formulas():
    """The solver's constraint reads the rate that it determines through the chain: at most 3 L/h."""
    b = Builder(UNITS)
    tank = b.entity('tank', value('water', 'L', 100, lower=0))
    use = b.entity('clinic', flow('use', tank.water, SINK, request=q(10, 'L/h')))
    rates = formula_chain(b, 'rates', use.use.actual_rate, 'L/h')
    b.entity(
        'provider',
        solver(
            'share',
            given('use', use.use),
            given('last', getattr(rates, f'y{DEPTH - 1}')),
            solve_for(local.use.actual_rate),
            constraint(local.last <= q(3, 'L/h')),
            maximize(local.use.actual_rate),
        ),
    )
    program = b.finish()
    record, _ = ran(program, 1)
    assert values(record, program, ['clinic.use.actual_rate'], 0.5) == [pytest.approx(3)]


@pytest.mark.parametrize('way', [COMPONENT, SPARSE])
def test_a_rate_that_moves_through_a_chain_of_formulas_integrates_to_its_closed_form(way):
    """A tank of 10 L drains at y / 10 h, y its water through the chain: 10 e^(-t / 10 h) L. With an
    endpoint setting on the tank, its set runs on the sparse integrator; without, on a component."""
    b = Builder(UNITS)
    settings = {'outflow': endpoint(capacity=q(100, 'L/h'))} if way == SPARSE else {}
    tank = b.entity('tank', value('water', 'L', 10, lower=0, **settings))
    chain = formula_chain(b, 'reading', tank.water, 'L')
    b.entity('valve', flow('drain', tank.water, SINK, request=formula(getattr(chain, f'y{DEPTH - 1}') / q(10, 'h'))))
    program = b.finish()
    record, made = ran(program, 5)
    assert {connected.way for connected, _ in made.ways.sets.values()} == {way}
    assert values(record, program, ['tank.water'], 5) == [pytest.approx(10 * math.exp(-0.5), rel=1e-6)]


def test_a_chain_of_named_collections_resolves_to_its_members():
    """c0 = Tank.instances, c_k = c_{k-1}.where(rank >= 1) at the root, and through the links of the
    nodes (each node's `kids` narrows its next node's): a sum over the last of each is the sum over
    every tank, 1 + 2 + 3 L."""
    b = Builder(UNITS)
    tank = b.template('Tank', input_('rank', '', 1), value('water', 'L', 1))
    for k in range(3):
        b.member(tank, f't{k}', water=k + 1)
    chain = [value('c0', group_of('Tank'), tank.instances)]
    for k in range(1, DEPTH):
        chain.append(value(f'c{k}', group_of('Tank'), getattr(root, f'c{k - 1}').where(local_rank() >= 1)))
    b.root(*chain, value('total', 'L', formula(fsum(getattr(root, f'c{DEPTH - 1}').water))))
    node = b.template('Node', value('kids', group_of('Tank'), tank.instances))
    b.member(node, 'n0')
    for k in range(1, DEPTH):
        b.member(node, f'n{k}', kids=named(f'n{k - 1}').kids.where(local_rank() >= 1))
    b.entity('crew', value('seen', 'L', 0), event('look', after(q(1, 'h'), assign(this.seen, fsum(named(f'n{DEPTH - 1}').kids.water)))))
    b.setup(start(named('crew').look))
    program = b.finish()
    record, _ = ran(program, 2)
    assert values(record, program, ['total', 'crew.seen'], 2) == [6, 6]


def local_rank():
    """`rank` of the member that a where tests."""
    from napkin.program.build import item

    return item.rank
