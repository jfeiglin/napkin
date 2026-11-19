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
    open: bool = true
        "The service is open"
    flow serve: this.waiting -> this.served  @fixture
        "Service"
        request = formula(this.rate if this.open else 0 people/h)
    stop = event():
        "The service stops."
        @assumption "The service stops at its end."
            assumption RT-FIXTURE
        when t >= this.end:
            this.stop.start()
        after 0 h:
            this.open = false

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


def datum_package(root, *, rate='2 people/h', datum=(2, 'people/h'), end='34 h', delay=(34, 'h'), half=None):
    """The service package of the synthetic catalogue, whose record `access` (cited by the rate)
    names the datum `rate` of C-ACCESS and whose record `timing` (cited by the end) the datum `delay`
    of C-ACTION; `half` is the record of the option "Half rate" in place of `@halved`."""
    library = evidence_library()
    library['claims'] = [
        fixture_claim('C-ACCESS', data={'rate': {'value': datum[0], 'unit': datum[1]}}),
        fixture_claim('C-ACTION', data={'delay': {'value': delay[0], 'unit': delay[1]}}),
    ]
    text = SERVICE.replace('input rate: people/h = 2 people/h', f'input rate: people/h = {rate}')
    text = text.replace(
        'input end: h = 8 h in [1 h, 10 h]  @fixture', f'input end: h = {end} in [1 h, 100 h]  @timing'
    )
    text = text.replace('        C-ACCESS\n', '        C-ACCESS\n            datum: rate\n')
    text += 'record timing: source "The time before the service stops."\n    claims:\n        C-ACTION\n            datum: delay\n'
    if half is not None:
        text = text.replace('service.rate = 1 people/h  @halved', f'service.rate = 1 people/h  {half}')
    return write_package(root, {'model.scn': text}, library)


# A package whose records cite no record of a library: a queue that one person joins each hour.
QUEUE = """\
scenario "Queue"
    horizon 4 h
    library "../library"

queue:
    "A queue."
    input arrivals: people/h = 1 people/h in [0 people/h, 10 people/h]  @fixture
        "Arrivals"
    waiting: people = 0 people in [0 people,]  @fixture
        "People waiting"
    flow arrive: SOURCE -> this.waiting  @fixture
        request = this.arrivals

record fixture: identity "Analytic contract fixture."
"""

# A family: the package SC97, whose main file uses its module `common`, and its variant `a`, which
# runs as the package's model. `{records}` stands for the records that the module cites.
FAMILY_MAIN = 'scenario "Queues"\n    horizon 4 h\n    library "../library"\nuse common\n'
FAMILY_MODULE = """\
queue:
    "A queue."
    input arrivals: people/h = 1 people/h in [0 people/h, 10 people/h]  {records}
        "Arrivals"
    waiting: people = 0 people in [0 people,]  @fixture
    flow arrive: SOURCE -> this.waiting  @fixture
        request = this.arrivals

record fixture: identity "Analytic contract fixture."
"""
FAMILY_VARIANT = 'variant "A"\n    horizon 6 h\n'


def family(root, library=None, records='@fixture', extra=''):
    """The entry file of the variant `SC97:a` of the family below `root` (see above), whose module's
    input cites `records`, with the lines `extra` at the end of the module."""
    module = FAMILY_MODULE.format(records=records) + extra
    files = {'model.scn': FAMILY_MAIN, 'common.scn': module, 'variants/a/model.scn': FAMILY_VARIANT}
    write_package(root, files, library, owner='SC97')
    return catalogue.locate('SC97:a', root).entry


# ---- evidence packs on a cached synthetic document ----------------------------------------------------

DOCUMENT = (
    'Incident summary. The con-\nfiguration change was reverted with high conﬁdence.\n'
    'Service restoration took 114 days in total; losses fell 42% after the soft­ware fix.\n'
    'Operators confirmed the breakers were reopened within 6 hours.\n'
)


def cached(tmp_path, content=DOCUMENT):
    """A retrieval record of `content`, whose bytes and extracted text are in `tmp_path/cache`."""
    from tools.evidence.fetch import extract, record

    raw = content.encode()
    found = record(
        'https://example.org/report.txt',
        'https://example.org/report.txt',
        200,
        'curl',
        'text/plain',
        raw,
        tmp_path / 'cache',
        retrieved_at='2026-09-18T00:00:00Z',
    )
    sha = found['sha256']
    return {**found, 'text': extract(tmp_path / 'cache' / 'sha256' / sha[:2] / f'{sha}.txt')}


def base_library():
    """The test library with one source that a pass did not reach, and its claim K-1."""
    from napkin.model.evidence import claim_digest

    lib = test_library()
    lib['sources'] = [
        {
            'id': 'kept',
            'type': 'report',
            'title': 'Kept source',
            'URL': 'https://example.org/kept',
            'custom': {
                'verification': {
                    'status': 'unverified',
                    'date': '2026-09-17',
                    'method': 'access_attempt',
                    'url': 'https://example.org/kept',
                    'notes': 'Not reached.',
                    'access': 'unavailable',
                }
            },
        }
    ]
    claim = {
        'id': 'K-1',
        'source': 'kept',
        'locator': 'p. 1',
        'evidence_type': 'guidance',
        'shows': 'Kept claim.',
        'limits': 'None.',
    }
    claim['verification'] = {
        'status': 'unverified',
        'date': '2026-09-17',
        'method': 'access_attempt',
        'checked_fields': [],
        'notes': 'Not reached.',
        'content_sha256': claim_digest(claim),
    }
    lib['claims'] = [claim]
    return lib


def claim(
    cid,
    *,
    quotes=('configuration change was reverted',),
    opened=True,
    fields=('shows', 'limits', 'quotes'),
    verdicts=None,
    method=None,
    data=None,
    action='new',
    **extra,
):
    """A claim of a pack, with the check of a pass that opened (or did not open) the document."""
    check = {
        'opened': opened,
        'checked_fields': list(fields),
        'field_verdicts': verdicts or {f: 'match' for f in fields},
        'notes': f'Checked {cid}.',
    }
    if method:
        check['method'] = method
    out = {
        'id': cid,
        'action': action,
        'locator': 'p. 1',
        'evidence_type': 'incident_report',
        'shows': f'{cid} shows.',
        'limits': f'{cid} limits.',
        'quotes': [{'locator': 'p. 1', 'text': q} for q in quotes],
        'check': check,
        **extra,
    }
    if data:
        out['data'] = data
    return out


def pack(tmp_path, sid, claims, *, retrievals=None, action='new', method=None, failures=(), owner='SC99'):
    """A pack of the folder `owner` with the source `sid` and its claims, on a cached document."""
    retrievals = [cached(tmp_path)] if retrievals is None else retrievals
    for c in claims:
        if c['check']['opened'] and retrievals:
            c['check'].setdefault('retrieval_sha256', retrievals[0]['sha256'])
    source = {'id': sid, 'action': action, 'access': 'accessible'}
    if action == 'new':
        source['csl'] = {'type': 'report', 'title': f'{sid} report', 'URL': 'https://example.org/report.txt'}
    if method:
        source['method'] = method
    return {
        'pack_version': '1',
        'scenario': owner,
        'pack_id': f'pack-{sid}',
        'agent': 'fixture',
        'date': '2026-09-18',
        'source': source,
        'retrievals': retrievals,
        'claims': claims,
        'access_failures': list(failures),
    }


def statuses(lib):
    """{claim: (status, method)} of a library."""
    return {c['id']: (c['verification']['status'], c['verification']['method']) for c in lib['claims']}
