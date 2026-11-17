"""`napkin run`: run a scenario's runs and print their outcomes (docs/cli.md).

The command reads the TARGET, compiles its model and runs one study: every run, or each `--run`
(D-30: the model is then checked for those runs only, and the output says so). Before the model
compiles, each `--run` must name a run that the files declare (`common.check_runs`). `--option` puts
options into each run in place of its own (`napkin.package.combined`, which checks the combination
and the edit document), one study for each run, and the reports merge into one. The engine does
every check; this command prints what the report holds: for each run, each outcome with its value
and unit at the end of the run and at each `--at` time, or why it has no value; with `--events`,
the events and their times; and the warnings of the study. `--json` prints the report as JSON
instead (`common.compact`).

Exit codes: 0 when the study is admitted, 1 when the model does not compile or the study is
rejected, 2 for a command line that is wrong.
"""

import sys
from pathlib import Path

from . import common

SUMMARY = "run a scenario's runs and print their outcomes"

DESCRIPTION = """\
Compile a scenario and run its runs: every run, or each --run. Print each outcome at the end of the
run, with its unit and its status. With --run, the model is checked for those runs only; `napkin
compile` checks every run. Exit 0 ok, 1 diagnostics."""

EXAMPLES = """\
examples:
  napkin run examples/piano_tuners
  napkin run scenarios/water_controls_wipe --variant juneau --run early_kept --option "Delayed response\""""

# What a report gives in place of the value of an outcome that has none: never a number.
NO_VALUE = {'unestimated': 'not estimated', 'not_applicable': 'not applicable'}


def configure(parser):
    """The description, the examples and the arguments of `napkin run`: `args.variant`; `args.run`,
    `args.option` and `args.set` (lists, empty when not given); `args.at` (the text, or None);
    `args.edits` (a Path, or None); `args.events` and `args.no_store` (True or False); `args.json`
    (None, `compact` or `full`: `cli.main` gives `--json` its value before it parses, so the flag never
    takes the TARGET); and `args.target`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    common.add_variant(parser)
    parser.add_argument(
        '--run',
        action='append',
        default=[],
        metavar='NAME',
        help='run only this run (repeatable; default every run)',
    )
    parser.add_argument(
        '--option',
        action='append',
        default=[],
        metavar='[GROUP=]OPTION',
        help='put this option into the run in place of its group\'s choice, e.g. --option "Delayed response"; '
        'the combination is checked when asked (repeatable)',
    )
    parser.add_argument(
        '--set',
        action='append',
        default=[],
        metavar='NAME=VALUE',
        help='give an input a value in its own unit for every run: --set tuners.rate=4, --set plan=fast '
        '(a word is text; otherwise JSON)',
    )
    parser.add_argument(
        '--at',
        metavar='TIME,…',
        help='also give every output at these times, e.g. --at 24h,7days (default: only at the end of the run)',
    )
    parser.add_argument('--edits', type=Path, metavar='FILE', help='apply an edit document (docs/cli.md)')
    parser.add_argument('--events', action='store_true', help="print each run's events and their times")
    parser.add_argument(
        '--rows',
        metavar='NAME,…',
        help='for a model with a table: the rows whose own events and health the report gives, '
        'e.g. --rows sites_3,sites_40 (the others are counted by group)',
    )
    parser.add_argument(
        '--json',
        nargs='?',
        const='compact',
        choices=('compact', 'full'),
        metavar='full',
        help='print the report as JSON (schema 0.0.1): outcomes, statuses and events; `full` adds the trace, '
        'the index and the evidence',
    )
    parser.add_argument(
        '--no-store',
        action='store_true',
        help='neither read nor write the run store (or set NAPKIN_STORE=off)',
    )
    common.add_target(parser)


def main(args):
    """Run the study that the arguments name and print its report; give the exit code."""
    target = common.one_target(args.target, args.variant)
    runs = list(dict.fromkeys(args.run)) or None
    core, why = common.table_core(target)
    # A value of an input, an option and an edit document are not for the groups of a table yet:
    # with one of them, a model with a table runs as before, with each row written out.
    given = (('--option', args.option), ('--set', args.set), ('--edits', args.edits))
    edited = next((flag for flag, value in given if value), None)
    if core is not None and edited is None:
        return run_table(args, target, core, runs)
    if core is not None:
        why = f'{edited} is not for the groups of a table yet'
    if args.rows:
        reason = f'with {edited}, the model runs' if core is not None else 'this model runs'
        raise common.UsageError(
            f'--rows names rows of a table that the model runs by group: {reason} with each row written out'
        )
    if why:
        # The note is no part of a JSON document: with --json it goes to the standard error.
        note = f'note: this model runs with each row of its table written out: {why}'
        print(note, file=sys.stderr if args.json is not None else sys.stdout)
    settings = common.parse_set(args.set)
    model = load(target, runs)
    options = common.parse_options(model, args.option)
    times = common.parse_times(model, args.at) if args.at is not None else []
    edits = common.read_edits(model, args.edits, settings)
    common.use_store(not args.no_store)
    report = study_report(model, runs, options, edits, [t for _, t in times])
    if args.json is not None:
        full = args.json == 'full'
        doc = common.compact(
            report, full=full, index=model.index if full else None, admitted=model.admission_runs
        )
        common.write_json(doc, sys.stdout)
        return 0 if report['admissible'] else 1
    note = common.scope_note(model)
    if note:
        print(f'note: {note}')
    if not report['admissible']:
        sys.stdout.flush()
        sys.stderr.write('The study is rejected:\n')
        common.show_diagnostics(report['diagnostics'], sys.stderr)
        return 1
    for k, (name, run) in enumerate(report['runs'].items()):
        if k:
            print()
        show_run(name, run, times, events=args.events)
    sys.stdout.flush()
    common.show_diagnostics(report['diagnostics'], sys.stderr)
    return 0


def run_table(args, target, core, runs):
    """`napkin run` of a model with a table: the runs of its hybrid core (`timeline/reports.study_of`).
    The outcomes print as those of any model. What the report says of the rows of a table is by
    group (a class of rows that the engine runs as one family): each group with its rows, and with
    `--events` how often each of its events happened. `--rows` names rows whose own events print.
    A run with an option, an edit or a value of an input does not come here (`main`)."""
    from ..engine.timeline import reports

    model = core.model
    names = list(common.check_runs(target, runs)) or list(model.runs)
    times = common.parse_times(model, args.at) if args.at is not None else []
    rows = [name.strip() for name in (args.rows or '').split(',') if name.strip()]
    try:
        report = reports.study_of(core, names, [t for _, t in times], rows)
    except ValueError as exc:
        raise common.UsageError(f'--rows: {exc}') from None
    if args.json is not None:
        common.write_json(compact_table(report, full=args.json == 'full'), sys.stdout)
        return 0 if report['admissible'] else 1
    if not report['admissible']:
        sys.stdout.flush()
        sys.stderr.write('The study is rejected:\n')
        common.show_diagnostics(report['diagnostics'], sys.stderr)
        return 1
    for k, (name, run) in enumerate(report['runs'].items()):
        if k:
            print()
        show_run(name, run, times, events=args.events)
        show_groups(run, events=args.events)
    sys.stdout.flush()
    common.show_diagnostics(report['diagnostics'], sys.stderr)
    return 0


def show_groups(run, *, events=False):
    """Print the groups of the rows of the tables of one run: each group by the row that stands for
    it, with its table and the number of its rows; and, with `events`, how many times each event of
    the group happened, in how many rows, and from when to when."""
    print('  groups of rows:')
    for group in run['groups']:
        print(f'    {group["group"]}: {group["rows"]} rows of {group["set"]}')
        if not events:
            continue
        for item in run['events']:
            if item['group'] != group['group'] or item['outcome'] is None:
                continue
            span = f'at {common.number(item["first"])} h'
            if item['last'] != item['first']:
                span = f'from {common.number(item["first"])} h to {common.number(item["last"])} h'
            print(
                f'      {item["event"]} ({item["outcome"]}): {item["count"]} times in {item["rows"]} rows, {span}'
            )


def compact_table(report, *, full=False):
    """The `--json` document of `napkin run` for a model with a table: what `common.compact` gives of
    each run, with its `groups` and the events of each group (`group_events`); with `full`, also the
    health of the groups at each time and the peaks."""
    from ..model.ir import thaw

    doc = common.compact(report, full=full)
    doc.pop('index', None)
    for name, run in report.get('runs', {}).items():
        shown = doc['runs'][name]
        shown['groups'] = thaw(run['groups'])
        shown['group_events'] = thaw(run['events'])
        if full:
            shown['health'] = thaw(run['health'])
            shown['peaks'] = thaw(run['peaks'])
    return doc


def load(target, runs):
    """The model of `target`, checked for `runs` only, or for every run when `runs` is None or empty
    (`common.load`). Before the model compiles, each run must be one that the files declare
    (`common.check_runs`): any other is a UsageError with the closest names. `napkin draw` loads its
    model the same way."""
    return common.load(target, runs=list(common.check_runs(target, runs)) or None)


def study_report(model, runs, options, edits, times):
    """The report of the study: `evaluate_study(model, edits, runs=runs)` and `sample_result` at
    `times`. With `options`, one study for each run (every run, or each of `runs`) on the model of
    that run with those options (`package.combined`, which checks the edit document on the whole
    model and then the combination), and the reports merged (`common.merged`). A combination or an
    edit document that the engine refuses gives a rejected report with its diagnostics, as a study
    does; no other run starts after it."""
    from ..engine import evaluate_study, sample_result
    from ..engine.study import StudyResult
    from ..model import ModelError
    from ..package import combined

    if not options:
        return sample_result(evaluate_study(model, edits, runs=runs), times)
    reports = []
    for run in runs or list(model.runs):
        try:
            derived, document = combined(model, run, options, edits)
        except ModelError as exc:
            found = [{**item, 'run': item.get('run') or run} for item in exc.diagnostics]
            reports.append(
                sample_result(StudyResult(model.model_hash, False, found, edits or {}, model=model))
            )
            break
        reports.append(sample_result(evaluate_study(derived, document, runs=[run]), times))
        if not reports[-1]['admissible']:
            break
    return common.merged(reports, edits=edits)


def show_run(name, run, times, *, events=False):
    """Print one run of a report: its name and its label, when that is another name (and its options,
    when the label does not name them); a table of each outcome's label and its value with its unit,
    or why it has none, at each time of `times` ([(point, t)], `common.parse_times`) and at the end of
    the run; and, with `events`, each event of the run with its time."""
    options, label = ' · '.join(run['options']), run['label']
    title = name if label in (None, '', name) else f'{name}: {label}'
    print(title + (f' ({options})' if options and options != label else ''))
    points = run['reporting_points']
    end = points['final']['t']
    columns = [(f'at {common.number(t)} h', points[point]) for point, t in times if t != end]
    columns.append((f'at the end ({common.number(end)} h)', points['final']))
    rows = [['', *(head for head, _ in columns)]]
    for outcome, item in run['outcomes'].items():
        rows.append([item['label'] or outcome, *(shown(row, outcome, item['unit']) for _, row in columns)])
    for row in common.table(rows):
        print(f'  {row}'.rstrip())
    if events:
        found = [entry for entry in run['trace'] if entry.get('outcome') is not None]
        print('  events:' if found else '  events: none')
        width = max((len(common.number(entry['t'])) for entry in found), default=0)
        for entry in found:
            text = entry.get('label') or entry['event']
            print(f'    {common.number(entry["t"]):>{width}} h  {text}  ({entry["event"]})')


def shown(row, outcome, unit):
    """The value of an outcome at a reporting point, with its unit; or, for an outcome that the report
    does not estimate, why it has no value."""
    status = row['statuses'].get(outcome)
    value = row['values'].get(outcome)
    if status != 'estimated' or value is None:
        return NO_VALUE.get(status, str(status).replace('_', ' '))
    return f'{common.number(value)} {unit}'
