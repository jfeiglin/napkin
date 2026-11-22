"""Analytic collection membership, creation order and filters over a changing enclosing value."""

from dataclasses import dataclass, replace
from fractions import Fraction as F
from hashlib import sha256
from math import isclose
from random import Random

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program import build as b
from napkin.program.record import Key
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
RESULT = Key('', ('observed',))


@dataclass(frozen=True)
class Probe:
    name: str
    text: str
    node: object
    unit: str
    answers: tuple


def _member(seed):
    weights = (3, 5, 9) if seed == 0 else tuple(Random(seed).sample(range(1, 55), 3))
    r = 1 + seed % 7
    members = ('first', 'middle', 'last')
    base = f"""scenario "Member creation keys"
    horizon 2 h
Entry:
    input rank: number = {r}
    input amount: number = 0
    input keep = true
"""
    for i, (name, amount) in enumerate(zip(members, weights, strict=True)):
        base += f'{name}: Entry\n    amount = {amount}\n'
        if i == 1:
            base += '    keep = false\n'
    natural = b.TemplateHandle('Entry').instances
    literal = b.literal(*(b.named(name) for name in reversed(members)))
    kept = literal.where(b.item.keep)
    spelling = '<last, middle, first>.where(keep)'
    a, _, c = weights
    for name, expr, node, number in (
        ('first', 'Entry.instances.at(0).amount', natural.at(0).amount, a),
        ('natural', f'{spelling}.at(2).amount', kept.at(2).amount, c),
        ('tie', f'{spelling}.by(rank).at({r}).amount', kept.by('rank').at(r).amount, c),
        ('count', f'count({spelling})', b.count(kept), 2),
        ('sum', f'sum({spelling}.amount)', b.fsum(kept.amount), a + c),
        ('minimum', f'min({spelling}.amount)', b.fmin(kept.amount), min(a, c)),
        ('maximum', f'max({spelling}.amount)', b.fmax(kept.amount), max(a, c)),
        ('any', 'any(Entry.instances.keep)', b.fany(natural.keep), True),
        ('all', 'all(Entry.instances.keep)', b.fall(natural.keep), False),
    ):
        yield (
            base,
            Probe('member.' + name, expr, node, 'bool' if type(number) is bool else '', (number, number)),
        )


def _flow(seed, life):
    base_rate, temp_rate = (1, 2) if seed == 0 else Random(seed).sample(range(1, 16), 2)
    cap = max(base_rate, temp_rate) + 1
    base = f"""scenario "Active flow keys"
    horizon 2 h
yard:
    stock: L = 100 L in [0,]
    flow base: this.stock -> SINK
        request = {base_rate} L/h
        capacity = {cap} L/h
    extra = event():
        flow pipe: this.stock -> SINK
            request = {temp_rate} L/h
            capacity = {cap} L/h
        after {float(life)} h
yard.extra.start()
"""
    yard = b.named('yard')
    collection = yard.stock.outflow.flows
    selected = collection.where(b.item.source == yard.stock)
    natural = 'yard.stock.outflow.flows'
    kept = natural + '.where(source == yard.stock)'
    for name, text, node, unit, active, ended in (
        ('first', natural + '.at(0).actual_rate', collection.at(0).actual_rate, 'L/h', base_rate, base_rate),
        (
            'latest',
            natural + '.at(999).actual_rate',
            collection.at(999).actual_rate,
            'L/h',
            temp_rate,
            base_rate,
        ),
        (
            'where-at',
            kept + '.at(999).actual_rate',
            selected.at(999).actual_rate,
            'L/h',
            temp_rate,
            base_rate,
        ),
        (
            'tie',
            natural + f'.by(capacity).at({cap} L/h).actual_rate',
            collection.by('capacity').at(b.q(cap, 'L/h')).actual_rate,
            'L/h',
            temp_rate,
            base_rate,
        ),
        ('count', f'count({kept})', b.count(selected), '', 2, 1),
        (
            'sum',
            f'sum({kept}.actual_rate)',
            b.fsum(selected.actual_rate),
            'L/h',
            base_rate + temp_rate,
            base_rate,
        ),
    ):
        yield base, Probe('flow.' + name, text, node, unit, (active, ended))


def _projected_flow(seed):
    first = 1 if seed == 0 else Random(seed).randint(1, 8)
    second = first + 1 + seed % 5
    base = f"""scenario "Keys of projected pipes"
    horizon 2 h
Pump:
    input rank: number = 2
    input desired: L/h = {first} L/h
    water: L = 0 L
    flow pipe: SOURCE -> this.water
        request = this.desired
left: Pump
right: Pump
    rank = 1
    desired = {second} L/h
"""
    pumps = b.TemplateHandle('Pump').instances
    projected = pumps.pipe
    for name, text, node, expected in (
        (
            'where',
            'sum(Pump.instances.pipe.where(sink == right.water).actual_rate)',
            b.fsum(projected.where(b.item.sink == b.named('right').water).actual_rate),
            second,
        ),
        (
            'by-flow',
            f'Pump.instances.pipe.by(request).at({first} L/h).actual_rate',
            projected.by('request').at(b.q(first, 'L/h')).actual_rate,
            first,
        ),
        (
            'by-member',
            'Pump.instances.by(rank).pipe.at(1).actual_rate',
            pumps.by('rank').pipe.at(1).actual_rate,
            second,
        ),
    ):
        yield base, Probe('projected-flow.' + name, text, node, 'L/h', (expected, expected))


def _occurrence(seed, life):
    a, c, later = (2, 7, 11) if not seed else Random(seed).sample(range(1, 55), 3)
    include = seed % 2 == 0
    rank = 1 + seed % 9
    base = f"""scenario "Occurrence filters and keys"
    horizon 2 h
yard:
    cursor: h = {float(life / 4)} h
    visit = event(amount: number, rank: number, keep: bool):
        after {float(life)} h
    launch = event():
        after {float(life)} h:
            this.visit.start({later}, {rank}, {str(include).lower()})
yard.visit.start({a}, {rank}, true)
yard.visit.start({c}, {rank}, true)
yard.launch.start()
"""
    y = b.named('yard')
    all_visits = y.visit.occurrences
    kept = all_visits.where(b.item.keep)
    natural = 'yard.visit.occurrences'
    filtered = natural + '.where(keep)'
    newest = later if include else c
    for name, text, node, active, past in (
        ('latest', natural + '.at(t).amount', all_visits.at(b.t).amount, c, later),
        ('fixed', natural + '.at(0 h).amount', all_visits.at(b.q(0, 'h')).amount, c, c),
        ('stored-time', natural + '.at(yard.cursor).amount', all_visits.at(y.cursor).amount, c, c),
        ('where-at', filtered + '.at(t).amount', kept.at(b.t).amount, c, newest),
        ('where-by', filtered + f'.by(rank).at({rank}).amount', kept.by('rank').at(rank).amount, c, newest),
        ('by', natural + f'.by(rank).at({rank}).amount', all_visits.by('rank').at(rank).amount, c, later),
        ('count', f'count({filtered})', b.count(kept), 2, 2 + int(include)),
        ('sum', f'sum({filtered}.amount)', b.fsum(kept.amount), a + c, a + c + (later if include else 0)),
        ('active', f'count({natural}.active)', b.count(all_visits.active), 2, 1),
    ):
        yield base, Probe('occurrence.' + name, text, node, '', (active, past))


def _run(program, config, expectations, times, *, reverse=False, continuous=False):
    """Report run, reference and read-order results independently, including a failed lookup."""
    errors = {}
    for reference in (False, True):
        who = 'reference' if reference else 'engine'
        try:
            if reference:
                result, failure = run_of(program, config)
            else:
                if continuous:
                    machine = Run(Plan.of(program, config))
                    result = machine.run()
                    actual = type(machine.ways.instance_of('yard.fill')).__name__
                    if actual != 'Sparse':
                        errors['method'] = actual, 'Sparse'
                else:
                    result = run(program, config)
                failure = result.failure
            if failure:
                errors[who] = {'stop': str(failure)}
                continue
        except NotCovered as error:
            if reference:
                continue
            errors[who] = str(error)
            continue
        except Exception as error:
            errors[who] = f'{type(error).__name__}: {error}'
            continue
        for backward in (False, True) if reverse else (False,):
            ordered = times[::-1] if backward else times
            for key, hand in expectations.items():
                label = f'{who}.{key}.' + ('backward' if backward else 'forward')
                try:
                    if reference:
                        rows = values_at(result, program, [key], ordered)[key]
                    else:
                        rows = read(result, program, [key], list(map(float, ordered)))[0].values
                    expected = hand[::-1] if backward else hand
                    close = tuple(rows) == tuple(expected)
                    if continuous and not reference:
                        close = all(
                            isclose(a, b, rel_tol=1e-9, abs_tol=2e-8)
                            for a, b in zip(rows, expected, strict=True)
                        )
                    if not close:
                        errors[label] = tuple(map(str, rows)), tuple(map(str, expected))
                except NotCovered as error:
                    if not reference:
                        errors[label] = str(error)
                except Exception as error:
                    errors[label] = f'{type(error).__name__}: {error}'
    return errors


def check_collection_kind(seed):
    """A rejected text spelling cannot mask a lower-level failure of the same structured Program."""
    life = F(1) if not seed else F(Random(seed).randint(6, 10), 8)
    times = life / 2, (life + min(2 * life, 2)) / 2
    differences = {}
    for probes in (_member(seed), _flow(seed, life), _occurrence(seed, life), _projected_flow(seed)):
        basic = None
        for base, case in probes:
            source = base + f'observed = formula({case.text})\n'
            expected = {RESULT: case.answers}
            failures = {}
            try:
                compiled = compile_text(source, UNITS)
            except Exception as error:
                failures['text'] = f'{type(error).__name__}: {error}'
                try:
                    if basic is None:
                        basic = compile_text(base, UNITS)
                    field = b.value(
                        'observed', b.BOOL if case.unit == 'bool' else case.unit, b.formula(case.node)
                    )
                    direct = replace(basic.program, root=(*basic.program.root, field))
                    failures.update(_run(direct, basic.configuration, expected, times))
                except Exception as problem:
                    failures['program'] = f'{type(problem).__name__}: {problem}'
            else:
                failures.update(_run(compiled.program, compiled.configuration, expected, times))
            if failures:
                differences[case.name] = {
                    'source_sha256': sha256(source.encode()).hexdigest(),
                    'source': source,
                    **failures,
                }
    assert not differences, (seed, 'collection-kind', differences)


def check_filter_history(seed):
    rng = Random(seed)
    ranks = (1, 2) if not seed else tuple(rng.sample(range(1, 24), rng.randint(2, 5)))
    at = F(1) if not seed else F(rng.randint(4, 12), 8)
    fixed = seed % 11 == 10
    threshold = 0 if fixed else max(ranks)
    members = ''.join(f'site{i}: Site\n    rank = {rank}\n' for i, rank in enumerate(ranks))
    source = f"""scenario "Changing filter threshold"
    horizon 2 h
Site:
    input rank: number = 0
{members}yard:
    threshold: number = 0
    result: number = 0
    eligible = formula(count(Site.instances.where(rank >= this.threshold)))
    change = event():
        after {float(at)} h:
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
    after = len(ranks) if fixed else 1
    marked = 0 if fixed else 11
    expected = {
        Key('yard', ('eligible',)): (len(ranks), after, after),
        Key('yard', ('result',)): (0, marked, marked),
    }
    weights = tuple(range(1, len(ranks) + 1))
    sites = ''.join(
        f'site{i}: Site\n    rank = {rank}\n    priority = {max(ranks) - rank}\n    weight = {weight} L/h\n'
        for i, (rank, weight) in enumerate(zip(ranks, weights, strict=True))
    )
    stream = f"""scenario "A changing filter feeds a stock"
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
        after {float(at)} h:
            this.threshold = {threshold}
yard.change.start()
"""
    high = weights[ranks.index(max(ranks))]
    low = weights[ranks.index(min(ranks))]
    old, new = sum(weights), sum(weights) if fixed else high
    times = (F(0), at / 2, (at + 2) / 2, F(2))
    flow_answers = {
        Key('yard', ('stock',)): tuple(min(t, at) * old + max(t - at, 0) * new for t in times),
        Key('yard', ('fill', 'actual_rate')): (old, old, new, new),
        Key('yard', ('winner',)): (low, low, low if fixed else high, low if fixed else high),
    }
    failures = {}
    for label, model_text, outputs, hours in (
        ('trigger-and-wait', source, expected, (F(0), at, F(2))),
        ('flow-and-key', stream, flow_answers, times),
    ):
        try:
            model = compile_text(model_text, UNITS)
            differences = _run(
                model.program,
                model.configuration,
                outputs,
                hours,
                reverse=True,
                continuous=label == 'flow-and-key',
            )
        except Exception as error:
            differences = {'text': f'{type(error).__name__}: {error}'}
        if differences:
            failures[label] = {
                'source_sha256': sha256(model_text.encode()).hexdigest(),
                'source': model_text,
                **differences,
            }
    assert not failures, (seed, 'filter-history', failures)
