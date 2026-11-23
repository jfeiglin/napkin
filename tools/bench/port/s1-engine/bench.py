"""The benchmark of S1-E (a benchmark, not a test): 30,000 places that read a keyed factor and that
the root reduces.

Each place drains its stock into its own tally at `base * Reading.instances.by(hour).at(t).factor`
(readings at 0, 12, 24 and 36 h: 1, 0.5, 1.5, 1); the root sums the stocks, the rates and the stocks
of the critical places (`where`), and counts the critical places. Every set is one flow whose rate
holds between moments, so all run on arrays (`napkin/engine/timeline/family.py`). The reductions at
three times are checked against the closed form max(0, initial - base * F(t)), F the integral of the
factor.

    cd /home/user/napkin && OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/bench/port/s1-engine/bench.py [rows]
"""

import argparse
import json
import time

import numpy as np

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run
from napkin.program.build import BOOL, Builder, count, flow, formula, fsum, input_, item, t, this, value
from napkin.program.config import Configuration, Request
from napkin.program.record import Key

HOURS = (0, 12, 24, 36)
FACTORS = (1, 0.5, 1.5, 1)


def program(rows):
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}})
    reading = b.template('Reading', input_('hour', 'h', 0), input_('factor', '', 1))
    b.table(
        'readings',
        reading,
        [{'id': f'r{k}', 'hour': h, 'factor': f} for k, (h, f) in enumerate(zip(HOURS, FACTORS))],
    )
    place = b.template(
        'Place',
        input_('base', 'L/h', 1),
        input_('initial', 'L', 10),
        input_('critical', BOOL, False),
        value('stock', 'L', this.initial, lower=0),
        value('used', 'L', 0, lower=0),
        flow(
            'use',
            this.stock,
            this.used,
            request=formula(this.base * reading.instances.by('hour').at(t).factor),
        ),
    )
    choose = np.random.default_rng(7)
    bases = choose.uniform(0.2, 2.0, rows).round(3)
    initials = choose.uniform(5.0, 60.0, rows).round(2)
    b.table(
        'places',
        place,
        [
            {
                'id': f'p{k:05d}',
                'base': float(bases[k]),
                'initial': float(initials[k]),
                'critical': k % 10 == 0,
            }
            for k in range(rows)
        ],
    )
    b.root(
        value('total', 'L', formula(fsum(place.instances.stock))),
        value('drawing', 'L/h', formula(fsum(place.instances.use.actual_rate))),
        value('critical_stock', 'L', formula(fsum(place.instances.where(item.critical).stock))),
        value('critical_count', '', count(place.instances.where(item.critical))),
    )
    return b.finish(), bases, initials


def integral(at):
    """F(t): the integral of the factor from 0 to t."""
    edges = [*HOURS, np.inf]
    return sum(f * max(0.0, min(at, edges[k + 1]) - edges[k]) for k, f in enumerate(FACTORS))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rows', type=int, nargs='?', default=30_000)
    parser.add_argument(
        '--full-record-only', action='store_true', help='skip the separate selective-record run'
    )
    args = parser.parse_args()
    start = time.perf_counter()
    made, bases, initials = program(args.rows)
    built = time.perf_counter()
    configuration = Configuration(Request(48))
    plan = Plan.of(made, configuration)
    planned = time.perf_counter()
    record = Run(plan).run()
    ran = time.perf_counter()
    assert record.failure is None, record.failure
    times = [6.0, 30.0, 48.0]
    paths = ['total', 'drawing', 'critical_stock', 'places.p00042.stock']
    readings = read(record, made, paths, times)
    done = time.perf_counter()
    for k, at in enumerate(times):
        # Inputs have exactly three and two decimal places. Classify a pipe that has
        # just emptied at this hour as closed before checking the reported flow rate.
        remaining = np.rint(initials * 1000) - np.rint(bases * 1000) * integral(at)
        stocks = np.maximum(0, remaining) / 1000
        factor = FACTORS[np.searchsorted(HOURS, at, side='right') - 1]
        expected = (stocks.sum(), bases[remaining > 0].sum() * factor, stocks[::10].sum(), stocks[42])
        for path, reading, target in zip(paths, readings, expected, strict=True):
            assert np.isclose(reading.values[k], target, rtol=1e-9, atol=1e-9), (
                at,
                path,
                reading.values[k],
                target,
            )
    pieces = sum(len(history.pieces) for history in record.histories)
    print(
        f'rows {args.rows}: build {built - start:.9f} s, plan {planned - built:.9f} s, run with its record {ran - planned:.9f} s, '
        f'read 4 paths at 3 times {done - ran:.9f} s; {len(record.histories)} histories, {pieces} pieces'
    )
    print('total at 6, 30, 48 h:', readings[0].values, 'drawing:', readings[1].values)
    print(
        'observations',
        json.dumps({path: reading.values for path, reading in zip(paths, readings, strict=True)}),
    )
    if not args.full_record_only:
        narrow = Configuration(
            Request(48, everything=False, keys=(Key('', ('total',)), Key('places.p00042', ('stock',))))
        )
        again = time.perf_counter()
        small = run(made, narrow)
        after = time.perf_counter()
        assert small.failure is None
        print(f'the same with a record of two values: plan and run {after - again:.9f} s')


if __name__ == '__main__':
    main()
