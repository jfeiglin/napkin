"""Two tanks exchange a signed rate whose unconstrained inventory has an interior minimum."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction as F
from hashlib import sha256
from math import isclose
from random import Random
from unittest.mock import patch

from numpy.polynomial.chebyshev import chebder, chebroots

from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.declared import MovingDeclared
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
KEYS = (Key('yard', ('a',)), Key('yard', ('b',)))
METHODS = {'sparse': 'Sparse', 'component': 'ComponentWay', 'declared': 'MovingDeclared', 'secant': 'Lines'}
DECLARED_EVALUATIONS = 1500


class _TrialLimit(Exception):
    """A moving solver exhausted the per-spelling trial budget before reaching the horizon."""


@dataclass(frozen=True)
class Tanks:
    turn: F
    slope: F
    width: F
    spare: F
    padding: F
    touch: bool
    upper: bool
    reverse: bool
    tick: F

    @property
    def opening(self):
        sign = -1 if self.touch else 1
        return self.slope * (self.turn**2 + sign * self.width**2) / 2

    @property
    def total(self):
        return self.opening + self.padding + self.spare

    def levels(self, at):
        # Integrate k(t-T) up to the first contact. Between contact and T
        # the donor cannot deliver. After T only the growing positive lobe counts.
        minimum = self.opening - self.slope * self.turn**2 / 2
        if self.touch and at >= self.turn - self.width:
            minimum = 0
            elapsed = max(0, at - self.turn)
        else:
            elapsed = at - self.turn
        losing = self.padding + minimum + self.slope * elapsed**2 / 2
        levels = self.total - losing, losing
        return levels[::-1] if self.reverse else levels

    def bounds(self):
        # With padding, the donor stays positive: only the other tank's upper
        # bound can stop the transfer. Without padding, only the donor's floor can.
        bounds = ((F(0), self.total - self.padding if self.upper else None), (F(0), None))
        return bounds[::-1] if self.reverse else bounds

    def times(self):
        contact = self.turn - self.width
        times = {self.tick, contact, contact + self.width / 2, self.turn, self.turn + self.width / 2}
        return sorted(times | {self.turn * i / 16 for i in range(33)})


def _case(seed):
    if seed == 0:
        return Tanks(F(3, 2), F(2), F(1, 2), F(1), F(0), True, False, False, F(3, 4))
    rng = Random(seed)
    turn = F(rng.randint(5, 16), 8)
    slope = F(rng.randint(1, 18), 4)
    width = turn / rng.choice((2, 4, 8, 16, 32, 64))
    # The supply in the other tank exceeds the amount needed for the entire refill.
    spare = slope * width**2 / 2 + F(rng.randint(1, 9), 4)
    upper = seed % 5 in (2, 3)
    padding = F(rng.randint(1, 8), 4) if upper else F(0)
    tick = (turn - width) * F(rng.randint(2, 7), 8)
    return Tanks(turn, slope, width, spare, padding, seed % 11 != 10, upper, bool(seed % 2), tick)


def _number(value):
    # These dyadic values terminate within 24 decimal places. Emit every digit
    # for the independent reference, including a tiny distance to a bound.
    return format(Decimal(value.numerator) / Decimal(value.denominator), 'f')


def _source(case, method, event):
    lines = ['scenario "Two bounded tanks"', f'    horizon {_number(2 * case.turn)} h', 'yard:']
    for key, level, (_, upper) in zip(KEYS, case.levels(0), case.bounds(), strict=True):
        ceiling = '' if upper is None else _number(upper) + ' L'
        lines.append(f'    {key.steps[0]}: L = {_number(level)} L in [0 L,{ceiling}]')
    receiving, losing = ('b', 'a') if case.reverse else ('a', 'b')
    signed = f'-{_number(case.slope * case.turn)} L/h + ({_number(case.slope)} L/h/h) * t'
    if method == 'component':
        # A signed route selects Sparse. Its two rigid, nonnegative, directed
        # legs carry exactly the same net flow on the public Component path.
        for flow, source, sink, sign in (
            ('forward', receiving, losing, ''),
            ('backward', losing, receiving, '-'),
        ):
            amount = f'formula(max(0 L/h, {sign}({signed})))'
            lines += [
                f'    flow {flow}: this.{source} -> this.{sink}',
                f'        request = {amount}',
                f'        capacity = {amount}',
            ]
    elif method == 'secant':
        # Two constant requests on the very same route reproduce the integrated
        # volumes at the contact, turn and horizon. The reference covers these.
        drain = case.slope * (case.turn + case.width) / 2
        refill = case.slope * case.turn / 2
        lines += [
            f'    flow pipe: this.{receiving} <-> this.{losing}',
            f'        request = -{_number(drain)} L/h',
            '    reverse = event():',
            f'        after {_number(case.turn)} h:',
            f'            this.pipe.request = {_number(refill)} L/h',
        ]
    else:
        lines += [
            f'    flow pipe: this.{receiving} <-> this.{losing}',
            f'        request = formula({signed})',
        ]
    if event:
        lines += ['    idle = event():', f'        after {_number(case.tick)} h']
    if method == 'declared':
        lines += [
            'provider:',
            '    share = solver:',
            '        inputs:',
            '            pipe = yard.pipe',
            '        solve_for:',
            '            pipe.actual_rate',
        ]
    if event:
        lines.append('yard.idle.start()')
    if method == 'secant':
        lines.append('yard.reverse.start()')
    return '\n'.join(lines) + '\n'


def _extrema(record, key):
    """Inspect each retained polynomial over its own interval, including both one-sided ends."""
    pieces = record.history(key).pieces
    for i, piece in enumerate(pieces):
        end = pieces[i + 1].t if i + 1 < len(pieces) else record.end
        times = [piece.t, end]
        curve = piece.curve
        if curve is not None and len(curve.coefficients) >= 3 and end > piece.t:
            for root in chebroots(chebder(curve.coefficients)):
                if abs(root.imag) <= 1e-12:
                    at = piece.t + (1 + root.real) * curve.length / 2
                    if piece.t < at < end:
                        times.append(float(at))
        for at in times:
            yield at, piece.at(at)


def _engine(model, method, case, times):
    machine = Run(Plan.of(model.program, model.configuration))
    if method == 'declared':
        # MovingDeclared does not debit Numerics.max_evaluations. Count calls
        # through its ordinary integrated field so a stalled run has a reproducible
        # failure and the other spelling can still run.
        evaluate = MovingDeclared._integrated_rates
        count = 0

        def counted(way, at, state):
            nonlocal count
            if count == DECLARED_EVALUATIONS:
                raise _TrialLimit(
                    type(way).__name__,
                    {
                        'completed_evaluations': count,
                        'accepted_at': float(way.time),
                        'trial_at': float(at),
                        'accepted_levels': dict(zip(way.stores, map(float, way.y), strict=False)),
                    },
                )
            count += 1
            return evaluate(way, at, state)

        try:
            with patch.object(MovingDeclared, '_integrated_rates', counted):
                record = machine.run()
        except _TrialLimit as stop:
            way, details = stop.args
            return way, {'trial_budget': details}
    else:
        record = machine.run()
    flow = 'yard.forward' if method == 'component' else 'yard.pipe'
    way = type(machine.ways.instance_of(flow)).__name__
    errors = {}
    if way != METHODS[method]:
        errors['method'] = way, METHODS[method]
    if record.failure is not None or record.end != 2 * case.turn:
        errors['stop'] = record.end, str(record.failure)
    observed = [at for at in times if at <= record.end]
    traces = read(record, model.program, KEYS, [float(at) for at in observed])
    tolerance = 2e-8 * max(1, float(case.total))
    for i, (trace, (low, high)) in enumerate(zip(traces, case.bounds(), strict=True)):
        name = str(trace.key)
        mismatches = []
        for at, actual in zip(observed, trace.values, strict=True):
            expected = float(case.levels(at)[i])
            if not isclose(actual, expected, abs_tol=tolerance, rel_tol=0):
                mismatches.append((float(at), actual, expected))
        if mismatches:
            errors[name] = mismatches
        out_of_range = [
            (at, value)
            for at, value in _extrema(record, trace.key)
            if value < low - tolerance or (high is not None and value > high + tolerance)
        ]
        if out_of_range:
            errors[name + '.dense-bounds'] = {'interval': (low, high), 'violations': out_of_range}
    return way, errors


def _reference(model, case, times):
    try:
        run, failure = run_of(model.program, model.configuration)
        if failure is not None:
            return {'stop': (str(run.view.t), str(failure))}
        rows = values_at(run, model.program, KEYS, times)
    except NotCovered as error:
        return str(error)
    errors = {}
    for i, (key, series) in enumerate(rows.items()):
        differences = [
            (str(at), str(actual), str(case.levels(at)[i]))
            for at, actual in zip(times, series, strict=True)
            if actual != case.levels(at)[i]
        ]
        if differences:
            errors[str(key)] = differences
    return errors


def check_reversible_bounds(seed):
    """Report every divergence for the unchanged topology and its empty-event spelling."""
    case = _case(seed)
    methods = (
        ('sparse', 'component', 'declared')
        if seed == 0
        else (('sparse', 'component', 'sparse', 'declared')[seed % 4],)
    )
    if case.touch and seed % 12 == 0:
        methods += ('secant',)
    differences = {}
    for method in methods:
        times = [0, case.turn - case.width, case.turn, 2 * case.turn] if method == 'secant' else case.times()
        for event in (False, True):
            source = _source(case, method, event)
            way, found, reference = None, {}, None
            try:
                model = compile_text(source, UNITS)
            except Exception as error:
                found['compile'] = f'{type(error).__name__}: {error}'
            else:
                try:
                    way, engine = _engine(model, method, case, times)
                    if engine:
                        found['engine'] = engine
                except Exception as error:
                    found['engine'] = f'{type(error).__name__}: {error}'
                try:
                    reference = _reference(model, case, times)
                    if isinstance(reference, dict) and reference:
                        found['reference'] = reference
                    if method == 'secant' and isinstance(reference, str):
                        found['reference'] = 'covered constant-rate control: ' + reference
                except Exception as error:
                    found['reference'] = f'{type(error).__name__}: {error}'
            if found:
                differences[method + ('.event' if event else '.plain')] = {
                    'method': way,
                    'reference_coverage': reference if isinstance(reference, str) else 'covered',
                    'source_sha256': sha256(source.encode()).hexdigest(),
                    'source': source,
                    **found,
                }
    assert not differences, (seed, 'reversible', differences)
