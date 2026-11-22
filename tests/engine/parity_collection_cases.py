"""Text/builder parity for collection projections, lexical scopes, and changing filters."""

from fractions import Fraction
from random import Random

from napkin.model.compile import compile_text
from napkin.program import build as b
from tests.engine import collection_kind_cases as kinds
from tests.engine import collection_scope_cases as scopes
from tests.engine.program_parity import check_pairs

UNITS = kinds.UNITS


def _members(seed):
    weights = (3, 5, 9) if seed == 0 else Random(seed).sample(range(1, 55), 3)
    builder = b.Builder(UNITS)
    entry = builder.template(
        'Entry', b.input_('rank', '', 1 + seed % 7), b.input_('amount', '', 0), b.input_('keep', b.BOOL, True)
    )
    for name, weight in zip(('first', 'middle', 'last'), weights, strict=True):
        overrides = {'keep': False} if name == 'middle' else {}
        builder.member(entry, name, amount=weight, **overrides)
    return builder


def _flows(seed, life):
    base, extra = (1, 2) if seed == 0 else Random(seed).sample(range(1, 16), 2)
    capacity = b.q(max(base, extra) + 1, 'L/h')
    builder = b.Builder(UNITS)
    builder.entity(
        'yard',
        b.value('stock', 'L', 100, lower=0),
        b.flow('base', b.this.stock, b.SINK, request=b.q(base, 'L/h'), capacity=capacity),
        b.event(
            'extra',
            b.flow('pipe', b.this.stock, b.SINK, request=b.q(extra, 'L/h'), capacity=capacity),
            b.after(b.q(float(life), 'h')),
        ),
    )
    builder.setup(b.start(b.named('yard').extra))
    return builder


def _projected(seed):
    first = 1 if seed == 0 else Random(seed).randint(1, 8)
    second = first + 1 + seed % 5
    builder = b.Builder(UNITS)
    pump = builder.template(
        'Pump',
        b.input_('rank', '', 2),
        b.input_('desired', 'L/h', first),
        b.value('water', 'L', 0),
        b.flow('pipe', b.SOURCE, b.this.water, request=b.this.desired),
    )
    builder.member(pump, 'left')
    builder.member(pump, 'right', rank=1, desired=b.q(second, 'L/h'))
    return builder


def _occurrences(seed, life):
    a, c, later = (2, 7, 11) if seed == 0 else Random(seed).sample(range(1, 55), 3)
    rank, keep = 1 + seed % 9, seed % 2 == 0
    wait = b.q(float(life), 'h')
    builder = b.Builder(UNITS)
    yard = builder.entity(
        'yard',
        b.value('cursor', 'h', float(life / 4)),
        b.event('visit', b.param('amount', ''), b.param('rank', ''), b.param('keep', b.BOOL), b.after(wait)),
        b.event('launch', b.after(wait, b.start(b.this.visit, later, rank, keep))),
    )
    builder.setup(
        b.start(yard.visit, a, rank, True), b.start(yard.visit, c, rank, True), b.start(yard.launch)
    )
    return builder


def _observed(make_base, probe):
    builder = make_base()
    builder.root(b.value('observed', b.BOOL if probe.unit == 'bool' else probe.unit, b.formula(probe.node)))
    return builder.finish()


def kind_pairs(seed):
    life = Fraction(1) if not seed else Fraction(Random(seed).randint(6, 10), 8)
    groups = [
        (kinds._member(seed), lambda: _members(seed)),
        (kinds._flow(seed, life), lambda: _flows(seed, life)),
        (kinds._occurrence(seed, life), lambda: _occurrences(seed, life)),
        (kinds._projected_flow(seed), lambda: _projected(seed)),
    ]
    for probes, base in groups:
        for text, probe in probes:
            source = text + f'observed = formula({probe.text})\n'
            yield (
                probe.name,
                lambda s=source: compile_text(s, UNITS).program,
                lambda p=probe, make=base: _observed(make, p),
                True,
            )


def scope_pairs(seed):
    data = scopes.data_for(seed)
    modes = scopes.SITE_MODES if not seed else (scopes.SITE_MODES[(seed - 1) % len(scopes.SITE_MODES)],)
    cases = [(mode, scopes.sites(data, mode)) for mode in modes]
    cases.extend(
        (name, scopes.flows(data, shadow))
        for name, shadow in (('flow-shadow', True), ('flow-renamed', False))
    )
    cases.extend(
        (name, scopes.dotted(data, table))
        for name, table in (('dotted-shadow', 'stations'), ('dotted-renamed', 'roster'))
    )
    for mode, (source, tables, builder, _, _) in cases:
        yield mode, lambda s=source, t=tables: compile_text(s, UNITS, tables=t).program, builder.finish, True


def filter_inputs(seed):
    rng = Random(seed)
    ranks = (1, 2) if seed == 0 else tuple(rng.sample(range(1, 24), rng.randint(2, 5)))
    time = 1.0 if seed == 0 else float(Fraction(rng.randint(4, 12), 8))
    threshold = 0 if seed % 11 == 10 else max(ranks)
    return ranks, time, threshold


def filter_text(ranks, at, threshold, stream):
    members = ''.join(f'site{i}: Site\n    rank = {rank}\n' for i, rank in enumerate(ranks))
    if not stream:
        return f"""scenario "Changing filter threshold"
    horizon 2 h
Site:
    input rank: number = 0
{members}yard:
    threshold: number = 0
    result: number = 0
    eligible = formula(count(Site.instances.where(rank >= this.threshold)))
    change = event():
        after {at} h:
            this.threshold = {threshold}
    alarm = event():
        when this.eligible == 1:
            this.alarm.start()
        after 0 h:
            this.result += 1
    wait = event():
        until this.eligible == 1
        after 0 h:
            this.result += 10
yard.change.start()
yard.wait.start()
"""
    sites = ''.join(
        f'site{i}: Site\n    rank = {rank}\n    priority = {max(ranks) - rank}\n    weight = {i + 1} L/h\n'
        for i, rank in enumerate(ranks)
    )
    return f"""scenario "A changing filter feeds a stock"
    horizon 2 h
Site:
    input rank: number = 0
    input priority: number = 0
    input weight: L/h = 1 L/h
{sites}yard:
    threshold: number = 0
    stock: L = 0 L
        inflow.capacity = 100 L/h
    winner = formula(Site.instances.where(rank >= this.threshold).by(priority).at(999).weight)
    flow fill: SOURCE -> this.stock
        request = formula(sum(Site.instances.where(rank >= this.threshold).weight))
        capacity = formula((100 + t / (1 h)) * (1 L/h))
    change = event():
        after {at} h:
            this.threshold = {threshold}
yard.change.start()
"""


def _filter_program(ranks, at, threshold, stream):
    builder = b.Builder(UNITS)
    fields = [b.input_('rank', '', 0)]
    if stream:
        fields.extend([b.input_('priority', '', 0), b.input_('weight', 'L/h', 1)])
    site = builder.template('Site', *fields)
    for i, rank in enumerate(ranks):
        overrides = dict(priority=max(ranks) - rank, weight=b.q(i + 1, 'L/h')) if stream else {}
        builder.member(site, f'site{i}', rank=rank, **overrides)
    subset = site.instances.where(b.item.rank >= b.this.threshold)
    change = b.event('change', b.after(b.q(at, 'h'), b.assign(b.this.threshold, threshold)))
    fields = [b.value('threshold', '', 0)]
    if stream:
        fields.extend(
            [
                b.value('stock', 'L', 0, inflow=b.endpoint(capacity=b.q(100, 'L/h'))),
                b.value('winner', 'L/h', b.formula(subset.by('priority').at(999).weight)),
                b.flow(
                    'fill',
                    b.SOURCE,
                    b.this.stock,
                    request=b.formula(b.fsum(subset.weight)),
                    capacity=b.formula((100 + b.t / b.q(1, 'h')) * b.q(1, 'L/h')),
                ),
                change,
            ]
        )
    else:
        eligible = b.this.eligible == 1
        zero = b.q(0, 'h')
        fields.extend(
            [
                b.value('result', '', 0),
                b.value('eligible', '', b.formula(b.count(subset))),
                change,
                b.event(
                    'alarm', b.when(eligible, b.start(b.this.alarm)), b.after(zero, b.add(b.this.result, 1))
                ),
                b.event('wait', b.until(eligible), b.after(zero, b.add(b.this.result, 10))),
            ]
        )
    yard = builder.entity('yard', *fields)
    builder.setup(b.start(yard.change))
    if not stream:
        builder.setup(b.start(yard.wait))
    return builder.finish()


def filter_pairs(seed):
    inputs = filter_inputs(seed)
    for label, stream in (('trigger-and-wait', False), ('flow-and-key', True)):
        yield (
            label,
            lambda s=stream: compile_text(filter_text(*inputs, s), UNITS).program,
            lambda s=stream: _filter_program(*inputs, s),
            True,
        )


def check_collection_kind_parity(seed):
    check_pairs(seed, kind_pairs(seed))


def check_collection_scope_parity(seed):
    check_pairs(seed, scope_pairs(seed))


def check_filter_history_parity(seed):
    check_pairs(seed, filter_pairs(seed))
