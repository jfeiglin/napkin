"""The record, its reader, the report's lag and its never-falls proof, and the evidence trail on
chains of thousands of links (the readiness audit of `8b3a01a`, row 15; `briefs/audit3.md` R).

With Python's recursion limit lowered to 400 while the run makes its record and the report reads it,
on each form of a chain that a model can write (the programs are made by the program's builder):
formulas of the top level, each the one before plus nothing; formulas of an entity, the same, and
each the greater of the one before and nothing (which no linear form writes, so the proof goes by its
parts); a total through child links, each node its own litre and its child's total; and inputs whose
defaults each read the one before, which a stage adds to a tally. Each at 1,500 links, several frames
a link far beyond the limit, and at 5,000 (`deep`), of every value and of the chain's end alone.

The expected values are closed forms: a tank that fills at 1 L/h holds t L, so the chain's end reads
2 L at 2 h, and its lag from 0.5 h to 1 h there is the mean of t over [1 h, 1.5 h], 1.25 L; the total of
n nodes is n L, at every time; the tally holds 1 L from 1 h. Each never falls: the fill only adds to
what the chain counts, nothing changes the nodes' litres, and the stage adds a fixed litre.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager

import pytest

from napkin.engine.report import Lag, report
from napkin.engine.timeline import Plan, Run, read
from napkin.program.build import (
    SOURCE,
    Builder,
    add,
    after,
    event,
    flow,
    fmax,
    formula,
    fsum,
    group_of,
    input_,
    literal,
    named,
    q,
    root,
    start,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
LIMIT = 400  # Python's recursion limit while the run makes its record and a report reads it
DEPTHS = [1500, pytest.param(5000, marks=pytest.mark.deep)]
LAG = Lag(0.5, 1)


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


def top_level(n):
    """`v0 = tank.water`, then `v{k} = v{k-1} + 0 L` at the top level; the end is `v{n-1}`."""
    b = Builder(UNITS)
    b.entity('tank', value('water', 'L', 0, lower=0), flow('fill', SOURCE, this.water, request=q(1, 'L/h')))
    b.root(
        value('v0', 'L', formula(named('tank').water + q(0, 'L'))),
        *(value(f'v{k}', 'L', formula(getattr(root, f'v{k - 1}') + q(0, 'L'))) for k in range(1, n)),
    )
    return b.finish(), Key('', (f'v{n - 1}',))


def entity(n, greatest=False):
    """The same chain in an entity, each link the one before plus nothing, or the greater of the one
    before and nothing."""
    b = Builder(UNITS)

    def link(before):
        return fmax(before, q(0, 'L')) if greatest else before + q(0, 'L')

    b.entity(
        'chain',
        value('water', 'L', 0, lower=0),
        flow('fill', SOURCE, this.water, request=q(1, 'L/h')),
        value('v0', 'L', formula(this.water + q(0, 'L'))),
        *(value(f'v{k}', 'L', formula(link(getattr(this, f'v{k - 1}')))) for k in range(1, n)),
    )
    return b.finish(), Key('chain', (f'v{n - 1}',))


def children(n):
    """Nodes that each add their own litre to the totals of their children, each but the last with
    the next as its one child; the end is the first node's total."""
    b = Builder(UNITS)
    node = b.template(
        'Node',
        value('own', 'L', 1),
        value('kids', group_of('Node'), literal()),
        value('total', 'L', formula(this.own + fsum(this.kids.total))),
    )
    for k in range(n):
        b.member(node, f'n{k:05d}', **({'kids': literal(named(f'n{k + 1:05d}'))} if k + 1 < n else {}))
    return b.finish(), Key('n00000', ('total',))


def inputs(n):
    """Inputs whose defaults each read the one before (the first 1 L), and a stage at 1 h that adds the
    last to a tally; the end is the tally."""
    b = Builder(UNITS)
    b.entity(
        'm',
        input_('i0', 'L', 1),
        *(input_(f'i{k}', 'L', getattr(this, f'i{k - 1}') + q(0, 'L')) for k in range(1, n)),
        value('tally', 'L', 0, lower=0),
        event('tick', after(q(1, 'h'), add(this.tally, getattr(this, f'i{n - 1}')))),
    )
    b.setup(start(named('m').tick))
    return b.finish(), Key('m', ('tally',))


FILLED = ('top level', 'entity', 'greatest')  # the forms whose chain reads a tank that a flow fills

# Each form: its program and the key of its end, and the end's value at 2 h and its lag there.
FORMS = {
    'top level': (top_level, 2, 1.25),
    'entity': (entity, 2, 1.25),
    'greatest': (lambda n: entity(n, greatest=True), 2, 1.25),
    'children': (children, None, None),  # n L, at every time
    'inputs': (inputs, 1, 1),
}


@pytest.mark.parametrize('narrow', [False, True], ids=['everything', 'the end'])
@pytest.mark.parametrize('form', sorted(FORMS))
@pytest.mark.parametrize('n', DEPTHS)
def test_a_chain_is_recorded_read_lagged_and_traced_without_recursion(n, form, narrow):
    made, value_at, lagged = FORMS[form]
    program, end = made(n)
    if value_at is None:
        value_at = lagged = n
    path = str(end)
    request = Request(2, everything=not narrow, keys=(end,) if narrow else ())
    configuration = Configuration(request)
    with shallow():
        record = Run(Plan.of(program, configuration)).run()
        assert record.failure is None, record.failure
        assert read(record, program, [path], [2])[0].values == (pytest.approx(value_at),)
        (plain,) = report(record, program, configuration, [path], [2]).values
        (delayed,) = report(record, program, configuration, [path], [2], {path: LAG}).values
    assert plain.values == (pytest.approx(value_at),) and plain.lag is None
    assert delayed.lag == LAG and delayed.values == (pytest.approx(lagged),), delayed.note
    # The trail reaches the chain to its start, and each part of it acted: every link was read, the
    # tank's fill moved water, the stage that adds to the tally committed. A record of the end alone
    # does not hold the fill's rate, so of the fill the trail says neither (`report._Trail.moved`).
    assert len(plain.trail) >= n
    unsure = [used.origin for used in plain.trail if used.exercised is None]
    assert unsure == (
        ['tank.fill' if form == 'top level' else 'chain.fill'] if narrow and form in FILLED else []
    )
    assert [used.origin for used in plain.trail if used.exercised is False] == []
