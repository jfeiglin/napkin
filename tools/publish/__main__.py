"""Publish current run readings and their source dossiers. Whole-catalogue runs also verify the source manifest."""

import argparse
import difflib
import sys
import time

from napkin import store

from ..catalogue import ROOT
from . import HISTORICAL, Context, build, builders, drift, prune, sample_spreads, selected, write

# Diff lines shown for each committed summary that differs from a fresh render.
SHOWN = 12


def changes(path, content):
    """The first lines of a diff from a committed summary to its fresh render (None: no longer produced)."""
    target = ROOT / path
    committed = target.read_text(encoding='utf-8', errors='replace').splitlines() if target.is_file() else []
    if isinstance(content, bytes):
        content = content.decode('utf-8', 'replace')
    fresh = [] if content is None else content.splitlines()
    lines = list(
        difflib.unified_diff(committed, fresh, f'{path} (committed)', 'fresh render', lineterm='', n=0)
    )
    if not lines:
        return [f'{path}: only the line endings or the encoding differ']
    return lines[:SHOWN] + ([f'... {len(lines) - SHOWN} more lines'] if len(lines) > SHOWN else [])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        '--write',
        action='store_true',
        help='Update the committed summaries in the checkout and delete those no longer produced',
    )
    action.add_argument(
        '--check',
        action='store_true',
        help='Fail when a committed summary differs from a fresh render or is no longer produced',
    )
    parser.add_argument(
        '--only',
        action='append',
        choices=sorted((*builders(), *HISTORICAL)),
        help='Select a publication format',
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        '--scenario',
        action='append',
        metavar='ID',
        help='Publish only this scenario (repeatable); skip aggregate builders',
    )
    selection.add_argument(
        '--model',
        metavar='PATH',
        help='Render current readings for a model or each variant of a package to its results/readings.md',
    )
    parser.add_argument('--jobs', type=int, default=4, help='Worker processes for studies and spreads')
    parser.add_argument(
        '--sample-spreads',
        action='store_true',
        help='Also run each current declared spread at its authored sample count',
    )
    parser.add_argument(
        '--committed-spreads',
        action='store_true',
        help='Historical brief option for revision 8488047',
    )
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error('--jobs is a whole number of at least 1')
    if args.model:
        if args.only or args.committed_spreads or args.sample_spreads:
            parser.error(
                '--model renders readings. Use --scenario to select other formats or sample declared spreads.'
            )
        from .readings import publish_package

        store.activate(store.default_directory())
        try:
            results = publish_package(args.model, check=args.check, jobs=args.jobs)
        except (OSError, ValueError) as error:
            print(error, file=sys.stderr)
            return 1
        for target, matches in results.items():
            if matches:
                print(f'{"Verified" if args.check else "Wrote"} {target}')
            else:
                print(f'{target} differs from the completed run records', file=sys.stderr)
        return int(not all(results.values()))
    if args.committed_spreads:
        parser.error(
            '--committed-spreads selects historical brief tables at revision 8488047. '
            'Use --check for current readings and dossiers, or napkin sample for a current spread.'
        )
    try:
        names = selected(args.only, args.scenario)
        ctx = Context(ROOT, jobs=args.jobs, scenario_ids=args.scenario)
    except ValueError as exc:
        parser.error(str(exc))
    # Each run that the summaries need comes from the run store when it is there.
    store.activate(store.default_directory())
    started = time.monotonic()
    ctx.progress = lambda message: print(
        f'[publish {time.monotonic() - started:6.1f}s] {message}', file=sys.stderr, flush=True
    )
    ctx.progress(
        'current publication formats: '
        + ', '.join(names)
        + '. Historical campaign reports and HTML are archived at 8488047.'
    )
    try:
        outputs = build(ctx, args.only)
        if args.sample_spreads:
            sample_spreads(ctx)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    if args.write:
        write(outputs, ROOT)
        print(f'Wrote {len(outputs)} committed summaries')
        removed = prune(outputs, ROOT, names, scenario_ids=ctx.scenario_ids)
        if removed:
            print(f'Deleted {len(removed)} committed summaries no longer produced: ' + ', '.join(removed))
        return 0
    stale = drift(outputs, ROOT, names, scenario_ids=ctx.scenario_ids)
    if stale:
        for path in stale:
            print('\n'.join(changes(path, outputs.get(path))), file=sys.stderr)
        print(
            'Committed summaries differ from a fresh render or are no longer produced: '
            + ', '.join(stale)
            + '\nRun: python -B -m tools.publish --write'
            + ''.join(f' --scenario {sid}' for sid in ctx.scenario_ids or ())
            + ''.join(f' --only {name}' for name in args.only or ()),
            file=sys.stderr,
        )
        return 1
    print(f'All {len(outputs)} committed summaries match a fresh render')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
