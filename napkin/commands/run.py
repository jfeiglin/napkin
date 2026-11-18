"""`napkin run`: compile a model, run it in its default configuration, and print the values of named
paths at chosen times (docs/cli.md).

The default run of a model is a median run to the horizon of its scenario line
(`napkin.model.compile`); `napkin.engine.run` gives its record and `napkin.engine.read` the values,
each in its declared unit. The command prints the value of each path of `--value`, or of every named
value of the model in the order of the file (a flow's actual rate, request and capacity under its
line), at each time of `--at`, or at the start and at the horizon. A number has six significant
figures, a yes/no is `true` or `false`, and a value that cannot be evaluated is `unavailable`, with
its reason under the table. `--json` prints one JSON document instead: the model, its title, the
times in hours and, for each path, its unit, its label and its values, each number in full and
`{"unavailable": reason}` for a value that has none.

A model that does not compile, or that the engine does not run yet, prints each problem
(`file:line:column: error: message [code]`) and exits 1. A run that stops prints the values up to
the time at which it stopped, then why, and exits 1. A path or a time that the model does not have
is a usage error (exit 2).
"""

import sys

from . import common

SUMMARY = 'run a model and print the values of named paths at chosen times'

DESCRIPTION = """\
Compile a model and run it in its default configuration: a median run to the horizon of its
scenario line. Print each named value (or each of --value) at the start and the horizon (or at
each of --at). Exit 0 ok, 1 diagnostics, 2 usage."""

EXAMPLES = """\
examples:
  napkin run examples/piano_tuners
  napkin run examples/piano_tuners --value tunings_done,tuners.due --at 0h,6months,1year"""

# The fields of a flow that a run records, in the order in which they are listed.
FLOW_FIELDS = ('actual_rate', 'request', 'capacity')


def configure(parser):
    """The description, the examples and the arguments of `napkin run`: `args.at` and `args.value`
    (lists of texts, each a list with commas; empty when not given), `args.json` (True or False) and
    `args.model`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    parser.add_argument(
        '--at',
        action='append',
        default=[],
        metavar='TIMES',
        help='the times, each a number and a unit of time of the model: --at 2h,160min (default: the '
        'start and the horizon)',
    )
    parser.add_argument(
        '--value',
        action='append',
        default=[],
        metavar='PATHS',
        help='the paths of the values: --value tank.water,clinic.delivery.actual_rate (default: every '
        'named value)',
    )
    parser.add_argument('--json', action='store_true', help='print one JSON document')
    common.add_model(parser)


def main(args):
    """Compile, run and print what the arguments ask; give the exit code."""
    entry = common.entry_of(args.model)
    try:
        model = common.compiled(entry)
        record = recorded(model, entry)
    except common.Failed as failed:
        if not args.json:
            raise
        common.write_json(
            {'model': common.shown(entry), 'diagnostics': list(map(common.problem_json, failed.problems))},
            sys.stdout,
        )
        return 1
    times = common.times_of(model, args.at)
    paths = chosen(named(model, record), args.value)
    stop = None if record.failure is None else float(record.failure.t)
    times = [(text, t) for text, t in times if stop is None or t <= stop]
    readings = read(model, record, paths, times)
    stopped = [] if stop is None else [stopped_at(record.failure, entry)]
    if args.json:
        common.write_json(document(model, entry, times, readings, stopped), sys.stdout)
        return 1 if stopped else 0
    horizon = common.number(float(model.configuration.request.horizon))
    print(f'{model.declared.scenario.title}: a median run to {horizon} h')
    if times:
        rows = [['', 'unit', *(text for text, _ in times)]]
        rows += [[path, unit, *map(cell, values)] for path, unit, _, values in readings]
        for row in common.table(rows):
            print(row)
    for path, _, _, values in readings:
        for (text, _), value in zip(times, values):
            if unavailable(value):
                print(f'{path} at {text}: unavailable: {value.reason}')
    sys.stdout.flush()
    if stopped:
        raise common.Failed(stopped)
    return 0


def recorded(model, entry):
    """The record of the default run of a compiled model (`napkin.engine.run`). A part that the
    engine does not run yet, and a configuration that the program cannot take, are a Failed."""
    from ..engine import run
    from ..engine.timeline import Outside
    from ..program.config import ConfigurationError

    try:
        return run(model.program, model.configuration)
    except Outside as error:
        raise common.Failed(
            [common.problem('later_slice', f'the engine does not run this yet: {error}', entry)]
        ) from None
    except ConfigurationError as error:
        raise common.Failed([common.problem('configuration', error, entry)]) from None


def named(model, record):
    """The path of every named value of a model that its record holds, in the order of the file: each
    value of an entity and of the top level, and each recorded field of a flow under its line."""
    from ..engine.timeline.plan import name_of
    from ..model.semantic import DeclaredFlow

    declared = model.declared
    parts = sorted(
        [*(part for entity in declared.entities for part in entity.parts), *declared.root],
        key=lambda part: part.line,
    )
    written = []
    for part in parts:
        if isinstance(part, DeclaredFlow):
            written += [f'{part.path}.{field}' for field in FLOW_FIELDS]
        else:
            written.append(part.path)
    held = [name_of(history.key) for history in record.histories]
    found = [path for path in written if path in held]
    return found + [path for path in held if path not in found]


def chosen(paths, items):
    """The paths of the `--value` items (each a list with commas), each once, in the order given; all
    of `paths` with no item. A path that names no value of the model is a UsageError, with the
    closest paths."""
    if not items:
        return paths
    found = []
    for path in (piece.strip() for text in items for piece in text.split(',')):
        if path not in paths:
            raise common.UsageError(
                f'--value {path}: no named value of the model' + common.close(path, paths)
            )
        if path not in found:
            found.append(path)
    return found


def read(model, record, paths, times):
    """[(path, unit, label, values)] of the paths at the times (`napkin.engine.read`). The label is
    the first text of the declared part (of the flow, for a field of a flow), or None."""
    from ..engine import read

    declared = model.declared
    found = []
    for reading in read(record, model.program, paths, [t for _, t in times]):
        part = declared.part(reading.path) or declared.part(reading.path.rpartition('.')[0])
        found.append((reading.path, reading.unit, getattr(part, 'text', None), reading.values))
    return found


def stopped_at(failure, entry):
    """The diagnostic of a run that stopped: when, and why."""
    message = failure.detail('message') or 'the run failed'
    return common.problem('run', f'the run stops at {common.number(float(failure.t))} h: {message}', entry)


def unavailable(value):
    """Whether a value read from a record is `Unavailable` (D7)."""
    from ..program.record import Unavailable

    return isinstance(value, Unavailable)


def cell(value):
    """A value as the table shows it."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return 'unavailable' if unavailable(value) else common.number(value)


def document(model, entry, times, readings, stopped):
    """The JSON document of `--json` (see the module)."""

    def shown(value):
        return {'unavailable': value.reason} if unavailable(value) else value

    return {
        'model': common.shown(entry),
        'title': model.declared.scenario.title,
        'mode': model.configuration.mode,
        'horizon': float(model.configuration.request.horizon),
        'times': [t for _, t in times],
        'values': {
            path: {'unit': unit, 'label': label, 'values': [shown(value) for value in values]}
            for path, unit, label, values in readings
        },
        'diagnostics': [common.problem_json(item) for item in stopped],
    }
