"""Selected file contracts retain the files of the selected package without reading unrelated edit
sets."""

import json

from scenarios.tests.test_scenario_files import source_contract_files
from tests import helpers


def write(root, name, text='not a compiled model'):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_source_selection_keeps_the_files_of_the_package_without_compilation(tmp_path):
    # The variant east of the package SC97 reads the package's main file, the module `common` and,
    # through it, the module `parts.clock` in a folder of the package; `unused` is in the package's folder.
    main = write(tmp_path, 'scenarios/SC97/model.scn', 'scenario "A"\nuse common\n')
    selected = write(tmp_path, 'scenarios/SC97/variants/east/model.scn', 'variant "East"\n')
    sheet = write(tmp_path, 'scenarios/SC97/variants/east/style.toml')
    brief = write(tmp_path, 'scenarios/SC97/variants/east/brief.toml')
    common = write(tmp_path, 'scenarios/SC97/common.scn', 'use parts.clock\n')
    clock = write(tmp_path, 'scenarios/SC97/parts/clock.scn')
    sibling = write(tmp_path, 'scenarios/SC97/unused.scn')
    # Another variant's files and the files of the package's tests are not the selected model's.
    write(tmp_path, 'scenarios/SC97/variants/west/model.scn', 'variant "West"\n')
    write(tmp_path, 'scenarios/SC97/variants/west/local.scn')
    write(tmp_path, 'scenarios/SC97/tests/fixture.scn')
    write(tmp_path, 'scenarios/SC98/model.scn')
    write(tmp_path, 'scenarios/SC98/style.toml')
    write(tmp_path, 'scenarios/SC98/brief.toml')
    write(tmp_path, 'scenarios/SC98/unrelated.scn')
    write(tmp_path, 'tests/acceptance/fixture.scn')

    scenarios, modules, fixtures, styles = source_contract_files(
        tmp_path, {'SC97:east'}, include_fixtures=False
    )
    assert scenarios == [selected]
    assert set(modules) == {main, common, clock, sibling}
    assert styles == sorted([sheet, brief])
    assert fixtures == []


def test_complete_source_selection_retains_unreferenced_modules_and_acceptance_files(tmp_path):
    model = write(tmp_path, 'scenarios/SC97/model.scn')
    orphan = write(tmp_path, 'scenarios/Shared/orphan.scn')
    orphan_style = write(tmp_path, 'scenarios/Shared/style.toml')
    orphan_brief = write(tmp_path, 'scenarios/Shared/brief.toml')
    fixture = write(tmp_path, 'tests/acceptance/fixture.scn')
    scenarios, modules, fixtures, styles = source_contract_files(tmp_path)
    assert scenarios == [model]
    assert modules == [orphan]
    assert fixtures == [fixture]
    assert styles == sorted([orphan_style, orphan_brief])


def test_selected_edit_discovery_does_not_read_unselected_documents(tmp_path, monkeypatch):
    write(tmp_path, 'scenarios/SC97/model.scn')
    write(tmp_path, 'scenarios/SC98/model.scn')
    write(
        tmp_path,
        'scenarios/SC97/edits/one.json',
        json.dumps({'scenario': 'SC97', 'set': {'service.capacity': 2}}),
    )
    write(tmp_path, 'scenarios/SC98/edits/broken.json', 'not JSON')
    monkeypatch.setattr(helpers, 'ROOT', tmp_path)
    monkeypatch.setattr(helpers, 'SCENARIO_IDS', ('SC97',))
    assert helpers.example_edit_sets() == {
        'scenarios/SC97/edits/one.json': ('SC97', {'set': {'service.capacity': 2}})
    }
