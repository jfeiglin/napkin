"""Events, occurrences and time in the front end (slice S4): the text of each example of
`tests/program/examples.py` that this slice lowers gives a program with the canonical bytes of the
example's; and the refusals of events, stages, triggers, enums, draws and choices, each by its code."""

import textwrap

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.format import format_text
from napkin.model.language.parse import parse
from napkin.model.language.problems import LanguageError
from napkin.program import parts as p
from napkin.program.canonical import program_bytes
from napkin.program.refs import THIS, Elapsed, Local, Lookup, Path, Since
from tests.program.examples import EXAMPLES, UNITS

# The spec's text of each example of S4. The entities stand in the order in which the example
# declares them, so that the templates of the two programs stand in one order.
GRINDER = """
    grinder:
        beans: g = 8
        readonly low_on_beans = formula(this.beans <= 10 g)
        refill = event(amount: g):
{body}
    grinder.refill.start(50 g)
    """
INSPECT = """
    plant:
        safe: bool = true
        clearance_received: bool = false
        inspect = event(delay: h):
            after delay:
                delay = 2 h
            after delay when this.safe:
                this.inspect_equipment.start()
            until this.clearance_received
            after 0 h:
                this.record_clearance.start()
        inspect_equipment = event():
        record_clearance = event():
        outage = event():
            when t >= {at} h:
                this.outage.start()
                reset when false
            after 0 h:
                this.safe = false
            after {lasting} h:
                this.safe = true
        clear = event():
            when t >= 6 h:
                this.clear.start()
                reset when false
            after 0 h:
                this.clearance_received = true

    plant.inspect.start(3 h)
    """
RAMP = """
    tank:
        water: L = 0 in [0,]
        receive = event(amount: L, starting_rate: L/h, rate_change: L/h/h):
            remaining: L = amount in [0 L, amount]
            readonly started_at: h = t
            flow delivery: remaining -> this.water
                request = formula(max(0 L/h, starting_rate + rate_change * (t - started_at)))
            until remaining <= 0 L

    tank.receive.start(20 L, 5 L/h, {change} L/h/h)

    started = formula(count(tank.receive.occurrences))
    completed = formula(count(tank.receive.occurrences.done))
    """
MOVE = """
    left:
        readonly water: L = 8 in [0,]

    right:
        readonly water: L = 0 in [0, 4]

    mover:
        shift = event(amount: L):
            after 0 h:
                move amount from left.water to right.water

    mover.shift.start({amount} L)
    """
CATEGORICAL = """
    machine:
        operational: bool = false
        parts = {parts}
        check = event():
            after 2 h:
                switch categorical(FIXED: 0.7, FAILED: 0.3).draw():
                    FIXED{guard}:
                        this.operational = true
                    FAILED:
                        this.repair.start()
        repair = event():
            after 0 h

    machine.check.start()

    repairs = formula(count(machine.repair.occurrences))
    """
# The acceptance example of item 15 of the plan's changes after G0: the dispatcher's forecast drawn
# into the occurrence's field `order`, and a switch on it, which a caller edits at a breakpoint.
DISPATCH = """
    dispatcher:
        forecast = categorical(SEND: 0, WAIT: 1)

    depot:
        spares = 1 in [0,]
        waits = 0
        request_pump = event():
            order: enum[SEND, WAIT] = WAIT
            after 0 h:
                order = dispatcher.forecast.draw()
                switch order:
                    SEND when this.spares >= 1:
                        this.send_pump.start()
                    WAIT:
                        this.waits += 1
        send_pump = event():
            after 0 h:
                this.spares -= 1

    depot.request_pump.start()

    sent = formula(count(depot.send_pump.occurrences))
    """
SCALAR_INPUT = """
    machine:
        operational: bool = false
        input repair_time = uniform(1 h, 3 h).draw() in [1 h, 12 h]
        repair = event():
            after this.repair_time:
                this.operational = true

    machine.repair.start()
    """
PINNED = """
    Customer:
        water: L = 0 in [0,]

    a: Customer
    b: Customer

    depot:
{depot}
    """
SEPARATE = """        deliver = event(customer: Customer):
            batch: L = 20 in [0,]
            flow pipe: batch -> customer.water
                request = 10 L/h
            until batch <= 0 L

    depot.deliver.start(a)
    depot.deliver.start(b)
"""
SHARED = """        supply: L = 40 in [0,]
            outflow.capacity = 10 L/h
        deliver = event(customer: Customer):
            flow pipe: this.supply -> customer.water
                request = 10 L/h
            until customer.water >= 20 L
{late}
    depot.deliver.start(a)
{second}"""
LATE = """            when t >= 1 h:
                this.deliver.start(b)
                reset when false
"""
WATER = """
    Utility:
        input demand: L/h = 10
        online: bool = true
        served: L = 0 in [0,]
        flow delivery: SOURCE -> this.served
            request = formula(this.demand)
            capacity = formula(this.demand if this.online else 0 L/h)
        unserved_rate = formula(max(0 L/h, this.demand - this.delivery.actual_rate))
        unserved: L = 0 in [0,]
        flow count_unserved: SOURCE -> this.unserved
            request = formula(this.unserved_rate)
        restore = event():
            when t >= 5 h:
                this.restore.start()
                reset when false
            after 0 h:
                this.online = true

    north: Utility
        online = false

    south: Utility
        demand = 4 L/h

    initial_unserved = sum(Utility.instances.unserved)
    unserved_volume = formula(sum(Utility.instances.unserved))
    unserved_now = formula(sum(Utility.instances.unserved_rate))
    """
SOURCES = {
    'grinder_refill': GRINDER.format(
        body="""            after 0.5 h:
                this.beans += amount
"""
    ),
    'grinder_trigger_and_manual': GRINDER.format(
        body="""            status: enum[WEIGHING, ADDED] = WEIGHING
            when this.low_on_beans:
                this.refill.start(50 g)
                reset when this.beans >= 30 g
            after 0.5 h:
                this.beans += amount
                status = ADDED
"""
    ),
    'deliveries_current_flows': """
        tank:
            water: L = 100 in [0,]
            deliver = event():
                flow pipe: this.water -> SINK
                    request = 2 L/h
                after 1 h
                when t >= 1 h:
                    this.deliver.start()
                    reset when false
                when t >= 3 h:
                    this.deliver.start()
                    reset when false

        started = formula(count(tank.deliver.occurrences))
        current = formula(count(tank.water.outflow.flows))
        requested = formula(sum(tank.water.outflow.flows.request))
        outflow = formula(tank.water.outflow.actual_rate)
        newest_request = formula(tank.deliver.occurrences.at(t).pipe.request)
        """,
    'deliveries_separate_batches': PINNED.format(depot=SEPARATE),
    'deliveries_shared_supply': PINNED.format(
        depot=SHARED.format(late='', second='    depot.deliver.start(b)\n')
    ),
    'deliveries_late_start': PINNED.format(depot=SHARED.format(late=LATE, second='')),
    'shared_limit': """
        depot:
            supply: L = 100 in [0,]
                outflow.capacity = 3 L/h
            deliver = event():
                flow pipe: this.supply -> SINK
                    request = 2 L/h
                after 2 h
                when t >= 1 h:
                    this.deliver.start()
                    reset when false

        depot.deliver.start()
        """,
    'same_round_writes': """
        jar:
            amount: g = 20
            set_low = event():
                after 0 h:
                    this.amount = 8 g
            add_some = event():
                after 0 h:
                    this.amount += 4 g

        jar.set_low.start()
        jar.add_some.start()
        """,
    'stage_sees_writes': """
        box:
            x = 1
            y = 0
            update = event():
                after 0 h:
                    this.x = 2
                    this.y = this.x

        box.update.start()
        """,
    'inspect_guard_read_once': INSPECT.format(at=4, lasting=0.5),
    'inspect_guard_false': INSPECT.format(at=4.5, lasting=1),
    'clock_trigger': """
        plant:
            inspections = 0
            inspect = event():
                when t >= 3 h:
                    this.inspect.start()
                    reset after 3 h
                after 0 h:
                    this.inspections += 1
        """,
    'alarm_cooldown': """
        plant:
            alarm: bool = true
            alarms = 0
            quiet = event():
                after 1 h:
                    this.alarm = false
                after 3 h:
                    this.alarm = true
            sound = event():
                when this.alarm:
                    this.sound.start()
                    reset after 3 h
                after 0 h:
                    this.alarms += 1

        plant.quiet.start()
        """,
    'crossing_drain': """
        tank:
            water: L = 11 in [0,]
            alarms = 0
            flow drain: this.water -> SINK
                request = 1 L/h
            alarm = event():
                when this.water <= 10 L:
                    this.alarm.start()
                    reset when false
                after 0 h:
                    this.alarms += 1
        """,
    'crossing_rejoin': """
        tank:
            water: L = 10 in [0,]
            flow fill: SOURCE -> this.water
                request = 1 L/h
            drain = event():
                flow pipe: this.water -> SINK
                    request = 2 L/h
                after 2 h
                when t >= 2 h:
                    this.drain.start()
                    reset when false
            alarm = event():
                when this.water >= 16 L:
                    this.alarm.start()
                    reset when false
        """,
    'retirement_failure': """
        customer:
            water: L = 0 in [0,]

        depot:
            supply: L = 100 in [0,]
            deliver = event():
                batch: L = 0 in [0, 20]
                flow out: batch -> customer.water
                    request = 4 L/h
                after 0 h:
                    move 20 L from this.supply to batch
                after 3 h

        depot.deliver.start()
        """,
    'rising_ramp': RAMP.format(change=5),
    'falling_ramp': RAMP.format(change=-2),
    'move_within_bounds': MOVE.format(amount=3),
    'move_over_bound': MOVE.format(amount=5),
    'frozen_formula': """
        counter:
            level = 7
            job = event():
                readonly total = formula(this.level + 4)
                after 1 h
            bump = event():
                after 0.5 h:
                    this.level = 10
                after 1.5 h:
                    this.level = 20

        counter.job.start()
        counter.bump.start()
        """,
    'lookup_below_first_key': """
        Reading:
            input hour: h = 0
            input factor = 1

        readings: Reading from "readings.csv"

        probe:
            copy = 0
            look = event():
                after 1 h:
                    this.copy = Reading.instances.by(hour).at(t).factor

        probe.look.start()
        """,
    'water_service_returns': WATER,
    'median_categorical': CATEGORICAL.format(parts=1, guard=''),
    'median_categorical_guarded': CATEGORICAL.format(parts=0, guard=' when this.parts >= 1'),
    'pump_dispatch_unattended': DISPATCH,
    'distribution_input': """
        machine:
            operational: bool = false
            input repair_times = uniform(1 h, 3 h)
            repair = event():
                duration: h = this.repair_times.draw()
                after duration:
                    this.operational = true

        machine.repair.start()
        """,
    'scalar_input_override': SCALAR_INPUT,
    'scalar_input_default': SCALAR_INPUT,
}
TABLES = {'lookup_below_first_key': {'readings.csv': 'hour: h,factor\n2,5\n'}}


def compiled(text, tables=None):
    return compile_text(textwrap.dedent(text), UNITS, tables=tables)


def refused(text, tables=None):
    with pytest.raises(LanguageError) as caught:
        compiled(text, tables)
    return caught.value


@pytest.mark.parametrize('name', sorted(SOURCES))
def test_the_text_of_an_example_lowers_to_its_program(name):
    found = compiled(SOURCES[name], TABLES.get(name)).program
    assert program_bytes(found) == program_bytes(EXAMPLES[name]().program)


# ---- what an event writes, reads and starts ----------------------------------------------------------


def program_of(text, tables=None):
    return compiled(text, tables).program


def test_a_start_on_a_collection_starts_one_occurrence_on_each_member():
    """Spec, "Calling an event on a collection": the path projects the event over the members."""
    found = program_of("""
        Machine:
            ok: bool = false
            repair = event(duration: h):
                after duration:
                    this.ok = true
        a: Machine
        b: Machine
        shop:
            machines = <a, b>
            fix = event():
                after 2 h:
                    this.machines.repair.start(3 h)
        shop.fix.start()
        """)
    (start,) = found.template('shop').events[0].steps[0].body
    assert (start.event.start, start.event.steps) == (THIS, ('machines', 'repair'))
    assert start.origin == 'shop.fix.step[0].do[0]' and found.setup[0].origin == 'setup[0]'


def test_if_else_and_the_reads_of_history_lower_to_their_parts():
    """Spec, "Choosing actions inside a stage" (D11) and "History and optional domain status"."""
    found = program_of("""
        plant:
            x = 1
            passes_test: bool = true
            operational: bool = false
            failed_tests = 0
            speeds = uniform(1 L/h, 3 L/h)
            mean_speed = formula(this.speeds.mean)
            since_fix = formula(since(this.fix))
            quiet = formula(elapsed(this.x))
            fix = event():
                after 0 h:
                    if this.passes_test:
                        this.operational = true
                    else:
                        this.failed_tests += 1
        """)
    plant = found.template('plant')
    (branch,) = plant.events[0].steps[0].body
    assert isinstance(branch, p.If) and [s.op for s in (*branch.then, *branch.orelse)] == ['=', '+=']
    assert [s.origin for s in branch.orelse] == ['plant.fix.step[0].do[0].else[0]']
    reads = {value.name: value.init.expr.reads[0][1] for value in plant.values if value.kind == p.FORMULA}
    assert reads['mean_speed'] == Path(THIS, ('speeds', 'mean'))
    assert reads['since_fix'] == Since(Path(THIS, ('fix',)))
    assert reads['quiet'] == Elapsed(Path(THIS, ('x',)))


def test_a_stage_writes_a_writable_local_of_a_live_occurrence():
    """Spec, "State owned by an invocation": a dispatch raises the crew of the newest repair."""
    found = program_of("""
        plant:
            repair = event():
                crew_size = 1
                after 5 h
            dispatch = event():
                after 1 h:
                    this.repair.occurrences.at(t).crew_size = 3
        plant.repair.start()
        plant.dispatch.start()
        """)
    (write,) = found.template('plant').events[1].steps[0].body
    assert isinstance(write.target.start, Lookup) and write.target.steps == ('crew_size',)


def test_a_trigger_captures_values_that_its_reset_reads():
    """Spec, "A trigger belongs to its event": `shift = this.shift` with `reset when this.shift !=
    shift`, and a combined time and recovery condition."""
    found = program_of("""
        plant:
            shift = 1
            water: L = 20 in [0,]
            notes = 0
            note = event():
                when this.shift > 0:
                    shift = this.shift
                    ready_at = t + 3 h
                    this.note.start()
                    reset when t >= ready_at and this.water >= 12 L and this.shift != shift
                after 0 h:
                    this.notes += 1
        """)
    (trigger,) = found.template('plant').events[0].triggers
    assert [capture.origin for capture in trigger.captures] == [
        'plant.note.when[0].shift',
        'plant.note.when[0].ready_at',
    ]
    assert trigger.reset.kind == 'when' and Path(Local('ready_at')) in dict(trigger.reset.expr.reads).values()


def test_an_enum_is_its_members_and_a_bare_member_takes_its_enum_from_its_place():
    """Spec, "Primitive and composite types": `gate == OPEN`, a conditional, an assignment and a
    categorical over the enum of the place; two declarations of one enum are one type (E1)."""
    found = program_of("""
        gate:
            state: enum[OPEN, CLOSED] = OPEN
            last: enum[OPEN, CLOSED] = CLOSED
            same = formula(this.state == this.last)
            is_open = formula(OPEN == this.state)
            odds: distribution(enum[OPEN, CLOSED]) = categorical(CLOSED: 1, OPEN: 3)
            shut = event():
                after 1 h:
                    this.state = CLOSED if this.is_open else OPEN
                    this.last = this.odds.draw()
        """)
    assert found.enums == (p.Enum('enum[OPEN, CLOSED]', ('OPEN', 'CLOSED')),)
    odds = found.template('gate').part('odds').init
    assert (odds.enum, odds.outcomes) == ('enum[OPEN, CLOSED]', ('CLOSED', 'OPEN'))
    # Members in another order are another enum, and so is a categorical's own enum.
    error = refused(
        'm:\n    a: enum[OPEN, CLOSED] = OPEN\n    b: enum[CLOSED, OPEN] = OPEN\n    c = formula(this.a == this.b)\n'
    )
    assert error.codes == ['type']
    error = refused(
        'm:\n    a: enum[OPEN, CLOSED] = OPEN\n    odds = categorical(CLOSED: 1, OPEN: 3)\n'
        '    go = event():\n        after 0 h:\n            this.a = this.odds.draw()\n'
    )
    assert error.codes == ['type'] and 'enum[CLOSED, OPEN]' in error.problems[0].message


def test_an_enum_column_of_a_table_names_a_member_in_each_cell():
    found = program_of(
        'Valve:\n    input state: enum[OPEN, SHUT] = OPEN\nvalves: Valve from "valves.csv"\n',
        {'valves.csv': 'id,state\nv1,SHUT\nv2,OPEN\n'},
    )
    (template,) = found.templates
    assert [dict(member.values)['state'].reads[0][1].member for member in template.members] == [
        'SHUT',
        'OPEN',
    ]
    assert refused(
        'Valve:\n    input state: enum[OPEN, SHUT] = OPEN\nvalves: Valve from "valves.csv"\n',
        {'valves.csv': 'id,state\nv1,AJAR\n'},
    ).codes == ['enum_member']


def test_a_stage_sets_the_request_of_its_flow_and_reserves_by_a_move():
    """Spec, "Reserving a delivery": the second form, which moves at once and opens the flow later."""
    found = program_of("""
        customer:
            water: L = 0 in [0,]
        depot:
            customer = customer
            supply: L = 50 in [0,]
            deliver = event(amount: L, target_rate: L/h, setup: h):
                batch: L = 0 L in [0 L, amount]
                flow delivery: batch -> this.customer.water
                    request = 0 L/h
                after 0 h:
                    move amount from this.supply to batch
                after setup:
                    delivery.request = target_rate
                until batch <= 0 L
        depot.deliver.start(20 L, 4 L/h, 2 h)
        """)
    event = found.template('depot').events[0]
    (move,) = event.steps[0].body
    (setting,) = event.steps[1].body
    assert (move.source, move.destination) == (Path(THIS, ('supply',)), Path(Local('batch')))
    assert setting.target == Path(Local('delivery'), ('request',))


def test_a_setup_start_formats_and_parses_to_the_same_tree():
    text = 'm:\n    go = event(d: h):\n        after d\n\nm.go.start(2 h)\n'
    assert format_text(text) == text and parse(format_text(text)) == parse(text)


# ---- refusals ------------------------------------------------------------------------------------------

TANK = """
    tank:
        water: L = 5 in [0,]
        input limit: L = 9
        flow out: this.water -> SINK
            request = 1 L/h
        clear = event():
            after 0 h:
                {statement}
    """


@pytest.mark.parametrize(
    ('statement', 'code'),
    [
        # The front end reads `.source` and `.sink` as the store at that end (S3), so a write
        # through them would reach the store: it is refused, as a write to an end is.
        ('this.out.source = 0 L', 'fixed_write'),
        ('this.out.sink.outflow.capacity = 1 L/h', 'fixed_write'),
        ('this.limit = 2 L', 'fixed_write'),
        ('this.clear = 1', 'fixed_write'),
        ('this.out.actual_rate = 0 L/h', 'result_write'),
        ('this.water.outflow.actual_rate = 0 L/h', 'result_write'),
        ('this.clear.occurrences.at(t).started = 1 h', 'result_write'),
        ('this.water = 2', 'unit'),
        ('this.water += true', 'type'),
        ('this.out.request = 3 L', 'unit'),
        ('move 2 L from this.limit to this.water', 'move_end'),
        ('move 2 h from this.water to this.water', 'unit'),
        ('this.water.start()', 'start'),
        ('this.clear.start(1 h)', 'arguments'),
        (
            'switch this.water > 1 L:\n                    A:\n                        this.water = 1 L',
            'type',
        ),
    ],
)
def test_a_statement_that_breaks_a_rule_is_refused_by_its_code(statement, code):
    assert refused(TANK.format(statement=statement)).codes == [code]


def test_a_readonly_value_is_assigned_by_no_statement_and_a_move_still_changes_it():
    text = 'tank:\n    readonly water: L = 5 in [0,]\n    sink: L = 0 in [0,]\n    go = event():\n        after 0 h:\n{line}\n'
    assert refused(text.format(line='            this.water -= 1 L')).codes == ['readonly_write']
    assert program_of(text.format(line='            move 1 L from this.water to this.sink'))


@pytest.mark.parametrize(
    ('text', 'code'),
    [
        # D14: a plain initializer reads the locals above it; a formula may read one below.
        (
            'm:\n    go = event():\n        doubled = left * 2\n        left = 3\n        after 0 h\n',
            'local_order',
        ),
        (
            'm:\n    go = event():\n        x: L = 0 in [0,]\n        flow f: x -> SINK\n            request = r\n        r: L/h = 1 L/h\n        after 0 h\n',
            'local_order',
        ),
        # D13: a parameter is a value copy, which holds no stock.
        (
            'm:\n    go = event(amount: L):\n        flow f: amount -> SINK\n            request = 1 L/h\n        after 1 h\n',
            'parameter_end',
        ),
        ('a:\n    x = 1\nm:\n    go = event():\n        target = a\n        after 0 h\n', 'link'),
        ('m:\n    go = event():\n        x: L\n        after 0 h\n', 'no_value'),
        ('m:\n    go = event(x: h):\n        x = 1\n        after 0 h\n', 'duplicate_name'),
        # A trigger has no occurrence: its condition reads the receiver, not a parameter.
        (
            'm:\n    go = event(a: h):\n        when a > 1 h:\n            this.go.start(1 h)\n        after 0 h\n',
            'unknown_name',
        ),
        ('m:\n    x = formula(uniform(1, 2).draw())\n', 'formula_draws'),
        (
            'm:\n    d = uniform(1 h, 2 h)\n    go = event():\n        until this.d.draw() > 1 h\n',
            'formula_draws',
        ),
        (
            'm:\n    d = uniform(1 h, 2 h)\n    go = event():\n        when this.d.draw() > 1 h:\n            this.go.start()\n',
            'formula_draws',
        ),
        ('m:\n    d = uniform(1, 2)\n    assert this.d.draw() > 0\n', 'formula_draws'),
        ('gate = OPEN\n', 'enum_member'),
        ('m:\n    s: enum[A, B] = C\n', 'enum_member'),
        (
            'm:\n    s: enum[A, B] = A\n    go = event():\n        after 0 h:\n            switch this.s:\n                C:\n                    this.s = B\n',
            'enum_member',
        ),
        ('m:\n    d = categorical(A: 1, B: -1)\n', 'distribution'),
        ('m:\n    x = 1\n    d = uniform(this.x, 2)\n', 'distribution'),
        (
            'a:\n    d = uniform(1, 2)\nm:\n    go = event():\n        after 0 h:\n            switch a.choose(a.d):\n                X:\n                    this.go.start()\n',
            'choose',
        ),
        ('m:\n    x = 1\nm.x += 1\n', 'syntax'),
    ],
)
def test_a_part_of_an_event_that_breaks_a_rule_is_refused_by_its_code(text, code):
    assert refused(text).codes == [code]


def test_delayed_is_refused_by_name_with_the_event_that_models_a_delayed_observation():
    """`delayed(x, D)` left the language (PLAN.md, change 12 after G0): the refusal names its line and
    column, and says that an event waits and then writes in its place."""
    found = refused("""
        tank:
            water: L = 5
            before = formula(delayed(this.water, 2 h))
        """)
    (problem,) = found.problems
    assert (problem.code, problem.line, problem.column) == ('delayed', 4, 22)
    assert problem.message.startswith('the language has no delayed read') and '`after D:`' in problem.message
