"""The owner's evidence rule (item 16 of the plan's changes after G0, `napkin/model/support.py`): a
warning, code `no_record`, for each part that rests on no record, of the kinds for which the
compiler before the rewrite refused a model, at the part's line. A value that an option or a
`change` sets keeps its error (R-A5-05). The lines below are counted by hand in the texts."""

import textwrap

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

TEXT = """\
record fixture: assumption "A fixture of a test."
plant:
    input rate: L/h = 2 L/h
    input name: text = "north"
    input cited: L/h = 1 L/h  @fixture
    water: L = 8 L
    safe: bool = true
    mode: enum[ON, OFF] = ON
    share = formula(this.water / 8 L)
    fill = event():
        after 1 h:
            this.water += 1 L
    assert this.water >= 0 L
    status ok when this.safe
    status degraded
quiet:
    "A thing with a record, on which its yes/no and its status rest."
    @fixture
    on: bool = true
    status ok when this.on
    status failed
Utility:
    capacity: L = 5 L  @fixture
north: Utility
    capacity = 7 L
south: Utility
    capacity = 6 L  @fixture
top = 3
"""


def warned(text, tables=None):
    found = compile_text(textwrap.dedent(text), UNITS, tables=tables).reports
    return [(item.message.split(':')[0], item.message.split(': ')[1], item.line, item.file) for item in found]


def test_each_part_of_a_kind_that_needs_a_record_and_has_none_is_a_warning_at_its_line():
    """An input but a text, a stored number or yes/no, a timed event, an assertion, a case of a
    status display, a member's own value and a stored value of the top level; a yes/no and a status
    rest on their thing's records."""
    assert warned(TEXT) == [
        ('plant.rate', 'an input rests on no record', 3, ''),
        ('plant.water', 'a stored value rests on no record', 6, ''),
        ('plant.safe', 'a stored value rests on no record', 7, ''),
        ('plant.fill', 'an event that acts at a time rests on no record', 10, ''),
        ('plant.assert[0]', 'an assertion rests on no record', 13, ''),
        ('plant.status.case[0]', 'a case of a status display rests on no record', 14, ''),
        ('plant.status.case[1]', 'a case of a status display rests on no record', 15, ''),
        ('north.capacity', "a member's own value rests on no record", 25, ''),
        ('top', 'a stored value rests on no record', 28, ''),
    ]
    (first,) = [item for item in compile_text(TEXT, UNITS).reports if item.line == 3]
    assert first.code == 'no_record'


def test_a_record_on_each_part_leaves_no_warning():
    cited = TEXT.replace('= 2 L/h\n', '= 2 L/h  @fixture\n').replace('plant:\n', 'plant:\n    @fixture\n')
    for line in (
        'water: L = 8 L',
        'fill = event():',
        'assert this.water >= 0 L',
        'capacity = 7 L',
        'top = 3',
    ):
        cited = cited.replace(f'{line}\n', f'{line}  @fixture\n')
    assert warned(cited) == []


def test_a_column_of_a_table_rests_on_the_records_of_its_header():
    text = 'record fixture: assumption "A fixture."\nSite:\n    level: L = 0 L  @fixture\nsites: Site from "sites.csv"\n'
    assert warned(text, {'sites.csv': 'id,level: L\na,1\nb,2\n'}) == [
        ('sites.level', 'a column of a table rests on no record', 1, 'sites.csv')
    ]
    assert warned(text, {'sites.csv': 'id,level: L @fixture\na,1\nb,2\n'}) == []


def test_a_value_that_an_option_sets_with_no_record_stays_an_error():
    text = TEXT + 'options "Pace":\n    "Fast":\n        "Faster."\n        plant.rate = 4 L/h\n'
    with pytest.raises(LanguageError) as caught:
        compile_text(text, UNITS)
    assert caught.value.codes == ['record']
