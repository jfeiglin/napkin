#!/usr/bin/env python
"""The migration check of stage M: a model in the language of now against its old model, by meaning.

    /home/user/napkin/.venv/bin/python check.py OLD_ENTRY.scn NEW_ENTRY.scn [--rename OLD=NEW]...
        [--changed CHANGED.md] [--at HOURS]... [--quiet]

OLD_ENTRY is the entry file of an old model (a package's main file, or a variant) at the base commit
8488047; NEW_ENTRY the entry file of its translation. Each side is a whole model: the entry file with
every file that it reads. The old side is read by the old compiler, in a process of its own
(`oldmodel.py`, under PYTHONPATH=/home/user/napkin-base, since both compilers are the package
`napkin`); the new side by the compiler of now (`newmodel.py`). The check fails (exit 1) when:

1. `compile`: the new model does not compile;
2. `number`: a number of the old model, with its unit, is not in the new one as often (each is
   compared as its value in base units and its dimension, so `12 h` and `0.5 day` are one number; a
   bare number has the unit that its place gives it, and a zero any unit);
3. `text`: a text of the old model (a label, a description, a card, a status text, a record's
   explanation, a note, an option's name) is not in the new one as often;
4. `kind`: a name of the old model is missing, or has another kind: an input, a fixed value, a
   formula, a named state, a stock (flows join it and take from it), a tally (flows only fill it), a
   number state (no flow joins it), a link, a collection, a flow, an event, an entity, a template, a
   member; or its type has another dimension. An output of the old model is a formula now (D10), and
   one with no estimate has no declaration (D4). `--rename OLD=NEW` names a member that the
   translation renamed (`Thing.status=Thing.state`);
5. `flow`: a flow joins other stores than it did (the pairs of an old flow are the legs of a new one);
6. `cumulative`: a value that the old compiler proved cumulative in a run is not proved never to fall
   by `napkin/program/proofs.py` under the same run (the old `base` run is the default run);
7. `run`: an output of the old model has another value in the new one, and the package's list of
   changes does not list the difference (m.md, "No change is silent").

The run step runs each run of the old model's default study under the old engine and the run of the
same name of the new model under the engine of now, each to its horizon, and compares each output of
the old model (one with an estimate, D4) with the new value of the same name (through `--rename`, by
its own path or by the template's path that declares it) at the old report's reporting times: the
start, the horizon (the old `final`) and each time that `--at` or a row of the list names. An old
output with a reporting lag is read in the new run with the same lag, which a caller selects now
(D10). Where the old model draws (a distribution, an event by chance), the old study's run is its
central run (each distribution at its median, each event at its likeliest outcome), and the new run
is in the mode `median`: the check compares this median run only, never a sample, and says so.

Two values agree when they differ by at most `RELATIVE` (1e-6) of the larger, or by `FLOOR` (1e-8)
of the old output's unit. Both engines integrate a curve to a relative 1e-9 (`rtol`, with an absolute
1e-10 of each store's scale) and move a line exactly; a run adds the errors of its pieces and of its
event times, so the relative tolerance is a thousand times one step's. A translation error moves a
result by at least the relative change of the number that it alters, and the catalogue writes its
numbers with four significant digits or fewer, so by 1e-4 or more: a hundred times the tolerance.
The floor is for values at or near zero, where no relative measure holds: the old report took a
nonnegative output down to 1e-8 of its unit below zero for a zero (`outputs_from`).

The list of changes is `scratch/rewrite/b1/m-<package>/changed.md` of the old entry's package
(`--changed` names another). The run step reads each row of its markdown table whose header is
`| test | quantity | old | new | cause | evidence |`:

    | check run examples/piano_tuners/model.scn | tunings_done at 8760 h | 2923.537487 tunings | 0 tunings | ... | ... |

- `test`: `check run ENTRY` for the default run of the old entry ENTRY (its path in the base commit),
  `check run ENTRY:RUN` for its run RUN. A row of another test (a scenario test that a package's
  agent ports) is the agent's own: the run step leaves it alone;
- `quantity`: `OUTPUT at T h`, the old output's name and the time in hours;
- `old`, `new`: a number in the old output's unit, which the cell may write after it; or a word:
  `unavailable` (the new run has no value: it failed or stopped first, or its engine does not run
  it), or the old report's status (`unestimated`, `not_applicable`);
- `cause`: the rule of the spec or the change after G0 that makes the difference; `evidence`: the
  trace or the check line. Neither is empty.

A difference passes only when a row of its test lists it and the row's numbers agree with the runs'
within the tolerance. The step fails on a difference that no row lists, on a row whose numbers do not
agree, on a row of the entry that lists no difference (its values agree, or the check compares no
such run, output or time), and on a row of the entry that does not read.

It notes, without failing, the numbers, names and flows that only the new model has, and the
warnings of the evidence rule (`no_record`, change 16), which `tools.check` refuses for a package.
"""

from __future__ import annotations

import collections
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import newmodel

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('NAPKIN_BASE', '/home/user/napkin-base'))
SHOWN = 12  # the differences shown in each group
# The tolerance of the run step (see the module): a share of the larger value, and a floor in the old
# output's unit.
RELATIVE = 1e-6
FLOOR = 1e-8
HEADER = ('test', 'quantity', 'old', 'new', 'cause', 'evidence')


def old_facts(entry, times=()):
    """The facts of the old model (`oldmodel.facts`), read by the old compiler in a process of its own,
    with its outputs also at `times`, in hours."""
    environment = {**os.environ, 'PYTHONPATH': str(BASE)}
    asked = [item for t in times for item in ('--at', repr(float(t)))]
    done = subprocess.run(
        [sys.executable, str(HERE / 'oldmodel.py'), str(entry), *asked],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
        cwd=HERE,
    )
    if done.returncode != 0:
        raise SystemExit(f'the old compiler could not read {entry}:\n{done.stderr[-2000:]}')
    return json.loads(done.stdout)


class Report:
    def __init__(self):
        self.errors = collections.defaultdict(list)
        self.notes = []

    def error(self, group, message):
        self.errors[group].append(message)

    def note(self, message):
        self.notes.append(message)


def dims(text):
    """A dimension as the check keeps it, in words: `time^-1 tunings`, or `no unit`."""
    found = json.loads(text) if text.startswith('[') else text
    if isinstance(found, str):
        return found
    return ' '.join(name if power == 1 else f'{name}^{power:g}' for name, power in found) or 'no unit'


def counter(rows):
    return collections.Counter({(value, dimension): count for value, dimension, count in rows})


def compare(old, new, renames, report):
    """Every difference of meaning between the facts of the old model and those of the new one."""
    # Numbers and texts.
    mine, theirs = counter(old['numbers']), counter(new['numbers'])
    for (value, dimension), count in sorted(mine.items()):
        if theirs[(value, dimension)] < count:
            report.error(
                'number',
                f'{value} ({dims(dimension)}): {count} in the old model, {theirs[(value, dimension)]} in the new one',
            )
    extra = theirs - mine
    if extra:
        report.note(
            f'{sum(extra.values())} numbers of the new model are not in the old one (a floor `in [0,]`, a capacity beside its request, a weight of `else`)'
        )
    for text, count in old['texts'].items():
        have = new['texts'].get(text, 0)
        if have < count:
            report.error('text', f'{count} in the old model, {have} in the new one: "{text[:100]}"')
    # Kinds and types.
    kinds = new['kinds']
    for written_path, (kind, written) in old['kinds'].items():
        path = renames.get(written_path, written_path)
        other = kinds.get(path)
        if other is None:
            report.error('kind', f'{path} ({kind}) is missing')
        elif other[0] != kind:
            report.error('kind', f'{path}: a {kind} in the old model, a {other[0]} in the new one')
        elif written and other[1] and written != other[1]:
            report.error(
                'kind', f'{path}: of {dims(written)} in the old model, of {dims(other[1])} in the new one'
            )
    named = {renames.get(path, path) for path in old['kinds']}
    new_names = sorted(path for path in kinds if path not in named)
    if new_names:
        report.note(
            f'{len(new_names)} names of the new model are not in the old one: {", ".join(new_names[:8])}'
        )
    for path in old['unestimated']:
        if path in kinds:
            report.error(
                'kind', f'{path} has no estimate in the old model, and a declaration in the new one (D4)'
            )
    # Flows.
    for written_path, ends in old['flows'].items():
        path = renames.get(written_path, written_path)
        other = new['flows'].get(path)
        renamed = sorted([renames.get(a, a), renames.get(b, b)] for a, b in ends)
        if other is not None and other != renamed:
            report.error('flow', f'{path}: joins {renamed} in the old model, {other} in the new one')
    # What the old compiler proved cumulative.
    for run, paths in old['proven'].items():
        for path in paths:
            proof = new['proofs'].get(path, {}).get(run)
            label = f'the run {run}' if run else 'the default run'
            if proof is None:
                report.error(
                    'cumulative',
                    f'{path}: proved cumulative in {label} of the old model; the new one has no such run or value',
                )
            elif not proof[0]:
                report.error(
                    'cumulative',
                    f'{path}: proved cumulative in {label} of the old model; in the new one it can fall: {proof[1]}',
                )
    warnings = collections.Counter(item[0] for item in new['warnings'])
    if warnings:
        report.note(f'the setup reports of the new model: {dict(warnings)}')


# ---- the run step -------------------------------------------------------------------------------------


def entry_name(entry):
    """The name of an old entry in a test of the list of changes: its path in the base commit."""
    path = Path(entry).resolve()
    try:
        return path.relative_to(BASE.resolve()).as_posix()
    except ValueError:
        return str(entry)


def changed_of(entry):
    """The list of changes of the package of an old entry: `b1/m-<package>/changed.md`, the package
    being the folder under `examples/` or `scenarios/` (a variant's is its package's)."""
    parts = Path(entry_name(entry)).parts
    package = (
        parts[1] if len(parts) > 2 and parts[0] in ('examples', 'scenarios') else Path(entry).parent.name
    )
    return HERE.parent / 'b1' / f'm-{package}' / 'changed.md'


def test_of(entry, run):
    """The test of the run step's rows for a run of an old entry (`''` is the default run)."""
    return f'check run {entry_name(entry)}' + (f':{run}' if run else '')


def of_entry(row, entry):
    """Whether a row of the list of changes is of the run step of an old entry, of any of its runs."""
    test = test_of(entry, '')
    return row.test == test or row.test.startswith(f'{test}:')


@dataclass(frozen=True)
class Row:
    """A row of the list of changes: its line in the file and its six cells, as written."""

    line: int
    test: str
    quantity: str
    old: str
    new: str
    cause: str
    evidence: str


def read_changed(path):
    """The rows of the tables of a list of changes whose header is `HEADER`, and the problems of the
    rows that do not read: (rows, [(line, problem)]). A file that does not exist lists nothing."""
    path = Path(path)
    if not path.is_file():
        return [], []
    rows, problems, inside = [], [], False
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip().startswith('|'):
            inside = False
            continue
        # A cell may hold a bar that a backslash escapes; backticks only mark code.
        cells = [
            ' '.join(cell.replace('\\|', '|').replace('`', '').split())
            for cell in re.split(r'(?<!\\)\|', line.strip().strip('|'))
        ]
        if tuple(cell.lower() for cell in cells) == HEADER:
            inside = True
        elif inside and not all(set(cell) <= set('-: ') for cell in cells):
            if len(cells) != len(HEADER):
                problems.append((number, f'{len(cells)} cells, not the {len(HEADER)} of {", ".join(HEADER)}'))
            else:
                rows.append(Row(number, *cells))
    return rows, problems


QUANTITY = re.compile(r'(?P<name>\S+) at (?P<t>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?) h')
NUMBER = re.compile(r'(?P<n>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)(?: +(?P<unit>.+))?')


def quantity_of(row):
    """(output, time in hours) of a row, or None for a quantity that does not read."""
    found = QUANTITY.fullmatch(row.quantity)
    return (found['name'], float(found['t'])) if found else None


def cell_value(cell, unit):
    """The value of an `old` or `new` cell: a number in the output's unit `unit`, a word, or None
    with the problem, as (value, problem)."""
    found = NUMBER.fullmatch(cell)
    if found is None:
        word = cell.lower()
        return (
            (word, None) if re.fullmatch(r'[a-z_]+', word) else (None, f'"{cell}" is no number and no word')
        )
    if found['unit'] is not None and found['unit'] != unit:
        return None, f'"{cell}" is not in the unit of the output, {unit or "a plain number"}'
    return float(found['n']), None


def agree(a, b):
    """Whether two values agree: numbers within the tolerance (see the module), in the old output's
    unit, or two equal words."""
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= max(RELATIVE * max(abs(a), abs(b)), FLOOR)
    return a == b


def shown(value, unit):
    """A value as the check writes it: a number with ten significant digits and its unit, or a word."""
    return f'{value:.10g} {unit}'.rstrip() if isinstance(value, float) else str(value)


def in_old_unit(value, info):
    """A new value (`newmodel.plain`) as `agree` compares it with the old output `info`: a number in
    the old output's unit, `unavailable`, or a word; with the reason of an unavailable one."""
    if isinstance(value, dict):
        return 'unavailable', value['unavailable']
    if isinstance(value, float):
        return value / info['scale'], None
    return str(value).lower(), None


def new_path(name, declared, renames):
    """The path in the new model of an old output: its rename, or the rename of the path that
    declares it (`T.x` for the output `member.x` of a member of the template T), or its own name."""
    if name in renames:
        return renames[name]
    if declared != name and declared in renames:
        head = name.rpartition('.')[0]
        return f'{head}.{renames[declared].rpartition(".")[2]}'
    return name


def reads_of(old, renames):
    """What the new side reads for the run step: {run: {'paths', 'times', 'lags'}} (`newmodel.outcomes`)."""
    reads = {}
    for run, entry in old['runs']['runs'].items():
        outputs = {name: info for name, info in entry['outputs'].items() if info['estimated']}
        paths = {name: new_path(name, info['declared'], renames) for name, info in outputs.items()}
        reads[run] = {
            'paths': sorted(set(paths.values())),
            'times': entry['times'],
            'lags': {
                paths[name]: info['lag'] for name, info in outputs.items() if isinstance(info['lag'], list)
            },
        }
    return reads


def compare_runs(old, new, renames, entry, rows, report):
    """The run step (see the module): each output of each old run against the new value of the same
    name at the same times, the differences against the rows of the list of changes. Gives the
    number of differences that rows list, with numbers that agree."""
    if old['runs']['refused']:
        report.error('run', f'the old engine does not admit the study: {old["runs"]["refused"][0][:200]}')
        return 0
    mine = [row for row in rows if of_entry(row, entry)]
    listed, used = 0, set()
    for run, entry_ in old['runs']['runs'].items():
        label = f'run {run}: ' if run else ''
        outcome = new['outcomes'][run]
        if entry_.get('refused'):
            report.error('run', f'{label}the old report cannot read the run: {entry_["refused"][:200]}')
            continue
        if outcome['error'] and outcome['error'].startswith('the run does not configure'):
            report.error('run', f'{label}the new model has no such run: {outcome["error"][:200]}')
            continue
        by_place = {}
        for row in mine:
            place = quantity_of(row)
            if row.test == test_of(entry, run) and place is not None:
                by_place.setdefault(place[0], []).append((place[1], row))
        for name, info in sorted(entry_['outputs'].items()):
            if not info['estimated']:
                continue  # an output with no estimate has no declaration now (D4)
            path = new_path(name, info['declared'], renames)
            found = outcome['values'].get(path) if not outcome['error'] else None
            if found is not None and 'missing' in found:
                report.error(
                    'run', f'{label}{name}: no value {path} in the new model (name it with --rename)'
                )
                continue
            if found is not None and info['dims'] is not None and found['dims'] != info['dims']:
                report.error(
                    'run',
                    f'{label}{name}: of {dims(info["dims"])} in the old model, of {dims(found["dims"])} in the new one',
                )
                continue
            for k, t in enumerate(entry_['times']):
                a = info['values'][k] if info['statuses'][k] == 'estimated' else info['statuses'][k]
                a = float(a) if isinstance(a, (int, float)) and not isinstance(a, bool) else a
                b, why = (
                    ('unavailable', outcome['error'])
                    if found is None
                    else in_old_unit(found['values'][k], info)
                )
                row = next(
                    (each for at, each in by_place.get(name, ()) if abs(at - t) <= 1e-9 * max(1.0, t)), None
                )
                where = f'{label}{name} at {t:g} h'
                if agree(a, b):
                    if row is not None:
                        used.add(row)
                        report.error(
                            'run',
                            f'changed.md:{row.line} lists {where}, but the runs agree: {shown(a, info["unit"])}',
                        )
                    continue
                values = f'old {shown(a, info["unit"])}, new {shown(b, info["unit"])}'
                if info['lag'] is not None:
                    values += f' (the old output has the lag {info["lag"]} h; the new report: {found and found["note"]})'
                if why:
                    values += f' ({why[:160]})'
                if row is None:
                    report.error('run', f'{where}: {values}; no row of the list of changes lists it')
                    continue
                used.add(row)
                cells = [cell_value(row.old, info['unit']), cell_value(row.new, info['unit'])]
                problem = next((problem for _, problem in cells if problem), None)
                if not (row.cause and row.evidence):
                    problem = 'its cause or its evidence is empty'
                if problem is None and agree(cells[0][0], a) and agree(cells[1][0], b):
                    listed += 1
                else:
                    report.error(
                        'run',
                        f'{where}: changed.md:{row.line} lists old {row.old}, new {row.new}; the runs give {values}'
                        + (f'; {problem}' if problem else ''),
                    )
    for row in mine:
        if row in used:
            continue
        if quantity_of(row) is None:
            report.error(
                'run', f'changed.md:{row.line}: the quantity "{row.quantity}" does not read as OUTPUT at T h'
            )
        else:
            report.error(
                'run',
                f'changed.md:{row.line} lists {row.quantity} of "{row.test}", which the check does not compare '
                '(no such run, output or time, or another row lists it)',
            )
    return listed


def runs_line(old):
    """What the run step compares, in a line: the runs, their times, and what the old model draws."""
    if old['runs']['refused']:
        return 'runs: none (the old engine does not admit the study)'
    runs = old['runs']['runs']
    names = ', '.join(run or 'the default run' for run in runs)
    times = sorted({t for entry in runs.values() for t in entry['times']})
    line = f'runs: {names}, at {", ".join(f"{t:g}" for t in times)} h'
    draws = sorted({name for entry in runs.values() for name in entry['draws']})
    what = []
    if draws:
        more = f' and {len(draws) - 4} more' if len(draws) > 4 else ''
        what.append(f'the inputs {", ".join(draws[:4])}{more}')
    if any(entry['chance'] for entry in runs.values()):
        what.append('events by chance')
    if what:
        line += f'; the old model draws ({" and ".join(what)}): the check compares its median run, the old central run, only'
    return line


def run(old_entry, new_entry, renames=None, quiet=False, out=sys.stdout, changed=None, at=()):
    """Compare a translation with its old model (see the module); the report. `changed` is the list
    of changes (default: the package's, `changed_of`) and `at` more times of the run step, in hours."""
    renames = renames or {}
    changed = Path(changed) if changed is not None else changed_of(old_entry)
    rows, problems = read_changed(changed)
    mine = [row for row in rows if of_entry(row, old_entry)]
    times = {float(t) for t in at} | {place[1] for place in map(quantity_of, mine) if place is not None}
    old = old_facts(old_entry, sorted(times))
    proven = sorted({path for paths in old['proven'].values() for path in paths})
    runs = sorted(run for run in old['proven'] if run)
    reads = reads_of(old, renames) if not old['runs']['refused'] else {}
    new = newmodel.facts(Path(new_entry), proven, runs, reads)
    report = Report()
    listed = 0
    if new['problems']:
        for code, file, line, message in new['problems']:
            report.error('compile', f'{code} {Path(file).name}:{line} {message[:150]}')
    else:
        compare(old, new, renames, report)
        for line, problem in problems:
            report.error('run', f'changed.md:{line}: {problem}')
        listed = compare_runs(old, new, renames, old_entry, rows, report)
    print(f'check {old_entry} -> {new_entry}', file=out)
    print(
        f'  old model: {sum(n for *_, n in old["numbers"])} numbers, {sum(old["texts"].values())} texts, '
        f'{len(old["kinds"])} names, {len(old["flows"])} flows; '
        f'proved cumulative: {sum(len(paths) for paths in old["proven"].values())} (value, run) pairs',
        file=out,
    )
    print(f'  {runs_line(old)}', file=out)
    if listed:
        print(f'  run: {changed} lists {listed} of the differences, with their numbers', file=out)
    if not quiet:
        for message in report.notes:
            print(f'  note: {message}', file=out)
        for group, messages in report.errors.items():
            for message in messages[:SHOWN]:
                print(f'  FAIL [{group}] {message}', file=out)
            if len(messages) > SHOWN:
                print(f'  FAIL [{group}] ... and {len(messages) - SHOWN} more', file=out)
    if report.errors:
        summary = ', '.join(f'{len(messages)} {group}' for group, messages in sorted(report.errors.items()))
        print(f'  FAILED: {summary}', file=out)
    else:
        print(
            '  PASSED: every number with its unit and every text is there, every name keeps its kind and '
            'its flows, every value proved cumulative is proved never to fall, and every output keeps its '
            'values in each run or its list of changes lists the difference',
            file=out,
        )
    return report


def main(argv):
    renames, args, changed, at, k = {}, [], None, [], 0
    while k < len(argv):
        if argv[k] in ('--rename', '--changed', '--at') and k + 1 < len(argv):
            if argv[k] == '--rename':
                old, _, new = argv[k + 1].partition('=')
                renames[old] = new
            elif argv[k] == '--changed':
                changed = argv[k + 1]
            else:
                at.append(float(argv[k + 1]))
            k += 2
            continue
        if not argv[k].startswith('--'):
            args.append(argv[k])
        k += 1
    if len(args) != 2:
        print(__doc__)
        return 2
    report = run(args[0], args[1], renames, '--quiet' in argv, changed=changed, at=at)
    return 1 if report.errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
