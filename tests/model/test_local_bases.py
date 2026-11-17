"""A named record has one name in its file, and each line keeps its own records.

A model file names its records at its end (docs/language.md, §2.10). A citation names one of
them by its plain name: a member's name, a dotted name or a name that no record has is no record. A
record is complete, with its kind and its explanation, and never an alias of another record. The
records of a value and of an option's line are their own, whichever record another line cites.
"""

import copy

import pytest

from napkin.model import ModelError
from napkin.model.evidence import basis_digest
from napkin.model.ir import freeze
from tests.build import append, compiled, edit, library, rejected, replace, scenario

# The lines of the analytic transfer that cite its record, `@fixture`.
N = 'input n: people = 10 people in 1 people to 100 people  @fixture'
RATE = 'input rate: people/day = 24 people/day in 1 people/day to 48 people/day  @fixture'
HALF_RATE = 'service.rate = 12 people/day  @fixture'
# The record of the analytic transfer, as the model holds it.
RECORD = {'kind': 'identity', 'explanation': 'Analytic contract fixture.'}
SHARED = 'record shared: identity "The root record."'
LOCAL = 'record service_shared: identity "The local record."'


def local_document(*records):
    """The analytic transfer with two more named records at its end, or with `records`."""
    return edit(scenario(), append(*(records or (SHARED, LOCAL))))


@pytest.mark.parametrize(
    ('reference', 'expected'),
    [
        # The file has the record service_shared, but no record shared.
        ('shared', ('basis', 'service/n')),
        # A member's name is not the name of its records.
        ('n', ('basis', 'service/n')),
        # A record has a plain name: a dotted name names no record.
        ('Missing.shared', ('syntax', '')),
        ('Service.shared.extra', ('syntax', '')),
    ],
    ids=['shared', 'Service.n', 'Missing.shared', 'Service.shared.extra'],
)
def test_no_fallback_or_member_lookup(reference, expected):
    text = edit(local_document(LOCAL), replace(N, N.replace('@fixture', f'@{reference}')))
    assert expected in rejected(text, library())


@pytest.mark.parametrize(
    'definition',
    ['record broken: shared', 'record broken: [shared]', 'record broken: identity'],
    ids=['shared', 'definition1', 'definition2'],
)
def test_a_definition_is_a_complete_record_not_an_alias(definition):
    """A record that names another record, a list of names, and a record without its explanation
    are each rejected at their own line."""
    text = local_document(SHARED, LOCAL, definition)
    with pytest.raises(ModelError) as raised:
        compiled(text)
    line = text.split('\n').index(definition) + 1
    assert [(d['code'], d['line']) for d in raised.value.diagnostics] == [('syntax', line)]


def test_values_and_options_keep_their_own_records():
    text = edit(
        local_document(),
        replace(N, N.replace('@fixture', '@shared')),
        replace(RATE, RATE.replace('@fixture', '@service_shared')),
        replace(HALF_RATE, 'service.rate = 12 people/day  @shared'),
    )
    model = compiled(text)
    assert model.inputs['service.n']['basis']['name'] == 'shared'
    assert model.inputs['service.rate']['basis']['name'] == 'service_shared'
    assert model.inputs['service.rate']['options']['Half rate']['basis']['name'] == 'shared'
    # Two records are two contents, and each name of the file names one of the model's records.
    aliases = model.evidence['aliases']
    assert aliases['shared'] != aliases['service_shared']
    assert set(aliases.values()) <= model.evidence['records'].keys()


def test_content_identity_excludes_alias_and_location_but_preserves_content():
    record = copy.deepcopy(RECORD)
    assert basis_digest(record) == basis_digest(
        {**record, 'name': 'service_shared', 'location': 'here', 'line': 3, 'path': 'there', 'file': 'x'}
    )
    assert basis_digest(record) != basis_digest({**record, 'explanation': 'Different support.'})
    nested = {**record, 'links': [{'claim': 'example', 'datum': 'count'}]}
    assert basis_digest(nested) == basis_digest(freeze(nested))
