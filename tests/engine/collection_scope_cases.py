"""A filter uses its member on the left, and the event, trigger or solver scope on the right."""

from dataclasses import dataclass
from random import Random

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program import artifact
from napkin.program import build as b
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
CONFIG = Configuration(Request(1))
ANSWER = Key('yard', ('answer',))
SITE_MODES = ('parameter', 'unshadowed', 'member-left', 'event-local', 'trigger-capture', 'solver-input')


@dataclass(frozen=True)
class Data:
    ranks: tuple
    weights: tuple
    rates: tuple
    east: int
    garden: int
    increment: int
    reverse: bool


def data_for(seed):
    if seed == 0:
        return Data((1, 2), (3, 8), (1, 2), 2, 7, 5, False)
    rng = Random(seed)
    return Data(
        tuple(rng.sample(range(1, 18), 2)),
        tuple(rng.sample(range(1, 51), 2)),
        tuple(rng.sample(range(1, 15), 2)),
        rng.randrange(1, 25),
        rng.randrange(31, 61),
        rng.randrange(1, 11),
        bool(seed % 2),
    )


def sites(data, mode):
    """Each row has a distinct rank, so only the weight of the argument's site can contribute."""
    a, z = data.ranks
    lexical = {'unshadowed': 'chosen', 'member-left': 'dest'}.get(mode, 'pick')
    builder = b.Builder(UNITS)
    group = builder.template('Site', b.input_('dest', '', 0), b.input_('weight', '', 0))
    builder.root(b.value('pick', '', a))
    lines = [f'pick = {a}', 'Site:', '    input dest = 0', '    input weight = 0']
    for index in ((1, 0) if data.reverse else (0, 1)):
        name = ('first', 'second')[index]
        rank, weight = data.ranks[index], data.weights[index]
        lines += [f'{name}: Site', f'    dest = {rank}', f'    weight = {weight}']
        builder.member(group, name, dest=rank, weight=weight)
    lines += ['yard:', f'    choice = {z}']
    fields = [b.value('choice', '', z)]
    solver = mode == 'solver-input'
    collection = b.local.sites if solver else group.instances
    operand = getattr(b.local, lexical)
    selected = b.fsum(collection.where(b.item.dest == operand).weight)
    source = ('sites' if solver else 'Site.instances') + f'.where(dest == {lexical})'
    total = f'sum({source}.weight)'
    if solver:
        lines += [
            '    measure = solver:',
            '        inputs:',
            '            pick = this.choice',
            '            sites = Site.instances',
            '        solve_for:',
            '            total: number in [0, 100]',
            '        constraints:',
            f'            total == {total}',
            '        objective:',
            '            maximize(total)',
        ]
        fields.append(
            b.solver(
                'measure',
                b.given('pick', b.this.choice),
                b.given('sites', group.instances),
                b.unknown('total', '', lower=0, upper=100),
                b.constraint(b.local.total == selected),
                b.maximize(b.local.total),
            )
        )
        keys = [Key('yard', ('measure', 'total'))]
    else:
        lines.append('    answer = 0')
        fields.append(b.value('answer', '', 0))
        keys = [ANSWER]
        if mode == 'trigger-capture':
            lines += [
                '    inspect = event(total: number):',
                '        when this.choice > 0:',
                '            pick = this.choice',
                f'            this.inspect.start({total})',
                '            reset when false',
                '        after 0.25 h:',
                '            this.answer = total',
            ]
            fields.append(
                b.event(
                    'inspect',
                    b.param('total', ''),
                    b.when(
                        b.this.choice > 0,
                        b.start(b.this.inspect, selected),
                        captures=(b.value('pick', '', b.this.choice),),
                        reset=b.reset_when(False),
                    ),
                    b.after(b.q(0.25, 'h'), b.assign(b.this.answer, b.local.total)),
                )
            )
        else:
            parts, args = [], []
            if mode == 'event-local':
                lines += ['    inspect = event():', '        pick = this.choice']
                parts.append(b.value('pick', '', b.this.choice))
            else:
                lines.append(f'    inspect = event({lexical}: number):')
                parts.append(b.param(lexical, ''))
                args.append(z)
            lines += [
                '        after 0.25 h:',
                f'            this.answer = {total}',
                f'yard.inspect.start({", ".join(map(str, args))})',
            ]
            parts.append(b.after(b.q(0.25, 'h'), b.assign(b.this.answer, selected)))
            fields.append(b.event('inspect', *parts))
            builder.setup(b.start(b.named('yard').inspect, *args))
    builder.entity('yard', *fields)
    return '\n'.join(lines) + '\n', {}, builder, keys, (data.weights[1],)


def flows(data, shadow):
    """The two sink stores differ in identity and the permanent flows request distinct rates."""
    lexical = 'pick' if shadow else 'chosen'
    first, second = data.rates
    source = f"""Site:
    water: L = 0 L in [0,]
pick: Site
garden: Site
yard:
    stock: L = 100 L in [0,]
    answer: L/h = 0 L/h
    flow base: this.stock -> pick.water
        request = {first} L/h
    flow extra: this.stock -> garden.water
        request = {second} L/h
    inspect = event({lexical}: Site):
        after 0.25 h:
            this.answer = sum(this.stock.outflow.flows.where(sink == {lexical}.water).actual_rate)
yard.inspect.start(garden)
"""
    builder = b.Builder(UNITS)
    site = builder.template('Site', b.value('water', 'L', 0, lower=0))
    pick = builder.member(site, 'pick')
    garden = builder.member(site, 'garden')
    selected = b.this.stock.outflow.flows.where(b.item.sink == getattr(b.local, lexical).water)
    yard = builder.entity(
        'yard',
        b.value('stock', 'L', 100, lower=0),
        b.value('answer', 'L/h', 0),
        b.flow('base', b.this.stock, pick.water, request=b.q(first, 'L/h')),
        b.flow('extra', b.this.stock, garden.water, request=b.q(second, 'L/h')),
        b.event(
            'inspect',
            b.param(lexical, b.ref_to('Site')),
            b.after(b.q(0.25, 'h'), b.assign(b.this.answer, b.fsum(selected.actual_rate))),
        ),
    )
    builder.setup(b.start(yard.inspect, garden))
    return source, {}, builder, [ANSWER], (second,)


def dotted(data, table):
    """Rename only the global table; both the read and the update must still use the argument."""
    source = f"""Station:
    reading = 0
{table}: Station from "stations.csv"
garden: Station
    reading = {data.garden}
Region:
    east: Station
district: Region
    east = garden
yard:
    answer = 0
    inspect = event(stations: Region):
        after 0.25 h:
            this.answer = stations.east.reading
            stations.east.reading += {data.increment}
yard.inspect.start(district)
"""
    tables = {'stations.csv': f'id,reading\neast,{data.east}\n'}
    builder = b.Builder(UNITS)
    station = builder.template('Station', b.value('reading', '', 0))
    builder.table(table, station, [{'id': 'east', 'reading': data.east}])
    garden = builder.member(station, 'garden', reading=data.garden)
    region = builder.template('Region', b.link('east', 'Station'))
    district = builder.member(region, 'district', east=garden)
    target = b.local.stations.east.reading
    yard = builder.entity(
        'yard',
        b.value('answer', '', 0),
        b.event(
            'inspect',
            b.param('stations', b.ref_to('Region')),
            b.after(b.q(0.25, 'h'), b.assign(b.this.answer, target), b.add(target, data.increment)),
        ),
    )
    builder.setup(b.start(yard.inspect, district))
    keys = [ANSWER, Key(f'{table}.east', ('reading',)), Key('garden', ('reading',))]
    return source, tables, builder, keys, (data.garden, data.east, data.garden + data.increment)


def _compare(errors, label, evaluate, expected):
    try:
        observed = evaluate()
    except Exception as exc:
        errors[label] = f'{type(exc).__name__}: {exc}'
    else:
        if observed != expected:
            errors[label] = {'expected': expected, 'observed': tuple(map(str, observed))}


def _values(program, keys):
    record = run(program, CONFIG)
    if record.failure is not None:
        raise ValueError(record.failure)
    return tuple(series.values[0] for series in read(record, program, keys, (1,)))


def _reference(program, keys):
    reference, failure = run_of(program, CONFIG)
    if failure is not None:
        raise ValueError(failure)
    values = values_at(reference, program, keys, (1,))
    return tuple(values[key][0] for key in keys)


def check_collection_scope(seed):
    data = data_for(seed)
    modes = SITE_MODES if not seed else (SITE_MODES[(seed - 1) % len(SITE_MODES)],)
    cases = [(mode, sites(data, mode)) for mode in modes]
    cases += [('flow-shadow', flows(data, True)), ('flow-renamed', flows(data, False))]
    cases += [('dotted-shadow', dotted(data, 'stations')), ('dotted-renamed', dotted(data, 'roster'))]
    differences = {}
    for mode, (source, tables, builder, keys, expected) in cases:
        errors, programs = {}, {}
        try:
            model = compile_text(source, UNITS, tables=tables)
        except Exception as exc:
            errors['text-compile'] = f'{type(exc).__name__}: {exc}'
        else:
            programs['text'] = model.program
            if mode.startswith('dotted'):
                try:
                    programs['artifact'] = artifact.loads(model.artifact().data()).program
                except Exception as exc:
                    errors['artifact-load'] = f'{type(exc).__name__}: {exc}'
        try:
            programs['builder'] = builder.finish()
        except Exception as exc:
            errors['builder-check'] = f'{type(exc).__name__}: {exc}'
        for form, program in programs.items():
            _compare(errors, form, lambda: _values(program, keys), expected)
            if form != 'artifact':
                _compare(errors, form + '-reference', lambda: _reference(program, keys), expected)
        if errors:
            differences[mode] = {'source': source, 'tables': tables, **errors}
    assert not differences, (seed, 'collection-scope', differences)
