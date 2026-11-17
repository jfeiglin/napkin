"""Selected publication confines evaluation and file changes to the requested catalogue cases."""

import copy
import json
from types import SimpleNamespace

import pytest

from tests.build import scenario
from tests.helpers import ROOT
from tests.owned import write_scenario
from tools import catalogue, publish
from tools.publish import __main__ as cli
from tools.publish import runs

# The committed location of each owner's brief and methods record (`publish._locations`).
BRIEF, METHODS = f'{publish.RESULTS}/brief.md', f'{publish.RESULTS}/methods.md'


def write_files(root, files):
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def sources(root):
    for sid in ('SC97', 'SC98'):
        write_scenario(root, scenario(), owner=sid)
    write_files(
        root,
        {
            'scenarios/SC99/model.scn': 'not a scenario',
        },
    )


def test_only_selected_models_are_read_and_evaluated_in_catalogue_order(tmp_path, monkeypatch):
    sources(tmp_path)
    evaluated = []
    evaluate = publish.evaluate_study

    def study(model):
        evaluated.append(catalogue.name_of(model.origin))
        return evaluate(model)

    monkeypatch.setattr(publish, 'evaluate_study', study)
    ctx = publish.Context(tmp_path, scenario_ids=['SC98', 'SC97', 'SC98'])
    assert list(ctx.paths) == ['SC97', 'SC98']
    # The unselected SC99 file is deliberately invalid. It must never reach the reader.
    assert list(ctx.models) == list(ctx.studies) == ['SC97', 'SC98']
    assert all(study.admissible for study in ctx.studies.values())
    assert evaluated == ['SC97', 'SC98']


def test_unknown_selection_fails_before_loading_or_evaluation(tmp_path, monkeypatch, capsys):
    sources(tmp_path)
    (tmp_path / 'scenarios/SC99/model.scn').unlink()
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(publish, 'load_scenario', lambda *a: pytest.fail('compiled before validation'))
    monkeypatch.setattr(publish, 'evaluate_study', lambda *a: pytest.fail('evaluated before validation'))
    with pytest.raises(SystemExit) as error:
        cli.main(['--write', '--scenario', 'SC97', '--scenario', 'SC99'])
    assert error.value.code == 2
    assert 'Unknown scenario IDs: SC99' in capsys.readouterr().err
    assert not (tmp_path / catalogue.DOCS).exists() and not (tmp_path / catalogue.INDEX).exists()


@pytest.mark.parametrize('options', [['--only', name] for name in publish.AGGREGATE])
def test_selected_aggregate_requests_fail_before_constructing_a_context(options, monkeypatch, capsys):
    monkeypatch.setattr(cli, 'Context', lambda *a, **k: pytest.fail('constructed a context'))
    with pytest.raises(SystemExit) as error:
        cli.main(['--check', '--scenario', 'SC97', *options])
    assert error.value.code == 2
    assert '--scenario' in capsys.readouterr().err


def test_no_selection_keeps_the_full_builder_order():
    assert publish.selected() == ['briefs', 'methods', 'dossier', 'manifest', 'assumptions', 'runs']
    assert publish.selected() == list(publish.builders())
    assert publish.selected(scenario_ids=[]) == publish.selected()
    assert publish.selected(scenario_ids=['SC97']) == ['briefs', 'methods', 'dossier', 'assumptions', 'runs']
    assert publish.selected(['methods'], scenario_ids=['SC97']) == ['methods']


@pytest.mark.parametrize(
    'selection,expected',
    [
        (['SC97'], ['scenarios/SC97/results/brief.md']),
        (['SC98'], ['scenarios/SC98/results/brief.md', 'scenarios/SC98/results/runs.json']),
    ],
)
def test_build_skips_aggregates_and_unselected_sweeps(tmp_path, monkeypatch, selection, expected):
    sources(tmp_path)
    messages = []
    ctx = publish.Context(tmp_path, scenario_ids=selection, progress=messages.append)
    monkeypatch.setattr(
        publish,
        'builders',
        lambda: {
            'briefs': (
                lambda ctx: {catalogue.result(sid, 'brief.md'): 'brief' for sid in ctx.paths},
                (BRIEF, 'scenarios/README.md'),
            ),
            'manifest': (
                lambda ctx: pytest.fail('ran an aggregate'),
                ('scenarios/docs/evidence/source-manifest.json',),
            ),
            'runs': (
                lambda ctx: (
                    {'scenarios/SC98/results/runs.json': 'sweeps'}
                    if 'SC98' in ctx.paths
                    else pytest.fail('ran unselected sweeps')
                ),
                ('scenarios/SC98/results/runs.json',),
            ),
        },
    )
    assert list(publish.build(ctx)) == expected
    assert any('skipping aggregate builders' in message for message in messages)
    assert any('scenarios/README.md' in message for message in messages)


@pytest.mark.parametrize('path', ['scenarios/SC99/results/brief.md', 'scenarios/README.md'])
def test_selected_builder_cannot_write_an_unselected_or_aggregate_file(tmp_path, monkeypatch, path):
    sources(tmp_path)
    monkeypatch.setattr(
        publish,
        'builders',
        lambda: {
            'briefs': (lambda ctx: {path: 'bad'}, (BRIEF, 'scenarios/README.md')),
        },
    )
    with pytest.raises(ValueError, match='outside its committed locations'):
        publish.build(publish.Context(tmp_path, scenario_ids=['SC97']))


def test_selected_write_check_and_prune_preserve_unselected_and_authored_files(tmp_path, monkeypatch, capsys):
    sources(tmp_path)
    retained = {
        'scenarios/SC99/results/brief.md': 'stale unselected brief',
        'scenarios/SC99/results/methods.md': 'stale unselected methods',
        'scenarios/SC98/results/runs.json': 'stale unselected sweeps',
        'scenarios/README.md': 'catalogue index',
        'scenarios/docs/evidence/source-manifest.json': 'aggregate',
        'scenarios/docs/evidence/SC97/calculation.md': 'authored calculation',
    }
    write_files(
        tmp_path,
        {
            **retained,
            'scenarios/SC97/results/brief.md': 'old brief',
            'scenarios/SC97/results/methods.md': 'obsolete methods',
        },
    )
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(
        publish,
        'builders',
        lambda: {
            'briefs': (
                lambda ctx: {catalogue.result(sid, 'brief.md'): 'new brief' for sid in ctx.paths},
                (BRIEF, 'scenarios/README.md'),
            ),
            'methods': (lambda ctx: {}, (METHODS,)),
        },
    )
    arguments = ['--scenario', 'SC97']
    assert cli.main(['--check', *arguments]) == 1
    assert '--scenario SC97' in capsys.readouterr().err
    assert cli.main(['--write', *arguments]) == 0
    assert (tmp_path / 'scenarios/SC97/results/brief.md').read_text() == 'new brief'
    assert not (tmp_path / 'scenarios/SC97/results/methods.md').exists()
    assert cli.main(['--check', *arguments]) == 0
    for path, text in retained.items():
        assert (tmp_path / path).read_text() == text


def test_a_variant_owns_the_summaries_in_its_own_results_folder(tmp_path):
    stale = {
        'scenarios/SC97/results/brief.md': 'package brief',
        'scenarios/SC97/variants/east/results/brief.md': 'east brief',
        'scenarios/SC97/variants/west/results/brief.md': 'west brief',
        # A folder that no variant can have.
        'scenarios/SC97/variants/East/results/brief.md': 'not a variant',
    }
    write_files(tmp_path, stale)
    east = 'scenarios/SC97/variants/east/results/brief.md'
    assert publish.orphans({}, tmp_path, ['briefs'], scenario_ids=['SC97:east']) == [east]
    assert publish.orphans({}, tmp_path, ['briefs']) == sorted(
        set(stale) - {'scenarios/SC97/variants/East/results/brief.md'}
    )
    assert publish.prune({}, tmp_path, ['briefs'], scenario_ids=['SC97:east']) == [east]
    assert sorted(path for path in stale if (tmp_path / path).is_file()) == sorted(set(stale) - {east})
    # A selection names an owner with a model of its own.
    write_files(tmp_path, {'scenarios/SC97/variants/west/model.scn': 'not compiled'})
    assert list(publish.Context(tmp_path, scenario_ids=['SC97:west']).paths) == ['SC97:west']
    with pytest.raises(ValueError, match='SC97:east'):
        publish.Context(tmp_path, scenario_ids=['SC97:east'])
    with pytest.raises(ValueError, match='must have the form'):
        publish.Context(tmp_path, scenario_ids=['SC97:East'])


def test_a_selection_keeps_declared_sweep_edits_and_rows(tmp_path, monkeypatch):
    sources(tmp_path)
    ctx = publish.Context(tmp_path, scenario_ids=['SC98'])
    edits = {'set': {'service.n': 8}}
    # The brief settings beside the model file declare the sweep.
    (tmp_path / 'scenarios/SC98/brief.toml').write_text(
        '[[sweep]]\nid = "selected_probe"\ndescription = "Probe"\nrun = "a"\nset = {"service.n" = 8}\n'
    )
    calls = []
    original = runs.sweep_row

    def sweep(model, run, rid, description, body):
        calls.append(copy.deepcopy(body))
        return original(model, run, rid, description, body)

    monkeypatch.setattr(runs, 'sweep_row', sweep)
    outputs = runs.artifacts(ctx)
    table = json.loads(outputs['scenarios/SC98/results/runs.json'])
    assert calls == [edits]
    assert [row['id'] for row in table['rows']] == [*ctx.models['SC98'].runs, 'selected_probe']
    assert table['rows'][-1]['edits'] == edits
    assert table['rows'][-1]['inputs']['service.n'] == 8
    assert set(outputs) == {'scenarios/SC98/results/runs.json', 'scenarios/SC98/results/runs.csv'}


def test_a_selected_scenario_without_sweeps_reads_no_model():
    # The run-table builder reads a model only for a scenario that declares sweeps.
    ctx = SimpleNamespace(
        root=ROOT, paths={'SC97': catalogue.scenario_path(ROOT, 'SC97')}, scenario_ids=('SC97',)
    )
    assert runs.artifacts(ctx) == {}
