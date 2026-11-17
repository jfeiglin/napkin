"""`napkin compile`: read, check and prove a scenario and each of its variants, and list what it
offers (docs/cli.md).

The command compiles each model that the TARGET names, with every run checked (D-30): a package's
own model, or each of its variants, or the variant that `--variant` names. The engine does every check
of a model. The command adds the checks of the files that only the tools read:

- the stylesheet of each model, as D-22 finds it (`napkin.draw.style.of`: the variant's own
  `style.toml`, else its package's);
- for a package with variants, compiled whole, the records of the package's folder that no variant
  uses (`napkin.model.library.unused_shared_records`), each at its line in its JSON file.

Then it lists what the package offers: its variants, the runs, the options of each group and the
actors with their choices (`napkin.model.views.actors`), and how many values rest on evidence. A
value is a line of the package's files that cites records, counted once also when several variants
read it. It is sourced when one of its records is a `source` or a `source_transfer`, and assumed when
one of them is an `assumption`, so a value can be both. Identities and conventions are neither.
`--inputs` and `--outputs` add each input and each output of each model, and `--json` prints all of
it as one JSON document.

Exit codes: 0 when every model compiles and every check holds, 1 for any diagnostic of an error, 2
for a command line that is wrong.
"""

import json
import os
import re
import sys
from pathlib import Path

from .. import paths
from . import common

SUMMARY = 'read, check and prove a scenario and each of its variants; list what it offers'

DESCRIPTION = """\
Compile a scenario: every variant unless --variant names one. Lists its variants, runs and options;
--inputs/--outputs add each input (unit, range, basis) and each output. Checks style.toml too.
Exit 0 ok, 1 diagnostics."""

EXAMPLES = """\
example:
  napkin compile scenarios/water_controls_wipe"""

# The kinds of record that make a value sourced, and the kind that makes it assumed (docs/language.md,
# §2.10). Identities and conventions are neither.
SOURCED = frozenset({'source', 'source_transfer'})
ASSUMED = frozenset({'assumption'})
# The `"id"` key of a record in a JSON file of records, with the ID as JSON text.
ID_KEY = re.compile(r'"id"\s*:\s*("(?:[^"\\]|\\.)*")')
# The room of a list of names on its line, before the list shows its first and last names only.
ROOM = 90


def configure(parser):
    """The description, the example and the arguments of `napkin compile`: `args.variant`,
    `args.inputs`, `args.outputs`, `args.json` (each True or False) and `args.target`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    common.add_variant(parser, 'compile only this variant (default: every variant)')
    parser.add_argument(
        '--inputs', action='store_true', help='also list each input: its unit, range and basis'
    )
    parser.add_argument('--outputs', action='store_true', help='also list each output')
    parser.add_argument('--json', action='store_true', help='print what it lists as JSON')
    common.add_target(parser)


def main(args):
    """Compile the models that the arguments name, check their files, and print what they offer;
    give the exit code."""
    found = common.targets(args.target, args.variant)
    package = found[0].package
    models, problems = {}, {}
    for target in found:
        try:
            models[target.name] = common.load(target)
            problems[target.name] = []
        except common.Failed as exc:
            problems[target.name] = list(exc.diagnostics)
    for name, model in models.items():
        problems[name] += style_problems(model)
    # A package with variants runs as its variants: the records of its folder are checked when every
    # variant is compiled, and compiles.
    whole = bool(found[0].variants) and len(found) == len(found[0].variants)
    shared = unused_records(package) if whole and len(models) == len(found) else []
    title = file_title(paths.entry(package))
    if args.json:
        from .. import SCHEMA_VERSION
        from ..model.ir import thaw

        doc = {
            'schema_version': SCHEMA_VERSION,
            'package': package.name,
            'title': title,
            'models': {
                target.name: model_doc(models.get(target.name), problems[target.name], args)
                for target in found
            },
            'diagnostics': shared,
            'evidence': evidence_counts(models),
        }
        common.write_json(thaw(doc), sys.stdout)
    else:
        if models:
            listing(package.name, title, found, models, args)
        sys.stdout.flush()
        shown = [item for target in found for item in problems[target.name]] + shared
        lines = dict.fromkeys(common.located(item) for item in shown)
        for line in lines:
            sys.stderr.write(line + '\n')
        sys.stderr.flush()
    errors = [item for items in (*problems.values(), shared) for item in items if is_error(item)]
    return 1 if errors else 0


def is_error(item):
    return item.get('severity', 'error') == 'error'


# --- The checks of the files that only the tools read --------------------------------------------


def style_problems(model):
    """The diagnostics of the stylesheet of a model (`napkin.draw.style.of`, D-22), each with its
    file: none when the model has no stylesheet or its stylesheet holds."""
    from ..draw import style

    try:
        style.of(model)
    except style.StyleError as exc:
        return list(exc.diagnostics)
    except (OSError, UnicodeDecodeError) as exc:
        path = style.beside(model, style.STYLE_FILE)
        reason = f'not UTF-8 text: {exc.reason}' if isinstance(exc, UnicodeDecodeError) else exc.strerror
        return [style.problem(str(path), None, reason or str(exc))]
    return []


def unused_records(package):
    """The diagnostics of the records of the package's folder that no variant uses
    (`unused_shared_records`), each at the line of its `"id"` in its JSON file
    (`<folder>/evidence/<collection>.json`)."""
    from ..model.library import unused_shared_records

    out = []
    for item in unused_shared_records(package):
        _, _, rest = str(item['path']).partition('/evidence/')
        collection, _, identifier = rest.partition('/')
        file = Path(package) / 'evidence' / f'{collection}.json'
        line = record_line(file, identifier)
        out.append({**item, 'file': str(file), **({'line': line} if line else {})})
    return out


def record_line(path, identifier):
    """The line of the `"id"` key of the record `identifier` in the JSON file at `path`, or None."""
    try:
        text = Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None
    for match in ID_KEY.finditer(text):
        try:
            if json.loads(match.group(1)) == identifier:
                return text.count('\n', 0, match.start()) + 1
        except json.JSONDecodeError:
            continue
    return None


# --- What a package offers -------------------------------------------------------------------------


def file_title(entry):
    """The title of a model file: the text of its first declaration, `scenario "Title"` or `variant
    "Title"`, on one line; None for a file that does not read or has no such line."""
    from ..model.language.lex import SyntaxProblem
    from ..model.language.parse import parse

    try:
        block = parse(Path(entry).read_text(encoding='utf-8')).scenario
    except (SyntaxProblem, OSError, ValueError):
        return None
    if block is None or block.title is None or not isinstance(block.title.value, str):
        return None
    return ' '.join(block.title.value.split())


def offers(model):
    """What a model offers a reader, as JSON: its runs ({run: {label, options, versus}}), its options
    ({group: {option: its text}}) and its actors (`views.actors`)."""
    from ..model.ir import thaw
    from ..model.views import actors

    runs = {
        name: {'label': run['name'], 'options': list(run['options']), 'versus': run['comparison_of']}
        for name, run in model.runs.items()
    }
    return {'runs': runs, 'options': thaw(model.menu), 'actors': actors(model)}


def evidence_counts(models):
    """{sourced, assumed}: the values of the models that rest on a source (or a source applied here),
    and those that rest on an assumption. A value is a line of a file that cites records (an index use
    of the model, `model.index`), counted once across the models, so a line of a file that several
    variants read counts once."""
    kinds = {}
    for model in models.values():
        index = model.index
        for use in index['uses']:
            file = os.path.abspath(use.get('file') or index['file'])
            place = (file, use['line']) if use.get('line') else (file, use['part'])
            kinds.setdefault(place, set()).add(use['kind'])
    return {
        'sourced': sum(1 for found in kinds.values() if found & SOURCED),
        'assumed': sum(1 for found in kinds.values() if found & ASSUMED),
    }


def inputs_of(model):
    """{input: {label, type, unit, value, distribution, range, values, fixed, basis}} of each input of
    a model: `distribution` is the text of its distribution or None, `values` the names that a named
    input takes or None, and `basis` the kinds of its records."""
    from ..model.ir import thaw

    out = {}
    for name, item in model.inputs.items():
        distribution = item.get('distribution')
        out[name] = {
            'label': item.get('doc'),
            'type': item.get('type'),
            'unit': item.get('unit'),
            'value': thaw(item.get('value')),
            'distribution': distribution['text'] if distribution else None,
            'range': thaw(item.get('range')),
            'values': thaw(item.get('values')),
            'fixed': bool(item.get('fixed')),
            'basis': basis_kinds(item.get('basis')),
        }
    return out


def basis_kinds(basis):
    """The kinds of the records of a basis: one record, or a list of them."""
    records = basis if isinstance(basis, (list, tuple)) else [basis] if basis else []
    return [record.get('kind') for record in records if hasattr(record, 'get')]


def outputs_of(model):
    """{output: {outcome, label, unit, kind, scope, status}} of each output of a model, by its name in
    the file; `outcome` is its name in the report."""

    structure = next(iter(model.structures.values()))
    out = {}
    for name, outcome in model.outputs.items():
        item = structure.outcomes[outcome]
        out[name] = {
            'outcome': outcome,
            'label': item.label,
            'unit': item.unit,
            'kind': item.kind,
            'scope': item.scope,
            'status': item.status,
        }
    return out


def model_doc(model, problems, args):
    """The JSON of one model: whether it compiles (`admissible`), its title, its diagnostics and, for a
    model that compiles, what it offers, with its inputs and outputs when they are asked for."""
    doc = {
        'admissible': model is not None,
        'title': None if model is None else model.scenario.title,
        'diagnostics': list(problems),
    }
    if model is None:
        return {**doc, 'runs': None, 'options': None, 'actors': None}
    doc.update(offers(model))
    if args.inputs:
        doc['inputs'] = inputs_of(model)
    if args.outputs:
        doc['outputs'] = outputs_of(model)
    return doc


# --- Text ------------------------------------------------------------------------------------------


def listing(package, title, found, models, args):
    """Print what the package offers: its name and title, its variants, its runs, options and actors
    (once when every model offers the same, else for each group of variants that offer the same),
    each model's inputs and outputs when they are asked for, and how many models compiled and how
    many values rest on evidence."""
    print(f'{package}  {title}' if title else package)
    variants = [target for target in found if target.variant is not None]
    # The models that offer the same runs, options and actors, in order: one group when every model
    # offers the same.
    groups = {}
    for target in found:
        if target.name in models:
            item = offers(models[target.name])
            groups.setdefault(json.dumps(item, sort_keys=True), (item, []))[1].append(target)
    if variants:
        total = len(found[0].variants)
        count = f' of {total}' if len(variants) < total else ''
        names = names_line([target.variant for target in variants], count)
        runs = names_line(list(next(iter(groups.values()))[0]['runs']))
        if len(groups) == 1 and len(names) + len(runs) <= ROOM:
            print(f'  variants: {names}    runs: {runs}')
        elif len(groups) == 1:
            print(f'  variants: {names}')
            print(f'  runs:     {runs}')
        else:
            print(f'  variants: {names}')
    if len(groups) == 1:
        item, members = next(iter(groups.values()))
        if not variants:
            print(f'  runs:     {names_line(list(item["runs"]))}')
        offer_lines(item, '  ')
    else:
        for item, members in groups.values():
            own = file_title(members[0].entry) if len(members) == 1 else None
            head = names_line([target.variant for target in members])
            print(f'  {members[0].variant}  {own}' if own else f'  {head}')
            print(f'    runs:     {names_line(list(item["runs"]))}')
            offer_lines(item, '    ')
    for target in found:
        model = models.get(target.name)
        if model is None:
            continue
        whose = f' of {target.name}' if target.variant is not None else ''
        if args.inputs:
            input_lines(model, whose)
        if args.outputs:
            output_lines(model, whose)
    counts = evidence_counts(models)
    if variants:
        done = f'{len(models)} of {len(found)}' if len(models) < len(found) else f'{len(found)}'
        head = f'{done} variant{"s" if len(found) > 1 else ""} compiled'
    else:
        head = 'compiled'
    print(f'  {head} · evidence: {counts["sourced"]} sourced values, {counts["assumed"]} assumed')


def offer_lines(item, indent):
    """Print the options of each group (their real names, D-18) and the actors with their choices."""
    groups = [
        f'{group}: {", ".join(f"{json.dumps(option, ensure_ascii=False)}" for option in options)}'
        for group, options in item['options'].items()
    ]
    if groups:
        print(f'{indent}options:  {" · ".join(groups)}')
    actors = []
    for actor in item['actors']:
        choices = [
            f'{choice["event"]} ({", ".join(outcome["name"] for outcome in choice["outcomes"])})'
            for choice in actor['choices']
        ]
        actors.append(f'{actor["name"]}: {", ".join(choices)}' if choices else f'{actor["name"]}: no choices')
    if actors:
        print(f'{indent}actors:   {" · ".join(actors)}')


def names_line(names, count=''):
    """Names on one line with their number, `a, b, c (3)`. A list that takes more than `ROOM`
    characters shows its first names, `…` and its last name."""
    text = ', '.join(names)
    if len(text) > ROOM and len(names) > 2:
        shown = names[:1]
        for name in names[1:-1]:
            if len(', '.join([*shown, name, f'… {names[-1]}'])) > ROOM:
                break
            shown.append(name)
        text = ', '.join([*shown, f'… {names[-1]}'])
    return f'{text} ({len(names)}{count})'


def input_lines(model, whose):
    """Print each input of a model: its name, its value (or its distribution) with its unit, its range,
    the kinds of its records and its label."""
    found = inputs_of(model)
    rows = []
    for name, item in found.items():
        rows.append([name, value_text(item), range_text(item), ', '.join(item['basis']), item['label'] or ''])
    print(f'  inputs{whose} ({len(rows)}):')
    for row in common.table(rows):
        print(f'    {row}'.rstrip())


def value_text(item):
    if item['distribution']:
        return item['distribution']
    value = item['value']
    if item['type'] == 'bool':
        return 'true' if value else 'false'
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return f'{common.number(value)} {item["unit"]}'


def range_text(item):
    if item['fixed']:
        return 'fixed'
    if item['values']:
        return ' | '.join(json.dumps(value, ensure_ascii=False) for value in item['values'])
    if item['range']:
        low, high = item['range']
        return f'{common.number(low)} to {common.number(high)} {item["unit"]}'
    return ''


def output_lines(model, whose):
    """Print each output of a model: its name, unit, kind, label and scope, and `not estimated` for an
    output that the model does not estimate."""
    rows = []
    for name, item in outputs_of(model).items():
        label = item['label'] or ''
        if item['status'] == 'unestimated':
            label += ' (not estimated)'
        rows.append([name, item['unit'] or '', item['kind'] or '', label, item['scope'] or ''])
    print(f'  outputs{whose} ({len(rows)}):')
    for row in common.table(rows):
        print(f'    {row}'.rstrip())
