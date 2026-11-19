"""The flow network in the front end (`napkin/model/semantic.py` and the lowering, slice S2): flows
whose ends go through links, to named members and to the top level; the settings of a store's
outflow and inflow, with `priority(...)` over named flows and over a projection of flows; the reads
of an endpoint (`actual_rate`, `request`, `capacity`, `flows`). A source text gives the program that
the builder makes of the same model, and each refusal has its code and its line. The spec's worked
models of local allocation (`reservoir_priority`, `common_sink`, the one pipe) are in
`test_lowering.py`, against the programs of `tests/program/examples.py`."""

import textwrap
from pathlib import Path

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    TemplateHandle,
    count,
    endpoint,
    flow,
    fmax,
    formula,
    fsum,
    group_of,
    input_,
    item,
    link,
    named,
    priority,
    q,
    root,
    this,
    value,
)
from napkin.program.canonical import program_bytes
from tests.program.examples import PLACES, ROUTES, UNITS

CORPUS = Path(__file__).parent / 'corpus'


def compiled(text, tables=None):
    return compile_text(textwrap.dedent(text), UNITS, tables=tables)


def same(text, builder, tables=None):
    return program_bytes(compiled(text, tables).program) == program_bytes(builder.finish())


def refused(text, code, line):
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    assert code in caught.value.codes, caught.value
    found = caught.value.problems[caught.value.codes.index(code)]
    assert found.line == line, found
    return found


# ---- flows across templates and entities -----------------------------------------------------------


def test_a_flow_of_a_template_ends_through_its_links():
    text = """
        Place:
            power: Wh = 0 in [0, 0]
            input need: W = 1
            flow use: this.power -> SINK
                request = formula(this.need)

        Route:
            origin: Place
            destination: Place
            flow carried: this.origin.power -> this.destination.power
                capacity = 3 W

        a: Place
        b: Place
        r: Route
            origin = a
            destination = b
        """
    b = Builder(UNITS)
    place = b.template(
        'Place',
        value('power', 'Wh', 0, lower=0, upper=0),
        input_('need', 'W', 1),
        flow('use', this.power, SINK, request=formula(this.need)),
    )
    route = b.template(
        'Route',
        link('origin', 'Place'),
        link('destination', 'Place'),
        flow('carried', this.origin.power, this.destination.power, capacity=q(3, 'W')),
    )
    b.member(place, 'a')
    b.member(place, 'b')
    b.member(route, 'r', origin=named('a'), destination=named('b'))
    assert same(text, b)


def test_a_flow_between_rows_of_two_tables_keeps_its_rows_when_the_files_are_reordered():
    """The worked network's routes as directed flows between the stores of place rows: the pinned
    engine refused a route-owned flow between stocks on rows (spec, "Worked network data")."""
    text = """
        Place:
            input base_need: W = 0
            input supply_limit: W = 0
            input critical: bool = false
            power: Wh = 0 in [0, 0]

        Route:
            origin: Place
            destination: Place
            input closes_at_two: bool = false
            flow carried: this.origin.power -> this.destination.power
                capacity = 4 W

        sites: Place from "places.csv"
        links: Route from "routes.csv"
        """
    b = Builder(UNITS)
    places = b.template(
        'Place',
        input_('base_need', 'W', 0),
        input_('supply_limit', 'W', 0),
        input_('critical', BOOL, False),
        value('power', 'Wh', 0, lower=0, upper=0),
    )
    routes = b.template(
        'Route',
        link('origin', 'Place'),
        link('destination', 'Place'),
        input_('closes_at_two', BOOL, False),
        flow('carried', this.origin.power, this.destination.power, capacity=q(4, 'W')),
    )
    b.table('sites', places, PLACES)
    b.table('links', routes, ROUTES)
    files = {name: (CORPUS / name).read_text() for name in ('places.csv', 'routes.csv')}
    assert same(text, b, files)
    reordered = {}
    for name, table in files.items():
        head, *rows = table.splitlines()
        reordered[name] = '\n'.join([head, *rows[::-1]]) + '\n'
    assert program_bytes(compiled(text, reordered).program) == program_bytes(compiled(text, files).program)


CUSTOMERS = """
    reservoir:
        water: L = 20 in [0, 20]
            outflow.capacity = 10 L/h
            outflow.allocation = priority(Customer.instances.by(rank).delivery)

    Customer:
        input rank = 1
        flow delivery: reservoir.water -> SINK
            request = 4 L/h

    first: Customer
    second: Customer
        rank = 2
    """


def test_a_template_s_flow_ends_at_a_named_entity_and_a_priority_ranks_a_projection_of_flows():
    b = Builder(UNITS)
    # The reservoir stands first in the text, so its template is the program's first.
    ranked = priority(TemplateHandle('Customer').instances.by('rank').delivery)
    b.entity(
        'reservoir',
        value(
            'water', 'L', 20, lower=0, upper=20, outflow=endpoint(capacity=q(10, 'L/h'), allocation=ranked)
        ),
    )
    customer = b.template(
        'Customer',
        input_('rank', '', 1),
        flow('delivery', named('reservoir').water, SINK, request=q(4, 'L/h')),
    )
    b.member(customer, 'first')
    b.member(customer, 'second', rank=2)
    assert same(CUSTOMERS, b)


def test_a_priority_ranks_a_collection_value_by_its_keys_as_the_spec_spells_it():
    """Spec, "Local allocation": `priority(customers.by(rank).delivery)`, with `customers` a
    collection value of the top level, which the program's checker reads as its members."""
    # CUSTOMERS ends with the indentation of its top level.
    text = CUSTOMERS.replace('Customer.instances.by', 'customers.by') + 'customers = Customer.instances\n'
    b = Builder(UNITS)
    ranked = priority(root.customers.by('rank').delivery)
    b.entity(
        'reservoir',
        value(
            'water', 'L', 20, lower=0, upper=20, outflow=endpoint(capacity=q(10, 'L/h'), allocation=ranked)
        ),
    )
    customer = b.template(
        'Customer',
        input_('rank', '', 1),
        flow('delivery', named('reservoir').water, SINK, request=q(4, 'L/h')),
    )
    b.member(customer, 'first')
    b.member(customer, 'second', rank=2)
    b.root(value('customers', group_of('Customer'), customer.instances))
    assert same(text, b)


def test_a_store_of_a_template_ranks_the_flows_that_leave_it_through_a_where_on_their_links():
    text = """
        Place:
            power: Wh = 0 in [0,]
                outflow.allocation = priority(Route.instances.where(origin == this).by(rank).carried)

        Route:
            origin: Place
            destination: Place
            input rank = 1
            flow carried: this.origin.power -> this.destination.power
                request = 1 W

        a: Place
        b: Place
        r: Route
            origin = a
            destination = b
        """
    b = Builder(UNITS)
    leaving = TemplateHandle('Route').instances.where(item.origin == this).by('rank').carried
    place = b.template(
        'Place', value('power', 'Wh', 0, lower=0, outflow=endpoint(allocation=priority(leaving)))
    )
    route = b.template(
        'Route',
        link('origin', 'Place'),
        link('destination', 'Place'),
        input_('rank', '', 1),
        flow('carried', this.origin.power, this.destination.power, request=q(1, 'W')),
    )
    b.member(place, 'a')
    b.member(place, 'b')
    b.member(route, 'r', origin=named('a'), destination=named('b'))
    assert same(text, b)


def test_a_flow_ends_at_a_store_of_the_top_level():
    text = 'pool: L = 10 in [0,]\ntank:\n    water: L = 0\n    flow fill: pool -> this.water\n        request = 1 L/h\n'
    b = Builder(UNITS)
    b.entity('tank', value('water', 'L', 0), flow('fill', root.pool, this.water, request=q(1, 'L/h')))
    b.root(value('pool', 'L', 10, lower=0))
    assert same(text, b)


# ---- the settings and the reads of an endpoint --------------------------------------------------------


def test_the_reads_of_an_endpoint_lower_as_the_builder_makes_them():
    text = """
        tank:
            water: L = 10 in [0,]
                outflow.capacity = 3 L/h
            flow a: this.water -> SINK
                request = 1 L/h
            flow b: this.water -> SINK
                request = 2 L/h
            out = formula(this.water.outflow.actual_rate)
            asked = formula(sum(this.water.outflow.flows.request))
            open = formula(count(this.water.outflow.flows))
            room = formula(this.water.outflow.capacity - this.water.outflow.actual_rate)
        """
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0, outflow=endpoint(capacity=q(3, 'L/h'))),
        flow('a', this.water, SINK, request=q(1, 'L/h')),
        flow('b', this.water, SINK, request=q(2, 'L/h')),
        value('out', 'L/h', formula(this.water.outflow.actual_rate)),
        value('asked', 'L/h', formula(fsum(this.water.outflow.flows.request))),
        value('open', '', formula(count(this.water.outflow.flows))),
        value('room', 'L/h', formula(this.water.outflow.capacity - this.water.outflow.actual_rate)),
    )
    assert same(text, b)


def test_two_outflows_with_no_allocation_share_by_the_default():
    # The default allocation is proportional(); writing it gives the same program as writing none.
    text = 'tank:\n    water: L = 10 in [0,]\n    flow a: this.water -> SINK\n        request = 1 L/h\n'
    text += '    flow b: this.water -> SINK\n        request = 2 L/h\n'
    written = text.replace('in [0,]\n', 'in [0,]\n        outflow.allocation = proportional()\n')
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        flow('a', this.water, SINK, request=q(1, 'L/h')),
        flow('b', this.water, SINK, request=q(2, 'L/h')),
    )
    assert same(text, b)
    assert program_bytes(compiled(written).program) == program_bytes(compiled(text).program)


def test_a_setting_may_read_its_own_store():
    """Spec, "Local allocation": `inflow.request = formula(max(0 L, 15 L - this.water) / (2 h))` on
    the tank's water fills it towards 15 L; a setting is no starting value, so it makes no cycle."""
    text = """
        tank:
            water: L = 5 in [0,]
                inflow.request = formula(max(0 L, 15 L - this.water) / (2 h))
            flow fill: SOURCE -> this.water
        """
    b = Builder(UNITS)
    fill = formula(fmax(q(0, 'L'), q(15, 'L') - this.water) / q(2, 'h'))
    b.entity(
        'tank',
        value('water', 'L', 5, lower=0, inflow=endpoint(request=fill)),
        flow('fill', SOURCE, this.water),
    )
    assert same(text, b)


def test_a_junction_carries_its_inflow_through_a_store_held_at_zero():
    # Spec, "Capacity, request and bounds": a junction can carry 8 W through a stock held at 0 Wh.
    text = """
        junction:
            power: Wh = 0 in [0, 0]
            flow supply: SOURCE -> this.power
                capacity = 8 W
            flow use: this.power -> SINK
                request = 8 W
        """
    b = Builder(UNITS)
    b.entity(
        'junction',
        value('power', 'Wh', 0, lower=0, upper=0),
        flow('supply', SOURCE, this.power, capacity=q(8, 'W')),
        flow('use', this.power, SINK, request=q(8, 'W')),
    )
    assert same(text, b)
    declared = compiled(text).declared.part('junction.power')
    assert (declared.outflow, declared.inflow) == (None, None)


def test_the_settings_of_an_endpoint_are_a_part_with_a_path_and_a_line():
    model = compiled(CUSTOMERS).declared
    settings = model.part('reservoir.water.outflow')
    assert (settings.path, settings.line, settings.allocation[0]) == (
        'reservoir.water.outflow',
        4,
        'priority',
    )
    assert model.part('reservoir.water').outflow is settings


# ---- a where over an endpoint's flows -----------------------------------------------------------------

DELIVERIES = """
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


def test_a_where_over_an_endpoints_flows_compares_their_ends_as_the_builder_writes_it():
    """Spec, "Collections, keys and projections": a fixed-field filter over an endpoint collection.
    In its test `source` and `sink` are the member's ends, fixed for the flow's lifetime, on either
    side of `==` or `!=`; the program reads them as `item.sink` and `item.source`."""
    b = Builder(UNITS)
    b.entity('clinic', value('water', 'L', 0, lower=0))
    b.entity('garden', value('water', 'L', 0, lower=0))
    clinic = named('clinic').water
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        flow('a', this.water, clinic, request=q(1, 'L/h')),
        flow('b', this.water, named('garden').water, request=q(2, 'L/h')),
        flow('c', this.water, SINK, request=q(4, 'L/h')),
        value(
            'to_clinic', 'L/h', formula(fsum(this.water.outflow.flows.where(item.sink == clinic).actual_rate))
        ),
        value('elsewhere', '', formula(count(this.water.outflow.flows.where(clinic != item.sink)))),
        value('from_here', '', formula(count(clinic.inflow.flows.where(item.source == this.water)))),
    )
    assert same(DELIVERIES, b)


@pytest.mark.parametrize(
    ('test', 'code', 'words'),
    [
        ('sink >= clinic.water', 'type', 'compared with == or != to a stored number'),
        ('sink == 3 L', 'type', 'not to a number in L'),
        ('sink == clinic', 'type', 'not to a member of clinic'),
        ('sink', 'type', 'where takes a yes/no, not an end of a flow'),
        ('sink + 1 L == clinic.water', 'type', 'an end of a flow'),
        ('request > 1 L/h', 'where_live', 'the request of a flow is not'),
        ('actual_rate > 0 L/h', 'where_live', 'the actual_rate of a flow is not'),
        ('sink == clinic.water.inflow', 'type', 'is no value'),
        ('sink.outflow.actual_rate > 0 L/h', 'where_live', 'sink.outflow is not read there'),
    ],
)
def test_a_where_over_flows_tests_their_ends_by_identity_and_nothing_live(test, code, words):
    text = DELIVERIES.replace('where(sink == clinic.water)', f'where({test})')
    found = refused(text, code, 14)
    assert words in found.message, found


def test_a_where_over_flows_compares_an_end_with_a_store_of_their_quantity():
    text = DELIVERIES.replace('    garden:\n', '    meter:\n        power: Wh = 0 in [0,]\n    garden:\n')
    text = text.replace('where(sink == clinic.water)', 'where(sink == meter.power)')
    found = refused(text, 'unit', 16)
    assert 'these flows carry L/h, and power holds Wh' in found.message, found


def test_a_projection_of_declared_flows_takes_its_where_before_the_projection():
    text = """
        Customer:
            water: L = 0 in [0,]
        tank:
            water: L = 10 in [0,]
        x = formula(count(Customer.instances.water.inflow.flows.where(source == tank.water)))
        """
    refused(text, 'collection', 6)
    text = """
        Customer:
            water: L = 0 in [0,]
            flow fill: tank.water -> this.water
                request = 1 L/h
        tank:
            water: L = 10 in [0,]
        x = formula(count(Customer.instances.fill.where(source == tank.water)))
        """
    found = refused(text, 'collection', 8)
    assert 'Template.instances.where(...).fill' in found.message, found


# ---- refusals ---------------------------------------------------------------------------------------

STORE = 'tank:\n    water: L = 10\n{settings}    flow a: this.water -> SINK\n{rest}'


@pytest.mark.parametrize(
    ('settings', 'rest', 'code', 'line', 'words'),
    [
        ('        outflow.size = 1 L/h\n', '', 'property', 3, 'no setting of a store'),
        ('        flows = 1\n', '', 'property', 3, 'no setting of a store'),
        ('        outflow.capacity = 1 L\n', '', 'unit', 3, 'a rate in L/h, not L'),
        ('        outflow.capacity = 2\n', '', 'unit', 3, 'a rate in L/h'),
        ('        inflow.request = 1 L/h\n        inflow.request = 2 L/h\n', '', 'property', 4, 'twice'),
        ('        outflow.allocation = 3\n', '', 'allocation', 3, 'priority(...) or proportional()'),
        ('        outflow.allocation = priority()\n', '', 'arguments', 3, 'names the flows'),
        ('        outflow.allocation = proportional(this.a)\n', '', 'arguments', 3, 'takes no argument'),
        ('        outflow.allocation = priority(this.a, this.a)\n', '', 'priority_item', 3, 'each flow once'),
        ('        outflow.allocation = priority(this.water)\n', '', 'priority_item', 3, 'not L'),
        (
            '        outflow.allocation = priority(this.water.outflow.flows)\n',
            '',
            'priority_item',
            3,
            "an endpoint's collection of flows",
        ),
        # Incidence is the program's rule: the checker's refusal is given at the line of the setting.
        (
            '        outflow.allocation = priority(other.b)\n',
            'other:\n    w: L = 1\n    flow b: this.w -> SINK\n',
            'priority_item',
            3,
            'not at this endpoint',
        ),
        ('', '    x = priority(this.a)\n', 'allocation', 4, 'is an allocation, no value'),
        ('', '    x = formula(this.water.outflow)\n', 'type', 4, 'is no value'),
        ('', '    x = formula(this.water.outflow.allocation)\n', 'allocation', 4, 'is no value'),
        ('', '    x = formula(this.water.outflow.share)\n', 'unknown_name', 4, 'not share'),
        ('', '    x = this.water.inflow.flows\n', 'collection', 4, 'collection of flows'),
        ('', '    x = formula(this.water.inflow.flows)\n', 'formula', 4, 'not a member or a collection'),
    ],
)
def test_a_setting_or_a_read_of_an_endpoint_is_refused_with_its_code(settings, rest, code, line, words):
    found = refused(STORE.format(settings=settings, rest=rest), code, line)
    assert words in found.message, found


@pytest.mark.parametrize(
    ('text', 'code', 'line', 'words'),
    [
        (
            'tank:\n    input water: L = 10\n        outflow.capacity = 1 L/h\n',
            'property',
            3,
            'no stored number',
        ),
        (
            'tank:\n    input water: L = 10\n    x = formula(this.water.outflow.actual_rate)\n',
            'flow_end',
            3,
            'no stored number',
        ),
        (
            'Tank:\n    water: L = 10\nsink:\n    flow f: Tank.instances.water -> SINK\n        request = 1 L/h\n',
            'flow_end',
            4,
            'is a projection',
        ),
        (
            'tank:\n    input water: L = 10\n    flow f: this.water -> SINK\n        request = 1 L/h\n',
            'flow_end',
            3,
            'no stored number',
        ),
        (
            'tank:\n    water: L = 10\n    flow f: this.water -> SINK\n        outflow.capacity = 1 L/h\n',
            'property',
            4,
            'takes request and capacity',
        ),
        (
            'Place:\n    power: Wh = 0\nRoute:\n    origin: Place\n    flow f: this.origin.pwr -> SINK\n',
            'flow_end',
            5,
            'this.origin.pwr is no stored number of Place',
        ),
        (
            'Place:\n    power: Wh = 0\nRoute:\n    origin: Place\n    flow f: this.orign.power -> SINK\n',
            'unknown_name',
            5,
            'did you mean origin',
        ),
        (
            'tank:\n    water: L = 10\n    flow f: this.water -> pump.water\n',
            'unknown_name',
            3,
            'names nothing',
        ),
    ],
)
def test_a_wrong_end_of_a_flow_is_refused_with_its_code(text, code, line, words):
    found = refused(text, code, line)
    assert words in found.message, found
