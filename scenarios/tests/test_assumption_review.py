"""Each scenario owns its assumption disclosure and retains its authored review status."""

import ast
import json

import pytest

from napkin.model.evidence import dependencies
from napkin.model.language.evidence import document
from napkin.model.library import library_folders, load_library
from tests.helpers import ROOT, SCENARIO_IDS, catalogue_model
from tools import catalogue


@pytest.mark.scenario_contract
@pytest.mark.parametrize('sid', SCENARIO_IDS)
def test_library_retains_the_owning_files_assumptions_and_reviews(sid):
    entry = catalogue.scenario_path(ROOT, sid)
    model = catalogue_model(sid)
    library = load_library(entry)
    effective = {item['id']: item for item in library['assumptions']}
    reached = set(dependencies(document(model.declared.tree), library)['assumptions'])
    for folder in library_folders(entry):
        path = folder / 'evidence' / 'assumptions.json'
        if path.exists():
            for item in json.loads(path.read_text(encoding='utf-8')):
                assert item['review']['status']
                assert effective[item['id']] == item, path
                if folder == entry.parent:
                    assert item['id'] in reached, path


def test_consequence_reference_mathematics_uses_independently_authored_functions():
    production = {
        'build_model',
        'compile_file',
        'compile_scenario',
        'evaluate_study',
        'sample_result',
        'load',
        'load_json',
        'load_scenario',
        'simulate',
        'model',
        'run',
        'final',
    }
    declared = set()
    for sid in catalogue.entries(ROOT):
        mapping = json.loads((catalogue.locate(sid, ROOT).folder / 'tests/oracle-inputs.json').read_text())
        declared.update(mapping)
    assert declared
    for name in sorted(declared):
        path = ROOT / name
        tree = ast.parse(path.read_text())
        if not path.name.startswith('test_'):
            modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            modules += [
                alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
            ]
            assert all(module and module.split('.')[0] not in ('napkin', 'tools') for module in modules)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.endswith(('_expected', '_probability')):
                continue
            calls = {
                call.func.id
                for call in ast.walk(node)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            }
            assert calls.isdisjoint(production)
