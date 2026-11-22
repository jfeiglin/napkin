"""Construct the lag models through the Python builder, independently of the text compiler."""

from decimal import Decimal
from random import Random

from napkin.model.compile import compile_text
from napkin.program import build as b
from tests.engine.lag_bend_cases import bend_model
from tests.engine.lag_monotonicity_cases import FAMILIES, UNITS, lag_model
from tests.engine.program_parity import check_pairs


def _transfer_program(seed, family):
    rng = Random(seed)
    low, step, delay = (2, 4, 1) if seed == 0 else (rng.randint(1, 14), rng.randint(1, 8), rng.randint(1, 4))
    high = low + 2 * step
    builder = b.Builder(UNITS)
    yard = b.named('yard')
    wait, transfer = b.q(delay, 'h'), b.q(step, 'L')
    if family == 'minimum':
        template = builder.template('Bin', b.value('stock', 'L', low), b.value('receipts', 'L', 0))
        first = builder.member(template, 'first', stock=b.q(high, 'L'))
        second = builder.member(template, 'second')
        builder.entity(
            'yard',
            b.value('floor', 'L', b.formula(b.fmin(template.instances.stock))),
            b.value('ceiling', 'L', b.formula(b.fmax(template.instances.stock))),
            b.value('total', 'L', b.formula(b.fsum(template.instances.stock))),
            b.value('least_receipts', 'L', b.formula(b.fmin(template.instances.receipts))),
            b.event(
                'exchange',
                b.after(wait, b.move(transfer, first.stock, second.stock), b.add(second.receipts, transfer)),
                b.after(wait, b.move(transfer, second.stock, first.stock), b.add(first.receipts, transfer)),
            ),
        )
        builder.setup(b.start(yard.exchange))
    elif family == 'cutoff':
        batches = b.this.batch.occurrences
        builder.entity(
            'yard',
            b.value('picked', 'L', b.formula(batches.at(b.q(2 * delay, 'h')).amount)),
            b.value('count_batches', '', b.formula(b.count(batches))),
            b.event('batch', b.param('amount', 'L'), b.after(b.q(4 * delay, 'h'))),
            b.event(
                'launch',
                b.after(wait, b.start(b.this.batch, b.q(low, 'L'))),
                b.after(b.q(2 * delay, 'h'), b.start(b.this.batch, b.q(high + step, 'L'))),
            ),
        )
        builder.setup(b.start(yard.batch, b.q(high, 'L')), b.start(yard.launch))
    elif family == 'overlap':
        batches = b.this.batch.occurrences
        kind = b.occurrence_of('yard', 'batch')
        builder.entity(
            'yard',
            b.event(
                'batch',
                b.param('initial', 'L'),
                b.value('stock', 'L', b.local.initial),
                b.after(b.q(4 * delay + 1, 'h')),
            ),
            b.event(
                'launch',
                b.after(wait, b.start(b.this.batch, b.q(low, 'L'))),
                b.after(wait, b.start(b.this.transfer)),
            ),
            b.event(
                'transfer',
                b.value('first', kind, batches.at(b.q(0, 'h'))),
                b.value('second', kind, batches.at(wait)),
                b.after(wait, b.move(transfer, b.local.first.stock, b.local.second.stock)),
            ),
        )
        builder.setup(b.start(yard.batch, b.q(high, 'L')), b.start(yard.launch))
    else:
        raise ValueError(f'unknown lag case {family}')
    return builder.finish()


def check_lag_monotonicity_parity(seed):
    check_pairs(
        seed,
        [
            (
                family,
                lambda f=family: compile_text(lag_model(seed, f)[0], UNITS).program,
                lambda f=family: _transfer_program(seed, f),
                True,
            )
            for family in FAMILIES
        ],
    )


def _bend_program(seed, rate, lower, upper):
    builder = b.Builder(UNITS)
    opening = float(Decimal(str(lower)) * rate)
    cap = float(Decimal(str(upper)) * rate)
    arm = b.fmin(2 * b.this.x - b.q(opening, 'L'), b.q(cap, 'L'))
    parts = [
        b.value('x', 'L', 0),
        b.flow('fill', b.SOURCE, b.this.x, request=b.q(rate, 'L/h')),
    ]
    if seed % 3 == 1:
        parts.append(b.value('capped', 'L', b.formula(arm)))
        arm = b.this.capped
    parts.extend(
        [
            b.value('credit', 'L', b.formula(b.fmax(b.this.x, arm))),
            b.value('plain', 'L', b.formula(b.this.x)),
        ]
    )
    builder.entity('yard', *parts)
    return builder.finish()


def check_lag_bends_parity(seed):
    source, rate, lower, upper = bend_model(seed)
    check_pairs(
        seed,
        [
            (
                'bend',
                lambda: compile_text(source, UNITS).program,
                lambda: _bend_program(seed, rate, lower, upper),
                True,
            )
        ],
    )
