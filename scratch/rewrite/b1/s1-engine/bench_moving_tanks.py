"""Run independent filling tanks on a specified method and check their analytical solution."""

import argparse
import math
import time
from unittest.mock import patch

from napkin.engine import read
from napkin.engine.timeline import Plan, Run
from napkin.program.build import SOURCE, Builder, flow, formula, q, this, value
from napkin.program.config import Configuration, Request


def program(count):
    builder = Builder({'L': {'volume': 1}, 'h': {'time': 1}})
    for i in range(count):
        builder.entity(
            f'tank{i}',
            value('water', 'L', 0, lower=0),
            flow('fill', SOURCE, this.water, request=formula((q(100 + i, 'L') - this.water) / q(4 + i, 'h'))),
        )
    return builder.finish()


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--tanks', type=int, default=12)
    args.add_argument('--hours', type=float, default=12)
    args.add_argument('--method', choices=('component', 'sparse'), required=True)
    args.add_argument('--repeat', type=int, default=1, help='fresh runs with identical inputs')
    options = args.parse_args()
    if options.tanks < 1 or options.hours <= 0 or options.repeat < 1:
        args.error('tanks, hours and repeat must be positive')
    model = program(options.tanks)
    config = Configuration(Request(options.hours))
    times = [options.hours * f for f in (0.25, 0.5, 1)]
    paths = [f'tank{i}.water' for i in range(options.tanks)]
    elapsed = 0
    with patch('napkin.engine.timeline.plan.LIMIT', 0 if options.method == 'sparse' else 150):
        for _ in range(options.repeat):
            plan = Plan.of(model, config)
            assert [group.way for group in plan.sets] == [options.method] * options.tanks
            start = time.perf_counter()
            record = Run(plan).run()
            elapsed += time.perf_counter() - start
            assert record.failure is None, record.failure
            for i, row in enumerate(read(record, model, paths, times)):
                for t, observed in zip(times, row.values):
                    expected = -(100 + i) * math.expm1(-t / (4 + i))
                    assert math.isclose(observed, expected, rel_tol=1e-8, abs_tol=1e-10), (i, t, observed, expected)
    print(f'{options.method}: {options.tanks} tanks, {options.hours:g} h, {options.repeat} runs, '
          f'run+record {elapsed:.6f} s, mean {elapsed/options.repeat:.6f} s')


if __name__ == '__main__':
    main()
