"""A package owns its units and its evidence; the library that its main file names shares the rest
(`napkin/model/library.py`). The packages here are those of a synthetic catalogue in `tmp_path`
(`tests/evidence/support.py`): the package's folder owns its units and its records, and the shared
library its vocabulary.

A unit is in one place only: a units file never redefines a unit of the prelude or of the shared
library, nor does the library redefine a unit of the prelude, even with the same definition. Each
record that a used record rests on is there; a record of the package's folder that the model does not
use is refused, except to an author who loads the library to adopt or draft records; and each evidence
file holds an array of records. Another package's folder neither supplies a missing record nor
changes the hash of the model. That the hash covers no record and no label is in
`tests/language/test_packages.py` and `tests/evidence/test_index.py`.
"""

from __future__ import annotations

import json

import pytest

from napkin.model import ModelError, load_library, load_scenario
from napkin.model.evidence import claim_digest
from napkin.model.library import prelude_units
from tests.evidence.support import SERVICE, evidence_library, fixture_claim, write_package
from tools import catalogue


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def package(root, library=None):
    """The main file of the package SC99 below `root`, with the records of `library` in its folder."""
    return write_package(root, {'model.scn': SERVICE}, evidence_library() if library is None else library)


def refused(path, load=load_scenario):
    with pytest.raises(ModelError) as raised:
        load(path)
    return raised.value.diagnostics


def test_a_package_loads_with_its_own_units_and_records_and_the_shared_vocabulary(tmp_path):
    path = package(tmp_path)
    assert not (tmp_path / catalogue.LIBRARY / 'library.json').exists()
    library = load_library(path)
    # The prelude's units, the shared ones and the records of the package's folder.
    assert set(prelude_units()) <= set(library['units']) and 'people/h' in library['units']
    assert [claim['id'] for claim in library['claims']] == ['C-ACCESS', 'C-ACTION']
    assert load_scenario(path).configuration.request.horizon == 10


def test_a_local_unit_cannot_reuse_a_shared_name_even_with_the_same_definition(tmp_path):
    path = package(tmp_path)
    vocabulary = json.loads((tmp_path / catalogue.LIBRARY / 'vocabulary.json').read_text())
    write_json(path.parent / 'units.json', {'people/h': vocabulary['units']['people/h']})
    (found,) = refused(path)
    assert (found['code'], found['path']) == ('unit_collision', 'units/people/h')
    assert 'may not reuse a shared name' in found['message']


def test_no_units_file_and_no_library_redefines_a_unit_of_the_prelude(tmp_path):
    """The prelude's names are every model's: a units file and a library that write one, even with the
    prelude's own definition, are errors at that unit."""
    path = package(tmp_path)
    write_json(path.parent / 'units.json', {'people': prelude_units()['people']})
    assert [(item['code'], item['path']) for item in refused(path)] == [('unit_collision', 'units/people')]
    write_json(path.parent / 'units.json', {})
    vocabulary_path = tmp_path / catalogue.LIBRARY / 'vocabulary.json'
    vocabulary = json.loads(vocabulary_path.read_text())
    vocabulary['units']['days'] = prelude_units()['days']
    write_json(vocabulary_path, vocabulary)
    assert [(item['code'], item['path']) for item in refused(path)] == [
        ('unit_collision', 'library/units/days')
    ]


def test_each_record_that_a_used_record_rests_on_must_be_present(tmp_path):
    library = evidence_library()
    library['claims'][0]['related'] = [{'claim': 'LINKED', 'relation': 'context_limitations'}]
    library['claims'][0]['verification']['content_sha256'] = claim_digest(library['claims'][0])
    library['claims'].append(fixture_claim('LINKED'))
    path = package(tmp_path, library)
    claims_path = path.parent / 'evidence/claims.json'
    records = json.loads(claims_path.read_text())
    write_json(claims_path, [record for record in records if record['id'] != 'LINKED'])
    assert any('Unknown claim LINKED' in item['message'] for item in refused(path, load_library))


def test_an_unused_record_of_the_package_is_refused_but_an_author_can_load_it(tmp_path):
    path = package(tmp_path)
    claims_path = path.parent / 'evidence/claims.json'
    write_json(claims_path, [*json.loads(claims_path.read_text()), fixture_claim('UNUSED')])
    assert [(item['code'], item['path']) for item in refused(path)] == [
        ('unused_evidence', 'evidence/claims/UNUSED')
    ]
    assert 'UNUSED' in [claim['id'] for claim in load_library(path, allow_unused=True)['claims']]


def test_another_package_neither_supplies_a_missing_record_nor_changes_the_hash(tmp_path):
    path = package(tmp_path)
    first = load_scenario(path).model_hash
    other = tmp_path / 'scenarios/SC98/evidence'
    write_json(other / 'claims.json', [fixture_claim('UNUSED')])
    write_json(other / 'sources.json', [{'id': 'src', 'title': 'A copy in another package'}])
    assert load_scenario(path).model_hash == first
    write_json(path.parent / 'evidence/sources.json', [])
    assert any('Unknown source src' in item['message'] for item in refused(path))


def test_an_evidence_file_holds_an_array_of_records(tmp_path):
    path = package(tmp_path)
    write_json(path.parent / 'evidence/claims.json', {'bad': 'shape'})
    assert any('array of objects' in item['message'] for item in refused(path, load_library))
