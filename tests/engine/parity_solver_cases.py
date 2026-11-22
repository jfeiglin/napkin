"""Author each rescaled stock or flow optimization through the public solver builder."""

from decimal import Decimal
from functools import partial
from random import Random

from napkin.model.compile import compile_text
from napkin.program import build as b
from tests.engine import solver_flow_scale_cases as flows
from tests.engine import solver_scale_cases as stocks
from tests.engine.program_parity import authored_number, check_pairs


def text_program(source, units):
    return compile_text(source, units).program


def stock_program(seed, label, limits, scale, small, reverse):
    unit = 'mL' if small else 'L'
    factor = 1000 if small else 1
    x_name, y_name = ('spare', 'stock') if reverse else ('x', 'y')
    x, y = getattr(b.local, x_name), getattr(b.local, y_name)
    x_max, y_max = limits
    upper = None if 'unbounded' in label else b.q(y_max * factor, unit)
    unknowns = [
        b.unknown(x_name, unit, lower=b.q(0, unit), upper=b.q(x_max * factor, unit)),
        b.unknown(
            y_name,
            unit,
            lower=b.q(0, unit),
            upper=upper,
            scale=b.q(scale * factor, unit) if scale is not None else None,
        ),
    ]
    if reverse:
        unknowns.reverse()
    decisions = []
    variables = b.named('yard').choose
    X, Y = getattr(variables, x_name), getattr(variables, y_name)
    readings = [('chosen_x', X), ('chosen_y', Y)]
    if label == 'ranked.bounded':
        budget = max(limits) + min(limits) // 2
        decisions += [
            b.constraint(x + y <= b.q(budget * factor, unit)),
            b.maximize(x + y),
            b.minimize(y) if seed % 2 else b.maximize(y),
        ]
        readings += [('rank1', X + Y), ('rank2', Y)]
    elif label == 'ranked.unbounded':
        decisions += [b.maximize(x), b.maximize(y)]
        readings += [('rank1', X), ('rank2', Y)]
    else:
        decisions.append(b.maximize(x + y))
        readings.append(('rank1', X + Y))
    builder = b.Builder(stocks.UNITS)
    builder.entity('yard', b.solver('choose', *unknowns, *decisions))
    builder.root(*(b.value(name, 'L', b.formula(expr)) for name, expr in readings))
    return builder.finish()


def stock_pairs(seed):
    rng = Random(seed)
    if seed:
        magnitude = 10 ** rng.choice((0, 1, 3, 6, 8, 9, 10))
        limits = (magnitude * rng.randint(2, 9), magnitude * rng.randint(2, 9))
        scale = rng.choice((1, 2, 4, max(1, limits[1] // 2)))
    else:
        limits, scale = (10**9, 10**9), 1
    for case in stocks.cases(seed):
        small = bool(seed % 3) != (case.name in ('ranked.bounded', 'bounded.rewritten'))
        reverse = bool(seed % 2) != (case.name in ('ranked.unbounded', 'bounded.rewritten'))
        explicit = None if case.name.endswith('implicit') else scale
        yield (
            case.name,
            partial(text_program, case.source, stocks.UNITS),
            partial(stock_program, seed, case.name, limits, explicit, small, reverse),
            True,
        )


def flow_program(size, shape, unit, scale):
    builder = b.Builder(flows.UNITS)
    rate = unit + '/h'

    def quantity(number):
        token = format(Decimal(number) * flows.PER_L[unit], 'f')
        return b.q(authored_number(token), rate)

    limit = b.this.limit
    capped = b.formula(limit) if shape != 'unbounded-feed' else None
    fields = [
        b.value('water', 'L', b.q(0, 'L')),
        b.value('limit', rate, quantity(size)),
        b.flow(
            'inlet',
            b.SOURCE,
            b.this.water,
            capacity=capped,
            request=b.formula(2 * limit) if shape == 'fair' else None,
        ),
    ]
    if shape == 'fair':
        fields.append(b.flow('second', b.SOURCE, b.this.water, request=b.formula(3 * limit), capacity=capped))
    tank = builder.entity('tank', *fields)
    feed, cap, spare = b.local.feed.actual_rate, b.local.cap, b.local.spare
    parts = [b.given('feed', tank.inlet), b.given('cap', tank.limit), b.solve_for(feed)]
    if shape == 'fair':
        parts.extend([b.given('second', tank.second), b.solve_for(b.local.second.actual_rate)])
    upper = None if shape == 'unbounded-spare' else (0.5 * cap if shape == 'ranked' else cap)
    parts.append(
        b.unknown(
            'spare',
            rate,
            lower=b.q(0, rate),
            upper=upper,
            scale=None if scale is None else quantity(scale),
        )
    )
    if shape == 'nonunique':
        other = b.local.other
        parts.extend(
            [
                b.unknown('other', rate, lower=b.q(0, rate), upper=cap),
                b.constraint(spare + other == cap),
                b.maximize(feed + spare + other),
            ]
        )
    elif shape == 'fair':
        parts.extend([b.constraint(feed + b.local.second.actual_rate <= cap), b.maximize(spare)])
    elif shape == 'unbounded-spare':
        parts.extend([b.maximize(feed), b.maximize(feed + spare)])
    else:
        if shape in ('ranked', 'infeasible'):
            parts.append(b.constraint(feed + spare <= cap))
        if shape == 'infeasible':
            parts.append(b.constraint(feed + spare >= 2 * cap))
        parts.append(b.maximize(feed + spare))
        if shape != 'unbounded-feed':
            parts.append(b.maximize(spare) if shape == 'ranked' else b.minimize(spare))
    builder.entity('planner', b.solver('dispatch', *parts))
    return builder.finish()


def flow_pairs(seed):
    for size, shape, unit, scale in flows.spellings(seed):
        yield (
            f'{shape}/{unit}/{scale}',
            partial(text_program, flows.flow_source(size, shape, unit, scale), flows.UNITS),
            partial(flow_program, size, shape, unit, scale),
            True,
        )


def check_solver_parity(seed):
    check_pairs(seed, (*stock_pairs(seed), *flow_pairs(seed)))
