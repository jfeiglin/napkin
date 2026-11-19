"""Room passed upstream through full stores, by local sharing (spec, "When a solver is required": the
engine enforces the rules "even when an empty store, a full store or connected capacities make
several rates interdependent").

A full store takes in only the room that its outflows make. Room is settled against the direction of
flow: the claims into a full store wait for those into the full stores that its outflows fill, as the
claims out of an empty store wait for its supply (`napkin/engine/timeline/network.py`). The expected
numbers are worked by hand in each docstring, and each run agrees with the oracle
(`tests/reference/`) in exact fractions.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.program.build import SINK, SOURCE, Builder, flow, named, q, this, value
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def full(name, b, *flows):
    """A member whose tank of 10 L is full, with its flows."""
    return b.entity(name, value('water', 'L', 10, lower=0, upper=10), *flows)


def rates(program, names, horizon=2, times=(0, 0.5, 1.5)):
    """The values at `times` of `names` (`member.flow.actual_rate` or `member.water`), each checked
    against the oracle at the same times."""
    configuration = Configuration(Request(horizon))
    record = run(program, configuration)
    assert record.failure is None, record.failure
    oracle, failed = run_of(program, configuration)
    assert failed is None
    found = {}
    for name in names:
        owner, *steps = name.split('.')
        key = Key(owner, tuple(steps))
        found[name] = read(record, program, [key], [float(t) for t in times])[0].values
        for t, number in zip(times, found[name]):
            assert number == pytest.approx(float(value_at(oracle, program, key, Fraction(t))), abs=1e-12)
    return found


def test_two_full_tanks_in_series_pass_a_transfer_through_both():
    """1 L/h fills the upper tank, which passes 1 L/h to the lower, which drains 1 L/h; both are full.
    The drain makes room in the lower tank, the pipe takes it and makes room in the upper one, and
    the fill takes that: each request is served, and both tanks stay full."""
    b = Builder(UNITS)
    down = full('down', b, flow('drain', this.water, SINK, request=q(1, 'L/h')))
    full(
        'up',
        b,
        flow('fill', SOURCE, this.water, request=q(1, 'L/h')),
        flow('pass_on', this.water, down.water, request=q(1, 'L/h')),
    )
    names = ['up.fill.actual_rate', 'up.pass_on.actual_rate', 'down.drain.actual_rate']
    found = rates(b.finish(), [*names, 'up.water', 'down.water'])
    for name in names:
        assert found[name] == (1, 1, 1)
    assert found['up.water'] == found['down.water'] == (10, 10, 10)


def test_room_passed_upstream_through_two_full_tanks_is_shared_locally():
    """The mirror of the spec's two junctions: a full tank whose drain can take 1 L/h is filled from A
    and by a pipe from a second full tank, which B and C fill; each asks 1 L/h. The first tank shares
    its room of 1 L/h between A and the pipe, 1/2 each, and the second shares the 1/2 that the pipe
    takes between B and C, 1/4 each (one level for all claims would give A, B and C 1/3 each)."""
    b = Builder(UNITS)
    first = full(
        'first',
        b,
        flow('drain', this.water, SINK, capacity=q(1, 'L/h')),
        flow('from_a', SOURCE, this.water, request=q(1, 'L/h')),
    )
    full(
        'second',
        b,
        flow('onward', this.water, first.water, request=q(1, 'L/h')),
        flow('from_b', SOURCE, this.water, request=q(1, 'L/h')),
        flow('from_c', SOURCE, this.water, request=q(1, 'L/h')),
    )
    expected = {'first.drain': 1, 'first.from_a': 0.5, 'second.onward': 0.5, 'second.from_b': 0.25}
    expected['second.from_c'] = 0.25
    found = rates(b.finish(), [f'{name}.actual_rate' for name in expected])
    for name, rate in expected.items():
        assert found[f'{name}.actual_rate'] == (rate,) * 3


def test_a_pipe_between_two_full_tanks_that_nothing_drains_carries_nothing():
    """A set of one flow (the family): the lower tank is full and nothing drains it, so the pipe,
    which asks 1 L/h, delivers nothing, and the run goes on."""
    b = Builder(UNITS)
    low = full('low', b)
    full('high', b, flow('pass_on', this.water, low.water, request=q(1, 'L/h')))
    found = rates(b.finish(), ['high.pass_on.actual_rate', 'high.water'])
    assert found['high.pass_on.actual_rate'] == (0, 0, 0)
    assert found['high.water'] == (10, 10, 10)


def test_a_ring_of_full_tanks_stops_the_run_by_name():
    """Two full tanks that fill each other pass room around, and a ring has no first tank: local
    sharing has no answer, which the oracle does not cover either."""
    b = Builder(UNITS)
    full('x', b, flow('there', this.water, named('y').water, request=q(1, 'L/h')))
    full('y', b, flow('back', this.water, named('x').water, request=q(1, 'L/h')))
    program = b.finish()
    configuration = Configuration(Request(1))
    with pytest.raises(NotCovered):
        run_of(program, configuration)
    record = run(program, configuration)
    assert record.failure.t == 0
    message = record.failure.detail('message')
    assert 'a ring of stores at their upper bound passes room around' in message
    assert 'x.water' in message and 'y.water' in message
