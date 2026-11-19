"""The command lines of the evidence tools: each mode refuses the options of the other modes and leaves
every file as it was, and the reports of pack integration and of the source check follow from their
inputs by the documented rules.

The inputs are those of the evidence tool tests (`tests/evidence/support.py`): a synthetic catalogue
scenario under tmp_path, a pack of claims on a cached synthetic document, and no network.
"""

import hashlib
import json
from pathlib import Path

import pytest

from tests.evidence.support import QUEUE, claim, pack, write_package
from tools.evidence import fetch, integrate


def files(root):
    """{path: bytes} of every file below `root`."""
    return {path: path.read_bytes() for path in sorted(Path(root).rglob('*')) if path.is_file()}


def refusal(capsys):
    """The error line of a parser error, which names what the command refused."""
    return capsys.readouterr().err.strip().splitlines()[-1]


# fetch: a retrieval, or the extraction of cached bytes (--extract).


@pytest.fixture
def cached_html(tmp_path):
    """Latin-1 HTML bytes in a content-addressed cache, not yet extracted."""
    content = '<html><body><p>Caf\u00e9 cr\u00e8me</p></body></html>'.encode('latin-1')
    sha = hashlib.sha256(content).hexdigest()
    path = tmp_path / 'cache' / 'sha256' / sha[:2] / f'{sha}.html'
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    return path


# Each option of a retrieval, by the name that a refusal gives it.
RETRIEVAL = {
    'URL': ['https://example.org/a'],
    '--url': ['--url', 'https://example.org/a'],
    '--from-file': ['--from-file', 'page.html'],
    '--tool': ['--tool', 'manual'],
    '--final-url': ['--final-url', 'https://example.org/b'],
    '--http-status': ['--http-status', '200'],
    '--archive-timestamp': ['--archive-timestamp', '20240101000000'],
    '--cache': ['--cache', 'elsewhere'],
    '--out': ['--out', 'record.json'],
}


@pytest.mark.parametrize('name', RETRIEVAL)
def test_extraction_refuses_every_option_of_a_retrieval(tmp_path, cached_html, capsys, name):
    before = files(tmp_path)
    with pytest.raises(SystemExit) as refused:
        fetch.main(['--extract', str(cached_html), *RETRIEVAL[name]])
    assert refused.value.code == 2 and name in refusal(capsys)
    assert files(tmp_path) == before


def test_extraction_reads_the_media_type_of_the_bytes_and_keeps_its_text_unless_forced(cached_html, capsys):
    assert fetch.main(['--extract', str(cached_html), '--media-type', 'text/html; charset=ISO-8859-1']) == 0
    printed = json.loads(capsys.readouterr().out)
    text = Path(printed['cache_path'])
    assert text.parent == cached_html.parent and text.name == f'{cached_html.stem}.extracted.txt'
    assert 'Caf\u00e9 cr\u00e8me' in text.read_text(encoding='utf-8')
    assert printed['sha256'] == hashlib.sha256(text.read_bytes()).hexdigest()
    sidecar = json.loads(text.with_suffix('.json').read_text(encoding='utf-8'))
    assert sidecar == {'extractor': printed['extractor'], 'sha256': printed['sha256']}
    # Without the media type the bytes decode as UTF-8, which loses the accents; the text that is
    # already there stays until --force.
    assert fetch.main(['--extract', str(cached_html)]) == 0
    assert json.loads(capsys.readouterr().out) == printed
    assert fetch.main(['--extract', str(cached_html), '--force']) == 0
    forced = json.loads(capsys.readouterr().out)
    assert forced['sha256'] != printed['sha256'] and 'Caf\u00e9' not in text.read_text(encoding='utf-8')


def test_a_retrieval_refuses_force_and_reads_the_media_type_of_the_bytes(tmp_path, monkeypatch, capsys):
    page = tmp_path / 'page.txt'
    page.write_bytes(b'plain text, 114 days')
    monkeypatch.setattr(fetch, 'curl', lambda *args, **kwargs: pytest.fail('a refused retrieval ran'))
    cache = tmp_path / 'cache'
    local = ['--from-file', str(page), '--url', 'https://example.org/a', '--cache', str(cache)]
    for args in (['https://example.org/a'], local):
        with pytest.raises(SystemExit) as refused:
            fetch.main([*args, '--force'])
        assert refused.value.code == 2 and '--force' in refusal(capsys)
    assert not cache.exists()
    assert fetch.main([*local, '--media-type', 'text/csv']) == 0
    record = json.loads(capsys.readouterr().out)
    assert record['media_type'] == 'text/csv' and record['cache_path'].endswith('.csv')
    assert Path(record['cache_path']).read_bytes() == page.read_bytes()


# integrate: pack integration (the default), the source check (--check) and the coverage report
# (--coverage).


@pytest.fixture
def catalogue(tmp_path):
    """A catalogue of one scenario, SC99, and a pack for it: V-1 quotes the cached document, and P-1
    quotes it once in two quotes ('14 days', where the document says 114 days)."""
    write_package(tmp_path, {'model.scn': QUEUE})
    (tmp_path / 'packs').mkdir()
    claims = [claim('V-1'), claim('P-1', quotes=('14 days', 'high confidence'))]
    (tmp_path / 'packs' / 'doc.json').write_text(json.dumps(pack(tmp_path, 'doc', claims)))
    return tmp_path


def pack_args(root):
    return [
        *('--root', str(root), '--packs', str(root / 'packs'), '--cache', str(root / 'cache')),
        *('--report', str(root / 'report.json')),
    ]


def check_args(root, cache='cache'):
    return [
        '--check',
        '--root',
        str(root),
        '--cache',
        str(root / cache),
        '--report',
        str(root / 'check.json'),
    ]


REFUSED = [
    *(('pack', option) for option in (['--jobs', '2'], ['--complete'], ['--require-cache'])),
    *(('check', option) for option in (['--packs', 'packs'], ['--reextract'], ['--write'], ['--prune'])),
    *(
        ('coverage', option)
        for option in (
            ['--root', '.'],
            ['--cache', 'cache'],
            ['--scenario', 'SC99'],
            ['--report', 'report.json'],
            ['--jobs', '2'],
            ['--complete'],
            ['--require-cache'],
            ['--packs', 'packs'],
            ['--reextract'],
            ['--write'],
            ['--prune'],
        )
    ),
]


@pytest.mark.parametrize('mode, option', REFUSED, ids=[f'{mode}{option[0]}' for mode, option in REFUSED])
def test_each_mode_of_integrate_refuses_the_options_of_the_other_modes(
    catalogue, monkeypatch, capsys, mode, option
):
    # Given alone, the pack and check command lines write their reports (the tests below), and the
    # coverage mode prints its report.
    monkeypatch.setattr(integrate, 'coverage_report', lambda root: pytest.fail('a refused mode ran'))
    command = {'pack': pack_args(catalogue), 'check': check_args(catalogue), 'coverage': ['--coverage']}
    before = files(catalogue)
    with pytest.raises(SystemExit) as refused:
        integrate.main([*command[mode], *option])
    assert refused.value.code == 2 and option[0] in refusal(capsys)
    assert files(catalogue) == before


def test_the_check_and_the_coverage_report_are_separate_modes(monkeypatch, capsys):
    monkeypatch.setattr(integrate, 'coverage_report', lambda root: pytest.fail('a refused mode ran'))
    with pytest.raises(SystemExit) as refused:
        integrate.main(['--check', '--coverage'])
    error = refusal(capsys)
    assert refused.value.code == 2 and '--check' in error and '--coverage' in error


def test_pack_integration_takes_one_scenario(catalogue, capsys):
    before = files(catalogue)
    with pytest.raises(SystemExit) as refused:
        integrate.main([*pack_args(catalogue), '--scenario', 'SC99', '--scenario', 'SC98'])
    assert refused.value.code == 2 and '--scenario' in refusal(capsys)
    assert files(catalogue) == before
    # One --scenario names the folder that every pack must target.
    assert integrate.main([*pack_args(catalogue), '--scenario', 'SC98']) == 1
    assert files(catalogue) == before
    assert integrate.main([*pack_args(catalogue), '--scenario', 'SC99']) == 0


def test_pack_integration_reports_each_claim_by_rule(catalogue, capsys):
    assert integrate.main([*pack_args(catalogue), '--write']) == 0
    report = json.loads((catalogue / 'report.json').read_text(encoding='utf-8'))
    assert report == {
        'packs': [str(catalogue / 'packs' / 'doc.json')],
        'new_sources': ['doc'],
        'new_claims': ['V-1', 'P-1'],
        'upgrades': [],
        'downgrades': [],
        'mismatches': [],
        'retrieval_problems': [],
        'claims': {
            'V-1': {
                'status': 'verified',
                'method': 'primary_full_text',
                'reasons': [],
                'quote_match': [1, 1],
            },
            'P-1': {
                'status': 'partial',
                'method': 'primary_full_text',
                'reasons': ['1/2 quotes re-matched'],
                'quote_match': [1, 2],
            },
        },
        'scenario': 'SC99',
        # The model cites none of the new records.
        'orphans': {'sources': ['doc'], 'claims': ['P-1', 'V-1'], 'assumptions': []},
        'changed': True,
        'written': True,
    }
    written = json.loads((catalogue / 'scenarios/SC99/evidence/claims.json').read_text(encoding='utf-8'))
    assert {c['id']: c['verification']['status'] for c in written} == {'V-1': 'verified', 'P-1': 'partial'}
    # The packs again change nothing, and a dry run writes the report only.
    before = files(catalogue / 'scenarios')
    assert integrate.main(pack_args(catalogue)) == 0
    again = json.loads((catalogue / 'report.json').read_text(encoding='utf-8'))
    assert (again['new_claims'], again['changed'], again['written']) == ([], False, False)
    assert files(catalogue / 'scenarios') == before


def test_the_source_check_reports_each_claim_and_counts_failures_by_mode(catalogue, capsys):
    assert integrate.main([*pack_args(catalogue), '--write']) == 0
    capsys.readouterr()
    assert integrate.main(check_args(catalogue)) == 0
    out, err = capsys.readouterr()
    result = json.loads((catalogue / 'check.json').read_text(encoding='utf-8'))
    nothing = {
        'sources': 0,
        'sources_with_retrieval': 0,
        'sources_without_retrieval': [],
        'claims': 0,
        'claims_checked': 0,
        'claims_without_retrieval': [],
        'claims_missing_bytes': 0,
        'claims_with_problems': 0,
        'sources_checked': 0,
        'sources_missing_bytes': 0,
        'sources_with_problems': 0,
        'failures': 0,
    }
    rows = [
        {'claim': 'V-1', 'status': 'verified', 'matched': 1, 'total': 1, 'problem': '', 'missing': False},
        {'claim': 'P-1', 'status': 'partial', 'matched': 1, 'total': 2, 'problem': '', 'missing': False},
    ]
    assert result == {
        'mode': 'recorded_retrievals',
        'failures': 0,
        'scenarios': {
            # The synthetic shared vocabulary holds no source.
            'shared': {'coverage': nothing, 'sources': {}, 'claims': []},
            'SC99': {
                'coverage': {
                    **nothing,
                    'sources': 1,
                    'sources_with_retrieval': 1,
                    'claims': 2,
                    'claims_checked': 2,
                    'sources_checked': 1,
                },
                'sources': {'doc': {'ok': True, 'missing': False, 'problems': []}},
                'claims': rows,
            },
        },
    }
    assert out.splitlines() == ['SC99:V-1 1/1 verified', 'SC99:P-1 1/2 partial']
    assert json.loads(err) == {'failures': 0, 'scenarios': 1}

    # Bytes that are not in the cache leave every claim unchecked; they fail only when the cache is
    # required, or in complete mode.
    def check(*options, cache='cache'):
        code = integrate.main([*check_args(catalogue, cache), *options])
        capsys.readouterr()
        return code, json.loads((catalogue / 'check.json').read_text(encoding='utf-8'))

    code, missing = check(cache='empty')
    claims = missing['scenarios']['SC99']['claims']
    assert code == 0 and missing['failures'] == 0
    assert all(row['missing'] and row['problem'] and row['matched'] is None for row in claims)
    code, required = check('--require-cache', cache='empty')
    assert code == 1 and required['failures'] == 2 and required['mode'] == 'recorded_retrievals'

    # Complete mode also fails each source and claim that has no retrieval record.
    folder = catalogue / 'scenarios/SC99/evidence'
    sources = json.loads((folder / 'sources.json').read_text(encoding='utf-8'))
    bare = {**sources[0], 'id': 'bare', 'custom': {'verification': {'status': 'unverified'}}}
    (folder / 'sources.json').write_text(json.dumps([*sources, bare]), encoding='utf-8')
    claims = json.loads((folder / 'claims.json').read_text(encoding='utf-8'))
    (folder / 'claims.json').write_text(json.dumps([*claims, {**claims[0], 'id': 'B-1', 'source': 'bare'}]))
    code, recorded = check()
    assert code == 0 and recorded['failures'] == 0
    code, complete = check('--complete')
    coverage = complete['scenarios']['SC99']['coverage']
    assert coverage['sources_without_retrieval'] == ['bare']
    assert coverage['claims_without_retrieval'] == ['B-1']
    assert code == 1 and complete['mode'] == 'complete' and complete['failures'] == 2
    # In complete mode, each claim whose bytes are not in the cache fails too.
    code, uncached = check('--complete', cache='empty')
    assert code == 1 and uncached['failures'] == 2 + 2


def test_the_defaults_of_the_packs_and_the_report_by_mode(catalogue, capsys):
    # Pack integration reads its packs from the work folder and writes its report there; the check
    # writes a report only when it is given one.
    (catalogue / '.work').mkdir()
    (catalogue / 'packs').rename(catalogue / '.work' / 'packs')
    assert integrate.main(['--root', str(catalogue), '--cache', str(catalogue / 'cache')]) == 0
    report = json.loads((catalogue / '.work/reports/integrate.json').read_text(encoding='utf-8'))
    assert report['packs'] == [str(catalogue / '.work/packs/doc.json')]
    assert report['new_claims'] == ['V-1', 'P-1']
    before = files(catalogue)
    assert integrate.main(['--check', '--root', str(catalogue), '--cache', str(catalogue / 'cache')]) == 0
    assert files(catalogue) == before


def test_the_source_check_refuses_another_extraction_environment(catalogue, capsys):
    assert integrate.main([*pack_args(catalogue), '--write']) == 0
    capsys.readouterr()
    path = catalogue / 'scenarios/SC99/evidence/sources.json'
    sources = json.loads(path.read_text(encoding='utf-8'))
    sources[0]['custom']['verification']['retrieval']['text']['extractor'] = 'html.parser-py2.7 blocks-v1'
    path.write_text(json.dumps(sources), encoding='utf-8')
    assert integrate.main(check_args(catalogue)) == 1
    out, err = capsys.readouterr()
    assert 'Python 2.7' in out and err == ''
    assert not (catalogue / 'check.json').exists()


def test_the_coverage_mode_prints_the_report_of_the_checkout(catalogue, monkeypatch, capsys):
    monkeypatch.setattr(integrate, 'ROOT', catalogue)
    assert integrate.main(['--coverage']) == 0
    printed = capsys.readouterr().out
    assert printed == integrate.coverage_report(catalogue) + '\n'
    assert printed.splitlines()[1].startswith('  SC99:')
