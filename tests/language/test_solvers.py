"""Solvers in the front end (slice S5): the text of each example of `tests/program/examples.py` with a
solver gives a program with the canonical bytes of the example's, also with the tables of the worked
network reordered; what a solver reads and what a caller reads of it; and the refusals by their
codes: the forms that the constraint language leaves out (`solver_form`), nonlinear and yes-or-no
problems (`nonlinear`), missing participants (`participant`), two solvers in one connected set of
flows and stores (`two_solvers`, which names both), and what an input, a `solve_for` entry and a
caller may not do."""

import textwrap

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.format import format_text
from napkin.model.language.parse import parse
from napkin.model.language.problems import LanguageError
from napkin.program import parts as p
from napkin.program.canonical import program_bytes
from napkin.program.refs import THIS, Instances, Local, Path
from tests.program.examples import EXAMPLES, UNITS

# ---- the texts of the examples -------------------------------------------------------------------

# The entities stand in the order in which the example declares them, so that the templates of the
# two programs stand in one order.
STAFFING_SOLVER = """
        staffing = solver:
            inputs:
                available = this.staff_hours
                minimum_outreach = this.outreach_minimum
            solve_for:
                care: h in [0 h, available]
                outreach: h in [minimum_outreach, available]
            constraints:
                care + outreach == available
            objective:
                maximize(care)"""
JUNCTIONS = """
    second:
        water: L = 0 in [0, 0]
        flow to_b: this.water -> SINK
            request = 1 L/h
        flow to_c: this.water -> SINK
            request = 1 L/h

    first:
        water: L = 0 in [0, 0]
        flow feed: SOURCE -> this.water
            capacity = 1 L/h
        flow to_a: this.water -> SINK
            request = 1 L/h
        flow onward: this.water -> second.water
            request = 1 L/h

    provider:
        fair = solver:
            inputs:
                a = first.to_a
                onward = first.onward
                b = second.to_b
                c = second.to_c
            solve_for:
                a.actual_rate
                onward.actual_rate
                b.actual_rate
                c.actual_rate
    """
NETWORK = """
    Reading:
        input hour: h = 0
        input factor = 1

    Place:
        input base_need: {power} = 0
        input supply_limit: {power} = 0
        input critical: bool = false
        level = 0 in [-30, 30]
        power: {energy} = 0 in [0, 0]
        need = formula(this.base_need * Reading.instances.by(hour).at(t).factor)
        flow supply: SOURCE -> this.power
            capacity = this.supply_limit
        flow use: this.power -> SINK
            request = formula(this.need)
            capacity = formula(this.need)
        unmet = formula(max(0 {power}, this.use.request - this.use.actual_rate))

    Route:
        origin: Place
        destination: Place
        input strength: {power} = {strength}
        input closes_at_two: bool = false
        up: bool = true
        pull = formula(this.strength if this.up else 0 {power})
        flow carried: this.origin.power <-> this.destination.power
        rate_follows_levels = formula(this.carried.actual_rate == this.pull * (this.origin.level - this.destination.level))
        close = event():
            when this.closes_at_two and t >= 2 h:
                this.close.start()
                reset when false
            after 0 h:
                this.up = false

    sites: Place from "places.csv"
    links: Route from "routes.csv"
    readings: Reading from "readings.csv"

    provider:
        dispatch = solver:
            inputs:
                places = Place.instances
                routes = Route.instances
            solve_for:
                places.level
                places.supply.actual_rate
                places.use.actual_rate
                routes.carried.actual_rate
            constraints:
                all(routes.rate_follows_levels)
            objective:{objective}
    """
CLINIC_FIRST = '\n                minimize(sum(places.where(critical).unmet))'
TOTAL = '\n                minimize(sum(places.unmet))'
# The spec's files, "Worked network data and expected rates".
PLACES = ['junction,{supply},0,false', 'clinic,0,{clinic},true', 'garden,0,{garden},false']
ROUTES = [
    'junction_clinic,sites.junction,sites.clinic,false',
    'garden_junction,sites.garden,sites.junction,true',
]
READINGS = 'hour: h,factor\n0,1\n1,0.5\n2,1\n'


def network(power='W', clinic_first=False, supply=8, clinic=6, garden=6, reverse=False):
    """The worked network's text and its three files; with `reverse`, the rows of the places and of
    the routes in the reverse order."""
    text = NETWORK.format(
        power=power,
        energy='Wh' if power == 'W' else 'kWh',
        strength=1 if power == 'W' else 0.001,
        objective=(CLINIC_FIRST if clinic_first else '') + TOTAL,
    )
    places = [row.format(supply=supply, clinic=clinic, garden=garden) for row in PLACES]
    routes = list(ROUTES)
    if reverse:
        places.reverse()
        routes.reverse()
    tables = {
        'places.csv': '\n'.join([f'id,supply_limit: {power},base_need: {power},critical', *places]) + '\n',
        'routes.csv': '\n'.join(['id,origin,destination,closes_at_two', *routes]) + '\n',
        'readings.csv': READINGS,
    }
    return text, tables


BOTTLENECKS = """
    Consumer:
        received: Wh = 0 in [0,]
        flow use: SOURCE -> this.received
            request = 6 W
            capacity = 6 W
        unmet = formula(max(0 W, this.use.request - this.use.actual_rate))

    a: Consumer
    b: Consumer
    c: Consumer

    provider:
        allocation = solver:
            inputs:
                consumers = Consumer.instances
                use_a = a.use
                use_b = b.use
                use_c = c.use
            solve_for:
                consumers.use.actual_rate
            constraints:
                use_a.actual_rate + use_b.actual_rate <= 4 W
                use_b.actual_rate + use_c.actual_rate <= 5 W{objective}

    total_unmet = formula(sum(Consumer.instances.unmet))
    """
STAFFING = f"""
    clinic:
        staff_hours: h = 100 h
        outreach_minimum = formula(0.30 * this.staff_hours)
        planned: bool = false{STAFFING_SOLVER}
        plan = event():
            after 1 h:
                this.staff_hours = 80 h
            after this.staffing.care:
                this.planned = true

    clinic.plan.start()
    """
TWO_WRITES = f"""
    office:
        staff_hours: h = 100 h
        outreach_minimum = formula(0.30 * this.staff_hours){STAFFING_SOLVER}
        lower = event():
            after 1 h:
                this.staff_hours = 90 h
        trim = event():
            after 1 h:
                this.staff_hours -= 10 h
        restore = event():
            when this.staffing.care <= 60 h:
                this.restore.start()
                reset when false
            after 0 h:
                this.staff_hours = 100 h

    office.lower.start()
    office.trim.start()
    """
PUMP = """
    tank:
        water: L = {water} in [0, 20]

    battery:
        energy: Wh = 0 in [0, 4]
        flow charge: SOURCE -> this.energy
            capacity = 1 W

    pump:
        flow fill: SOURCE -> tank.water
            capacity = 4 L/h
        flow power: battery.energy -> SINK

    clinic:
        flow delivery: tank.water -> SINK
            request = {request} L/h

    town:
        flow delivery: tank.water -> SINK
            request = {request} L/h

    provider:
        distribution = solver:
            inputs:
                charge = battery.charge
                motor = pump.power
                fill = pump.fill
                clinic_use = clinic.delivery
                town_use = town.delivery
            solve_for:
                charge.actual_rate
                motor.actual_rate
                fill.actual_rate
                clinic_use.actual_rate
                town_use.actual_rate
            constraints:
                motor.actual_rate == fill.actual_rate * (0.5 Wh/L)
            objective:
                minimize(max(0 L/h, clinic_use.request - clinic_use.actual_rate))
                minimize(max(0 L/h, town_use.request - town_use.actual_rate))
                minimize(fill.actual_rate)
                minimize(charge.actual_rate)
    """
PROVIDER = """
    east_site:
        energy: Wh = 0 in [0, 10]
        flow charge: SOURCE -> this.energy
            capacity = 6 W
            request = {east} W

    west_site:
        energy: Wh = 0 in [0, 10]
        flow charge: SOURCE -> this.energy
            capacity = 6 W
            request = 6 W

    provider:
        contract_limit: W = 8 W
        charging = solver:
            inputs:
                east = east_site.charge
                west = west_site.charge
                limit = this.contract_limit
            solve_for:
                east.actual_rate
                west.actual_rate
            constraints:
                east.actual_rate + west.actual_rate <= limit
            objective:
                minimize(max(0 W, east.request - east.actual_rate))
                minimize(max(0 W, west.request - west.actual_rate))
                minimize(east.actual_rate + west.actual_rate)
    """
DISTANCE = """
    plan:
        split = solver:
            solve_for:
                x: number = {target}
                y: number = {target}
            constraints:
                {test}
    """
SOURCES = {
    'two_junctions_solver': (JUNCTIONS, None),
    'network': network(),
    'network_clinic_first': network(clinic_first=True),
    'network_unequal': network(supply=4, clinic=2),
    'network_kw': network(power='kW', supply=0.008, clinic=0.006, garden=0.006),
    'two_bottlenecks_fair': (BOTTLENECKS.format(objective=''), None),
    'two_bottlenecks_total_unmet': (
        BOTTLENECKS.format(
            objective='\n            objective:\n                minimize(sum(consumers.unmet))'
        ),
        None,
    ),
    'staffing': (STAFFING, None),
    'two_writes_one_solve': (TWO_WRITES, None),
    'pump_battery': (PUMP.format(water=0, request=6), None),
    'pump_battery_stocked': (PUMP.format(water=10, request=6), None),
    'pump_battery_idle': (PUMP.format(water=0, request=0), None),
    'provider_limit': (PROVIDER.format(east=6), None),
    'provider_limit_east_low': (PROVIDER.format(east=2), None),
    'distance_targets_zero': (DISTANCE.format(target=0, test='4 <= x + y <= 6'), None),
    'distance_targets_five': (DISTANCE.format(target=5, test='4 <= x + y <= 6'), None),
    'distance_equality': (DISTANCE.format(target=0, test='x + y == 1'), None),
}


def compiled(text, tables=None):
    return compile_text(textwrap.dedent(text), UNITS, tables=tables)


@pytest.mark.parametrize('name', sorted(SOURCES))
def test_the_text_of_an_example_lowers_to_its_program(name):
    text, tables = SOURCES[name]
    assert program_bytes(compiled(text, tables).program) == program_bytes(EXAMPLES[name]().program)


def test_the_text_of_each_example_formats_to_a_text_of_the_same_tree():
    for written, _ in SOURCES.values():
        text = textwrap.dedent(written)
        once = format_text(text)
        assert parse(once) == parse(text)
        assert format_text(once) == once


def test_a_range_test_in_a_constraint_is_the_chain_of_its_two_relations():
    found = compiled(DISTANCE.format(target=0, test='x + y in [4, 6]')).program
    assert program_bytes(found) == program_bytes(EXAMPLES['distance_targets_zero']().program)


def test_each_example_with_a_solver_has_its_text():
    with_solvers = {
        name
        for name, make in EXAMPLES.items()
        if any(template.solvers for template in make().program.templates)
    }
    assert with_solvers == set(SOURCES)


def test_the_worked_network_with_its_tables_reordered_gives_the_same_program():
    """Spec, "Worked network data and expected rates": reorder either file, or both, without editing
    a link cell; each route keeps its ends, so the program is the same."""
    text, tables = network(reverse=True)
    assert program_bytes(compiled(text, tables).program) == program_bytes(EXAMPLES['network']().program)


# ---- what a solver reads, and what a caller reads of it -------------------------------------------


def test_a_bare_name_of_a_solver_is_an_input_or_an_unknown():
    (solver,) = compiled(STAFFING).program.templates[0].solvers
    assert [(item.name, item.source) for item in solver.inputs] == [
        ('available', Path(THIS, ('staff_hours',))),
        ('minimum_outreach', Path(THIS, ('outreach_minimum',))),
    ]
    care, outreach = solver.unknowns
    assert (care.name, care.kind, care.type, care.init) == ('care', p.STATE, p.Number('h'), None)
    assert dict(outreach.lower.reads) == {'minimum_outreach': Path(Local('minimum_outreach'))}
    text, tables = network()
    (dispatch,) = compiled(text, tables).program.templates[-1].solvers
    assert dispatch.inputs[0].source == Path(Instances('Place'))
    assert dispatch.solve_for[1] == Path(Local('places'), ('supply', 'actual_rate'))


def test_a_caller_reads_the_unknowns_of_a_solver_by_their_paths():
    """Spec, "Time, waiting and completion": a delay of `this.staffing.care`."""
    program = compiled(STAFFING).program
    step = program.templates[0].events[0].steps[1]
    assert dict(step.delay.reads) == {'this.staffing.care': Path(THIS, ('staffing', 'care'))}


def test_a_solver_accepts_the_forms_of_its_language():
    """Affine relations and their conjunction, a bound on a sum, a positive part on the small side,
    a route's leg (the positive part of its rate), an endpoint whose flows the solver determines,
    a known coefficient chosen by a condition, a scaled unknown, and another solver's result as a
    known value of this one."""
    compiled("""
        tank:
            water: L = 10 in [0, 20]
            open: bool = true
            flow fill: SOURCE -> this.water
                capacity = 4 L/h

        other:
            water: L = 10 in [0, 20]
            flow link: tank.water <-> this.water

        Taker:
            flow draw: tank.water -> SINK
                request = 3 L/h

        east: Taker
        west: Taker

        planner:
            first = solver:
                solve_for:
                    x: L/h in [0 L/h, 9 L/h] scale 2 L/h
                objective:
                    maximize(x)

        provider:
            plan = solver:
                inputs:
                    draws = <east, west>
                    limit = planner.first.x
                solve_for:
                    tank.fill.actual_rate
                    other.link.actual_rate
                    draws.draw.actual_rate
                    spare: L/h = 1 L/h in [0 L/h, limit]
                constraints:
                    sum(draws.draw.actual_rate) <= limit and spare <= 2 L/h
                    max(0 L/h, spare - 1 L/h) <= 3 L/h
                    other.link.forward.actual_rate - 1 L/h <= 3 L/h
                    tank.water.outflow.actual_rate <= (5 L/h if tank.open else 0 L/h)
                    other.link.backward.actual_rate + spare <= 4 L/h
                objective:
                    minimize(max(0 L/h, east.draw.request - east.draw.actual_rate))
                    maximize(2 * spare - tank.fill.actual_rate)
        """)


def test_the_solvers_of_members_on_their_own_stores_need_no_coordinator():
    """Each member's solver decides the rate of its own store's flow, and no store joins two."""
    compiled("""
        Site:
            stock: L = 0 in [0, 10]
            flow fill: SOURCE -> this.stock
                capacity = 2 L/h
            plan = solver:
                inputs:
                    own = this.fill
                solve_for:
                    own.actual_rate
                objective:
                    maximize(own.actual_rate)

        a: Site
        b: Site
        """)


# ---- refusals ---------------------------------------------------------------------------------------

# A provider that determines two draws from one tank and an unknown; each case writes one line of its
# constraints, or of its objective.
MODEL = """
    tank:
        water: L = 10 in [0, 20]
        flow fill: SOURCE -> this.water
            capacity = 4 L/h

    east:
        flow draw: tank.water -> SINK
            request = 3 L/h

    west:
        on: bool = true
        flow draw: tank.water -> SINK
            request = 3 L/h

    Taker:
        flow draw: tank.water -> SINK
            request = 1 L/h
        low = formula(this.draw.actual_rate <= 1 L/h)

    north: Taker
    south: Taker

    Reading:
        input hour: h = 0
        input factor = 1

    first: Reading

    provider:
        limit: L/h = 5 L/h
        half = formula(this.limit / 2)
        plan = solver:
            inputs:
                e = east.draw
                w = west.draw
                takers = Taker.instances
            solve_for:
                e.actual_rate
                w.actual_rate
                takers.draw.actual_rate
                x: L/h in [0 L/h, 10 L/h]
                y: number in [0, 1]
                z: h in [0 h, 2 h]
            {section}:
                {line}
    """


def refused(text, tables=None):
    with pytest.raises(LanguageError) as caught:
        compiled(text, tables)
    return caught.value


def line_of(text, written):
    """The last line of the file that is a line as written."""
    lines = textwrap.dedent(text).splitlines()
    return max(k + 1 for k, line in enumerate(lines) if line.strip() == written)


@pytest.mark.parametrize(
    ('section', 'line', 'code', 'words'),
    [
        ('constraints', 'e.actual_rate < 2 L/h', 'solver_form', 'strict inequality'),
        ('constraints', 'e.actual_rate > 2 L/h', 'solver_form', 'strict inequality'),
        ('constraints', 'e.actual_rate != 2 L/h', 'solver_form', '!='),
        ('constraints', 'e.actual_rate <= 2 L/h or w.actual_rate <= 2 L/h', 'solver_form', 'disjunction'),
        ('constraints', 'any(takers.low)', 'solver_form', 'any(...)'),
        ('constraints', 'all(takers.low) or x <= 1 L/h', 'solver_form', 'disjunction'),
        ('constraints', 'not (e.actual_rate <= 2 L/h)', 'solver_form', 'not of a relation'),
        ('constraints', 'west.on and e.actual_rate <= 2 L/h', 'solver_form', 'under a condition'),
        ('constraints', '(x <= 1 L/h) if west.on else (x <= 2 L/h)', 'solver_form', 'under a condition'),
        ('constraints', '0 L/h <= limit_of_none', 'unknown_name', 'names nothing'),
        ('constraints', '1 L/h <= 2 L/h <= x', 'solver_form', 'under a condition'),
        ('constraints', '(1 L/h if x <= 2 L/h else 0 L/h) <= e.actual_rate', 'solver_form', 'test'),
        ('constraints', 'Reading.instances.by(hour).at(z).factor <= y', 'solver_form', 'lookup'),
        ('constraints', 'x * y <= 2 L/h', 'nonlinear', 'product'),
        ('constraints', 'e.actual_rate / y <= 2 L/h', 'nonlinear', 'division'),
        ('constraints', 'abs(x) <= 2 L/h', 'nonlinear', 'abs'),
        ('constraints', 'min(x, e.actual_rate) <= 2 L/h', 'nonlinear', 'min'),
        ('constraints', 'max(0 L/h, x) >= 1 L/h', 'nonlinear', 'large side'),
        ('constraints', 'x == max(0 L/h, e.actual_rate)', 'nonlinear', 'large side'),
        ('constraints', '(-max(0 L/h, x)) <= 1 L/h', 'nonlinear', 'negative of a positive part'),
        ('constraints', '1 L/h - max(0 L/h, x) <= 1 L/h', 'nonlinear', 'subtracted'),
        ('constraints', '(-2) * max(0 L/h, x) <= 1 L/h', 'nonlinear', 'negative number'),
        ('constraints', 'max(0 L/h, x) / (-2) <= 1 L/h', 'nonlinear', 'negative number'),
        ('constraints', 'max(0 L/h, max(0 L/h, x) - 1 L/h) <= 2 L/h', 'nonlinear', 'positive part of'),
        ('constraints', 'y ** 2 <= 1', 'nonlinear', 'power'),
        ('constraints', 'tank.fill.actual_rate <= 2 L/h', 'participant', 'tank.fill'),
        ('constraints', 'tank.water.inflow.actual_rate <= 2 L/h', 'participant', 'tank.fill'),
        ('constraints', 'provider.limit <= 6 L/h', 'participant', 'reads nothing'),
        ('constraints', 'e.actual_rate', 'type', 'a constraint takes a yes/no'),
        ('objective', 'minimize(provider.limit)', 'participant', 'ranks no answer'),
        ('objective', 'maximize(max(0 L/h, x))', 'nonlinear', 'maximize of a positive part'),
        ('objective', 'minimize(e.actual_rate <= 1 L/h)', 'type', 'takes numbers'),
        ('objective', 'minimize(tank.fill.actual_rate)', 'participant', 'tank.fill'),
    ],
)
def test_a_constraint_or_an_objective_outside_the_language_is_refused_by_name(section, line, code, words):
    """Spec, "Using collections in a solver" and "Final targets for flows and other unknowns": the
    language of a solver is affine relations and their conjunction, and objectives that are affine or
    minimized sums of positive parts; a rate that it reads is its own."""
    text = MODEL.format(section=section, line=line)
    error = refused(text)
    assert error.codes == [code], error
    (problem,) = error.problems
    assert words in problem.message, problem.message
    assert problem.line == line_of(text, line)


@pytest.mark.parametrize(
    ('entry', 'code', 'words'),
    [
        ('ok: bool', 'nonlinear', 'yes-or-no'),
        ('state: enum[ON, OFF]', 'nonlinear', 'yes-or-no'),
        ('west.on', 'nonlinear', 'yes-or-no'),
        ('provider.half', 'solve_for', 'cannot determine provider.half'),
        ('e.request', 'solve_for', 'cannot determine e.request'),
        ('tank.water.outflow.actual_rate', 'solve_for', 'total of an endpoint'),
        ('u: L/h in [0 L/h, x]', 'solver_form', 'the domain of u'),
        ('u: L/h = x', 'solver_form', 'the preferred value of u'),
        ('x: L/h', 'duplicate_name', 'declared twice'),
        ('e: L/h', 'duplicate_name', 'declared twice'),
    ],
)
def test_a_solve_for_entry_that_a_solver_cannot_determine_is_refused(entry, code, words):
    """Spec, "An entity owns its solver": `solve_for` names stored numbers, the rates of flows and
    routes and served fractions, or declares new unknowns, which are numbers."""
    text = MODEL.format(section='constraints', line='x + e.actual_rate <= 8 L/h').replace(
        '                z: h in [0 h, 2 h]\n',
        f'                z: h in [0 h, 2 h]\n                {entry}\n',
    )
    error = refused(text)
    assert error.codes == [code], error
    assert words in error.problems[0].message, error.problems[0].message
    assert error.problems[0].line == line_of(text, entry)


ROUTE_AND_LEGS = """
    west:
        water: L = 5 in [0, 10]
    east:
        water: L = 5 in [0, 10]
        crew: crew_h = 4 in [0, 8]
    channel:
        flow link: west.water <-> east.water
            capacity = 3 L/h
        flow restore:
            flow labor: east.crew -> SINK
                request = 2 crew_h/h
            flow work: east.water -> SINK
                request = 1 L/h
    provider:
        plan = solver:
            solve_for:
                {entry}
    """


@pytest.mark.parametrize(
    ('entry', 'words'),
    [
        ('channel.link.forward.actual_rate', 'name channel.link.actual_rate'),
        ('channel.restore.labor.actual_rate', 'name channel.restore.served_fraction'),
    ],
)
def test_a_leg_is_determined_through_its_route_or_its_fraction(entry, words):
    """Spec, "Flows and algebraic solvers": in `solve_for`, name `link.actual_rate` for the route's
    one decision variable (its directional rates are derived), and a flow with legs has one
    `served_fraction`."""
    error = refused(ROUTE_AND_LEGS.format(entry=entry))
    assert error.codes == ['solve_for'] and words in error.problems[0].message, error


def test_a_route_and_a_flow_with_legs_are_determined_by_their_rate_and_their_fraction():
    program = compiled(
        ROUTE_AND_LEGS.format(
            entry='channel.link.actual_rate\n                channel.restore.served_fraction'
        )
    ).program
    assert len(program.templates[-1].solvers[0].solve_for) == 2


@pytest.mark.parametrize(
    ('replace', 'by', 'code', 'words'),
    [
        ('e = east.draw', 'e = east.draw.request * 2', 'solver_input', 'by its path'),
        ('e = east.draw', 'e = t', 'solver_input', 'the time'),
        ('w = west.draw', 'w = west.draw\n                e = tank.fill', 'duplicate_name', 'twice'),
        (
            '    limit: L/h = 5 L/h',
            '    limit: L/h = 5 L/h\n        copy = formula(provider.plan.e.request)',
            'unknown_name',
            'e is an input',
        ),
        (
            '    limit: L/h = 5 L/h',
            '    limit: L/h = 5 L/h\n        copy = formula(provider.plan)',
            'type',
            'a solver is no value',
        ),
        (
            '    limit: L/h = 5 L/h',
            '    limit: L/h = 5 L/h\n        copy = formula(provider.plan.q)',
            'unknown_name',
            'publishes the unknowns',
        ),
        (
            '    limit: L/h = 5 L/h',
            '    limit: L/h = 5 L/h\n        since_x = formula(elapsed(provider.plan.x))',
            'history',
            "solver's result",
        ),
        (
            '    limit: L/h = 5 L/h',
            '    limit: L/h = 5 L/h\n        cut = event():\n            after 1 h:\n'
            '                this.plan.x = 2 L/h',
            'result_write',
            'read-only to its callers',
        ),
    ],
)
def test_an_input_and_a_caller_of_a_solver_are_refused_by_their_codes(replace, by, code, words):
    text = MODEL.format(section='constraints', line='x + e.actual_rate <= 8 L/h').replace(replace, by)
    error = refused(text)
    assert error.codes == [code], error
    assert words in error.problems[0].message, error.problems[0].message


def test_a_member_gives_its_template_no_solver():
    error = refused("""
        Site:
            stock: L = 0 in [0, 10]
            plan = solver:
                solve_for:
                    this.stock

        a: Site
            plan = 2
        """)
    assert error.codes == ['property'] and 'solver of Site' in error.problems[0].message


def test_a_value_that_a_solver_determines_and_a_stage_writes_has_two_writers():
    """Spec, "Solver and execution contract": one writer determines each result (the program's
    rule, at the line of the solver)."""
    text = """
        plan:
            level: L = 0 in [0, 5]
            split = solver:
                solve_for:
                    this.level
                objective:
                    maximize(this.level)
            raise_it = event():
                after 1 h:
                    this.level = 2 L
        """
    error = refused(text)
    assert error.codes == ['two_writers'], error
    assert error.problems[0].line == line_of(text, 'split = solver:')


# ---- one coordinating solver ------------------------------------------------------------------------

SHARED = """
    tank:
        water: L = 10 in [0, 20]
        flow fill: SOURCE -> this.water
            capacity = 4 L/h

    east:
        flow draw: tank.water -> SINK
            request = 3 L/h

    west:
        flow draw: {west_from} -> SINK
            request = 3 L/h

    other:
        water: L = 10 in [0, 20]

    east_provider:
        plan = solver:
            inputs:
                own = east.draw
            solve_for:
                own.actual_rate
            objective:
                maximize(own.actual_rate)

    west_provider:
        plan = solver:
            inputs:
                own = west.draw
            solve_for:
                own.actual_rate
            objective:
                maximize(own.actual_rate)
    """


def test_two_solvers_that_would_compete_for_one_store_are_refused_with_both_named():
    """Spec, "An entity owns its solver": when two declared solvers would each choose rates that
    compete for one binding hard resource, the model is refused with a diagnostic that names both."""
    text = SHARED.format(west_from='tank.water')
    error = refused(text)
    assert error.codes == ['two_solvers'], error
    (problem,) = error.problems
    assert 'east_provider.plan and west_provider.plan' in problem.message
    assert 'one coordinating solver' in problem.message
    assert problem.line == line_of(text, 'plan = solver:')
    # The draws from two stores that nothing joins compete for nothing.
    compiled(SHARED.format(west_from='other.water'))


def test_two_solvers_joined_through_a_flow_that_neither_determines_are_refused():
    """A flow between the two stores joins them in one connected set, even when no solver names it."""
    text = SHARED.format(west_from='other.water').replace(
        '    other:\n        water: L = 10 in [0, 20]\n',
        '    other:\n        water: L = 10 in [0, 20]\n        flow pipe: tank.water -> this.water\n',
    )
    assert refused(text).codes == ['two_solvers']


def test_the_solvers_of_two_members_on_one_store_are_refused_with_both_named():
    error = refused("""
        hub:
            water: L = 10 in [0, 20]

        Site:
            flow draw: hub.water -> SINK
                request = 1 L/h
            plan = solver:
                inputs:
                    own = this.draw
                solve_for:
                    own.actual_rate
                objective:
                    maximize(own.actual_rate)

        a: Site
        b: Site
        """)
    assert error.codes == ['two_solvers'] and 'a.plan and b.plan' in error.problems[0].message


def test_the_solvers_of_members_that_each_name_every_rate_are_refused():
    """Each member's solver would choose the rates of every member: one solver must own them."""
    text = """
        Site:
            stock: L = 0 in [0, 10]
            flow fill: SOURCE -> this.stock
                capacity = 2 L/h
            plan = solver:
                inputs:
                    sites = Site.instances
                solve_for:
                    sites.fill.actual_rate
                objective:
                    maximize(sum(sites.fill.actual_rate))
        """
    members = ''.join(f'site_{k}: Site\n' for k in range(2000))
    error = refused(textwrap.dedent(text).rstrip() + '\n\n' + members)
    assert error.codes == ['two_solvers'] and 'site_0.plan and site_1.plan' in error.problems[0].message


def test_two_solvers_of_one_flow_are_two_writers():
    """Two solvers that name one rate are refused by the program's rule, which names both."""
    error = refused(SHARED.format(west_from='tank.water').replace('own = west.draw', 'own = east.draw'))
    assert error.codes == ['two_writers'], error
    assert 'east_provider.plan' in error.problems[0].message
    assert 'west_provider.plan' in error.problems[0].message
