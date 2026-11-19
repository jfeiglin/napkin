#!/usr/bin/env python
"""The migration check of stage M: a model in the language of now against its old model, by meaning.

    /home/user/napkin/.venv/bin/python check.py OLD_ENTRY.scn NEW_ENTRY.scn [--rename OLD=NEW]... [--quiet]

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
   by `napkin/program/proofs.py` under the same run (the old `base` run is the default run).

It notes, without failing, the numbers, names and flows that only the new model has, and the
warnings of the evidence rule (`no_record`, change 16), which `tools.check` refuses for a package.
"""

from __future__ import annotations

import collections
import json
import os
import subprocess
import sys
from pathlib import Path

import newmodel

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('NAPKIN_BASE', '/home/user/napkin-base'))
SHOWN = 12  # the differences shown in each group


def old_facts(entry):
    """The facts of the old model (`oldmodel.facts`), read by the old compiler in a process of its own."""
    environment = {**os.environ, 'PYTHONPATH': str(BASE)}
    done = subprocess.run(
        [sys.executable, str(HERE / 'oldmodel.py'), str(entry)],
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
            report.error('number', f'{value} ({dims(dimension)}): {count} in the old model, {theirs[(value, dimension)]} in the new one')
    extra = theirs - mine
    if extra:
        report.note(f'{sum(extra.values())} numbers of the new model are not in the old one (a floor `in [0,]`, a capacity beside its request, a weight of `else`)')
    for text, count in old['texts'].items():
        have = new['texts'].get(text, 0)
        if have < count:
            report.error('text', f'{count} in the old model, {have} in the new one: "{text[:100]}"')
    # Kinds and types.
    kinds = new['kinds']
    for path, (kind, written) in old['kinds'].items():
        path = renames.get(path, path)
        other = kinds.get(path)
        if other is None:
            report.error('kind', f'{path} ({kind}) is missing')
        elif other[0] != kind:
            report.error('kind', f'{path}: a {kind} in the old model, a {other[0]} in the new one')
        elif written and other[1] and written != other[1]:
            report.error('kind', f'{path}: of {dims(written)} in the old model, of {dims(other[1])} in the new one')
    named = {renames.get(path, path) for path in old['kinds']}
    new_names = sorted(path for path in kinds if path not in named)
    if new_names:
        report.note(f'{len(new_names)} names of the new model are not in the old one: {", ".join(new_names[:8])}')
    for path in old['unestimated']:
        if path in kinds:
            report.error('kind', f'{path} has no estimate in the old model, and a declaration in the new one (D4)')
    # Flows.
    for path, ends in old['flows'].items():
        path = renames.get(path, path)
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
                report.error('cumulative', f'{path}: proved cumulative in {label} of the old model; the new one has no such run or value')
            elif not proof[0]:
                report.error('cumulative', f'{path}: proved cumulative in {label} of the old model; in the new one it can fall: {proof[1]}')
    warnings = collections.Counter(item[0] for item in new['warnings'])
    if warnings:
        report.note(f'the setup reports of the new model: {dict(warnings)}')


def run(old_entry, new_entry, renames=None, quiet=False, out=sys.stdout):
    """Compare a translation with its old model (see the module); the report."""
    old = old_facts(old_entry)
    proven = sorted({path for paths in old['proven'].values() for path in paths})
    runs = sorted(run for run in old['proven'] if run)
    new = newmodel.facts(Path(new_entry), proven, runs)
    report = Report()
    if new['problems']:
        for code, file, line, message in new['problems']:
            report.error('compile', f'{code} {Path(file).name}:{line} {message[:150]}')
    else:
        compare(old, new, renames or {}, report)
    print(f'check {old_entry} -> {new_entry}', file=out)
    print(
        f'  old model: {sum(n for *_, n in old["numbers"])} numbers, {sum(old["texts"].values())} texts, '
        f'{len(old["kinds"])} names, {len(old["flows"])} flows; '
        f'proved cumulative: {sum(len(paths) for paths in old["proven"].values())} (value, run) pairs',
        file=out,
    )
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
            'its flows, and every value proved cumulative is proved never to fall',
            file=out,
        )
    return report


def main(argv):
    renames, args, k = {}, [], 0
    while k < len(argv):
        if argv[k] == '--rename':
            old, _, new = argv[k + 1].partition('=')
            renames[old] = new
            k += 2
            continue
        if not argv[k].startswith('--'):
            args.append(argv[k])
        k += 1
    if len(args) != 2:
        print(__doc__)
        return 2
    report = run(args[0], args[1], renames, '--quiet' in argv)
    return 1 if report.errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
