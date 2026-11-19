"""A `where` over an endpoint's flows, from source to the record (spec, "Collections, keys and
projections": "A fixed-field filter over an endpoint collection follows these membership changes";
"What each scope can see": a connection reads its two endpoint identities). In its test, `source`
and `sink` are the ends of each member, fixed for the flow's lifetime, and compare by identity with a
store; the members that it keeps are present as the collection's are: an entity's flow for the whole
run, an occurrence's from its start to its finish. The values are worked by hand from the requests.

The oracle (`tests/reference/`) does not cover this: it reads an end of a flow in a test as the
amount in that store, and stops with a TypeError at an end at SOURCE or SINK.
"""

from __future__ import annotations

import textwrap

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Outside
from napkin.model.compile import compile_text
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    after,
    constraint,
    count,
    event,
    flow,
    formula,
    fsum,
    given,
    item,
    local,
    named,
    q,
    solve_for,
    solver,
    start,
    this,
    value,
)
from napkin.program.config import Configuration, Request
from tests.program.examples import UNITS


def values(text, paths, times, horizon):
    """The values of the paths at the times, in a run of a source text to the horizon."""
    program = compile_text(textwrap.dedent(text), UNITS).program
    record = run(program, Configuration(Request(horizon)))
    assert record.failure is None, record.failure
    return [reading.values for reading in read(record, program, paths, times)]


TANK = """
    clinic:
        water: L = 0 in [0,]
    garden:
        water: L = 0 in [0,]
    tank:
        water: L = 10 in [0,]
        flow a: this.water -> clinic.water
            request = 1 L/h
        flow b: this.water -> garden.water
            request = 2 L/h
        flow c: this.water -> SINK
            request = 4 L/h
        to_clinic = formula(sum(this.water.outflow.flows.where(sink == clinic.water).actual_rate))
        elsewhere = formula(count(this.water.outflow.flows.where(clinic.water != sink)))
        from_here = formula(count(clinic.water.inflow.flows.where(source == this.water)))
    """


def test_a_where_keeps_the_flows_of_an_entity_by_their_ends_for_the_whole_run():
    """The tank holds 10 L and its three outflows ask 7 L/h: it is empty at 10/7 h. The flow to the
    clinic carries 1 L/h until then, and nothing after; the two others stay members, starved, and the
    clinic's one inflow comes from the tank."""
    found = values(TANK, ['tank.to_clinic', 'tank.elsewhere', 'tank.from_here'], [0, 1, 1.5, 2], 2)
    assert found == [(1, 1, 0, 0), (2, 2, 2, 2), (1, 1, 1, 1)]


DEPOT = """
    Customer:
        water: L = 0 in [0,]

    a: Customer
    b: Customer

    depot:
        supply: L = 40 in [0,]
        deliver = event(customer: Customer):
            flow pipe: this.supply -> customer.water
                request = 10 L/h
            until customer.water >= 20 L
            when t >= 1 h:
                this.deliver.start(b)
                reset when false

    depot.deliver.start(a)
    to_a = formula(count(depot.supply.outflow.flows.where(sink == a.water)))
    not_a = formula(count(depot.supply.outflow.flows.where(sink != a.water)))
    rate_to_b = formula(sum(depot.supply.outflow.flows.where(sink == b.water).actual_rate))
    """


def test_a_where_follows_the_flows_of_occurrences_as_they_join_and_leave():
    """The delivery to a runs from 0 h and the one to b from 1 h, each at 10 L/h until its customer
    holds 20 L: a's ends at 2 h and b's at 3 h, when the depot's 40 L are gone. Each pipe is a member
    from its start to its finish, and the where keeps it by its sink."""
    found = values(DEPOT, ['to_a', 'not_a', 'rate_to_b'], [0, 0.5, 1.5, 2, 2.5, 3, 3.5], 4)
    assert found == [
        (1, 1, 1, 0, 0, 0, 0),
        (0, 0, 1, 1, 1, 0, 0),
        (0, 0, 10, 10, 10, 0, 0),
    ]


CHANNEL = """
    west:
        water: L = 10 in [0, 20]
    east:
        water: L = 10 in [0, 20]
    channel:
        flow link: west.water <-> east.water
            request = -3 L/h
    drain:
        flow out: west.water -> SINK
            request = 1 L/h
    eastward = formula(sum(west.water.outflow.flows.where(sink == east.water).actual_rate))
    westward = formula(sum(east.water.outflow.flows.where(sink == west.water).actual_rate))
    leaving_west = formula(count(west.water.outflow.flows.where(sink != east.water)))
    """


def test_the_legs_of_a_route_are_kept_by_their_own_ends():
    """Spec, "Endpoint collections": `link.forward` is in west's outflows with the rate max(x, 0) and
    `link.backward` in east's with max(-x, 0); at -3 L/h east sends 3 L/h west. West's other outflow,
    the drain, ends at SINK, which is no store."""
    found = values(CHANNEL, ['eastward', 'westward', 'leaving_west'], [0, 1], 1)
    assert found == [(0, 0), (3, 3), (1, 1)]


@pytest.mark.parametrize(
    ('test', 'kept', 'rate'),
    [
        (lambda: item.sink == named('clinic').water, 1, 1),
        (lambda: item.sink != named('clinic').water, 2, 6),
        (lambda: item.source == named('clinic').water, 0, 0),
        (lambda: (item.sink == named('clinic').water) | (item.sink == named('garden').water), 2, 3),
        (lambda: item.source == item.sink, 0, 0),
    ],
)
def test_a_program_built_by_hand_compares_the_ends_by_identity(test, kept, rate):
    """Three outflows of a tank that holds 6.5 L at 0.5 h, so each carries its request (1, 2 and
    4 L/h), to two stores that hold the same amount and to SINK: identity, not the amounts at the
    ends, decides; SINK is no store, and no flow ends where it starts."""
    b = Builder(UNITS)
    b.entity('clinic', value('water', 'L', 0, lower=0))
    b.entity('garden', value('water', 'L', 0, lower=0))
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        flow('a', this.water, named('clinic').water, request=q(1, 'L/h')),
        flow('b', this.water, named('garden').water, request=q(2, 'L/h')),
        flow('c', this.water, SINK, request=q(4, 'L/h')),
        value('kept', '', formula(count(this.water.outflow.flows.where(test())))),
        value('rate', 'L/h', formula(fsum(this.water.outflow.flows.where(test()).actual_rate))),
    )
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert record.failure is None, record.failure
    assert [reading.values for reading in read(record, program, ['tank.kept', 'tank.rate'], [0.5])] == [
        (kept,),
        (rate,),
    ]


def test_a_where_of_a_where_keeps_what_both_keep():
    text = TANK.replace(
        'where(clinic.water != sink)', 'where(clinic.water != sink).where(sink != garden.water)'
    )
    assert values(text, ['tank.elsewhere'], [0, 2], 2) == [(1, 1)]


def test_a_where_over_flows_that_join_and_leave_is_refused_inside_a_solver():
    """A solver's problem names the members of a collection of flows without the test of its where:
    where an event owns flows, the engine refuses such a read there by name."""
    b = Builder(UNITS)
    depot = b.entity(
        'depot',
        value('water', 'L', 0, lower=0, upper=10),
        flow('fill', SOURCE, this.water, capacity=q(3, 'L/h')),
        event('deliver', flow('pipe', this.water, SINK, request=q(2, 'L/h')), after(q(2, 'h'))),
    )
    asked = fsum(named('depot').water.outflow.flows.where(item.sink != named('depot').water).request)
    b.entity(
        'provider',
        solver(
            'supply',
            given('fill', depot.fill),
            solve_for(local.fill.actual_rate),
            constraint(local.fill.actual_rate <= asked),
        ),
    )
    b.setup(start(depot.deliver))
    with pytest.raises(Outside, match='in a solver: this engine reads a where over the flows of an endpoint'):
        run(b.finish(), Configuration(Request(1)))
