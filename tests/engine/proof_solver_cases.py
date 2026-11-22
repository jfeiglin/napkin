"""Physical solver writes, their dependencies, and citations through an identity formula."""

from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
from random import Random

from napkin.engine import read, run
from napkin.engine.report import report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text
from napkin.program.artifact import loads
from napkin.program.proofs import Proofs

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}, 'mL': ({'volume': 1}, Fraction(1, 1000))}


def solver_cases(seed):
    rng = Random(seed)
    limit = 3 if seed == 0 else rng.randint(1, 42)
    spare = limit + rng.randint(2, 10)
    hi = spare + 5
    unit, factor = ('mL', 1000) if seed % 2 else ('L', 1)
    a, cap = ('chosen', 'bound') if seed % 3 else ('target', 'cap')
    foot = 'record measurement: source "Measured limit."\nrecord other: source "Independent reading."\n'
    for alias in (True, False):
        dest = a if alias else 'this.value'
        body = f"""scenario "Solver writes and evidence"
    horizon 1 h
box:
    input meter: {unit} = {limit * factor} {unit} @measurement
    input spare: L = {spare} L @other
    value: L = 0 L in [0 L, {hi} L]
    observed = formula(this.value)
    result = formula(this.plan.quantity)
    plan = solver:
        inputs:
            {a} = this.value
            {cap} = this.meter
            unused = this.spare
        solve_for:
            {dest}
            quantity: L in [0 L, {hi} L]
        constraints:
            {a} == {cap}
            quantity == {cap}
"""
        paths = dict.fromkeys(('box.value', 'box.observed', 'box.plan.quantity', 'box.result'), limit)
        yield 'stored.alias' if alias else 'stored.qualified', body + foot, paths, spare

    body = f"""scenario "Solver sets a flow through an input alias"
    horizon 1 h
box:
    input meter: {unit}/h = {limit * factor} {unit}/h @measurement
    input spare: L/h = {spare} L/h @other
    stock: L = 0 L
    flow feed: SOURCE -> this.stock
        request = {hi} L/h
    rate = formula(this.feed.actual_rate)
    plan = solver:
        inputs:
            {a} = this.feed
            {cap} = this.meter
            unused = this.spare
        solve_for:
            {a}.actual_rate
        constraints:
            {a}.actual_rate <= {cap}
        objective:
            maximize({a}.actual_rate)
"""
    yield (
        'flow.alias',
        body + foot,
        {**dict.fromkeys(('box.feed.actual_rate', 'box.rate'), limit), 'box.feed.request': hi},
        spare,
    )


def check_proof_solver(seed):
    failures = {}
    for name, source, physical, spare in solver_cases(seed):
        errors = {}
        try:
            model = compile_text(source, UNITS)
            artifact = loads(model.artifact().data())
            expected = {**physical, 'box.spare': spare}
            keys = {p: key_of(artifact.program, p) for p in expected}
            for mode in ('full', 'selective'):
                request = model.configuration.request
                if mode == 'selective':
                    request = replace(request, everything=False, keys=tuple(keys.values()))
                cfg = replace(model.configuration, request=request)
                program = artifact.program
                record = run(program, cfg)
                if record.failure is not None:
                    errors[mode] = record.failure.detail('message')
                    continue
                proofs = Proofs(program, cfg)
                for path, value in expected.items():
                    if path == 'box.spare':
                        cited, required = {'other'}, {'box.spare'}
                    elif path == 'box.feed.request':
                        cited, required = set(), {'box.feed'}
                    else:
                        cited, required = {'measurement'}, {'box.plan', 'box.meter'}
                    try:
                        key = keys[path]
                        times = (1, 0) if seed % 2 else (0, 1)
                        rows = read(record, program, (key,), times)
                        graph = {part.origin for part in proofs.reads(key).edges}
                        observation = report(
                            record, program, cfg, [path], times, table=artifact.table
                        ).values[0]
                        credits = {c for part in observation.trail if part.exercised for c in part.records}
                        if rows[0].values != (value, value) or observation.values != (value, value):
                            errors[f'{mode}.{path}.values'] = (rows[0].values, observation.values, value)
                        if required - graph:
                            errors[f'{mode}.{path}.proof'] = {
                                'expected': sorted(required),
                                'found': sorted(graph),
                            }
                        if credits != cited:
                            errors[f'{mode}.{path}.citations'] = {
                                'expected': sorted(cited),
                                'found': sorted(credits),
                            }
                    except Exception as exc:
                        errors[f'{mode}.{path}'] = f'{type(exc).__name__}: {exc}'
        except Exception as exc:
            errors['construction'] = f'{type(exc).__name__}: {exc}'
        if errors:
            failures[name] = {
                'source': source,
                'sha256': sha256(source.encode()).hexdigest(),
                'differences': errors,
            }
    if failures:
        raise AssertionError(failures)
