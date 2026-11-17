"""Owned scenario resources, narrow publication ownership and explicit link contexts."""

from tools import catalogue
from tools.publish import orphans, prune


def test_discovery_requires_the_owned_model_and_ignores_flat_files(tmp_path):
    folder = tmp_path / 'scenarios'
    folder.mkdir()
    (folder / 'SC97.yaml').write_text('old layout')
    (folder / 'SC98').mkdir()
    assert catalogue.entries(tmp_path) == {}
    assert catalogue.scenario_path(tmp_path, 'SC97') == folder / 'SC97/model.scn'
    (folder / 'SC98/model.scn').touch()
    assert list(catalogue.entries(tmp_path)) == ['SC98']


def test_pruning_only_owns_named_outputs_and_preserves_other_material(tmp_path):
    retained = (
        'scenarios/SC97/README.md',
        'scenarios/SC97/model.scn',
        'scenarios/SC97/style.toml',
        'scenarios/SC97/brief.toml',
        'scenarios/SC97/results/notes.md',
        'scenarios/SC97/results/unknown.json',
        'scenarios/SC98/results/brief.md',
        'scenarios/SC98/results/methods.md',
        'scenarios/unknown/results/brief.md',
    )
    removed = 'scenarios/SC97/results/methods.md'
    for name in (*retained, removed):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    assert orphans({}, tmp_path, ['methods'], scenario_ids=['SC97']) == [removed]
    assert prune({}, tmp_path, ['methods'], scenario_ids=['SC97']) == [removed]
    assert all((tmp_path / name).read_text() == name for name in retained)
