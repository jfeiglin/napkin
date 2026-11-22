"""A second set selects its throughput from a first set's rate at the same physical state."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction as F
from hashlib import sha256
from math import isclose
from random import Random

from napkin.engine.timeline import Plan, Run, read
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.errors import NotCovered
from tests.reference.from_program import run_of, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
METER = Key('yard', ('meter',))
WATER = Key('yard', ('water',))
TAP = Key('yard', ('tap', 'actual_rate'))
PIPE = Key('yard', ('pipe', 'actual_rate'))
RELAY = Key('yard', ('relay', 'actual_rate'))
MODES = (
    'guard-capacity',
    'key-capacity',
    'guard-request',
    'key-request',
    'linear-request',
    'linear-capacity',
)


def _text(value):
    return format(Decimal(value.numerator) / Decimal(value.denominator), 'f')


@dataclass(frozen=True)
class Case:
    horizon: F
    crossing: F
    start: F
    slope: F
    below: F
    above: F
    event: F
    multiplier: int
    state_driver: bool
    switches: bool

    def times(self):
        x, h = self.crossing, self.horizon
        # Interior rate samples either side of x avoid imposing a point-value
        # convention on a strict comparison and an inclusive table lookup.
        return (F(0), x / 2, (x + h) / 2, h)

    def upstream(self, at):
        return self.start + self.slope * at

    def cutoff(self):
        if self.switches:
            return self.multiplier * self.upstream(self.crossing)
        return self.multiplier * max(self.upstream(0), self.upstream(self.horizon)) + 1

    def expected(self, mode, at):
        meter = self.start * at + self.slope * at**2 / 2
        incoming = self.upstream(at)
        if mode.startswith('linear'):
            water, pipe = self.multiplier * meter, self.multiplier * incoming
        else:
            first = self.above if self.switches and self.slope < 0 else self.below
            last = self.above if self.switches and self.slope > 0 else self.below
            water = first * min(at, self.crossing) + last * max(0, at - self.crossing)
            pipe = last if at > self.crossing else first
        answers = {METER: meter, WATER: water, TAP: incoming, PIPE: pipe}
        if self.multiplier != 1:
            answers[RELAY] = incoming * self.multiplier
        return answers


def case_for(seed):
    if not seed:
        return Case(F(2), F(1, 2), F(0), F(2), F(2), F(1, 4), F(1), 1, False, True)
    rng = Random(seed)
    horizon = F(rng.randint(6, 20), 8)
    cross = horizon * F(rng.choice((2, 3, 4, 5, 6)), 8)
    slope = F(rng.randint(1, 12), 4) * (-1 if (seed + seed // len(MODES)) % 2 else 1)
    start = F(rng.randint(1, 5), 4) + max(0, -slope * horizon)
    below, above = rng.sample([F(i, 4) for i in range(1, 16)], 2)
    tick = horizon / 2 if seed % 3 else cross / 2
    return Case(
        horizon,
        cross,
        start,
        slope,
        below,
        above,
        tick,
        2 if seed % 7 == 3 else 1,
        seed % 5 == 1,
        seed % 13 != 12,
    )


def source_of(case, mode, event):
    selector, setting = mode.split('-')
    lines = ['scenario "Rates across two sets"', f'    horizon {_text(case.horizon)} h']
    if selector == 'key':
        lines += [
            'Band:',
            '    input cutoff: L/h = 0 L/h',
            f'    input rate: L/h = {_text(case.below)} L/h',
            'low: Band',
            'high: Band',
            f'    cutoff = {_text(case.cutoff())} L/h',
            f'    rate = {_text(case.above)} L/h',
        ]
    lines += ['yard:', '    meter: L = 0 L', '    water: L = 0 L']
    if case.state_driver:
        lines += [
            '    driver: L = 0 L',
            '    flow wind: SOURCE -> this.driver',
            '        request = 1 L/h',
        ]
        moving = f'({_text(case.slope)} * this.driver / (1 h))'
    else:
        moving = f'(({_text(case.slope)} L/h/h) * t)'
    lines += [
        '    flow tap: SOURCE -> this.meter',
        f'        request = formula({_text(case.start)} L/h + {moving})',
    ]
    upstream = 'this.tap.actual_rate'
    if case.multiplier != 1:
        lines += [
            '    relay_meter: L = 0 L',
            '    flow relay: SOURCE -> this.relay_meter',
            f'        request = formula({case.multiplier} * {upstream})',
        ]
        upstream = 'this.relay.actual_rate'
    if selector == 'guard':
        rate = (
            f'{_text(case.above)} L/h if {upstream} > {_text(case.cutoff())} L/h else {_text(case.below)} L/h'
        )
    elif selector == 'key':
        rate = f'Band.instances.by(cutoff).at({upstream}).rate'
    else:
        rate = upstream
    lines.append('    flow pipe: SOURCE -> this.water')
    if setting == 'capacity':
        maximum = max(case.above, case.below)
        if selector == 'linear':
            maximum = case.multiplier * max(case.upstream(0), case.upstream(case.horizon))
        lines.append(f'        request = {_text(maximum)} L/h')
    lines.append(f'        {setting} = formula({rate})')
    if event:
        lines += ['    idle = event():', f'        after {_text(case.event)} h', 'yard.idle.start()']
    return '\n'.join(lines) + '\n'


def engine_rows(model, keys, times):
    machine = Run(Plan.of(model.program, model.configuration))
    record = machine.run()
    way = machine.ways.instance_of('yard.pipe')
    method = type(way).__name__
    levels = {
        flow: level
        for group, level in zip(getattr(way, 'sets', ()), getattr(way, 'set_levels', ()), strict=True)
        for flow in group.flows
    }
    path = method, levels
    if record.failure is not None or record.end != model.configuration.request.horizon:
        return path, {'stop': (record.end, str(record.failure))}, {}
    rows = read(record, model.program, keys, [float(at) for at in times])
    return path, {}, {row.key: row.values for row in rows}


def _compare(case, mode, times, rows):
    differences = {}
    for key, values in rows.items():
        failures = []
        for at, actual in zip(times, values, strict=True):
            target = case.expected(mode, at)[key]
            if not isclose(actual, float(target), abs_tol=3e-8, rel_tol=1e-9):
                failures.append((str(at), str(actual), str(target)))
        if failures:
            differences[str(key)] = failures
    return differences


def check_cross_rate(seed):
    """Compare all spellings chosen for a seed before reporting its disagreements."""
    case = case_for(seed)
    times = case.times()
    modes = MODES if not seed else (MODES[seed % len(MODES)],)
    keys = tuple(case.expected(modes[0], 0))
    differences = {}
    for mode in modes:
        for event in (False, True):
            source = source_of(case, mode, event)
            errors, path, coverage = {}, None, 'covered'
            try:
                model = compile_text(source, UNITS)
            except Exception as error:
                errors['compile'] = f'{type(error).__name__}: {error}'
            else:
                try:
                    path, engine, observed = engine_rows(model, keys, times)
                    method, levels = path
                    expected_flows = ['yard.tap', 'yard.pipe']
                    if case.multiplier != 1:
                        expected_flows.insert(1, 'yard.relay')
                    ordered = [levels.get(flow, -1) for flow in expected_flows]
                    if method != 'Sparse' or ordered[0] < 0 or ordered != sorted(set(ordered)):
                        engine['dependency order'] = expected_flows, path
                    engine.update(_compare(case, mode, times, observed))
                    if engine:
                        errors['engine'] = engine
                except Exception as error:
                    errors['engine'] = f'{type(error).__name__}: {error}'
                try:
                    reference, failure = run_of(model.program, model.configuration)
                    if failure is not None:
                        errors['reference'] = {'stop': str(failure)}
                    else:
                        sampled = values_at(reference, model.program, keys, times)
                        mismatches = _compare(case, mode, times, sampled)
                        if mismatches:
                            errors['reference'] = mismatches
                except NotCovered as error:
                    coverage = str(error)
                except Exception as error:
                    errors['reference'] = f'{type(error).__name__}: {error}'
            if errors:
                differences[mode + ('.event' if event else '.plain')] = {
                    'sparse_levels': path,
                    'reference_coverage': coverage,
                    'source_sha256': sha256(source.encode()).hexdigest(),
                    'source': source,
                    **errors,
                }
    assert not differences, (seed, 'cross-rate', differences)
