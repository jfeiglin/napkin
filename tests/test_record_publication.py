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
