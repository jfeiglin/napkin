"""Independent builder forms of the historical record, lookup, and precision models."""

from decimal import Decimal
from fractions import Fraction
from functools import partial
from random import Random

from napkin.model.compile import compile_text
from napkin.program import build as b
from tests.engine import record_history_cases as history
from tests.engine import record_identity_cases as identity
from tests.engine import record_numerics_cases as numerics
from tests.engine.program_parity import check_pairs


def pair(name, source, units, build):
    def text_program():
        return compile_text(source, units).program

    return name, text_program, build, True


def written(value):
    """Represent the written decimal as an integer, float or exact rational in the builder API."""
    token = str(value)
    if not any(mark in token for mark in '.eE'):
        return int(token)
    rounded = float(token)
    exact = Fraction(token)
    return rounded if Fraction(str(rounded)) == exact else exact


def postings(seed, returns):
    multiple = Random(seed).randrange(1, 300) if seed else 1
    opening, delta = 4_000_000 * multiple, Decimal('3e-10') * multiple
    make = b.Builder(history.UNITS)

    def transfer(amount, source, sink):
        return b.move(b.q(written(amount), 'L'), getattr(b.this, source), getattr(b.this, sink))

    second = (
        [transfer(delta, 'receipt', 'stock')]
        if returns
        else [transfer(delta, 'supply', 'receipt'), transfer(2 * delta, 'supply', 'stock')]
    )
    yard = make.entity(
        'yard',
        b.value('stock', 'L', opening, lower=0, upper=opening),
        b.value('supply', 'L', written(4 * delta), lower=0),
        b.value('receipt', 'L', 0, lower=0),
        b.event(
            'work', b.after(b.q(1, 'h'), transfer(delta, 'stock', 'receipt')), b.after(b.q(1, 'h'), *second)
        ),
    )
    make.setup(b.start(yard.work))
    return make.finish()


def elapsed_history(seed, mode):
    rand = Random(seed)
    first = float(Fraction(rand.randrange(3, 11), 8)) if seed else 1.0
    wait = float(Fraction(rand.randrange(1, 6), 8)) if seed else 0.5
    tiny = Decimal(rand.randrange(1, 10)) / 10 if seed else Decimal('0.5')
    value = tiny if mode != 'visible' else rand.randrange(1, 20)
    unit = 'pL' if mode != 'visible' else 'L'
    second = value if mode == 'repeat' else value * 2
    make = b.Builder(history.UNITS)
    elapsed = b.elapsed(b.this.amount)
    yard = make.entity(
        'yard',
        b.value('amount', 'L', 0),
        b.value('first_seen', 'h', 0),
        b.value('last_seen', 'h', 0),
        b.value('age', 'h', b.formula(elapsed)),
        b.event(
            'work',
            b.after(b.q(first, 'h'), b.assign(b.this.amount, b.q(written(value), unit))),
            b.after(b.q(wait, 'h'), b.assign(b.this.first_seen, elapsed)),
            b.after(b.q(wait, 'h'), b.assign(b.this.amount, b.q(written(second), unit))),
            b.after(b.q(wait, 'h'), b.assign(b.this.last_seen, elapsed)),
        ),
    )
    make.setup(b.start(yard.work))
    return make.finish()


def same_time(seed, separate):
    rand = Random(seed)
    first = float(Fraction(rand.randrange(3, 11), 8)) if seed else 1.0
    wait = float(Fraction(rand.randrange(1, 6), 8)) if seed else 0.5
    amount = b.q(0.5, 'pL') if seed % 2 else b.q(rand.randrange(1, 12) if seed else 1, 'L')
    make = b.Builder(history.UNITS)
    zero = b.assign(b.this.amount, b.q(0, 'L'))
    elapsed = b.elapsed(b.this.amount)
    restore = [b.event('restore', b.after(b.q(0, 'h'), zero))] if separate else []
    yard = make.entity(
        'yard',
        b.value('amount', 'L', 0),
        b.value('seen', 'h', 0),
        b.value('age', 'h', b.formula(elapsed)),
        *restore,
        b.event(
            'work',
            b.after(
                b.q(first, 'h'),
                b.assign(b.this.amount, amount),
                b.start(b.this.restore) if separate else zero,
            ),
            b.after(b.q(wait, 'h'), b.assign(b.this.seen, elapsed)),
        ),
    )
    make.setup(b.start(yard.work))
    return make.finish()


def check_parity_history(seed):
    pairs = []
    for returns in (False, True):
        case = history.postings(seed, returns)
        pairs.append(pair(case.name, case.source, history.UNITS, partial(postings, seed, returns)))
    for mode in ('visible', 'tiny', 'repeat'):
        case = history.elapsed(seed, mode)
        pairs.append(pair(case.name, case.source, history.UNITS, partial(elapsed_history, seed, mode)))
    for separate in (False, True):
        case = history.same_time(seed, separate)
        pairs.append(pair(case.name, case.source, history.UNITS, partial(same_time, seed, separate)))
    check_pairs(seed, pairs)


def stored_identity(seed, first, second, early, gap, horizon):
    make = b.Builder(identity.UNITS)
    hold = b.after(b.q(horizon + 1, 'h'))
    yard = make.entity(
        'yard',
        b.input_('delay', 'h', early),
        b.event('measure', b.param('amount', 'L'), hold),
        b.event(
            'capture',
            b.value('job', b.occurrence_of('yard', 'measure'), b.this.measure.occurrences.at(b.t)),
            b.value('observed', 'L', b.formula(b.local.job.amount)),
            b.value('origin', 'h', b.formula(b.local.job.started)),
            hold,
        ),
        b.event('load', b.after(b.q(gap, 'h'), b.start(b.this.measure, b.q(second, 'L')))),
        b.event('launch', b.after(b.this.delay, b.start(b.this.capture))),
    )
    starts = (b.start(yard.load), b.start(yard.launch))
    make.setup(b.start(yard.measure, b.q(first, 'L')), *(starts[::-1] if seed % 2 else starts))
    return make.finish()


def check_parity_identity(seed):
    source, times, expected = identity._case(seed)
    first, _, early = expected['A']
    second, gap, _ = expected['B']
    check_pairs(
        seed,
        [
            pair(
                'independent-starts',
                source,
                identity.UNITS,
                partial(stored_identity, seed, first, second, early, gap, times[-1]),
            )
        ],
    )


def stored_numerics(seed, unit):
    bound, gap, start, old, new = numerics.case_values(seed)

    def amount(value):
        return b.q(written(format(value * numerics.PER_L[unit], 'f')), unit)

    limit, above = amount(bound), amount(bound + gap)
    outside = amount(Decimal(bound) * Decimal('0.9999'))
    date = b.q(start, 'h')
    members = b.this.batch.occurrences

    def selected(end):
        return members.at(b.ifelse(b.this.level <= end, date, b.q(0, 'h'))).amount

    make = b.Builder(numerics.UNITS)
    meter = make.entity(
        'meter',
        b.value('level', unit, above, scale=amount(1)),
        b.value('seen', 'L', 0),
        b.value('near', 'L', b.formula(selected(limit))),
        b.value('filtered', 'L', b.formula(members.where(b.item.gate <= limit).at(b.t).amount)),
        b.value('outside', 'L', b.formula(selected(outside))),
        b.value('equal', 'L', b.formula(selected(above))),
        b.event('batch', b.param('amount', 'L'), b.param('gate', 'L'), b.after(b.q(start + 3, 'h'))),
        b.event(
            'launch',
            b.after(date, b.start(b.this.batch, b.q(new, 'L'), above)),
            b.after(b.q(1, 'h'), b.assign(b.this.seen, b.this.near)),
        ),
    )
    make.setup(b.start(meter.batch, b.q(old, 'L'), limit), b.start(meter.launch))
    return make.finish()


def check_parity_numerics(seed):
    check_pairs(
        seed,
        [
            pair(
                unit, numerics.record_source(seed, unit), numerics.UNITS, partial(stored_numerics, seed, unit)
            )
            for unit in ('L', 'kL' if seed % 2 else 'mL')
        ],
    )
