"""The units of the test library, and the test library itself.

This file reads no model and no part of the compiler: the prelude's units come from their file
(`napkin/std/units.json`) and the format version from the library's schema. So the tests of
`napkin/core/` need no front end. `tests/build.py` passes these names on to the tests of the models.
"""

import copy
import json
from pathlib import Path

from napkin.schema import FOLDER as SCHEMAS

# The library's own format version, as its schema states it.
LIBRARY_VERSION = json.loads((SCHEMAS / 'library.schema.json').read_text(encoding='utf-8'))['properties'][
    'schema_version'
]['const']

# The units of the test library. The prelude's units are its own, as every model's library has them
# (`napkin/std/units.json`).
PRELUDE = json.loads((Path(SCHEMAS).parent / 'std' / 'units.json').read_text(encoding='utf-8'))
UNITS = {
    'fraction': PRELUDE['fraction'],
    'h': PRELUDE['h'],
    'days': PRELUDE['days'],
    'per_h': {'dimensions': {'time': -1}, 'scale': 1},
    'people': PRELUDE['people'],
    'episodes': {'dimensions': {'episodes': 1}, 'scale': 1},
    'people/h': {'dimensions': {'people': 1, 'time': -1}, 'scale': 1},
    'people/day': {'dimensions': {'people': 1, 'time': -1}, 'scale': 1 / 24},
    'USD2025': {'dimensions': {'USD2025': 1}, 'scale': 1},
    'USD2024': {'dimensions': {'USD2024': 1}, 'scale': 1},
    'USD2025/h': {'dimensions': {'USD2025': 1, 'time': -1}, 'scale': 1},
}


def library():
    return {
        'schema_version': LIBRARY_VERSION,
        'id': 'test',
        'title': 'Test library',
        'sources': [],
        'claims': [],
        'assumptions': [],
        'units': copy.deepcopy(UNITS),
    }
