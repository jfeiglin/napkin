"""Portable acquisition uses the recorded source bytes and full coverage counts.

The sources are synthetic: a pack integrates one cached document (`tests/evidence/support.py`), and a
project document and the catalogue live under tmp_path. Nothing reads the network or the real cache.
"""

import copy
import hashlib
import json

import pytest

from tests.evidence.support import QUEUE, base_library, claim, pack, write_package
from tools.evidence.integrate import integrate, retrieval_coverage
from tools.evidence.manifest import PATH, acquire, artifacts, main, restore


def integrated(tmp_path):
    """A library with the source `doc`, whose bytes are in tmp_path/cache, and its two claims."""
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
    return lib


def lost_copy(source):
    """A copy of a source, under another ID, whose recorded bytes no cache holds."""
    lost = copy.deepcopy(source)
    lost['id'] = 'lost'
    lost['custom']['verification']['retrieval']['sha256'] = '0' * 64
    return lost


def test_complete_coverage_counts_unrecorded_sources_claims_and_failed_reproduction():
    library = {
        'sources': [
            {'id': 's1', 'custom': {'verification': {'retrieval': {'sha256': 'x'}}}},
            {'id': 's2', 'custom': {'verification': {}}},
        ],
        'claims': [{'id': 'c1', 'source': 's1'}, {'id': 'c2', 'source': 's2'}],
    }
    rows = [{'claim': 'c1', 'missing': True, 'problem': 'Raw hash mismatch'}]
    result = retrieval_coverage(library, rows)
    assert result == {
        'sources': 2,
        'sources_with_retrieval': 1,
        'sources_without_retrieval': ['s2'],
        'claims': 2,
        'claims_checked': 1,
        'claims_without_retrieval': ['c2'],
        'claims_missing_bytes': 1,
        'claims_with_problems': 1,
        'sources_checked': 0,
        'sources_missing_bytes': 0,
        'sources_with_problems': 0,
    }


def test_complete_source_reproduction_covers_an_unclaimed_source(tmp_path):
    from tools.evidence.integrate import rematch

    source = next(s for s in integrated(tmp_path)['sources'] if s['id'] == 'doc')
    scope = {'sources': [source], 'claims': []}
    # A cache without the source's bytes: the source is still checked, with no claim to read it.
    rows = rematch(scope, tmp_path / 'empty')
    result = retrieval_coverage(scope, rows)
    assert rows == []
    assert result['sources_checked'] == 1
    assert result['sources_missing_bytes'] == 1
    assert result['sources_with_problems'] == 1
    assert rows.source_checks[source['id']]['missing']


def test_project_acquisition_restores_then_reuses_exact_cache_bytes(tmp_path):
    raw = b'A document of the project.\n'
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/project.md').write_bytes(raw)
    retrieval = {
        'sha256': hashlib.sha256(raw).hexdigest(),
        'bytes': len(raw),
        'media_type': 'text/markdown',
        'final_url': 'https://example.org/project.md',
    }
    item = {'id': 'project', 'project_document': 'docs/project.md', 'retrieval': retrieval}
    first = acquire(item, tmp_path / 'cache', tmp_path)
    assert first.read_bytes() == raw
    # The second acquisition reads the cache: it needs the document no longer.
    (tmp_path / 'docs/project.md').unlink()
    second = acquire(item, tmp_path / 'cache', tmp_path)
    assert first == second
    assert hashlib.sha256(second.read_bytes()).hexdigest() == retrieval['sha256']
    with pytest.raises(ValueError, match='expected sha256'):
        restore(item, raw + b'changed', tmp_path / 'cache')


def test_bulk_acquisition_reports_a_source_without_a_retrieval_record(tmp_path, capsys, monkeypatch):
    document = {
        'manifest_version': '2.0',
        'shared': {'sources': []},
        'scenarios': [{'scenario': 'SC99', 'sources': [{'id': 'unrecorded', 'retrieval': None}]}],
    }
    monkeypatch.setattr(
        'tools.evidence.manifest.artifacts',
        lambda root: {PATH: json.dumps(document)},
    )
    assert main(['--root', str(tmp_path), '--cache', str(tmp_path / 'cache'), '--acquire-all']) == 1
    err = capsys.readouterr().err
    assert [item['source'] for item in json.loads(err[err.index('{') :])['acquisitions_required']] == [
        'unrecorded'
    ]


def test_parallel_reproduction_retains_order_and_unclaimed_failure(tmp_path):
    from tools.evidence.integrate import rematch

    library = integrated(tmp_path)
    good = next(s for s in library['sources'] if s['id'] == 'doc')
    # The source whose bytes are missing comes first, so the threads finish out of order.
    subset = {
        'sources': [lost_copy(good), good],
        'claims': [c for c in library['claims'] if c['source'] == good['id']],
    }
    serial = rematch(subset, tmp_path / 'cache')
    parallel = rematch(subset, tmp_path / 'cache', jobs=4)
    assert parallel == serial
    assert parallel.source_checks == serial.source_checks
    assert list(parallel.source_checks) == [s['id'] for s in subset['sources']]
    assert retrieval_coverage(subset, parallel)['sources_with_problems'] == 1
    assert parallel.source_checks['lost']['missing']
    assert not parallel.source_checks['doc']['missing']


def test_selected_evidence_commands_do_not_load_an_invalid_sibling(tmp_path, capsys):
    from tools.evidence.integrate import main as integrate_main

    write_package(tmp_path, {'model.scn': QUEUE})
    other = tmp_path / 'scenarios/SC98'
    other.mkdir()
    (other / 'model.scn').write_text('not a valid model: [')
    assert main(['--root', str(tmp_path), '--scenario', 'SC99']) == 0
    assert json.loads(capsys.readouterr().out)['scenario'] == 'SC99'
    assert integrate_main(['--check', '--root', str(tmp_path), '--scenario', 'SC99']) == 0


def test_scenario_manifest_import_commands_keep_the_owner(tmp_path):
    # SC99 owns the source `doc` with its retrieval, which a pack wrote; the shared vocabulary has none.
    from tools.evidence.integrate import main as integrate_main

    write_package(tmp_path, {'model.scn': QUEUE})
    (tmp_path / 'packs').mkdir()
    (tmp_path / 'packs' / 'doc.json').write_text(json.dumps(pack(tmp_path, 'doc', [claim('V-1')])))
    options = [
        '--root',
        str(tmp_path),
        '--packs',
        str(tmp_path / 'packs'),
        '--cache',
        str(tmp_path / 'cache'),
    ]
    assert integrate_main([*options, '--report', str(tmp_path / 'report.json'), '--write']) == 0
    document = json.loads(artifacts(tmp_path)[PATH])
    (row,) = document['scenarios']
    (source,) = row['sources']
    assert (row['scenario'], source['id'], source['claims']) == ('SC99', 'doc', ['V-1'])
    assert source['import_command'] == (
        'python -m tools.evidence.manifest --scenario SC99 --import doc=/path/to/raw-document'
    )
    assert document['shared']['sources'] == [] and document['library_source_count'] == 1


def test_inline_evidence_needs_no_owned_files_in_a_manifest_or_dossier(tmp_path):
    from tests.evidence.support import SERVICE, evidence_library
    from tools.publish import Context, build

    library = evidence_library()
    library['sources'][0]['custom']['verification']['url'] = 'https://example.test/source'
    write_package(tmp_path, {'model.scn': SERVICE}, library)
    inline = tmp_path / 'scenarios' / 'observations'
    inline.mkdir()
    (inline / 'model.scn').write_text(
        'scenario "Observations"\n    horizon 1 h\ninput rate = 3 @r\nrecord r: assumption "Local estimate."\n'
    )
    result = json.loads(artifacts(tmp_path)[PATH])
    rows = {row['scenario']: row for row in result['scenarios']}
    assert rows['observations']['sources'] == []
    assert result['library_source_count'] == rows['SC99']['library_source_count'] == 1

    dossiers = build(Context(tmp_path), only=['dossier'])
    local = json.loads(dossiers['scenarios/observations/results/source-dossier.json'])
    assert local['sources'] == [] and local['summary']['claims'] == 0
    sourced = json.loads(dossiers['scenarios/SC99/results/source-dossier.json'])
    assert {claim['id'] for claim in sourced['sources'][0]['claims']} == {'C-ACCESS', 'C-ACTION'}
    assert all(claim['reachable_from_scenarios'] == ['SC99'] for claim in sourced['sources'][0]['claims'])


def test_missing_or_partial_owned_evidence_cannot_hide_a_source_reference(tmp_path):
    from napkin.model.ir import ModelError
    from tests.evidence.support import SERVICE, evidence_library

    write_package(tmp_path, {'model.scn': SERVICE}, evidence_library())
    folder = tmp_path / 'scenarios' / 'SC99' / 'evidence'
    (folder / 'sources.json').unlink()
    with pytest.raises(FileNotFoundError, match=r'sources\.json'):
        artifacts(tmp_path)
    (folder / 'sources.json').write_text('{bad JSON')
    with pytest.raises(ValueError):
        artifacts(tmp_path)
    folder.rename(tmp_path / 'archived-evidence')
    with pytest.raises(ModelError, match=r'Unknown (claim|assumption)'):
        artifacts(tmp_path)
