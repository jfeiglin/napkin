"""Independent public authoring for the original Plant and the stage, band, switch and stock corpora."""

from fractions import Fraction
from functools import partial
from random import Random

from napkin.program import build as b
from tests.engine import stage_broadcast_cases as broadcast
from tests.engine import stage_read_cases as scalar
from tests.engine.parity_stage_bands import check_comparison, check_switch
from tests.engine.parity_stage_inputs import UNITS, text
from tests.engine.parity_stage_stocks import check_cross_rate, check_stock
from tests.engine.port_cases import UNITS as PLANT_UNITS
from tests.engine.port_cases import Case, Spelling, text_program
from tests.engine.program_parity import check_pairs

__all__ = [
    'check_comparison',
    'check_cross_rate',
    'check_plant',
    'check_stage',
    'check_stock',
    'check_switch',
]


def plant(case, spelling):
    """Match the authored declaration order and explicit arithmetic of the Plant text form."""
    builder = b.Builder(PLANT_UNITS)
    unit = spelling.unit
    rate_unit = f'{unit}/h'

    def qty(value, u=unit):
        value = Fraction(value)
        n = b.q(value.numerator * spelling.factor, u)
        return n if value.denominator == 1 else n / value.denominator

    def stock(name, initial=0, u=unit):
        return b.value(name, u, qty(initial), lower=b.q(0, u), scale=qty(1))

    early, late = (case.high, case.low) if case.falling else (case.low, case.high)
    demand = b.ifelse(b.t > b.q(float(case.opening), 'h'), qty(late, rate_unit), qty(early, rate_unit))
    request = b.fmax(qty(0, rate_unit), b.this.demand if spelling.named else demand)
    if not case.hard_cap:
        request = b.fmin(request, qty(case.ceiling, rate_unit))
    drain = [b.move(qty(1), b.local.batch, b.this.bulk)] if spelling.split else []
    drain.extend(
        (
            b.move(b.local.batch, b.local.batch, b.this.bulk),
            b.move(qty(case.large), b.this.bulk, b.this.saved),
            b.move(b.this.bulk, b.this.bulk, b.this.paid),
        )
    )
    parts = [
        stock('delivered', u='L'),
        b.value(
            'projected',
            'L/h',
            b.formula(b.this.delivered / b.q(4, 'h')),
            scale=qty(Fraction(1, 4), rate_unit),
        ),
        stock('basin', case.large, 'L'),
        stock('refund'),
        stock('parked'),
        stock('cash', 2),
        stock('bulk'),
        stock('paid'),
        stock('saved'),
        b.value('marked', b.BOOL, False),
        b.event(
            'observe',
            b.after(
                b.q(1, 'h'), b.assign(b.this.marked, True), when=b.this.delivered > qty(case.guard_level)
            ),
        ),
        b.event('signal', b.after(b.q(0, 'h')), b.when(b.t >= b.q(1.25, 'h'), b.start(b.this.signal))),
    ]
    if spelling.named:
        parts.append(b.value('demand', 'L/h', b.formula(demand)))
    parts.extend(
        (
            b.flow(
                'tap',
                b.SOURCE,
                b.this.delivered,
                request=b.formula(request),
                capacity=b.q(case.ceiling, 'L/h') if case.hard_cap else None,
            ),
            b.flow(
                'ramp',
                b.SOURCE,
                b.this.basin,
                request=b.formula(qty(Fraction(1, 10), rate_unit) * b.t / b.q(1, 'h')),
            ),
            b.event(
                'refund_batch',
                b.after(
                    b.q(1, 'h'),
                    b.move(qty(case.large), b.this.basin, b.this.parked),
                    b.move(b.this.basin, b.this.basin, b.this.refund),
                ),
            ),
            b.event(
                'work',
                stock('batch', case.large),
                b.after(b.q(0, 'h'), b.move(qty(case.share), b.this.cash, b.local.batch)),
                b.after(b.q(1, 'h'), *drain),
            ),
        )
    )
    if spelling.empty_event:
        parts.append(b.event('idle', b.after(b.q(0.875, 'h'))))
    entity = builder.entity('plant', *parts)
    starts = [b.start(entity.work), b.start(entity.refund_batch), b.start(entity.observe)]
    if spelling.empty_event:
        starts.append(b.start(entity.idle))
    builder.setup(*starts)
    return builder.finish()


def pairs_plant(seed):
    case = Case.of(seed)
    pairs = []
    for flag in ('base', 'named', 'small_unit', 'split', 'empty_event'):
        spelling = Spelling(**({} if flag == 'base' else {flag: True}))
        pairs.append(
            (flag, lambda s=spelling: text_program(case, s).program, partial(plant, case, spelling), True)
        )
    return pairs


def check_plant(seed):
    check_pairs(seed, pairs_plant(seed))


def scalar_program(seed):
    if seed == 0:
        old, new, cutoff, target, old_floor, new_floor = 0, 2, 1, 2, 'narrow', 'wide'
    else:
        rng = Random(seed)
        lo = rng.randrange(12)
        cutoff = lo + rng.randint(1, 4)
        hi = cutoff + rng.randint(1, 4)
        old, new = (hi, lo) if rng.getrandbits(1) else (lo, hi)
        old_floor, new_floor = ('wide', 'narrow') if rng.getrandbits(1) else ('narrow', 'wide')
        target = old if rng.getrandbits(1) else new
    builder = b.Builder(UNITS)
    choice = builder.enum('enum[PICK, PASS]', 'PICK', 'PASS')
    t = b.this
    guard = t.a > cutoff
    choose = b.ifelse(guard, 7, 3)
    moved = b.ifelse(guard, b.q(7, 'L'), b.q(3, 'L'))
    fields = [
        b.value('a', '', b.formula(old)),
        b.value('half', '', b.formula(old + 0.5)),
        b.value('nested', b.BOOL, b.formula(guard)),
        b.value('narrow', '', 1e-6, scale=1),
        b.value('wide', '', 1e-6, scale=10000),
        b.value('probe', '', b.formula(getattr(t, old_floor))),
    ]
    for name in (
        'direct',
        'greater',
        'equal',
        'member',
        'choice',
        'guarded',
        'selected',
        'indirect',
        'difference',
        'within_floor',
    ):
        is_bool = name in ('greater', 'equal', 'member', 'indirect', 'within_floor')
        fields.append(b.value(name, b.BOOL if is_bool else '', False if is_bool else -1))
    fields.extend(
        b.value(name, 'L', initial) for name, initial in [('stock', 32), ('moved', 0), ('captured', 0)]
    )
    remember = b.event(
        'remember', b.param('amount', 'L'), b.after(b.q(0, 'h'), b.assign(t.captured, b.local.amount))
    )
    change = b.event(
        'change',
        b.after(
            b.q(1, 'h'),
            b.assign(t.a, b.formula(new)),
            b.assign(t.half, b.formula(new + 0.5)),
            b.assign(t.probe, b.formula(getattr(t, new_floor))),
            b.assign(t.direct, t.a),
            b.assign(t.greater, guard),
            b.assign(t.equal, t.a == target),
            b.assign(t.member, b.within(t.a, target, target)),
            b.assign(t.choice, choose),
            b.if_(guard, [b.assign(t.guarded, 7)], [b.assign(t.guarded, 3)]),
            b.switch(
                b.draw(b.categorical(choice, PICK=2, PASS=1)),
                b.case(choice.PICK, b.assign(t.selected, 7), when=guard),
                b.case(choice.PASS, b.assign(t.selected, 3)),
            ),
            b.assign(t.indirect, t.nested),
            b.assign(t.difference, t.half - cutoff),
            b.assign(t.within_floor, t.probe == 0),
            b.move(moved, t.stock, t.moved),
            b.start(t.remember, moved),
        ),
    )
    entity = builder.entity('box', *fields, remember, change)
    builder.setup(b.start(entity.change))
    return builder.finish()


def broadcast_program(seed, family, split):
    rng = Random(seed)
    ranks = [1, 2] if not seed else rng.sample(range(1, 24), rng.randint(2, 5))
    order = sorted(range(len(ranks)), key=ranks.__getitem__)
    builder = b.Builder(broadcast.UNITS)
    setting = b.input_ if family == 'selection' else b.value
    template = builder.template(
        'Machine',
        setting('rank', '', 0),
        b.event('act', b.after(b.q(0, 'h'), b.assign(b.named('dispatcher').winner, b.this.rank))),
    )
    members = [builder.member(template, f'm{i}', rank=rank) for i, rank in enumerate(ranks)]
    threshold = 0
    if family == 'selection':
        k = rng.choice(order[1:])
        new = ranks[k]
        if seed % 2:
            threshold, new = new, min(ranks)
        assign = b.assign(b.this.threshold, new)
        receivers = template.instances.where(b.item.rank >= b.this.threshold)
    else:
        k = order[-1] if seed % 2 else order[0]
        assign = b.assign(members[k].rank, min(ranks) - 1 if seed % 2 else max(ranks) + 1)
        receivers = template.instances.by('rank')
    start = b.start(receivers.act)
    stages = (
        (b.after(b.q(1, 'h'), assign), b.after(b.q(0, 'h'), start))
        if split
        else (b.after(b.q(1, 'h'), assign, start),)
    )
    entity = builder.entity(
        'dispatcher', b.value('threshold', '', threshold), b.value('winner', '', 0), b.event('send', *stages)
    )
    builder.setup(b.start(entity.send))
    return builder.finish()


def pairs_stage(seed):
    pairs = [
        ('scalar', lambda: text(scalar.scalar_stage_model(seed)[0]), partial(scalar_program, seed), True)
    ]
    for family in broadcast.FAMILIES:
        for split in (False, True):
            source = broadcast.broadcast_source(seed, family, split)
            pairs.append(
                (
                    f'{family}.{split}',
                    partial(text, source, broadcast.UNITS),
                    partial(broadcast_program, seed, family, split),
                    True,
                )
            )
    return pairs


def check_stage(seed):
    check_pairs(seed, pairs_stage(seed))
