"""Evidence authoring tools: quote normalization, status by rule, idempotent integration.

Packs and cached documents are synthetic and live under tmp_path (`tests/evidence/support.py`);
nothing touches the network, the real cache or scenario evidence files. Expected statuses follow from
the documented rules applied to hand-built inputs, never from a production run. The checks of the
catalogue's own files wait for stage M (`tests/evidence/test_catalogue.py`).
"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from napkin.model.evidence import claim_digest, validate_library
from tests.evidence.support import DOCUMENT, base_library, cached, claim, pack, statuses
from tests.units import library
from tools import catalogue
from tools.evidence.fetch import GS, archive_id, extract, extract_bytes, record, sniff
from tools.evidence.integrate import PACK_SCHEMA, IntegrationError, dump, integrate, pack_validator, rematch
from tools.evidence.normalize import NORMALIZATION, match_quotes, matches, normalize


@pytest.mark.parametrize(
    'quote,text',
    [
        ('high confidence', 'with high con\ufb01dence.'),  # fi ligature in the document
        ('the software fix', 'the soft\u00adware fix'),  # soft hyphen inside a word
        ('configuration change', 'the con-\nfiguration change'),  # line-break hyphenation
        ('a multi-site attack', 'a multi-\nsite attack'),  # hyphenated compound broken at the line end
        ('rose 4.2%', 'it rose 4.2 % overall'),  # percent is its own token either way
        ('1,445,630 residents', 'of 1,445,630 residents.'),
        ('Reopened within 6 HOURS', 'reopened\n within 6 hours'),
        ('45 439 residents', 'of 45 439 residents'),  # narrow no-break space groups one number
        ('104–127 volts', 'range 104---127 volts'),  # extracted en dash is a range, not a sign
        ('fell −0.4%', 'losses fell −0.4% overall'),
        ('a cyberattack', 'a cyber\u00ad\nattack'),  # a soft hyphen breaks one word at the line end
    ],
)
def test_normalization_matches_layout_variants(quote, text):
    assert matches(quote, text)


@pytest.mark.parametrize(
    'quote,text',
    [
        ('14 days', 'took 114 days in total'),  # digit boundary
        ('4.2%', 'losses fell 42% after'),  # decimal point is kept
        ('confident', 'with high confidence'),  # whole tokens only
        ('confidence', 'we are confident'),
        ('4.2', 'a ratio of 14.2'),
        ('1,000', 'about 1 000 people'),
        ('', 'any text'),
        ('5% of deaths', '.5% of deaths'),  # a leading decimal point stays with its number
        ('0.4% decline', '−0.4% decline'),  # so does a sign
        ('2% of deaths', '14·2% of deaths'),  # a middle-dot decimal
        ('102 people', '10² people'),  # a superscript is not a digit
        ('2 hours', '1½ hours'),  # nor is a vulgar fraction
        ('outage affected 225', '225 000 customers'),  # thin-space digit groups are one number
        ('cyber attack', 'a cyber\u00ad\nattack'),  # a soft hyphen never splits a word in two
        ('20202021', 'from 2020\u00ad\n2021'),  # nor joins two numbers
    ],
)
def test_normalization_rejects_counterexamples(quote, text):
    assert not matches(quote, text)


def test_normalized_form_keeps_numbers_and_percent():
    assert normalize('Losses: 4.2%, then 1,000 (approx.)!') == 'losses 4.2 % then 1,000 approx'
    assert normalize('e\ufb03cient \ufb02ow') == 'efficient flow'
    assert match_quotes(
        [{'locator': 'p1', 'text': 'high confidence'}, {'text': '14 days', 'locator': 'p2'}], DOCUMENT
    ) == (1, 2)


def test_claim_digest_is_the_compilers_digest_over_every_field_but_verification():
    lib = library()
    lib['sources'] = [
        {
            'id': 's',
            'title': 'S',
            'custom': {
                'verification': {
                    'status': 'unverified',
                    'date': '2026-09-18',
                    'method': 'fixture',
                    'notes': 'n',
                }
            },
        }
    ]
    claim = {
        'id': 'c',
        'source': 's',
        'locator': 'p. 1',
        'shows': 'Shows',
        'limits': 'Limits',
        'evidence_type': 'guidance',
        'valid_for': {'unit': 'x'},
    }
    independent = hashlib.sha256(
        json.dumps(claim, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    ).hexdigest()
    assert claim_digest(claim) == independent == claim_digest(dict(reversed(list(claim.items()))))
    claim['verification'] = {
        'status': 'unverified',
        'date': '2026-09-18',
        'method': 'fixture',
        'notes': 'n',
        'checked_fields': [],
        'content_sha256': independent,
    }
    claim['verified'] = True
    lib['claims'] = [claim]
    assert not validate_library(lib)
    for field, value in [
        ('locator', 'p. 2'),
        ('evidence_type', 'news_report'),
        ('valid_for', {'unit': 'y'}),
        ('quotes', [{'locator': 'p', 'text': 't'}]),
    ]:
        edited = copy.deepcopy(lib)
        edited['claims'][0][field] = value
        assert [d['code'] for d in validate_library(edited)] == ['evidence_digest'], field


def test_fetch_and_extract_records_are_content_addressed(tmp_path):
    assert archive_id('https://web.archive.org/web/20180129123848/https://www.fda.gov/x') == (
        'https://www.fda.gov/x',
        'https://web.archive.org/web/20180129123848id_/https://www.fda.gov/x',
    )
    assert archive_id('https://example.org/a', '20240101') == (
        'https://example.org/a',
        'https://web.archive.org/web/20240101id_/https://example.org/a',
    )
    html = b'<html><head><style>p{}</style><script>var hidden=1;</script></head><body><p>First</p><p>second &amp; third</p></body></html>'
    (tmp_path / 'page').write_bytes(html)
    r = record(
        'https://example.org/a', 'https://example.org/a', 200, 'manual', 'text/html', html, tmp_path / 'cache'
    )
    assert (
        r['sha256'] == hashlib.sha256(html).hexdigest()
        and r['bytes'] == len(html)
        and r['cache_path'].endswith(r['sha256'] + '.html')
    )
    text = extract(r['cache_path'])
    body = Path(text['cache_path']).read_text()
    assert (
        'hidden' not in body
        and 'p{}' not in body
        and matches('first second & third', body)
        and not matches('firstsecond', body)
    )
    assert text['sha256'] == hashlib.sha256(body.encode()).hexdigest() and extract(r['cache_path']) == text


@pytest.mark.parametrize(
    'url, extension',
    [
        ('https://www.cisa.gov', 'bin'),  # a host names no file
        ('https://doi.org/10.1016/j.cell.2020.01.001', 'bin'),  # a number is no extension
        ('https://example.org/view?file=report.pdf', 'bin'),  # nor is a query
        ('https://example.org/data/Table.XLSX?download=1#top', 'xlsx'),
    ],
)
def test_bytes_of_no_known_type_take_the_extension_of_their_file_name(url, extension):
    assert sniff(b'\x00\x01 opaque bytes', '', url) == ('application/octet-stream', extension)


@pytest.mark.parametrize('media', ['text/html; CHARSET=ISO-8859-1', 'TEXT/HTML; charset=ISO-8859-1'])
def test_the_charset_of_a_media_type_in_any_case_decodes_html(tmp_path, media):
    html = '<html><body><p>Caf\u00e9 cr\u00e8me</p></body></html>'.encode('latin-1')
    r = record('https://example.org/a', 'https://example.org/a', 200, 'manual', media, html, tmp_path)
    assert 'Caf\u00e9 cr\u00e8me' in extract_bytes(html, 'html', r['media_type'])[1]


@pytest.mark.skipif(
    not Path(GS).exists(), reason='Ghostscript is an authoring dependency, not a gate dependency'
)
def test_pdf_text_comes_from_ghostscript_txtwrite():
    stream = b'BT /F1 12 Tf 72 720 Td (Restoration took 14 days at 4.2% loss) Tj ET'
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    pdf = b'%PDF-1.4\n'
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += b'%d 0 obj\n' % number + body + b'\nendobj\n'
    start = len(pdf)
    pdf += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(b'%010d 00000 n \n' % o for o in offsets)
    pdf += b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % start
    extractor, text = extract_bytes(pdf, 'pdf')
    assert extractor.startswith('gs-') and extractor.endswith(' txtwrite-pages')
    assert (
        matches('took 14 days at 4.2% loss', text)
        and not matches('4 days', text)
        and not matches('42%', text)
    )


# Integration on synthetic packs.


def test_integration_assigns_status_by_rule(tmp_path):
    packs = [
        (
            'a.json',
            pack(
                tmp_path,
                'doc',
                [
                    claim(
                        'V-OK',
                        quotes=('configuration change was reverted', 'high confidence', 'within 6 hours'),
                    ),
                    claim('P-DIGIT', quotes=('restoration took 14 days',)),  # the document says 114 days
                    claim('P-PERCENT', quotes=('fell 4.2% after',)),  # the document says 42%
                    claim('P-FIELDS', fields=('shows', 'quotes')),
                    claim(
                        'P-VERDICT',
                        verdicts={
                            'shows': 'mismatch: says 6 h, not 4 h',
                            'limits': 'match',
                            'quotes': 'match',
                        },
                    ),
                    claim('P-NOQUOTE', quotes=()),
                    claim('P-DATA', data={'duration': {'value': 6, 'unit': 'h'}}),
                    claim('P-INDEXED', method='primary_indexed_extract'),
                    claim('U-CLOSED', opened=False, fields=()),
                ],
            ),
        ),
        (
            'b.json',
            pack(
                tmp_path,
                'third',
                [claim('P-THIRD', method='third_party_primary_retrieval')],
                method='third_party_primary_retrieval',
            ),
        ),
    ]
    lib, report = integrate(base_library(), packs, tmp_path / 'cache')
    got = statuses(lib)
    assert got['V-OK'] == ('verified', 'primary_full_text')
    for cid in ('P-DIGIT', 'P-PERCENT', 'P-FIELDS', 'P-VERDICT', 'P-NOQUOTE', 'P-DATA'):
        assert got[cid] == ('partial', 'primary_full_text'), cid
    assert got['P-INDEXED'] == ('partial', 'primary_indexed_extract')
    assert got['P-THIRD'] == (
        'partial',
        'third_party_primary_retrieval',
    )  # never verified, even when every other rule holds
    assert got['U-CLOSED'] == ('unverified', 'access_attempt') and got['K-1'] == (
        'unverified',
        'access_attempt',
    )
    claims = {c['id']: c for c in lib['claims']}
    ok = claims['V-OK']['verification']
    assert (
        ok['quote_match'] == {'normalization': NORMALIZATION, 'matched': 3, 'total': 3}
        and ok['retrieval_sha256'] == packs[0][1]['retrievals'][0]['sha256']
    )
    assert (
        claims['P-DIGIT']['verification']['quote_match']['matched'] == 0
        and '0/1 quotes re-matched' in claims['P-DIGIT']['verification']['notes']
    )
    assert (
        'quote_match' not in claims['U-CLOSED']['verification']
        and claims['U-CLOSED']['verification']['checked_fields'] == []
    )
    assert all(c['verification']['content_sha256'] == claim_digest(c) for c in lib['claims'])
    assert next(c['id'] for c in lib['claims']) == 'K-1' and report['new_claims'][:2] == ['V-OK', 'P-DIGIT']
    sources = {s['id']: s['custom']['verification'] for s in lib['sources']}
    assert (
        sources['doc']['status'] == 'partial'
        and sources['third']['status'] == 'partial'
        and sources['kept']['status'] == 'unverified'
    )
    assert (
        sources['doc']['retrieval']['text']['sha256'] == packs[0][1]['retrievals'][0]['text']['sha256']
        and 'cache_path' not in sources['doc']['retrieval']
    )
    only = [('c.json', pack(tmp_path, 'solo', [claim('V-SOLO')]))]
    assert (
        integrate(base_library(), only, tmp_path / 'cache')[0]['sources'][-1]['custom']['verification'][
            'status'
        ]
        == 'verified'
    )


def test_cache_tampering_and_missing_text_block_verification(tmp_path):
    good = cached(tmp_path)
    path = tmp_path / 'cache' / 'sha256' / good['sha256'][:2] / f'{good["sha256"]}.txt'
    lib, _ = integrate(
        base_library(),
        [('a.json', pack(tmp_path, 'doc', [claim('C')], retrievals=[good]))],
        tmp_path / 'cache',
    )
    assert statuses(lib)['C'] == ('verified', 'primary_full_text')
    path.write_text(DOCUMENT.replace('114', '14'))  # bytes no longer hash to the record
    lib, report = integrate(
        base_library(),
        [('a.json', pack(tmp_path, 'doc', [claim('C')], retrievals=[good]))],
        tmp_path / 'cache',
    )
    assert statuses(lib)['C'] == ('partial', 'primary_full_text') and report['retrieval_problems']
    assert lib['sources'][-1]['custom']['verification']['method'] == 'access_attempt'
    path.write_text(DOCUMENT)
    Path(good['text']['cache_path']).write_text('replaced text with configuration change was reverted')
    lib, _ = integrate(
        base_library(),
        [('a.json', pack(tmp_path, 'doc', [claim('C')], retrievals=[good]))],
        tmp_path / 'cache',
    )
    assert statuses(lib)['C'] == (
        'verified',
        'primary_full_text',
    )  # re-extracted text reproduces the recorded sha256
    wrong = {**good, 'text': {**good['text'], 'sha256': '0' * 64}}
    lib, _ = integrate(
        base_library(),
        [('a.json', pack(tmp_path, 'doc', [claim('C')], retrievals=[wrong]))],
        tmp_path / 'cache',
    )
    assert statuses(lib)['C'] == ('partial', 'primary_full_text')


def test_reapplying_packs_is_a_no_op_and_downgrades_keep_their_history(tmp_path):
    first = [
        ('a.json', pack(tmp_path, 'doc', [claim('V-1'), claim('P-1', quotes=('14 days',))])),
        (
            'b.json',
            {
                'pack_version': '1',
                'kind': 'assumptions',
                'scenario': 'SC99',
                'upsert': [
                    {
                        'id': 'A-SC99-new',
                        'statement': 'S',
                        'rationale': 'R',
                        'review': {'status': 'unreviewed'},
                    }
                ],
                'retire': [],
            },
        ),
    ]
    once, _ = integrate(base_library(), first, tmp_path / 'cache')
    twice, report = integrate(once, first, tmp_path / 'cache')
    assert (
        dump(twice) == dump(once)
        and not report['upgrades']
        and not report['downgrades']
        and not report['new_claims']
    )
    again = [
        (
            'a.json',
            pack(
                tmp_path,
                'doc',
                [
                    claim('V-1', quotes=('4.2%',), action='revise'),
                    claim('P-1', quotes=('14 days',), action='reverify'),
                ],
                action='reverify',
            ),
        )
    ]
    down, report = integrate(once, again, tmp_path / 'cache')
    notes = next(c for c in down['claims'] if c['id'] == 'V-1')['verification']['notes']
    assert report['downgrades'] == [{'claim': 'V-1', 'from': 'verified', 'to': 'partial'}]
    assert notes.endswith(' Previously verified (primary_full_text, 2026-09-18).')
    assert dump(integrate(down, again, tmp_path / 'cache')[0]) == dump(down)
    assert [c['id'] for c in down['claims']] == [c['id'] for c in once['claims']]


def test_integration_rejects_conflicts_instead_of_guessing(tmp_path):
    lib = base_library()
    with pytest.raises(IntegrationError, match='also in'):
        integrate(
            lib,
            [
                ('a.json', pack(tmp_path, 'one', [claim('X')])),
                ('b.json', pack(tmp_path, 'two', [claim('X')])),
            ],
            tmp_path / 'cache',
        )
    with pytest.raises(IntegrationError, match='use action revise'):
        integrate(
            lib,
            [('a.json', pack(tmp_path, 'kept', [claim('K-1', action='reverify')], action='reverify'))],
            tmp_path / 'cache',
        )
    foreign = pack(tmp_path, 'foreign', [claim('FOREIGN')])
    foreign['scenario'] = 'SC98'
    with pytest.raises(IntegrationError, match='one scenario folder'):
        integrate(
            lib, [('a.json', pack(tmp_path, 'one', [claim('OWN')])), ('b.json', foreign)], tmp_path / 'cache'
        )
    with pytest.raises(IntegrationError, match='related claim'):
        integrate(
            lib,
            [
                (
                    'a.json',
                    pack(
                        tmp_path,
                        'doc',
                        [claim('R', related=[{'claim': 'MISSING', 'relation': 'consistent_with'}])],
                    ),
                )
            ],
            tmp_path / 'cache',
        )
    stale = copy.deepcopy(lib)
    stale['claims'][0]['shows'] = 'Edited by hand.'
    with pytest.raises(IntegrationError, match='digest is stale'):
        integrate(stale, [('a.json', pack(tmp_path, 'doc', [claim('V')]))], tmp_path / 'cache')
    two = pack(
        tmp_path,
        'doc',
        [claim('A'), claim('B', quotes=('first line',))],
        retrievals=[cached(tmp_path), cached(tmp_path, 'The first line.')],
    )
    two['claims'][1]['check']['retrieval_sha256'] = two['retrievals'][1]['sha256']
    with pytest.raises(IntegrationError, match='one per source'):
        integrate(lib, [('a.json', two)], tmp_path / 'cache')
    with pytest.raises(IntegrationError, match='check'):
        bad = pack(tmp_path, 'doc', [claim('V')])
        del bad['claims'][0]['check']
        integrate(lib, [('a.json', bad)], tmp_path / 'cache')


def test_a_pack_relates_claims_only_by_the_relations_of_the_library(tmp_path):
    proves = pack(tmp_path, 'doc', [claim('R', related=[{'claim': 'K-1', 'relation': 'proves'}])])
    with pytest.raises(IntegrationError, match=r"a\.json: claims/0/related/0/relation 'proves'"):
        integrate(base_library(), [('a.json', proves)], tmp_path / 'cache')


@pytest.mark.parametrize(
    'owner, valid',
    [
        # A package (a scenario's folder or a family's folder of modules), or a variant of one.
        ('SC99', True),
        ('SC99_east', True),
        ('SC99:east', True),
        ('SC99_a:b_2', True),
        ('water_controls:juneau', True),
        ('', False),
        ('SC99:', False),
        (':east', False),
        ('SC99:East', False),
        ('SC99:east:west', False),
        ('SC99/east', False),
        ('../SC99', False),
        ('9SC', False),
    ],
)
def test_a_pack_names_a_package_or_a_variant_of_a_package(tmp_path, owner, valid):
    source = {**pack(tmp_path, 'doc', [claim('V-1')]), 'scenario': owner}
    assumptions = {'pack_version': '1', 'kind': 'assumptions', 'scenario': owner, 'upsert': [], 'retire': []}
    validator = pack_validator()
    for document in (source, assumptions):
        problems = [list(error.path) for error in validator.iter_errors(document)]
        assert problems == ([] if valid else [['scenario']]), (owner, document.get('kind'))


def test_the_pack_schema_is_a_tool_file_and_the_package_ships_only_the_compiler_schemas():
    from napkin.model.load import SCHEMAS
    from napkin.schema import FOLDER

    assert PACK_SCHEMA.is_file() and PACK_SCHEMA.parent == catalogue.ROOT / 'tools' / 'evidence'
    shipped = sorted(path.name for path in FOLDER.glob('*.json'))
    assert shipped == sorted(f'{name}.schema.json' for name in SCHEMAS)


def test_reverify_cannot_launder_a_hand_edit(tmp_path):
    lib, _ = integrate(
        base_library(), [('a.json', pack(tmp_path, 'doc', [claim('V-1')]))], tmp_path / 'cache'
    )
    edited = copy.deepcopy(lib)
    v = next(c for c in edited['claims'] if c['id'] == 'V-1')
    v['shows'] = 'Edited by hand.'
    v['data'] = {'duration': {'value': 40, 'unit': 'days'}}
    bare = {k: val for k, val in claim('V-1', action='reverify').items() if k in ('id', 'action', 'check')}
    with pytest.raises(IntegrationError, match='changed by hand'):
        integrate(edited, [('a.json', pack(tmp_path, 'doc', [bare], action='reverify'))], tmp_path / 'cache')


def test_assumption_packs_never_review_or_change_origin(tmp_path):
    def upsert(**record):
        return [
            (
                'b.json',
                {
                    'pack_version': '1',
                    'kind': 'assumptions',
                    'scenario': 'SC99',
                    'upsert': [
                        {
                            'id': 'A-SC99-new',
                            'statement': 'S',
                            'rationale': 'R',
                            'review': {'status': 'unreviewed'},
                            **record,
                        }
                    ],
                    'retire': [],
                },
            )
        ]

    lib, _ = integrate(
        base_library(),
        upsert(
            origin='model_redteam',
            elicitation={
                'method': 'machine_redteam',
                'elicited': 'e',
                'date': '2026-09-18',
                'question': 'q',
                'argument': 'a',
                'dissent': 'd',
                'falsifier': 'f',
            },
        ),
        tmp_path / 'cache',
    )
    with pytest.raises(IntegrationError, match='must be unreviewed'):
        integrate(lib, upsert(review={'status': 'confirmed', 'by': 'evidence agent'}), tmp_path / 'cache')
    with pytest.raises(IntegrationError, match='cannot change origin'):
        integrate(lib, upsert(origin='author'), tmp_path / 'cache')


def test_rematch_rechecks_recorded_retrievals_offline(tmp_path):
    lib, _ = integrate(
        base_library(),
        [
            (
                'a.json',
                pack(tmp_path, 'doc', [claim('V-1'), claim('P-1', quotes=('14 days', 'high confidence'))]),
            )
        ],
        tmp_path / 'cache',
    )
    rows = {r['claim']: r for r in rematch(lib, tmp_path / 'cache')}
    assert (rows['V-1']['matched'], rows['V-1']['total'], rows['V-1']['problem']) == (1, 1, '')
    assert (rows['P-1']['matched'], rows['P-1']['total']) == (1, 2) and 'K-1' not in rows
    lib['claims'][1]['verification']['quote_match']['matched'] = 2
    assert (
        next(r for r in rematch(lib, tmp_path / 'cache') if r['claim'] == 'V-1')['problem'] == 'recorded 2/1'
    )
    assert all(r['matched'] is None and r['problem'] for r in rematch(lib, tmp_path / 'missing'))


def test_source_reproduction_requires_the_recorded_extraction_environment(monkeypatch):
    import sys

    import tools.evidence.fetch as fetch_module
    from tools.evidence.integrate import extraction_environment_problems

    python = f'{sys.version_info.major}.{sys.version_info.minor}'

    def source(extractor):
        return {'custom': {'verification': {'retrieval': {'text': {'extractor': extractor}}}}}

    library = {'sources': [source('gs-9.99 txtwrite-pages'), source(f'html.parser-py{python} blocks-v1'), {}]}
    monkeypatch.setattr(fetch_module, 'gs_version', lambda gs: '9.99')
    assert extraction_environment_problems(library) == []
    monkeypatch.setattr(fetch_module, 'gs_version', lambda gs: '10.0')
    assert extraction_environment_problems(library) == [
        'records name Ghostscript 9.99 for PDF extraction; found 10.0'
    ]
    library['sources'].append(source('html.parser-py2.7 blocks-v1'))
    assert any('Python 2.7' in problem for problem in extraction_environment_problems(library))
