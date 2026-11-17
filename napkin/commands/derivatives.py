"""`napkin derivatives`: the derivative of each outcome of one run by each input (docs/cli.md).

The command reads the TARGET, compiles the hybrid core of its model (a model with no table is its
own core) and makes the report of the derivatives of one run
(`napkin.engine.timeline.derivatives.report`): the run that `--run` names, or the only run of the model.
For each outcome it prints its value at the end of the run, and for each input the derivative of
the outcome by that input, with its unit and its class. A class that is not `smooth` or
`structurally zero` has its reason under the line. `--input` names the inputs (default: every
input). `--json` prints the report as JSON instead.

Exit codes: 0 when the report is made, 1 when the model does not compile or the run stops, 2 for
a command line that is wrong.
"""

import sys

from . import common

SUMMARY = 'give the derivative of each outcome of a run by each input, with its kind'

DESCRIPTION = """\
Run one run of a scenario and print the derivative of each outcome at the end of the run by each
input, for one unit of the input as the file writes it. Each derivative has a class: smooth,
one-sided (true for changes to one side), undefined, unsupported (the engine carries no derivative
through a part of the run, which it names) or structurally zero (the input cannot reach the
outcome). Exit 0 ok, 1 diagnostics."""

EXAMPLES = """\
examples:
  napkin derivatives examples/reservoir
  napkin derivatives examples/piano_tuners --run base --input tuners.staff --json"""


def configure(parser):
    """The description, the examples and the arguments of `napkin derivatives`: `args.variant`,
    `args.run` (a name, or None), `args.input` (a list, empty when not given), `args.json` (True or
    False) and `args.target`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    common.add_variant(parser)
    parser.add_argument('--run', metavar='NAME', help='the run (needed when the model has several)')
    parser.add_argument(
        '--input',
        action='append',
        default=[],
        metavar='NAME',
        help='an input to take the derivatives by, e.g. --input service.rate (repeatable; default every input)',
    )
    parser.add_argument('--json', action='store_true', help='print the report as JSON')
    common.add_target(parser)


def main(args):
    """Make the report that the arguments name and print it; give the exit code."""
    from ..engine import timeline
    from ..engine.errors import SimulationError
    from ..engine.timeline import derivatives
    from ..model import hybrid

    target = common.one_target(args.target, args.variant)
    run = common.the_run(target, args.run)
    with common._read(target):
        core = hybrid.compile(target.entry)
    try:
        plan = timeline.Plan.of(core, run)
    except timeline.Outside as problem:
        raise common.Failed(
            [{'message': f'The engine does not run this part of the model: {problem}'}]
        ) from None
    names = list(dict.fromkeys(args.input))
    for name in names:
        if name not in plan.parameter_scale:
            close = common._close(name, sorted(plan.parameter_scale))
            raise common.UsageError(f'{name} is no input of the model{close}')
    try:
        report = derivatives.report(plan, None, names or None)
    except (SimulationError, timeline.Outside) as problem:
        raise common.Failed([{'message': str(problem), 'run': run}]) from None
    if args.json:
        common.write_json({'run': run, **report}, sys.stdout)
        return 0
    show(run, report)
    return 0


def show(run, report):
    """Print a report: each outcome with its value, and under it each input with the derivative of
    the outcome by it, the unit and the class; then the reason of each class that has one."""
    print(f'run {run}: the derivative of each outcome at the end of the run, by each input')
    for output, row in report['derivatives'].items():
        value = report['outputs'][output]
        print()
        print(f'{value["label"] or output}: {value["value"]:.6g} {value["unit"]}')
        width = max((len(name) for name in row), default=0)
        for name, item in row.items():
            number = 'none' if item['value'] is None else f'{item["value"]:.6g}'
            print(f'  by {name:<{width}}  {number:>12}  {item["unit"]}  [{item["class"]}]')
            for reason in item['why']:
                print(f'  {"":<{width + 3}}  {reason}')
    for output in report['unestimated']:
        print()
        print(f'{output}: not estimated')
    if report['unsupported'] is not None:
        print()
        print(f'note: the engine carries no derivative through a part of this run: {report["unsupported"]}')
    sys.stdout.flush()
