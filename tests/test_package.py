"""A package's models (`napkin.package.load_package`) and the run of a combination of options under an
edit document (`napkin.package.combined`).

The packages are written in `tmp_path` with generic names. `load_package` builds what `load_scenario`
builds for each entry file, so each expectation is the model or the diagnostics of `load_scenario` on
the same file. The combinations use the analytic transfer of `tests/engine/test_combinations.py`,
whose served total is min(n, rate * end) by its closed form, with the values that the test reads from
the model or edits itself.
"""

from __future__ import annotations

import copy

import pytest

from napkin.engine import edits_for, evaluate_study, resolve_edits, sample_result
from napkin.model import ModelError, SourceError, load_scenario
from napkin.model.ir import thaw
from napkin.model.language import front
from napkin.package import combined, load_package, source_problem
from tests.build import compiled, library, replace, runs
from tests.engine.test_combinations import fixture, served

MAIN = """\
scenario "A desk"
    summary "A file for tests only."
    horizon 10 h
    scope "Fixture"

desk:  @fixture
    "A desk."
    role environment
    input rate = 2 people/h in 0 people/h to 10 people/h  @fixture
        "Rate"
    var served: people = 0 people size 1000 people  @fixture
        "People served"
    flow serve: -> served at rate  @fixture

output served: people = desk.served  @fixture
    "People served"

record fixture: identity "Fixture."
"""


def variant(title, rate):
    """A variant that gives the desk its own rate."""
    return f'variant "{title}"\n\nchange desk:\n    rate = {rate} people/h  @fixture\n'


def write(folder, files):
    """The files {path in the folder: text} of a package in `folder`; its entry file."""
    for relative, text in files.items():
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return folder / 'model.scn'


def diagnostics(path):
    with pytest.raises(ModelError) as caught:
        load_scenario(path)
    return caught.value.diagnostics


# ---- load_package ---------------------------------------------------------------------------------


def test_a_package_without_variants_is_its_own_model_named_by_its_folder(tmp_path):
    entry = write(tmp_path / 'desk', {'model.scn': MAIN})
    for target in (tmp_path / 'desk', entry):
        models = load_package(target)
        assert list(models) == ['desk']
        assert models['desk'].model_hash == load_scenario(entry).model_hash


def test_a_relative_path_is_named_by_the_folder_that_it_stands_for(tmp_path, monkeypatch):
    write(tmp_path / 'desk', {'model.scn': MAIN})
    monkeypatch.chdir(tmp_path / 'desk')
    assert list(load_package('.')) == ['desk']
    assert list(load_package('model.scn')) == ['desk']


def test_a_package_with_variants_is_the_model_of_each_variant_in_name_order(tmp_path):
    """The main file is part of each variant's model and no model of its own. The variants come in
    name order, whatever the order in which their folders were made."""
    files = {
        'model.scn': MAIN,
        'variants/west/model.scn': variant('West', 3),
        'variants/east/model.scn': variant('East', 4),
        'variants/notes/README.md': 'A folder without an entry file is no variant.\n',
    }
    entry = write(tmp_path / 'family', files)
    models = load_package(tmp_path / 'family')
    assert list(models) == ['family:east', 'family:west']
    for name in ('east', 'west'):
        alone = load_scenario(tmp_path / 'family' / 'variants' / name / 'model.scn')
        assert models[f'family:{name}'].model_hash == alone.model_hash
    assert load_package(entry).keys() == models.keys()
    # Each variant is a model of its own: its rate.
    rates = {name: model.inputs['desk.rate']['value'] for name, model in models.items()}
    assert rates == {'family:east': 4, 'family:west': 3}


def test_every_diagnostic_of_every_model_is_kept_and_named_by_its_model(tmp_path):
    """Two variants fail, each in its own way; the third builds. The one error holds the diagnostics of
    both, each as `load_scenario` gives it, with the name of its model."""
    files = {
        'model.scn': MAIN,
        'variants/east/model.scn': variant('East', 4).replace('people/h', 'pople/h'),
        'variants/north/model.scn': variant('North', 5),
        'variants/west/model.scn': variant('West', 3).replace('change desk:', 'change desk'),
    }
    write(tmp_path / 'family', files)
    with pytest.raises(ModelError) as caught:
        load_package(tmp_path / 'family')
    found = caught.value.diagnostics
    assert {item['model'] for item in found} == {'family:east', 'family:west'}
    for name in ('east', 'west'):
        own = [
            {k: v for k, v in item.items() if k != 'model'}
            for item in found
            if item['model'] == f'family:{name}'
        ]
        assert own and own == diagnostics(tmp_path / 'family' / 'variants' / name / 'model.scn')


def test_a_file_that_is_not_valid_source_is_a_diagnostic_with_its_file(tmp_path):
    """A units file with a key written twice raises a SourceError, which keeps its file. Beside it,
    the diagnostics of a model that fails are kept too."""
    files = {
        'model.scn': MAIN,
        'variants/east/model.scn': variant('East', 4),
        'variants/east/units.json': '{"desks": {"dimensions": {"desks": 1}, "scale": 1}, "desks": {}}',
        'variants/west/model.scn': variant('West', 3).replace('people/h', 'pople/h'),
    }
    write(tmp_path / 'family', files)
    units = tmp_path / 'family' / 'variants' / 'east' / 'units.json'
    with pytest.raises(SourceError) as raised:
        load_scenario(units.with_name('model.scn'))
    with pytest.raises(ModelError) as caught:
        load_package(tmp_path / 'family')
    (east,) = [item for item in caught.value.diagnostics if item['model'] == 'family:east']
    assert (east['code'], east['file'], east['severity']) == ('source', str(units), 'error')
    assert 'line' not in east and str(raised.value) == f'{units}: {east["message"]}'
    assert any(item['model'] == 'family:west' for item in caught.value.diagnostics)


def test_a_source_error_with_a_line_keeps_the_line(tmp_path):
    problem = source_problem(SourceError(tmp_path / 'units.json', 7, 'a key written twice'))
    assert {key: problem[key] for key in ('code', 'file', 'line', 'message')} == {
        'code': 'source',
        'file': str(tmp_path / 'units.json'),
        'line': 7,
        'message': 'a key written twice',
    }


def test_a_folder_without_a_model_is_no_package(tmp_path):
    (tmp_path / 'empty').mkdir()
    with pytest.raises(FileNotFoundError):
        load_package(tmp_path / 'empty')


def test_admission_reaches_each_model(tmp_path):
    entry = write(tmp_path / 'family', {'model.scn': MAIN, 'variants/east/model.scn': variant('East', 4)})
    (model,) = load_package(entry, admission_runs=['base']).values()
    assert model.admission_runs == ('base',)


# ---- combined -------------------------------------------------------------------------------------

# The runs of the transfer (`fixture`): a (Default), b (Default and Half rate) and c (Fast, which stops
# later). The combination of run `a` with Half rate is the options of `b`; no run of `a` makes it.
RUNS = runs(a=['Default'], b=['Default', 'Half rate'], c=['Fast'])


def compiled_fixture(*steps, checked=False):
    return compiled(fixture(*steps, checked=checked))


def body():
    """An edit document's levels: every run, the three options, run `a` and run `c`. Each value is in
    its input's range."""
    return {
        'set': {'service.n': 9},
        'options': {
            'Half rate': {'service.rate': 6},
            'Fast': {'service.end': 16},
            'Default': {'service.end': 10},
        },
        'runs': {'a': {'service.n': 8}, 'c': {'service.rate': 30}},
        'reason': 'A test.',
    }


def test_the_document_keeps_what_reaches_the_combined_run():
    model = compiled_fixture()
    edits = edits_for(model, body())
    before = copy.deepcopy(edits)
    derived, kept = combined(model, 'a', ['Half rate'], edits)
    assert list(derived.runs) == ['a'] and derived.runs['a']['options'] == ('Default', 'Half rate')
    assert kept == {
        'schema_version': edits['schema_version'],
        'model_hash': model.model_hash,
        'reason': 'A test.',
        'set': {'service.n': 9},
        'options': {'Half rate': {'service.rate': 6}, 'Default': {'service.end': 10}},
        'runs': {'a': {'service.n': 8}},
    }
    assert edits == before  # the caller's document is not changed
    # The edit of run c is checked and dropped: the derived model has no run c, and refuses it.
    assert evaluate_study(derived, kept).admissible
    refused = evaluate_study(derived, edits)
    assert not refused.admissible and {d['code'] for d in refused.diagnostics} == {'reference'}


def test_an_edit_of_another_run_that_breaks_a_check_is_refused():
    """In run c (Fast, which stops at 20 h), a rate of 12 people a day breaks the check that a slow
    rate stops early. The combination of run a takes no edit of run c, so a check of the combined run
    alone would admit the document; `combined` checks every run and refuses it, as the engine does."""
    model = compiled_fixture(checked=True)
    edits = edits_for(model, {'runs': {'c': {'service.rate': 12}}})
    with pytest.raises(ModelError) as caught:
        combined(model, 'a', ['Half rate'], edits)
    with pytest.raises(ModelError) as engine:
        resolve_edits(model, edits)
    assert caught.value.diagnostics == engine.value.diagnostics
    assert {(d['code'].partition(':')[0], d['run']) for d in caught.value.diagnostics} == {('check', 'c')}
    # The counterexample: the document reduced to run a alone is admissible in the combination.
    derived = model.combination('a', ['Half rate'])
    assert evaluate_study(derived, {key: value for key, value in edits.items() if key != 'runs'}).admissible


def test_the_combined_study_equals_the_study_of_a_model_that_names_the_combination_as_a_run():
    """The transfer written with run `a` as Default and Half rate is the combination, declared. Under
    the same edits, the two studies of run `a` give the same values, report and trace, and the served
    total of the closed form."""
    model = compiled_fixture()
    named = compiled_fixture(replace(RUNS, runs(a=['Default', 'Half rate'], c=['Fast'])))
    derived, kept = combined(model, 'a', ['Half rate'], edits_for(model, body()))
    mine = evaluate_study(derived, kept)
    theirs = evaluate_study(named, edits_for(named, body()), runs=['a'])
    assert mine.admissible and theirs.admissible
    values = mine.runs['a']['resolved'].parameter_values
    assert values == theirs.runs['a']['resolved'].parameter_values
    assert (values['service.n'], values['service.rate'], values['service.end']) == (8, 6, 10)
    assert mine.runs['a']['trajectory'].trace == theirs.runs['a']['trajectory'].trace
    final = {
        name: sample_result(study)['runs']['a']['reporting_points']['final']
        for name, study in (('mine', mine), ('theirs', theirs))
    }
    assert final['mine'] == final['theirs']
    assert final['mine']['values']['delivered'] == pytest.approx(served(values), rel=1e-9)


def test_without_edits_the_combination_is_the_model_s_own():
    model = compiled_fixture()
    derived, kept = combined(model, 'c', ['Half rate'])
    assert kept is None
    assert derived.runs['c']['options'] == model.combination('c', ['Half rate']).runs['c']['options']


@pytest.mark.parametrize(
    ('run', 'chosen', 'change', 'code'),
    [
        ('a', ['Quick'], {}, 'reference'),
        ('a', ['Default', 'Fast'], {}, 'combination'),
        ('a', ['Half rate'], {'model_hash': 'another'}, 'model_hash'),
        ('a', ['Half rate'], {'runs': {'d': {'service.n': 2}}}, 'reference'),
        ('a', ['Half rate'], {'set': {'service.n': 1000}}, 'bounds'),
    ],
    ids=['unknown option', 'two options of a group', 'another revision', 'unknown run', 'out of range'],
)
def test_the_engine_s_errors_come_unchanged(run, chosen, change, code):
    model = compiled_fixture()
    edits = {**edits_for(model, {'set': {'service.n': 5}}), **change}
    with pytest.raises(ModelError) as caught:
        combined(model, run, chosen, edits)
    # The engine's own error: the check of the document first, then the combination.
    with pytest.raises(ModelError) as engine:
        resolve_edits(model, edits)
        model.combination(run, chosen)
    assert caught.value.diagnostics == engine.value.diagnostics
    assert code in {d['code'] for d in engine.value.diagnostics}


def test_a_model_admitted_for_some_runs_is_checked_in_those_runs():
    """A model built for run a alone (`admission_runs`) resolves only run a: the edits of run c are
    still checked against their inputs, and the rest of the document applies to the combination."""
    text = fixture(checked=True)
    scoped = front.compile_file(
        front.read(text, 'test.scn'), 'test.scn', thaw(library()), admission_runs=['a']
    )
    edits = edits_for(scoped, {'runs': {'a': {'service.n': 4}, 'c': {'service.rate': 12}}})
    derived, kept = combined(scoped, 'a', ['Half rate'], edits)
    assert kept['runs'] == {'a': {'service.n': 4}}
    assert evaluate_study(derived, kept).admissible
    with pytest.raises(ModelError) as caught:
        combined(scoped, 'a', ['Half rate'], {**edits, 'runs': {'c': {'service.rate': 0}}})
    assert {d['path'] for d in caught.value.diagnostics} == {'edits/runs/c/service.rate'}
