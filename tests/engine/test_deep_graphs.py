"""Every evaluation over the dependency graph is iterative (re-audit 15, `briefs/audit2.md` part B).

A total read through 100 acyclic child links raised a RecursionError: each formula that a formula
read was evaluated one Python call deeper, in the present (`run.Run.value`), in the expansions of the
plan and in the walks of the conditions. One driver now walks the graph on an explicit stack
(`continuous/walk.walked`). The rule: for random acyclic graphs far deeper than Python's recursion
limit, with that limit lowered to 400 frames, the run gives each value its closed form, computed here
by evaluating the same graph in Python integers, in the order of its links:

- a random graph of formulas through links, a stage and an assertion over state reading its end;
- a chain of boolean formulas that a trigger, its near-ties and its prediction read;
- a store read through a chain of formulas, whose first contact a trigger predicts through it;
- a reduction over thousands of formulas, each read once (a sum, in one pass).

The reader of a record is not walked here (agent C makes it iterative): the run writes the values
that it reads into stored values, which a reader reads with no evaluation.
"""

from __future__ import annotations

import random
import sys
from contextlib import contextmanager

import pytest

from napkin.engine.timeline import read, run
from napkin.program.build import (
    BOOL,
    SINK,
    Builder,
    after,
    assertion,
    assign,
    event,
    flow,
    formula,
    fsum,
    literal,
    named,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, Request

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
DEPTH = 1500  # links in a chain: several Python frames each, when it recursed
LIMIT = 400  # Python's recursion limit while the run walks it


@contextmanager
def shallow(limit=LIMIT):
    """Python's recursion limit lowered to `limit` frames, so that any walk whose depth grows with a
    chain fails."""
    before = sys.getrecursionlimit()
    sys.setrecursionlimit(max(limit, 1))
    try:
        yield
    finally:
        sys.setrecursionlimit(before)


def at(record, program, path, time):
    (reading,) = read(record, program, [path], [time])
    return reading.values[0]


def chain(seed):
    """Nodes n0 ... n{DEPTH-1}, each an entity: n_k.v = n_{k-1}.v + s n_j.v + c for a random earlier
    j and small whole s and c (a graph with sharing, as deep as it is long). The closed form is the
    same sums in Python integers."""
    rng = random.Random(seed)
    b = Builder(UNITS)
    b.entity('base', value('v', '', 1))
    values = [1]
    b.entity('n0', value('v', '', formula(named('base').v + 0)))
    for k in range(1, DEPTH):
        j, s, c = rng.randrange(k), rng.choice([-1, 0, 1]), rng.randint(-3, 3)
        b.entity(f'n{k}', value('v', '', formula(named(f'n{k - 1}').v + s * named(f'n{j}').v + c)))
        values.append(values[-1] + s * values[j] + c)
    return b, values[-1]


@pytest.mark.parametrize('seed', range(3))
def test_a_deep_graph_of_formulas_through_links_is_read_by_a_stage_and_an_assertion(seed):
    b, expected = chain(seed)
    top = named(f'n{DEPTH - 1}').v
    b.entity(
        'crew',
        value('seen', '', 0),
        assertion(top >= expected - 1),
        event('look', after(q(1, 'h'), assign(this.seen, top))),
    )
    b.setup(start(named('crew').look))
    program = b.finish()
    with shallow():
        record = run(program, Configuration(Request(2)))
    assert record.failure is None, record.failure.detail('message')
    assert at(record, program, 'crew.seen', 2) == expected


def test_a_trigger_reads_a_deep_chain_of_boolean_formulas():
    """ok_k = ok_{k-1} and flag > 0: the trigger on the last fires when a stage sets the flag, at 2 h,
    and its condition, its near-ties and its prediction walk the whole chain."""
    b = Builder(UNITS)
    b.entity('gate', value('flag', '', 0), event('open', after(q(2, 'h'), assign(this.flag, 1))))
    b.entity('ok0', value('v', BOOL, formula(named('gate').flag > 0)))
    for k in range(1, DEPTH):
        b.entity(f'ok{k}', value('v', BOOL, formula(named(f'ok{k - 1}').v & (named('gate').flag > 0))))
    b.entity(
        'bell',
        value('rung', 'h', -1),
        event(
            'ring',
            when(named(f'ok{DEPTH - 1}').v, start(this.ring), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.rung, t)),
        ),
    )
    b.setup(start(named('gate').open))
    program = b.finish()
    with shallow():
        record = run(program, Configuration(Request(3)))
    assert record.failure is None, record.failure.detail('message')
    assert at(record, program, 'bell.rung', 3) == 2


def test_a_store_read_through_a_deep_chain_has_its_contact_predicted_through_it():
    """A tank of 10 L drains at 1 L/h; y_k = y_{k-1} + 0 L from y_0 = the water: a trigger on
    y_last <= 4 L fires when the tank holds 4 L, at 6 h, found through the chain."""
    b = Builder(UNITS)
    b.entity('tank', value('water', 'L', 10, lower=0), flow('drain', this.water, SINK, request=q(1, 'L/h')))
    b.entity('y0', value('v', 'L', formula(named('tank').water + q(0, 'L'))))
    for k in range(1, DEPTH):
        b.entity(f'y{k}', value('v', 'L', formula(named(f'y{k - 1}').v + q(0, 'L'))))
    b.entity(
        'alarm',
        value('at', 'h', -1),
        event(
            'sound',
            when(named(f'y{DEPTH - 1}').v <= q(4, 'L'), start(this.sound), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.at, t)),
        ),
    )
    program = b.finish()
    with shallow():
        record = run(program, Configuration(Request(8)))
    assert record.failure is None, record.failure.detail('message')
    assert at(record, program, 'alarm.at', 8) == pytest.approx(6, abs=1e-7)


def test_a_sum_over_thousands_of_formulas_reads_each_once():
    """sum of <m0 ... m2999>.w, each w = k + 1 a formula: 3000 * 3001 / 2, read by a stage, in one
    pass over the formulas (a sum asks for all of them at once)."""
    count = 3000
    b = Builder(UNITS)
    node = b.template('Node', value('k', '', 0), value('w', '', formula(this.k + 1)))
    for k in range(count):
        b.member(node, f'm{k}', k=k)
    b.entity(
        'crew',
        value('seen', '', 0),
        event(
            'look',
            after(q(1, 'h'), assign(this.seen, fsum(literal(*[named(f'm{k}') for k in range(count)]).w))),
        ),
    )
    b.setup(start(named('crew').look))
    program = b.finish()
    with shallow():
        record = run(program, Configuration(Request(2)))
    assert record.failure is None, record.failure.detail('message')
    assert at(record, program, 'crew.seen', 2) == count * (count + 1) // 2


@pytest.mark.parametrize('links', [100, 3000])
def test_a_total_through_acyclic_child_links_is_read_by_the_run(links):
    """Re-audit 15: total_k = this.child.total + 1 down a chain of links to a leaf of 1, read by a
    stage: links + 1."""
    b = Builder(UNITS)
    b.entity('leaf', value('total', '', 1))
    b.entity('c0', value('total', '', formula(named('leaf').total + 1)))
    for k in range(1, links):
        b.entity(f'c{k}', value('total', '', formula(named(f'c{k - 1}').total + 1)))
    b.entity(
        'crew',
        value('seen', '', 0),
        event('look', after(q(1, 'h'), assign(this.seen, named(f'c{links - 1}').total))),
    )
    b.setup(start(named('crew').look))
    program = b.finish()
    with shallow():
        record = run(program, Configuration(Request(2)))
    assert record.failure is None, record.failure.detail('message')
    assert at(record, program, 'crew.seen', 2) == links + 1
