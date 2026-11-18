"""What the present models write, counted with the present lexer and parser (base commit).

    PYTHONPATH=/home/user/napkin-base python census_names.py [--base /home/user/napkin-base]

It reads each `.scn` file under `examples/` and `scenarios/` of the base copy with the old front end
(`napkin.model.language`), and writes `census.json` and `census.md`:

- each name that a model declares, by its kind (thing, template, field, event, outcome, flow, share,
  link, output, record, run), with the files that declare it;
- each unit word that follows a number or stands as a type, and the forms that the proposed unit rule
  touches (`-`, `^`, `{...}`, a unit that an arithmetic operator follows);
- the texts that hold a backslash, a `#` or a brace, and the comment lines;
- the tokens of an expression that the new notation reads differently (`is`, `**`, `[`, `|`).

The reserved words that `parser.py` proposes are checked against the declared names.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def walk_members(thing, add, where):
    from napkin.model.language import nodes

    for member in thing.members:
        if isinstance(member, nodes.Value):
            add('field', member.name, where)
        elif isinstance(member, nodes.Event):
            add('event', member.name, where)
            for outcome in member.outcomes:
                if outcome.name != 'done':
                    add('outcome', outcome.name, where)
        elif isinstance(member, nodes.Flow):
            add('flow', member.name, where)
        elif isinstance(member, nodes.Allocate):
            add('share', member.name, where)
        elif isinstance(member, (nodes.LinkDecl, nodes.LinkBind)):
            add('link', member.name, where)
        elif isinstance(member, nodes.Output):
            add('output', member.name, where)
        elif isinstance(member, nodes.Change):
            add('changed member', member.name, where)


def census(base):
    from napkin.model.language import lex, nodes, parse

    names = defaultdict(lambda: defaultdict(set))  # kind -> name -> files
    units = Counter()  # unit word after a number
    type_units = Counter()  # unit word in a type
    notes = Counter()
    examples = defaultdict(list)
    files = sorted([*Path(base, 'examples').rglob('*.scn'), *Path(base, 'scenarios').rglob('*.scn')])

    def add(kind, name, where):
        names[kind][name].add(where)

    def example(key, text, limit=6):
        if len(examples[key]) < limit:
            examples[key].append(text)

    for path in files:
        where = str(path.relative_to(base))
        text = path.read_text(encoding='utf-8')
        found = lex.lines(text)
        for line in found:
            if line.kind == 'comment':
                notes['comment lines (a whole line)'] += 1
                continue
            tokens = line.tokens
            for i, token in enumerate(tokens):
                following = tokens[i + 1] if i + 1 < len(tokens) else None
                if token.kind == 'unit':
                    units[token.value] += 1
                    if following is not None and following.kind == 'op' and following.value in '+-*/':
                        notes['a unit, then a space and an arithmetic operator (48 h / 2)'] += 1
                        example('unit then operator', f'{where}:{token.line}')
                    if '{' in token.value:
                        notes['a unit with a text parameter ({item}/h)'] += 1
                        example('braces in a unit', f'{where}:{token.line} {token.value}')
                if token.kind == 'number' and following is not None and following.kind == 'name':
                    if following.space and following.value not in lex.NOT_UNITS:
                        notes['a number, then a name that is no unit token'] += 1
                        example('number then name', f'{where}:{token.line} {token.value} {following.value}')
                if token.kind == 'text':
                    if '\\' in token.value:
                        notes['texts with a backslash'] += 1
                        example('backslash in a text', f'{where}:{token.line}')
                    if '#' in token.value:
                        notes['texts with #'] += 1
                        example('# in a text', f'{where}:{token.line}')
                    if '{' in token.value:
                        notes['texts with a brace'] += 1
                    if token.lines > 1:
                        notes['texts over several lines'] += 1
                    notes['texts'] += 1
                if token.kind == 'name' and token.value == 'is':
                    notes['is (equality)'] += 1
                if token.kind == 'op' and token.value == '**':
                    notes['** (power of a value)'] += 1
                    example('**', f'{where}:{token.line}')
                if token.kind == 'op' and token.value == '^':
                    notes['^ outside a unit token'] += 1
                    example('^ as a token', f'{where}:{token.line}')
                if token.kind == 'op' and token.value == '|':
                    notes['| (named values)'] += 1
                if token.kind == 'op' and token.value in ('<', '>', '<=', '>='):
                    notes['comparisons with < > <= >='] += 1
            if len({t.line for t in tokens}) > 1 and not any(t.kind == 'text' and t.lines > 1 for t in tokens):
                notes['logical lines that a bracket wraps'] += 1
        parsed = parse.parse(text)
        for record in parsed.records:
            add('record', record.name, where)
        for run in parsed.runs:
            add('run', run.name, where)
        for output in parsed.outputs:
            add('output', output.name, where)
        for thing in [*parsed.things, *parsed.changes]:
            if thing.kind == 'template':
                add('template', thing.name, where)
            elif thing.kind == 'change':
                add('changed thing', thing.name, where)
            else:
                add('thing', thing.name, where)
            walk_members(thing, add, where)
            for member in thing.members:
                declared = getattr(member, 'type', None)
                if isinstance(member, nodes.Value) and isinstance(declared, str) and declared != 'bool':
                    type_units[declared] += 1
                if isinstance(member, nodes.Change) and member.lines is not None:
                    declared = member.lines.type
                    if isinstance(declared, str) and declared != 'bool':
                        type_units[declared] += 1
        for output in parsed.outputs:
            if isinstance(output.type, str):
                type_units[output.type] += 1
    return files, names, units, type_units, notes, examples


def unit_registry(base):
    """The names of the units that the prelude, the library and the packages declare."""
    declared = Counter()
    for path in [
        Path(base, 'napkin/std/units.json'),
        *Path(base, 'scenarios').rglob('units.json'),
        *Path(base, 'examples').rglob('units.json'),
        Path(base, 'scenarios/library/vocabulary.json'),
    ]:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        table = data.get('units', data) if isinstance(data, dict) else {}
        for name in table:
            if isinstance(table[name], dict):
                declared[name] += 1
    return declared


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='/home/user/napkin-base')
    args = parser.parse_args(argv)
    sys.path.insert(0, str(HERE))
    import parser as new  # the prototype: its reserved words

    files, names, units, type_units, notes, examples = census(args.base)
    declared_units = unit_registry(args.base)

    every = defaultdict(set)  # name -> kinds
    for kind, table in names.items():
        for name in table:
            every[name].add(kind)

    def hits(words):
        return {word: sorted(every[word]) for word in sorted(words) if word in every}

    reserved = hits(new.RESERVED)
    contextual = hits(new.CONTEXTUAL)
    type_words = hits(new.TYPE_WORDS)
    builtins = hits(new.FUNCTIONS | new.DISTRIBUTIONS)
    members = hits(new.BUILTIN_MEMBERS)
    python = hits(new.PYTHON_KEYWORDS - new.RESERVED)
    unit_hits = {word: declared_units[word] for word in sorted(new.RESERVED | new.TYPE_WORDS) if word in declared_units}
    # A name of a value that is also the name of a declared unit: `2 g` against `2 * g`.
    value_names = {name for name, kinds in every.items() if kinds - {'record', 'run'}}
    both = sorted(value_names & set(declared_units))
    capitals = {
        kind: sorted(name for name in table if name[:1].isupper())
        for kind, table in names.items()
        if kind not in ('template', 'record')
    }
    capitals = {kind: found for kind, found in capitals.items() if found}
    lower_templates = sorted(name for name in names.get('template', {}) if not name[:1].isupper())

    def forms(counter):
        out = Counter()
        for word, count in counter.items():
            if '-' in re.sub(r'\^-', '^', word):
                out['with - (a product)'] += count
            if '^' in word:
                out['with ^ (a power)'] += count
            if '/' in word:
                out['with / (a quotient)'] += count
            if '{' in word:
                out['with {name}'] += count
            if not re.fullmatch(new.UNIT_WORD.pattern, word):
                out['outside the proposed unit grammar'] += count
        return out

    summary = {
        'base': args.base,
        'files': len(files),
        'declared names': {kind: len(table) for kind, table in sorted(names.items())},
        'reserved words that a model declares': reserved,
        'contextual words that a model declares': contextual,
        'type words that a model declares': type_words,
        'function names that a model declares': builtins,
        'built-in member names that a model declares': members,
        'Python keywords (not reserved by the proposal) that a model declares': python,
        'reserved or type words that are declared units': unit_hits,
        'names of values that are also declared units': both,
        'names with a capital first letter, by kind': capitals,
        'templates with a small first letter': lower_templates,
        'unit words after a number': {'distinct': len(units), 'uses': sum(units.values()), **forms(units)},
        'unit words in a type': {'distinct': len(type_units), 'uses': sum(type_units.values()), **forms(type_units)},
        'units outside the proposed grammar': sorted(
            word for word in {*units, *type_units, *declared_units} if not re.fullmatch(new.UNIT_WORD.pattern, word)
        ),
        'declared units': {'distinct': len(declared_units), **forms(Counter(dict.fromkeys(declared_units, 1)))},
        'notation counts': dict(sorted(notes.items())),
        'examples': dict(examples),
        'where': {
            word: {kind: sorted(names[kind][word]) for kind in kinds}
            for word, kinds in {**reserved, **contextual, **type_words, **python}.items()
        },
    }
    (HERE / 'census.json').write_text(json.dumps(summary, indent=2, sort_keys=False) + '\n', encoding='utf-8')

    out = ['# Census of the present models (base commit)', '']
    out.append(f'{len(files)} `.scn` files under `examples/` and `scenarios/` of `{args.base}`, read with the')
    out.append('present lexer and parser. `census_names.py` makes this file again.')
    out.append('')
    out.append('## Declared names')
    out.append('')
    out.append('| Kind | Distinct names |')
    out.append('| --- | ---: |')
    for kind, count in summary['declared names'].items():
        out.append(f'| {kind} | {count} |')
    out.append('')

    def table(title, found, note):
        out.append(f'## {title}')
        out.append('')
        if not found:
            out.append(f'None. {note}'.strip())
            out.append('')
            return
        if note:
            out.append(note)
            out.append('')
        out.append('| Word | Declared as | Files |')
        out.append('| --- | --- | --- |')
        for word, kinds in found.items():
            where = sorted({f for kind in kinds for f in names[kind][word]})
            shown = ', '.join(where[:3]) + (f' and {len(where) - 3} more' if len(where) > 3 else '')
            out.append(f'| `{word}` | {", ".join(kinds)} | {shown} |')
        out.append('')

    table('Reserved words that a present model declares', reserved, 'Each of these names must change.')
    table(
        'Contextual words that a present model declares',
        contextual,
        'These stay valid names: the next token decides (`status ok` against `status: ...`).',
    )
    table('Type words that a present model declares', type_words, 'A value can keep the name; a unit or a template cannot.')
    table('Function names that a present model declares', builtins, 'These stay valid names: a call has `(` after the name.')
    table(
        'Built-in member names that a present model declares',
        members,
        'A name is refused only on an owner whose type has the built-in member (R-A1-09).',
    )
    table('Python keywords, not reserved by the proposal, that a present model declares', python, '')
    out.append('## Units')
    out.append('')
    out.append(f'- Reserved or type words that are declared units: {unit_hits or "none"}.')
    out.append(f'- Names of values that are also declared units: {", ".join(f"`{n}`" for n in both) or "none"}.')
    out.append(f'- Names with a capital first letter, by kind: {capitals or "none"}.')
    out.append(f'- Templates with a small first letter: {lower_templates or "none"}.')
    out.append('')
    out.append('| Where | Distinct | Uses | With `/` | With `-` | With `^` | With `{name}` | Outside the proposed grammar |')
    out.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
    for title, key in (('After a number', 'unit words after a number'), ('In a type', 'unit words in a type')):
        row = summary[key]
        out.append(
            f'| {title} | {row["distinct"]} | {row["uses"]} | {row.get("with / (a quotient)", 0)} | '
            f'{row.get("with - (a product)", 0)} | {row.get("with ^ (a power)", 0)} | {row.get("with {name}", 0)} | '
            f'{row.get("outside the proposed unit grammar", 0)} |'
        )
    row = summary['declared units']
    out.append(
        f'| Declared in a registry | {row["distinct"]} | | {row.get("with / (a quotient)", 0)} | '
        f'{row.get("with - (a product)", 0)} | {row.get("with ^ (a power)", 0)} | {row.get("with {name}", 0)} | '
        f'{row.get("outside the proposed unit grammar", 0)} |'
    )
    out.append('')
    outside = summary['units outside the proposed grammar']
    out.append(f'Unit words outside the proposed grammar: {", ".join(f"`{w}`" for w in outside) or "none"}.')
    out.append('')
    out.append('## Notation counts')
    out.append('')
    out.append('| Form | Count |')
    out.append('| --- | ---: |')
    for key, count in summary['notation counts'].items():
        out.append(f'| {key} | {count} |')
    out.append('')
    out.append('## Examples')
    out.append('')
    for key, found in summary['examples'].items():
        out.append(f'- {key}: ' + '; '.join(f'`{item}`' for item in found))
    out.append('')
    (HERE / 'census.md').write_text('\n'.join(out), encoding='utf-8')
    print(f'{len(files)} files; wrote census.json and census.md')


if __name__ == '__main__':
    main(sys.argv[1:])
