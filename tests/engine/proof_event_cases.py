"""Trace evidence for a concrete occurrence, and prove reachability under categorical overrides."""

from dataclasses import replace
from hashlib import sha256
from random import Random
from traceback import format_exc

from napkin.engine import read, run
from napkin.engine.report import Lag, report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text
from napkin.program.config import InputValue
from napkin.program.proofs import Proofs
from napkin.program.reach import reach
from napkin.program.record import Unavailable
from napkin.program.refs import Distribution

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def _expect(errors, name, actual, expected):
    if actual != expected:
        errors[name] = {'expected': expected, 'actual': actual}


def _case(errors, name, source, check):
    observations = {}
    try:
        check(observations)
    except Exception:
        observations['exception'] = format_exc()
    if observations:
        errors[name] = {'sha256': sha256(source.encode()).hexdigest(), 'source': source, **observations}


def _configuration(model, paths, selective):
    cfg = model.configuration
    if selective:
        keys = tuple(key_of(model.program, path) for path in paths)
        cfg = replace(cfg, request=replace(cfg.request, keys=keys, everything=False))
    return cfg


def argument_model(seed):
    rng = Random(seed)
    first, second, factor, delay = (
        (2, 9, 2, 1)
        if seed == 0
        else (rng.randint(1, 7), rng.randint(8, 29), rng.randint(1, 4), rng.randint(1, 3))
    )
    sources = ('first', 'second') if seed % 2 == 0 else ('second', 'first')
    if seed and seed % 5 == 0:
        delay = 0
    # Two concrete occurrences can share a launching statement and even a timestamp.
    # Their captured argument then depends on which caller occurrence launched each.
    relay = seed % 3 == 1
    target = 'relay' if relay else 'job'
    intermediate = (
        '    relay = event(forwarded: L):\n        after 0 h:\n            this.job.start(forwarded)\n'
        if relay
        else ''
    )
    duration = delay + 1
    source = f"""scenario "Occurrence arguments"
    horizon {delay + duration + 1} h
yard:
    input first: L = {first} L @first_read
    input second: L = {second} L @second_read
    input idle_meter: L = 7 L @idle_read
    saved: L = 0 L
    job = event(amount: L):
        derived = formula(amount * {factor})
        after {duration} h
{intermediate}    launch = event():
        after {delay} h:
            this.{target}.start(this.{sources[1]})
    idle = event():
        captured: L = this.idle_meter
        derived = formula(this.idle_meter)
        after 1 h:
            this.saved = this.idle_meter
yard.{target}.start(yard.{sources[0]})
yard.launch.start()
record first_read: source "First independent measurement."
record second_read: source "Second independent measurement."
record idle_read: source "Unused measurement."
"""
    amounts = {'first': first, 'second': second}
    return source, sources, amounts, factor, delay, duration


def _arguments(seed, selective, errors):
    source, sources, amounts, factor, delay, duration = argument_model(seed)
    model = compile_text(source, UNITS)
    paths = [f'yard.job#{i}.{field}' for i in (0, 1) for field in ('amount', 'derived')]
    unused = ['yard.saved', 'yard.idle#0.captured', 'yard.idle#0.derived']
    cfg = _configuration(model, [*paths, *unused], selective)
    program = model.program
    record = run(program, cfg)
    _expect(errors, 'run failure', record.failure, None)
    _expect(errors, 'job starts', tuple(e.t for e in record.entries('start', 'yard.job')), (0, delay))
    _expect(
        errors,
        'job finishes',
        tuple(e.t for e in record.entries('finish', 'yard.job')),
        (duration, delay + duration),
    )
    _expect(errors, 'idle starts', record.entries('start', 'yard.idle'), ())
    proofs = Proofs(program, cfg)
    ids = {'first_read', 'second_read', 'idle_read'}
    for i, origin in enumerate(sources):
        for field, scale in (('amount', 1), ('derived', factor)):
            path = f'yard.job#{i}.{field}'
            try:
                graph = proofs.reads(key_of(program, path))
                _expect(
                    errors,
                    path + '/graph includes argument source',
                    f'yard.{origin}' in {part.origin for part in graph.edges},
                    True,
                )
            except Exception:
                errors[path + '/graph'] = format_exc()
            for label, time in (('active', delay + 0.5), ('finished', delay + duration + 0.5)):
                try:
                    row = report(record, program, cfg, [path], [time], table=model.table).values[0]
                    _expect(errors, f'{path}/{label}/value', row.values, (amounts[origin] * scale,))
                    credits = sorted(
                        {cite for part in row.trail if part.exercised for cite in part.records} & ids
                    )
                    _expect(errors, f'{path}/{label}/credits', credits, [origin + '_read'])
                except Exception:
                    errors[f'{path}/{label}'] = format_exc()
    for path in unused:
        try:
            row = report(record, program, cfg, [path], [delay + duration], table=model.table).values[0]
            actual = row.values[0]
            if '#' in path:
                _expect(errors, path + '/uncreated', isinstance(actual, Unavailable), True)
            else:
                _expect(errors, path + '/untouched', actual, 0)
            exercised = [part.origin for part in row.trail if part.exercised and 'idle_read' in part.records]
            _expect(errors, path + '/unused input', exercised, [])
        except Exception:
            errors[path] = format_exc()


def check_proof_arguments(seed):
    errors = {}
    source = argument_model(seed)[0]
    for selective in (False, True):
        _case(
            errors, 'selective' if selective else 'full', source, lambda obs: _arguments(seed, selective, obs)
        )
    assert not errors, (seed, errors)


def reach_model(seed, override):
    rng = Random(seed)
    start, stock, take = (
        (1, 10, 4) if seed == 0 else (rng.randint(1, 4), rng.randint(10, 23), rng.randint(1, 9))
    )
    weight = 1 if seed == 0 else rng.randint(1, 7)
    send = f'categorical(WAIT: 0, SEND: {weight})'
    wait = f'categorical(WAIT: {weight}, SEND: 0)'
    forecast = ('input ' if override == 'configuration' else '') + 'forecast: distribution(enum[WAIT, SEND])'
    stage = f'        after 0 h:\n            this.forecast = {send}\n' if override == 'stage' else ''
    dormant = (
        f'    unused = event():\n        after 0 h:\n            this.forecast = {send}\n'
        if override == 'dormant'
        else ''
    )
    member = f'\n    forecast = {send}' if override == 'member' else ''
    source = f"""scenario "Certain dispatch"
    horizon {start + 2} h
Depot:
    {forecast} = {wait}
    stock: L = {stock} L in [0 L,]
    moved: L = 0 L in [0 L,]
    waits = 0
    choose = event():
        order: enum[WAIT, SEND] = WAIT
{stage}        after {start} h:
            order = this.forecast.draw()
            switch order:
                SEND:
                    this.dispatch.start()
                WAIT:
                    this.waits += 1
{dormant}    dispatch = event():
        after 0 h:
            move {take} L from this.stock to this.moved
yard: Depot{member}
yard.choose.start()
"""
    return source, start, stock, take, weight


def _reach(seed, override, selective, errors):
    source, start, stock, take, weight = reach_model(seed, override)
    model = compile_text(source, UNITS)
    program = model.program
    paths = ['yard.stock', 'yard.moved', 'yard.waits']
    cfg = _configuration(model, paths, selective)
    if override == 'configuration':
        distribution = Distribution(
            'categorical', (0, weight), enum='enum[WAIT, SEND]', outcomes=('WAIT', 'SEND')
        )
        cfg = replace(cfg, inputs=(InputValue('yard', 'forecast', distribution),))
    sends = override in ('member', 'stage', 'configuration')
    record = run(program, cfg)
    _expect(errors, 'run failure', record.failure, None)
    _expect(
        errors,
        'dispatch starts',
        tuple(e.t for e in record.entries('start', 'Depot.dispatch')),
        (start,) if sends else (),
    )
    times = (0, start + 1)
    values = [(stock, stock - take), (0, take), (0, 0)] if sends else [(stock, stock), (0, 0), (0, 1)]
    for row, expected in zip(read(record, program, paths, times), values, strict=True):
        _expect(errors, f'{row.path}/record', row.values, expected)
    proofs = Proofs(program, cfg)
    can_start, reason = reach(program, cfg).events['Depot.dispatch']
    if can_start != sends:
        errors['dispatch can start'] = {'expected': sends, 'actual': can_start, 'reason': reason}
    for path, monotone in (('yard.stock', not sends), ('yard.moved', True)):
        try:
            key = key_of(program, path)
            proof = proofs.never_falls(key)
            if proof.holds != monotone:
                errors[path + '/never falls'] = {
                    'expected': monotone,
                    'actual': proof.holds,
                    'reason': proof.reason,
                }
            graph = proofs.reads(key)
            _expect(
                errors, path + '/dispatch in graph', 'Depot.dispatch' in {p.origin for p in graph.edges}, True
            )
            _expect(
                errors,
                path + '/dispatch blocked',
                'Depot.dispatch' in {p.origin for p in graph.blocked},
                not sends,
            )
            row = report(record, program, cfg, [path], [start + 1], table=model.table).values[0]
            dispatch = [
                part for part in row.trail if part.kind == 'event' and part.origin == 'Depot.dispatch'
            ]
            _expect(errors, path + '/dispatch exercised', [p.exercised for p in dispatch], [sends])
            lag = Lag(1, 1)
            row = report(record, program, cfg, [path], [start + 1], {path: lag}, table=model.table).values[0]
            if (row.lag is not None) != monotone:
                errors[path + '/lag'] = {'expected': monotone, 'actual': row.lag, 'reason': row.note}
        except Exception:
            errors[path] = format_exc()


def check_proof_reach(seed):
    errors = {}
    for override in ('member', 'stage', 'configuration', 'none', 'dormant'):
        source = reach_model(seed, override)[0]
        _case(errors, override, source, lambda obs: _reach(seed, override, bool(seed % 2), obs))
    assert not errors, (seed, errors)
