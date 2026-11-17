"""Each scenario owns its assumption disclosure and retains its authored review status."""

import ast
import json
from collections import Counter
from functools import cache
from hashlib import sha256

from tests.helpers import ROOT
from tests.owned import block_at
from tools import catalogue
from tools.publish import Context
from tools.publish.assumptions import artifacts


@cache
def rendered_inventory():
    return {path: json.loads(content) for path, content in artifacts(Context(ROOT)).items()}


def test_inventory_keeps_owned_records_separate_and_retains_review_and_origin():
    outputs = rendered_inventory()
    # One inventory for each scenario, in its results folder; none for the catalogue as a whole.
    assert set(outputs) == {
        catalogue.result(sid, 'assumption-review.json') for sid in catalogue.entries(ROOT)
    }
    for sid in catalogue.entries(ROOT):
        inventory = outputs[catalogue.result(sid, 'assumption-review.json')]
        retained = {(item['scenario'], item['id']): item for item in inventory['assumptions']}
        expected = {
            (sid, item['id']): item
            for item in json.loads((catalogue.locate(sid, ROOT).evidence / 'assumptions.json').read_text())
        }
        assert retained.keys() == expected.keys()
        for key, item in expected.items():
            row = retained[key]
            assert row['authoritative_review'] == item['review']
            assert row['review_status'] == item['review']['status']
            assert row['origin'] == item.get('origin')
            assert row['origin_declared'] == ('origin' in item)
            assert row['selection_status'] == item.get('status')
            assert row['decided'] == item.get('decided')
        assert inventory['counts']['authoritative_review_status'] == dict(
            Counter(item['review']['status'] for item in expected.values())
        )


def test_local_inventories_identify_their_own_files_and_reference_locations():
    outputs = rendered_inventory()
    for sid, model_path in catalogue.entries(ROOT).items():
        inventory = outputs[catalogue.result(sid, 'assumption-review.json')]
        basis = inventory['authoritative_basis']
        owned = catalogue.locate(sid, ROOT).evidence / 'assumptions.json'
        assert basis['path'] == owned.relative_to(ROOT).as_posix()
        assert basis['sha256'] == sha256((ROOT / basis['path']).read_bytes()).hexdigest()
        authored = model_path.read_text(encoding='utf-8')
        for record in inventory['assumptions']:
            assert record['scenario'] == sid
            # Each place is a line of the file whose line, or a line under it, names the assumption.
            for place in record['places']:
                assert record['id'] in block_at(authored, place), place


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
