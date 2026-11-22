"""Selected publication confines evaluation and file changes to the requested catalogue cases."""

import pytest

from tests.evidence.support import QUEUE, write_package
from tools import catalogue, publish
from tools.publish import __main__ as cli

# The committed location of each owner's readings and source dossier (`publish._locations`).
READINGS, DOSSIER = f'{publish.RESULTS}/readings.md', f'{publish.RESULTS}/source-dossier.json'


def write_files(root, files):
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def sources(root):
    for sid in ('SC97', 'SC98'):
        write_package(root, {'model.scn': QUEUE}, owner=sid)
    write_files(
        root,
        {
            'scenarios/SC99/model.scn': 'not a scenario',
        },
    )


def test_only_selected_models_are_read_and_evaluated_in_catalogue_order(tmp_path, monkeypatch):
    sources(tmp_path)
    evaluated = []
    evaluate = catalogue.completed_study

    def study(model, **options):
        evaluated.append(catalogue.owner_of(model.declared.files[-1][0], tmp_path))
        return evaluate(model, **options)

    monkeypatch.setattr(catalogue, 'completed_study', study)
    ctx = publish.Context(tmp_path, scenario_ids=['SC98', 'SC97', 'SC98'])
    assert list(ctx.paths) == ['SC97', 'SC98']
    # The unselected SC99 file is deliberately invalid. It must never reach the reader.
    assert list(ctx.models) == list(ctx.studies) == ['SC97', 'SC98']
    assert all(records[None].end == 4 for records in ctx.studies.values())
    assert evaluated == ['SC97', 'SC98']


def test_unknown_selection_fails_before_loading_or_evaluation(tmp_path, monkeypatch, capsys):
    sources(tmp_path)
    (tmp_path / 'scenarios/SC99/model.scn').unlink()
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(publish, 'load_scenario', lambda *a: pytest.fail('compiled before validation'))
    monkeypatch.setattr(catalogue, 'completed_study', lambda *a: pytest.fail('evaluated before validation'))
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
    assert {'readings', 'dossier', 'manifest'} <= set(publish.selected())
    assert publish.selected() == list(publish.builders())
    assert publish.selected(scenario_ids=[]) == publish.selected()
    assert publish.selected(scenario_ids=['SC97']) == [
        name for name in publish.builders() if name not in publish.AGGREGATE
    ]
    assert publish.selected(['dossier'], scenario_ids=['SC97']) == ['dossier']


@pytest.mark.parametrize(
    'selection,expected',
    [
        (['SC97'], ['scenarios/SC97/results/readings.md']),
        (['SC98'], ['scenarios/SC98/results/readings.md', 'scenarios/SC98/results/source-dossier.json']),
    ],
)
def test_build_skips_aggregates_and_builders_outside_the_selection(
    tmp_path, monkeypatch, selection, expected
):
    sources(tmp_path)
    messages = []
    ctx = publish.Context(tmp_path, scenario_ids=selection, progress=messages.append)
    monkeypatch.setattr(
        publish,
        'builders',
        lambda: {
            'readings': (
                lambda ctx: {catalogue.result(sid, 'readings.md'): 'readings' for sid in ctx.paths},
                (READINGS, 'scenarios/README.md'),
            ),
            'manifest': (
                lambda ctx: pytest.fail('ran an aggregate'),
                ('scenarios/docs/evidence/source-manifest.json',),
            ),
            'dossier': (
                lambda ctx: (
                    {'scenarios/SC98/results/source-dossier.json': 'dossier'}
                    if 'SC98' in ctx.paths
                    else pytest.fail('ran unselected builder')
                ),
                ('scenarios/SC98/results/source-dossier.json',),
            ),
        },
    )
    assert list(publish.build(ctx)) == expected
    assert any('skipping aggregate builders' in message for message in messages)


@pytest.mark.parametrize('path', ['scenarios/SC99/results/readings.md', 'scenarios/README.md'])
def test_selected_builder_cannot_write_an_unselected_or_aggregate_file(tmp_path, monkeypatch, path):
    sources(tmp_path)
    monkeypatch.setattr(
        publish,
        'builders',
        lambda: {
            'readings': (lambda ctx: {path: 'bad'}, (READINGS, 'scenarios/README.md')),
        },
    )
    with pytest.raises(ValueError, match='outside its committed locations'):
        publish.build(publish.Context(tmp_path, scenario_ids=['SC97']))


def test_selected_write_check_and_prune_preserve_unselected_and_authored_files(tmp_path, monkeypatch, capsys):
    sources(tmp_path)
    retained = {
        'scenarios/SC99/results/readings.md': 'stale unselected readings',
        'scenarios/SC99/results/source-dossier.json': 'stale unselected dossier',
        'scenarios/SC98/results/source-dossier.json': 'other unselected dossier',
        'scenarios/README.md': 'catalogue index',
        'scenarios/docs/evidence/source-manifest.json': 'aggregate',
        'scenarios/docs/evidence/SC97/calculation.md': 'authored calculation',
    }
    write_files(
        tmp_path,
        {
            **retained,
            'scenarios/SC97/results/readings.md': 'old readings',
            'scenarios/SC97/results/source-dossier.json': 'obsolete dossier',
        },
    )
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(
        publish,
        'builders',
        lambda: {
            'readings': (
                lambda ctx: {catalogue.result(sid, 'readings.md'): 'new readings' for sid in ctx.paths},
                (READINGS, 'scenarios/README.md'),
            ),
            'dossier': (lambda ctx: {}, (DOSSIER,)),
        },
    )
    arguments = ['--scenario', 'SC97']
    assert cli.main(['--check', *arguments]) == 1
    assert '--scenario SC97' in capsys.readouterr().err
    assert cli.main(['--write', *arguments]) == 0
    assert (tmp_path / 'scenarios/SC97/results/readings.md').read_text() == 'new readings'
    assert not (tmp_path / 'scenarios/SC97/results/source-dossier.json').exists()
    assert cli.main(['--check', *arguments]) == 0
    for path, text in retained.items():
        assert (tmp_path / path).read_text() == text


def test_a_variant_owns_the_summaries_in_its_own_results_folder(tmp_path):
    stale = {
        'scenarios/SC97/results/readings.md': 'package readings',
        'scenarios/SC97/variants/east/results/readings.md': 'east readings',
        'scenarios/SC97/variants/west/results/readings.md': 'west readings',
        # Invalid even on filesystems where east and East name the same folder.
        'scenarios/SC97/variants/North/results/readings.md': 'not a variant',
    }
    write_files(tmp_path, stale)
    east = 'scenarios/SC97/variants/east/results/readings.md'
    assert publish.orphans({}, tmp_path, ['readings'], scenario_ids=['SC97:east']) == [east]
    assert publish.orphans({}, tmp_path, ['readings']) == sorted(
        set(stale) - {'scenarios/SC97/variants/North/results/readings.md'}
    )
    assert publish.prune({}, tmp_path, ['readings'], scenario_ids=['SC97:east']) == [east]
    assert not (tmp_path / east).exists()
    for path, contents in stale.items():
        if path != east:
            assert (tmp_path / path).read_text() == contents
    # A selection names an owner with a model of its own.
    write_files(tmp_path, {'scenarios/SC97/variants/west/model.scn': 'not compiled'})
    assert list(publish.Context(tmp_path, scenario_ids=['SC97:west']).paths) == ['SC97:west']
    with pytest.raises(ValueError, match='SC97:east'):
        publish.Context(tmp_path, scenario_ids=['SC97:east'])
    with pytest.raises(ValueError, match='must have the form'):
        publish.Context(tmp_path, scenario_ids=['SC97:East'])
