"""`napkin sample`: run one run many times with drawn inputs, and print the spread of each outcome
(docs/cli.md).

The work is the engine's Monte Carlo study, through `napkin.spread`:

- **The runs.** The run is `--run`, or the only run of the model (`common.the_run`). The command
  samples it with the runs that it is compared with (`versus`, `spread.sampled_runs`), on the same
  draws.
- **The check (D-42).** With `--run X`, the model is checked for X and those runs only, and the
  command says so (`common.scope_note`). The files give those runs before the model compiles
  (`common.declared_runs`), so the model loads once. Without `--run`, the model is checked for every
  run.
- **The inputs.** `--set` and `--edits` give the edit document, as for `napkin run`. The inputs with
  a distribution, in the model or in that document, are drawn. The engine checks the document, and
  each sample, before the first sample runs: a refusal is exit 1 with its diagnostics. A model whose
  runs have no input with a distribution has no spread: the command says so and exits 0.
- **`--option`.** Each sampled run takes the options in place of its own (`package.combined`, which
  checks the whole edit document on the model first). The combination of a run has no comparison,
  so each run takes a spread of its own, with the same seed: the spreads draw the same values.

For each outcome of each run, at the time of `--at` (by default the end of the run), the command
prints the engine's summary (`uncertainty_report`): the mean, the middle 50% (p25 to p75) and the
middle 90% (p5 to p95). It also prints the 1-in-100 value (p99) from 1000 samples and the 1-in-200
value (p99.5) from 2000 samples, so that at least 10 samples lie beyond each (`TAILS`). The engine's
summaries do not hold these: they are type-7 quantiles of the samples' outcome rows. Then come the
inputs that move the outcome most, by the engine's rank correlations (`DRIVERS`), and the chance of
each `--exceed`: the share of the samples above the value, P(X > V) = count / N.

`--json` writes one document (`document`): the envelope of the engine's report, and for each run its
settings, the distribution of each drawn input, the label and unit of each outcome, every sample
(its draws, and the value and status of each outcome) and the summary of each outcome. It names the
inputs as edits name them (`spread.input_id`).
"""

import argparse
import os
import sys
from fractions import Fraction
from pathlib import Path

from . import common

SUMMARY = 'run one run many times with drawn inputs; print the spread of each outcome'

DESCRIPTION = """\
Draw every input that has a distribution (in the model or the edit document) and run the run, and the
run it is compared with (`versus`), on the same draws. For each outcome it prints the mean, the middle
50% and 90%, the 1-in-100 and 1-in-200 values when there are enough samples, and the inputs that
move it most. Invalid inputs are rejected before the first sample. With `--run`, the model is
checked for these runs only; `napkin compile` checks every run."""

EXAMPLES = """\
example:
  napkin sample scenarios/water_controls_wipe --variant washington_dc --run delayed_kept_human \\
    --edits scenarios/water_controls_wipe/variants/washington_dc/spreads/uncertainty.json \\
    --samples 2000 --exceed economic_loss=0.05"""


def count(text):
    """A whole number of 1 or more, for `--samples` and `--jobs`."""
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f'give a whole number of 1 or more, not {text!r}')
    return value


def seed(text):
    """A whole number of 0 or more, for `--seed`."""
    try:
        value = int(text)
    except ValueError:
        value = -1
    if value < 0:
        raise argparse.ArgumentTypeError(f'give a whole number of 0 or more, not {text!r}')
    return value


def configure(parser):
    """The description, the example and the arguments of `napkin sample`: `args.variant` and `args.run`
    (None when not given); `args.option`, `args.set` and `args.exceed` (lists, empty when not given);
    `args.samples` (200 by default), `args.seed` (0) and `args.jobs` (None: the CPU count); `args.at`
    (the text of one time, or None); `args.edits` (a Path, or None); `args.json` (True or False); and
    `args.target`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    common.add_variant(parser)
    parser.add_argument('--run', metavar='NAME', help='the run to sample (default: the only run)')
    parser.add_argument(
        '--option',
        action='append',
        default=[],
        metavar='[GROUP=]OPTION',
        help="put this option into the run in place of its group's choice (repeatable)",
    )
    parser.add_argument(
        '--set',
        action='append',
        default=[],
        metavar='NAME=VALUE',
        help='give an input a value in its own unit (a word is text; otherwise JSON)',
    )
    parser.add_argument(
        '--samples', type=count, default=200, metavar='N', help='the number of samples (default 200)'
    )
    parser.add_argument('--seed', type=seed, default=0, metavar='N', help='the seed of the draws (default 0)')
    parser.add_argument(
        '--jobs', type=count, metavar='N', help='the processes that run the samples (default: CPU count)'
    )
    parser.add_argument('--at', metavar='TIME', help='the spread at this time (default: the end of the run)')
    parser.add_argument(
        '--exceed',
        action='append',
        default=[],
        metavar='NAME=VALUE',
        help='also print the chance that outcome NAME passes VALUE (repeatable)',
    )
    parser.add_argument(
        '--edits',
        type=Path,
        metavar='FILE',
        help='apply an edit document, which can give inputs distributions (docs/cli.md)',
    )
    parser.add_argument(
        '--json', action='store_true', help='every draw and its outcomes, for exceedance curves elsewhere'
    )
    common.add_target(parser)


# The values of the far tail: (percentile, its name). Each shows only when at least BEYOND samples
# lie beyond it (`shown_tails`): from 1000 samples for p99 and from 2000 for p99.5.
TAILS = ((Fraction(99), '1-in-100 value'), (Fraction(199, 2), '1-in-200 value'))
BEYOND = 10
# The inputs that the summary of an outcome names as those that move it most.
DRIVERS = 3


def shown_tails(samples):
    """The percentiles of `TAILS` that `samples` samples show: those beyond which lie at least `BEYOND`
    samples, N · (100 − p) / 100 ≥ BEYOND."""
    return [p for p, _ in TAILS if samples * (100 - p) >= BEYOND * 100]


def tail_key(p):
    """The key of a tail value in the JSON summary: `p99`, `p99.5`."""
    return f'p{int(p) if p.denominator == 1 else float(p)}'


def main(args):
    """`napkin sample` (the module's docstring)."""
    from .. import spread

    target = common.one_target(args.target, args.variant)
    settings = common.parse_set(args.set)
    checked(args)
    declared = common.declared_runs(target)
    if args.run is None and len(declared) > 1:
        # Several runs and no --run: the command lists the runs and stops (`common.the_run`). But when
        # no input of any run has a distribution, in the model or in the edit document, there is no
        # spread to pick a run for, and the command says that first (V8). Only the compiled model
        # knows its distributions, so this case alone compiles the model, for every run, before the
        # files give the listing. Every other case finds its runs in the files and compiles the model
        # once, for those runs only.
        model = common.load(target)
        edits = common.read_edits(model, args.edits, settings)
        if not drawn(model, list(model.runs), edits):
            return nothing(args, target, model, None)
    run = common.the_run(target, args.run)
    if args.run is None:
        # The only run: the model is checked for every run, which is that run.
        model = common.load(target)
    else:
        model = common.load(target, [name for name in declared if name == run or name in declared[run]])
    edits = common.read_edits(model, args.edits, settings)
    options = common.parse_options(model, args.option)
    point, t = at(model, args.at)
    exceed = common.parse_exceed(model, args.exceed)
    runs = spread.sampled_runs(model, run)
    studies = studies_of(model, runs, options, edits)
    if not any(drawn(*study) for study in studies):
        return nothing(args, target, model, runs)
    common.use_store()
    # No more processes than samples: a process beyond them would load the model and run nothing.
    jobs = min(args.jobs if args.jobs is not None else os.cpu_count() or 1, args.samples)
    found = sampled(model, studies, options, args, () if args.at is None else (t,), jobs)
    doc = document(model, found, options, edits, point, t, exceed)
    if args.json:
        common.write_json(doc, sys.stdout)
    else:
        show(sys.stdout, target, model, doc, args)
    return 0


def checked(args):
    """Refuse sampling settings that the engine refuses (`SamplingSettings`), before the model loads."""
    from ..engine import SamplingSettings

    try:
        SamplingSettings(args.samples, args.seed)
    except ValueError as exc:
        raise common.UsageError(f'--samples {args.samples} --seed {args.seed}: {exc}') from None


def at(model, text):
    """(the reporting point, its time in hours) of `--at`: the end of the run by default."""
    if text is None:
        return 'final', float(model.time['horizon'])
    return common.parse_times(model, text, many=False)[0]


def studies_of(model, runs, options, edits):
    """[(the model of a spread, its runs, its edit document)]: one spread of `runs` under `edits`; with
    options, one spread of each run with the options in place of its own, under the part of the
    document that reaches it (`package.combined`, which first checks the whole document on `model`).
    Raises Failed with the engine's diagnostics for options or edits that the engine refuses."""
    from .. import package, spread
    from ..model import ModelError

    if not options:
        return [(model, list(runs), edits)]
    out = []
    for run in runs:
        try:
            derived, reduced = package.combined(model, run, options, edits)
        except ModelError as exc:
            raise common.Failed(spread.readable(model, exc.diagnostics)) from None
        out.append((derived, [run], reduced))
    return out


def drawn(model, runs, edits):
    """Whether an input of one of `runs` has a distribution, in the model or in the edit document: the
    engine's values of the runs (`uncertainty.written_values`), which check the document. Raises
    Failed with the engine's diagnostics for a document that it refuses."""
    from .. import spread
    from ..engine.sampling import uncertain
    from ..engine.uncertainty import written_values
    from ..model import ModelError

    try:
        values = written_values(model, edits, runs)
    except ModelError as exc:
        raise common.Failed(spread.readable(model, exc.diagnostics)) from None
    return any(uncertain(values[run]) for run in runs)


def nothing(args, target, model, runs):
    """Say that no input of `runs` (None: of any run of the model) has a distribution, so there is no
    spread; exit 0. With `--json`, a document with no run that says so (`note`)."""
    where = 'the model' if runs is None else f'{"run" if len(runs) == 1 else "runs"} {common.listed(runs)}'
    note = (
        f'No input of {where} has a distribution, in the model or in the edit document. '
        'Every sample is the same, so there is no spread. '
        'An edit document (--edits FILE) can give an input a distribution.'
    )
    if args.json:
        from .. import SCHEMA_VERSION, paths

        scenario, variant = paths.names_of(model.origin)
        doc = {
            'schema_version': SCHEMA_VERSION,
            'model_hash': model.model_hash,
            'implementation_hash': model.implementation_hash,
            'scenario': scenario,
            'variant': variant,
            'title': model.scenario.title,
            'admitted_runs': admitted(model),
            'note': note,
            'runs': {},
        }
        common.write_json(doc, sys.stdout)
    else:
        sys.stdout.write(f'{target.name}: {note}\n')
    return 0


def admitted(model):
    """The runs that the model was checked for, or None for every run."""
    return None if model.admission_runs is None else list(model.admission_runs)


def sampled(model, studies, options, args, times, jobs):
    """The engine's spread of each study (`spread.spread`), with the same settings and seed. A spread
    that the engine does not complete stops the command: Failed, with its diagnostics."""
    from .. import spread
    from ..model import ModelError

    progress = Progress(sys.stderr)
    found = []
    try:
        for _, runs, edits in studies:
            try:
                result = spread.spread(
                    model,
                    runs,
                    edits,
                    samples=args.samples,
                    seed=args.seed,
                    times=times,
                    options=options,
                    progress=progress,
                    jobs=jobs,
                )
            except ModelError as exc:
                raise common.Failed(spread.readable(model, exc.diagnostics)) from None
            except ValueError as exc:
                raise common.Failed([], str(exc)) from None
            if result['status'] != 'completed':
                why = (
                    'The report of the samples is not numerically valid'
                    if result['status'] == 'failed'
                    else 'The engine refuses the spread'
                )
                items = [with_sample(model, item) for item in result['diagnostics']]
                raise common.Failed(items, f'{why}: no spread is shown.')
            found.append(result)
    finally:
        progress.close()
    return found


def with_sample(model, item):
    """A diagnostic of one sample (`sample`, `seed` and `drawn`, which the engine gives it) with them in
    its message, each draw named as edits name its input; any other diagnostic as it is."""
    from .. import spread

    if 'sample' not in item:
        return item
    drawn = ', '.join(
        f'{spread.input_id(model, name)}={common.number(value)}'
        for name, value in (item.get('drawn') or {}).items()
    )
    where = f'sample {item["sample"]}, seed {item["seed"]}' + (f': {drawn}' if drawn else '')
    return {**item, 'message': f'{item["message"]} ({where})'}


class Progress:
    """The progress of the samples on a terminal (`spread`'s `progress`); nothing on any other stream."""

    def __init__(self, stream):
        self.stream = stream if stream.isatty() else None
        self.width = 0

    def __call__(self, phase, done, total):
        if self.stream is None:
            return
        text = f'{phase}: {done} of {total} samples'
        self.stream.write('\r' + text.ljust(self.width))
        self.stream.flush()
        self.width = max(self.width, len(text))

    def close(self):
        if self.stream is not None and self.width:
            self.stream.write('\r' + ' ' * self.width + '\r')
            self.stream.flush()


# --- The document -----------------------------------------------------------------------------------


def document(model, found, options, edits, point, t, exceed):
    """The `--json` document of the spreads `found`: the envelope of the engine's reports (`merged`:
    `schema_version`, the hashes, the scenario, the edit document that the command applied, the
    diagnostics), `admitted_runs`, the `options`, and each run (`run_record`), in order."""
    # The envelopes only: the runs of the central study are large, and the records below give them.
    reports = [
        {
            **{key: value for key, value in item['report'].items() if key not in ('uncertainty', 'runs')},
            'runs': {},
        }
        for item in found
    ]
    envelope = common.merged(reports, edits=None if len(reports) == 1 else edits)
    doc = {key: value for key, value in envelope.items() if key != 'runs'}
    doc['admitted_runs'] = admitted(model)
    doc['options'] = list(options)
    doc['runs'] = {}
    for item in found:
        for run in item['report']['runs']:
            doc['runs'][run] = run_record(model, item, run, point, t, exceed)
    return doc


def run_record(model, found, run, point, t, exceed):
    """What the document gives of one run of a spread: its `label`, `options` and `horizon`; the
    `settings` (the engine's sampling settings, and the reporting point and its time); the
    distribution of each drawn input (`inputs`); the label and unit of each outcome (`outcomes`);
    each sample (`samples`), with its draws and the value and status of each outcome at the time;
    and the `summary` of each outcome (`summary_of`). A run that the engine did not sample (no input
    of it has a distribution, and no event of it goes by chance) has no sample, and its summary gives
    the run's own value (`sampled: false`)."""
    from .. import spread

    report = found['report']
    shown = report['runs'][run]
    summaries = report['uncertainty']['runs'].get(run)
    inputs = {} if summaries is None else summaries['inputs']
    names = {name: spread.input_id(model, name) for name in inputs}
    record = {
        'label': shown['label'],
        'options': list(shown['options']),
        'horizon': shown['horizon'],
        'settings': {**report['uncertainty']['settings'], 'point': point, 't': t},
        'inputs': {
            names[name]: {'label': label_of(model, name), 'distribution': item['distribution']['text']}
            for name, item in inputs.items()
        },
        'outcomes': {
            name: {'label': outcome['label'], 'unit': outcome['unit']}
            for name, outcome in shown['outcomes'].items()
        },
    }
    if summaries is None:
        row = shown['reporting_points'][point]
        record['samples'] = []
        record['summary'] = {
            name: {'sampled': False, 'value': row['values'][name], 'status': row['statuses'][name]}
            for name in shown['outcomes']
        }
        return record
    rows = [rows_at(sample, t) for sample in found['result'].samples[run]['rows']]
    record['samples'] = [
        {
            'draws': {names[name]: item['draws'][k] for name, item in inputs.items()},
            'values': dict(row['values']),
            'statuses': dict(row['statuses']),
        }
        for k, row in enumerate(rows)
    ]
    record['summary'] = {
        name: summary_of(summaries['outcomes'][name]['points'][point], name, rows, exceed, names)
        for name in shown['outcomes']
    }
    return record


def rows_at(sample, t):
    """The outcome row of one sample at the time `t`."""
    return next(row for row in sample if row['t'] == t)


def label_of(model, name):
    """The label of an input, by its name in the structure."""
    return (model.inputs.get(name) or {}).get('doc')


def summary_of(summary, outcome, rows, exceed, names):
    """The summary of one outcome over the samples: the engine's (`uncertainty.summary`: the mean, the
    standard deviation, the extremes and p5 to p95), with its drivers named as edits name the inputs
    (`drivers`), the far tail from the samples' rows (`p99` from 1000 samples, `p99.5` from 2000:
    `shown_tails`), and the chance of each `--exceed` on the outcome (`exceed`: `{value, count,
    samples, chance}`). An outcome that is not estimated in every sample gives the engine's statuses
    only."""
    import numpy as np

    from ..model.ir import thaw

    if not summary.get('estimated'):
        return thaw(summary)
    out = thaw(summary)
    out['drivers'] = {names.get(name, name): rho for name, rho in summary['drivers'].items()}
    values = np.asarray([row['values'][outcome] for row in rows], dtype=float)
    tails = shown_tails(len(values))
    for p, value in zip(tails, np.percentile(values, [float(p) for p in tails], method='linear')):
        out[tail_key(p)] = float(value)
    out['exceed'] = [
        {
            'value': value,
            'count': int(np.count_nonzero(values > value)),
            'samples': len(values),
            'chance': float(np.count_nonzero(values > value)) / len(values),
        }
        for name, value in exceed
        if name == outcome
    ]
    return out


# --- The text ---------------------------------------------------------------------------------------


def show(stream, target, model, doc, args):
    """The spread as text: a heading (the model, the check, the settings and the runs), then each
    outcome with each run beside the others (`outcome_lines`)."""
    runs = doc['runs']
    first = next(iter(runs.values()))
    settings = first['settings']
    lines = [f'{target.name}: {doc["title"]}']
    note = common.scope_note(model)
    if note:
        lines.append(note)
    hours = f'{common.number(settings["t"])} h'
    when = f'at the end of the run ({hours})' if args.at is None else f'at {hours}'
    lines.append(f'{settings["samples"]} samples, seed {settings["seed"]}, {when}')
    if doc['options']:
        lines.append(f'options: {" · ".join(doc["options"])}')
    width = max(len(name) for name in runs)
    lines += [
        f'  {name:<{width}}  {record["label"]}' if record['label'] != name else f'  {name}'
        for name, record in runs.items()
    ]
    outcomes = list(dict.fromkeys(name for record in runs.values() for name in record['outcomes']))
    for outcome in outcomes:
        lines.append('')
        lines += outcome_lines(outcome, runs, width)
    stream.write('\n'.join(lines) + '\n')
    stream.flush()


def outcome_lines(outcome, runs, width):
    """The lines of one outcome: its name, label and unit, then each run that gives it."""
    number = common.number
    head = next(record['outcomes'][outcome] for record in runs.values() if outcome in record['outcomes'])
    lines = [f'{outcome}: {head["label"]} ({head["unit"]})']
    for name, record in runs.items():
        if outcome not in record['outcomes']:
            continue
        summary = record['summary'][outcome]
        pad = f'  {"":<{width}}  '
        start = f'  {name:<{width}}  '
        if summary.get('sampled') is False:
            value = summary['value']
            shown = 'not estimated' if value is None or summary['status'] != 'estimated' else number(value)
            lines.append(f'{start}{shown}: no input of the run has a distribution')
            continue
        if not summary.get('estimated'):
            lines.append(f'{start}not estimated')
            continue
        lines.append(
            f'{start}mean {number(summary["mean"])}; middle 50%: {number(summary["p25"])} to '
            f'{number(summary["p75"])}; middle 90%: {number(summary["p5"])} to {number(summary["p95"])}'
        )
        tails = [f'{label}: {number(summary[tail_key(p)])}' for p, label in TAILS if tail_key(p) in summary]
        if tails:
            lines.append(pad + '; '.join(tails))
        movers = sorted(
            ((abs(rho), name, rho) for name, rho in summary['drivers'].items() if rho is not None),
            key=lambda item: (-item[0], item[1]),
        )[:DRIVERS]
        if movers:
            shown = ', '.join(f'{name} {rho:+.2f}' for _, name, rho in movers)
            lines.append(f'{pad}inputs that move it most (rank correlation): {shown}')
        for item in summary['exceed']:
            lines.append(
                f'{pad}P({outcome} > {number(item["value"])}) = {number(item["chance"])} '
                f'({item["count"]} of {item["samples"]} samples)'
            )
    return lines
