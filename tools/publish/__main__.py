"""Render the committed summaries: python -m tools.publish --write | --check."""

import argparse
import difflib
import sys
import time

from napkin import store

from ..catalogue import ROOT
from . import Context, build, builders, drift, prune, selected, write

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
        '--only', action='append', choices=sorted(builders()), help='Restrict to named builders'
    )
    parser.add_argument(
        '--scenario',
        action='append',
        metavar='ID',
        help='Publish only this scenario (repeatable); skip aggregate builders',
    )
    parser.add_argument('--jobs', type=int, default=4, help='Worker processes for studies and spreads')
    parser.add_argument(
        '--committed-spreads',
        action='store_true',
        help="With --check: take each brief's spread section from its committed brief, sampling none",
    )
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error('--jobs is a whole number of at least 1')
    if args.committed_spreads and not args.check:
        parser.error('--committed-spreads goes with --check: --write samples every spread')
    try:
        names = selected(args.only, args.scenario)
        ctx = Context(
            ROOT, jobs=args.jobs, scenario_ids=args.scenario, committed_spreads=args.committed_spreads
        )
    except ValueError as exc:
        parser.error(str(exc))
    # Each run that the summaries need comes from the run store when it is there.
    store.activate(store.default_directory())
    started = time.monotonic()
    ctx.progress = lambda message: print(
        f'[publish {time.monotonic() - started:6.1f}s] {message}', file=sys.stderr, flush=True
    )
    outputs = build(ctx, args.only)
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
            + ''.join(f' --scenario {sid}' for sid in ctx.scenario_ids or ()),
            file=sys.stderr,
        )
        return 1
    print(f'All {len(outputs)} committed summaries match a fresh render')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
