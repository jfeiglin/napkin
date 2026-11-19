"""`napkin run`: compile a model, run one of its runs, and print the report of named paths at chosen
times (docs/cli.md).

The run is the model's default run, a median run to the horizon of its scenario line, or the named
run of `--run NAME`, under the edit document of `--edits FILE` (`Compiled.configure`, which checks
the document whole). `napkin.engine.run` gives its record, and the report reads it
(`napkin.engine.report.report`, D10): the value of each path of `--value`, or of every named value
of the model in the order of the file (a status display with its entity's values; a flow's actual
rate, request and capacity under its line, a route's then those of its legs `forward` and
`backward`, a flow with legs' `served_fraction` then each leg's), at each time of `--at`, or at the
start and at the horizon, each in its declared unit, with its label; a row whose path names a member
with a title gives the title in brackets (`dc.demand (DC Water)`). The values of an occurrence
(`tank.deliver#0.pipe.request`, the first start of `tank.deliver`) are not in that list, as a run can
start many: `--value` names them, and before its start such a value is `unavailable`.

Under the table come, in this order:

- each reporting lag of `--lag PATH=FROM..TO` (`--lag unserved_volume=2h..6h`, or one delay): the
  path's values are the mean of its history from TO to FROM before each time, and the line gives
  the proof that it never falls. A path that can fall keeps its plain read, and a warning gives the
  reason (spec, "Formulas and the values a caller can read");
- the text of each case of a status display that the table shows, with its times: its rating is in
  the table, and two cases of one rating keep their own texts;
- the reason of each value that is unavailable;
- each near-tie of the run: a firing or a test that it decided within tolerance of its boundary,
  which the engine detects and does not compute more precisely (change 10).

How a value shows. A number has six significant figures, a yes/no is `true` or `false`, a link the
name of the member it names, an enum its member. A number at most the run's absolute tolerance from
0, `atol_factor` (1e-10) times the largest magnitude of its history, shows as `0`: the run resolves
no smaller difference of it, and an integration or a solver leaves such residues where the answer
is 0 (`4.05538e-26`). A unit that composes names shows as the name that the model's table of units
gives the same dimension and scale (`Wh/h` as `W`), so the number is the record's number in either
(`common.unit_shown`). `--json` prints one JSON document instead: the model, its title, the run and
the edits, the times in hours and, for each path, its unit, its label, its member's title, its
values as the record holds them (`{"unavailable": reason}` for a value that has none, `{"rating",
"text", "case"}` for a status display), its lag and its note, and its evidence trail (with the
settings of the options that the run takes); the records that the trails cite; the near-ties; why
the run stopped; the diagnostics; and every warning of the model, with its place (`warnings`: the
text gives the parts that rest on no record as one line that counts them, `common.warn`).

The run goes through the run store (`napkin.store`): a run that the store holds is read, not run
again; `NAPKIN_STORE=off` turns it off.

A model that does not compile, or that the engine does not run, prints each problem
(`file:line:column: error: message [code]`) and exits 1, and so does an edit document that does not
hold. A run that stops prints the values up to the time at which it stopped, then why, and exits 1.
A path, a run or a time that the model does not have is a usage error (exit 2).
"""

import sys

from . import common

SUMMARY = 'run a model and print the values of named paths at chosen times'

DESCRIPTION = """\
Compile a model and run it: its default run, a median run to the horizon of its scenario line, or
the run --run names, under the edits of --edits FILE. Print each named value (or each of --value)
at the start and the horizon (or at each of --at). Exit 0 ok, 1 diagnostics, 2 usage."""

EXAMPLES = """\
examples:
  napkin run examples/piano_tuners
  napkin run examples/piano_tuners --value tunings_done,tuners.due --at 0h,6months,1year
  napkin run examples/piano_tuners --value tunings_done --lag tunings_done=1month..2months"""

# The fields of a flow that a run records, in the order in which they are listed; a route records
# them, then those of its two legs, which read the positive part of its rate and its request.
FLOW_FIELDS = ('actual_rate', 'request', 'capacity')
ROUTE_LEGS = ('forward', 'backward')
ROUTE_LEG_FIELDS = ('actual_rate', 'request')


def configure(parser):
    """The description, the examples and the arguments of `napkin run`: `args.run` (None when not
    given), `args.edits` (a path, or None), `args.at`, `args.value` and `args.lag` (lists of texts,
    `--at` and `--value` each a list with commas; empty when not given), `args.json` (True or False)
    and `args.model`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    parser.add_argument('--run', metavar='NAME', help='the named run (default: the default run)')
    parser.add_argument('--edits', metavar='FILE', help='an edit document of the inputs (JSON)')
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
    parser.add_argument(
        '--lag',
        action='append',
        default=[],
        metavar='PATH=FROM..TO',
        help='report PATH as the mean of its history from TO to FROM before each time, when it never '
        'falls: --lag unserved_volume=2h..6h (repeatable)',
    )
    parser.add_argument('--json', action='store_true', help='print one JSON document')
    common.add_model(parser)


def main(args):
    """Compile, run and report what the arguments ask; give the exit code."""
    entry = common.entry_of(args.model)
    try:
        model = common.compiled(entry)
        edits = common.edits_of(model, args.edits)
        configuration = common.configured(model, args.run, edits, args.edits)
        record = recorded(model.program, configuration, entry)
    except common.Failed as failed:
        if not args.json:
            raise
        common.write_json(
            {'model': common.shown(entry), 'diagnostics': list(map(common.problem_json, failed.problems))},
            sys.stdout,
        )
        return 1
    horizon = float(configuration.request.horizon)
    times = common.times_of(model, args.at, horizon)
    known = held(record)
    lags = lags_of(model, args.lag, known)
    paths = chosen(named(model, record), known, args.value)
    paths += [path for path in lags if path not in paths]
    found = reported(model, record, configuration, paths, times, lags, options_of(model, args.run))
    # The times after the run stopped hold nothing: the table ends there, and `stopped` says why.
    times = [(text, t) for text, t in times if t <= found.end]
    stopped = [] if found.stopped is None else [common.problem('run', found.stopped, entry)]
    refused = [
        common.problem('lag', value.note)
        for value in found.values
        if value.path in lags and value.lag is None and value.note is not None
    ]
    if args.json:
        doc = document(model, entry, args, configuration, times, found, stopped)
        common.write_json(doc, sys.stdout)
        return 1 if stopped else 0
    for item in refused:
        sys.stderr.write(common.located(item, 'warning') + '\n')
    sys.stderr.flush()
    print(heading(model, args, horizon))
    for line in lines(model, record, configuration, times, found):
        print(line)
    sys.stdout.flush()
    if stopped:
        raise common.Failed(stopped)
    return 0


def recorded(program, configuration, entry):
    """The record of a run of a program, through the run store (`napkin.store.run`, `common.stored`):
    the stored record when one covers the run, else a new run. A part that the engine does not run,
    and a configuration that the program cannot take, are a Failed."""
    from .. import store
    from ..engine.timeline import Outside
    from ..program.config import ConfigurationError

    common.stored()
    try:
        return store.run(program, configuration)
    except Outside as error:
        raise common.Failed(
            [common.problem('engine', f'the engine does not run this: {error}', entry)]
        ) from None
    except ConfigurationError as error:
        raise common.Failed([common.problem('configuration', error, entry)]) from None


def held(record):
    """The path of every value that a record holds, an occurrence's included, in its order."""
    from ..engine.timeline.plan import name_of

    return [name_of(history.key) for history in record.histories]


def named(model, record):
    """The path of every named value of a model that its record holds, in the order of the file: each
    value of an entity and of the top level, an entity's status display, and each recorded field of a
    flow under its line; then the other values that it holds (of the members of a table), but not
    those of an occurrence."""
    from ..model.semantic import DeclaredFlow, DeclaredLegs, DeclaredRoute

    declared = model.declared
    parts = sorted(
        [
            *(part for entity in declared.entities for part in entity.parts),
            *(entity.status for entity in declared.entities if entity.status is not None),
            *declared.root,
        ],
        key=lambda part: part.line,
    )
    written = []
    for part in parts:
        if isinstance(part, DeclaredLegs):
            written.append(f'{part.path}.served_fraction')
            written += [f'{leg.path}.{field}' for leg in part.legs for field in FLOW_FIELDS]
        elif isinstance(part, DeclaredFlow):
            written += [f'{part.path}.{field}' for field in FLOW_FIELDS]
            if isinstance(part, DeclaredRoute):
                written += [f'{part.path}.{leg}.{field}' for leg in ROUTE_LEGS for field in ROUTE_LEG_FIELDS]
        else:
            written.append(part.path)
    kept = held(record)
    found = [path for path in written if path in kept]
    return found + [path for path in kept if path not in found and '#' not in path]


def chosen(paths, known, items):
    """The paths of the `--value` items (each a list with commas), each once, in the order given; all
    of `paths` with no item. A path that names no value of `known` is a UsageError, with the closest
    paths."""
    if not items:
        return list(paths)
    found = []
    for path in (piece.strip() for text in items for piece in text.split(',')):
        if path not in known:
            raise common.UsageError(
                f'--value {path}: no named value of the model' + common.close(path, known)
            )
        if path not in found:
            found.append(path)
    return found


def lags_of(model, items, known):
    """{path: `Lag`} of the `--lag PATH=FROM..TO` items, in the order given: a window from the shorter
    delay to the longer (`2h..6h`), or one delay (`3h`), each a number and a unit of time. A path
    that names no value of `known`, a path given twice and a window that is not one are a
    UsageError."""
    from ..engine.report import Lag

    found = {}
    for item in items:
        path, separator, window = (piece.strip() for piece in item.partition('='))
        if not separator or not path or not window:
            raise common.UsageError(f'--lag takes PATH=FROM..TO, such as tank.water=2h..6h, not {item!r}')
        if path not in known:
            raise common.UsageError(f'--lag {path}: no named value of the model' + common.close(path, known))
        if path in found:
            raise common.UsageError(f'--lag gives {path} twice')
        ends = [common.hours(model, end.strip(), '--lag')[1] for end in window.split('..')]
        if len(ends) > 2 or not 0 <= ends[0] <= ends[-1]:
            raise common.UsageError(
                f'--lag {item}: give one delay, or a window from the shorter delay to the longer, '
                'such as 2h..6h'
            )
        found[path] = Lag(ends[0], ends[-1])
    return found


def options_of(model, run):
    """The names of the options that the run `run` of a compiled model takes (none for the default
    run), whose settings the evidence trails cite (`napkin.model.runs.options_of`)."""
    from ..model.runs import options_of

    return options_of(model.declared, run)


def reported(model, record, configuration, paths, times, lags, options=()):
    """The report of the paths at the times (`napkin.engine.report.report`), with the texts and the
    evidence of the declared model, under the options that the run takes."""
    from ..engine.report import report

    return report(
        record,
        model.program,
        configuration,
        paths,
        [t for _, t in times],
        lags,
        model=model.declared,
        options=options,
    )


def heading(model, args, horizon):
    """The first line: the title, the run and its edits."""
    run = f'the run {args.run}, ' if args.run is not None else ''
    edits = f', with the edits of {common.shown(args.edits)}' if args.edits is not None else ''
    return f'{model.declared.scenario.title}: {run}a median run to {common.number(horizon)} h{edits}'


def lines(model, record, configuration, times, found):
    """The table of the report, then what comes under it (see the module)."""
    from ..engine.report import Shown

    shown = []
    if times:
        rows = [['', 'unit', *(text for text, _ in times)]]
        for value in found.values:
            floor = floor_of(record, model.program, value, configuration.numerics.atol_factor)
            cells = [cell(item, floor) for item in value.values[: len(times)]]
            rows.append([row_name(value), common.unit_shown(model.declared.units, value.unit), *cells])
        shown += common.table(rows)
    for value in found.values:
        if value.lag is not None:
            shown.append(
                f'{row_name(value)}: the mean of its history from {common.number(value.lag.longest)} h to '
                f'{common.number(value.lag.shortest)} h before each time; it never falls: {value.note}'
            )
    for value in found.values:
        cases = {}
        for (text, _), item in zip(times, value.values):
            if isinstance(item, Shown):
                cases.setdefault(item, []).append(text)
        for item, at in cases.items():
            words = f': {item.text}' if item.text else ''
            shown.append(f'{value.path} at {", ".join(at)}: {item.rating}{words}')
    for value in found.values:
        for (text, _), item in zip(times, value.values):
            if unavailable(item):
                shown.append(f'{value.path} at {text}: unavailable: {item.reason}')
    shown += [f'near-tie: {tie.message}' for tie in found.near_ties]
    return shown


def row_name(value):
    """The name of a row: its path, with the title of its member in brackets when it has one
    (`dc.demand (DC Water)`), and its lag when it has one (`s.finished (lag 2 h..6 h)`)."""
    name = f'{value.path} ({value.title})' if value.title else value.path
    if value.lag is None:
        return name
    lag = value.lag
    if lag.shortest == lag.longest:
        return f'{name} (lag {common.number(lag.shortest)} h)'
    return f'{name} (lag {common.number(lag.shortest)} h..{common.number(lag.longest)} h)'


def floor_of(record, program, value, factor):
    """The magnitude at or below which a number of a reported value shows as 0 (see the module):
    `factor` times the largest magnitude of its history in the record and of its reported numbers,
    in its declared unit. The history's pieces give their values at both ends (a line's end is its
    value plus its rate over the piece)."""
    from ..engine.timeline.record import key_of, unit_of

    key = key_of(program, value.path)
    _, scale = unit_of(program, key)
    largest = max((abs(item) for item in value.values if number_like(item)), default=0.0) * scale
    try:
        pieces = record.history(key).pieces
    except KeyError:
        pieces = ()
    ends = [*(piece.t for piece in pieces[1:]), record.manifest.horizon]
    for piece, end in zip(pieces, ends):
        if number_like(piece.value):
            largest = max(largest, abs(piece.value), abs(piece.value + piece.rate * (end - piece.t)))
    return factor * float(largest) / scale


def number_like(value):
    """Whether a value is a number: not a yes/no, a text, a status display or `Unavailable`."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def unavailable(value):
    """Whether a value read from a record is `Unavailable` (D7)."""
    from ..program.record import Unavailable

    return isinstance(value, Unavailable)


def cell(value, floor=0.0):
    """A value as the table shows it: a number at most `floor` from 0 as `0` (see the module)."""
    from ..engine.report import Shown

    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, str):  # a link: the name of the member that it names; an enum: its member
        return value
    if isinstance(value, Shown):
        return value.rating
    if unavailable(value):
        return 'unavailable'
    return '0' if abs(value) <= floor else common.number(value)


def document(model, entry, args, configuration, times, found, stopped):
    """The JSON document of `--json` (see the module)."""
    from ..engine.report import Shown

    def shown(value):
        if unavailable(value):
            return {'unavailable': value.reason}
        if isinstance(value, Shown):
            return {'rating': value.rating, 'text': value.text, 'case': value.case}
        return value

    def lag(value):
        return None if value.lag is None else {'shortest': value.lag.shortest, 'longest': value.lag.longest}

    def trail(value):
        return [
            {
                'kind': used.kind,
                'origin': used.origin,
                'owner': used.owner,
                'records': list(used.records),
                'exercised': used.exercised,
                'why': used.why,
            }
            for used in value.trail
        ]

    return {
        'model': common.shown(entry),
        'title': model.declared.scenario.title,
        'run': args.run,
        'edits': common.shown(args.edits) if args.edits is not None else None,
        'mode': configuration.mode,
        'horizon': float(configuration.request.horizon),
        'times': [t for _, t in times],
        'values': {
            value.path: {
                'unit': common.unit_shown(model.declared.units, value.unit),
                'label': value.label,
                'title': value.title,
                'values': [shown(item) for item in value.values[: len(times)]],
                'lag': lag(value),
                'note': value.note,
                'trail': trail(value),
            }
            for value in found.values
        },
        'records': [{'name': name, 'kind': kind, 'text': text} for name, kind, text in found.records],
        'near_ties': [
            {
                't': tie.t,
                'kind': tie.kind,
                'part': tie.part,
                'owner': tie.owner,
                'comparison': tie.comparison,
                'difference': tie.difference,
                'tolerance': tie.tolerance,
                'message': tie.message,
            }
            for tie in found.near_ties
        ],
        'stopped': found.stopped,
        'diagnostics': [common.problem_json(item) for item in stopped],
        'warnings': [common.problem_json(item) for item in model.reports],
    }
