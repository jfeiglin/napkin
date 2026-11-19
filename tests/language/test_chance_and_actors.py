"""Distributions, draws, actors and enum states in the front end (slice S4), ported from the front-end
tests of the old compiler (`tests/model/test_distribution_contracts.py`, `test_named_arguments.py`,
`test_views.py`, `test_state_assignment.py`). Their rules changed at G0: a distribution's parameters
are numbers written in place, in the order of today's constructors (no argument by name); an enum is
its members; and the views read the compiled model. At item 15 of the plan's changes after G0,
`choose(...)` and `sees` left the language: a decision is a field that a branch reads, which a caller
edits at a breakpoint (the acceptance example, `PUMP_DISPATCH`)."""

import textwrap
from fractions import Fraction

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.model.views import actors
from napkin.program import parts as p
from napkin.program.canonical import program_bytes
from napkin.program.refs import Distribution, EnumValue, Named, Path
from tests.program.examples import UNITS, pump_dispatch

UNITS = dict(UNITS, day=({'time': 1}, 24), people={'people': 1})


def compiled(text, tables=None):
    return compile_text(textwrap.dedent(text), UNITS, tables=tables)


def codes(text):
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    return caught.value.codes


def input_of(text, name='end'):
    return compiled(text).program.template('service').part(name)


# ---- distributions as inputs, from test_distribution_contracts.py and test_named_arguments.py ---------


def test_a_distribution_takes_the_unit_of_its_input_or_converts_its_own():
    """The bare arguments of a draw that is the whole initializer take the declared unit; written
    in another unit of the dimension, they are converted to it (2 days is 48 h)."""
    bare = input_of('service:\n    input end: h = uniform(4, 9).draw()\n')
    assert bare.init.reads[0][1].source == Distribution('uniform', (4, 9), 'h')
    days = input_of('service:\n    input end: h = uniform(1 day, 2 day).draw()\n')
    assert days.init.reads[0][1].source == Distribution('uniform', (24, 48), 'h')
    # The default range is the support of the distribution, in the input's unit.
    assert (days.lower.node.args[0].value, days.upper.node.args[0].value) == (24, 48)


def test_the_bounded_forms_take_their_bounds_in_order_and_their_shape_plain():
    """`normal(mean, sd, lower, upper)` and `lognormal(median, gsd, lower, upper)`: the bounds are
    the support, which the input's range must hold; a lognormal's gsd is a plain number."""
    normal = input_of('service:\n    input end: h = normal(2 h, 40 h, 1 h, 3 h).draw()\n')
    assert normal.init.reads[0][1].source == Distribution('normal', (2, 40, 1, 3), 'h')
    assert (normal.lower.node.args[0].value, normal.upper.node.args[0].value) == (1, 3)
    shaped = input_of('service:\n    input end: h = lognormal(4 h, 1.5, 2 h, 8 h).draw()\n')
    assert shaped.init.reads[0][1].source == Distribution('lognormal', (4, 1.5, 2, 8), 'h')
    assert codes('service:\n    input end: h = lognormal(4 h, 1.5 h).draw()\n') == ['unit']


@pytest.mark.parametrize(
    ('line', 'code'),
    [
        ('input end: h = uniform(1 L, 3 L).draw()', 'unit'),
        ('input end: h = uniform(1 h, 3 h).draw() in [2 h, 12 h]', 'range'),
        ('input end: h = uniform(1 h, 2 h, 3 h).draw()', 'arguments'),
        # No argument by name (the old `normal(2 h, sd=40 h)`): the bounded form is positional.
        ('input end: h = normal(2 h, sd = 40 h).draw()', 'syntax'),
        # A distribution's parameters are numbers written in place; a run changes an input that
        # holds a distribution instead (D2).
        ('input start: h = 1 h\n    input end: h = uniform(this.start, 3 h).draw()', 'distribution'),
    ],
)
def test_a_distribution_that_its_input_cannot_take_is_refused_by_its_code(line, code):
    assert codes(f'service:\n    {line}\n') == [code]


def test_a_refusal_of_a_distribution_is_at_its_line():
    with pytest.raises(LanguageError) as caught:
        compiled('service:\n    level = 1\n    input end: h = uniform(1 L, 3 L).draw()\n')
    assert (caught.value.codes, caught.value.problems[0].line) == (['unit'], 3)


def test_an_input_that_holds_a_distribution_is_changed_by_a_member_with_a_compatible_one():
    """D2: a distribution-valued input, overridden by a member with another distribution of its unit;
    one of another dimension is refused."""
    text = """
        Machine:
            input repair_times = uniform(1 h, 3 h)
        slow: Machine
            repair_times = uniform(2 h, 4 h)
        """
    (machine,) = compiled(text).program.templates
    assert machine.part('repair_times').type == p.DistributionType(p.Number('h'))
    assert machine.members[0].value('repair_times') == Distribution('uniform', (2, 4), 'h')
    assert codes(text.replace('uniform(2 h, 4 h)', 'uniform(2 L, 4 L)')) == ['unit']


def test_an_enum_input_draws_its_default_from_a_categorical_over_its_members():
    found = input_of(
        'service:\n    input weather: enum[DRY, WET] = categorical(WET: 0.3, DRY: 0.7).draw()\n', 'weather'
    )
    assert found.type == p.EnumType('enum[DRY, WET]')
    draw = found.init.reads[0][1]
    assert (draw.source.enum, draw.source.outcomes, draw.source.params) == (
        'enum[DRY, WET]',
        ('WET', 'DRY'),
        (0.3, 0.7),
    )


# ---- named states, from test_state_assignment.py ------------------------------------------------------

DESK = """
    world:
        alarm: enum[OFF, ON] = OFF
        input level: enum[LOW, HIGH, SEVERE] = HIGH
        ring = event():
            when t >= 1 h:
                this.ring.start()
                reset when false
            after 0 h:
                this.alarm = ON

    desk:
        echo: enum[OFF, ON] = OFF
        grade: enum[LOW, HIGH, SEVERE] = LOW
        seen: bool = false
        look = event():
            when t >= 2 h:
                this.look.start()
                reset when false
            after 0 h:
                {line}
    """


@pytest.mark.parametrize(
    ('line', 'read'),
    [
        ('this.echo = world.alarm', Path(Named('world'), ('alarm',))),
        ('this.grade = world.level', Path(Named('world'), ('level',))),
        (
            'this.grade = world.level if world.alarm == ON else LOW',
            EnumValue('enum[LOW, HIGH, SEVERE]', 'LOW'),
        ),
        ('this.seen = world.alarm == ON', EnumValue('enum[OFF, ON]', 'ON')),
    ],
)
def test_a_state_takes_a_value_of_its_type(line, read):
    """A named state takes another state or an input of its enum, or a conditional between them; a
    yes/no takes a condition."""
    (statement,) = compiled(DESK.format(line=line)).program.template('desk').events[0].steps[0].body
    assert read in dict(statement.value.reads).values()


@pytest.mark.parametrize(
    'line',
    [
        # `world.level` is of another enum, which `echo` cannot hold.
        'this.echo = world.level',
        # A number is no member of an enum.
        'this.echo = 1',
        # A member of another enum.
        'this.echo = HIGH',
    ],
)
def test_a_state_refuses_a_value_it_cannot_hold(line):
    assert codes(DESK.format(line=line)) in (['type'], ['enum_member'])


# ---- the acceptance example of item 15 of the plan's changes after G0 ---------------------------------

# The forecast drawn into the occurrence's field `order`, a `switch` on it, and the eligibility of
# SEND as its case's guard: a caller that wants another order stops before the switch and edits it.
# `tests/language/test_events.py` lowers it to the program of `pump_dispatch_unattended`.
PUMP_DISPATCH = """
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


# ---- no player machinery (item 15) ---------------------------------------------------------------------

# The dispatcher of the spec as G0 wrote it, with an actor that sees the spares and chooses.
DEPOT = """
    dispatcher:
        sees depot.spares
        forecast = categorical(SEND: 0, WAIT: 1)

    depot:
        spares = 1 in [0,]
        waits = 0
        request_pump = event():
            after 0 h:
                switch dispatcher.choose(dispatcher.forecast):
                    SEND when this.spares >= 1:
                        this.send_pump.start()
                    WAIT:
                        this.waits += 1
        send_pump = event():
            after 0 h:
                this.spares -= 1

    depot.request_pump.start()
    """


def problems(text):
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    return caught.value.problems


def test_a_choice_and_a_sight_are_refused_by_name_with_what_to_write_instead():
    """`choose(...)` and `sees` left the language: each is refused at its line, and the message
    says to store the value in a field, branch on it, and pause before the branch."""
    found = sorted(problems(DEPOT), key=lambda problem: problem.line)
    assert [(problem.code, problem.line) for problem in found] == [('sees', 3), ('choose', 11)]
    for problem in found:
        assert 'store the value in a field and branch on it' in problem.message
        assert 'pause before the branch' in problem.message
    assert codes('a:\n    d = categorical(X: 1)\n    x = formula(a.choose(a.d) == X)\n') == ['choose']
    assert actors(compiled(PUMP_DISPATCH)) == []


def test_the_spec_s_dispatcher_written_with_a_field_lowers_as_the_acceptance_example():
    """The dispatcher's choice becomes a draw of its forecast into `order`, which a caller edits."""
    written = DEPOT.replace('        sees depot.spares\n', '').replace(
        '            after 0 h:\n                switch dispatcher.choose(dispatcher.forecast):',
        '            order: enum[SEND, WAIT] = WAIT\n            after 0 h:\n'
        '                order = dispatcher.forecast.draw()\n                switch order:',
    )
    written = written.rstrip() + '\n    sent = formula(count(depot.send_pump.occurrences))\n'
    assert program_bytes(compiled(written).program) == program_bytes(pump_dispatch())


def test_a_draw_of_a_categorical_in_a_median_and_a_weight_of_zero_lower_as_written():
    """The forecast that always waits keeps its zero weight: eligibility and probability are
    independent (D1), so an edit of `order` at a breakpoint may still send."""
    forecast = compiled(PUMP_DISPATCH).program.template('dispatcher').part('forecast').init
    assert (forecast.outcomes, forecast.params) == (('SEND', 'WAIT'), (0, 1))
    assert Fraction(sum(forecast.params)) == 1
