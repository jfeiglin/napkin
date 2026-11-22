"""Paired source and public-builder programs for provenance graphs and event reachability."""

from functools import partial
from random import Random

from napkin.program import build as b
from tests.engine import proof_event_cases as events
from tests.engine import proof_network_cases as network
from tests.engine import proof_solver_cases as solvers
from tests.engine.parity_records import pair
from tests.engine.program_parity import check_pairs


def network_program(seed, sign):
    rng = Random(seed)
    magnitude = rng.randrange(1, 25) if seed else 3
    fraction = rng.choice((0.25, 0.5, 0.75)) if seed else 0.5
    asked = 4 * (rng.randrange(1, 8) if seed else 1)
    cutoff = rng.randrange(3, 9) / 8 if seed else 0.5
    spare = rng.randrange(3, 35) if seed else 7
    make = b.Builder(network.UNITS)
    for name in ('west', 'east'):
        make.entity(
            name,
            b.value('water', 'L', 200),
            b.value('incoming', 'L/h', b.formula(b.fsum(b.this.water.inflow.flows.actual_rate))),
            b.value('outgoing', 'L/h', b.formula(b.fsum(b.this.water.outflow.flows.actual_rate))),
        )
    west, east = b.named('west').water, b.named('east').water
    link = b.named('channel').link
    channel = make.entity(
        'channel',
        b.input_('meter', 'L/h', sign * magnitude),
        b.input_('unrelated', 'L/h', spare),
        b.value('control', 'L/h', b.formula(b.this.unrelated)),
        b.route('link', west, east, request=b.formula(b.this.meter)),
        b.value('noted', 'L/h', 0),
        b.event(
            'inspect',
            b.value('forward', 'L/h', b.formula(link.forward.actual_rate)),
            b.value('backward', 'L/h', b.formula(link.backward.actual_rate)),
            b.value('included', 'L/h', b.formula(b.fsum(west.outflow.flows.actual_rate))),
            b.value('endpoint', 'L/h', b.formula(west.inflow.actual_rate)),
            b.after(
                b.q(cutoff, 'h'), b.assign(b.this.noted, west.outflow.actual_rate - west.inflow.actual_rate)
            ),
        ),
    )
    make.entity(
        'works',
        b.input_('quota', 'L/h', asked * fraction),
        b.value('stock', 'L', 200),
        b.value('supply', 'L', 200),
        b.legs(
            'batch',
            b.flow('use', b.this.stock, b.SINK, request=b.q(asked, 'L/h'), capacity=b.formula(b.this.quota)),
            b.flow('pair', b.this.supply, b.SINK, request=b.q(2 * asked, 'L/h')),
        ),
        b.value('scale_reading', '', b.formula(b.this.batch.served_fraction)),
    )
    make.setup(b.start(channel.inspect))
    return make.finish()


def check_parity_network(seed):
    check_pairs(
        seed,
        [
            pair(str(sign), network._case(seed, sign)[0], network.UNITS, partial(network_program, seed, sign))
            for sign in (-1, 1)
        ],
    )


def solver_program(seed, variant):
    rng = Random(seed)
    limit = rng.randint(1, 42) if seed else 3
    spare = limit + rng.randint(2, 10)
    high = spare + 5
    unit, factor = ('mL', 1000) if seed % 2 else ('L', 1)
    selected, bound = ('chosen', 'bound') if seed % 3 else ('target', 'cap')
    make = b.Builder(solvers.UNITS)
    a, c = getattr(b.local, selected), getattr(b.local, bound)
    uses_flow = variant == 'flow.alias'
    measured_unit = f'{unit}/h' if uses_flow else unit
    parts = [
        b.input_('meter', measured_unit, limit * factor),
        b.input_('spare', 'L/h' if uses_flow else 'L', spare),
    ]
    givens = [
        b.given(selected, b.this.feed if uses_flow else b.this.value),
        b.given(bound, b.this.meter),
        b.given('unused', b.this.spare),
    ]
    if uses_flow:
        parts.extend(
            [
                b.value('stock', 'L', 0),
                b.flow('feed', b.SOURCE, b.this.stock, request=b.q(high, 'L/h')),
                b.value('rate', 'L/h', b.formula(b.this.feed.actual_rate)),
                b.solver(
                    'plan',
                    *givens,
                    b.solve_for(a.actual_rate),
                    b.constraint(a.actual_rate <= c),
                    b.maximize(a.actual_rate),
                ),
            ]
        )
    else:
        parts.extend(
            [
                b.value('value', 'L', 0, lower=0, upper=high),
                b.value('observed', 'L', b.formula(b.this.value)),
                b.value('result', 'L', b.formula(b.this.plan.quantity)),
                b.solver(
                    'plan',
                    *givens,
                    b.solve_for(a if variant == 'stored.alias' else b.this.value),
                    b.unknown('quantity', 'L', lower=0, upper=high),
                    b.constraint(a == c),
                    b.constraint(b.local.quantity == c),
                ),
            ]
        )
    make.entity('box', *parts)
    return make.finish()


def check_parity_solver(seed):
    check_pairs(
        seed,
        [
            pair(name, source, solvers.UNITS, partial(solver_program, seed, name))
            for name, source, _, _ in solvers.solver_cases(seed)
        ],
    )


def arguments(seed, sources, amounts, factor, delay, duration):
    make = b.Builder(events.UNITS)
    relay = seed % 3 == 1
    target = 'relay' if relay else 'job'
    extra = (
        [
            b.event(
                'relay',
                b.param('forwarded', 'L'),
                b.after(b.q(0, 'h'), b.start(b.this.job, b.local.forwarded)),
            )
        ]
        if relay
        else []
    )
    yard = make.entity(
        'yard',
        b.input_('first', 'L', amounts['first']),
        b.input_('second', 'L', amounts['second']),
        b.input_('idle_meter', 'L', 7),
        b.value('saved', 'L', 0),
        b.event(
            'job',
            b.param('amount', 'L'),
            b.value('derived', 'L', b.formula(b.local.amount * factor)),
            b.after(b.q(duration, 'h')),
        ),
        *extra,
        b.event(
            'launch', b.after(b.q(delay, 'h'), b.start(getattr(b.this, target), getattr(b.this, sources[1])))
        ),
        b.event(
            'idle',
            b.value('captured', 'L', b.this.idle_meter),
            b.value('derived', 'L', b.formula(b.this.idle_meter)),
            b.after(b.q(1, 'h'), b.assign(b.this.saved, b.this.idle_meter)),
        ),
    )
    make.setup(b.start(getattr(yard, target), getattr(yard, sources[0])), b.start(yard.launch))
    return make.finish()


def check_parity_arguments(seed):
    source, *data = events.argument_model(seed)
    check_pairs(
        seed,
        [pair('relay' if seed % 3 == 1 else 'direct', source, events.UNITS, partial(arguments, seed, *data))],
    )


def dispatch(override, start, stock, take, weight):
    make = b.Builder(events.UNITS)
    order = make.enum('enum[WAIT, SEND]', 'WAIT', 'SEND')
    wait = b.categorical(order, WAIT=weight, SEND=0)
    send = b.categorical(order, WAIT=0, SEND=weight)
    declare = b.input_ if override == 'configuration' else b.value
    write = b.after(b.q(0, 'h'), b.assign(b.this.forecast, send))
    steps = [write] if override == 'stage' else []
    steps.append(
        b.after(
            b.q(start, 'h'),
            b.assign(b.local.order, b.draw(b.this.forecast)),
            b.switch(
                b.local.order,
                b.case(order.SEND, b.start(b.this.dispatch)),
                b.case(order.WAIT, b.add(b.this.waits, 1)),
            ),
        )
    )
    idle = [b.event('unused', write)] if override == 'dormant' else []
    depot = make.template(
        'Depot',
        declare('forecast', b.dist_of(order), wait),
        b.value('stock', 'L', stock, lower=0),
        b.value('moved', 'L', 0, lower=0),
        b.value('waits', '', 0),
        b.event('choose', b.value('order', order, order.WAIT), *steps),
        *idle,
        b.event('dispatch', b.after(b.q(0, 'h'), b.move(b.q(take, 'L'), b.this.stock, b.this.moved))),
    )
    yard = make.member(depot, 'yard', **({'forecast': send} if override == 'member' else {}))
    make.setup(b.start(yard.choose))
    return make.finish()


def check_parity_reach(seed):
    pairs = []
    for override in ('member', 'stage', 'configuration', 'none', 'dormant'):
        source, *data = events.reach_model(seed, override)
        pairs.append(pair(override, source, events.UNITS, partial(dispatch, override, *data)))
    check_pairs(seed, pairs)
