"""Templates, tables and collections on the engine (`napkin/engine/timeline`): members as rows of a
pool, links, paths through links, `Template.instances`, literals, projections, the six reductions,
`where` on fixed fields, `by` and `.at(...)` with its key times, assertions over inputs and the order
of initializers across members.

Each expected value is worked by hand from the spec's rules ("Collections, keys and projections")
on small tanks that drain at constant rates: a line until the tank is empty. Where the oracle
(`tests/reference/from_program.py`) runs the program, the engine also agrees with it.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan
from napkin.engine.timeline.collections import Reduction
from napkin.program.build import (
    BOOL,
    SINK,
    Builder,
    TemplateHandle,
    assertion,
    count,
    fall,
    fany,
    flow,
    fmax,
    fmin,
    formula,
    fsum,
    group_of,
    input_,
    item,
    link,
    literal,
    named,
    q,
    t,
    this,
    value,
)
from napkin.program.canonical import program_bytes
from napkin.program.config import Configuration, InputValue, Request
from napkin.program.record import Key, Unavailable
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TANKS = (
    {'id': 'a', 'capacity': 10, 'critical': True},
    {'id': 'b', 'capacity': 4, 'critical': False},
    {'id': 'c', 'capacity': 6, 'critical': False},
)
TANK, PIPE = TemplateHandle('Tank'), TemplateHandle('Pipe')
PIPES = (
    {'id': 'ab', 'source': 'tanks.a', 'target': 'tanks.b', 'limit': 2},
    {'id': 'cb', 'source': 'tanks.c', 'target': 'tanks.b', 'limit': 3},
    {'id': 'ac', 'source': 'tanks.a', 'target': 'tanks.c', 'limit': 5},
)


def test_planning_a_sum_visits_its_members_once(monkeypatch):
    b = Builder(UNITS)
    sites = b.template('Site', input_('stock', 'L', 1), value('double', 'L', formula(2 * this.stock)))
    b.table('sites', sites, [{'id': f's{i}'} for i in range(80)])
    b.root(value('total', 'L', formula(fsum(sites.instances.double))))
    program = b.finish()
    plan = Plan.of(program, Configuration(Request(1)))
    visits = []
    original = Reduction.reads

    def reads(reduction):
        visits.append(reduction.name)
        return original(reduction)

    monkeypatch.setattr(Reduction, 'reads', reads)
    found = plan.expanded('total')
    assert found.leaves == {f'sites.s{i}.stock' for i in range(80)}
    assert found.formulas == {'total', *plan.reductions, *(f'sites.s{i}.double' for i in range(80))}
    assert visits == list(plan.reductions)
    assert at(run(program, Configuration(Request(1))), program, 'total', 0) == (160,)


def configured(horizon, **settings):
    return Configuration(Request(horizon), **settings)


def at(record, program, path, *times):
    (reading,) = read(record, program, [path], [float(time) for time in times])
    return reading.values


def same(found, expected):
    if isinstance(expected, bool):
        return found is expected
    return found == pytest.approx(float(expected), rel=1e-9, abs=1e-12)


def agrees_with_the_oracle(program, configuration, paths, times):
    """Each path at each time is the oracle's value."""
    record = run(program, configuration)
    oracle, failed = run_of(program, configuration)
    assert record.failure is None and failed is None
    for path in paths:
        key = path if isinstance(path, Key) else Key(*_split(program, path))
        for time in times:
            assert same(at(record, program, key, time)[0], value_at(oracle, program, key, Fraction(time))), (
                path,
                time,
            )


def _split(program, path):
    owner, _, name = path.rpartition('.')
    return owner, (name,)


def tanks(tank_rows=TANKS, pipe_rows=PIPES, *parts):
    """Three tanks, each half full and draining at 1 L/h (a at 5 h, b at 2 h, c at 3 h), and pipes
    that link two tanks each. A tank sums the limits of the pipes into it (the reverse index of
    `target`); a pipe reads the gap between its two tanks through its links; the root reduces the
    tanks."""
    b = Builder(UNITS)
    tank = b.template(
        'Tank',
        input_('capacity', 'L', 10),
        input_('critical', BOOL, False),
        value('water', 'L', this.capacity / 2, lower=0),
        value('empty', BOOL, formula(this.water <= q(0, 'L'))),
        flow('drain', this.water, SINK, request=q(1, 'L/h')),
        value('inflow_limit', 'L/h', formula(fsum(PIPE.instances.where(item.target == this).limit))),
    )
    pipe = b.template(
        'Pipe',
        link('source', 'Tank'),
        link('target', 'Tank'),
        input_('limit', 'L/h', 1),
        value('gap', 'L', formula(this.source.water - this.target.water)),
    )
    b.table('tanks', tank, tank_rows)
    b.table('pipes', pipe, pipe_rows)
    b.root(
        value('total', 'L', formula(fsum(tank.instances.water))),
        value('critical', '', count(tank.instances.where(item.critical))),
        value('wettest', 'L', formula(fmax(tank.instances.water))),
        value('driest', 'L', formula(fmin(tank.instances.water))),
        value('any_empty', BOOL, formula(fany(tank.instances.empty))),
        value('all_empty', BOOL, formula(fall(tank.instances.empty))),
        *parts,
    )
    return b.finish()


# ---- links, projections and reductions -------------------------------------------------------------


def test_links_projections_and_reductions_follow_the_members():
    program = tanks()
    record = run(program, configured(6))
    assert record.failure is None
    assert at(record, program, 'tanks.a.water', 1, 2.5, 4, 6) == pytest.approx([4, 2.5, 1, 0])
    assert at(record, program, 'total', 1, 2.5, 4, 6) == pytest.approx([7, 3, 1, 0])
    assert at(record, program, 'wettest', 1, 2.5) == pytest.approx([4, 2.5])
    assert at(record, program, 'driest', 1, 2.5) == pytest.approx([1, 0])
    assert at(record, program, 'any_empty', 1, 2.5) == (False, True)
    assert at(record, program, 'all_empty', 4, 5) == (False, True)
    assert at(record, program, 'critical', 0) == (1,)
    # Through the links: a - b, c - b and a - c at 1 h.
    assert [at(record, program, f'pipes.{pipe}.gap', 1)[0] for pipe in ('ab', 'cb', 'ac')] == pytest.approx(
        [3, 1, 2]
    )
    # The pipes into each tank, by the reverse index of `target`: none into a.
    limits = [at(record, program, f'tanks.{tank}.inflow_limit', 0)[0] for tank in 'abc']
    assert limits == pytest.approx([0, 5, 5])
    # The record names each row by its id, and keeps a link as the id of the member that it names.
    assert record.value(Key('pipes.cb', ('source',)), 0) == 'tanks.c'


def test_the_reductions_agree_with_the_oracle():
    agrees_with_the_oracle(
        tanks(),
        configured(6),
        ['total', 'wettest', 'driest', 'any_empty', 'all_empty', 'tanks.b.inflow_limit', 'pipes.ab.gap'],
        [0, 1, 2.5, 4, 6],
    )


def test_a_reordered_table_is_the_same_program_and_gives_the_same_named_results():
    first, second = tanks(), tanks(tuple(reversed(TANKS)), (PIPES[2], PIPES[0], PIPES[1]))
    assert program_bytes(first) == program_bytes(second)
    one, two = run(first, configured(6)), run(second, configured(6))
    assert {history.key: history.pieces for history in one.histories} == {
        history.key: history.pieces for history in two.histories
    }


def test_a_where_on_an_input_follows_the_configuration():
    program = tanks()
    given = (InputValue('tanks.b', 'critical', True), InputValue('tanks.c', 'critical', True))
    record = run(program, configured(1, inputs=given))
    assert at(record, program, 'critical', 0) == (3,)


def test_empty_reductions_have_their_meanings_and_min_and_max_fail_when_read():
    """No tank is above 100 L: the sum is 0 L, the count 0, any false and all true; min and max have
    no value (D4), and a rate that reads one fails the run at its start."""
    none = TANK.instances.where(item.capacity > q(100, 'L'))
    parts = (
        value('none_sum', 'L', formula(fsum(none.water))),
        value('none_count', '', formula(count(none))),
        value('none_any', BOOL, formula(fany(none.empty))),
        value('none_all', BOOL, formula(fall(none.empty))),
        value('none_least', 'L', formula(fmin(none.water))),
    )
    program = tanks(TANKS, PIPES, *parts)
    record = run(program, configured(1))
    assert at(record, program, 'none_sum', 0) == (0,)
    assert at(record, program, 'none_count', 0) == (0,)
    assert at(record, program, 'none_any', 0) == (False,)
    assert at(record, program, 'none_all', 0) == (True,)
    (least,) = at(record, program, 'none_least', 0)
    assert isinstance(least, Unavailable) and 'empty collection' in least.reason
    b = Builder(UNITS)
    tank = b.template('Tank', input_('capacity', 'L', 1), value('water', 'L', 5, lower=0))
    b.member(tank, 'one')
    b.entity(
        'outlet',
        value('spilled', 'L', 0),
        flow(
            'spill',
            named('one').water,
            SINK,
            request=formula(fmin(tank.instances.where(item.capacity > q(9, 'L')).water) / q(1, 'h')),
        ),
    )
    failed = run(b.finish(), configured(1))
    assert 'empty collection' in failed.failure.detail('message') and failed.failure.t == 0


# ---- keys and keyed reads ---------------------------------------------------------------------------


def readings_program(rows, *, moving=False):
    """Tanks x and y of 10 L drain at their pace times the factor of the reading at the time: x at
    1 L/h and y at 2 L/h, times 1 from 0 h, 0.5 from 2 h and 2 from 5 h. `moving` adds to each
    request a part that reads the tank (times zero): the rates then read a value that moves, and
    each tank runs as a component of the continuous engine."""
    b = Builder(UNITS)
    reading = b.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
    b.table('readings', reading, rows)
    factor = reading.instances.by('hour').at(t).factor
    request = this.pace * factor + (0 * this.water / q(1, 'h') if moving else q(0, 'L/h'))
    tank = b.template(
        'Tank',
        input_('pace', 'L/h', 1),
        value('water', 'L', 10, lower=0),
        flow('drain', this.water, SINK, request=formula(request)),
    )
    b.member(tank, 'x')
    b.member(tank, 'y', pace=q(2, 'L/h'))
    b.root(value('factor_now', '', formula(factor)))
    return b.finish()


READINGS = (
    {'id': 'r0', 'hour': 0, 'factor': 1},
    {'id': 'r1', 'hour': 2, 'factor': Fraction(1, 2)},
    {'id': 'r2', 'hour': 5, 'factor': 2},
)


@pytest.mark.parametrize('moving', [False, True])
def test_a_keyed_read_by_the_time_changes_the_rates_at_its_key_times(moving):
    """x: 10 - t to 8 L at 2 h, 8 - (t - 2) / 2 to 6.5 L at 5 h, then 2 L/h: empty at 8.25 h. y: 6 L
    at 2 h, 3 L at 5 h, then 4 L/h: empty at 5.75 h."""
    program = readings_program(READINGS, moving=moving)
    record = run(program, configured(9))
    assert record.failure is None
    assert at(record, program, 'x.water', 1, 2, 3.5, 5, 6, 8.25, 9) == pytest.approx(
        [9, 8, 7.25, 6.5, 4.5, 0, 0]
    )
    assert at(record, program, 'y.water', 1, 2, 3.5, 5, 5.75, 6) == pytest.approx(
        [8, 6, 4.5, 3, 0, 0], abs=1e-9
    )
    assert at(record, program, 'x.drain.actual_rate', 1, 3, 6, 9) == pytest.approx([1, 0.5, 2, 0])
    assert at(record, program, 'factor_now', 1.99, 2, 4.99, 5, 9) == pytest.approx([1, 0.5, 0.5, 2, 2])
    starts = [piece.t for piece in record.history(Key('x', ('water',))).pieces]
    assert any(abs(time - 2) < 1e-12 for time in starts) and any(abs(time - 5) < 1e-12 for time in starts)


def test_a_keyed_read_agrees_with_the_oracle():
    agrees_with_the_oracle(
        readings_program(READINGS),
        configured(9),
        ['x.water', 'y.water', 'factor_now', Key('x', ('drain', 'actual_rate'))],
        [0, 1, 2, 3.5, 5, 5.75, 7, 9],
    )


def test_of_equal_keys_the_member_created_later_is_read():
    rows = (
        {'id': 'r0', 'hour': 0, 'factor': 1},
        {'id': 'r1', 'hour': 2, 'factor': 3},
        {'id': 'r2', 'hour': 2, 'factor': 5},
    )
    program = readings_program(rows)
    assert at(run(program, configured(4)), program, 'factor_now', 1, 3) == pytest.approx([1, 5])


def test_a_keyed_read_below_its_first_key_has_no_value_and_a_rate_that_reads_it_fails():
    rows = ({'id': 'r0', 'hour': 1, 'factor': 1},)
    b = Builder(UNITS)
    reading = b.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
    b.table('readings', reading, rows)
    b.root(value('factor_now', '', formula(reading.instances.by('hour').at(t).factor)))
    program = b.finish()
    record = run(program, configured(2))
    (before, after) = at(record, program, 'factor_now', 0.5, 1)
    assert isinstance(before, Unavailable) and 'at(t)' in before.reason and after == 1
    failing = readings_program(rows)
    record = run(failing, configured(2))
    assert 'at(t)' in record.failure.detail('message') and record.failure.t == 0


# ---- literals, assertions, initializers -------------------------------------------------------------


def stations(primary, backup):
    b = Builder(UNITS)
    pump = b.template('Pump', input_('rate', 'L/h', 1), input_('running', BOOL, True))
    for name, rate in (('p1', 2), ('p2', 3), ('p3', 7)):
        b.member(pump, name, rate=q(rate, 'L/h'), running=name != 'p1')
    station = b.template(
        'Station',
        link('primary', 'Pump'),
        link('backup', 'Pump'),
        value('pumps', group_of('Pump'), literal(this.primary, this.backup)),
        value('total', 'L/h', formula(fsum(this.pumps.rate))),
        value('running', '', count(this.pumps.running)),
    )
    b.member(station, 's', primary=named(primary), backup=named(backup))
    return b.finish()


def test_a_literal_collection_reduces_its_members_and_names_each_once():
    program = stations('p3', 'p1')
    record = run(program, configured(1))
    assert at(record, program, 's.total', 0) == pytest.approx([9])
    assert at(record, program, 's.running', 0) == (1,)
    agrees_with_the_oracle(program, configured(1), ['s.total'], [0, 1])
    twice = run(stations('p2', 'p2'), configured(1))
    assert 'names p2 twice' in twice.failure.detail('message') and twice.failure.t == 0


def test_an_assertion_over_inputs_is_checked_once_at_the_start():
    holds = tanks(TANKS, PIPES, assertion(fsum(TANK.instances.capacity) <= q(30, 'L')))
    assert run(holds, configured(1)).failure is None
    b = Builder(UNITS)
    tank = b.template('Tank', input_('capacity', 'L', 10), assertion(this.capacity >= q(5, 'L')))
    b.table('tanks', tank, [{'id': row['id'], 'capacity': row['capacity']} for row in TANKS[:2]])
    record = run(b.finish(), configured(1))
    message = record.failure.detail('message')
    assert record.failure.t == 0 and 'Tank.assert[0]' in message and 'tanks.b' in message


def test_initializers_follow_their_dependencies_across_members_and_a_cycle_fails():
    """y is declared before x, and reads it. Each cell starts one above the cell before it, through
    a chain of links over 3,000 rows (no recursion follows it)."""
    b = Builder(UNITS)
    b.entity('first', value('y', 'L', named('second').x * 2))
    b.entity('second', value('x', 'L', 3))
    cell = b.template('Cell', link('previous', 'Cell'), value('n', '', this.previous.n + 1))
    rows = [{'id': f'c{k:04d}', 'previous': f'cells.c{max(k - 1, 0):04d}'} for k in range(3000)]
    rows[0]['n'] = 0
    b.table('cells', cell, rows)
    program = b.finish()
    record = run(program, configured(0))
    assert at(record, program, 'first.y', 0) == pytest.approx([6])
    assert at(record, program, 'cells.c2999.n', 0) == (2999,)
    b = Builder(UNITS)
    b.entity('first', value('y', 'L', named('second').x * 2))
    b.entity('second', value('x', 'L', named('first').y + q(1, 'L')))
    record = run(b.finish(), configured(0))
    assert 'reads itself' in record.failure.detail('message')


# ---- many rows on arrays ----------------------------------------------------------------------------


def test_a_large_table_of_like_rows_runs_on_arrays_to_its_closed_forms():
    """2,000 tanks of k L for k = 1 ... 2,000 drain at 1 L/h: tank k is empty at k h, so at t h the
    total is the sum of (k - t) over k > t."""
    b = Builder(UNITS)
    tank = b.template(
        'Tank', value('water', 'L', 1, lower=0), flow('drain', this.water, SINK, request=q(1, 'L/h'))
    )
    b.table('tanks', tank, [{'id': f't{k:04d}', 'water': k} for k in range(1, 2001)])
    b.root(value('total', 'L', formula(fsum(tank.instances.water))))
    program = b.finish()
    record = run(program, configured(1500.5))
    for time in (0, 10.5, 999, 1500.5):
        expected = sum(k - time for k in range(1, 2001) if k > time)
        assert at(record, program, 'total', time) == pytest.approx([expected], rel=1e-12)
    assert at(record, program, 'tanks.t0700.water', 699.5, 700, 1000) == pytest.approx([0.5, 0, 0], abs=1e-9)


# ---- flows across templates --------------------------------------------------------------------------


def test_a_flow_between_members_of_two_templates_runs():
    b = Builder(UNITS)
    b.template('Basin', value('level', 'L', 0, lower=0))
    b.member('Basin', 'basin')
    pump = b.template(
        'Pump',
        link('into', 'Basin'),
        value('store', 'L', 5, lower=0),
        flow('push', this.store, this.into.level, request=q(1, 'L/h')),
    )
    b.member(pump, 'pump', into=named('basin'))
    program = b.finish()
    record = run(program, configured(1))
    assert at(record, program, 'pump.store', 1) == pytest.approx([4])
    assert at(record, program, 'basin.level', 1) == pytest.approx([1])


def test_a_rate_that_reads_a_reduction_of_moving_stores_joins_them_in_one_component():
    """Tanks a (6 L) and b (2 L) each drain at a tenth of their total an hour: the total S falls as
    S' = -S / 5, so S = 8 exp(-t / 5), and each tank loses half of what the total lost:
    a = 6 - (8 - S) / 2 and b = 2 - (8 - S) / 2, until b is empty at S = 4 L, t = 5 ln 2. After that
    a alone drains at its total over 10 h: a = 4 exp(-(t - 5 ln 2) / 10)."""
    b = Builder(UNITS)
    tank = b.template(
        'Tank',
        value('water', 'L', 1, lower=0),
        flow('out', this.water, SINK, request=formula(fsum(TANK.instances.water) / q(10, 'h'))),
    )
    b.member(tank, 'a', water=q(6, 'L'))
    b.member(tank, 'b', water=q(2, 'L'))
    program = b.finish()
    record = run(program, configured(8))
    assert record.failure is None
    empty = 5 * math.log(2)
    for time in (1.0, 3.0):
        total = 8 * math.exp(-time / 5)
        assert at(record, program, 'a.water', time) == pytest.approx([6 - (8 - total) / 2], rel=1e-8)
        assert at(record, program, 'b.water', time) == pytest.approx([2 - (8 - total) / 2], rel=1e-8)
    assert at(record, program, 'b.water', 4.0, 8) == pytest.approx([0, 0], abs=1e-8)
    assert at(record, program, 'a.water', 7.5) == pytest.approx([4 * math.exp(-(7.5 - empty) / 10)], rel=1e-8)
