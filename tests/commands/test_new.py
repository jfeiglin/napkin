"""`napkin new`: a starter package in the new language that compiles and runs as written, its variants,
and the names, titles and folders that it refuses before it writes any file.

The starter's run follows a closed form: the flow moves `rate` people a day from 1000 waiting
people to the served, so served(t) = min(1000, rate t).
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from napkin import paths
from napkin.model.compile import load_scenario
from napkin.model.language.format import format_text
from tests.commands.call import napkin

PRELUDE = Path(__file__).resolve().parents[2] / 'napkin' / 'std' / 'units.json'


def written(folder):
    """{path in the folder: text} of every file in `folder`."""
    return {
        path.relative_to(folder).as_posix(): path.read_text(encoding='utf-8')
        for path in sorted(folder.rglob('*'))
        if path.is_file()
    }


def test_new_writes_a_starter_that_compiles_with_the_prelude_and_one_record(tmp_path, capsys):
    """One formatted file; the prelude's units only; one entity with an input, two stores and the
    flow between them, and a value of the top level that follows the people served (no `output`:
    the caller chooses what to report, D10); one assumption record that every value cites."""
    folder = tmp_path / 'demo'
    found = napkin(capsys, 'new', folder)
    assert found.code == 0, found.err
    files = written(folder)
    assert list(files) == [paths.ENTRY]
    assert format_text(files[paths.ENTRY]) == files[paths.ENTRY]
    declared = load_scenario(folder / paths.ENTRY).declared
    assert set(declared.units.base) == set(json.loads(PRELUDE.read_text(encoding='utf-8')))
    (service,) = declared.entities
    assert [part.path for part in service.parts] == [
        'service.rate',
        'service.waiting',
        'service.served',
        'service.serve',
    ]
    assert [part.path for part in declared.root] == ['people_served']
    assert [(record.name, record.kind) for record in declared.records] == [('guess', 'assumption')]
    for part in (*service.parts, *declared.root):
        assert [item.name for item in part.evidence] == ['guess'], part.path
    # What to replace next: the title, the input and the record.
    assert '"A new scenario"' in found.out and 'service.rate' in found.out and 'guess' in found.out


@pytest.mark.parametrize(
    'rate, day, served',
    [(10, 30, 300), (0, 30, 0), (50, 15, 750), (50, 20, 1000), (50, 30, 1000), (100, 30, 1000)],
)
def test_the_starters_flow_moves_its_rate_until_the_stock_runs_out(tmp_path, capsys, rate, day, served):
    folder = tmp_path / 'demo'
    assert napkin(capsys, 'new', folder).code == 0
    edits = tmp_path / 'edits.json'
    edits.write_text(json.dumps({'set': {'service.rate': rate}}), encoding='utf-8')
    found = napkin(capsys, 'run', folder, '--edits', edits, '--json', '--at', f'{day}days')
    assert found.code == 0, found.err
    values = found.doc['values']
    assert values['people_served']['values'] == pytest.approx([served], abs=1e-9)
    assert values['service.waiting']['values'] == pytest.approx([1000 - served], abs=1e-9)
    assert values['people_served']['label'] == 'People served'


def test_new_with_variants_writes_variants_that_change_one_input(tmp_path, capsys):
    """The k-th variant (from 1) sets the rate to (k + 1) x 10 people a day, and nothing else: its
    declared model has the main file's parts, and only the rate's value differs."""
    folder = tmp_path / 'demo'
    found = napkin(capsys, 'new', '--variants', 'east,west', folder)
    assert found.code == 0, found.err
    files = written(folder)
    assert set(files) == {
        paths.ENTRY,
        *(f'{paths.VARIANTS}/{name}/{paths.ENTRY}' for name in ('east', 'west')),
    }
    assert all(format_text(text) == text for text in files.values())
    main = load_scenario(folder / paths.ENTRY)
    for k, name in enumerate(('east', 'west'), start=1):
        variant = load_scenario(folder / paths.VARIANTS / name / paths.ENTRY)
        assert variant.declared.scenario.title == f'A new scenario: {name}'
        assert [part.path for part in variant.declared.entities[0].parts] == [
            part.path for part in main.declared.entities[0].parts
        ]
        rate = napkin(capsys, 'run', folder / paths.VARIANTS / name, '--json', '--value', 'service.rate')
        assert rate.doc['values']['service.rate']['values'] == [(k + 1) * 10] * 2
    assert napkin(capsys, 'run', folder, '--json', '--value', 'service.rate').doc['values']['service.rate'][
        'values'
    ] == [10, 10]


def test_the_commands_that_new_prints_run_the_model_and_its_variants(tmp_path, capsys):
    folder = tmp_path / 'demo'
    found = napkin(capsys, 'new', '--variants', 'east', folder)
    (line,) = [line for line in found.out.splitlines() if 'napkin run ' in line]
    commands = line.partition(': ')[2].split('; ')
    assert len(commands) == 2
    for command in commands:
        argv = shlex.split(command)
        assert argv[0] == 'napkin'
        ran = napkin(capsys, *argv[1:])
        assert ran.code == 0, ran.err
        assert 'people_served' in ran.out


def test_new_refuses_a_model_that_is_there_and_writes_nothing(tmp_path, capsys):
    folder = tmp_path / 'demo'
    assert napkin(capsys, 'new', folder).code == 0
    before = written(folder)
    for flags in ([], ['--variants', 'east'], ['--title', 'Another']):
        assert napkin(capsys, 'new', *flags, folder).code == 2
        assert written(folder) == before
    # A variant's file that is there is refused too, and the main file is not written.
    other = tmp_path / 'other'
    (other / paths.VARIANTS / 'east').mkdir(parents=True)
    (other / paths.VARIANTS / 'east' / paths.ENTRY).write_text('# mine\n', encoding='utf-8')
    assert napkin(capsys, 'new', '--variants', 'west,east', other).code == 2
    assert written(other) == {f'{paths.VARIANTS}/east/{paths.ENTRY}': '# mine\n'}
    (tmp_path / 'file').write_text('', encoding='utf-8')
    found = napkin(capsys, 'new', tmp_path / 'file')
    assert found.code == 2 and 'usage: napkin new' in found.err


@pytest.mark.parametrize(
    'flags',
    [
        ['--variants', 'East'],
        ['--variants', '9east'],
        ['--variants', '_east'],
        ['--variants', 'east-side'],
        ['--variants', 'éast'],
        ['--variants', ''],
        ['--variants', 'east,'],
        ['--variants', 'east,,west'],
        ['--variants', 'east,east'],
        ['--variants', 'east/west'],
        ['--title', 'A "quoted" title'],
        ['--title', ' \t '],
    ],
)
def test_new_refuses_a_bad_variant_name_or_title_and_writes_nothing(tmp_path, capsys, flags):
    folder = tmp_path / 'demo'
    found = napkin(capsys, 'new', *flags, folder)
    assert found.code == 2 and 'usage: napkin new' in found.err
    assert not folder.exists()


@pytest.mark.parametrize('title', ['A shop', 'Water in “the” valley, {east} # 2', ' Two\tlines\nof  text '])
def test_the_title_of_the_starter_is_the_title_given(tmp_path, capsys, title):
    folder = tmp_path / 'demo'
    assert napkin(capsys, 'new', '--title', title, folder).code == 0
    assert load_scenario(folder / paths.ENTRY).declared.scenario.title == ' '.join(title.split())


def test_a_starter_with_a_wrong_line_fails_with_its_file_line_and_column(tmp_path, capsys):
    """A line at the top level that starts no declaration, after the starter's last line."""
    folder = tmp_path / 'demo'
    assert napkin(capsys, 'new', folder).code == 0
    path = folder / paths.ENTRY
    text = path.read_text(encoding='utf-8')
    path.write_text(text + 'not a declaration\n', encoding='utf-8')
    found = napkin(capsys, 'run', folder)
    assert found.code == 1
    assert f'{path}:{len(text.splitlines()) + 1}:' in found.err
