"""A passive meter opens on a comparison of two independently specified linear trajectories."""

from fractions import Fraction
from math import isclose
from operator import ge, gt, le, lt
from random import Random
from unittest.mock import patch

from napkin.engine.timeline import Plan, Run, read
from napkin.engine.timeline.declared import MovingDeclared
from napkin.program.build import (
    SINK,
    SOURCE,
    Builder,
    endpoint,
    flow,
    fmax,
    formula,
    given,
    ifelse,
    local,
    q,
    solve_for,
    solver,
    t,
    this,
    value,
)
from napkin.program.config import Configuration, Numerics, Request
from napkin.program.record import Key
from tests.comparison_bands import band_samples

WAYS = {'component': 'ComponentWay', 'sparse': 'Sparse', 'declared': 'MovingDeclared'}
TIMES = (Fraction(1, 4), Fraction(3, 4), Fraction(1))
VARIANTS = ('co-moving', 'crossing', 'inside-band', 'departure', 'late-separation', 'band-exit')


def switch_gap(scale):
    (band,) = band_samples(Configuration(Request(1)), scale, multiples=(1,))
    return Fraction(str(band))


def _run(machine, family, case):
    if family != 'declared':
        return machine.run()
    # MovingDeclared does not count its Radau evaluations against Numerics.max_evaluations.
    # Give a chattering baseline the same deterministic stop as the other two methods.
    evaluate = MovingDeclared._integrated_rates
    evaluations = 0

    def counted(way, at, state):
        nonlocal evaluations
        evaluations += 1
        if evaluations > machine.plan.numerics.max_evaluations:
            raise AssertionError((case, 'declared integration evaluation budget exceeded', way.time, at))
        return evaluate(way, at, state)

    with patch.object(MovingDeclared, '_integrated_rates', counted):
        return machine.run()


def check_switch_side(seed, family):
    rng = Random(seed)
    variant = VARIANTS[(seed // 4) % len(VARIANTS)]
    # The first four rows cover the four directed examples in the brief.
    pace = (7, Fraction(1, 10), -7, Fraction(-1, 10))[seed % 4]
    start = 5 if seed < 2 else rng.randint(max(5, 1 - pace), 25)
    if seed >= 16:
        pace = (1 if pace > 0 else -1) * Fraction(rng.randint(1, 19), rng.choice((5, 8, 10)))
    op = (gt, lt, lt, gt)[seed % 4]
    if seed >= 16 and seed % 5 == 0:
        op = ge if op == gt else le
    origin, slope, scale = start, pace, None
    cross = Fraction(rng.choice((3, 4, 5)), 8)
    before = after = int(op(0, 0))
    if variant == 'inside-band':
        # The raw gap changes sign at cross, always strictly inside the comparison band.
        change = switch_gap(1) * Fraction(1 if seed % 2 else -1, 1000)
        origin += change * cross
        slope -= change
    elif variant == 'band-exit':
        # Start halfway from equality to the edge of the declared stock's band. The operands
        # leave it at cross without crossing raw zero anywhere on this trajectory.
        scale = 100_000
        edge = switch_gap(scale) * (1 if op in (gt, le) else -1)
        origin -= edge / 2
        slope -= edge / (2 * cross)
        after = int(op(edge, 0))
    elif variant != 'co-moving':
        change = Fraction(pace, 2) * (1 if seed % 2 else -1)
        if variant == 'departure':
            cross = Fraction(0)
        if variant != 'late-separation':
            origin += change * cross
            slope -= change
            before = int(op(-change, 0))
        after = int(op(change, 0))
    mirror = q(origin, 'L') + t * q(slope, 'L/h')
    if variant == 'late-separation':
        # Both trajectories coincide throughout [0, cross]. Only the mirror's velocity
        # changes there. The hand calculation integrates the two open-interval rates.
        mirror -= q(change, 'L/h') * fmax(q(0, 'h'), t - q(cross, 'h'))

    builder = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    cap = endpoint(capacity=q(40, 'L/h')) if family == 'sparse' else None
    source, sink = (SOURCE, this.level) if pace > 0 else (this.level, SINK)
    plant = builder.entity(
        'plant',
        value(
            'level',
            'L',
            start,
            scale=scale,
            inflow=cap if pace > 0 else None,
            outflow=cap if pace < 0 else None,
        ),
        value('mirror', 'L', formula(mirror)),
        value('delivery', 'L', 0),
        flow('drive', source, sink, request=q(abs(pace), 'L/h')),
        flow(
            'meter',
            SOURCE,
            this.delivery,
            request=formula(ifelse(op(this.level, this.mirror), q(1, 'L/h'), q(0, 'L/h'))),
        ),
    )
    if family == 'declared':
        builder.entity(
            'provider',
            solver(
                'share',
                given('drive', plant.drive),
                given('meter', plant.meter),
                solve_for(local.drive.actual_rate),
                solve_for(local.meter.actual_rate),
            ),
        )

    model = builder.finish()
    keys = (Key('plant', ('level',)), Key('plant', ('delivery',)), Key('plant', ('meter', 'actual_rate')))
    config = Configuration(
        Request(1, everything=False, keys=keys, pieces=256), numerics=Numerics(max_evaluations=512)
    )
    machine = Run(Plan.of(model, config))
    case = (seed, family, variant, op.__name__, start, str(pace), str(origin), str(slope))
    record = _run(machine, family, case)
    actual_way = type(machine.ways.instance_of('plant.meter')).__name__
    assert actual_way == WAYS[family], (case, actual_way)
    assert record.failure is None and record.end == 1, (case, record.end, record.failure)

    expected = (
        [start + pace * at for at in TIMES],
        [min(at, cross) * before + max(at - cross, 0) * after for at in TIMES],
        [before if at < cross else after for at in TIMES],
    )
    rows = read(record, model, keys, list(map(float, TIMES)))
    for row, hand in zip(rows, expected, strict=True):
        assert all(
            isclose(value, float(target), abs_tol=2e-8, rel_tol=1e-10)
            for value, target in zip(row.values, hand, strict=True)
        ), (case, str(row.key), row.values, tuple(map(float, hand)))
