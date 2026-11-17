"""Packages and variants (docs/language.md, §2.12), on fake packages written in `tmp_path`.

A file's role is its first declaration: a package's main file, a variant or a module. A variant reads
its package's main file first and overlays its scenario line. A `use` line names a module of the
package, so a model never reads a file of another package. A model's library is the folder that its
main file's `library "PATH"` line names. Two packages with one name in two places are two models, and
a new variant changes no sibling's identity.
"""

from __future__ import annotations

import json

import pytest

from napkin.engine.runtime import simulate
from napkin.model import ModelError
from napkin.model.ir import thaw
from napkin.model.language import front
from napkin.model.language.modules import role_of
from napkin.model.library import load_library, prelude_units
from napkin.model.model import build_model
from tests.model.test_modules import CHANGE, POOL, TANKS, module, scenario, variant
from tests.owned import write_family
from tools import catalogue

# The main file of a package that holds only what its variants share: its scenario line and its use.
MAIN = scenario(body='')


def package(root, files):
    """{path below scenarios/: path} of the files written below `root/scenarios`, with the library."""
    return write_family(root, files)


def problems(path):
    with pytest.raises(ModelError) as raised:
        build_model(path)
    return raised.value.diagnostics


def final_water(model, run='a'):
    """The water that the pool holds at the end of a run."""
    trajectory = simulate(model.resolve(run), thaw(model.library), None)
    return trajectory.env_at(trajectory.horizon)['pool.water']


# ---- roles ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('text', 'role'),
    [
        ('scenario "A"\n', 'main'),
        ('# A comment comes first.\n\nvariant "A"\n', 'variant'),
        ('use other\n\nthing:\n    "A thing."\n', 'module'),
        ('record r: identity "A record."\n', 'module'),
        ('', 'module'),
    ],
)
def test_a_files_role_is_its_first_declaration(text, role):
    assert role_of(text) == role
    assert front.read(text, 'x.scn').role == role


def test_a_scenario_line_after_another_declaration_is_an_error():
    with pytest.raises(ModelError, match='first declaration'):
        front.read('record r: identity "A record."\n\nscenario "Late"\n', 'x.scn')


def test_a_module_is_no_model_and_a_main_file_is_no_module(tmp_path):
    paths = package(tmp_path, {'SC97/common.scn': module(), 'SC97/model.scn': scenario()})
    assert any('scenario line' in item['message'] for item in problems(paths['SC97/common.scn']))
    paths = package(tmp_path / 'other', {'SC97/model.scn': scenario(uses=('model',))})
    assert any('not a module' in item['message'] for item in problems(paths['SC97/model.scn']))


# ---- the variant overlay ----------------------------------------------------------------------------


def test_a_variant_reads_its_package_first_and_overlays_the_lines_that_it_writes(tmp_path):
    """A variant's model is its package's main file, the modules that it uses, then the variant: the
    same model as the main file with the variant's declarations written into it. Its scenario line is
    the main file's with each line that the variant writes in its place, and its title is the main
    file's title with the variant's."""
    head = 'variant "East"\n    summary "The east."\n    horizon 6 h\n    scope "The east."\n\n'
    paths = package(
        tmp_path,
        {
            'SC97/common.scn': module(),
            'SC97/model.scn': MAIN,
            'SC97/variants/east/model.scn': head + TANKS + '\n' + CHANGE.format(20),
            'SC98/common.scn': module(),
            'SC98/model.scn': scenario(body=TANKS + '\n' + CHANGE.format(20)),
        },
    )
    east, whole = build_model(paths['SC97/variants/east/model.scn']), build_model(paths['SC98/model.scn'])
    assert east.scenario.title == 'Tanks: East'
    assert (east.scenario.summary, east.scenario.scope) == ('The east.', 'The east.')
    assert east.time['horizon'] == 6 and whole.time['horizon'] == 12
    outcomes = next(iter(east.whole.values())).outcomes
    assert {item.scope for item in outcomes.values()} == {'The east.'}
    # The parts are the same model's: the same inputs and the same rules, in the same order.
    assert thaw(east.inputs) == thaw(whole.inputs)
    assert list(east.structures[()].rules) == list(whole.structures[()].rules)
    # A line that the variant does not write is the main file's.
    bare = package(
        tmp_path / 'bare',
        {
            'SC97/common.scn': module(),
            'SC97/model.scn': MAIN,
            'SC97/variants/east/model.scn': variant('East'),
        },
    )
    model = build_model(bare['SC97/variants/east/model.scn'])
    assert model.time['horizon'] == 12 and model.scenario.scope == 'Fixture'


def test_a_variant_names_no_library_and_lives_in_its_packages_variants(tmp_path):
    with pytest.raises(ModelError, match='library of its package'):
        front.read('variant "East"\n    library "../library"\n', 'model.scn')
    paths = package(tmp_path, {'SC97/common.scn': module(), 'SC97/east.scn': variant('East')})
    assert any('variants/<name>/model.scn' in item['message'] for item in problems(paths['SC97/east.scn']))


# ---- imports never leave the package ------------------------------------------------------------------


def test_a_use_names_a_module_of_its_own_package_only(tmp_path):
    """`use common` is the package's own `common.scn`: another package's module of the same name is not
    read, and a name with no module in the package is an error, whatever other packages hold."""
    paths = package(
        tmp_path,
        {
            'SC97/common.scn': module(water='30 people'),
            'SC97/model.scn': scenario(body=TANKS),
            'SC98/common.scn': module(water='60 people'),
            'SC98/model.scn': scenario(body=TANKS),
            'SC98/shared.scn': POOL.format(water='5 people'),
            'SC99/model.scn': scenario(uses=('common', 'shared'), body=TANKS),
        },
    )
    assert build_model(paths['SC97/model.scn']).inputs['pool.start_water']['value'] == 30
    assert build_model(paths['SC98/model.scn']).inputs['pool.start_water']['value'] == 60
    found = problems(paths['SC99/model.scn'])
    assert {item['message'] for item in found} >= {
        'use common: the package SC99 has no module common.scn',
        'use shared: the package SC99 has no module shared.scn',
    }
    # A name is a path from the package's folder: no part of it leaves the folder.
    with pytest.raises(ModelError):
        front.read('use ..common\n', 'x.scn')


# ---- one library, by its path --------------------------------------------------------------------


def test_a_model_reads_the_library_that_its_main_file_names(tmp_path):
    """The library is the folder that `library "PATH"` names, from the main file's folder; a variant
    reads its package's; a model whose files name none reads the prelude and its package's files only."""
    paths = package(
        tmp_path,
        {
            'SC97/common.scn': module(),
            'SC97/model.scn': MAIN,
            'SC97/variants/east/model.scn': variant('East'),
        },
    )
    vocabulary = json.loads((tmp_path / catalogue.LIBRARY / 'vocabulary.json').read_text())
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    marked = {**vocabulary, 'title': 'Another vocabulary'}
    (elsewhere / 'vocabulary.json').write_text(json.dumps(marked))
    main = paths['SC97/model.scn']
    east = paths['SC97/variants/east/model.scn']
    assert build_model(east).library['title'] == vocabulary['title']
    main.write_text(MAIN.replace('library "../library"', 'library "../../elsewhere"'), encoding='utf-8')
    assert build_model(east).library['title'] == 'Another vocabulary'
    main.write_text(MAIN.replace('    library "../library"\n', ''), encoding='utf-8')
    alone = load_library(east)
    assert alone['units'] == prelude_units()
    assert not any(alone[collection] for collection in ('sources', 'claims', 'assumptions'))
    with pytest.raises(ModelError, match='written twice'):
        front.read(MAIN.replace('library "../library"', 'library "a"\n    library "b"'), 'model.scn')


# ---- two packages of one name, and a new variant --------------------------------------------------


def test_two_packages_with_one_name_run_independently(tmp_path):
    """The package SC97 in two catalogues, with other start water, is two models: each builds and runs
    its own values, and running one changes nothing of the other."""
    models = {}
    for name, water in (('one', '30 people'), ('two', '60 people')):
        paths = package(
            tmp_path / name, {'SC97/common.scn': module(water=water), 'SC97/model.scn': scenario(body=TANKS)}
        )
        models[name] = build_model(paths['SC97/model.scn'])
    one, two = models['one'], models['two']
    assert one.model_hash != two.model_hash
    first = final_water(one)
    assert final_water(two) != first
    assert final_water(one) == first
    assert one.inputs['pool.start_water']['value'] == 30 and two.inputs['pool.start_water']['value'] == 60


def test_a_new_variant_leaves_the_identity_of_its_siblings(tmp_path):
    files = {
        'SC97/common.scn': module(),
        'SC97/model.scn': MAIN,
        'SC97/variants/east/model.scn': variant('East'),
    }
    paths = package(tmp_path, files)
    east = build_model(paths['SC97/variants/east/model.scn'])
    paths = package(tmp_path, {**files, 'SC97/variants/west/model.scn': variant('West', TANKS)})
    again = build_model(paths['SC97/variants/east/model.scn'])
    west = build_model(paths['SC97/variants/west/model.scn'])
    assert (again.model_hash, again.library_hash) == (east.model_hash, east.library_hash)
    assert west.model_hash != east.model_hash


def test_a_new_variant_with_records_in_its_packages_folder_leaves_its_siblings_identity(tmp_path):
    """A record that only the new variant reaches joins the package's folder: the hashes of a sibling
    cover the records that the sibling reaches, so they stay."""
    from tests.build import evidence_library, fixture_claim

    files = {
        'SC97/common.scn': module(),
        'SC97/model.scn': MAIN,
        'SC97/variants/east/model.scn': variant('East'),
    }
    paths = package(tmp_path, files)
    east = build_model(paths['SC97/variants/east/model.scn'])
    own = 'record west_count: source_transfer "Applied here."\n    claims:\n        C-WEST\n'
    west = variant('West', TANKS + '\n' + CHANGE.format(20).replace('@fixture', '@west_count') + '\n' + own)
    paths = package(tmp_path, {**files, 'SC97/variants/west/model.scn': west})
    evidence = paths['SC97/model.scn'].parent / 'evidence'
    (evidence / 'sources.json').write_text(json.dumps(evidence_library()['sources']))
    (evidence / 'claims.json').write_text(json.dumps([fixture_claim('C-WEST')]))
    reached = build_model(paths['SC97/variants/west/model.scn']).library['claims']
    assert [claim['id'] for claim in reached] == ['C-WEST']
    again = build_model(paths['SC97/variants/east/model.scn'])
    assert (again.model_hash, again.library_hash) == (east.model_hash, east.library_hash)


# ---- the prelude and the identity of a package ------------------------------------------------------

EAST = {'SC97/common.scn': module(), 'SC97/model.scn': MAIN, 'SC97/variants/east/model.scn': variant('East')}


def test_no_folder_of_a_package_redefines_a_unit_of_the_prelude(tmp_path):
    """The prelude's names are every model's: a package's or a variant's units file that writes one,
    even with the prelude's own definition, is an error at that unit."""
    paths = package(tmp_path, EAST)
    east = paths['SC97/variants/east/model.scn']
    for folder in (east.parent, paths['SC97/model.scn'].parent):
        (folder / 'units.json').write_text(json.dumps({'day': prelude_units()['day']}))
        found = problems(east)
        assert [(item['code'], item['path']) for item in found] == [('unit_collision', 'units/day')]
        assert 'prelude' in found[0]['message']
        (folder / 'units.json').write_text('{}')
    assert build_model(east)


def test_the_units_come_from_the_prelude_the_library_the_package_and_the_variant_in_that_order(tmp_path):
    paths = package(tmp_path, EAST)
    east = paths['SC97/variants/east/model.scn']
    vocabulary = json.loads((tmp_path / catalogue.LIBRARY / 'vocabulary.json').read_text())
    crates = {'crates': {'dimensions': {'crates': 1}, 'scale': 1}}
    (paths['SC97/model.scn'].parent / 'units.json').write_text(json.dumps(crates))
    (east.parent / 'units.json').write_text(json.dumps({'boxes': {'dimensions': {'boxes': 1}, 'scale': 1}}))
    assert list(load_library(east)['units']) == [*prelude_units(), *vocabulary['units'], 'crates', 'boxes']


def test_a_unit_that_the_prelude_adds_leaves_every_hash(tmp_path, monkeypatch):
    """The hashes cover the units that a model uses, so a later prelude's new unit changes none of them,
    while the model can read the new unit."""
    import napkin.model.library as library_module

    east = package(tmp_path, EAST)['SC97/variants/east/model.scn']
    before = build_model(east)
    grown = {**prelude_units(), 'fortnight': {'kind': 'time', 'dimensions': {'time': 1}, 'scale': 336}}
    monkeypatch.setattr(library_module, '_PRELUDE_UNITS', grown)
    after = build_model(east)
    assert 'fortnight' in after.library['units']
    assert (after.model_hash, after.library_hash) == (before.model_hash, before.library_hash)


def test_a_renamed_package_and_a_moved_library_keep_the_hashes(tmp_path):
    """The model hash covers no name and no path: the package SC97 renamed SC98, with its library moved
    out of `scenarios/` to the root of the checkout and its `library` line changed to the new folder, has
    the same hashes, its variant too."""
    import shutil

    paths = package(tmp_path, EAST)
    before = build_model(paths['SC97/variants/east/model.scn'])
    shutil.move(tmp_path / 'scenarios/SC97', tmp_path / 'scenarios/SC98')
    shutil.move(tmp_path / catalogue.LIBRARY, tmp_path / 'library')
    main = tmp_path / 'scenarios/SC98/model.scn'
    main.write_text(MAIN.replace('library "../library"', 'library "../../library"'), encoding='utf-8')
    after = build_model(tmp_path / 'scenarios/SC98/variants/east/model.scn')
    assert (after.model_hash, after.library_hash) == (before.model_hash, before.library_hash)


def test_a_lone_package_compiles_and_runs_with_only_the_prelude(tmp_path):
    """A package whose main file names no library, with no units file and no evidence file, builds: its
    units are the prelude's and their compositions (`people/h`), and its records are written in its
    files. It runs as the same package with a library does, bit for bit."""
    import shutil

    with_library = package(tmp_path / 'with', {'SC97/common.scn': module(), 'SC97/model.scn': scenario()})
    alone = package(tmp_path / 'alone', {'SC97/common.scn': module(), 'SC97/model.scn': scenario()})
    main = alone['SC97/model.scn']
    main.write_text(main.read_text().replace('    library "../library"\n', ''), encoding='utf-8')
    for path in [main.parent / 'units.json', *(main.parent / 'evidence').glob('*.json')]:
        path.unlink()
    shutil.rmtree(tmp_path / 'alone' / catalogue.LIBRARY)
    model = build_model(main)
    assert set(model.library['units']) == set(prelude_units())
    assert not any(model.library[collection] for collection in ('sources', 'claims', 'assumptions'))
    assert final_water(model) == final_water(build_model(with_library['SC97/model.scn']))
