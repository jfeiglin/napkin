"""Synthetic packages and libraries for the evidence-tool tests, in the language of the rewrite: no
catalogue data, no network.

`SERVICE` is the main file of a package of a synthetic catalogue: twenty people wait for a service
that serves two of them an hour until it stops at 8 h, so 16 are served (8 under the run `half`, at
1 person an hour), and an archive template has two members. `evidence_library()` holds the source,
the claims and the red-team assumption that the records of the tests cite. `write_package` writes a
package below `root/scenarios`, with the shared library that its main file names and the records that
its folder owns.
"""

import copy
import hashlib
import json
import textwrap

from napkin.model.evidence import dependencies
from tests.units import PRELUDE, UNITS
from tests.units import library as test_library
from tools import catalogue

SERVICE = """\
scenario "Service"
    summary "People wait for a service that serves them until it stops."
    horizon 10 h
    library "../library"

options "Rate":
    "Full rate":
        "The service runs at its rate."
    "Half rate":
        "The service runs at half its rate."
        service.rate = 1 people/h  @halved

runs:
    full = "Full rate"
    half = "Half rate"

service:
    "The service."
    role operator
    input n: people = 20 people in [0 people, 100 people]  @fixture
        "People who need the service"
    input rate: people/h = 2 people/h in [0 people/h, 10 people/h]  @access
        "Rate of service"
    input end: h = 8 h in [1 h, 10 h]  @fixture
        "When the service stops"
    waiting: people = this.n in [0 people,]  @fixture
        "People waiting"
    served: people = 0 people in [0 people,]  @fixture
        "People served"
    flow serve: this.waiting -> this.served  @fixture
        "Service"
        request = this.rate
    stop = event():
        "The service stops."
        @assumption "The service stops at its end."
            assumption RT-FIXTURE
        when t >= this.end:
            this.stop.start()
        after 0 h:
            this.serve.request = 0 people/h

Archive:
    "Archived records."
    kept: people = 0 people in [0 people,]  @archived
    seen: people = 0 people in [0 people,]  @archived

north: Archive

south: Archive

record fixture: identity "Analytic contract fixture."
record access: source_transfer "Applied from another setting."
    claims:
        C-ACCESS
record halved: assumption "The rate halves."
    assumption RT-FIXTURE
record archived: source_transfer "Archived by the operator."
    claims:
        C-ACTION
"""


def fixture_claim(identifier, **fields):
    """A claim of the source `src`, with a verification record that pins its digest."""
    claim = {
        'id': identifier,
        'source': 'src',
        'locator': 'p. 1',
        'shows': f'{identifier} fixture fact.',
        'limits': 'Synthetic.',
        **fields,
    }
    digest = hashlib.sha256(
        json.dumps(claim, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    ).hexdigest()
    return {
        **claim,
        'verification': {
            'status': 'unverified',
            'date': '2026-09-18',
            'method': 'access_attempt',
            'notes': 'Synthetic.',
            'checked_fields': [],
            'content_sha256': digest,
        },
    }


def evidence_library():
    """The test library with the source `src`, its claims C-ACCESS and C-ACTION and the machine
    red-team assumption RT-FIXTURE, which C-ACTION supports."""
    lib = test_library()
    lib['sources'] = [
        {
            'id': 'src',
            'title': 'Fixture source',
            'custom': {
                'verification': {
                    'status': 'unverified',
                    'date': '2026-09-18',
                    'method': 'access_attempt',
                    'notes': 'Synthetic.',
                }
            },
        }
    ]
    lib['claims'] = [fixture_claim('C-ACCESS'), fixture_claim('C-ACTION')]
    lib['assumptions'] = [
        {
            'id': 'RT-FIXTURE',
            'statement': 'The service stops.',
            'rationale': 'Fixture.',
            'review': {'status': 'unreviewed'},
            'origin': 'model_redteam',
            'supports': [{'claim': 'C-ACTION', 'relation': 'mechanism_precedent'}],
            'elicitation': {
                'method': 'machine_redteam',
                'elicited': 'fixture',
                'date': '2026-09-18',
                'question': 'Does it?',
                'argument': 'Precedent.',
                'dissent': 'None cited.',
                'falsifier': 'A counterexample.',
            },
        }
    ]
    return lib


def vocabulary_of(library):
    """The shared library that a test library writes (`vocabulary.json`): the units of the test units
    (`tests.units.UNITS`) that the prelude does not hold, its conventions and the records that they rest
    on. Every other unit and record of the library is a folder's own."""
    shared = {key: copy.deepcopy(value) for key, value in test_library().items() if key != 'units'}
    shared['units'] = {name: copy.deepcopy(unit) for name, unit in UNITS.items() if name not in PRELUDE}
    if 'conventions' in library:
        shared['conventions'] = copy.deepcopy(library['conventions'])
        reached = dependencies({'conventions': library['conventions']}, library)
        for kind in catalogue.COLLECTIONS:
            ids = set(reached[kind])
            shared[kind] = [copy.deepcopy(record) for record in library.get(kind, ()) if record['id'] in ids]
    return shared


def write_package(root, files, library=None, *, owner='SC99'):
    """The entry file of the owner `owner` of a synthetic catalogue below `root`: a package's main file,
    or a variant's (`SC97:east`). `files` maps a file of the package's folder (`model.scn`, `common.scn`,
    `variants/east/model.scn`) to its text. The catalogue's shared library holds the units of the test
    library that the prelude does not hold and the conventions of `library` (the test library by
    default); the package's folder owns the other units and the records of `library`, and the folder of
    each variant owns none."""
    library = test_library() if library is None else library
    shared = vocabulary_of(library)
    package = catalogue.locate(owner.partition(':')[0], root).folder
    (root / catalogue.LIBRARY).mkdir(parents=True, exist_ok=True)
    (root / catalogue.LIBRARY / 'vocabulary.json').write_text(json.dumps(shared), encoding='utf-8')
    folders = []
    for name, text in files.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding='utf-8')
        if path.parent not in folders and (path.parent == package or path.name == 'model.scn'):
            folders.append(path.parent)
    for folder in folders:
        own = folder == package
        units = {
            name: unit
            for name, unit in library['units'].items()
            if own and name not in shared['units'] and name not in PRELUDE
        }
        (folder / 'units.json').write_text(json.dumps(units), encoding='utf-8')
        (folder / 'evidence').mkdir(exist_ok=True)
        for kind in catalogue.COLLECTIONS:
            held = {record['id'] for record in shared[kind]}
            records = [record for record in library.get(kind, []) if record['id'] not in held] if own else []
            (folder / 'evidence' / f'{kind}.json').write_text(json.dumps(records), encoding='utf-8')
    return catalogue.locate(owner, root).entry
