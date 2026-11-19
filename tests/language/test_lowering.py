"""The lowering (`napkin/model/lowering.py`) and the entry point (`napkin/model/compile.py`): the text of
each example of `tests/program/examples.py` that this slice lowers gives a program with the canonical
bytes of the example's; inputs that draw their default lower as the examples build them; a construct of
a later slice is refused by name; and the migrated piano tuners load, lower and pass `finish()`."""

import textwrap
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from napkin.model.compile import compile_text, library_units, load_scenario
from napkin.model.language.format import format_text
from napkin.model.language.problems import LanguageError
from napkin.model.lowering import _located
from napkin.program import parts as p
from napkin.program.build import (
    SOURCE,
    Builder,
    dist_of,
    draw,
    flow,
    fmax,
    formula,
    ifelse,
    input_,
    q,
    t,
    this,
    uniform,
    value,
)
from napkin.program.canonical import program_bytes
from napkin.program.check import Diagnostic
from napkin.program.config import Configuration, Request
from tests.program.examples import EXAMPLES, UNITS

ROOT = Path(__file__).resolve().parents[2]
PIANO = ROOT / 'examples' / 'piano_tuners' / 'model.scn'

# The spec's text of each example in this slice's subset. The entities stand in the order in which the
# example declares them, so that the templates of the two programs stand in one order.
SOURCES = {
    'tank_delivery': """
        tank:
            readonly water: L = 8 in [0, 20]

        clinic:
            flow delivery: tank.water -> SINK
                capacity = 5 L/h
                request = 3 L/h
        """,
    'unit_division': """
        close: h = 48 h/2
        spaced: h = 48 h / 2
        """,
    'unit_product': """
        effort: person * year = (3 person) * (2 year)
        """,
    'two_junctions': """
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
        """,
    'keyed_lookup': """
        Reading:
            input hour: h = 0
            input factor = 1

        readings: Reading from "readings.csv"

        factor_now = formula(Reading.instances.by(hour).at(t).factor)
        """,
    'reservoir_priority': """
        reservoir:
            water: L = 20 in [0, 20]
                outflow.capacity = 10 L/h
                outflow.allocation = priority(hospital.delivery, garden.delivery)

        hospital:
            flow delivery: reservoir.water -> SINK
                request = 8 L/h

        garden:
            flow delivery: reservoir.water -> SINK
                request = 12 L/h
        """,
    # The default allocation, as the spec says: "The default `proportional()` instead gives 4 and 6".
    'reservoir_proportional': """
        reservoir:
            water: L = 20 in [0, 20]
                outflow.capacity = 10 L/h

        hospital:
            flow delivery: reservoir.water -> SINK
                request = 8 L/h

        garden:
            flow delivery: reservoir.water -> SINK
                request = 12 L/h
        """,
    'common_sink': """
        clinic:
            water: L = 0 in [0,]
                inflow.request = 6 L/h
                inflow.allocation = priority(this.main, this.backup)
            flow main: SOURCE -> this.water
                capacity = 4 L/h
            flow backup: SOURCE -> this.water
        """,
}
# "One pipe and three requests": the source, the pipe and the sink request 10, 8 and 6 L/h, and a cap
# of 7 L/h stands at one of the three scopes, or at none.
ONE_PIPE = """
    upstream:
        water: L = 100 in [0,]
            outflow.request = 10 L/h{source}

    downstream:
        water: L = 0 in [0,]
            inflow.request = 6 L/h{sink}

    pipe:
        flow carry: upstream.water -> downstream.water
            request = 8 L/h{pipe}

    source_short = formula(max(0 L/h, upstream.water.outflow.request - upstream.water.outflow.actual_rate))
    pipe_short = formula(max(0 L/h, pipe.carry.request - pipe.carry.actual_rate))
    sink_short = formula(max(0 L/h, downstream.water.inflow.request - downstream.water.inflow.actual_rate))
    """
CAPS = {'source': 'outflow.capacity', 'pipe': 'capacity', 'sink': 'inflow.capacity'}
for _name, _at in (('one_pipe', None), *((f'one_pipe_capped_at_{at}', at) for at in CAPS)):
    SOURCES[_name] = ONE_PIPE.format(
        **{scope: f'\n            {CAPS[scope]} = 7 L/h' if scope == _at else '' for scope in CAPS}
    )
# The tables that a source names, by the name that it writes.
TABLES = {'keyed_lookup': {'readings.csv': 'hour: h,factor\n10,2\n11,3\n'}}

# The water model of the spec (D17) as `water_service_returns` builds it, with the event that gives
# service back at 5 h, which a later slice (S4) brings.
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
    {restore}
    north: Utility
        online = false

    south: Utility
        demand = 4 L/h

    initial_unserved = sum(Utility.instances.unserved)
    unserved_volume = formula(sum(Utility.instances.unserved))
    unserved_now = formula(sum(Utility.instances.unserved_rate))
    """
RESTORE = """    restore = event():
            when t >= 5 h:
                this.restore.start()
                reset when false
            after 0 h:
                this.online = true
"""


def compiled(text, units=UNITS, tables=None):
    return compile_text(textwrap.dedent(text), units, tables=tables)


def same(program, expected):
    return program_bytes(program) == program_bytes(expected)


@pytest.mark.parametrize('name', sorted(SOURCES))
def test_the_text_of_an_example_lowers_to_its_program(name):
    assert same(compiled(SOURCES[name], tables=TABLES.get(name)).program, EXAMPLES[name]().program)


def test_the_water_model_lowers_to_its_program_but_for_the_event_of_a_later_slice():
    example = EXAMPLES['water_service_returns']().program
    (utility,) = example.templates
    # Without its event the example spells no unit h: only the event's times are in hours.
    expected = replace(
        example,
        templates=(replace(utility, events=()),),
        units=tuple(unit for unit in example.units if unit.name != 'h'),
    )
    assert same(compiled(WATER.format(restore='')).program, expected)
    with pytest.raises(LanguageError) as caught:
        compiled(WATER.format(restore=RESTORE))
    assert caught.value.codes == ['later_slice'] and '(S4)' in str(caught.value)


def test_a_reordered_table_with_ids_gives_the_same_program():
    text = 'Tank:\n    input held: L = 0\n    input open: bool = true\n\ntanks: Tank from "tanks.csv"\n'
    rows = ['north,30,true', 'south,20,false', 'east,5,true']
    programs = [
        compiled(text, tables={'tanks.csv': '\n'.join(['id,held,open', *order]) + '\n'}).program
        for order in (rows, rows[::-1], rows[1:] + rows[:1])
    ]
    assert len({program_bytes(program) for program in programs}) == 1
    (tank,) = programs[0].templates
    assert [member.id for member in tank.members] == ['tanks.east', 'tanks.north', 'tanks.south']


def test_the_two_spellings_of_a_unit_division_are_one_program():
    # `48 h/2` and `48 h / 2` are both 24 h: the example holds the one quotient twice.
    program = compiled(SOURCES['unit_division']).program
    close, spaced = program.root
    assert close.init == spaced.init


def test_a_bare_number_and_a_number_with_its_unit_are_one_program():
    written = compiled(
        'tank:\n    readonly water: L = 8 L in [0 L, 20 L]\nclinic:\n    flow delivery: tank.water -> SINK\n'
        '        capacity = 5 L/h\n        request = 3 L/h\n'
    ).program
    assert same(written, EXAMPLES['tank_delivery']().program)


def test_an_input_that_draws_its_default_lowers_as_the_examples_build_it():
    b = Builder(UNITS)
    b.entity(
        'machine',
        input_('repair_time', 'h', draw(uniform(1, 3, 'h')), lower=1, upper=12),
        input_('repair_times', None, uniform(1, 3, 'h')),
        input_('spread', 'h', draw(uniform(1, 3, 'h')), lower=1, upper=3),
    )
    text = """
        machine:
            input repair_time = uniform(1 h, 3 h).draw() in [1 h, 12 h]
            input repair_times = uniform(1 h, 3 h)
            input spread: h = uniform(1, 3).draw()
        """
    assert same(compiled(text).program, b.finish())


def test_formulas_inputs_and_flows_with_live_settings():
    b = Builder(UNITS)
    b.entity(
        'utility',
        input_('demand', 'L/h', q(10, 'L/h')),
        value('online', p.BOOL, True),
        value('served', 'L', 0, lower=0),
        flow(
            'delivery',
            SOURCE,
            this.served,
            request=formula(this.demand),
            capacity=formula(ifelse(this.online, this.demand, q(0, 'L/h'))),
        ),
        value('unserved_rate', 'L/h', formula(fmax(q(0, 'L/h'), this.demand - this.delivery.actual_rate))),
    )
    text = """
        utility:
            input demand: L/h = 10
            online: bool = true
            served: L = 0 in [0,]
            flow delivery: SOURCE -> this.served
                request = formula(this.demand)
                capacity = formula(this.demand if this.online else 0 L/h)
            unserved_rate = formula(max(0 L/h, this.demand - this.delivery.actual_rate))
        """
    assert same(compiled(text).program, b.finish())


def test_a_field_named_as_an_operation_of_a_handle_is_read_through_a_handle():
    """A model may name a field `start`, `draw`, `where`, `by`, `at` or `choose`: `this.start` reads
    it, and the builder's handle reads it too, while `c.by(...)` and `c.at(...)` still key and look up."""
    b = Builder(UNITS)
    clock = b.template(
        'Clock',
        value('start', 'h', 0),
        value('at', 'h', 2),
        *(value(name, '', number) for number, name in enumerate(('where', 'by', 'draw', 'choose'), 1)),
        value('span', 'h', formula(this.at - this.start)),
        value('total', '', formula(this.where + this.by + this.draw + this.choose)),
    )
    b.member(clock, 'c')
    b.root(value('first', 'h', formula(clock.instances.by('start').at(t).start)))
    text = """
        Clock:
            start: h = 0
            at: h = 2
            where = 1
            by = 2
            draw = 3
            choose = 4
            span = formula(this.at - this.start)
            total = formula(this.where + this.by + this.draw + this.choose)
        c: Clock
        first = formula(Clock.instances.by(start).at(t).start)
        """
    assert same(compiled(text).program, b.finish())


def test_a_distribution_valued_value_keeps_its_type():
    found = compiled('m:\n    speeds = uniform(1 L/h, 3 L/h)\n').program.templates[0].values[0]
    assert (found.kind, found.type) == (p.DISTRIBUTION, dist_of('L/h'))


@pytest.mark.parametrize(
    ('text', 'construct', 'slice_'),
    [
        ('tank:\n    refill = event():\n        after 1 h:\n            this.x += 1\n', 'an event', 'S4'),
        ('p:\n    s = solver:\n        solve_for:\n            this.x\n', 'a solver', 'S5'),
        ('c:\n    status ok\n        "Fine."\n', 'a status display', 'C'),
        ('tank:\n    water: L = 8\nassert tank.water > 0 L\n', 'an assertion over state', 'S4'),
        ('d:\n    sees e.x\ne:\n    x = 1\n', 'sees', 'S4'),
        (
            'tank:\n    water: L = 8\n    flow f: this.water -> SINK\n    far = formula(this.f.sink)\n',
            "a flow's ends as values",
            'S3',
        ),
        ('c:\n    a: L = 1\n    b: L = 1\n    flow link: this.a <-> this.b\n', 'a reversible route', 'S3'),
        (
            's:\n    a: L = 1\n    b: L = 0\n    flow r:\n        flow l: this.a -> this.b\n            request = 1 L/h\n',
            'a flow with legs',
            'S3',
        ),
        ('use pumps.common\n', 'use', 'S6'),
        ('change tank:\n    x = 2\n', 'change', 'S6'),
        ('options "Speed":\n    "Fast":\n        tank.x = 2\n', 'options', 'S6'),
        ('runs:\n    fast = "Fast"\n', 'runs', 'S6'),
        ('variant "Wet"\n    horizon 1 h\n', 'a variant', 'S6'),
        ('gate: enum[OPEN, CLOSED] = OPEN\n', 'an enum', 'S4'),
        ('d = categorical(A: 1, B: 0)\n', 'a categorical distribution', 'S4'),
        ('tank:\n    x = 1\ntank.x = 3\n', 'a property set by its path', 'S6'),
        ('x = 1\ny = formula(x.mean)\n', None, None),
    ],
)
def test_a_construct_of_a_later_slice_is_refused_by_name(text, construct, slice_):
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    if construct is None:
        assert caught.value.codes == ['unknown_name']
        return
    assert caught.value.codes == ['later_slice'], caught.value
    message = caught.value.problems[0].message
    assert construct in message and f'({slice_})' in message
    assert caught.value.problems[0].line >= 1


def test_a_value_that_reads_a_later_slice_is_refused_with_it():
    with pytest.raises(LanguageError) as caught:
        compiled(
            'gate: enum[OPEN, CLOSED] = OPEN\nopen = formula(gate == OPEN)\nboth = formula(open and open)\n'
        )
    assert caught.value.codes == ['later_slice'] * 3


def test_a_refusal_of_the_checker_is_at_the_line_of_its_part():
    model = compiled('tank:\n    x = 1\n\n    water: L = 8\n').declared
    found = _located(model, Diagnostic('kind', 'tank.water.outflow', 'no endpoint'))
    assert (found.code, found.line) == ('kind', 4)


# ---- the entry point -----------------------------------------------------------------------------


def test_a_text_with_a_horizon_has_its_default_run():
    found = compiled('scenario "Tank"\n    horizon 3 h\n' + textwrap.dedent(SOURCES['tank_delivery']))
    assert found.configuration == Configuration(Request(3))
    assert compiled(SOURCES['tank_delivery']).configuration is None


def test_the_units_of_a_library_keep_their_exact_scales():
    units = library_units(
        {
            'units': {
                'pp': {'dimensions': {}, 'scale': 0.01},
                'year': {'dimensions': {'time': 1}, 'scale': 8760},
            }
        }
    )
    assert units == {'pp': ({}, Fraction(1, 100)), 'year': ({'time': 1}, Fraction(8760))}


def test_a_missing_file_and_a_module_are_no_scenario(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_scenario(tmp_path / 'model.scn')
    module = tmp_path / 'model.scn'
    module.write_text('x = 1\n')
    with pytest.raises(LanguageError) as caught:
        load_scenario(module)
    assert caught.value.codes == ['scenario']


def test_the_piano_tuners_load_lower_and_pass_the_checker():
    found = load_scenario(PIANO)
    (tuners,) = found.program.templates
    kinds = {item.name: item.kind for item in tuners.values}
    assert kinds == {'rate': p.INPUT, 'staff': p.INPUT, 'need': p.INPUT, 'due': p.STATE, 'done': p.STATE}
    rate = tuners.part('rate')
    assert rate.type == p.Number('tunings/tuner/year')
    (tune,) = tuners.flows
    assert (tune.unit, isinstance(tune.request, p.Formula), isinstance(tune.capacity, p.Formula)) == (
        'tunings/h',
        True,
        True,
    )
    assert [item.name for item in found.program.root] == ['tunings_done']
    # One year is 8760 hours; the default run is a median run to it.
    assert found.configuration == Configuration(Request(8760))
    assert found.declared.scenario.title == 'Piano tuners'
    text = PIANO.read_text()
    assert format_text(text) == text
