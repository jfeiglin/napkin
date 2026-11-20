"""Declared solvers on the engine (spec: "Solver and execution contract"; G0, D5).

Two writes in one round cause one solve, and a trigger that reacts to the result causes a second
round with a second solve at the same time. All stages in a round read the last solve's results,
directly or through formulas. The next round reads the results published after those stages
(PLAN, change 27). A solve that cannot answer stops the run
there, naming the solver and the step, before a trigger reads a partial answer. Flows of occurrences
that join and leave a solver's store join and leave its problem, on the solver that the run keeps,
and a store held at both bounds is one equality of it. A problem whose requests follow its tanks is
solved at trial states between moments, and one beyond the limit of such a set stops by name; two
solvers in one calculation, and a relation outside the constraint language, fail by name.

A solver decides only the rates that it names (the owner's rule after G2): a flow of its calculation
that it does not name keeps its endpoints' local sharing, and a relation on such a flow is refused by
name. A store that the answer moves off its bound is released at once and the problem solved again.
The polish of an answer is relative to each unknown's own size: a small requested delivery survives
it, and an idle pipe with a small capacity stays idle.

The expected numbers are worked by hand from the rules of the spec: the staffing solver of
"Allocating staff hours" gives care 70% of the staff hours (outreach at its minimum, 30%), and fair
sharing of one supply of 3 L/h among requests of 2 L/h serves each in full or both at 1.5 L/h; tanks
that fill at their headroom per hour follow 10 L - c e^-t once their requests are met.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan
from napkin.engine.timeline.run import Run
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    constraint,
    endpoint,
    event,
    flow,
    fmin,
    formula,
    given,
    local,
    maximize,
    named,
    priority,
    q,
    reset_when,
    solve_for,
    solver,
    start,
    subtract,
    t,
    this,
    unknown,
    value,
    when,
)
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def staffing():
    """The solver of "Allocating staff hours": care + outreach == available, outreach at least its
    live minimum of 30%, maximize care."""
    return solver(
        'staffing',
        given('available', this.staff_hours),
        given('minimum_outreach', this.outreach_minimum),
        unknown('care', 'h', lower=q(0, 'h'), upper=local.available),
        unknown('outreach', 'h', lower=local.minimum_outreach, upper=local.available),
        constraint(local.care + local.outreach == local.available),
        maximize(local.care),
    )


def office(*parts, setup=(), horizon=2):
    """An office of 100 staff hours with the staffing solver and the parts given; its record."""
    b = Builder(UNITS)
    made = b.entity(
        'office',
        value('staff_hours', 'h', 100),
        value('outreach_minimum', 'h', formula(0.30 * this.staff_hours)),
        value('note', 'h', 0),
        value('twice_care', 'h', formula(2 * this.staffing.care)),
        staffing(),
        *parts,
    )
    b.setup(*[start(getattr(made, name)) for name in setup])
    program = b.finish()
    return program, run(program, Configuration(Request(horizon)))


def values(record, program, path, times):
    return read(record, program, [path], [float(time) for time in times])[0].values


def solves(record):
    return [(entry.t, entry.round) for entry in record.entries('solve', 'office.staffing')]


def test_two_writes_in_one_round_cause_one_solve():
    program, record = office(
        event('lower', after(q(1, 'h'), assign(this.staff_hours, q(90, 'h')))),
        event('trim', after(q(1, 'h'), subtract(this.staff_hours, q(10, 'h')))),
        setup=('lower', 'trim'),
    )
    assert record.failure is None
    assert solves(record) == [(0, 0), (1, 1)]
    assert values(record, program, 'office.staffing.care', (0, 1, 2)) == pytest.approx((70, 56, 56))
    assert values(record, program, 'office.staffing.outreach', (1,)) == pytest.approx((24,))


def test_a_trigger_on_the_result_makes_a_second_round_with_a_second_solve():
    """The cut to 80 h gives care 56 h; a trigger on `care <= 60 h` adds 20 h in the next round of
    the same time, which solves again: 70 h."""
    program, record = office(
        event('cut', after(q(1, 'h'), assign(this.staff_hours, q(80, 'h')))),
        event(
            'restore',
            when(this.staffing.care <= q(60, 'h'), start(this.restore), reset=reset_when(False)),
            after(q(0, 'h'), add(this.staff_hours, q(20, 'h'))),
        ),
        setup=('cut',),
    )
    assert record.failure is None
    assert solves(record) == [(0, 0), (1, 1), (1, 2)]
    assert [(entry.t, entry.round) for entry in record.entries('fire', 'office.restore.when[0]')] == [(1, 1)]
    assert values(record, program, 'office.staffing.care', (1, 2)) == pytest.approx((70, 70))


def test_a_write_that_leaves_the_inputs_as_they_were_solves_nothing():
    _, record = office(
        event('same', after(q(1, 'h'), assign(this.staff_hours, q(100, 'h')))), setup=('same',)
    )
    assert record.failure is None and solves(record) == [(0, 0)]


@pytest.mark.parametrize(
    ('expression', 'expected'),
    [(this.staffing.care, 70), (this.twice_care, 140)],
    ids=['direct', 'through a formula'],
)
def test_a_stage_reads_the_last_solve_after_it_changes_an_input(expression, expected):
    program, record = office(
        event('cut', after(q(1, 'h'), assign(this.staff_hours, q(80, 'h')), assign(this.note, expression))),
        setup=('cut',),
    )
    assert record.failure is None
    assert values(record, program, 'office.note', (1,)) == pytest.approx((expected,))


def test_a_later_stage_of_the_round_reads_the_last_solve():
    program, record = office(
        event('cut', after(q(1, 'h'), assign(this.staff_hours, q(80, 'h')))),
        event('copy', after(q(1, 'h'), assign(this.note, this.staffing.care))),
        setup=('cut', 'copy'),
    )
    assert record.failure is None
    assert values(record, program, 'office.note', (1,)) == pytest.approx((70,))


def test_a_result_reads_as_settled_in_a_round_that_changes_none_of_its_inputs():
    program, record = office(
        event('cut', after(q(1, 'h'), assign(this.staff_hours, q(80, 'h')))),
        event('copy', after(q(2, 'h'), assign(this.note, this.staffing.care))),
        setup=('cut', 'copy'),
        horizon=3,
    )
    assert record.failure is None
    assert values(record, program, 'office.note', (1, 2)) == pytest.approx((0, 56))


def test_a_result_read_in_the_setup_is_read_before_its_first_solve():
    b = Builder(UNITS)
    b.entity(
        'office',
        value('staff_hours', 'h', 100),
        value('outreach_minimum', 'h', 30),
        value('note', 'h', 0),
        staffing(),
    )
    b.setup(assign(named('office').note, named('office').staffing.care))
    record = run(b.finish(), Configuration(Request(1)))
    assert record.failure.t == 0
    assert 'office.staffing.care is read before its first solve' in record.failure.detail('message')


def test_an_infeasible_solve_stops_the_run_before_a_trigger_reads_it():
    """At 1 h the staff falls to 10 h while the outreach must stay at least 20 h: no answer. The
    trigger on care never fires, and the run stops at 1 h naming the solver and the step."""
    b = Builder(UNITS)
    made = b.entity(
        'office',
        value('staff_hours', 'h', 100),
        value('fired', 'h', 0),
        solver(
            'staffing',
            given('available', this.staff_hours),
            unknown('care', 'h', lower=q(0, 'h')),
            unknown('outreach', 'h', lower=q(20, 'h')),
            constraint(local.care + local.outreach == local.available),
            maximize(local.care),
        ),
        event('cut', after(q(1, 'h'), assign(this.staff_hours, q(10, 'h')))),
        event(
            'watch',
            when(this.staffing.care <= q(50, 'h'), start(this.watch), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.fired, q(1, 'h'))),
        ),
    )
    b.setup(start(made.cut))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    message = record.failure.detail('message')
    assert record.failure.t == 1
    assert 'the solver office.staffing cannot answer at t = 1 h' in message
    assert 'infeasible in the hard constraints' in message
    assert record.entries('fire') == ()
    assert values(record, program, 'office.staffing.care', (0,)) == pytest.approx((80,))


def deliveries(capacity=3):
    """A depot whose empty tank passes on what its fill brings, at most `capacity` L/h; the provider's
    solver determines the fill. Deliveries of 2 L/h for 2 h start at 0 h and 1 h: their pipes join
    the tank, and so the solver's problem, at their starts and leave at their finishes."""
    b = Builder(UNITS)
    depot = b.entity(
        'depot',
        value('water', 'L', 0, lower=0, upper=10),
        flow('fill', SOURCE, this.water, capacity=q(capacity, 'L/h')),
        event('deliver', flow('pipe', this.water, SINK, request=q(2, 'L/h')), after(q(2, 'h'))),
        event('second', after(q(1, 'h'), start(this.deliver))),
    )
    b.entity('provider', solver('supply', given('fill', depot.fill), solve_for(local.fill.actual_rate)))
    b.setup(start(depot.deliver), start(depot.second))
    return b.finish()


def junction():
    """A junction held at 0 L passes on what its feed brings, at most 3 L/h, to two pipes that request
    2 L/h each; the provider's solver determines the three rates."""
    b = Builder(UNITS)
    hub = b.entity(
        'hub',
        value('water', 'L', 0, lower=0, upper=0),
        flow('feed', SOURCE, this.water, capacity=q(3, 'L/h')),
        flow('east', this.water, SINK, request=q(2, 'L/h')),
        flow('west', this.water, SINK, request=q(2, 'L/h')),
    )
    flows = [given(name, getattr(hub, name)) for name in ('feed', 'east', 'west')]
    rates = [solve_for(getattr(local, name).actual_rate) for name in ('feed', 'east', 'west')]
    b.entity('provider', solver('supply', *flows, *rates))
    return b.finish()


def test_a_store_held_at_both_bounds_is_one_equality_of_its_solvers_problem():
    """The junction's books are one row, feed - east - west == 0, and no row of either sign alone; fair
    sharing gives each pipe half of the feed's 3 L/h."""
    program = junction()
    made = Run(Plan.of(program, Configuration(Request(1))))
    record = made.run()
    assert record.failure is None
    for path, rate in (('hub.feed', 3), ('hub.east', 1.5), ('hub.west', 1.5)):
        assert values(record, program, f'{path}.actual_rate', (0.5,)) == pytest.approx((rate,), abs=1e-6)
    rows = [key for key in made.ways.kept['provider.supply']._rows if key[:2] == ('store', 'hub.water')]
    assert rows == [('store', 'hub.water', 'held')]


def test_flows_that_join_and_leave_a_solvers_store_join_and_leave_its_problem():
    """A alone gets 2 L/h; A and B share the fill's 3 L/h, 1.5 each, as the depot's outflow shares
    what reaches it (the solver names the fill, not the pipes); B alone 2; then nothing: the fill,
    which has no request, is the least that serves them. The solver keeps one instance of HiGHS:
    B's pipe is a column that joins it at 1 h, and A's leaves at 2 h."""
    program = deliveries()
    configuration = Configuration(Request(4))
    made = Run(Plan.of(program, configuration))
    record = made.run()
    assert record.failure is None
    a, b = 'depot.deliver#0.pipe.actual_rate', 'depot.deliver#1.pipe.actual_rate'
    times = (0.5, 1.5, 2.5, 3.5)
    assert values(record, program, a, times) == pytest.approx((2, 1.5, 0, 0))
    assert values(record, program, b, times[1:]) == pytest.approx((1.5, 2, 0))
    assert values(record, program, 'depot.fill.actual_rate', times) == pytest.approx((2, 3, 2, 0))
    assert values(record, program, 'depot.water', (4,)) == pytest.approx((0,))
    kept = made.ways.kept['provider.supply']
    assert ('flow', a.rsplit('.', 1)[0]) not in kept._columns
    assert ('flow', 'depot.fill') in kept._columns
    assert [entry.t for entry in record.entries('solve', 'provider.supply')] == [0, 1, 2, 3]


def tapering(count=2, upper=None):
    """Tanks that fill toward 10 L at `(10 L - water) / 1 h`, each at most 6 L/h, under one limit of
    8 L/h on the sum, which a provider's solver shares; the first tank may stop at `upper`."""
    b = Builder(UNITS)
    tanks = []
    for k in range(count):
        tanks.append(
            b.entity(
                f'tank{k}',
                value('water', 'L', 0, lower=0, upper=upper if k == 0 else None),
                flow(
                    'fill',
                    SOURCE,
                    this.water,
                    request=formula((q(10, 'L') - this.water) / q(1, 'h')),
                    capacity=q(6, 'L/h'),
                ),
            )
        )
    names = [given(f'f{k}', tank.fill) for k, tank in enumerate(tanks)]
    rates = [getattr(local, f'f{k}').actual_rate for k in range(count)]
    total = rates[0]
    for rate in rates[1:]:
        total = total + rate
    b.entity(
        'provider',
        solver('share', *names, *[solve_for(rate) for rate in rates], constraint(total <= q(8, 'L/h'))),
    )
    return b.finish()


def test_a_solver_whose_requests_follow_their_tanks_is_solved_at_trial_states():
    """Two empty tanks ask 10 L/h each, falling as they fill: the limit gives 4 L/h each until the
    requests fall to 4 L/h at 1.5 h (6 L each), and from then each gets its request: 10 - 4 e^-(t-1.5)."""
    program = tapering()
    record = run(program, Configuration(Request(3)))
    assert record.failure is None
    times = (1, 1.5, 2, 3)
    expected = [4, 6, 10 - 4 * math.exp(-0.5), 10 - 4 * math.exp(-1.5)]
    for name in ('tank0.water', 'tank1.water'):
        assert values(record, program, name, times) == pytest.approx(expected, rel=1e-6)
    assert values(record, program, 'tank0.fill.actual_rate', (1, 2)) == pytest.approx(
        (4, 4 * math.exp(-0.5)), rel=1e-6
    )


def test_a_moving_solver_solves_again_where_a_store_meets_its_bound():
    """The first tank stops at 5 L, at 1.25 h; from then the second gets its own request alone, 5 L/h
    falling: 10 - 5 e^-(t-1.25)."""
    program = tapering(upper=5)
    record = run(program, Configuration(Request(2)))
    assert record.failure is None
    assert values(record, program, 'tank0.water', (1, 2)) == pytest.approx((4, 5), rel=1e-6)
    assert values(record, program, 'tank0.fill.actual_rate', (2,)) == pytest.approx((0,), abs=1e-6)
    assert values(record, program, 'tank1.water', (1, 2)) == pytest.approx(
        (4, 10 - 5 * math.exp(-0.75)), rel=1e-6
    )


def test_a_moving_solver_beyond_its_limit_of_stores_stops_by_name():
    record = run(tapering(count=21), Configuration(Request(1)))
    message = record.failure.detail('message')
    assert record.failure.t == 0
    assert 'the solver provider.share' in message and '21 stores' in message and 'more than 20' in message


def test_two_solvers_whose_flows_share_a_store_fail_by_name():
    """Two providers would each choose a rate out of one tank: one calculation, which one solver
    must own."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 0, lower=0),
        flow('a', this.water, SINK, request=q(1, 'L/h')),
        flow('b', this.water, SINK, request=q(1, 'L/h')),
    )
    b.entity('first', solver('own', given('a', tank.a), solve_for(local.a.actual_rate)))
    b.entity('second', solver('own', given('b', tank.b), solve_for(local.b.actual_rate)))
    record = run(b.finish(), Configuration(Request(1)))
    message = record.failure.detail('message')
    assert record.failure.t == 0
    assert 'two solvers meet in one calculation' in message
    assert 'first.own' in message and 'second.own' in message


@pytest.mark.parametrize(
    'relation, form',
    [
        (lambda x: x.actual_rate < q(2, 'L/h'), 'the relation <'),
        (lambda x: fmin(x.actual_rate, q(2, 'L/h')) >= q(1, 'L/h'), 'min of an unknown'),
        (lambda x: x.actual_rate * x.actual_rate <= q(4, 'L/h') * q(1, 'L/h'), 'a product of two unknowns'),
        (lambda x: (x.actual_rate <= q(2, 'L/h')) | (x.actual_rate >= q(3, 'L/h')), 'a disjunction'),
    ],
    ids=['strict', 'min', 'product', 'or'],
)
def test_a_relation_outside_the_constraint_language_fails_and_names_its_form(relation, form):
    b = Builder(UNITS)
    tank = b.entity(
        'tank', value('water', 'L', 10, lower=0), flow('out', this.water, SINK, request=q(3, 'L/h'))
    )
    b.entity(
        'provider',
        solver('plan', given('x', tank.out), solve_for(local.x.actual_rate), constraint(relation(local.x))),
    )
    record = run(b.finish(), Configuration(Request(1)))
    message = record.failure.detail('message')
    assert record.failure.t == 0
    assert 'unsupported in the solver provider.plan' in message and form in message


def common_sink(order, limit=None):
    """The common sink of "Local allocation" (6 L/h asked at the clinic's inflow, `main` capped at
    4 L/h) with a provider's solver that determines both feeds, and `limit` on their sum, if any."""
    b = Builder(UNITS)
    clinic = b.entity(
        'clinic',
        value(
            'water',
            'L',
            0,
            lower=0,
            inflow=endpoint(request=q(6, 'L/h'), allocation=priority(*(getattr(this, n) for n in order))),
        ),
        flow('main', SOURCE, this.water, capacity=q(4, 'L/h')),
        flow('backup', SOURCE, this.water),
    )
    parts = [given('m', clinic.main), given('b', clinic.backup)]
    parts += [solve_for(local.m.actual_rate), solve_for(local.b.actual_rate)]
    if limit is not None:
        parts.append(constraint(local.m.actual_rate + local.b.actual_rate <= q(limit, 'L/h')))
    b.entity('provider', solver('feeds', *parts))
    return b.finish()


@pytest.mark.parametrize(
    'order, limit, rates',
    [
        (('main', 'backup'), None, (4, 2)),
        (('main', 'backup'), 5, (4, 1)),
        (('backup', 'main'), None, (0, 6)),
        (('backup', 'main'), 5, (0, 5)),
    ],
    ids=['main-first', 'main-first-short', 'backup-first', 'backup-first-short'],
)
def test_the_preferred_routes_of_a_request_carry_it_first_inside_a_solver(order, limit, rates):
    """Spec, "Selection order": "A preferred route has first access to useful requested work, up to
    the outstanding claim it serves". The sink's claim of 6 L/h (or the 5 L/h that the limit
    leaves) is served first; then the preferred feed carries as much of it as it can, within its
    capacity, and the other feed the rest. By hand: main first gives 4 and 2 L/h, as local sharing
    does (acceptance row 6), and 4 and 1 L/h under a limit of 5 L/h; backup first carries all of it."""
    program = common_sink(order, limit)
    configuration = Configuration(Request(1))
    record = run(program, configuration)
    assert record.failure is None, record.failure
    found = [values(record, program, f'clinic.{name}.actual_rate', [0.5])[0] for name in ('main', 'backup')]
    assert found == pytest.approx(list(rates), abs=1e-9)
    oracle, failed = run_of(program, configuration)
    assert failed is None
    for name, rate in zip(('main', 'backup'), rates):
        expected = value_at(oracle, program, Key('clinic', (name, 'actual_rate')), 0)
        assert float(expected) == rate


def test_a_formula_that_reads_an_enforced_equality_holds_within_the_solvers_tolerance():
    """R-A3-02: the worked network's `rate_follows_levels` (a route's signed rate equals its pull times
    the difference of the levels), which the solver enforces, holds at every time; the solver leaves
    the idle route at 4e-26 W against 0 W, which an exact comparison reads as false from 2 h. The
    solver reads the equality; its readers compare to 1e-7 relative, one canonical unit at least."""
    from dataclasses import replace

    from tests.program.examples import EXAMPLES

    example = EXAMPLES['network']()
    configuration = replace(example.configuration, request=Request(4))
    record = run(example.program, configuration)
    names = ['links.garden_junction.rate_follows_levels', 'links.junction_clinic.rate_follows_levels']
    for reading in read(record, example.program, names, [0, 1, 2, 2.5, 3, 4]):
        assert reading.values == (True,) * 6
    plan = Plan.of(example.program, configuration)
    assert set(plan.enforced) == set(names)
    assert all(plan.enforced[name].ops == ('eq',) for name in names)


def test_a_solver_of_the_feed_alone_leaves_the_junctions_their_local_sharing():
    """The example `two_junctions_upstream_solver` (worked by hand there): the feed carries 1 L/h, A
    and the onward pipe 1/2 each, B and C 1/4 each, as the oracle has it, in one solve."""
    from tests.program.examples import EXAMPLES

    example = EXAMPLES['two_junctions_upstream_solver']()
    record = run(example.program, example.configuration)
    assert record.failure is None
    oracle, failed = run_of(example.program, example.configuration)
    assert failed is None
    expected = {('first', 'feed'): 1, ('first', 'to_a'): 0.5, ('first', 'onward'): 0.5}
    expected |= {('second', 'to_b'): 0.25, ('second', 'to_c'): 0.25}
    for (owner, name), rate in expected.items():
        key = Key(owner, (name, 'actual_rate'))
        assert values(record, example.program, key, (0, 0.5)) == pytest.approx((rate, rate), abs=1e-12)
        assert float(value_at(oracle, example.program, key, 0)) == rate
    assert [entry.t for entry in record.entries('solve', 'provider.upstream')] == [0]


def test_a_relation_on_a_flow_that_the_solver_does_not_name_is_refused():
    """A flow that a solver does not name keeps its endpoints' local sharing: a constraint of the
    solver on it would decide who is served without naming it."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 10, lower=0, upper=10),
        flow('out', this.water, SINK, request=q(2, 'L/h')),
        flow('fill', SOURCE, this.water),
    )
    b.entity(
        'provider',
        solver(
            'plan',
            given('out', tank.out),
            given('fill', tank.fill),
            solve_for(local.fill.actual_rate),
            constraint(local.out.actual_rate <= q(1, 'L/h')),
        ),
    )
    record = run(b.finish(), Configuration(Request(1)))
    assert record.failure.t == 0
    message = record.failure.detail('message')
    assert 'the solver provider.plan reads tank.out.actual_rate, which it does not determine' in message


def released():
    """A full tank drains 2 L/h and is filled from A and by a pipe from a second tank, which starts
    empty; each asks 2 L/h. The provider's solver determines the fill of the second tank alone: 3 L/h,
    its request within its capacity. A third tank, which nothing joins, empties at 1 h."""
    b = Builder(UNITS)
    full = b.entity(
        'full',
        value('water', 'L', 10, lower=0, upper=10),
        flow('drain', this.water, SINK, request=q(2, 'L/h'), capacity=q(2, 'L/h')),
        flow('from_a', SOURCE, this.water, request=q(2, 'L/h')),
    )
    tank = b.entity(
        'tank',
        value('water', 'L', 0, lower=0, upper=10),
        flow('fill', SOURCE, this.water, request=q(3, 'L/h'), capacity=q(3, 'L/h')),
        flow('onward', this.water, full.water, request=q(2, 'L/h')),
    )
    b.entity('clock', value('water', 'L', 1, lower=0), flow('drain', this.water, SINK, request=q(1, 'L/h')))
    b.entity('provider', solver('supply', given('fill', tank.fill), solve_for(local.fill.actual_rate)))
    return b.finish()


def test_a_store_that_the_answer_moves_off_its_bound_is_released_at_once():
    """At 0 h the second tank is empty, so the claim of its pipe waits for its supply: the full tank's
    room would go to A, 2 L/h, and the pipe would carry nothing. That answer fills the tank at 3 L/h,
    off its bound, so the bound is released and the problem solved again: the pipe's claim is then on
    the level of A's, and they share the room, 1 L/h each; the tank rises at 2 L/h. The third tank,
    which empties at 1 h, changes nothing (the oracle settles every calculation then), and the
    solve is traced once."""
    program = released()
    configuration = Configuration(Request(2))
    record = run(program, configuration)
    assert record.failure is None
    oracle, failed = run_of(program, configuration)
    assert failed is None
    times = (0, 0.5, 1.5)
    for path in ('full.from_a.actual_rate', 'tank.onward.actual_rate'):
        assert values(record, program, path, times) == pytest.approx((1, 1, 1), abs=1e-12)
    assert values(record, program, 'tank.water', (0.5, 1.5)) == pytest.approx((1, 3), abs=1e-12)
    for owner, name in (('full', 'from_a'), ('tank', 'onward'), ('tank', 'water')):
        key = Key(owner, (name, 'actual_rate') if name != 'water' else (name,))
        for at in times:
            found = values(record, program, key, (at,))[0]
            assert found == pytest.approx(float(value_at(oracle, program, key, Fraction(at))), abs=1e-12)
    assert [entry.t for entry in record.entries('solve', 'provider.supply')] == [0]


def outflows(trickle, spare=None):
    """A tank of 10 L drains 5 L/h by `main` and, by `trickle`, its request (if any) within the capacity
    `spare` (if any); the provider's solver determines both."""
    b = Builder(UNITS)
    settings = {} if trickle is None else {'request': q(trickle, 'L/h')}
    if spare is not None:
        settings['capacity'] = q(spare, 'L/h')
    tank = b.entity(
        'tank',
        value('water', 'L', 10, lower=0, upper=20),
        flow('main', this.water, SINK, request=q(5, 'L/h')),
        flow('trickle', this.water, SINK, **settings),
    )
    parts = [given('main', tank.main), given('trickle', tank.trickle)]
    parts += [solve_for(local.main.actual_rate), solve_for(local.trickle.actual_rate)]
    b.entity('provider', solver('plan', *parts))
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None
    return values(record, program, 'tank.trickle.actual_rate', (0.5,))[0], values(
        record, program, 'tank.water', (1,)
    )[0]


@pytest.mark.parametrize('trickle', [2e-7, 5e-10])
def test_a_small_requested_delivery_survives_the_polish(trickle):
    """The tank holds stock, so each pipe gets its request: 5 L/h and the trickle's own 2e-7 or
    5e-10 L/h, which the polish of the answer once took for a rounding of zero (it snapped a value
    within 1e-6 L/h of a bound to it). The tank holds 10 - 5 - trickle L at 1 h."""
    rate, water = outflows(trickle)
    assert rate == pytest.approx(trickle, rel=1e-9)
    assert water == pytest.approx(5 - trickle, rel=0, abs=1e-15)


@pytest.mark.parametrize('spare', [1e-7, 5e-7])
def test_an_idle_pipe_with_a_small_capacity_stays_idle(spare):
    """A pipe with no request asks nothing and its target is zero: it stays at 0 L/h, where the polish
    once put it at its capacity, which is within 1e-6 L/h of zero as well (the snap to the upper bound
    came after the snap to the lower one). The tank holds 5 L at 1 h."""
    rate, water = outflows(None, spare)
    assert rate == 0
    assert water == 5


def test_a_ring_of_empty_tanks_among_the_flows_that_a_solver_does_not_name_stops_by_name():
    """Two empty tanks pass water to each other and the solver names only the fill of the first: the
    pipes between them keep local sharing, which has no answer for a ring of empty stores (each waits
    for the other's supply). The run stops at once and says how to decide them."""
    b = Builder(UNITS)
    first = b.entity('first', value('water', 'L', 0, lower=0, upper=10))
    second = b.entity('second', value('water', 'L', 0, lower=0, upper=10))
    b.entity(
        'pipes',
        flow('fill', SOURCE, first.water, capacity=q(2, 'L/h')),
        flow('there', first.water, second.water, request=q(1, 'L/h')),
        flow('back', second.water, first.water, request=q(1, 'L/h')),
    )
    b.entity(
        'provider', solver('plan', given('fill', named('pipes').fill), solve_for(local.fill.actual_rate))
    )
    record = run(b.finish(), Configuration(Request(1)))
    assert record.failure.t == 0
    message = record.failure.detail('message')
    assert 'a ring of stores at their lower bound passes supply around' in message
    assert 'the solver provider.plan does not name every flow there' in message


def turning(horizon=7):
    """A tank, empty at first, that the provider's solver fills at 4 L/h and that a drain of t L/h^2
    empties: the drain reads the time, so the problem moves (`MovingDeclared`). It holds 4t - t^2/2 L,
    up to 8 L at 4 h. `high` fires where it reaches 6 L, once, and `low` where it is at most 6 L,
    again each time that it has been above."""

    def watch(name, test, reset=None):
        return (
            value(f'{name}s', '', 0),
            event(
                name,
                when(test, start(getattr(this, name)), reset=reset),
                after(q(0, 'h'), add(getattr(this, f'{name}s'), 1)),
            ),
        )

    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 0, lower=0),
        flow('fill', SOURCE, this.water, request=q(4, 'L/h'), capacity=q(4, 'L/h')),
        flow('drain', this.water, SINK, request=formula(t / q(1, 'h') * q(1, 'L/h'))),
        *watch('high', this.water >= q(6, 'L'), reset_when(False)),
        *watch('low', this.water <= q(6, 'L')),
    )
    b.entity('provider', solver('supply', given('fill', tank.fill), solve_for(local.fill.actual_rate)))
    return b.finish(), Configuration(Request(horizon))


def test_a_value_that_turns_on_a_moving_solver_is_certified_as_on_the_other_ways():
    """4t - t^2/2 = 6 at 2 h, rising, and at 6 h, falling: `high` fires at 2 h, and `low` at 0 h (the
    tank holds 0 L) and at 6 h, read from the form of each step of the integrator (its cubic), with
    no near-tie. The tank holds 8 L at its peak."""
    program, configuration = turning()
    made = Run(Plan.of(program, configuration))
    record = made.run()
    assert record.failure is None, record.failure
    assert {connected.way for connected, _ in made.ways.sets.values()} == {'declared'}
    assert [entry.t for entry in record.entries('fire', 'tank.high.when[0]')] == pytest.approx([2], abs=1e-6)
    assert [entry.t for entry in record.entries('fire', 'tank.low.when[0]')] == pytest.approx(
        [0, 6], abs=1e-6
    )
    assert record.near_ties() == ()
    assert values(record, program, 'tank.water', (4,)) == pytest.approx((8,), rel=1e-6)
