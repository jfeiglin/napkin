"""Builder counterparts of reversible trajectories and simultaneous stock contacts."""

from functools import partial

from napkin.program import build as b
from tests.engine import reversible_bound_cases as reversible
from tests.engine import simultaneous_bound_cases as simultaneous
from tests.engine.parity_records import pair, written
from tests.engine.program_parity import check_pairs


def reversible_program(case, method, event):
    make = b.Builder(reversible.UNITS)

    def quantity(value, unit):
        return b.q(written(reversible._number(value)), unit)

    parts = []
    for name, opening, (_, high) in zip(('a', 'b'), case.levels(0), case.bounds(), strict=True):
        parts.append(
            b.value(
                name,
                'L',
                quantity(opening, 'L'),
                lower=0,
                upper=None if high is None else quantity(high, 'L'),
            )
        )
    source, sink = (b.this.b, b.this.a) if case.reverse else (b.this.a, b.this.b)
    hour = quantity(case.turn, 'h')
    rate = quantity(-case.slope * case.turn, 'L/h') + quantity(case.slope, 'L/h/h') * b.t
    if method == 'component':
        for name, left, right, req in [('forward', source, sink, rate), ('backward', sink, source, -rate)]:
            positive = b.formula(b.fmax(b.q(0, 'L/h'), req))
            parts.append(b.flow(name, left, right, request=positive, capacity=positive))
    elif method == 'secant':
        drain = case.slope * (case.turn + case.width) / 2
        refill = case.slope * case.turn / 2
        parts.extend(
            [
                b.route('pipe', source, sink, request=quantity(-drain, 'L/h')),
                b.event('reverse', b.after(hour, b.assign(b.this.pipe.request, quantity(refill, 'L/h')))),
            ]
        )
    else:
        parts.append(b.route('pipe', source, sink, request=b.formula(rate)))
    if event:
        parts.append(b.event('idle', b.after(quantity(case.tick, 'h'))))
    yard = make.entity('yard', *parts)
    if method == 'declared':
        make.entity(
            'provider', b.solver('share', b.given('pipe', yard.pipe), b.solve_for(b.local.pipe.actual_rate))
        )
    if event:
        make.setup(b.start(yard.idle))
    if method == 'secant':
        make.setup(b.start(yard.reverse))
    return make.finish()


def check_parity_reversible(seed):
    case = reversible._case(seed)
    check_pairs(
        seed,
        [
            pair(
                f'{method}.event={cut}',
                reversible._source(case, method, cut),
                reversible.UNITS,
                partial(reversible_program, case, method, cut),
            )
            for method in reversible.METHODS
            for cut in (False, True)
        ],
    )


def simultaneous_program(seed, method, cut):
    make = b.Builder(simultaneous.UNITS)
    rate, at, _, floor, _, event = simultaneous._data(seed)

    def quantity(value, unit):
        return b.q(written(simultaneous._lit(value)), unit)

    parts = []
    for name, (low, opening, high) in zip(
        ('donor', 'receiver'), simultaneous._stocks(seed, method), strict=True
    ):
        parts.append(
            b.value(
                name,
                'L',
                quantity(opening, 'L'),
                lower=quantity(low, 'L'),
                upper=quantity(high, 'L'),
                scale=quantity(floor, 'L'),
            )
        )
    reversible_flow = method in ('lines', 'sparse')
    backwards = reversible_flow and seed % 2
    source, sink = (b.this.receiver, b.this.donor) if backwards else (b.this.donor, b.this.receiver)
    rate_value = quantity(-rate if backwards else rate, 'L/h')
    request = b.formula(rate_value * (2 - b.t / quantity(at, 'h'))) if method == 'sparse' else rate_value
    connection = b.route if reversible_flow else b.flow
    yard = make.entity('yard', *parts, connection('pipe', source, sink, request=request))
    if method == 'declared':
        make.entity(
            'owner', b.solver('hold', b.given('pipe', yard.pipe), b.solve_for(b.local.pipe.actual_rate))
        )
    if cut:
        clock = make.entity('clock', b.event('tick', b.after(quantity(event, 'h'))))
        make.setup(b.start(clock.tick))
    return make.finish()


def check_parity_simultaneous(seed):
    check_pairs(
        seed,
        [
            pair(
                f'{method}.event={cut}',
                simultaneous.simultaneous_source(seed, method, cut),
                simultaneous.UNITS,
                partial(simultaneous_program, seed, method, cut),
            )
            for method in simultaneous.METHODS
            for cut in (False, True)
        ],
    )
