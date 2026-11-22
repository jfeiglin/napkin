"""Committed summaries compare byte for byte, and a file a fresh render no longer produces is drift."""

import pytest

from tests.evidence.support import QUEUE, write_package
from tools import catalogue, publish
from tools.publish import __main__ as cli

READINGS = '# SC97 — Blackout\n\nA dash — and a degree sign: 40 °C.\n'


def rendered():
    """A fresh render: a readings page and a source dossier."""
    return {
        'scenarios/SC97/results/readings.md': READINGS,
        'scenarios/SC97/results/source-dossier.json': '{"scenario":"SC97"}\n',
    }


def checkout(root, files):
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))


def test_written_summaries_are_exact_utf8_with_their_own_line_endings(tmp_path):
    publish.write(rendered(), tmp_path)
    assert (tmp_path / 'scenarios/SC97/results/readings.md').read_bytes() == READINGS.encode('utf-8')
    assert publish.drift(rendered(), tmp_path) == []


@pytest.mark.parametrize(
    'content',
    [
        READINGS.replace('\n', '\r\n').encode('utf-8'),  # the same text with CRLF line endings
        READINGS.encode('cp1252'),  # the same text in a legacy encoding
        READINGS.encode('utf-8') + b'\n',  # one extra line
    ],
)
def test_any_byte_difference_is_drift(tmp_path, content):
    checkout(tmp_path, rendered())
    checkout(tmp_path, {'scenarios/SC97/results/readings.md': content})
    assert publish.drift(rendered(), tmp_path) == ['scenarios/SC97/results/readings.md']


def test_a_missing_summary_is_drift(tmp_path):
    checkout(tmp_path, rendered())
    (tmp_path / 'scenarios/SC97/results/source-dossier.json').unlink()
    assert publish.drift(rendered(), tmp_path) == ['scenarios/SC97/results/source-dossier.json']


def orphaned(root):
    """A checkout with the fresh render plus summaries no builder writes any more, and hand-written files."""
    checkout(root, rendered())
    checkout(
        root,
        {
            # Summaries of removed cases.
            'scenarios/SC99/results/readings.md': '# SC99 — removed\n',
            'scenarios/SC98/results/source-dossier.json': '{"scenario":"SC98"}\n',
            # Hand-written files beside or outside the builders' locations are never theirs.
            'scenarios/SC97/evidence/independent-calculation.md': '# Independent calculation\n',
            'scenarios/docs/evidence/SC99-control-chains/source-dossier.json': '# Control chains\n',
            'scenarios/reading-guide.md': '# Reading guide\n',
        },
    )


def test_files_a_fresh_render_no_longer_produces_are_drift(tmp_path):
    orphaned(tmp_path)
    assert publish.drift(rendered(), tmp_path) == [
        'scenarios/SC98/results/source-dossier.json',
        'scenarios/SC99/results/readings.md',
    ]


def test_only_the_locations_of_the_builders_that_rendered_are_checked(tmp_path):
    orphaned(tmp_path)
    outputs = {path: content for path, content in rendered().items() if path.endswith('/readings.md')}
    assert publish.drift(outputs, tmp_path, ['readings']) == ['scenarios/SC99/results/readings.md']


def test_prune_deletes_the_orphans_and_nothing_else(tmp_path):
    orphaned(tmp_path)
    removed = publish.prune(rendered(), tmp_path)
    assert removed == ['scenarios/SC98/results/source-dossier.json', 'scenarios/SC99/results/readings.md']
    remaining = sorted(
        path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob('*') if path.is_file()
    )
    assert remaining == [
        'scenarios/SC97/evidence/independent-calculation.md',
        'scenarios/SC97/results/readings.md',
        'scenarios/SC97/results/source-dossier.json',
        'scenarios/docs/evidence/SC99-control-chains/source-dossier.json',
        'scenarios/reading-guide.md',
    ]
    # The removed case's emptied directory goes too.
    assert not (tmp_path / 'scenarios/SC98/results').exists()
    assert publish.drift(rendered(), tmp_path) == []


def test_publish_write_deletes_orphans_and_check_reports_them(tmp_path, monkeypatch, capsys):
    orphaned(tmp_path)
    checkout(tmp_path, {'scenarios/SC97/results/readings.md': READINGS.replace('\n', '\r\n')})
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(cli, 'build', lambda ctx, only: rendered())
    assert cli.main(['--check']) == 1
    reported = capsys.readouterr().err
    for path in ('scenarios/SC97/results/readings.md', 'scenarios/SC99/results/readings.md'):
        assert path in reported
    assert 'tools.publish --write' in reported
    # Each differing summary shows its first changed lines.
    assert '-# SC99 — removed' in reported
    assert 'scenarios/SC97/results/readings.md: only the line endings or the encoding differ' in reported
    assert cli.main(['--write']) == 0
    assert not (tmp_path / 'scenarios/SC99/results/readings.md').exists()
    assert (tmp_path / 'scenarios/SC97/results/readings.md').read_bytes() == READINGS.encode('utf-8')
    assert cli.main(['--check']) == 0


def test_a_differing_summary_shows_its_first_changed_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    # A legacy encoding cannot stop the report.
    checkout(tmp_path, {'scenarios/SC97/results/readings.md': READINGS.encode('cp1252')})
    assert '+A dash — and a degree sign: 40 °C.' in cli.changes(
        'scenarios/SC97/results/readings.md', READINGS
    )
    # A long difference is cut short.
    shown = cli.changes('scenarios/SC97/results/readings.md', ''.join(f'{n}\n' for n in range(100)))
    assert len(shown) == cli.SHOWN + 1
    assert shown[-1].endswith('more lines')


@pytest.mark.parametrize(
    'path,inside',
    [
        ('scenarios/SC97/results/readings.md', True),
        ('scenarios/SC97/results/source-dossier.json', True),
        # A wildcard stays within one directory and a class matches one character, so none of these
        # could be found again by the orphan check.
        ('docs/scenarios/archive/SC97.md', False),
        ('docs/scenarios/SCX1.md', False),
        ('docs/evidence/SC97/extra/source-dossier.json', False),
        ('docs/SC97.md', False),
    ],
)
def test_a_builder_cannot_write_a_summary_outside_its_committed_locations(monkeypatch, path, inside):
    locations = (
        'scenarios/SC[0-9][0-9]/results/readings.md',
        'scenarios/SC[0-9][0-9]/results/source-dossier.json',
    )
    monkeypatch.setattr(publish, 'builders', lambda: {'readings': (lambda ctx: {path: 'text'}, locations)})
    context = type('Context', (), {'progress': staticmethod(lambda message: None)})()
    if inside:
        assert publish.build(context) == {path: 'text'}
    else:
        with pytest.raises(ValueError, match='outside its committed locations'):
            publish.build(context)


def test_the_evidence_builders_write_only_within_their_declared_locations(tmp_path):
    for sid in ('SC97', 'SC98'):
        write_package(tmp_path, {'model.scn': QUEUE}, owner=sid)
    only = ['dossier', 'manifest']
    outputs = publish.build(publish.Context(tmp_path), only=only)
    assert set(outputs) == {
        'scenarios/docs/evidence/source-manifest.json',
        catalogue.result('SC97', 'source-dossier.json'),
        catalogue.result('SC98', 'source-dossier.json'),
    }
    assert publish.orphans(outputs, tmp_path, names=only) == []
