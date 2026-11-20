"""The worked models of the spec as programs, with the results that the spec states.

Each function returns an `Example`: the program, the run configuration, and the expected results,
which are values at times (`At`), entries of the trace (`Traced`) or a failure (`Fails`). They are the
shared fixtures of the oracle, the engine and the front end: the front end lowers the spec's text to
the same program, and the oracle and the engine run it to the same numbers. `ROWS` maps each row of
the spec's table "Acceptance cases" to the examples that check it; the others are worked models of
the spec with stated numbers.

The expected numbers are the spec's, or worked by hand from its rules where a docstring says so; none
comes from a run. A value is stated in the declared unit of the value at its key (a rate in its flow's
unit), a time in hours, after the last round at that time. Members are named by their ids, an
occurrence by `receiver.event#n`, its start on that receiver counted from 0, and a part of the trace by
its origin (`build.py` gives the origins: `plant.inspect.step[1]`, `plant.inspect.when[0]`). An enum is
named by its spelling (`enum[FIXED, FAILED]`), as the front end names it: the language's enum is its
members.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

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
    chained,
    constraint,
    count,
    dist_of,
    draw,
    endpoint,
    event,
    fall,
    flow,
    fmax,
    formula,
    fsum,
    given,
    ifelse,
    input_,
    item,
    legs,
    link,
    local,
    maximize,
    minimize,
    move,
    named,
    param,
    priority,
    proportional,
    q,
    ref_to,
    reset_after,
    reset_when,
    route,
    solve_for,
    solver,
    start,
    subtract,
    switch,
    t,
    this,
    uniform,
    unknown,
    until,
    value,
    when,
)
from napkin.program.config import Configuration, InputValue, Quantity, Request
from napkin.program.parts import Program
from napkin.program.record import Key

# The units of the examples: a spelling and its dimension, or its dimension and its scale.
UNITS = {
    'h': {'time': 1},
    'year': ({'time': 1}, 8760),
    'L': {'volume': 1},
    'g': {'mass': 1},
    'Wh': {'energy': 1},
    'W': {'energy': 1, 'time': -1},
    'kWh': ({'energy': 1}, 1000),
    'kW': ({'energy': 1, 'time': -1}, 1000),
    'person': {'people': 1},
    'crew_h': {'crew_time': 1},
    'work_unit': {'work': 1},
}


@dataclass(frozen=True)
class At:
    """At time `t`, after its last round, the value at `key` is `value` (in its declared unit)."""

    t: Fraction
    key: Key
    value: object


@dataclass(frozen=True)
class Traced:
    """The trace has entries of `kind` for the part `part` at exactly these times, in order, and in
    these rounds when `rounds` is given. No times: no such entry."""

    kind: str
    part: str
    times: tuple
    rounds: tuple | None = None


@dataclass(frozen=True)
class Fails:
    """The run stops with a failure whose message holds `message`, at time `t` when it is given. The
    values stated with it are those committed when the run stopped."""

    message: str
    t: Fraction | None = None


@dataclass(frozen=True)
class Example:
    name: str
    program: Program
    configuration: Configuration
    expected: tuple


EXAMPLES = {}


def example(function):
    """Registers an example under the name of its function."""
    EXAMPLES[function.__name__] = function
    return function


def key(owner, *steps):
    return Key(owner, steps)


def run(horizon, **settings):
    """A median run to the horizon, recording everything."""
    return Configuration(Request(horizon), **settings)


def F(numerator, denominator=1):
    return Fraction(numerator, denominator)


def _example(name, b, horizon, expected, **settings):
    return Example(name, b.finish(), run(horizon, **settings), tuple(expected))


# ---- values, units, flows -------------------------------------------------------------------------


def _grinder(b):
    return b.entity(
        'grinder',
        value('beans', 'g', 8),
        value('low_on_beans', BOOL, formula(this.beans <= q(10, 'g')), readonly=True),
        event('refill', param('amount', 'g'), after(q(0.5, 'h'), add(this.beans, local.amount))),
    )


@example
def grinder_refill():
    """Spec, "How to declare, read and change a value": a grinder at 8 g and `refill.start(50 g)`
    has 58 g after half an hour, and `low_on_beans` reads false (acceptance row 1)."""
    b = Builder(UNITS)
    grinder = _grinder(b)
    b.setup(start(grinder.refill, q(50, 'g')))
    expected = [
        At(0, key('grinder', 'beans'), 8),
        At(0, key('grinder', 'low_on_beans'), True),
        At(F(1, 4), key('grinder', 'beans'), 8),
        At(F(1, 2), key('grinder', 'beans'), 58),
        At(F(1, 2), key('grinder', 'low_on_beans'), False),
        Traced('start', 'grinder.refill', (0,)),
        Traced('finish', 'grinder.refill', (F(1, 2),)),
    ]
    return _example('grinder_refill', b, 1, expected)


@example
def unit_division():
    """Spec, "Units, comparisons and layout": `48 h/2` and `48 h / 2` are both 24 h. The front end
    lowers both spellings to this one quotient of a quantity by a number (acceptance row 2)."""
    b = Builder(UNITS)
    b.root(value('close', 'h', q(48, 'h') / 2), value('spaced', 'h', q(48, 'h') / 2))
    return _example('unit_division', b, 0, [At(0, key('', 'close'), 24), At(0, key('', 'spaced'), 24)])


@example
def unit_product():
    """Spec, "Units, comparisons and layout": `(3 person) * (2 year)` is `6 person * year`
    (acceptance row 3)."""
    b = Builder(UNITS)
    b.root(value('effort', 'person * year', q(3, 'person') * q(2, 'year')))
    return _example('unit_product', b, 0, [At(0, key('', 'effort'), 6)])


@example
def tank_delivery():
    """Spec, "Flows and algebraic solvers": a tank of 8 L and a delivery that requests 3 L/h with a
    capacity of 5 L/h gives 3 L/h until the tank empties at 2 h 40 min, then 0; the request and the
    capacity still read 3 and 5 L/h (acceptance row 4)."""
    b = Builder(UNITS)
    tank = b.entity('tank', value('water', 'L', 8, lower=0, upper=20, readonly=True))
    b.entity('clinic', flow('delivery', tank.water, SINK, capacity=q(5, 'L/h'), request=q(3, 'L/h')))
    rate = key('clinic', 'delivery', 'actual_rate')
    expected = [
        At(0, rate, 3),
        At(2, rate, 3),
        At(2, key('tank', 'water'), 2),
        At(F(8, 3), key('tank', 'water'), 0),
        At(F(8, 3), rate, 0),
        At(3, rate, 0),
        At(3, key('clinic', 'delivery', 'request'), 3),
        At(3, key('clinic', 'delivery', 'capacity'), 5),
    ]
    return _example('tank_delivery', b, 3, expected)


def _reservoir(policy):
    """Spec, "Local allocation": a reservoir limited to 10 L/h and requests of 8 and 12 L/h."""
    b = Builder(UNITS)
    allocation = priority(named('hospital').delivery, named('garden').delivery) if policy else proportional()
    reservoir = b.entity(
        'reservoir',
        value(
            'water',
            'L',
            20,
            lower=0,
            upper=20,
            outflow=endpoint(capacity=q(10, 'L/h'), allocation=allocation),
        ),
    )
    b.entity('hospital', flow('delivery', reservoir.water, SINK, request=q(8, 'L/h')))
    b.entity('garden', flow('delivery', reservoir.water, SINK, request=q(12, 'L/h')))
    return b


@example
def reservoir_priority():
    """Spec, "Local allocation": `priority(hospital.delivery, garden.delivery)` gives 8 and 2 L/h,
    and the reservoir empties in two hours (acceptance row 5)."""
    b = _reservoir(True)
    hospital, garden = key('hospital', 'delivery', 'actual_rate'), key('garden', 'delivery', 'actual_rate')
    expected = [At(0, hospital, 8), At(0, garden, 2), At(1, key('reservoir', 'water'), 10)]
    expected += [At(2, key('reservoir', 'water'), 0), At(3, hospital, 0), At(3, garden, 0)]
    return _example('reservoir_priority', b, 3, expected)


@example
def reservoir_proportional():
    """Spec, "Local allocation": `proportional()` gives 4 and 6 L/h, the same half of each claim,
    and the reservoir empties in two hours (acceptance row 5)."""
    b = _reservoir(False)
    hospital, garden = key('hospital', 'delivery', 'actual_rate'), key('garden', 'delivery', 'actual_rate')
    expected = [At(0, hospital, 4), At(0, garden, 6), At(1, key('reservoir', 'water'), 10)]
    expected += [At(2, key('reservoir', 'water'), 0), At(3, hospital, 0), At(3, garden, 0)]
    return _example('reservoir_proportional', b, 3, expected)


@example
def common_sink():
    """Spec, "Local allocation": a common sink that requests 6 L/h with `priority(main, backup)`
    and `main.capacity = 4 L/h` gets 4 and 2 L/h, given supply and room (acceptance row 6)."""
    b = Builder(UNITS)
    b.entity(
        'clinic',
        value(
            'water',
            'L',
            0,
            lower=0,
            inflow=endpoint(request=q(6, 'L/h'), allocation=priority(this.main, this.backup)),
        ),
        flow('main', SOURCE, this.water, capacity=q(4, 'L/h')),
        flow('backup', SOURCE, this.water),
    )
    expected = [
        At(0, key('clinic', 'main', 'actual_rate'), 4),
        At(0, key('clinic', 'backup', 'actual_rate'), 2),
        At(1, key('clinic', 'water'), 6),
    ]
    return _example('common_sink', b, 1, expected)


def _one_pipe(name, cap_at):
    """Spec, "Capacity, request and bounds", "One pipe and three requests": the source, the pipe
    and the sink request 10, 8 and 6 L/h. With no binding cap the pipe carries 10 L/h, the least
    transfer that serves all three claims; a cap of 7 L/h at any of the three scopes makes it 7 L/h,
    with shortfalls of 3, 1 and 0 L/h (acceptance row 7)."""
    b = Builder(UNITS)
    cap = q(7, 'L/h')
    upstream = b.entity(
        'upstream',
        value(
            'water',
            'L',
            100,
            lower=0,
            outflow=endpoint(request=q(10, 'L/h'), capacity=cap if cap_at == 'source' else None),
        ),
    )
    downstream = b.entity(
        'downstream',
        value(
            'water',
            'L',
            0,
            lower=0,
            inflow=endpoint(request=q(6, 'L/h'), capacity=cap if cap_at == 'sink' else None),
        ),
    )
    pipe = b.entity(
        'pipe',
        flow(
            'carry',
            upstream.water,
            downstream.water,
            request=q(8, 'L/h'),
            capacity=cap if cap_at == 'pipe' else None,
        ),
    )
    zero = q(0, 'L/h')
    b.root(
        value(
            'source_short',
            'L/h',
            formula(fmax(zero, upstream.water.outflow.request - upstream.water.outflow.actual_rate)),
        ),
        value('pipe_short', 'L/h', formula(fmax(zero, pipe.carry.request - pipe.carry.actual_rate))),
        value(
            'sink_short',
            'L/h',
            formula(fmax(zero, downstream.water.inflow.request - downstream.water.inflow.actual_rate)),
        ),
    )
    rate = 10 if cap_at is None else 7
    shorts = (0, 0, 0) if cap_at is None else (3, 1, 0)
    expected = [At(0, key('pipe', 'carry', 'actual_rate'), rate)]
    expected += [
        At(0, key('', name), short)
        for name, short in zip(('source_short', 'pipe_short', 'sink_short'), shorts)
    ]
    expected += [At(1, key('downstream', 'water'), rate), At(1, key('upstream', 'water'), 100 - rate)]
    return _example(name, b, 1, expected)


@example
def one_pipe():
    """Spec, "Capacity, request and bounds": with no binding cap the pipe carries 10 L/h."""
    return _one_pipe('one_pipe', None)


@example
def one_pipe_capped_at_source():
    """Spec, "Capacity, request and bounds": `outflow.capacity = 7 L/h` at the source gives
    7 L/h, with shortfalls of 3, 1 and 0 L/h."""
    return _one_pipe('one_pipe_capped_at_source', 'source')


@example
def one_pipe_capped_at_pipe():
    """Spec, "Capacity, request and bounds": `capacity = 7 L/h` on the pipe gives 7 L/h, with
    shortfalls of 3, 1 and 0 L/h."""
    return _one_pipe('one_pipe_capped_at_pipe', 'pipe')


@example
def one_pipe_capped_at_sink():
    """Spec, "Capacity, request and bounds": `inflow.capacity = 7 L/h` at the sink gives 7 L/h,
    with shortfalls of 3, 1 and 0 L/h."""
    return _one_pipe('one_pipe_capped_at_sink', 'sink')


def _two_junctions(name, solved):
    """The junctions of "Sharing is local by default"; with `solved`, a provider's solver that
    determines the four requested rates (`'fair'`) or the upstream feed alone (`'upstream'`)."""
    b = Builder(UNITS)
    second = b.entity(
        'second',
        value('water', 'L', 0, lower=0, upper=0),
        flow('to_b', this.water, SINK, request=q(1, 'L/h')),
        flow('to_c', this.water, SINK, request=q(1, 'L/h')),
    )
    first = b.entity(
        'first',
        value('water', 'L', 0, lower=0, upper=0),
        flow('feed', SOURCE, this.water, capacity=q(1, 'L/h')),
        flow('to_a', this.water, SINK, request=q(1, 'L/h')),
        flow('onward', this.water, second.water, request=q(1, 'L/h')),
    )
    if solved == 'fair':
        names = {'a': first.to_a, 'onward': first.onward, 'b': second.to_b, 'c': second.to_c}
        parts = [given(name, source) for name, source in names.items()]
        parts += [solve_for(getattr(local, name).actual_rate) for name in names]
        b.entity('provider', solver('fair', *parts))
    elif solved == 'upstream':
        b.entity('provider', solver('upstream', given('feed', first.feed), solve_for(local.feed.actual_rate)))
    fair = solved == 'fair'
    share = F(1, 3) if fair else F(1, 4)
    expected = [
        At(0, key('first', 'to_a', 'actual_rate'), F(1, 3) if fair else F(1, 2)),
        At(0, key('first', 'onward', 'actual_rate'), 2 * share),
        At(0, key('second', 'to_b', 'actual_rate'), share),
        At(0, key('second', 'to_c', 'actual_rate'), share),
        At(0, key('first', 'feed', 'actual_rate'), 1),
    ]
    return _example(name, b, 1, expected)


@example
def two_junctions():
    """Spec, "Sharing is local by default": 1 L/h reaches a [0, 0] junction whose two pipes
    request 1 L/h each, one to A and one to a second junction that B and C share. Each junction
    shares its own inflow: A gets 1/2, B and C 1/4 each (acceptance row 8)."""
    return _two_junctions('two_junctions', None)


@example
def two_junctions_solver():
    """Spec, "Sharing is local by default": one solver that determines the four requested rates,
    with no objective, shares fairly across its claims, and A, B and C get 1/3 L/h each; the onward
    pipe carries B's and C's 2/3, and the feed, which no solver names, balances the first junction
    at 1 L/h (acceptance row 8)."""
    return _two_junctions('two_junctions_solver', 'fair')


@example
def two_junctions_upstream_solver():
    """The owner's rule after G2 (PLAN.md, change 19): a solver decides only the rates that it
    names, and a flow that it does not name keeps its endpoints' local sharing. A solver that names
    only the upstream feed of the junctions leaves 1/2, 1/4 and 1/4. Worked by hand: the feed is the
    solver's, with no request and no claim of its own; the four pipes are not, and their claims keep
    their levels of local sharing after the solver's claims. To A and onward, out of the first
    junction (held at 0 L, so it passes on what the feed brings), the level is one: each gets half of
    what the feed can bring, at most its capacity of 1 L/h, so the feed carries 1 L/h and A and
    onward 1/2 L/h each. B and C, out of the second junction, are at level two and split its 1/2:
    1/4 L/h each."""
    return _two_junctions('two_junctions_upstream_solver', 'upstream')


@example
def reversible_route():
    """Spec, "Flows and algebraic solvers", the table of legs: at `link.actual_rate = -3 L/h` the
    forward leg reads 0 and the backward leg 3 L/h (acceptance row 9). The route's signed request
    of -3 L/h, with stock and room at both ends, gives that rate; worked by hand, west gains and east
    loses 3 L each hour."""
    b = Builder(UNITS)
    west = b.entity('west', value('water', 'L', 10, lower=0, upper=20))
    east = b.entity('east', value('water', 'L', 10, lower=0, upper=20))
    b.entity('channel', route('link', west.water, east.water, request=q(-3, 'L/h')))
    expected = [
        At(0, key('channel', 'link', 'actual_rate'), -3),
        At(0, key('channel', 'link', 'forward', 'actual_rate'), 0),
        At(0, key('channel', 'link', 'backward', 'actual_rate'), 3),
        At(1, key('west', 'water'), 13),
        At(1, key('east', 'water'), 7),
    ]
    return _example('reversible_route', b, 1, expected)


def _legs(name, labor, work, labor_cap, fraction):
    """Spec, "Shared resources and competing invocations": a flow with a labor leg (crew_h) and a
    work leg (work_unit), served at one fraction (acceptance row 10)."""
    b = Builder(UNITS)
    crew = b.entity('crew', value('hours', 'crew_h', 100, lower=0), value('used', 'crew_h', 0, lower=0))
    capacity = None if labor_cap is None else q(labor_cap, 'crew_h/h')
    b.entity(
        'site',
        link('crew', 'crew'),
        value('controls_work', 'work_unit', 100, lower=0),
        value('controls_done', 'work_unit', 0, lower=0),
        legs(
            'restore',
            flow('labor', this.crew.hours, this.crew.used, request=q(labor, 'crew_h/h'), capacity=capacity),
            flow('work', this.controls_work, this.controls_done, request=q(work, 'work_unit/h')),
        ),
        crew=crew,
    )
    expected = [
        At(0, key('site', 'restore', 'served_fraction'), fraction),
        At(0, key('site', 'restore', 'labor', 'actual_rate'), fraction * labor),
        At(0, key('site', 'restore', 'work', 'actual_rate'), fraction * work),
    ]
    return _example(name, b, 1, expected)


@example
def legs_half_service():
    """Spec, "Shared resources and competing invocations": legs that request 4 crew_h/h and
    8 work_unit/h, with labor limited to 2 crew_h/h, are served at 1/2 and carry 2 and 4."""
    return _legs('legs_half_service', 4, 8, 2, F(1, 2))


@example
def legs_zero_leg():
    """Spec, "Shared resources and competing invocations": legs that request 0 and 8, with ample
    capacity, carry 0 and 8 at fraction 1."""
    return _legs('legs_zero_leg', 0, 8, None, 1)


@example
def legs_all_zero():
    """Spec, "Shared resources and competing invocations": when every leg requests 0, the
    fraction is defined as 0."""
    return _legs('legs_all_zero', 0, 0, None, 0)


@example
def deliveries_current_flows():
    """Spec, "Flows created during a run": each `deliver` owns a pipe of 2 L/h from the tank.
    Delivery A runs from 1 h to 2 h and B from 3 h to 4 h. The occurrences are 0, 1, 1, 2 and the
    current flows 0, 1, 0, 1 at the four moments of the table; between A and B, the newest
    occurrence's pipe still reads A's frozen 2 L/h (acceptance row 11)."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 100, lower=0),
        event(
            'deliver',
            flow('pipe', this.water, SINK, request=q(2, 'L/h')),
            after(q(1, 'h')),
            when(t >= q(1, 'h'), start(this.deliver), reset=reset_when(False)),
            when(t >= q(3, 'h'), start(this.deliver), reset=reset_when(False)),
        ),
    )
    b.root(
        value('started', '', formula(count(tank.deliver.occurrences))),
        value('current', '', formula(count(tank.water.outflow.flows))),
        value('requested', 'L/h', formula(fsum(tank.water.outflow.flows.request))),
        value('outflow', 'L/h', formula(tank.water.outflow.actual_rate)),
        value('newest_request', 'L/h', formula(tank.deliver.occurrences.at(t).pipe.request)),
    )
    expected = []
    for moment, row in zip(
        (F(1, 2), F(3, 2), F(5, 2), F(7, 2)), ((0, 0, 0, 0), (1, 1, 2, 2), (1, 0, 0, 0), (2, 1, 2, 2))
    ):
        expected += [
            At(moment, key('', name), number)
            for name, number in zip(('started', 'current', 'requested', 'outflow'), row)
        ]
    expected += [At(F(3, 2), key('', 'newest_request'), 2), At(F(5, 2), key('', 'newest_request'), 2)]
    expected += [At(F(7, 2), key('', 'newest_request'), 2), At(4, key('tank', 'water'), 96)]
    return _example('deliveries_current_flows', b, 4, expected)


# ---- the worked network ----------------------------------------------------------------------------

PLACES = (
    {'id': 'junction', 'supply_limit': 8, 'base_need': 0, 'critical': False},
    {'id': 'clinic', 'supply_limit': 0, 'base_need': 6, 'critical': True},
    {'id': 'garden', 'supply_limit': 0, 'base_need': 6, 'critical': False},
)
ROUTES = (
    {
        'id': 'junction_clinic',
        'origin': 'sites.junction',
        'destination': 'sites.clinic',
        'closes_at_two': False,
    },
    {
        'id': 'garden_junction',
        'origin': 'sites.garden',
        'destination': 'sites.junction',
        'closes_at_two': True,
    },
)
# A table's cells are read as written: `0.5` is a float.
READINGS = ({'hour': 0, 'factor': 1}, {'hour': 1, 'factor': 0.5}, {'hour': 2, 'factor': 1})


def network_program(places=PLACES, routes=ROUTES, critical_first=False, power='W'):
    """Spec, "Using collections in a solver": three places, two reversible routes and hourly
    readings, from the tables of "Worked network data and expected rates". `power` is the unit of
    every power of the model (`kW` writes it in kW and kWh, the route strength 0.001 kW, and the
    table's cells 0.008 and 0.006 as the file writes them). As in its source, a flow's rates are in
    its stores' unit per hour (`Wh/h`, `kWh/h`), which measures what `W` and `kW` measure."""
    energy = 'Wh' if power == 'W' else 'kWh'
    b = Builder(UNITS)
    readings = b.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
    places_template = b.template(
        'Place',
        input_('base_need', power, 0),
        input_('supply_limit', power, 0),
        input_('critical', BOOL, False),
        value('level', '', 0, lower=-30, upper=30),
        value('power', energy, 0, lower=0, upper=0),
        value('need', power, formula(this.base_need * readings.instances.by('hour').at(t).factor)),
        flow('supply', SOURCE, this.power, capacity=this.supply_limit),
        flow('use', this.power, SINK, request=formula(this.need), capacity=formula(this.need)),
        value('unmet', power, formula(fmax(q(0, power), this.use.request - this.use.actual_rate))),
    )
    routes_template = b.template(
        'Route',
        link('origin', 'Place'),
        link('destination', 'Place'),
        input_('strength', power, 1 if power == 'W' else 0.001),
        input_('closes_at_two', BOOL, False),
        value('up', BOOL, True),
        value('pull', power, formula(ifelse(this.up, this.strength, q(0, power)))),
        route('carried', this.origin.power, this.destination.power),
        value(
            'rate_follows_levels',
            BOOL,
            formula(this.carried.actual_rate == this.pull * (this.origin.level - this.destination.level)),
        ),
        event(
            'close',
            when(this.closes_at_two & (t >= q(2, 'h')), start(this.close), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.up, False)),
        ),
    )
    scaled = [dict(row) for row in places]
    if power == 'kW':
        for row in scaled:
            for name in ('supply_limit', 'base_need'):
                row[name] = row[name] / 1000 if row[name] else 0
    b.table('sites', places_template, scaled)
    b.table('links', routes_template, routes)
    b.table('readings', readings, READINGS)
    objective = [minimize(fsum(local.places.unmet))]
    if critical_first:
        objective.insert(0, minimize(fsum(local.places.where(item.critical).unmet)))
    b.entity(
        'provider',
        solver(
            'dispatch',
            given('places', places_template.instances),
            given('routes', routes_template.instances),
            solve_for(local.places.level),
            solve_for(local.places.supply.actual_rate),
            solve_for(local.places.use.actual_rate),
            solve_for(local.routes.carried.actual_rate),
            constraint(fall(local.routes.rate_follows_levels)),
            *objective,
        ),
    )
    return b.finish()


def _network_rows(moment, clinic, garden, supply, to_clinic, from_garden, levels=None):
    """One row of the spec's table of rates, and the levels (junction, clinic, garden)."""
    found = [
        At(moment, key('sites.clinic', 'use', 'actual_rate'), clinic),
        At(moment, key('sites.garden', 'use', 'actual_rate'), garden),
        At(moment, key('sites.junction', 'supply', 'actual_rate'), supply),
        At(moment, key('links.junction_clinic', 'carried', 'actual_rate'), to_clinic),
        At(moment, key('links.garden_junction', 'carried', 'actual_rate'), from_garden),
    ]
    for place, level in zip(('junction', 'clinic', 'garden'), levels or ()):
        found.append(At(moment, key(f'sites.{place}', 'level'), level))
    return found


@example
def network():
    """Spec, "Worked network data and expected rates": at 0 h the equally ranked 6 W claims get 4 W
    each and the levels are (8/3, -4/3, -4/3); at 1 h the demands fall to 3 W and are met; at 2 h,
    after the garden route closes, the clinic gets 6 W and the garden none, with levels (3, -3, 0)
    (acceptance row 12). The levels at 1 h, (2, -1, -1), are worked by hand from the same rule:
    the least sum of squares with the route equations."""
    expected = _network_rows(0, 4, 4, 8, 4, -4, (F(8, 3), F(-4, 3), F(-4, 3)))
    expected += _network_rows(1, 3, 3, 6, 3, -3, (2, -1, -1))
    expected += _network_rows(2, 6, 0, 6, 6, 0, (3, -3, 0))
    expected += [
        At(2, key('links.garden_junction', 'up'), False),
        Traced('fire', 'Route.close.when[0]', (2,)),
    ]
    return Example('network', network_program(), run(2), tuple(expected))


@example
def network_clinic_first():
    """Spec, "Worked network data and expected rates": with `minimize(sum(places.where(critical).
    unmet))` first, the clinic gets 6 W and the garden 2 W at 0 h. The levels (8/3, -10/3, 2/3) are
    worked by hand."""
    expected = _network_rows(0, 6, 2, 8, 6, -2, (F(8, 3), F(-10, 3), F(2, 3)))
    return Example('network_clinic_first', network_program(critical_first=True), run(0), tuple(expected))


@example
def network_unequal():
    """Spec, "Worked network data and expected rates": with requests of 2 W and 6 W and a supply of
    4 W, proportional service gives 1 W and 3 W. The routes' rates and the levels (4/3, 1/3, -5/3)
    are worked by hand."""
    places = (
        {**PLACES[0], 'supply_limit': 4},
        {**PLACES[1], 'base_need': 2},
        PLACES[2],
    )
    expected = _network_rows(0, 1, 3, 4, 1, -3, (F(4, 3), F(1, 3), F(-5, 3)))
    return Example('network_unequal', network_program(places=places), run(0), tuple(expected))


@example
def network_kw():
    """Spec, "Worked network data and expected rates": with the model written in kW, the two
    baseline deliveries are each 0.004 kW, and the levels are unchanged, since the distance step
    does not depend on the units in which a model writes its rates."""
    k = F(1, 1000)
    expected = _network_rows(0, 4 * k, 4 * k, 8 * k, 4 * k, -4 * k, (F(8, 3), F(-4, 3), F(-4, 3)))
    return Example('network_kw', network_program(power='kW'), run(0), tuple(expected))


# ---- solvers -------------------------------------------------------------------------------------


def _two_bottlenecks(name, total_first):
    """Spec, "Acceptance case with two bottlenecks": three consumers request 6 W each, with
    `a + b <= 4 W` and `b + c <= 5 W` (acceptance row 13)."""
    b = Builder(UNITS)
    consumer = b.template(
        'Consumer',
        value('received', 'Wh', 0, lower=0),
        flow('use', SOURCE, this.received, request=q(6, 'W'), capacity=q(6, 'W')),
        value('unmet', 'W', formula(fmax(q(0, 'W'), this.use.request - this.use.actual_rate))),
    )
    for id in 'abc':
        b.member(consumer, id)
    parts = [given('consumers', consumer.instances)]
    parts += [given(f'use_{id}', named(id).use) for id in 'abc']
    parts += [
        solve_for(local.consumers.use.actual_rate),
        constraint(local.use_a.actual_rate + local.use_b.actual_rate <= q(4, 'W')),
        constraint(local.use_b.actual_rate + local.use_c.actual_rate <= q(5, 'W')),
    ]
    if total_first:
        parts.append(minimize(fsum(local.consumers.unmet)))
    b.entity('provider', solver('allocation', *parts))
    b.root(value('total_unmet', 'W', formula(fsum(consumer.instances.unmet))))
    rates = (4, 0, 5) if total_first else (2, 2, 3)
    expected = [At(0, key(id, 'use', 'actual_rate'), rate) for id, rate in zip('abc', rates)]
    expected.append(At(0, key('', 'total_unmet'), 9 if total_first else 11))
    return _example(name, b, 0, expected)


@example
def two_bottlenecks_fair():
    """Spec, "Acceptance case with two bottlenecks": with no objective, equal-priority fair
    sharing gives (2, 2, 3) W and 11 W unmet."""
    return _two_bottlenecks('two_bottlenecks_fair', False)


@example
def two_bottlenecks_total_unmet():
    """Spec, "Acceptance case with two bottlenecks": with `minimize(sum(consumers.unmet))`
    first, (4, 0, 5) W and 9 W unmet; B is left unserved."""
    return _two_bottlenecks('two_bottlenecks_total_unmet', True)


def _staffing_solver():
    return solver(
        'staffing',
        given('available', this.staff_hours),
        given('minimum_outreach', this.outreach_minimum),
        unknown('care', 'h', lower=q(0, 'h'), upper=local.available),
        unknown('outreach', 'h', lower=local.minimum_outreach, upper=local.available),
        constraint(local.care + local.outreach == local.available),
        maximize(local.care),
    )


@example
def staffing():
    """Spec, "Allocating staff hours": with 100 h, care 70 h and outreach 30 h; when the staff
    falls to 80 h at 1 h, the live minimum is 24 h and care 56 h (acceptance row 14). Spec, "Time,
    waiting and completion": a delay of `this.staffing.care`, captured at the commit that cuts the
    staff, uses the settled 56 h, so the next stage runs at 57 h."""
    b = Builder(UNITS)
    clinic = b.entity(
        'clinic',
        value('staff_hours', 'h', 100),
        value('outreach_minimum', 'h', formula(0.30 * this.staff_hours)),
        value('planned', BOOL, False),
        _staffing_solver(),
        event(
            'plan',
            after(q(1, 'h'), assign(this.staff_hours, q(80, 'h'))),
            after(this.staffing.care, assign(this.planned, True)),
        ),
    )
    b.setup(start(clinic.plan))
    care, outreach = key('clinic', 'staffing', 'care'), key('clinic', 'staffing', 'outreach')
    expected = [At(0, care, 70), At(0, outreach, 30), At(1, care, 56), At(1, outreach, 24)]
    expected += [At(1, key('clinic', 'outreach_minimum'), 24), At(56, key('clinic', 'planned'), False)]
    expected += [At(57, key('clinic', 'planned'), True), Traced('commit', 'clinic.plan.step[1]', (57,))]
    return _example('staffing', b, 57, expected)


def _pump_battery(name, water, requests, expected):
    """Spec, "Water and electricity in one coordinated decision": a pump of 0.5 Wh/L, a charger of
    1 W, a tank and a clinic-first provider (acceptance row 15). As in its source, the pump's power
    flow is in its battery's unit per hour (`Wh/h`, which measures what `W` measures)."""
    b = Builder(UNITS)
    tank = b.entity('tank', value('water', 'L', water, lower=0, upper=20))
    battery = b.entity(
        'battery',
        value('energy', 'Wh', 0, lower=0, upper=4),
        flow('charge', SOURCE, this.energy, capacity=q(1, 'W')),
    )
    pump = b.entity(
        'pump',
        flow('fill', SOURCE, tank.water, capacity=q(4, 'L/h')),
        flow('power', battery.energy, SINK),
    )
    clinic = b.entity('clinic', flow('delivery', tank.water, SINK, request=q(requests, 'L/h')))
    town = b.entity('town', flow('delivery', tank.water, SINK, request=q(requests, 'L/h')))
    names = {
        'charge': battery.charge,
        'motor': pump.power,
        'fill': pump.fill,
        'clinic_use': clinic.delivery,
        'town_use': town.delivery,
    }
    parts = [given(name, source) for name, source in names.items()]
    parts += [solve_for(getattr(local, name).actual_rate) for name in names]
    zero = q(0, 'L/h')
    parts += [
        constraint(local.motor.actual_rate == local.fill.actual_rate * q(0.5, 'Wh/L')),
        minimize(fmax(zero, local.clinic_use.request - local.clinic_use.actual_rate)),
        minimize(fmax(zero, local.town_use.request - local.town_use.actual_rate)),
        minimize(local.fill.actual_rate),
        minimize(local.charge.actual_rate),
    ]
    b.entity('provider', solver('distribution', *parts))
    return _example(name, b, 1, expected)


def _pump_rates(moment, fill, clinic, town, motor, charge):
    return [
        At(moment, key('pump', 'fill', 'actual_rate'), fill),
        At(moment, key('clinic', 'delivery', 'actual_rate'), clinic),
        At(moment, key('town', 'delivery', 'actual_rate'), town),
        At(moment, key('pump', 'power', 'actual_rate'), motor),
        At(moment, key('battery', 'charge', 'actual_rate'), charge),
    ]


@example
def pump_battery():
    """Spec, "Water and electricity in one coordinated decision": with both stocks empty, the
    charger's 1 W lets the pump fill 2 L/h, which the clinic gets first; the town gets nothing
    (acceptance row 15)."""
    expected = _pump_rates(0, 2, 2, 0, 1, 1) + _pump_rates(1, 2, 2, 0, 1, 1)
    return _pump_battery('pump_battery', 0, 6, expected)


@example
def pump_battery_stocked():
    """Spec, "Water and electricity in one coordinated decision": with 10 L in the tank, the
    final flow targets give exactly 6 L/h to each destination with zero fill and charge. Worked by
    hand: the tank empties at 5/6 h, and from then on the empty-tank answer holds."""
    expected = [*_pump_rates(0, 0, 6, 6, 0, 0), At(F(5, 6), key('tank', 'water'), 0)]
    expected += _pump_rates(1, 2, 2, 0, 1, 1)
    return _pump_battery('pump_battery_stocked', 10, 6, expected)


@example
def pump_battery_idle():
    """Spec, "Water and electricity in one coordinated decision": in the empty-tank case,
    withdrawing both requests leaves every transfer idle."""
    return _pump_battery('pump_battery_idle', 0, 0, _pump_rates(0, 0, 0, 0, 0, 0))


def _provider_limit(name, east_request, expected):
    """Spec, "A provider limit across separate connections": two chargers of 6 W, each with a 10 Wh
    battery, and a contract of 8 W (acceptance row 16)."""
    b = Builder(UNITS)
    east = b.entity(
        'east_site',
        value('energy', 'Wh', 0, lower=0, upper=10),
        flow('charge', SOURCE, this.energy, capacity=q(6, 'W'), request=q(east_request, 'W')),
    )
    west = b.entity(
        'west_site',
        value('energy', 'Wh', 0, lower=0, upper=10),
        flow('charge', SOURCE, this.energy, capacity=q(6, 'W'), request=q(6, 'W')),
    )
    zero = q(0, 'W')
    b.entity(
        'provider',
        value('contract_limit', 'W', 8),
        solver(
            'charging',
            given('east', east.charge),
            given('west', west.charge),
            given('limit', this.contract_limit),
            solve_for(local.east.actual_rate),
            solve_for(local.west.actual_rate),
            constraint(local.east.actual_rate + local.west.actual_rate <= local.limit),
            minimize(fmax(zero, local.east.request - local.east.actual_rate)),
            minimize(fmax(zero, local.west.request - local.west.actual_rate)),
            minimize(local.east.actual_rate + local.west.actual_rate),
        ),
    )
    return _example(name, b, 3, expected)


def _charges(moment, east, west):
    return [
        At(moment, key('east_site', 'charge', 'actual_rate'), east),
        At(moment, key('west_site', 'charge', 'actual_rate'), west),
    ]


@example
def provider_limit():
    """Spec, "A provider limit across separate connections": 6 W to East and 2 W to West; once
    East is full, at 5/3 h, it draws nothing and West draws 6 W. Worked by hand: West holds 16/3 Wh
    at 2 h and is full at 25/9 h."""
    expected = [*_charges(0, 6, 2), At(F(5, 3), key('east_site', 'energy'), 10)]
    expected += [*_charges(2, 0, 6), At(2, key('west_site', 'energy'), F(16, 3))]
    expected += [At(F(25, 9), key('west_site', 'energy'), 10), *_charges(3, 0, 0)]
    return _provider_limit('provider_limit', 6, expected)


@example
def provider_limit_east_low():
    """Spec, "A provider limit across separate connections": with East asking 2 W, they get
    2 W and 6 W. Worked by hand: West is full at 5/3 h, and East
    keeps its 2 W."""
    return _provider_limit('provider_limit_east_low', 2, _charges(0, 2, 6) + _charges(2, 2, 0))


def _distance(name, targets, equality, answer):
    """The acceptance row "`4 <= x + y <= 6` in the distance step" (spec, "Final targets for flows
    and other unknowns"): two plain unknowns, equally scaled, and their written initializers as
    their preferred values (acceptance row 17)."""
    b = Builder(UNITS)
    test = local.x + local.y == 1 if equality else chained(4, local.x + local.y, 6)
    b.entity(
        'plan',
        solver(
            'split', unknown('x', '', init=targets[0]), unknown('y', '', init=targets[1]), constraint(test)
        ),
    )
    expected = [At(0, key('plan', 'split', 'x'), answer[0]), At(0, key('plan', 'split', 'y'), answer[1])]
    return _example(name, b, 0, expected)


@example
def distance_targets_zero():
    """Spec, "Final targets for flows and other unknowns": targets (0, 0) give (2, 2)."""
    return _distance('distance_targets_zero', (0, 0), False, (2, 2))


@example
def distance_targets_five():
    """Spec, "Final targets for flows and other unknowns": targets (5, 5) give (3, 3)."""
    return _distance('distance_targets_five', (5, 5), False, (3, 3))


@example
def distance_equality():
    """Spec, "Final targets for flows and other unknowns": `x + y == 1` with targets zero
    gives (1/2, 1/2)."""
    return _distance('distance_equality', (0, 0), True, (F(1, 2), F(1, 2)))


@example
def shared_limit():
    """Spec, "Shared resources and competing invocations": a supply with `outflow.capacity = 3 L/h`
    and deliveries that each request 2 L/h for two hours. A runs from 0 h and B from 1 h: A alone
    gets 2, A and B 1.5 each, B alone 2, then none (acceptance row 18)."""
    b = Builder(UNITS)
    depot = b.entity(
        'depot',
        value('supply', 'L', 100, lower=0, outflow=endpoint(capacity=q(3, 'L/h'))),
        event(
            'deliver',
            flow('pipe', this.supply, SINK, request=q(2, 'L/h')),
            after(q(2, 'h')),
            when(t >= q(1, 'h'), start(this.deliver), reset=reset_when(False)),
        ),
    )
    b.setup(start(depot.deliver))
    a, bb = key('depot.deliver#0', 'pipe', 'actual_rate'), key('depot.deliver#1', 'pipe', 'actual_rate')
    total = key('depot', 'supply', 'outflow', 'actual_rate')
    expected = [At(F(1, 2), a, 2), At(F(1, 2), total, 2), At(F(3, 2), a, F(3, 2)), At(F(3, 2), bb, F(3, 2))]
    expected += [At(F(3, 2), total, 3), At(F(5, 2), bb, 2), At(F(5, 2), a, 0), At(F(5, 2), total, 2)]
    expected += [At(F(7, 2), total, 0), At(F(7, 2), key('depot', 'supply'), 93)]
    return _example('shared_limit', b, 4, expected)


# ---- rounds, stages, triggers ------------------------------------------------------------------------


@example
def same_round_writes():
    """Spec, "Solver and execution contract", "Rounds" (D5): starting with 20 g, a stage that sets
    8 g and a later stage of the same round that adds 4 g leave 12 g (acceptance row 19)."""
    b = Builder(UNITS)
    jar = b.entity(
        'jar',
        value('amount', 'g', 20),
        event('set_low', after(q(0, 'h'), assign(this.amount, q(8, 'g')))),
        event('add_some', after(q(0, 'h'), add(this.amount, q(4, 'g')))),
    )
    b.setup(start(jar.set_low), start(jar.add_some))
    expected = [
        At(0, key('jar', 'amount'), 12),
        Traced('commit', 'jar.set_low.step[0]', (0,), (1,)),
        Traced('commit', 'jar.add_some.step[0]', (0,), (1,)),
    ]
    return _example('same_round_writes', b, 1, expected)


@example
def two_writes_one_solve():
    """Spec, "Solver and execution contract", "Rounds" (D5): two writes in one round cause one
    solve, and a trigger that reacts to the result causes a second round, with a second solve, at
    the same time (acceptance row 20). Two stages at 1 h cut the staff of the solver of "Allocating
    staff hours" to 80 h; a trigger on `care <= 60 h` restores 100 h in the next round. Setup has
    its own solve in round zero."""
    b = Builder(UNITS)
    office = b.entity(
        'office',
        value('staff_hours', 'h', 100),
        value('outreach_minimum', 'h', formula(0.30 * this.staff_hours)),
        _staffing_solver(),
        event('lower', after(q(1, 'h'), assign(this.staff_hours, q(90, 'h')))),
        event('trim', after(q(1, 'h'), subtract(this.staff_hours, q(10, 'h')))),
        event(
            'restore',
            when(this.staffing.care <= q(60, 'h'), start(this.restore), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.staff_hours, q(100, 'h'))),
        ),
    )
    b.setup(start(office.lower), start(office.trim))
    expected = [
        Traced('solve', 'office.staffing', (0, 1, 1), (0, 1, 2)),
        Traced('fire', 'office.restore.when[0]', (1,), (1,)),
        At(1, key('office', 'staff_hours'), 100),
        At(1, key('office', 'staffing', 'care'), 70),
    ]
    return _example('two_writes_one_solve', b, 1, expected)


def _inspect(name, outage, safe_at_five):
    """Spec, "Time, waiting and completion": `inspect.start(3 h)` runs its stages at hours 3 and 5;
    the guard of the second is read once, when it comes due, so a loss of safety that is over by
    then does not matter; then the gate waits for clearance at 6 h (acceptance row 21). `outage` is
    the time at which safety is lost and how long it stays lost, as a model text writes them (a
    decimal is a float, `4.5 h`)."""
    b = Builder(UNITS)
    plant = b.entity(
        'plant',
        value('safe', BOOL, True),
        value('clearance_received', BOOL, False),
        event(
            'inspect',
            param('delay', 'h'),
            after(local.delay, assign(local.delay, q(2, 'h'))),
            after(local.delay, start(this.inspect_equipment), when=this.safe),
            until(this.clearance_received),
            after(q(0, 'h'), start(this.record_clearance)),
        ),
        event('inspect_equipment'),
        event('record_clearance'),
        event(
            'outage',
            when(t >= q(outage[0], 'h'), start(this.outage), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.safe, False)),
            after(q(outage[1], 'h'), assign(this.safe, True)),
        ),
        event(
            'clear',
            when(t >= q(6, 'h'), start(this.clear), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.clearance_received, True)),
        ),
    )
    b.setup(start(plant.inspect, q(3, 'h')))
    expected = [
        Traced('commit', 'plant.inspect.step[0]', (3,)),
        Traced('start', 'plant.inspect_equipment', (5,) if safe_at_five else ()),
        Traced('start', 'plant.record_clearance', (6,)),
        Traced('finish', 'plant.inspect', (6,)),
    ]
    if safe_at_five:
        expected.append(Traced('commit', 'plant.inspect.step[1]', (5,)))
    return _example(name, b, 7, expected)


@example
def inspect_guard_read_once():
    """Spec, "Time, waiting and completion": safety is lost from 4 h to 4.5 h and holds at
    5 h, so the equipment inspection starts at 5 h."""
    return _inspect('inspect_guard_read_once', (4, 0.5), True)


@example
def inspect_guard_false():
    """Spec, "Time, waiting and completion": safety is lost from 4.5 h to 5.5 h, so at 5 h the
    guard is false, the body is skipped, and the invocation goes on to the gate and finishes at
    6 h."""
    return _inspect('inspect_guard_false', (4.5, 1), False)


@example
def clock_trigger():
    """Spec, "A trigger belongs to its event": `when t >= 3 h` with `reset after 3 h` fires at hours
    3, 6 and 9 (acceptance row 22)."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('inspections', '', 0),
        event(
            'inspect',
            when(t >= q(3, 'h'), start(this.inspect), reset=reset_after(q(3, 'h'))),
            after(q(0, 'h'), add(this.inspections, 1)),
        ),
    )
    expected = [Traced('fire', 'plant.inspect.when[0]', (3, 6, 9)), At(10, key('plant', 'inspections'), 3)]
    return _example('clock_trigger', b, 10, expected)


@example
def alarm_cooldown():
    """Spec, "A trigger belongs to its event": a conditional alarm with a three-hour cooldown that
    becomes eligible at hour three but fires at hour four is eligible again at hour seven. The alarm
    holds at 0 h, fails at 1 h and holds again from 4 h, so it fires at 0, 4 and 7 h (worked by hand
    from the rule)."""
    b = Builder(UNITS)
    plant = b.entity(
        'plant',
        value('alarm', BOOL, True),
        value('alarms', '', 0),
        event(
            'quiet', after(q(1, 'h'), assign(this.alarm, False)), after(q(3, 'h'), assign(this.alarm, True))
        ),
        event(
            'sound',
            when(this.alarm, start(this.sound), reset=reset_after(q(3, 'h'))),
            after(q(0, 'h'), add(this.alarms, 1)),
        ),
    )
    b.setup(start(plant.quiet))
    expected = [Traced('fire', 'plant.sound.when[0]', (0, 4, 7)), At(8, key('plant', 'alarms'), 3)]
    return _example('alarm_cooldown', b, 8, expected)


@example
def grinder_trigger_and_manual():
    """Spec, "A trigger belongs to its event": a grinder at 8 g whose low-beans trigger and a manual
    start of 50 g both refill it reaches 108 g (acceptance row 23). The manual start is the setup's,
    occurrence #0; the trigger fires at its first check, after setup, and starts #1."""
    b = Builder(UNITS)
    states = b.enum('enum[WEIGHING, ADDED]', 'WEIGHING', 'ADDED')
    grinder = b.entity(
        'grinder',
        value('beans', 'g', 8),
        value('low_on_beans', BOOL, formula(this.beans <= q(10, 'g')), readonly=True),
        event(
            'refill',
            param('amount', 'g'),
            value('status', states, states.WEIGHING),
            when(
                this.low_on_beans, start(this.refill, q(50, 'g')), reset=reset_when(this.beans >= q(30, 'g'))
            ),
            after(q(0.5, 'h'), add(this.beans, local.amount), assign(local.status, states.ADDED)),
        ),
    )
    b.setup(start(grinder.refill, q(50, 'g')))
    expected = [
        At(F(1, 2), key('grinder', 'beans'), 108),
        At(F(1, 4), key('grinder.refill#1', 'status'), 'WEIGHING'),
        At(F(1, 2), key('grinder.refill#0', 'status'), 'ADDED'),
        At(F(1, 2), key('grinder.refill#1', 'status'), 'ADDED'),
        Traced('start', 'grinder.refill', (0, 0)),
        Traced('fire', 'grinder.refill.when[0]', (0,)),
    ]
    return _example('grinder_trigger_and_manual', b, 1, expected)


@example
def crossing_drain():
    """Spec, "Monitoring a threshold": a tank at 11 L draining 1 L/h reaches `water <= 10 L` at
    hour 1, between scheduled events, and the trigger fires then (acceptance row 24)."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 11, lower=0),
        value('alarms', '', 0),
        flow('drain', this.water, SINK, request=q(1, 'L/h')),
        event(
            'alarm',
            when(this.water <= q(10, 'L'), start(this.alarm), reset=reset_when(False)),
            after(q(0, 'h'), add(this.alarms, 1)),
        ),
    )
    expected = [Traced('fire', 'tank.alarm.when[0]', (1,)), At(1, key('tank', 'water'), 10)]
    expected.append(At(2, key('tank', 'alarms'), 1))
    return _example('crossing_drain', b, 2, expected)


@example
def crossing_rejoin():
    """Spec, "Monitoring a threshold": a tank at 10 L filling 1 L/h, and an occurrence that drains
    2 L/h more from hour 2 to hour 4: 12 L at hour 2, 10 L at hour 4, and a trigger on `>= 16 L`
    fires at hour 10 (acceptance row 25)."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0),
        flow('fill', SOURCE, this.water, request=q(1, 'L/h')),
        event(
            'drain',
            flow('pipe', this.water, SINK, request=q(2, 'L/h')),
            after(q(2, 'h')),
            when(t >= q(2, 'h'), start(this.drain), reset=reset_when(False)),
        ),
        event('alarm', when(this.water >= q(16, 'L'), start(this.alarm), reset=reset_when(False))),
    )
    expected = [
        At(2, key('tank', 'water'), 12),
        At(4, key('tank', 'water'), 10),
        At(10, key('tank', 'water'), 16),
    ]
    expected.append(Traced('fire', 'tank.alarm.when[0]', (10,)))
    return _example('crossing_rejoin', b, 11, expected)


# ---- occurrences and their stores --------------------------------------------------------------------


@example
def retirement_failure():
    """Spec, "Time, waiting and completion", "Retirement": 20 L moves into an occurrence's batch and
    12 L is delivered at 4 L/h over three hours; finishing with the other 8 L in the batch fails the
    run, which names the 8 L (acceptance row 26)."""
    b = Builder(UNITS)
    customer = b.entity('customer', value('water', 'L', 0, lower=0))
    depot = b.entity(
        'depot',
        value('supply', 'L', 100, lower=0),
        event(
            'deliver',
            value('batch', 'L', 0, lower=0, upper=20),
            flow('out', local.batch, customer.water, request=q(4, 'L/h')),
            after(q(0, 'h'), move(q(20, 'L'), this.supply, local.batch)),
            after(q(3, 'h')),
        ),
    )
    b.setup(start(depot.deliver))
    expected = [
        At(2, key('customer', 'water'), 8),
        At(2, key('depot.deliver#0', 'batch'), 12),
        At(2, key('depot', 'supply'), 80),
        Fails('8 L', 3),
    ]
    return _example('retirement_failure', b, 4, expected)


def _ramp(name, change, horizon, expected):
    """Spec, "Delivering at a changing rate": `tank.receive.start(20 L, 5 L/h, change)`, whose
    request `max(0 L/h, starting_rate + rate_change * (t - started_at))` drains a batch of 20 L that
    the invocation brings with it."""
    b = Builder(UNITS)
    tank = b.entity(
        'tank',
        value('water', 'L', 0, lower=0),
        event(
            'receive',
            param('amount', 'L'),
            param('starting_rate', 'L/h'),
            param('rate_change', 'L/h/h'),
            value('remaining', 'L', local.amount, lower=q(0, 'L'), upper=local.amount),
            value('started_at', 'h', t, readonly=True),
            flow(
                'delivery',
                local.remaining,
                this.water,
                request=formula(
                    fmax(q(0, 'L/h'), local.starting_rate + local.rate_change * (t - local.started_at))
                ),
            ),
            until(local.remaining <= q(0, 'L')),
        ),
    )
    b.setup(start(tank.receive, q(20, 'L'), q(5, 'L/h'), q(change, 'L/h/h')))
    b.root(
        value('started', '', formula(count(tank.receive.occurrences))),
        value('completed', '', formula(count(tank.receive.occurrences.done))),
    )
    return _example(name, b, horizon, expected)


@example
def rising_ramp():
    """Spec, "Delivering at a changing rate": the rate rises from 5 to 10 L/h in the first hour.
    At 1 h, 7.5 L delivered, 12.5 L in transit, one start and no completion; at 2 h, all 20 L and one
    completion (acceptance row 27)."""
    remaining = key('tank.receive#0', 'remaining')
    expected = [At(1, key('tank', 'water'), F(15, 2)), At(1, remaining, F(25, 2))]
    expected += [
        At(1, key('', 'started'), 1),
        At(1, key('', 'completed'), 0),
        At(2, key('tank', 'water'), 20),
    ]
    expected += [At(2, key('', 'completed'), 1), Traced('finish', 'tank.receive', (2,))]
    return _ramp('rising_ramp', 5, 2, expected)


@example
def falling_ramp():
    """Spec, "Delivering at a changing rate": starting at 5 L/h and falling by 2 L/h each hour
    delivers only 6.25 L by the time the rate reaches zero at 2.5 h; the gate then waits, and nothing
    completes."""
    expected = [At(F(5, 2), key('tank', 'water'), F(25, 4)), At(4, key('tank', 'water'), F(25, 4))]
    expected += [At(4, key('tank.receive#0', 'remaining'), F(55, 4)), At(4, key('', 'completed'), 0)]
    return _ramp('falling_ramp', -2, 4, expected)


def _move(name, amount, expected):
    """Spec, "Expressions and instantaneous transfers": `move` between two readonly stocks, from 8 L
    into an empty one capped at 4 L (acceptance row 28)."""
    b = Builder(UNITS)
    left = b.entity('left', value('water', 'L', 8, lower=0, readonly=True))
    right = b.entity('right', value('water', 'L', 0, lower=0, upper=4, readonly=True))
    mover = b.entity(
        'mover',
        event('shift', param('amount', 'L'), after(q(0, 'h'), move(local.amount, left.water, right.water))),
    )
    b.setup(start(mover.shift, q(amount, 'L')))
    return _example(name, b, 1, expected)


@example
def move_within_bounds():
    """Spec, "Expressions and instantaneous transfers": moving 3 L leaves 5 L and 3 L."""
    return _move('move_within_bounds', 3, [At(0, key('left', 'water'), 5), At(0, key('right', 'water'), 3)])


@example
def move_over_bound():
    """Spec, "Expressions and instantaneous transfers": moving 5 L fails the destination's
    bound and leaves 8 L and 0 L."""
    expected = [Fails('right.water', 0), At(0, key('left', 'water'), 8), At(0, key('right', 'water'), 0)]
    return _move('move_over_bound', 5, expected)


@example
def frozen_formula():
    """Spec, "History and optional domain status" (D7): a formula of an occurrence that read 14 at
    its finish reads 14 afterwards (acceptance row 29). The occurrence's `total = formula(level + 4)`
    reads 11 at first, 14 after the level becomes 10 at 0.5 h, and keeps 14 after its finish at 1 h,
    when the level becomes 20 at 2 h."""
    b = Builder(UNITS)
    counter = b.entity(
        'counter',
        value('level', '', 7),
        event('job', value('total', '', formula(this.level + 4), readonly=True), after(q(1, 'h'))),
        event('bump', after(q(0.5, 'h'), assign(this.level, 10)), after(q(1.5, 'h'), assign(this.level, 20))),
    )
    b.setup(start(counter.job), start(counter.bump))
    total = key('counter.job#0', 'total')
    expected = [
        At(F(1, 4), total, 11),
        At(F(3, 4), total, 14),
        At(3, total, 14),
        At(3, key('counter', 'level'), 20),
    ]
    return _example('frozen_formula', b, 3, expected)


# ---- draws and inputs ------------------------------------------------------------------------------------


def _categorical(name, parts, guarded, expected):
    """Spec, "Choosing actions inside a stage": `switch categorical(FIXED: 0.7, FAILED: 0.3).draw()`
    at 2 h, in a median run (acceptance row 30)."""
    b = Builder(UNITS)
    outcome = b.enum('enum[FIXED, FAILED]', 'FIXED', 'FAILED')
    machine = b.entity(
        'machine',
        value('operational', BOOL, False),
        value('parts', '', parts),
        event(
            'check',
            after(
                q(2, 'h'),
                switch(
                    draw(categorical(outcome, FIXED=0.7, FAILED=0.3)),
                    case(
                        outcome.FIXED,
                        assign(this.operational, True),
                        when=this.parts >= 1 if guarded else None,
                    ),
                    case(outcome.FAILED, start(this.repair)),
                ),
            ),
        ),
        event('repair', after(q(0, 'h'))),
    )
    b.setup(start(machine.check))
    b.root(value('repairs', '', formula(count(machine.repair.occurrences))))
    return _example(name, b, 3, expected)


@example
def median_categorical():
    """Spec, "Choosing actions inside a stage": a median run takes FIXED, the most likely
    outcome."""
    expected = [At(2, key('machine', 'operational'), True), At(2, key('', 'repairs'), 0)]
    expected.append(Traced('draw', 'machine.check.step[0].do[0].draw[0]', (2,)))
    return _categorical('median_categorical', 1, False, expected)


@example
def median_categorical_guarded():
    """Spec, "Choosing actions inside a stage": `FIXED when this.parts >= 1` with no parts. FIXED
    is not eligible, so the median run takes FAILED, the most likely eligible outcome, and starts a
    repair (worked from the spec's rule)."""
    expected = [At(2, key('machine', 'operational'), False), At(2, key('', 'repairs'), 1)]
    return _categorical('median_categorical_guarded', 0, True, expected)


DISPATCH_SWITCH = 'depot.request_pump.step[0].do[1]'
DISPATCH = 'depot.request_pump#0'


@dataclass(frozen=True)
class Stop:
    """A breakpoint at the part of the origin `at`, for one occurrence (None: any), and the edits
    made there before the run resumes, each a key of a stored value and its new value in the value's
    declared unit (an enum member by its name)."""

    at: str
    occurrence: str | None = None
    edits: tuple = ()


def pump_dispatch(spares=1):
    """Item 15 of the plan's changes after G0, the acceptance example: a depot asks for a pump at
    0 h. The dispatcher's forecast, which never sends (SEND 0, WAIT 1), is drawn into the
    occurrence's field `order`, and a `switch` on it sends a spare pump, which needs a spare (the
    eligibility of SEND is its case's guard), or counts a wait. Unattended it waits once."""
    b = Builder(UNITS)
    action = b.enum('enum[SEND, WAIT]', 'SEND', 'WAIT')
    dispatcher = b.entity(
        'dispatcher', value('forecast', dist_of(action), categorical(action, SEND=0, WAIT=1))
    )
    depot = b.entity(
        'depot',
        value('spares', '', spares, lower=0),
        value('waits', '', 0),
        event(
            'request_pump',
            value('order', action, action.WAIT),
            after(
                q(0, 'h'),
                assign(local.order, draw(dispatcher.forecast)),
                switch(
                    local.order,
                    case(action.SEND, start(this.send_pump), when=this.spares >= 1),
                    case(action.WAIT, add(this.waits, 1)),
                ),
            ),
        ),
        event('send_pump', after(q(0, 'h'), subtract(this.spares, 1))),
    )
    b.setup(start(depot.request_pump))
    b.root(value('sent', '', formula(count(depot.send_pump.occurrences))))
    return b.finish()


# The acceptance example's stops, each with its results (worked from item 15): untouched, the run is
# the unattended one; with `order` edited from WAIT to SEND before the switch, the send branch runs
# once, at 0 h, and the drawn WAIT stays in the history; with no spare, SEND is not eligible and
# nothing runs; with two stops in the stage, the first edit is neither lost nor made twice.
DISPATCH_DRAW = Traced('draw', 'depot.request_pump.step[0].do[0].draw[0]', (0,))
PAUSES = {
    'untouched': (
        1,
        (Stop(DISPATCH_SWITCH, DISPATCH),),
        [At(0, key('depot', 'waits'), 1), At(0, key('', 'sent'), 0), DISPATCH_DRAW],
    ),
    'sends': (
        1,
        (Stop(DISPATCH_SWITCH, DISPATCH, ((key(DISPATCH, 'order'), 'SEND'),)),),
        [
            At(0, key('depot', 'waits'), 0),
            At(0, key('depot', 'spares'), 0),
            At(0, key('', 'sent'), 1),
            DISPATCH_DRAW,
            Traced('start', 'depot.send_pump', (0,)),
            Traced('edit', DISPATCH_SWITCH, (0,)),
        ],
    ),
    'no_spare': (
        0,
        (Stop(DISPATCH_SWITCH, DISPATCH, ((key(DISPATCH, 'order'), 'SEND'),)),),
        [At(0, key('depot', 'waits'), 0), At(0, key('', 'sent'), 0), Traced('start', 'depot.send_pump', ())],
    ),
    'two_stops': (
        1,
        (
            Stop('depot.request_pump.step[0].do[0]', DISPATCH, ((key('depot', 'waits'), 5),)),
            Stop(DISPATCH_SWITCH, DISPATCH, ((key(DISPATCH, 'order'), 'SEND'),)),
        ),
        [At(0, key('depot', 'waits'), 5), At(0, key('', 'sent'), 1), DISPATCH_DRAW],
    ),
}


@example
def pump_dispatch_unattended():
    """The acceptance example of item 15 run unattended: the forecast waits, nothing is sent."""
    expected = [At(0, key('depot', 'waits'), 1), At(0, key('', 'sent'), 0), DISPATCH_DRAW]
    return Example('pump_dispatch_unattended', pump_dispatch(), run(1), tuple(expected))


@example
def distribution_input():
    """Spec, "Distributions and explicit draws" (D2): a run overrides the distribution-valued input
    `repair_times` with `uniform(2 h, 4 h)`, and the repair still draws its own duration; in a median
    run that is the median, 3 h."""
    b = Builder(UNITS)
    machine = b.entity(
        'machine',
        value('operational', BOOL, False),
        input_('repair_times', None, uniform(1, 3, 'h')),
        event(
            'repair',
            value('duration', 'h', this.repair_times.draw()),
            after(local.duration, assign(this.operational, True)),
        ),
    )
    b.setup(start(machine.repair))
    inputs = (InputValue('machine', 'repair_times', uniform(2, 4, 'h')),)
    expected = [At(F(5, 2), key('machine', 'operational'), False), At(3, key('machine', 'operational'), True)]
    return _example('distribution_input', b, 4, expected, inputs=inputs)


def _scalar_input(name, inputs, ready):
    """Spec, "Distributions and explicit draws" (D2): `input repair_time = uniform(1 h, 3 h).draw()
    in [1 h, 12 h]`. A scalar override of 5 h skips the default draw; without one, a median run draws
    the median, 2 h."""
    b = Builder(UNITS)
    machine = b.entity(
        'machine',
        value('operational', BOOL, False),
        input_('repair_time', 'h', draw(uniform(1, 3, 'h')), lower=1, upper=12),
        event('repair', after(this.repair_time, assign(this.operational, True))),
    )
    b.setup(start(machine.repair))
    expected = [
        At(ready - F(1, 2), key('machine', 'operational'), False),
        At(ready, key('machine', 'operational'), True),
    ]
    expected.append(At(0, key('machine', 'repair_time'), ready))
    return _example(name, b, 6, expected, inputs=inputs)


@example
def scalar_input_override():
    """Spec, "Distributions and explicit draws" (D2): the override of 5 h, in the admitted
    range, skips the default draw, and the repair is done at 5 h."""
    return _scalar_input(
        'scalar_input_override', (InputValue('machine', 'repair_time', Quantity(5, 'h')),), 5
    )


@example
def scalar_input_default():
    """Spec, "Distributions and explicit draws" (D2): with no override, a median run draws the
    median of the default, 2 h."""
    return _scalar_input('scalar_input_default', (), 2)


# ---- reports, lookups, stages -----------------------------------------------------------------------


@example
def water_service_returns():
    """Spec, "Formulas and the values a caller can read" (D17): a utility without service until hour
    5. The unserved rate is 0 at hour 6, and the unserved volume at hour 6 still holds the water
    missed through hour 5 (acceptance row 32). North wants 10 L/h and is out until 5 h; South wants
    4 L/h and is served throughout; the numbers are worked by hand."""
    b = Builder(UNITS)
    utility = b.template(
        'Utility',
        input_('demand', 'L/h', 10),
        value('online', BOOL, True),
        value('served', 'L', 0, lower=0),
        flow(
            'delivery',
            SOURCE,
            this.served,
            request=formula(this.demand),
            capacity=formula(ifelse(this.online, this.demand, q(0, 'L/h'))),
        ),
        value('unserved_rate', 'L/h', formula(fmax(q(0, 'L/h'), this.demand - this.delivery.actual_rate))),
        value('unserved', 'L', 0, lower=0),
        flow('count_unserved', SOURCE, this.unserved, request=formula(this.unserved_rate)),
        event(
            'restore',
            when(t >= q(5, 'h'), start(this.restore), reset=reset_when(False)),
            after(q(0, 'h'), assign(this.online, True)),
        ),
    )
    b.member(utility, 'north', online=False)
    b.member(utility, 'south', demand=q(4, 'L/h'))
    b.root(
        value('initial_unserved', 'L', fsum(utility.instances.unserved)),
        value('unserved_volume', 'L', formula(fsum(utility.instances.unserved))),
        value('unserved_now', 'L/h', formula(fsum(utility.instances.unserved_rate))),
    )
    expected = [
        At(4, key('', 'unserved_now'), 10),
        At(4, key('', 'unserved_volume'), 40),
        At(6, key('', 'unserved_now'), 0),
        At(6, key('north', 'unserved_rate'), 0),
        At(6, key('', 'unserved_volume'), 50),
        At(6, key('', 'initial_unserved'), 0),
        At(6, key('south', 'unserved'), 0),
    ]
    return _example('water_service_returns', b, 6, expected)


def _pinned(name, shared, late, expected):
    """Spec, "Delivery experiments on the pinned engine": two deliveries of 20 L that request
    10 L/h each, to customers a and b. The rewrite's local sharing gives the same numbers. The
    parameter is `customer`: `to` is a word of the language."""
    b = Builder(UNITS)
    customer = b.template('Customer', value('water', 'L', 0, lower=0))
    a, bb = b.member(customer, 'a'), b.member(customer, 'b')
    triggers = [when(t >= q(1, 'h'), start(this.deliver, bb), reset=reset_when(False))] if late else []
    if shared:
        depot = b.entity(
            'depot',
            value('supply', 'L', 40, lower=0, outflow=endpoint(capacity=q(10, 'L/h'))),
            event(
                'deliver',
                param('customer', ref_to('Customer')),
                flow('pipe', this.supply, local.customer.water, request=q(10, 'L/h')),
                until(local.customer.water >= q(20, 'L')),
                *triggers,
            ),
        )
    else:
        depot = b.entity(
            'depot',
            event(
                'deliver',
                param('customer', ref_to('Customer')),
                value('batch', 'L', 20, lower=0),
                flow('pipe', local.batch, local.customer.water, request=q(10, 'L/h')),
                until(local.batch <= q(0, 'L')),
            ),
        )
    b.setup(start(depot.deliver, a), *([] if late else [start(depot.deliver, bb)]))
    return _example(name, b, 4, expected)


def _delivered(moment, first, second):
    return [At(moment, key('a', 'water'), first), At(moment, key('b', 'water'), second)]


@example
def deliveries_separate_batches():
    """Spec, "Delivery experiments on the pinned engine": separate 20 L batches give 10 / 10 L
    at 1 h, and both complete at 2 h."""
    expected = [*_delivered(1, 10, 10), Traced('finish', 'depot.deliver', (2, 2))]
    return _pinned('deliveries_separate_batches', False, False, expected)


@example
def deliveries_shared_supply():
    """Spec, "Delivery experiments on the pinned engine": a shared 40 L supply with 10 L/h of
    total throughput gives 5 / 5 L at 1 h, and both complete at 4 h."""
    expected = [*_delivered(1, 5, 5), Traced('finish', 'depot.deliver', (4, 4))]
    return _pinned('deliveries_shared_supply', True, False, expected)


@example
def deliveries_late_start():
    """Spec, "Delivery experiments on the pinned engine": the same shared supply with B
    starting at 1 h: 10 / 0 L at 1 h; 15 / 5, 20 / 10 and 20 / 20 L
    at 2, 3 and 4 h; A completes at 3 h and B at 4 h."""
    expected = _delivered(1, 10, 0) + _delivered(2, 15, 5) + _delivered(3, 20, 10) + _delivered(4, 20, 20)
    expected.append(Traced('finish', 'depot.deliver', (3, 4)))
    return _pinned('deliveries_late_start', True, True, expected)


@example
def stage_sees_writes():
    """Spec, "Reference behavior in the current compiler": setting `x = 2` and then `y = x` when x
    starts at 1 leaves y at 1 in the current compiler; in a rewrite stage, y reads the new 2."""
    b = Builder(UNITS)
    box = b.entity(
        'box',
        value('x', '', 1),
        value('y', '', 0),
        event('update', after(q(0, 'h'), assign(this.x, 2), assign(this.y, this.x))),
    )
    b.setup(start(box.update))
    return _example('stage_sees_writes', b, 1, [At(0, key('box', 'y'), 2), At(0, key('box', 'x'), 2)])


def _readings(b, rows):
    readings = b.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
    b.table('readings', readings, rows)
    return readings


@example
def keyed_lookup():
    """Spec, "Collections, keys and projections": `Reading.instances.by(hour).at(t).factor` holds
    the 10:00 reading at 10:40 and switches at 11:00; beyond the last key the last entry applies."""
    b = Builder(UNITS)
    readings = _readings(b, ({'hour': 10, 'factor': 2}, {'hour': 11, 'factor': 3}))
    b.root(value('factor_now', '', formula(readings.instances.by('hour').at(t).factor)))
    expected = [At(F(32, 3), key('', 'factor_now'), 2), At(11, key('', 'factor_now'), 3)]
    expected.append(At(13, key('', 'factor_now'), 3))
    return _example('keyed_lookup', b, 13, expected)


@example
def lookup_below_first_key():
    """Spec, "Collections, keys and projections": a first sample at 2 h cannot supply a reading at
    1 h, and a stage that reads it at 1 h fails the run."""
    b = Builder(UNITS)
    readings = _readings(b, ({'hour': 2, 'factor': 5},))
    probe = b.entity(
        'probe',
        value('copy', '', 0),
        event('look', after(q(1, 'h'), assign(this.copy, readings.instances.by('hour').at(t).factor))),
    )
    b.setup(start(probe.look))
    return _example('lookup_below_first_key', b, 2, [Fails('at(t)', 1), At(0, key('probe', 'copy'), 0)])


# ---- the acceptance cases ----------------------------------------------------------------------------

# Each row of the spec's table "Acceptance cases", with the examples that check it.
ROWS = {
    'A grinder at 8 g; `refill.start(50 g)`': ('grinder_refill',),
    '`48 h/2` and `48 h / 2`': ('unit_division',),
    '`(3 person) * (2 year)`': ('unit_product',),
    'A tank of 8 L; a delivery that requests 3 L/h with a capacity of 5 L/h': ('tank_delivery',),
    'A reservoir limited to 10 L/h; requests of 8 and 12 L/h': (
        'reservoir_priority',
        'reservoir_proportional',
    ),
    'A common sink that requests 6 L/h from `main` and `backup`; `main` capped at 4 L/h': ('common_sink',),
    'One pipe; the source, the pipe and the sink request 10, 8 and 6 L/h': (
        'one_pipe',
        'one_pipe_capped_at_source',
        'one_pipe_capped_at_pipe',
        'one_pipe_capped_at_sink',
    ),
    'Two junctions, 1 L/h, recipients A, B and C': ('two_junctions', 'two_junctions_solver'),
    'A reversible route at -3 L/h': ('reversible_route',),
    'Legs that request 4 and 8, at half service': ('legs_half_service', 'legs_zero_leg', 'legs_all_zero'),
    'Deliveries A and B, each owning one pipe of 2 L/h': ('deliveries_current_flows',),
    'The worked network': ('network', 'network_clinic_first', 'network_unequal', 'network_kw'),
    'Two bottlenecks, `a + b <= 4 W` and `b + c <= 5 W`': (
        'two_bottlenecks_fair',
        'two_bottlenecks_total_unmet',
    ),
    'Staffing': ('staffing',),
    'Pump and battery': ('pump_battery',),
    'Provider limit of 8 W': ('provider_limit', 'provider_limit_east_low'),
    '`4 <= x + y <= 6` in the distance step': (
        'distance_targets_zero',
        'distance_targets_five',
        'distance_equality',
    ),
    'A shared limit of 3 L/h; each occurrence requests 2 L/h': ('shared_limit',),
    '20 g; one stage sets 8 g and a later stage of the same round adds 4 g': ('same_round_writes',),
    'Two writes in one round, and a trigger that reacts to the result': ('two_writes_one_solve',),
    '`inspect.start(3 h)`': ('inspect_guard_read_once',),
    '`when t >= 3 h` with `reset after 3 h`': ('clock_trigger',),
    'A grinder at 8 g; its trigger and a manual start of 50 g': ('grinder_trigger_and_manual',),
    'A tank at 11 L draining 1 L/h; `when this.water <= 10 L`': ('crossing_drain',),
    'A tank at 10 L filling 1 L/h; an occurrence drains 2 L/h more from hour 2 to hour 4; `>= 16 L`': (
        'crossing_rejoin',
    ),
    'An occurrence with 20 L in its batch and 12 L delivered tries to finish': ('retirement_failure',),
    'The 20 L delivery with a rising rate': ('rising_ramp',),
    '`move` 3 L from a stock of 8 L into an empty stock capped at 4 L': (
        'move_within_bounds',
        'move_over_bound',
    ),
    'A formula of an occurrence that read 14 at its finish': ('frozen_formula',),
    '`categorical(FIXED: 0.7, FAILED: 0.3).draw()` in a median run': ('median_categorical',),
    'A dispatcher whose forecast always waits, with one spare pump': ('pump_dispatch_unattended',),
    'The water model; service returns at hour 5': ('water_service_returns',),
}
