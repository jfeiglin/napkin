"""Make the corpus again from the specification.

    python extract_corpus.py            # writes corpus/NN-name.scn, corpus/data/*.csv, corpus/MANIFEST.tsv
    python extract_corpus.py --check    # writes nothing: fails when a file differs from the spec

Each fenced `text` block of `../spec.md` is one file `corpus/NN-name.scn`, byte for byte, in the order
of the spec. Each `csv` block is one file of `corpus/data/`, named by the bold file name that the spec
writes above it. `corpus/MANIFEST.tsv` gives, for each file, the lines of the spec that it comes from
and the place where its lines stand (`context`), which the parser needs because most blocks of the
spec are fragments:

    file     a whole model file: entities, templates, instances, tables, records, top-level values
    members  the lines of the body of an entity or of a template
    event    the lines of the body of an event (locals, flows, triggers, timing steps)

`corpus/inline.txt` is written by hand (the notation that the spec shows only inline); this script does
not touch it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE.parent / 'spec.md'
CORPUS = HERE / 'corpus'

# The name and the context of each `text` block, in the order of the spec. The key is the line of
# the spec where the block opens, so that a change of the spec that moves a block is seen.
TEXT_BLOCKS = [
    (41, 'grinder', 'file'),
    (68, 'range-and-assert', 'members'),
    (86, 'collection-literals', 'members'),
    (103, 'formulas', 'members'),
    (113, 'reportable-bindings', 'file'),
    (124, 'status-cases', 'file'),
    (142, 'none-and-record', 'file'),
    (158, 'input-draw', 'members'),
    (170, 'tank-clinic', 'file'),
    (235, 'local-allocation', 'file'),
    (268, 'network', 'file'),
    (379, 'staffing', 'file'),
    (403, 'water-electricity', 'file'),
    (454, 'provider-limit', 'file'),
    (505, 'record-delivery', 'file'),
    (521, 'switch', 'event'),
    (535, 'broadcast', 'event'),
    (556, 'inspect', 'members'),
    (592, 'trigger', 'members'),
    (607, 'clock-trigger', 'members'),
    (639, 'repair', 'members'),
    (656, 'legs', 'members'),
    (686, 'reserve-delivery', 'members'),
    (700, 'reserve-at-outset', 'members'),
    (720, 'changing-rate', 'members'),
    (738, 'diff', 'file'),
    (762, 'record-claims', 'file'),
]
CSV_NAME = re.compile(r'^\*\*([a-z_]+\.csv)\*\*$')


def blocks(lines):
    """(kind, first line of the block in the spec from 1, its lines) for each fenced block."""
    out, i = [], 0
    while i < len(lines):
        found = re.fullmatch(r'```(\w+)', lines[i])
        if found:
            start = i
            i += 1
            body = []
            while lines[i] != '```':
                body.append(lines[i])
                i += 1
            out.append((found.group(1), start + 1, body))
        i += 1
    return out


def files():
    """{path relative to corpus/: content} and the rows of the manifest."""
    lines = SPEC.read_text(encoding='utf-8').split('\n')
    found = blocks(lines)
    texts = [block for block in found if block[0] == 'text']
    tables = [block for block in found if block[0] == 'csv']
    others = [block for block in found if block[0] not in ('text', 'csv')]
    if others:
        raise SystemExit(f'a fenced block of another kind: {[(k, n) for k, n, _ in others]}')
    if [start for _, start, _ in texts] != [start for start, _, _ in TEXT_BLOCKS]:
        raise SystemExit(
            'the text blocks of the spec moved: '
            f'{[start for _, start, _ in texts]} against {[start for start, _, _ in TEXT_BLOCKS]}'
        )
    out, manifest = {}, []
    for number, ((_, start, body), (_, name, context)) in enumerate(zip(texts, TEXT_BLOCKS), 1):
        path = f'{number:02d}-{name}.scn'
        out[path] = '\n'.join(body) + '\n'
        manifest.append((path, f'{start + 1}-{start + len(body)}', context))
    for _, start, body in tables:
        # The name of a table is the bold line above its block.
        k = start - 2
        while not lines[k].strip():
            k -= 1
        named = CSV_NAME.fullmatch(lines[k].strip())
        if not named:
            raise SystemExit(f'no file name above the csv block at line {start}')
        path = f'data/{named.group(1)}'
        out[path] = '\n'.join(body) + '\n'
        manifest.append((path, f'{start + 1}-{start + len(body)}', 'table'))
    rows = ['file\tspec lines\tcontext'] + ['\t'.join(row) for row in manifest]
    out['MANIFEST.tsv'] = '\n'.join(rows) + '\n'
    return out


def main(argv):
    wanted = files()
    if '--check' in argv:
        wrong = [
            path
            for path, content in wanted.items()
            if not (CORPUS / path).exists() or (CORPUS / path).read_text(encoding='utf-8') != content
        ]
        if wrong:
            raise SystemExit(f'not as the spec writes them: {wrong}')
        print(f'{len(wanted) - 1} corpus files are the blocks of the spec, byte for byte')
        return
    for path, content in wanted.items():
        target = CORPUS / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    print(f'wrote {len(wanted) - 1} corpus files and MANIFEST.tsv')


if __name__ == '__main__':
    main(sys.argv[1:])
