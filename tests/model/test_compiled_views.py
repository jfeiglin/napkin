"""Compiler views are the one interpretation that the studies, the pages and the map use."""

import ast
from dataclasses import replace
from importlib.util import resolve_name
from pathlib import Path
from unittest.mock import patch

import pytest

from napkin.engine import evaluate_study, resolve_edits
from napkin.model.ir import freeze, thaw
from napkin.model.language import front
from napkin.model.language.resolve import resolve
from napkin.model.runs import Runs
from napkin.model.semantic import Assign
from tests.build import compiled, document, edit, entity, library, parameter, scenario, template, text_value
from tests.build import replace as replace_text
from tools.publish.pages import Pages


def test_raw_runs_collects_problems_without_lowering_or_proofs():
    # A number of people written without its unit: a problem of the run table.
    text = edit(scenario(), replace_text('input n: people = 10 people in', 'input n: people = -1 in'))
    with (
        patch('napkin.model.language.front.compile_file', side_effect=AssertionError('compile')),
        patch('napkin.model.analysis.values.value_facts', side_effect=AssertionError('proof')),
        patch('napkin.model.model.Builder', side_effect=AssertionError('lowering')),
    ):
        semantic, _ = resolve(front.read(text, 'test.scn'), library())
        raw = Runs.from_scenario(semantic, library())
        frozen = Runs.from_table(raw.table)
    assert raw.problems and raw.problems == frozen.problems
    assert raw.inputs == frozen.inputs


def test_compilation_builds_one_table_and_consumers_reuse_it():
    with patch.object(Runs, 'from_scenario', wraps=Runs.from_scenario) as build_table:
        model = compiled(scenario(), library())
        assert build_table.call_count == 1
        assert evaluate_study(model).admissible
        Pages(model).all()
        assert build_table.call_count == 1
    with pytest.raises(TypeError):
        model.run_table.data['inputs']['service.n']['value'] = 1
    with pytest.raises(AttributeError):
        model.scenario.entity('service').value('n').value = 1


def test_each_entity_uses_its_own_resolved_unit():
    text = document(
        'Different items',
        template(
            'Channel',
            text_value('item', 'people'),
            parameter('n', 5, '{item}', 1, 10),
            doc='A channel.',
            role='warehouse',
        ),
        entity('first', template='Channel', records=None),
        entity('second', 'item = "episodes"', template='Channel', records=None),
        notes='checked: "By a fixture."',
    )
    model = compiled(text, library())
    table = Runs.from_table(model.run_table)
    assert table.inputs['first.n'].unit == model.inputs['first.n']['unit'] == 'people'
    assert table.inputs['second.n'].unit == model.inputs['second.n']['unit'] == 'episodes'
    assert model.scenario.entity('first').role == 'warehouse'
    written = {note.key: note.value.value for note in front.read(text, 'test.scn').notes}
    assert {note.key: thaw(note.value) for note in model.scenario.notes} == written


def test_consumers_need_only_source_review_not_raw_language_declarations():
    """The model keeps no declaration of its file, and its line map serves only the diagnostics: the
    study and the pages are the same without it."""
    model = compiled(scenario(), library())
    assert not hasattr(model, 'document')
    expected_pages = Pages(model).all()
    stripped = replace(model, lines=freeze({}))
    assert resolve_edits(stripped) == resolve_edits(model)
    assert evaluate_study(stripped).admissible
    assert Pages(stripped).all() == expected_pages
    # The semantic model holds the change of each event: the lines of its one outcome.
    (event,) = [event for event in model.scenario.entity('service').events if event.name == 'stop']
    ((outcome, (line,)),) = [(outcome, outcome.lines) for outcome in event.outcomes]
    assert outcome.name == 'done' and isinstance(line, Assign)
    assert (line.target.entity, line.target.member) == ('service', 'state')


# The front end, which reads a model file into its semantic model.
FRONT = 'napkin.model.language'


# The checkout, which holds the package (`napkin/`) and the maintainer tools (`tools/`).
ROOT = Path(__file__).resolve().parents[2]


def imported_modules(source):
    """The modules that a file of the package or of the tools imports, by their absolute names, with
    each name that a `from` import takes as a module of its own."""
    here = '.'.join(source.relative_to(ROOT).with_suffix('').parts)
    found = set()
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name('.' * node.level + (node.module or ''), here.rpartition('.')[0])
            found.update({base, *(f'{base}.{alias.name}' for alias in node.names)})
    return found


def test_consumers_do_not_import_source_merge_or_resolution_helpers():
    inner = {f'{FRONT}.{name}' for name in ('parse', 'nodes', 'resolve', 'evidence', 'expressions')}
    forbidden = {'merged_fields', 'merged_options', 'merged_policy', 'resolve_basis', 'resolve_bases'}
    for folder in ('napkin/engine', 'napkin/draw', 'tools/publish', 'tools/evidence'):
        sources = sorted((ROOT / folder).rglob('*.py'))
        assert sources, folder
        for source in sources:
            tree = ast.parse(source.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not forbidden.intersection(alias.name for alias in node.names), source
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id != 'Runs', source
            # The consumers read the semantic model, never the parts of the front end that read a
            # file into it. Only the stylesheet reads its lines, and the catalogue the scenario block.
            assert not inner & imported_modules(source), source
    # The builder reads the semantic model only: no front end, reader or loader.
    lowering = sorted((ROOT / 'napkin' / 'model' / 'lower').glob('*.py'))
    assert len(lowering) >= 3
    for build in lowering:
        read = {m for m in imported_modules(build) if m.startswith(FRONT)}
        assert not read and 'napkin.model.load' not in imported_modules(build), build
