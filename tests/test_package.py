"""A package's models (`napkin.package.load_package`): the main file of a package with no variants,
else each variant, each compiled as `load_scenario` compiles its entry file, and the problems of
every model that fails in one error.

The packages are written in `tmp_path` with generic names. Each expectation is what `load_scenario`
gives on the same file, or a rate that a variant writes, which a run reads back: a desk that serves
at `rate` serves rate x t people.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.model.compile import load_scenario
from napkin.model.language.problems import LanguageError
from napkin.package import entries, load_package, name_of

MAIN = """\
scenario "A desk"
    horizon 10 h

desk:
    input rate: people/h = 2 people/h in [0 people/h, 10 people/h]
        "Rate"
    served: people = 0 people in [0,]
        "People served"
    flow serve: SOURCE -> this.served
        request = formula(this.rate)

record fixture: identity "A value of a test."
"""


def variant(title, rate):
    """A variant that gives the desk its own rate, which cites its record (a number that a change sets
    does)."""
    return f'variant "{title}"\n\nchange desk:\n    rate = {rate} people/h  @fixture\n'


def write(folder, files):
    """The files {path in the folder: text} of a package in `folder`; its entry file."""
    for relative, text in files.items():
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return folder / 'model.scn'


def served_at(model, t):
    """The people that a model's desk has served at `t` hours, in its default run."""
    record = run(model.program, model.configuration)
    (found,) = read(record, model.program, ['desk.served'], [t])
    return found.values[0]


def test_a_package_without_variants_is_its_own_model_named_by_its_folder(tmp_path):
    entry = write(tmp_path / 'desk', {'model.scn': MAIN})
    for target in (tmp_path / 'desk', entry):
        models = load_package(target)
        assert list(models) == ['desk']
        assert models['desk'].model_hash == load_scenario(entry).model_hash
    assert served_at(models['desk'], 10) == pytest.approx(20)


def test_a_relative_path_is_named_by_the_folder_that_it_stands_for(tmp_path, monkeypatch):
    write(tmp_path / 'desk', {'model.scn': MAIN})
    monkeypatch.chdir(tmp_path / 'desk')
    assert list(load_package('.')) == ['desk']
    assert list(load_package('model.scn')) == ['desk']
    assert name_of('model.scn') == 'desk'


def test_a_package_with_variants_is_the_model_of_each_variant_in_name_order(tmp_path):
    """The main file is part of each variant's model and no model of its own. The variants come in
    name order, whatever the order in which their folders were made; a folder without an entry file
    is no variant. Each variant serves at its own rate: 4 and 3 people an hour, 40 and 30 people in
    10 h."""
    files = {
        'model.scn': MAIN,
        'variants/west/model.scn': variant('West', 3),
        'variants/east/model.scn': variant('East', 4),
        'variants/notes/README.md': 'A folder without an entry file is no variant.\n',
    }
    entry = write(tmp_path / 'family', files)
    models = load_package(tmp_path / 'family')
    assert list(models) == ['family:east', 'family:west']
    assert list(entries(entry)) == list(models)
    for name in ('east', 'west'):
        alone = load_scenario(tmp_path / 'family' / 'variants' / name / 'model.scn')
        assert models[f'family:{name}'].model_hash == alone.model_hash
    assert {name: served_at(model, 10) for name, model in models.items()} == pytest.approx(
        {'family:east': 40, 'family:west': 30}
    )


def test_every_problem_of_every_model_is_kept_once(tmp_path):
    """Two variants fail, each in its own way; the third compiles. The one error holds the problems
    of both, each as `load_scenario` gives it at its own file. A problem of the main file, which each
    variant reads, comes once."""
    files = {
        'model.scn': MAIN,
        'variants/east/model.scn': variant('East', 4).replace('people/h', 'pople/h'),
        'variants/north/model.scn': variant('North', 5),
        'variants/west/model.scn': variant('West', 3).replace('change desk:', 'change desk'),
    }
    write(tmp_path / 'family', files)
    with pytest.raises(LanguageError) as caught:
        load_package(tmp_path / 'family')
    expected = []
    for name in ('east', 'west'):
        with pytest.raises(LanguageError) as alone:
            load_scenario(tmp_path / 'family' / 'variants' / name / 'model.scn')
        expected += alone.value.problems
    assert list(caught.value.problems) == expected
    assert {problem.file.split('/variants/')[1] for problem in expected} == {
        'east/model.scn',
        'west/model.scn',
    }
    broken = write(
        tmp_path / 'broken',
        {
            'model.scn': MAIN.replace('people/h =', 'pople/h ='),
            **{f'variants/{name}/model.scn': variant(name.title(), 3) for name in ('east', 'west')},
        },
    )
    with pytest.raises(LanguageError) as once:
        load_package(broken)
    with pytest.raises(LanguageError) as alone:
        load_scenario(broken.parent / 'variants' / 'east' / 'model.scn')
    assert once.value.problems == alone.value.problems


def test_a_folder_without_a_model_is_no_package(tmp_path):
    (tmp_path / 'empty').mkdir()
    with pytest.raises(FileNotFoundError):
        load_package(tmp_path / 'empty')
