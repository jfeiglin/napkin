"""The checker (`napkin/program/check.py`): each malformed program is refused with its code.

Each case builds the smallest program that breaks one invariant that an engine relies on, and
`finish()` refuses it with the code of that invariant and the origin of the part. Two cases that the
builders cannot write (a node with a name that has no read, a constant None) change a record of a
valid program. The last tests show what the rules permit: the forms that the spec gives as the right
way to write what a refused case tried.
"""

import re
import textwrap
from dataclasses import replace

import pytest

import napkin.program.build as builders
import napkin.program.check as checker
from napkin.core import expr as nodes
from napkin.program import parts as p
from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    case,
    categorical,
    draw,
    elapsed,
    endpoint,
    event,
    flow,
    formula,
    fsum,
    given,
    group_of,
    input_,
    item,
    link,
    literal,
    local,
    minimize,
    move,
    named,
    param,
    priority,
    q,
    rating,
    ref_to,
    reset_when,
    route,
    since,
    solve_for,
    solver,
    start,
    status,
    switch,
    t,
    this,
    uniform,
    unknown,
    until,
    value,
    when,
)
from napkin.program.check import ProgramError, check
from napkin.program.refs import Distribution, Expr, Formula

from .examples import UNITS


def refusals(make):
    """The refusals of the program that `make` declares on a builder."""
    b = Builder(UNITS)
    make(b)
    with pytest.raises(ProgramError) as caught:
        b.finish()
    return caught.value.diagnostics


def tank(b, *parts, readonly=False, **values):
    """The entity `tank`, with a store `water` and the parts and the member's values given."""
    return b.entity('tank', value('water', 'L', 8, lower=0, readonly=readonly), *parts, **values)


def solved_twice(b):
    supply = tank(b, flow('fill', SOURCE, this.water, capacity=q(1, 'L/h')))
    for name in ('one', 'two'):
        b.entity(name, solver('s', given('fill', supply.fill), solve_for(local.fill.actual_rate)))


def solved_and_assigned(b):
    b.entity(
        'plan',
        value('level', '', 0),
        solver('s', solve_for(this.level)),
        event('push', after(q(1, 'h'), assign(this.level, 3))),
    )


def stored_and_solved(b):
    tank(b, flow('drain', this.water, SINK, request=q(1, 'L/h')), solver('s', solve_for(this.water)))


def live_where(b):
    site = b.template('Site', value('need', '', 1))
    b.root(value('total', '', formula(fsum(site.instances.where(item.need > 0).need))))


def enum_outside(b):
    gate = b.enum('Gate', 'OPEN', 'SHUT')
    b.entity('door', value('state', gate, gate.AJAR))


def case_outside(b):
    outcome = b.enum('Outcome', 'FIXED')
    b.entity('m', event('go', after(q(1, 'h'), switch(draw(categorical(outcome, FIXED=1)), case('BROKEN')))))


def twice_in_literal(b):
    b.template('Pump')
    b.member('Pump', 'first')
    b.entity('station', value('pumps', group_of('Pump'), literal(named('first'), named('first'))))


def route_bare_in_priority(b):
    tank(
        b,
        value('other', 'L', 0, outflow=endpoint(allocation=priority(this.link))),
        route('link', this.other, this.water, unit='L/h'),
    )


def priority_elsewhere(b):
    tank(
        b,
        value('other', 'L', 0),
        flow('out', this.water, SINK),
        flow('into', SOURCE, this.other),
        value('spare', 'L', 0, outflow=endpoint(allocation=priority(this.out, this.into))),
    )


GO = 'tank.go.step[0].do[0]'  # the first statement of the first stage of `tank.go`

# (code, what the case declares, the origin that the refusal names)
CASES = [
    ('unknown_name', lambda b: tank(b, flow('drain', this.waterr, SINK, request=q(1, 'L/h'))), 'tank.drain'),
    ('unknown_name', lambda b: b.entity('tank', value('water', 'L', 8), volume=3), 'tank'),
    ('unknown_name', lambda b: b.root(value('total', 'L', formula(named('nowhere').water))), 'total'),
    ('unknown_name', lambda b: tank(b, event('go', after(q(1, 'h'), start(this.water)))), GO),
    ('duplicate_name', lambda b: tank(b, value('water', 'L', 2)), 'tank'),
    ('duplicate_name', lambda b: (b.entity('a'), b.member('a', 'a')), 'members'),
    ('unknown_unit', lambda b: b.entity('tank', value('water', 'gal', 8)), 'tank.water'),
    ('kind', lambda b: b.entity('gate', value('open', BOOL, True, lower=0)), 'gate.open'),
    (
        'kind',
        lambda b: tank(b, value('ready', BOOL, False, outflow=endpoint(capacity=q(1, 'L/h')))),
        'tank.ready',
    ),
    ('link_unset', lambda b: (b.entity('place'), b.entity('route', link('origin', 'place'))), 'route'),
    (
        'link_unset',
        lambda b: (b.entity('place'), b.entity('route', link('origin', 'place'), origin='nowhere')),
        'route',
    ),
    ('no_value', lambda b: (b.template('Pump', input_('rate', 'L/h')), b.member('Pump', 'pump')), 'pump'),
    (
        'no_value',
        lambda b: tank(b, event('go', value('left', 'L'), until(local.left <= q(0, 'L')))),
        'tank.go.left',
    ),
    ('two_writers', solved_twice, 'one.s'),
    ('two_writers', solved_and_assigned, 'plan.s'),
    ('two_writers', stored_and_solved, 'tank.s'),
    (
        'readonly_write',
        lambda b: tank(b, event('go', after(q(1, 'h'), add(this.water, q(2, 'L')))), readonly=True),
        GO,
    ),
    (
        'fixed_write',
        lambda b: tank(
            b, input_('rate', 'L/h', 1), event('go', after(q(1, 'h'), assign(this.rate, q(2, 'L/h'))))
        ),
        GO,
    ),
    (
        'fixed_write',
        lambda b: tank(
            b,
            flow('drain', this.water, SINK),
            event('go', after(q(1, 'h'), assign(this.drain.source, this.water))),
        ),
        GO,
    ),
    (
        'fixed_write',
        lambda b: tank(
            b,
            link('next', 'tank'),
            event('go', after(q(1, 'h'), assign(this.next, named('tank')))),
            next=named('tank'),
        ),
        GO,
    ),
    (
        'result_write',
        lambda b: tank(
            b,
            flow('drain', this.water, SINK),
            event('go', after(q(1, 'h'), assign(this.drain.actual_rate, q(1, 'L/h')))),
        ),
        GO,
    ),
    (
        'result_write',
        lambda b: tank(b, solver('s', unknown('x', '')), event('go', after(q(1, 'h'), assign(this.s.x, 1)))),
        GO,
    ),
    (
        'assign_value',
        lambda b: tank(b, value('open', BOOL, False), event('go', after(q(1, 'h'), add(this.open, True)))),
        GO,
    ),
    (
        'assign_value',
        lambda b: tank(
            b,
            value('low', BOOL, formula(this.water <= q(1, 'L'))),
            event('go', after(q(1, 'h'), assign(this.low, True))),
        ),
        GO,
    ),
    ('flow_end', lambda b: tank(b, input_('rate', 'L', 1), flow('drain', this.rate, SINK)), 'tank.drain'),
    ('flow_end', lambda b: tank(b, flow('back', SINK, this.water)), 'tank.back'),
    (
        'flow_end',
        lambda b: tank(b, value('level', 'L', formula(this.water * 2)), flow('drain', this.level, SINK)),
        'tank.drain',
    ),
    (
        'parameter_end',
        lambda b: tank(
            b,
            event(
                'go',
                param('amount', 'L'),
                flow('pipe', local.amount, SINK, request=q(1, 'L/h')),
                after(q(1, 'h')),
            ),
        ),
        'tank.go.pipe',
    ),
    (
        'parameter_end',
        lambda b: tank(
            b, event('go', param('amount', 'L'), after(q(0, 'h'), move(q(1, 'L'), local.amount, this.water)))
        ),
        GO,
    ),
    ('route_end', lambda b: tank(b, route('link', SOURCE, this.water, unit='L/h')), 'tank.link'),
    ('route_end', lambda b: tank(b, route('link', this.water, SINK, unit='L/h')), 'tank.link'),
    (
        'flow_units',
        lambda b: tank(b, value('sand', 'g', 0), flow('mix', this.water, this.sand, unit='L/h')),
        'tank.mix',
    ),
    ('flow_units', lambda b: b.entity('outside', flow('through', SOURCE, SINK)), 'outside.through'),
    ('flow_units', lambda b: tank(b, flow('drain', this.water, SINK, unit='g/h')), 'tank.drain'),
    (
        'move_end',
        lambda b: tank(
            b,
            value('level', 'L', formula(this.water * 2)),
            event('go', after(q(0, 'h'), move(q(1, 'L'), this.level, this.water))),
        ),
        GO,
    ),
    ('formula_draws', lambda b: tank(b, value('next', 'h', formula(draw(uniform(1, 3, 'h'))))), 'tank.next'),
    (
        'formula_draws',
        lambda b: tank(b, event('go', when(draw(uniform(0, 1)) >= 0.5, start(this.go)))),
        'tank.go.when[0]',
    ),
    (
        'formula_draws',
        lambda b: tank(b, event('go', until(this.water <= draw(uniform(0, 1, 'L'))))),
        'tank.go.step[0]',
    ),
    (
        'trigger_start',
        lambda b: tank(b, event('other'), event('go', when(t >= q(1, 'h'), start(this.other)))),
        'tank.go.when[0]',
    ),
    (
        'trigger_start',
        lambda b: tank(b, value('n', '', 0), event('go', when(t >= q(1, 'h'), add(this.n, 1)))),
        'tank.go.when[0]',
    ),
    (
        'local_order',
        lambda b: tank(b, event('go', value('doubled', '', local.half * 2), value('half', '', 1))),
        'tank.go.doubled',
    ),
    (
        'local_order',
        lambda b: tank(
            b, event('go', flow('pipe', this.water, SINK, request=local.rate), value('rate', 'L/h', 1))
        ),
        'tank.go.pipe',
    ),
    (
        'solve_for',
        lambda b: tank(b, flow('drain', this.water, SINK), solver('s', solve_for(this.drain.request))),
        'tank.s',
    ),
    (
        'solve_for',
        lambda b: tank(
            b,
            value('other', 'L', 1),
            route('link', this.water, this.other, unit='L/h'),
            solver('s', solve_for(this.link.forward.actual_rate)),
        ),
        'tank.s',
    ),
    ('priority_item', route_bare_in_priority, 'tank.other.outflow'),
    ('priority_item', priority_elsewhere, 'tank.spare.outflow'),
    ('enum_member', enum_outside, 'door.state'),
    ('enum_member', case_outside, 'm.go.step[0].do[0].BROKEN'),
    ('distribution', lambda b: tank(b, value('d', None, Distribution('uniform', (1, 2, 3), 'h'))), 'tank.d'),
    ('distribution', lambda b: tank(b, value('d', None, Distribution('poisson', (1,), 'h'))), 'tank.d'),
    ('distribution', lambda b: tank(b, value('later', 'L', this.water.draw())), 'tank.later'),
    ('collection', lambda b: tank(b, value('total', 'L', formula(fsum(this.water)))), 'tank.total'),
    ('duplicate_literal', twice_in_literal, 'station.pumps'),
    ('where_live', live_where, 'total'),
    (
        'status_fallback',
        lambda b: tank(
            b,
            status(
                rating('ok', when=this.water > q(1, 'L')), rating('degraded', when=this.water <= q(1, 'L'))
            ),
        ),
        'tank.status',
    ),
    (
        'status_fallback',
        lambda b: tank(b, status(rating('ok'), rating('degraded', when=this.water <= q(1, 'L')))),
        'tank.status',
    ),
    (
        'arguments',
        lambda b: tank(
            b, event('pour', param('amount', 'L')), event('go', after(q(0, 'h'), start(this.pour)))
        ),
        GO,
    ),
]


@pytest.mark.parametrize(
    ('code', 'make', 'part'), CASES, ids=[f'{case[0]}-{index}' for index, case in enumerate(CASES)]
)
def test_a_malformed_program_is_refused_with_its_code(code, make, part):
    found = refusals(make)
    assert code in {each.code for each in found}, found
    assert part in {each.part for each in found if each.code == code}, found


def test_each_code_has_a_case():
    """Each code that the checker documents is checked here; two by a changed record below."""
    documented = set()
    for line in checker.__doc__.splitlines():
        if line.startswith('- `'):
            documented.update(re.findall(r'`(\w+)`', line.split(':')[0]))
    assert len(documented) == 30
    assert documented - {'unbound_symbol', 'none_value'} == {case[0] for case in CASES}


def valid():
    b = Builder(UNITS)
    tank(b, value('level', 'L', formula(this.water * 2)))
    return b.finish()


def with_level(program, init):
    """The valid program, with the formula `level` given another initializer."""
    template = program.template('tank')
    values = tuple(replace(each, init=init) if each.name == 'level' else each for each in template.values)
    return replace(program, templates=(replace(template, values=values),))


def test_a_valid_program_has_no_refusal():
    assert check(valid()) == ()


def test_a_name_without_its_read_is_refused():
    node = nodes.binary('mul', nodes.ref('this.water'), nodes.const(2))
    program = with_level(valid(), Formula(Expr(node)))
    assert {each.code for each in check(program)} == {'unbound_symbol'}


def test_a_constant_none_is_refused():
    """D4: the language has no none value."""
    program = with_level(valid(), Formula(Expr(nodes.const(None))))
    assert 'none_value' in {each.code for each in check(program)}


def test_what_the_rules_permit():
    """The forms that the spec gives in place of the refused ones: a flow and a checked move change a
    readonly stock (spec, "How to declare, read and change a value"); an event that must draw from one
    tank takes the tank and uses its field (D13); a retained formula may read a later local (D14); a
    trigger starts its own event with a captured value; a where filters on an input; `since` and
    `elapsed` read an event and a value."""
    b = Builder(UNITS)
    site = b.template('Site', input_('critical', BOOL, False), value('need', '', 1))
    b.member(site, 'north', critical=True)
    keeper = b.entity(
        'keeper',
        value('water', 'L', 8, lower=0, readonly=True),
        value('spare', 'L', 0, lower=0, readonly=True),
        flow('drain', this.water, SINK, request=q(1, 'L/h')),
        event('top_up', after(q(0, 'h'), move(q(1, 'L'), this.water, this.spare))),
        event(
            'pour',
            param('source', ref_to('keeper')),
            value('rate', 'L/h', formula(local.later / q(1, 'h'))),
            value('later', 'L', 2),
            flow('pipe', local.source.water, SINK, request=formula(local.rate)),
            after(q(1, 'h')),
        ),
        event(
            'watch',
            param('level', 'L'),
            when(
                this.water <= q(4, 'L'),
                start(this.watch, local.seen),
                captures=(value('seen', 'L', this.water),),
                reset=reset_when(False),
            ),
        ),
    )
    b.root(
        value('critical_need', '', formula(fsum(site.instances.where(item.critical).need))),
        value('since_top_up', 'h', formula(since(keeper.top_up))),
        value('still', 'h', formula(elapsed(keeper.water))),
    )
    b.setup(start(keeper.top_up), start(keeper.pour, keeper))
    assert check(b.finish()) == ()


def test_the_example_of_the_builders_docstring_finishes():
    """The tank of `build.py`'s docstring, as it is written there."""
    source = builders.__doc__.split('::', 1)[1].split('An expression is written', 1)[0]
    scope = {}
    exec(textwrap.dedent(source), scope)
    program = scope['program']
    assert [template.name for template in program.templates] == ['tank', 'clinic']
    assert program.template('clinic').flows[0].unit == 'L/h'


def test_a_solver_reads_its_unknowns_by_name():
    b = Builder(UNITS)
    b.entity('plan', solver('s', unknown('x', '', lower=0), minimize(local.x)))
    assert check(b.finish()) == ()


def test_a_message_names_the_part():
    found = refusals(lambda b: tank(b, flow('drain', this.waterr, SINK, request=q(1, 'L/h'))))
    assert any('this.waterr' in each.message for each in found)
    assert str(ProgramError(found)).startswith('unknown_name at tank.drain')


def test_a_categorical_outcome_is_a_member_of_its_enum():
    b = Builder(UNITS)
    outcome = b.enum('Outcome', 'FIXED', 'FAILED')
    b.entity('m', value('d', None, categorical(outcome, FIXED=1, BROKEN=1)))
    with pytest.raises(ProgramError) as caught:
        b.finish()
    assert {each.code for each in caught.value.diagnostics} == {'enum_member'}


def test_a_flow_of_an_event_may_end_at_an_entity_parameters_store():
    """D13: `source: Tank` and `source.water` is the way to draw from a particular tank."""
    b = Builder(UNITS)
    keeper = b.entity(
        'keeper',
        value('water', 'L', 8, lower=0),
        event(
            'pour',
            param('source', p.EntityType('keeper')),
            flow('pipe', local.source.water, SINK),
            after(q(1, 'h')),
        ),
    )
    b.setup(start(keeper.pour, keeper))
    assert check(b.finish()) == ()
