"""A named record has one name in its model, and each line keeps its own records (spec, "Evidence at the
point of use").

A model names its records with `record name: kind "explanation"`. A citation `@name` names one of
them by its plain name: a member's name, or a name that no record has, is no record
(`unknown_record`), and a dotted name is no citation. A record is complete, with its kind and its
explanation, and never an alias of another record. The records of a value and of an option's line
are their own, whichever record another line cites.
"""

from __future__ import annotations

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

SERVICE = """\
scenario "Service"
    horizon 4 h

options "Rate":
    "Full rate":
        "The service runs at its rate."
    "Half rate":
        "The service runs at half its rate."
        service.rate = 1 person/h  @shared

runs:
    full = "Full rate"
    half = "Half rate"

service:
    "The service."
    input n: person = 10 person in [1 person, 100 person]  @shared
        "People"
    input rate: person/h = 2 person/h in [1 person/h, 4 person/h]  @service_shared
        "Rate of service"

record shared: identity "The root record."
record service_shared: identity "The local record."
"""
N = 'input n: person = 10 person in [1 person, 100 person]  @shared'


def problems(text):
    with pytest.raises(LanguageError) as raised:
        compile_text(text, UNITS)
    return [(item.code, item.line) for item in raised.value.problems]


def line_of(text, words):
    return next(number for number, row in enumerate(text.split('\n'), 1) if words in row)


@pytest.mark.parametrize(
    ('reference', 'code'),
    [
        # The model has the record service_shared, but no record service.
        ('service', 'unknown_record'),
        # A member's name is not the name of its records.
        ('n', 'unknown_record'),
        # A record has a plain name: a dotted name names no record.
        ('Missing.shared', 'syntax'),
        ('service.shared.extra', 'syntax'),
    ],
)
def test_a_citation_names_a_record_by_its_plain_name(reference, code):
    text = SERVICE.replace(N, N.replace('@shared', f'@{reference}'))
    assert problems(text) == [(code, line_of(text, 'input n:'))]


@pytest.mark.parametrize(
    'definition',
    ['record broken: shared', 'record broken: [shared]', 'record broken: identity'],
    ids=['alias', 'list', 'no explanation'],
)
def test_a_definition_is_a_complete_record_not_an_alias(definition):
    """A record that names another record, a list of names, and a record without its explanation
    are each refused at their own line."""
    text = SERVICE + definition + '\n'
    assert problems(text) == [('syntax', line_of(text, definition))]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason='bug: a second record of one name is accepted and replaces the first '
    '(napkin/model/semantic.py, Resolver.check_names reads no record)',
)
def test_a_record_name_is_declared_once():
    text = SERVICE + 'record shared: assumption "Another record of the same name."\n'
    try:
        compile_text(text, UNITS)
    except LanguageError as error:
        assert [(item.code, item.line) for item in error.problems] == [
            ('duplicate_name', line_of(text, 'Another record'))
        ]
    else:
        raise AssertionError('the model was accepted')


def test_values_and_options_keep_their_own_records():
    model = compile_text(SERVICE, UNITS).declared
    assert [item.name for item in model.part('service.n').evidence] == ['shared']
    assert [item.name for item in model.part('service.rate').evidence] == ['service_shared']
    (half,) = [option for option in model.options if option.name == 'Half rate']
    assert [item.name for setting in half.settings for item in setting.evidence] == ['shared']
    # A run of the option rests on the value's own record and on the option's.
    found = model.evidence('service.rate', 'service', ('Half rate',))
    assert [item.name for item in found] == ['service_shared', 'shared']
    # Two records are two contents, each under its own name.
    records = {record.name: (record.kind, record.text) for record in model.records}
    assert records == {
        'shared': ('identity', 'The root record.'),
        'service_shared': ('identity', 'The local record.'),
    }
