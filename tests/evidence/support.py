"""Write independent synthetic evidence folders for evidence-tool tests, and change the records that a
line of a model text rests on."""

import json

from tests.build import indent, places
from tests.owned import own_units, vocabulary_of
from tools import catalogue


def write_library(root, scenario, library):
    """The folder of `scenario` below `root` with the records and the units of the test library
    `library` that it owns, and the shared vocabulary that the library writes (`owned.vocabulary_of`)."""
    shared = vocabulary_of(library)
    folder = catalogue.locate(scenario, root).evidence
    folder.mkdir(parents=True, exist_ok=True)
    (root / catalogue.LIBRARY).mkdir(parents=True, exist_ok=True)
    (root / catalogue.LIBRARY / 'vocabulary.json').write_text(json.dumps(shared))
    (folder.parent / 'units.json').write_text(json.dumps(own_units(library, shared)))
    for kind in ('sources', 'claims', 'assumptions'):
        ids = {record['id'] for record in shared[kind]}
        (folder / f'{kind}.json').write_text(json.dumps([r for r in library[kind] if r['id'] not in ids]))


def resting(text, place, record):
    """`text` with the line at `place` resting on `record` alone (docs/language.md, §2.10): the
    records at the end of the line go, and `record` follows the line's text, one level deeper. The
    record is written in place (`@kind "explanation"` with its lines), or it cites a named record
    (`@name`)."""
    found = places(text)
    rows = text.split('\n')
    start = found[place][0]
    rows[start] = rows[start].split('  @')[0]
    after = found[f'{place}/""'][1] if f'{place}/""' in found else start + 1
    depth = (len(rows[start]) - len(rows[start].lstrip(' '))) // 4 + 1
    return '\n'.join([*rows[:after], *indent(record, depth).split('\n'), *rows[after:]])
