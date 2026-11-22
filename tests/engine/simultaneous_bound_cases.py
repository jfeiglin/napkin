"""Paired inventory bounds on the two ends of a held or reversing transfer."""

import math
from decimal import Decimal
from fractions import Fraction
from random import Random
from traceback import format_exc

import numpy as np

from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}
METHODS = {'family': 'Family', 'lines': 'Lines', 'declared': 'DeclaredWay', 'sparse': 'Sparse'}


def _data(seed):
    rng = Random(seed)
    unit = Fraction(10 ** rng.randrange(0, 4), 10 ** rng.randrange(0, 3))
    rate = rng.randrange(1, 12) * unit
    at = Fraction(rng.randrange(2, 15), rng.choice((4, 8)))
    # Separate contacts by zero, a fraction of a comparison band, or many bands.
    relative = (0, 1, -1, 20_000, -20_000)[seed % 5]
    shift = Fraction(relative, 10**11) * rate * at
    floor = rate * at * rng.choice((Fraction(1, 10), 1, 8))
    lower = Fraction(rng.randrange(0, 8), 8) * rate * at
    event = at * rng.choice((Fraction(3, 4), 1, Fraction(3, 2), Fraction(7, 4)))
    return rate, at, shift, floor, lower, event


def _lit(number):
    value = Fraction(number)
    return format(Decimal(value.numerator) / Decimal(value.denominator), 'f')


def _stocks(seed, method):
    rate, at, shift, _, lower, _ = _data(seed)
    to_face = rate * at * (Fraction(3, 2) if method == 'sparse' else 1)
    back = rate * at / 2
    donor = (lower, lower + to_face, lower + to_face + back + shift)
    receiver = (lower, lower + back, lower + back + to_face + shift)
    return donor, receiver


def simultaneous_source(seed, method, cut):
    rate, at, _, floor, _, event = _data(seed)
    donor, receiver = _stocks(seed, method)
    source = f'scenario "Two ends at their bounds"\n    horizon {_lit(at * Fraction(17, 4))} h\nyard:\n'
    for name, (lo, initial, hi) in zip(('donor', 'receiver'), (donor, receiver), strict=True):
        source += f'    {name}: L = {_lit(initial)} L in [{_lit(lo)} L, {_lit(hi)} L] scale {_lit(floor)} L\n'
    route = method in ('lines', 'sparse')
    backwards = route and seed % 2
    left, right = ('receiver', 'donor') if backwards else ('donor', 'receiver')
    source += f'    flow pipe: this.{left} {"<->" if route else "->"} this.{right}\n'
    signed = -rate if backwards else rate
    if method == 'sparse':
        request = f'formula({_lit(signed)} L/h * (2 - t / {_lit(at)} h))'
    else:
        request = f'{_lit(signed)} L/h'
    source += f'        request = {request}\n'
    if method == 'declared':
        source += """owner:
    hold = solver:
        inputs:
            pipe = yard.pipe
        solve_for:
            pipe.actual_rate
"""
    if cut:
        source += f'clock:\n    tick = event():\n        after {_lit(event)} h\nclock.tick.start()\n'
    return source


def _levels(time, rate, at, donor, receiver, method):
    space = min(donor[1] - donor[0], receiver[2] - receiver[1])
    if method != 'sparse':
        moved = min(space, rate * time)
    elif time <= 2 * at:
        moved = min(space, rate * time * (2 - time / (2 * at)))
    else:
        # The transfer rests until its request reverses at 2*at. It then gains
        # reverse volume rate*(t-2*at)^2/(2*at) until the opposite pair of bounds.
        returned = rate * (time - 2 * at) ** 2 / (2 * at)
        moved = max(space - returned, donor[1] - donor[2], receiver[0] - receiver[1])
    return donor[1] - moved, receiver[1] + moved


def _dense_points(piece, end):
    """Endpoints and every interior stationary point of this recorded dense polynomial."""
    yield piece.t
    yield (piece.t + end) / 2
    yield end
    if piece.curve is not None and len(piece.curve.coefficients) > 2:
        derivative = np.polynomial.chebyshev.chebder(piece.curve.coefficients)
        for root in np.polynomial.chebyshev.chebroots(derivative):
            if abs(root.imag) < 1e-12:
                at = piece.t + (float(root.real) + 1) * piece.curve.length / 2
                if piece.t < at < end:
                    yield at


def _case(seed, method, cut):
    source = simultaneous_source(seed, method, cut)
    model = compile_text(source, UNITS)
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    actual_method = type(machine.ways.instance_of('yard.pipe')).__name__
    differences = {}
    if actual_method != METHODS[method]:
        differences['method'] = (actual_method, METHODS[method])
    rate, at, _, floor, _, _ = _data(seed)
    donor, receiver = _stocks(seed, method)
    times = tuple(at * Fraction(k, 8) for k in range(35))
    keys = [Key('yard', (field,)) for field in ('donor', 'receiver')]
    # The exact reference covers both signs of a held reversible request (Lines).
    # Continuously varying requests lie outside its supported subset (Sparse).
    if method != 'sparse':
        try:
            oracle, error = run_of(model.program, model.configuration)
            if error is not None:
                differences['reference.failure'] = str(error)
            else:
                for t in times:
                    expected = _levels(t, rate, at, donor, receiver, method)
                    got = tuple(value_at(oracle, model.program, key, t) for key in keys)
                    if any(abs(a - b) > floor / 10**9 for a, b in zip(got, expected, strict=True)):
                        differences['reference.levels'] = (
                            str(t),
                            list(map(str, got)),
                            list(map(str, expected)),
                        )
                        break
        except Exception:
            differences['reference.exception'] = format_exc()
    if record.failure is not None:
        differences['stopped'] = (record.end, record.failure.detail('message'), str(record.failure.details))
    reads = {}
    for which, (key, bounds) in enumerate(zip(keys, (donor, receiver), strict=True)):
        history = record.history(key)
        lo, hi = float(bounds[0]), float(bounds[2])
        probes = []
        for t in times:
            if t > record.end:
                break
            value = record.value(key, float(t))
            reads[str(key), float(t)] = value
            probes.append((float(t), value))
        for k, piece in enumerate(history.pieces):
            end = history.pieces[k + 1].t if k + 1 < len(history.pieces) else record.end
            probes.extend((t, piece.at(t)) for t in _dense_points(piece, end))
        for t, value in probes:
            expected = float(_levels(Fraction(t), rate, at, donor, receiver, method)[which])
            edge = min(max(value, lo), hi)
            band = float(model.configuration.numerics.rtol) * max(float(floor), abs(edge), abs(value))
            if abs(value - edge) > band:
                differences.setdefault(f'{key}.bound', (t, value, lo, hi, band))
            tolerance = max(band, float(rate * at) * 2e-8)
            if not math.isclose(value, expected, rel_tol=0, abs_tol=tolerance):
                differences.setdefault(f'{key}.level', (t, value, expected, tolerance))
    return differences, reads, float(model.configuration.numerics.rtol)


def check_simultaneous_bounds(seed):
    failures = {}
    # 43 of 300 seeds also take the more expensive implicit path. This rotation
    # crosses both orientations and all five contact offsets, including seed 3.
    _, _, _, floor, _, _ = _data(seed)
    for method in METHODS:
        if method == 'sparse' and seed % 7 != 3:
            continue
        whole = {}
        for cut in (False, True):
            try:
                differences, reads, rtol = _case(seed, method, cut)
                if not cut:
                    whole = reads
                else:
                    for (key, t), value in reads.items():
                        if (key, t) not in whole:
                            continue
                        other = whole[key, t]
                        band = rtol * max(float(floor), abs(value), abs(other))
                        if not math.isclose(value, other, rel_tol=0, abs_tol=band):
                            differences.setdefault(f'{key}.whole-vs-cut', (t, other, value, band))
            except Exception:
                differences = {'exception': format_exc()}
            if differences:
                failures[f'{method}.{"cut" if cut else "whole"}'] = {
                    'differences': differences,
                    'source': simultaneous_source(seed, method, cut),
                }
    assert not failures, (seed, failures)
