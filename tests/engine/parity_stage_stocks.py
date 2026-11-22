"""Independent stock postings, checkpoint edits, and cross-set rate programs."""

from functools import partial

from napkin.program import build as b
from tests.engine import cross_rate_cases as rates
from tests.engine import stock_balance_cases as balances
from tests.engine import stock_edit_cases as edits
from tests.engine.parity_stage_inputs import UNITS, number, text
from tests.engine.program_parity import check_pairs


def litres(amount):
    return b.q(number(amount), 'L')


def stock(name, opening=0, lower=0, upper=None):
    if not isinstance(opening, b.X):
        opening = litres(opening)
    return b.value(
        name, 'L', opening, lower=litres(lower), upper=litres(upper) if upper is not None else None
    )


def move(amount, source, destination):
    return b.move(litres(amount), getattr(b.this, source), getattr(b.this, destination))


def stock_program(case):
    builder = b.Builder(UNITS)
    name = case.name
    shifts = [move(n, src, dst) for _, src, dst, n in case.moves]
    if name.startswith(('+=.', '-=.', '=.')):
        principal = case.moves[0][3]
        extra = case.moves[1][3]
        if name.startswith('+='):
            opening, assign = principal, b.add(b.this.stock, litres(extra))
        elif name.startswith('='):
            opening, assign = principal, b.assign(b.this.stock, b.this.stock + litres(extra))
        else:
            opening, assign = int(principal + 2 * extra), b.subtract(b.this.stock, litres(extra))
        fields = [stock('stock', opening), stock('bulk'), stock('receipt')]
        stages = [(assign, shifts[0]), (shifts[1],)]
    elif name == 'stock-dependent-opening':
        principal = case.moves[0][3]
        extra = case.moves[-1][3]
        fields = [
            stock('anchor', principal + extra),
            stock('stock', b.this.anchor + litres(extra)),
            stock('bulk'),
            stock('receipt'),
        ]
        stages = [shifts[:2], shifts[2:]]
    elif name == 'assign-decimal-bound':
        total = case.moves[0][3] + case.moves[1][3]
        fields = [stock('stock', upper=total), stock('bulk'), stock('receipt')]
        stages = [(b.assign(b.this.stock, litres(total)), shifts[0]), (shifts[1],)]
    elif case.refused:
        dest = name.startswith('destination.')
        step = case.moves[0][3]
        base = int(dict(case.balances)['stock'] + (step if dest else -step))
        fields = [
            stock('stock', base, 0 if dest else base, base if dest else None),
            stock('supply', 4 * step),
            stock('receipt'),
        ]
        ends = ('supply', 'stock') if dest else ('stock', 'receipt')
        stages = [(shifts[0],), (move(step, 'supply', 'receipt'), move(2 * step, *ends))]
    elif name == 'exact-capacity':
        extra, principal = (m[3] for m in case.moves)
        fields = [stock('stock', principal, upper=principal + extra), stock('small', extra), stock('bulk')]
        stages = [(m,) for m in shifts]
    else:
        opening = name == 'leftover.opening'
        principal = case.moves[-1][3]
        extra = dict(case.balances)['stock']
        fields = [
            stock('stock', principal + extra if opening else principal),
            stock('bulk'),
            stock('small', 0 if opening else extra),
        ]
        stages = [(m,) for m in shifts]
    if name.endswith('.idle'):
        fields.append(b.flow('idle', b.this.stock, b.SINK, request=b.q(0, 'L/h')))
    yard = builder.entity(
        'yard', *fields, b.event('work', *(b.after(b.q(1, 'h'), *actions) for actions in stages))
    )
    builder.setup(b.start(yard.work))
    return builder.finish()


def edit_program(seed, position, idle):
    opening, intake, principal, _ = edits.stock_edit_amounts(seed)
    withdraw = principal + intake if position == 'before' else principal
    first = move(intake, 'supply', 'tank')
    second = move(withdraw, 'tank', 'receipt')
    stages = (
        (b.after(b.q(0.25, 'h'), first, second),)
        if position == 'within'
        else (b.after(b.q(0.25, 'h'), first), b.after(b.q(0.5, 'h'), second))
    )
    fields = [stock('tank', opening), stock('supply', intake), stock('receipt'), b.value('ordinary', '', 7)]
    if idle:
        fields.append(b.flow('idle', b.SOURCE, b.this.tank, request=b.q(0, 'L/h')))
    builder = b.Builder(UNITS)
    yard = builder.entity('yard', *fields, b.event('transfer', *stages))
    builder.setup(b.start(yard.transfer))
    return builder.finish()


def pairs_stock(seed):
    pairs = []
    for case in (*balances._inventory(seed), *balances._capacity(seed)):
        pairs.append((case.name, partial(text, case.source), partial(stock_program, case), True))
    for position in edits.STOPS:
        for idle in (False, True):
            pairs.append(
                (
                    f'edit.{position}.{idle}',
                    partial(text, edits.stock_edit_source(seed, position, idle)),
                    partial(edit_program, seed, position, idle),
                    True,
                )
            )
    return pairs


def check_stock(seed):
    check_pairs(seed, pairs_stock(seed))


def rate_program(case, mode, event):
    selector, setting = mode.split('-')
    builder = b.Builder(UNITS)

    def rate(value):
        return b.q(number(value), 'L/h')

    if selector == 'key':
        band = builder.template(
            'Band', b.input_('cutoff', 'L/h', 0), b.input_('rate', 'L/h', rate(case.below))
        )
        builder.member(band, 'low')
        builder.member(band, 'high', cutoff=rate(case.cutoff()), rate=rate(case.above))
    fields = [b.value('meter', 'L', 0), b.value('water', 'L', 0)]
    if case.state_driver:
        fields.extend((b.value('driver', 'L', 0), b.flow('wind', b.SOURCE, b.this.driver, request=rate(1))))
        moving = number(case.slope) * b.this.driver / b.q(1, 'h')
    else:
        moving = b.q(number(case.slope), 'L/h/h') * b.t
    fields.append(b.flow('tap', b.SOURCE, b.this.meter, request=b.formula(rate(case.start) + moving)))
    upstream = b.this.tap.actual_rate
    if case.multiplier != 1:
        fields.extend(
            (
                b.value('relay_meter', 'L', 0),
                b.flow('relay', b.SOURCE, b.this.relay_meter, request=b.formula(case.multiplier * upstream)),
            )
        )
        upstream = b.this.relay.actual_rate
    if selector == 'guard':
        requested = b.ifelse(upstream > rate(case.cutoff()), rate(case.above), rate(case.below))
    elif selector == 'key':
        requested = band.instances.by('cutoff').at(upstream).rate
    else:
        requested = upstream
    settings = {setting: b.formula(requested)}
    if setting == 'capacity':
        maximum = (
            case.multiplier * max(case.upstream(0), case.upstream(case.horizon))
            if selector == 'linear'
            else max(case.above, case.below)
        )
        settings['request'] = rate(maximum)
    fields.append(b.flow('pipe', b.SOURCE, b.this.water, **settings))
    if event:
        fields.append(b.event('idle', b.after(b.q(number(case.event), 'h'))))
    yard = builder.entity('yard', *fields)
    if event:
        builder.setup(b.start(yard.idle))
    return builder.finish()


def pairs_cross_rate(seed):
    case = rates.case_for(seed)
    pairs = []
    for mode in rates.MODES if seed == 0 else (rates.MODES[seed % len(rates.MODES)],):
        for event in (False, True):
            pairs.append(
                (
                    f'{mode}.event={event}',
                    partial(text, rates.source_of(case, mode, event)),
                    partial(rate_program, case, mode, event),
                    True,
                )
            )
    return pairs


def check_cross_rate(seed):
    check_pairs(seed, pairs_cross_rate(seed))
