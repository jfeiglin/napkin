"""Compare two runs by their names, their values and their traces: python -m tools.compare BASE OTHER
[--run NAME] [--at HOURS] [--rename FILE] [--relative R] [--absolute A]; or keep the capture of one
run: python -m tools.compare MODEL --write FILE [--run NAME] [--at HOURS].

G0 (D16) reduced the old comparison of two revisions, bit for bit, to the checks that verify a
migration: that a model rewritten, refactored or run by another revision still has the names of the
base, gives its values and does what its trace did. Agreement shows that a change kept the results;
it does not show that either side is right, which the independent tests and the oracle do.

**A side** is one of:

- a model (a package folder or a `.scn` file), which the tool runs now with this checkout's engine:
  its default run, or `--run NAME`;
- a capture, a JSON document that `--write` keeps (`capture`), here or at another revision that has
  this tool;
- the results that the old publisher wrote for a scenario of the catalogue (`results/runs.json`):
  the outcomes of the run `--run NAME` (or of its only row) at the horizon, with no unit and no trace
  (`published`). A scenario migrated in stage M is checked against them, with `--rename` from the
  old outcome names to the new paths.

**A capture** holds the model's name, the run, the horizon, the times (by default 0 h and each
sixteenth of the horizon, or `--at`, in hours), and for each named value of the run (the listing of
`napkin run`, `napkin.commands.run.named`) its unit and its values at the times as the record holds
them, in the declared unit (a number, a yes/no, a text or `{"unavailable": reason}`); and its trace:
each start, finish, commit, firing, move and failure (`TRACED`), with its time, its part and its
owner. A time after the run stopped holds `{"unavailable": ...}`.

**The comparison** (`compare`):

- names: each name of the base is in the other after `--rename` (a JSON object {base: other}, each
  key a whole dotted path from the left: `tank` renames `tank.water` and `tank.deliver#1.pipe`, and
  never `tanks.water`); a name that only the other has is counted and is no difference, because a
  migrated model may name more;
- values: at each time of the base that the other holds, two numbers agree within `--absolute`
  (default 1e-9) plus `--relative` (default 1e-6, the six figures of a published result) times the
  larger magnitude; a yes/no, a text and an unavailable value agree only with the same; two units
  agree when they are equal or one side gives none;
- trace: the base's entries, in order, against the other's: the same kind, part and owner (renamed),
  each at a time within the same tolerances; the first entry that differs is the difference, as the
  rest follows from it. A side with no trace (a published result) is compared by its values only.

Exit codes: 0 when the two agree (or a capture is written), 1 when they differ, 2 for a command
line that is wrong or a side that cannot be read.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# The kinds of trace entry that a capture keeps: what the model does, and not how the engine solves.
TRACED = ('start', 'finish', 'commit', 'fire', 'move', 'failure')
# The default times: 0 h and each sixteenth of the horizon.
PARTS = 16
# The most differences that the command prints.
SHOWN = 50


def capture(entry, run=None, times=None):
    """The capture of a run of the model at `entry` (see the module): its default run, or `run`, at
    `times` (hours; by default 0 h and each sixteenth of the horizon)."""
    from napkin.commands.run import named
    from napkin.engine import read
    from napkin.engine import run as engine_run
    from napkin.engine.timeline import paused
    from napkin.model.compile import load_scenario
    from napkin.package import name_of
    from napkin.program.record import Unavailable

    model = load_scenario(entry)
    configuration = model.configure(run) if run is not None else model.configuration
    record = engine_run(model.program, configuration)
    horizon = float(configuration.request.horizon)
    times = [float(t) for t in times] if times else [horizon * k / PARTS for k in range(PARTS + 1)]
    stop, why = horizon, None
    if record.failure is not None:
        stop, why = float(record.failure.t), record.failure.detail('message') or 'the run failed'
    elif paused(record) is not None:
        stop, why = float(paused(record).t), 'the run paused'
    held = [t for t in times if t <= stop]
    values = {}
    for found in read(record, model.program, named(model, record), held):
        shown = [{'unavailable': item.reason} if isinstance(item, Unavailable) else item for item in found.values]
        shown += [{'unavailable': f'the run stopped at {stop:g} h: {why}'}] * (len(times) - len(held))
        values[found.path] = {'unit': found.unit, 'values': shown}
    return {
        'model': name_of(entry),
        'run': run,
        'horizon': horizon,
        'times': times,
        'values': values,
        'trace': [
            {'t': float(entry.t), 'kind': entry.kind, 'part': entry.part, 'owner': entry.owner}
            for entry in record.trace
            if entry.kind in TRACED
        ]
        + (
            [{'t': stop, 'kind': 'failure', 'part': '', 'owner': ''}]
            if record.failure is not None
            else []
        ),
    }


def published(document, run=None):
    """The capture of a run of the old publisher's results (`results/runs.json`, see the module): the
    row of `run`, or the only row; each outcome at the horizon, its value when its status is
    `estimated`, else unavailable with its status; no unit and no trace. Raises ValueError for a run
    that the document does not have."""
    rows = document['rows']
    names = [row['run'] for row in rows]
    if run is None and len(rows) != 1:
        raise ValueError(f'the results hold the runs {", ".join(names)}: give --run NAME')
    row = rows[0] if run is None else next((row for row in rows if row['run'] == run), None)
    if row is None:
        raise ValueError(f'the results hold no run {run}: they hold {", ".join(names)}')
    values = {
        name: {
            'unit': None,
            'values': [
                outcome['value']
                if outcome.get('status') == 'estimated'
                else {'unavailable': outcome.get('status', '')}
            ],
        }
        for name, outcome in row['outcomes'].items()
    }
    horizon = float(document['horizon_h'])
    return {'model': document['scenario'], 'run': row['run'], 'horizon': horizon, 'times': [horizon], 'values': values, 'trace': None}


def side(text, run=None, times=None):
    """The capture of a side of the command line: a capture or published results (a `.json` file),
    else a model."""
    path = Path(text)
    if path.suffix == '.json':
        document = json.loads(path.read_text(encoding='utf-8'))
        return published(document, run) if 'rows' in document else document
    return capture(path / 'model.scn' if path.is_dir() else path, run, times)


def renamer(renames):
    """The function that renames a path, a part or an owner by `renames` ({base: other}): the
    longest key that is the whole path or a whole leading run of its dotted segments (an occurrence's
    `#n` ends a segment)."""
    keys = sorted(renames or {}, key=len, reverse=True)

    def rename(path):
        for key in keys:
            if path == key or (path.startswith(key) and path[len(key)] in '.#'):
                return renames[key] + path[len(key) :]
        return path

    return rename


def agree(a, b, relative, absolute):
    """Whether two values agree (see the module)."""
    if isinstance(a, dict) or isinstance(b, dict):
        return isinstance(a, dict) and isinstance(b, dict) and 'unavailable' in a and 'unavailable' in b
    if isinstance(a, (bool, str)) or isinstance(b, (bool, str)):
        return type(a) is type(b) and a == b
    return math.isclose(a, b, rel_tol=relative, abs_tol=absolute)


def text(value):
    """A value of a capture as a difference shows it."""
    if isinstance(value, dict):
        return f'unavailable ({value.get("unavailable")})'
    return repr(value)


def compare(base, other, renames=None, relative=1e-6, absolute=1e-9):
    """(the differences, as lines, and the counts: `names` of the base, `values` compared, `extra`
    names that only the other has, `entries` of the trace compared) of two captures (see the
    module)."""
    rename = renamer(renames)
    found, compared = [], 0
    at = {round(t, 9): k for k, t in enumerate(other['times'])}
    common = [(k, at[round(t, 9)]) for k, t in enumerate(base['times']) if round(t, 9) in at]
    if not common:
        found.append('no time of the base is a time of the other')
    theirs, named = other['values'], set()
    for path, mine in base['values'].items():
        name = rename(path)
        named.add(name)
        if name not in theirs:
            renamed = f' (as {name})' if name != path else ''
            found.append(f'{path}: the other has no value of this name{renamed}')
            continue
        their = theirs[name]
        if mine.get('unit') and their.get('unit') and mine['unit'] != their['unit']:
            found.append(f'{path}: in {mine["unit"]}, and the other in {their["unit"]}')
            continue
        for k, j in common:
            compared += 1
            a, b = mine['values'][k], their['values'][j]
            if not agree(a, b, relative, absolute):
                found.append(f'{path} at {base["times"][k]:g} h: {text(a)}, and the other {text(b)}')
    entries = 0
    if base.get('trace') is not None and other.get('trace') is not None:
        for k, (a, b) in enumerate(zip(base['trace'], other['trace'], strict=False)):
            entries += 1
            same = (a['kind'], rename(a['part']), rename(a['owner'])) == (b['kind'], b['part'], b['owner'])
            if not same or not math.isclose(a['t'], b['t'], rel_tol=relative, abs_tol=absolute):
                found.append(
                    f'trace entry {k}: {a["kind"]} {a["part"]} of {a["owner"] or "the root"} at {a["t"]:g} h, '
                    f'and the other {b["kind"]} {b["part"]} of {b["owner"] or "the root"} at {b["t"]:g} h'
                )
                break
        else:
            if len(base['trace']) != len(other['trace']):
                longer, kept = ('the base', base) if len(base['trace']) > len(other['trace']) else ('the other', other)
                extra = kept['trace'][entries]
                found.append(
                    f'trace entry {entries}: only {longer} has it, {extra["kind"]} {extra["part"]} at {extra["t"]:g} h'
                )
    counts = {
        'names': len(base['values']),
        'values': compared,
        'extra': len(set(theirs) - named),
        'entries': entries,
    }
    return found, counts


def main(argv=None):
    """The command (see the module); give the exit code."""
    parser = argparse.ArgumentParser(
        prog='python -m tools.compare',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument('base', metavar='BASE', help='a model, a capture or published results (.json)')
    parser.add_argument('other', metavar='OTHER', nargs='?', help='a model, a capture or published results')
    parser.add_argument('--run', metavar='NAME', help='the named run of a model, or the row of published results')
    parser.add_argument('--at', metavar='HOURS', help='the times of a capture, in hours: --at 0,12,24')
    parser.add_argument('--rename', type=Path, metavar='FILE', help='a JSON object {base path: other path}')
    parser.add_argument('--relative', type=float, default=1e-6, metavar='R', help='the relative tolerance (1e-6)')
    parser.add_argument('--absolute', type=float, default=1e-9, metavar='A', help='the absolute tolerance (1e-9)')
    parser.add_argument('--write', type=Path, metavar='FILE', help='write the capture of BASE, a model')
    args = parser.parse_args(argv)
    if (args.write is None) == (args.other is None):
        parser.error('give BASE and OTHER to compare, or BASE and --write FILE to keep its capture')
    try:
        times = [float(t) for t in args.at.split(',')] if args.at else None
    except ValueError:
        parser.error(f'--at {args.at}: give hours, such as 0,12,24')
    from napkin.model.language.problems import LanguageError

    try:
        base = side(args.base, args.run, times)
        if args.write is not None:
            args.write.write_text(json.dumps(base, indent=1, allow_nan=False) + '\n', encoding='utf-8')
            print(f'{args.write}: {len(base["values"])} values at {len(base["times"])} times, {len(base["trace"] or ())} trace entries')
            return 0
        other = side(args.other, args.run, times)
        renames = json.loads(args.rename.read_text(encoding='utf-8')) if args.rename else None
    except (OSError, ValueError, KeyError, LanguageError) as error:
        parser.error(str(error))
    found, counts = compare(base, other, renames, args.relative, args.absolute)
    for line in found[:SHOWN]:
        print(line)
    if len(found) > SHOWN:
        print(f'and {len(found) - SHOWN} more differences')
    print(
        f'{len(found)} differences: {counts["names"]} names, {counts["values"]} values, '
        f'{counts["entries"]} trace entries compared; {counts["extra"]} names only in the other'
    )
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
