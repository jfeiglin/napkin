"""The command of the benchmark: python -m tools.bench (the contract is in `tools/bench/__init__.py`)."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from tools import bench
from tools.catalogue import ROOT
from tools.check import positive_integer

from . import measure
from .families import FAMILIES
from .workloads import RUNS, workloads

# The variables that set the threads of the linear algebra: the document says what each one was.
THREADS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')


def positive_seconds(text):
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('must be a positive number of seconds') from exc
    if not 0 < value < float('inf'):
        raise argparse.ArgumentTypeError('must be a positive number of seconds')
    return value


def size_list(text):
    """The sizes of `--sizes`: whole numbers from 1, with commas between them."""
    try:
        return [positive_integer(part) for part in text.split(',')]
    except argparse.ArgumentTypeError as exc:
        raise argparse.ArgumentTypeError('must be positive integers with commas between them') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='python -m tools.bench',
        description=bench.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--scenario',
        action='append',
        metavar='ID',
        help='Measure this scenario of the catalogue (repeatable); a package with variants gives each variant',
    )
    parser.add_argument(
        '--runs', choices=RUNS, default='first', help='The runs of each model: its first run (default) or all'
    )
    parser.add_argument('--example', action='store_true', help='Measure each examples/*/model.scn')
    parser.add_argument(
        '--family',
        action='append',
        choices=tuple(FAMILIES),
        metavar='NAME',
        help=f'Measure this synthetic family (repeatable): {", ".join(FAMILIES)}',
    )
    parser.add_argument(
        '--sizes',
        type=size_list,
        default=[10, 40],
        metavar='N,N',
        help='The sizes of each family (default: 10,40)',
    )
    parser.add_argument(
        '--repeats',
        type=positive_integer,
        default=3,
        metavar='N',
        help='Warm runs of each workload (default: 3)',
    )
    parser.add_argument(
        '--samples',
        type=positive_integer,
        metavar='N',
        help='Also run a Monte Carlo study of N samples of each workload (default: none)',
    )
    parser.add_argument(
        '--survey',
        action='store_true',
        help='Also time one warm run of each run of each model, in the process of its warm runs',
    )
    parser.add_argument(
        '--jobs',
        type=positive_integer,
        default=1,
        metavar='N',
        help='The processes of the Monte Carlo study (default: 1, the samples in one process)',
    )
    parser.add_argument(
        '--timeout',
        type=positive_seconds,
        default=600,
        metavar='SECONDS',
        help='The time limit of each process of a measurement (default: 600)',
    )
    parser.add_argument('--out', type=Path, metavar='FILE', help='Write the result document to this file')
    # The process of one measurement runs this (`measure.isolated`).
    parser.add_argument('--measure', help=argparse.SUPPRESS)
    parser.add_argument('--result', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.measure:
        return measure.child(args.measure, args.result)

    settings = {
        'scenarios': list(args.scenario or ()),
        'runs': args.runs,
        'examples': args.example,
        'families': list(args.family or ()),
        'sizes': list(args.sizes),
        'repeats': args.repeats,
        'samples': args.samples,
        'jobs': args.jobs,
        'survey': args.survey,
        'timeout': args.timeout,
        'threads': {name: os.environ.get(name) for name in THREADS},
    }
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='napkin-bench-') as folder:
        try:
            selected = workloads(
                ROOT,
                scenarios=settings['scenarios'],
                examples=args.example,
                families=settings['families'],
                sizes=args.sizes,
                runs=args.runs,
                folder=folder,
            )
        except ValueError as exc:
            parser.error(str(exc))
        if not selected:
            parser.error('nothing to measure: give --scenario ID, --example or --family NAME')
        print(f'Measure {len(selected)} workloads, each measurement in a process of its own:', flush=True)
        records = measure.bench(
            selected,
            repeats=args.repeats,
            samples=args.samples,
            jobs=args.jobs,
            survey=args.survey,
            timeout=args.timeout,
            say=lambda line: print(line, flush=True),
        )
    document = measure.document(records, settings)
    print()
    print(measure.table(document))
    print(f'({time.monotonic() - started:.0f} s)')
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'The result document is in {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
