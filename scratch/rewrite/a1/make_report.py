"""Make every table of this folder again.

    PYTHONPATH=/home/user/napkin-base python make_report.py

It runs, in this order:

1. `extract_corpus.py --check`: the corpus is the blocks of the spec, byte for byte;
2. the parser on each file of `corpus/`, on `corpus/inline.txt` and on `corpus/refused.txt`;
3. `hunt.py`: the ambiguity cases, written to `ambiguities.md`;
4. `check.py`: the checks behind the claims of FINDINGS.md;
5. `census_names.py`: the names and the notation of the present models, written to `census.md` and
   `census.json`;
6. a timing of the parser on the corpus: the best of three runs, with the load of the machine.

It writes `parse_report.md`. It exits with 1 when a file of the corpus does not parse, a refused
piece parses, or a check fails.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check  # noqa: E402
import hunt  # noqa: E402
import parser as P  # noqa: E402

CORPUS = HERE / 'corpus'


def cell(text):
    return str(text).replace('|', '&#124;').replace('\n', '<br>')


def code(text):
    """A piece of notation in a cell of a table."""
    return '`' + str(text).replace('|', '&#124;').replace('\n', ' ⏎ ') + '`'


def given(kind, found):
    """What the parser gives for a piece of inline notation, on one line."""
    if kind == 'expression':
        return P.sexpr(found)
    if kind == 'type':
        return f'{type(found).__name__} {P.type_text(found)}'
    if kind == 'range':
        return f'Range {P.show(found)}'
    return ' / '.join(' '.join(row.split()) for row in P.dump(found))


def best_of_three():
    """The seconds to read and parse the 27 files of the corpus: the best of three runs."""
    files = [(path.read_text(encoding='utf-8'), context) for path, context in check.corpus_files()]
    runs = []
    for _ in range(3):
        start = time.perf_counter()
        for text, context in files:
            P.parse(text, context)
        runs.append(time.perf_counter() - start)
    return min(runs), sum(text.count('\n') for text, _ in files)


def main():
    failed = 0
    out = ['# Parse report', '']
    out.append('`make_report.py` makes this file again. Nothing here is written by hand.')
    out.append('')
    out.append(f'- Python {platform.python_version()}; `napkin` from `{P.BASE}` (the base commit).')
    load = ', '.join(f'{value:.2f}' for value in os.getloadavg())
    out.append(f'- Load of the machine when this ran (1, 5, 15 min): {load}.')

    done = subprocess.run([sys.executable, str(HERE / 'extract_corpus.py'), '--check'], capture_output=True, text=True)
    out.append(f'- Corpus: {(done.stdout or done.stderr).strip()}.')
    failed += done.returncode != 0

    seconds, rows = best_of_three()
    out.append(
        f'- Time to parse the 27 files of the corpus ({rows} lines), best of three runs: {seconds * 1000:.1f} ms.'
    )
    out.append('')

    # ---- the blocks of the spec
    manifest = {}
    for row in (CORPUS / 'MANIFEST.tsv').read_text(encoding='utf-8').split('\n')[1:]:
        if row:
            name, spec, context = row.split('\t')
            manifest[name] = (spec, context)
    out.append('## The blocks of the spec')
    out.append('')
    out.append('Each fenced `text` block of `spec.md` is one file. `Stands in` is the place where its lines')
    out.append('stand: most blocks of the spec are fragments (`corpus/MANIFEST.tsv`).')
    out.append('')
    out.append('| File | Spec lines | Stands in | Result | What the tree holds |')
    out.append('| --- | --- | --- | --- | --- |')
    parsed = 0
    for path, context in check.corpus_files():
        spec, _ = manifest[path.name]
        try:
            tree = P.parse(path.read_text(encoding='utf-8'), context)
            parsed += 1
            out.append(f'| `{path.name}` | {spec} | {context} | parsed | {P.summary(tree)} |')
        except P.SyntaxProblem as problem:
            failed += 1
            where = f'line {problem.line}' + (f', column {problem.column}' if problem.column else '')
            out.append(f'| `{path.name}` | {spec} | {context} | **refused** at {where} | {cell(problem.message)} |')
    out.append('')
    out.append(f'{parsed} of {len(check.corpus_files())} files parse.')
    out.append('')
    tables = sorted((CORPUS / 'data').glob('*.csv'))
    out.append(
        f'The {len(tables)} `csv` blocks are in `corpus/data/` ({", ".join(f"`{t.name}`" for t in tables)}). '
        'The parser reads the line that names a table (`sites: Place from "places.csv"`); it does not read the '
        'table. The headers of two of them hold a unit after a colon (`supply_limit: W`), as the present tables do.'
    )
    out.append('')

    # ---- which places accept which block
    out.append('### The same block in another place')
    out.append('')
    out.append('A block is read where it stands. This table shows what each of the other two places says for it:')
    out.append('the place of a line is part of its meaning.')
    out.append('')
    out.append('| File | file | members | event |')
    out.append('| --- | --- | --- | --- |')
    for path, context in check.corpus_files():
        cells = []
        for place in ('file', 'members', 'event'):
            try:
                P.parse(path.read_text(encoding='utf-8'), place)
                cells.append('parsed' + (' (its place)' if place == context else ''))
            except P.SyntaxProblem as problem:
                cells.append(f'refused, line {problem.line}')
        out.append(f'| `{path.name}` | {" | ".join(cells)} |')
    out.append('')

    # ---- the inline notation
    out.append('## The notation that the spec shows inline')
    out.append('')
    out.append('`corpus/inline.txt`, one piece on each line. An expression is shown as a tree in brackets;')
    out.append('a line is shown as the nodes of its tree.')
    out.append('')
    kinds, wrong = Counter(), 0
    table = ['| Spec line | Kind | Notation | What the parser gives |', '| ---: | --- | --- | --- |']
    for number, columns in check.rows_of('inline.txt'):
        kind, spec, text = columns[:3]
        note = ' (derived)' if len(columns) > 3 else ''
        kinds[kind] += 1
        try:
            table.append(f'| {spec} | {kind}{note} | {code(text)} | {code(given(kind, P.parse_inline(kind, text)))} |')
        except P.SyntaxProblem as problem:
            wrong += 1
            table.append(f'| {spec} | {kind}{note} | {code(text)} | **refused**: {cell(problem.message)} |')
    failed += wrong
    total = sum(kinds.values())
    listed = ', '.join(f'{count} {kind}' for kind, count in kinds.most_common())
    out.append(f'{total - wrong} of {total} pieces parse ({listed}).')
    out.append('')
    out += table
    out.append('')

    # ---- the refused notation
    out.append('## The notation that the parser refuses')
    out.append('')
    out.append('`corpus/refused.txt`: notation of the present compiler that the spec quotes, candidates that')
    out.append('the rulings leave out, and what the rules of FINDINGS.md refuse. Each piece must be refused')
    out.append('with a message that holds the part written in the file.')
    out.append('')
    table = ['| From | Kind | Notation | Message |', '| --- | --- | --- | --- |']
    count = wrong = 0
    for number, (kind, origin, text, part) in check.rows_of('refused.txt'):
        count += 1
        try:
            found = P.parse_inline(kind, text)
            wrong += 1
            table.append(f'| {origin} | {kind} | {code(text)} | **parsed**: {code(given(kind, found))} |')
        except P.SyntaxProblem as problem:
            if part not in problem.message:
                wrong += 1
            mark = '' if part in problem.message else '**another message**: '
            table.append(f'| {origin} | {kind} | {code(text)} | {mark}{cell(problem.message)} |')
    failed += wrong
    out.append(f'{count - wrong} of {count} pieces are refused with their message.')
    out.append('')
    out += table
    out.append('')

    # ---- the hunt
    rows, cases, wrong = hunt.run()
    (HERE / 'ambiguities.md').write_text('\n'.join(rows), encoding='utf-8')
    failed += len(wrong)
    out.append('## The hunt for ambiguities')
    out.append('')
    out.append(
        f'`ambiguities.md` has the {len(hunt.ITEMS)} items of the brief with their grammar rules and {cases} cases; '
        f'{cases - len(wrong)} are as `hunt.py` writes them.'
    )
    out.append('')

    # ---- the checks
    out.append('## The checks')
    out.append('')
    out.append('`check.py`. Each check is behind a claim of FINDINGS.md.')
    out.append('')
    out.append('| Check | Result |')
    out.append('| --- | --- |')
    for test in check.TESTS:
        try:
            out.append(f'| `{test.__name__}` | {cell(test())} |')
        except AssertionError as problem:
            failed += 1
            out.append(f'| `{test.__name__}` | **failed**: {cell(problem)} |')
    out.append('')
    files, total, same, why, examples = check.catalogue_tokens()
    out.append('### The present models, token by token')
    out.append('')
    out.append(
        f'The new tokenizer against the present one (`lex.py` at the base commit), on each of the {total} logical '
        f'lines of the {files} present model files. {same} lines give the same tokens.'
    )
    out.append('')
    out.append('| Lines | Why they differ | First place |')
    out.append('| ---: | --- | --- |')
    for key, number in why.most_common():
        out.append(f'| {number} | {cell(key)} | `{examples[key]}` |')
    out.append('')

    # ---- the census
    done = subprocess.run(
        [sys.executable, str(HERE / 'census_names.py'), '--base', P.BASE],
        capture_output=True,
        text=True,
        env={**os.environ, 'PYTHONPATH': P.BASE},
    )
    failed += done.returncode != 0
    out.append('## The census of the present models')
    out.append('')
    out.append(f'`census_names.py`: {(done.stdout or done.stderr).strip()}. See `census.md`.')
    out.append('')

    (HERE / 'parse_report.md').write_text('\n'.join(out), encoding='utf-8')
    print(f'wrote parse_report.md, ambiguities.md, census.md and census.json; {failed} failures')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
