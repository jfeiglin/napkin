"""Committed summaries compare byte for byte, and a file a fresh render no longer produces is drift."""

import math

import pytest

from napkin.engine import edits_for, evaluate_study
from tests.build import compiled, scenario
from tools import publish
from tools.publish import __main__ as cli
from tools.publish import runs

BRIEF = '# SC97 — Blackout\n\nA dash — and a degree sign: 40 °C.\n'


def rendered():
    """A fresh render: two briefs and one methods record."""
    return {
        'scenarios/SC97/results/brief.md': BRIEF,
        'scenarios/README.md': '# Scenario briefs\n',
        'scenarios/SC97/results/methods.md': '# SC97 methods\n',
    }


def checkout(root, files):
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))


def test_written_summaries_are_exact_utf8_with_their_own_line_endings(tmp_path):
    publish.write(rendered(), tmp_path)
    assert (tmp_path / 'scenarios/SC97/results/brief.md').read_bytes() == BRIEF.encode('utf-8')
    assert publish.drift(rendered(), tmp_path) == []


@pytest.mark.parametrize(
    'content',
    [
        BRIEF.replace('\n', '\r\n').encode('utf-8'),  # the same text with CRLF line endings
        BRIEF.encode('cp1252'),  # the same text in a legacy encoding
        BRIEF.encode('utf-8') + b'\n',  # one extra line
    ],
)
def test_any_byte_difference_is_drift(tmp_path, content):
    checkout(tmp_path, rendered())
    checkout(tmp_path, {'scenarios/SC97/results/brief.md': content})
    assert publish.drift(rendered(), tmp_path) == ['scenarios/SC97/results/brief.md']


def test_a_missing_summary_is_drift(tmp_path):
    checkout(tmp_path, rendered())
    (tmp_path / 'scenarios/SC97/results/methods.md').unlink()
    assert publish.drift(rendered(), tmp_path) == ['scenarios/SC97/results/methods.md']


def orphaned(root):
    """A checkout with the fresh render plus summaries no builder writes any more, and hand-written files."""
    checkout(root, rendered())
    checkout(
        root,
        {
            # A removed case's brief and methods record.
            'scenarios/SC99/results/brief.md': '# SC99 — removed\n',
            'scenarios/SC98/results/methods.md': '# SC98 methods\n',
            # Hand-written files beside or outside the builders' locations are never theirs.
            'scenarios/SC97/evidence/independent-calculation.md': '# Independent calculation\n',
            'scenarios/docs/evidence/SC99-control-chains/methods.md': '# Control chains\n',
            'scenarios/reading-guide.md': '# Reading guide\n',
        },
    )


def test_files_a_fresh_render_no_longer_produces_are_drift(tmp_path):
    orphaned(tmp_path)
    assert publish.drift(rendered(), tmp_path) == [
        'scenarios/SC98/results/methods.md',
        'scenarios/SC99/results/brief.md',
    ]


def test_only_the_locations_of_the_builders_that_rendered_are_checked(tmp_path):
    orphaned(tmp_path)
    outputs = {
        path: content
        for path, content in rendered().items()
        if path == 'scenarios/README.md' or path.endswith('/brief.md')
    }
    assert publish.drift(outputs, tmp_path, ['briefs']) == ['scenarios/SC99/results/brief.md']


def test_prune_deletes_the_orphans_and_nothing_else(tmp_path):
    orphaned(tmp_path)
    removed = publish.prune(rendered(), tmp_path)
    assert removed == ['scenarios/SC98/results/methods.md', 'scenarios/SC99/results/brief.md']
    remaining = sorted(
        path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob('*') if path.is_file()
    )
    assert remaining == [
        'scenarios/README.md',
        'scenarios/SC97/evidence/independent-calculation.md',
        'scenarios/SC97/results/brief.md',
        'scenarios/SC97/results/methods.md',
        'scenarios/docs/evidence/SC99-control-chains/methods.md',
        'scenarios/reading-guide.md',
    ]
    # The removed case's emptied directory goes too.
    assert not (tmp_path / 'scenarios/SC98/results').exists()
    assert publish.drift(rendered(), tmp_path) == []


def test_publish_write_deletes_orphans_and_check_reports_them(tmp_path, monkeypatch, capsys):
    orphaned(tmp_path)
    checkout(tmp_path, {'scenarios/SC97/results/brief.md': BRIEF.replace('\n', '\r\n')})
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(cli, 'build', lambda ctx, only: rendered())
    assert cli.main(['--check']) == 1
    reported = capsys.readouterr().err
    for path in ('scenarios/SC97/results/brief.md', 'scenarios/SC99/results/brief.md'):
        assert path in reported
    assert 'tools.publish --write' in reported
    # Each differing summary shows its first changed lines.
    assert '-# SC99 — removed' in reported
    assert 'scenarios/SC97/results/brief.md: only the line endings or the encoding differ' in reported
    assert cli.main(['--write']) == 0
    assert not (tmp_path / 'scenarios/SC99/results/brief.md').exists()
    assert (tmp_path / 'scenarios/SC97/results/brief.md').read_bytes() == BRIEF.encode('utf-8')
    assert cli.main(['--check']) == 0


def test_a_differing_summary_shows_its_first_changed_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    # A legacy encoding cannot stop the report.
    checkout(tmp_path, {'scenarios/SC97/results/brief.md': BRIEF.encode('cp1252')})
    assert '+A dash — and a degree sign: 40 °C.' in cli.changes('scenarios/SC97/results/brief.md', BRIEF)
    # A long difference is cut short.
    shown = cli.changes('scenarios/SC97/results/brief.md', ''.join(f'{n}\n' for n in range(100)))
    assert len(shown) == cli.SHOWN + 1
    assert shown[-1].endswith('more lines')


@pytest.mark.parametrize(
    'values',
    [
        # One final value from the AVX-512 and the AVX2 kernels.
        (250.5507685346087, 250.5507685346086),
        # A value on a tie at six figures, and one unit in the last place either side.
        (math.nextafter(1.234565, 0), 1.234565, math.nextafter(1.234565, math.inf)),
        # Numerical residuals of a completed repair, which differ in sign and size.
        (5.795364188543317e-14, -4.29101199017623e-14, 0.0),
    ],
)
def test_a_run_table_value_is_the_same_on_every_computer(values):
    assert len({runs.final_value(value) for value in values}) == 1


def test_an_unestimated_run_table_value_stays_unestimated():
    assert runs.final_value(None) is None


def test_a_run_table_row_lists_only_the_edits_that_reach_its_run():
    """An edit of another run or of an option that the run does not name changes nothing in the run,
    and the run's row does not list it. A listed value is the one that the run takes, from the
    narrowest edit, in the order that the edits write the inputs. Every other input keeps the run's
    own value, and a study of the run alone gives the same row."""
    model = compiled(scenario())
    assert 'Half rate' in model.runs['b']['options'] and 'Half rate' not in model.runs['a']['options']
    edits = {
        'set': {'service.n': 30},
        'options': {'Half rate': {'service.end': 6}},
        'runs': {'a': {'service.rate': 30}, 'b': {'service.n': 40, 'service.end': 8}},
    }
    expected = {'a': {'service.n': 30, 'service.rate': 30}, 'b': {'service.n': 40, 'service.end': 8}}
    study = evaluate_study(model, edits_for(model, edits))
    assert study.admissible, study.diagnostics
    for run, changed in expected.items():
        row = runs.row(study, run, run, 'Edited', edits)
        listed = {name: item['value'] for name, item in row['changed'].items()}
        assert list(listed.items()) == list(changed.items())
        own = model.run_values(run)
        assert {key: value for key, value in row['inputs'].items() if value != own[key]} == changed
        assert runs.sweep_row(model, run, run, 'Edited', edits)['changed'] == row['changed']


@pytest.mark.parametrize(
    'path,inside',
    [
        ('scenarios/SC97/results/brief.md', True),
        ('scenarios/SC97/results/methods.md', True),
        # A wildcard stays within one directory and a class matches one character, so none of these
        # could be found again by the orphan check.
        ('docs/scenarios/archive/SC97.md', False),
        ('docs/scenarios/SCX1.md', False),
        ('docs/evidence/SC97/extra/methods.md', False),
        ('docs/SC97.md', False),
    ],
)
def test_a_builder_cannot_write_a_summary_outside_its_committed_locations(monkeypatch, path, inside):
    locations = ('scenarios/SC[0-9][0-9]/results/brief.md', 'scenarios/SC[0-9][0-9]/results/methods.md')
    monkeypatch.setattr(publish, 'builders', lambda: {'briefs': (lambda ctx: {path: 'text'}, locations)})
    context = type('Context', (), {'progress': staticmethod(lambda message: None)})()
    if inside:
        assert publish.build(context) == {path: 'text'}
    else:
        with pytest.raises(ValueError, match='outside its committed locations'):
            publish.build(context)


def test_the_evidence_builders_write_only_within_their_declared_locations():
    only = ['dossier', 'manifest', 'assumptions']
    outputs = publish.build(publish.Context(), only=only)
    # The evidence builders write for the whole catalogue, whatever scenarios the session checks.
    from tests.helpers import ALL_SCENARIO_IDS
    from tools import catalogue

    # The manifest covers the catalogue; each scenario has its own dossier and inventory, and no dossier or
    # inventory covers the catalogue as a whole.
    expected = {
        'scenarios/docs/evidence/source-manifest.json',
        *(
            catalogue.result(sid, f'{name}.json')
            for sid in ALL_SCENARIO_IDS
            for name in ('source-verification', 'assumption-review')
        ),
    }
    assert set(outputs) == expected

    assert publish.orphans(outputs, names=only) == []
