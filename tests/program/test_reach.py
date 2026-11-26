"""Reachability (`napkin/program/reach.py`, D16): which events can start and which values each named
state can take under a configuration, each with its reason. The expected conclusions are worked by
hand from the rules of the module's docstring. The runs of generated models check the other side: an
event that a run starts is one that can start."""

import pytest

from napkin.engine import run
from napkin.program.build import (
    BOOL,
    Builder,
    add,
    after,
    assign,
    case,
    categorical,
    count,
    draw,
    event,
    if_,
    ifelse,
    input_,
    named,
    q,
    reset_when,
    start,
    switch,
    this,
    value,
    when,
)
from napkin.program.config import Configuration, InputValue, Request
from napkin.program.reach import reach
from napkin.program.refs import EnumValue
from tests.engine.port_cases import Case, Spelling, text_program
from tests.program.examples import EXAMPLES, UNITS


def test_a_fixed_gate_selects_the_operand_of_a_reachability_comparison():
    """The gate stays closed. The condition reads zero and cannot start the event."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        input_('open', BOOL, False),
        event('work', when(ifelse(this.open, 2, 0) > 1, start(this.work)), after(q(1, 'h'))),
    )
    assert reach(b.finish()).events['plant.work'][0] is False


def _plant(gate='CLOSED', as_input=False):
    """A plant whose inspection fires while its gate is open, which nothing opens; an event that
    counts restorations, which nothing starts; and a follow-up that waits for one."""
    b = Builder(UNITS)
    states = b.enum('enum[OPEN, CLOSED]', 'OPEN', 'CLOSED')
    make = input_ if as_input else value
    b.entity(
        'plant',
        make('gate', states, getattr(states, gate)),
        value('alarm', BOOL, False),
        value('inspections', '', 0),
        event(
            'inspect',
            when(this.gate == states.OPEN, start(this.inspect), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.alarm, True)),
        ),
        event('tick', after(q(1, 'h'), add(this.inspections, 1))),
        event('restored', after(q(0, 'h'))),
        event('follow', when(count(this.restored.occurrences) > 0, start(this.follow)), after(q(0, 'h'))),
    )
    b.setup(start(named('plant').tick))
    return b.finish()


def test_an_event_that_its_condition_rules_out_cannot_start_and_says_why():
    """ "This event cannot fire with the plant closed": the gate starts closed and nothing opens it,
    so the inspection cannot start and the alarm never turns on; the tick starts in the setup."""
    found = reach(_plant())
    assert found.events['plant.tick'] == (True, 'setup[0] starts it')
    assert (
        found.events['plant.inspect'][0] is False
        and 'no trigger whose condition can hold' in found.events['plant.inspect'][1]
    )
    assert found.states['plant.gate'] == {
        'OPEN': (False, 'no start value and no assignment that can run gives it this value'),
        'CLOSED': (True, 'its start value'),
    }
    assert found.states['plant.alarm'][True][0] is False


def test_the_count_of_an_event_that_cannot_start_is_zero():
    found = reach(_plant())
    assert not found.events['plant.restored'][0] and not found.events['plant.follow'][0]


def test_the_configuration_decides_what_an_input_lets_happen():
    """With the gate an input that the configuration opens, the inspection can fire and the alarm can
    turn on; the conclusion holds for that configuration only."""
    program = _plant(as_input=True)
    opened = Configuration(
        Request(1), inputs=(InputValue('plant', 'gate', EnumValue('enum[OPEN, CLOSED]', 'OPEN')),)
    )
    found = reach(program, opened)
    assert found.events['plant.inspect'] == (True, 'its trigger plant.inspect.when[0] can fire')
    assert found.states['plant.alarm'][True] == (True, 'plant.inspect.step[0].do[0] sets it')
    assert not reach(program).events['plant.inspect'][0]


def test_a_start_follows_its_branches_and_the_guard_of_its_stage():
    """A stage whose guard cannot hold starts nothing; an `if` whose test cannot fail never takes its
    `else`; a case whose member the selector cannot give starts nothing."""
    b = Builder(UNITS)
    b.entity(
        'shop',
        value('ready', BOOL, True),
        event(
            'open',
            after(q(1, 'h'), start(this.never), when=~this.ready & this.ready),
            after(q(1, 'h'), if_(this.ready, [start(this.then)], [start(this.otherwise)])),
        ),
        event('never'),
        event('then'),
        event('otherwise'),
    )
    b.setup(start(named('shop').open))
    found = reach(b.finish())
    assert {name: can for name, (can, _) in found.events.items()} == {
        'shop.open': True,
        'shop.never': False,
        'shop.then': True,
        'shop.otherwise': False,
    }
    assert found.events['shop.then'] == (True, 'shop.open.step[1].do[0].then[0] starts it')


def test_a_draw_never_gives_an_outcome_of_no_weight():
    """D1: a forecast that always waits never draws SEND, whether a switch reads the draw or the field
    that holds it (the acceptance example of docs/design/decisions.md, change 15), so the send
    branch cannot run. Only an edit at a breakpoint sends, and an edit is no part of a configuration."""
    assert reach(EXAMPLES['pump_dispatch_unattended']().program).events['depot.send_pump'][0] is False
    b = Builder(UNITS)
    action = b.enum('enum[SEND, WAIT]', 'SEND', 'WAIT')
    b.entity(
        'depot',
        event(
            'request_pump',
            after(
                q(0, 'h'),
                switch(
                    draw(categorical(action, SEND=0, WAIT=1)),
                    case(action.SEND, start(this.send_pump)),
                    case(action.WAIT, start(this.wait)),
                ),
            ),
        ),
        event('send_pump'),
        event('wait'),
    )
    b.setup(start(named('depot').request_pump))
    found = reach(b.finish())
    assert (found.events['depot.send_pump'][0], found.events['depot.wait'][0]) == (False, True)


def test_the_locals_of_an_event_take_their_start_and_assigned_values():
    found = reach(EXAMPLES['grinder_trigger_and_manual']().program)
    assert found.states['grinder.refill.status'] == {
        'WEIGHING': (True, 'its start value'),
        'ADDED': (True, 'grinder.refill.step[0].do[1] sets it'),
    }


@pytest.mark.parametrize('seed', range(5))
def test_every_event_that_a_run_starts_can_start(seed):
    """ "Cannot start" is a proof, so no run of the same configuration starts such an event. A model of
    the generated corpus (`tests/engine/port_cases.py`) starts events in its setup and by a trigger."""
    model = text_program(Case.of(seed), Spelling())
    started = run(model.program, model.configuration).entries('start')
    events = reach(model.program, model.configuration).events
    assert started
    assert [entry.part for entry in started if not events[entry.part][0]] == []
