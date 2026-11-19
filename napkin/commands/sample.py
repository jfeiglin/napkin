"""`napkin sample`: run one run many times with drawn inputs, and print the spread of named values
(docs/cli.md).

The work is the engine's Monte Carlo study (`napkin.spread.spread`, `napkin.engine.uncertainty`). The
run is the model's default run, or `--run NAME`, under the edit document of `--edits FILE`, which can
give an input a distribution ("pert(48 h, 96 h, 200 h)"); the document is checked whole first. A
central run in `median` mode gives each value's central value, its unit and its label; then
`--samples` samples (200 by default) run in `sampled` mode, each with its own seed from `--seed` (0),
on `--jobs` processes (the processors, and no more than the samples). One sample gives the same values
alone, in a batch or in another process, within the stated tolerances (change 11).

The values are each path of `--value`, or every named number of the run (the listing of
`napkin run`), at `--at TIME` (the horizon by default). For each, the command prints its unit, the
central value, the mean of the samples, and their middle 50% (p25 to p75) and middle 90% (p5 to
p95); from 1000 samples the 1-in-100 value (p99) and from 2000 the 1-in-200 value (p99.5), so that at
least 10 samples lie beyond each (`TAILS`), as type-7 quantiles of the samples
(`expectations.quantile`). Under the table come the draws that move each value most, by rank
correlation (`DRIVERS`), and each `--exceed PATH=VALUE`: the share of the samples above VALUE, in the
value's unit, P(X > V) = k / n, with its Clopper-Pearson interval. A value that some sample cannot
give, or a text named by `--value`, has no spread, and the command says why.

Each run goes through the run store (`napkin.store`; `NAPKIN_STORE=off` turns it off).

A run whose samples draw nothing has no spread: each sample is the central run. The command says so
and exits 0. A study that a sample refuses (a sample that stops before the horizon, which no
estimate leaves out), a central run that stops, and an edit document that does not hold are
diagnostics (exit 1). A path, a run or a time that the model does not have is a usage error (exit 2).

`--json` prints one document: the model, the run, the edits, the settings and the time; for each
value its unit, its label, the central value, the mean with its interval, the standard deviation and
error, the least and the greatest value, the percentiles and the tails, the drivers and the
exceedances; each sample's seed, values and draws (site, owner, value in canonical units); and every
warning of the model, with its place (`warnings`: the text gives the parts that rest on no record as
one line that counts them, `common.warn`).
"""

import argparse
import os
import sys
from fractions import Fraction

from . import common

SUMMARY = 'run one run many times with drawn inputs; print the spread of named values'

DESCRIPTION = """\
Sample one run (the default run, or --run NAME) under its edits: each input with a distribution, in
the model or the edit document, is drawn in each sample. Print, for each named value at --at (the
horizon by default), the central value, the mean, the middle 50% and 90% of the samples, the
1-in-100 and 1-in-200 values when there are enough samples, and the draws that move it most.
Exit 0 ok, 1 diagnostics, 2 usage."""

EXAMPLES = """\
example:
  napkin sample examples/piano_tuners --value tunings_done --samples 1000 --exceed tunings_done=3000"""

# The values of the far tail: (percentile, its name). Each shows only when at least BEYOND samples lie
# beyond it (`shown_tails`): from 1000 samples for p99 and from 2000 for p99.5.
TAILS = ((Fraction(99), '1-in-100 value'), (Fraction(199, 2), '1-in-200 value'))
BEYOND = 10
# The draws that the summary of a value names as those that move it most.
DRIVERS = 3


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
    """The description, the example and the arguments of `napkin sample`: `args.run` (None when not
    given), `args.edits` (a path, or None), `args.value` and `args.exceed` (lists, empty when not
    given), `args.at` (the text of one time, or None), `args.samples` (200), `args.seed` (0),
    `args.jobs` (None: the processors), `args.json` (True or False) and `args.model`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    parser.add_argument('--run', metavar='NAME', help='the named run (default: the default run)')
    parser.add_argument(
        '--edits', metavar='FILE', help='an edit document of the inputs, which can give them distributions'
    )
    parser.add_argument(
        '--value',
        action='append',
        default=[],
        metavar='PATHS',
        help='the paths of the values: --value tank.water,deliveries (default: every named number)',
    )
    parser.add_argument('--at', metavar='TIME', help='the spread at this time (default: the horizon)')
    parser.add_argument(
        '--samples', type=count, default=200, metavar='N', help='the number of samples (default 200)'
    )
    parser.add_argument(
        '--seed', type=seed, default=0, metavar='N', help='the seed of the samples (default 0)'
    )
    parser.add_argument(
        '--jobs', type=count, metavar='N', help='the processes that run the samples (default: the processors)'
    )
    parser.add_argument(
        '--exceed',
        action='append',
        default=[],
        metavar='PATH=VALUE',
        help='also print the share of the samples in which PATH is above VALUE, in its unit (repeatable)',
    )
    parser.add_argument('--json', action='store_true', help='print one JSON document, with every sample')
    common.add_model(parser)


def shown_tails(samples):
    """The percentiles of `TAILS` that `samples` samples show: those beyond which lie at least `BEYOND`
    samples, N (100 - p) / 100 >= BEYOND."""
    return [p for p, _ in TAILS if samples * (100 - p) >= BEYOND * 100]


def tail_key(p):
    """The key of a tail value: `p99`, `p99.5`."""
    return f'p{int(p) if p.denominator == 1 else float(p)}'


def main(args):
    """Sample the run that the arguments name, and print the spread of its values; give the exit
    code."""
    from ..model.language.problems import LanguageError
    from ..spread import spread
    from .run import chosen, held, named, recorded

    entry = common.entry_of(args.model)
    model = common.compiled(entry)
    edits = common.edits_of(model, args.edits)
    configuration = common.configured(model, args.run, edits, args.edits)
    horizon = float(configuration.request.horizon)
    when = (f'{common.number(horizon)} h', horizon)
    if args.at is not None:
        when = common.hours(model, args.at, '--at')
        if not 0 <= when[1] <= horizon:
            raise common.UsageError(f'--at {args.at}: the run goes from 0 h to {common.number(horizon)} h')
    # The central run gives the paths that the run names: what its record holds.
    record = recorded(model.program, configuration, entry)
    listed = not args.value
    paths = chosen(named(model, record), held(record), args.value)
    exceed = exceedances(args.exceed, held(record))
    paths += [path for path, _ in exceed if path not in paths]
    jobs = min(args.jobs if args.jobs is not None else os.cpu_count() or 1, args.samples)
    common.stored()
    try:
        found = spread(
            model,
            paths,
            [when[1]],
            run=args.run,
            edits=edits,
            samples=args.samples,
            seed=args.seed,
            jobs=jobs,
        )
    except LanguageError as error:
        raise common.Failed(error.problems) from None
    if found.refused is not None:
        raise common.Failed([common.problem('sample', found.refused, entry)])
    rows = [item for item in found.spreads if not (listed and isinstance(item.summary.central, str))]
    drawn = any(sample.draws for sample in found.samples)
    doc = document(model, entry, args, configuration, when, found, rows, exceed, drawn)
    if args.json:
        common.write_json(doc, sys.stdout)
        return 0
    for line in lines(model, args, when, doc, drawn):
        print(line)
    sys.stdout.flush()
    return 0


def exceedances(items, known):
    """[(path, value)] of the `--exceed PATH=VALUE` items, in the order given: VALUE is a number in
    the path's declared unit. A path that names no value of `known`, and a VALUE that is no number, are
    a UsageError."""
    found = []
    for item in items:
        path, separator, text = (piece.strip() for piece in item.partition('='))
        if not separator or not path or not text:
            raise common.UsageError(f'--exceed takes PATH=VALUE, such as tank.water=5, not {item!r}')
        if path not in known:
            raise common.UsageError(
                f'--exceed {path}: no named value of the model' + common.close(path, known)
            )
        try:
            value = float(text)
        except ValueError:
            raise common.UsageError(f'--exceed {item}: give a number in the unit of {path}') from None
        found.append((path, value))
    return found


def document(model, entry, args, configuration, when, found, rows, exceed, drawn):
    """The JSON document of `--json` (see the module), which the text shows a part of."""
    from ..engine import expectations

    def estimate(item):
        return None if item is None else {'value': item.value, 'low': item.low, 'high': item.high}

    place = {path: k for k, path in enumerate(found.paths)}
    values = {}
    for item in rows:
        sampled = [sample.values[place[item.path]][0] for sample in found.samples]
        summary = item.summary
        shown = {
            'unit': common.unit_shown(model.declared.units, item.unit),
            'label': item.label,
            # A central value that is unavailable has no number: its reason is the summary's.
            'central': None if hasattr(summary.central, 'reason') else summary.central,
            'estimated': summary.estimated,
            'reason': summary.reason,
        }
        if summary.estimated:
            shown.update(
                mean=estimate(summary.mean),
                sd=summary.sd,
                sem=summary.sem,
                least=summary.least,
                greatest=summary.greatest,
                percentiles={f'p{p}': value for p, value in summary.percentiles},
                tails={
                    tail_key(p): expectations.quantile(sampled, float(p) / 100).value
                    for p in shown_tails(len(sampled))
                },
                drivers=[{'site': site, 'owner': owner, 'rho': rho} for site, owner, rho in item.drivers],
            )
        values[item.path] = shown
    exceeded = []
    for path, value in exceed:
        sampled = [sample.values[place[path]][0] for sample in found.samples]
        if all(isinstance(each, (int, float)) for each in sampled):
            share = expectations.exceedance(sampled, value)
            above = round(share.value * share.n)
            exceeded.append(
                {
                    'path': path,
                    'threshold': value,
                    'above': above,
                    'samples': share.n,
                    'share': estimate(share),
                }
            )
        else:
            exceeded.append({'path': path, 'threshold': value, 'reason': 'a sample gives no number of it'})
    return {
        'model': common.shown(entry),
        'title': model.declared.scenario.title,
        'run': args.run,
        'edits': common.shown(args.edits) if args.edits is not None else None,
        'samples': args.samples,
        'seed': args.seed,
        'at': when[1],
        'drawn': drawn,
        'values': values,
        'exceed': exceeded,
        'draws': [
            {
                'seed': sample.seed,
                'values': {path: sample.values[place[path]][0] for path in values},
                'draws': [
                    {'site': site, 'owner': owner, 'value': value} for site, owner, value in sample.draws
                ],
            }
            for sample in found.samples
        ],
        'warnings': [common.problem_json(item) for item in model.reports],
    }


def lines(model, args, when, doc, drawn):
    """The text of the command (see the module)."""
    run = f'the run {args.run}' if args.run is not None else 'the default run'
    shown = [f'{doc["title"]}: {run}, {args.samples} samples from the seed {args.seed}, at {when[0]}']
    if not drawn:
        return [*shown, 'Its samples draw nothing: each sample is its central run, so it has no spread.']
    tails = shown_tails(args.samples)
    head = ['', 'unit', 'central', 'mean', 'p5', 'p25', 'p50', 'p75', 'p95', *(tail_key(p) for p in tails)]
    rows, reasons, drivers = [head], [], []
    for path, value in doc['values'].items():
        if not value['estimated']:
            reasons.append(f'{path}: no spread: {value["reason"]}')
            continue
        percentiles = value['percentiles']
        rows.append(
            [
                path,
                value['unit'],
                common.number(value['central']),
                common.number(value['mean']['value']),
                *(common.number(percentiles[f'p{p}']) for p in (5, 25, 50, 75, 95)),
                *(common.number(value['tails'][tail_key(p)]) for p in tails),
            ]
        )
        moved = [
            f'{item["site"]} of {item["owner"] or "the root"} ({item["rho"]:.2f})'
            for item in value['drivers']
        ]
        if moved:
            drivers.append(f'{path}: moved most by {", ".join(moved[:DRIVERS])}')
    shown += common.table(rows) if len(rows) > 1 else []
    shown += reasons + drivers
    for item in doc['exceed']:
        chance = f'P({item["path"]} > {common.number(item["threshold"])})'
        if 'reason' in item:
            shown.append(f'{chance}: {item["reason"]}')
            continue
        share = item['share']
        shown.append(
            f'{chance} = {item["above"]}/{item["samples"]} = {common.number(share["value"])} '
            f'(95% from {common.number(share["low"])} to {common.number(share["high"])})'
        )
    return shown
