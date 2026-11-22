"""A package publishes the evidence behind the actual readings at each reported time."""

import pytest

from napkin.model import load_scenario
from tools.publish import readings
from tools.publish.__main__ import main

SOURCE = """\
scenario "Gauge readings"
    horizon 2 h

input first = 2 @early
input second = 5 @late
level = formula(first if t < 1 h else second) @selection

options "Gauge":
    "Local":
        second = 7 @local
    "Reference":
        second = 5 @late

runs:
    standard = "Reference"
    nearby = "Local"

notes:
    not_estimated:
        forecast:
            reason: "The field gauge measures only the present."

record early: assumption "The initial gauge reading."
record late: assumption "The later reference gauge reading."
record local: assumption "The local gauge reading."
record selection: identity "The accepted gauge reading at the specified time."
"""


def package(folder, source=SOURCE):
    path = folder / 'model.scn'
    path.write_text(source)
    (folder / 'brief.toml').write_text('show = ["level", "forecast"]\nfeatured = ["nearby"]\n')
    return path


def test_readings_follow_featured_order_and_credit_the_exercised_branch(tmp_path):
    text = readings.render(load_scenario(package(tmp_path)))
    assert text.index('## nearby') < text.index('## standard')
    nearby = text.split('## nearby')[1].split('## standard')[0]
    first, last = [line for line in nearby.splitlines() if line.startswith('| level |')]
    assert (
        first.startswith('| level | 0 | 2 |')
        and 'early' in first
        and 'late' not in first
        and 'local' not in first
    )
    assert last.startswith('| level | 2 | 7 |') and 'local' in last and 'early' not in last
    assert 'Not estimated (The field gauge measures only the present.)' in text
    assert '## Evidence' in text and 'The local gauge reading.' in text


def test_explicit_model_publication_detects_drift_without_touching_historical_pages(tmp_path, capsys):
    entry = package(tmp_path)
    results = tmp_path / 'results'
    results.mkdir()
    (results / 'brief.md').write_bytes(b'historical bytes\n')
    assert main(['--write', '--model', str(entry), '--jobs', '1']) == 0
    assert main(['--check', '--model', str(tmp_path), '--jobs', '1']) == 0
    target = tmp_path / readings.OUTPUT
    assert target.read_text() == readings.render(load_scenario(entry))
    target.write_text('altered\n')
    assert main(['--check', '--model', str(entry), '--jobs', '1']) == 1
    assert 'differs' in capsys.readouterr().err and target.read_text() == 'altered\n'
    assert (results / 'brief.md').read_bytes() == b'historical bytes\n'


def test_failed_run_or_unsupported_input_cannot_replace_the_previous_summary(tmp_path):
    entry = package(tmp_path)
    target, _ = readings.publish(entry, check=False)
    saved = target.read_bytes()
    entry.write_text(SOURCE + '\nassert t < 2 h @selection\n')
    with pytest.raises(ValueError, match='2 h'):
        readings.publish(entry, check=False)
    entry.write_text(SOURCE.replace('input first = 2 @early', 'input first = 2'))
    with pytest.raises(ValueError, match='no_record'):
        readings.publish(entry, check=False)
    assert target.read_bytes() == saved


def test_family_entry_checks_each_variants_own_readings_before_writing(tmp_path):
    package(tmp_path)
    folders = [tmp_path / 'variants' / name for name in ('east', 'west')]
    for folder in folders:
        folder.mkdir(parents=True)
        (folder / 'model.scn').write_text(f'variant "{folder.name}"\n')
    assert main(['--write', '--model', str(tmp_path)]) == 0
    assert not (tmp_path / readings.OUTPUT).exists()
    assert all((folder / readings.OUTPUT).is_file() for folder in folders)
    assert main(['--check', '--model', str(tmp_path / 'model.scn')]) == 0
    first = folders[0] / readings.OUTPUT
    first.write_text('previous version\n')
    assert main(['--check', '--model', str(tmp_path)]) == 1
    (folders[1] / 'model.scn').write_text('variant "west"\nassert t < 2 h @selection\n')
    assert main(['--write', '--model', str(tmp_path)]) == 1
    assert first.read_text() == 'previous version\n'


def test_scoped_and_whole_catalogue_own_only_current_artifacts(tmp_path, monkeypatch, capsys):
    import json

    from napkin import SCHEMA_VERSION
    from tools.evidence import manifest
    from tools.publish import __main__ as runner

    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    scenarios = tmp_path / 'scenarios'
    library = scenarios / 'library'
    library.mkdir(parents=True)
    vocabulary = {
        'schema_version': SCHEMA_VERSION,
        'id': 'vocabulary',
        'title': 'Vocabulary',
        'units': {},
        'sources': [],
        'claims': [],
        'assumptions': [],
    }
    (library / 'vocabulary.json').write_text(json.dumps(vocabulary))
    historical = [scenarios / 'README.md']
    for sid in ('SC97', 'SC98'):
        folder = scenarios / sid
        results = folder / 'results'
        results.mkdir(parents=True)
        package(folder)
        historical.extend(
            results / filename
            for filename in (
                'methods.md',
                'source-verification.json',
                'assumption-review.json',
                'runs.csv',
                'runs.json',
                'index.html',
            )
        )
    for path in historical:
        path.write_bytes(b'preserved historical publication\n')
    first = scenarios / 'SC97' / 'results'
    second = scenarios / 'SC98' / 'results'
    manifest_file = tmp_path / manifest.PATH
    scoped = ['--scenario', 'SC97', '--jobs', '1']
    assert main(['--write', *scoped]) == 0
    current = first / 'brief.md', first / 'readings.md', first / 'source-dossier.json'
    assert all(path.is_file() for path in current)
    assert not manifest_file.exists()
    assert not (second / 'readings.md').exists() and not (second / 'source-dossier.json').exists()
    for stale in current:
        saved = stale.read_bytes()
        stale.write_bytes(b'stale current data\n')
        assert main(['--check', *scoped]) == 1
        assert stale.name in capsys.readouterr().err
        stale.write_bytes(saved)
    assert main(['--check', *scoped]) == 0
    assert main(['--write', '--jobs', '1']) == 0
    assert manifest_file.exists() and (second / 'source-dossier.json').exists()
    assert main(['--check', '--jobs', '1']) == 0
    manifest_file.write_bytes(b'changed manifest')
    assert main(['--check', *scoped]) == 0
    assert main(['--check', '--jobs', '1']) == 1
    assert manifest.PATH in capsys.readouterr().err
    assert all(path.read_bytes() == b'preserved historical publication\n' for path in historical)


@pytest.mark.parametrize(
    'request_args',
    [
        ['--only', 'html'],
        ['--only', 'runs'],
        ['--only', 'methods'],
        ['--only', 'assumptions'],
        ['--committed-spreads'],
    ],
)
def test_historical_formats_explain_the_supported_current_publication(request_args, capsys):
    with pytest.raises(SystemExit) as exit_code:
        main(['--check', *request_args])
    assert exit_code.value.code == 2
    diagnostic = capsys.readouterr().err.lower()
    assert 'historical' in diagnostic and '8488047' in diagnostic
    assert 'readings' in diagnostic and 'dossier' in diagnostic


def test_explicit_spread_check_completes_the_authored_runs_and_rejects_a_failed_sample(tmp_path):
    from tools import publish

    entry = tmp_path / 'scenarios' / 'measured'
    entry.mkdir(parents=True)
    source = SOURCE.replace('input first = 2 @early', 'input first = uniform(1, 3).draw() @early')
    package(entry, source)
    with (entry / 'brief.toml').open('a') as out:
        out.write('\n[[spread]]\nid = "gauges"\nruns = ["nearby", "standard"]\nsamples = 3\nseed = 2\n')
    (entry / 'spreads').mkdir()
    (entry / 'spreads' / 'gauges.json').write_text('{"set":{}}')
    messages = []
    ctx = publish.Context(tmp_path, jobs=1, scenario_ids=['measured'], progress=messages.append)
    publish.sample_spreads(ctx)
    assert messages[-1] == 'verified 6 samples from current declared spreads'
    # The central and sampled checks must both run. Seed 2 includes a first reading above 2.1.
    (entry / 'model.scn').write_text(source + '\nassert first <= 2.1 @selection\n')
    with pytest.raises(ValueError, match=r'measured gauges nearby: sample \d+ .*stops'):
        publish.sample_spreads(publish.Context(tmp_path, jobs=1, scenario_ids=['measured']))


def test_selecting_a_catalogue_family_writes_each_variant_once(tmp_path, monkeypatch):
    from tools.publish import __main__ as runner

    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    root = tmp_path / 'scenarios' / 'gauges'
    root.mkdir(parents=True)
    package(root)
    variants = [root / 'variants' / name for name in ('east', 'west')]
    for entry in variants:
        entry.mkdir(parents=True)
        (entry / 'model.scn').write_text(f'variant "{entry.name}"\n')
    scope = ['--scenario', 'gauges', '--scenario', 'gauges:east', '--jobs', '1']
    assert main(['--write', *scope]) == 0
    assert not (root / 'results').exists()
    for folder in variants:
        assert sorted(f.name for f in (folder / 'results').iterdir()) == [
            'brief.md',
            'readings.md',
            'source-dossier.json',
        ]
    assert main(['--check', *scope]) == 0
