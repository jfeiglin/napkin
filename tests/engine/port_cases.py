"""Small exact models for the engine-port gate; spell each model in both public front ends."""

from dataclasses import dataclass
from fractions import Fraction as F
from random import Random

from napkin.model.compile import compile_text
from napkin.program import build as b

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}, 'mL': ({'volume': 1}, F(1, 1000))}
HORIZON = 2


@dataclass(frozen=True)
class Case:
    opening: F
    ceiling: int
    low: F
    high: int
    large: int
    share: F
    hard_cap: bool
    falling: bool
    guard_level: F

    @classmethod
    def of(cls, seed):
        rng = Random(seed)
        ceiling = rng.randint(1, 5)
        return cls(
            F(rng.randint(2, 6), 8),
            ceiling,
            F(rng.randint(0, 3), 4),
            ceiling + rng.randint(1, 4),
            rng.choice((10_000, 4_000_000, 10_000_000)),
            F(rng.choice((1, 2, 4)), rng.choice((3, 7, 11))),
            rng.choice((False, True)),
            rng.choice((False, True)),
            F(rng.choice((1, 3, 5, 7)), 4),
        )


@dataclass(frozen=True)
class Spelling:
    empty_event: bool = False
    named: bool = False
    small_unit: bool = False
    split: bool = False

    @property
    def unit(self):
        return 'mL' if self.small_unit else 'L'

    @property
    def factor(self):
        return 1000 if self.small_unit else 1


def text_program(case, spelling):
    unit, factor = spelling.unit, spelling.factor

    def quantity(number, dimension=unit):
        numerator, denominator = F(number).as_integer_ratio()
        numerator *= factor
        if denominator == 1:
            return f'{numerator} {dimension}'
        return f'({numerator} {dimension} / {denominator})'

    def rate(number):
        return quantity(number, f'{unit}/h')

    after, before = (case.low, case.high) if case.falling else (case.high, case.low)
    jump = f'({rate(after)} if t > {float(case.opening)} h else {rate(before)})'
    if spelling.named:
        demand = f'    demand = formula({jump})\n'
        jump = 'this.demand'
    else:
        demand = ''
    # Both branches are represented across seeds. The explicit-cap form uses an outer max;
    # the inline-cap form additionally uses min, whose selected operand can change on a jump.
    request = f'max({rate(0)}, {jump})'
    if not case.hard_cap:
        request = f'min({request}, {rate(case.ceiling)})'
    scale = quantity(1)
    lines = [
        'scenario "Port corpus"',
        f'    horizon {HORIZON} h',
        'plant:',
        f'    delivered: {unit} = {quantity(0)} in [0,] scale {scale}',
    ]
    lines.extend(
        [
            f'    projected = formula(this.delivered / (4 h)) scale {rate(F(1, 4))}',
            f'    basin: {unit} = {quantity(case.large)} in [0,] scale {scale}',
            f'    refund: {unit} = {quantity(0)} in [0,] scale {scale}',
            f'    parked: {unit} = {quantity(0)} in [0,] scale {scale}',
            f'    cash: {unit} = {quantity(2)} in [0,] scale {scale}',
            f'    bulk: {unit} = {quantity(0)} in [0,] scale {scale}',
            f'    paid: {unit} = {quantity(0)} in [0,] scale {scale}',
            f'    saved: {unit} = {quantity(0)} in [0,] scale {scale}',
        ]
    )
    lines.extend(
        [
            '    marked = false',
            '    observe = event():',
            f'        after 1 h when this.delivered > {quantity(case.guard_level)}:',
            '            this.marked = true',
        ]
    )
    lines.extend(
        [
            '    signal = event():',
            '        after 0 h',
            '        when t >= 1.25 h:',
            '            this.signal.start()',
        ]
    )
    if demand:
        lines.append(demand.rstrip())
    lines.extend(['    flow tap: SOURCE -> this.delivered', f'        request = formula({request})'])
    if case.hard_cap:
        lines.append(f'        capacity = {rate(case.ceiling)}')
    lines.extend(
        [
            '    flow ramp: SOURCE -> this.basin',
            f'        request = formula({rate(F(1, 10))} * t / (1 h))',
            '    refund_batch = event():',
            '        after 1 h:',
            f'            move {quantity(case.large)} from this.basin to this.parked',
            '            move this.basin from this.basin to this.refund',
            '    work = event():',
            f'        batch: {unit} = {quantity(case.large)} in [0,] scale {scale}',
            '        after 0 h:',
            f'            move {quantity(case.share)} from this.cash to batch',
            '        after 1 h:',
        ]
    )
    if spelling.split:
        lines.append(f'            move {quantity(1)} from batch to this.bulk')
    lines.extend(
        [
            '            move batch from batch to this.bulk',
            f'            move {quantity(case.large)} from this.bulk to this.saved',
            '            move this.bulk from this.bulk to this.paid',
        ]
    )
    if spelling.empty_event:
        lines.extend(['    idle = event():', '        after 0.875 h'])
    lines += ['plant.work.start()', 'plant.refund_batch.start()', 'plant.observe.start()']
    if spelling.empty_event:
        lines.append('plant.idle.start()')
    return compile_text('\n'.join(lines) + '\n', UNITS)


def builder_program(case, spelling):
    unit, factor = spelling.unit, spelling.factor

    def amount(number):
        return b.q(number * factor, unit)

    def rate(number):
        return b.q(number * factor, f'{unit}/h')

    def stock(name, initial=0, **options):
        return b.value(name, unit, amount(initial), lower=amount(0), scale=amount(1), **options)

    builder = b.Builder(UNITS)
    after, before = (case.low, case.high) if case.falling else (case.high, case.low)
    jump = b.ifelse(b.t > b.q(case.opening, 'h'), rate(after), rate(before))
    fields = []
    if spelling.named:
        fields.append(b.value('demand', f'{unit}/h', b.formula(jump)))
        jump = b.this.demand
    request = b.call('max', rate(0), jump)
    if not case.hard_cap:
        request = b.call('min', request, rate(case.ceiling))
    drain = []
    if spelling.split:
        drain.append(b.move(amount(1), b.local.batch, b.this.bulk))
    drain.extend(
        [
            b.move(b.local.batch, b.local.batch, b.this.bulk),
            b.move(amount(case.large), b.this.bulk, b.this.saved),
            b.move(b.this.bulk, b.this.bulk, b.this.paid),
        ]
    )
    if spelling.empty_event:
        fields.append(b.event('idle', b.after(b.q(F(7, 8), 'h'))))
    plant = builder.entity(
        'plant',
        stock('delivered'),
        b.value('marked', b.BOOL, False),
        b.event('signal', b.after(b.q(0, 'h')), b.when(b.t >= b.q(F(5, 4), 'h'), b.start(b.this.signal))),
        b.event(
            'observe',
            b.after(
                b.q(1, 'h'), b.assign(b.this.marked, True), when=b.this.delivered > amount(case.guard_level)
            ),
        ),
        stock('cash', 2),
        stock('bulk'),
        stock('paid'),
        stock('saved'),
        *fields,
        stock('basin', case.large),
        stock('refund'),
        stock('parked'),
        b.value('projected', f'{unit}/h', b.formula(b.this.delivered / b.q(4, 'h')), scale=rate(F(1, 4))),
        b.flow('ramp', b.SOURCE, b.this.basin, request=b.formula(rate(F(1, 10)) * b.t / b.q(1, 'h'))),
        b.event(
            'refund_batch',
            b.after(
                b.q(1, 'h'),
                b.move(amount(case.large), b.this.basin, b.this.parked),
                b.move(b.this.basin, b.this.basin, b.this.refund),
            ),
        ),
        b.flow(
            'tap',
            b.SOURCE,
            b.this.delivered,
            request=b.formula(request),
            capacity=rate(case.ceiling) if case.hard_cap else None,
        ),
        b.event(
            'work',
            stock('batch', case.large),
            b.after(b.q(0, 'h'), b.move(amount(case.share), b.this.cash, b.local.batch)),
            b.after(b.q(1, 'h'), *drain),
        ),
    )
    starts = [b.start(plant.work), b.start(plant.refund_batch), b.start(plant.observe)]
    if spelling.empty_event:
        starts.append(b.start(plant.idle))
    builder.setup(*starts)
    return builder.finish()
