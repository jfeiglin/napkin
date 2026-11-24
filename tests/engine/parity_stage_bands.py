"""Comparison and switch programs expressed independently in text and in the structured DSL."""

from fractions import Fraction
from functools import partial
from operator import ge, gt, le, lt
from random import Random

from napkin.program import build as b
from tests.engine import comparison_band_cases as bands
from tests.engine import switch_selection_cases as selections
from tests.engine import switch_side_cases as switches
from tests.engine.parity_stage_inputs import UNITS, number, text
from tests.engine.program_parity import check_pairs


def gap_program(seed, placement, unit, section, end=None):
    origin, delta, other, floor = bands.gap_case(seed, placement)

    def quantity(hours):
        return b.q(number(hours * (60 if unit == 'min' else 1)), unit)

    compare = lt if seed % 2 else gt

    def guard(operand):
        return compare(operand - quantity(origin), b.q(0, 'h') if end is not None else quantity(0))

    definition = b.value('a', unit, b.formula(quantity(origin + delta)), scale=quantity(floor))
    builder = b.Builder(bands.UNITS)
    if end is not None:
        builder.entity(
            'box', definition, b.value('choice', '', b.ifelse(guard(b.this.a), 7, 1), lower=end, upper=end)
        )
        return builder.finish()
    fields = [
        definition,
        b.value('guard', b.BOOL, b.formula(guard(b.this.a))),
        b.value('choice', '', b.ifelse(guard(b.this.a), 7, 1)),
    ]
    if section in ('fields', 'rates', 'full'):
        parts = fields.copy()
        if section != 'fields':
            parts.extend(
                (
                    b.value('water', 'L', 0),
                    b.flow(
                        'use',
                        b.SOURCE,
                        b.this.water,
                        request=b.formula(b.ifelse(guard(b.this.a), b.q(7, 'L/h'), b.q(1, 'L/h'))),
                    ),
                )
            )
        template = builder.template('Box', *parts)
        builder.member(template, 'first')
        builder.member(template, 'second', a=b.formula(quantity(origin + other)))
    if section in ('solver', 'full'):
        solver = b.solver(
            'dispatch',
            b.given('pipe', b.this.use),
            b.given('amount', b.this.a),
            b.solve_for(b.local.pipe.actual_rate),
            b.constraint(
                b.local.pipe.actual_rate <= b.ifelse(guard(b.local.amount), b.q(7, 'L/h'), b.q(1, 'L/h'))
            ),
            b.maximize(b.local.pipe.actual_rate),
        )
        builder.entity(
            'solver_host',
            *fields,
            b.value('water', 'L', 0),
            b.flow('use', b.SOURCE, b.this.water, request=b.q(10, 'L/h')),
            solver,
        )
    return builder.finish()


def range_literal_program(kind, lower, unit):
    """The range source writes each endpoint as one decimal quantity."""
    lo = b.q(number(lower * (60 if unit == 'min' else 1)), unit)
    hi = b.q(0, unit)
    builder = b.Builder(bands.UNITS)
    if kind == 'field':
        builder.entity('box', b.value('duration', 'h', hi, lower=lo, upper=hi))
    else:
        box = builder.entity(
            'box', b.event('take', b.param('duration', 'h', lower=lo, upper=hi), b.after(b.q(1, 'h')))
        )
        builder.setup(b.start(box.take, hi))
    return builder.finish()


def pairs_comparison(seed):
    pairs = []
    for placement, lower in bands.interval_limits(seed).items():
        for unit in ('h', 'min'):
            for kind in ('parameter', 'field'):
                pairs.append(
                    (
                        f'range.{placement}.{unit}.{kind}',
                        partial(text, bands.range_source(kind, lower, unit), bands.UNITS),
                        partial(range_literal_program, kind, lower, unit),
                        placement == 'inside',
                    )
                )
            for section in ('fields', 'rates', 'solver'):
                pairs.append(
                    (
                        f'gap.{placement}.{unit}.{section}',
                        partial(text, bands.gap_source(seed, placement, unit, section), bands.UNITS),
                        partial(gap_program, seed, placement, unit, section),
                        True,
                    )
                )
            origin, delta, _, floor = bands.gap_case(seed, placement)
            op = '<' if seed % 2 else '>'
            for end in (1, 7):
                literal = bands.quantity
                source = f'box:\n    a = formula({literal(origin + delta, unit)}) scale {literal(floor, unit)}\n    choice = 7 if this.a - {literal(origin, unit)} {op} 0 h else 1 in [{end}, {end}]\n'
                pairs.append(
                    (
                        f'initializer.{placement}.{unit}.{end}',
                        partial(text, source, bands.UNITS),
                        partial(gap_program, seed, placement, unit, 'initializer', end),
                        True,
                    )
                )
    return pairs


def check_comparison(seed):
    check_pairs(seed, pairs_comparison(seed))


def switch_inputs(seed):
    rng = Random(seed)
    variant = switches.VARIANTS[(seed // 4) % len(switches.VARIANTS)]
    pace = (7, Fraction(1, 10), -7, Fraction(-1, 10))[seed % 4]
    start = 5 if seed < 2 else rng.randint(max(5, 1 - pace), 25)
    if seed >= 16:
        pace = (1 if pace > 0 else -1) * Fraction(rng.randint(1, 19), rng.choice((5, 8, 10)))
    op = ('>', '<', '<', '>')[seed % 4]
    if seed >= 16 and seed % 5 == 0:
        op += '='
    origin, slope, scale, change = start, pace, None, None
    cross = Fraction(rng.choice((3, 4, 5)), 8)
    if variant == 'inside-band':
        change = switches.switch_gap(1) * Fraction(1 if seed % 2 else -1, 1000)
        origin += change * cross
        slope -= change
    elif variant == 'band-exit':
        scale = 100_000
        edge = switches.switch_gap(scale) * (1 if op in ('>', '<=') else -1)
        origin -= edge / 2
        slope -= edge / (2 * cross)
    elif variant != 'co-moving':
        change = Fraction(pace, 2) * (1 if seed % 2 else -1)
        if variant == 'departure':
            cross = Fraction(0)
        if variant != 'late-separation':
            origin += change * cross
            slope -= change
    return variant, op, start, pace, origin, slope, scale, change, cross


def rational_text(n, u):
    """Spell a nonintegral physical coefficient exactly using public text quantity arithmetic."""
    q = Fraction(n)
    return f'{q.numerator} {u}' if q.denominator == 1 else f'({q.numerator} {u} / {q.denominator})'


def switch_text(settings, family):
    variant, op, start, pace, origin, slope, scale, change, cross = settings
    limit = '' if scale is None else f' scale {scale} L'
    lines = ['plant:', f'    level: L = {start} L{limit}']
    if family == 'sparse':
        lines.append(f'        {"inflow" if pace > 0 else "outflow"}.capacity = 40 L/h')
    mirror = f'{rational_text(origin, "L")} + t * {rational_text(slope, "L/h")}'
    if variant == 'late-separation':
        mirror += f' - {rational_text(change, "L/h")} * max(0 h, t - {rational_text(cross, "h")})'
    route = 'SOURCE -> this.level' if pace > 0 else 'this.level -> SINK'
    lines.extend(
        (
            f'    mirror = formula({mirror})',
            '    delivery: L = 0 L',
            f'    flow drive: {route}',
            f'        request = {rational_text(abs(pace), "L/h")}',
            '    flow meter: SOURCE -> this.delivery',
            f'        request = formula(1 L/h if this.level {op} this.mirror else 0 L/h)',
        )
    )
    if family == 'declared':
        lines.extend(
            (
                'provider:',
                '    share = solver:',
                '        inputs:',
                '            drive = plant.drive',
                '            meter = plant.meter',
                '        solve_for:',
                '            drive.actual_rate',
                '            meter.actual_rate',
            )
        )
    return text('\n'.join(lines) + '\n')


def switch_builder(settings, family):
    variant, op, start, pace, origin, slope, scale, change, cross = settings
    builder = b.Builder(UNITS)

    def coefficient(n, u):
        ratio = Fraction(n)
        qty = b.q(ratio.numerator, u)
        return qty if ratio.denominator == 1 else qty / ratio.denominator

    mirror = coefficient(origin, 'L') + b.t * coefficient(slope, 'L/h')
    if variant == 'late-separation':
        mirror -= coefficient(change, 'L/h') * b.fmax(b.q(0, 'h'), b.t - coefficient(cross, 'h'))
    cap = b.endpoint(capacity=b.q(40, 'L/h')) if family == 'sparse' else None
    endpoints = (b.SOURCE, b.this.level) if pace > 0 else (b.this.level, b.SINK)
    compare = {'>': gt, '<': lt, '>=': ge, '<=': le}[op]
    plant = builder.entity(
        'plant',
        b.value(
            'level',
            'L',
            start,
            scale=scale,
            inflow=cap if pace > 0 else None,
            outflow=cap if pace < 0 else None,
        ),
        b.value('mirror', 'L', b.formula(mirror)),
        b.value('delivery', 'L', 0),
        b.flow('drive', *endpoints, request=coefficient(abs(pace), 'L/h')),
        b.flow(
            'meter',
            b.SOURCE,
            b.this.delivery,
            request=b.formula(b.ifelse(compare(b.this.level, b.this.mirror), b.q(1, 'L/h'), b.q(0, 'L/h'))),
        ),
    )
    if family == 'declared':
        builder.entity(
            'provider',
            b.solver(
                'share',
                b.given('drive', plant.drive),
                b.given('meter', plant.meter),
                b.solve_for(b.local.drive.actual_rate),
                b.solve_for(b.local.meter.actual_rate),
            ),
        )
    return builder.finish()


def selection_builder(seed, mode, leaves):
    base, slope, cross, (older, later) = selections._settings(seed)
    drift = selections.selection_drift(base, leaves)

    def q(n, u):
        return b.q(number(n), u)

    builder = b.Builder(UNITS)
    parts = [
        b.input_('origin', 'L', base),
        b.input_('slope', 'L/h', q(slope, 'L/h')),
        b.input_('price', 'L/h', later),
    ]
    if mode == 'rank':
        parts.extend(
            (
                b.value('rank', 'L', b.this.origin),
                b.flow('measure', b.SOURCE, b.this.rank, request=b.this.slope, capacity=b.this.slope),
            )
        )
    else:
        parts.append(b.value('rank', 'L', b.formula(b.this.origin + b.this.slope * b.t)))
    meter = builder.template('Meter', *parts)
    first = builder.member(
        meter,
        'older',
        origin=q(base - drift * cross, 'L'),
        slope=q(slope + drift, 'L/h'),
        price=q(older, 'L/h'),
    )
    last = builder.member(meter, 'later')
    if mode == 'trigger':
        builder.entity(
            'yard',
            b.value('counts', '', 0),
            b.value('fired', 'h', -1),
            b.event(
                'alarm',
                b.when(first.rank >= last.rank, b.start(b.this.alarm), reset=b.reset_when(False)),
                b.after(b.q(0, 'h'), b.add(b.this.counts, 1), b.assign(b.this.fired, b.t)),
            ),
        )
    else:
        rate = (
            b.ifelse(first.rank > last.rank, first.price, last.price)
            if mode == 'clock'
            else meter.instances.by('rank').at(b.q(30, 'L')).price
        )
        builder.entity(
            'yard', b.value('total', 'L', 0), b.flow('meter', b.SOURCE, b.this.total, request=b.formula(rate))
        )
    return builder.finish()


def pairs_switch(seed):
    pairs = []
    settings = switch_inputs(seed)
    for family in switches.WAYS:
        pairs.append(
            (
                f'{family}.{settings[0]}',
                partial(switch_text, settings, family),
                partial(switch_builder, settings, family),
                True,
            )
        )
    for mode in ('clock', 'rank', 'trigger'):
        for leaves in (False, True):
            pairs.append(
                (
                    f'selection.{mode}.{leaves}',
                    partial(text, selections.switch_selection_source(seed, mode, leaves)),
                    partial(selection_builder, seed, mode, leaves),
                    True,
                )
            )
    return pairs


def check_switch(seed):
    check_pairs(seed, pairs_switch(seed))
