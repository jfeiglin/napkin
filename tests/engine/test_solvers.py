"""Declared solvers on the engine (spec: "Solver and execution contract"; G0, D5).

Rounds: two writes in one round cause one solve, and a trigger that reacts to the result causes a
second round with a second solve at the same time. Reading a result whose inputs changed in the round
before the solve settles fails, naming the result, also through a formula and in a later stage of
the round; reading it once it has settled does not. A solve that cannot answer stops the run there,
naming the solver and the step, before a trigger reads a partial answer. Flows of occurrences that
join and leave a solver's store join and leave its problem, on the solver that the run keeps. A
problem whose requests follow its tanks is solved at trial states between moments, and one beyond
the limit of such a set stops by name; two solvers in one calculation, and a relation outside the
constraint language, fail by name.

The expected numbers are worked by hand from the rules of the spec: the staffing solver of
"Allocating staff hours" gives care 70% of the staff hours (outreach at its minimum, 30%), and fair
sharing of one supply of 3 L/h among requests of 2 L/h serves each in full or both at 1.5 L/h; tanks
that fill at their headroom per hour follow 10 L - c e^-t once their requests are met.
"""

from __future__ import annotations

import math

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
    'stage',
    [
        (assign(this.staff_hours, q(80, 'h')), assign(this.note, this.staffing.care)),
        (assign(this.staff_hours, q(80, 'h')), assign(this.note, this.twice_care)),
    ],
    ids=['direct', 'through a formula'],
)
def test_a_result_read_before_its_solve_settles_fails_and_names_it(stage):
    _, record = office(event('cut', after(q(1, 'h'), *stage)), setup=('cut',))
    message = record.failure.detail('message')
    assert record.failure.t == 1
    assert 'office.staffing.care is read before its solve settles' in message
    assert 'office.staff_hours' in message


def test_a_later_stage_of_the_round_reads_no_stale_result_either():
    _, record = office(
        event('cut', after(q(1, 'h'), assign(this.staff_hours, q(80, 'h')))),
        event('copy', after(q(1, 'h'), assign(this.note, this.staffing.care))),
        setup=('cut', 'copy'),
    )
    assert record.failure.t == 1
    assert 'office.staffing.care is read before its solve settles' in record.failure.detail('message')


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


def test_flows_that_join_and_leave_a_solvers_store_join_and_leave_its_problem():
    """A alone gets 2 L/h; A and B share the fill's 3 L/h, 1.5 each, by fair sharing; B alone 2; then
    nothing: the fill, which has no request, is the least that serves them. The solver keeps one instance of HiGHS: B's pipe is a
    column that joins it at 1 h, and A's leaves at 2 h."""
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
