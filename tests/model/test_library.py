"""Scenario files own their evidence and units; shared vocabulary is the only common input."""

import json

import pytest

from napkin.model import ModelError, load_json, load_library, load_scenario
from napkin.model.evidence import claim_digest
from napkin.model.ir import thaw
from napkin.model.library import prelude_units
from tests.build import compiled, edit, evidence_library, fixture_claim, member, parameter, sc99
from tests.owned import write_scenario
from tools import catalogue


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(thaw(value)), encoding='utf-8')


def owned_files(root, library=None):
    """(the model.scn of the folder of SC99 in `root`, with its own units and evidence and the shared
    vocabulary of `library`; the model of the same text that `library` builds in memory)."""
    library = evidence_library() if library is None else library
    path, _ = write_scenario(root, sc99(), library)
    return path, compiled(sc99(), library)


def test_physical_ownership_preserves_projection_and_requires_no_central_library(tmp_path):
    path, projected = owned_files(tmp_path)
    assert not (tmp_path / catalogue.LIBRARY / 'library.json').exists()
    actual = load_scenario(path)
    assert actual.model_hash == projected.model_hash
    assert actual.library_hash == projected.library_hash
    assert actual.structures == projected.structures
    first = next(iter(projected.runs))
    assert actual.resolve(first) == projected.resolve(first)


def test_local_unit_cannot_reuse_a_shared_name_even_with_the_same_definition(tmp_path):
    path, _ = owned_files(tmp_path)
    vocabulary = json.loads((tmp_path / catalogue.LIBRARY / 'vocabulary.json').read_text())
    write_json(path.parent / 'units.json', {'people/h': vocabulary['units']['people/h']})
    with pytest.raises(ModelError, match='local unit may not reuse'):
        load_scenario(path)


def test_no_library_and_no_units_file_redefines_a_unit_of_the_prelude(tmp_path):
    """The prelude's names are every model's: a units file and a library that write one, even with the
    prelude's own definition, are errors at that unit."""
    path, _ = owned_files(tmp_path)
    prelude = prelude_units()
    write_json(path.parent / 'units.json', {'people': prelude['people']})
    with pytest.raises(ModelError, match='unit of the prelude') as raised:
        load_scenario(path)
    assert [item['path'] for item in raised.value.diagnostics] == ['units/people']
    write_json(path.parent / 'units.json', {})
    vocabulary_path = tmp_path / catalogue.LIBRARY / 'vocabulary.json'
    vocabulary = json.loads(vocabulary_path.read_text())
    vocabulary['units']['days'] = prelude['days']
    write_json(vocabulary_path, vocabulary)
    with pytest.raises(ModelError, match='unit of the prelude') as raised:
        load_scenario(path)
    assert [item['path'] for item in raised.value.diagnostics] == ['library/units/days']


def test_local_record_dependencies_must_be_present(tmp_path):
    library = evidence_library()
    library['claims'][0]['related'] = [{'claim': 'LINKED', 'relation': 'context_limitations'}]
    library['claims'][0]['verification']['content_sha256'] = claim_digest(library['claims'][0])
    library['claims'].append(fixture_claim('LINKED'))
    path, _ = owned_files(tmp_path, library)
    claims_path = path.parent / 'evidence/claims.json'
    records = json.loads(claims_path.read_text())
    write_json(claims_path, [record for record in records if record['id'] != 'LINKED'])
    with pytest.raises(ModelError, match='Unknown claim LINKED'):
        load_library(path)


def test_unused_local_records_are_rejected_but_authoring_can_load_them(tmp_path):
    path, _ = owned_files(tmp_path)
    claims_path = path.parent / 'evidence/claims.json'
    records = json.loads(claims_path.read_text())
    records.append(fixture_claim('UNUSED'))
    write_json(claims_path, records)
    with pytest.raises(ModelError, match='Local record is not used'):
        load_scenario(path)
    assert any(record['id'] == 'UNUSED' for record in load_library(path, allow_unused=True)['claims'])


def test_another_scenario_neither_supplies_missing_records_nor_changes_identity(tmp_path):
    path, projected = owned_files(tmp_path)
    other = tmp_path / 'scenarios/SC98/evidence'
    write_json(other / 'claims.json', [fixture_claim('UNUSED')])
    write_json(other / 'sources.json', [{'id': 'src', 'title': 'Different independent copy'}])
    assert load_scenario(path).model_hash == projected.model_hash
    sources_path = path.parent / 'evidence/sources.json'
    write_json(sources_path, [])
    with pytest.raises(ModelError, match='Unknown source src'):
        load_scenario(path)


def test_record_array_shape_is_validated_before_merging(tmp_path):
    path, _ = owned_files(tmp_path)
    write_json(path.parent / 'evidence/claims.json', {'bad': 'shape'})
    with pytest.raises(ModelError, match='array of objects'):
        load_library(path)


def test_edits_to_owned_content_change_identity_without_changing_other_folders(tmp_path):
    path, first = owned_files(tmp_path)
    claims_path = path.parent / 'evidence/claims.json'
    records = json.loads(claims_path.read_text())
    records[0]['shows'] = 'Changed owned scientific content.'
    records[0]['verification']['content_sha256'] = claim_digest(records[0])
    write_json(claims_path, records)
    assert load_scenario(path).model_hash != first.model_hash


def test_each_owned_evidence_and_units_file_is_in_the_identity(tmp_path):
    """A change to each file of the model's own evidence (its sources, claims and assumptions) and to
    its local units changes the model hash, one file after another."""
    records = evidence_library()
    records['units']['care_slots'] = {'dimensions': {'care_slots': 1}, 'scale': 1}
    text = edit(sc99(), member('service', parameter('slots', 1, 'care_slots', 0, 2)))
    source, model = write_scenario(tmp_path, text, records)
    previous = model.model_hash
    files = {
        'sources': source.parent / 'evidence/sources.json',
        'claims': source.parent / 'evidence/claims.json',
        'assumptions': source.parent / 'evidence/assumptions.json',
        'units': source.parent / 'units.json',
    }
    for collection, path in files.items():
        contents = load_json(path)
        if collection == 'sources':
            contents[0]['title'] += ', revised'
        elif collection == 'claims':
            contents[0]['shows'] += ' Revised.'
            contents[0]['verification']['content_sha256'] = claim_digest(contents[0])
        elif collection == 'assumptions':
            contents[0]['rationale'] += ' Revised.'
        else:
            contents['care_slots']['description'] = 'Revised local unit description.'
        path.write_text(json.dumps(contents))
        current = load_scenario(source).model_hash
        assert current != previous, collection
        previous = current


def test_shared_unit_changes_change_identity(tmp_path):
    path, first = owned_files(tmp_path)
    vocabulary_path = tmp_path / catalogue.LIBRARY / 'vocabulary.json'
    vocabulary = json.loads(vocabulary_path.read_text())
    vocabulary['units']['people/h']['description'] = 'People per hour; a revised shared definition.'
    write_json(vocabulary_path, vocabulary)
    assert load_scenario(path).model_hash != first.model_hash
