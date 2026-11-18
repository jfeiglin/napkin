"""`napkin fmt`: the formatter of the new front end, from the command line."""

from __future__ import annotations

from pathlib import Path

from tests.commands.call import napkin

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / 'examples' / 'piano_tuners' / 'model.scn'


def badly_formatted():
    """The example with its spacing changed in two lines: the same tree, another layout."""
    text = EXAMPLE.read_text(encoding='utf-8')
    changed = text.replace(
        'input staff = 3 tuner in [1 tuner, 10 tuner]', 'input staff=3 tuner  in [1 tuner,10 tuner]'
    ).replace('formula(this.rate * this.staff)', 'formula( this.rate*this.staff )')
    assert changed != text
    return changed


def test_fmt_check_passes_on_the_example(capsys):
    found = napkin(capsys, 'fmt', '--check', EXAMPLE.parent)
    assert found.code == 0, found.err
    assert found.out == ''
    assert found.err == '1 file checked, all formatted\n'


def test_fmt_check_fails_on_a_badly_formatted_copy_and_changes_nothing(tmp_path, capsys):
    copy = tmp_path / 'model.scn'
    copy.write_text(badly_formatted(), encoding='utf-8')
    found = napkin(capsys, 'fmt', '--check', copy)
    assert found.code == 1
    assert found.out == f'{copy}\n'
    assert found.err == '1 of 1 file would change\n'
    assert copy.read_text(encoding='utf-8') == badly_formatted()


def test_fmt_writes_the_layout_of_the_language(tmp_path, capsys):
    copy = tmp_path / 'model.scn'
    copy.write_text(badly_formatted(), encoding='utf-8')
    found = napkin(capsys, 'fmt', tmp_path)
    assert found.code == 0, found.err
    assert copy.read_text(encoding='utf-8') == EXAMPLE.read_text(encoding='utf-8')
    assert napkin(capsys, 'fmt', '--check', copy).code == 0


def test_a_file_that_does_not_parse_is_a_diagnostic_with_its_place(tmp_path, capsys):
    broken = tmp_path / 'model.scn'
    broken.write_text('scenario "Tank"\n    horizon 4 h\n\ntank:\n   water: L = 8\n', encoding='utf-8')
    found = napkin(capsys, 'fmt', '--check', broken)
    assert found.code == 1
    # Three spaces where a level of nesting is four: the line 5, after its three spaces.
    assert f'{broken}:5:4: error: each level of nesting is four spaces [indent]' in found.err.splitlines()


def test_a_file_that_is_no_scn_file_is_a_usage_error(tmp_path, capsys):
    other = tmp_path / 'notes.txt'
    other.write_text('notes', encoding='utf-8')
    assert napkin(capsys, 'fmt', other).code == 2
    assert napkin(capsys, 'fmt', tmp_path / 'nowhere.scn').code == 2
