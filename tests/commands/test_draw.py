"""`napkin draw`, and `napkin compile` and `napkin draw` stopping on a problem of the stylesheet.

The picture's own rules are tested in tests/draw/; these tests check what the commands do with them:
the file that each writes, its name, the notes, a run, and the diagnostics of a stylesheet, each
with its file and its key, with no file drawn.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.commands.call import napkin, package

SVG = '{http://www.w3.org/2000/svg}'

# Two things: a district whose people a flow serves, and a shop that a trigger closes at 3 h. The
# shop opens again only in the run `staffed`, whose option staffs it.
WARDS = """\
scenario "Wards"
    horizon 10 h

record fixture: assumption "The values and events of a test."

north:
    "A district."
    input x: h = 2 h in [1 h, 5 h]  @fixture
        "X"
    people: people = 10 people in [0,]  @fixture
        "People"
    served: people = 0 people in [0,]  @fixture
        "People served"
    flow serve: this.people -> this.served
        request = 1 people/h

shop:
    "A shop."
    input staffed: bool = false  @fixture
    open: bool = true  @fixture
    close = event():  @fixture
        when t >= 3 h:
            this.close.start()
        after 0 h:
            this.open = false
    reopen = event():  @fixture
        when this.staffed and t >= 5 h:
            this.reopen.start()
        after 0 h:
            this.open = true

options "Staff":
    "Staffed":
        "The shop has staff."
        shop.staffed = true  @staff

runs:
    staffed = "Staffed"

record staff: assumption "The staff of a test."
"""


def things(path):
    """The cards of an SVG that `napkin draw` wrote, by their `data-thing`; the file must parse."""
    root = ET.parse(path).getroot()
    assert root.tag == f'{SVG}svg' and root.get('role') == 'img'
    return {g.get('data-thing') for g in root.iter(f'{SVG}g') if g.get('data-thing')}


def test_draw_writes_the_svg_to_the_file_that_the_package_names(tmp_path, monkeypatch, capsys):
    """A package's picture is `<package>.svg`, a run's `<package>.<run>.svg`, a variant's
    `<package>.<variant>.svg`, each in the current folder."""
    folder = package(tmp_path / 'wards', WARDS)
    variant = folder / 'variants' / 'east' / 'model.scn'
    variant.parent.mkdir(parents=True)
    variant.write_text('variant "East"\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    found = napkin(capsys, 'draw', 'wards')
    assert found.code == 0, found.err
    assert things(tmp_path / 'wards.svg') == {'north', 'shop'}
    assert found.out == 'wards.svg: 2 things, 0 arrows\n'
    assert napkin(capsys, 'draw', 'wards', '--run', 'staffed').out.startswith('wards.staffed.svg: ')
    assert things(tmp_path / 'wards.staffed.svg') == {'north', 'shop'}
    assert napkin(capsys, 'draw', 'wards/variants/east').code == 0
    assert things(tmp_path / 'wards.east.svg') == {'north', 'shop'}


def shown_events(path):
    """The events that the cards of an SVG name, by their `data-event` (names separated by spaces)."""
    root = ET.parse(path).getroot()
    return {name for g in root.iter(f'{SVG}g') for name in (g.get('data-event') or '').split()}


def test_a_model_with_one_run_is_drawn_as_that_run(tmp_path, monkeypatch, capsys):
    """Under the default run the shop has no staff, so reachability proves that `reopen` cannot
    start (D16), and the picture leaves it out. A model whose one named run staffs the shop is drawn
    as that run, which shows it. The stylesheet makes the shop's card name its events."""
    names = '[triggers]\nnames = ["shop"]\n'
    one = package(tmp_path / 'wards', WARDS)
    alone = package(tmp_path / 'alone', WARDS.split('options')[0] + 'record staff: assumption "S."\n')
    for folder in (one, alone):
        (folder / 'style.toml').write_text(names, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    assert napkin(capsys, 'draw', 'wards').code == 0
    assert shown_events(tmp_path / 'wards.svg') == {'shop.close', 'shop.reopen'}
    assert napkin(capsys, 'draw', 'alone').code == 0
    assert shown_events(tmp_path / 'alone.svg') == {'shop.close'}


def test_a_run_that_the_model_does_not_have_is_a_usage_error(tmp_path, monkeypatch, capsys):
    package(tmp_path / 'wards', WARDS)
    monkeypatch.chdir(tmp_path)
    found = napkin(capsys, 'draw', 'wards', '--run', 'staffd')
    assert found.code == 2
    assert 'usage: napkin draw' in found.err and 'did you mean staffed?' in found.err
    assert not list(tmp_path.glob('*.svg'))


def test_draw_writes_the_file_that_o_names_and_fails_on_one_it_cannot_write(tmp_path, capsys):
    folder = package(tmp_path / 'wards', WARDS)
    output = tmp_path / 'pictures' / 'map.svg'
    output.parent.mkdir()
    found = napkin(capsys, 'draw', folder, '-o', output)
    assert found.code == 0 and things(output) and found.out.startswith(f'{output}: ')
    missing = tmp_path / 'no-such-folder' / 'map.svg'
    found = napkin(capsys, 'draw', folder, '-o', missing)
    assert found.code == 1 and str(missing) in found.err and not missing.exists()


def test_draw_says_when_the_picture_is_taller_than_a_pdf_page(tmp_path, monkeypatch, capsys):
    from napkin.draw import layout as layouts

    folder = package(tmp_path / 'wards', WARDS)
    output = tmp_path / 'map.svg'
    assert napkin(capsys, 'draw', folder, '-o', output).code == 0
    height = float(re.search(r'height="([0-9.]+)"', output.read_text(encoding='utf-8')).group(1))
    monkeypatch.setattr(layouts, 'PAGE_HEIGHT', height - 0.5)
    lines = napkin(capsys, 'draw', folder, '-o', output).out.splitlines()
    (note,) = [line for line in lines if 'PDF page' in line]
    assert note.startswith(f'note: {output} is {height:,.0f} px tall')
    assert lines[-1].startswith(f'{output}: ')
    monkeypatch.setattr(layouts, 'PAGE_HEIGHT', height)
    assert 'PDF page' not in napkin(capsys, 'draw', folder, '-o', output).out


def test_draw_writes_the_latex_of_the_panels_to_the_file_that_latex_names(tmp_path, capsys):
    """A panel of the district's equations: the fragment holds one `align*` for each block of the
    picture's panels; without [equations] it holds comments only, and a note says so."""
    from napkin.draw import model_map
    from napkin.model.compile import load_scenario

    folder = package(tmp_path / 'wards', WARDS)
    (folder / 'style.toml').write_text('[equations]\nthings = ["north"]\n', encoding='utf-8')
    latex = tmp_path / 'wards.tex'
    found = napkin(capsys, 'draw', folder, '-o', tmp_path / 'wards.svg', '--latex', latex)
    assert found.code == 0, found.err
    assert found.out.splitlines()[-1].startswith(f'{latex}: ')
    panels = model_map.picture(load_scenario(folder / 'model.scn'), run='staffed')['panels']
    blocks = [block for block in panels['equations'] if block['lines']]
    text = latex.read_text(encoding='utf-8')
    assert blocks and text.count(r'\begin{align*}') == len(blocks)
    (folder / 'style.toml').write_text('', encoding='utf-8')
    found = napkin(capsys, 'draw', folder, '-o', tmp_path / 'wards.svg', '--latex', tmp_path / 'none.tex')
    assert f'note: {tmp_path / "none.tex"}: the stylesheet names no thing' in found.out
    assert all(
        row.startswith('%') for row in (tmp_path / 'none.tex').read_text(encoding='utf-8').splitlines()
    )


def test_draw_gives_the_problem_of_a_stylesheet_that_it_cannot_read(tmp_path, monkeypatch, capsys):
    folder = package(tmp_path / 'wards', WARDS)
    monkeypatch.chdir(tmp_path)
    found = napkin(capsys, 'draw', folder, '--style', tmp_path / 'missing.toml')
    assert found.code == 1 and 'missing.toml: error: there is no such file [style]' in found.err
    (folder / 'style.toml').write_text('[nonsense]\nkey = 1\n', encoding='utf-8')
    found = napkin(capsys, 'draw', 'wards')
    assert found.code == 1 and f'{Path("wards", "style.toml")}: error: ' in found.err
    assert not list(tmp_path.glob('*.svg'))


# The four checks of a stylesheet that stop `napkin compile` and `napkin draw` (they were tests of
# tests/draw/test_style.py and test_trigger_levels.py): each sheet, the key that its problem names,
# the words of the problem, and a sheet that holds.
SHEETS = [
    # The district has the stocks `people` and `served`, and no `flood`.
    ('[stocks]\nnorth = ["flood"]\n', 'stocks.north', 'flood', '[stocks]\nnorth = ["served"]\n'),
    # A column holds 2 to 16 cards.
    ('[layout]\ncards_per_column = 1\n', 'layout.cards_per_column', '', '[layout]\ncards_per_column = 2\n'),
    # One symbol for two values of the district.
    (
        '[symbol.north]\nx = "W_s"\npeople = "W_s"\n',
        'symbol.north.people',
        'W_s',
        '[symbol.north]\nx = "W_s"\npeople = "P_s"\n',
    ),
    # A thing shows its events at one level.
    (
        '[triggers]\nrules = ["shop"]\ncount = ["shop"]\n',
        'triggers.count',
        'names shop, which triggers.rules also names',
        '[triggers]\nrules = ["shop"]\n',
    ),
]


@pytest.mark.parametrize('sheet, key, words, fixed', SHEETS)
def test_compile_and_draw_stop_on_a_problem_of_the_stylesheet(
    tmp_path, monkeypatch, capsys, sheet, key, words, fixed
):
    """Both commands read the package's stylesheet, give the one problem with the file as the command
    names it and the key, and exit 1; draw writes no file. Once the sheet holds, both exit 0."""
    folder = package(tmp_path / 'wards', WARDS)
    (folder / 'style.toml').write_text(sheet, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    for command in ('compile', 'draw'):
        found = napkin(capsys, command, 'wards')
        assert found.code == 1, command
        (line,) = found.err.splitlines()
        assert line.startswith(f'{Path("wards", "style.toml")}: error: {key}: '), line
        assert words in line and line.endswith('[style]')
    assert not list(tmp_path.glob('*.svg'))
    doc = napkin(capsys, 'compile', 'wards', '--json').doc
    (problem,) = doc['diagnostics']
    assert (problem['code'], problem['file']) == ('style', str(Path('wards', 'style.toml')))
    (folder / 'style.toml').write_text(fixed, encoding='utf-8')
    assert napkin(capsys, 'compile', 'wards').code == 0
    assert napkin(capsys, 'draw', 'wards').code == 0
    assert things(tmp_path / 'wards.svg') == {'north', 'shop'}
