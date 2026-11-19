"""Reversible routes and flows with legs in the front end (`napkin/model/semantic.py` and the
lowering, slice S3): a route's signed rate and request, its capacity and its two legs, which are
members of its ends' collections of flows and are named in the `priority(...)` of the endpoint in
their direction; a flow with legs, its `served_fraction` and its legs, each a directed flow in its
own unit and named in the priority of its own endpoint; and the reads of a flow's ends (`.source`,
`.sink`), which read the store at that end. A source text gives the program that the builder makes
of the same model, and each refusal has its code and its line. The spec's worked models
(`reversible_route` and the three `legs_*`) are in `test_lowering.py`, against the programs of
`tests/program/examples.py`."""

import textwrap

import pytest

from napkin.model import semantic as s
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.model.lowering import _located
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    TemplateHandle,
    count,
    endpoint,
    flow,
    formula,
    fsum,
    legs,
    link,
    named,
    priority,
    q,
    route,
    this,
    value,
)
from napkin.program.canonical import program_bytes
from napkin.program.check import Diagnostic
from tests.program.examples import UNITS


def compiled(text):
    return compile_text(textwrap.dedent(text), UNITS)


def same(text, builder):
    return program_bytes(compiled(text).program) == program_bytes(builder.finish())


def refused(text, code, line):
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    assert code in caught.value.codes, caught.value
    found = caught.value.problems[caught.value.codes.index(code)]
    assert found.line == line, found
    return found


# ---- reversible routes -----------------------------------------------------------------------------

CHANNEL = """
    west:
        water: L = 10 in [0, 20]{west}

    east:
        water: L = 10 in [0, 20]{east}

    channel:
        flow link: west.water <-> east.water
            request = {request}{rest}
    """


def test_a_route_reads_its_signed_rate_its_settings_and_its_legs():
    """Spec, "What each scope can see": a route reads its signed `actual_rate` and `request` and its
    `capacity`; each leg reads its own `actual_rate` and `request`; the forward leg is a member of
    the first end's outflow. A request that changes sign is one signed formula."""
    reads = (
        '\n            capacity = 5 L/h'
        '\n        signed = formula(this.link.actual_rate)'
        '\n        eastward = formula(this.link.forward.actual_rate)'
        '\n        westward = formula(this.link.backward.actual_rate)'
        '\n        asked_west = formula(this.link.backward.request)'
        '\n        limit = formula(this.link.capacity)'
        '\n\n    leaving_west = formula(count(west.water.outflow.flows))\n'
    )
    text = CHANNEL.format(west='', east='', request='formula((west.water - east.water) / (4 h))', rest=reads)
    b = Builder(UNITS)
    west = b.entity('west', value('water', 'L', 10, lower=0, upper=20))
    east = b.entity('east', value('water', 'L', 10, lower=0, upper=20))
    b.entity(
        'channel',
        route(
            'link',
            west.water,
            east.water,
            request=formula((west.water - east.water) / q(4, 'h')),
            capacity=q(5, 'L/h'),
        ),
        value('signed', 'L/h', formula(this.link.actual_rate)),
        value('eastward', 'L/h', formula(this.link.forward.actual_rate)),
        value('westward', 'L/h', formula(this.link.backward.actual_rate)),
        value('asked_west', 'L/h', formula(this.link.backward.request)),
        value('limit', 'L/h', formula(this.link.capacity)),
    )
    b.root(value('leaving_west', '', formula(count(west.water.outflow.flows))))
    assert same(text, b)
    declared = compiled(text).declared.part('channel.link')
    assert isinstance(declared, s.DeclaredRoute)
    assert (declared.source.start, declared.sink.start) == (('named', 'west'), ('named', 'east'))


def test_the_legs_of_a_route_are_named_in_the_priorities_of_its_ends():
    """Spec, "Local allocation": a route contributes `link.forward` to its first end's outflow and
    `link.backward` to its second end's, each named in that endpoint's priority."""
    text = CHANNEL.format(
        west='\n            outflow.allocation = priority(channel.link.forward, this.spill)'
        '\n        flow spill: this.water -> SINK\n            request = 1 L/h',
        east='\n            outflow.allocation = priority(channel.link.backward)',
        request='2 L/h',
        rest='',
    )
    b = Builder(UNITS)
    first = priority(named('channel').link.forward, this.spill)
    west = b.entity(
        'west',
        value('water', 'L', 10, lower=0, upper=20, outflow=endpoint(allocation=first)),
        flow('spill', this.water, SINK, request=q(1, 'L/h')),
    )
    second = priority(named('channel').link.backward)
    east = b.entity('east', value('water', 'L', 10, lower=0, upper=20, outflow=endpoint(allocation=second)))
    b.entity('channel', route('link', west.water, east.water, request=q(2, 'L/h')))
    assert same(text, b)


def test_a_store_that_a_flow_fills_from_outside_is_an_end_of_a_route():
    """The language has no mark of a tally (a store that only receives). A store is known to be a
    tally only by what the model does with it, and a route takes from both of its ends: a store at
    an end of a route is a stock, whatever else fills it. So `SOURCE` and `SINK`, which cannot both
    supply and receive, are what a route's end refuses, besides what is no stored number."""
    text = """
        west:
            water: L = 0 in [0,]
            flow rain: SOURCE -> this.water
                request = 1 L/h

        east:
            water: L = 0 in [0,]

        channel:
            flow link: west.water <-> east.water
                request = 1 L/h
        """
    b = Builder(UNITS)
    west = b.entity(
        'west', value('water', 'L', 0, lower=0), flow('rain', SOURCE, this.water, request=q(1, 'L/h'))
    )
    east = b.entity('east', value('water', 'L', 0, lower=0))
    b.entity('channel', route('link', west.water, east.water, request=q(1, 'L/h')))
    assert same(text, b)


@pytest.mark.parametrize(
    ('west', 'asked', 'rest', 'code', 'line', 'words'),
    [
        # A leg in the other direction is not incident there: the program's rule, at the setting's line.
        (
            '\n            outflow.allocation = priority(channel.link.backward)',
            '1 L/h',
            '',
            'priority_item',
            4,
            'not at this endpoint',
        ),
        (
            '\n            outflow.allocation = priority(channel.link)',
            '1 L/h',
            '',
            'priority_item',
            4,
            'name its leg in the direction of this endpoint',
        ),
        (
            '',
            '1 L/h',
            '\n            limit = 2 L/h',
            'property',
            11,
            'a reversible route takes request and capacity',
        ),
        (
            '',
            '1 L/h',
            '\n        x = formula(this.link.forward.capacity)',
            'unknown_name',
            11,
            'limits both its legs',
        ),
        ('', '1 L/h', '\n        x = formula(this.link.source)', 'unknown_name', 11, 'as forward.source'),
        ('', '1 L/h', '\n        x = formula(this.link)', 'type', 11, 'a flow is no value'),
        ('', '1 W', '', 'flow_units', 9, 'two dimensions'),
    ],
)
def test_a_route_is_refused_with_its_code(west, asked, rest, code, line, words):
    found = refused(CHANNEL.format(west=west, east='', request=asked, rest=rest), code, line)
    assert words in found.message, found


@pytest.mark.parametrize(
    ('text', 'code', 'words'),
    [
        ('tank:\n    water: L = 1\n    flow link: SOURCE <-> this.water\n', 'route_end', 'SOURCE and SINK'),
        ('tank:\n    water: L = 1\n    flow link: this.water <-> SINK\n', 'route_end', 'SOURCE and SINK'),
        (
            'tank:\n    input water: L = 1\n    b: L = 1\n    flow link: this.water <-> this.b\n',
            'flow_end',
            'no stored',
        ),
        (
            'tank:\n    water: L = 1\n    b = formula(this.water)\n    flow link: this.water <-> this.b\n',
            'flow_end',
            'no stored',
        ),
    ],
)
def test_a_route_ends_at_two_stores(text, code, words):
    found = refused(text, code, text.count('\n'))
    assert words in found.message, found


# ---- flows with legs -------------------------------------------------------------------------------

SITES = """
    Crew:
        hours: crew_h = 100 in [0,]
        used: crew_h = 0 in [0,]

    Site:
        crew: Crew
        work: work_unit = 100 in [0,]
        done: work_unit = 0 in [0,]
        flow restore:
            flow labor: this.crew.hours -> this.crew.used
                request = 4 crew_h/h
                capacity = 2 crew_h/h
            flow work: this.work -> this.done
                request = 8 work_unit/h{rest}

    team: Crew
    north: Site
        crew = team
    """


def _sites(*rest):
    """The builder's program of `SITES`, with more values of a site."""
    b = Builder(UNITS)
    crew = b.template('Crew', value('hours', 'crew_h', 100, lower=0), value('used', 'crew_h', 0, lower=0))
    site = b.template(
        'Site',
        link('crew', 'Crew'),
        value('work', 'work_unit', 100, lower=0),
        value('done', 'work_unit', 0, lower=0),
        legs(
            'restore',
            flow(
                'labor', this.crew.hours, this.crew.used, request=q(4, 'crew_h/h'), capacity=q(2, 'crew_h/h')
            ),
            flow('work', this.work, this.done, request=q(8, 'work_unit/h')),
        ),
        *rest,
    )
    b.member(crew, 'team')
    b.member(site, 'north', crew=named('team'))
    return b


def test_a_flow_with_legs_reads_its_fraction_and_each_leg_in_its_own_unit():
    """Spec, "Shared resources and competing invocations": `restore.served_fraction` is a plain
    number, and each leg reads its rates in its own unit (crew_h/h and work_unit/h)."""
    rest = (
        '\n        progress = formula(this.restore.served_fraction)'
        '\n        pace = formula(this.restore.work.actual_rate)'
        '\n        asked = formula(this.restore.labor.request)'
    )
    text = SITES.format(rest=rest) + 'busy = formula(sum(Site.instances.restore.served_fraction))\n'
    b = _sites(
        value('progress', '', formula(this.restore.served_fraction)),
        value('pace', 'work_unit/h', formula(this.restore.work.actual_rate)),
        value('asked', 'crew_h/h', formula(this.restore.labor.request)),
    )
    b.root(value('busy', '', formula(fsum(TemplateHandle('Site').instances.restore.served_fraction))))
    assert same(text, b)
    model = compiled(text).declared
    restore = model.part('Site.restore')
    assert isinstance(restore, s.DeclaredLegs)
    assert [(leg.path, leg.rate.unit) for leg in restore.legs] == [
        ('Site.restore.labor', 'crew_h/h'),
        ('Site.restore.work', 'work_unit/h'),
    ]
    # A refusal of the checker that names a leg is given at the leg's line.
    found = _located(model, Diagnostic('kind', 'Site.restore.work', 'a leg'))
    assert found.line == 14


def test_a_leg_is_named_in_the_priority_of_its_own_endpoint():
    """Spec, "Shared resources and competing invocations": a leg joins its own endpoints' flows and
    is named in their priority; two endpoints may rank the same legs in other orders."""
    text = """
        crew:
            hours: crew_h = 100 in [0,]
                outflow.capacity = 2 crew_h/h
                outflow.allocation = priority(north.restore.labor, south.restore.labor)
            used: crew_h = 0 in [0,]
                inflow.allocation = priority(south.restore.labor, north.restore.labor)

        north:
            work: work_unit = 10 in [0,]
            done: work_unit = 0 in [0,]
            flow restore:
                flow labor: crew.hours -> crew.used
                    request = 2 crew_h/h
                flow work: this.work -> this.done
                    request = 4 work_unit/h

        south:
            work: work_unit = 10 in [0,]
            done: work_unit = 0 in [0,]
            flow restore:
                flow labor: crew.hours -> crew.used
                    request = 2 crew_h/h
                flow work: this.work -> this.done
                    request = 4 work_unit/h
        """
    b = Builder(UNITS)
    north, south = named('north'), named('south')
    out = endpoint(capacity=q(2, 'crew_h/h'), allocation=priority(north.restore.labor, south.restore.labor))
    into = endpoint(allocation=priority(south.restore.labor, north.restore.labor))
    crew = b.entity(
        'crew',
        value('hours', 'crew_h', 100, lower=0, outflow=out),
        value('used', 'crew_h', 0, lower=0, inflow=into),
    )
    for name in ('north', 'south'):
        b.entity(
            name,
            value('work', 'work_unit', 10, lower=0),
            value('done', 'work_unit', 0, lower=0),
            legs(
                'restore',
                flow('labor', crew.hours, crew.used, request=q(2, 'crew_h/h')),
                flow('work', this.work, this.done, request=q(4, 'work_unit/h')),
            ),
        )
    assert same(text, b)


@pytest.mark.parametrize(
    ('rest', 'code', 'line', 'words'),
    [
        ('\n        x = formula(this.restore.actual_rate)', 'type', 16, 'has no actual_rate of its own'),
        ('\n        x = formula(this.restore)', 'type', 16, 'a flow with legs is no value'),
        ('\n        x = formula(this.restore.labour.actual_rate)', 'unknown_name', 16, 'did you mean labor'),
        ('\n        x = formula(count(Site.instances.restore))', 'type', 16, 'count counts members'),
        ('\n            flow work: this.done -> this.work', 'duplicate_name', 16, 'two legs named work'),
        ('\n            flow served_fraction: this.done -> this.work', 'reserved', 16, 'reads the flow'),
        ('\n                limit = 1 work_unit/h', 'property', 16, 'takes request and capacity'),
        ('\n            flow rest: this.crew -> this.done', 'flow_end', 16, 'no stored number'),
        # The parser: a leg goes one way, and the parent of the legs takes no setting.
        ('\n            flow back: this.done <-> this.work', 'syntax', 16, 'a leg of a flow goes one way'),
    ],
)
def test_a_flow_with_legs_is_refused_with_its_code(rest, code, line, words):
    found = refused(SITES.format(rest=rest), code, line)
    assert words in found.message, found


@pytest.mark.parametrize(
    ('allocation', 'code', 'words'),
    [
        ('priority(this.restore.work)', 'priority_item', 'not at this endpoint'),
        ('priority(this.restore)', 'priority_item', 'name its leg at this endpoint'),
    ],
)
def test_a_priority_names_a_leg_at_its_own_endpoint(allocation, code, words):
    text = SITES.replace(
        'done: work_unit = 0 in [0,]',
        f'done: work_unit = 0 in [0,]\n            outflow.allocation = {allocation}',
    )
    found = refused(text.format(rest=''), code, 10)
    assert words in found.message, found


def test_the_parent_of_the_legs_takes_no_setting():
    text = 'site:\n    a: L = 1\n    b: L = 0\n    flow r:\n        request = 1 L/h\n        flow l: this.a -> this.b\n'
    found = refused(text, 'layout', 5)
    assert 'give each leg its request and capacity' in found.message


# ---- the ends of a flow ------------------------------------------------------------------------------

PUMPS = """
    tank:
        water: L = 10 in [0,]

    Pump:
        basin: L = 0 in [0,]
        flow lift: tank.water -> this.basin
            request = 1 L/h{rest}

    p1: Pump
    """


def test_the_ends_of_a_flow_read_the_stores_at_its_ends():
    """Spec, "What each scope can see": a flow reads its two ends, which are fixed for the run. An
    end reads as its store, with the store's amount and its steps, so the program reads the store by
    its own path, from the member of the flow; a projection keeps the collection's keys."""
    rest = (
        '\n        below = formula(this.lift.source)'
        '\n        above = formula(this.lift.sink)'
        '\n        room = formula(this.lift.sink.inflow.request)'
    )
    text = (
        PUMPS.format(rest=rest)
        + 'held = formula(sum(Pump.instances.lift.sink))\n    first = formula(p1.lift.sink)\n'
    )
    b = Builder(UNITS)
    tank = b.entity('tank', value('water', 'L', 10, lower=0))
    pump = b.template(
        'Pump',
        value('basin', 'L', 0, lower=0),
        flow('lift', tank.water, this.basin, request=q(1, 'L/h')),
        value('below', 'L', formula(tank.water)),
        value('above', 'L', formula(this.basin)),
        value('room', 'L/h', formula(this.basin.inflow.request)),
    )
    b.member(pump, 'p1')
    b.root(
        value('held', 'L', formula(fsum(pump.instances.basin))),
        value('first', 'L', formula(named('p1').basin)),
    )
    assert same(text, b)


def test_the_ends_of_a_leg_and_of_a_leg_of_a_route_are_its_own():
    """A leg reads the ends that it writes; the forward leg of a route runs from its first end and
    the backward leg from its second."""
    rest = (
        '\n        drawn_from = formula(this.restore.labor.source)'
        '\n        backward_into = formula(this.swap.backward.sink)'
        '\n        flow swap: this.work <-> this.done'
    )
    text = SITES.format(rest=rest)
    b = _sites(
        value('drawn_from', 'crew_h', formula(this.crew.hours)),
        value('backward_into', 'work_unit', formula(this.work)),
        route('swap', this.work, this.done),
    )
    assert same(text, b)


@pytest.mark.parametrize(
    ('rest', 'tail', 'code', 'words'),
    [
        (
            '\n        flow out: this.basin -> SINK\n        x = formula(this.out.sink)',
            '',
            'flow_end',
            'is SINK',
        ),
        (
            '\n        x = formula(sum(this.basin.inflow.flows.source))',
            '',
            'flow_end',
            'may end at any store',
        ),
        ('', 'x = formula(sum(Pump.instances.lift.source))\n', 'collection', 'for every member'),
    ],
)
def test_an_end_that_holds_no_one_store_is_refused(rest, tail, code, words):
    text = PUMPS.format(rest=rest) + tail
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    assert caught.value.codes == [code], caught.value
    assert words in caught.value.problems[0].message
