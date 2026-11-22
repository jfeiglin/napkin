"""Read the meter upstream of a signed route, and the limiting input upstream of served_fraction."""

from dataclasses import replace
from hashlib import sha256
from math import isclose
from random import Random

from napkin.engine import run
from napkin.engine.report import report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text
from napkin.program.artifact import loads
from napkin.program.proofs import Proofs

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
CITATIONS = {'channel.meter': 'meter', 'works.quota': 'quota', 'channel.unrelated': 'independent'}


def _case(seed, sign):
    rng = Random(seed)
    magnitude = rng.randrange(1, 25) if seed else 3
    fraction = rng.choice((0.25, 0.5, 0.75)) if seed else 0.5
    asked = 4 * (rng.randrange(1, 8) if seed else 1)
    cutoff = rng.randrange(3, 9) / 8 if seed else 0.5
    spare = rng.randrange(3, 35) if seed else 7
    signed = sign * magnitude
    source = f"""scenario "Route and batch meters"
    horizon 2 h
west:
    water: L = 200 L
    incoming = formula(sum(this.water.inflow.flows.actual_rate))
    outgoing = formula(sum(this.water.outflow.flows.actual_rate))
east:
    water: L = 200 L
    incoming = formula(sum(this.water.inflow.flows.actual_rate))
    outgoing = formula(sum(this.water.outflow.flows.actual_rate))
channel:
    input meter: L/h = {signed} L/h @meter
    input unrelated: L/h = {spare} L/h @independent
    control = formula(this.unrelated)
    flow link: west.water <-> east.water
        request = formula(this.meter)
    noted: L/h = 0 L/h
    inspect = event():
        forward = formula(channel.link.forward.actual_rate)
        backward = formula(channel.link.backward.actual_rate)
        included = formula(sum(west.water.outflow.flows.actual_rate))
        endpoint = formula(west.water.inflow.actual_rate)
        after {cutoff} h:
            this.noted = west.water.outflow.actual_rate - west.water.inflow.actual_rate
works:
    input quota: L/h = {asked * fraction} L/h @quota
    stock: L = 200 L
    supply: L = 200 L
    flow batch:
        flow use: this.stock -> SINK
            request = {asked} L/h
            capacity = formula(this.quota)
        flow pair: this.supply -> SINK
            request = {2 * asked} L/h
    scale_reading = formula(this.batch.served_fraction)
channel.inspect.start()
record meter: source "Route meter."
record quota: source "Batch quota."
record independent: source "Independent control."
"""
    forward, backward = max(0, signed), max(0, -signed)
    # Each side is the sum of its entering or leaving directional legs (both are nonnegative).
    rates = {
        'channel.link.actual_rate': signed,
        'channel.link.forward.actual_rate': forward,
        'channel.link.backward.actual_rate': backward,
        'channel.inspect#0.forward': forward,
        'channel.inspect#0.backward': backward,
        'channel.inspect#0.included': forward,
        'channel.inspect#0.endpoint': backward,
    }
    for place, incoming, outgoing in (('west', backward, forward), ('east', forward, backward)):
        for side, local, value in (('inflow', 'incoming', incoming), ('outflow', 'outgoing', outgoing)):
            rates[f'{place}.water.{side}.actual_rate'] = value
            rates[f'{place}.{local}'] = value
    expected = {path: ('meter', (value, value)) for path, value in rates.items()}
    expected['channel.noted'] = 'meter', (0, signed)
    expected['channel.control'] = 'independent', (spare, spare)
    expected['works.batch.served_fraction'] = 'quota', (fraction, fraction)
    expected['works.scale_reading'] = 'quota', (fraction, fraction)
    expected['works.batch.use.actual_rate'] = 'quota', (asked * fraction, asked * fraction)
    return source, [cutoff / 2, (cutoff + 2) / 2], expected


def _graph_sources(proofs, key):
    tree = proofs.reads(key)
    pending, seen = [tree.start], set()
    while pending:
        part = pending.pop()
        if part not in seen:
            seen.add(part)
            pending.extend(tree.edges.get(part, ()))
    return sorted({CITATIONS[part.origin] for part in seen if part.origin in CITATIONS})


def _check_row(row, expected):
    tag, hand = expected
    differences = {}
    if any(
        not isinstance(actual, (float, int)) or not isclose(actual, value, rel_tol=1e-9, abs_tol=1e-10)
        for actual, value in zip(row.values, hand, strict=True)
    ):
        differences['values'] = {'expected': hand, 'observed': tuple(map(str, row.values))}
    exercised = sorted({cite for used in row.trail if used.exercised for cite in used.records})
    if exercised != [tag]:
        differences['exercised'] = {'expected': [tag], 'observed': exercised}
    return differences


def check_proof_network(seed):
    differences = {}
    for sign in (-1, 1):
        source, times, expected = _case(seed, sign)
        failures = {}
        try:
            model = compile_text(source, UNITS)
            artifact = loads(model.artifact().data())
        except Exception as error:
            failures['compile'] = f'{type(error).__name__}: {error}'
        else:
            keys = {name: key_of(artifact.program, name) for name in expected}
            proofs = Proofs(artifact.program, model.configuration)
            for name, key in keys.items():
                try:
                    actual = _graph_sources(proofs, key)
                    want = [expected[name][0]]
                    if actual != want:
                        failures['graph/' + name] = {'expected': want, 'observed': actual}
                except Exception as error:
                    failures['graph/' + name] = f'{type(error).__name__}: {error}'
            for full in (True, False):
                mode = 'full' if full else 'selective'
                cfg = replace(
                    model.configuration,
                    request=replace(
                        model.configuration.request,
                        everything=full,
                        keys=() if full else tuple(keys.values()),
                    ),
                )
                evidence = {'model': model.declared} if full else {'table': artifact.table}
                try:
                    record = run(artifact.program, cfg)
                    if record.failure:
                        raise ValueError(record.failure)
                except Exception as error:
                    failures[mode + '/run'] = f'{type(error).__name__}: {error}'
                    continue
                paths = list(expected) if full else list(reversed(expected))
                try:
                    rows = report(record, artifact.program, cfg, paths, times, **evidence).values
                except Exception:
                    # A refusal of one path cannot conceal the others.
                    rows = []
                    for name in paths:
                        try:
                            rows.extend(
                                report(record, artifact.program, cfg, [name], times, **evidence).values
                            )
                        except Exception as error:
                            failures[f'{mode}/{name}'] = f'{type(error).__name__}: {error}'
                for row in rows:
                    wrong = _check_row(row, expected[row.path])
                    if wrong:
                        failures[f'{mode}/{row.path}'] = wrong
        if failures:
            differences['forward' if sign > 0 else 'reverse'] = {
                'source_sha256': sha256(source.encode()).hexdigest(),
                'source': source,
                'times': times,
                'differences': failures,
            }
    assert not differences, (seed, 'proof-network', differences)
