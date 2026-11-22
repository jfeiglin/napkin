"""Compare authored catalogue interfaces at 8488047 and in the working tree, without running models.

    python scratch/rewrite/audit/catalogue_interface_inventory.py /path/to/clean/8488047 > inventory.csv

Run from the candidate checkout using its Python environment. The legacy extractor runs in a
separate interpreter with imports restricted to the supplied legacy checkout and installed Python.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

BASE = '8488047dbb7eafee1f5582cf59839c6bea0cf8cd'
PACKAGES = ('water_controls_wipe', 'heat_wave_blackout', 'iv_fluid_shortage', 'cyber_learning_loop')
SCRIPT = Path(__file__).resolve()


def scenarios(root):
    for package in PACKAGES:
        folder = root / 'scenarios' / package
        variants = sorted((folder / 'variants').glob('*/model.scn'))
        for entry in variants or [folder / 'model.scn']:
            yield (f'{package}:{entry.parent.name}' if variants else package), entry


def put(rows, kind, name, **fields):
    rows[f'{kind}::{name}'] = fields


def publication(rows, entry):
    path = entry.with_name('brief.toml')
    if not path.is_file() and entry.parent.parent.name == 'variants':
        path = entry.parents[2] / 'brief.toml'
    brief = tomllib.loads(path.read_text()) if path.is_file() else {}
    for key in ('featured', 'show', 'drivers', 'attack', 'choice_group'):
        if key in brief:
            put(rows, 'brief key', key, value=brief[key])
    for pair in brief.get('comparison', []):
        put(rows, 'comparison', f'{pair["run"]} against {pair["against"]}')
    for kind in ('sweep', 'spread'):
        for row in brief.get(kind, []):
            name = row['id']
            put(rows, kind, name, **{k: v for k, v in row.items() if k not in ('id', 'set')})
            for target, value in row.get('set', {}).items():
                put(rows, 'sweep setting', f'{name}/{target}', value=value)
            if kind == 'spread':
                document = json.loads((path.parent / 'spreads' / f'{name}.json').read_text())
                for target, value in document.get('set', {}).items():
                    put(rows, 'spread setting', f'{name}/all/{target}', value=value)
                for run, edits in document.get('runs', {}).items():
                    for target, value in edits.items():
                        put(rows, 'spread setting', f'{name}/{run}/{target}', value=value)


def historical(entry):
    from napkin.model.language import nodes as n
    from napkin.model.language.format import one_line
    from napkin.model.language.modules import read

    tree, _ = read(entry)
    rows = {}
    for thing in tree.things:
        kind = ('table' if thing.table else 'instance') if thing.template else thing.kind
        put(rows, 'entity', thing.name, kind_of_entity=kind, template=thing.template)
        for part in thing.members:
            if isinstance(part, n.Change) and part.lines and part.lines.value:
                put(
                    rows,
                    'instance setting',
                    f'{thing.name}.{part.name}',
                    value=one_line(part.lines.value.tokens),
                )
                continue
            if isinstance(part, n.LinkBind):
                value = (
                    '<' + ', '.join(part.targets) + '>' if isinstance(part.targets, list) else part.targets
                )
                put(rows, 'instance setting', f'{thing.name}.{part.name}', value=value)
                continue
            if isinstance(part, n.Value):
                fields = {'kind_of_field': {'var': 'state'}.get(part.kind, part.kind)}
                if part.kind == 'input':
                    fields.update(
                        default=one_line(part.value.tokens) if part.value else None,
                        lower=one_line(part.min.expr.tokens) if part.min else None,
                        upper=one_line(part.max.expr.tokens) if part.max else None,
                    )
            elif isinstance(part, (n.Event, n.Flow, n.LinkDecl)):
                fields = {
                    'kind_of_field': 'link' if isinstance(part, n.LinkDecl) else type(part).__name__.lower()
                }
            else:
                continue
            put(rows, 'field', f'{thing.name}.{part.name}', **fields)
    for output in tree.outputs:
        put(rows, 'root reading', output.name)
    for group in tree.profiles:
        put(rows, 'option group', group.name)
        for option in group.profiles:
            put(rows, 'option', option.name, group=group.name)
            for setting in option.settings:
                put(
                    rows,
                    'option setting',
                    f'{option.name}/{setting.target}',
                    value=one_line(setting.value.tokens),
                )
    for run in tree.runs:
        put(rows, 'run', run.name, options=run.profiles)
        if run.versus:
            put(rows, 'comparison', f'{run.name} against {run.versus}')
    return rows


def candidate(entry):
    from napkin.model import load_scenario
    from napkin.model import semantic as s
    from napkin.model.language import nodes as n
    from napkin.model.language.format import expression

    model = load_scenario(entry).declared
    rows = {}
    for entity in model.entities:
        kind = 'template' if isinstance(entity, s.DeclaredTemplate) else 'entity'
        put(rows, 'entity', entity.path, kind_of_entity=kind, template=None)
        for part in entity.parts:
            if isinstance(part, s.DeclaredValue):
                kind = part.kind
            elif isinstance(part, (s.DeclaredFlow, s.DeclaredLegs)):
                kind = 'flow'
            elif isinstance(part, s.DeclaredEvent):
                kind = 'event'
            elif isinstance(part, s.DeclaredSolver):
                kind = 'solver'
            else:
                continue
            put(rows, 'field', part.path, kind_of_field=kind)
    for member in (*model.members, *model.tables):
        if isinstance(member, s.DeclaredTable):
            kind = 'table'
        elif member.table is None:
            kind = 'instance'
        else:
            continue
        put(rows, 'entity', member.path, kind_of_entity=kind, template=member.template)
    for part in model.root:
        put(rows, 'root reading', part.path)
    # A reporting note can replace an old unestimated root output without declaring a value.
    for note in model.notes:
        if note.key == 'not_estimated':
            for item in note.notes:
                if '.' not in item.key and any(child.key == 'reason' for child in item.notes):
                    put(rows, 'root reading', item.key)
    for run in model.runs:
        put(rows, 'run', run.name, options=list(run.options))
    instances = {member.path for member in model.members if member.table is None}
    for item in model.tree.items:
        if isinstance(item, n.Declaration) and item.name in instances:
            for setting in item.properties:
                path = '.'.join((item.name, *setting.path))
                put(rows, 'instance setting', path, value=expression(setting.value))
        elif isinstance(item, n.Entity):
            for field in item.members:
                if isinstance(field, n.Declaration) and field.modifier == 'input':
                    limits = field.range
                    rows[f'field::{item.name}.{field.name}'].update(
                        default=expression(field.value) if field.value is not None else None,
                        lower=expression(limits.low) if limits and limits.low is not None else None,
                        upper=expression(limits.high) if limits and limits.high is not None else None,
                    )
        elif isinstance(item, n.Options):
            put(rows, 'option group', item.group)
            for option in item.options:
                put(rows, 'option', option.name, group=item.group)
                for setting in option.settings:
                    path = '.'.join(setting.path).replace('.instances.', '.')
                    put(rows, 'option setting', f'{option.name}/{path}', value=expression(setting.value))
    return rows


def inventory(root, extract):
    found = {}
    for name, entry in scenarios(root):
        rows = extract(entry)
        publication(rows, entry)
        found[name] = rows
    return found


def main(base):
    root = SCRIPT.parents[3]
    assert subprocess.check_output(['git', '-C', base, 'rev-parse', 'HEAD'], text=True).strip() == BASE
    subprocess.run(['git', '-C', base, 'diff', '--quiet', BASE, '--', 'scenarios', 'napkin'], check=True)
    old = json.loads(
        subprocess.check_output(
            [sys.executable, '-B', SCRIPT, base, '--legacy'],
            cwd=base,
            env={**os.environ, 'PYTHONPATH': str(base)},
        )
    )
    sys.path.insert(0, str(root))
    new = inventory(root, candidate)
    assert old.keys() == new.keys()
    differences = defaultdict(list)
    counts = Counter()
    for sid in new:
        package, _, variant = sid.partition(':')
        before, after = old[sid], new[sid]
        for key in sorted(before.keys() | after.keys()):
            fields = ''
            previous = current = ''
            if key not in before:
                status = 'added'
            elif key not in after:
                status = 'absent'
            else:
                a, b = before[key], after[key]
                edits = sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))
                fields = ','.join(edits)
                if edits:
                    previous, current = (
                        json.dumps({k: row.get(k) for k in edits}, ensure_ascii=False, sort_keys=True)
                        for row in (a, b)
                    )
                status = 'changed' if fields else 'matched'
            counts[package, status] += 1
            if status != 'matched':
                kind, name = key.split('::', 1)
                differences[package, kind, name, status, fields, previous, current].append(variant)
    writer = csv.writer(sys.stdout, lineterminator='\n')
    writer.writerow(
        ('package', 'variants', 'interface', 'name', 'status', 'changed_fields', 'previous', 'current')
    )
    for (package, kind, name, status, fields, previous, current), variants in sorted(differences.items()):
        all_variants = [sid.partition(':')[2] for sid in new if sid.partition(':')[0] == package]
        selected = '*' if variants == all_variants else ','.join(variants)
        writer.writerow((package, selected, kind, name, status, fields, previous, current))
    for package in PACKAGES:
        print(
            package,
            {k: counts[package, k] for k in ('matched', 'changed', 'absent', 'added')},
            file=sys.stderr,
        )


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('baseline', type=Path)
    cli.add_argument('--legacy', action='store_true', help=argparse.SUPPRESS)
    args = cli.parse_args()
    if args.legacy:
        print(json.dumps(inventory(args.baseline.resolve(), historical)))
    else:
        main(args.baseline.resolve())
