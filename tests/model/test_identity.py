"""Independent content and implementation identities, with synthetic evidence graphs."""

import copy

import pytest

from napkin.model.evidence import claim_digest, dependencies, digest
from napkin.model.identity import library_content, reached
from napkin.model.ir import ModelError
from napkin.model.language import front
from tests.build import block, compiled, edit, evidence_library, fixture_claim, in_place, member, sc99


def with_noted_claims(*claims):
    """The text of SC99 whose notes cite `claims` with a record of a note (D-10)."""
    return edit(sc99(), member('notes:', block('benchmark:', in_place('source', 'The benchmark.', *claims))))


def test_dependency_closure_follows_records_assumptions_conventions_related_cycles_and_sources():
    document = {
        'basis': {'claim': 'direct'},
        'range': {'basis': [{'status': 'chosen'}, {'kind': 'source', 'links': [{'claim': 'context'}]}]},
        'notes:/benchmark:': {'kind': 'source', 'links': [{'claim': 'review'}], 'assumption': 'chosen'},
        # A plain list of IDs names nothing: only a record cites.
        'plain': {'source_claims': ['unused']},
        # A convention record names a convention of the library, which rests on its claims.
        'rule': {'kind': 'convention', 'convention': 'ROUND'},
    }
    library = {
        'assumptions': [{'id': 'chosen', 'supports': [{'claim': 'support'}]}],
        'conventions': [{'id': 'ROUND', 'supports': [{'claim': 'rule-support'}]}, {'id': 'UNCITED'}],
        'claims': [
            {'id': 'direct', 'source': 'one', 'related': [{'claim': 'next'}]},
            {'id': 'context', 'source': 'two'},
            {'id': 'review', 'source': 'one'},
            {'id': 'support', 'source': 'three'},
            {'id': 'rule-support', 'source': 'five'},
            {'id': 'next', 'source': 'four', 'related': [{'claim': 'last'}]},
            {'id': 'last', 'source': 'four', 'related': [{'claim': 'direct'}]},
            {'id': 'unused', 'source': 'outside'},
        ],
    }
    assert dependencies(document, library) == {
        'claims': ['direct', 'context', 'review', 'support', 'rule-support', 'next', 'last'],
        'assumptions': ['chosen'],
        'sources': ['one', 'two', 'three', 'five', 'four'],
        'conventions': ['ROUND'],
    }


def test_content_identity_ignores_other_evidence_order_and_storage_labels():
    library = evidence_library()
    library['claims'].append(fixture_claim('UNRELATED'))
    before = compiled(sc99(), library)
    changed = copy.deepcopy(library)
    changed['claims'][-1]['shows'] = 'A fact used by another model.'
    changed['claims'][-1]['verification']['content_sha256'] = claim_digest(changed['claims'][-1])
    changed['claims'].reverse()
    changed.update(
        id='different-storage-label', title='A different file title', metadata={'location': 'elsewhere'}
    )
    after = compiled(sc99(), changed)
    assert before.model_hash == after.model_hash
    assert before.library_hash == after.library_hash
    assert before.structures == after.structures


def test_the_evidence_of_a_note_and_related_evidence_are_local_model_content():
    library = evidence_library()
    library['claims'].extend(
        [
            fixture_claim('REVIEW', related=[{'claim': 'RELATED', 'relation': 'context_limitations'}]),
            fixture_claim('RELATED'),
        ]
    )
    text = with_noted_claims('REVIEW')
    before = compiled(text, library)
    library['claims'][-1]['shows'] = 'A changed related fact.'
    library['claims'][-1]['verification']['content_sha256'] = claim_digest(library['claims'][-1])
    after = compiled(text, library)
    assert before.model_hash != after.model_hash
    assert before.library_hash != after.library_hash
    assert before.structures == after.structures


def test_the_model_hash_covers_the_language_version_and_not_the_package_version(monkeypatch):
    """The identity of a model changes with the language (`ir.LANGUAGE_VERSION`), never with the version
    of the package (`napkin.__version__`), so a new release of the package keeps every saved edit."""
    import napkin
    import napkin.model.model as model_module

    before = compiled(sc99(), evidence_library())
    monkeypatch.setattr(napkin, '__version__', f'{napkin.__version__}.post1')
    assert compiled(sc99(), evidence_library()).model_hash == before.model_hash
    monkeypatch.setattr(model_module, 'LANGUAGE_VERSION', model_module.LANGUAGE_VERSION + '.next')
    assert compiled(sc99(), evidence_library()).model_hash != before.model_hash


def test_a_missing_claim_of_a_note_is_rejected():
    with pytest.raises(ModelError, match='Unknown claim MISSING'):
        compiled(with_noted_claims('MISSING'), evidence_library())


def test_the_hashes_cover_the_units_that_a_model_uses_and_the_projection_is_idempotent():
    """A unit of the library that the model does not use leaves both hashes, a used unit's definition
    is in them, and the content that the model reaches from that content is the same content."""
    library = evidence_library()
    before = compiled(sc99(), library)
    unused = copy.deepcopy(library)
    unused['units']['tonnes'] = {'dimensions': {'mass': 1}, 'scale': 1000}
    after = compiled(sc99(), unused)
    assert (after.model_hash, after.library_hash) == (before.model_hash, before.library_hash)
    # The model's library still reads every unit: an edit or a value may write any of them.
    assert 'tonnes' in after.library['units']
    changed = copy.deepcopy(library)
    changed['units']['people/h']['description'] = 'People per hour, described again.'
    again = compiled(sc99(), changed)
    assert again.model_hash != before.model_hash and again.library_hash != before.library_hash
    # What the evidence walkers read of the file: its projection, with the units that it writes.
    document = front.projection(front.read(sc99(), 'SC99.scn'))
    written = {item['unit'] for item in document['units']}
    effective, content = reached(document, library)
    assert set(content['units']) == written & set(library['units'])
    assert reached(document, effective)[1] == content
    assert digest(library_content(reached(document, content)[1])) == digest(library_content(content))
